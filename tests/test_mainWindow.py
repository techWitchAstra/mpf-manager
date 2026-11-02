from pathlib import Path
from typing import cast

import pytest
from PySide6.QtGui import QStandardItemModel
from PySide6.QtWidgets import QMessageBox

from mpfmanager.core import compatibilityManager, projectManager, uvManager
from mpfmanager.core.compatibilityManager import PyPIRelease
from mpfmanager.core.storageManager import Project, RunProfile, StorageProcessor, VirtualEnvironment
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
    window.openProject(window.storedData.projectList[0])
    return window


def _selectMode(window: MainWindow, mode: str) -> None:
    window.runModeOption.setCurrentIndex(window.runModeOption.findData(mode))


def test_projectStatuses(qtbot, tmp_path):
    store = StorageProcessor()
    store.addProject(Project("ok", str(_machine(tmp_path / "ok"))))
    (tmp_path / "noconfig").mkdir()
    store.addProject(Project("noconfig", str(tmp_path / "noconfig")))
    store.addProject(Project("missing", str(tmp_path / "missing")))
    assert [mainWindow.projectStatus(project, {}) for project in store.projectList] == [
        "OK",
        "No config/config.yaml",
        "Missing",
    ]
    assert mainWindow.projectStatus(store.projectList[0], {str(tmp_path / "ok"): {"game": None}}) == "Running (game)"

    # The open project's details are shown on the Project Manager
    window = _window(qtbot, store)
    window.openProject(store.projectList[0])
    assert window.overviewLabels["status"].text() == "OK"
    assert window.overviewLabels["config"].text() == f"v{projectManager.CONFIG_VERSION}"
    assert window.overviewLabels["path"].text() == str(tmp_path / "ok")
    window.openProject(store.projectList[1])
    assert window.overviewLabels["config"].text() == "—"
    assert window.overviewLabels["status"].text() == "No config/config.yaml"


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
    added = window.addExistingProject()
    assert added is not None and window.storedData.getProjectbyPath(str(machine)) is added

    # Opening a folder that is listed gives its project
    assert window.addExistingProject() is added
    assert errors == [] and len(window.storedData.projectList) == 1


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
    assert window.overviewLabels["status"].text() == "Running (game + monitor)"
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


def test_saveRunProfileFromRunOptions(qtbot, tmp_path, monkeypatch):
    window = _projectWindow(qtbot, tmp_path, _installedEnvironment(tmp_path, addOns=["mpf-monitor"]))
    _selectMode(window, "game")
    window.runMediaControllerOption.setChecked(True)
    window.runMPFMonitorCheckBox.setChecked(True)
    window.hardwareOption.setCurrentIndex(1)
    window.extraRunArguments.setText("-v")
    monkeypatch.setattr(mainWindow.QInputDialog, "getText", lambda *_a, **_k: (" attract ", True))
    window.saveRunProfile()
    profile = StorageProcessor().getRunProfileByName("attract")
    assert profile == RunProfile("attract", str(tmp_path / "machine"), "game", ["-x"], True, True, False, "-v")
    assert window.selectedRunProfile() == window.storedData.getRunProfileByName("attract")
    assert window.runProfileOption.currentText().startswith("attract  (Game)")


def test_saveRunProfileAsksBeforeReplacing(qtbot, tmp_path, monkeypatch):
    window = _projectWindow(qtbot, tmp_path, _installedEnvironment(tmp_path))
    window.storedData.saveRunProfile(RunProfile("p", str(tmp_path / "machine"), "monitor"))
    monkeypatch.setattr(mainWindow.QInputDialog, "getText", lambda *_a, **_k: ("p", True))
    monkeypatch.setattr(QMessageBox, "question", lambda *_a: QMessageBox.StandardButton.No)
    _selectMode(window, "game")
    window.saveRunProfile()
    assert window.storedData.getRunProfileByName("p").runMode == "monitor"
    monkeypatch.setattr(QMessageBox, "question", lambda *_a: QMessageBox.StandardButton.Yes)
    window.saveRunProfile()
    assert window.storedData.getRunProfileByName("p").runMode == "game"
    monkeypatch.setattr(mainWindow.QInputDialog, "getText", lambda *_a, **_k: ("other", False))
    window.saveRunProfile()
    assert window.storedData.getRunProfileByName("other") is None


