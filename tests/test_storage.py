import pytest

from mpfmanager.core import yamlInterfacer
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
