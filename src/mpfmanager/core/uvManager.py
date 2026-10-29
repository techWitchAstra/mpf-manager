"""Manager for building and running UV to manage the virtual
Python/MPF Environments"""

#   uvManager - Responsible for managing virtual environments using uv
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human by a human at all stages

from __future__ import annotations

# The following imports json, shell utility and sub process packages
# for later use
import json
import os
import shutil
import subprocess
import sys

# Import file path objects
from pathlib import Path


# The following class helps process runtime errors related to UV
class UvNotFoundError(RuntimeError):
    pass


# The following function is used to locate and determine a UV instance
# to be used
def locateUV() -> str:
    """UV Locator"""

    if getattr(sys, "frozen", False):
        bundleFolder = getattr(sys, "_MEIPASS", None)
        if bundleFolder:
            bundledUV = Path(bundleFolder) / ("uv.exe" if os.name == "nt" else "uv")
            if bundledUV.exists():
                return str(bundledUV)

    # The following Try attempts to work out the file path for UV
    try:
        # It first tries local to the application
        from uv import find_uv_bin

    # If that fails due to an import error it passes the error
    except ImportError:
        pass

    # It will then attempt another try within the user's system
    else:
        try:
            return find_uv_bin()

        # If it fails to find it in the user's system it will pass that
        except FileNotFoundError:
            pass

    # The Following Sets the UV Path
    uvPath = shutil.which("uv")

    # The following error is displayed if UV is not found in the application or system
    if not uvPath:
        raise UvNotFoundError(
            "uv could not be found, re-install mpf-manager or install uv separately (not-recommended)"
        )

    return uvPath


# The following sets up the virtual environment using a specific path
# and python version
def setupVENV(filePath: Path, pythonVersion: str) -> list[str]:
    """setupVENV sets up a virtual environment given a path and python version"""
    return [locateUV(), "venv", "--python", pythonVersion, str(filePath)]


# The following installs objects in the virtual environment based on
# a list of required packages, optional editable source folders, and a virtual environment path
def installVENVPackages(
    venvPath: Path, requiredPackages: list[str], editablePaths: list[Path] | None = None
) -> list[str]:
    """installVENVPackages installs packages (and editable source folders) inside of a virtual environment container"""
    editableArguments = [argument for editablePath in editablePaths or [] for argument in ("-e", str(editablePath))]
    return [locateUV(), "pip", "install", "--python", str(venvPath), *editableArguments, *requiredPackages]


# The following un-installs objects in a virtual environment based
# on a list of packaged and the virtual environment path
def uninstallVENVPackages(venvPath: Path, packagesToRemove: list[str]) -> list[str]:
    """uninstallVENVPackages remove packages from a virtual environment"""
    return [locateUV(), "pip", "uninstall", "--python", str(venvPath), *packagesToRemove]


# The following outputs a list of the packages installed in a virtual environment
def listVENVPackages(venvPath: Path) -> dict[str, str]:
    """listVENVPackages lists the installed packages in a given VENV"""

    # The following process uses uv to output the list of installed python packages
    outputList = subprocess.run(
        [locateUV(), "pip", "list", "--python", str(venvPath), "--format", "json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    # The following returns the list by parsing the list from the output
    return {
        listPointer["name"].lower().replace("_", "-"): listPointer["version"]
        for listPointer in json.loads(outputList or "[]")
    }


# The following outputs a list of the python versions usable for UV in creating VENVs
def listPythonVersions() -> set[str]:
    """listPythonVersions lists the installed python versions for use with UV"""

    # The following process uses UV to determine all the installed python versions
    outputList = subprocess.run(
        [locateUV(), "python", "list", "--only-installed", "--output-format", "json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    # The following creates an object to store the version result in
    versions = set()

    # The following iterates through the JSON output going row by row removing the patch number
    for listItem in json.loads(outputList or "[]"):
        versionParts = str(listItem.get("version", "")).split(".")
        if len(versionParts) >= 2:
            versions.add(f"{versionParts[0]}.{versionParts[1]}")

    # The following returns the versions object
    return versions
