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
import subprocess
import sys
import urllib.error
from dataclasses import dataclass
from pathlib import Path

from packaging.version import Version

from mpfmanager.core import compatibilityManager

# tomllib is only part of python from 3.11 onwards, 3.10 falls back to a pattern match
if sys.version_info >= (3, 11):
    import tomllib
else:
    tomllib = None

# The following defines where mpf's source is cloned and read from
MPF_GIT_URL = "https://github.com/missionpinball/mpf.git"
MPF_RAW_URL = "https://raw.githubusercontent.com/missionpinball/mpf/{branch}/{path}"
MPF_DEV_BRANCH = "dev"

# Release line branches older than this need pythons that uv environments can't be made with
MPF_BRANCH_MIN_VERSION = Version("0.57")
_RELEASE_BRANCH_RE = re.compile(r"^(\d+\.\d+)(\.x)?$")
_UNSAFE_FOLDER_CHARACTERS_RE = re.compile(r"[^A-Za-z0-9._-]")

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


# The following turns the text of mpf/_version.py (and pyproject.toml if there is one) into source information
def parseMPFSource(sourcePath: Path, versionText: str, pyprojectText: str | None) -> LocalMPFSource:
    """returns version information from the contents of an mpf checkout's version and project files"""
    mpfVersion = _versionField(versionText, "__version__")
    if not mpfVersion:
        raise ValueError(f"Could not read __version__ for the MPF source at {sourcePath}")
    requiredPython = _requiredPython(pyprojectText) if pyprojectText is not None else None
    return LocalMPFSource(sourcePath, mpfVersion, requiredPython, _versionField(versionText, "__gmc_version__"))


# The following checks if a folder looks like an installable mpf checkout
def isMPFSource(sourcePath: Path) -> bool:
    """returns true if the folder has mpf/_version.py and a pyproject.toml or setup.py"""
    return (sourcePath / "mpf" / "_version.py").is_file() and (
        (sourcePath / "pyproject.toml").is_file() or (sourcePath / "setup.py").is_file()
    )


# The following reads a local mpf source folder
def readLocalMPFSource(sourcePath: Path) -> LocalMPFSource:
    """returns version information for a local mpf checkout, raising if it isn't one"""

    # First a check is run to see if the folder looks like an installable mpf checkout
    if not isMPFSource(sourcePath):
        raise FileNotFoundError(f"'{sourcePath}' does not look like an MPF source folder (no mpf/_version.py)")

    # The following reads the version information
    pyprojectFile = sourcePath / "pyproject.toml"
    return parseMPFSource(
        sourcePath,
        (sourcePath / "mpf" / "_version.py").read_text(encoding="utf-8"),
        pyprojectFile.read_text(encoding="utf-8") if pyprojectFile.is_file() else None,
    )


# The following reads mpf's version information for a branch straight from github, without cloning it
def readRemoteMPFSource(branchName: str, destinationPath: Path) -> LocalMPFSource:
    """returns version information for an mpf branch on github, as it will be once cloned to destinationPath"""
    versionText = compatibilityManager.urlRetriever(
        MPF_RAW_URL.format(branch=branchName, path="mpf/_version.py")
    ).decode("utf-8")

    # Older branches have no pyproject.toml, which github reports as not found
    try:
        pyprojectText: str | None = compatibilityManager.urlRetriever(
            MPF_RAW_URL.format(branch=branchName, path="pyproject.toml")
        ).decode("utf-8")
    except urllib.error.HTTPError as httpException:
        if httpException.code != 404:
            raise
        pyprojectText = None
    return parseMPFSource(destinationPath, versionText, pyprojectText)


# The following finds git, which is needed for anything involving mpf's github source
def _gitPath() -> str:
    gitPath = shutil.which("git")
    if not gitPath:
        raise FileNotFoundError("git could not be found, install git or choose an existing MPF source folder")
    return gitPath


# The following lists the mpf branches that can be installed in editable mode, dev first then newest release lines
def listMPFBranches() -> list[str]:
    """returns the dev branch and release line branches (e.g. 0.82.x) of mpf on github"""
    output = subprocess.run(
        [_gitPath(), "ls-remote", "--heads", MPF_GIT_URL],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout

    # The following keeps dev and release lines, leaving out feature branches and very old release lines
    branchNames = set()
    for line in output.splitlines():
        reference = line.split("\t")[-1].strip()
        branchName = reference.removeprefix("refs/heads/")
        if branchName == MPF_DEV_BRANCH:
            branchNames.add(branchName)
        elif (match := _RELEASE_BRANCH_RE.match(branchName)) and Version(match.group(1)) >= MPF_BRANCH_MIN_VERSION:
            branchNames.add(branchName)

    releaseLines = sorted(
        (branchName for branchName in branchNames if branchName != MPF_DEV_BRANCH),
        key=lambda branchName: Version(branchName.removesuffix(".x")),
        reverse=True,
    )
    return ([MPF_DEV_BRANCH] if MPF_DEV_BRANCH in branchNames else []) + releaseLines


# The following returns where mpf-manager keeps its own checkout of an mpf branch
def managedSourcePath(homePath: Path, branchName: str) -> Path:
    """returns the managed folder a github branch of mpf is cloned into"""
    return homePath / "mpf-sources" / f"mpf-{_UNSAFE_FOLDER_CHARACTERS_RE.sub('_', branchName)}"


# The following builds the command to clone mpf's source for an editable install
def cloneMPFSource(destinationPath: Path, branchName: str = "dev") -> list[str]:
    """returns a git clone command for mpf's source"""
    return [_gitPath(), "clone", "--branch", branchName, MPF_GIT_URL, str(destinationPath)]


# The following builds the command to bring an existing checkout up to date with its github branch
def updateMPFSource(sourcePath: Path, branchName: str) -> list[str]:
    """returns a git pull command for an existing mpf checkout"""
    return [_gitPath(), "-C", str(sourcePath), "pull", "--ff-only", "origin", branchName]


# The following picks between cloning a branch or updating the checkout that is already there
def sourceCommands(sourcePath: Path, branchName: str) -> list[list[str]]:
    """returns the git commands that leave sourcePath holding an up to date checkout of the branch"""
    if isMPFSource(sourcePath):
        return [updateMPFSource(sourcePath, branchName)]
    if sourcePath.exists() and any(sourcePath.iterdir()):
        raise FileExistsError(f"'{sourcePath}' already exists and is not an MPF source folder")
    return [cloneMPFSource(sourcePath, branchName)]
