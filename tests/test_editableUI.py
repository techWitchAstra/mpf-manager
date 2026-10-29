from pathlib import Path

import pytest
from PySide6.QtWidgets import QDialogButtonBox

from mpfmanager.core import compatibilityManager, sourceManager, uvManager
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
    dialog.sourceChoice.setCurrentIndex(dialog.sourceChoice.findData("local"))
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
    dialog.sourceChoice.setCurrentIndex(dialog.sourceChoice.findData("local"))
    dialog.editableSourceEdit.setText(str(tmp_path))
    assert not _okEnabled(dialog)
    assert "does not look like an MPF source folder" in dialog.operationStatus.text()


def test_switchingBackToPyPIPinsRelease(qtbot, tmp_path):
    dialog = _loadedDialog(qtbot, StorageProcessor())
    dialog.sourceChoice.setCurrentIndex(dialog.sourceChoice.findData("local"))
    dialog.editableSourceEdit.setText(str(_fakeSource(tmp_path / "mpf-src")))
    dialog.sourceChoice.setCurrentIndex(dialog.sourceChoice.findData("pypi"))
    plan = dialog.plan()
    assert plan.editableMPFPath is None
    assert plan.mpfVersionRequirements == ["mpf==0.80.0"]


def test_existingEditableEnvironmentStartsOnItsSource(qtbot, tmp_path):
    source = _fakeSource(tmp_path / "mpf-src")
    environment = VirtualEnvironment("env", str(tmp_path / "env"), "3.13", "0.82.0.dev0", [], str(source))
    dialog = _loadedDialog(qtbot, StorageProcessor(), environment)
    assert dialog.sourceChoice.currentData() == "local"
    assert dialog.dialogMPFVersion.currentData() == "0.82.0.dev0"
    assert _okEnabled(dialog)


def test_editableSourceMustSupportEnvironmentPython(qtbot, tmp_path):
    source = _fakeSource(tmp_path / "mpf-src", ">=3.10,<3.12")
    environment = VirtualEnvironment("env", str(tmp_path / "env"), "3.13", "0.80.0")
    dialog = _loadedDialog(qtbot, StorageProcessor(), environment)
    dialog.sourceChoice.setCurrentIndex(dialog.sourceChoice.findData("local"))
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


def _githubDialog(qtbot, monkeypatch, store, venvObject=None, branches=("dev", "0.82.x"), versions=None):
    versions = versions or {"dev": "0.82.0.dev0", "0.82.x": "0.82.0.dev1"}
    monkeypatch.setattr(sourceManager, "listMPFBranches", lambda: list(branches))
    monkeypatch.setattr(sourceManager.shutil, "which", lambda _name: "git")
    monkeypatch.setattr(
        sourceManager,
        "readRemoteMPFSource",
        lambda branchName, path: sourceManager.LocalMPFSource(path, versions[branchName], ">=3.10,<3.15", "1.0.0"),
    )
    dialog = _loadedDialog(qtbot, store, venvObject)
    dialog.sourceChoice.setCurrentIndex(dialog.sourceChoice.findData("github"))
    qtbot.waitUntil(lambda: dialog.dialogMPFVersion.count() == 1)
    return dialog


def test_githubSourcePlansCloneOfDevBranch(qtbot, tmp_path, monkeypatch):
    store = StorageProcessor()
    dialog = _githubDialog(qtbot, monkeypatch, store)
    sourcePath = store.homePath / "mpf-sources" / "mpf-dev"
    assert dialog.githubBranch.currentData() == "dev"
    assert dialog.dialogMPFVersion.currentText() == "0.82.0.dev0  (editable, dev)"
    assert dialog.githubLocation.text() == str(sourcePath)
    assert dialog.venvDialogName.text().startswith("mpf-0.82.0.dev0-dev-py")
    assert _okEnabled(dialog)

    plan = dialog.plan()
    assert plan.editableMPFPath == sourcePath
    assert plan.editableMPFRef == "dev"
    assert plan.sourceCommands == [["git", "clone", "--branch", "dev", sourceManager.MPF_GIT_URL, str(sourcePath)]]
    assert plan.mpfVersionRequirements == []


def test_githubBranchChangeRereadsVersion(qtbot, tmp_path, monkeypatch):
    dialog = _githubDialog(qtbot, monkeypatch, StorageProcessor())
    dialog.githubBranch.setCurrentIndex(dialog.githubBranch.findData("0.82.x"))
    qtbot.waitUntil(lambda: dialog.dialogMPFVersion.currentData() == "0.82.0.dev1")
    assert dialog.plan().editableMPFRef == "0.82.x"


def test_githubExistingCheckoutIsUpdated(qtbot, tmp_path, monkeypatch):
    store = StorageProcessor()
    _fakeSource(store.homePath / "mpf-sources" / "mpf-dev")
    dialog = _githubDialog(qtbot, monkeypatch, store)
    assert "will be updated (git pull)" in dialog.operationStatus.text()
    assert dialog.plan().sourceCommands[0][-4:] == ["pull", "--ff-only", "origin", "dev"]


