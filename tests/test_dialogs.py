import runpy
import sys

import pytest
from PySide6.QtWidgets import QDialogButtonBox

import mpfmanager
from mpfmanager import app
from mpfmanager.core import compatibilityManager, uvManager
from mpfmanager.core.compatibilityManager import PyPIRelease
from mpfmanager.core.storageManager import Settings, StorageProcessor, VirtualEnvironment
from mpfmanager.ui import dialogs
from mpfmanager.ui.dialogs import SettingsDialog, VENVManagementDialog, environmentPairing

RELEASES = {
    "mpf": [PyPIRelease("0.80.0", ">=3.8"), PyPIRelease("0.80.1.dev1", ">=3.10"), PyPIRelease("0.57.0", ">=3.7")],
    "mpf-mc": [PyPIRelease("0.57.0", ">=3.7")],
    "mpf-monitor": [PyPIRelease("1.0.0", ">=3.8")],
}


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MPF_MANAGER_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(compatibilityManager, "pypiReleaseRetriever", lambda package: RELEASES[package])
    monkeypatch.setattr(uvManager, "listPythonVersions", lambda: {"3.12"})


def _loadedDialog(qtbot, store, venvObject=None) -> VENVManagementDialog:
    dialog = VENVManagementDialog(store, None, venvObject)
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: bool(dialog.availableReleases))
    return dialog


def _okEnabled(dialog: VENVManagementDialog) -> bool:
    return dialog.dialogButtons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()


def test_settingsDialogAppliesSettings(qtbot):
    settings = Settings("/envs", "/projects", False, "")
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)
    dialog.venvDirectoryDialog.setText(" /new-envs ")
    dialog.projectDirectoryDialog.setText("/new-projects")
    dialog.preReleasesCheckBox.setChecked(True)
    dialog.godotExecutableDialog.setText("/opt/godot")
    dialog.applySettings(settings)
    assert settings == Settings("/new-envs", "/new-projects", True, "/opt/godot")


def test_settingsDialogDetectsGodot(qtbot, monkeypatch):
    dialog = SettingsDialog(Settings())
    qtbot.addWidget(dialog)
    monkeypatch.setattr(dialogs.mpfProjects, "detectGodotExecutable", lambda: "/usr/bin/godot")
    dialog._detectGodot()
    assert dialog.godotExecutableDialog.text() == "/usr/bin/godot"

    shown = []
    monkeypatch.setattr(dialogs.mpfProjects, "detectGodotExecutable", lambda: None)
    monkeypatch.setattr(dialogs.QMessageBox, "information", lambda *args: shown.append(args[2]))
    dialog._detectGodot()
    assert shown and "could not be found" in shown[0]


def test_venvDialogLoadsReleasesAndSuggestsName(qtbot):
    dialog = _loadedDialog(qtbot, StorageProcessor())
    assert dialog.dialogMPFVersion.currentData() == "0.80.0"
    assert dialog.venvDialogName.text() == "mpf-0.80.0-py3.14"
    assert dialog.pythonVersionDialog.itemText(dialog.pythonVersionDialog.findData("3.12")) == "3.12  (installed)"
    assert _okEnabled(dialog)

    dialog.preReleaseCheckbox.setChecked(True)
    assert dialog.dialogMPFVersion.findData("0.80.1.dev1") >= 0


def test_venvDialogKeepsEditedName(qtbot):
    dialog = _loadedDialog(qtbot, StorageProcessor())
    dialog.venvDialogName.setText("mine")
    dialog.venvDialogName.textEdited.emit("mine")
    dialog.dialogMPFVersion.setCurrentIndex(dialog.dialogMPFVersion.findData("0.57.0"))
    assert dialog.venvDialogName.text() == "mine"


def test_venvDialogAddOnsFollowMPFVersion(qtbot):
    dialog = _loadedDialog(qtbot, StorageProcessor())
    assert not dialog.mpfAddOnDialogs["mpf-mc"].isEnabled()
    dialog.dialogMPFVersion.setCurrentIndex(dialog.dialogMPFVersion.findData("0.57.0"))
    assert dialog.mpfAddOnDialogs["mpf-mc"].isEnabled()
    dialog.mpfAddOnDialogs["mpf-mc"].setChecked(True)
    plan = dialog.plan()
    assert plan.mpfVersionRequirements == ["mpf==0.57.0", "mpf-mc==0.57.0"]
    assert plan.companionPackages == ["mpf-mc"]
    assert plan.venvPath == dialog.venvParentFolderPath() / plan.venvName


@pytest.mark.parametrize(
    ("name", "message"),
    [("", "Enter a name."), ("a/b", "The name cannot contain path separators."), ("taken", "already exists")],
)
def test_venvDialogValidatesName(qtbot, tmp_path, name, message):
    store = StorageProcessor()
    store.addVENV(VirtualEnvironment("taken", str(tmp_path / "taken"), "3.12", "0.80.0"))
    dialog = _loadedDialog(qtbot, store)
    dialog.venvDialogName.setText(name)
    assert not _okEnabled(dialog)
    assert message in dialog.operationStatus.text()


