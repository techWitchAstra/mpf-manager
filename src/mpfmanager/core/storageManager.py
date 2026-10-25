"""Manages the storage of environment and project information in home folder yaml folders"""

#   storageManager - Responsible for storing and processing environment, setting, and project information
# 
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human by a human at all stages

from __future__ import annotations

# The following imports libraries related to writing storage data to a yaml via the yaml Interfacer
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from mpfmanager.core import yamlInterfacer

STORE_VERSION = 1

# The following function determines the default config information storage location
def default_home() -> Path:
    """Outputs a path object where the configuration data will be stored for the application"""
    if env := os.environ.get("MPF_MANAGER_HOME"):
        return Path(env).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "mpfmanager"

# The following creates a class to store environment information in for use in this and other functions
@dataclass
class VirtualEnvironment:
    venvName: str
    pathToVENV: str
    installedPython: str
    installedMPFVersion: str
    additionalPackages: list[str] = field(default_factory=list)

    # The following property returns the path to its respective virtual environment
    @property
    def venvPath(self) -> Path:
        return Path(self.pathToVENV)

    # The following function returns the path to the executable to run the virtual environment depending on OS
    def executable(self, venvName: str) -> Path:
        """Path of a console script (e.g. 'mpf') inside this environment."""
        if os.name == "nt":
            return self.venvPath / "Scripts" / f"{venvName}.exe"
        return self.venvPath/ "bin" / venvName

    # The following property returns if a virtual environment exists or not
    @property
    def exists(self) -> bool:
        return (self.venvPath / "pyvenv.cfg").exists()

# The following creates a class to store project information in for use in this and other functions
@dataclass
class Project:
    projectName: str
    projectPath: str
    virtualEnvironment: str | None = None

# The following creates a settings class to store user settings in.
@dataclass
class Settings:
    venvDirectory: str = ""
    projectDirectory: str = ""
    includePreReleases: bool = False

# The following class is used to process storage operations within MPF Manager
class StorageProcessor:
    """Performs storage operations for settings, projects, and virtual environments using yaml"""

    # The following initializes the class and sets a save file path, initializes directory paths for mpf and the virtual environments
    def __init__(self, homePath: Path | None = None):
        self.homePath = homePath or default_home()
        self.savePath = self.homePath / "config.yaml"
        self.settings = Settings(
            venvDirectory=str(self.homePath / "envs"),
            projectDirectory=str(Path.home() / "mpf-projects"),
        )
        self.environmentList: list[VirtualEnvironment] = []
        self.projectList: list[Project] = []
        self.loadConfiguration()

    # The following loads up the configuration data for mpf-manager using yamlInterfacer
    def loadConfiguration(self) -> None:
        """loads the list of virtual environments, project, and settings from the config.yaml file"""
        data = yamlInterfacer.loadYAML(self.savePath) or {}

        # The following gets the settings specific data
        settings = data.get("settings") or {}

        # The following applies the settings for each of the settings
        for settingKey in asdict(self.settings):
            if settingKey in settings:
                setattr(self.settings, settingKey, settings[settingKey])
        
        # The following loads the virtual environments list data from the config
        # yaml into an object
        self.environmentList = [
            VirtualEnvironment(
                venvName=str(environment["venvName"]),
                pathToVENV=str(environment["pathToVENV"]),
                installedPython=str(environment.get("installedPython", "")),
                installedMPFVersion=str(environment.get("installedMPFVersion", "")),
                additionalPackages=[str(x) for x in environment.get("additionalPackages") or []],
            )
            for environment in data.get("environmentList") or []
        ]

        # The following saves the project list data from the config.yaml to an object
        self.projectList = [
            Project(
                projectName=str(project["projectName"]),
                projectPath=str(project["projectPath"]),
                virtualEnvironment=project.get("virtualEnvironment"),
            )
            for project in data.get("projectList") or []
        ]

    # The following saves the configuration data for mpf-manager using yamlInterfacer
    def saveConfiguration(self) -> None:
        """saves the list of virtual environments, project, and settings from the config.yaml file"""
        data = {
            "version": STORE_VERSION,
            "settings": asdict(self.settings),
            "environmentList": [asdict(environment) for environment in self.environmentList],
            "projectList": [asdict(project) for project in self.projectList],
        }
        yamlInterfacer.writeYAML(data, self.savePath, headerString="# MPF-Manager configuration")

    # VirtualEnvironment Specific Functions

    # The following finds a virtual environment given a name
    def getVENVbyName(self, venvName: str | None) -> VirtualEnvironment | None:
        """gives the virtual environment data class for a given virtualEnvironment Name"""
        return next((environment for environment in self.environmentList if environment.venvName == venvName), None)

    # The following adds a virtual environment given the virtual environment object
    def addVENV(self, environmentToAdd: VirtualEnvironment) -> None:
        """adds a given virtual environment to the class"""

        # The following checks to see if the virtual environment already exists
        if self.getVENVbyName(environmentToAdd.venvName):
            raise ValueError(f"A virtual environment named '{environmentToAdd.venvName}' already exists")

        # If the virtual environment doesn't already exist in the list then it is added
        self.environmentList.append(environmentToAdd)
        self.saveConfiguration()


    def removeVENV(self, nameEnvironmentToRemove: str) -> None:
        """removes a given virtual environment from the class"""

        # Below removes the environment to be removed from the list of environments
        # if it exists
        self.environmentList = [environment for environment in self.environmentList if environment.venvName != nameEnvironmentToRemove]
        
        # The following removes the environment for any projects that listed the 
        # environment being removed
        for project in self.projectList:
            if project.virtualEnvironment == nameEnvironmentToRemove:
                project.virtualEnvironment = None
        self.saveConfiguration()

    # Project Specific Functions

    # The following returns a project object when given the path to the project
    def getProjectbyPath(self, projectPath: str) -> Project | None:
        """gives a project object when given a path to a project"""
        resolvedPath = str(Path(projectPath).resolve())
        return next((project for project in self.projectList if str(Path(project.projectPath).resolve()) == resolvedPath), None)

    # The following adds a project to the class given the project
    def addProject(self, project: Project) -> None:
        """adds a project to the class when given a project"""

        # The following checks to see if the project is already registered
        if self.getProjectbyPath(project.projectPath):
            raise ValueError(f"Project at '{project.projectPath}' is already registered")
        
        # If the project does not exist it adds it to the configuration
        self.projectList.append(project)
        self.saveConfiguration()

    # The following removes a project from the class given the path
    def removeProject(self, projectToBeRemovedpath: str) -> None:
        """removes a project from the class when given a project path"""
        
        resolvedPath = str(Path(projectToBeRemovedpath).resolve())
        self.projectList = [project for project in self.projectList if str(Path(project.projectPath).resolve()) != resolvedPath]
        self.saveConfiguration()

    # The following sets a virtual environment for a project
    def setProjectVENV(self, projectPath: str, venvName: str | None) -> None:
        if project := self.getProjectbyPath(projectPath):
            project.virtualEnvironment = venvName
            self.saveConfiguration()