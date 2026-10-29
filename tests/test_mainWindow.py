from pathlib import Path
from typing import cast

import pytest
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QMessageBox

from mpfmanager.core import compatibilityManager, projectManager, uvManager
from mpfmanager.core.compatibilityManager import PyPIRelease
from mpfmanager.core.storageManager import Project, StorageProcessor, VirtualEnvironment
from mpfmanager.ui import dialogs, mainWindow
from mpfmanager.ui.dialogs import venvDialogData
from mpfmanager.ui.mainWindow import MainWindow


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MPF_MANAGER_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(compatibilityManager, "pypiReleaseRetriever", lambda _package: [PyPIRelease("0.80.0", ">=3.8")])
    monkeypatch.setattr(uvManager, "listPythonVersions", lambda: {"3.13"})


class _FakeProcess:
    """Stands in for RunningProcess so tests can see what was stopped"""

    def __init__(self):
        self.stopped = False

    def stopProcess(self):
        self.stopped = True

    def deleteLater(self):
        pass


def _window(qtbot, store: StorageProcessor) -> MainWindow:
    window = MainWindow(store)
    qtbot.addWidget(window)
    return window


def _errors(window: MainWindow, monkeypatch) -> list[str]:
    errors: list[str] = []
    monkeypatch.setattr(window, "_error", errors.append)
    return errors


def _machine(path: Path) -> Path:
    projectManager.createNewMPFProject(path)
    return path


def _installedEnvironment(tmp_path: Path, mpfVersion: str = "0.80.0", addOns=None) -> VirtualEnvironment:
    environment = VirtualEnvironment("env", str(tmp_path / "env"), "3.13", mpfVersion, list(addOns or []))
    environment.executable("mpf").parent.mkdir(parents=True)
    environment.executable("mpf").write_text("")
    (tmp_path / "env" / "pyvenv.cfg").write_text("")
    return environment


def _projectWindow(qtbot, tmp_path, environment: VirtualEnvironment | None):
    store = StorageProcessor()
    if environment:
        store.addVENV(environment)
    store.addProject(Project("machine", str(_machine(tmp_path / "machine")), environment and environment.venvName))
    window = _window(qtbot, store)
    window.projectListTable.selectRow(0)
    return window


def _selectMode(window: MainWindow, mode: str) -> None:
    window.runModeOption.setCurrentIndex(window.runModeOption.findData(mode))


def _cellText(window: MainWindow, row: int, column: int) -> str:
    item = window.projectListTable.item(row, column)
    return item.text() if item else ""


def test_projectStatuses(qtbot, tmp_path):
    store = StorageProcessor()
    store.addProject(Project("ok", str(_machine(tmp_path / "ok"))))
    (tmp_path / "noconfig").mkdir()
    store.addProject(Project("noconfig", str(tmp_path / "noconfig")))
    store.addProject(Project("missing", str(tmp_path / "missing")))
    window = _window(qtbot, store)
    assert [_cellText(window, row, 3) for row in range(3)] == ["OK", "No config/config.yaml", "Missing"]
    assert _cellText(window, 0, 2) == f"v{projectManager.CONFIG_VERSION}"
    assert _cellText(window, 1, 2) == "—"


