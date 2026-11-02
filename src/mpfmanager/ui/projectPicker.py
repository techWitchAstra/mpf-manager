"""Project picker: the dialog that asks which MPF project to open"""

#   projectPicker - Responsible for the dialog shown when MPF-Manager opens,
#       and from File > Open project, listing the projects to choose one of,
#       or to make a new project or open an existing machine folder
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mpfmanager.core.storageManager import Project, StorageProcessor

NO_PROJECTS_TEXT = "No projects yet. Create a new one, or open an existing machine folder."
PROJECT_COLUMNS = ["Project", "Environment", "Status", "Machine folder"]


# The following dialog lists the projects to open one of.  A new project, or a machine folder opened, is made by the
# window, and opened straight away.  Projects can be taken off the list, keeping their files
class ProjectPickerDialog(QDialog):
    def __init__(
        self,
        store: StorageProcessor,
        createProject: Callable[[], Project | None],
        addProject: Callable[[], Project | None],
        projectStatus: Callable[[Project], str],
        parentWidget: QWidget | None = None,
    ):
        super().__init__(parentWidget)
        self.store = store
        self.createProject = createProject
        self.addProject = addProject
        self.projectStatus = projectStatus
        self.chosenProject: Project | None = None
        self.setWindowTitle("Open MPF project")
        self.setMinimumSize(720, 360)

        heading = QLabel("Choose a project to open")
        heading.setObjectName("sectionHeading")
        headingFont = heading.font()
        headingFont.setPointSizeF(headingFont.pointSizeF() * 1.3)
        headingFont.setBold(True)
        heading.setFont(headingFont)

        self.projectTable = QTableWidget(0, len(PROJECT_COLUMNS))
        self.projectTable.setHorizontalHeaderLabels(PROJECT_COLUMNS)
        self.projectTable.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.projectTable.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.projectTable.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.projectTable.verticalHeader().setVisible(False)
        self.projectTable.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.projectTable.horizontalHeader().setStretchLastSection(True)
        self.projectTable.itemSelectionChanged.connect(self._updateButtons)
        self.projectTable.cellDoubleClicked.connect(lambda _row, _column: self.openChosen())
        self.emptyLabel = QLabel(NO_PROJECTS_TEXT)
        self.emptyLabel.setWordWrap(True)

        self.newButton = QPushButton("New project…")
        self.newButton.setToolTip("Create a new MPF project, and an environment for it if wanted")
        self.newButton.clicked.connect(lambda: self._choose(self.createProject()))
        self.openFolderButton = QPushButton("Open folder…")
        self.openFolderButton.setToolTip("Open an existing MPF machine folder, adding it to the list")
        self.openFolderButton.clicked.connect(lambda: self._choose(self.addProject()))
        self.removeButton = QPushButton("Remove from list")
        self.removeButton.setToolTip("Take the project off the list. Its files are kept")
        self.removeButton.clicked.connect(self.removeChosen)
        projectButtons = QHBoxLayout()
        for button in (self.newButton, self.openFolderButton):
            projectButtons.addWidget(button)
        projectButtons.addStretch()
        projectButtons.addWidget(self.removeButton)

        self.dialogButtons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.openButton = self.dialogButtons.addButton("Open", QDialogButtonBox.ButtonRole.AcceptRole)
        self.openButton.setDefault(True)
        self.openButton.setObjectName("primary")
        self.dialogButtons.accepted.connect(self.openChosen)
        self.dialogButtons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(heading)
        layout.addWidget(self.projectTable, 1)
        layout.addWidget(self.emptyLabel)
        layout.addLayout(projectButtons)
        layout.addWidget(self.dialogButtons)
        self.refresh()

    # The following lists the projects, choosing the first
    def refresh(self) -> None:
        self.projectTable.setRowCount(0)
        for project in self.store.projectList:
            row = self.projectTable.rowCount()
            self.projectTable.insertRow(row)
            nameItem = QTableWidgetItem(project.projectName)
            nameItem.setData(Qt.ItemDataRole.UserRole, project.projectPath)
            self.projectTable.setItem(row, 0, nameItem)
            self.projectTable.setItem(row, 1, QTableWidgetItem(project.virtualEnvironment or "(none)"))
            self.projectTable.setItem(row, 2, QTableWidgetItem(self.projectStatus(project)))
            self.projectTable.setItem(row, 3, QTableWidgetItem(project.projectPath))
        if self.projectTable.rowCount():
            self.projectTable.selectRow(0)
        self.emptyLabel.setVisible(not self.store.projectList)
        self.projectTable.setVisible(bool(self.store.projectList))
        self._updateButtons()

    # The following returns the project chosen in the list
    def selectedProject(self) -> Project | None:
        row = self.projectTable.currentRow()
        nameItem = self.projectTable.item(row, 0) if row >= 0 and self.projectTable.selectedItems() else None
        return self.store.getProjectbyPath(nameItem.data(Qt.ItemDataRole.UserRole)) if nameItem else None

    def _updateButtons(self) -> None:
        project = self.selectedProject()
        self.openButton.setEnabled(project is not None)
        isRunning = project is not None and self.projectStatus(project).startswith("Running")
        self.removeButton.setEnabled(project is not None and not isRunning)

    # The following opens the project chosen in the list
    def openChosen(self) -> None:
        self._choose(self.selectedProject())

    def _choose(self, project: Project | None) -> None:
        if project is None:
            self.refresh()
            return
        self.chosenProject = project
        self.accept()

    # The following takes the chosen project off the list, once it is agreed to, keeping its files
    def removeChosen(self) -> bool:
        project = self.selectedProject()
        if project is None:
            return False
        answer = QMessageBox.question(
            self,
            "Remove from list",
            f"Take '{project.projectName}' off the list? Its files at {project.projectPath} are kept.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        self.store.removeProject(project.projectPath)
        self.refresh()
        return True