def test_runRunProfileUsesSavedOptions(qtbot, tmp_path, monkeypatch):
    environment = _installedEnvironment(tmp_path)
    window = _projectWindow(qtbot, tmp_path, environment)
    window.storedData.saveRunProfile(
        RunProfile("p", str(tmp_path / "machine"), "game", ["-x"], True, False, False, "-v")
    )
    window.refreshMainWindow()
    started = _spyStarts(window, monkeypatch)
    _selectMode(window, "monitor")
    window.runProfileButton.click()
    command, label, _workingPath = started[0]
    assert label == "game"
    assert command == [str(environment.executable("mpf")), "game", "-t", "-x", "-b", "-v"]


def test_runRunProfileErrors(qtbot, tmp_path, monkeypatch):
    window = _projectWindow(qtbot, tmp_path, _installedEnvironment(tmp_path))
    errors = _errors(window, monkeypatch)
    window.runRunProfile(None)
    window.runRunProfile(RunProfile("gone", str(tmp_path / "gone")))
    window.runningProcesses[str(tmp_path / "machine")] = {"game": _FakeProcess()}
    window.runRunProfile(RunProfile("p", str(tmp_path / "machine")))
    assert errors == [
        "The project for run profile 'gone' is no longer in the project list.",
        "'machine' is already running.",
    ]


def test_loadRunProfileSetsRunOptions(qtbot, tmp_path, monkeypatch):
    store = StorageProcessor()
    store.addVENV(_installedEnvironment(tmp_path, "0.57.0", ["mpf-mc", "mpf-monitor"]))
    store.addProject(Project("first", str(_machine(tmp_path / "first")), "env"))
    store.addProject(Project("second", str(_machine(tmp_path / "second")), "env"))
    store.saveRunProfile(RunProfile("p", str(tmp_path / "second"), "both", [], False, True, False, "-v"))
    window = _window(qtbot, store)
    window.openProject(window.storedData.projectList[0])
    # Only the open project's run profiles are listed, and loading one opens its project
    assert window.runProfileOption.count() == 0 and not window.loadRunProfileButton.isEnabled()
    window.loadRunProfile(store.getRunProfileByName("p"))
    assert window.selectedProject().projectName == "second"
    assert window.runProfileOption.currentData() == "p"
    assert window.runModeOption.currentData() == "both"
    assert window.hardwareOption.currentData() == []
    assert window.runMPFMonitorCheckBox.isChecked()
    assert window.extraRunArguments.text() == "-v"
    errors = _errors(window, monkeypatch)
    window.loadRunProfile(RunProfile("gone", str(tmp_path / "gone")))
    assert errors == ["The project for run profile 'gone' is no longer in the project list."]


def test_runAtStartupCheckBoxAndStartupRun(qtbot, tmp_path, monkeypatch):
    window = _projectWindow(qtbot, tmp_path, _installedEnvironment(tmp_path))
    window.storedData.saveRunProfile(RunProfile("p", str(tmp_path / "machine")))
    window.refreshMainWindow()
    assert not window.runAtStartupCheckBox.isChecked()
    window.runAtStartupCheckBox.setChecked(True)
    assert StorageProcessor().startupProfile().profileName == "p"
    assert window.runProfileOption.currentText().endswith("[startup]")

    # A fresh window, as at startup, runs the profile
    restarted = _window(qtbot, StorageProcessor())
    started = _spyStarts(restarted, monkeypatch)
    restarted.runStartupProfile()
    assert [label for _command, label, _path in started] == ["game"]
    assert restarted.selectedProject().projectName == "machine"

    window.runAtStartupCheckBox.setChecked(False)
    assert StorageProcessor().startupProfile() is None
    disabled = _window(qtbot, StorageProcessor())
    started = _spyStarts(disabled, monkeypatch)
    disabled.runStartupProfile()
    assert started == []


def test_startupProfileThatNoLongerExists(qtbot, tmp_path):
    store = StorageProcessor()
    store.settings.runProfileAtStartup = True
    store.settings.startupRunProfile = "gone"
    window = _window(qtbot, store)
    window.runStartupProfile()
    assert "The startup run profile 'gone' no longer exists." in window.outputViewer.toPlainText()


