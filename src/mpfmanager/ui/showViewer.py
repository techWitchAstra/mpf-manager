"""Show viewer window: an MPF show drawn as a light sequencing grid"""

#   showViewer - Responsible for the window that displays MPF show files as a
#       grid of channels (lights and show tokens) against time, in the style of
#       a Light-O-Rama sequence editor
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

import copy
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QAbstractTableModel,
    QElapsedTimer,
    QEvent,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPoint,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QAction, QActionGroup, QBrush, QColor, QFont, QIcon, QKeySequence, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSplitter,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mpfmanager.core import lightGroups, monitorManager, showEditor, showEffects, showManager
from mpfmanager.core.lightGroups import LightGroup
from mpfmanager.core.monitorManager import PlayfieldLights
from mpfmanager.core.showManager import ChannelSegment, ChannelState, MPFShow, ShowChannel, ShowStep, SoundPlay
from mpfmanager.ui.audioWaveform import WaveformLoader
from mpfmanager.ui.effectsPanel import EffectsPanel
from mpfmanager.ui.managerTabs import (
    PROJECT_MANAGER_TAB,
    SHOW_MANAGER_TAB,
    ManagerTabBar,
)
from mpfmanager.ui.playfieldView import PlayfieldView
from mpfmanager.ui.ribbon import actionButton, ribbonIcon
from mpfmanager.ui.showAudio import ShowAudio
from mpfmanager.ui.showExplorer import KEY_ROLE, LABEL_ROLE, SHOW_ROLE, ShowExplorer
from mpfmanager.ui.showTools import (
    TOOL_ERASE,
    TOOL_PAINT,
    TOOL_PICK,
    TOOL_SELECT,
    TOOL_SHORTCUTS,
    AddSoundDialog,
    ChaseDialog,
    NewShowDialog,
    RemoveSoundDialog,
    ReusableShowDialog,
    ShowRibbon,
)
from mpfmanager.ui.theme import sectionHeading

# The following are the grid timebases offered, the time each column covers, with None meaning the show's own
# suggested timebase.  Others can be typed in
RESOLUTIONS: dict[str, float | None] = {
    "Auto": None,
    "10 ms": 0.01,
    "25 ms": 0.025,
    "50 ms": 0.05,
    "100 ms": 0.1,
    "250 ms": 0.25,
    "500 ms": 0.5,
    "1 s": 1.0,
}

# The following keeps very long shows at very fine resolutions from making an enormous grid
MAX_GRID_COLUMNS = 20000

PREVIEW_OVERLAY_BRUSH = QBrush(QColor(128, 128, 128, 120), Qt.BrushStyle.BDiagPattern)
UNSET_CELL_BRUSH = QBrush(QColor(150, 150, 150), Qt.BrushStyle.Dense7Pattern)
TOKEN_CHANNEL_COLOR = QColor(160, 90, 220)
TOKEN_CELL_BRUSH = QBrush(QColor(160, 90, 220), Qt.BrushStyle.BDiagPattern)
STOP_CELL_BRUSH = QBrush(QColor(128, 128, 128), Qt.BrushStyle.Dense6Pattern)
INVALID_CELL_BRUSH = QBrush(QColor(220, 0, 0), Qt.BrushStyle.DiagCrossPattern)

# The following sets how the audio row looks: its height, background, and the colors of each sound's waveform
AUDIO_ROW_HEIGHT = 44
AUDIO_ROW_BACKGROUND = QColor(28, 30, 36)
AUDIO_CENTER_LINE_COLOR = QColor(80, 84, 96)
SOUND_COLORS = (
    QColor(80, 200, 255),
    QColor(255, 170, 60),
    QColor(140, 230, 110),
    QColor(240, 110, 200),
    QColor(250, 230, 90),
    QColor(170, 140, 255),
)

# The following sets how the rows under a light naming the shows that set it look: their height, the color of their
# label, and the colors each show is marked in
SOURCE_ROW_HEIGHT = 18
SOURCE_LABEL_COLOR = QColor(110, 110, 110)
SOURCE_COLORS = (
    QColor(196, 222, 255),
    QColor(255, 222, 186),
    QColor(204, 240, 196),
    QColor(250, 205, 235),
    QColor(250, 242, 180),
    QColor(222, 212, 255),
)

# The following is the data role that marks cells drawn in a token's preview color rather than a real color
PREVIEW_ROLE = Qt.ItemDataRole.UserRole + 1

# The following is the data role that marks the audio row, which is drawn as a waveform
AUDIO_ROLE = Qt.ItemDataRole.UserRole + 2

# The following is the data role that marks the column the playhead is in, and how it is drawn
PLAYHEAD_ROLE = Qt.ItemDataRole.UserRole + 3
PLAYHEAD_FILL = QColor(255, 255, 255, 90)
PLAYHEAD_PEN = QPen(QColor(255, 200, 0), 3)

# The following is the data role that gives, for a cell of the row under a light, the name of the show setting the
# light and the column where that show starts setting it, so the name can be drawn across all the show's cells
SOURCE_LABEL_ROLE = Qt.ItemDataRole.UserRole + 4

# The following are the playback speeds offered, and how often the playback moves on
PLAYBACK_SPEEDS = {"0.25×": 0.25, "0.5×": 0.5, "1×": 1.0, "2×": 2.0, "4×": 4.0}
PLAYBACK_INTERVAL_MS = 33
PLAY_TEXT = "Play"
PAUSE_TEXT = "Pause"

# The following is where the Effects tab sits in the ribbon, after the Cells tab, and how long a new effect lasts
# when no cells are chosen
EFFECTS_RIBBON_TAB = 2
DEFAULT_EFFECT_SECONDS = 1.0
# A new effect moves on at least this often, or as often as the grid's columns when they are finer, so its movement
# looks smooth
DEFAULT_EFFECT_STEP = 0.05
# How long an effect's settings stay unchanged before the lights it would give are worked out again
EFFECT_PREVIEW_DEBOUNCE_MS = 150
# The effect preview waits this long at the end of the effect before playing it again
EFFECT_PREVIEW_PAUSE = 0.3
# A light's size is across it, so a shape that reaches a quarter of its size from its middle covers its middle half
LIGHT_REACH = 0.25

# The following is how much zooming in or out widens or narrows the grid's columns
ZOOM_STEP = 4


# The following are the only data roles the grid answers, so the others are answered without working anything out
_GRID_ROLES = frozenset(
    {
        Qt.ItemDataRole.DisplayRole,
        Qt.ItemDataRole.BackgroundRole,
        Qt.ItemDataRole.ForegroundRole,
        Qt.ItemDataRole.ToolTipRole,
        PREVIEW_ROLE,
        AUDIO_ROLE,
        PLAYHEAD_ROLE,
        SOURCE_LABEL_ROLE,
    }
)


# The following gives an action the shortcuts of a standard key for this platform, along with any others given,
# leaving out ones that repeat, as a key given twice would be ambiguous
def _setShortcuts(action: QAction, standardKey: QKeySequence.StandardKey, *others: str) -> None:
    shortcuts = list(QKeySequence.keyBindings(standardKey))
    for other in others:
        if QKeySequence(other) not in shortcuts:
            shortcuts.append(QKeySequence(other))
    action.setShortcuts(shortcuts)


# The following makes a checkable action that shows and hides a part of the window
def _panelAction(text: str, panel: QWidget, parent: QObject) -> QAction:
    action = QAction(text, parent)
    action.setCheckable(True)
    action.setChecked(True)
    action.toggled.connect(panel.setVisible)
    return action


# The following formats a time in seconds for headers and tooltips
def _formatTime(seconds: float) -> str:
    return f"{seconds:.3f}".rstrip("0").rstrip(".") + "s"


# The following labels a typed timebase for the list, keeping a frame rate as typed alongside its time
def _timebaseLabel(text: str, seconds: float) -> str:
    label = f"{seconds * 1000:.3f}".rstrip("0").rstrip(".") + " ms"
    return f"{label} ({text.lower().replace(' ', '')})" if text.lower().endswith("fps") else label


# The following names a step in tooltips, where a step added by painting has no number in the show's file yet
def _stepLabel(step: ShowStep) -> str:
    return f"Step {step.stepNumber}" if step.stepNumber else "Added step"


# The following picks black or white text so it can be read on a cell's color
def _textColorFor(rgb: tuple[int, int, int]) -> QColor:
    red, green, blue = rgb
    return QColor(Qt.GlobalColor.black) if (red * 299 + green * 587 + blue * 114) / 1000 > 128 else QColor("white")


# The following draws cells, adding a light hatch over colors that are only a preview of a show token,
# and drawing the audio rows' cells as the waveform of their sound file
class _PreviewHatchDelegate(QStyledItemDelegate):
    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex
    ) -> None:
        model = index.model()
        sourceLabel = index.data(SOURCE_LABEL_ROLE)
        if index.data(AUDIO_ROLE) and isinstance(model, ShowTimelineModel):
            self._paintAudio(painter, option.rect, model, index.row(), index.column())
        elif sourceLabel is not None:
            self._paintSourceLabel(painter, option, index, *sourceLabel)
        else:
            super().paint(painter, option, index)
            if index.data(PREVIEW_ROLE):
                painter.fillRect(option.rect, PREVIEW_OVERLAY_BRUSH)
        if index.data(PLAYHEAD_ROLE):
            # The playhead's column is lightened, with a line down its left edge
            painter.save()
            painter.fillRect(option.rect, PLAYHEAD_FILL)
            painter.setPen(PLAYHEAD_PEN)
            painter.drawLine(option.rect.topLeft(), option.rect.bottomLeft())
            painter.restore()

    # The following draws a cell of the row under a light in its show's color, with the part of the show's name that
    # falls in the cell, so the name reads across all the cells the show sets the light in rather than being cut short
    def _paintSourceLabel(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex | QPersistentModelIndex,
        label: str,
        startColumn: int,
    ) -> None:
        rect = option.rect
        painter.save()
        painter.fillRect(rect, index.data(Qt.ItemDataRole.BackgroundRole))
        painter.setClipRect(rect)
        painter.setFont(option.font)
        painter.setPen(index.data(Qt.ItemDataRole.ForegroundRole))
        labelLeft = rect.left() - (index.column() - startColumn) * rect.width() + 3
        painter.drawText(
            QRect(labelLeft, rect.top(), max(rect.right() - labelLeft, 0) + 1, rect.height()),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            label,
        )
        painter.restore()

    # The following draws a slice of an audio row's sound: the peak level lightly, and the energy (rms) solidly over it
    def _paintAudio(self, painter: QPainter, rect: QRect, model: ShowTimelineModel, row: int, column: int) -> None:
        painter.save()
        painter.fillRect(rect, AUDIO_ROW_BACKGROUND)
        centerY = rect.center().y()
        halfHeight = max(rect.height() / 2 - 2, 1)
        painter.setPen(AUDIO_CENTER_LINE_COLOR)
        painter.drawLine(rect.left(), centerY, rect.right(), centerY)
        color = model.audioRows[row].color
        for levels in model.audioTraces(row, column, max(rect.width(), 1)):
            peakColor = QColor(color)
            peakColor.setAlpha(110)
            for pixel, level in enumerate(levels):
                if level is None:
                    continue
                x = rect.left() + pixel
                if level == "loading":
                    painter.fillRect(
                        x, rect.top() + 2, 1, rect.height() - 4, QBrush(color, Qt.BrushStyle.Dense5Pattern)
                    )
                    continue
                peak, energy = level
                painter.setPen(peakColor)
                painter.drawLine(x, int(centerY - peak * halfHeight), x, int(centerY + peak * halfHeight))
                painter.setPen(color)
                painter.drawLine(x, int(centerY - energy * halfHeight), x, int(centerY + energy * halfHeight))
        painter.restore()


# The following data class holds an audio row: a sound file, the sound names that play it, and its waveform color
@dataclass
class AudioRow:
    """One row of the audio rows, for one sound file"""

    soundFile: Path | None
    color: QColor
    soundNames: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.soundFile is not None:
            return self.soundFile.name
        return f"{self.soundNames[0]} (no file found)"


# The following data class holds a light row of the grid: a channel, or the row under it that names the shows the
# show plays that set it
@dataclass
class GridRow:
    """One light row of the grid"""

    channel: ShowChannel
    isSourceRow: bool = False


