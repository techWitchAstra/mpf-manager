"""Show tools: the tools for painting lights in the show viewer's grid"""

#   showTools - Responsible for the ribbon of the show viewer, with the show
#       file, clipboard and undo actions, the tools (paint, erase or pick a
#       color) along with the color, intensity and fade that lights are
#       painted with, and what can be done with the cells chosen in the grid
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QStandardItemModel
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QToolButton,
    QWidget,
)

from mpfmanager.core import showEditor
from mpfmanager.core.showManager import LightSetting
from mpfmanager.ui.ribbon import Ribbon, ribbonIcon

# The following are the tools: moving the playhead, painting lights, erasing what the show sets them to, and picking
# the color to paint with from a cell
TOOL_SELECT = "select"
TOOL_PAINT = "paint"
TOOL_ERASE = "erase"
TOOL_PICK = "pick"
TOOLS = {
    TOOL_SELECT: (
        "Select",
        "Click the grid to move the playhead, and drag over cells to copy them, chase them or make a show of them",
    ),
    TOOL_PAINT: ("Paint", "Drag over cells to paint the lights with the color, intensity and fade"),
    TOOL_ERASE: ("Erase", "Drag over cells to take out what the show sets the lights to there"),
    TOOL_PICK: ("Pick", "Click a cell to paint with its color and intensity"),
}
TOOL_SHORTCUTS = {TOOL_SELECT: "V", TOOL_PAINT: "B", TOOL_ERASE: "E", TOOL_PICK: "I"}
TOOL_SYMBOLS = {TOOL_SELECT: "↖", TOOL_PAINT: "✎", TOOL_ERASE: "⌫", TOOL_PICK: "◉"}

# The following are the colors offered as swatches for painting quickly
SWATCH_COLORS = {
    "red": (255, 0, 0),
    "orange": (255, 165, 0),
    "yellow": (255, 255, 0),
    "lime": (0, 255, 0),
    "cyan": (0, 255, 255),
    "blue": (0, 0, 255),
    "purple": (128, 0, 128),
    "magenta": (255, 0, 255),
    "white": (255, 255, 255),
    "off": (0, 0, 0),
}


