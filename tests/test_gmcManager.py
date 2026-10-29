import io
import subprocess
import zipfile
from pathlib import Path

import pytest

from mpfmanager.core import gmcManager
from mpfmanager.core.storageManager import VirtualEnvironment


def _fakeAddon(tmp_path: Path) -> Path:
    addon = tmp_path / "source" / "addons" / "mpf-gmc"
    (addon / "slides").mkdir(parents=True)
    (addon / "plugin.cfg").write_text('[plugin]\nversion="1.0.0"\n')
    (addon / "slides" / "window.tscn").write_text("[gd_scene]\n")
    return addon


def _archive(members: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def test_createGMCProjectWritesConfiguredProject(tmp_path):
    machine = tmp_path / "machine"
    gmcManager.createGMCProject(machine, 'My "Pin"', _fakeAddon(tmp_path), "4.4", Path("/envs/a/bin/mpf"))

    projectText = (machine / "project.godot").read_text()
    assert 'MPF="*res://addons/mpf-gmc/mpf_gmc.gd"' in projectText
    assert 'enabled=PackedStringArray("res://addons/mpf-gmc/plugin.cfg")' in projectText
    assert 'run/main_scene="res://addons/mpf-gmc/slides/window.tscn"' in projectText
    assert 'config/features=PackedStringArray("4.4")' in projectText
    assert 'config/name="My \\"Pin\\""' in projectText
    assert (machine / "addons" / "mpf-gmc" / "slides" / "window.tscn").is_file()
    assert 'executable_path="/envs/a/bin/mpf"' in (machine / "gmc.cfg").read_text()
    assert ".godot/" in (machine / ".gitignore").read_text()
    assert (machine / "slides").is_dir() and (machine / "widgets").is_dir()


def test_createGMCProjectKeepsExistingGitignore(tmp_path):
    machine = tmp_path / "machine"
    machine.mkdir()
    (machine / ".gitignore").write_text("*.log\n")
    gmcManager.createGMCProject(machine, "x", _fakeAddon(tmp_path))
    gitignoreText = (machine / ".gitignore").read_text()
    assert gitignoreText.startswith("*.log\n")
    assert ".godot/" in gitignoreText
    assert ";executable_path=" in (machine / "gmc.cfg").read_text()


def test_createGMCProjectRefusesExistingProject(tmp_path):
    machine = tmp_path / "machine"
    machine.mkdir()
    (machine / "project.godot").write_text("")
    with pytest.raises(FileExistsError):
        gmcManager.createGMCProject(machine, "x", _fakeAddon(tmp_path))


def test_fetchGMCAddonExtractsAndCaches(tmp_path, monkeypatch):
    downloads = []
    archiveBytes = _archive(
        {
            "mpf-gmc-1.0.0/README.md": "readme",
            "mpf-gmc-1.0.0/addons/mpf-gmc/plugin.cfg": "[plugin]",
            "mpf-gmc-1.0.0/addons/mpf-gmc/classes/mpf_slide.gd": "extends Node",
        }
    )
    monkeypatch.setattr(
        gmcManager.compatibilityManager, "urlRetriever", lambda url, _timeout=30: downloads.append(url) or archiveBytes
    )

    addon = gmcManager.fetchGMCAddon("1.0.0", tmp_path / "cache")
    assert addon == tmp_path / "cache" / "1.0.0" / "addons" / "mpf-gmc"
    assert (addon / "classes" / "mpf_slide.gd").is_file()
    assert not (tmp_path / "cache" / "1.0.0" / "README.md").exists()
    assert downloads == ["https://github.com/missionpinball/mpf-gmc/archive/refs/tags/v1.0.0.zip"]

    # The second call is served from the cache
    assert gmcManager.fetchGMCAddon("1.0.0", tmp_path / "cache") == addon
    assert len(downloads) == 1


def test_fetchGMCAddonRejectsPathTraversal(tmp_path, monkeypatch):
    archiveBytes = _archive({"mpf-gmc-1.0.0/addons/mpf-gmc/../../../../evil.txt": "x"})
    monkeypatch.setattr(gmcManager.compatibilityManager, "urlRetriever", lambda _url, _timeout=30: archiveBytes)
    with pytest.raises(ValueError):
        gmcManager.fetchGMCAddon("1.0.0", tmp_path / "cache")
    assert not (tmp_path / "cache" / "1.0.0").exists()


def test_fetchGMCAddonRequiresPluginCfg(tmp_path, monkeypatch):
    archiveBytes = _archive({"mpf-gmc-1.0.0/addons/mpf-gmc/readme.txt": "x"})
    monkeypatch.setattr(gmcManager.compatibilityManager, "urlRetriever", lambda _url, _timeout=30: archiveBytes)
    with pytest.raises(FileNotFoundError):
        gmcManager.fetchGMCAddon("1.0.0", tmp_path / "cache")
    assert not any((tmp_path / "cache").iterdir())


def test_listGMCVersionsSortsAndSkipsInvalidTags(monkeypatch):
    monkeypatch.setattr(
        gmcManager.compatibilityManager,
        "jsonRetriever",
        lambda _url: [{"name": "v0.1.6"}, {"name": "v1.0.0"}, {"name": "not-a-version"}, {"name": "v0.1.10"}],
    )
    assert gmcManager.listGMCVersions() == ["1.0.0", "0.1.10", "0.1.6"]


@pytest.mark.parametrize(
    ("output", "expected"),
    [("4.4.1.stable.official.49a5bc7b6\n", "4.4"), ("4.3.stable.mono\n", "4.3"), ("garbage", None)],
)
def test_godotVersionParsing(monkeypatch, output, expected):
    monkeypatch.setattr(
        gmcManager.subprocess, "run", lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, stdout=output)
    )
    version = gmcManager.godotVersion("godot")
    assert (str(version) if version else None) == expected