# The following model lays a show out as channels (rows) against time slices (columns)
class ShowTimelineModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.show: MPFShow | None = None
        self.resolution = showManager.MAX_RESOLUTION_SECONDS
        self.columnCountValue = 0
        self.stepStartColumns: dict[int, ShowStep] = {}
        self.soundFiles: dict[str, Path] = {}
        self.waveformLoader: WaveformLoader | None = None
        self.audioRows: list[AudioRow] = []
        self.playheadColumn: int | None = None
        self.gridRows: list[GridRow] = []
        self.extraChannelNames: list[str] = []
        # The rows naming the shows that set each light can be collapsed, to see more lights at once
        self.showSourceRows = True
        self.sourceColors: dict[str, QColor] = {}
        self._cellStates: dict[tuple[str, int], ChannelState] = {}
        self._sourceRunStarts: dict[tuple[str, int], int] = {}

    # The following moves the playhead to a column, redrawing the column it left and the one it moved to
    def setPlayheadColumn(self, column: int | None) -> None:
        if column == self.playheadColumn:
            return
        changedColumns = [changed for changed in (self.playheadColumn, column) if changed is not None]
        self.playheadColumn = column
        lastRow = self.rowCount() - 1
        for changed in changedColumns:
            if lastRow >= 0 and 0 <= changed < self.columnCountValue:
                self.dataChanged.emit(self.index(0, changed), self.index(lastRow, changed), [PLAYHEAD_ROLE])

    # The following gives the model the project's sound files and the loader that decodes them
    def setAudio(self, soundFiles: dict[str, Path], waveformLoader: WaveformLoader | None) -> None:
        self.soundFiles = soundFiles
        self.waveformLoader = waveformLoader

    # The following works out the audio rows: one for each sound file the show plays, in the order they first play
    def _buildAudioRows(self) -> None:
        rows: dict[str, AudioRow] = {}
        for play in self.show.soundPlays if self.show else []:
            soundFile = self.soundFiles.get(play.soundName)
            rowKey = str(soundFile) if soundFile else f"\0{play.soundName}"
            audioRow = rows.setdefault(rowKey, AudioRow(soundFile, SOUND_COLORS[len(rows) % len(SOUND_COLORS)]))
            if play.soundName not in audioRow.soundNames:
                audioRow.soundNames.append(play.soundName)
        self.audioRows = list(rows.values())

    @property
    def audioRowCount(self) -> int:
        return len(self.audioRows)

    # The following works out the light rows: a row for each channel, with a row under it when shows the show plays
    # set it, so it can be seen which show gives the light its colors.  Each of those shows is given its own color.
    # Rows can be kept in the order they had, so they do not move about while a show is being painted
    def _buildGridRows(self, keepRowOrder: bool = False) -> None:
        rowOrder = {gridRow.channel.name: index for index, gridRow in enumerate(self.gridRows)} if keepRowOrder else {}
        channels = list(self.show.channels) if self.show else []
        # Lights added to be painted have rows too, until the show sets them
        channelNames = {channel.name for channel in channels}
        channels += [
            ShowChannel(name, name.startswith("(")) for name in self.extraChannelNames if name not in channelNames
        ]
        channels.sort(key=lambda channel: rowOrder.get(channel.name, len(rowOrder)))
        self.gridRows = []
        self.sourceColors = {}
        for channel in channels:
            self.gridRows.append(GridRow(channel))
            showPaths = self.show.channelShowPaths(channel.name) if self.show else []
            if showPaths and self.showSourceRows:
                self.gridRows.append(GridRow(channel, isSourceRow=True))
            for showPath in showPaths:
                self.sourceColors.setdefault(showPath[-1], SOURCE_COLORS[len(self.sourceColors) % len(SOURCE_COLORS)])

    # The following returns the channel of a light row, or None for an audio row or a row naming shows
    def lightChannel(self, row: int) -> ShowChannel | None:
        gridIndex = row - self.audioRowCount
        if 0 <= gridIndex < len(self.gridRows) and not self.gridRows[gridIndex].isSourceRow:
            return self.gridRows[gridIndex].channel
        return None

    # The following returns the state of a light row's cell, for picking its color
    def cellState(self, row: int, column: int) -> ChannelState | None:
        channel = self.lightChannel(row)
        return self._channelState(channel.name, column) if channel is not None else None

    # The following returns whether a row is one naming the shows that set the light above it
    def isSourceRow(self, row: int) -> bool:
        gridIndex = row - self.audioRowCount
        return 0 <= gridIndex < len(self.gridRows) and self.gridRows[gridIndex].isSourceRow

    # The following redraws the audio rows, e.g. once a sound has been decoded
    def refreshAudio(self) -> None:
        if self.audioRowCount and self.columnCountValue:
            self.dataChanged.emit(
                self.index(0, 0), self.index(self.audioRowCount - 1, self.columnCountValue - 1), [AUDIO_ROLE]
            )
            self.headerDataChanged.emit(Qt.Orientation.Vertical, 0, self.audioRowCount - 1)

    def soundColor(self, soundName: str) -> QColor:
        for audioRow in self.audioRows:
            if soundName in audioRow.soundNames:
                return audioRow.color
        return SOUND_COLORS[0]

    # The following describes where a sound's file is and whether its waveform can be drawn
    def soundStatus(self, soundName: str) -> str:
        soundFile = self.soundFiles.get(soundName)
        if soundFile is None:
            return "no sound file found"
        if self.waveformLoader is not None and self.waveformLoader.hasFailed(soundFile):
            return f"{soundFile.name} could not be read"
        if self.waveformLoader is None or self.waveformLoader.waveform(soundFile) is None:
            return f"{soundFile.name}, reading…"
        return soundFile.name

    def _soundLength(self, play: SoundPlay) -> float | None:
        soundFile = self.soundFiles.get(play.soundName)
        waveform = self.waveformLoader.waveform(soundFile) if self.waveformLoader and soundFile else None
        return waveform.duration if waveform else None

    def _rowPlays(self, audioRow: AudioRow) -> list[SoundPlay]:
        return [play for play in self.show.soundPlays if play.soundName in audioRow.soundNames] if self.show else []

    # The following returns, for each play of an audio row's sound, its level at each pixel across a column,
    # as (peak, energy), "loading" while it has no waveform yet, or None where it is not playing
    def audioTraces(self, row: int, column: int, pixelCount: int) -> list[list[Any]]:
        if self.show is None or not 0 <= row < self.audioRowCount:
            return []
        audioRow = self.audioRows[row]
        waveform = (
            self.waveformLoader.waveform(audioRow.soundFile) if self.waveformLoader and audioRow.soundFile else None
        )
        traces: list[list[Any]] = []
        pixelSeconds = self.resolution / pixelCount
        columnStart = self.timeForColumn(column)
        for play in self._rowPlays(audioRow):
            levels: list[Any] = []
            for pixel in range(pixelCount):
                pixelTime = columnStart + pixel * pixelSeconds
                if waveform is None:
                    # Without a waveform the length is unknown, so the sound is marked from its start until stopped
                    isPlaying = pixelTime >= play.startTime and (play.stopTime is None or pixelTime < play.stopTime)
                    levels.append("loading" if isPlaying else None)
                    continue
                position = play.positionAt(pixelTime, waveform.duration)
                if position is None:
                    levels.append(None)
                    continue
                gain = min(play.gainAt(pixelTime, waveform.duration), 1.0)
                peak, energy = waveform.envelope(position, position + pixelSeconds)
                levels.append((peak * gain, energy * gain))
            if any(level is not None for level in levels):
                traces.append(levels)
        return traces

    def _audioTooltip(self, audioRow: AudioRow, sliceStart: float) -> str:
        lines = [f"{audioRow.label} at {_formatTime(sliceStart)}"]
        for play in self._rowPlays(audioRow):
            soundLength = self._soundLength(play)
            if soundLength is None:
                if sliceStart < play.startTime or (play.stopTime is not None and sliceStart >= play.stopTime):
                    continue
                lines.append(f"{play.soundName} ({self.soundStatus(play.soundName)})")
                continue
            position = play.positionAt(sliceStart, soundLength)
            if position is None:
                continue
            line = f"{play.soundName} at {_formatTime(position)} of {_formatTime(soundLength)}"
            line += f", step {play.stepNumber}" + (f" of show {play.showName}" if play.showName else "")
            lines.append(line)
        if len(lines) == 1:
            lines.append("Not playing")
        return "\n".join(lines)

    # The following swaps in a new show and/or resolution
    def setShow(
        self,
        show: MPFShow | None,
        resolution: float | None = None,
        keepRowOrder: bool = False,
        extraChannelNames: list[str] | None = None,
    ) -> None:
        self.beginResetModel()
        self.extraChannelNames = list(extraChannelNames or [])
        self.show = show
        self.playheadColumn = None
        self._cellStates = {}
        self._sourceRunStarts = {}
        self._buildAudioRows()
        self._buildGridRows(keepRowOrder)
        if show is not None:
            self.resolution = resolution or show.suggestedResolution()
            # Finer resolutions are coarsened for long shows so the grid stays a usable size
            if show.totalDuration / self.resolution > MAX_GRID_COLUMNS:
                self.resolution = show.totalDuration / MAX_GRID_COLUMNS
            self.columnCountValue = max(1, math.ceil(round(show.totalDuration / self.resolution, 6)))
            self.stepStartColumns = {self.columnForTime(step.startTime): step for step in show.steps}
        else:
            self.columnCountValue = 0
            self.stepStartColumns = {}
        self.endResetModel()

    def columnForTime(self, seconds: float) -> int:
        return int(round(seconds / self.resolution, 6))

    def timeForColumn(self, column: int) -> float:
        return column * self.resolution

    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() or self.show is None else len(self.gridRows) + self.audioRowCount

    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else self.columnCountValue

    # The following returns what a grid cell shows: its color, and the token or command it is set to
    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role not in _GRID_ROLES or self.show is None or not index.isValid():
            return None
        if role == PLAYHEAD_ROLE:
            return index.column() == self.playheadColumn
        sliceStart = self.timeForColumn(index.column())
        if index.row() < self.audioRowCount:
            audioRow = self.audioRows[index.row()]
            if role == AUDIO_ROLE:
                return True
            if role == Qt.ItemDataRole.BackgroundRole:
                return QBrush(AUDIO_ROW_BACKGROUND)
            return self._audioTooltip(audioRow, sliceStart) if role == Qt.ItemDataRole.ToolTipRole else None
        gridRow = self.gridRows[index.row() - self.audioRowCount]
        channel = gridRow.channel
        state = self._channelState(channel.name, index.column())
        if gridRow.isSourceRow:
            return self._sourceData(channel.name, index.column(), state, role)
        segment = state.segment
        if segment is None:
            # Cells before the show first sets a channel are dotted, so they are not mistaken for white or off
            if role == Qt.ItemDataRole.BackgroundRole:
                return UNSET_CELL_BRUSH
            return self._emptyCellTooltip(channel.name, sliceStart) if role == Qt.ItemDataRole.ToolTipRole else None
        setting = segment.setting
        isFirstColumn = self.columnForTime(segment.startTime) == index.column()

        if role == Qt.ItemDataRole.BackgroundRole:
            if state.rgb is not None:
                return QBrush(QColor(*state.rgb))
            return {"token": TOKEN_CELL_BRUSH, "stop": STOP_CELL_BRUSH}.get(setting.kind, INVALID_CELL_BRUSH)
        if role == Qt.ItemDataRole.DisplayRole:
            # The value is written where a token, stop or invalid color starts, since it has no color to show
            return setting.value if isFirstColumn and setting.rgb is None else None
        if role == Qt.ItemDataRole.ForegroundRole:
            return _textColorFor(state.rgb) if state.rgb is not None else None
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._cellTooltip(channel.name, sliceStart, segment, state.rgb, state.isFading)
        if role == PREVIEW_ROLE:
            return setting.kind == "preview"
        return None

    # The following works out each cell's state once, as a cell is asked about several roles every time it is drawn,
    # and a light's row and the row under it naming its shows both use it
    def _channelState(self, channelName: str, column: int) -> ChannelState:
        if self.show is None:
            return ChannelState(None, None)
        cellKey = (channelName, column)
        state = self._cellStates.get(cellKey)
        if state is None:
            state = self._cellStates[cellKey] = self.show.channelState(channelName, self.timeForColumn(column))
        return state

    # The following returns what a cell of the row under a light shows: the show the show plays that gives the light
    # its color at that time, named where it starts.  Cells where the show's own steps set the light are left empty
    def _sourceData(self, channelName: str, column: int, state: ChannelState, role: int) -> Any:
        segment = state.segment
        sliceStart = self.timeForColumn(column)
        if segment is None or not segment.isFromOtherShow:
            if role == Qt.ItemDataRole.ToolTipRole:
                setBy = "Set by this show's own steps" if segment is not None else "Not set by a show"
                return f"{channelName} at {_formatTime(sliceStart)}\n{setBy}"
            return None
        showName = segment.showPath[-1]
        if role == Qt.ItemDataRole.BackgroundRole:
            return QBrush(self.sourceColors.get(showName, SOURCE_COLORS[0]))
        if role == Qt.ItemDataRole.ForegroundRole:
            return QColor(Qt.GlobalColor.black)
        if role == Qt.ItemDataRole.DisplayRole:
            # The show is named where it starts giving the light its color, rather than in every cell
            return " › ".join(segment.showPath) if self._sourceRunStart(channelName, column) == column else None
        if role == SOURCE_LABEL_ROLE:
            return " › ".join(segment.showPath), self._sourceRunStart(channelName, column)
        if role == Qt.ItemDataRole.ToolTipRole:
            lines = [f"{channelName} at {_formatTime(sliceStart)}", f"Set by show {showName}"]
            if len(segment.showPath) > 1:
                lines.append("Played by " + " › ".join(segment.showPath[:-1]))
            lines.append(f"{_stepLabel(segment.step)} of {showName}: {segment.setting.value}")
            return "\n".join(lines)
        return None

    # The following returns the column where the show setting a light at a column started setting it, remembering the
    # columns worked out so a long run of cells is only walked through once
    def _sourceRunStart(self, channelName: str, column: int) -> int:
        segment = self._channelState(channelName, column).segment
        showPath = segment.showPath if segment is not None else ()
        walked: list[int] = []
        runStart = column
        while (channelName, runStart) not in self._sourceRunStarts:
            previous = self._channelState(channelName, runStart - 1).segment if runStart > 0 else None
            if previous is None or previous.showPath != showPath:
                self._sourceRunStarts[(channelName, runStart)] = runStart
                break
            walked.append(runStart)
            runStart -= 1
        runStart = self._sourceRunStarts[(channelName, runStart)]
        for walkedColumn in walked:
            self._sourceRunStarts[(channelName, walkedColumn)] = runStart
        return runStart

    def _emptyCellTooltip(self, channelName: str, sliceStart: float) -> str:
        return f"{channelName} at {_formatTime(sliceStart)}\nNot set by a show"

    def _cellTooltip(
        self,
        channelName: str,
        sliceStart: float,
        segment: ChannelSegment,
        rgb: tuple[int, int, int] | None,
        isFading: bool,
    ) -> str:
        setting = segment.setting
        lines = [f"{channelName} at {_formatTime(sliceStart)}"]
        if segment.showName:
            lines.append(f"From show {segment.showName}")
        lines.append(f"{_stepLabel(segment.step)}: {setting.value}")
        if setting.fadeMs:
            lines.append(f"Fade: {setting.fadeMs} ms" + (" (fading)" if isFading else ""))
        elif setting.fadeText:
            # A fade that is a show token without a value, or not a time, is drawn as no fade
            lines.append(f"Fade: {setting.fadeText} (not drawn)")
        if setting.kind == "preview" and rgb is not None:
            lines.append("Preview color: #{:02x}{:02x}{:02x}".format(*rgb))
            lines.append("The color is a show token, drawn in the preview color as no value is given for it")
        elif rgb is not None:
            lines.append("Color: #{:02x}{:02x}{:02x}".format(*rgb))
        elif setting.kind == "token":
            lines.append("Show token, replaced by show_tokens when the show is played")
        elif setting.kind == "stop":
            lines.append("Removes the show's color from the light")
        else:
            lines.append("Not a color MPF understands")
        return "\n".join(lines)

    # The following labels an audio row with its sound file's name, in the color its waveform is drawn in
    def _audioHeaderData(self, audioRow: AudioRow, role: int) -> Any:
        if role == Qt.ItemDataRole.DisplayRole:
            return f"♪ {audioRow.label}"
        if role == Qt.ItemDataRole.ToolTipRole:
            return "\n".join(f"Sound {name}: {self.soundStatus(name)}" for name in audioRow.soundNames)
        if role == Qt.ItemDataRole.ForegroundRole:
            return audioRow.color.darker(130)
        if role == Qt.ItemDataRole.FontRole:
            font = QFont()
            font.setBold(True)
            return font
        return None

    # The following labels the row under a light that names the shows setting it
    def _sourceHeaderData(self, channel: ShowChannel, role: int) -> Any:
        if role == Qt.ItemDataRole.DisplayRole:
            return "    ↳ from show"
        if role == Qt.ItemDataRole.ForegroundRole:
            return SOURCE_LABEL_COLOR
        if role == Qt.ItemDataRole.FontRole:
            font = QFont()
            font.setItalic(True)
            return font
        if role == Qt.ItemDataRole.ToolTipRole and self.show is not None:
            showNames = ", ".join(" › ".join(path) for path in self.show.channelShowPaths(channel.name))
            return (
                f"The shows played by this show that set {channel.name}: {showNames}\n"
                "Empty cells are set by this show's own steps"
            )
        return None

    # The following labels the channel column with the light or show token, and time columns where steps start
    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if self.show is None:
            return None
        if orientation == Qt.Orientation.Vertical:
            if section < self.audioRowCount:
                return self._audioHeaderData(self.audioRows[section], role)
            section -= self.audioRowCount
            if section >= len(self.gridRows):
                return None
            gridRow = self.gridRows[section]
            channel = gridRow.channel
            if gridRow.isSourceRow:
                return self._sourceHeaderData(channel, role)
            if role == Qt.ItemDataRole.DisplayRole:
                return f"{channel.name}  [{'token' if channel.isToken else 'light'}]"
            if role == Qt.ItemDataRole.ForegroundRole and channel.isToken:
                return TOKEN_CHANNEL_COLOR
            if role == Qt.ItemDataRole.FontRole and channel.isToken:
                font = QFont()
                font.setItalic(True)
                return font
            if role == Qt.ItemDataRole.ToolTipRole:
                if channel.isToken:
                    tooltip = f"Show token {channel.name}: the lights are given by show_tokens when the show is played"
                else:
                    tooltip = f"Light or light tag {channel.name}"
                # With the rows naming the shows collapsed, the light's own tooltip says which shows set it
                showPaths = self.show.channelShowPaths(channel.name) if self.show and not self.showSourceRows else []
                if showPaths:
                    tooltip += "\nThe shows played by this show that set it: " + ", ".join(
                        " › ".join(path) for path in showPaths
                    )
                return tooltip
            return None

        step = self.stepStartColumns.get(section)
        if role == Qt.ItemDataRole.DisplayRole:
            return _formatTime(self.timeForColumn(section)) if step is not None else ""
        if role == Qt.ItemDataRole.ToolTipRole:
            tooltip = _formatTime(self.timeForColumn(section))
            if step is not None:
                tooltip += f"\n{_stepLabel(step)}" + (" (holds until advanced)" if step.isHold else "")
                if step.shows:
                    tooltip += "\nPlays shows: " + ", ".join(step.shows)
                if step.otherSections:
                    tooltip += "\nAlso plays: " + ", ".join(step.otherSections)
            return tooltip
        return None


