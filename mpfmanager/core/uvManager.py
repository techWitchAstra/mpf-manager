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
import shutil
import subprocess

# Import file path objects
from pathlib import Path

# The following class helps process runtime errors related to UV
class UvNotFoundError(RuntimeError):
    pass

# The following function is used to locate and determine a UV instance 
# to be used
def locateUV() -> str:
    """UV Locator"""

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
        except FileExistsError:
            pass

    # The Following Sets the UV Path    
    uvPath = shutil.which("uv")

    if not uvPath:
        raise UvNotFoundError(
            "uv could not be found, re-install mpf-manager or install "
            "uv separately (not-recommended)"
        )

    # The following sets up the virtual environment using a specific path 
    # and python version
    def setupVENV(filePath: Path, pythonVersion: str) -> list[str]:
        return [locateUV(), "venv", "--python", pythonVersion,str(filePath)]

    # The following installs objects in the virtual environment based on 
    # a list of required packages and a virtual environment path
    def installPythonInVENV(venvPath: Path, requiredPackages: list[str]) -> list[str]:
        return [locateUV(), "pip", "install", "--python", str(venvPath), *requiredPackages]

    