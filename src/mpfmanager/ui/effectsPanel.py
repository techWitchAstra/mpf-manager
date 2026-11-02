"""Effects panel: the list of a show's lighting effects, and the settings of the one being edited"""

#   effectsPanel - Responsible for the panel beside the playfield in the
#       show viewer's effects mode: the effects drawn for the show, and the
#       shape, color, timing and movement of the chosen effect
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mpfmanager.core import showEffects
from mpfmanager.core.showEffects import LightEffect
from mpfmanager.ui.theme import sectionHeading


def _hexText(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _styleColorButton(button: QPushButton, rgb: tuple[int, int, int]) -> None:
    red, green, blue = rgb
    textColor = "black" if (red * 299 + green * 587 + blue * 114) / 1000 > 128 else "white"
    button.setText(_hexText(rgb))
    button.setStyleSheet(f"background-color: {_hexText(rgb)}; color: {textColor}; padding: 2px 8px;")


def _spin(minimum: float, maximum: float, suffix: str, step: float = 1, decimals: int = 0) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setRange(minimum, maximum)
    spin.setDecimals(decimals)
    spin.setSingleStep(step)
    spin.setSuffix(suffix)
    spin.setKeyboardTracking(False)
    return spin


# The following panel lists a show's effects and edits the chosen one.  Every change is told to the window, which
# redraws the effect on the playfield, and the effect is painted into the show when Apply is pressed
class EffectsPanel(QWidget):
    effectChanged = Signal()
    currentEffectChanged = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.effects: list[LightEffect] = []
        self._isFilling = False

        self.effectList = QListWidget()
        self.effectList.setMaximumHeight(72)
        self.effectList.currentRowChanged.connect(self._currentRowChanged)

        # The following are the effect's shape and where it is, in percent of the playfield's width
        self.nameEdit = QLineEdit()
        self.shapeOption = QComboBox()
        for shape in showEffects.SHAPES:
            self.shapeOption.addItem(shape.capitalize(), shape)
        self.centerXSpin = _spin(-100, 200, "%", 1, 1)
        self.centerYSpin = _spin(-100, 400, "%", 1, 1)
        self.widthSpin = _spin(0, 300, "%", 1, 1)
        self.heightSpin = _spin(0, 600, "%", 1, 1)
        self.rotationSpin = _spin(-360, 360, "°", 5)
        self.thicknessSpin = _spin(0.5, 50, "%", 0.5, 1)
        self.thicknessSpin.setToolTip("How thick a line, ring or spiral arm is")
        self.softnessSpin = _spin(0, 50, "%", 0.5, 1)
        self.softnessSpin.setToolTip("How far past its edge the shape lights lights more dimly")

        # The following are a pinwheel's blades or a spiral's arms: how many, how far a spiral winds, and how much of
        # the pinwheel each blade fills
        self.armsSpin = QSpinBox()
        self.armsSpin.setRange(1, 36)
        self.armsSpin.setKeyboardTracking(False)
        self.armsSpin.setToolTip("How many blades a pinwheel has, or arms a spiral has")
        self.turnsSpin = _spin(0.1, 20, " turns", 0.25, 2)
        self.turnsSpin.setToolTip("How many times a spiral's arms wind around its center")
        self.bladeFillSpin = _spin(1, 100, "%", 5)
        self.bladeFillSpin.setToolTip("How much of the pinwheel each blade fills, with the gaps between them the rest")

        # The following are its color, and the color it changes to by its end
        self.rgb: tuple[int, int, int] = (255, 255, 255)
        self.endRGB: tuple[int, int, int] = (255, 255, 255)
        self.colorButton = QPushButton()
        self.colorButton.clicked.connect(lambda: self._chooseColor(isEnd=False))
        self.endColorCheckBox = QCheckBox("Change to")
        self.endColorButton = QPushButton()
        self.endColorButton.clicked.connect(lambda: self._chooseColor(isEnd=True))
        self.intensitySpin = QSpinBox()
        self.intensitySpin.setRange(1, 100)
        self.intensitySpin.setSuffix("%")
        self.intensitySpin.setKeyboardTracking(False)

        # The following are when it runs, and the steps it is painted in
        self.startSpin = _spin(0, 3600, " s", 0.1, 3)
        self.durationSpin = _spin(0.01, 3600, " s", 0.1, 3)
        self.stepSpin = _spin(1, 10000, " ms", 10)
        self.stepSpin.setToolTip("How often the lights are worked out again as the shape moves")

        # The following are how it moves: the way and how far, the turn, the size it ends at, and its repeats
        self.moveAngleSpin = _spin(-360, 360, "°", 15)
        self.moveAngleSpin.setToolTip("The way the shape moves: 0° to the right, 90° up, 180° left, 270° down")
        self.moveDistanceSpin = _spin(0, 400, "%", 5, 1)
        self.moveDistanceSpin.setToolTip("How far the shape moves, in percent of the playfield's width")
        self.spinSpin = _spin(-3600, 3600, "°", 15)
        self.endScaleSpin = _spin(0, 1000, "%", 10)
        self.endScaleSpin.setToolTip("The size the shape grows or shrinks to by its end")
        self.repeatsSpin = QSpinBox()
        self.repeatsSpin.setRange(1, 100)
        self.repeatsSpin.setKeyboardTracking(False)
        self.bounceCheckBox = QCheckBox("Bounce back")
        self.easingOption = QComboBox()
        self.easingOption.addItems(showEffects.EASINGS)
        self.offOutsideCheckBox = QCheckBox("Turn lights off outside the shape")
        self.smoothCheckBox = QCheckBox("Fade between steps")

        self.applyButton = QPushButton("Apply to show")
        self.applyButton.setObjectName("primary")
        self.applyButton.setToolTip("Paint the effect into the show. Applying it again replaces it")

        # The following colors the effect in rainbows: laid round its middle, out from it, or across it, how many
        # rainbows fit across it, and how many times its colors go round over the effect
        self.colorModeOption = QComboBox()
        for colorMode in showEffects.COLOR_MODES:
            self.colorModeOption.addItem(colorMode.capitalize(), colorMode)
        self.colorModeOption.setToolTip("Light the effect in its color, or in a rainbow starting from its color's hue")
        self.rainbowBandsSpin = _spin(0.1, 20, "", 0.25, 2)
        self.rainbowBandsSpin.setToolTip("How many rainbows fit across the shape")
        self.rainbowCyclesSpin = _spin(-50, 50, " cycles", 0.5, 2)
        self.rainbowCyclesSpin.setToolTip(
            "How many times the rainbow's colors go round over the effect, flowing one way, or the other below 0"
        )

        # The following are a starfield's stars: their shape, size, how many there are, their colors, and how they move
        self.starShapeOption = QComboBox()
        for starShape in showEffects.STAR_SHAPES:
            self.starShapeOption.addItem(starShape.capitalize(), starShape)
        self.starSizeSpin = _spin(0.5, 50, "%", 0.5, 1)
        self.starSizeSpin.setToolTip("How big each star is, in percent of the playfield's width")
        self.starDensitySpin = _spin(0, 20, "", 0.1, 2)
        self.starDensitySpin.setToolTip("How many stars there are in each square a tenth of the playfield wide")
        self.starColoringOption = QComboBox()
        self.starColoringOption.addItems(showEffects.STAR_COLORINGS)
        self.starColoringOption.setToolTip("Light the stars in the effect's colors, or each in a color of its own")
        self.starSeedSpin = QSpinBox()
        self.starSeedSpin.setRange(1, 9999)
        self.starSeedSpin.setKeyboardTracking(False)
        self.starSeedSpin.setToolTip("Change to scatter the stars differently")
        self.starMotionOption = QComboBox()
        self.starMotionOption.addItems(showEffects.STAR_MOTIONS)
        self.starMotionOption.setToolTip(
            "Keep the stars still, drift them across the field, or fly them out from its middle (warp)"
        )
        self.starSpeedSpin = _spin(0, 500, "%/s", 5, 1)
        self.starSpeedSpin.setToolTip("How fast the stars move, in percent of the playfield's width each second")
        self.starAngleSpin = _spin(-360, 360, "°", 15)
        self.starAngleSpin.setToolTip("The way the stars drift: 0° to the right, 90° up, 180° left, 270° down")
        self.twinkleSpin = _spin(0, 100, "%", 10)
        self.twinkleSpin.setToolTip("How much the stars dim as they twinkle")
        self.twinkleRateSpin = _spin(0.05, 20, "/s", 0.25, 2)
        self.twinkleRateSpin.setToolTip("How many times each second the stars twinkle")

        colorRow = QWidget()
        colorLayout = QHBoxLayout(colorRow)
        colorLayout.setContentsMargins(0, 0, 0, 0)
        colorLayout.addWidget(self.colorButton)
        colorLayout.addWidget(self.endColorCheckBox)
        colorLayout.addWidget(self.endColorButton)

        form = QFormLayout()
        form.addRow("Name:", self.nameEdit)
        form.addRow("Shape:", self.shapeOption)
        form.addRow("Center:", _pair(self.centerXSpin, self.centerYSpin))
        form.addRow("Size:", _pair(self.widthSpin, self.heightSpin))
        form.addRow("Rotation:", self.rotationSpin)
        form.addRow("Thickness:", self.thicknessSpin)
        form.addRow("Soft edge:", self.softnessSpin)
        form.addRow("Arms:", self.armsSpin)
        form.addRow("Spiral:", self.turnsSpin)
        form.addRow("Blade fill:", self.bladeFillSpin)
        form.addRow("Color:", colorRow)
        form.addRow("Colors:", self.colorModeOption)
        form.addRow("Rainbows:", _pair(self.rainbowBandsSpin, self.rainbowCyclesSpin))
        form.addRow("Intensity:", self.intensitySpin)
        form.addRow("Starts at:", self.startSpin)
        form.addRow("Lasts:", self.durationSpin)
        form.addRow("Step:", self.stepSpin)
        form.addRow(_heading("Stars"))
        form.addRow("Star shape:", self.starShapeOption)
        form.addRow("Star size:", self.starSizeSpin)
        form.addRow("Density:", self.starDensitySpin)
        form.addRow("Star colors:", self.starColoringOption)
        form.addRow("Shuffle:", self.starSeedSpin)
        form.addRow("Star motion:", self.starMotionOption)
        form.addRow("Star speed:", _pair(self.starSpeedSpin, self.starAngleSpin))
        form.addRow("Twinkle:", _pair(self.twinkleSpin, self.twinkleRateSpin))
        form.addRow(_heading("Movement"))
        form.addRow("Moves:", _pair(self.moveAngleSpin, self.moveDistanceSpin))
        form.addRow("Turns:", self.spinSpin)
        form.addRow("Ends at size:", self.endScaleSpin)
        form.addRow("Runs:", _pair(self.repeatsSpin, QLabel("times")))
        form.addRow("", self.bounceCheckBox)
        form.addRow("Easing:", self.easingOption)
        form.addRow(_heading("Lights"))
        form.addRow("", self.offOutsideCheckBox)
        form.addRow("", self.smoothCheckBox)

        self.settingsWidget = QWidget()
        self.settingsWidget.setLayout(form)
        scrollArea = QScrollArea()
        scrollArea.setWidgetResizable(True)
        scrollArea.setWidget(self.settingsWidget)
        scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.emptyLabel = QLabel("Choose a shape on the Effects tab and drag on the playfield to draw an effect.")
        self.emptyLabel.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(sectionHeading("Effects"))
        layout.addWidget(self.effectList)
        layout.addWidget(self.emptyLabel)
        layout.addWidget(scrollArea, 1)
        layout.addWidget(self.applyButton)

        # Every setting is written to the effect when it is changed
        for spin in (
            self.centerXSpin,
            self.centerYSpin,
            self.widthSpin,
            self.heightSpin,
            self.rotationSpin,
            self.thicknessSpin,
            self.softnessSpin,
            self.turnsSpin,
            self.bladeFillSpin,
            self.rainbowBandsSpin,
            self.rainbowCyclesSpin,
            self.starSizeSpin,
            self.starDensitySpin,
            self.starSpeedSpin,
            self.starAngleSpin,
            self.twinkleSpin,
            self.twinkleRateSpin,
            self.startSpin,
            self.durationSpin,
            self.stepSpin,
            self.moveAngleSpin,
            self.moveDistanceSpin,
            self.spinSpin,
            self.endScaleSpin,
        ):
            spin.valueChanged.connect(self._writeEffect)
        for intSpin in (self.intensitySpin, self.repeatsSpin, self.armsSpin, self.starSeedSpin):
            intSpin.valueChanged.connect(self._writeEffect)
        for checkBox in (self.endColorCheckBox, self.bounceCheckBox, self.offOutsideCheckBox, self.smoothCheckBox):
            checkBox.toggled.connect(self._writeEffect)
        for option in (
            self.shapeOption,
            self.easingOption,
            self.colorModeOption,
            self.starShapeOption,
            self.starColoringOption,
            self.starMotionOption,
        ):
            option.currentIndexChanged.connect(self._writeEffect)
        self.nameEdit.editingFinished.connect(self._writeEffect)
        self.setEffects([])

    # The following lists a show's effects, choosing one of them
    def setEffects(self, effects: list[LightEffect], currentIndex: int | None = None) -> None:
        self.effects = effects
        self.effectList.blockSignals(True)
        self.effectList.clear()
        self.effectList.addItems([effect.name for effect in effects])
        if effects:
            index = len(effects) - 1 if currentIndex is None else min(max(currentIndex, 0), len(effects) - 1)
            self.effectList.setCurrentRow(index)
        self.effectList.blockSignals(False)
        self._fillSettings()

    def currentEffect(self) -> LightEffect | None:
        row = self.effectList.currentRow()
        return self.effects[row] if 0 <= row < len(self.effects) else None

    def currentIndex(self) -> int | None:
        row = self.effectList.currentRow()
        return row if 0 <= row < len(self.effects) else None

    def setCurrentIndex(self, index: int) -> None:
        self.effectList.setCurrentRow(index)

    def _currentRowChanged(self, _row: int) -> None:
        self._fillSettings()
        self.currentEffectChanged.emit()

    # The following shows the chosen effect's settings, e.g. after it is moved on the playfield
    def refresh(self) -> None:
        self._fillSettings()

    def _fillSettings(self) -> None:
        effect = self.currentEffect()
        self.settingsWidget.setEnabled(effect is not None)
        self.applyButton.setEnabled(effect is not None)
        self.emptyLabel.setVisible(not self.effects)
        if effect is None:
            return
        self._isFilling = True
        place = effect.place
        self.nameEdit.setText(effect.name)
        self.shapeOption.setCurrentIndex(self.shapeOption.findData(effect.shape))
        for spin, value in (
            (self.centerXSpin, place.centerX * 100),
            (self.centerYSpin, place.centerY * 100),
            (self.widthSpin, place.width * 100),
            (self.heightSpin, place.height * 100),
            (self.rotationSpin, place.rotation),
            (self.thicknessSpin, effect.thickness * 100),
            (self.softnessSpin, effect.softness * 100),
            (self.turnsSpin, effect.turns),
            (self.bladeFillSpin, effect.bladeFill * 100),
            (self.rainbowBandsSpin, effect.rainbowBands),
            (self.rainbowCyclesSpin, effect.rainbowCycles),
            (self.starSizeSpin, effect.starSize * 100),
            (self.starDensitySpin, effect.starDensity),
            (self.starSpeedSpin, effect.starSpeed * 100),
            (self.starAngleSpin, effect.starAngle),
            (self.twinkleSpin, effect.twinkle * 100),
            (self.twinkleRateSpin, effect.twinkleRate),
            (self.startSpin, effect.startTime),
            (self.durationSpin, effect.duration),
            (self.stepSpin, effect.stepTime * 1000),
            (self.moveAngleSpin, effect.moveAngle),
            (self.moveDistanceSpin, effect.moveDistance * 100),
            (self.spinSpin, effect.spin),
            (self.endScaleSpin, effect.endScale * 100),
        ):
            spin.setValue(value)
        self.intensitySpin.setValue(effect.intensity)
        self.repeatsSpin.setValue(effect.repeats)
        self.armsSpin.setValue(effect.arms)
        self.starSeedSpin.setValue(effect.starSeed)
        self.colorModeOption.setCurrentIndex(max(self.colorModeOption.findData(effect.colorMode), 0))
        self.starShapeOption.setCurrentIndex(max(self.starShapeOption.findData(effect.starShape), 0))
        self.starColoringOption.setCurrentText(effect.starColoring)
        self.starMotionOption.setCurrentText(effect.starMotion)
        self.rgb = effect.rgb
        self.endRGB = effect.endRGB or effect.rgb
        self.endColorCheckBox.setChecked(effect.endRGB is not None)
        self.bounceCheckBox.setChecked(effect.bounce)
        self.easingOption.setCurrentText(effect.easing)
        self.offOutsideCheckBox.setChecked(effect.offOutside)
        self.smoothCheckBox.setChecked(effect.smooth)
        self._updateColorButtons()
        self._isFilling = False

    def _updateColorButtons(self) -> None:
        _styleColorButton(self.colorButton, self.rgb)
        _styleColorButton(self.endColorButton, self.endRGB)
        self.endColorButton.setEnabled(self.endColorCheckBox.isChecked())
        effect = self.currentEffect()
        shape = effect.shape if effect is not None else ""
        self.thicknessSpin.setEnabled(
            shape in (showEffects.SHAPE_LINE, showEffects.SHAPE_RING, showEffects.SHAPE_SPIRAL)
        )
        self.armsSpin.setEnabled(shape in showEffects.ARMED_SHAPES)
        self.turnsSpin.setEnabled(shape == showEffects.SHAPE_SPIRAL)
        self.bladeFillSpin.setEnabled(shape == showEffects.SHAPE_PINWHEEL)
        isRainbow = self.colorModeOption.currentData() != showEffects.COLOR_SOLID
        self.rainbowBandsSpin.setEnabled(isRainbow)
        self.rainbowCyclesSpin.setEnabled(isRainbow)
        isStarfield = shape == showEffects.SHAPE_STARFIELD
        for starWidget in (
            self.starShapeOption,
            self.starSizeSpin,
            self.starDensitySpin,
            self.starColoringOption,
            self.starSeedSpin,
            self.starMotionOption,
            self.starSpeedSpin,
            self.twinkleSpin,
            self.twinkleRateSpin,
        ):
            starWidget.setEnabled(isStarfield)
        self.starAngleSpin.setEnabled(isStarfield and self.starMotionOption.currentText() == showEffects.STARS_DRIFT)
        self.heightSpin.setEnabled(effect is not None and effect.shape != showEffects.SHAPE_LINE)

    def _chooseColor(self, isEnd: bool, chooser: Callable[..., QColor] | None = None) -> None:
        chosenColor = (chooser or QColorDialog.getColor)(QColor(*(self.endRGB if isEnd else self.rgb)), self, "Color")
        if not chosenColor.isValid():
            return
        rgb = (chosenColor.red(), chosenColor.green(), chosenColor.blue())
        if isEnd:
            self.endRGB = rgb
            self.endColorCheckBox.setChecked(True)
        else:
            self.rgb = rgb
        self._writeEffect()

    # The following writes the settings shown to the chosen effect
    def _writeEffect(self) -> None:
        effect = self.currentEffect()
        if effect is None or self._isFilling:
            return
        effect.name = self.nameEdit.text().strip() or effect.name
        effect.shape = self.shapeOption.currentData()
        effect.place.centerX = self.centerXSpin.value() / 100
        effect.place.centerY = self.centerYSpin.value() / 100
        effect.place.width = self.widthSpin.value() / 100
        effect.place.height = self.heightSpin.value() / 100
        effect.place.rotation = self.rotationSpin.value()
        effect.thickness = self.thicknessSpin.value() / 100
        effect.softness = self.softnessSpin.value() / 100
        effect.arms = self.armsSpin.value()
        effect.turns = self.turnsSpin.value()
        effect.bladeFill = self.bladeFillSpin.value() / 100
        effect.colorMode = self.colorModeOption.currentData()
        effect.rainbowBands = self.rainbowBandsSpin.value()
        effect.rainbowCycles = self.rainbowCyclesSpin.value()
        effect.starShape = self.starShapeOption.currentData()
        effect.starSize = self.starSizeSpin.value() / 100
        effect.starDensity = self.starDensitySpin.value()
        effect.starColoring = self.starColoringOption.currentText()
        effect.starSeed = self.starSeedSpin.value()
        effect.starMotion = self.starMotionOption.currentText()
        effect.starSpeed = self.starSpeedSpin.value() / 100
        effect.starAngle = self.starAngleSpin.value()
        effect.twinkle = self.twinkleSpin.value() / 100
        effect.twinkleRate = self.twinkleRateSpin.value()
        effect.rgb = self.rgb
        effect.endRGB = self.endRGB if self.endColorCheckBox.isChecked() else None
        effect.intensity = self.intensitySpin.value()
        effect.startTime = self.startSpin.value()
        effect.duration = self.durationSpin.value()
        effect.stepTime = self.stepSpin.value() / 1000
        effect.moveAngle = self.moveAngleSpin.value()
        effect.moveDistance = self.moveDistanceSpin.value() / 100
        effect.spin = self.spinSpin.value()
        effect.endScale = self.endScaleSpin.value() / 100
        effect.repeats = self.repeatsSpin.value()
        effect.bounce = self.bounceCheckBox.isChecked()
        effect.easing = self.easingOption.currentText()
        effect.offOutside = self.offOutsideCheckBox.isChecked()
        effect.smooth = self.smoothCheckBox.isChecked()
        item = self.effectList.currentItem()
        if item is not None:
            item.setText(effect.name)
        self._updateColorButtons()
        self.effectChanged.emit()


def _pair(first: QWidget, second: QWidget) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(first)
    layout.addWidget(second)
    return row


def _heading(text: str) -> QLabel:
    label = QLabel(f"<b>{text}</b>")
    return label