def test_venvDialogValidatesLocation(qtbot, tmp_path):
    dialog = _loadedDialog(qtbot, StorageProcessor())
    dialog.venvParentLocation.setText("")
    assert dialog.operationStatus.text() == "Choose a folder for the environment."
    (tmp_path / "file").write_text("")
    dialog.venvParentLocation.setText(str(tmp_path / "file"))
    assert "is not a folder" in dialog.operationStatus.text()
    dialog.venvParentLocation.setText(str(tmp_path))
    (tmp_path / dialog.venvDialogName.text()).mkdir()
    dialog.venvDialogName.setText(dialog.venvDialogName.text())
    dialog._validateVENV()
    assert "already exists" in dialog.operationStatus.text()


def test_venvDialogEditingPlansRemovals(qtbot, tmp_path):
    environment = VirtualEnvironment("env", str(tmp_path / "env"), "3.12", "0.80.0", ["mpf-monitor"])
    dialog = _loadedDialog(qtbot, StorageProcessor(), environment)
    assert dialog.windowTitle() == "Change MPF version"
    assert dialog.dialogMPFVersion.currentText() == "0.80.0  (current)"
    assert dialog.pythonVersionDialog.currentData() == "3.12"
    dialog.mpfAddOnDialogs["mpf-monitor"].setChecked(False)
    plan = dialog.plan()
    assert plan.packagesToRemove == ["mpf-monitor"]
    assert plan.venvPath == environment.venvPath


def test_venvDialogReportsPyPIFailure(qtbot, monkeypatch):
    def offline(_package):
        raise ConnectionError("offline")

    monkeypatch.setattr(compatibilityManager, "pypiReleaseRetriever", offline)
    dialog = VENVManagementDialog(StorageProcessor())
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: "Could not load releases from PyPI: offline" in dialog.operationStatus.text())
    assert not _okEnabled(dialog)


def test_venvDialogWithoutUVPythons(qtbot, monkeypatch):
    def noUV():
        raise uvManager.UvNotFoundError("missing")

    monkeypatch.setattr(uvManager, "listPythonVersions", noUV)
    dialog = _loadedDialog(qtbot, StorageProcessor())
    assert dialog.installedVENVPackages == set()


def test_environmentPairing(qtbot, tmp_path):
    store = StorageProcessor()
    store.addVENV(VirtualEnvironment("a", str(tmp_path / "a"), "3.12", "0.80.0"))
    store.addVENV(VirtualEnvironment("b", str(tmp_path / "b"), "3.11", "0.57.0"))
    combo = environmentPairing(store, "b")
    qtbot.addWidget(combo)
    assert combo.count() == 3
    assert combo.currentData() == "b"
    assert "MPF 0.57.0, Python 3.11" in combo.currentText()
    unknown = environmentPairing(store, "missing")
    qtbot.addWidget(unknown)
    assert unknown.currentData() is None


def test_newProjectDialogValidation(qtbot, tmp_path):
    store = StorageProcessor()
    dialog = dialogs.mpfProjectCreationDialog(store)
    qtbot.addWidget(dialog)
    assert dialog.operationStatus.text() == "Enter a project name."
    dialog.projectParentFolder.setText(str(tmp_path))
    dialog.projectName.setText("a:b")
    assert "path separators" in dialog.operationStatus.text()
    (tmp_path / "exists").mkdir()
    dialog.projectName.setText("exists")
    assert "already exists" in dialog.operationStatus.text()
    dialog.projectName.setText("new")
    assert dialog.operationStatus.text() == ""
    assert dialog.projectPath() == tmp_path / "new"


def test_browseButtonsFillInChoices(qtbot, monkeypatch):
    monkeypatch.setattr(dialogs.QFileDialog, "getExistingDirectory", lambda *_args: "/chosen/folder")
    monkeypatch.setattr(dialogs.QFileDialog, "getOpenFileName", lambda *_args: ("/chosen/godot", ""))
    dialog = SettingsDialog(Settings())
    qtbot.addWidget(dialog)
    for button in dialog.findChildren(dialogs.QPushButton):
        if button.text() == "Browse…":
            button.click()
    assert dialog.venvDirectoryDialog.text() == "/chosen/folder"
    assert dialog.godotExecutableDialog.text() == "/chosen/godot"


def test_packageMainStartsApp(monkeypatch):
    started = []
    monkeypatch.setattr(app, "main", lambda: started.append(True))
    mpfmanager.main()
    assert started == [True]


def test_runningPackageAsModuleStartsApp(monkeypatch):
    started = []
    monkeypatch.setattr(mpfmanager, "main", lambda: started.append(True))
    monkeypatch.delitem(sys.modules, "mpfmanager.__main__", raising=False)
    runpy.run_module("mpfmanager", run_name="__main__")
    assert started == [True]


def test_appMainShowsWindowAndExitsWithAppCode(monkeypatch):
    events = []

    class FakeApplication:
        def __init__(self, argv):
            events.append(("app", argv))

        def setApplicationName(self, name):
            events.append(("name", name))

        def exec(self):
            return 7

    class FakeWindow:
        def show(self):
            events.append(("show",))

    monkeypatch.setattr(app, "QApplication", FakeApplication)
    monkeypatch.setattr(app, "MainWindow", FakeWindow)
    with pytest.raises(SystemExit) as exited:
        app.main()
    assert exited.value.code == 7
    assert ("name", "mpf-Manager") in events and ("show",) in events
