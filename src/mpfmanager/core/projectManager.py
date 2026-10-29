"""projectManager manages the mpf projects including running them and setting them up"""

#   projectManager - Responsible for managing and launching projects
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human by a human at all stages

from __future__ import annotations

import os
import re
import shutil
import sys
from pathlib import Path

from packaging.version import InvalidVersion, Version

from mpfmanager.core.storageManager import VirtualEnvironment

# The following sets up a generic MPF Template that will be used
# to give the program/player a building off point. This will likely be
# depricated in future versions as the editor builds out
CONFIG_VERSION = 6
_CONFIG_VERSION_RE = re.compile(r"^#config_version=(\d+)")

MONITOR_START_DELAY_MS = 2000

GMC_MIN_MPF_VERSION = Version("0.80.0.dev0")
GMC_START_DELAY_MS = 2000

GODOT_EXECUTABLE_NAMES = ("godot", "godot4", "Godot", "godot.exe", "Godot.exe")
GODOT_MACOS_APP_PATH = Path("/Applications/Godot.app/Contents/MacOS/Godot")

MAIN_CONFIG_TEMPLATE = """\
#config_version={version}

# Main machine config for {projectName}.
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
RUN_MODES = {
    "Game": "game",
    "Game + Media Controller (mpf-mc)": "both",
    "Media Controller only (mpf-mc)": "mc",
    "Game + GMC (Godot)": "gmc",
    "GMC only (Godot)": "gmconly",
    "Monitor (mpf-monitor)": "monitor",
}

# The following groups the run modes by which media controller they need
MPF_MC_MODES = ("both", "mc")
GMC_MODES = ("gmc", "gmconly")

MONITOR_COMPATIBLE_MODES = ("game", "both", "gmc")

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


# The following checks if a virtual environment's MPF version can use the Godot Media Controller
def isGMCEligible(virtualEnvironment: VirtualEnvironment | None) -> bool:
    """returns true if the environment has MPF 0.80 or newer installed"""
    if virtualEnvironment is None or not virtualEnvironment.installedMPFVersion:
        return False
    try:
        return Version(virtualEnvironment.installedMPFVersion) >= GMC_MIN_MPF_VERSION
    except InvalidVersion:
        return False


# The following looks for a Godot project in a MPF machine folder, either at
# the root or one folder down (e.g. machine/gmc/project.godot)
def findGodotProject(projectPath: Path) -> Path | None:
    """returns the folder containing project.godot, or None if one can't be found"""
    if (projectPath / "project.godot").is_file():
        return projectPath
    if not projectPath.is_dir():
        return None
    return next(
        (
            subFolder
            for subFolder in sorted(projectPath.iterdir())
            if subFolder.is_dir() and (subFolder / "project.godot").is_file()
        ),
        None,
    )


# The following attempts to find an installed copy of Godot, this is only used to
# fill in the setting, the path in settings always wins
def detectGodotExecutable() -> str | None:
    """returns the path to an installed godot executable if one can be found"""
    for executableName in GODOT_EXECUTABLE_NAMES:
        if foundExecutable := shutil.which(executableName):
            return foundExecutable
    if sys.platform == "darwin" and GODOT_MACOS_APP_PATH.is_file():
        return str(GODOT_MACOS_APP_PATH)
    return None


# The following checks that a configured godot path points at something runnable
def checkGodotExecutable(godotExecutable: str) -> bool:
    """returns true if the given godot path exists and can be executed"""
    godotPath = Path(godotExecutable)
    return bool(godotExecutable) and godotPath.is_file() and os.access(godotPath, os.X_OK)


# The following creates a new skeleton MPF project given a pathm and project name
def createNewMPFProject(newProjectPath: Path, projectName: str | None = None) -> Path:
    """creates a skeleton mpf project at a given path"""

    # First a check is run to see if the path or file already exists
    if newProjectPath.exists() and any(newProjectPath.iterdir()):
        raise FileExistsError(f"'{newProjectPath}' already exists and is not empty")

    # If the directory/config does not exist, it is created and written to the drive including
    # directories to hold shows, modes, and the basic config file
    projectName = projectName or newProjectPath.name
    (newProjectPath / "config").mkdir(parents=True)
    for folder in ("modes", "shows"):
        (newProjectPath / folder).mkdir()
    mainConfigPath(newProjectPath).write_text(
        MAIN_CONFIG_TEMPLATE.format(version=CONFIG_VERSION, projectName=projectName), encoding="utf-8"
    )
    return newProjectPath


# The following command launches MPF
def runMPF(
    virtualEnvironment: VirtualEnvironment,
    mpfLaunchMode: str,
    hardwareArguements: list[str],
    additionalLaunchPackages: list[str],
) -> list[str]:
    """can be used to start MPF and run a game, but cannot use the MPF GUI"""
    # GMC is launched separately through godot, so MPF itself only runs the game
    mpfSubcommand = "game" if mpfLaunchMode == "gmc" else mpfLaunchMode
    cmd = [str(virtualEnvironment.executable("mpf")), mpfSubcommand]
    if mpfSubcommand in ("game", "both"):
        # The text UI needs a real terminal, which a GUI-launched process doesn't have.
        cmd += ["-t", *hardwareArguements]
    return cmd + additionalLaunchPackages


# The following builds the command to launch a Godot (GMC) project
def runGMC(godotExecutable: str, gmcProjectPath: Path, openEditor: bool = False) -> list[str]:
    """returns the command to launch godot pointed at a GMC project"""
    cmd = [godotExecutable, "--path", str(gmcProjectPath)]
    if openEditor:
        cmd.append("-e")
    return cmd


def runMPFWithMonitor(
    virtualEnvironment, mpfLaunchMode, hardwareArguements, additonalLaunchPackages, startMonitor
) -> list[list[str]]:
    """returns the game command and the monitor commands"""

    commandList = [runMPF(virtualEnvironment, mpfLaunchMode, hardwareArguements, additonalLaunchPackages)]
    if startMonitor and mpfLaunchMode in MONITOR_COMPATIBLE_MODES:
        commandList.append(runMPF(virtualEnvironment, "monitor", [], []))
    return commandList
