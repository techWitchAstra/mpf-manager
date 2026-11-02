from PySide6.QtWidgets import QDialog, QDialogButtonBox
from test_audioWaveform import writeTone
from test_showAudio import FakePlayer
from test_showViewer import _machine

from mpfmanager.core import showEditor, showManager
from mpfmanager.ui import showViewer
from mpfmanager.ui.showTools import AddSoundDialog, NewShowDialog, RemoveSoundDialog
from mpfmanager.ui.showViewer import ShowViewerWindow


def _window(qtbot, tmp_path) -> ShowViewerWindow:
    machinePath = _machine(tmp_path)
    writeTone(machinePath / "sounds" / "boom.wav", 0.5)
    window = ShowViewerWindow(machinePath)
    qtbot.addWidget(window)
    return window


def test_newShowDialogChecksTheName(qtbot, tmp_path):
    (tmp_path / "taken_file.yaml").write_text("")
    dialog = NewShowDialog(tmp_path, {"taken"}, "fresh")
    qtbot.addWidget(dialog)
    okButton = dialog.buttons.button(QDialogButtonBox.StandardButton.Ok)
    assert okButton.isEnabled() and dialog.showFile == tmp_path / "fresh.yaml" and dialog.length == 2.0
    for name, problem in [
        ("bad name", "letters, numbers"),
        ("taken", "already a show called taken"),
        ("taken_file", "already exists"),
    ]:
        dialog.nameEdit.setText(name)
        assert problem in dialog.problemLabel.text() and not okButton.isEnabled()
    dialog.nameEdit.setText("fine")
    dialog.folderEdit.setText("")
    assert "Choose a folder" in dialog.problemLabel.text()


def test_newBlankShow(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    machinePath = window.machinePath
    assert window.ribbon.newShowButton.defaultAction() is window.ribbon.newShowAction
    file_menu = window.pageMenus[0]
    assert file_menu.actions()[0] is window.ribbon.newShowAction

    # The dialog suggests a name not in use, in the folder chosen in the show files, or the shows folder
    seen = {}

    def accept(dialog):
        seen["folder"], seen["name"] = dialog.folderEdit.text(), dialog.showName
        dialog.nameEdit.setText("intro")
        dialog.lengthSpin.setValue(3.0)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(NewShowDialog, "exec", accept)
    window.showList.setCurrentItem(None)
    assert window.openNewShowDialog()
    assert seen == {"folder": str(machinePath / "shows"), "name": "new_show_1"}
    showFile = machinePath / "shows" / "intro.yaml"
    assert showFile.is_file() and showManager.loadShowFile(showFile)[0].totalDuration == 3.0
    assert window.selectedShow().name == "intro" and window.library["intro"] is window.selectedShow()
    assert [item.text(0) for item in window.showList.showItemsOfFile(showFile)] == ["intro"]
    assert window.statusBar().currentMessage().startswith("Made the show intro")

    # A show made outside a shows folder is listed, with a word that MPF will not play it from there
    assert window.newShow("elsewhere", machinePath / "sounds", 1.0)
    assert "move it there to play it" in window.statusBar().currentMessage()
    assert window.selectedShow().name == "elsewhere"
    window.reloadShows()
    assert "elsewhere" in [item.text(0) for item in window.showList.showItems()]

    # A show name or file in use is refused, and a cancelled dialog makes nothing
    warnings = []
    monkeypatch.setattr(showViewer.QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    assert not window.newShow("intro", machinePath / "shows")
    assert warnings
    monkeypatch.setattr(NewShowDialog, "exec", lambda _dialog: QDialog.DialogCode.Rejected)
    assert not window.openNewShowDialog()


def test_addingAndRemovingSounds(qtbot, tmp_path, monkeypatch):
    window = _window(qtbot, tmp_path)
    window.setPlayTime(0.5)
    seen = {}

    def accept(dialog):
        seen["sounds"] = [dialog.soundOption.itemText(index) for index in range(dialog.soundOption.count())]
        seen["at"] = dialog.atTime
        dialog.volumeSpin.setValue(70)
        dialog.loopsSpin.setValue(1)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(AddSoundDialog, "exec", accept)
    assert window.openAddSoundDialog()
    assert seen == {"sounds": ["boom"], "at": 0.5}
    show = window.selectedShow()
    assert showManager.stepToData(next(step for step in show.steps if step.sounds))["sounds"] == {
        "boom": {"action": "play", "volume": 0.7, "loops": 1}
    }
    assert window.timelineModel.audioRowCount == 1 and window.hasUnsavedChanges()

    # A sound with no file of its name is added, with a word that it was not found
    assert window.addSound("missing", 0.0)
    assert "no sound file of that name" in window.statusBar().currentMessage()

    # Sounds are taken out from a list of the show's sounds
    def remove(dialog):
        seen["entries"] = [dialog.entryOption.itemText(index) for index in range(dialog.entryOption.count())]
        dialog.entryOption.setCurrentIndex(1)
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(RemoveSoundDialog, "exec", remove)
    assert window.openRemoveSoundDialog()
    assert seen["entries"] == ["missing  at 0s", "boom  at 0.5s"]
    assert [name for _time, name in showEditor.soundEntries(show)] == ["missing"]
    window.undo()
    assert len(window.timelineModel.show.soundPlays) == 2


def test_soundsNeedAShowAndSoundsToRemove(qtbot, tmp_path):
    window = ShowViewerWindow()
    qtbot.addWidget(window)
    assert not window.openAddSoundDialog()
    assert window.statusBar().currentMessage() == "Choose a show to add a sound to"
    assert not window.openRemoveSoundDialog()
    assert window.statusBar().currentMessage() == "The show does not play any sounds of its own"
    dialog = AddSoundDialog([], 1.0)
    qtbot.addWidget(dialog)
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()


def test_soundsAreHeardWhileTheShowPlays(qtbot, tmp_path):
    window = _window(qtbot, tmp_path)
    players: list[FakePlayer] = []
    window.showAudio.playerFactory = lambda: players.append(FakePlayer()) or players[-1]
    window.addSound("boom", 0.0)
    assert window.addSoundAction in window.pageMenus[3].actions()
    assert list(window.ribbon.ribbonTab("Playback").groups) == ["Transport", "Options", "Audio"]

    # Playing the show plays its sounds, at the volume chosen, and pausing stops them
    window.volumeSlider.setValue(50)
    window.setPlayTime(0.0)
    window.togglePlayback()
    assert players and players[0].playing and players[0].volume == 0.5
    window.togglePlayback()
    assert not players[0].playing

    # Sounds can be turned off
    window.hearSoundsAction.setChecked(False)
    window.togglePlayback()
    assert not players[0].playing
    window.pausePlayback()
    window.hearSoundsAction.setChecked(True)

    # Choosing another show forgets its players
    sample = window.showList.currentShowItem()
    assert window.newShow("other", window.machinePath / "shows")
    window.showList.selectShowItem(sample)
    assert window.showAudio.players == {}
