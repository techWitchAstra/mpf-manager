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
from typing import cast

# The following imports the used Qt assets for Main Window
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QFontDatabase, QStandardItemModel
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
from mpfmanager.core import uvManager as uvCMDs
from mpfmanager.core.storageManager import Project, StorageProcessor, VirtualEnvironment
from mpfmanager.ui.dialogs import (
    SettingsDialog,
    VENVManagementDialog,
    environmentPairing,
    mpfProjectCreationDialog,
    venvDialogData,
)
from mpfmanager.ui.uiWorkers import CommandQueue, RunningProcess, runInThread


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
        self.commandQueue.outputSignal.connect(self.outputLogger)
        self.commandQueue.busyChangedSignal.connect(self._updateButtons)
        self.runningProcesses: dict[str, dict[str, RunningProcess]] = {}

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
        open_config.triggered.connect(lambda: _openMPFmachineFolder(self.storedData.homePath))
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
            lambda: (
                (selectedEnvironment := self.selectedEnvironment())
                and _openMPFmachineFolder(selectedEnvironment.venvPath)
            )
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
            lambda: (p := self.selectedProject()) and _openMPFmachineFolder(Path(p.projectPath))
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

        # The following sets up the combination box for the run mode options
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

        self.runMPFMonitorCheckBox = QCheckBox("Run MPF-Monitor?")
        self.runMPFMonitorCheckBox.setToolTip("Check to run monitor when opening MPF")
        self.runModeOption.currentIndexChanged.connect(
            self._updateRunOptions
        )  # The following lets the godot project be opened in the editor rather than run
        self.openGodotEditorCheckBox = QCheckBox("Open in Godot editor")
        self.openGodotEditorCheckBox.setToolTip("Opens the GMC project in the Godot editor instead of running it")
        self.projectListTable.itemSelectionChanged.connect(self._updateRunOptions)

        # The following lays out the run configuration buttons
        runConfigurationLayout = QHBoxLayout()
        runConfigurationLayout.addWidget(QLabel("Run:"))
        runConfigurationLayout.addWidget(self.runModeOption)
        runConfigurationLayout.addWidget(self.hardwareOption)
        runConfigurationLayout.addWidget(self.runMediaControllerOption)
        runConfigurationLayout.addWidget(self.runMPFMonitorCheckBox)
        runConfigurationLayout.addWidget(self.openGodotEditorCheckBox)
        runConfigurationLayout.addWidget(self.extraRunArguments, 1)
        runConfigurationLayout.addWidget(self.runMPFButton)
        runConfigurationLayout.addWidget(self.stopMPFButton)

        # The following puts all the project tab elements together
        projectTabPage = QWidget()
        projectTabLayout = QVBoxLayout(projectTabPage)
        projectTabLayout.addWidget(self.projectListTable)
        projectTabLayout.addLayout(projectManagementButtonBar)
        projectTabLayout.addLayout(runConfigurationLayout)

        self._updateRunOptions()

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
        selectedItem = self.venvAvailableTable.item(selectedRow, 0)
        if selectedItem is None:
            return None
        return self.storedData.getVENVbyName(selectedItem.data(Qt.ItemDataRole.UserRole))

    # The following outputs the selected project
    def selectedProject(self) -> Project | None:
        row = self.projectListTable.currentRow()
        if row < 0 or not self.projectListTable.selectedItems():
            return None
        selectedProjectItem = self.projectListTable.item(row, 0)
        if selectedProjectItem is None:
            return None
        return self.storedData.getProjectbyPath(selectedProjectItem.data(Qt.ItemDataRole.UserRole))

    # The following refreshes the main Window
    def refreshMainWindow(self) -> None:

        # The following updates the virtualEnvironmentTable
        selectedVENV = self.selectedEnvironment()
        self.venvAvailableTable.setRowCount(0)
        for environment in self.storedData.environmentList:
            row = self.venvAvailableTable.rowCount()
            self.venvAvailableTable.insertRow(row)
            self.venvAvailableTable.setItem(row, 0, _item(environment.venvName, environment.venvName))
            self.venvAvailableTable.setItem(row, 1, _item(environment.installedMPFVersion))
            self.venvAvailableTable.setItem(row, 2, _item(environment.installedPython))
            self.venvAvailableTable.setItem(row, 3, _item(", ".join(environment.additionalPackages)))
            self.venvAvailableTable.setItem(row, 4, _item("OK" if environment.exists else "Missing"))
            self.venvAvailableTable.setItem(row, 5, _item(environment.pathToVENV))
            if selectedVENV and environment.venvName == selectedVENV.venvName:
                self.venvAvailableTable.selectRow(row)

        # The following updates the project information table
        selectedProject = self.selectedProject()
        self.projectListTable.setRowCount(0)

        for projectTableItem in self.storedData.projectList:
            row = self.projectListTable.rowCount()
            path = Path(projectTableItem.projectPath)
            self.projectListTable.insertRow(row)
            self.projectListTable.setItem(row, 0, _item(projectTableItem.projectName, projectTableItem.projectPath))
            combo = environmentPairing(self.storedData, projectTableItem.virtualEnvironment)
            combo.currentIndexChanged.connect(
                lambda _i, p=projectTableItem.projectPath, c=combo: self._setProjectEnvironment(p, c.currentData())
            )
            self.projectListTable.setCellWidget(row, 1, combo)
            version = mpfProjects.checkConfigVersion(path)
            self.projectListTable.setItem(row, 2, _item(f"v{version}" if version else "—"))
            if projectTableItem.projectPath in self.runningProcesses:
                runningLabels = self.runningProcesses[projectTableItem.projectPath]
                status = f"Running ({' + '.join(runningLabels)})"
            elif not path.exists():
                status = "Missing"
            elif not mpfProjects.checkMPFProjectAtPath(path):
                status = "No config/config.yaml"
            else:
                status = "OK"
            self.projectListTable.setItem(row, 3, _item(status))
            self.projectListTable.setItem(row, 4, _item(projectTableItem.projectPath))
            if selectedProject and projectTableItem.projectPath == selectedProject.projectPath:
                self.projectListTable.selectRow(row)
        self._updateButtons()

    # The Following updates the button States
    def _updateButtons(self) -> None:
        idle = not self.commandQueue.isBusy
        environment = self.selectedEnvironment()
        self.newVENVButton.setEnabled(idle)
        for b in (self.changeVENVButton, self.verifyVENVButton, self.deleteVENVButton):
            b.setEnabled(idle and environment is not None and environment.exists)
        self.deleteVENVButton.setEnabled(idle and environment is not None)
        self.openVENVButton.setEnabled(environment is not None and environment.exists)

        projectTableItem = self.selectedProject()
        running = projectTableItem is not None and projectTableItem.projectPath in self.runningProcesses
        self.openProjectFolderButton.setEnabled(projectTableItem is not None)
        self.removeProjectButton.setEnabled(projectTableItem is not None and not running)
        self.runMPFButton.setEnabled(projectTableItem is not None and not running)
        self.stopMPFButton.setEnabled(running)

    # The following sets the project environment
    def _setProjectEnvironment(self, path: str, env_name: str | None) -> None:
        self.storedData.setProjectVENV(path, env_name)

        # The following enables only the run options that the selected project's environment supports

        # The following enables only the run options that the selected project's environment supports

    def _updateRunOptions(self) -> None:
        selectedProject = self.selectedProject()
        environment = self.storedData.getVENVbyName(selectedProject.virtualEnvironment) if selectedProject else None
        gmcAllowed = mpfProjects.isGMCEligible(environment)

        # The following disables the GMC modes for MPF before 0.80, and mpf-mc modes for 0.80 and after
        # QComboBox.model() is typed as QAbstractItemModel, but is a QStandardItemModel by default
        runModeModel = cast(QStandardItemModel, self.runModeOption.model())
        for index in range(self.runModeOption.count()):
            mode = self.runModeOption.itemData(index)
            enabled = True
            if mode in mpfProjects.GMC_MODES:
                enabled = gmcAllowed
            elif mode in mpfProjects.MPF_MC_MODES and environment is not None:
                enabled = not gmcAllowed
            runModeModel.item(index).setEnabled(enabled)

        # The following moves off a mode that is no longer allowed
        if not runModeModel.item(self.runModeOption.currentIndex()).isEnabled():
            self.runModeOption.setCurrentIndex(self.runModeOption.findData("game"))

        currentMode = self.runModeOption.currentData()
        monitorAllowed = currentMode in mpfProjects.MONITOR_COMPATIBLE_MODES
        self.runMPFMonitorCheckBox.setEnabled(monitorAllowed)
        if not monitorAllowed:
            self.runMPFMonitorCheckBox.setChecked(False)
        self.runMediaControllerOption.setEnabled(currentMode == "game")
        self.openGodotEditorCheckBox.setEnabled(currentMode in mpfProjects.GMC_MODES)

        # The following finds the GMC (godot) folder for a project, asking the user if it can't be found

    def _resolveGMCPath(self, project: Project) -> Path | None:
        if project.gmcFolderPath and (Path(project.gmcFolderPath) / "project.godot").is_file():
            return Path(project.gmcFolderPath)
        if foundPath := mpfProjects.findGodotProject(Path(project.projectPath)):
            return foundPath

        chosenFolder = QFileDialog.getExistingDirectory(
            self, "Where is the GMC (Godot) project for this machine?", project.projectPath
        )
        if not chosenFolder:
            return None
        if not (Path(chosenFolder) / "project.godot").is_file():
            self._error(f"'{chosenFolder}' has no project.godot, so it does not look like a Godot project.")
            return None
        self.storedData.setProjectGMCPath(project.projectPath, chosenFolder)
        return Path(chosenFolder)

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
                self.storedData.saveConfiguration()
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
            if plannedVENV.packagesToRemove:
                commandList.append(uvCMDs.uninstallVENVPackages(plannedVENV.venvPath, plannedVENV.packagesToRemove))
            commandList.append(uvCMDs.installVENVPackages(plannedVENV.venvPath, plannedVENV.mpfVersionRequirements))
        except uvCMDs.UvNotFoundError as exc:
            self._error(str(exc))
            return

        # Function to be called when virtual environment creation is attempted
        def done(ok: bool) -> None:
            # The following is called to output the reason an environment failed to setup
            if not ok:
                self.outputLogger("Environment setup failed; see the output above.")
                if create and plannedVENV.venvPath.exists():
                    self.outputLogger(f"The partial environment was left at {plannedVENV.venvPath}")
                return
            if create:
                self.storedData.addVENV(
                    VirtualEnvironment(
                        plannedVENV.venvName,
                        str(plannedVENV.venvPath),
                        plannedVENV.pythonVersion,
                        plannedVENV.mpfVersion,
                        plannedVENV.companionPackages,
                    )
                )
            else:
                environment = self.storedData.getVENVbyName(plannedVENV.venvName)
                if environment is None:
                    self.outputLogger(f"Environment '{plannedVENV.venvName}' is no longer registered.")
                    return
                environment.installedMPFVersion, environment.additionalPackages = (
                    plannedVENV.mpfVersion,
                    plannedVENV.companionPackages,
                )
                self.storedData.saveConfiguration()
            self.outputLogger(f"Environment '{plannedVENV.venvName}' now has MPF {plannedVENV.mpfVersion}.")
            self.refreshMainWindow()

        self.commandQueue.run(commandList, done)

    # The following function verifies virtual environment packages for errors
    def verifyVENVPackages(self) -> None:
        environment = self.selectedEnvironment()
        if not environment:
            return
        self.outputLogger(f"Checking packages in '{environment.venvName}'…")

        # The following processes the finish of the verification process
        def done(packages: dict[str, str]) -> None:
            version = packages.get("mpf")
            if not version:
                self.outputLogger(f"mpf is not installed in '{environment.venvName}'.")
                return
            environment.installedMPFVersion = version
            environment.additionalPackages = [
                package for package in environment.additionalPackages if package in packages
            ]
            self.storedData.saveConfiguration()
            installedPackageText = ", ".join(
                f"{package} {packages[package]}" for package in ("mpf", *environment.additionalPackages)
            )
            self.outputLogger(f"'{environment.venvName}': {installedPackageText}")
            self.refreshMainWindow()

        runInThread(lambda: uvCMDs.listVENVPackages(environment.venvPath), done, self.outputLogger)

    # The following function deletes virtual environments when necessary
    def deleteVENV(self) -> None:
        environmentToDelete = self.selectedEnvironment()
        if not environmentToDelete:
            return
        projectsUsingVENV = [
            projectUsingVENV.projectName
            for projectUsingVENV in self.storedData.projectList
            if projectUsingVENV.virtualEnvironment == environmentToDelete.venvName
        ]
        warningText = (
            f"Delete environment '{environmentToDelete.venvName}' and its folder?\n\n{environmentToDelete.venvPath}"
        )

        # The following warns about deletion and which projects currently run using that Environment
        if projectsUsingVENV:
            warningText += "\n\nUsed by: " + ", ".join(projectsUsingVENV)
        if QMessageBox.question(self, "Delete environment", warningText) != QMessageBox.StandardButton.Yes:
            return
        if environmentToDelete.exists:
            # Only remove folders that really are virtual environments.
            shutil.rmtree(environmentToDelete.venvPath, ignore_errors=True)
        self.storedData.removeVENV(environmentToDelete.venvName)
        self.outputLogger(f"Deleted environment '{environmentToDelete.venvName}'.")
        self.refreshMainWindow()

    # project ui actions

    # The following Function creates a new project
    def createNewProject(self) -> None:
        newProjectDialog = mpfProjectCreationDialog(self.storedData, self)
        if not newProjectDialog.exec():
            return
        newProjectPath = newProjectDialog.projectPath()
        try:
            mpfProjects.createNewMPFProject(newProjectPath, newProjectDialog.projectName.text().strip())
            self.storedData.addProject(
                Project(
                    newProjectDialog.projectName.text().strip(),
                    str(newProjectPath),
                    newProjectDialog.environmentPair.currentData(),
                )
            )
        except (OSError, ValueError) as exc:
            self._error(str(exc))
            return
        self.outputLogger(f"Created MPF project at {newProjectPath}")
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
                f"'{pathToCheck}' has no config/config.yaml, so it does not look like an MPF project. Add it anyway?",
            )
            if responseDialogForMissingProject != QMessageBox.StandardButton.Yes:
                return
        try:
            self.storedData.addProject(Project(pathToCheck.name, str(pathToCheck)))
        except ValueError as exc:
            self._error(str(exc))
            return
        self.refreshMainWindow()

    # The following is used to remove a project from the list
    def removeProject(self) -> None:
        projectToRemove = self.selectedProject()
        if projectToRemove:
            self.storedData.removeProject(projectToRemove.projectPath)
            self.outputLogger(f"Removed '{projectToRemove.projectName}' from the list (files were not deleted).")
            self.refreshMainWindow()

    # The following is used to run a mpf project
    def runMPFProject(self) -> None:
        projectToRun = self.selectedProject()

        # The following catches situations where a project or environment are not
        # setup properly
        if not projectToRun:
            return
        environment = self.storedData.getVENVbyName(projectToRun.virtualEnvironment)
        if not environment:
            self._error("Choose an environment for this project first.")
            return
        mpfRunMode = self.runModeOption.currentData()
        if mpfRunMode in ("both", "mc") and "mpf-mc" not in environment.additionalPackages:
            self._error(f"'{environment.venvName}' does not have mpf-mc installed.")
            return
        if mpfRunMode == "monitor" and "mpf-monitor" not in environment.additionalPackages:
            self._error(f"'{environment.venvName}' does not have mpf-monitor installed.")
            return
        if self.runMPFMonitorCheckBox.isChecked() and "mpf-monitor" not in environment.additionalPackages:
            self._error(f"'{environment.venvName}' does not have mpf-monitor installed.")
            return
        gmcCommand: list[str] | None = None
        gmcFolderPath: Path | None = None
        if mpfRunMode in mpfProjects.GMC_MODES:
            if not mpfProjects.isGMCEligible(environment):
                self._error(
                    f"GMC requires MPF 0.80 or newer, '{environment.venvName}' has MPF {environment.installedMPFVersion}."
                )
                return
            godotExecutablePath = self.storedData.settings.godotExecutablePath
            if not mpfProjects.checkGodotExecutable(godotExecutablePath):
                self._error("Set the path to your installed Godot in File → Settings before running GMC.")
                return
            gmcFolderPath = self._resolveGMCPath(projectToRun)
            if gmcFolderPath is None:
                return
            gmcCommand = mpfProjects.runGMC(
                godotExecutablePath, gmcFolderPath, self.openGodotEditorCheckBox.isChecked()
            )

        # GMC only needs godot, MPF is assumed to already be running elsewhere (or not needed for editing)
        if mpfRunMode == "gmconly" and gmcCommand and gmcFolderPath:
            self._startProjectProcess(projectToRun, gmcCommand, "gmc", gmcFolderPath)
            self.refreshMainWindow()
            return
        if not environment.executable("mpf").exists():
            self._error(f"MPF is not installed in '{environment.venvName}' ({environment.executable('mpf')}).")
            return

        # The following catches exceptions related to extra arguments
        try:
            extraArguments = shlex.split(self.extraRunArguments.text())
        except ValueError as argumentException:
            self._error(f"Invalid extra arguments: {argumentException}")
            return

        if mpfRunMode == "game" and self.runMediaControllerOption.isChecked():
            extraArguments.insert(0, "-b")

            # The following sets up the commands for the game and, if requested, the monitor
        runCommands = mpfProjects.runMPFWithMonitor(
            environment,
            mpfRunMode,
            self.hardwareOption.currentData(),
            extraArguments,
            self.runMPFMonitorCheckBox.isChecked(),
        )

        # The following starts the game, and schedules the monitor to start once the game has had time to start up
        gameProcess = self._startProjectProcess(projectToRun, runCommands[0], "game")

        if gmcCommand and gmcFolderPath:
            QTimer.singleShot(
                mpfProjects.GMC_START_DELAY_MS,
                lambda: self._startDelayedCompanion(projectToRun, gmcCommand, "gmc", gameProcess, gmcFolderPath),
            )
        if len(runCommands) > 1:
            monitorCommand = runCommands[1]
            QTimer.singleShot(
                mpfProjects.MONITOR_START_DELAY_MS,
                lambda: self._startDelayedCompanion(projectToRun, monitorCommand, "monitor", gameProcess),
            )

        self.refreshMainWindow()

    # The following is used to stop a mpf project, stopping the monitor before the game
    def stopMPFProject(self) -> None:
        projectToStop = self.selectedProject()
        if not projectToStop:
            return
        for process in reversed(list(self.runningProcesses.get(projectToStop.projectPath, {}).values())):
            process.stopProcess()

        # The following processes one of a project's processes stopping

    def _processStopped(self, project: Project, process: RunningProcess, label: str, stopCode: int) -> None:
        self.outputLogger(f"[{project.projectName}/{label}] exited with code {stopCode}")

        # The following removes the stopped process from the project's running processes
        projectProcesses = self.runningProcesses.get(project.projectPath, {})
        if projectProcesses.get(label) is process:
            del projectProcesses[label]
        process.deleteLater()

        # The monitor cannot do anything without the game, so it is stopped when the game stops
        if label == "game":
            for remainingProcess in list(projectProcesses.values()):
                remainingProcess.stopProcess()

        # Once nothing is left running, the project is no longer marked as running
        if not projectProcesses:
            self.runningProcesses.pop(project.projectPath, None)
            self.refreshMainWindow()

    # additional utiltities

    # The following is used to edit the settings of the application
    def edit_settings(self) -> None:
        settingsDialog = SettingsDialog(self.storedData.settings, self)
        if settingsDialog.exec():
            settingsDialog.applySettings(self.storedData.settings)
            self.storedData.saveConfiguration()

    # The following is used to close the application
    def closeEvent(self, closeEvent) -> None:  # noqa: N802 - Qt override

        # The following closes all of the running processes upon a close event, monitors before games
        for projectProcesses in list(self.runningProcesses.values()):
            for processToStop in reversed(list(projectProcesses.values())):
                processToStop.stopProcess()
        super().closeEvent(closeEvent)

        # The following starts one MPF related process for a project and tracks it under a label

    def _startProjectProcess(
        self, project: Project, command: list[str], label: str, workingPath: Path | None = None
    ) -> RunningProcess:
        process = RunningProcess(command, workingPath or Path(project.projectPath), self)
        process = RunningProcess(command, Path(project.projectPath), self)
        process.outputSignal.connect(
            lambda text, name=project.projectName, tag=label: self.outputLogger(f"[{name}/{tag}] {text}")
        )
        process.stoppedSignal.connect(
            lambda code, p=project, proc=process, tag=label: self._processStopped(p, proc, tag, code)
        )
        self.runningProcesses.setdefault(project.projectPath, {})[label] = process
        process.startProcess()
        return process

        # The following starts the monitor only if the same game it was scheduled for is still running

    # The following starts a companion process (monitor or gmc) only if the game it was scheduled for is still running
    def _startDelayedCompanion(
        self,
        project: Project,
        companionCommand: list[str],
        label: str,
        gameProcess: RunningProcess,
        workingPath: Path | None = None,
    ) -> None:
        projectProcesses = self.runningProcesses.get(project.projectPath, {})
        if projectProcesses.get("game") is not gameProcess:
            self.outputLogger(f"[{project.projectName}] the game is no longer running, so {label} was not started")
            return
        self._startProjectProcess(project, companionCommand, label, workingPath)
        self.refreshMainWindow()