def test_githubFolderHoldingSomethingElseBlocksOk(qtbot, tmp_path, monkeypatch):
    store = StorageProcessor()
    otherFolder = store.homePath / "mpf-sources" / "mpf-dev"
    otherFolder.mkdir(parents=True)
    (otherFolder / "notes.txt").write_text("x")
    dialog = _githubDialog(qtbot, monkeypatch, store)
    assert not _okEnabled(dialog)
    assert "is not an MPF source folder" in dialog.operationStatus.text()


def test_githubBranchListFailureIsShown(qtbot, tmp_path, monkeypatch):
    def noGit():
        raise FileNotFoundError("git could not be found")

    monkeypatch.setattr(sourceManager, "listMPFBranches", noGit)
    dialog = _loadedDialog(qtbot, StorageProcessor())
    dialog.sourceChoice.setCurrentIndex(dialog.sourceChoice.findData("github"))
    qtbot.waitUntil(lambda: "git could not be found" in dialog.operationStatus.text())
    assert not _okEnabled(dialog)


def test_githubRemoteReadFailureIsShown(qtbot, tmp_path, monkeypatch):
    def offline(_branchName, _path):
        raise ConnectionError("offline")

    monkeypatch.setattr(sourceManager, "listMPFBranches", lambda: ["dev"])
    monkeypatch.setattr(sourceManager, "readRemoteMPFSource", offline)
    dialog = _loadedDialog(qtbot, StorageProcessor())
    dialog.sourceChoice.setCurrentIndex(dialog.sourceChoice.findData("github"))
    qtbot.waitUntil(lambda: "Could not read dev from GitHub: offline" in dialog.operationStatus.text())
    assert not _okEnabled(dialog)


def test_existingGitHubEnvironmentReopensOnItsBranch(qtbot, tmp_path, monkeypatch):
    store = StorageProcessor()
    sourcePath = store.homePath / "mpf-sources" / "mpf-0.82.x"
    environment = VirtualEnvironment("env", str(tmp_path / "env"), "3.13", "0.82.0.dev1", [], str(sourcePath), "0.82.x")
    monkeypatch.setattr(sourceManager, "listMPFBranches", lambda: ["dev", "0.82.x"])
    monkeypatch.setattr(sourceManager.shutil, "which", lambda _name: "git")
    monkeypatch.setattr(
        sourceManager,
        "readRemoteMPFSource",
        lambda branchName, path: sourceManager.LocalMPFSource(path, "0.82.0.dev1", ">=3.10", None),
    )
    dialog = _loadedDialog(qtbot, store, environment)
    assert dialog.sourceChoice.currentData() == "github"
    assert dialog.editableSourceEdit.text() == ""
    qtbot.waitUntil(lambda: dialog.dialogMPFVersion.count() == 1)
    assert dialog.githubBranch.currentData() == "0.82.x"


def test_applyPlanRunsSourceCommandsFirstAndSavesBranch(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(uvManager, "locateUV", lambda: "uv")
    window = MainWindow(StorageProcessor())
    qtbot.addWidget(window)
    ranCommands = []
    monkeypatch.setattr(
        window.commandQueue, "run", lambda commands, onDone: (ranCommands.extend(commands), onDone(True))
    )
    cloneCommand = ["git", "clone", "--branch", "dev", sourceManager.MPF_GIT_URL, str(tmp_path / "mpf-dev")]

    window._applyPlan(
        venvDialogData(
            venvName="dev-env",
            venvPath=tmp_path / "dev-env",
            pythonVersion="3.13",
            mpfVersion="0.82.0.dev0",
            mpfVersionRequirements=[],
            companionPackages=[],
            packagesToRemove=[],
            editableMPFPath=tmp_path / "mpf-dev",
            editableMPFRef="dev",
            sourceCommands=[cloneCommand],
        ),
        create=True,
    )

    assert ranCommands[0] == cloneCommand
    assert ranCommands[1][:2] == ["uv", "venv"]
    environment = window.storedData.getVENVbyName("dev-env")
    assert environment is not None
    assert environment.editableMPFRef == "dev"
    versionItem = window.venvAvailableTable.item(0, 1)
    assert versionItem is not None
    assert versionItem.text() == "0.82.0.dev0  (editable, dev)"
    assert "Tracks dev from GitHub" in versionItem.toolTip()


def test_planErrorsAreReportedInsteadOfApplied(qtbot, monkeypatch):
    window = MainWindow(StorageProcessor())
    qtbot.addWidget(window)
    errors = []
    monkeypatch.setattr(window, "_error", errors.append)

    class FailingDialog:
        def plan(self):
            raise FileNotFoundError("git could not be found")

    window._applyDialogPlan(FailingDialog(), create=True)  # type: ignore[arg-type]
    assert errors == ["git could not be found"]


def test_existingAddOnsStayTickedWhileReleasesLoad(qtbot, tmp_path):
    environment = VirtualEnvironment("env", str(tmp_path / "env"), "3.13", "0.80.0", ["mpf-monitor"])
    dialog = _loadedDialog(qtbot, StorageProcessor(), environment)
    assert dialog.mpfAddOnDialogs["mpf-monitor"].isChecked()
    assert dialog.plan().packagesToRemove == []
