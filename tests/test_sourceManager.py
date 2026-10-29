import subprocess
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

from mpfmanager.core import sourceManager, uvManager


def _fakeSource(root: Path, gmcLine: str = "__gmc_version__ = '1.0.0'\n") -> Path:
    (root / "mpf").mkdir(parents=True)
    (root / "mpf" / "_version.py").write_text(f'"""doc"""\n\n__version__ = \'0.82.0.dev0\'\n{gmcLine}')
    (root / "pyproject.toml").write_text('[project]\nname = "mpf"\nrequires-python = ">=3.10,<3.15"\n')
    return root


def test_readLocalMPFSource(tmp_path):
    source = sourceManager.readLocalMPFSource(_fakeSource(tmp_path / "mpf-src"))
    assert source.sourcePath == tmp_path / "mpf-src"
    assert source.mpfVersion == "0.82.0.dev0"
    assert source.gmcVersion == "1.0.0"
    assert source.requiredPythonVersion == ">=3.10,<3.15"


def test_readLocalMPFSourceWithoutGMCVersion(tmp_path):
    assert sourceManager.readLocalMPFSource(_fakeSource(tmp_path, "")).gmcVersion is None


def test_readLocalMPFSourceWithoutTomllib(tmp_path, monkeypatch):
    monkeypatch.setattr(sourceManager, "tomllib", None)
    assert sourceManager.readLocalMPFSource(_fakeSource(tmp_path)).requiredPythonVersion == ">=3.10,<3.15"


def test_readLocalMPFSourceRejectsOtherFolders(tmp_path):
    with pytest.raises(FileNotFoundError):
        sourceManager.readLocalMPFSource(tmp_path)


def test_readLocalMPFSourceNeedsVersion(tmp_path):
    source = _fakeSource(tmp_path)
    (source / "mpf" / "_version.py").write_text("nothing = 1\n")
    with pytest.raises(ValueError):
        sourceManager.readLocalMPFSource(source)


def test_cloneMPFSource(monkeypatch, tmp_path):
    monkeypatch.setattr(sourceManager.shutil, "which", lambda _name: "/usr/bin/git")
    assert sourceManager.cloneMPFSource(tmp_path / "mpf", "0.82.x") == [
        "/usr/bin/git",
        "clone",
        "--branch",
        "0.82.x",
        "https://github.com/missionpinball/mpf.git",
        str(tmp_path / "mpf"),
    ]


def test_cloneMPFSourceWithoutGit(monkeypatch, tmp_path):
    monkeypatch.setattr(sourceManager.shutil, "which", lambda _name: None)
    with pytest.raises(FileNotFoundError):
        sourceManager.cloneMPFSource(tmp_path)


def test_installVENVPackagesEditable(monkeypatch, tmp_path):
    monkeypatch.setattr(uvManager, "locateUV", lambda: "uv")
    command = uvManager.installVENVPackages(tmp_path / "venv", ["mpf-monitor==1.0.0"], [tmp_path / "src"])
    assert command == [
        "uv",
        "pip",
        "install",
        "--python",
        str(tmp_path / "venv"),
        "-e",
        str(tmp_path / "src"),
        "mpf-monitor==1.0.0",
    ]


def test_installVENVPackagesWithoutEditable(monkeypatch, tmp_path):
    monkeypatch.setattr(uvManager, "locateUV", lambda: "uv")
    assert uvManager.installVENVPackages(tmp_path, ["mpf==0.80.0"])[-1] == "mpf==0.80.0"


LS_REMOTE_OUTPUT = "\n".join(
    f"{index:040x}\trefs/heads/{name}"
    for index, name in enumerate(
        ["0.21", "0.56.x", "0.57.x", "0.80.x", "0.82.x", "0.81.x", "dev", "feature-branch", "dependabot/pip/x"]
    )
)


def test_listMPFBranches(monkeypatch):
    calls = []

    def fakeRun(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=LS_REMOTE_OUTPUT)

    monkeypatch.setattr(sourceManager.shutil, "which", lambda _name: "git")
    monkeypatch.setattr(sourceManager.subprocess, "run", fakeRun)
    assert sourceManager.listMPFBranches() == ["dev", "0.82.x", "0.81.x", "0.80.x", "0.57.x"]
    assert calls == [["git", "ls-remote", "--heads", sourceManager.MPF_GIT_URL]]