def test_deleteRunProfile(qtbot, tmp_path, monkeypatch):
    window = _projectWindow(qtbot, tmp_path, _installedEnvironment(tmp_path))
    window.storedData.saveRunProfile(RunProfile("p", str(tmp_path / "machine")))
    window.storedData.setStartupRunProfile("p")
    window.refreshMainWindow()
    monkeypatch.setattr(QMessageBox, "question", lambda *_a: QMessageBox.StandardButton.No)
    window.deleteRunProfileButton.click()
    assert window.storedData.getRunProfileByName("p") is not None
    monkeypatch.setattr(QMessageBox, "question", lambda *_a: QMessageBox.StandardButton.Yes)
    window.deleteRunProfileButton.click()
    assert StorageProcessor().runProfileList == [] and StorageProcessor().startupProfile() is None
    assert window.runProfileOption.count() == 0 and not window.runProfileButton.isEnabled()


def _menuTitles(window: MainWindow) -> list[str]:
    return [action.text().replace("&", "") for action in window.menuBar().actions()]


def test_projectManagerRibbonRunsTheProject(qtbot, tmp_path):
    window = _projectWindow(qtbot, tmp_path, _installedEnvironment(tmp_path))
    ribbon = window.ribbon
    assert [ribbon.tabText(index) for index in range(ribbon.count())] == ["Run", "Project"]
    assert ribbon.currentIndex() == mainWindow.RUN_RIBBON_TAB
    assert list(ribbon.ribbonTab("Run").groups) == ["Run", "Options", "Run profiles"]
    assert list(ribbon.ribbonTab("Project").groups) == ["Project", "Open", "Environment", "Godot"]
    assert window.windowTitle() == "MPF-Manager — machine"
    assert window.managerTabs.tabText(mainWindow.PROJECT_MANAGER_TAB) == "Project Manager"


def test_projectManagerMenus(qtbot):
    window = _window(qtbot, StorageProcessor())
    assert _menuTitles(window) == ["File", "Project", "Run", "Settings", "View"]
    menus = {action.text().replace("&", ""): action.menu() for action in window.menuBar().actions()}
    assert window.openProjectAction in menus["File"].actions() and window.newProjectAction in menus["File"].actions()
    assert window.runMPFAction in menus["Run"].actions()
    assert menus["Settings"].actions() == [window.manageEnvironmentsAction, window.settingsAction]
    assert window.settingsAction.text() == "&Preferences…"

    # An action and its ribbon button are enabled together, so the menus and ribbon agree
    assert not window.stopMPFAction.isEnabled() and not window.stopMPFButton.isEnabled()
    assert window.newVENVAction.isEnabled() and window.newVENVButton.isEnabled()

    # The ribbon and output log can be hidden
    window.show()
    window.showOutputAction.setChecked(False)
    assert not window.outputViewer.isVisible()
    window.showRibbonAction.setChecked(False)
    assert not window.ribbon.isVisible()


def test_withoutAProjectTheWindowAsksForOne(qtbot, tmp_path, monkeypatch):
    window = _projectWindow(qtbot, tmp_path, None)
    window.show()
    assert window.projectDetails.isVisible() and not window.noProjectPrompt.isVisible()
    window.closeProjectAction.trigger()
    assert window.selectedProject() is None and window.windowTitle() == "MPF-Manager"
    assert window.noProjectPrompt.isVisible() and not window.projectDetails.isVisible()
    for action in (
        window.runMPFAction,
        window.openProjectFolderAction,
        window.viewShowsAction,
        window.saveRunProfileAction,
        window.closeProjectAction,
    ):
        assert not action.isEnabled()
    assert not window.environmentOption.isEnabled()

    # The prompt's button asks which project to open
    asked = []
    monkeypatch.setattr(window, "showProjectPicker", lambda: asked.append(True))
    window.promptOpenButton.click()
    window.openProjectAction.trigger()
    assert asked == [True, True]


def test_openProjectChecksTheProjectIsListed(qtbot, tmp_path):
    window = _projectWindow(qtbot, tmp_path, None)
    assert not window.openProject(Project("stranger", str(tmp_path / "stranger")))
    assert window.selectedProject().projectName == "machine"
    # A project taken off the list is no longer open
    window.removeProject()
    assert window.selectedProject() is None and window.windowTitle() == "MPF-Manager"


def test_theRibbonChoosesTheProjectsEnvironment(qtbot, tmp_path):
    store = StorageProcessor()
    store.addVENV(_installedEnvironment(tmp_path, "0.80.0"))
    store.addProject(Project("machine", str(_machine(tmp_path / "machine"))))
    window = _window(qtbot, store)
    window.openProject(store.projectList[0])
    assert window.environmentOption.currentData() is None
    assert "None" in window.overviewLabels["environment"].text()
    assert not window.createGMCAction.isEnabled()

    window.environmentOption.setCurrentIndex(window.environmentOption.findData("env"))
    assert StorageProcessor().projectList[0].virtualEnvironment == "env"
    assert window.overviewLabels["environment"].text() == "env  (MPF 0.80.0, Python 3.13)"
    # The run options follow the environment, which can run GMC
    assert window.createGMCAction.isEnabled()
    runModeModel = cast(QStandardItemModel, window.runModeOption.model())
    assert runModeModel.item(window.runModeOption.findData("gmc")).isEnabled()


