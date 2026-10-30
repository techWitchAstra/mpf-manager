import os
from pathlib import Path

import pytest

from mpfmanager.core import projectManager
from mpfmanager.core.storageManager import VirtualEnvironment


def _environment(tmp_path: Path, mpfVersion: str = "0.80.0") -> VirtualEnvironment:
    return VirtualEnvironment("env", str(tmp_path / "env"), "3.13", mpfVersion)


def test_newProjectHasConfigVersion(tmp_path):
    machine = projectManager.createNewMPFProject(tmp_path / "machine")
    assert projectManager.mainConfigPath(machine) == machine / "config" / "config.yaml"
    assert projectManager.checkMPFProjectAtPath(machine)
    assert projectManager.checkConfigVersion(machine) == projectManager.CONFIG_VERSION
    assert (machine / "modes").is_dir() and (machine / "shows").is_dir()
    assert "Main machine config for machine." in projectManager.mainConfigPath(machine).read_text()


def test_newProjectUsesGivenName(tmp_path):
    machine = projectManager.createNewMPFProject(tmp_path / "folder", "My Pin")
    assert "Main machine config for My Pin." in projectManager.mainConfigPath(machine).read_text()


def test_newProjectAllowsEmptyFolderButNotFullOne(tmp_path):
    (tmp_path / "empty").mkdir()
    projectManager.createNewMPFProject(tmp_path / "empty")
    (tmp_path / "full").mkdir()
    (tmp_path / "full" / "x.txt").write_text("x")
    with pytest.raises(FileExistsError):
        projectManager.createNewMPFProject(tmp_path / "full")


def test_checkConfigVersionWithoutConfigOrHeader(tmp_path):
    assert not projectManager.checkMPFProjectAtPath(tmp_path)
    assert projectManager.checkConfigVersion(tmp_path) is None
    (tmp_path / "config").mkdir()
    projectManager.mainConfigPath(tmp_path).write_text("hardware: {}\n")
    assert projectManager.checkConfigVersion(tmp_path) is None


@pytest.mark.parametrize(
    ("mpfVersion", "eligible"),
    [("", False), ("not-a-version", False), ("0.57.3", False), ("0.80.0.dev5", True), ("0.82.0", True)],
)
def test_isGMCEligible(tmp_path, mpfVersion, eligible):
    assert projectManager.isGMCEligible(_environment(tmp_path, mpfVersion)) is eligible


def test_isGMCEligibleWithoutEnvironment():
    assert not projectManager.isGMCEligible(None)


def test_findGodotProject(tmp_path):
    assert projectManager.findGodotProject(tmp_path / "missing") is None
    assert projectManager.findGodotProject(tmp_path) is None
    (tmp_path / "b-gmc").mkdir()
    (tmp_path / "b-gmc" / "project.godot").write_text("")
    (tmp_path / "a-other").mkdir()
    assert projectManager.findGodotProject(tmp_path) == tmp_path / "b-gmc"
    (tmp_path / "project.godot").write_text("")
    assert projectManager.findGodotProject(tmp_path) == tmp_path


def test_detectGodotExecutableFromPath(monkeypatch):
    monkeypatch.setattr(projectManager.shutil, "which", lambda name: "/usr/bin/godot4" if name == "godot4" else None)
    assert projectManager.detectGodotExecutable() == "/usr/bin/godot4"


def test_detectGodotExecutableOnMacOS(monkeypatch, tmp_path):
    macGodot = tmp_path / "Godot"
    macGodot.write_text("")
    monkeypatch.setattr(projectManager.shutil, "which", lambda _name: None)
    monkeypatch.setattr(projectManager.sys, "platform", "darwin")
    monkeypatch.setattr(projectManager, "GODOT_MACOS_APP_PATH", macGodot)
    assert projectManager.detectGodotExecutable() == str(macGodot)


def test_detectGodotExecutableNotFound(monkeypatch):
    monkeypatch.setattr(projectManager.shutil, "which", lambda _name: None)
    monkeypatch.setattr(projectManager.sys, "platform", "linux")
    assert projectManager.detectGodotExecutable() is None


def test_checkGodotExecutable(tmp_path):
    godot = tmp_path / "godot"
    assert not projectManager.checkGodotExecutable("")
    assert not projectManager.checkGodotExecutable(str(godot))
    godot.write_text("")
    godot.chmod(0o755)
    assert projectManager.checkGodotExecutable(str(godot)) is os.access(godot, os.X_OK)


def test_runMPFGameAddsTextUIAndHardwareFlags(tmp_path):
    environment = _environment(tmp_path)
    assert projectManager.runMPF(environment, "game", ["-X"], ["-v"]) == [
        str(environment.executable("mpf")),
        "game",
        "-t",
        "-X",
        "-v",
    ]


def test_runMPFGMCModeRunsTheGame(tmp_path):
    assert projectManager.runMPF(_environment(tmp_path), "gmc", [], [])[1:] == ["game", "-t"]


def test_runMPFMediaControllerHasNoTextUI(tmp_path):
    assert projectManager.runMPF(_environment(tmp_path), "mc", ["-X"], [])[1:] == ["mc"]


def test_runGMC(tmp_path):
    assert projectManager.runGMC("godot", tmp_path) == ["godot", "--path", str(tmp_path)]
    assert projectManager.runGMC("godot", tmp_path, openEditor=True)[-1] == "-e"


def test_runMPFWithMonitor(tmp_path):
    environment = _environment(tmp_path)
    commands = projectManager.runMPFWithMonitor(environment, "game", [], [], True)
    assert len(commands) == 2
    assert commands[1][1] == "monitor"
    assert len(projectManager.runMPFWithMonitor(environment, "game", [], [], False)) == 1
    assert len(projectManager.runMPFWithMonitor(environment, "mc", [], [], True)) == 1
