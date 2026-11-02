"""Main window: the managers' pages, with the Project Manager for running the open project, and its output log"""

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
from collections.abc import Callable
from pathlib import Path
from typing import cast

from packaging.version import Version

# The following imports the used Qt assets for Main Window
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QFontDatabase, QIcon, QKeySequence, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# The following imports the needed parts of the application from other files
from mpfmanager.core import compatibilityManager, gmcManager, sourceManager
from mpfmanager.core import projectManager as mpfProjects
from mpfmanager.core import uvManager as uvCMDs
from mpfmanager.core.storageManager import Project, RunProfile, StorageProcessor, VirtualEnvironment
from mpfmanager.ui.dialogs import (
    GMCProjectDialog,
    SettingsDialog,
    VENVManagementDialog,
    environmentPairing,
    mpfProjectCreationDialog,
    venvDialogData,
)
from mpfmanager.ui.managerTabs import PROJECT_MANAGER_TAB, SHOW_MANAGER_TAB, ManagerTabBar
from mpfmanager.ui.projectPicker import ProjectPickerDialog
from mpfmanager.ui.ribbon import Ribbon, actionButton, ribbonIcon
from mpfmanager.ui.showViewer import ShowViewerWindow
from mpfmanager.ui.theme import THEME_LABELS, applyTheme, setStatusBadge, themeName
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


# The following describes a project's state: running, missing, without a config, or ready to run
def projectStatus(project: Project, runningProcesses: dict[str, dict[str, RunningProcess]]) -> str:
    path = Path(project.projectPath)
    if project.projectPath in runningProcesses:
        return f"Running ({' + '.join(runningProcesses[project.projectPath])})"
    if not path.exists():
        return "Missing"
    if not mpfProjects.checkMPFProjectAtPath(path):
        return "No config/config.yaml"
    return "OK"


# The following is the window's title, followed by the open project's name
WINDOW_TITLE = "MPF-Manager"

# The following are the details of the open project shown on the Project Manager, with their labels
OVERVIEW_FIELDS = {
    "path": "Machine folder",
    "environment": "Environment",
    "config": "Config version",
    "gmc": "GMC project",
    "status": "Status",
}

# The following are the tabs of the Project Manager's ribbon: running the project, and the project itself
RUN_RIBBON_TAB, PROJECT_RIBBON_TAB = 0, 1

# The following is the smallest size the window grows to for the Show Manager, which shows the grid and playfield
SHOW_MANAGER_SIZE = (1400, 760)


