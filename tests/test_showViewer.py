from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QItemSelection, QItemSelectionModel, QPoint, QPointF, Qt
from PySide6.QtGui import QColor, QKeySequence, QMouseEvent
from PySide6.QtWidgets import QAbstractItemView, QApplication, QDialog, QTabBar
from test_audioWaveform import writeTone
from test_playfieldView import writePlayfieldImage

from mpfmanager.core import showEditor, showManager
from mpfmanager.core.storageManager import Project, StorageProcessor
from mpfmanager.ui import managerTabs, showViewer
from mpfmanager.ui.mainWindow import MainWindow
from mpfmanager.ui.showTools import TOOL_ERASE, TOOL_PAINT, TOOL_PICK, TOOL_SELECT
from mpfmanager.ui.showViewer import ShowTimelineModel, ShowViewerWindow

SHOW_FILE = """\
#show_version=6
- duration: 500ms
  lights:
    l_a: red
    (leds): (color)
- duration: 500ms
  lights:
    l_a: off
    l_b: on-f500ms
    l_c: nope
  events: done
- duration: -1
  lights:
    l_b: stop
"""


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MPF_MANAGER_HOME", str(tmp_path / "home"))


def _showLabels(window: ShowViewerWindow) -> list[str]:
    return [item.text(0) for item in window.showList.showItems()]


def _machine(tmp_path: Path) -> Path:
    (tmp_path / "machine" / "shows").mkdir(parents=True)
    (tmp_path / "machine" / "shows" / "sample.yaml").write_text(SHOW_FILE)
    return tmp_path / "machine"


def _model(tmp_path: Path, resolution: float | None = None) -> ShowTimelineModel:
    model = ShowTimelineModel()
    model.setShow(showManager.loadShowFile(_machine(tmp_path) / "shows" / "sample.yaml")[0], resolution)
    return model


def _cell(model: ShowTimelineModel, row: int, column: int, role=Qt.ItemDataRole.DisplayRole):
    return model.data(model.index(row, column), role)


