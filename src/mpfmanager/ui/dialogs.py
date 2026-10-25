"""mpf-Manager QT Dialog functions and configuration"""

#   dialogs - Responsible for containing functions and data classes for dialogs
# 
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human by a human at all stages

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# The following imports the UI related elements as needed for the dialogs
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# The following imnports the needed mpf-manager related functions and classes
from mpfmanager.core import compatibilityManager
from mpfmanager.core import uvManager as uvCMDs
from mpfmanager.core.storageManager import VirtualEnvironment, Settings, StorageProcessor
from mpfmanager.ui.uiWorkers import runInThread

# The following delcares packages to be installed
PACKAGES = ["mpf", *compatibilityManager.MPF_ADD_ONS]

# The following creates a data class to store information for dialogs related to virtualEnvironments
@dataclass
class venvDialogData:
    """dataObject for storage of virtualEnvironment for use in dialogs related to virtualEnvironments"""

    venvName: str
    venvPath: Path
    pythonVersion: str
    mpfVersion: str
    mpfVersionRequirements: list[str]
    companionPackages: list[str]
    packagesToRemove: list[str]

# The following creates a browse button and selection widget
def _browseWidget(editWidget: QLineEdit, parentWidget: QWidget, widgetTitle: str) -> QWidget:
    browseWidget = QWidget()
    browseWidgetLayout = QHBoxLayout(browseWidget)
    browseWidgetLayout.setContentsMargins(0, 0, 0, 0)
    browseWidgetLayout.addWidget(editWidget)
    browseButton = QPushButton("Browse…")
    browseButton.clicked.connect(
        lambda: (d := QFileDialog.getExistingDirectory(parentWidget, widgetTitle, editWidget.text())) and editWidget.setText(d)
    )
    browseWidgetLayout.addWidget(browseButton)
    return browseWidget

