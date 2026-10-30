import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from mpfmanager.core import uvManager


def _fakeUVModule(monkeypatch, findUVBin):
    monkeypatch.setitem(sys.modules, "uv", types.SimpleNamespace(find_uv_bin=findUVBin))


def test_locateUVUsesBundledCopyWhenFrozen(monkeypatch, tmp_path):
    bundledUV = tmp_path / ("uv.exe" if uvManager.os.name == "nt" else "uv")
    bundledUV.write_text("")
    monkeypatch.setattr(uvManager.sys, "frozen", True, raising=False)
    monkeypatch.setattr(uvManager.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert uvManager.locateUV() == str(bundledUV)


def test_locateUVUsesUVPackage(monkeypatch):
    _fakeUVModule(monkeypatch, lambda: "/site-packages/uv/bin/uv")
    assert uvManager.locateUV() == "/site-packages/uv/bin/uv"


def test_locateUVFallsBackToPath(monkeypatch):
    def missing():
        raise FileNotFoundError

    _fakeUVModule(monkeypatch, missing)
    monkeypatch.setattr(uvManager.shutil, "which", lambda _name: "/usr/local/bin/uv")
    assert uvManager.locateUV() == "/usr/local/bin/uv"


def test_locateUVWithoutUVPackage(monkeypatch):
    monkeypatch.setitem(sys.modules, "uv", None)  # makes "from uv import ..." raise ImportError
    monkeypatch.setattr(uvManager.shutil, "which", lambda _name: "/usr/local/bin/uv")
    assert uvManager.locateUV() == "/usr/local/bin/uv"


def test_locateUVNotFound(monkeypatch):
    monkeypatch.setitem(sys.modules, "uv", None)
    monkeypatch.setattr(uvManager.shutil, "which", lambda _name: None)
    with pytest.raises(uvManager.UvNotFoundError):
        uvManager.locateUV()


def test_commandBuilders(monkeypatch, tmp_path):
    monkeypatch.setattr(uvManager, "locateUV", lambda: "uv")
    assert uvManager.setupVENV(tmp_path, "3.13") == ["uv", "venv", "--python", "3.13", str(tmp_path)]
    assert uvManager.uninstallVENVPackages(tmp_path, ["mpf-mc"]) == [
        "uv",
        "pip",
        "uninstall",
        "--python",
        str(tmp_path),
        "mpf-mc",
    ]


def _fakeRun(monkeypatch, stdout: str):
    calls = []

    def fakeRun(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout=stdout)

    monkeypatch.setattr(uvManager, "locateUV", lambda: "uv")
    monkeypatch.setattr(uvManager.subprocess, "run", fakeRun)
    return calls


def test_listVENVPackagesNormalisesNames(monkeypatch):
    calls = _fakeRun(
        monkeypatch, json.dumps([{"name": "MPF", "version": "0.80.0"}, {"name": "mpf_monitor", "version": "1.0.0"}])
    )
    assert uvManager.listVENVPackages(Path("/venv")) == {"mpf": "0.80.0", "mpf-monitor": "1.0.0"}
    assert calls[0][-2:] == ["--format", "json"]


def test_listVENVPackagesEmptyOutput(monkeypatch):
    _fakeRun(monkeypatch, "")
    assert uvManager.listVENVPackages(Path("/venv")) == {}


def test_listPythonVersions(monkeypatch):
    _fakeRun(
        monkeypatch,
        json.dumps([{"version": "3.13.2"}, {"version": "3.13.1"}, {"version": "3.10.16"}, {"version": "3"}, {}]),
    )
    assert uvManager.listPythonVersions() == {"3.13", "3.10"}