def test_godotVersionMissingExecutable(monkeypatch):
    def missing(*_args, **_kwargs):
        raise FileNotFoundError("godot")

    monkeypatch.setattr(gmcManager.subprocess, "run", missing)
    assert gmcManager.godotVersion("godot") is None


def test_requiredGMCVersion(monkeypatch, tmp_path):
    calls = []

    def fakeRun(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="1.0.0\n")

    monkeypatch.setattr(gmcManager.subprocess, "run", fakeRun)
    environment = VirtualEnvironment("env", str(tmp_path / "env"), "3.13", "0.82.0")
    assert gmcManager.requiredGMCVersion(environment) == "1.0.0"
    assert calls[0][0] == str(environment.executable("python"))


def test_requiredGMCVersionWhenMPFDoesNotSayOne(monkeypatch, tmp_path):
    monkeypatch.setattr(
        gmcManager.subprocess, "run", lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, stdout="\n")
    )
    assert gmcManager.requiredGMCVersion(VirtualEnvironment("env", str(tmp_path), "3.13", "0.80.0")) is None


def test_updateGMCExecutable(tmp_path):
    machine = tmp_path / "machine"
    gmcManager.createGMCProject(machine, "x", _fakeAddon(tmp_path))
    assert gmcManager.updateGMCExecutable(machine, Path("/envs/b/bin/mpf"))
    configText = (machine / "gmc.cfg").read_text()
    assert 'executable_path="/envs/b/bin/mpf"' in configText
    assert configText.count("executable_path") == 1

    assert gmcManager.updateGMCExecutable(machine, None)
    assert ";executable_path=" in (machine / "gmc.cfg").read_text()


def test_updateGMCExecutableAddsMissingLine(tmp_path):
    (tmp_path / "gmc.cfg").write_text("[gmc]\n\nfullscreen=false\n")
    assert gmcManager.updateGMCExecutable(tmp_path, Path("/envs/c/bin/mpf"))
    assert (tmp_path / "gmc.cfg").read_text().endswith('[mpf]\n\nexecutable_path="/envs/c/bin/mpf"\n')
    assert not gmcManager.updateGMCExecutable(tmp_path / "missing", None)


def test_importGMCProjectCommand(tmp_path):
    assert gmcManager.importGMCProject("godot", tmp_path) == [
        "godot",
        "--headless",
        "--path",
        str(tmp_path),
        "--import",
    ]