# The following sets up the 
class VENVManagementDialog(QDialog):
    """Dialog for creating or editing the mpf version of a virtual environment"""

    # The following initializes the dialog
    def __init__(self, storageObject: StorageProcessor, parentWidget: QWidget | None = None, venvObject: VirtualEnvironment | None = None):

        # Override of parent init
        super().__init__(parentWidget)
        self.storageObject = storageObject
        self.venvObject = venvObject
        self.availableReleases: dict[str, list[compatibilityManager.PyPIRelease]] = {}
        self.installedVENVPackages: set[str] = set()
        self._nameWasEdited = False

        # The following sets up the window for the widget
        self.setWindowTitle("Change MPF version" if venvObject else "New MPF environment")
        self.setMinimumWidth(520)

        # The following sets up an edit line for name
        self.venvDialogName = QLineEdit(venvObject.venvName if venvObject else "")
        self.venvDialogName.setEnabled(venvObject is None)
        self.venvDialogName.textEdited.connect(lambda: setattr(self, "_nameWasEdited", True))
        self.venvDialogName.textChanged.connect(self._updateVENVLocation)

        # The following sets up a mpf combination box
        self.dialogMPFVersion = QComboBox()
        self.dialogMPFVersion.currentIndexChanged.connect(self._mpfVersionWasChanged)

        # The following creates a checkbox for if pre-releases should be included
        self.preReleaseCheckbox = QCheckBox("Include pre-release mpf builds (dev builds)")
        self.preReleaseCheckbox.setChecked(storageObject.settings.includePreReleases)
        self.preReleaseCheckbox.toggled.connect(self._populateMPFVersions)

        # The following creates a box to select a python version
        self.pythonVersionDialog = QComboBox()
        self.pythonVersionDialog.setEnabled(venvObject is None)
        self.pythonVersionDialog.currentIndexChanged.connect(self._suggestVENVName)

        # the following creates a group of checkboxes for the mpf add-ons
        self.mpfAddOnDialogs: dict[str, QCheckBox] = {}

        # The following creates a box to edit the virtual environment directory
        self.venvParentLocation = QLineEdit(storageObject.settings.venvDirectory)
        self.venvParentLocation.textChanged.connect(self._updateVENVLocation)

        # The following displays the resolved path for the Virtual Environment
        self.resolvedVENVLocation = QLabel()
        self.resolvedVENVLocation.setWordWrap(True)

        # The following creates a lable to put status of operations
        self.operationStatus = QLabel("Loading MPF releases from PyPI…")
        self.operationStatus.setWordWrap(True)

        # The following creates a dialog form to submit as part of dialog box
        dialogForm = QFormLayout()
        dialogForm.addRow("Name:", self.venvDialogName)
        dialogForm.addRow("MPF version:", self.dialogMPFVersion)
        dialogForm.addRow("", self.preReleaseCheckbox)

        # The following adds a checkbox for each add-on that can be installed with MPF
        for index, (optionalPackage, packageDescription) in enumerate(compatibilityManager.MPF_ADD_ONS.items()):
            currentCheckBox = QCheckBox(f"{optionalPackage} – {packageDescription}")
            currentCheckBox.setChecked(venvObject is not None and optionalPackage in venvObject.additionalPackages)
            currentCheckBox.toggled.connect(self._updatePythonModules)
            self.mpfAddOnDialogs[optionalPackage] = currentCheckBox
            dialogForm.addRow("" if index else "Also install:", currentCheckBox)

        # The following creates a dialog for python version
        dialogForm.addRow("Python:", self.pythonVersionDialog)

        # The following creates a dialog for where to store the virtual environment, that does not display when 
        # editting the mpf add-ons for a virtual environment
        self.parentFolderDialog = _browseWidget(self.venvParentLocation, self, "Choose where to create the environment")
        dialogForm.addRow("Create in:", self.parentFolderDialog)
        dialogForm.setRowVisible(self.parentFolderDialog, venvObject is None)

        # The following label displays the location of the virtual environment
        dialogForm.addRow("Location:", self.resolvedVENVLocation)

        # The following adds a pair of buttons to resolve the dialog box
        self.dialogButtons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.dialogButtons.accepted.connect(self.accept)
        self.dialogButtons.rejected.connect(self.reject)
        self.dialogButtons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)

        # The following lays out all the elements of the dialog box
        dialogWidgetLayout = QVBoxLayout(self)
        dialogWidgetLayout.addLayout(dialogForm)
        dialogWidgetLayout.addWidget(self.operationStatus)
        dialogWidgetLayout.addWidget(self.dialogButtons)


        self._updateVENVLocation()
        runInThread(self._loadVENV, self._venvLoaded, self._venvLoadFailed)

    # The following is responsible for loading a virtual environment
    @staticmethod
    def _loadVENV() -> tuple[dict[str, list[compatibilityManager.PyPIRelease]], set[str]]:

        # The following retrieves the releases for a given package
        packageReleases = {package: compatibilityManager.pypiReleaseRetriever(package) for package in PACKAGES}
        
        try:
            installedPythonVersions = uvCMDs.listPythonVersions()
        except Exception:
            installedPythonVersions = set()
        return packageReleases, installedPythonVersions

    # The following is called when a virtualEnvironment is succesfully loaded
    def _venvLoaded(self, loadResult: tuple[dict[str, list[compatibilityManager.PyPIRelease]], set[str]]) -> None:
        self.availableReleases, self.installedVENVPackages = loadResult
        self.operationStatus.setText("")
        self._populateMPFVersions()

    # The following is called upon a failed virtual environment packages load
    def _venvLoadFailed(self, errorMessage: str) -> None:
        self.operationStatus.setText(f"Could not load releases from PyPI: {errorMessage}")

    # Updaters

    # The following function is called to force the MPF versions to re-populate depending
    # on pre-release status updates, and venv updates
    def _populateMPFVersions(self) -> None:
        compatibleReleases = compatibilityManager.filterPyPIReleases(self.availableReleases.get("mpf", []), self.preReleaseCheckbox.isChecked())
        if self.venvObject:
            compatibleReleases = [release for release in compatibleReleases if compatibilityManager.pythonSetCheck(release.requiredPythonVersion, self.venvObject.installedPython)]
        current = self.dialogMPFVersion.currentData() or (self.venvObject.installedMPFVersion if self.venvObject else None)
        self.dialogMPFVersion.blockSignals(True)
        self.dialogMPFVersion.clear()

        # iteriatively adds each mpf version that works to the label
        for release in compatibleReleases:
            currentLabel = release.pypiVersion
            if self.venvObject and release.pypiVersion == self.venvObject.installedMPFVersion:
                currentLabel += "  (current)"
            self.dialogMPFVersion.addItem(currentLabel, release.pypiVersion)

        # Creates an index to be used.
        index = self.dialogMPFVersion.findData(current)
        self.dialogMPFVersion.setCurrentIndex(max(index, 0))
        self.dialogMPFVersion.blockSignals(False)
        self._mpfVersionWasChanged()

    # The following outputs the next release given a selected mpf version
    def _selectedRelease(self) -> compatibilityManager.PyPIRelease | None:
        selectedVersion = self.dialogMPFVersion.currentData()
        return next((release for release in self.availableReleases.get("mpf", []) if release.pypiVersion == selectedVersion), None)

    # The following outputs a compatable companion package given an add on package name
    def _compatibleAddOnRelease(self, addOnPackage: str) -> compatibilityManager.PyPIRelease | None:
        selectedRelease = self._selectedRelease()
        if not selectedRelease:
            return None
        return compatibilityManager.companionReleasePicker(
            addOnPackage, selectedRelease.pypiVersion, self.availableReleases.get(addOnPackage, []), self.preReleaseCheckbox.isChecked()
        )

    # The following function is called when the MPF Version for a VENV is changed
    def _mpfVersionWasChanged(self) -> None:

        # The following sets each package to be installed depending on if the box is checked
        for package, currentCheckBox in self.mpfAddOnDialogs.items():
            matchedRelease = self._compatibleAddOnRelease(package)
            currentCheckBox.setEnabled(matchedRelease is not None)
            if matchedRelease is None:
                currentCheckBox.setChecked(False)
                currentCheckBox.setToolTip("No releases matches this MPF version")
            else:
                currentCheckBox.setToolTip(f"Will install {package}=={matchedRelease.pypiVersion}")
        self._updatePythonModules()

    # The following outputs a list of requirements for a selected release
    def _pythonRequirements(self) -> list[str | None]:
        selectedRelease = self._selectedRelease()
        requirementList = [selectedRelease.requiredPythonVersion] if selectedRelease else []
        for package, box in self.mpfAddOnDialogs.items():
            if box.isChecked() and (match := self._compatibleAddOnRelease(package)):
                requirementList.append(match.requiredPythonVersion)
        return requirementList

    # The following function is used to update the python modules in a virtual environment
    def _updatePythonModules(self) -> None:
        if self.venvObject:
            pythons = [self.venvObject.installedPython]
        else:
            pythons = compatibilityManager.compatablePythonResolver(self._pythonRequirements())
        current = self.pythonVersionDialog.currentData()
        self.pythonVersionDialog.blockSignals(True)
        self.pythonVersionDialog.clear()
        for pythonVersion in pythons:
            self.pythonVersionDialog.addItem(f"{pythonVersion}  (installed)" if pythonVersion in self.installedVENVPackages else pythonVersion, pythonVersion)
        index = self.pythonVersionDialog.findData(current)
        self.pythonVersionDialog.setCurrentIndex(index if index >= 0 else 0)
        self.pythonVersionDialog.blockSignals(False)
        self._validateVENV()
        self._suggestVENVName()

    # The following suggests a virtual environment name based on mpf and python version
    def _suggestVENVName(self) -> None:
        if self.venvObject or self._nameWasEdited:
            return
        version, python = self.dialogMPFVersion.currentData(), self.pythonVersionDialog.currentData()
        if version and python:
            self.venvDialogName.setText(f"mpf-{version}-py{python}")

    # The following updates the location text for a virtual environment
    def _updateVENVLocation(self) -> None:
        self.resolvedVENVLocation.setText(str(self._venvPath()))
        self._validateVENV()

    # The following outputs the full VENV path
    def _venvPath(self) -> Path:
        if self.venvObject:
            return self.venvObject.venvPath
        return self.venvParentFolderPath() / self.venvDialogName.text().strip()

    # The following outputs just parent folder path
    def venvParentFolderPath(self) -> Path:
        return Path(self.venvParentLocation.text().strip()).expanduser()

    # The following runs a set of tests against the VENV to validate it
    def _validateVENV(self) -> None:
        problem = None
        name = self.venvDialogName.text().strip()
        if not self.availableReleases:
            problem = ""  # still loading or failed; status label explains
        elif not self.dialogMPFVersion.currentData():
            problem = "No MPF versions available."
        elif not self.pythonVersionDialog.currentData():
            problem = "No Python version supports this combination of packages."
        elif not self.venvObject:
            if not name:
                problem = "Enter a name."
            elif any(c in name for c in "/\\:"):
                problem = "The name cannot contain path separators."
            elif not self.venvParentLocation.text().strip():
                problem = "Choose a folder for the environment."
            elif self.venvParentFolderPath().exists() and not self.venvParentFolderPath().is_dir():
                problem = f"'{self.venvParentFolderPath()}' is not a folder."
            elif self.storageObject.getVENVbyName(name):
                problem = f"An environment named '{name}' already exists."
            elif self._venvPath().exists():
                problem = f"'{self._venvPath()}' already exists."
        if problem is not None and self.availableReleases:
            self.operationStatus.setText(problem)
        elif self.availableReleases:
            self.operationStatus.setText("")
        self.dialogButtons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(problem is None)

    # The following creates a skeleton virtual environment
    def plan(self) -> venvDialogData:
        mpfVersion = self.dialogMPFVersion.currentData()
        mpfVersionRequirements = [f"mpf=={mpfVersion}"]
        companionPackages, packagesToRemove = [], []
        for package, box in self.mpfAddOnDialogs.items():
            match = self._compatibleAddOnRelease(package) if box.isChecked() else None
            if match:
                mpfVersionRequirements.append(f"{package}=={match.pypiVersion}")
                companionPackages.append(package)
            elif self.venvObject and package in self.venvObject.additionalPackages:
                packagesToRemove.append(package)
        return venvDialogData(
            venvName=self.venvDialogName.text().strip(),
            venvPath=self._venvPath(),
            pythonVersion=self.pythonVersionDialog.currentData(),
            mpfVersion=mpfVersion,
            mpfVersionRequirements=mpfVersionRequirements,
            companionPackages=companionPackages,
            packagesToRemove=packagesToRemove
        )

