"""projectManager manages the mpf projects including running them and setting them up"""

from __future__ import annotations

import re
from pathlib import Path

from mpfmanager.core.storageManager import VirtualEnvironment

# The following sets up a generic MPF Template that will be used 
# to give the program/player a building off point. This will likely be 
# depricated in future versions as the editor builds out
CONFIG_VERSION = 6
_CONFIG_VERSION_RE = re.compile(r"^#config_version=(\d+)")

MAIN_CONFIG_TEMPLATE = """\
#config_version={version}

# Main machine config for {name}.
# See https://missionpinball.org for the full configuration reference.

hardware:
  platform: smart_virtual

playfields:
  playfield:
    tags: default
    default_source_device: None

switches:
  s_start:
    number: 1
    tags: start

coils: {{}}

modes:
  - attract
  - game
"""

# What MPF can be asked to do from the manager, mapped to its CLI subcommand.
# To be added - GMC related launching, and both game and monitor
RUN_MODES = {
    "Game": "game",
    "Game + Media Controller (mpf-mc)": "both",
    "Media Controller only (mpf-mc)": "mc",
    "Monitor (mpf-monitor)": "monitor",
}

# Hardware flags for `mpf game`.
# To be added, with/without media controller
HARDWARE_MODES = {
    "Config platform": [],
    "Virtual (-x)": ["-x"],
    "Smart virtual (-X)": ["-X"],
}

# The Following Outputs the main MPF config's path
def mainConfigPath(projectPath: Path) -> Path:
    """returns the path for the main mpf config given a project path"""
    return projectPath / "config" / "config.yaml"

# The following checks if there is a mpf project at a path based on 
# if there is a config file in the correct location.
def checkMPFProjectAtPath(testMPFPath: Path) -> bool:
    """returns true if a config exists at a given test projectPath"""
    return mainConfigPath(testMPFPath).is_file()

# The following checks to see what MPF config version exists at a given 
# project Path
def checkConfigVersion(testConfigpath: Path) -> int | None:
    """checks what version is listed in a given path to a config.yaml"""

    # First the test config path is configured, and tested to see if the file exists
    configFile = mainConfigPath(testConfigpath)
    if not configFile.is_file():
        return None

    # If the config file exists, it is registry matched to find the version number
    with configFile.open(encoding="utf-8") as fileData:
        match = _CONFIG_VERSION_RE.match(fileData.readline().strip())
    return int(match.group(1)) if match else None

# The following creates a new skeleton MPF project given a pathm and project name
def create_project(newProjectPath: Path, projectName: str | None = None) -> Path:
    """creates a skeleton mpf project at a given path"""

    # First a check is run to see if the path or file already exists
    if newProjectPath.exists() and any(newProjectPath.iterdir()):
        raise FileExistsError(f"'{newProjectPath}' already exists and is not empty")

    # If the directory/config does not exist, it is created and written to the drive including
    # directories to hold shows, modes, and the basic config file    
    projectName = projectName or newProjectPath.projectName
    (newProjectPath / "config").mkdir(parents=True)
    for folder in ("modes", "shows"):
        (newProjectPath/ folder).mkdir()
    mainConfigPath(newProjectPath).write_text(
        MAIN_CONFIG_TEMPLATE.format(version=CONFIG_VERSION, projectName=projectName), encoding="utf-8"
    )
    return newProjectPath

# The following command launches MPF 
def runMPF(virtualEnvironment: VirtualEnvironment, mpfLaunchMode: str, hardwareArguements: list[str], additionalLaunchPackages: list[str]) -> list[str]:
    """can be used to start MPF and run a game, but cannot use the MPF GUI"""
    cmd = [str(virtualEnvironment.executable("mpf")), mpfLaunchMode]
    if mpfLaunchMode in ("game", "both"):
        # The text UI needs a real terminal, which a GUI-launched process doesn't have.
        cmd += ["-t", *hardwareArguements]
    return cmd + additionalLaunchPackages