def _hexText(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _textColorName(rgb: tuple[int, int, int]) -> str:
    red, green, blue = rgb
    return "black" if (red * 299 + green * 587 + blue * 114) / 1000 > 128 else "white"


# The following is the show editor's ribbon.  Its tabs hold the tools for each type of item: the Home tab the show
# file, the clipboard and undo, and the Cells tab the tools with the paint color, intensity and fade, and what can be
# done with the cells chosen in the grid.  The window adds tabs of its own, for playback, the view and the
# playfield.  Each button is an action, so the window's menus can offer the same actions with their shortcuts
class ShowRibbon(Ribbon):
    toolChanged = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.paintRGB: tuple[int, int, int] = (255, 0, 0)
        ThemeIcon = QIcon.ThemeIcon

        # The following are the show file and edit actions, given their shortcuts by the window
        self.newShowAction = self._action(
            "New show…", "Make a new, blank show file (Ctrl+N)", ThemeIcon.DocumentNew, "✚"
        )
        self.openAction = self._action("Open…", "Open a show file (Ctrl+O)", ThemeIcon.DocumentOpen, "📂")
        self.reloadAction = self._action(
            "Reload", "Read the show files again, e.g. after editing them (F5)", ThemeIcon.ViewRefresh, "⟳"
        )
        self.saveAction = self._action("Save", "Write the show to its show file (Ctrl+S)", ThemeIcon.DocumentSave, "💾")
        self.saveAsAction = self._action(
            "Save as…", "Write the show to a new show file (Ctrl+Shift+S)", ThemeIcon.DocumentSaveAs, "🖫"
        )
        self.undoAction = self._action("Undo", "Undo the last change to the show (Ctrl+Z)", ThemeIcon.EditUndo, "↶")
        self.redoAction = self._action("Redo", "Redo the change undone (Ctrl+Shift+Z)", ThemeIcon.EditRedo, "↷")
        self.copyAction = self._action(
            "Copy", "Copy what the show sets the chosen lights to (Ctrl+C)", ThemeIcon.EditCopy, "⧉"
        )
        self.pasteAction = self._action(
            "Paste",
            "Paste where the chosen cells start, onto the chosen lights, or at the playhead onto the lights copied (Ctrl+V)",
            ThemeIcon.EditPaste,
            "📋",
        )

        # The following act on the cells chosen in the grid
        self.repeatAction = self._action(
            "Repeat…", "Repeat the chosen cells straight after themselves (Ctrl+D repeats once)", None, "⇉"
        )
        self.repeatOnceAction = self._action("Repeat once", "Repeat the chosen cells once, straight after themselves")
        self.chaseAction = self._action(
            "Chase…", "Paint a chase over the chosen lights with the paint color", None, "⇶"
        )
        self.makeShowAction = self._action(
            "Make show…",
            "Make a show of the chosen cells, with the lights and colors as show tokens, and play it there instead",
            None,
            "★",
        )
        self.addLightAction = self._action(
            "Add light…",
            "Add a row for a light or tag of the machine the show does not set yet",
            ThemeIcon.ListAdd,
            "+",
        )
        self.removeLightAction = self._action(
            "Remove light",
            "Take the chosen rows' lights out of the show, everywhere it sets them",
            ThemeIcon.ListRemove,
            "−",
        )

        # The following are the tools, chosen one at a time
        self.toolActions: dict[str, QAction] = {}
        self.toolGroup = QActionGroup(self)
        self.toolGroup.setExclusive(True)
        for tool, (label, tooltip) in TOOLS.items():
            action = self._action(label, f"{tooltip} ({TOOL_SHORTCUTS[tool]})", None, TOOL_SYMBOLS[tool])
            action.setCheckable(True)
            action.toggled.connect(lambda checked, chosen=tool: checked and self.toolChanged.emit(chosen))
            self.toolGroup.addAction(action)
            self.toolActions[tool] = action

        # The following is the color lights are painted with, chosen from a dialog or a swatch
        self.colorButton = QPushButton()
        self.colorButton.setToolTip("Choose the color to paint with")
        self.colorButton.setMinimumWidth(90)
        self.colorButton.clicked.connect(self.chooseColor)
        self.swatchButtons: dict[str, QToolButton] = {}
        for colorName, rgb in SWATCH_COLORS.items():
            swatch = QToolButton()
            swatch.setToolTip(colorName)
            swatch.setFixedSize(18, 18)
            swatch.setStyleSheet(f"background-color: {_hexText(rgb)}; border: 1px solid #777;")
            swatch.clicked.connect(lambda _checked=False, chosen=rgb: self.setColor(chosen))
            self.swatchButtons[colorName] = swatch

        # The following is the intensity lights are painted at, written as a brightness such as red%50
        self.intensitySlider = QSlider(Qt.Orientation.Horizontal)
        self.intensitySlider.setRange(0, 100)
        self.intensitySlider.setValue(100)
        self.intensitySlider.setMinimumWidth(80)
        self.intensitySlider.setMaximumWidth(140)
        self.intensitySpin = QSpinBox()
        self.intensitySpin.setRange(0, 100)
        self.intensitySpin.setSuffix("%")
        self.intensitySpin.setValue(100)
        self.intensitySpin.setToolTip("The intensity to paint with, written as the color's brightness, e.g. red%50")
        self.intensitySlider.valueChanged.connect(self.intensitySpin.setValue)
        self.intensitySpin.valueChanged.connect(self.intensitySlider.setValue)
        self.intensitySpin.valueChanged.connect(self._updateColorButton)

        # The following is how long painted lights take to fade into their color
        self.fadeSpin = QSpinBox()
        self.fadeSpin.setRange(0, 60000)
        self.fadeSpin.setSingleStep(50)
        self.fadeSpin.setSuffix(" ms")
        self.fadeSpin.setToolTip("How long a painted light takes to fade into its color")

        # The following lays out the tabs
        homeTab = self.addRibbonTab("Home")
        fileGroup = homeTab.addGroup("Show file")
        self.newShowButton = fileGroup.addLargeAction(self.newShowAction)
        self.openButton = fileGroup.addLargeAction(self.openAction)
        self.saveButton = fileGroup.addLargeAction(self.saveAction)
        self.saveAsButton = fileGroup.addSmallAction(self.saveAsAction)
        self.reloadButton = fileGroup.addSmallAction(self.reloadAction)
        clipboardGroup = homeTab.addGroup("Clipboard")
        self.pasteButton = clipboardGroup.addLargeAction(self.pasteAction)
        self.copyButton = clipboardGroup.addSmallAction(self.copyAction)
        historyGroup = homeTab.addGroup("History")
        self.undoButton = historyGroup.addLargeAction(self.undoAction)
        self.redoButton = historyGroup.addLargeAction(self.redoAction)

        cellsTab = self.addRibbonTab("Cells")
        toolGroup = cellsTab.addGroup("Tools")
        self.toolButtons: dict[str, QToolButton] = {
            tool: toolGroup.addLargeAction(action) for tool, action in self.toolActions.items()
        }
        colorGroup = cellsTab.addGroup("Color")
        colorGroup.addSmallWidget(self.colorButton)
        colorGroup.addGrid(list(self.swatchButtons.values()), columns=5)
        settingGroup = cellsTab.addGroup("Brightness and fade")
        intensityRow = QWidget()
        intensityLayout = QHBoxLayout(intensityRow)
        intensityLayout.setContentsMargins(0, 0, 0, 0)
        intensityLayout.addWidget(self.intensitySlider)
        intensityLayout.addWidget(self.intensitySpin)
        settingGroup.addSmallWidget(intensityRow, "Intensity:")
        settingGroup.addSmallWidget(self.fadeSpin, "Fade:")

        patternGroup = cellsTab.addGroup("Patterns")
        self.repeatButton = patternGroup.addLargeAction(self.repeatAction)
        self.chaseButton = patternGroup.addLargeAction(self.chaseAction)
        reuseGroup = cellsTab.addGroup("Reuse")
        self.makeShowButton = reuseGroup.addLargeAction(self.makeShowAction)
        rowsGroup = cellsTab.addGroup("Rows")
        self.addLightButton = rowsGroup.addLargeAction(self.addLightAction)
        self.removeLightButton = rowsGroup.addLargeAction(self.removeLightAction)

        self.toolActions[TOOL_SELECT].setChecked(True)
        self._updateColorButton()

    def _action(
        self, text: str, tooltip: str, themeIcon: QIcon.ThemeIcon | None = None, symbol: str | None = None
    ) -> QAction:
        action = QAction(text, self)
        action.setToolTip(tooltip)
        action.setStatusTip(tooltip)
        if symbol is not None:
            action.setIcon(ribbonIcon(themeIcon, symbol))
        return action

    @property
    def currentTool(self) -> str:
        return next((tool for tool, action in self.toolActions.items() if action.isChecked()), TOOL_SELECT)

    def setTool(self, tool: str) -> None:
        self.toolActions[tool].setChecked(True)

    @property
    def intensity(self) -> int:
        return self.intensitySpin.value()

    @property
    def fadeMs(self) -> int:
        return self.fadeSpin.value()

    # The following sets the color to paint with, and its intensity when one is given
    def setColor(self, rgb: tuple[int, int, int], intensity: int | None = None) -> None:
        self.paintRGB = rgb
        if intensity is not None:
            self.intensitySpin.setValue(intensity)
        self._updateColorButton()

    def chooseColor(self) -> None:
        chosenColor = QColorDialog.getColor(QColor(*self.paintRGB), self, "Paint color")
        if chosenColor.isValid():
            self.setColor((chosenColor.red(), chosenColor.green(), chosenColor.blue()))

    # The following shows the paint color as it will look at the chosen intensity
    def _updateColorButton(self) -> None:
        shownRGB = showEditor.paintSetting(self.paintRGB, self.intensity).rgb or self.paintRGB
        self.colorButton.setText(showEditor.colorValue(self.paintRGB, self.intensity))
        self.colorButton.setStyleSheet(
            f"background-color: {_hexText(shownRGB)}; color: {_textColorName(shownRGB)}; padding: 2px 8px;"
        )

    # The following returns the setting lights are painted with, written with the project's color names
    def paintSetting(self, namedColors: dict[str, tuple[int, int, int]] | None = None) -> LightSetting:
        return showEditor.paintSetting(self.paintRGB, self.intensity, self.fadeMs, namedColors)

    # The following enables undo, redo and save for what can be done
    def setEditState(self, canUndo: bool, canRedo: bool, canSave: bool, canSaveAs: bool) -> None:
        self.undoAction.setEnabled(canUndo)
        self.redoAction.setEnabled(canRedo)
        self.saveAction.setEnabled(canSave)
        self.saveAsAction.setEnabled(canSaveAs)


# The following dialog asks how a chase runs: the order of the lights, its pattern, how long each step of it is, how
# many lights are lit together, and what the lights are between being lit
class ChaseDialog(QDialog):
    BETWEEN_OFF = "Off"
    BETWEEN_UNCHANGED = "As they were"

    def __init__(
        self, lightCount: int, stepMs: int, paintValue: str, hasPositions: bool, parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setWindowTitle("Chase")
        layout = QFormLayout(self)
        layout.addRow(QLabel(f"Chase {lightCount} lights with {paintValue}, the paint color"))

        self.orderOption = QComboBox()
        self.orderOption.addItems(showEditor.LIGHT_ORDERS)
        if not hasPositions:
            # Without a playfield layout the lights can only be chased in the grid's order
            orderModel = self.orderOption.model()
            assert isinstance(orderModel, QStandardItemModel)
            for row in range(1, self.orderOption.count()):
                orderItem = orderModel.item(row)
                if orderItem is not None:
                    orderItem.setEnabled(False)
            self.orderOption.setToolTip("Lights can be ordered by the playfield when it has an MPF-Monitor layout")
        layout.addRow("Light order:", self.orderOption)

        self.patternOption = QComboBox()
        self.patternOption.addItems(showEditor.CHASE_PATTERNS)
        layout.addRow("Pattern:", self.patternOption)

        self.stepSpin = QSpinBox()
        self.stepSpin.setRange(1, 60000)
        self.stepSpin.setSuffix(" ms")
        self.stepSpin.setValue(max(stepMs, 1))
        layout.addRow("Step time:", self.stepSpin)

        self.widthSpin = QSpinBox()
        self.widthSpin.setRange(1, max(lightCount, 1))
        self.widthSpin.setToolTip("How many lights are lit together, as a tail behind the chase")
        layout.addRow("Lights lit:", self.widthSpin)

        self.betweenOption = QComboBox()
        self.betweenOption.addItems([self.BETWEEN_OFF, self.BETWEEN_UNCHANGED])
        self.betweenOption.setToolTip("What the lights are while the chase is not lighting them")
        layout.addRow("Between:", self.betweenOption)

        self.fadeOutSpin = QSpinBox()
        self.fadeOutSpin.setRange(0, 60000)
        self.fadeOutSpin.setSingleStep(50)
        self.fadeOutSpin.setSuffix(" ms")
        self.fadeOutSpin.setToolTip("How long lights take to fade off after the chase leaves them")
        self.betweenOption.currentTextChanged.connect(
            lambda text: self.fadeOutSpin.setEnabled(text == self.BETWEEN_OFF)
        )
        layout.addRow("Fade off:", self.fadeOutSpin)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    @property
    def order(self) -> str:
        return self.orderOption.currentText()

    @property
    def pattern(self) -> str:
        return self.patternOption.currentText()

    @property
    def stepTime(self) -> float:
        return self.stepSpin.value() / 1000

    @property
    def litCount(self) -> int:
        return self.widthSpin.value()

    # The following returns the setting lights are given between being lit, or None to leave them as they were
    def betweenSetting(self) -> LightSetting | None:
        if self.betweenOption.currentText() == self.BETWEEN_UNCHANGED:
            return None
        return showEditor.paintSetting((0, 0, 0), 100, self.fadeOutSpin.value())


# The following dialog asks for the name of a show made from cells of the grid, and whether its colors are tokens too
class ReusableShowDialog(QDialog):
    def __init__(self, defaultName: str, lightCount: int, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Make show")
        layout = QFormLayout(self)
        explanation = QLabel(
            f"The {lightCount} chosen lights become show tokens, (light1), (light2) and so on, so the new show can be "
            "played on any lights. The show being edited plays it there instead, with show_tokens for these lights."
        )
        explanation.setWordWrap(True)
        layout.addRow(explanation)
        self.nameEdit = QLineEdit(defaultName)
        layout.addRow("Show name:", self.nameEdit)
        self.tokenizeColorsCheckBox = QCheckBox("Make the colors show tokens too, (color1) and so on")
        self.tokenizeColorsCheckBox.setChecked(True)
        layout.addRow(self.tokenizeColorsCheckBox)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.nameEdit.textChanged.connect(self._checkName)
        layout.addRow(self.buttons)
        self._checkName()

    @property
    def showName(self) -> str:
        return self.nameEdit.text().strip()

    @property
    def tokenizeColors(self) -> bool:
        return self.tokenizeColorsCheckBox.isChecked()

    # A show name is used as its file's name and in show_player, so it is letters, numbers and underscores
    def _checkName(self) -> None:
        okButton = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        okButton.setEnabled(bool(re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", self.showName)))


# A show's name is used as its file's name and in show_player, so it is letters, numbers and underscores
SHOW_NAME_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")


# The following dialog asks for a new show's name, the folder its file is made in, and how long it lasts
class NewShowDialog(QDialog):
    def __init__(
        self, folder: Path, takenNames: set[str], defaultName: str = "new_show", parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.setWindowTitle("New show")
        self.setMinimumWidth(460)
        self.takenNames = takenNames
        layout = QFormLayout(self)
        self.nameEdit = QLineEdit(defaultName)
        self.nameEdit.setToolTip("Letters, numbers and underscores. The show's file is named after it")
        layout.addRow("Show name:", self.nameEdit)
        self.folderEdit = QLineEdit(str(folder))
        browseButton = QPushButton("Browse…")
        browseButton.clicked.connect(self._browse)
        folderRow = QWidget()
        folderLayout = QHBoxLayout(folderRow)
        folderLayout.setContentsMargins(0, 0, 0, 0)
        folderLayout.addWidget(self.folderEdit, 1)
        folderLayout.addWidget(browseButton)
        layout.addRow("Folder:", folderRow)
        self.lengthSpin = QDoubleSpinBox()
        self.lengthSpin.setRange(0.01, 3600)
        self.lengthSpin.setDecimals(3)
        self.lengthSpin.setSingleStep(0.5)
        self.lengthSpin.setSuffix(" s")
        self.lengthSpin.setValue(2.0)
        self.lengthSpin.setToolTip("How long the show lasts. It grows as lights and sounds are put past its end")
        layout.addRow("Length:", self.lengthSpin)
        self.problemLabel = QLabel()
        self.problemLabel.setWordWrap(True)
        layout.addRow(self.problemLabel)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)
        self.nameEdit.textChanged.connect(self._check)
        self.folderEdit.textChanged.connect(self._check)
        self._check()

    @property
    def showName(self) -> str:
        return self.nameEdit.text().strip()

    @property
    def showFile(self) -> Path:
        return Path(self.folderEdit.text().strip()).expanduser() / f"{self.showName}.yaml"

    @property
    def length(self) -> float:
        return self.lengthSpin.value()

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Folder for the show", self.folderEdit.text())
        if folder:
            self.folderEdit.setText(folder)

    # The following explains why a show cannot be made with the name and folder given, if it cannot
    def problem(self) -> str:
        if not SHOW_NAME_RE.fullmatch(self.showName):
            return "Use letters, numbers and underscores for the name."
        if self.showName in self.takenNames:
            return f"There is already a show called {self.showName}."
        if not self.folderEdit.text().strip():
            return "Choose a folder for the show."
        if self.showFile.exists():
            return f"{self.showFile} already exists."
        return ""

    def _check(self) -> None:
        problem = self.problem()
        self.problemLabel.setText(problem)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(not problem)


# The following dialog asks which sound a show plays, when, and how: its volume, how many times it loops, where in the
# sound it starts, and how long it takes to fade in
class AddSoundDialog(QDialog):
    def __init__(self, soundNames: list[str], atTime: float, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Add sound")
        self.setMinimumWidth(420)
        layout = QFormLayout(self)
        self.soundOption = QComboBox()
        self.soundOption.setEditable(True)
        self.soundOption.addItems(soundNames)
        self.soundOption.setToolTip("The machine's sounds, by name. A sound's name can be typed in too")
        layout.addRow("Sound:", self.soundOption)
        if not soundNames:
            noSounds = QLabel("No sound files were found in this machine's folder. Type a sound's name to play it.")
            noSounds.setWordWrap(True)
            layout.addRow(noSounds)
        self.startSpin = _secondsSpin(atTime, 3600)
        self.startSpin.setToolTip("When the show plays the sound")
        layout.addRow("Plays at:", self.startSpin)
        self.volumeSpin = QSpinBox()
        self.volumeSpin.setRange(0, 100)
        self.volumeSpin.setSuffix("%")
        self.volumeSpin.setValue(100)
        layout.addRow("Volume:", self.volumeSpin)
        self.loopsSpin = QSpinBox()
        self.loopsSpin.setRange(-1, 999)
        self.loopsSpin.setSpecialValueText("forever")
        self.loopsSpin.setValue(0)
        self.loopsSpin.setToolTip("How many more times the sound plays after the first, or forever")
        layout.addRow("Loops:", self.loopsSpin)
        self.startAtSpin = _secondsSpin(0.0, 3600)
        self.startAtSpin.setToolTip("Where in the sound it starts playing from")
        layout.addRow("Starts at:", self.startAtSpin)
        self.fadeInSpin = _secondsSpin(0.0, 600)
        layout.addRow("Fades in over:", self.fadeInSpin)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addRow(self.buttons)
        self.soundOption.currentTextChanged.connect(self._check)
        self._check()

    @property
    def soundName(self) -> str:
        return self.soundOption.currentText().strip()

    @property
    def atTime(self) -> float:
        return self.startSpin.value()

    # The following returns the sound's settings as a show's sounds: section writes them
    def settings(self) -> dict[str, float | int]:
        return {
            "volume": round(self.volumeSpin.value() / 100, 2),
            "loops": self.loopsSpin.value(),
            "start_at": round(self.startAtSpin.value(), 3),
            "fade_in": round(self.fadeInSpin.value(), 3),
        }

    def _check(self) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(self.soundName))


# The following dialog asks which of the sounds a show's own steps play to take out
class RemoveSoundDialog(QDialog):
    def __init__(self, entries: list[tuple[float, str]], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Remove sound")
        layout = QFormLayout(self)
        self.entryOption = QComboBox()
        for atTime, soundName in entries:
            self.entryOption.addItem(f"{soundName}  at {atTime:g}s", (atTime, soundName))
        layout.addRow("Sound:", self.entryOption)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def chosenEntry(self) -> tuple[float, str] | None:
        return self.entryOption.currentData()


def _secondsSpin(value: float, maximum: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(0, maximum)
    spin.setDecimals(3)
    spin.setSingleStep(0.1)
    spin.setSuffix(" s")
    spin.setValue(value)
    return spin
