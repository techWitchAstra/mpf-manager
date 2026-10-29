import io
import json
import ssl
import urllib.error

import pytest

from mpfmanager.core import compatibilityManager
from mpfmanager.core.compatibilityManager import PyPIRelease

PYPI_DATA = {
    "releases": {
        "0.57.0": [{"requires_python": ">=3.7"}],
        "0.80.0": [{"requires_python": None}, {"requires_python": ">=3.8"}],
        "0.81.0.dev2": [{"requires_python": ">=3.10"}],
        "0.50.0": [{"yanked": True}],
        "0.10.0": [],
        "bad version": [{"requires_python": ">=3.8"}],
    }
}


def test_pypiReleaseProcessor():
    releases = compatibilityManager.pypiReleaseProcessor(PYPI_DATA)
    assert releases == [
        PyPIRelease("0.81.0.dev2", ">=3.10"),
        PyPIRelease("0.80.0", ">=3.8"),
        PyPIRelease("0.57.0", ">=3.7"),
    ]
    assert releases[0].isPreRelease and not releases[1].isPreRelease
    assert compatibilityManager.pypiReleaseProcessor({}) == []


def test_filterPyPIReleases():
    releases = compatibilityManager.pypiReleaseProcessor(PYPI_DATA)
    assert [r.pypiVersion for r in compatibilityManager.filterPyPIReleases(releases, False)] == ["0.80.0", "0.57.0"]
    assert len(compatibilityManager.filterPyPIReleases(releases, True)) == 3


@pytest.mark.parametrize(
    ("required", "python", "expected"),
    [(None, "3.8", True), ("not a specifier", "3.8", True), (">=3.10", "3.13", True), (">=3.10", "3.9", False)],
)
def test_pythonSetCheck(required, python, expected):
    assert compatibilityManager.pythonSetCheck(required, python) is expected


def test_compatablePythonResolver():
    assert compatibilityManager.compatablePythonResolver([">=3.10", "<3.13", None]) == ["3.12", "3.11", "3.10"]
    assert compatibilityManager.compatablePythonResolver([">=4.0"]) == []


MONITOR_RELEASES = [PyPIRelease("1.1.0.dev1", None), PyPIRelease("1.0.0", None), PyPIRelease("0.57.0", None)]
MC_RELEASES = [PyPIRelease("0.57.2", None), PyPIRelease("0.56.0", None)]


def test_companionReleasePickerMonitorForGMCEraMPF():
    assert compatibilityManager.companionReleasePicker("mpf-monitor", "0.80.0", MONITOR_RELEASES).pypiVersion == "1.0.0"
    picked = compatibilityManager.companionReleasePicker("mpf-monitor", "0.80.0", MONITOR_RELEASES, True)
    assert picked is not None and picked.pypiVersion == "1.1.0.dev1"


def test_companionReleasePickerMatchesMinorVersion():
    picked = compatibilityManager.companionReleasePicker("mpf-mc", "0.57.3", MC_RELEASES)
    assert picked is not None and picked.pypiVersion == "0.57.2"
    picked = compatibilityManager.companionReleasePicker("mpf-monitor", "0.57.0", MONITOR_RELEASES)
    assert picked is not None and picked.pypiVersion == "0.57.0"
    assert compatibilityManager.companionReleasePicker("mpf-mc", "0.80.0", MC_RELEASES) is None


def test_isCertException():
    certError = ssl.SSLCertVerificationError("bad cert")
    assert compatibilityManager.isCertException(certError)
    assert compatibilityManager.isCertException(urllib.error.URLError(certError))
    assert not compatibilityManager.isCertException(urllib.error.URLError("timed out"))


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _contexts(monkeypatch, *outcomes):
    """Each outcome is either bytes to return or an exception to raise, one per certificate source"""
    monkeypatch.setattr(
        compatibilityManager,
        "_ssl_contexts",
        lambda: [(f"source{index}", lambda: object()) for index in range(len(outcomes))],
    )
    remaining = list(outcomes)

    def fakeUrlopen(_url, timeout, context):
        outcome = remaining.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return _FakeResponse(outcome)

    monkeypatch.setattr(compatibilityManager.urllib.request, "urlopen", fakeUrlopen)
    return remaining


def test_urlRetrieverFallsBackAfterCertificateFailure(monkeypatch):
    certFailure = urllib.error.URLError(ssl.SSLCertVerificationError("bad cert"))
    _contexts(monkeypatch, certFailure, b"payload")
    assert compatibilityManager.urlRetriever("https://example.test") == b"payload"


def test_urlRetrieverReraisesOtherErrors(monkeypatch):
    remaining = _contexts(monkeypatch, urllib.error.URLError("timed out"), b"never used")
    with pytest.raises(urllib.error.URLError):
        compatibilityManager.urlRetriever("https://example.test")
    assert remaining == [b"never used"]


def test_urlRetrieverReportsWhenEveryCertificateSourceFails(monkeypatch):
    certFailure = ssl.SSLCertVerificationError("bad cert")
    _contexts(monkeypatch, certFailure, certFailure)
    with pytest.raises(ConnectionError, match="(?s)source0.*source1"):
        compatibilityManager.urlRetriever("https://example.test")


def test_sslContextsCanBeCreated():
    for _name, makeContext in compatibilityManager._ssl_contexts():
        assert isinstance(makeContext(), ssl.SSLContext)


def test_jsonAndPyPIRetrievers(monkeypatch):
    requested = []
    monkeypatch.setattr(
        compatibilityManager,
        "urlRetriever",
        lambda url, _timeout: requested.append(url) or json.dumps(PYPI_DATA).encode(),
    )
    assert compatibilityManager.jsonRetriever("https://example.test") == PYPI_DATA
    assert compatibilityManager.pypiReleaseRetriever("mpf")[0].pypiVersion == "0.81.0.dev2"
    assert requested[-1] == "https://pypi.org/pypi/mpf/json"
