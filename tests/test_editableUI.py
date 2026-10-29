from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialogButtonBox

from mpfmanager.core import compatibilityManager, uvManager
from mpfmanager.core.compatibilityManager import PyPIRelease
from mpfmanager.core.storageManager import StorageProcessor, VirtualEnvironment
from mpfmanager.ui import mainWindow
from mpfmanager.ui.dialogs import VENVManagementDialog, venvDialogData
from mpfmanager.ui.mainWindow import MainWindow

RELEASES = {
    "mpf": [PyPIRelease("0.80.0", ">=3.8"), PyPIRelease("0.57.0", ">=3.8")],
    "mpf-mc": [PyPIRelease("0.57.0", ">=3.8")],
    "mpf-monitor": [PyPIRelease("1.0.0", ">=3.8")],
}


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MPF_MANAGER_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(compatibilityManager, "pypiReleaseRetriever", lambda package: RELEASES[package])
    monkeypatch.setattr(uvManager, "listPythonVersions", lambda: {"3.13"})


def _fakeSource(root: Path, requiresPython: str = ">=3.10,<3.15") -> Path:
    (root / "mpf").mkdir(parents=True)
    (root / "mpf" / "_version.py").write_text("__version__ = '0.82.0.dev0'\n__gmc_version__ = '1.0.0'\n")
    (root / "pyproject.toml").write_text(f'[project]\nname = "mpf"\nrequires-python = "{requiresPython}"\n')
    return root


def _okEnabled(dialog: VENVManagementDialog) -> bool:
    return dialog.dialogButtons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()


def _loadedDialog(qtbot, store, venvObject=None) -> VENVManagementDialog:
    dialog = VENVManagementDialog(store, None, venvObject)
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: bool(dialog.availableReleases))
    return dialog


def test_editableSourcePlansEditableInstall(qtbot, tmp_path):
    dialog = _loadedDialog(qtbot, StorageProcessor())
    dialog.sourceChoice.setCurrentIndex(dialog.sourceChoice.findData("editable"))
    assert not _okEnabled(dialog)
    assert "Choose an MPF source folder" in dialog.operationStatus.text()

    dialog.editableSourceEdit.setText(str(_fakeSource(tmp_path / "mpf-src")))
    assert dialog.dialogMPFVersion.currentData() == "0.82.0.dev0"
    assert dialog.venvDialogName.text() == f"mpf-0.82.0.dev0-editable-py{dialog.pythonVersionDialog.currentData()}"
    dialog.mpfAddOnDialogs["mpf-monitor"].setChecked(True)
    assert _okEnabled(dialog)

    plan = dialog.plan()
    assert plan.editableMPFPath == tmp_path / "mpf-src"
    assert plan.mpfVersion == "0.82.0.dev0"
    assert plan.mpfVersionRequirements == ["mpf-monitor==1.0.0"]
    assert plan.companionPackages == ["mpf-monitor"]


def test_invalidEditableSourceBlocksOk(qtbot, tmp_path):
    dialog = _loadedDialog(qtbot, StorageProcessor())
    dialog.sourceChoice.setCurrentIndex(dialog.sourceChoice.findData("editable"))
    dialog.editableSourceEdit.setText(str(tmp_path))
    assert not _okEnabled(dialog)
    assert "does not look like an MPF source folder" in dialog.operationStatus.text()


def test_switchingBackToPyPIPinsRelease(qtbot, tmp_path):
    dialog = _loadedDialog(qtbot, StorageProcessor())
    dialog.sourceChoice.setCurrentIndex(dialog.sourceChoice.findData("editable"))
    dialog.editableSourceEdit.setText(str(_fakeSource(tmp_path / "mpf-src")))
    dialog.sourceChoice.setCurrentIndex(dialog.sourceChoice.findData("pypi"))
    plan = dialog.plan()
    assert plan.editableMPFPath is None
    assert plan.mpfVersionRequirements == ["mpf==0.80.0"]


def test_existingEditableEnvironmentStartsOnItsSource(qtbot, tmp_path):
    source = _fakeSource(tmp_path / "mpf-src")
    environment = VirtualEnvironment("env", str(tmp_path / "env"), "3.13", "0.82.0.dev0", [], str(source))
    dialog = _loadedDialog(qtbot, StorageProcessor(), environment)
    assert dialog.sourceChoice.currentData() == "editable"
    assert dialog.dialogMPFVersion.currentData() == "0.82.0.dev0"
    assert _okEnabled(dialog)


def test_editableSourceMustSupportEnvironmentPython(qtbot, tmp_path):
    source = _fakeSource(tmp_path / "mpf-src", ">=3.10,<3.12")
    environment = VirtualEnvironment("env", str(tmp_path / "env"), "3.13", "0.80.0")
    dialog = _loadedDialog(qtbot, StorageProcessor(), environment)
    dialog.sourceChoice.setCurrentIndex(dialog.sourceChoice.findData("editable"))
    dialog.editableSourceEdit.setText(str(source))
    assert not _okEnabled(dialog)
    assert "needs Python" in dialog.operationStatus.text()


def test_applyPlanInstallsEditableAndSavesSource(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(uvManager, "locateUV", lambda: "uv")
    window = MainWindow(StorageProcessor())
    qtbot.addWidget(window)
    ranCommands = []
    monkeypatch.setattr(
        window.commandQueue, "run", lambda commands, onDone: (ranCommands.extend(commands), onDone(True))
    )

    plan = venvDialogData(
        venvName="dev-env",
        venvPath=tmp_path / "dev-env",
        pythonVersion="3.13",
        mpfVersion="0.82.0.dev0",
        mpfVersionRequirements=[],
        companionPackages=[],
        packagesToRemove=[],
        editableMPFPath=tmp_path / "mpf-src",
    )
    window._applyPlan(plan, create=True)

    assert ranCommands[-1][-2:] == ["-e", str(tmp_path / "mpf-src")]
    environment = window.storedData.getVENVbyName("dev-env")
    assert environment is not None
    assert environment.editableMPFPath == str(tmp_path / "mpf-src")
    versionItem = window.venvAvailableTable.item(0, 1)
    assert versionItem is not None
    assert versionItem.text() == "0.82.0.dev0  (editable)"


def test_verifyEditableReadsVersionFromSource(qtbot, tmp_path, monkeypatch):
    source = _fakeSource(tmp_path / "mpf-src")
    store = StorageProcessor()
    store.addVENV(VirtualEnvironment("env", str(tmp_path / "env"), "3.13", "0.81.0.dev0", [], str(source)))
    monkeypatch.setattr(mainWindow.uvCMDs, "listVENVPackages", lambda _path: {"mpf": "0.81.0.dev0"})

    window = MainWindow(store)
    qtbot.addWidget(window)
    window.venvAvailableTable.selectRow(0)
    assert window.openSourceButton.isEnabled()
    window.verifyVENVPackages()

    environment = store.getVENVbyName("env")
    assert environment is not None
    qtbot.waitUntil(lambda: environment.installedMPFVersion == "0.82.0.dev0")