def test_environmentsAreManagedFromSettings(qtbot, tmp_path):
    store = StorageProcessor()
    store.addVENV(_installedEnvironment(tmp_path))
    window = _window(qtbot, store)
    window.show()
    assert not window.environmentsDialog.isVisible()
    window.manageEnvironmentsAction.trigger()
    assert window.environmentsDialog.isVisible() and not window.environmentsDialog.isModal()
    assert window.venvAvailableTable.window() is window.environmentsDialog
    assert window.venvAvailableTable.rowCount() == 1
    assert [button.defaultAction() for button in window.environmentsDialog.buttons] == [
        window.newVENVAction,
        window.changeVENVAction,
        window.verifyVENVAction,
        window.openVENVAction,
        window.openSourceAction,
        window.deleteVENVAction,
    ]


def test_startUpAsksWhichProjectToOpen(qtbot, tmp_path, monkeypatch):
    store = StorageProcessor()
    store.addProject(Project("machine", str(_machine(tmp_path / "machine"))))
    window = _window(qtbot, store)

    # The project chosen in the dialog is opened
    def choose(picker):
        picker.openChosen()
        return 1

    monkeypatch.setattr(mainWindow.ProjectPickerDialog, "exec", choose)
    window.startUp()
    assert window.selectedProject().projectName == "machine"

    # Cancelling it leaves the window without a project
    window.closeProject()
    monkeypatch.setattr(mainWindow.ProjectPickerDialog, "exec", lambda _picker: 0)
    window.startUp()
    assert window.selectedProject() is None

    # A new project made from the dialog is opened
    def makeNew(picker):
        picker.newButton.click()
        return picker.result()

    newMachine = _machine(tmp_path / "new")
    monkeypatch.setattr(
        window,
        "createNewProject",
        lambda: (
            window.storedData.addProject(Project("new", str(newMachine)))
            or window.storedData.getProjectbyPath(str(newMachine))
        ),
    )
    monkeypatch.setattr(mainWindow.ProjectPickerDialog, "exec", makeNew)
    assert window.showProjectPicker()
    assert window.selectedProject().projectName == "new"


def test_startUpRunsTheStartupProfileWithoutAsking(qtbot, tmp_path, monkeypatch):
    environment = _installedEnvironment(tmp_path)
    store = StorageProcessor()
    store.addVENV(environment)
    store.addProject(Project("machine", str(_machine(tmp_path / "machine")), "env"))
    store.saveRunProfile(RunProfile("p", str(tmp_path / "machine")))
    store.setStartupRunProfile("p")
    window = _window(qtbot, store)
    started = _spyStarts(window, monkeypatch)
    monkeypatch.setattr(mainWindow.ProjectPickerDialog, "exec", lambda _picker: pytest.fail("asked for a project"))
    window.startUp()
    assert window.selectedProject().projectName == "machine"
    assert [label for _command, label, _path in started] == ["game"]


def test_managersArePagesOfOneWindow(qtbot):
    window = _window(qtbot, StorageProcessor())
    window.show()
    assert window.managerTabs.currentIndex() == mainWindow.PROJECT_MANAGER_TAB
    assert window.pages.currentWidget() is window.projectManagerPage

    # The Show Manager is a page of the same window, with its own menus, and without tabs of its own
    window.showManagerAction.trigger()
    viewer = window.showViewerWindow
    assert viewer is not None and window.pages.currentWidget() is viewer and viewer.isVisible()
    assert not viewer.managerTabs.isVisible() and viewer.isWindow() is False
    assert window.managerTabs.currentIndex() == mainWindow.SHOW_MANAGER_TAB
    assert _menuTitles(window) == ["File", "Edit", "View", "Playback", "Tools"]
    assert window.windowTitle() == viewer.windowTitle()
    assert window.width() >= mainWindow.SHOW_MANAGER_SIZE[0]

    # Closing the Show Manager, or choosing the Project Manager tab, goes back to the Project Manager
    viewer.closeAction.trigger()
    assert window.pages.currentWidget() is window.projectManagerPage and not viewer.isVisible()
    assert _menuTitles(window) == ["File", "Project", "Run", "Settings", "View"]
    assert window.windowTitle() == "MPF-Manager"
    window.managerTabs.managerChosen.emit(mainWindow.SHOW_MANAGER_TAB)
    assert window.pages.currentWidget() is viewer
    window.managerTabs.managerChosen.emit(mainWindow.PROJECT_MANAGER_TAB)
    assert window.managerTabs.currentIndex() == mainWindow.PROJECT_MANAGER_TAB
    assert window.pages.currentWidget() is window.projectManagerPage