def test_modelLaysOutChannelsAgainstTime(tmp_path):
    model = _model(tmp_path)
    assert model.resolution == 0.1
    assert (model.rowCount(), model.columnCount()) == (4, 20)

    # The channel column names each light or token
    assert [model.headerData(row, Qt.Orientation.Vertical) for row in range(4)] == [
        "l_a  [light]",
        "(leds)  [token]",
        "l_b  [light]",
        "l_c  [light]",
    ]
    assert model.headerData(1, Qt.Orientation.Vertical, Qt.ItemDataRole.FontRole).italic()
    assert model.headerData(1, Qt.Orientation.Vertical, Qt.ItemDataRole.ForegroundRole) is not None
    assert "Show token" in model.headerData(1, Qt.Orientation.Vertical, Qt.ItemDataRole.ToolTipRole)
    assert "Light" in model.headerData(0, Qt.Orientation.Vertical, Qt.ItemDataRole.ToolTipRole)
    assert model.headerData(0, Qt.Orientation.Vertical, Qt.ItemDataRole.FontRole) is None
    assert model.headerData(9, Qt.Orientation.Vertical) is None

    # Time columns are labelled where steps start
    assert [model.headerData(column, Qt.Orientation.Horizontal) for column in (0, 1, 5, 10)] == ["0s", "", "0.5s", "1s"]
    assert "Also plays: events" in model.headerData(5, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
    assert "holds until advanced" in model.headerData(10, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
    assert model.headerData(3, Qt.Orientation.Horizontal, Qt.ItemDataRole.FontRole) is None


def test_modelColorsCells(tmp_path):
    model = _model(tmp_path)
    background = Qt.ItemDataRole.BackgroundRole

    # Defined colors are shown in the cell, including the blend of a fade
    assert _cell(model, 0, 0, background).color().name() == "#ff0000"
    assert _cell(model, 0, 0) is None
    assert _cell(model, 0, 0, Qt.ItemDataRole.ForegroundRole).name() == "#ffffff"
    assert _cell(model, 0, 6, background).color().name() == "#000000"
    assert _cell(model, 2, 7, background).color().name() == "#666666"
    assert _cell(model, 2, 9, Qt.ItemDataRole.ForegroundRole).name() == "#000000"
    assert "(fading)" in _cell(model, 2, 7, Qt.ItemDataRole.ToolTipRole)
    assert "Color: #ff0000" in _cell(model, 0, 0, Qt.ItemDataRole.ToolTipRole)

    # Color tokens without a value are drawn in the preview color and marked as a preview
    assert _cell(model, 1, 0) is None
    assert _cell(model, 1, 0, background).color().name() == "#ffffff"
    assert _cell(model, 1, 0, showViewer.PREVIEW_ROLE) is True
    assert _cell(model, 0, 0, showViewer.PREVIEW_ROLE) is False
    assert "Preview color: #ffffff" in _cell(model, 1, 0, Qt.ItemDataRole.ToolTipRole)

    # Without the preview, tokens, stop and invalid colors have no color, so their value is written where they start
    model.show.buildTimeline(previewRGB=None)
    model.setShow(model.show)
    assert _cell(model, 1, 0) == "(color)"
    assert _cell(model, 1, 1) is None
    assert _cell(model, 1, 0, background) is showViewer.TOKEN_CELL_BRUSH
    assert "Show token" in _cell(model, 1, 0, Qt.ItemDataRole.ToolTipRole)
    assert _cell(model, 2, 10) == "stop"
    assert _cell(model, 2, 10, background) is showViewer.STOP_CELL_BRUSH
    assert "Removes" in _cell(model, 2, 10, Qt.ItemDataRole.ToolTipRole)
    assert _cell(model, 3, 5) == "nope"
    assert _cell(model, 3, 5, background) is showViewer.INVALID_CELL_BRUSH
    assert "Not a color" in _cell(model, 3, 5, Qt.ItemDataRole.ToolTipRole)
    assert _cell(model, 3, 5, Qt.ItemDataRole.ForegroundRole) is None

    # Cells before a channel is first set are dotted rather than white or black
    assert _cell(model, 2, 0, background) is showViewer.UNSET_CELL_BRUSH
    assert "Not set" in _cell(model, 2, 0, Qt.ItemDataRole.ToolTipRole)
    assert _cell(model, 2, 0) is None
    assert _cell(model, 0, 0, Qt.ItemDataRole.SizeHintRole) is None


def test_modelResolutionAndEmpty(tmp_path, monkeypatch):
    model = _model(tmp_path, 0.5)
    assert model.columnCount() == 4
    monkeypatch.setattr(showViewer, "MAX_GRID_COLUMNS", 10)
    model.setShow(model.show, 0.01)
    assert model.columnCount() == 10

    model.setShow(None)
    assert (model.rowCount(), model.columnCount()) == (0, 0)
    assert model.data(model.index(0, 0)) is None
    assert model.headerData(0, Qt.Orientation.Horizontal) is None


def test_viewerListsProjectShows(qtbot, tmp_path):
    machinePath = _machine(tmp_path)
    (machinePath / "modes" / "attract" / "shows").mkdir(parents=True)
    (machinePath / "modes" / "attract" / "shows" / "bad.yaml").write_text("a: 1\n")
    window = ShowViewerWindow(machinePath)
    qtbot.addWidget(window)
    # Folders are listed by name, and the machine's own first show is chosen
    assert _showLabels(window) == ["bad ⚠", "sample ⚠"]
    assert window.selectedShow().name == "sample"
    assert window.timelineModel.rowCount() == 4
    assert "3 steps" in window.showSummary.text()
    assert "Show tokens: (leds), (color)" in window.showSummary.text()
    assert "Problems" in window.showSummary.text()
    assert "machine" in window.windowTitle()

    # Changing the resolution and zoom redraws the grid
    window.resolutionOption.setCurrentIndex(window.resolutionOption.findData(0.5))
    assert window.timelineModel.columnCount() == 4
    window.zoomSlider.setValue(40)
    assert window.timelineView.horizontalHeader().defaultSectionSize() == 40

    # Reloading keeps the chosen show selected
    window.showList.selectShowItem(window.showList.showItems()[0])
    window.reloadShows()
    assert window.selectedShow().name == "bad"


def test_viewerOpensShowFiles(qtbot, tmp_path, monkeypatch):
    window = ShowViewerWindow()
    qtbot.addWidget(window)
    assert window.selectedShow() is None
    assert "Open a show file" in window.showSummary.text()

    showFile = _machine(tmp_path) / "shows" / "sample.yaml"
    configFile = tmp_path / "config.yaml"
    configFile.write_text("shows:\n  flash:\n    - lights:\n        l_a: red\n")
    monkeypatch.setattr(showViewer.QFileDialog, "getOpenFileName", lambda *args: (str(showFile), ""))
    window.openShowButton.click()
    monkeypatch.setattr(showViewer.QFileDialog, "getOpenFileName", lambda *args: (str(configFile), ""))
    window.browseShowFile()
    window.openShowFile(configFile)
    assert _showLabels(window) == ["sample ⚠", "flash"]
    assert window.selectedShow().name == "flash"

    monkeypatch.setattr(showViewer.QFileDialog, "getOpenFileName", lambda *args: ("", ""))
    window.browseShowFile()
    assert len(window.showList.showItems()) == 2


def test_viewerWithoutShows(qtbot, tmp_path):
    window = ShowViewerWindow(tmp_path)
    qtbot.addWidget(window)
    assert "No show files" in window.showSummary.text()


def test_mainWindowOpensShowViewer(qtbot, tmp_path):
    store = StorageProcessor()
    store.addProject(Project("machine", str(_machine(tmp_path))))
    otherMachine = tmp_path / "other"
    otherMachine.mkdir()
    store.addProject(Project("other", str(otherMachine)))
    window = MainWindow(store)
    qtbot.addWidget(window)
    assert not window.viewShowsButton.isEnabled()

    window.openShowViewer()
    viewer = window.showViewerWindow
    assert viewer is not None and viewer.isVisible() and viewer.machinePath is None

    window.openProject(window.storedData.projectList[0])
    assert window.viewShowsButton.isEnabled()
    window.viewShowsButton.click()
    assert window.showViewerWindow is viewer
    assert viewer.machinePath == Path(window.selectedProject().projectPath)
    assert len(viewer.showList.showItems()) == 1

    window.openProject(window.storedData.projectList[1])
    window.openShowViewer()
    assert viewer.machinePath == otherMachine

    # The Project Manager tab on the viewer's left edge switches back to the main window
    viewer.managerTabs.tabBarClicked.emit(managerTabs.PROJECT_MANAGER_TAB)
    assert not viewer.isVisible() and window.isVisible()
    window.openShowViewer()
    assert viewer.isVisible()
    assert len(viewer.showList.showItems()) == 0
    # Closing the project leaves the Show Manager with no machine
    window.closeProject()
    assert viewer.machinePath is None


NESTED_SHOW = """\
- duration: 1s
  shows:
    sample:
      loops: 0
      show_tokens:
        leds: l_x, l_y
        color: (tint)
"""


def test_viewerTokenValuesAndNestedShows(qtbot, tmp_path, monkeypatch):
    machinePath = _machine(tmp_path)
    (machinePath / "shows" / "wrapper.yaml").write_text(NESTED_SHOW)
    window = ShowViewerWindow(machinePath)
    qtbot.addWidget(window)
    window.resize(900, 500)
    window.show()

    # The nested show is played with the lights its tokens name, and the wrapper's own token is listed
    window.showList.selectShowItem(window.showList.showItems()[1])
    model = window.timelineModel
    channelNames = [model.headerData(row, Qt.Orientation.Vertical) for row in range(model.rowCount())]
    # Each light the nested show sets has a row under it naming that show
    assert channelNames[:5] == ["l_a  [light]", "    ↳ from show", "l_x  [light]", "    ↳ from show", "l_y  [light]"]
    assert "Plays shows: sample" in model.headerData(0, Qt.Orientation.Horizontal, Qt.ItemDataRole.ToolTipRole)
    assert "From show sample" in _cell(model, 2, 0, Qt.ItemDataRole.ToolTipRole)
    assert [window.tokenTable.item(row, 0).text() for row in range(window.tokenTable.rowCount())] == ["(tint)"]
    assert _cell(model, 2, 0, Qt.ItemDataRole.BackgroundRole).color().name() == "#ffffff"
    window.grab()

    # Giving the token a value draws the real color, and the value is kept for the show
    window.tokenTable.item(0, 1).setText("green")
    assert _cell(model, 2, 0, Qt.ItemDataRole.BackgroundRole).color().name() == "#008000"
    assert _cell(model, 2, 0, showViewer.PREVIEW_ROLE) is False
    window.showList.selectShowItem(window.showList.showItems()[0])
    window.showList.selectShowItem(window.showList.showItems()[1])
    assert window.tokenTable.item(0, 1).text() == "green"

    # The preview color can be changed or turned off
    window.showList.selectShowItem(window.showList.showItems()[0])
    monkeypatch.setattr(showViewer.QColorDialog, "getColor", lambda *args: QColor("#0000ff"))
    window.previewColorButton.click()
    assert window.previewColorButton.text() == "#0000ff"
    assert _cell(model, 1, 0, Qt.ItemDataRole.BackgroundRole).color().name() == "#0000ff"
    monkeypatch.setattr(showViewer.QColorDialog, "getColor", lambda *args: QColor())
    window.choosePreviewColor()
    assert window.previewRGB == (0, 0, 255)
    window.previewTokensAction.setChecked(False)
    assert _cell(model, 1, 0, Qt.ItemDataRole.BackgroundRole) is showViewer.TOKEN_CELL_BRUSH

    # Shows that are not in the project are reported
    (machinePath / "shows" / "wrapper.yaml").write_text("- shows:\n    missing_show: play\n")
    window.reloadShows()
    window.showList.selectShowItem(window.showList.showItems()[1])
    assert "Show missing_show is not in this project" in window.showSummary.text()


LAYERED_SHOW = """\
- duration: 1s
  lights:
    l_own: red
  shows:
    middle:
      loops: 0
- duration: 1s
  lights:
    l_shared: blue
"""


def test_rowsNameTheShowsThatSetALight(qtbot, tmp_path):
    machinePath = _machine(tmp_path)
    (machinePath / "shows" / "sample.yaml").unlink()
    (machinePath / "shows" / "layered.yaml").write_text(LAYERED_SHOW)
    (machinePath / "shows" / "middle.yaml").write_text(
        "- duration: 500ms\n  lights:\n    l_shared: lime\n  shows:\n    inner:\n      loops: 0\n"
        "- duration: 500ms\n  lights:\n    l_shared: off\n"
    )
    (machinePath / "shows" / "inner.yaml").write_text("- duration: 1s\n  lights:\n    l_deep: white\n")
    window = ShowViewerWindow(machinePath)
    qtbot.addWidget(window)
    window.show()
    window.showList.selectShowItem(window.showList.showItems()[1])
    assert window.selectedShow().name == "layered"
    model = window.timelineModel
    window.resolutionOption.setCurrentIndex(window.resolutionOption.findData(0.5))
    background = Qt.ItemDataRole.BackgroundRole
    tooltip = Qt.ItemDataRole.ToolTipRole

    # A light only set by the show's own steps has no row under it, while the lights other shows set do
    headers = [model.headerData(row, Qt.Orientation.Vertical) for row in range(model.rowCount())]
    assert headers == ["l_own  [light]", "l_shared  [light]", "    ↳ from show", "l_deep  [light]", "    ↳ from show"]
    assert [model.isSourceRow(row) for row in range(model.rowCount())] == [False, False, True, False, True]
    assert not model.isSourceRow(99)
    assert model.headerData(2, Qt.Orientation.Vertical, Qt.ItemDataRole.FontRole).italic()
    assert model.headerData(2, Qt.Orientation.Vertical, Qt.ItemDataRole.ForegroundRole) == showViewer.SOURCE_LABEL_COLOR
    assert "set l_shared: middle" in model.headerData(2, Qt.Orientation.Vertical, tooltip)
    assert "set l_deep: middle › inner" in model.headerData(2 + 2, Qt.Orientation.Vertical, tooltip)
    assert model.headerData(2, Qt.Orientation.Vertical, Qt.ItemDataRole.SizeHintRole) is None
    assert window.timelineView.verticalHeader().sectionSize(2) == showViewer.SOURCE_ROW_HEIGHT

    # The rows naming the shows can be collapsed, from the View menu or the ribbon, and shown again
    window.showSourceRowsAction.setChecked(False)
    headers = [model.headerData(row, Qt.Orientation.Vertical) for row in range(model.rowCount())]
    assert headers == ["l_own  [light]", "l_shared  [light]", "l_deep  [light]"]
    assert "that set it: middle" in model.headerData(1, Qt.Orientation.Vertical, tooltip)
    window.setSourceRowsShown(True)
    assert window.showSourceRowsAction.isChecked()
    assert model.rowCount() == 5 and model.isSourceRow(2)
    assert model.lightChannel(1).name == "l_shared"
    assert model.lightChannel(2) is None and model.cellState(2, 0) is None
    assert (
        window.timelineView.verticalHeader().sectionSize(1) == window.timelineView.verticalHeader().defaultSectionSize()
    )

    # The show is named where it starts giving the light its color, in that show's color
    assert [_cell(model, 2, column) for column in range(4)] == ["middle", None, None, None]
    middleColor = _cell(model, 2, 0, background).color()
    assert middleColor == model.sourceColors["middle"]
    assert _cell(model, 2, 1, background).color() == middleColor
    assert _cell(model, 2, 0, Qt.ItemDataRole.ForegroundRole).name() == "#000000"
    assert "Set by show middle" in _cell(model, 2, 1, tooltip)
    assert "Step 2 of middle: off" in _cell(model, 2, 1, tooltip)
    assert _cell(model, 2, 0, showViewer.PREVIEW_ROLE) is None

    # Every cell of the show's run knows the name and where it starts, so the name is drawn across the whole run
    assert _cell(model, 2, 1, showViewer.SOURCE_LABEL_ROLE) == ("middle", 0)
    assert _cell(model, 2, 0, showViewer.SOURCE_LABEL_ROLE) == ("middle", 0)
    assert _cell(model, 2, 2, showViewer.SOURCE_LABEL_ROLE) is None
    assert _cell(model, 1, 0, showViewer.SOURCE_LABEL_ROLE) is None

    # Cells where the show's own steps set the light are left as they are
    assert _cell(model, 2, 2) is None
    assert _cell(model, 2, 2, background) is None
    assert "Set by this show's own steps" in _cell(model, 2, 2, tooltip)
    assert _cell(model, 1, 2, background).color().name() == "#0000ff"

    # A show played by a played show is named with the show that played it, in its own color
    assert _cell(model, 4, 0) == "middle › inner"
    assert _cell(model, 4, 0, background).color() == model.sourceColors["inner"] != middleColor
    assert "Played by middle" in _cell(model, 4, 0, tooltip)
    assert "Not set by a show" in _cell(model, 4, 3, tooltip)
    assert _cell(model, 4, 3) is None
    assert _cell(model, 4, 0, showViewer.PLAYHEAD_ROLE) is True
    window.grab()


AUDIO_SHOW = """\
- duration: 1s
  sounds:
    tone:
      loops: 1
      volume: 2
  lights:
    l_a: red
- duration: 500ms
  sounds:
    missing_sound: play
    tone: stop
"""


def test_eachSoundFileHasItsOwnAudioRow(qtbot, tmp_path):
    machinePath = _machine(tmp_path)
    (machinePath / "shows" / "sample.yaml").unlink()
    (machinePath / "shows" / "music.yaml").write_text(AUDIO_SHOW + "- duration: 1s\n  sounds:\n    chime: play\n")
    (machinePath / "config").mkdir()
    (machinePath / "config" / "config.yaml").write_text("sounds:\n  chime:\n    file: tone.wav\n")
    writeTone(machinePath / "sounds" / "tone.wav", 0.6, amplitude=0.9)
    window = ShowViewerWindow(machinePath)
    qtbot.addWidget(window)
    window.resize(900, 400)
    window.show()
    model = window.timelineModel
    window.resolutionOption.setCurrentIndex(window.resolutionOption.findData(0.1))

    # Each sound file has its own row above the channels, named after the file, and chime plays the same file as tone
    assert model.audioRowCount == 2
    assert model.rowCount() == 3
    assert [model.headerData(row, Qt.Orientation.Vertical) for row in range(3)] == [
        "♪ tone.wav",
        "♪ missing_sound (no file found)",
        "l_a  [light]",
    ]
    assert model.audioRows[0].soundNames == ["tone", "chime"]
    assert model.headerData(0, Qt.Orientation.Vertical, Qt.ItemDataRole.FontRole).bold()
    assert model.headerData(0, Qt.Orientation.Vertical, Qt.ItemDataRole.ForegroundRole) == showViewer.SOUND_COLORS[
        0
    ].darker(130)
    assert model.headerData(1, Qt.Orientation.Vertical, Qt.ItemDataRole.ToolTipRole) == (
        "Sound missing_sound: no sound file found"
    )
    assert model.soundColor("chime") == showViewer.SOUND_COLORS[0]
    assert model.soundColor("missing_sound") == showViewer.SOUND_COLORS[1]
    assert _cell(model, 2, 0, Qt.ItemDataRole.BackgroundRole).color().name() == "#ff0000"
    header = window.timelineView.verticalHeader()
    assert [header.sectionSize(row) for row in range(2)] == [showViewer.AUDIO_ROW_HEIGHT] * 2
    assert _cell(model, 1, 0, showViewer.AUDIO_ROLE) is True
    assert _cell(model, 1, 0, Qt.ItemDataRole.BackgroundRole).color() == showViewer.AUDIO_ROW_BACKGROUND
    assert _cell(model, 0, 0) is None

    # While the sound is read it is marked from where it starts, and the missing sound is reported
    if model.waveformLoader.waveform(model.soundFiles["tone"]) is None:
        assert model.audioTraces(0, 0, 4) == [["loading"] * 4]
        assert "reading" in model.soundStatus("tone")
        assert "tone (tone.wav, reading…)" in _cell(model, 0, 0, Qt.ItemDataRole.ToolTipRole)
        window.timelineView.grab()
        qtbot.waitUntil(lambda: model.waveformLoader.waveform(model.soundFiles["tone"]) is not None, timeout=20000)
    assert "missing_sound (no sound file found)" in window.showSummary.text()
    assert "tone (tone.wav)" in window.showSummary.text()
    assert "Sound chime: tone.wav" in model.headerData(0, Qt.Orientation.Vertical, Qt.ItemDataRole.ToolTipRole)

    # Once read, each column of a row holds its sound's waveform levels, louder as the tone gets louder
    traces = model.audioTraces(0, 0, 10)
    assert len(traces) == 1
    levels = traces[0]
    assert all(level is not None for level in levels)
    assert levels[0][0] < levels[-1][0] <= 1.0
    assert all(energy <= peak for peak, energy in levels)

    # The tone plays twice (loops: 1) and is stopped at 1s, the missing sound only shows in its own row,
    # and chime plays the tone file in the tone's row at 1.5s
    loopTooltip = _cell(model, 0, 7, Qt.ItemDataRole.ToolTipRole)
    assert loopTooltip.startswith("tone.wav at 0.7s") and "tone at 0.1" in loopTooltip and "s, step 1" in loopTooltip
    assert model.audioTraces(0, 12, 4) == []
    assert "Not playing" in _cell(model, 0, 12, Qt.ItemDataRole.ToolTipRole)
    assert model.audioTraces(1, 12, 4) == [["loading"] * 4]
    assert "missing_sound (no sound file found)" in _cell(model, 1, 12, Qt.ItemDataRole.ToolTipRole)
    assert len(model.audioTraces(0, 15, 4)) == 1
    assert "chime at 0s" in _cell(model, 0, 15, Qt.ItemDataRole.ToolTipRole)
    assert "Not playing" in _cell(model, 1, 0, Qt.ItemDataRole.ToolTipRole)
    assert model.audioTraces(5, 0, 4) == []
    window.timelineView.grab()
    assert model.soundColor("unknown") == showViewer.SOUND_COLORS[0]

    # Switching to a show without sounds puts the rows back to the normal height
    (machinePath / "shows" / "quiet.yaml").write_text("- lights:\n    l_a: red\n    l_b: blue\n    l_c: lime\n")
    window.reloadShows()
    window.showList.selectShowItem(window.showList.showItems()[1])
    assert model.audioRowCount == 0
    assert [header.sectionSize(row) for row in range(3)] == [header.defaultSectionSize()] * 3


def test_audioRowWithoutSounds(qtbot, tmp_path):
    model = _model(tmp_path)
    assert model.audioRowCount == 0
    assert model.audioTraces(0, 0, 4) == []
    model.setAudio({"tone": tmp_path / "tone.wav"}, None)
    assert model.soundStatus("tone") == "tone.wav, reading…"
    model.refreshAudio()
    model.setShow(None)
    assert model.audioTraces(0, 0, 4) == []
    assert model.soundColor("tone") == showViewer.SOUND_COLORS[0]


def test_audioRowReportsUnreadableSounds(qtbot, tmp_path):
    machinePath = _machine(tmp_path)
    (machinePath / "shows" / "music.yaml").write_text(AUDIO_SHOW)
    (machinePath / "sounds").mkdir()
    (machinePath / "sounds" / "tone.ogg").write_bytes(b"not audio")
    window = ShowViewerWindow(machinePath)
    qtbot.addWidget(window)
    window.showList.selectShowItem(window.showList.showItems()[0])
    model = window.timelineModel
    qtbot.waitUntil(lambda: model.waveformLoader.hasFailed(model.soundFiles["tone"]), timeout=20000)
    assert model.soundStatus("tone") == "tone.ogg could not be read"


def test_openedShowFilesUseTheirMachinesSounds(qtbot, tmp_path):
    machinePath = _machine(tmp_path)
    (machinePath / "shows" / "music.yaml").write_text(AUDIO_SHOW)
    writeTone(machinePath / "sounds" / "tone.wav", 0.2)
    window = ShowViewerWindow()
    qtbot.addWidget(window)
    window.openShowFile(machinePath / "shows" / "music.yaml")
    assert window.soundFiles == {"tone": machinePath / "sounds" / "tone.wav"}
    qtbot.waitUntil(
        lambda: window.waveformLoader.waveform(machinePath / "sounds" / "tone.wav") is not None, timeout=20000
    )


def test_fadeTokenTooltip():
    model = ShowTimelineModel()
    model.setShow(showManager.parseShow([{"lights": {"l_a": "red-f(fade)"}}], "fade token"))
    assert "Fade: (fade) (not drawn)" in _cell(model, 0, 0, Qt.ItemDataRole.ToolTipRole)


def test_viewerUsesTheProjectsNamedColors(qtbot, tmp_path):
    machinePath = _machine(tmp_path)
    (machinePath / "shows" / "sample.yaml").write_text("- lights:\n    l_a: color_grunt\n")
    (machinePath / "shows" / "unknown.yaml").write_text("- lights:\n    l_a: color_unknown\n")
    (machinePath / "config").mkdir()
    (machinePath / "config" / "config.yaml").write_text("named_colors:\n  color_grunt: FF6611\n")
    window = ShowViewerWindow(machinePath)
    qtbot.addWidget(window)
    assert window.namedColors == {"color_grunt": (255, 102, 17)}
    assert _showLabels(window) == ["sample", "unknown ⚠"]
    assert _cell(window.timelineModel, 0, 0, Qt.ItemDataRole.BackgroundRole).color().name() == "#ff6611"

    window.showList.selectShowItem(window.showList.showItems()[1])
    assert "Step 1: l_a has an invalid color 'color_unknown'" in window.showSummary.text()

    # A show file opened from another machine uses that machine's named colors
    otherMachine = tmp_path / "other"
    (otherMachine / "shows").mkdir(parents=True)
    (otherMachine / "config").mkdir()
    (otherMachine / "config" / "config.yaml").write_text("named_colors:\n  color_space: 0044AA\n")
    (otherMachine / "shows" / "space.yaml").write_text("- lights:\n    l_b: color_space\n")
    window.openShowFile(otherMachine / "shows" / "space.yaml")
    assert window.namedColors["color_space"] == (0, 68, 170)
    assert _cell(window.timelineModel, 0, 0, Qt.ItemDataRole.BackgroundRole).color().name() == "#0044aa"


def test_viewerListsShowsDefinedInConfigs(qtbot, tmp_path):
    machinePath = _machine(tmp_path)
    (machinePath / "shows" / "sample.yaml").write_text(
        "- shows:\n    color_flashing_fast:\n      show_tokens:\n        leds: l_x\n"
    )
    (machinePath / "config").mkdir()
    (machinePath / "config" / "config.yaml").write_text("shows:\n  machine_pulse:\n    - lights:\n        l_a: red\n")
    (machinePath / "modes" / "base" / "config").mkdir(parents=True)
    (machinePath / "modes" / "base" / "config" / "base.yaml").write_text(
        "shows:\n  color_flashing_fast:\n    - lights:\n        (leds): blue\n"
    )
    window = ShowViewerWindow(machinePath)
    qtbot.addWidget(window)
    assert _showLabels(window) == [
        "machine_pulse",
        "color_flashing_fast",
        "sample",
    ]
    assert window.showList.showItems()[1].toolTip(0) == str(machinePath / "modes" / "base" / "config" / "base.yaml")
    assert _cell(window.timelineModel, 0, 0, Qt.ItemDataRole.BackgroundRole).color().name() == "#0000ff"

    # A show file opened from another machine can play that machine's config shows
    otherMachine = tmp_path / "other"
    (otherMachine / "shows").mkdir(parents=True)
    (otherMachine / "config").mkdir()
    (otherMachine / "config" / "config.yaml").write_text("shows:\n  other_pulse:\n    - lights:\n        l_o: lime\n")
    (otherMachine / "shows" / "outer.yaml").write_text("- shows:\n    other_pulse: play\n")
    window.openShowFile(otherMachine / "shows" / "outer.yaml")
    assert window.selectedShow().name == "outer"
    assert "other_pulse" in window.library
    assert _cell(window.timelineModel, 0, 0, Qt.ItemDataRole.BackgroundRole).color().name() == "#00ff00"


PLAYBACK_SHOW = """\
- duration: 1s
  lights:
    gi: red
    l_a: blue
- duration: 1s
  lights:
    gi: lime-f1s
"""


def _playbackMachine(tmp_path: Path) -> Path:
    machinePath = _machine(tmp_path)
    (machinePath / "shows" / "sample.yaml").write_text(PLAYBACK_SHOW)
    (machinePath / "shows" / "zzz_other.yaml").write_text("- lights:\n    l_b: white\n")
    (machinePath / "config").mkdir()
    (machinePath / "config" / "config.yaml").write_text("lights:\n  l_a:\n    tags: gi\n  l_b:\n    tags: gi\n")
    (machinePath / "monitor").mkdir()
    (machinePath / "monitor" / "monitor.yaml").write_text(
        "light:\n  l_a:\n    x: 0.2\n    y: 0.2\n  l_b:\n    x: 0.8\n    y: 0.8\n"
    )
    (machinePath / "monitor" / "monitor_b.yaml").write_text("light:\n  l_b:\n    x: 0.5\n    y: 0.5\n")
    writePlayfieldImage(machinePath / "monitor" / "playfield.jpg")
    return machinePath


def _lightColor(window: ShowViewerWindow, lightName: str) -> tuple[int, int, int] | None:
    return window.playfieldView.lightItems[lightName].rgb


def test_playfieldFollowsThePlayhead(qtbot, tmp_path):
    window = ShowViewerWindow(_playbackMachine(tmp_path))
    qtbot.addWidget(window)
    window.show()
    model = window.timelineModel

    # The playfield is drawn from the machine's MPF-Monitor layout, with the show's colors at the playhead
    assert [window.monitorConfigOption.itemText(row) for row in range(2)] == ["monitor.yaml", "monitor_b.yaml"]
    assert window.monitorConfigOption.currentText() == "monitor.yaml"
    assert window.playfieldView.hasImage
    assert window.playfieldSummary.text() == "2 lights placed"
    assert window.timeLabel.text() == "0.00s / 2.00s"
    assert (_lightColor(window, "l_a"), _lightColor(window, "l_b")) == ((0, 0, 255), (255, 0, 0))
    assert model.playheadColumn == 0
    assert _cell(model, 0, 0, showViewer.PLAYHEAD_ROLE) is True
    assert _cell(model, 0, 1, showViewer.PLAYHEAD_ROLE) is False

    # Moving the playhead, by the time slider, the ruler or a grid cell, updates the grid and the playfield
    window.timeSlider.setValue(1500)
    assert window.playTime == 1.5
    assert window.timeLabel.text() == "1.50s / 2.00s"
    assert model.playheadColumn == model.columnForTime(1.5)
    assert _lightColor(window, "l_a") == (0, 127, 127)
    assert window.playfieldView.lightItems["l_a"].toolTip().endswith("Set by gi")
    window.timelineView.horizontalHeader().sectionClicked.emit(model.columnForTime(1.0))
    assert window.playTime == 1.0
    window.timelineView.clicked.emit(model.index(0, 0))
    assert window.playTime == 0.0
    window.setPlayTime(-5)
    assert window.playTime == 0.0
    window.setPlayTime(99, follow=True)
    assert window.playTime == 2.0
    assert model.playheadColumn == model.columnCount() - 1
    window.grab()

    # Another layout from the monitor folder can be chosen
    window.monitorConfigOption.setCurrentText("monitor_b.yaml")
    assert list(window.playfieldView.lightItems) == ["l_b"]
    assert window.playfieldSummary.text() == "1 lights placed. Not on this playfield: l_a"


def test_playback(qtbot, tmp_path):
    window = ShowViewerWindow(_playbackMachine(tmp_path))
    qtbot.addWidget(window)
    window.show()

    window.speedOption.setCurrentIndex(window.speedOption.findData(4.0))
    window.togglePlayback()
    assert window.isPlaying and window.playButton.text() == "Pause"
    qtbot.waitUntil(lambda: window.playTime > 1.0, timeout=5000)
    assert _lightColor(window, "l_b") != (255, 0, 0)

    # Looping playback carries on from the start, and without looping it stops at the end
    qtbot.waitUntil(lambda: window.playTime < 1.0, timeout=5000)
    assert window.isPlaying
    window.loopAction.setChecked(False)
    qtbot.waitUntil(lambda: not window.isPlaying, timeout=5000)
    assert window.playTime == 2.0 and window.playButton.text() == "Play"

    # Playing from the end starts again from the beginning, and pausing keeps the time
    window.togglePlayback()
    assert window.playTime == 0.0 and window.isPlaying
    window.togglePlayback()
    assert not window.isPlaying
    window.rewindButton.click()
    assert window.playTime == 0.0

    # Choosing another show, or hiding the window, pauses playback
    window.togglePlayback()
    window.hide()
    assert not window.isPlaying
    window.show()
    window.setPlayTime(1.0)
    window.togglePlayback()
    window.showList.selectShowItem(window.showList.showItems()[1])
    assert not window.isPlaying and window.playTime == 0.0
    assert _lightColor(window, "l_b") == (255, 255, 255)

    # Playback stops when there is no show to play
    window.togglePlayback()
    window.timelineModel.setShow(None)
    window._advancePlayback()
    assert not window.isPlaying
    window.togglePlayback()
    assert not window.isPlaying


def test_playfieldWithoutALayout(qtbot, tmp_path):
    machinePath = _machine(tmp_path)
    window = ShowViewerWindow(machinePath)
    qtbot.addWidget(window)
    assert window.monitorConfigOption.count() == 0
    assert "No MPF-Monitor layout" in window.playfieldSummary.text()

    (machinePath / "monitor").mkdir()
    (machinePath / "monitor" / "monitor.yaml").write_text("light:\n  l_x:\n    x: 0.5\n    y: 0.5\n")
    window.reloadShows()
    assert window.playfieldSummary.text().startswith("1 lights placed, no playfield image. Not on this playfield: l_a")

    # A show file opened without a machine uses its own machine's playfield
    otherWindow = ShowViewerWindow()
    qtbot.addWidget(otherWindow)
    otherWindow.openShowFile(machinePath / "shows" / "sample.yaml")
    assert otherWindow.playfieldMachine == machinePath
    assert list(otherWindow.playfieldView.lightItems) == ["l_x"]


def _typeTimebase(window: ShowViewerWindow, text: str) -> None:
    window.resolutionOption.setEditText(text)
    lineEdit = window.resolutionOption.lineEdit()
    assert lineEdit is not None
    lineEdit.editingFinished.emit()


def test_customTimebase(qtbot, tmp_path, monkeypatch):
    window = ShowViewerWindow(_playbackMachine(tmp_path))
    qtbot.addWidget(window)
    model = window.timelineModel
    itemCount = window.resolutionOption.count()

    # A typed timebase is added to the list and used for the grid's columns and the playhead
    _typeTimebase(window, "40ms")
    assert window.resolutionOption.currentText() == "40 ms"
    assert window.resolutionOption.count() == itemCount + 1
    assert model.resolution == pytest.approx(0.04)
    assert model.columnCount() == 50
    assert "grid of 0.04s per column" in window.showSummary.text()
    window.setPlayTime(1.0)
    assert model.playheadColumn == 25

    # A frame rate keeps the rate in its label, and typing one already in the list chooses it
    _typeTimebase(window, "30fps")
    assert window.resolutionOption.currentText() == "33.333 ms (30fps)"
    assert model.resolution == pytest.approx(1 / 30)
    assert model.columnCount() == 60
    _typeTimebase(window, "40")
    assert window.resolutionOption.currentText() == "40 ms"
    _typeTimebase(window, "100ms")
    assert window.resolutionOption.currentText() == "100 ms"
    _typeTimebase(window, "auto")
    assert window.resolutionOption.currentText() == "Auto"
    assert window.resolutionOption.count() == itemCount + 2

    # Text that is not a timebase is explained, and the chosen timebase is kept
    _typeTimebase(window, "fast")
    assert window.timebaseMessage.isVisibleTo(window)
    assert "'fast' is not a timebase" in window.timebaseMessage.text()
    assert window.resolutionOption.currentText() == "Auto"
    _typeTimebase(window, "0.25s")
    assert not window.timebaseMessage.isVisibleTo(window)
    assert window.resolutionOption.currentText() == "250 ms"

    # A timebase too fine for a long show is coarsened, and the summary says so
    monkeypatch.setattr(showViewer, "MAX_GRID_COLUMNS", 10)
    _typeTimebase(window, "1ms")
    assert model.columnCount() == 10
    assert "the 0.001s timebase would make too many columns" in window.showSummary.text()


def test_typingATimebase(qtbot, tmp_path):
    window = ShowViewerWindow(_playbackMachine(tmp_path))
    qtbot.addWidget(window)
    window.show()
    lineEdit = window.resolutionOption.lineEdit()
    assert lineEdit is not None
    lineEdit.selectAll()
    qtbot.keyClicks(lineEdit, "24fps")
    qtbot.keyClick(lineEdit, Qt.Key.Key_Return)
    assert window.resolutionOption.currentText() == "41.667 ms (24fps)"
    assert window.timelineModel.resolution == pytest.approx(1 / 24)


def _select(window: ShowViewerWindow, row: int, firstColumn: int, lastColumn: int, lastRow: int | None = None) -> None:
    model = window.timelineModel
    selection = QItemSelection(model.index(row, firstColumn), model.index(lastRow or row, lastColumn))
    window.timelineView.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.Select)


def _background(model: ShowTimelineModel, row: int, column: int) -> str:
    return _cell(model, row, column, Qt.ItemDataRole.BackgroundRole).color().name()


def test_paintingCells(qtbot, tmp_path):
    window = ShowViewerWindow(_machine(tmp_path))
    qtbot.addWidget(window)
    window.show()
    model = window.timelineModel
    ribbon = window.ribbon
    assert not ribbon.undoButton.isEnabled() and not ribbon.saveButton.isEnabled()
    assert ribbon.saveAsButton.isEnabled()

    # The paint and erase tools let cells be chosen, which the other tools do not
    ribbon.setTool(TOOL_PAINT)
    assert window.timelineView.selectionMode() == QAbstractItemView.SelectionMode.ContiguousSelection
    ribbon.setColor((0, 0, 255), 50)

    # Painting the cells chosen sets the light's color there, and it goes back to its color afterwards
    _select(window, 0, 2, 3)
    assert window.applyToolToSelection()
    assert [_background(model, 0, column) for column in (1, 2, 3, 4)] == ["#ff0000", "#00007f", "#00007f", "#ff0000"]
    assert model.resolution == 0.1
    assert not window.timelineView.selectionModel().hasSelection()
    assert "Painted blue%50 on l_a from 0.2s to 0.4s" in window.statusBar().currentMessage()
    assert window.showList.currentShowItem().text(0) == "● sample ⚠"
    assert ribbon.undoButton.isEnabled() and ribbon.saveButton.isEnabled()
    assert "Added step: red" in _cell(model, 0, 4, Qt.ItemDataRole.ToolTipRole)
    assert not window.applyToolToSelection()

    # Several lights are painted at once, and the rows of tokens are painted by their names
    ribbon.setColor((255, 255, 255), 100)
    _select(window, 0, 6, 7, lastRow=1)
    window.applyToolToSelection()
    assert [_background(model, row, 6) for row in (0, 1)] == ["#ffffff", "#ffffff"]

    # Changes can be undone and redone
    window.undo()
    assert _background(model, 0, 6) == "#000000"
    window.undo()
    assert _background(model, 0, 2) == "#ff0000"
    assert not ribbon.undoButton.isEnabled() and ribbon.redoButton.isEnabled()
    window.undo()
    window.redo()
    assert _background(model, 0, 2) == "#00007f"

    # Erasing takes out what the show set the light to, so it carries on with its color from before
    ribbon.setTool(TOOL_ERASE)
    window.paintCells(["l_a"], 2, 3, erase=True)
    assert _background(model, 0, 2) == "#ff0000"
    assert window.statusBar().currentMessage().startswith("Erased l_a")
    assert not window.paintCells([], 2, 3)

    # The select tool chooses cells without painting them, and the pick tool chooses none
    ribbon.setTool(TOOL_SELECT)
    assert window.timelineView.selectionMode() == QAbstractItemView.SelectionMode.ContiguousSelection
    _select(window, 0, 2, 3)
    assert not window.applyToolToSelection()
    ribbon.setTool(TOOL_PICK)
    assert window.timelineView.selectionMode() == QAbstractItemView.SelectionMode.NoSelection
    window.grab()


def test_paintingByClicking(qtbot, tmp_path):
    window = ShowViewerWindow(_machine(tmp_path))
    qtbot.addWidget(window)
    window.resize(1200, 600)
    window.show()
    qtbot.waitExposed(window)
    model = window.timelineModel
    window.ribbon.setTool(TOOL_PAINT)
    window.ribbon.setColor((0, 255, 0))

    cellCenter = window.timelineView.visualRect(model.index(3, 2)).center()
    qtbot.mouseClick(window.timelineView.viewport(), Qt.MouseButton.LeftButton, pos=cellCenter)
    qtbot.waitUntil(lambda: _background(model, 3, 2) == "#00ff00")
    assert window.playTime == pytest.approx(0.2)
    assert _cell(model, 3, 3, Qt.ItemDataRole.BackgroundRole) is showViewer.STOP_CELL_BRUSH

    # The rows stay in their order while the show is painted, though the light is now set before the one above it
    assert [model.headerData(row, Qt.Orientation.Vertical) for row in (2, 3)] == ["l_b  [light]", "l_c  [light]"]

    # With the select tool, clicking only moves the playhead
    window.ribbon.setTool(TOOL_SELECT)
    cellCenter = window.timelineView.visualRect(model.index(3, 5)).center()
    qtbot.mouseClick(window.timelineView.viewport(), Qt.MouseButton.LeftButton, pos=cellCenter)
    assert window.playTime == pytest.approx(0.5)
    assert _cell(model, 3, 5) == "nope"

    # Once the show is shown again, its rows are in the order the lights are first set
    window._displaySelectedShow()
    assert model.headerData(2, Qt.Orientation.Vertical) == "l_c  [light]"


def test_pickingColors(qtbot, tmp_path):
    window = ShowViewerWindow(_machine(tmp_path))
    qtbot.addWidget(window)
    window.show()
    model = window.timelineModel
    window.ribbon.setTool(TOOL_PICK)

    # Picking a cell paints with its color and intensity next
    window._cellClicked(model.index(2, 9))
    assert window.ribbon.paintRGB == (255, 255, 255) and window.ribbon.intensity == 100
    assert window.ribbon.currentTool == TOOL_PAINT
    window.ribbon.setTool(TOOL_PICK)
    window.timelineModel.show.steps[0].lights["l_a"] = showManager.parseLightSetting("red%30")
    window._displaySelectedShow()
    assert window.pickColor(0, 0)
    assert (window.ribbon.paintRGB, window.ribbon.intensity) == ((255, 0, 0), 30)
    assert window.statusBar().currentMessage() == "Painting with red%30"

    # Cells without a color have nothing to pick
    window.ribbon.setTool(TOOL_PICK)
    assert not window.pickColor(1, 0)
    assert not window.pickColor(2, 0)
    assert window.statusBar().currentMessage() == "That cell has no color to pick"
    assert window.ribbon.currentTool == TOOL_PICK


def test_savingPaintedShows(qtbot, tmp_path, monkeypatch):
    machinePath = _machine(tmp_path)
    showFile = machinePath / "shows" / "sample.yaml"
    window = ShowViewerWindow(machinePath)
    qtbot.addWidget(window)
    window.show()
    window.ribbon.setColor((0, 0, 255), 50)
    window.paintCells(["l_a"], 2, 3)

    # Saving writes the show to its file, keeping its comments, and the show is numbered as the file is now
    assert window.saveShow()
    savedText = showFile.read_text()
    assert savedText.startswith("#show_version=6\n- duration: 200ms\n")
    assert "l_a: blue%50" in savedText
    assert [step.stepNumber for step in window.selectedShow().steps] == [1, 2, 3, 4, 5]
    assert window.showList.currentShowItem().text(0) == "sample ⚠"
    assert not window.ribbon.saveButton.isEnabled() and not window.ribbon.undoButton.isEnabled()
    assert not window.saveShow()
    assert "Saved sample to" in window.statusBar().currentMessage()
    reloaded = showManager.loadShowFile(showFile)[0]
    reloaded.buildTimeline()
    assert reloaded.channelState("l_a", 0.3).rgb == (0, 0, 127)

    # Saving as a new file lists the show with that file
    window.tokenValues[window._selectedShowKey()] = {"color": "red"}
    window.paintCells(["l_b"], 0, 1)
    newFile = tmp_path / "elsewhere" / "copy.yaml"
    monkeypatch.setattr(showViewer.QFileDialog, "getSaveFileName", lambda *args: (str(newFile), ""))
    window.ribbon.saveAsButton.click()
    assert newFile.is_file()
    assert window.showList.currentShowItem().toolTip(0) == str(newFile)
    # The saved show keeps its problem mark, and the original file is still listed, as it is in its file
    assert window.showList.currentShowItem().text(0) == "copy ⚠"
    assert window.selectedShow().name == "copy" and window.library["copy"] is window.selectedShow()
    assert window.tokenValues[window._selectedShowKey()] == {"color": "red"}
    assert newFile in window.extraShowFiles
    assert window.selectedShow().sourcePath == newFile
    originals = window.showList.showItemsOfFile(showFile)
    assert len(originals) == 1 and originals[0].text(0) == "sample ⚠"
    original = originals[0].data(0, showViewer.SHOW_ROLE)
    assert original is not window.selectedShow() and original.sourcePath == showFile
    assert not window.hasUnsavedChanges()

    # Saving over a file that is listed lists the file once, with the show saved to it
    zzzFile = showFile.parent / "zzz_other.yaml"
    monkeypatch.setattr(showViewer.QFileDialog, "getSaveFileName", lambda *args: (str(zzzFile), ""))
    assert window.saveShowAs()
    assert [item.text(0) for item in window.showList.showItemsOfFile(zzzFile)] == ["zzz_other ⚠"]
    assert window.showList.currentShowItem().parent().text(0) == "shows"
    assert [item.text(0) for item in window.showList.showItemsOfFile(newFile)] == ["copy ⚠"]
    monkeypatch.setattr(showViewer.QFileDialog, "getSaveFileName", lambda *args: ("", ""))
    assert not window.saveShowAs()

    # A show that cannot be written says so and stays unsaved
    window.paintCells(["l_b"], 2, 3)
    monkeypatch.setattr(showManager, "exportShowFile", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    warnings = []
    monkeypatch.setattr(showViewer.QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    assert not window.saveShow()
    assert "disk full" in warnings[0]
    assert window.hasUnsavedChanges()


def test_showsInConfigsAreSavedAsShowFiles(qtbot, tmp_path):
    machinePath = _machine(tmp_path)
    (machinePath / "shows" / "sample.yaml").unlink()
    (machinePath / "config").mkdir()
    (machinePath / "config" / "config.yaml").write_text("shows:\n  pulse:\n    - lights:\n        l_a: red\n")
    window = ShowViewerWindow(machinePath)
    qtbot.addWidget(window)
    window.paintCells(["l_a"], 0, 0)
    assert not window.ribbon.saveButton.isEnabled() and window.ribbon.saveAsButton.isEnabled()
    assert "Save as" in window.ribbon.saveButton.toolTip()
    assert not window.saveShow()


def test_unsavedChangesAreNotLostWithoutAsking(qtbot, tmp_path, monkeypatch):
    machinePath = _machine(tmp_path)
    window = ShowViewerWindow(machinePath)
    qtbot.addWidget(window)
    window.paintCells(["l_a"], 2, 3)
    answers = []

    def answer(button):
        def question(*args, **kwargs):
            answers.append(args[2])
            return button

        return question

    # Reloading, opening a file or another machine asks first, and keeps the changes if cancelled
    monkeypatch.setattr(showViewer.QMessageBox, "question", answer(showViewer.QMessageBox.StandardButton.Cancel))
    assert not window.reloadShows()
    assert "sample" in answers[0]
    window.openShowFile(machinePath / "shows" / "sample.yaml")
    window.setMachinePath(tmp_path)
    assert window.machinePath == machinePath
    assert window.hasUnsavedChanges()
    assert window.showList.currentShowItem().text(0).startswith("●")

    # Discarding reads the shows again from their files
    monkeypatch.setattr(showViewer.QMessageBox, "question", answer(showViewer.QMessageBox.StandardButton.Discard))
    assert window.reloadShows()
    assert not window.hasUnsavedChanges()
    assert _background(window.timelineModel, 0, 2) == "#ff0000"
    assert not window.ribbon.undoButton.isEnabled()

    # The main window asks too before closing
    store = StorageProcessor()
    mainWindow = MainWindow(store)
    qtbot.addWidget(mainWindow)
    mainWindow.openShowViewer()
    viewer = mainWindow.showViewerWindow
    viewer.unsavedKeys.add("somewhere\nedited")
    monkeypatch.setattr(showViewer.QMessageBox, "question", answer(showViewer.QMessageBox.StandardButton.Cancel))
    assert not mainWindow.close()
    assert "edited" in answers[-1]
    monkeypatch.setattr(showViewer.QMessageBox, "question", answer(showViewer.QMessageBox.StandardButton.Discard))
    assert mainWindow.close()


def _row(model: ShowTimelineModel, channelName: str) -> int:
    return next(
        row for row in range(model.rowCount()) if (channel := model.lightChannel(row)) and channel.name == channelName
    )


def _colorAt(window: ShowViewerWindow, channelName: str, atTime: float):
    return window.selectedShow().channelState(channelName, atTime).rgb


def _editWindow(qtbot, tmp_path) -> ShowViewerWindow:
    window = ShowViewerWindow(_playbackMachine(tmp_path))
    qtbot.addWidget(window)
    window.show()
    window.resolutionOption.setCurrentIndex(window.resolutionOption.findData(0.25))
    return window


def test_actionsNeedCellsChosen(qtbot, tmp_path):
    window = _editWindow(qtbot, tmp_path)
    for action in (window.copyCells, window.repeatCells, window.openChaseDialog, window.openMakeShowDialog):
        assert not action()
        assert window.statusBar().currentMessage() == "Choose some light cells first, by dragging over them"
    assert not window.pasteCells()
    assert window.statusBar().currentMessage() == "Copy some cells first"
    assert not window.chaseCells("grid order", "forward", 0.25)
    assert not window.makeShowFromCells("anything")


def test_copyAndPasteCells(qtbot, tmp_path):
    window = _editWindow(qtbot, tmp_path)
    model = window.timelineModel
    blue = (0, 0, 255)

    # Copying the chosen cells and pasting with none chosen pastes onto the same light at the playhead
    _select(window, _row(model, "l_a"), 0, 1)
    assert window.copyCells()
    assert window.statusBar().currentMessage() == "Copied l_a from 0s to 0.5s"
    window.timelineView.clearSelection()
    window.setPlayTime(1.0)
    window.ribbon.pasteButton.click()
    assert window.statusBar().currentMessage() == "Pasted onto l_a at 1s"
    assert _colorAt(window, "l_a", 1.25) == blue
    assert _colorAt(window, "l_a", 1.75) == blue

    # Pasting with one light chosen pastes from its first cell onto it
    _select(window, _row(model, "gi"), 2, 2)
    assert window.pasteCells()
    assert _colorAt(window, "gi", 0.6) == blue
    assert _colorAt(window, "gi", 1.1) is not None

    # As many lights chosen as were copied are pasted onto in order
    _select(window, _row(model, "gi"), 0, 1, lastRow=_row(model, "l_a"))
    window.copyCells()
    window.timelineView.clearSelection()
    window.ribbon.setColor((255, 255, 255))
    window.paintCells(["l_a", "gi"], 4, 7)
    _select(window, _row(model, "gi"), 4, 4, lastRow=_row(model, "l_a"))
    assert window.pasteCells()
    assert _colorAt(window, "gi", 1.1) == (255, 0, 0)
    assert _colorAt(window, "l_a", 1.1) == blue

    # Pasting can be undone
    window.undo()
    assert _colorAt(window, "l_a", 1.1) == (255, 255, 255)

    # With fewer lights chosen than were copied, they are pasted onto the light rows from the first one chosen
    window.addLightRow("l_b")
    window.timelineView.clearSelection()
    _select(window, _row(model, "l_a"), 6, 6)
    assert window.pasteCells()
    assert window.statusBar().currentMessage() == "Pasted onto l_a, l_b at 1.5s"
    assert _colorAt(window, "l_a", 1.6) == (255, 0, 0)
    assert _colorAt(window, "l_b", 1.6) == blue


def test_repeatCells(qtbot, tmp_path, monkeypatch):
    window = _editWindow(qtbot, tmp_path)
    model = window.timelineModel
    window.ribbon.setColor((255, 255, 255))
    window.paintCells(["l_a"], 0, 0)
    _select(window, _row(model, "l_a"), 0, 1)

    # Repeating asks how many times, and is left if cancelled
    monkeypatch.setattr(showViewer.QInputDialog, "getInt", lambda *args: (2, False))
    assert not window.repeatCells()
    monkeypatch.setattr(showViewer.QInputDialog, "getInt", lambda *args: (3, True))
    window.ribbon.repeatButton.click()
    assert window.statusBar().currentMessage() == "Repeated l_a 3 times"
    assert [_colorAt(window, "l_a", atTime) for atTime in (1.1, 1.4, 1.6)] == [
        (255, 255, 255),
        (0, 0, 255),
        (255, 255, 255),
    ]

    # Repeating once goes on past the end of the show, making it longer
    _select(window, _row(model, "l_a"), 6, 7)
    assert window.repeatCells(1)
    assert window.selectedShow().totalDuration == 2.5


def test_chaseCells(qtbot, tmp_path, monkeypatch):
    window = _editWindow(qtbot, tmp_path)
    model = window.timelineModel
    window.addLightRow("l_b")
    window.ribbon.setColor((255, 255, 255))
    off = showEditor.paintSetting((0, 0, 0))

    # The lights are ordered by where they are on the playfield, here bottom to top: l_b and then l_a
    assert window.channelPositions(["l_a", "gi", "l_x"]) == {"l_a": (0.2, 0.2), "gi": (0.5, 0.5)}
    _select(window, _row(model, "l_a"), 0, 3, lastRow=_row(model, "l_b"))
    assert window.chaseCells("bottom to top", "forward", 0.25, 1, off)
    assert window.statusBar().currentMessage() == "Chased l_b, l_a from 0s to 1s"
    assert [(_colorAt(window, "l_b", atTime), _colorAt(window, "l_a", atTime)) for atTime in (0.1, 0.4, 0.6)] == [
        ((255, 255, 255), (0, 0, 0)),
        ((0, 0, 0), (255, 255, 255)),
        ((255, 255, 255), (0, 0, 0)),
    ]

    # The dialog asks how to chase, and nothing changes if it is cancelled
    window.undo()
    _select(window, _row(model, "l_a"), 0, 3, lastRow=_row(model, "l_b"))
    monkeypatch.setattr(showViewer.ChaseDialog, "exec", lambda dialog: QDialog.DialogCode.Rejected)
    assert not window.openChaseDialog()
    monkeypatch.setattr(showViewer.ChaseDialog, "exec", lambda dialog: QDialog.DialogCode.Accepted)
    assert window.ribbon.chaseButton.isEnabled()
    assert window.openChaseDialog()
    # The dialog's own choices are the grid's order, forward, and a step of the grid's timebase
    assert _colorAt(window, "l_a", 0.1) == (255, 255, 255)
    assert _colorAt(window, "l_b", 0.1) == (0, 0, 0)
    assert _colorAt(window, "l_b", 0.3) == (255, 255, 255)


def test_makeShowFromCells(qtbot, tmp_path, monkeypatch):
    window = _editWindow(qtbot, tmp_path)
    model = window.timelineModel
    machinePath = window.machinePath
    before = [(_colorAt(window, "gi", atTime), _colorAt(window, "l_a", atTime)) for atTime in (0.5, 1.5)]
    showCount = len(window.showList.showItems())

    # The dialog makes a show of the chosen cells, with tokens for the lights and colors, played in their place
    _select(window, _row(model, "gi"), 0, 7, lastRow=_row(model, "l_a"))
    monkeypatch.setattr(showViewer.ReusableShowDialog, "exec", lambda dialog: QDialog.DialogCode.Rejected)
    assert not window.openMakeShowDialog()
    monkeypatch.setattr(showViewer.ReusableShowDialog, "exec", lambda dialog: QDialog.DialogCode.Accepted)
    assert window.openMakeShowDialog()
    showFile = machinePath / "shows" / "sample_part.yaml"
    assert showFile.read_text().startswith("#show_version=6\n- duration: 1s\n  lights:\n    (light1): (color1)\n")
    assert "sample_part" in window.library
    assert len(window.showList.showItems()) == showCount + 1
    assert [item.text(0) for item in window.showList.showItemsOfFile(showFile)] == ["sample_part"]
    assert window.selectedShow().name == "sample"
    assert window.selectedShow().steps[0].shows["sample_part"]["show_tokens"] == {
        "light1": "gi",
        "light2": "l_a",
        "color1": "red",
        "color2": "blue",
        "color3": "lime",
    }
    assert [(_colorAt(window, "gi", atTime), _colorAt(window, "l_a", atTime)) for atTime in (0.5, 1.5)] == before
    assert window.selectedShow().channelState("l_a", 0.5).segment.showPath == ("sample_part",)
    assert window.statusBar().currentMessage().startswith("Made show sample_part")

    # A show name already used, or a file already there, is not made
    warnings = []
    monkeypatch.setattr(showViewer.QMessageBox, "warning", lambda *args: warnings.append(args[2]))
    _select(window, _row(model, "gi"), 0, 1)
    assert not window.makeShowFromCells("sample_part")
    (machinePath / "shows" / "taken.yaml").write_text("- lights: {}\n")
    assert not window.makeShowFromCells("taken")
    monkeypatch.setattr(showManager, "exportShowFile", lambda *args: (_ for _ in ()).throw(OSError("read only")))
    assert not window.makeShowFromCells("unwritable")
    assert warnings == [
        "There is already a show called sample_part.",
        f"{machinePath / 'shows' / 'taken.yaml'} already exists.",
        f"The show could not be written to {machinePath / 'shows' / 'unwritable.yaml'}:\nread only",
    ]


def test_addLightRow(qtbot, tmp_path, monkeypatch):
    window = _editWindow(qtbot, tmp_path)
    model = window.timelineModel

    # A light the show does not set is given a row, so it can be painted
    assert window.addLightRow("l_b")
    row = _row(model, "l_b")
    assert model.headerData(row, Qt.Orientation.Vertical) == "l_b  [light]"
    assert _cell(model, row, 0, Qt.ItemDataRole.BackgroundRole) is showViewer.UNSET_CELL_BRUSH
    window.ribbon.setColor((0, 255, 0))
    window.paintCells(["l_b"], 0, 1)
    assert _colorAt(window, "l_b", 0.1) == (0, 255, 0)
    assert not window.addLightRow("l_b")
    assert not window.addLightRow("  ")

    # The dialog offers the machine's lights and tags
    choices = []
    monkeypatch.setattr(showViewer.QInputDialog, "getItem", lambda *args: choices.append(args[3]) or ("(token)", True))
    window.ribbon.addLightButton.click()
    assert choices == [["gi", "l_a", "l_b"]]
    assert model.headerData(model.rowCount() - 1, Qt.Orientation.Vertical) == "(token)  [token]"
    monkeypatch.setattr(showViewer.QInputDialog, "getItem", lambda *args: ("", False))
    assert not window.addLightRow()

    # Added rows are forgotten when the shows are read again
    monkeypatch.setattr(showViewer.QMessageBox, "question", lambda *args: showViewer.QMessageBox.StandardButton.Discard)
    window.reloadShows()
    assert "(token)" not in [model.headerData(row, Qt.Orientation.Vertical) for row in range(model.rowCount())]


def test_choosingLightsOnThePlayfield(qtbot, tmp_path):
    window = _editWindow(qtbot, tmp_path)
    model = window.timelineModel
    view = window.playfieldView
    window.chooseLightsAction.setChecked(True)
    assert view.isSelectMode

    # Choosing lights chooses their rows over the whole show, adding a row for a light the show does not set
    view.selectLights(["l_b", "l_a"], notify=True)
    assert model.headerData(_row(model, "l_b"), Qt.Orientation.Vertical) == "l_b  [light]"
    assert window.selectedCells() == (["l_a", "l_b"], 0, model.columnCount() - 1)
    assert window.statusBar().currentMessage() == "Chose l_b, l_a from the playfield"

    # With cells chosen in the grid, the lights' rows are chosen over the same columns
    window.timelineView.clearSelection()
    _select(window, _row(model, "gi"), 2, 3)
    view.selectLights(["l_a"], notify=True)
    assert window.selectedCells() == (["l_a"], 2, 3)

    # The grid can show only the rows of the lights chosen
    window.onlyChosenAction.setChecked(True)
    assert window.timelineView.isRowHidden(_row(model, "gi"))
    assert not window.timelineView.isRowHidden(_row(model, "l_a"))
    window.ribbon.setColor((0, 0, 255))
    window.paintCells(["l_a"], 0, 0)
    assert window.timelineView.isRowHidden(_row(model, "gi"))
    view.selectLights([], notify=True)
    assert not window.timelineView.isRowHidden(_row(model, "gi"))
    assert window.selectedCells() is None
    view.selectLights(["l_b"], notify=True)
    window.onlyChosenAction.setChecked(False)
    assert not any(window.timelineView.isRowHidden(row) for row in range(model.rowCount()))

    # The chosen lights' rows can be chased in their order on the playfield
    view.selectLights(["l_a", "l_b"], notify=True)
    window.ribbon.setColor((255, 255, 255))
    assert window.chaseCells("top to bottom", "forward", 1.0)
    assert window.statusBar().currentMessage() == "Chased l_a, l_b from 0s to 2s"
    assert _colorAt(window, "l_a", 0.5) == (255, 255, 255)
    assert _colorAt(window, "l_b", 1.5) == (255, 255, 255)

    # Without a show nothing is chosen
    window.showList.clearShows(window.machinePath)
    window._displaySelectedShow()
    view.selectLights(["l_a"], notify=True)
    assert window.selectedCells() is None


def test_playfieldPreviewsPainting(qtbot, tmp_path):
    window = _editWindow(qtbot, tmp_path)
    window.resize(1400, 700)
    qtbot.waitExposed(window)
    model = window.timelineModel
    viewport = window.timelineView.viewport()
    playheadColors = (_lightColor(window, "l_a"), _lightColor(window, "l_b"))
    assert playheadColors == ((0, 0, 255), (255, 0, 0))

    def cellPoint(channelName: str, column: int):
        return window.timelineView.visualRect(model.index(_row(model, channelName), column)).center()

    def moveMouse(point):
        position = QPointF(point)
        QApplication.sendEvent(
            viewport,
            QMouseEvent(
                QEvent.Type.MouseMove,
                position,
                QPointF(viewport.mapToGlobal(point)),
                Qt.MouseButton.NoButton,
                Qt.MouseButton.NoButton,
                Qt.KeyboardModifier.NoModifier,
            ),
        )

    # With the select tool the playfield stays at the playhead
    moveMouse(cellPoint("l_a", 6))
    assert (_lightColor(window, "l_a"), _lightColor(window, "l_b")) == playheadColors

    # With the paint tool, the playfield follows the cell under the mouse, with its light in the paint color
    window.ribbon.setTool(TOOL_PAINT)
    window.ribbon.setColor((255, 0, 255))
    moveMouse(cellPoint("l_a", 6))
    assert _lightColor(window, "l_a") == (255, 0, 255)
    assert _lightColor(window, "l_b") == window.playfieldLights.lightColors(1.5)["l_b"][0]
    assert window.playfieldView.lightItems["l_a"].toolTip().endswith("Set by the paint tool")
    assert window.playTime == 0.0

    # A tag's row previews each of its lights, and the rows naming shows and the audio rows preview no light
    assert window.previewAt(cellPoint("gi", 0))
    assert (_lightColor(window, "l_a"), _lightColor(window, "l_b")) == ((255, 0, 255), (255, 0, 255))

    # While dragging, the lights of every row being dragged over are previewed
    window.addLightRow("l_b")
    window.ribbon.setColor((0, 255, 255))
    _select(window, _row(model, "l_a"), 1, 2, lastRow=_row(model, "l_b"))
    assert window.previewAt(cellPoint("l_a", 2), isDragging=True)
    assert (_lightColor(window, "l_a"), _lightColor(window, "l_b")) == ((0, 255, 255), (0, 255, 255))

    # Leaving the grid shows the playfield at the playhead again
    QApplication.sendEvent(viewport, QEvent(QEvent.Type.Leave))
    assert (_lightColor(window, "l_a"), _lightColor(window, "l_b")) == playheadColors
    assert not window.isPreviewing

    # With the erase tool the playfield only follows the time, and changing the tool ends the preview
    window.ribbon.setTool(TOOL_ERASE)
    assert window.previewAt(cellPoint("l_a", 6))
    assert _lightColor(window, "l_a") == window.playfieldLights.lightColors(1.5)["l_a"][0]
    window.ribbon.setTool(TOOL_SELECT)
    assert (_lightColor(window, "l_a"), _lightColor(window, "l_b")) == playheadColors
    assert not window.previewAt(QPoint(-5, -5))

    # Letting go of the mouse paints, and shows the playfield at the playhead
    window.ribbon.setTool(TOOL_PAINT)
    window.previewAt(cellPoint("l_a", 6))
    qtbot.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=cellPoint("l_a", 0))
    qtbot.waitUntil(lambda: _colorAt(window, "l_a", 0.1) == (0, 255, 255))
    assert _lightColor(window, "l_a") == (0, 255, 255)


def test_menusOfferTheRibbonsActions(qtbot, tmp_path):
    window = ShowViewerWindow(_machine(tmp_path))
    qtbot.addWidget(window)
    menus = {action.text().replace("&", ""): action.menu() for action in window.menuBar().actions()}
    assert list(menus) == ["File", "Edit", "View", "Playback", "Tools"]
    fileActions = menus["File"].actions()
    assert window.ribbon.openAction in fileActions and window.ribbon.saveAsAction in fileActions
    assert window.ribbon.undoAction in menus["Edit"].actions() and window.ribbon.copyAction in menus["Edit"].actions()
    assert window.playAction in menus["Playback"].actions()
    assert window.ribbon.chaseAction in menus["Tools"].actions()
    assert [window.ribbon.tabText(index) for index in range(window.ribbon.count())] == [
        "Home",
        "Cells",
        "Effects",
        "Playback",
        "View",
        "Playfield",
    ]

    # The actions have their shortcuts, and the ones for cells only act on the grid
    assert window.ribbon.saveAction.shortcut().matches(QKeySequence(QKeySequence.StandardKey.Save))
    assert window.ribbon.saveAsAction.shortcuts()
    assert window.ribbon.toolActions[TOOL_PAINT].shortcut() == QKeySequence("B")
    assert window.ribbon.copyAction.shortcutContext() == Qt.ShortcutContext.WidgetWithChildrenShortcut
    assert window.ribbon.copyAction in window.timelineView.actions()

    # Tools chosen from the menu are chosen in the ribbon
    window.ribbon.toolActions[TOOL_ERASE].trigger()
    assert window.ribbon.currentTool == TOOL_ERASE and window.ribbon.toolButtons[TOOL_ERASE].isChecked()


def test_viewMenuZoomsAndShowsParts(qtbot, tmp_path):
    window = ShowViewerWindow(_machine(tmp_path))
    qtbot.addWidget(window)
    window.show()
    width = window.zoomSlider.value()
    window.zoomInAction.trigger()
    assert window.zoomSlider.value() > width
    assert window.timelineView.horizontalHeader().defaultSectionSize() == window.zoomSlider.value()
    window.zoomOutAction.trigger()
    assert window.zoomSlider.value() == width

    window.showPlayfieldAction.setChecked(False)
    assert not window.playfieldPanel.isVisible()
    window.showListAction.setChecked(False)
    assert not window.showListPanel.isVisible()
    window.showRibbonAction.setChecked(False)
    assert not window.ribbon.isVisible()
    window.showRibbonAction.setChecked(True)
    assert window.ribbon.isVisible()

    # Cells can all be chosen, and cleared, from the Edit menu
    window.selectAllCellsAction.trigger()
    assert window.selectedCells() is not None
    window.clearSelectionAction.trigger()
    assert window.selectedCells() is None


def test_managerTabsOnTheLeftEdge(qtbot, tmp_path):
    window = ShowViewerWindow(_machine(tmp_path))
    qtbot.addWidget(window)
    tabs = window.managerTabs
    assert [tabs.tabText(index) for index in range(tabs.count())] == [
        "Project Manager",
        "Show Manager",
        "Hardware Manager",
        "Game Manager",
    ]
    assert tabs.shape() == QTabBar.Shape.RoundedWest
    assert tabs.currentIndex() == managerTabs.SHOW_MANAGER_TAB
    assert tabs.isTabEnabled(managerTabs.PROJECT_MANAGER_TAB)
    assert not tabs.isTabEnabled(managerTabs.HARDWARE_MANAGER_TAB)
    assert not tabs.isTabEnabled(managerTabs.GAME_MANAGER_TAB)

    # Asking for the File Manager keeps this window's tab chosen, as it is the Show Manager
    with qtbot.waitSignal(window.projectManagerRequested):
        tabs.tabBarClicked.emit(managerTabs.PROJECT_MANAGER_TAB)
    tabs.setCurrentIndex(managerTabs.PROJECT_MANAGER_TAB)
    qtbot.waitUntil(lambda: tabs.currentIndex() == managerTabs.SHOW_MANAGER_TAB)


def _treeLines(item, depth: int = 0) -> list[str]:
    lines = ["  " * depth + item.text(0)]
    for childIndex in range(item.childCount()):
        lines += _treeLines(item.child(childIndex), depth + 1)
    return lines


def test_showFilesAreListedWhereTheyAre(qtbot, tmp_path):
    machinePath = _machine(tmp_path)
    (machinePath / "shows" / "sub").mkdir()
    (machinePath / "shows" / "sub" / "deep.yaml").write_text("- duration: 1s\n  lights:\n    l_a: red\n")
    (machinePath / "config").mkdir()
    (machinePath / "config" / "config.yaml").write_text(
        "shows:\n  pulse_one:\n    - lights:\n        l_a: red\n  pulse_two:\n    - lights:\n        l_a: blue\n"
    )
    (machinePath / "modes" / "base" / "config").mkdir(parents=True)
    (machinePath / "modes" / "base" / "config" / "base.yaml").write_text(
        "shows:\n  base_show:\n    - lights:\n        l_a: lime\n"
    )
    # Folders of MPF files without shows are listed too, but not hidden folders or the machine's logs
    (machinePath / "sounds").mkdir()
    (machinePath / "sounds" / "boom.wav").write_bytes(b"")
    for skipped in ("logs", ".git"):
        (machinePath / skipped).mkdir()
        (machinePath / skipped / "notes.yaml").write_text("")
    (machinePath / "empty").mkdir()
    window = ShowViewerWindow(machinePath)
    qtbot.addWidget(window)
    explorer = window.showList
    tree = [line for index in range(explorer.topLevelItemCount()) for line in _treeLines(explorer.topLevelItem(index))]
    assert tree == [
        "machine",
        "  config",
        "    config.yaml",
        "      pulse_one",
        "      pulse_two",
        "  modes",
        "    base",
        "      config",
        "        base.yaml",
        "          base_show",
        "  shows",
        "    sub",
        "      deep",
        "    sample ⚠",
        "  sounds",
    ]
    # Only shows are listed, and a folder without shows is drawn faintly
    assert [item.text(0) for item in explorer.showItems()] == [
        "pulse_one",
        "pulse_two",
        "base_show",
        "deep",
        "sample ⚠",
    ]
    soundsFolder = explorer.topLevelItem(0).child(3)
    assert "No shows in this folder yet" in soundsFolder.toolTip(0)
    assert soundsFolder.foreground(0).color() != explorer.topLevelItem(0).child(2).foreground(0).color()
    assert window.selectedShow().name == "sample"
    deepItem = explorer.showItems()[3]
    assert deepItem.toolTip(0) == str(machinePath / "shows" / "sub" / "deep.yaml")

    # Choosing a folder, e.g. to fold it, keeps the show in the grid, and is where a new show is made
    configFolder = explorer.topLevelItem(0).child(0)
    explorer.setCurrentItem(configFolder)
    configFolder.setExpanded(False)
    assert window.selectedShow().name == "sample"
    assert window._selectedShowKey().endswith("\nsample")
    assert explorer.currentFolder() == machinePath / "config"
    explorer.setCurrentItem(configFolder.child(0))
    assert explorer.currentFolder() == machinePath / "config"

    # Folders stay folded when the shows are read again
    window.reloadShows()
    assert not explorer.topLevelItem(0).child(0).isExpanded()
    assert explorer.topLevelItem(0).child(2).isExpanded()
    window.collapseFoldersAction.trigger()
    assert not explorer.topLevelItem(0).isExpanded()
    window.expandFoldersAction.trigger()
    assert explorer.topLevelItem(0).child(0).isExpanded()

    # Choosing a show shows it, and a file opened from elsewhere is listed under Other files
    explorer.selectShowItem(deepItem := explorer.showItems()[3])
    assert explorer.currentFolder() == machinePath / "shows" / "sub"
    assert window.selectedShow().name == "deep"
    otherFile = tmp_path / "elsewhere" / "outer.yaml"
    otherFile.parent.mkdir()
    otherFile.write_text("- duration: 1s\n  lights:\n    l_a: white\n")
    window.openShowFile(otherFile)
    otherFolder = explorer.topLevelItem(1)
    assert _treeLines(otherFolder) == ["Other files", f"  {otherFile.parent}", "    outer"]
    assert window.selectedShow().name == "outer"


def test_explorerMovesShowsBetweenFiles(qtbot, tmp_path):
    from mpfmanager.ui.showExplorer import ShowExplorer

    explorer = ShowExplorer()
    qtbot.addWidget(explorer)
    explorer.clearShows(tmp_path)
    showFile = tmp_path / "shows" / "lights.yaml"

    class Named:
        def __init__(self, name):
            self.name = name

    # A file's lone show named after it is listed on its own, until the file has a second show
    first = explorer.addShow(showFile, Named("lights"), "lights", "first")
    assert first.parent().text(0) == "shows"
    second = explorer.addShow(showFile, Named("other"), "other", "second")
    assert first.parent().text(0) == "lights.yaml" and second.parent() is first.parent()

    # Moving a show to another file takes it out of the old file, and empty files and folders go with it
    explorer.selectShowItem(second)
    explorer.moveShow(second, tmp_path / "saved" / "other.yaml")
    assert second.parent().text(0) == "saved" and explorer.currentShowItem() is second
    explorer.moveShow(first, tmp_path / "saved" / "lights.yaml")
    assert [
        explorer.topLevelItem(0).child(index).text(0) for index in range(explorer.topLevelItem(0).childCount())
    ] == ["saved"]


def test_savingAConfigShowAsAFileKeepsTheConfigListed(qtbot, tmp_path, monkeypatch):
    machinePath = _machine(tmp_path)
    (machinePath / "config").mkdir()
    configFile = machinePath / "config" / "config.yaml"
    configFile.write_text(
        "shows:\n  pulse:\n    - lights:\n        l_a: red\n  other:\n    - lights:\n        l_a: blue\n"
    )
    window = ShowViewerWindow(machinePath)
    qtbot.addWidget(window)
    pulseItem = next(item for item in window.showList.showItems() if item.text(0) == "pulse")
    window.showList.selectShowItem(pulseItem)
    window.paintCells(["l_a"], 0, 0)
    assert not window.ribbon.saveAction.isEnabled()

    savedFile = machinePath / "shows" / "pulse.yaml"
    monkeypatch.setattr(showViewer.QFileDialog, "getSaveFileName", lambda *args: (str(savedFile), ""))
    assert window.saveShowAs()
    assert [item.text(0) for item in window.showList.showItemsOfFile(configFile)] == ["pulse", "other"]
    assert [item.text(0) for item in window.showList.showItemsOfFile(savedFile)] == ["pulse"]
    assert window.selectedShow().sourcePath == savedFile and not window.selectedShow().isInConfig
    configPulse = window.showList.showItemsOfFile(configFile)[0].data(0, showViewer.SHOW_ROLE)
    assert configPulse.isInConfig and configPulse is not window.selectedShow()