# The following class is a dialog box for creating new mpf projects
class mpfProjectCreationDialog(QDialog):
    """Creates a new MPF Project with skeleton objects"""

    # The following initializes the dialog
    def __init__(self, store: StorageProcessor, parentWidget: QWidget | None = None):
        super().__init__(parentWidget)
        self.store = store
        self.setWindowTitle("New MPF project")
        self.setMinimumWidth(480)

        self.projectName = QLineEdit()
        self.projectName.textChanged.connect(self._validateProject)
        self.projectParentFolder = QLineEdit(store.settings.projectDirectory)
        self.projectParentFolder.textChanged.connect(self._validateProject)
        self.environmentPair = environmentPairing(store)
        self.operationStatus = QLabel()

        # The following sets up the new project form
        projectForm = QFormLayout()
        projectForm.addRow("Name:", self.projectName)
        projectForm.addRow("Create in:", _browseWidget(self.projectParentFolder, self, "Choose a folder"))
        projectForm.addRow("Environment:", self.environmentPair)

        # The following creates the dialog buttons
        self.projectDialogbuttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.projectDialogbuttons.accepted.connect(self.accept)
        self.projectDialogbuttons.rejected.connect(self.reject)

        # The following lays out the widget for the dialog to add new projects
        projectDialoglayout = QVBoxLayout(self)
        projectDialoglayout.addLayout(projectForm)
        projectDialoglayout.addWidget(self.operationStatus)
        projectDialoglayout.addWidget(self.projectDialogbuttons)
        self._validateProject()

    # The following returns the path of the project
    def projectPath(self) -> Path:
        return Path(self.projectParentFolder.text().strip()).expanduser() / self.projectName.text().strip()

    # The following validates the project dialog box
    def _validateProject(self) -> None:
        name = self.projectName.text().strip()
        problem = ""
        if not name:
            problem = "Enter a project name."
        elif any(c in name for c in "/\\:"):
            problem = "The name cannot contain path separators."
        elif self.projectPath().exists():
            problem = f"'{self.projectPath()}' already exists."
        self.operationStatus.setText(problem)
        self.projectDialogbuttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not problem)

