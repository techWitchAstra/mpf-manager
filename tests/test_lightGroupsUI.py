from PySide6.QtWidgets import QMessageBox
from test_showViewer import _colorAt, _machine, _playbackMachine, _row, _select

from mpfmanager.core import lightGroups
from mpfmanager.ui import showViewer
from mpfmanager.ui.showViewer import ShowViewerWindow


def _window(qtbot, tmp_path) -> ShowViewerWindow:
    window = ShowViewerWindow(_playbackMachine(tmp_path))
    qtbot.addWidget(window)
    window.show()
    window.resolutionOption.setCurrentIndex(window.resolutionOption.findData(0.25))
    return window


def _groupLabels(window) -> list[str]:
    return [window.groupOption.itemText(index) for index in range(window.groupOption.count())]


def test_lightGroupsAreMadeFromChosenLights(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    machinePath = window.machinePath
    # The machine's light tags make groups of their own, which cannot be changed
    assert _groupLabels(window) == ["tag: gi  (2)"]
    assert list(window.ribbon.ribbonTab("Playfield").groups) == ["Layout", "Lights", "Light groups"]
    assert window.chooseGroupAction.isEnabled() and not window.renameGroupAction.isEnabled()
    assert not window.newGroupAction.isEnabled() and not window.newLightGroup("nothing")

    # A group is made of the lights chosen on the playfield, and kept with the machine
    window.playfieldView.selectLights(["l_a"], notify=True)
    assert window.newGroupAction.isEnabled()
    monkeypatch.setattr(showViewer.QInputDialog, "getText", lambda *args, **kwargs: ("left side", True))
    assert window.newLightGroup()
    assert _groupLabels(window) == ["left side  (1)", "tag: gi  (2)"]
    assert window.groupOption.currentData() == "left side"
    assert lightGroups.loadLightGroups(machinePath)[0].lights == ["l_a"]
    assert not window.newLightGroup("left side") and not window.newLightGroup("tag: sneaky")

    # Lights are added to and taken out of a group, and choosing a group chooses its lights and their rows
    window.playfieldView.selectLights(["l_a", "l_b"], notify=True)
    assert window.addChosenToGroup()
    assert window.currentLightGroup().lights == ["l_a", "l_b"]
    window.playfieldView.selectLights(["l_a"], notify=True)
    assert window.removeChosenFromGroup()
    assert window.currentLightGroup().lights == ["l_b"]
    window.playfieldView.selectLights([], notify=True)
    assert window.chooseGroup()
    assert window.playfieldView.chosenLights == ["l_b"]
    assert window.selectedCells()[0] == ["l_b"]
    assert window.statusBar().currentMessage() == "Chose the 1 lights of left side"

    # Groups are renamed and deleted, and are read again with the shows
    assert window.renameLightGroup("right side")
    assert not window.renameLightGroup(" ")
    window.reloadShows()
    assert _groupLabels(window) == ["right side  (1)", "tag: gi  (2)"]
    monkeypatch.setattr(showViewer.QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.No)
    assert not window.deleteLightGroup()
    monkeypatch.setattr(showViewer.QMessageBox, "question", lambda *_args: QMessageBox.StandardButton.Yes)
    assert window.deleteLightGroup()
    assert _groupLabels(window) == ["tag: gi  (2)"] and lightGroups.loadLightGroups(machinePath) == []

    # A tag's group chooses its lights, but cannot be changed
    assert window.chooseGroup()
    assert sorted(window.playfieldView.chosenLights) == ["l_a", "l_b"]
    for change in (
        window.addChosenToGroup,
        window.removeChosenFromGroup,
        window.renameLightGroup,
        window.deleteLightGroup,
    ):
        assert not change()


def test_lightRowsAreTakenOutOfTheShow(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    model = window.timelineModel
    assert window.ribbon.removeLightButton.defaultAction() is window.ribbon.removeLightAction
    assert not window.removeLightRows([]) and "Choose the rows" in window.statusBar().currentMessage()

    # Taking a light out takes it out of every step, and can be undone
    _select(window, _row(model, "l_a"), 0, 1)
    assert window.removeLightRows()
    assert "l_a" not in [row.channel.name for row in model.gridRows]
    assert window.statusBar().currentMessage() == "Took l_a out of the show"
    window.undo()
    assert _colorAt(window, "l_a", 0.1) == (0, 0, 255)

    # A row added to paint a light the show does not set yet is taken away
    assert window.addLightRow("l_new")
    assert window.removeLightRows(["l_new"])
    assert "l_new" not in [row.channel.name for row in model.gridRows]
    assert window.statusBar().currentMessage() == "Took away the rows for l_new"

    # Without a show there is nothing to take out
    empty = ShowViewerWindow(_machine(tmp_path / "other"))
    qtbot.addWidget(empty)
    empty.showList.clearShows(None)
    empty._displaySelectedShow()
    assert not empty.removeLightRows(["l_a"])
