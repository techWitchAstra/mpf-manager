import pytest

from mpfmanager.core import storageManager, yamlInterfacer
from mpfmanager.core.storageManager import Project, StorageProcessor, VirtualEnvironment


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MPF_MANAGER_HOME", str(tmp_path / "home"))


def test_gmcFolderPathSurvivesSaveAndLoad(tmp_path):
    store = StorageProcessor()
    store.addProject(Project("machine", str(tmp_path / "machine")))
    store.setProjectGMCPath(str(tmp_path / "machine"), str(tmp_path / "machine" / "gmc"))

    reloaded = StorageProcessor()
    project = reloaded.getProjectbyPath(str(tmp_path / "machine"))
    assert project is not None
    assert project.gmcFolderPath == str(tmp_path / "machine" / "gmc")


def test_legacyGMCPathKeyStillLoads(tmp_path):
    store = StorageProcessor()
    yamlInterfacer.writeYAML(
        {"projectList": [{"projectName": "old", "projectPath": str(tmp_path), "gmcPath": "/old/gmc"}]},
        store.savePath,
    )
    project = StorageProcessor().getProjectbyPath(str(tmp_path))
    assert project is not None
    assert project.gmcFolderPath == "/old/gmc"


def test_environmentWithoutEditableKeyLoads(tmp_path):
    store = StorageProcessor()
    yamlInterfacer.writeYAML(
        {
            "environmentList": [
                {"venvName": "env", "pathToVENV": str(tmp_path / "env"), "installedMPFVersion": "0.80.0"}
            ]
        },
        store.savePath,
    )
    environment = StorageProcessor().getVENVbyName("env")
    assert environment is not None
    assert environment.editableMPFPath == ""
    assert not environment.isEditable


def test_editableMPFPathSurvivesSaveAndLoad(tmp_path):
    store = StorageProcessor()
    store.addVENV(VirtualEnvironment("env", str(tmp_path / "env"), "3.13", "0.82.0.dev0", [], str(tmp_path / "src")))
    environment = StorageProcessor().getVENVbyName("env")
    assert environment is not None
    assert environment.isEditable
    assert environment.editableMPFPath == str(tmp_path / "src")


def test_defaultHomeUsesEnvironmentVariable(tmp_path):
    assert storageManager.default_home() == tmp_path / "home"


@pytest.mark.skipif(storageManager.os.name == "nt", reason="XDG_CONFIG_HOME is only used outside of Windows")
def test_defaultHomeUsesXDGConfigHome(tmp_path, monkeypatch):
    monkeypatch.delenv("MPF_MANAGER_HOME")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    assert storageManager.default_home() == tmp_path / "xdg" / "mpfmanager"


def test_duplicatesAreRefused(tmp_path):
    store = StorageProcessor()
    store.addVENV(VirtualEnvironment("env", str(tmp_path / "env"), "3.13", "0.80.0"))
    with pytest.raises(ValueError):
        store.addVENV(VirtualEnvironment("env", str(tmp_path / "other"), "3.13", "0.80.0"))
    store.addProject(Project("machine", str(tmp_path / "machine")))
    with pytest.raises(ValueError):
        store.addProject(Project("again", str(tmp_path / "machine")))


def test_removingEnvironmentClearsProjects(tmp_path):
    store = StorageProcessor()
    store.addVENV(VirtualEnvironment("env", str(tmp_path / "env"), "3.13", "0.80.0"))
    store.addProject(Project("machine", str(tmp_path / "machine"), "env"))
    store.removeVENV("env")
    project = StorageProcessor().getProjectbyPath(str(tmp_path / "machine"))
    assert project is not None and project.virtualEnvironment is None
    assert store.getVENVbyName("env") is None


def test_projectEnvironmentAndRemoval(tmp_path):
    store = StorageProcessor()
    store.addProject(Project("machine", str(tmp_path / "machine")))
    store.setProjectVENV(str(tmp_path / "machine"), "env")
    project = StorageProcessor().getProjectbyPath(str(tmp_path / "machine"))
    assert project is not None and project.virtualEnvironment == "env"
    store.setProjectVENV(str(tmp_path / "unknown"), "env")
    store.removeProject(str(tmp_path / "machine"))
    assert StorageProcessor().projectList == []


def test_settingsSurviveSaveAndLoad(tmp_path):
    store = StorageProcessor()
    store.settings.godotExecutablePath = "/usr/bin/godot"
    store.settings.includePreReleases = True
    store.saveConfiguration()
    reloaded = StorageProcessor()
    assert reloaded.settings.godotExecutablePath == "/usr/bin/godot"
    assert reloaded.settings.includePreReleases


def test_virtualEnvironmentPaths(tmp_path):
    environment = VirtualEnvironment("env", str(tmp_path / "env"), "3.13", "0.80.0")
    assert not environment.exists
    (tmp_path / "env").mkdir()
    (tmp_path / "env" / "pyvenv.cfg").write_text("")
    assert environment.exists
    if storageManager.os.name == "nt":
        assert environment.executable("mpf") == tmp_path / "env" / "Scripts" / "mpf.exe"
    else:
        assert environment.executable("mpf") == tmp_path / "env" / "bin" / "mpf"
