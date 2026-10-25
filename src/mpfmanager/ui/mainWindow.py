"""Main window: environments tab, projects tab and a shared output outputLogger."""

#   mainWindow - Responsible for the main GUI window containing everything
# 
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human by a human at all stages

from __future__ import annotations

# The following imports the needed standard python libraries
import shlex
import shutil
from pathlib import Path

# The following imports the used Qt assets for Main Window
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

# The following imports the needed parts of the application from other files
from mpfmanager.core import projectManager as mpfProjects
from mpfmanager.core import uv as uvCMDs
from mpfmanager.core.storageManager import VirtualEnvironment, Project, StorageProcessor
from mpfmanager.ui.dialogs import (
    VENVManagementDialog,
    venvDialogData,
    mpfProjectCreationDialog,
    SettingsDialog,
    environmentPairing,
)
from mpfmanager.ui.uiWorkers import CommandQueue, RunningProcess, run_in_thread

# The following creates a table widget to be called later in the application
def _table(headers: list[str]) -> QTableWidget:
    tableWidget = QTableWidget(0, len(headers))
    tableWidget.setHorizontalHeaderLabels(headers)
    tableWidget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tableWidget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    tableWidget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tableWidget.verticalHeader().setVisible(False)
    tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    tableWidget.horizontalHeader().setStretchLastSection(True)
    return tableWidget

# The following creates a table widget item given a name and data
def _item(text: str, data: str | None = None) -> QTableWidgetItem:
    tableWidgetItem = QTableWidgetItem(text)
    if data is not None:
        tableWidgetItem.setData(Qt.ItemDataRole.UserRole, data)
    return tableWidgetItem

# The following function opens a folder using QDesktopServices
def _openMPFmachineFolder(folderPath: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folderPath)))