def test_openFolderButtons(qtbot, tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(mainWindow, "_openMPFmachineFolder", opened.append)
    environment = _installedEnvironment(tmp_path)
    window = _projectWindow(qtbot, tmp_path, environment)
    window.openProjectFolderButton.click()
    window.venvAvailableTable.selectRow(0)
    window.openVENVButton.click()
    assert opened == [tmp_path / "machine", environment.venvPath]


def test_addExistingProject(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, StorageProcessor())
    errors = _errors(window, monkeypatch)
    machine = _machine(tmp_path / "machine")
    monkeypatch.setattr(mainWindow.QFileDialog, "getExistingDirectory", lambda *_args: str(machine))
    window.addExistingProject()
    assert window.storedData.getProjectbyPath(str(machine)) is not None

    window.addExistingProject()
    assert errors and "already registered" in errors[0]


def test_addExistingProjectWithoutConfigAsks(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, StorageProcessor())
    (tmp_path / "plain").mkdir()
    monkeypatch.setattr(mainWindow.QFileDialog, "getExistingDirectory", lambda *_args: str(tmp_path / "plain"))
    monkeypatch.setattr(mainWindow.QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.No)
    window.addExistingProject()
    assert window.storedData.projectList == []

    monkeypatch.setattr(mainWindow.QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    window.addExistingProject()
    assert len(window.storedData.projectList) == 1


def test_addExistingProjectCancelled(qtbot, monkeypatch):
    window = _window(qtbot, StorageProcessor())
    monkeypatch.setattr(mainWindow.QFileDialog, "getExistingDirectory", lambda *_args: "")
    window.addExistingProject()
    assert window.storedData.projectList == []


def test_removeProjectKeepsFiles(qtbot, tmp_path):
    window = _projectWindow(qtbot, tmp_path, None)
    window.removeProject()
    assert window.storedData.projectList == []
    assert (tmp_path / "machine" / "config" / "config.yaml").is_file()
    assert "files were not deleted" in window.outputViewer.toPlainText()


def test_deleteVENV(qtbot, tmp_path, monkeypatch):
    environment = _installedEnvironment(tmp_path)
    window = _projectWindow(qtbot, tmp_path, environment)
    window.venvAvailableTable.selectRow(0)
    questions = []

    def answer(response):
        def question(_parent, _title, text):
            questions.append(text)
            return response

        return question

    monkeypatch.setattr(mainWindow.QMessageBox, "question", answer(QMessageBox.StandardButton.No))
    window.deleteVENV()
    assert window.storedData.getVENVbyName("env") is not None
    assert "Used by: machine" in questions[0]

    monkeypatch.setattr(mainWindow.QMessageBox, "question", answer(QMessageBox.StandardButton.Yes))
    window.deleteVENV()
    assert window.storedData.getVENVbyName("env") is None
    assert not environment.venvPath.exists()
    project = window.storedData.getProjectbyPath(str(tmp_path / "machine"))
    assert project is not None and project.virtualEnvironment is None


def test_deleteEditableVENVKeepsSource(qtbot, tmp_path, monkeypatch):
    store = StorageProcessor()
    (tmp_path / "src").mkdir()
    store.addVENV(VirtualEnvironment("env", str(tmp_path / "missing-env"), "3.13", "0.82.0", [], str(tmp_path / "src")))
    window = _window(qtbot, store)
    window.venvAvailableTable.selectRow(0)
    questions = []
    monkeypatch.setattr(
        mainWindow.QMessageBox,
        "question",
        lambda _parent, _title, text: questions.append(text) or QMessageBox.StandardButton.Yes,
    )
    window.deleteVENV()
    assert "The MPF source folder will be kept" in questions[0]
    assert (tmp_path / "src").is_dir()


def _modeEnabled(window: MainWindow, mode: str) -> bool:
    model = cast(QStandardItemModel, window.runModeOption.model())
    return model.item(window.runModeOption.findData(mode)).isEnabled()


@pytest.mark.parametrize(
    ("mpfVersion", "gmcEnabled", "mpfMCEnabled"),
    [(None, False, True), ("0.57.0", False, True), ("0.80.0", True, False)],
)
def test_runModesFollowEnvironment(qtbot, tmp_path, mpfVersion, gmcEnabled, mpfMCEnabled):
    environment = _installedEnvironment(tmp_path, mpfVersion) if mpfVersion else None
    window = _projectWindow(qtbot, tmp_path, environment)
    assert _modeEnabled(window, "gmc") is gmcEnabled
    assert _modeEnabled(window, "gmconly") is gmcEnabled
    assert _modeEnabled(window, "both") is mpfMCEnabled


def test_runOptionsFollowMode(qtbot, tmp_path):
    window = _projectWindow(qtbot, tmp_path, _installedEnvironment(tmp_path))
    _selectMode(window, "monitor")
    assert not window.runMPFMonitorCheckBox.isEnabled()
    assert not window.runMediaControllerOption.isEnabled()
    _selectMode(window, "gmc")
    assert window.runMPFMonitorCheckBox.isEnabled()
    assert window.openGodotEditorCheckBox.isEnabled()


@pytest.mark.parametrize(
    ("mode", "addOns", "monitor", "message"),
    [
        ("monitor", [], False, "does not have mpf-monitor installed"),
        ("game", [], True, "does not have mpf-monitor installed"),
    ],
)
def test_runMPFProjectChecksAddOns(qtbot, tmp_path, monkeypatch, mode, addOns, monitor, message):
    window = _projectWindow(qtbot, tmp_path, _installedEnvironment(tmp_path, addOns=addOns))
    errors = _errors(window, monkeypatch)
    _selectMode(window, mode)
    window.runMPFMonitorCheckBox.setChecked(monitor)
    window.runMPFProject()
    assert errors and message in errors[0]


def test_runMPFProjectNeedsMPFMC(qtbot, tmp_path, monkeypatch):
    window = _projectWindow(qtbot, tmp_path, _installedEnvironment(tmp_path, "0.57.0"))
    errors = _errors(window, monkeypatch)
    _selectMode(window, "both")
    window.runMPFProject()
    assert errors and "does not have mpf-mc installed" in errors[0]


def test_runMPFProjectNeedsEnvironment(qtbot, tmp_path, monkeypatch):
    window = _projectWindow(qtbot, tmp_path, None)
    errors = _errors(window, monkeypatch)
    window.runMPFProject()
    assert errors == ["Choose an environment for this project first."]


def test_runMPFProjectNeedsGodotForGMC(qtbot, tmp_path, monkeypatch):
    window = _projectWindow(qtbot, tmp_path, _installedEnvironment(tmp_path))
    errors = _errors(window, monkeypatch)
    _selectMode(window, "gmc")
    window.runMPFProject()
    assert errors and "Set the path to your installed Godot" in errors[0]


def test_runMPFProjectNeedsMPFInstalled(qtbot, tmp_path, monkeypatch):
    environment = _installedEnvironment(tmp_path)
    environment.executable("mpf").unlink()
    window = _projectWindow(qtbot, tmp_path, environment)
    errors = _errors(window, monkeypatch)
    window.runMPFProject()
    assert errors and "MPF is not installed" in errors[0]


def test_runMPFProjectRejectsBadArguments(qtbot, tmp_path, monkeypatch):
    window = _projectWindow(qtbot, tmp_path, _installedEnvironment(tmp_path))
    errors = _errors(window, monkeypatch)
    window.extraRunArguments.setText('-v "unterminated')
    window.runMPFProject()
    assert errors and errors[0].startswith("Invalid extra arguments")


def _spyStarts(window: MainWindow, monkeypatch) -> list[tuple]:
    started: list[tuple] = []

    def fakeStart(project, command, label, workingPath=None):
        started.append((command, label, workingPath))
        return _FakeProcess()

    monkeypatch.setattr(window, "_startProjectProcess", fakeStart)
    return started


def test_runMPFProjectStartsGame(qtbot, tmp_path, monkeypatch):
    environment = _installedEnvironment(tmp_path)
    window = _projectWindow(qtbot, tmp_path, environment)
    started = _spyStarts(window, monkeypatch)
    _selectMode(window, "game")
    window.runMediaControllerOption.setChecked(True)
    window.extraRunArguments.setText("-v")
    window.runMPFProject()
    command, label, _workingPath = started[0]
    assert label == "game"
    assert command[:3] == [str(environment.executable("mpf")), "game", "-t"]
    assert command[-2:] == ["-b", "-v"]


def test_runGMCOnlyStartsGodotInTheGMCFolder(qtbot, tmp_path, monkeypatch):
    godot = tmp_path / "godot"
    godot.write_text("")
    godot.chmod(0o755)
    window = _projectWindow(qtbot, tmp_path, _installedEnvironment(tmp_path))
    window.storedData.settings.godotExecutablePath = str(godot)
    (tmp_path / "machine" / "project.godot").write_text("")
    started = _spyStarts(window, monkeypatch)
    _selectMode(window, "gmconly")
    window.openGodotEditorCheckBox.setChecked(True)
    window.runMPFProject()
    assert started == [([str(godot), "--path", str(tmp_path / "machine"), "-e"], "gmc", tmp_path / "machine")]


def test_resolveGMCPath(qtbot, tmp_path, monkeypatch):
    window = _projectWindow(qtbot, tmp_path, None)
    errors = _errors(window, monkeypatch)
    project = window.storedData.projectList[0]

    # Asked, but the chosen folder is not a godot project
    (tmp_path / "notgodot").mkdir()
    monkeypatch.setattr(mainWindow.QFileDialog, "getExistingDirectory", lambda *_args: str(tmp_path / "notgodot"))
    assert window._resolveGMCPath(project) is None
    assert errors and "has no project.godot" in errors[0]

    # Asked and cancelled
    monkeypatch.setattr(mainWindow.QFileDialog, "getExistingDirectory", lambda *_args: "")
    assert window._resolveGMCPath(project) is None

    # Asked and given a godot project, which is remembered
    (tmp_path / "gmc").mkdir()
    (tmp_path / "gmc" / "project.godot").write_text("")
    monkeypatch.setattr(mainWindow.QFileDialog, "getExistingDirectory", lambda *_args: str(tmp_path / "gmc"))
    assert window._resolveGMCPath(project) == tmp_path / "gmc"
    assert project.gmcFolderPath == str(tmp_path / "gmc")
    monkeypatch.setattr(mainWindow.QFileDialog, "getExistingDirectory", pytest.fail)
    assert window._resolveGMCPath(project) == tmp_path / "gmc"


def test_resolveGMCPathFindsProjectInMachineFolder(qtbot, tmp_path):
    window = _projectWindow(qtbot, tmp_path, None)
    (tmp_path / "machine" / "gmc").mkdir()
    (tmp_path / "machine" / "gmc" / "project.godot").write_text("")
    assert window._resolveGMCPath(window.storedData.projectList[0]) == tmp_path / "machine" / "gmc"


def test_stoppingTheGameStopsCompanions(qtbot, tmp_path):
    window = _projectWindow(qtbot, tmp_path, None)
    project = window.storedData.projectList[0]
    game, monitor = _FakeProcess(), _FakeProcess()
    window.runningProcesses[project.projectPath] = {"game": game, "monitor": monitor}  # type: ignore[dict-item]
    window.refreshMainWindow()
    assert _cellText(window, 0, 3) == "Running (game + monitor)"
    assert window.stopMPFButton.isEnabled()

    window._processStopped(project, game, "game", 0)  # type: ignore[arg-type]
    assert monitor.stopped
    window._processStopped(project, monitor, "monitor", 0)  # type: ignore[arg-type]
    assert project.projectPath not in window.runningProcesses
    assert "[machine/game] exited with code 0" in window.outputViewer.toPlainText()


def test_stopButtonAndCloseStopProcesses(qtbot, tmp_path):
    window = _projectWindow(qtbot, tmp_path, None)
    project = window.storedData.projectList[0]
    game = _FakeProcess()
    window.runningProcesses[project.projectPath] = {"game": game}  # type: ignore[dict-item]
    window.stopMPFProject()
    assert game.stopped

    game.stopped = False
    window.close()
    assert game.stopped


def test_delayedCompanionOnlyStartsWhileGameRuns(qtbot, tmp_path, monkeypatch):
    window = _projectWindow(qtbot, tmp_path, None)
    project = window.storedData.projectList[0]
    started = _spyStarts(window, monkeypatch)
    game = _FakeProcess()
    window._startDelayedCompanion(project, ["monitor"], "monitor", game)  # type: ignore[arg-type]
    assert started == []
    assert "the game is no longer running" in window.outputViewer.toPlainText()

    window.runningProcesses[project.projectPath] = {"game": game}  # type: ignore[dict-item]
    window._startDelayedCompanion(project, ["monitor"], "monitor", game)  # type: ignore[arg-type]
    assert started == [(["monitor"], "monitor", None)]


def test_startProjectProcessTracksRealProcess(qtbot, tmp_path):
    import sys

    window = _projectWindow(qtbot, tmp_path, None)
    project = window.storedData.projectList[0]
    process = window._startProjectProcess(project, [sys.executable, "-c", "print('hi')"], "game", tmp_path)
    assert process.process.workingDirectory() == str(tmp_path)
    qtbot.waitUntil(lambda: project.projectPath not in window.runningProcesses, timeout=15000)
    assert "[machine/game] hi" in window.outputViewer.toPlainText()


def test_editSettings(qtbot, monkeypatch):
    window = _window(qtbot, StorageProcessor())

    def accept(dialog):
        dialog.godotExecutableDialog.setText("/opt/godot")
        return 1

    monkeypatch.setattr(dialogs.SettingsDialog, "exec", accept)
    window.edit_settings()
    assert StorageProcessor().settings.godotExecutablePath == "/opt/godot"


def test_createNewProject(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, StorageProcessor())

    def accept(dialog):
        dialog.projectName.setText("pinball")
        dialog.projectParentFolder.setText(str(tmp_path))
        return 1

    monkeypatch.setattr(dialogs.mpfProjectCreationDialog, "exec", accept)
    window.createNewProject()
    assert projectManager.checkMPFProjectAtPath(tmp_path / "pinball")
    assert window.storedData.getProjectbyPath(str(tmp_path / "pinball")) is not None


def test_createNewProjectReportsErrors(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, StorageProcessor())
    errors = _errors(window, monkeypatch)
    (tmp_path / "pinball").mkdir()
    (tmp_path / "pinball" / "x.txt").write_text("x")

    def accept(dialog):
        dialog.projectName.setText("pinball")
        dialog.projectParentFolder.setText(str(tmp_path))
        return 1

    monkeypatch.setattr(dialogs.mpfProjectCreationDialog, "exec", accept)
    window.createNewProject()
    assert errors and "already exists" in errors[0]


def test_createAndChangeVENVButtons(qtbot, tmp_path, monkeypatch):
    environment = _installedEnvironment(tmp_path)
    store = StorageProcessor()
    store.addVENV(environment)
    window = _window(qtbot, store)
    applied = []
    monkeypatch.setattr(window, "_applyDialogPlan", lambda dialog, create: applied.append(create))

    monkeypatch.setattr(dialogs.VENVManagementDialog, "exec", lambda _dialog: 0)
    window.createVENVButton()
    assert applied == []

    def accept(dialog):
        dialog.venvParentLocation.setText(str(tmp_path / "envs"))
        return 1

    monkeypatch.setattr(dialogs.VENVManagementDialog, "exec", accept)
    window.createVENVButton()
    assert applied == [True]
    assert store.settings.venvDirectory == str(tmp_path / "envs")

    window.venvAvailableTable.selectRow(0)
    window.changeVENVmpf()
    assert applied == [True, False]


def test_applyPlanUpdatesExistingEnvironment(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(uvManager, "locateUV", lambda: "uv")
    store = StorageProcessor()
    store.addVENV(VirtualEnvironment("env", str(tmp_path / "env"), "3.13", "0.80.0", ["mpf-mc"]))
    window = _window(qtbot, store)
    ranCommands = []
    monkeypatch.setattr(
        window.commandQueue, "run", lambda commands, onDone: (ranCommands.extend(commands), onDone(True))
    )
    plan = venvDialogData("env", tmp_path / "env", "3.13", "0.80.1", ["mpf==0.80.1"], [], ["mpf-mc"])
    window._applyPlan(plan, create=False)
    assert [command[2] for command in ranCommands] == ["uninstall", "install"]
    environment = store.getVENVbyName("env")
    assert environment is not None
    assert environment.installedMPFVersion == "0.80.1" and environment.additionalPackages == []


def test_applyPlanFailureLeavesEnvironmentUnregistered(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(uvManager, "locateUV", lambda: "uv")
    window = _window(qtbot, StorageProcessor())
    monkeypatch.setattr(window.commandQueue, "run", lambda _commands, onDone: onDone(False))
    (tmp_path / "env").mkdir()
    window._applyPlan(venvDialogData("env", tmp_path / "env", "3.13", "0.80.0", [], [], []), create=True)
    assert window.storedData.environmentList == []
    assert "The partial environment was left at" in window.outputViewer.toPlainText()


def test_applyPlanWithoutUV(qtbot, tmp_path, monkeypatch):
    def noUV():
        raise uvManager.UvNotFoundError("uv could not be found")

    monkeypatch.setattr(uvManager, "locateUV", noUV)
    window = _window(qtbot, StorageProcessor())
    errors = _errors(window, monkeypatch)
    window._applyPlan(venvDialogData("env", tmp_path / "env", "3.13", "0.80.0", [], [], []), create=True)
    assert errors == ["uv could not be found"]


def test_verifyVENVPackages(qtbot, tmp_path, monkeypatch):
    store = StorageProcessor()
    store.addVENV(VirtualEnvironment("env", str(tmp_path / "env"), "3.13", "0.80.0", ["mpf-monitor", "mpf-mc"]))
    window = _window(qtbot, store)
    window.venvAvailableTable.selectRow(0)
    monkeypatch.setattr(mainWindow.uvCMDs, "listVENVPackages", lambda _path: {"mpf": "0.80.2", "mpf-monitor": "1.0.0"})
    window.verifyVENVPackages()
    environment = store.getVENVbyName("env")
    assert environment is not None
    qtbot.waitUntil(lambda: environment.installedMPFVersion == "0.80.2")
    assert environment.additionalPackages == ["mpf-monitor"]

    monkeypatch.setattr(mainWindow.uvCMDs, "listVENVPackages", lambda _path: {})
    window.venvAvailableTable.selectRow(0)
    window.verifyVENVPackages()
    qtbot.waitUntil(lambda: "mpf is not installed in 'env'" in window.outputViewer.toPlainText())