def _newProjectWithEnvironment(window, tmp_path, monkeypatch, mpfVersion="0.80.0", createGMC=False):
    plan = venvDialogData("fresh", tmp_path / "fresh", "3.13", mpfVersion, [f"mpf=={mpfVersion}"], [], [])

    def accept(dialog):
        dialog.projectName.setText("pinball")
        dialog.projectParentFolder.setText(str(tmp_path))
        dialog.newEnvironmentPlan = plan
        dialog.newEnvironmentFolder = tmp_path / "envs"
        dialog.environmentPair.addItem("fresh (new)", "fresh")
        dialog.environmentPair.setCurrentIndex(dialog.environmentPair.count() - 1)
        dialog.createGMCCheckBox.setChecked(createGMC)
        return 1

    monkeypatch.setattr(dialogs.mpfProjectCreationDialog, "exec", accept)
    window.createNewProject()


def test_createNewProjectWithANewEnvironment(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(uvManager, "locateUV", lambda: "uv")
    window = _window(qtbot, StorageProcessor())
    ranCommands = []
    monkeypatch.setattr(
        window.commandQueue, "run", lambda commands, onDone: (ranCommands.extend(commands), onDone(True))
    )
    _newProjectWithEnvironment(window, tmp_path, monkeypatch)

    # The project is made, then the environment, which the project is paired with
    assert projectManager.checkMPFProjectAtPath(tmp_path / "pinball")
    assert len(ranCommands) == 2 and ranCommands[1][2] == "install"
    assert window.storedData.getVENVbyName("fresh") is not None
    project = window.storedData.getProjectbyPath(str(tmp_path / "pinball"))
    assert project is not None and project.virtualEnvironment == "fresh"
    assert window.storedData.settings.venvDirectory == str(tmp_path / "envs")
    assert "'pinball' now uses the environment 'fresh'." in window.outputViewer.toPlainText()


def test_createNewProjectWhenItsEnvironmentFails(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(uvManager, "locateUV", lambda: "uv")
    window = _window(qtbot, StorageProcessor())
    monkeypatch.setattr(window.commandQueue, "run", lambda _commands, onDone: onDone(False))
    gmcProjects = []
    monkeypatch.setattr(window, "createGMCProject", gmcProjects.append)
    _newProjectWithEnvironment(window, tmp_path, monkeypatch, createGMC=True)
    project = window.storedData.getProjectbyPath(str(tmp_path / "pinball"))
    assert project is not None and project.virtualEnvironment is None
    assert window.storedData.environmentList == [] and gmcProjects == []
    assert "'pinball' was created without an environment" in window.outputViewer.toPlainText()


def test_createNewProjectMakesGMCOnceItsEnvironmentIsMade(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(uvManager, "locateUV", lambda: "uv")
    window = _window(qtbot, StorageProcessor())
    pending = []
    monkeypatch.setattr(window.commandQueue, "run", lambda _commands, onDone: pending.append(onDone))
    gmcProjects = []
    monkeypatch.setattr(window, "createGMCProject", gmcProjects.append)
    _newProjectWithEnvironment(window, tmp_path, monkeypatch, createGMC=True)
    assert gmcProjects == []
    pending[0](True)
    assert [project.projectName for project in gmcProjects] == ["pinball"]
    assert gmcProjects[0].virtualEnvironment == "fresh"


def test_applyPlanTellsWhenItIsDone(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, StorageProcessor())
    results = []

    def noUV():
        raise uvManager.UvNotFoundError("uv is not installed")

    monkeypatch.setattr(uvManager, "locateUV", noUV)
    monkeypatch.setattr(window, "_error", lambda _message: None)
    window._applyPlan(venvDialogData("env", tmp_path / "env", "3.13", "0.80.0", [], [], []), True, results.append)
    assert results == [False]
