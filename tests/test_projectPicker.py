import pytest
from PySide6.QtWidgets import QMessageBox

from mpfmanager.core import compatibilityManager, projectManager, uvManager
from mpfmanager.core.compatibilityManager import PyPIRelease
from mpfmanager.core.storageManager import Project, StorageProcessor
from mpfmanager.ui import projectPicker
from mpfmanager.ui.projectPicker import ProjectPickerDialog


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MPF_MANAGER_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(compatibilityManager, "pypiReleaseRetriever", lambda _package: [PyPIRelease("0.80.0", ">=3.8")])
    monkeypatch.setattr(uvManager, "listPythonVersions", lambda: {"3.13"})


def _store(tmp_path) -> StorageProcessor:
    store = StorageProcessor()
    for name in ("alpha", "beta"):
        projectManager.createNewMPFProject(tmp_path / name)
        store.addProject(Project(name, str(tmp_path / name), "env" if name == "beta" else None))
    return store


def _picker(qtbot, store, createProject=lambda: None, addProject=lambda: None, statuses=None):
    picker = ProjectPickerDialog(
        store, createProject, addProject, lambda project: (statuses or {}).get(project.projectName, "OK")
    )
    qtbot.addWidget(picker)
    return picker


def _column(picker, column: int) -> list[str]:
    return [picker.projectTable.item(row, column).text() for row in range(picker.projectTable.rowCount())]


def test_pickerListsTheProjects(qtbot, tmp_path):
    picker = _picker(qtbot, _store(tmp_path), statuses={"beta": "Missing"})
    assert _column(picker, 0) == ["alpha", "beta"]
    assert _column(picker, 1) == ["(none)", "env"]
    assert _column(picker, 2) == ["OK", "Missing"]
    assert _column(picker, 3) == [str(tmp_path / "alpha"), str(tmp_path / "beta")]
    assert picker.selectedProject().projectName == "alpha" and picker.openButton.isEnabled()
    assert picker.emptyLabel.isHidden()


def test_pickerOpensTheChosenProject(qtbot, tmp_path):
    store = _store(tmp_path)
    picker = _picker(qtbot, store)
    picker.projectTable.selectRow(1)
    picker.openButton.click()
    assert picker.result() == 1 and picker.chosenProject.projectName == "beta"

    # Double clicking a project opens it too
    picker = _picker(qtbot, store)
    picker.projectTable.cellDoubleClicked.emit(0, 0)
    assert picker.chosenProject.projectName == "alpha"

    # Cancelling chooses none
    picker = _picker(qtbot, store)
    picker.reject()
    assert picker.chosenProject is None


def test_pickerMakesAndOpensProjects(qtbot, tmp_path):
    store = _store(tmp_path)
    made = Project("made", str(tmp_path / "made"))
    picker = _picker(qtbot, store, createProject=lambda: made)
    picker.newButton.click()
    assert picker.chosenProject is made and picker.result() == 1

    added = store.projectList[1]
    picker = _picker(qtbot, store, addProject=lambda: added)
    picker.openFolderButton.click()
    assert picker.chosenProject is added

    # A project not made, e.g. a cancelled dialog, keeps the picker open
    picker = _picker(qtbot, store)
    picker.newButton.click()
    picker.openFolderButton.click()
    assert picker.chosenProject is None and picker.result() == 0


def test_pickerRemovesProjectsFromTheList(qtbot, tmp_path, monkeypatch):
    store = _store(tmp_path)
    picker = _picker(qtbot, store, statuses={"alpha": "Running (game)"})
    assert not picker.removeButton.isEnabled()
    picker.projectTable.selectRow(1)
    assert picker.removeButton.isEnabled()
    monkeypatch.setattr(projectPicker.QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.No)
    assert not picker.removeChosen()
    monkeypatch.setattr(projectPicker.QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    assert picker.removeChosen()
    assert _column(picker, 0) == ["alpha"] and [project.projectName for project in store.projectList] == ["alpha"]
    assert (tmp_path / "beta").is_dir()


def test_pickerWithoutProjects(qtbot):
    picker = _picker(qtbot, StorageProcessor())
    assert not picker.emptyLabel.isHidden() and picker.emptyLabel.text() == projectPicker.NO_PROJECTS_TEXT
    assert picker.projectTable.isHidden()
    assert not picker.openButton.isEnabled() and not picker.removeButton.isEnabled()
    assert not picker.removeChosen()
    picker.openChosen()
    assert picker.chosenProject is None