# The following defines the main window for MPF Manager
class MainWindow(QMainWindow):

    # The following function initializes the main window upon inital call
    def __init__(self, storedData: StorageProcessor | None = None):
        super().__init__()
        self.storedData = storedData or StorageProcessor()
        self.commandQueue = CommandQueue(self)
        self.commandQueue.output.connect(self.logResult)
        self.commandQueue.busyChangedSignal.connect(self._updateButtons)
        self.runningProcesses: dict[str, RunningProcess] = {}

        # The following sets up the application window
        self.setWindowTitle("MPF-Manager")
        self.resize(1000, 680)
        self._buildMenu()

        # The following sets up the Application Focus Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(self._buildEnvironmentsTab(), "MPF+Python Environments")
        self.tabs.addTab(self._buildProjectsTab(), "MPF Projects")

        # The following sets up the output viewer console
        self.outputViewer = QPlainTextEdit()
        self.outputViewer.setReadOnly(True)
        self.outputViewer.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.outputViewer.setMaximumBlockCount(5000)

        # The following assembles the outputViewer and the Tabs together
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.tabs)
        splitter.addWidget(self.outputViewer)
        splitter.setSizes([440, 240])
        self.setCentralWidget(splitter)

        self.refreshMainWindow()

    # The following function builds out the menu for the application
    def _buildMenu(self) -> None:
        menu = self.menuBar().addMenu("&File")
        settings = QAction("&Settings…", self)
        settings.triggered.connect(self.edit_settings)
        menu.addAction(settings)
        open_config = QAction("Open config &folder", self)
        open_config.triggered.connect(lambda: _openMPFmachineFolder(self.storedData.home))
        menu.addAction(open_config)
        menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

    # The following builds the tab for managing mpf+python environments
    def _buildEnvironmentsTab(self) -> QWidget:
        self.venvAvailableTable = _table(["Name", "MPF", "Python", "Add-Ons", "Status", "Virtual Environment Path"])
        self.venvAvailableTable.itemSelectionChanged.connect(self._updateButtons)

        # The following adds a button to create a new vitual environment
        self.newVENVButton = QPushButton("New environment…")
        self.newVENVButton.clicked.connect(self.createVENVButton)

        # The following creates a new button to change the MPF version of a selected virtual environment
        self.changeVENVButton = QPushButton("Change MPF version…")
        self.changeVENVButton.clicked.connect(self.changeVENVmpf)

        # The following creates a new button to view the package versions from the virtual environment
        self.verifyVENVButton = QPushButton("Verify Package Versions")
        self.verifyVENVButton.setToolTip("Read installed package versions from the environment")
        self.verifyVENVButton.clicked.connect(self.verifyVENVPackages)

        # The following creates a button that opens the containing folder for a virtual environment
        self.openVENVButton = QPushButton("Open Virtual Environment's Folder")
        self.openVENVButton.setToolTip("Opens the folder containing the selected Virtual Environment")
        self.openVENVButton.clicked.connect(
            lambda: (selectedEnvironment := self.selectedEnvironment()) and _openMPFmachineFolder(selectedEnvironment.venvPath)
        )

        # The following creates a button to delete a selected virtual environment
        self.deleteVENVButton = QPushButton("Delete…")
        self.deleteVENVButton.clicked.connect(self.deleteVENV)

        # The following creates a box to hold the buttons related to virtualEnvironments
        venvButtons = QHBoxLayout()
        for currentButton in (self.newVENVButton, self.changeVENVButton, self.verifyVENVButton, self.openVENVButton):
            venvButtons.addWidget(currentButton)
        venvButtons.addStretch()
        venvButtons.addWidget(self.deleteVENVButton)

        # The following lays out the virtual environment tab
        venvTab = QWidget()
        venvLayout = QVBoxLayout(venvTab)
        venvLayout.addWidget(self.venvAvailableTable)
        venvLayout.addLayout(venvButtons)
        return venvTab

    # The following function is used to build to the projects tab
    def _buildProjectsTab(self) -> QWidget:

        # The following builds the project list table
        self.projectListTable = _table(["Project Name", "Environment", "Config", "Verification Status", "Path"])
        self.projectListTable.itemSelectionChanged.connect(self._updateButtons)

        # The following adds a button for new MPF Projects
        self.newprojectButton = QPushButton("New MPF project…")
        self.newprojectButton.clicked.connect(self.createNewProject)

        # The following adds a button to add an existing MPF project via the machine folder
        self.addProjectButton = QPushButton("Add existing MPF Project…")
        self.addProjectButton.clicked.connect(self.addExistingProject)
        self.addProjectButton.setToolTip("Add an Existing MPF Project via the machine directory")

        # The following adds a button to open a selected MPF machine folder
        self.openProjectFolderButton = QPushButton("Open MPF machine folder")
        self.openProjectFolderButton.clicked.connect(
            lambda: (p := self.selectedProject()) and _openMPFmachineFolder(Path(p.path))
        )

        # The following adds a button to remove a mpf project from the list
        self.removeProjectButton = QPushButton("Remove from list")
        self.removeProjectButton.clicked.connect(self.removeProject)

        # The following sets up a layout for the project management buttons
        projectManagementButtonBar = QHBoxLayout()
        for currentButton in (self.newprojectButton, self.addProjectButton, self.openProjectFolderButton):
            projectManagementButtonBar.addWidget(currentButton)
        projectManagementButtonBar.addStretch()
        projectManagementButtonBar.addWidget(self.removeProjectButton)

        #The following sets up the combination box for the run mode options
        self.runModeOption = QComboBox()
        for label, mode in mpfProjects.RUN_MODES.items():
            self.runModeOption.addItem(label, mode)

        # The following sets up the combination hardware options
        self.hardwareOption = QComboBox()
        for label, flags in mpfProjects.HARDWARE_MODES.items():
            self.hardwareOption.addItem(label, flags)
        self.hardwareOption.setCurrentIndex(2)

        # The following sets up if the media controller will be flagged out
        self.runMediaControllerOption = QCheckBox("No media controller (-b)")
        self.runMediaControllerOption.setToolTip(
            "Without this, MPF waits for a media controller (GMC or mpf-mc) to connect over BCP"
        )

        # The following adds an extra text space for additional arguments
        self.extraRunArguments = QLineEdit()
        self.extraRunArguments.setPlaceholderText("extra arguments, e.g. -v")

        # The following adds a run MPF Button
        self.runMPFButton = QPushButton("Run MPF")
        self.runMPFButton.clicked.connect(self.runMPFProject)

        # The following adds a stop button for MPF
        self.stopMPFButton = QPushButton("Stop MPF")
        self.stopMPFButton.clicked.connect(self.stopMPFProject)

        # The following lays out the run configuration buttons
        runConfigurationLayout = QHBoxLayout()
        runConfigurationLayout.addWidget(QLabel("Run:"))
        runConfigurationLayout.addWidget(self.runModeOption)
        runConfigurationLayout.addWidget(self.hardwareOption)
        runConfigurationLayout.addWidget(self.runMediaControllerOption)
        runConfigurationLayout.addWidget(self.extraRunArguments, 1)
        runConfigurationLayout.addWidget(self.runMPFButton)
        runConfigurationLayout.addWidget(self.stopMPFButton)

        # The following puts all the project tab elements together
        projectTabPage = QWidget()
        projectTabLayout = QVBoxLayout(projectTabPage)
        projectTabLayout.addWidget(self.projectListTable)
        projectTabLayout.addLayout(projectManagementButtonBar)
        projectTabLayout.addLayout(runConfigurationLayout)
        return projectTabPage

    # The following utilities help accomplish functions in the mainWindow

    # The following logs text to the output viewer
    def outputLogger(self, text: str) -> None:
        self.outputViewer.appendPlainText(text)

    # The following outputs the selected virtual environment
    def selectedEnvironment(self) -> VirtualEnvironment | None:
        selectedRow = self.venvAvailableTable.currentRow()
        if selectedRow < 0 or not self.venvAvailableTable.selectedItems():
            return None
        return self.storedData.get_environment(self.venvAvailableTable.item(selectedRow, 0).data(Qt.ItemDataRole.UserRole))

    # The following outputs the selected project
    def selectedProject(self) -> Project | None:
        row = self.projectListTable.currentRow()
        if row < 0 or not self.projectListTable.selectedItems():
            return None
        return self.storedData.getProjectbyPath(self.projectListTable.item(row, 0).data(Qt.ItemDataRole.UserRole))

    # The following refreshes the main Window
    def refresh(self) -> None:

        # The following updates the virtualEnvironmentTable
        selectedVENV = self.selectedEnvironment()
        self.venvAvailableTable.setRowCount(0)
        for environment in self.storedData.environments:
            row = self.venvAvailableTable.rowCount()
            self.venvAvailableTable.insertRow(row)
            self.venvAvailableTable.setItem(row, 0, _item(environment.name, environment.name))
            self.venvAvailableTable.setItem(row, 1, _item(environment.mpf_version))
            self.venvAvailableTable.setItem(row, 2, _item(environment.python))
            self.venvAvailableTable.setItem(row, 3, _item(", ".join(environment.extras)))
            self.venvAvailableTable.setItem(row, 4, _item("OK" if environment.exists else "Missing"))
            self.venvAvailableTable.setItem(row, 5, _item(environment.path))
            if selectedVENV and environment.name == selectedVENV.name:
                self.venvAvailableTable.selectRow(row)

        # The following updates the project information table
        self.selectedProject = self.selectedProject()
        self.projectListTable.setRowCount(0)

        for projectTableItem in self.storedData.projects:
            row = self.projectListTable.rowCount()
            path = Path(projectTableItem.path)
            self.projectListTable.insertRow(row)
            self.projectListTable.setItem(row, 0, _item(projectTableItem.name, projectTableItem.path))
            combo = environmentPairing(self.storedData, projectTableItem.environment)
            combo.currentIndexChanged.connect(
                lambda _i, p=projectTableItem.path, c=combo: self._setProjectEnvironment(p, c.currentData())
            )
            self.projectListTable.setCellWidget(row, 1, combo)
            version = mpfProjects.config_version(path)
            self.projectListTable.setItem(row, 2, _item(f"v{version}" if version else "—"))
            if projectTableItem.path in self.runningProcesses:
                status = "Running"
            elif not path.exists():
                status = "Missing"
            elif not mpfProjects.is_mpf_project(path):
                status = "No config/config.yaml"
            else:
                status = "OK"
            self.projectListTable.setItem(row, 3, _item(status))
            self.projectListTable.setItem(row, 4, _item(projectTableItem.path))
            if selectedProject and projectTableItem.path == selectedProject.path:
                self.projectListTable.selectRow(row)
        self._updateButtons()

    # The Following updates the button States
    def _updateButtons(self) -> None:
        idle = not self.commandQueue.busy
        environment = self.selectedEnvironment()
        self.newVENVButton.setEnabled(idle)
        for b in (self.changeVENVButton, self.verifyVENVButton, self.deleteVENVButton):
            b.setEnabled(idle and environment is not None and environment.exists)
        self.deleteVENVButton.setEnabled(idle and environment is not None)
        self.openVENVButton.setEnabled(environment is not None and environment.exists)

        projectTableItem = self.selectedProject()
        running = projectTableItem is not None and projectTableItem.path in self.runningProcesses
        self.openProjectFolderButton.setEnabled(projectTableItem is not None)
        self.removeProjectButton.setEnabled(projectTableItem is not None and not running)
        self.runMPFButton.setEnabled(projectTableItem is not None and not running)
        self.stopMPFButton.setEnabled(running)

    # The following sets the project environment
    def _setProjectEnvironment(self, path: str, env_name: str | None) -> None:
        self.storedData.setProjectVENV(path, env_name)

    # The following catches MPF-Manager errors for the main window
    def _error(self, message: str) -> None:
        QMessageBox.warning(self, "MPF Manager", message)

    # venv UI actions

    # The following button helps create new virtual environments
    def createVENVButton(self) -> None:
        dialog = VENVManagementDialog(self.storedData, self)
        if dialog.exec():
            # Default the next new environment to the folder chosen this time.
            folder = str(dialog.venvParentFolderPath())
            if folder != self.storedData.settings.venvDirectory:
                self.storedData.settings.venvDirectory = folder
                self.storedData.save()
            self._applyPlan(dialog.plan(), create=True)

    # The following changes the MPF related to a selected VENV
    def changeVENVmpf(self) -> None:
        environment = self.selectedEnvironment()
        if not environment:
            return
        dialog = VENVManagementDialog(self.storedData, self, environment)
        if dialog.exec():
            self._applyPlan(dialog.plan(), create=False)

    # The following attempts to create a venv based on the plan via a dialog
    def _applyPlan(self, plannedVENV: venvDialogData, create: bool) -> None:
        try:
            commandList = []
            if create:
                commandList.append(uvCMDs.setupVENV(plannedVENV.venvPath, plannedVENV.pythonVersion))
            if plannedVENV.remove:
                commandList.append(uvCMDs.uninstallVENVPackages(plannedVENV.venvPath, plannedVENV.packagesToRemove))
            commandList.append(uvCMDs.installVENVPackages(plannedVENV.venvPath, plannedVENV.companionPackages))
        except uvCMDs.UvNotFoundError as exc:
            self._error(str(exc))
            return

        # Function to be called when virtual environment creation is attempted
        def done(ok: bool) -> None:
            # The following is called to output the reason an environment failed to setup
            if not ok:
                self.logResult("Environment setup failed; see the output above.")
                if create and plannedVENV.venvPath.exists():
                    self.logResult(f"The partial environment was left at {plannedVENV.venvPath}")
                return
            if create:
                self.storedData.addVENV(
                    VirtualEnvironment(plannedVENV.venvName, str(plannedVENV.venvPath), plannedVENV.pythonVersion, plannedVENV.mpfVersion, plannedVENV.companionPackages)
                )
            else:
                environment = self.storedData.getVENVbyName(plannedVENV.venvName)
                environment.mpfVersion, environment.companionPackages = plannedVENV.mpfVersion, plannedVENV.companionPackages
                self.storedData.save()
            self.logResult(f"Environment '{plannedVENV.venvName}' now has MPF {plannedVENV.mpfVersion}.")
            self.refreshMainWindow()

        self.commandQueue.run(commandList, done)

    # The following function verifies virtual environment packages for errors
    def verifyVENVPackages(self) -> None:
        environment = self.selectedEnvironment()
        if not environment:
            return
        self.logResult(f"Checking packages in '{environment.venvName}'…")

        # The following processes the finish of the verification process
        def done(packages: dict[str, str]) -> None:
            version = packages.get("mpf")
            if not version:
                self.logResult(f"mpf is not installed in '{environment.venvName}'.")
                return
            environment.mpfVersion = version
            environment.companionPackages = [package for package in environment.companionPackages if package in packages]
            self.storedData.save()
            installedPackageText = ", ".join(f"{package} {packages[package]}" for package in ("mpf", *environment.extras))
            self.logResult(f"'{environment.name}': {installedPackageText}")
            self.refreshMainWindow()

        run_in_thread(lambda: uvCMDs.listVENVPackages(environment.venvPath), done, self.logResult)

    # The following function deletes virtual environments when necessary
    def deleteVENV(self) -> None:
        environmentToDelete = self.selectedEnvironment()
        if not environmentToDelete:
            return
        projectsUsingVENV = [projectUsingVENV.projectName for projectUsingVENV in self.storedData.projectList if projectUsingVENV.virtualEnvironment == environmentToDelete.venvName]
        warningText = f"Delete environment '{environmentToDelete.venvName}' and its folder?\n\n{environmentToDelete.venvPath}"

        # The following warns about deletion and which projects currently run using that Environment
        if projectsUsingVENV:
            warningText += "\n\nUsed by: " + ", ".join(projectsUsingVENV)
        if QMessageBox.question(self, "Delete environment", warningText) != QMessageBox.StandardButton.Yes:
            return
        if environmentToDelete.exists:
            # Only remove folders that really are virtual environments.
            shutil.rmtree(environmentToDelete.venvPath, ignore_errors=True)
        self.storedData.removeVENV(environmentToDelete.venvName)
        self.logResult(f"Deleted environment '{environmentToDelete.venvName}'.")
        self.refreshMainWindow()

    # project ui actions

    # The following Function creates a new project
    def createNewProject(self) -> None:
        newProjectDialog = mpfProjectCreationDialog(self.storedData, self)
        if not newProjectDialog.exec():
            return
        newProjectPath = newProjectDialog.path()
        try:
            mpfProjects.createNewMPFProject(newProjectPath, newProjectDialog.projectName.text().strip())
            self.storedData.addProject(
                Project(newProjectDialog.projectName.text().strip(), str(newProjectPath), newProjectDialog.virtualEnvironment.currentData())
            )
        except (OSError, ValueError) as exc:
            self._error(str(exc))
            return
        self.logResult(f"Created MPF project at {newProjectPath}")
        self.tabs.setCurrentIndex(1)
        self.refreshMainWindow()

    # The following is used to create an existing MPF machine by directory
    def addExistingProject(self) -> None:
        existingMachineFolder = QFileDialog.getExistingDirectory(
            self, "Where is your existing MPF Machine Folder", self.storedData.settings.projectDirectory
        )
        if not existingMachineFolder:
            return

        # The following checks to see if a project already exists there, and if not offers to create one.
        pathToCheck = Path(existingMachineFolder)
        if not mpfProjects.checkMPFProjectAtPath(pathToCheck):
            responseDialogForMissingProject = QMessageBox.question(
                self,
                "Add project",
                f"'{pathToCheck}' has no config/config.yaml, so it does not look like an MPF project. "
                "Add it anyway?",
            )
            if responseDialogForMissingProject != QMessageBox.StandardButton.Yes:
                return
        try:
            self.storedData.addProject(Project(pathToCheck.projectName, str(pathToCheck)))
        except ValueError as exc:
            self._error(str(exc))
            return
        self.refreshMainWindow()

    # The following is used to remove a project from the list
    def removeProject(self) -> None:
        projectToRemove = self.selectedProject()
        if projectToRemove:
            self.storedData.removeProject(projectToRemove.projectPath)
            self.logResult(f"Removed '{projectToRemove.projectName}' from the list (files were not deleted).")
            self.refreshMainWindow()

    # The following is used to run a mpf project
    def runMPFProject(self) -> None:
        projectToRun = self.selectedProject()

        # The following catches situations where a project or environment are not 
        # setup properly
        if not projectToRun:
            return
        environment = self.storedData.get_environment(projectToRun.environment)
        if not environment:
            self._error("Choose an environment for this project first.")
            return
        mpfRunMode = self.runModeOption.currentData()
        if mpfRunMode in ("both", "mc") and "mpf-mc" not in environment.extras:
            self._error(f"'{environment.name}' does not have mpf-mc installed.")
            return
        if mpfRunMode == "monitor" and "mpf-monitor" not in environment.extras:
            self._error(f"'{environment.name}' does not have mpf-monitor installed.")
            return
        if not environment.executable("mpf").exists():
            self._error(f"MPF is not installed in '{environment.name}' ({environment.executable('mpf')}).")
            return
        
        # The following catches exceptions related to extra arguments
        try:
            extraArguments = shlex.split(self.extraRunArguments.text())
        except ValueError as argumentException:
            self._error(f"Invalid extra arguments: {argumentException}")
            return
        
        if mpfRunMode == "game" and self.runMediaControllerOption.isChecked():
            extraArguments.insert(0, "-b")

        # The following sets up the command for the process
        runCommand = mpfProjects.run_command(environment, mpfRunMode, self.hardwareOption.currentData(), extraArguments)

        # The following sets up the MPF Run Process and starts it
        proc = RunningProcess(runCommand, Path(projectToRun.path), self)
        proc.output.connect(lambda text, name=projectToRun.name: self.logResult(f"[{name}] {text}"))
        proc.stopped.connect(lambda code, p=projectToRun: self._project_stopped(p, code))
        self.runningProcesses[projectToRun.path] = proc
        proc.start()

        self.refreshMainWindow()

    # The following is used to stop a mpf project
    def stopMPFProject(self) -> None:
        projectToStop = self.selectedProject()
        if projectToStop and (process := self.runningProcesses.get(projectToStop.path)):
            process.stop()

    # The following is used to process a project stopping
    def _project_stopped(self, stoppedProject: Project, stopCode: int) -> None:
        if processStopped := self.runningProcesses.pop(stoppedProject.path, None):
            processStopped.deleteLater()
        self.logResult(f"[{stoppedProject.projectName}] exited with code {stopCode}")
        self.refreshMainWindow()

    # additional utiltities

    # The following is used to edit the settings of the application
    def edit_settings(self) -> None:
        settingsDialog = SettingsDialog(self.storedData.settings, self)
        if settingsDialog.exec():
            settingsDialog.apply(self.storedData.settings)
            self.storedData.save()

    # The following is used to close the application
    def closeEvent(self, closeEvent) -> None:  # noqa: N802 - Qt override

        # The following closes all of the running processes upon a close event
        for processToStop in list(self.runningProcesses.values()):
            processToStop.stop()
        super().closeEvent(closeEvent)