def test_listMPFBranchesWithoutGit(monkeypatch):
    monkeypatch.setattr(sourceManager.shutil, "which", lambda _name: None)
    with pytest.raises(FileNotFoundError):
        sourceManager.listMPFBranches()


def _rawFiles(files: dict[str, bytes | int]):
    def fakeRetriever(url, _timeout=30):
        content = files[url.rsplit("/", 1)[-1]]
        if isinstance(content, int):
            raise urllib.error.HTTPError(url, content, "error", Message(), None)
        return content

    return fakeRetriever


def test_readRemoteMPFSource(monkeypatch, tmp_path):
    requested = []
    retriever = _rawFiles(
        {
            "_version.py": b"__version__ = '0.82.0.dev0'\n__gmc_version__ = '1.0.0'\n",
            "pyproject.toml": b'[project]\nrequires-python = ">=3.10"\n',
        }
    )
    monkeypatch.setattr(
        sourceManager.compatibilityManager, "urlRetriever", lambda url, *args: requested.append(url) or retriever(url)
    )
    source = sourceManager.readRemoteMPFSource("dev", tmp_path / "mpf-dev")
    assert source == sourceManager.LocalMPFSource(tmp_path / "mpf-dev", "0.82.0.dev0", ">=3.10", "1.0.0")
    assert requested[0] == "https://raw.githubusercontent.com/missionpinball/mpf/dev/mpf/_version.py"


def test_readRemoteMPFSourceWithoutPyproject(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sourceManager.compatibilityManager,
        "urlRetriever",
        _rawFiles({"_version.py": b"__version__ = '0.57.6'\n", "pyproject.toml": 404}),
    )
    source = sourceManager.readRemoteMPFSource("0.57.x", tmp_path)
    assert source.mpfVersion == "0.57.6"
    assert source.requiredPythonVersion is None
    assert source.gmcVersion is None


def test_readRemoteMPFSourceReraisesOtherErrors(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sourceManager.compatibilityManager,
        "urlRetriever",
        _rawFiles({"_version.py": b"__version__ = '0.82.0'\n", "pyproject.toml": 500}),
    )
    with pytest.raises(urllib.error.HTTPError):
        sourceManager.readRemoteMPFSource("dev", tmp_path)


def test_managedSourcePath(tmp_path):
    assert sourceManager.managedSourcePath(tmp_path, "0.82.x") == tmp_path / "mpf-sources" / "mpf-0.82.x"
    assert sourceManager.managedSourcePath(tmp_path, "a/b c") == tmp_path / "mpf-sources" / "mpf-a_b_c"


def test_sourceCommandsClonesNewFolder(monkeypatch, tmp_path):
    monkeypatch.setattr(sourceManager.shutil, "which", lambda _name: "git")
    assert sourceManager.sourceCommands(tmp_path / "mpf-dev", "dev") == [
        ["git", "clone", "--branch", "dev", sourceManager.MPF_GIT_URL, str(tmp_path / "mpf-dev")]
    ]
    (tmp_path / "empty").mkdir()
    assert sourceManager.sourceCommands(tmp_path / "empty", "dev")[0][1] == "clone"


def test_sourceCommandsUpdatesExistingCheckout(monkeypatch, tmp_path):
    monkeypatch.setattr(sourceManager.shutil, "which", lambda _name: "git")
    source = _fakeSource(tmp_path / "mpf-dev")
    assert sourceManager.sourceCommands(source, "dev") == [
        ["git", "-C", str(source), "pull", "--ff-only", "origin", "dev"]
    ]


def test_sourceCommandsRefusesOtherFolders(monkeypatch, tmp_path):
    monkeypatch.setattr(sourceManager.shutil, "which", lambda _name: "git")
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "file.txt").write_text("x")
    with pytest.raises(FileExistsError):
        sourceManager.sourceCommands(tmp_path / "other", "dev")


def test_isMPFSourceAcceptsSetupPy(tmp_path):
    (tmp_path / "mpf").mkdir()
    (tmp_path / "mpf" / "_version.py").write_text("__version__ = '0.50.0'\n")
    assert not sourceManager.isMPFSource(tmp_path)
    (tmp_path / "setup.py").write_text("")
    assert sourceManager.isMPFSource(tmp_path)
    assert sourceManager.readLocalMPFSource(tmp_path).requiredPythonVersion is None