# The following dialog lists the MPF+Python environments, with what can be done with them.  It is opened from the
# Settings menu, and stays open beside the window, so the output log can be seen while an environment is made
class EnvironmentsDialog(QDialog):
    def __init__(self, table: QTableWidget, actions: list[QAction | None], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("MPF+Python Environments")
        self.setModal(False)
        self.resize(880, 380)
        # The buttons sit on a panel of their own, as the ribbon's do
        toolCard = QWidget()
        toolCard.setObjectName("toolCard")
        toolCard.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        buttons = QHBoxLayout(toolCard)
        buttons.setContentsMargins(6, 4, 6, 4)
        self.buttons: list[QToolButton] = []
        for action in actions:
            if action is None:
                buttons.addStretch()
                continue
            button = actionButton(action)
            buttons.addWidget(button)
            self.buttons.append(button)
        closeButtons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        closeButtons.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addWidget(toolCard)
        layout.addWidget(table, 1)
        layout.addWidget(closeButtons)


# The following defines the main window for MPF Manager.  It holds each manager as a page, switched with the tabs down
# its left edge: the Project Manager, for running the project that is open, and the Show Manager.  Each page has its
# own ribbon and menus, and the menu bar shows the menus of the page shown.  A project is chosen in a dialog, at
# startup or from File > Open project
class MainWindow(QMainWindow):
    # The following function initializes the main window upon inital call
    def __init__(self, storedData: StorageProcessor | None = None):
        super().__init__()
        self.storedData = storedData or StorageProcessor()
        self.commandQueue = CommandQueue(self)
        self.commandQueue.outputSignal.connect(self.outputLogger)
        self.commandQueue.busyChangedSignal.connect(self._updateButtons)
        self.runningProcesses: dict[str, dict[str, RunningProcess]] = {}
        self.showViewerWindow: ShowViewerWindow | None = None
        self.currentProject: Project | None = None

        # The following sets up the application window
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(1000, 680)

        # The following sets up the run options, the environments list, and the output viewer console
        self._buildRunOptions()
        self.venvAvailableTable = _table(["Name", "MPF", "Python", "Add-Ons", "Status", "Virtual Environment Path"])
        self.venvAvailableTable.itemSelectionChanged.connect(self._updateButtons)
        self.outputViewer = QPlainTextEdit()
        self.outputViewer.setReadOnly(True)
        self.outputViewer.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.outputViewer.setMaximumBlockCount(5000)

        # The following builds the Project Manager's ribbon, and the dialog the environments are managed in
        self._buildRibbon()
        self.environmentsDialog = EnvironmentsDialog(
            self.venvAvailableTable,
            [
                self.newVENVAction,
                self.changeVENVAction,
                self.verifyVENVAction,
                self.openVENVAction,
                self.openSourceAction,
                None,
                self.deleteVENVAction,
            ],
            self,
        )
        (
            self.newVENVButton,
            self.changeVENVButton,
            self.verifyVENVButton,
            self.openVENVButton,
            self.openSourceButton,
            self.deleteVENVButton,
        ) = self.environmentsDialog.buttons

        # The following assembles the open project's overview and the output viewer, under the ribbon
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._buildOverview())
        splitter.addWidget(self.outputViewer)
        splitter.setSizes([300, 300])
        self.projectManagerPage = QWidget()
        projectManagerLayout = QVBoxLayout(self.projectManagerPage)
        projectManagerLayout.setContentsMargins(4, 0, 4, 4)
        projectManagerLayout.addWidget(self.ribbon)
        projectManagerLayout.addWidget(splitter, 1)

        # The following puts the managers' pages beside the tabs down the left edge that switch between them
        self.pages = QStackedWidget()
        self.pages.addWidget(self.projectManagerPage)
        self.managerTabs = ManagerTabBar(PROJECT_MANAGER_TAB)
        self.managerTabs.managerChosen.connect(self._managerChosen)
        windowWidget = QWidget()
        windowLayout = QHBoxLayout(windowWidget)
        windowLayout.setContentsMargins(0, 0, 0, 0)
        windowLayout.setSpacing(0)
        windowLayout.addWidget(self.managerTabs, 0, Qt.AlignmentFlag.AlignTop)
        windowLayout.addWidget(self.pages, 1)
        self.setCentralWidget(windowWidget)

        self._buildMenu()
        self._setPageMenus(self.projectManagerMenus)
        self._updateRunOptions()
        self.refreshMainWindow()

    # The following makes an action for the Project Manager, with its tooltip and icon
    def _action(
        self, text: str, tooltip: str = "", themeIcon: QIcon.ThemeIcon | None = None, symbol: str | None = None
    ) -> QAction:
        action = QAction(text, self)
        if tooltip:
            action.setToolTip(tooltip)
            action.setStatusTip(tooltip)
        if symbol is not None:
            action.setIcon(ribbonIcon(themeIcon, symbol))
        return action

    # The following builds the Project Manager's ribbon: a tab for running the project, and one for the project.  Each
    # button is an action, so the menus offer the same actions.  The environments' actions are shown in their dialog
    def _buildRibbon(self) -> None:
        ThemeIcon = QIcon.ThemeIcon

        # The following are the actions for projects
        self.openProjectAction = self._action(
            "Open project…", "Choose a project, make a new one, or open a machine folder", ThemeIcon.DocumentOpen, "📂"
        )
        self.openProjectAction.triggered.connect(lambda: self.showProjectPicker())
        self.newProjectAction = self._action("New project…", "Create a new MPF project", ThemeIcon.DocumentNew, "✚")
        self.newProjectAction.triggered.connect(lambda: self.openProject(self.createNewProject()))
        self.closeProjectAction = self._action("Close project", "Close the project, leaving no project open")
        self.closeProjectAction.triggered.connect(self.closeProject)
        self.openProjectFolderAction = self._action(
            "Machine folder", "Open the project's MPF machine folder", ThemeIcon.FolderOpen, "🗀"
        )
        self.openProjectFolderAction.triggered.connect(
            lambda: (p := self.selectedProject()) and _openMPFmachineFolder(Path(p.projectPath))
        )
        self.viewShowsAction = self._action(
            "View shows", "Open the project's show files in the Show Manager", None, "✦"
        )
        self.viewShowsAction.triggered.connect(self.openShowViewer)
        self.createGMCAction = self._action(
            "Create GMC project…",
            "Generate a blank Godot project with mpf-gmc configured in the machine folder",
            None,
            "◈",
        )
        self.createGMCAction.triggered.connect(lambda: self.createGMCProject())
        self.manageEnvironmentsAction = self._action(
            "Environments…", "Make, change and remove MPF+Python environments", None, "⚙"
        )
        self.manageEnvironmentsAction.triggered.connect(self.showEnvironments)

        # The following are the actions for environments, shown in the environments dialog
        self.newVENVAction = self._action(
            "New environment…", "Create a new MPF+Python environment", ThemeIcon.DocumentNew, "✚"
        )
        self.newVENVAction.triggered.connect(self.createVENVButton)
        self.changeVENVAction = self._action(
            "Change MPF version…", "Change the MPF version or add-ons of the selected environment", None, "⇅"
        )
        self.changeVENVAction.triggered.connect(self.changeVENVmpf)
        self.verifyVENVAction = self._action(
            "Verify packages", "Read installed package versions from the environment", ThemeIcon.SystemSearch, "✓"
        )
        self.verifyVENVAction.triggered.connect(self.verifyVENVPackages)
        self.openVENVAction = self._action(
            "Open environment folder",
            "Opens the folder containing the selected Virtual Environment",
            ThemeIcon.FolderOpen,
            "🗀",
        )
        self.openVENVAction.triggered.connect(
            lambda: (
                (selectedEnvironment := self.selectedEnvironment())
                and _openMPFmachineFolder(selectedEnvironment.venvPath)
            )
        )
        self.openSourceAction = self._action(
            "Open MPF source folder",
            "Opens the local MPF source folder an editable environment runs from",
            ThemeIcon.FolderOpen,
            "🗀",
        )
        self.openSourceAction.triggered.connect(
            lambda: (
                (selectedEnvironment := self.selectedEnvironment())
                and selectedEnvironment.isEditable
                and _openMPFmachineFolder(Path(selectedEnvironment.editableMPFPath))
            )
        )
        self.deleteVENVAction = self._action("Delete…", "Delete the selected environment", ThemeIcon.EditDelete, "✕")
        self.deleteVENVAction.triggered.connect(self.deleteVENV)

        # The following are the actions for running the project and its run profiles
        self.runMPFAction = self._action(
            "Run MPF", "Run the project with the run options", ThemeIcon.MediaPlaybackStart, "▶"
        )
        self.runMPFAction.triggered.connect(self.runMPFProject)
        self.stopMPFAction = self._action(
            "Stop MPF", "Stop the project's running game", ThemeIcon.MediaPlaybackStop, "■"
        )
        self.stopMPFAction.triggered.connect(self.stopMPFProject)
        self.runProfileAction = self._action("Run profile", "Run the chosen run profile", None, "▶")
        self.runProfileAction.triggered.connect(lambda: self.runRunProfile(self.selectedRunProfile()))
        self.loadRunProfileAction = self._action(
            "Load into options", "Set the run options to match the chosen run profile", None, "⇩"
        )
        self.loadRunProfileAction.triggered.connect(lambda: self.loadRunProfile(self.selectedRunProfile()))
        self.saveRunProfileAction = self._action(
            "Save as profile…",
            "Save the run options as a run profile of the project",
            ThemeIcon.DocumentSave,
            "💾",
        )
        self.saveRunProfileAction.triggered.connect(self.saveRunProfile)
        self.deleteRunProfileAction = self._action(
            "Delete profile", "Delete the chosen run profile", ThemeIcon.EditDelete, "✕"
        )
        self.deleteRunProfileAction.triggered.connect(self.deleteRunProfile)

        # The following chooses the environment the project runs in
        self.environmentOption = QComboBox()
        self.environmentOption.setMinimumWidth(240)
        self.environmentOption.setToolTip("The MPF+Python environment the project runs in")
        self.environmentOption.currentIndexChanged.connect(self._environmentChosen)

        self.ribbon = Ribbon()
        runTab = self.ribbon.addRibbonTab("Run")
        runGroup = runTab.addGroup("Run")
        self.runMPFButton = runGroup.addLargeAction(self.runMPFAction)
        self.stopMPFButton = runGroup.addLargeAction(self.stopMPFAction)
        optionsGroup = runTab.addGroup("Options")
        optionsGroup.addSmallWidget(self.runModeOption, "Run:")
        optionsGroup.addSmallWidget(self.hardwareOption, "Hardware:")
        optionsGroup.addSmallWidget(self.extraRunArguments, "Arguments:")
        for runCheckBox in (self.runMediaControllerOption, self.runMPFMonitorCheckBox, self.openGodotEditorCheckBox):
            optionsGroup.addSmallWidget(runCheckBox)
        profilesGroup = runTab.addGroup("Run profiles")
        profilesGroup.addSmallWidget(self.runProfileOption, "Profile:")
        profilesGroup.addSmallWidget(self.runAtStartupCheckBox)
        self.runProfileButton = profilesGroup.addSmallAction(self.runProfileAction)
        self.loadRunProfileButton = profilesGroup.addSmallAction(self.loadRunProfileAction)
        self.saveRunProfileButton = profilesGroup.addSmallAction(self.saveRunProfileAction)
        self.deleteRunProfileButton = profilesGroup.addSmallAction(self.deleteRunProfileAction)

        projectTab = self.ribbon.addRibbonTab("Project")
        projectGroup = projectTab.addGroup("Project")
        self.openProjectButton = projectGroup.addLargeAction(self.openProjectAction)
        self.newprojectButton = projectGroup.addLargeAction(self.newProjectAction)
        openGroup = projectTab.addGroup("Open")
        self.openProjectFolderButton = openGroup.addLargeAction(self.openProjectFolderAction)
        self.viewShowsButton = openGroup.addLargeAction(self.viewShowsAction)
        environmentGroup = projectTab.addGroup("Environment")
        environmentGroup.addSmallWidget(self.environmentOption, "Runs in:")
        self.manageEnvironmentsButton = environmentGroup.addSmallAction(self.manageEnvironmentsAction)
        godotGroup = projectTab.addGroup("Godot")
        self.createGMCButton = godotGroup.addLargeAction(self.createGMCAction)

    # The following builds out the Project Manager's menus, which the menu bar shows while the Project Manager is shown
    def _buildMenu(self) -> None:
        self.settingsAction = QAction("&Preferences…", self)
        self.settingsAction.triggered.connect(self.edit_settings)
        openConfigAction = QAction("Open config &folder", self)
        openConfigAction.triggered.connect(lambda: _openMPFmachineFolder(self.storedData.homePath))
        self.quitAction = QAction("&Quit", self)
        self.quitAction.setShortcuts(
            QKeySequence.keyBindings(QKeySequence.StandardKey.Quit) or [QKeySequence("Ctrl+Q")]
        )
        self.quitAction.triggered.connect(self.close)
        self.openProjectAction.setShortcut(QKeySequence(QKeySequence.StandardKey.Open))
        self.newProjectAction.setShortcut(QKeySequence(QKeySequence.StandardKey.New))
        self.runMPFAction.setShortcut(QKeySequence("Ctrl+R"))
        self.stopMPFAction.setShortcut(QKeySequence("Ctrl+."))

        fileMenu = QMenu("&File", self)
        fileMenu.addActions([self.openProjectAction, self.newProjectAction, self.closeProjectAction])
        fileMenu.addSeparator()
        fileMenu.addAction(openConfigAction)
        fileMenu.addSeparator()
        fileMenu.addAction(self.quitAction)

        projectMenu = QMenu("&Project", self)
        projectMenu.addActions([self.openProjectFolderAction, self.viewShowsAction, self.createGMCAction])

        runMenu = QMenu("&Run", self)
        runMenu.addActions([self.runMPFAction, self.stopMPFAction])
        runMenu.addSeparator()
        runMenu.addActions(
            [self.runProfileAction, self.loadRunProfileAction, self.saveRunProfileAction, self.deleteRunProfileAction]
        )

        settingsMenu = QMenu("&Settings", self)
        settingsMenu.addActions([self.manageEnvironmentsAction, self.settingsAction])

        # The following switch between the managers, and show and hide the parts of the Project Manager
        self.projectManagerAction = QAction("Project Manager", self)
        self.projectManagerAction.setShortcut(QKeySequence("Ctrl+1"))
        self.projectManagerAction.triggered.connect(self.showProjectManager)
        self.showManagerAction = QAction("Show Manager", self)
        self.showManagerAction.setShortcut(QKeySequence("Ctrl+2"))
        self.showManagerAction.triggered.connect(self.openShowViewer)
        self.showRibbonAction = QAction("Ribbon", self)
        self.showRibbonAction.setCheckable(True)
        self.showRibbonAction.setChecked(True)
        self.showRibbonAction.toggled.connect(self.ribbon.setVisible)
        self.showOutputAction = QAction("Output log", self)
        self.showOutputAction.setCheckable(True)
        self.showOutputAction.setChecked(True)
        self.showOutputAction.toggled.connect(self.outputViewer.setVisible)
        viewMenu = QMenu("&View", self)
        viewMenu.addActions([self.projectManagerAction, self.showManagerAction])
        viewMenu.addSeparator()
        viewMenu.addActions([self.showRibbonAction, self.showOutputAction])

        self.projectManagerMenus = [fileMenu, projectMenu, runMenu, settingsMenu, viewMenu]
        # The managers can be switched between from either page's menus
        self.addActions([self.projectManagerAction, self.showManagerAction])

    # The following shows a page's menus on the menu bar
    def _setPageMenus(self, menus: list[QMenu]) -> None:
        menuBar = self.menuBar()
        menuBar.clear()
        for menu in menus:
            menuBar.addMenu(menu)

    # The following switches to the manager chosen on the left edge
    def _managerChosen(self, index: int) -> None:
        if index == PROJECT_MANAGER_TAB:
            self.showProjectManager()
        elif index == SHOW_MANAGER_TAB:
            self.openShowViewer()

    # The following builds the overview of the open project: where it is, what it runs in, and how it is.  Without a
    # project, it asks for one to be opened
    def _buildOverview(self) -> QWidget:
        self.overviewLabels: dict[str, QLabel] = {}
        overviewForm = QFormLayout()
        for field, label in OVERVIEW_FIELDS.items():
            valueLabel = QLabel()
            valueLabel.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            valueLabel.setWordWrap(True)
            overviewForm.addRow(f"{label}:", valueLabel)
            self.overviewLabels[field] = valueLabel
        self.projectHeading = QLabel()
        self.projectHeading.setObjectName("projectHeading")
        headingFont = self.projectHeading.font()
        headingFont.setPointSizeF(headingFont.pointSizeF() * 1.5)
        headingFont.setBold(True)
        self.projectHeading.setFont(headingFont)
        self.projectDetails = QWidget()
        self.projectDetails.setLayout(overviewForm)

        self.noProjectPrompt = QWidget()
        promptLayout = QVBoxLayout(self.noProjectPrompt)
        promptLayout.addStretch()
        promptLabel = QLabel("Open a project to get started")
        promptLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        promptLabel.setFont(headingFont)
        self.promptOpenButton = QPushButton("Open project…")
        self.promptOpenButton.setObjectName("primary")
        self.promptOpenButton.clicked.connect(lambda: self.showProjectPicker())
        promptLayout.addWidget(promptLabel)
        promptLayout.addWidget(self.promptOpenButton, 0, Qt.AlignmentFlag.AlignCenter)
        promptLayout.addStretch()

        # The overview sits on a panel, so the project's details stand out
        overview = QWidget()
        overview.setObjectName("overviewCard")
        overview.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        overviewLayout = QVBoxLayout(overview)
        overviewLayout.setContentsMargins(18, 14, 18, 14)
        overviewLayout.addWidget(self.projectHeading)
        overviewLayout.addWidget(self.projectDetails)
        overviewLayout.addWidget(self.noProjectPrompt, 1)
        overviewLayout.addStretch()
        return overview

    # The following builds the run options and run profiles the Run tab of the ribbon holds
    def _buildRunOptions(self) -> None:
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
        self.extraRunArguments.setMinimumWidth(160)

        self.runMPFMonitorCheckBox = QCheckBox("Run MPF-Monitor?")
        self.runMPFMonitorCheckBox.setToolTip("Check to run monitor when opening MPF")
        self.runModeOption.currentIndexChanged.connect(self._updateRunOptions)

        # The following lets the godot project be opened in the editor rather than run
        self.openGodotEditorCheckBox = QCheckBox("Open in Godot editor")
        self.openGodotEditorCheckBox.setToolTip("Opens the GMC project in the Godot editor instead of running it")

        # The following sets up the list of the project's saved run profiles
        self.runProfileOption = QComboBox()
        self.runProfileOption.setMinimumWidth(180)
        self.runProfileOption.currentIndexChanged.connect(self._updateButtons)

        # The following lets the chosen run profile be run when mpf-manager starts
        self.runAtStartupCheckBox = QCheckBox("Run at startup")
        self.runAtStartupCheckBox.setToolTip("Run this profile automatically when MPF-Manager starts")
        self.runAtStartupCheckBox.toggled.connect(self._setRunAtStartup)

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

    # The following returns the open project, while it is still in the list of projects
    def selectedProject(self) -> Project | None:
        if self.currentProject is None:
            return None
        return self.storedData.getProjectbyPath(self.currentProject.projectPath)

    # The following outputs the chosen run profile
    def selectedRunProfile(self) -> RunProfile | None:
        return self.storedData.getRunProfileByName(self.runProfileOption.currentData())

    # The following opens a project, or closes the one open when given none.  The Show Manager follows it to the
    # project's machine, asking first if it has changes that are not saved
    def openProject(self, project: Project | None) -> bool:
        if project is not None and self.storedData.getProjectbyPath(project.projectPath) is None:
            return False
        if self.showViewerWindow is not None:
            machinePath = Path(project.projectPath) if project else None
            if machinePath != self.showViewerWindow.machinePath:
                if not self.showViewerWindow.confirmDiscardChanges():
                    return False
                self.showViewerWindow.setMachinePath(machinePath)
        self.currentProject = project
        self.refreshMainWindow()
        self._updateWindowTitle()
        self._updateRunOptions()
        if project is not None:
            self.outputLogger(f"Opened '{project.projectName}' at {project.projectPath}")
        return True

    def closeProject(self) -> None:
        self.openProject(None)

    # The following asks which project to open: one of the projects, a new one, or a machine folder.  It returns
    # whether one was opened
    def showProjectPicker(self) -> bool:
        picker = ProjectPickerDialog(
            self.storedData,
            createProject=self.createNewProject,
            addProject=self.addExistingProject,
            projectStatus=lambda project: projectStatus(project, self.runningProcesses),
            parentWidget=self,
        )
        if not picker.exec() or picker.chosenProject is None:
            self.refreshMainWindow()
            return False
        return self.openProject(picker.chosenProject)

    # The following starts MPF-Manager: it runs the startup run profile if there is one, and otherwise asks which
    # project to open
    def startUp(self) -> None:
        settings = self.storedData.settings
        if settings.runProfileAtStartup and self.storedData.startupProfile() is not None:
            self.runStartupProfile()
            return
        self.showProjectPicker()

    # The following shows the environments, to make, change or remove them
    def showEnvironments(self) -> None:
        self.environmentsDialog.show()
        self.environmentsDialog.raise_()
        self.environmentsDialog.activateWindow()

    # The following pairs the open project with the environment chosen in the ribbon
    def _environmentChosen(self) -> None:
        project = self.selectedProject()
        if project is None or self.environmentOption.signalsBlocked():
            return
        environmentName = self.environmentOption.currentData()
        if environmentName != project.virtualEnvironment:
            self._setProjectEnvironment(project.projectPath, environmentName)
            self._updateRunOptions()
            self._updateOverview()

    # The following refreshes the main Window
    def refreshMainWindow(self) -> None:

        # The following updates the virtualEnvironmentTable
        selectedVENV = self.selectedEnvironment()
        self.venvAvailableTable.setRowCount(0)
        for environment in self.storedData.environmentList:
            row = self.venvAvailableTable.rowCount()
            self.venvAvailableTable.insertRow(row)
            self.venvAvailableTable.setItem(row, 0, _item(environment.venvName, environment.venvName))
            if environment.editableMPFRef:
                mpfVersionItem = _item(f"{environment.installedMPFVersion}  (editable, {environment.editableMPFRef})")
                mpfVersionItem.setToolTip(
                    f"Tracks {environment.editableMPFRef} from GitHub, source at {environment.editableMPFPath}"
                )
            elif environment.isEditable:
                mpfVersionItem = _item(f"{environment.installedMPFVersion}  (editable)")
                mpfVersionItem.setToolTip(f"Installed in editable mode from {environment.editableMPFPath}")
            else:
                mpfVersionItem = _item(environment.installedMPFVersion)
            self.venvAvailableTable.setItem(row, 1, mpfVersionItem)
            self.venvAvailableTable.setItem(row, 2, _item(environment.installedPython))
            self.venvAvailableTable.setItem(row, 3, _item(", ".join(environment.additionalPackages)))
            self.venvAvailableTable.setItem(row, 4, _item("OK" if environment.exists else "Missing"))
            self.venvAvailableTable.setItem(row, 5, _item(environment.pathToVENV))
            if selectedVENV and environment.venvName == selectedVENV.venvName:
                self.venvAvailableTable.selectRow(row)

        # A project taken off the list is no longer open
        if self.currentProject is not None and self.selectedProject() is None:
            self.currentProject = None
            self._updateWindowTitle()

        # The following lists the environments the project can run in
        project = self.selectedProject()
        self.environmentOption.blockSignals(True)
        self.environmentOption.clear()
        pairing = environmentPairing(self.storedData, project.virtualEnvironment if project else None)
        for index in range(pairing.count()):
            self.environmentOption.addItem(pairing.itemText(index), pairing.itemData(index))
        self.environmentOption.setCurrentIndex(pairing.currentIndex())
        pairing.deleteLater()
        self.environmentOption.blockSignals(False)

        # The following lists the project's run profiles, keeping the chosen profile chosen
        chosenProfileName = self.runProfileOption.currentData()
        self.runProfileOption.blockSignals(True)
        self.runProfileOption.clear()
        for profile in self.storedData.runProfileList:
            if project is not None and profile.projectPath == project.projectPath:
                self.runProfileOption.addItem(self._runProfileLabel(profile), profile.profileName)
        self.runProfileOption.setCurrentIndex(max(self.runProfileOption.findData(chosenProfileName), 0))
        self.runProfileOption.blockSignals(False)
        self._updateOverview()
        self._updateButtons()

    # The following shows the open project's details, or asks for a project to be opened
    def _updateOverview(self) -> None:
        project = self.selectedProject()
        self.projectHeading.setVisible(project is not None)
        self.projectDetails.setVisible(project is not None)
        self.noProjectPrompt.setVisible(project is None)
        if project is None:
            return
        self.projectHeading.setText(project.projectName)
        environment = self.storedData.getVENVbyName(project.virtualEnvironment)
        if environment is not None:
            environmentText = (
                f"{environment.venvName}  (MPF {environment.installedMPFVersion}, Python {environment.installedPython})"
            )
        else:
            environmentText = "None. Choose one on the Project tab of the ribbon"
        configVersion = mpfProjects.checkConfigVersion(Path(project.projectPath))
        values = {
            "path": project.projectPath,
            "environment": environmentText,
            "config": f"v{configVersion}" if configVersion else "—",
            "gmc": project.gmcFolderPath or str(mpfProjects.findGodotProject(Path(project.projectPath)) or "None"),
            "status": projectStatus(project, self.runningProcesses),
        }
        for field, value in values.items():
            self.overviewLabels[field].setText(value)
        # The status is a badge: green when the project is ready or running, amber when something is wrong
        status = values["status"]
        statusLabel = self.overviewLabels["status"]
        statusLabel.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        setStatusBadge(statusLabel, "ok" if status == "OK" or status.startswith("Running") else "warn")

    # The following describes a run profile for the run profile list
    def _runProfileLabel(self, profile: RunProfile) -> str:
        modeLabel = next(
            (label for label, mode in mpfProjects.RUN_MODES.items() if mode == profile.runMode), profile.runMode
        )
        startupText = (
            "  [startup]"
            if self.storedData.settings.runProfileAtStartup
            and self.storedData.settings.startupRunProfile == profile.profileName
            else ""
        )
        return f"{profile.profileName}  ({modeLabel}){startupText}"

    # The Following updates the button States
    def _updateButtons(self) -> None:
        idle = not self.commandQueue.isBusy
        environment = self.selectedEnvironment()
        self.newVENVAction.setEnabled(idle)
        for b in (self.changeVENVAction, self.verifyVENVAction, self.deleteVENVAction):
            b.setEnabled(idle and environment is not None and environment.exists)
        self.deleteVENVAction.setEnabled(idle and environment is not None)
        self.openVENVAction.setEnabled(environment is not None and environment.exists)
        self.openSourceAction.setEnabled(environment is not None and environment.isEditable)

        project = self.selectedProject()
        running = project is not None and project.projectPath in self.runningProcesses
        self.closeProjectAction.setEnabled(project is not None)
        self.openProjectFolderAction.setEnabled(project is not None)
        self.viewShowsAction.setEnabled(project is not None)
        self.environmentOption.setEnabled(project is not None)
        self.runMPFAction.setEnabled(project is not None and not running)
        self.stopMPFAction.setEnabled(running)
        projectEnvironment = self.storedData.getVENVbyName(project.virtualEnvironment) if project else None
        self.createGMCAction.setEnabled(idle and mpfProjects.isGMCEligible(projectEnvironment))

        # The following updates the run profile controls for the chosen profile
        runProfile = self.selectedRunProfile()
        profileRunning = runProfile is not None and runProfile.projectPath in self.runningProcesses
        self.runProfileAction.setEnabled(runProfile is not None and not profileRunning)
        self.loadRunProfileAction.setEnabled(runProfile is not None)
        self.deleteRunProfileAction.setEnabled(runProfile is not None)
        self.saveRunProfileAction.setEnabled(project is not None)
        self.runAtStartupCheckBox.setEnabled(runProfile is not None)
        self.runAtStartupCheckBox.blockSignals(True)
        self.runAtStartupCheckBox.setChecked(runProfile is not None and self.storedData.startupProfile() is runProfile)
        self.runAtStartupCheckBox.blockSignals(False)

    # The following sets the project environment
    def _setProjectEnvironment(self, path: str, env_name: str | None) -> None:
        self.storedData.setProjectVENV(path, env_name)

        # The following keeps the GMC project's gmc.cfg pointed at the newly chosen environment's mpf
        project = self.storedData.getProjectbyPath(path)
        gmcFolder = (project.gmcFolderPath or mpfProjects.findGodotProject(Path(path))) if project else None
        if gmcFolder:
            environment = self.storedData.getVENVbyName(env_name)
            try:
                gmcManager.updateGMCExecutable(Path(gmcFolder), environment.executable("mpf") if environment else None)
            except OSError as exc:
                self.outputLogger(f"Could not update gmc.cfg: {exc}")
        self._updateButtons()

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
            self._rememberVENVFolder(dialog.venvParentFolderPath())
            self._applyDialogPlan(dialog, create=True)

    # The following defaults the next new environment to the folder chosen this time
    def _rememberVENVFolder(self, folderPath: Path) -> None:
        folder = str(folderPath)
        if folder != self.storedData.settings.venvDirectory:
            self.storedData.settings.venvDirectory = folder
            self.storedData.saveConfiguration()

    # The following changes the MPF related to a selected VENV
    def changeVENVmpf(self) -> None:
        environment = self.selectedEnvironment()
        if not environment:
            return
        dialog = VENVManagementDialog(self.storedData, self, environment)
        if dialog.exec():
            self._applyDialogPlan(dialog, create=False)

    # The following builds the plan from an accepted dialog, reporting problems such as git being missing
    def _applyDialogPlan(self, dialog: VENVManagementDialog, create: bool) -> None:
        try:
            plannedVENV = dialog.plan()
        except OSError as planException:
            self._error(str(planException))
            return
        self._applyPlan(plannedVENV, create)

    # The following attempts to create a venv based on the plan via a dialog
    # When it is done, onDone is told whether it worked, e.g. so a new project can be paired with its environment
    def _applyPlan(
        self, plannedVENV: venvDialogData, create: bool, onDone: Callable[[bool], None] | None = None
    ) -> None:
        try:
            # A github source is cloned (or updated) first, so a failed clone leaves no half made environment
            commandList = list(plannedVENV.sourceCommands)
            if create:
                commandList.append(uvCMDs.setupVENV(plannedVENV.venvPath, plannedVENV.pythonVersion))
            if plannedVENV.packagesToRemove:
                commandList.append(uvCMDs.uninstallVENVPackages(plannedVENV.venvPath, plannedVENV.packagesToRemove))
            commandList.append(
                uvCMDs.installVENVPackages(
                    plannedVENV.venvPath,
                    plannedVENV.mpfVersionRequirements,
                    [plannedVENV.editableMPFPath] if plannedVENV.editableMPFPath else None,
                )
            )
        except uvCMDs.UvNotFoundError as exc:
            self._error(str(exc))
            if onDone is not None:
                onDone(False)
            return

        editablePath = str(plannedVENV.editableMPFPath or "")

        # Function to be called when virtual environment creation is attempted
        def done(ok: bool) -> None:
            applied(ok)
            if onDone is not None:
                onDone(ok)

        def applied(ok: bool) -> None:
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
                        editablePath,
                        plannedVENV.editableMPFRef,
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
                environment.editableMPFPath = editablePath
                environment.editableMPFRef = plannedVENV.editableMPFRef
                self.storedData.saveConfiguration()
            sourceText = f" (editable from {editablePath})" if editablePath else ""
            if plannedVENV.editableMPFRef:
                sourceText = f" (editable, {plannedVENV.editableMPFRef} from GitHub at {editablePath})"
            self.outputLogger(f"Environment '{plannedVENV.venvName}' now has MPF {plannedVENV.mpfVersion}{sourceText}.")
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

            # An editable install's version comes from its source folder, which may have changed since installing
            if environment.isEditable:
                try:
                    localSource = sourceManager.readLocalMPFSource(Path(environment.editableMPFPath))
                except (OSError, ValueError) as sourceException:
                    self.outputLogger(f"Could not read the MPF source folder: {sourceException}")
                else:
                    version = localSource.mpfVersion
                    if not compatibilityManager.pythonSetCheck(
                        localSource.requiredPythonVersion, environment.installedPython
                    ):
                        self.outputLogger(
                            f"Warning: the MPF source now needs Python {localSource.requiredPythonVersion}, "
                            f"'{environment.venvName}' has Python {environment.installedPython}."
                        )
                    self.outputLogger(
                        "Code changes in the source folder are picked up automatically; if its dependencies "
                        "changed, re-apply it with 'Change MPF version…'."
                    )
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
        if environmentToDelete.isEditable:
            warningText += f"\n\nThe MPF source folder will be kept:\n{environmentToDelete.editableMPFPath}"
        if QMessageBox.question(self, "Delete environment", warningText) != QMessageBox.StandardButton.Yes:
            return
        if environmentToDelete.exists:
            # Only remove folders that really are virtual environments.
            shutil.rmtree(environmentToDelete.venvPath, ignore_errors=True)
        self.storedData.removeVENV(environmentToDelete.venvName)
        self.outputLogger(f"Deleted environment '{environmentToDelete.venvName}'.")
        self.refreshMainWindow()

    # project ui actions

    # The following Function creates a new project, returning it, or None if it was not made
    def createNewProject(self) -> Project | None:
        newProjectDialog = mpfProjectCreationDialog(self.storedData, self)
        if not newProjectDialog.exec():
            return None
        newProjectPath = newProjectDialog.projectPath()
        projectName = newProjectDialog.projectName.text().strip()
        newEnvironment = newProjectDialog.pendingEnvironment()
        try:
            mpfProjects.createNewMPFProject(newProjectPath, projectName)
            # A new environment is paired with the project once it has been made
            self.storedData.addProject(
                Project(
                    projectName,
                    str(newProjectPath),
                    None if newEnvironment else newProjectDialog.environmentPair.currentData(),
                )
            )
        except (OSError, ValueError) as exc:
            self._error(str(exc))
            return None
        self.outputLogger(f"Created MPF project at {newProjectPath}")
        self.refreshMainWindow()
        createGMC = newProjectDialog.createGMCCheckBox.isChecked()
        newProject = self.storedData.getProjectbyPath(str(newProjectPath))
        if newEnvironment is None:
            if createGMC and newProject is not None:
                self.createGMCProject(newProject)
            return newProject

        # The following makes the new environment, then pairs the project with it and makes its GMC project
        def environmentMade(ok: bool) -> None:
            if not ok:
                self.outputLogger(
                    f"'{projectName}' was created without an environment. Choose one on the Project tab of the "
                    "ribbon once one is set up."
                )
                return
            self._setProjectEnvironment(str(newProjectPath), newEnvironment.venvName)
            self.outputLogger(f"'{projectName}' now uses the environment '{newEnvironment.venvName}'.")
            self.refreshMainWindow()
            if createGMC and (newProject := self.storedData.getProjectbyPath(str(newProjectPath))):
                self.createGMCProject(newProject)

        if newProjectDialog.newEnvironmentFolder is not None:
            self._rememberVENVFolder(newProjectDialog.newEnvironmentFolder)
        self.outputLogger(f"Setting up the environment '{newEnvironment.venvName}' for '{projectName}'…")
        self._applyPlan(newEnvironment, create=True, onDone=environmentMade)
        return newProject

    # The following generates a GMC godot project for a project (the selected one by default)
    def createGMCProject(self, project: Project | None = None) -> None:
        project = project or self.selectedProject()
        environment = self.storedData.getVENVbyName(project.virtualEnvironment) if project else None
        if not project or not environment:
            return
        if not mpfProjects.isGMCEligible(environment):
            self._error(
                f"GMC requires MPF 0.80 or newer, '{environment.venvName}' has MPF {environment.installedMPFVersion}."
            )
            return
        if existingGodotProject := mpfProjects.findGodotProject(Path(project.projectPath)):
            self._error(f"This machine folder already has a Godot project at {existingGodotProject}.")
            return

        # The following shows the dialog once MPF has said which GMC version it wants
        def versionKnown(suggestedVersion: str | None) -> None:
            dialog = GMCProjectDialog(project, suggestedVersion, self)
            if not dialog.exec():
                return
            gmcVersion: str | None = dialog.gmcVersion.currentData()
            if not gmcVersion:
                return
            gmcPath = dialog.gmcProjectPath()
            runImport = dialog.runImportCheckBox.isChecked()
            godotExecutable = self.storedData.settings.godotExecutablePath
            cachePath = self.storedData.gmcCachePath
            self.outputLogger(f"Fetching mpf-gmc {gmcVersion}…")

            # The following downloads the addon and writes the project off of the GUI thread
            def build() -> tuple[Path, Version | None]:
                addonSource = gmcManager.fetchGMCAddon(gmcVersion, cachePath)
                detectedGodot = (
                    gmcManager.godotVersion(godotExecutable)
                    if mpfProjects.checkGodotExecutable(godotExecutable)
                    else None
                )
                godotFeature = (
                    f"{detectedGodot.major}.{detectedGodot.minor}"
                    if detectedGodot
                    else gmcManager.GODOT_DEFAULT_FEATURE
                )
                gmcManager.createGMCProject(
                    gmcPath, project.projectName, addonSource, godotFeature, environment.executable("mpf")
                )
                return gmcPath, detectedGodot

            # The following records the new GMC project and optionally imports it with godot
            def built(result: tuple[Path, Version | None]) -> None:
                createdPath, detectedGodot = result
                self.storedData.setProjectGMCPath(project.projectPath, str(createdPath))
                self.outputLogger(f"Created GMC {gmcVersion} project at {createdPath}")
                self.refreshMainWindow()
                if not runImport:
                    return
                if detectedGodot is None or detectedGodot < gmcManager.GODOT_IMPORT_MIN_VERSION:
                    self.outputLogger(
                        "Skipped the asset import: set Godot 4.3 or newer in File → Settings, "
                        "or open the project once in the Godot editor."
                    )
                elif self.commandQueue.isBusy:
                    self.outputLogger("Skipped the asset import because another operation is running.")
                else:
                    self.commandQueue.run([gmcManager.importGMCProject(godotExecutable, createdPath)])

            runInThread(build, built, lambda message: self._error(f"Could not create the GMC project: {message}"))

        self.outputLogger(f"Checking which GMC version '{environment.venvName}' needs…")
        runInThread(
            lambda: gmcManager.requiredGMCVersion(environment), versionKnown, lambda _message: versionKnown(None)
        )

    # The following is used to create an existing MPF machine by directory
    # It returns the project, which is the one already listed for a folder that is listed
    def addExistingProject(self) -> Project | None:
        existingMachineFolder = QFileDialog.getExistingDirectory(
            self, "Where is your existing MPF Machine Folder", self.storedData.settings.projectDirectory
        )
        if not existingMachineFolder:
            return None

        # The following checks to see if a project already exists there, and if not offers to create one.
        pathToCheck = Path(existingMachineFolder)
        if listedProject := self.storedData.getProjectbyPath(str(pathToCheck)):
            return listedProject
        if not mpfProjects.checkMPFProjectAtPath(pathToCheck):
            responseDialogForMissingProject = QMessageBox.question(
                self,
                "Add project",
                f"'{pathToCheck}' has no config/config.yaml, so it does not look like an MPF project. Add it anyway?",
            )
            if responseDialogForMissingProject != QMessageBox.StandardButton.Yes:
                return None
        try:
            self.storedData.addProject(Project(pathToCheck.name, str(pathToCheck)))
        except ValueError as exc:
            self._error(str(exc))
            return None
        self.refreshMainWindow()
        return self.storedData.getProjectbyPath(str(pathToCheck))

    # The following takes a project off the list of projects, the open one unless another is given, keeping its files
    def removeProject(self, project: Project | None = None) -> None:
        projectToRemove = project or self.selectedProject()
        if projectToRemove:
            self.storedData.removeProject(projectToRemove.projectPath)
            self.outputLogger(f"Removed '{projectToRemove.projectName}' from the list (files were not deleted).")
            self.refreshMainWindow()

    # The following collects the run options currently shown in the projects tab into a run profile
    def currentRunOptions(self, project: Project, profileName: str = "") -> RunProfile:
        return RunProfile(
            profileName=profileName,
            projectPath=project.projectPath,
            runMode=self.runModeOption.currentData(),
            hardwareArguments=list(self.hardwareOption.currentData()),
            noMediaController=self.runMediaControllerOption.isEnabled() and self.runMediaControllerOption.isChecked(),
            runMonitor=self.runMPFMonitorCheckBox.isEnabled() and self.runMPFMonitorCheckBox.isChecked(),
            openGodotEditor=self.openGodotEditorCheckBox.isEnabled() and self.openGodotEditorCheckBox.isChecked(),
            extraArguments=self.extraRunArguments.text(),
        )

    # The following is used to run the selected mpf project with the options shown in the projects tab
    def runMPFProject(self) -> None:
        projectToRun = self.selectedProject()
        if projectToRun:
            self._runProject(projectToRun, self.currentRunOptions(projectToRun))

    # The following runs a saved run profile
    def runRunProfile(self, profile: RunProfile | None) -> None:
        if profile is None:
            return
        projectToRun = self.storedData.getProjectbyPath(profile.projectPath)
        if projectToRun is None:
            self._error(f"The project for run profile '{profile.profileName}' is no longer in the project list.")
            return
        if projectToRun.projectPath in self.runningProcesses:
            self._error(f"'{projectToRun.projectName}' is already running.")
            return
        self.outputLogger(f"Running profile '{profile.profileName}'…")
        self._runProject(projectToRun, profile)

    # The following runs the run profile chosen to run at startup, if running one at startup is enabled
    def runStartupProfile(self) -> None:
        settings = self.storedData.settings
        if not settings.runProfileAtStartup:
            return
        profile = self.storedData.startupProfile()
        if profile is None:
            self.outputLogger(f"The startup run profile '{settings.startupRunProfile}' no longer exists.")
            return
        self._openProjectAt(profile.projectPath)
        self.runProfileOption.setCurrentIndex(max(self.runProfileOption.findData(profile.profileName), 0))
        self.runRunProfile(profile)

    # The following saves the selected project and the run options shown as a run profile
    def saveRunProfile(self) -> None:
        project = self.selectedProject()
        if project is None:
            return
        chosenProfile = self.selectedRunProfile()
        suggestedName = (
            chosenProfile.profileName
            if chosenProfile and chosenProfile.projectPath == project.projectPath
            else f"{project.projectName} - {self.runModeOption.currentText()}"
        )
        profileName, accepted = QInputDialog.getText(self, "Save run profile", "Profile name:", text=suggestedName)
        profileName = profileName.strip()
        if not accepted or not profileName:
            return
        if (
            self.storedData.getRunProfileByName(profileName)
            and QMessageBox.question(self, "Save run profile", f"Replace the run profile '{profileName}'?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        try:
            self.storedData.saveRunProfile(self.currentRunOptions(project, profileName))
        except ValueError as exc:
            self._error(str(exc))
            return
        self.outputLogger(f"Saved run profile '{profileName}'.")
        self.refreshMainWindow()
        self.runProfileOption.setCurrentIndex(self.runProfileOption.findData(profileName))

    # The following opens a project by its machine folder, unless it is the one open, returning whether it is open
    def _openProjectAt(self, projectPath: str) -> bool:
        project = self.storedData.getProjectbyPath(projectPath)
        if project is None:
            return False
        if (current := self.selectedProject()) is not None and current.projectPath == project.projectPath:
            return True
        return self.openProject(project)

    # The following opens a run profile's project and sets the run options to match the profile
    def loadRunProfile(self, profile: RunProfile | None) -> None:
        if profile is None:
            return
        if not self._openProjectAt(profile.projectPath):
            self._error(f"The project for run profile '{profile.profileName}' is no longer in the project list.")
            return
        modeIndex = self.runModeOption.findData(profile.runMode)
        if modeIndex >= 0:
            self.runModeOption.setCurrentIndex(modeIndex)
        for index in range(self.hardwareOption.count()):
            if self.hardwareOption.itemData(index) == profile.hardwareArguments:
                self.hardwareOption.setCurrentIndex(index)
        self.runMediaControllerOption.setChecked(profile.noMediaController)
        self.runMPFMonitorCheckBox.setChecked(profile.runMonitor)
        self.openGodotEditorCheckBox.setChecked(profile.openGodotEditor)
        self.extraRunArguments.setText(profile.extraArguments)
        self._updateRunOptions()

    # The following deletes the chosen run profile
    def deleteRunProfile(self) -> None:
        profile = self.selectedRunProfile()
        if profile is None:
            return
        if (
            QMessageBox.question(self, "Delete run profile", f"Delete the run profile '{profile.profileName}'?")
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.storedData.removeRunProfile(profile.profileName)
        self.outputLogger(f"Deleted run profile '{profile.profileName}'.")
        self.refreshMainWindow()

    # The following enables or disables running the chosen run profile at startup
    def _setRunAtStartup(self, enabled: bool) -> None:
        profile = self.selectedRunProfile()
        if profile is None:
            return
        if enabled:
            self.storedData.setStartupRunProfile(profile.profileName)
            self.outputLogger(f"'{profile.profileName}' will run when MPF-Manager starts.")
        elif self.storedData.startupProfile() is profile:
            self.storedData.setStartupRunProfile(None)
            self.outputLogger("No run profile will run when MPF-Manager starts.")
        self.refreshMainWindow()

    # The following runs a project using the given run options
    def _runProject(self, projectToRun: Project, runOptions: RunProfile) -> None:

        # The following catches situations where a project or environment are not
        # setup properly
        environment = self.storedData.getVENVbyName(projectToRun.virtualEnvironment)
        if not environment:
            self._error("Choose an environment for this project first.")
            return
        mpfRunMode = runOptions.runMode
        if mpfRunMode in ("both", "mc") and "mpf-mc" not in environment.additionalPackages:
            self._error(f"'{environment.venvName}' does not have mpf-mc installed.")
            return
        if mpfRunMode == "monitor" and "mpf-monitor" not in environment.additionalPackages:
            self._error(f"'{environment.venvName}' does not have mpf-monitor installed.")
            return
        if runOptions.runMonitor and "mpf-monitor" not in environment.additionalPackages:
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
            gmcCommand = mpfProjects.runGMC(godotExecutablePath, gmcFolderPath, runOptions.openGodotEditor)

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
            extraArguments = shlex.split(runOptions.extraArguments)
        except ValueError as argumentException:
            self._error(f"Invalid extra arguments: {argumentException}")
            return

        if mpfRunMode == "game" and runOptions.noMediaController:
            extraArguments.insert(0, "-b")

            # The following sets up the commands for the game and, if requested, the monitor
        runCommands = mpfProjects.runMPFWithMonitor(
            environment,
            mpfRunMode,
            runOptions.hardwareArguments,
            extraArguments,
            runOptions.runMonitor,
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
        settingsDialog = SettingsDialog(self.storedData.settings, self, self.storedData.runProfileList)
        if settingsDialog.exec():
            previousTheme = themeName(self.storedData.settings.theme)
            settingsDialog.applySettings(self.storedData.settings)
            self.storedData.saveConfiguration()
            self.refreshMainWindow()
            if themeName(self.storedData.settings.theme) != previousTheme:
                self.applyTheme(self.storedData.settings.theme)

    # The following changes how MPF-Manager looks.  Icons drawn in the theme's colors are drawn again when it is next
    # opened, so it says so
    def applyTheme(self, name: str) -> None:
        app = QApplication.instance()
        if isinstance(app, QApplication):
            chosen = applyTheme(app, name)
            self.outputLogger(
                f"Now using the {THEME_LABELS[chosen]} theme. Some icons change once MPF-Manager is opened again."
            )

    # The following switches to the Show Manager, showing the open project's shows.  Its page is made the first time
    # it is shown, and keeps its shows and changes while the Project Manager is shown
    def openShowViewer(self) -> None:
        selectedProject = self.selectedProject()
        machinePath = Path(selectedProject.projectPath) if selectedProject else None
        if self.showViewerWindow is None:
            self.showViewerWindow = ShowViewerWindow(machinePath, embedded=True)
            self.showViewerWindow.projectManagerRequested.connect(self.showProjectManager)
            self.showViewerWindow.windowTitleChanged.connect(self._updateWindowTitle)
            self.pages.addWidget(self.showViewerWindow)
            width, height = SHOW_MANAGER_SIZE
            self.resize(max(self.width(), width), max(self.height(), height))
        elif machinePath is not None and machinePath != self.showViewerWindow.machinePath:
            self.showViewerWindow.setMachinePath(machinePath)
        self.pages.setCurrentWidget(self.showViewerWindow)
        self.managerTabs.setCurrentIndex(SHOW_MANAGER_TAB)
        self._setPageMenus(self.showViewerWindow.pageMenus)
        self._updateWindowTitle()
        self.show()
        self.raise_()
        self.activateWindow()

    # The following switches to the Project Manager.  Leaving the Show Manager pauses its playback and keeps its changes
    def showProjectManager(self) -> None:
        self.pages.setCurrentWidget(self.projectManagerPage)
        self.managerTabs.setCurrentIndex(PROJECT_MANAGER_TAB)
        self._setPageMenus(self.projectManagerMenus)
        self._updateWindowTitle()
        self.show()
        self.raise_()
        self.activateWindow()

    # The following titles the window after the manager shown, e.g. the machine whose shows are shown
    def _updateWindowTitle(self) -> None:
        viewer = self.showViewerWindow
        isShowManager = viewer is not None and self.pages.currentWidget() is viewer
        if viewer is not None and isShowManager:
            self.setWindowTitle(viewer.windowTitle())
            return
        project = self.selectedProject()
        self.setWindowTitle(f"{WINDOW_TITLE} — {project.projectName}" if project else WINDOW_TITLE)

    # The following is used to close the application
    def closeEvent(self, closeEvent) -> None:  # noqa: N802 - Qt override

        # The following checks that changes to shows not saved in the show viewer can be lost
        if self.showViewerWindow is not None and not self.showViewerWindow.confirmDiscardChanges():
            closeEvent.ignore()
            return

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