# The following class sets up the dialog box for settings
class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parentWidget: QWidget | None = None):
        super().__init__(parentWidget)
        self.setWindowTitle("MPF-Manager Settings")
        self.setMinimumWidth(480)
        self.venvDirectoryDialog = QLineEdit(settings.venvDirectory)
        self.projectDirectoryDialog = QLineEdit(settings.projectDirectory)
        self.preReleasesCheckBox = QCheckBox("Show MPF pre-releases by default")
        self.preReleasesCheckBox.setChecked(settings.includePreReleases)

        # The following sets up the form for configuring settings
        settingsForm = QFormLayout()
        settingsForm.addRow("Environments folder:", _browseWidget(self.venvDirectoryDialog, self, "Environments folder"))
        settingsForm.addRow("Projects folder:", _browseWidget(self.projectDirectoryDialog, self, "Projects folder"))
        settingsForm.addRow("", self.preReleasesCheckBox)

        # The following configures the dialog buttons for settings
        settingsDialogbuttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        settingsDialogbuttons.accepted.connect(self.accept)
        settingsDialogbuttons.rejected.connect(self.reject)

        # The following configures the layout for the settings dialog box
        settingsDialogLayout = QVBoxLayout(self)
        settingsDialogLayout.addLayout(settingsForm)
        settingsDialogLayout.addWidget(settingsDialogbuttons)

    # The following applies the settings
    def applySettings(self, settings: Settings) -> None:
        settings.venvDirectory = self.venvDirectoryDialog.text().strip()
        settings.projectDirectory = self.projectDirectoryDialog.text().strip()
        settings.includePreReleases = self.preReleasesCheckBox.isChecked()

# The following creates a callable combo box to display the installed environment pairings
def environmentPairing(store: StorageProcessor, selected: str | None = None) -> QComboBox:
    environmentComboBox = QComboBox()
    environmentComboBox.addItem("(none)", None)
    for environment in store.environmentList:
        environmentComboBox.addItem(f"{environment.venvName}  (MPF {environment.installedMPFVersion}, Python {environment.installedPython})", environment.venvName)
    index = environmentComboBox.findData(selected)
    environmentComboBox.setCurrentIndex(max(index, 0))
    return environmentComboBox