# The following is the separate window for viewing the show files of a project, or any show file
class ShowViewerWindow(QMainWindow):
    projectManagerRequested = Signal()

    # The window is a page of MPF-Manager's window when embedded, which then gives it its manager tabs and menus
    def __init__(self, machinePath: Path | None = None, parent: QWidget | None = None, embedded: bool = False):
        super().__init__(parent)
        self.isEmbedded = embedded
        if not embedded:
            self.setWindowFlag(Qt.WindowType.Window)
        self.setWindowTitle("MPF Show Viewer")
        self.resize(1500, 760)
        self.machinePath = machinePath
        self.extraShowFiles: list[Path] = []
        self.library: dict[str, MPFShow] = {}
        self.tokenValues: dict[str, dict[str, str]] = {}
        self.previewRGB = showManager.DEFAULT_PREVIEW_RGB
        self.soundFiles: dict[str, Path] = {}
        self.namedColors: dict[str, tuple[int, int, int]] = {}
        self.waveformLoader = WaveformLoader(self)
        self.playfieldLights = PlayfieldLights(None, {})
        self.playfieldMachine: Path | None = None
        self.playTime = 0.0
        self.playTimer = QTimer(self)
        self.playTimer.setInterval(PLAYBACK_INTERVAL_MS)
        self.playTimer.timeout.connect(self._advancePlayback)
        self.playClock = QElapsedTimer()
        self.histories: dict[str, showEditor.EditHistory] = {}
        self.lightClip: showEditor.LightClip | None = None
        self.extraRows: dict[str, list[str]] = {}
        # The lighting effects drawn for each show, kept while the window is open
        self.effects: dict[str, list[showEffects.LightEffect]] = {}
        self.unsavedKeys: set[str] = set()

        # The following is the ribbon, with a tab of tools for each type of item.  The show, painting and cell tools
        # are its own, and the tabs for playback, the view and the playfield are added below
        self.ribbon = ShowRibbon()
        self.ribbon.toolChanged.connect(self._toolChanged)
        self.ribbon.openAction.triggered.connect(self.browseShowFile)
        self.ribbon.newShowAction.triggered.connect(lambda: self.openNewShowDialog())
        self.ribbon.reloadAction.triggered.connect(self.reloadShows)
        self.ribbon.saveAction.triggered.connect(self.saveShow)
        self.ribbon.saveAsAction.triggered.connect(self.saveShowAs)
        self.ribbon.undoAction.triggered.connect(self.undo)
        self.ribbon.redoAction.triggered.connect(self.redo)
        self.ribbon.copyAction.triggered.connect(self.copyCells)
        self.ribbon.pasteAction.triggered.connect(self.pasteCells)
        self.ribbon.repeatAction.triggered.connect(lambda: self.repeatCells())
        self.ribbon.repeatOnceAction.triggered.connect(lambda: self.repeatCells(1))
        self.ribbon.chaseAction.triggered.connect(self.openChaseDialog)
        self.ribbon.makeShowAction.triggered.connect(self.openMakeShowDialog)
        self.ribbon.addLightAction.triggered.connect(lambda: self.addLightRow())
        self.ribbon.removeLightAction.triggered.connect(lambda: self.removeLightRows())
        self.openShowButton = self.ribbon.openButton
        self.refreshButton = self.ribbon.reloadButton

        # The following lists the shows that can be viewed
        self.showList = ShowExplorer()
        self.showList.showChanged.connect(self._showChanged)

        # The following lets values be given for the selected show's tokens, as show_tokens would when it is played
        self.tokenTable = QTableWidget(0, 2)
        self.tokenTable.setHorizontalHeaderLabels(["Token", "Value"])
        self.tokenTable.verticalHeader().setVisible(False)
        self.tokenTable.verticalHeader().setDefaultSectionSize(22)
        self.tokenTable.horizontalHeader().setStretchLastSection(True)
        self.tokenTable.setToolTip(
            "Give a value to a token to see the show as it plays with it, e.g. a light name, a list of lights, or a color"
        )
        self.tokenTable.itemChanged.connect(self._tokenValueChanged)

        self.showListPanel = QWidget()
        showListLayout = QVBoxLayout(self.showListPanel)
        showListLayout.setContentsMargins(0, 0, 0, 0)
        showListLayout.addWidget(sectionHeading("Show files"))
        showListLayout.addWidget(self.showList, 2)
        showListLayout.addWidget(sectionHeading("Show token values"))
        showListLayout.addWidget(self.tokenTable, 1)

        # The following builds the channel against time grid
        self.timelineModel = ShowTimelineModel(self)
        self.timelineView = QTableView()
        self.timelineView.setModel(self.timelineModel)
        self.timelineView.setItemDelegate(_PreviewHatchDelegate(self.timelineView))
        self.waveformLoader.waveformReady.connect(self._waveformReady)
        # Cells can be chosen by dragging over them, for the tools to use
        self.timelineView.setSelectionMode(QAbstractItemView.SelectionMode.ContiguousSelection)
        self.timelineView.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.timelineView.setShowGrid(True)
        self.timelineView.setWordWrap(False)
        self.timelineView.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.timelineView.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.timelineView.horizontalHeader().setMinimumSectionSize(1)
        self.timelineView.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        self.timelineView.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.timelineView.verticalHeader().setDefaultSectionSize(22)
        self.timelineView.verticalHeader().setMinimumSectionSize(SOURCE_ROW_HEIGHT)
        self.timelineView.verticalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.timelineView.viewport().installEventFilter(self)
        # The mouse is followed over the grid, so the playfield can preview painting where it is
        self.timelineView.viewport().setMouseTracking(True)
        self.isPreviewing = False

        # The following are the playback actions: play and pause, back to the start, and looping
        self.playAction = QAction(ribbonIcon(QIcon.ThemeIcon.MediaPlaybackStart, "▶"), PLAY_TEXT, self)
        self.playAction.setToolTip("Play or pause the show (Space)")
        self.playAction.triggered.connect(self.togglePlayback)
        self.rewindAction = QAction(ribbonIcon(QIcon.ThemeIcon.MediaSkipBackward, "⏮"), "Back to start", self)
        self.rewindAction.setToolTip("Back to the start of the show (Home)")
        self.rewindAction.triggered.connect(lambda: self.setPlayTime(0.0))
        self.loopAction = QAction(ribbonIcon(QIcon.ThemeIcon.MediaPlaylistRepeat, "🔁"), "Loop", self)
        self.loopAction.setCheckable(True)
        self.loopAction.setChecked(True)
        self.loopAction.setToolTip("Start the show again when it reaches the end")
        self.speedOption = QComboBox()
        for label, speed in PLAYBACK_SPEEDS.items():
            self.speedOption.addItem(label, speed)
        self.speedOption.setCurrentIndex(list(PLAYBACK_SPEEDS.values()).index(1.0))
        self.speedOption.setToolTip("How fast the show plays")

        # The transport, above the grid, moves through the show
        self.rewindButton = actionButton(self.rewindAction)
        self.rewindButton.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.playButton = actionButton(self.playAction)
        self.playButton.setMinimumWidth(80)
        self.timeSlider = QSlider(Qt.Orientation.Horizontal)
        self.timeSlider.setToolTip("Drag to move through the show")
        self.timeSlider.valueChanged.connect(lambda milliseconds: self.setPlayTime(milliseconds / 1000))
        self.timeLabel = QLabel()
        # The transport sits on a panel of its own, so it is easy to find above the grid
        self.transportCard = QWidget()
        self.transportCard.setObjectName("toolCard")
        self.transportCard.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        transportControls = QHBoxLayout(self.transportCard)
        transportControls.setContentsMargins(6, 2, 8, 2)
        transportControls.addWidget(self.rewindButton)
        transportControls.addWidget(self.playButton)
        transportControls.addWidget(self.timeSlider, 1)
        transportControls.addWidget(self.timeLabel)

        playbackTab = self.ribbon.addRibbonTab("Playback")
        transportGroup = playbackTab.addGroup("Transport")
        transportGroup.addLargeAction(self.playAction)
        transportGroup.addLargeAction(self.rewindAction)
        playOptionsGroup = playbackTab.addGroup("Options")
        playOptionsGroup.addSmallWidget(self.speedOption, "Speed:")
        playOptionsGroup.addSmallAction(self.loopAction)

        # The following hears the show's sounds as it plays, and puts sounds in the show or takes them out
        self.showAudio = ShowAudio(parent=self)
        self.hearSoundsAction = QAction(ribbonIcon(QIcon.ThemeIcon.AudioVolumeHigh, "🔊"), "Hear sounds", self)
        self.hearSoundsAction.setCheckable(True)
        self.hearSoundsAction.setChecked(True)
        self.hearSoundsAction.setToolTip("Play the show's sounds while it plays")
        self.hearSoundsAction.toggled.connect(self.showAudio.setEnabled)
        self.volumeSlider = QSlider(Qt.Orientation.Horizontal)
        self.volumeSlider.setRange(0, 100)
        self.volumeSlider.setValue(80)
        self.volumeSlider.setMinimumWidth(110)
        self.volumeSlider.setToolTip("How loud the show's sounds are played")
        self.volumeSlider.valueChanged.connect(lambda value: self.showAudio.setVolume(value / 100))
        self.showAudio.setVolume(self.volumeSlider.value() / 100)
        self.addSoundAction = QAction(ribbonIcon(None, "♪"), "Add sound…", self)
        self.addSoundAction.setToolTip("Make the show play one of the machine's sounds, at the playhead or a time")
        self.addSoundAction.triggered.connect(lambda: self.openAddSoundDialog())
        self.removeSoundAction = QAction(ribbonIcon(QIcon.ThemeIcon.EditDelete, "✕"), "Remove sound…", self)
        self.removeSoundAction.setToolTip("Take a sound the show plays out of it")
        self.removeSoundAction.triggered.connect(lambda: self.openRemoveSoundDialog())
        audioGroup = playbackTab.addGroup("Audio")
        audioGroup.addLargeAction(self.addSoundAction)
        audioGroup.addSmallAction(self.removeSoundAction)
        audioGroup.addSmallAction(self.hearSoundsAction)
        audioGroup.addSmallWidget(self.volumeSlider, "Volume:")

        # Clicking a time column, or its time in the ruler, moves the playhead there
        self.timelineView.clicked.connect(self._cellClicked)
        self.timelineView.horizontalHeader().sectionClicked.connect(
            lambda column: self.setPlayTime(self.timelineModel.timeForColumn(column))
        )

        # The following are the grid's timebase and zoom controls.  A timebase can be chosen or typed in, e.g. 40ms,
        # 0.5s or 30fps, and a typed one is added to the list
        self.resolutionOption = QComboBox()
        for label, seconds in RESOLUTIONS.items():
            self.resolutionOption.addItem(label, seconds)
        self.resolutionOption.setEditable(True)
        self.resolutionOption.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.resolutionOption.setMinimumWidth(150)
        self.resolutionOption.setToolTip(
            "The time each grid column covers. Choose one, or type your own, e.g. 40ms, 0.5s, 33 (milliseconds) or 30fps"
        )
        timebaseEdit = self.resolutionOption.lineEdit()
        assert timebaseEdit is not None
        timebaseEdit.setPlaceholderText("e.g. 40ms or 30fps")
        timebaseEdit.editingFinished.connect(self._timebaseEntered)
        self.resolutionOption.currentIndexChanged.connect(self._displaySelectedShow)
        # A timebase that cannot be used is explained in the status bar, so it is seen whichever tab is open
        self.timebaseMessage = QLabel()
        self.timebaseMessage.setStyleSheet("color: #c0392b;")
        self.statusBar().addPermanentWidget(self.timebaseMessage)
        self.timebaseMessage.hide()
        self.zoomSlider = QSlider(Qt.Orientation.Horizontal)
        self.zoomSlider.setRange(4, 80)
        self.zoomSlider.setValue(24)
        self.zoomSlider.setMinimumWidth(120)
        self.zoomSlider.setMaximumWidth(200)
        self.zoomSlider.setToolTip("How wide each grid column is drawn")
        self.zoomSlider.valueChanged.connect(self._applyZoom)
        self.zoomInAction = QAction(ribbonIcon(QIcon.ThemeIcon.ZoomIn, "+"), "Zoom in", self)
        self.zoomInAction.setToolTip("Draw the grid's columns wider")
        self.zoomInAction.triggered.connect(lambda: self.zoomBy(ZOOM_STEP))
        self.zoomOutAction = QAction(ribbonIcon(QIcon.ThemeIcon.ZoomOut, "−"), "Zoom out", self)
        self.zoomOutAction.setToolTip("Draw the grid's columns narrower")
        self.zoomOutAction.triggered.connect(lambda: self.zoomBy(-ZOOM_STEP))

        # The following draws color tokens without a value in a preview color, so their brightness steps can be seen
        self.previewTokensAction = QAction(ribbonIcon(None, "◐"), "Preview tokens", self)
        self.previewTokensAction.setCheckable(True)
        self.previewTokensAction.setChecked(True)
        self.previewTokensAction.setToolTip("Draw color tokens that have no value in the preview color")
        self.previewTokensAction.toggled.connect(self._displaySelectedShow)
        self.previewColorAction = QAction("Preview color…", self)
        self.previewColorAction.setToolTip("Choose the color tokens with no value are drawn in")
        self.previewColorAction.triggered.connect(self.choosePreviewColor)
        self.previewColorButton = QPushButton()
        self.previewColorButton.setToolTip("Choose the preview color")
        self.previewColorButton.clicked.connect(self.choosePreviewColor)
        self._updatePreviewColorButton()

        # The following collapses the rows under the lights that name the shows setting them, e.g. ↳ from attract
        self.showSourceRowsAction = QAction(ribbonIcon(None, "↳"), "Where cells come from", self)
        self.showSourceRowsAction.setCheckable(True)
        self.showSourceRowsAction.setChecked(True)
        self.showSourceRowsAction.setToolTip(
            "Show the rows under each light naming the show that sets it, e.g. ↳ from attract. "
            "Untick to collapse them and see more lights at once"
        )
        self.showSourceRowsAction.toggled.connect(self.setSourceRowsShown)

        viewTab = self.ribbon.addRibbonTab("View")
        gridGroup = viewTab.addGroup("Grid")
        gridGroup.addSmallWidget(self.resolutionOption, "Timebase:")
        gridGroup.addSmallWidget(self.zoomSlider, "Zoom:")
        zoomGroup = viewTab.addGroup("Zoom")
        zoomGroup.addLargeAction(self.zoomInAction)
        zoomGroup.addLargeAction(self.zoomOutAction)
        tokensGroup = viewTab.addGroup("Show tokens")
        tokensGroup.addSmallAction(self.previewTokensAction)
        tokensGroup.addSmallWidget(self.previewColorButton, "In:")
        rowsGroup = viewTab.addGroup("Rows")
        rowsGroup.addSmallAction(self.showSourceRowsAction)

        # The following is the playfield, drawn from MPF-Monitor's layout, with a choice of the machine's layout files
        self.playfieldView = PlayfieldView()
        self.monitorConfigOption = QComboBox()
        self.monitorConfigOption.setMinimumWidth(140)
        self.monitorConfigOption.setToolTip("The MPF-Monitor layout to draw, from the machine's monitor folder")
        self.monitorConfigOption.currentIndexChanged.connect(self._loadMonitorLayout)
        self.playfieldSummary = QLabel()
        self.playfieldSummary.setWordWrap(True)

        # The following choose lights on the playfield, which chooses their rows in the grid to be painted
        self.chooseLightsAction = QAction(ribbonIcon(None, "◎"), "Choose lights", self)
        self.chooseLightsAction.setCheckable(True)
        self.chooseLightsAction.setToolTip(
            "Click lights on the playfield, or drag a box around them, to choose their rows in the grid"
        )
        self.chooseLightsAction.toggled.connect(self.playfieldView.setSelectMode)
        self.onlyChosenAction = QAction("Only chosen lights in the grid", self)
        self.onlyChosenAction.setCheckable(True)
        self.onlyChosenAction.setToolTip("Show only the rows of the lights chosen on the playfield")
        self.onlyChosenAction.toggled.connect(self._applyLightFilter)
        self.playfieldView.lightsSelected.connect(self.chooseLightRows)

        playfieldTab = self.ribbon.addRibbonTab("Playfield")
        layoutGroup = playfieldTab.addGroup("Layout")
        layoutGroup.addSmallWidget(self.monitorConfigOption, "Playfield:")
        lightsGroup = playfieldTab.addGroup("Lights")
        lightsGroup.addLargeAction(self.chooseLightsAction)
        lightsGroup.addSmallAction(self.onlyChosenAction)
        self._buildLightGroups(playfieldTab)

        self._buildEffects()

        # The playfield shares its panel with the effects' settings, shown while the Effects tab is chosen
        self.playfieldSplitter = QSplitter(Qt.Orientation.Vertical)
        self.playfieldSplitter.addWidget(self.playfieldView)
        self.playfieldSplitter.addWidget(self.effectsPanel)
        self.playfieldSplitter.setSizes([340, 440])
        self.effectsPanel.hide()
        self.playfieldPanel = QWidget()
        playfieldLayout = QVBoxLayout(self.playfieldPanel)
        playfieldLayout.setContentsMargins(0, 0, 0, 0)
        playfieldLayout.addWidget(self.playfieldSplitter, 1)
        playfieldLayout.addWidget(self.playfieldSummary)

        # The following shows details and any problems found in the show
        self.showSummary = QLabel()
        self.showSummary.setWordWrap(True)
        self.showSummary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        gridPanel = QWidget()
        gridLayout = QVBoxLayout(gridPanel)
        gridLayout.setContentsMargins(0, 0, 0, 0)
        gridLayout.addWidget(self.transportCard)
        gridLayout.addWidget(self.timelineView, 1)
        gridLayout.addWidget(self.showSummary)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.showListPanel)
        splitter.addWidget(gridPanel)
        splitter.addWidget(self.playfieldPanel)
        splitter.setSizes([220, 760, 380])

        centralWidget = QWidget()
        centralLayout = QVBoxLayout(centralWidget)
        centralLayout.setContentsMargins(4, 0, 4, 4)
        centralLayout.addWidget(self.ribbon)
        centralLayout.addWidget(splitter, 1)

        # The following are the managers along the left edge, with this window's Show Manager chosen
        self.managerTabs = ManagerTabBar(SHOW_MANAGER_TAB)
        self.managerTabs.managerChosen.connect(self._managerTabClicked)
        self.managerTabs.setVisible(not embedded)

        windowWidget = QWidget()
        windowLayout = QHBoxLayout(windowWidget)
        windowLayout.setContentsMargins(0, 0, 0, 0)
        windowLayout.setSpacing(0)
        windowLayout.addWidget(self.managerTabs, 0, Qt.AlignmentFlag.AlignTop)
        windowLayout.addWidget(centralWidget, 1)
        self.setCentralWidget(windowWidget)

        self._buildMenus()
        self.reloadShows()

    # The following builds the menus: the show file, editing, the view, playback and the tools, each with the
    # shortcuts of its actions.  The actions are the ribbon's, so a menu and the ribbon always agree
    def _buildMenus(self) -> None:
        ribbon = self.ribbon
        _setShortcuts(ribbon.openAction, QKeySequence.StandardKey.Open)
        _setShortcuts(ribbon.newShowAction, QKeySequence.StandardKey.New)
        _setShortcuts(ribbon.reloadAction, QKeySequence.StandardKey.Refresh, "F5")
        _setShortcuts(ribbon.saveAction, QKeySequence.StandardKey.Save)
        _setShortcuts(ribbon.saveAsAction, QKeySequence.StandardKey.SaveAs, "Ctrl+Shift+S")
        _setShortcuts(ribbon.undoAction, QKeySequence.StandardKey.Undo)
        _setShortcuts(ribbon.redoAction, QKeySequence.StandardKey.Redo, "Ctrl+Shift+Z")
        _setShortcuts(self.zoomInAction, QKeySequence.StandardKey.ZoomIn)
        _setShortcuts(self.zoomOutAction, QKeySequence.StandardKey.ZoomOut)
        self.playAction.setShortcut(QKeySequence(Qt.Key.Key_Space))
        self.rewindAction.setShortcut(QKeySequence(Qt.Key.Key_Home))
        for tool, action in ribbon.toolActions.items():
            action.setShortcut(QKeySequence(TOOL_SHORTCUTS[tool]))

        # The following only act on the grid, so the keys copy and paste text as usual elsewhere, such as in the
        # token values
        self.selectAllCellsAction = QAction("Select all cells", self)
        self.selectAllCellsAction.triggered.connect(self.timelineView.selectAll)
        self.clearSelectionAction = QAction("Clear chosen cells", self)
        self.clearSelectionAction.triggered.connect(self.timelineView.clearSelection)
        _setShortcuts(ribbon.copyAction, QKeySequence.StandardKey.Copy)
        _setShortcuts(ribbon.pasteAction, QKeySequence.StandardKey.Paste)
        _setShortcuts(self.selectAllCellsAction, QKeySequence.StandardKey.SelectAll)
        ribbon.repeatOnceAction.setShortcut(QKeySequence("Ctrl+D"))
        self.clearSelectionAction.setShortcut(QKeySequence(Qt.Key.Key_Escape))
        for gridAction in (
            ribbon.copyAction,
            ribbon.pasteAction,
            ribbon.repeatOnceAction,
            self.selectAllCellsAction,
            self.clearSelectionAction,
        ):
            gridAction.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            self.timelineView.addAction(gridAction)

        # Closing the Show Manager when it is a page of MPF-Manager's window goes back to the Project Manager
        self.closeAction = QAction("Close", self)
        _setShortcuts(self.closeAction, QKeySequence.StandardKey.Close)
        self.closeAction.triggered.connect(
            lambda: self.projectManagerRequested.emit() if self.isEmbedded else self.close()
        )

        # The menus are the page's, given to MPF-Manager's window when embedded, or put on this window's menu bar
        fileMenu = QMenu("&File", self)
        fileMenu.addActions([ribbon.newShowAction, ribbon.openAction, ribbon.reloadAction])
        fileMenu.addSeparator()
        fileMenu.addActions([ribbon.saveAction, ribbon.saveAsAction])
        fileMenu.addSeparator()
        fileMenu.addAction(self.closeAction)

        editMenu = QMenu("&Edit", self)
        editMenu.addActions([ribbon.undoAction, ribbon.redoAction])
        editMenu.addSeparator()
        editMenu.addActions([ribbon.copyAction, ribbon.pasteAction])
        editMenu.addSeparator()
        editMenu.addActions([ribbon.repeatOnceAction, ribbon.repeatAction])
        editMenu.addSeparator()
        editMenu.addActions([self.selectAllCellsAction, self.clearSelectionAction])

        # The following show and hide the parts of the window
        self.showRibbonAction = _panelAction("Ribbon", self.ribbon, self)
        self.showListAction = _panelAction("Show list", self.showListPanel, self)
        self.showPlayfieldAction = _panelAction("Playfield", self.playfieldPanel, self)
        viewMenu = QMenu("&View", self)
        viewMenu.addActions([self.zoomInAction, self.zoomOutAction])
        viewMenu.addSeparator()
        viewMenu.addActions([self.previewTokensAction, self.previewColorAction])
        viewMenu.addSeparator()
        viewMenu.addActions([self.showSourceRowsAction, self.onlyChosenAction])
        viewMenu.addSeparator()
        self.expandFoldersAction = viewMenu.addAction("Expand all folders")
        self.expandFoldersAction.triggered.connect(self.showList.expandAll)
        self.collapseFoldersAction = viewMenu.addAction("Collapse all folders")
        self.collapseFoldersAction.triggered.connect(self.showList.collapseAll)
        viewMenu.addSeparator()
        viewMenu.addActions([self.showRibbonAction, self.showListAction, self.showPlayfieldAction])

        playbackMenu = QMenu("&Playback", self)
        playbackMenu.addActions([self.playAction, self.rewindAction])
        playbackMenu.addSeparator()
        playbackMenu.addAction(self.loopAction)
        playbackMenu.addSeparator()
        playbackMenu.addActions([self.addSoundAction, self.removeSoundAction, self.hearSoundsAction])

        toolsMenu = QMenu("&Tools", self)
        toolsMenu.addActions(list(ribbon.toolActions.values()))
        toolsMenu.addSeparator()
        paintColorAction = toolsMenu.addAction("Paint color…")
        paintColorAction.triggered.connect(ribbon.chooseColor)
        toolsMenu.addSeparator()
        toolsMenu.addActions([ribbon.chaseAction, ribbon.makeShowAction, ribbon.addLightAction])
        toolsMenu.addSeparator()
        toolsMenu.addAction(self.chooseLightsAction)
        groupsMenu = toolsMenu.addMenu("Light groups")
        groupsMenu.addActions(
            [
                self.chooseGroupAction,
                self.newGroupAction,
                self.addToGroupAction,
                self.removeFromGroupAction,
                self.renameGroupAction,
                self.deleteGroupAction,
            ]
        )
        toolsMenu.addSeparator()
        effectsMenu = toolsMenu.addMenu("Effects")
        effectsMenu.addActions(list(self.effectToolActions.values()))
        effectsMenu.addSeparator()
        effectsMenu.addMenu(self.patternMenu)
        effectsMenu.addSeparator()
        effectsMenu.addActions([self.applyEffectAction, self.duplicateEffectAction, self.deleteEffectAction])
        effectsMenu.addSeparator()
        effectsMenu.addActions([self.previewEffectAction, self.previewEffectsAction, self.showShapesAction])

        self.pageMenus = [fileMenu, editMenu, viewMenu, playbackMenu, toolsMenu]
        if not self.isEmbedded:
            for menu in self.pageMenus:
                self.menuBar().addMenu(menu)

    # The following builds the Effects tab of the ribbon and the panel of effect settings.  An effect is a shape drawn
    # on the playfield, which can move, turn, grow and change color, and lights the lights it passes over
    def _buildEffects(self) -> None:
        self.effectsPanel = EffectsPanel()
        self.effectsPanel.effectChanged.connect(self._effectsEdited)
        self.effectsPanel.currentEffectChanged.connect(self._effectsEdited)
        self.effectsPanel.applyButton.clicked.connect(self.applyCurrentEffect)

        # The following are the tools for the playfield: choosing and moving shapes, or drawing a new one
        self.effectToolActions: dict[str | None, QAction] = {}
        self.effectToolGroup = QActionGroup(self)
        self.effectToolGroup.setExclusive(True)
        effectTools: list[tuple[str | None, str, str, str]] = [
            (None, "Choose", "↖", "Click an effect's shape to edit it, and drag it to move it"),
            (showEffects.SHAPE_LINE, "Line", "╱", "Drag along the playfield to draw a line"),
            (showEffects.SHAPE_RECTANGLE, "Rectangle", "▭", "Drag from corner to corner to draw a rectangle"),
            (showEffects.SHAPE_ELLIPSE, "Ellipse", "◯", "Drag from corner to corner to draw an ellipse"),
            (showEffects.SHAPE_RING, "Ring", "◎", "Drag from corner to corner to draw a ring"),
            (showEffects.SHAPE_PINWHEEL, "Pinwheel", "✢", "Drag from corner to corner to draw a pinwheel of blades"),
            (showEffects.SHAPE_SPIRAL, "Spiral", "🌀", "Drag from corner to corner to draw a spiral"),
            (showEffects.SHAPE_STARFIELD, "Starfield", "✦", "Drag from corner to corner to draw a field of stars"),
        ]
        for shape, label, symbol, tooltip in effectTools:
            action = QAction(ribbonIcon(None, symbol), label, self)
            action.setToolTip(tooltip)
            action.setCheckable(True)
            action.toggled.connect(lambda checked, chosen=shape: checked and self.playfieldView.setDrawShape(chosen))
            self.effectToolGroup.addAction(action)
            self.effectToolActions[shape] = action
        self.effectToolActions[None].setChecked(True)

        self.applyEffectAction = QAction(ribbonIcon(None, "✓"), "Apply to show", self)
        self.applyEffectAction.setToolTip("Paint the effect into the show. Applying it again replaces it")
        self.applyEffectAction.triggered.connect(self.applyCurrentEffect)
        self.duplicateEffectAction = QAction(ribbonIcon(QIcon.ThemeIcon.EditCopy, "⧉"), "Duplicate", self)
        self.duplicateEffectAction.setToolTip("Make a copy of the effect, e.g. to run it again later")
        self.duplicateEffectAction.triggered.connect(self.duplicateCurrentEffect)
        self.deleteEffectAction = QAction(ribbonIcon(QIcon.ThemeIcon.EditDelete, "✕"), "Delete", self)
        self.deleteEffectAction.setToolTip("Take the effect off the list, leaving what it painted in the show")
        self.deleteEffectAction.triggered.connect(self.deleteCurrentEffect)
        self.previewEffectsAction = QAction(ribbonIcon(None, "◐"), "Preview lights", self)
        self.previewEffectsAction.setCheckable(True)
        self.previewEffectsAction.setChecked(True)
        self.previewEffectsAction.setToolTip(
            "Light the playfield as the show would with the effect being edited applied, without applying it"
        )
        self.previewEffectsAction.toggled.connect(self._refreshPlayfield)
        self.showShapesAction = QAction(ribbonIcon(None, "▢"), "Show shapes", self)
        self.showShapesAction.setCheckable(True)
        self.showShapesAction.setChecked(True)
        self.showShapesAction.setToolTip("Draw the effects' shapes over the playfield, or hide them to see the lights")
        self.showShapesAction.toggled.connect(self._refreshPlayfield)

        # The following plays the effect being edited on its own, over and over, without applying it or moving the
        # playhead, so it can be seen as it will look while its settings are changed
        self.previewEffectAction = QAction(ribbonIcon(QIcon.ThemeIcon.MediaPlaybackStart, "▶"), "Preview effect", self)
        self.previewEffectAction.setCheckable(True)
        self.previewEffectAction.setToolTip("Play the effect over and over on the playfield, without applying it")
        self.previewEffectAction.toggled.connect(self.setEffectPreviewing)
        self.effectPreviewTimer = QTimer(self)
        self.effectPreviewTimer.setInterval(PLAYBACK_INTERVAL_MS)
        self.effectPreviewTimer.timeout.connect(self._advanceEffectPreview)
        self.effectPreviewClock = QElapsedTimer()
        self.effectPreviewTime = 0.0
        self._previewCache: tuple[MPFShow, PlayfieldLights] | None = None
        self._previewFor: tuple[MPFShow | None, showEffects.LightEffect | None] = (None, None)
        self.previewBuilds = 0
        # While an effect's settings are being changed, e.g. by clicking a spin box's arrows or dragging its shape, the
        # lights it would give are worked out again once the changes pause, rather than for each change.  Its shape
        # follows each change straight away
        self.effectPreviewDebounce = QTimer(self)
        self.effectPreviewDebounce.setSingleShot(True)
        self.effectPreviewDebounce.setInterval(EFFECT_PREVIEW_DEBOUNCE_MS)
        self.effectPreviewDebounce.timeout.connect(self._rebuildEffectPreview)

        effectsTab = self.ribbon.addRibbonTab("Effects", EFFECTS_RIBBON_TAB)
        drawGroup = effectsTab.addGroup("Draw")
        for action in self.effectToolActions.values():
            drawGroup.addLargeAction(action)
        effectGroup = effectsTab.addGroup("Effect")
        effectGroup.addLargeAction(self.applyEffectAction)
        effectGroup.addSmallAction(self.duplicateEffectAction)
        effectGroup.addSmallAction(self.deleteEffectAction)
        # The following gives the effect being edited a ready-made pattern, such as a spinning pinwheel or a spiral
        self.patternMenu = QMenu("Patterns", self)
        self.patternActions: dict[str, QAction] = {}
        for groupName, presetNames in showEffects.presetGroups().items():
            self.patternMenu.addSection(groupName)
            for presetName in presetNames:
                presetAction = self.patternMenu.addAction(presetName)
                presetAction.triggered.connect(lambda _checked=False, chosen=presetName: self.applyEffectPreset(chosen))
                self.patternActions[presetName] = presetAction
        self.patternsAction = QAction(ribbonIcon(None, "✺"), "Patterns", self)
        self.patternsAction.setToolTip(
            "Make the effect a ready-made pattern: a pinwheel, a spiral, a rainbow or a starfield"
        )
        self.patternsAction.setMenu(self.patternMenu)
        patternGroup = effectsTab.addGroup("Patterns")
        patternButton = patternGroup.addLargeAction(self.patternsAction)
        patternButton.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        previewGroup = effectsTab.addGroup("Preview")
        previewGroup.addLargeAction(self.previewEffectAction)
        previewGroup.addSmallAction(self.previewEffectsAction)
        previewGroup.addSmallAction(self.showShapesAction)
        self.ribbon.currentChanged.connect(self._ribbonTabChanged)

        self.playfieldView.shapeDrawn.connect(self.addEffect)
        self.playfieldView.effectClicked.connect(self.effectsPanel.setCurrentIndex)
        self.playfieldView.effectMoved.connect(self.moveCurrentEffect)
        self._updateEffectActions()

    # The following shows the effects on the playfield, and their settings, while the Effects tab is chosen
    def _ribbonTabChanged(self, _index: int) -> None:
        isEffects = self.isEffectsMode
        if not isEffects:
            self.stopEffectPreview()
        self.effectsPanel.setVisible(isEffects)
        self.playfieldView.setEffectsMode(isEffects)
        self._refreshPlayfield()

    @property
    def isEffectsMode(self) -> bool:
        return self.ribbon.tabText(self.ribbon.currentIndex()) == "Effects"

    def _effectsEdited(self) -> None:
        self.effectPreviewDebounce.start()
        self._updateEffectActions()
        if self.effectsPanel.currentEffect() is None:
            self.stopEffectPreview()
        self._refreshPlayfield()

    def _updateEffectActions(self) -> None:
        hasEffect = self.effectsPanel.currentEffect() is not None
        for action in (
            self.applyEffectAction,
            self.duplicateEffectAction,
            self.deleteEffectAction,
            self.previewEffectAction,
            self.patternsAction,
        ):
            action.setEnabled(hasEffect)

    # The following returns where the playfield's lights are, in fractions of its width as effects are measured
    def effectLightPositions(self) -> dict[str, tuple[float, float]]:
        layout = self.playfieldLights.layout
        if layout is None:
            return {}
        aspect = self.playfieldView.aspect()
        return {name: (light.x, light.y * aspect) for name, light in layout.lights.items()}

    # The following returns how far each light reaches from its middle, in fractions of the playfield's width.  An
    # effect lights a light once its shape covers the middle half of it, so what the shape is drawn over is lit
    def effectLightReaches(self) -> dict[str, float]:
        layout = self.playfieldLights.layout
        if layout is None:
            return {}
        return {name: light.size * LIGHT_REACH for name, light in layout.lights.items()}

    # The following draws the playfield at a time: the lights as the show sets them, and in the Effects tab the
    # effects' shapes, with the lights as they would be with the effect being edited applied
    def _showPlayfieldAt(self, atTime: float) -> None:
        lightColors = self.playfieldLights.lightColors(atTime)
        if self.isEffectsMode:
            effects = self.effectsPanel.effects if self.showShapesAction.isChecked() else []
            self.playfieldView.setEffectShapes(effects, atTime, self.effectsPanel.currentIndex())
            preview = self._effectPreview() if self.previewEffectsAction.isChecked() else None
            if preview is not None:
                lightColors = preview[1].lightColors(atTime)
        self.playfieldView.setLightColors(lightColors)

    # The following draws the playfield again, at the effect being previewed or at the playhead
    def _refreshPlayfield(self) -> None:
        self._showPlayfieldAt(self.effectPreviewTime if self.isPreviewingEffect else self.playTime)

    # The following returns the arguments the show's timeline is worked out with: its token values, the shows it can
    # play, the color tokens are previewed in, and the project's color names
    def _timelineArguments(self) -> tuple[dict[str, str], dict[str, MPFShow], tuple[int, int, int] | None, Any]:
        previewRGB = self.previewRGB if self.previewTokensAction.isChecked() else None
        tokenValues = {
            token: value for token, value in self.tokenValues.get(self._selectedShowKey(), {}).items() if value
        }
        return tokenValues, self.library, previewRGB, self.namedColors

    # The following returns a copy of the show with the effect being edited applied, and its lights, so the playfield
    # shows exactly what applying it would.  It is worked out again once the effect or the show changes
    def _effectPreview(self) -> tuple[MPFShow, PlayfieldLights] | None:
        show, effect = self.selectedShow(), self.effectsPanel.currentEffect()
        positions = self.effectLightPositions()
        if show is None or effect is None or not positions:
            return None
        # A preview of another effect, or of another show, is not shown while waiting to work this one out
        if self._previewFor != (show, effect):
            self._previewCache = None
        if self._previewCache is None:
            # Only the show's steps are changed by the effect, so only they are copied
            previewShow = copy.copy(show)
            previewShow.errors = list(show.errors)
            if effect.appliedBefore is not None and effect.appliedAfter == show.steps:
                previewShow.steps = copy.deepcopy(effect.appliedBefore)
            else:
                previewShow.steps = copy.deepcopy(show.steps)
            showEffects.applyEffect(
                previewShow, copy.deepcopy(effect), positions, self.namedColors, self.effectLightReaches()
            )
            previewShow.buildTimeline(*self._timelineArguments())
            previewLights = PlayfieldLights(self.playfieldLights.layout, self.playfieldLights.lightTags)
            previewLights.setShow(previewShow)
            self._previewCache = (previewShow, previewLights)
            self._previewFor = (show, effect)
            self.previewBuilds += 1
        return self._previewCache

    # The following works the effect's preview out again once its settings have stopped changing, and shows it
    def _rebuildEffectPreview(self) -> None:
        self._previewCache = None
        self._refreshPlayfield()

    @property
    def isPreviewingEffect(self) -> bool:
        return self.effectPreviewTimer.isActive()

    # The following starts or stops playing the effect being edited on its own, from its start, over and over
    def setEffectPreviewing(self, isPreviewing: bool) -> bool:
        if not isPreviewing:
            self.stopEffectPreview()
            return False
        effect = self.effectsPanel.currentEffect()
        if effect is None or not self.effectLightPositions():
            if effect is not None:
                self.statusBar().showMessage(
                    "Effects need the machine's MPF-Monitor layout, to know where lights are", 4000
                )
            self.previewEffectAction.setChecked(False)
            return False
        self.pausePlayback()
        self.effectPreviewTime = effect.startTime
        self.effectPreviewClock.start()
        self.effectPreviewTimer.start()
        self.previewEffectAction.setChecked(True)
        self._refreshPlayfield()
        return True

    def stopEffectPreview(self) -> None:
        if not self.effectPreviewTimer.isActive() and not self.previewEffectAction.isChecked():
            return
        self.effectPreviewTimer.stop()
        self.previewEffectAction.setChecked(False)
        self._updatePlayfield()

    # The following moves the effect preview on, starting it again after a pause once the effect has ended
    def _advanceEffectPreview(self) -> None:
        effect = self.effectsPanel.currentEffect()
        if effect is None:
            self.stopEffectPreview()
            return
        elapsed = self.effectPreviewClock.restart() / 1000 * self.speedOption.currentData()
        self.effectPreviewTime += elapsed
        if self.effectPreviewTime < effect.startTime or self.effectPreviewTime > effect.endTime + EFFECT_PREVIEW_PAUSE:
            self.effectPreviewTime = effect.startTime
        shownTime = min(self.effectPreviewTime, effect.endTime)
        self._showPlayfieldAt(shownTime)
        self.playfieldSummary.setText(
            f"Previewing {effect.name}: {_formatTime(shownTime - effect.startTime)} of {_formatTime(effect.duration)}"
        )

    # The following makes an effect from a shape drawn on the playfield, running over the chosen cells, or for a second
    # from the playhead, in the paint color
    def addEffect(self, shape: str, startX: float, startY: float, endX: float, endY: float) -> showEffects.LightEffect:
        cells = self.selectedCells()
        if cells is not None:
            startTime = self.timelineModel.timeForColumn(cells[1])
            duration = self.timelineModel.timeForColumn(cells[2] + 1) - startTime
        else:
            startTime, duration = self.playTime, DEFAULT_EFFECT_SECONDS
        effects = self.effects.setdefault(self._selectedShowKey(), [])
        usedNames = {effect.name for effect in effects}
        number = len(effects) + 1
        while f"Effect {number}" in usedNames:
            number += 1
        effect = showEffects.effectFromDrag(
            f"Effect {number}",
            shape,
            startX,
            startY,
            endX,
            endY,
            rgb=self.ribbon.paintRGB,
            intensity=max(self.ribbon.intensity, 1),
            startTime=startTime,
            duration=max(duration, 0.01),
            stepTime=min(self.timelineModel.resolution, DEFAULT_EFFECT_STEP),
        )
        effects.append(effect)
        self.effectsPanel.setEffects(effects, len(effects) - 1)
        # Once drawn, the shape can be edited and moved straight away
        self.effectToolActions[None].setChecked(True)
        self._effectsEdited()
        self.statusBar().showMessage(f"Drew {effect.name}. Change its settings, then Apply to show", 4000)
        return effect

    # The following moves the effect being edited by an amount, in fractions of the playfield's width
    def moveCurrentEffect(self, offsetX: float, offsetY: float) -> None:
        effect = self.effectsPanel.currentEffect()
        if effect is None:
            return
        effect.place.centerX += offsetX
        effect.place.centerY += offsetY
        self.effectsPanel.refresh()
        self._effectsEdited()

    # The following paints the effect being edited into the show, in place of what it painted when last applied
    def applyCurrentEffect(self) -> bool:
        effect = self.effectsPanel.currentEffect()
        if effect is None:
            return False
        positions = self.effectLightPositions()
        if not positions:
            self.statusBar().showMessage(
                "Effects need the machine's MPF-Monitor layout, to know where lights are", 4000
            )
            return False
        self.stopEffectPreview()
        reaches = self.effectLightReaches()
        return self._editShow(
            lambda show: showEffects.applyEffectInPlace(show, effect, positions, self.namedColors, reaches),
            f"Applied {effect.name} from {_formatTime(effect.startTime)} to {_formatTime(effect.endTime)}",
        )

    # The following gives the effect being edited a ready-made pattern's shape and movement, keeping its place, color
    # and timing
    def applyEffectPreset(self, presetName: str) -> bool:
        effect = self.effectsPanel.currentEffect()
        if effect is None:
            return False
        showEffects.applyPreset(effect, presetName)
        self.effectsPanel.refresh()
        self._effectsEdited()
        self.statusBar().showMessage(f"{effect.name} is now a {presetName.lower()}", 4000)
        return True

    def duplicateCurrentEffect(self) -> showEffects.LightEffect | None:
        effect = self.effectsPanel.currentEffect()
        if effect is None:
            return None
        duplicate = copy.deepcopy(effect)
        duplicate.name = f"{effect.name} copy"
        duplicate.appliedBefore = duplicate.appliedAfter = None
        effects = self.effectsPanel.effects
        effects.append(duplicate)
        self.effectsPanel.setEffects(effects, len(effects) - 1)
        self._effectsEdited()
        return duplicate

    def deleteCurrentEffect(self) -> bool:
        index = self.effectsPanel.currentIndex()
        if index is None:
            return False
        effects = self.effectsPanel.effects
        del effects[index]
        self.effectsPanel.setEffects(effects, index)
        self._effectsEdited()
        return True

    # The following switches to the manager clicked on the left edge, when this is a window of its own.  This window
    # stays the Show Manager, so its tab is chosen again once the Project Manager has been asked for
    def _managerTabClicked(self, index: int) -> None:
        if index == PROJECT_MANAGER_TAB:
            self.projectManagerRequested.emit()
            QTimer.singleShot(0, lambda: self.managerTabs.setCurrentIndex(SHOW_MANAGER_TAB))

    # The following shows or collapses the rows naming the shows that set each light, keeping the grid where it is
    def setSourceRowsShown(self, isShown: bool) -> None:
        self.showSourceRowsAction.setChecked(isShown)
        if self.timelineModel.showSourceRows != isShown:
            self.timelineModel.showSourceRows = isShown
            self._displaySelectedShow(keepView=True)

    # The following widens or narrows the grid's columns
    def zoomBy(self, step: int) -> None:
        self.zoomSlider.setValue(self.zoomSlider.value() + step)

    # The following points the window at a machine folder and lists its shows
    def setMachinePath(self, machinePath: Path | None) -> None:
        if not self.confirmDiscardChanges():
            return
        self.machinePath = machinePath
        self.reloadShows()

    # The following reads all the show files and lists every show in them, keeping the current one selected.  Changes
    # not saved are lost, so it is checked first that they can be.  It returns whether the shows were read
    def reloadShows(self) -> bool:
        if not self.confirmDiscardChanges():
            return False
        self.histories.clear()
        self.unsavedKeys.clear()
        self.extraRows.clear()
        currentKey = self._selectedShowKey() or None

        showFiles: list[Path] = []
        if self.machinePath is not None:
            showFiles += showManager.findShowFiles(self.machinePath)
            self.setWindowTitle(f"MPF Show Viewer - {self.machinePath.name}")
        showFiles += [path for path in self.extraShowFiles if path not in showFiles]

        # The sound files and named colors of the project, and of the machine folders of any show files opened, are used
        self.soundFiles = showManager.findSoundFiles(self.machinePath) if self.machinePath else {}
        self.namedColors = showManager.loadNamedColors(self.machinePath) if self.machinePath else {}
        for showFile in self.extraShowFiles:
            for soundName, soundFile in showManager.findSoundFiles(showFile.parent.parent).items():
                self.soundFiles.setdefault(soundName, soundFile)
            for colorName, rgb in showManager.loadNamedColors(showFile.parent.parent).items():
                self.namedColors.setdefault(colorName, rgb)

        # The playfield is the machine's, or that of the first show file opened when there is no machine
        playfieldMachine = self.machinePath or (self.extraShowFiles[0].parent.parent if self.extraShowFiles else None)
        self.playfieldLights.lightTags = monitorManager.loadLightTags(playfieldMachine) if playfieldMachine else {}
        self._listMonitorConfigs(playfieldMachine)
        self._loadLightGroups()

        # The project's shows, and the shows built into MPF, can be played by the shows being viewed
        # Shows defined in the shows: sections of the machine's and its modes' configs are listed after the show files
        self.library = showManager.builtInShows()
        loadedShows = [(showFile, show) for showFile in showFiles for show in showManager.loadShowFile(showFile)]
        configShows = showManager.loadConfigShows(self.machinePath) if self.machinePath else []
        for showFile in self.extraShowFiles:
            self.library.update({show.name: show for show in showManager.loadConfigShows(showFile.parent.parent)})
        self.library.update({show.name: show for show in configShows})
        self.library.update({show.name: show for _showFile, show in loadedShows})
        loadedShows += [(show.sourcePath or Path(), show) for show in configShows]

        self.showList.clearShows(self.machinePath)
        # The machine's folders with MPF files in them are listed, whether or not they have shows
        for machineFolder in showManager.findMachineFolders(self.machinePath) if self.machinePath else []:
            self.showList.addFolder(machineFolder)
        firstItem = None
        for showFile, show in loadedShows:
            item = self._addShowItem(showFile, show)
            firstItem = firstItem or item
            if f"{showFile}\n{show.name}" == currentKey:
                self.showList.selectShowItem(item, notify=False)

        # The first show of the machine's own shows folder is chosen, as the tree lists folders by name
        if self.showList.currentShowItem() is None and firstItem is not None:
            self.showList.selectShowItem(firstItem, notify=False)
        self._displaySelectedShow()
        return True

    # The following lists a show under the folder and file it is in, marking it if it has problems
    def _addShowItem(self, showFile: Path, show: MPFShow) -> QTreeWidgetItem:
        # Problems such as invalid colors are found once the show is worked out with the project's colors
        show.buildTimeline({}, self.library, showManager.DEFAULT_PREVIEW_RGB, self.namedColors)
        hasProblems = bool(show.errors or show.timelineErrors)
        return self.showList.addShow(
            showFile, show, show.name + (" ⚠" if hasProblems else ""), f"{showFile}\n{show.name}"
        )

    # The following opens a show file from anywhere and selects its first show
    def browseShowFile(self) -> None:
        startFolder = str(self.machinePath / "shows") if self.machinePath else ""
        fileName, _ = QFileDialog.getOpenFileName(self, "Open show file", startFolder, "YAML files (*.yaml *.yml)")
        if fileName:
            self.openShowFile(Path(fileName))

    def openShowFile(self, showFile: Path) -> None:
        if showFile not in self.extraShowFiles:
            self.extraShowFiles.append(showFile)
        if not self.reloadShows():
            return
        for item in self.showList.showItems():
            if item.toolTip(0) == str(showFile):
                self.showList.selectShowItem(item)
                break

    def selectedShow(self) -> MPFShow | None:
        item = self.showList.currentShowItem()
        return item.data(0, SHOW_ROLE) if item else None

    # The following lists the machine's MPF-Monitor layout files, keeping the chosen one, or monitor.yaml at first
    def _listMonitorConfigs(self, playfieldMachine: Path | None) -> None:
        self.playfieldMachine = playfieldMachine
        chosenConfig = self.monitorConfigOption.currentText() or "monitor.yaml"
        configNames = (
            sorted(path.name for path in (playfieldMachine / "monitor").glob("*.yaml")) if playfieldMachine else []
        )
        self.monitorConfigOption.blockSignals(True)
        self.monitorConfigOption.clear()
        self.monitorConfigOption.addItems(configNames)
        if chosenConfig in configNames:
            self.monitorConfigOption.setCurrentText(chosenConfig)
        self.monitorConfigOption.blockSignals(False)
        self._loadMonitorLayout()

    # The following draws the chosen MPF-Monitor layout and colors it for the current show and time
    def _loadMonitorLayout(self) -> None:
        configName = self.monitorConfigOption.currentText()
        layout = (
            monitorManager.loadMonitorLayout(self.playfieldMachine, configName)
            if self.playfieldMachine and configName
            else None
        )
        self.playfieldLights.layout = layout
        self._previewCache = None
        self.playfieldView.setMonitorLayout(layout)
        self.playfieldLights.setShow(self.timelineModel.show)
        self._updatePlayfield()

    def _updatePlayfield(self) -> None:
        self._refreshPlayfield()
        layout = self.playfieldLights.layout
        if layout is None:
            self.playfieldSummary.setText("No MPF-Monitor layout (monitor/monitor.yaml) was found for this machine.")
            return
        summary = f"{len(layout.lights)} lights placed"
        if layout.imagePath is None:
            summary += ", no playfield image"
        unplaced = [channel for channel in self.playfieldLights.unplacedChannels if not channel.startswith("(")]
        if unplaced:
            summary += f". Not on this playfield: {', '.join(unplaced[:8])}" + ("…" if len(unplaced) > 8 else "")
        self.playfieldSummary.setText(summary)

    # The following starts or pauses playback, starting again from the beginning once the show has ended
    def togglePlayback(self) -> None:
        if self.playTimer.isActive():
            self.pausePlayback()
            return
        show = self.timelineModel.show
        if show is None or show.totalDuration <= 0:
            return
        self.stopEffectPreview()
        if self.playTime >= show.totalDuration:
            self.setPlayTime(0.0)
        self.playClock.start()
        self.playTimer.start()
        self._syncAudio()
        self.playAction.setText(PAUSE_TEXT)
        self.playAction.setIcon(ribbonIcon(QIcon.ThemeIcon.MediaPlaybackPause, "⏸"))

    def pausePlayback(self) -> None:
        self.playTimer.stop()
        self.showAudio.stopAll()
        self.playAction.setText(PLAY_TEXT)
        self.playAction.setIcon(ribbonIcon(QIcon.ThemeIcon.MediaPlaybackStart, "▶"))

    @property
    def isPlaying(self) -> bool:
        return self.playTimer.isActive()

    # The following moves playback on by the time that has passed, at the chosen speed
    def _advancePlayback(self) -> None:
        show = self.timelineModel.show
        if show is None or show.totalDuration <= 0:
            self.pausePlayback()
            return
        playTime = self.playTime + self.playClock.restart() / 1000 * self.speedOption.currentData()
        if playTime >= show.totalDuration:
            if self.loopAction.isChecked():
                playTime %= show.totalDuration
            else:
                playTime = show.totalDuration
                self.pausePlayback()
        looped = playTime < self.playTime
        self.setPlayTime(playTime, follow=True)
        if looped:
            self.showAudio.stopAll()
        self._syncAudio()

    # The following plays the show's sounds where the playhead is, while the show plays
    def _syncAudio(self) -> None:
        show = self.timelineModel.show
        if show is None or not self.isPlaying:
            return

        def soundLength(audioPath: Path) -> float | None:
            waveform = self.waveformLoader.waveform(audioPath)
            return waveform.duration if waveform else None

        self.showAudio.sync(
            show.soundPlays, self.soundFiles, soundLength, self.playTime, self.speedOption.currentData()
        )

    # The following moves the playhead to a time: the grid's playhead column, the time controls and the playfield
    def setPlayTime(self, playTime: float, follow: bool = False) -> None:
        # Moving the playhead shows the show there again, rather than the effect being previewed
        if self.isPreviewingEffect:
            self.stopEffectPreview()
        show = self.timelineModel.show
        totalDuration = show.totalDuration if show else 0.0
        self.playTime = min(max(playTime, 0.0), totalDuration)
        self.timeSlider.blockSignals(True)
        self.timeSlider.setRange(0, int(round(totalDuration * 1000)))
        self.timeSlider.setValue(int(round(self.playTime * 1000)))
        self.timeSlider.blockSignals(False)
        self.timeLabel.setText(f"{self.playTime:.2f}s / {totalDuration:.2f}s")

        columnCount = self.timelineModel.columnCount()
        playheadColumn = (
            min(int(self.playTime / self.timelineModel.resolution + 1e-9), columnCount - 1) if columnCount else None
        )
        self.timelineModel.setPlayheadColumn(playheadColumn)
        if follow and playheadColumn is not None:
            # While playing, the grid pages along to keep the playhead in view, a little in from the left
            playheadX = self.timelineView.horizontalHeader().sectionPosition(playheadColumn)
            scrollBar = self.timelineView.horizontalScrollBar()
            viewWidth = self.timelineView.viewport().width()
            if not scrollBar.value() <= playheadX <= scrollBar.value() + viewWidth * 0.85:
                scrollBar.setValue(int(playheadX - viewWidth * 0.15))
        self.isPreviewing = False
        self._showPlayfieldAt(self.playTime)

    # The following shows a newly chosen show from its start, paused
    def _showChanged(self) -> None:
        self.stopEffectPreview()
        self.pausePlayback()
        self.showAudio.reset()
        self.playTime = 0.0
        self._displaySelectedShow()

    def hideEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.pausePlayback()
        self.stopEffectPreview()
        super().hideEvent(event)

    def _selectedShowKey(self) -> str:
        item = self.showList.currentShowItem()
        return item.data(0, KEY_ROLE) if item else ""

    # The following draws the selected show in the grid, with its token values and the shows it plays.  After a change
    # to the show, the grid keeps its timebase and where it is scrolled to, so the change is seen where it was made
    def _displaySelectedShow(self, keepView: bool = False) -> None:
        show = self.selectedShow()
        resolution = self.resolutionOption.currentData()
        if keepView and resolution is None:
            resolution = self.timelineModel.resolution
        scrollPositions = (
            self.timelineView.horizontalScrollBar().value(),
            self.timelineView.verticalScrollBar().value(),
        )
        self._previewCache = None
        if show is not None:
            show.buildTimeline(*self._timelineArguments())
        self.timelineModel.setAudio(self.soundFiles, self.waveformLoader)
        self.timelineModel.setShow(
            show, resolution, keepRowOrder=keepView, extraChannelNames=self.extraRows.get(self._selectedShowKey())
        )
        for play in show.soundPlays if show else []:
            if play.soundName in self.soundFiles:
                self.waveformLoader.request(self.soundFiles[play.soundName])
        # Every row's height is set, as rows keep the height they had for the show shown before
        verticalHeader = self.timelineView.verticalHeader()
        for row in range(self.timelineModel.rowCount()):
            if row < self.timelineModel.audioRowCount:
                rowHeight = AUDIO_ROW_HEIGHT
            elif self.timelineModel.isSourceRow(row):
                rowHeight = SOURCE_ROW_HEIGHT
            else:
                rowHeight = verticalHeader.defaultSectionSize()
            verticalHeader.resizeSection(row, rowHeight)
        self._applyZoom()
        self._fillTokenTable(show)
        showEffectsList = self.effects.setdefault(self._selectedShowKey(), [])
        if self.effectsPanel.effects is not showEffectsList:
            self.effectsPanel.setEffects(showEffectsList)
        self.showSummary.setText(self._summaryText(show))
        self.playfieldLights.setShow(show)
        self._updatePlayfield()
        self.setPlayTime(self.playTime)
        self._updateEditState()
        self._applyLightFilter()
        if keepView:
            self.timelineView.horizontalScrollBar().setValue(scrollPositions[0])
            self.timelineView.verticalScrollBar().setValue(scrollPositions[1])

    # The following lists the selected show's tokens with the values given for them
    def _fillTokenTable(self, show: MPFShow | None) -> None:
        values = self.tokenValues.get(self._selectedShowKey(), {})
        self.tokenTable.blockSignals(True)
        self.tokenTable.setRowCount(0)
        for token in show.tokens if show else []:
            row = self.tokenTable.rowCount()
            self.tokenTable.insertRow(row)
            tokenItem = QTableWidgetItem(f"({token})")
            tokenItem.setFlags(tokenItem.flags() & ~Qt.ItemFlag.ItemIsEditable)
            tokenItem.setData(Qt.ItemDataRole.UserRole, token)
            self.tokenTable.setItem(row, 0, tokenItem)
            self.tokenTable.setItem(row, 1, QTableWidgetItem(values.get(token, "")))
        self.tokenTable.blockSignals(False)

    def _tokenValueChanged(self, item: QTableWidgetItem) -> None:
        tokenItem = self.tokenTable.item(item.row(), 0)
        if tokenItem is None:
            return
        token = tokenItem.data(Qt.ItemDataRole.UserRole)
        self.tokenValues.setdefault(self._selectedShowKey(), {})[token] = item.text().strip()
        self._displaySelectedShow()

    # The following picks the color that color tokens without a value are drawn in
    def choosePreviewColor(self) -> None:
        chosenColor = QColorDialog.getColor(QColor(*self.previewRGB), self, "Token preview color")
        if chosenColor.isValid():
            self.previewRGB = (chosenColor.red(), chosenColor.green(), chosenColor.blue())
            self._updatePreviewColorButton()
            self._displaySelectedShow()

    def _updatePreviewColorButton(self) -> None:
        self.previewColorButton.setText("#{:02x}{:02x}{:02x}".format(*self.previewRGB))
        self.previewColorButton.setStyleSheet(
            "background-color: #{:02x}{:02x}{:02x}; color: {};".format(
                *self.previewRGB, _textColorFor(self.previewRGB).name()
            )
        )

    # The following redraws the audio row and its details once a sound has been decoded
    def _waveformReady(self, _audioPath: str) -> None:
        self.timelineModel.refreshAudio()
        self.showSummary.setText(self._summaryText(self.selectedShow()))

    def _applyZoom(self) -> None:
        self.timelineView.horizontalHeader().setDefaultSectionSize(self.zoomSlider.value())

    # The following uses a typed timebase, adding it to the list, or explains why the text is not one
    def _timebaseEntered(self) -> None:
        text = self.resolutionOption.currentText().strip()
        existingIndex = self.resolutionOption.findText(text, Qt.MatchFlag.MatchFixedString)
        seconds = None if existingIndex >= 0 else showManager.parseTimebase(text)
        if existingIndex < 0 and seconds is not None:
            existingIndex = self.resolutionOption.findData(seconds)
            if existingIndex < 0:
                self.resolutionOption.addItem(_timebaseLabel(text, seconds), seconds)
                existingIndex = self.resolutionOption.count() - 1
        if existingIndex >= 0:
            self.timebaseMessage.hide()
            self.resolutionOption.setCurrentIndex(existingIndex)
            # Typing over the chosen timebase keeps it, so the list's own label is shown again
            self.resolutionOption.setEditText(self.resolutionOption.itemText(existingIndex))
            return
        self.timebaseMessage.setText(f"'{text}' is not a timebase from 1ms to 60s, e.g. 40ms, 0.5s or 30fps")
        self.timebaseMessage.show()
        self.resolutionOption.setEditText(self.resolutionOption.itemText(self.resolutionOption.currentIndex()))

    # The following lets cells be dragged over to choose them, which paints or erases them with those tools.  Cells
    # are not chosen with the pick tool, which picks the color of the cell clicked
    def _toolChanged(self, tool: str) -> None:
        self.endPreview()
        self.timelineView.clearSelection()
        self.timelineView.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
            if tool == TOOL_PICK
            else QAbstractItemView.SelectionMode.ContiguousSelection
        )
        cursor = Qt.CursorShape.CrossCursor if tool != TOOL_SELECT else Qt.CursorShape.ArrowCursor
        self.timelineView.viewport().setCursor(cursor)

    # The following paints or erases the cells dragged over once the mouse is let go, and while painting or erasing has
    # the playfield follow the cell under the mouse
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt override
        if watched is self.timelineView.viewport() and self.ribbon.currentTool in (TOOL_PAINT, TOOL_ERASE):
            if event.type() == QEvent.Type.MouseMove and isinstance(event, QMouseEvent):
                self.previewAt(event.position().toPoint(), bool(event.buttons() & Qt.MouseButton.LeftButton))
            elif event.type() == QEvent.Type.Leave:
                self.endPreview()
            elif event.type() == QEvent.Type.MouseButtonRelease:
                self.endPreview()
                QTimer.singleShot(0, self.applyToolToSelection)
        return super().eventFilter(watched, event)

    # The following shows on the playfield the lights at the time of the cell under the mouse, without moving the
    # playhead.  With the paint tool, the light under the mouse, or the lights being dragged over, are shown in the
    # paint color, so it can be seen on the playfield what is about to be painted
    def previewAt(self, viewportPoint: QPoint, isDragging: bool = False) -> bool:
        index = self.timelineView.indexAt(viewportPoint)
        if not index.isValid() or self.selectedShow() is None:
            return False
        model = self.timelineModel
        lightColors = self.playfieldLights.lightColors(model.timeForColumn(index.column()))
        if self.ribbon.currentTool == TOOL_PAINT:
            paintRGB = self.ribbon.paintSetting(self.namedColors).rgb
            hoveredChannel = model.lightChannel(index.row())
            cells = self.selectedCells() if isDragging else None
            if cells is not None:
                channelNames = cells[0]
            else:
                channelNames = [hoveredChannel.name] if hoveredChannel is not None else []
            for channelName in channelNames:
                for lightName in self.playfieldLights.lightsForChannel(channelName):
                    lightColors[lightName] = (paintRGB, "the paint tool")
        self.playfieldView.setLightColors(lightColors)
        self.isPreviewing = True
        return True

    # The following shows the playfield at the playhead again once the preview ends
    def endPreview(self) -> None:
        if self.isPreviewing:
            self.isPreviewing = False
            self.playfieldView.setLightColors(self.playfieldLights.lightColors(self.playTime))

    # The following moves the playhead to a clicked cell, and with the pick tool paints with the cell's color next
    def _cellClicked(self, index: QModelIndex) -> None:
        self.setPlayTime(self.timelineModel.timeForColumn(index.column()))
        if self.ribbon.currentTool == TOOL_PICK:
            self.pickColor(index.row(), index.column())

    def pickColor(self, row: int, column: int) -> bool:
        state = self.timelineModel.cellState(row, column)
        picked = (
            showEditor.splitColorValue(state.segment.setting.value, self.namedColors)
            if state is not None and state.segment is not None
            else None
        )
        if picked is None:
            self.statusBar().showMessage("That cell has no color to pick", 4000)
            return False
        self.ribbon.setColor(*picked)
        self.ribbon.setTool(TOOL_PAINT)
        self.statusBar().showMessage(f"Painting with {showEditor.colorValue(*picked, self.namedColors)}", 4000)
        return True

    def _history(self) -> showEditor.EditHistory:
        return self.histories.setdefault(self._selectedShowKey(), showEditor.EditHistory())

    # The following changes the selected show with a change that returns whether it changed anything, so the change
    # can be undone, and draws the show again with a message saying what was done
    def _editShow(self, change: Any, message: str) -> bool:
        show = self.selectedShow()
        if show is None:
            return False
        stepsBefore = copy.deepcopy(show.steps)
        if not change(show):
            return False
        self._history().record(stepsBefore)
        self.statusBar().showMessage(message, 4000)
        self._showEdited()
        return True

    def _spanText(self, firstColumn: int, lastColumn: int) -> str:
        show = self.selectedShow()
        endTime = self.timelineModel.timeForColumn(lastColumn + 1)
        endTime = min(endTime, show.totalDuration) if show else endTime
        return f"from {_formatTime(self.timelineModel.timeForColumn(firstColumn))} to {_formatTime(endTime)}"

    # The following paints the chosen lights from one column to another with the paint tool's setting, or erases them
    def paintCells(self, channelNames: list[str], firstColumn: int, lastColumn: int, erase: bool = False) -> bool:
        if not channelNames:
            return False
        model = self.timelineModel
        startTime, endTime = model.timeForColumn(firstColumn), model.timeForColumn(lastColumn + 1)
        setting = None if erase else self.ribbon.paintSetting(self.namedColors)

        def paint(show: MPFShow) -> bool:
            changed = False
            for channelName in channelNames:
                # Each light is given its own copy of the setting, so changing one later leaves the others as they are
                changed |= showEditor.paintLight(show, channelName, startTime, endTime, copy.copy(setting))
            return changed

        action = "Erased" if erase else f"Painted {setting.value if setting else ''} on"
        return self._editShow(paint, f"{action} {', '.join(channelNames)} {self._spanText(firstColumn, lastColumn)}")

    # The following returns the lights of the light rows chosen in the grid, leaving out the audio rows and the rows
    # naming shows, with the first and last columns chosen, or None when no light cells are chosen
    def selectedCells(self) -> tuple[list[str], int, int] | None:
        indexes = self.timelineView.selectionModel().selectedIndexes()
        channelNames: list[str] = []
        for row in sorted({index.row() for index in indexes}):
            channel = self.timelineModel.lightChannel(row)
            if channel is not None and channel.name not in channelNames:
                channelNames.append(channel.name)
        if not channelNames:
            return None
        columns = [index.column() for index in indexes]
        return channelNames, min(columns), max(columns)

    # The following paints or erases the light cells chosen in the grid
    def applyToolToSelection(self) -> bool:
        tool = self.ribbon.currentTool
        cells = self.selectedCells()
        self.timelineView.clearSelection()
        if tool not in (TOOL_PAINT, TOOL_ERASE) or cells is None:
            return False
        return self.paintCells(*cells, erase=tool == TOOL_ERASE)

    # The following tells the user that cells need choosing first, returning the cells chosen if there are any
    def _requireCells(self) -> tuple[list[str], int, int] | None:
        cells = self.selectedCells()
        if cells is None:
            self.statusBar().showMessage("Choose some light cells first, by dragging over them", 4000)
        return cells

    # The following copies what the show sets the chosen lights to
    def copyCells(self) -> bool:
        show = self.selectedShow()
        cells = self._requireCells()
        if show is None or cells is None:
            return False
        channelNames, firstColumn, lastColumn = cells
        model = self.timelineModel
        self.lightClip = showEditor.copyLights(
            show, channelNames, model.timeForColumn(firstColumn), model.timeForColumn(lastColumn + 1)
        )
        self.statusBar().showMessage(
            f"Copied {', '.join(channelNames)} {self._spanText(firstColumn, lastColumn)}", 4000
        )
        return True

    # The following pastes what was copied where the chosen cells start, onto the chosen lights when as many are chosen
    # as were copied, or else onto the light rows from the first one chosen.  With no cells chosen, it is pasted at the
    # playhead onto the lights it was copied from
    def pasteCells(self) -> bool:
        clip = self.lightClip
        if clip is None:
            self.statusBar().showMessage("Copy some cells first", 4000)
            return False
        cells = self.selectedCells()
        targetNames: list[str] | None = None
        atTime = self.playTime
        if cells is not None:
            channelNames, firstColumn, _lastColumn = cells
            atTime = self.timelineModel.timeForColumn(firstColumn)
            targetNames = channelNames
            if len(channelNames) != len(clip.lightNames):
                firstRow = min(index.row() for index in self.timelineView.selectionModel().selectedIndexes())
                lightRows = [
                    channel.name
                    for row in range(firstRow, self.timelineModel.rowCount())
                    if (channel := self.timelineModel.lightChannel(row)) is not None
                    and not self.timelineView.isRowHidden(row)
                ]
                targetNames = lightRows[: len(clip.lightNames)]
        pastedNames = targetNames or clip.lightNames
        return self._editShow(
            lambda show: showEditor.pasteLights(show, clip, atTime, targetNames),
            f"Pasted onto {', '.join(pastedNames[: len(clip.lightNames)])} at {_formatTime(atTime)}",
        )

    # The following repeats the chosen cells straight after themselves, asking how many times when not given
    def repeatCells(self, count: int | None = None) -> bool:
        cells = self._requireCells()
        if cells is None:
            return False
        if count is None:
            count, accepted = QInputDialog.getInt(
                self, "Repeat", "Repeat the chosen cells this many times:", 1, 1, 1000
            )
            if not accepted:
                return False
        channelNames, firstColumn, lastColumn = cells
        startTime = self.timelineModel.timeForColumn(firstColumn)
        endTime = self.timelineModel.timeForColumn(lastColumn + 1)
        return self._editShow(
            lambda show: showEditor.repeatLights(show, channelNames, startTime, endTime, count),
            f"Repeated {', '.join(channelNames)} {count} times",
        )

    # The following returns where each channel is on the playfield, as the middle of the placed lights it sets
    def channelPositions(self, channelNames: list[str]) -> dict[str, tuple[float, float]]:
        layout = self.playfieldLights.layout
        positions: dict[str, tuple[float, float]] = {}
        for channelName in channelNames:
            lights = (
                [layout.lights[name] for name in self.playfieldLights.lightsForChannel(channelName)] if layout else []
            )
            if lights:
                positions[channelName] = (
                    sum(light.x for light in lights) / len(lights),
                    sum(light.y for light in lights) / len(lights),
                )
        return positions

    # The following asks how to chase the chosen lights, and paints the chase
    def openChaseDialog(self) -> bool:
        cells = self._requireCells()
        if cells is None:
            return False
        channelNames = cells[0]
        dialog = ChaseDialog(
            len(channelNames),
            round(self.timelineModel.resolution * 1000),
            self.ribbon.paintSetting(self.namedColors).value,
            bool(self.channelPositions(channelNames)),
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        return self.chaseCells(dialog.order, dialog.pattern, dialog.stepTime, dialog.litCount, dialog.betweenSetting())

    # The following paints a chase over the chosen lights, in an order from the playfield or the grid's order, with
    # the paint tool's setting
    def chaseCells(
        self,
        order: str,
        pattern: str,
        stepTime: float,
        litCount: int = 1,
        betweenSetting: showManager.LightSetting | None = None,
    ) -> bool:
        cells = self._requireCells()
        if cells is None:
            return False
        channelNames, firstColumn, lastColumn = cells
        orderedNames = showEditor.orderLights(channelNames, self.channelPositions(channelNames), order)
        startTime = self.timelineModel.timeForColumn(firstColumn)
        endTime = self.timelineModel.timeForColumn(lastColumn + 1)
        setting = self.ribbon.paintSetting(self.namedColors)
        return self._editShow(
            lambda show: showEditor.chaseLights(
                show, orderedNames, startTime, endTime, setting, stepTime, pattern, litCount, betweenSetting
            ),
            f"Chased {', '.join(orderedNames)} {self._spanText(firstColumn, lastColumn)}",
        )

    # The following asks for the name of a show to make of the chosen cells, and makes it
    def openMakeShowDialog(self) -> bool:
        show = self.selectedShow()
        cells = self._requireCells()
        if show is None or cells is None:
            return False
        dialog = ReusableShowDialog(f"{show.name}_part", len(cells[0]), self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        return self.makeShowFromCells(dialog.showName, dialog.tokenizeColors)

    # The following makes a show of the chosen cells, with the lights and colors as show tokens, writes it to a show
    # file in the machine's shows folder, or next to the show's own file, and plays it in place of the cells
    def makeShowFromCells(self, showName: str, tokenizeColors: bool = True) -> bool:
        show = self.selectedShow()
        cells = self._requireCells()
        if show is None or cells is None:
            return False
        if showName in self.library:
            QMessageBox.warning(self, "Show not made", f"There is already a show called {showName}.")
            return False
        showsFolder = self.machinePath / "shows" if self.machinePath else (show.sourcePath or Path.cwd()).parent
        showFile = showsFolder / f"{showName}.yaml"
        if showFile.exists():
            QMessageBox.warning(self, "Show not made", f"{showFile} already exists.")
            return False

        channelNames, firstColumn, lastColumn = cells
        startTime = self.timelineModel.timeForColumn(firstColumn)
        endTime = self.timelineModel.timeForColumn(lastColumn + 1)
        newShow, showTokens = showEditor.makeReusableShow(
            show, channelNames, startTime, endTime, showName, tokenizeColors
        )
        try:
            showManager.exportShowFile(newShow, showFile)
        except OSError as error:
            QMessageBox.warning(self, "Show not made", f"The show could not be written to {showFile}:\n{error}")
            return False
        newShow.sourcePath = showFile
        self.library[showName] = newShow
        knownFiles = showManager.findShowFiles(self.machinePath) if self.machinePath else []
        if showFile not in knownFiles:
            self.extraShowFiles.append(showFile)
        self.showList.blockSignals(True)
        for staleItem in self.showList.showItemsOfFile(showFile):
            self.showList.removeShow(staleItem)
        self._addShowItem(showFile, newShow)
        self.showList.blockSignals(False)
        return self._editShow(
            lambda edited: showEditor.playShowInPlace(edited, channelNames, startTime, endTime, showName, showTokens),
            f"Made show {showName} in {showFile}, played with " + ", ".join(f"{k}: {v}" for k, v in showTokens.items()),
        )

    # The following asks for a new show's name, folder and length, and makes it.  The folder is the one chosen in the
    # show files, or the machine's shows folder
    def openNewShowDialog(self) -> bool:
        folder = self.showList.currentFolder() or self._defaultShowFolder()
        dialog = NewShowDialog(folder, set(self.library), self._unusedShowName(), self)
        if not dialog.exec():
            return False
        return self.newShow(dialog.showName, dialog.showFile.parent, dialog.length)

    def _defaultShowFolder(self) -> Path:
        if self.machinePath is not None:
            return self.machinePath / "shows"
        show = self.selectedShow()
        return show.sourcePath.parent if show is not None and show.sourcePath is not None else Path.cwd()

    def _unusedShowName(self) -> str:
        number = 1
        while f"new_show_{number}" in self.library:
            number += 1
        return f"new_show_{number}"

    # The following makes a new, blank show file in a folder, lists it and shows it, ready to be painted.  MPF plays
    # shows from the shows folders of the machine and its modes, so a show made elsewhere is said to be
    def newShow(self, showName: str, folder: Path, length: float = 2.0) -> bool:
        showFile = folder / f"{showName}.yaml"
        if not showName or showName in self.library or showFile.exists():
            QMessageBox.warning(
                self, "Show not made", f"There is already a show called {showName} or a file {showFile}."
            )
            return False
        show = showEditor.newShow(showName, length, showFile)
        try:
            folder.mkdir(parents=True, exist_ok=True)
            showManager.exportShowFile(show, showFile)
        except OSError as error:
            QMessageBox.warning(self, "Show not made", f"The show could not be written to {showFile}:\n{error}")
            return False
        self.library[showName] = show
        knownFiles = showManager.findShowFiles(self.machinePath) if self.machinePath else []
        if showFile not in knownFiles and showFile not in self.extraShowFiles:
            self.extraShowFiles.append(showFile)
        self.showList.blockSignals(True)
        item = self._addShowItem(showFile, show)
        self.showList.blockSignals(False)
        self.showList.selectShowItem(item)
        message = f"Made the show {showName} in {showFile}"
        if knownFiles and showFile not in knownFiles:
            message += ". MPF plays shows from a shows folder, so move it there to play it"
        self.statusBar().showMessage(message, 6000)
        return True

    # The following asks which sound the show plays, when and how, and puts it in the show
    def openAddSoundDialog(self) -> bool:
        if self.selectedShow() is None:
            self.statusBar().showMessage("Choose a show to add a sound to", 4000)
            return False
        dialog = AddSoundDialog(sorted(self.soundFiles), self.playTime, self)
        if not dialog.exec():
            return False
        return self.addSound(dialog.soundName, dialog.atTime, dialog.settings())

    # The following makes the show play a sound at a time.  Its waveform is drawn above the lights once it is read
    def addSound(self, soundName: str, atTime: float, settings: dict | None = None) -> bool:
        changed = self._editShow(
            lambda show: showEditor.addSound(show, soundName, atTime, settings),
            f"Added the sound {soundName} at {_formatTime(atTime)}",
        )
        if changed and soundName not in self.soundFiles:
            self.statusBar().showMessage(f"Added {soundName}, but no sound file of that name was found", 6000)
        return changed

    # The following asks which of the show's sounds to take out, and takes it out
    def openRemoveSoundDialog(self) -> bool:
        show = self.selectedShow()
        entries = showEditor.soundEntries(show) if show else []
        if not entries:
            self.statusBar().showMessage("The show does not play any sounds of its own", 4000)
            return False
        dialog = RemoveSoundDialog(entries, self)
        chosen = dialog.chosenEntry() if dialog.exec() else None
        return self.removeSound(*chosen) if chosen else False

    def removeSound(self, atTime: float, soundName: str) -> bool:
        return self._editShow(
            lambda show: showEditor.removeSound(show, atTime, soundName),
            f"Took the sound {soundName} at {_formatTime(atTime)} out of the show",
        )

    # The following chooses the rows of lights chosen on the playfield, over the columns chosen in the grid or the whole
    # show, adding rows for the lights the show does not set yet so they can be painted
    def chooseLightRows(self, lightNames: list[str]) -> None:
        if self.selectedShow() is None:
            return
        cells = self.selectedCells()
        firstColumn, lastColumn = (cells[1], cells[2]) if cells else (0, self.timelineModel.columnCount() - 1)
        shownNames = {gridRow.channel.name for gridRow in self.timelineModel.gridRows}
        missingNames = [name for name in lightNames if name not in shownNames]
        if missingNames:
            self.extraRows.setdefault(self._selectedShowKey(), []).extend(missingNames)
            self._displaySelectedShow(keepView=True)
        self._applyLightFilter()

        model = self.timelineModel
        selection = QItemSelection()
        for row in range(model.rowCount()):
            channel = model.lightChannel(row)
            if channel is not None and channel.name in lightNames:
                selection.select(model.index(row, firstColumn), model.index(row, lastColumn))
        self.timelineView.selectionModel().select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        if lightNames:
            self.statusBar().showMessage(f"Chose {', '.join(lightNames)} from the playfield", 4000)

    # The following shows only the rows of the lights chosen on the playfield, with the rows naming the shows that set
    # them, when asked to and lights are chosen
    def _applyLightFilter(self) -> None:
        chosenNames = set(self.playfieldView.chosenLights) if self.onlyChosenAction.isChecked() else set()
        model = self.timelineModel
        for row in range(model.rowCount()):
            gridIndex = row - model.audioRowCount
            isHidden = (
                bool(chosenNames) and gridIndex >= 0 and model.gridRows[gridIndex].channel.name not in chosenNames
            )
            self.timelineView.setRowHidden(row, isHidden)

    # The following adds a row for a light or tag the show does not set yet, so it can be painted, asking which when
    # not given from the machine's lights and tags
    def addLightRow(self, lightName: str | None = None) -> bool:
        if self.selectedShow() is None:
            return False
        if lightName is None:
            lightTags = self.playfieldLights.lightTags
            choices = sorted({*lightTags, *(tag for tags in lightTags.values() for tag in tags)})
            lightName, accepted = QInputDialog.getItem(
                self, "Add light", "Light or tag to add a row for:", choices, 0, True
            )
            if not accepted:
                return False
        lightName = lightName.strip()
        shownNames = {gridRow.channel.name for gridRow in self.timelineModel.gridRows}
        if not lightName or lightName in shownNames:
            return False
        self.extraRows.setdefault(self._selectedShowKey(), []).append(lightName)
        self._displaySelectedShow(keepView=True)
        return True

    # The following takes the chosen rows' lights out of the show, everywhere it sets them, or the row of the cell
    # clicked when no cells are chosen.  Rows added to paint a light the show does not set yet are taken away
    def removeLightRows(self, channelNames: list[str] | None = None) -> bool:
        show = self.selectedShow()
        if show is None:
            return False
        if channelNames is None:
            cells = self.selectedCells()
            channel = self.timelineModel.lightChannel(self.timelineView.currentIndex().row())
            channelNames = cells[0] if cells else ([channel.name] if channel else [])
        if not channelNames:
            self.statusBar().showMessage("Choose the rows of the lights to take out, by dragging over them", 4000)
            return False
        extraRows = self.extraRows.get(self._selectedShowKey(), [])
        addedRows = [name for name in channelNames if name in extraRows]
        for name in addedRows:
            extraRows.remove(name)
        names = ", ".join(channelNames)
        changed = self._editShow(
            lambda edited: any([showEditor.removeLightFromShow(edited, name) for name in channelNames]),
            f"Took {names} out of the show",
        )
        if addedRows and not changed:
            self._displaySelectedShow(keepView=True)
            self.statusBar().showMessage(f"Took away the rows for {names}", 4000)
        return changed or bool(addedRows)

    # The following builds the light groups on the Playfield tab: groups of lights named by the user, kept with the
    # machine, and the groups MPF's light tags make, to choose many lights at once
    def _buildLightGroups(self, playfieldTab) -> None:
        self.lightGroups: list[LightGroup] = []
        self.groupOption = QComboBox()
        self.groupOption.setMinimumWidth(170)
        self.groupOption.setToolTip("The machine's light groups, and the groups its light tags make")
        self.groupOption.currentIndexChanged.connect(self._updateGroupActions)

        def groupAction(text: str, tooltip: str, symbol: str) -> QAction:
            action = QAction(ribbonIcon(None, symbol), text, self)
            action.setToolTip(tooltip)
            return action

        self.chooseGroupAction = groupAction(
            "Choose group", "Choose the group's lights on the playfield and in the grid", "◎"
        )
        self.newGroupAction = groupAction("New group…", "Make a group of the lights chosen on the playfield", "✚")
        self.addToGroupAction = groupAction("Add chosen", "Add the lights chosen on the playfield to the group", "+")
        self.removeFromGroupAction = groupAction(
            "Remove chosen", "Take the lights chosen on the playfield out of the group", "−"
        )
        self.renameGroupAction = groupAction("Rename…", "Rename the group", "✎")
        self.deleteGroupAction = groupAction("Delete group", "Delete the group, keeping its lights", "✕")
        self.chooseGroupAction.triggered.connect(lambda: self.chooseGroup())
        self.newGroupAction.triggered.connect(lambda: self.newLightGroup())
        self.addToGroupAction.triggered.connect(lambda: self.addChosenToGroup())
        self.removeFromGroupAction.triggered.connect(lambda: self.removeChosenFromGroup())
        self.renameGroupAction.triggered.connect(lambda: self.renameLightGroup())
        self.deleteGroupAction.triggered.connect(lambda: self.deleteLightGroup())
        groupsGroup = playfieldTab.addGroup("Light groups")
        groupsGroup.addSmallWidget(self.groupOption, "Group:")
        groupsGroup.addSmallAction(self.chooseGroupAction)
        groupsGroup.addSmallAction(self.newGroupAction)
        groupsGroup.addSmallAction(self.addToGroupAction)
        groupsGroup.addSmallAction(self.removeFromGroupAction)
        groupsGroup.addSmallAction(self.renameGroupAction)
        groupsGroup.addSmallAction(self.deleteGroupAction)
        self.playfieldView.lightsSelected.connect(lambda _names: self._updateGroupActions())
        self._updateGroupActions()

    # The following reads the machine's light groups, and the groups its light tags make
    def _loadLightGroups(self) -> None:
        self.lightGroups = lightGroups.loadLightGroups(self.playfieldMachine)
        self._listLightGroups()

    def _allLightGroups(self) -> list[LightGroup]:
        return [*self.lightGroups, *lightGroups.tagGroups(self.playfieldLights.lightTags)]

    # The following lists the groups, keeping the group chosen
    def _listLightGroups(self, chosenLabel: str | None = None) -> None:
        chosenLabel = chosenLabel if chosenLabel is not None else self.groupOption.currentData()
        self.groupOption.blockSignals(True)
        self.groupOption.clear()
        for group in self._allLightGroups():
            self.groupOption.addItem(f"{group.label}  ({len(group.lights)})", group.label)
        self.groupOption.setCurrentIndex(max(self.groupOption.findData(chosenLabel), 0))
        self.groupOption.blockSignals(False)
        self._updateGroupActions()

    def currentLightGroup(self) -> LightGroup | None:
        label = self.groupOption.currentData()
        return next((group for group in self._allLightGroups() if group.label == label), None)

    def _updateGroupActions(self) -> None:
        group = self.currentLightGroup()
        canEdit = group is not None and not group.isTag
        hasChosen = bool(self.playfieldView.chosenLights)
        self.chooseGroupAction.setEnabled(group is not None)
        self.newGroupAction.setEnabled(hasChosen and self.playfieldMachine is not None)
        self.addToGroupAction.setEnabled(canEdit and hasChosen)
        self.removeFromGroupAction.setEnabled(canEdit and hasChosen)
        self.renameGroupAction.setEnabled(canEdit)
        self.deleteGroupAction.setEnabled(canEdit)

    def _saveLightGroups(self, message: str, chosenLabel: str | None = None) -> bool:
        if self.playfieldMachine is None:
            return False
        try:
            lightGroups.saveLightGroups(self.playfieldMachine, self.lightGroups)
        except OSError as error:
            QMessageBox.warning(self, "Light groups not saved", f"The light groups could not be saved:\n{error}")
            return False
        self._listLightGroups(chosenLabel)
        self.statusBar().showMessage(message, 4000)
        return True

    # The following chooses a group's lights on the playfield, which chooses their rows in the grid
    def chooseGroup(self, group: LightGroup | None = None) -> bool:
        group = group or self.currentLightGroup()
        if group is None:
            return False
        self.playfieldView.selectLights(group.lights, notify=True)
        self.statusBar().showMessage(f"Chose the {len(group.lights)} lights of {group.label}", 4000)
        return True

    # The following makes a group of the lights chosen on the playfield, asking its name when not given
    def newLightGroup(self, name: str | None = None) -> bool:
        chosen = list(self.playfieldView.chosenLights)
        if not chosen or self.playfieldMachine is None:
            self.statusBar().showMessage("Choose some lights on the playfield first", 4000)
            return False
        if name is None:
            name, accepted = QInputDialog.getText(self, "New light group", "Name of the group:")
            if not accepted:
                return False
        name = name.strip()
        if not name or any(group.name == name for group in self.lightGroups) or name.startswith(lightGroups.TAG_PREFIX):
            self.statusBar().showMessage(f"There is already a group called {name}, or the name is empty", 4000)
            return False
        self.lightGroups.append(LightGroup(name, chosen))
        return self._saveLightGroups(f"Made the group {name} of {len(chosen)} lights", name)

    def addChosenToGroup(self) -> bool:
        group = self.currentLightGroup()
        if group is None or group.isTag or not self.playfieldView.chosenLights:
            return False
        added = [name for name in self.playfieldView.chosenLights if name not in group.lights]
        group.lights.extend(added)
        return self._saveLightGroups(f"Added {len(added)} lights to {group.name}", group.label)

    def removeChosenFromGroup(self) -> bool:
        group = self.currentLightGroup()
        if group is None or group.isTag or not self.playfieldView.chosenLights:
            return False
        before = len(group.lights)
        group.lights = [name for name in group.lights if name not in self.playfieldView.chosenLights]
        return self._saveLightGroups(f"Took {before - len(group.lights)} lights out of {group.name}", group.label)

    def renameLightGroup(self, name: str | None = None) -> bool:
        group = self.currentLightGroup()
        if group is None or group.isTag:
            return False
        if name is None:
            name, accepted = QInputDialog.getText(self, "Rename light group", "New name:", text=group.name)
            if not accepted:
                return False
        name = name.strip()
        if not name or any(other.name == name for other in self.lightGroups if other is not group):
            self.statusBar().showMessage(f"There is already a group called {name}, or the name is empty", 4000)
            return False
        oldName, group.name = group.name, name
        return self._saveLightGroups(f"Renamed {oldName} to {name}", name)

    def deleteLightGroup(self) -> bool:
        group = self.currentLightGroup()
        if group is None or group.isTag:
            return False
        answer = QMessageBox.question(self, "Delete light group", f"Delete the group {group.name}? Its lights stay.")
        if answer != QMessageBox.StandardButton.Yes:
            return False
        self.lightGroups.remove(group)
        return self._saveLightGroups(f"Deleted the group {group.name}")

    def undo(self) -> None:
        show = self.selectedShow()
        if show is not None and self._history().undo(show):
            self._showEdited()

    def redo(self) -> None:
        show = self.selectedShow()
        if show is not None and self._history().redo(show):
            self._showEdited()

    # The following marks the selected show as changed and draws it again, along with the shows that play it
    def _showEdited(self) -> None:
        self.unsavedKeys.add(self._selectedShowKey())
        self._updateItemLabel(self.showList.currentShowItem())
        self._displaySelectedShow(keepView=True)

    def _updateItemLabel(self, item: QTreeWidgetItem | None) -> None:
        if item is not None:
            isUnsaved = item.data(0, KEY_ROLE) in self.unsavedKeys
            item.setText(0, ("● " if isUnsaved else "") + item.data(0, LABEL_ROLE))

    # The following enables undo, redo and save for the selected show.  Shows in a config file can only be saved as a
    # show file, as saving them over the config would lose its other sections
    def _updateEditState(self) -> None:
        show = self.selectedShow()
        history = self.histories.get(self._selectedShowKey())
        isUnsaved = self._selectedShowKey() in self.unsavedKeys
        self.ribbon.setEditState(
            bool(history and history.canUndo),
            bool(history and history.canRedo),
            show is not None and isUnsaved and show.sourcePath is not None and not show.isInConfig,
            show is not None,
        )
        if show is not None and show.isInConfig:
            self.ribbon.saveAction.setToolTip("Shows in a config file can be saved as a show file with Save as…")
        else:
            self.ribbon.saveAction.setToolTip("Write the show to its show file (Ctrl+S)")

    # The following writes the selected show to its show file, keeping the file's comments
    def saveShow(self) -> bool:
        show = self.selectedShow()
        if show is None or not self.ribbon.saveAction.isEnabled() or show.sourcePath is None:
            return False
        return self._writeShow(show, show.sourcePath)

    # The following writes the selected show to a new show file, which is then listed with the project's shows
    def saveShowAs(self) -> bool:
        show = self.selectedShow()
        if show is None:
            return False
        startFolder = self.machinePath / "shows" if self.machinePath else (show.sourcePath or Path()).parent
        fileName, _ = QFileDialog.getSaveFileName(
            self, "Save show as", str(startFolder / f"{show.name}.yaml"), "YAML files (*.yaml *.yml)"
        )
        if not fileName:
            return False
        showFile = Path(fileName)
        item = self.showList.currentShowItem()
        assert item is not None
        oldFile, wasInConfig, oldName = show.sourcePath, show.isInConfig, show.name
        # MPF names a show in a show file after the file, so the show takes the new file's name
        newName = showFile.stem
        oldKey, newKey = self._selectedShowKey(), f"{showFile}\n{newName}"
        if not self._writeShow(show, showFile):
            return False
        show.name = newName
        self.library[newName] = show
        knownFiles = showManager.findShowFiles(self.machinePath) if self.machinePath else []
        if showFile not in knownFiles and showFile not in self.extraShowFiles:
            self.extraShowFiles.append(showFile)

        # The show is now the new file's, so what is kept for it moves to the file's name.  Its token values stay with
        # the original too, which is listed again as it is in its file
        self.unsavedKeys.discard(oldKey)
        if oldKey in self.tokenValues:
            self.tokenValues[newKey] = dict(self.tokenValues[oldKey])
        if oldKey in self.histories:
            self.histories[newKey] = self.histories.pop(oldKey)
        if oldKey in self.effects:
            self.effects[newKey] = self.effects.pop(oldKey)

        # The tree is kept as the files are: the original file still has its show, and the file written has only
        # the show saved to it, in place of anything listed for it before
        self.showList.blockSignals(True)
        for staleItem in self.showList.showItemsOfFile(showFile):
            if staleItem is not item:
                self.showList.removeShow(staleItem)
        oldParent = item.parent()
        oldIndex = oldParent.indexOfChild(item) if oldParent is not None else -1
        self.showList.removeShow(item)
        if oldFile is not None and oldFile != showFile:
            original = self._reloadOriginalShow(oldFile, oldName, wasInConfig)
            if original is not None and oldName != newName:
                self.library[oldName] = original.data(0, SHOW_ROLE)
            # A show of a file with others, such as a config file, goes back to its place among them
            if original is not None and oldParent is not None and original.parent() is oldParent:
                oldParent.takeChild(oldParent.indexOfChild(original))
                oldParent.insertChild(min(oldIndex, oldParent.childCount()), original)
        newItem = self._addShowItem(showFile, show)
        self.showList.blockSignals(False)
        self.showList.selectShowItem(newItem, notify=False)
        self._updateItemLabel(newItem)
        self._updateEditState()
        return True

    # The following lists a show again as it is in its file, e.g. once its changes have been saved to another file
    def _reloadOriginalShow(self, showFile: Path, showName: str, isInConfig: bool) -> QTreeWidgetItem | None:
        if isInConfig:
            machines = [self.machinePath] if self.machinePath else []
            machines += [extraFile.parent.parent for extraFile in self.extraShowFiles]
            candidates = [show for machine in machines for show in showManager.loadConfigShows(machine)]
        else:
            candidates = showManager.loadShowFile(showFile) if showFile.is_file() else []
        original = next((show for show in candidates if show.name == showName and show.sourcePath == showFile), None)
        # A show file's show is named after the file
        if original is None and not isInConfig and candidates:
            original = candidates[0]
        return self._addShowItem(showFile, original) if original is not None else None

    def _writeShow(self, show: MPFShow, showFile: Path) -> bool:
        try:
            showManager.exportShowFile(show, showFile)
        except OSError as error:
            QMessageBox.warning(self, "Show not saved", f"The show could not be written to {showFile}:\n{error}")
            return False
        # The file's steps are now the show's steps, so each is numbered as it is in the file.  Changes from before
        # can no longer be undone, as their steps are numbered for the file as it was
        for stepNumber, step in enumerate(show.steps, start=1):
            step.stepNumber = stepNumber
        show.sourcePath, show.isInConfig = showFile, False
        self._history().clear()
        self.unsavedKeys.discard(self._selectedShowKey())
        self._updateItemLabel(self.showList.currentShowItem())
        self._updateEditState()
        self.statusBar().showMessage(f"Saved {show.name} to {showFile}", 4000)
        return True

    # The following returns whether shows have changes that are not saved
    def hasUnsavedChanges(self) -> bool:
        return bool(self.unsavedKeys)

    # The following asks whether changes not saved can be lost, returning whether they can
    def confirmDiscardChanges(self) -> bool:
        if not self.unsavedKeys:
            return True
        showNames = sorted(key.split("\n", 1)[-1] for key in self.unsavedKeys)
        answer = QMessageBox.question(
            self,
            "Unsaved changes",
            f"These shows have changes that are not saved: {', '.join(showNames)}.\nDiscard the changes?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Discard:
            return False
        self.unsavedKeys.clear()
        return True

    def _summaryText(self, show: MPFShow | None) -> str:
        if show is None:
            if self.machinePath is None:
                return "Open a show file to view it."
            return "No show files were found in this machine's shows folders. Open a show file to view one."
        lightCount = sum(not channel.isToken for channel in show.channels)
        tokenCount = len(show.channels) - lightCount
        summary = (
            f"{len(show.steps)} steps, {_formatTime(show.totalDuration)} long, "
            f"{lightCount} lights, {tokenCount} token channels, "
            f"grid of {_formatTime(self.timelineModel.resolution)} per column"
        )
        chosenTimebase = self.resolutionOption.currentData()
        if chosenTimebase and self.timelineModel.resolution > chosenTimebase + 1e-12:
            summary += f" (the {_formatTime(chosenTimebase)} timebase would make too many columns for a show this long)"
        if show.tokens:
            summary += "\nShow tokens: " + ", ".join(f"({token})" for token in show.tokens)
        if show.soundPlays:
            soundNames = dict.fromkeys(play.soundName for play in show.soundPlays)
            summary += "\nSounds: " + ", ".join(
                f"{name} ({self.timelineModel.soundStatus(name)})" for name in soundNames
            )
        if show.errors or show.timelineErrors:
            summary += "\nProblems: " + "; ".join(show.errors + show.timelineErrors)
        return summary
