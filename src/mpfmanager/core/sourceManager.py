"""sourceManager reads information about local MPF source checkouts for editable installs"""

#   sourceManager - Responsible for local MPF source folders that are installed in editable mode
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human by a human at all stages

from __future__ import annotations

# The following imports the file, pattern and system utilities used to read a source checkout
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

# tomllib is only part of python from 3.11 onwards, 3.10 falls back to a pattern match
if sys.version_info >= (3, 11):
    import tomllib
else:
    tomllib = None

# The following defines where mpf's source is cloned from, and the branches offered when cloning
MPF_GIT_URL = "https://github.com/missionpinball/mpf.git"
MPF_SOURCE_BRANCHES = ["dev", "0.82.x", "0.81.x", "0.80.x", "0.57.x"]

_VERSION_FIELD_RE = r"^{fieldName}\s*=\s*['\"]([^'\"]+)['\"]"
_REQUIRES_PYTHON_RE = re.compile(r"^requires-python\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE)


# The following stores what was read from a local mpf checkout
@dataclass(frozen=True)
class LocalMPFSource:
    sourcePath: Path
    mpfVersion: str
    requiredPythonVersion: str | None
    gmcVersion: str | None


# The following reads a single version field out of mpf/_version.py without importing it
def _versionField(versionText: str, fieldName: str) -> str | None:
    match = re.search(_VERSION_FIELD_RE.format(fieldName=re.escape(fieldName)), versionText, re.MULTILINE)
    return match.group(1) if match else None


# The following reads the required python versions out of a pyproject.toml
def _requiredPython(pyprojectText: str) -> str | None:
    if tomllib is not None:
        requiredPython = tomllib.loads(pyprojectText).get("project", {}).get("requires-python")
        return str(requiredPython) if requiredPython else None
    match = _REQUIRES_PYTHON_RE.search(pyprojectText)
    return match.group(1) if match else None


# The following reads a local mpf source folder
def readLocalMPFSource(sourcePath: Path) -> LocalMPFSource:
    """returns version information for a local mpf checkout, raising if it isn't one"""

    # First a check is run to see if the folder looks like an installable mpf checkout
    versionFile = sourcePath / "mpf" / "_version.py"
    pyprojectFile = sourcePath / "pyproject.toml"
    if not versionFile.is_file() or not (pyprojectFile.is_file() or (sourcePath / "setup.py").is_file()):
        raise FileNotFoundError(f"'{sourcePath}' does not look like an MPF source folder (no mpf/_version.py)")

    # The following reads the version information
    versionText = versionFile.read_text(encoding="utf-8")
    mpfVersion = _versionField(versionText, "__version__")
    if not mpfVersion:
        raise ValueError(f"Could not read __version__ from {versionFile}")
    requiredPython = _requiredPython(pyprojectFile.read_text(encoding="utf-8")) if pyprojectFile.is_file() else None

    return LocalMPFSource(sourcePath, mpfVersion, requiredPython, _versionField(versionText, "__gmc_version__"))


# The following builds the command to clone mpf's source for an editable install
def cloneMPFSource(destinationPath: Path, branchName: str = "dev") -> list[str]:
    """returns a git clone command for mpf's source"""
    gitPath = shutil.which("git")
    if not gitPath:
        raise FileNotFoundError("git could not be found, install git or choose an existing MPF source folder")
    return [gitPath, "clone", "--branch", branchName, MPF_GIT_URL, str(destinationPath)]
