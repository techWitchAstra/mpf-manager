#   compatabilityManager - Responsible for finding the latest python
#       versions that are compatable with a pypi package, to help setup the virtual
#       environment.
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human by a human at all stages

from __future__ import annotations

# Importation of JSON, SSL, and URL library objects for retrieving the
#   package JSON to find the compatable python versions
import json
import ssl
import urllib.error
import urllib.request

# Importation of libraries to make callable objects and classes for data
from collections.abc import Callable
from dataclasses import dataclass

# Importation of two different options for SSL Certificates
import certifi
import truststore
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

# Definition of PYPI_URL to be called when retrieving the JSON for checking
PYPI_URL = "https://pypi.org/pypi/{package}/json"

PYTHON_VERSION_OPTIONS = ["3.8", "3.9", "3.10", "3.11", "3.12", "3.13", "3.14"]

# MPF Add-Ons that can be utilized alongside MPF's core framework
# Currently Supported (in Utility)
# - mpf-mc (Legacy Media Controller)
# - mpf-monitor (Tool for virtually interacting with a machine)
MPF_ADD_ONS = {
    "mpf-mc": "Legacy Media Controller for MPF versions 0.57 and earlier",
    "mpf-monitor": "Tool for virtually testing a MPF project",
}


# The following defines a data class to store information on pypi releases
# such as version and the minimum python version
@dataclass(frozen=True)
class PyPIRelease:
    pypiVersion: str
    requiredPythonVersion: str | None

    # The following adds a version property to the data class
    @property
    def parsed(self) -> Version:
        return Version(self.pypiVersion)

    # The following adds a Pre-Release Check
    @property
    def isPreRelease(self) -> bool:
        return self.parsed.is_prerelease


# The following parses through all of the pypi release data for a minimum required python version
def pypiReleaseProcessor(releaseData: dict) -> list[PyPIRelease]:
    """pypiReleaseProcessor pulls pypi Release information from pypi json data"""

    # The following makes an object to store releases in
    pypiReleases = []

    # The following iterates through the data looking for release information for each version and
    # required python version
    for pypiVersion, releaseFiles in (releaseData.get("releases") or {}).items():
        releaseFiles = [filePointer for filePointer in releaseFiles if not filePointer.get("yanked")]
        if not releaseFiles:
            continue
        try:
            Version(pypiVersion)
        except InvalidVersion:
            continue
        requiredPython = next(
            (filePointer.get("requires_python") for filePointer in releaseFiles if filePointer.get("requires_python")),
            None,
        )

        # The following appends a release to the list object
        pypiReleases.append(PyPIRelease(pypiVersion, requiredPython))

    # The following sorts the releases by newest, and returns the releases
    pypiReleases.sort(key=lambda r: r.parsed, reverse=True)
    return pypiReleases


# The following function holds the SSL certificates to try
def _ssl_contexts() -> list[tuple[str, Callable[[], ssl.SSLContext]]]:
    """Returns the list of ssl certificate sources to try in order
    the python default one works on most systems but not macOS and
    the mozilla one is used instead"""

    return [
        ("system trust store", lambda: truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)),
        ("certifi bundle", lambda: ssl.create_default_context(cafile=certifi.where())),
    ]


# The following function checks if an exception is a ssl certificate exception
def isCertException(certException: Exception) -> bool:
    exceptionReason = certException.reason if isinstance(certException, urllib.error.URLError) else certException
    return isinstance(exceptionReason, ssl.SSLCertVerificationError)


def jsonRetriever(jsonURL: str, connectionTimeout: float = 15) -> dict:
    """function for retrieval of JSON data from a url"""

    # The follow places a location to store failure exceptions
    failureAttempts = []

    # The following attempts pull the json data for each ssl bundle
    for certificateSource, make_context in _ssl_contexts():
        try:
            with urllib.request.urlopen(
                jsonURL, timeout=connectionTimeout, context=make_context()
            ) as connectionResponse:
                return json.load(connectionResponse)

        # The following logs the failure attempt if it is a certificate
        # exception, if not immediately raises it
        except (urllib.error.URLError, ssl.SSLError) as urlException:
            if not isCertException(urlException):
                raise
            failureAttempts.append(f"{certificateSource}:{urlException}")

    # The following raises and outputs the reason for the connection failure
    raise ConnectionError(
        "Could not verify HTTPS certificate for PyPI. If you are behind "
        "a proxy or anti-virus that inspects HTTPS you may need to add "
        "PyPI's certificate to your system trust store. \n" + "\n".join(failureAttempts)
    )


# The following function utilizes the jsonRetriever to get the pypi release
# informatin for a given package
def pypiReleaseRetriever(pypiPackage: str, connectionTimeout: float = 15) -> list[PyPIRelease]:
    """Retrieves the release information for a given pypi package"""
    return pypiReleaseProcessor(jsonRetriever(PYPI_URL.format(package=pypiPackage), connectionTimeout))


# The following filters out pypi releases considered pre-release
def filterPyPIReleases(pypiReleases: list[PyPIRelease], includePreReleases: bool) -> list[PyPIRelease]:
    """Selectively includes pre-releases in list of releases"""
    return [release for release in pypiReleases if includePreReleases or not release.isPreRelease]


# The following determines if the python version is suported given a set and a python version
def pythonSetCheck(requiredPythonVersion: str | None, testPythonVersion: str) -> bool:
    """Determines with a given python version if the configuration is supported based
    on a potential required python set"""

    # If a set is not given then it will return true
    if not requiredPythonVersion:
        return True
    try:
        # The following returns if the python version is in the set given
        return SpecifierSet(requiredPythonVersion).contains(testPythonVersion, prereleases=True)
    except InvalidSpecifier:
        return True


# The following function given a list of acceptable pythonVersions, will check against the global variable of python
# versions to create a list of acceptable python versions
def compatablePythonResolver(
    pythonVersionRequired: list[str | None], candidates: list[str] = PYTHON_VERSION_OPTIONS
) -> list[str]:
    """outputs a list of python versions compatable with a given set of requirements"""

    # The following creates an array of python versions that pass the check against the required python version
    acceptablePythonVersions = [p for p in candidates if all(pythonSetCheck(r, p) for r in pythonVersionRequired)]

    # The following returns all acceptable python versions
    return sorted(acceptablePythonVersions, key=Version, reverse=True)


# The following determines what companion package versions are compatable based on their mpf version
def companionReleasePicker(
    companionPackage: str, mpfVersion: str, companionReleases: list[PyPIRelease], includePreReleases: bool = False
) -> PyPIRelease | None:
    """picks a companion media controller and/or monitor version based on an mpf version"""

    # The following sets the mpf version as the version passed to the function
    mpf = Version(mpfVersion)

    companionReleaseCanidates = filterPyPIReleases(companionReleases, includePreReleases or mpf.is_prerelease)

    if companionPackage == "mpf-monitor" and mpf >= Version("0.80.0.dev0"):
        return next((release for release in companionReleaseCanidates if release.parsed.major >= 1), None)
    return next(
        (release for release in companionReleaseCanidates if release.parsed.release[:2] == mpf.release[:2]),
        None,
    )
