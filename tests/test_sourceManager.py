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
