from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialogButtonBox

from mpfmanager.core import gmcManager
from mpfmanager.core.storageManager import Project, StorageProcessor, VirtualEnvironment
from mpfmanager.ui import dialogs
from mpfmanager.ui.dialogs import GMCProjectDialog, mpfProjectCreationDialog
from mpfmanager.ui.mainWindow import MainWindow


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MPF_MANAGER_HOME", str(tmp_path / "home"))


def _store(tmp_path: Path, mpfVersion: str = "0.82.0") -> StorageProcessor:
    store = StorageProcessor()
    store.addVENV(VirtualEnvironment("env", str(tmp_path / "env"), "3.13", mpfVersion))
    (tmp_path / "machine").mkdir()
    store.addProject(Project("machine", str(tmp_path / "machine"), "env"))
    return store


def _okEnabled(dialog: GMCProjectDialog) -> bool:
    return dialog.gmcDialogButtons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()


def test_gmcDialogPreselectsVersionMPFRequires(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(gmcManager, "listGMCVersions", lambda: ["1.0.0", "0.1.6"])
    project = Project("machine", str(tmp_path))
    dialog = GMCProjectDialog(project, "0.1.6", None)
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: dialog.gmcVersion.count() == 2)
    assert dialog.gmcVersion.currentData() == "0.1.6"
    assert _okEnabled(dialog)

    (tmp_path / "project.godot").write_text("")
    dialog.gmcLocation.setText(str(tmp_path) + "/")
    assert not _okEnabled(dialog)


def test_gmcDialogFallsBackToMPFVersionWhenOffline(qtbot, tmp_path, monkeypatch):
    def offline():
        raise ConnectionError("offline")

    monkeypatch.setattr(gmcManager, "listGMCVersions", offline)
    dialog = GMCProjectDialog(Project("machine", str(tmp_path)), "1.0.0", None)
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: "offline" in dialog.operationStatus.text())
    assert dialog.gmcVersion.currentData() == "1.0.0"
    assert _okEnabled(dialog)


def test_newProjectGMCOptionNeedsEligibleEnvironment(qtbot, tmp_path):
    store = StorageProcessor()
    store.addVENV(VirtualEnvironment("old", str(tmp_path / "old"), "3.11", "0.57.0"))
    store.addVENV(VirtualEnvironment("new", str(tmp_path / "new"), "3.13", "0.80.0"))
    dialog = mpfProjectCreationDialog(store, None)
    qtbot.addWidget(dialog)
    assert not dialog.createGMCCheckBox.isEnabled()
    dialog.environmentPair.setCurrentIndex(dialog.environmentPair.findData("old"))
    assert not dialog.createGMCCheckBox.isEnabled()
    dialog.environmentPair.setCurrentIndex(dialog.environmentPair.findData("new"))
    assert dialog.createGMCCheckBox.isEnabled()


def test_createGMCButtonOnlyForEligibleEnvironment(qtbot, tmp_path):
    window = MainWindow(_store(tmp_path, "0.57.0"))
    qtbot.addWidget(window)
    window.projectListTable.selectRow(0)
    assert not window.createGMCButton.isEnabled()

    environment = window.storedData.getVENVbyName("env")
    assert environment is not None
    environment.installedMPFVersion = "0.80.0"
    window.refreshMainWindow()
    window.projectListTable.selectRow(0)
    assert window.createGMCButton.isEnabled()


def test_createGMCProjectEndToEnd(qtbot, tmp_path, monkeypatch):
    addon = tmp_path / "cache-src" / "addons" / "mpf-gmc"
    addon.mkdir(parents=True)
    (addon / "plugin.cfg").write_text("[plugin]")
    fetched = []
    monkeypatch.setattr(gmcManager, "requiredGMCVersion", lambda _environment: "1.0.0")
    monkeypatch.setattr(gmcManager, "listGMCVersions", lambda: ["1.0.0"])
    monkeypatch.setattr(gmcManager, "fetchGMCAddon", lambda version, cache: fetched.append((version, cache)) or addon)

    # exec is replaced by waiting for the versions to load, then accepting like the user pressing OK
    def acceptOnceLoaded(dialog):
        qtbot.waitUntil(lambda: dialog.gmcVersion.count() > 0)
        return 1

    monkeypatch.setattr(dialogs.GMCProjectDialog, "exec", acceptOnceLoaded)

    window = MainWindow(_store(tmp_path))
    qtbot.addWidget(window)
    window.projectListTable.selectRow(0)
    window.createGMCProject()

    project = window.storedData.getProjectbyPath(str(tmp_path / "machine"))
    assert project is not None
    qtbot.waitUntil(lambda: project.gmcFolderPath is not None, timeout=5000)
    assert project.gmcFolderPath == str(tmp_path / "machine")
    assert fetched == [("1.0.0", window.storedData.gmcCachePath)]
    machine = tmp_path / "machine"
    assert (machine / "project.godot").is_file()
    environment = window.storedData.getVENVbyName("env")
    assert environment is not None
    assert f'executable_path="{environment.executable("mpf").as_posix()}"' in (machine / "gmc.cfg").read_text()
    assert "Skipped the asset import" in window.outputViewer.toPlainText()


def test_changingEnvironmentUpdatesGMCConfig(qtbot, tmp_path):
    store = _store(tmp_path)
    store.addVENV(VirtualEnvironment("other", str(tmp_path / "other"), "3.13", "0.82.0"))
    machine = tmp_path / "machine"
    (machine / "gmc.cfg").write_text('[mpf]\n\nexecutable_path="/old/mpf"\n')
    store.setProjectGMCPath(str(machine), str(machine))

    window = MainWindow(store)
    qtbot.addWidget(window)
    window._setProjectEnvironment(str(machine), "other")
    otherEnvironment = store.getVENVbyName("other")
    assert otherEnvironment is not None
    assert f'executable_path="{otherEnvironment.executable("mpf").as_posix()}"' in (machine / "gmc.cfg").read_text()
