import math

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor
from test_showViewer import _colorAt, _lightColor, _machine, _playbackMachine

from mpfmanager.core import showEffects
from mpfmanager.ui.showViewer import EFFECTS_RIBBON_TAB, ShowViewerWindow


def _effectsWindow(qtbot, tmp_path) -> ShowViewerWindow:
    window = ShowViewerWindow(_playbackMachine(tmp_path))
    qtbot.addWidget(window)
    window.resize(1400, 800)
    window.show()
    window.resolutionOption.setCurrentIndex(window.resolutionOption.findData(0.25))
    window.ribbon.setCurrentIndex(EFFECTS_RIBBON_TAB)
    return window


def _viewPoint(window: ShowViewerWindow, x: float, y: float):
    width = window.playfieldView.scene().sceneRect().width()
    return window.playfieldView.mapFromScene(QPointF(x * width, y * width))


def test_effectsTabShowsTheEffects(qtbot, tmp_path):
    window = _effectsWindow(qtbot, tmp_path)
    assert window.ribbon.tabText(EFFECTS_RIBBON_TAB) == "Effects"
    assert window.isEffectsMode and window.effectsPanel.isVisible() and window.playfieldView.isEffectsMode
    assert window.effectsPanel.emptyLabel.isVisible()
    assert not window.applyEffectAction.isEnabled()
    window.ribbon.setCurrentIndex(0)
    assert not window.effectsPanel.isVisible() and not window.playfieldView.isEffectsMode


def test_drawingAnEffectOnThePlayfield(qtbot, tmp_path):
    window = _effectsWindow(qtbot, tmp_path)
    window.ribbon.setColor((255, 0, 0))
    view = window.playfieldView
    aspect = view.aspect()
    lowX, lowY = window.effectLightPositions()["l_a"]
    assert (lowX, lowY) == (0.2, 0.2 * aspect)

    # Dragging with the rectangle tool draws an effect around the light, in the paint color from the playhead
    window.effectToolActions[showEffects.SHAPE_RECTANGLE].trigger()
    assert view.drawShape == showEffects.SHAPE_RECTANGLE
    qtbot.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=_viewPoint(window, 0.1, lowY - 0.1))
    qtbot.mouseMove(view.viewport(), pos=_viewPoint(window, 0.2, lowY))
    assert view._drawingItem is not None
    qtbot.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=_viewPoint(window, 0.3, lowY + 0.1))
    effect = window.effectsPanel.currentEffect()
    assert effect is not None and effect.name == "Effect 1" and effect.shape == "rectangle"
    assert (effect.place.centerX, effect.place.centerY) == (
        pytest.approx(0.2, abs=0.01),
        pytest.approx(lowY, abs=0.01),
    )
    assert (effect.rgb, effect.startTime, effect.duration, effect.stepTime) == ((255, 0, 0), 0.0, 1.0, 0.05)
    assert view.drawShape is None and window.effectToolActions[None].isChecked()
    assert len(view.effectItems) == 1 and view.effectItems[0].isCurrent

    # The playfield previews the effect's lights at the playhead
    assert _lightColor(window, "l_a") == (255, 0, 0)
    window.previewEffectsAction.setChecked(False)
    assert _lightColor(window, "l_a") == (0, 0, 255)

    # Applying paints the effect into the show, and can be undone
    assert window.applyCurrentEffect()
    assert _colorAt(window, "l_a", 0.5) == (255, 0, 0)
    assert window.hasUnsavedChanges()
    assert "Applied Effect 1 from 0s to 1s" in window.statusBar().currentMessage()

    # Changing the effect and applying it again replaces it
    window.effectsPanel.durationSpin.setValue(0.5)
    assert effect.duration == 0.5
    assert window.applyCurrentEffect()
    assert _colorAt(window, "l_a", 0.75) == (0, 0, 255)
    # The effect's step follows the grid when the grid is finer
    window.resolutionOption.setCurrentIndex(window.resolutionOption.findData(0.025))
    assert window.addEffect("rectangle", 0.1, 0.1, 0.2, 0.2).stepTime == 0.025
    window.effectsPanel.setCurrentIndex(0)
    window.undo()
    assert _colorAt(window, "l_a", 0.75) == (255, 0, 0)

    # A click without a drag draws a shape of a set size
    window.effectToolActions[showEffects.SHAPE_ELLIPSE].trigger()
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=_viewPoint(window, 0.8, 0.8 * aspect))
    circle = window.effectsPanel.currentEffect()
    assert circle.name == "Effect 3" and circle.place.width == pytest.approx(0.15, abs=0.01)


def test_editingEffects(qtbot, tmp_path, monkeypatch):
    window = _effectsWindow(qtbot, tmp_path)
    panel = window.effectsPanel
    first = window.addEffect("line", 0.0, 0.1, 1.0, 0.1)
    second = window.addEffect("ring", 0.5, 0.5, 0.7, 0.7)
    assert [effect.name for effect in panel.effects] == ["Effect 1", "Effect 2"]
    assert panel.currentEffect() is second
    assert panel.heightSpin.isEnabled() and panel.thicknessSpin.isEnabled()

    # Clicking another effect's shape edits it, and dragging the one edited moves it
    window.playfieldView.effectClicked.emit(0)
    assert panel.currentEffect() is first
    assert not panel.heightSpin.isEnabled()
    window.playfieldView.effectMoved.emit(0.1, 0.2)
    assert (first.place.centerX, first.place.centerY) == (0.6, pytest.approx(0.3))
    assert panel.centerYSpin.value() == pytest.approx(30)

    # The settings are written to the effect
    panel.moveDistanceSpin.setValue(50)
    panel.spinSpin.setValue(90)
    panel.repeatsSpin.setValue(3)
    panel.bounceCheckBox.setChecked(True)
    panel.offOutsideCheckBox.setChecked(True)
    panel.easingOption.setCurrentText(showEffects.EASING_SMOOTH)
    panel.nameEdit.setText("Sweep")
    panel.nameEdit.editingFinished.emit()
    assert (first.moveDistance, first.spin, first.repeats, first.bounce, first.offOutside) == (0.5, 90, 3, True, True)
    assert first.easing == showEffects.EASING_SMOOTH and first.name == "Sweep"
    assert panel.effectList.item(0).text() == "Sweep"
    panel._chooseColor(isEnd=True, chooser=lambda *_args: QColor("#00ff00"))
    assert first.endRGB == (0, 255, 0) and panel.endColorCheckBox.isChecked()
    panel._chooseColor(isEnd=False, chooser=lambda *_args: QColor())
    panel.endColorCheckBox.setChecked(False)
    assert first.endRGB is None

    # Effects can be copied and taken off the list
    copied = window.duplicateCurrentEffect()
    assert copied is not None and copied.name == "Sweep copy" and copied.place is not first.place
    assert window.deleteCurrentEffect()
    assert [effect.name for effect in panel.effects] == ["Sweep", "Effect 2"]

    # Each show has its own effects
    window.showList.selectShowItem(window.showList.showItems()[1])
    assert panel.effects == []
    window.showList.selectShowItem(window.showList.showItems()[0])
    assert [effect.name for effect in panel.effects] == ["Sweep", "Effect 2"]


def test_effectsNeedAPlayfieldLayout(qtbot, tmp_path):
    window = ShowViewerWindow(_machine(tmp_path))
    qtbot.addWidget(window)
    window.ribbon.setCurrentIndex(EFFECTS_RIBBON_TAB)
    window.addEffect("rectangle", 0.1, 0.1, 0.5, 0.5)
    assert not window.applyCurrentEffect()
    assert "MPF-Monitor layout" in window.statusBar().currentMessage()
    window.deleteCurrentEffect()
    assert not window.applyCurrentEffect() and window.duplicateCurrentEffect() is None
    assert not window.deleteCurrentEffect()


def test_previewLightsShowsTheEffectAsItWouldBeApplied(qtbot, tmp_path):
    window = _effectsWindow(qtbot, tmp_path)
    window.ribbon.setColor((255, 0, 0))
    aspect = window.playfieldView.aspect()
    # A shape over l_b only, which turns the lights it passes off outside it: l_a is one of them
    effect = window.addEffect("rectangle", 0.7, 0.7 * aspect, 0.9, 0.9 * aspect)
    # It moves from l_b to l_a over its second
    effect.moveAngle = math.degrees(math.atan2(0.6 * aspect, -0.6))
    effect.moveDistance = math.hypot(0.6, 0.6 * aspect)
    window.effectsPanel.refresh()
    window.effectsPanel.offOutsideCheckBox.setChecked(True)
    window.setPlayTime(0.1)
    # The show sets l_a blue, but the effect turns it off until the shape reaches it.  The preview is worked out
    # again once the changes pause
    qtbot.waitUntil(lambda: _lightColor(window, "l_a") == (0, 0, 0), timeout=2000)
    assert _lightColor(window, "l_b") == (255, 0, 0)
    # The preview follows the effect's changes, and is only a preview
    window.effectsPanel._chooseColor(isEnd=False, chooser=lambda *_args: QColor("#00ff00"))
    qtbot.waitUntil(lambda: _lightColor(window, "l_b") == (0, 255, 0), timeout=2000)
    assert _colorAt(window, "l_a", 0.1) == (0, 0, 255)
    window.previewEffectsAction.setChecked(False)
    assert _lightColor(window, "l_a") == (0, 0, 255)


def test_previewEffectPlaysTheEffectOverAndOver(qtbot, tmp_path):
    window = _effectsWindow(qtbot, tmp_path)
    effect = window.addEffect("ellipse", 0.1, 0.1, 0.3, 0.3)
    effect.startTime, effect.duration = 0.5, 0.4
    window.setPlayTime(1.5)
    window.togglePlayback()
    assert window.isPlaying

    # Previewing pauses the show and plays just the effect, leaving the playhead where it was
    window.previewEffectAction.trigger()
    assert window.isPreviewingEffect and not window.isPlaying
    assert window.effectPreviewTime == 0.5
    playTime = window.playTime
    qtbot.waitUntil(lambda: window.effectPreviewTime > 0.6, timeout=3000)
    assert window.playfieldSummary.text().startswith("Previewing Effect 1: ")
    # Once the effect has ended it starts again
    qtbot.waitUntil(lambda: window.effectPreviewTime < 0.6, timeout=3000)
    assert window.playTime == playTime

    # It stops when turned off, when the playhead moves, the show plays, the effect is applied, or the tab is left
    window.previewEffectAction.trigger()
    assert not window.isPreviewingEffect and window.playfieldSummary.text() == "2 lights placed"
    for stop in (
        lambda: window.setPlayTime(0.2),
        window.togglePlayback,
        window.applyCurrentEffect,
        lambda: window.ribbon.setCurrentIndex(0),
    ):
        window.ribbon.setCurrentIndex(EFFECTS_RIBBON_TAB)
        window.pausePlayback()
        assert window.setEffectPreviewing(True)
        stop()
        assert not window.isPreviewingEffect and not window.previewEffectAction.isChecked()

    # And when the show changes, or there is no effect left
    window.ribbon.setCurrentIndex(EFFECTS_RIBBON_TAB)
    window.setEffectPreviewing(True)
    window.showList.selectShowItem(window.showList.showItems()[1])
    assert not window.isPreviewingEffect
    window.showList.selectShowItem(window.showList.showItems()[0])
    window.setEffectPreviewing(True)
    window.deleteCurrentEffect()
    assert not window.isPreviewingEffect and not window.previewEffectAction.isEnabled()


def test_shapesCanBeHidden(qtbot, tmp_path):
    window = _effectsWindow(qtbot, tmp_path)
    window.addEffect("ring", 0.1, 0.1, 0.5, 0.5)
    window.addEffect("line", 0.1, 0.6, 0.9, 0.6)
    assert len(window.playfieldView.effectItems) == 2
    window.showShapesAction.setChecked(False)
    assert window.playfieldView.effectItems == []
    window.setEffectPreviewing(True)
    window._advanceEffectPreview()
    assert window.playfieldView.effectItems == []
    window.showShapesAction.setChecked(True)
    assert len(window.playfieldView.effectItems) == 2


def test_previewNeedsAPlayfieldLayout(qtbot, tmp_path):
    window = ShowViewerWindow(_machine(tmp_path))
    qtbot.addWidget(window)
    window.ribbon.setCurrentIndex(EFFECTS_RIBBON_TAB)
    window.addEffect("rectangle", 0.1, 0.1, 0.5, 0.5)
    assert not window.setEffectPreviewing(True)
    assert not window.previewEffectAction.isChecked()
    assert "MPF-Monitor layout" in window.statusBar().currentMessage()


def test_pinwheelAndSpiralEffects(qtbot, tmp_path):
    window = _effectsWindow(qtbot, tmp_path)
    panel = window.effectsPanel
    assert not window.patternsAction.isEnabled()
    assert not window.applyEffectPreset("Radar sweep")

    # Pinwheels and spirals are drawn like the other shapes, with settings for their blades and arms
    window.effectToolActions[showEffects.SHAPE_PINWHEEL].trigger()
    assert window.playfieldView.drawShape == showEffects.SHAPE_PINWHEEL
    pinwheel = window.addEffect("pinwheel", 0.1, 0.1, 0.9, 0.9)
    assert panel.armsSpin.isEnabled() and panel.bladeFillSpin.isEnabled() and not panel.turnsSpin.isEnabled()
    panel.armsSpin.setValue(6)
    panel.bladeFillSpin.setValue(25)
    assert (pinwheel.arms, pinwheel.bladeFill) == (6, 0.25)
    assert not window.playfieldView.effectItems[0].path().isEmpty()

    spiral = window.addEffect("spiral", 0.1, 0.1, 0.9, 0.9)
    assert panel.turnsSpin.isEnabled() and panel.thicknessSpin.isEnabled() and not panel.bladeFillSpin.isEnabled()
    panel.turnsSpin.setValue(2.5)
    assert spiral.turns == 2.5
    assert not window.playfieldView.effectItems[1].path().isEmpty()

    # A pattern gives the effect its shape and movement, keeping where it is and its timing
    window.patternActions["Radar sweep"].trigger()
    assert (spiral.shape, spiral.arms, spiral.spin) == ("pinwheel", 1, 360.0)
    assert (spiral.place.centerX, spiral.startTime) == (pytest.approx(0.5), 0.0)
    assert panel.shapeOption.currentData() == "pinwheel" and panel.armsSpin.value() == 1
    assert window.statusBar().currentMessage() == "Effect 2 is now a radar sweep"

    # It can be previewed and applied like any other effect
    window.patternActions["Spiral out"].trigger()
    window.setPlayTime(0.5)
    assert window.applyCurrentEffect()


@pytest.mark.parametrize("shape", [shape for shape in showEffects.SHAPES if shape != showEffects.SHAPE_STARFIELD])
@pytest.mark.parametrize("rotation", [0.0, 50.0])
def test_shapesLightWhatTheirOutlinesCover(qtbot, shape, rotation):
    from PySide6.QtGui import QImage, QPainter

    from mpfmanager.ui.playfieldView import effectShapePath

    # What a shape is drawn over on the playfield is what it lights, for every shape
    place = showEffects.ShapePlace(0.5, 0.5, 0.8, 0.6, rotation)
    size = 400
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor("black"))
    painter = QPainter(image)
    painter.translate(size / 2, size / 2)
    painter.rotate(rotation)
    painter.fillPath(effectShapePath(shape, place, 0.08, size, (3, 1.25, 0.4)), QColor("white"))
    painter.end()
    agree = total = 0
    for column in range(4, 96, 2):
        for row in range(4, 96, 2):
            x, y = column / 100, row / 100
            drawn = QColor(image.pixel(int(x * size), int(y * size))).red() > 128
            lit = showEffects.shapeCoverage(shape, place, x, y, 0.08, 0, arms=3, turns=1.25, bladeFill=0.4) == 1.0
            agree += drawn == lit
            total += 1
    # A spiral's arms are measured as if its ellipse were round, which is close for the ellipses lights are in
    assert agree / total > (0.93 if shape == showEffects.SHAPE_SPIRAL else 0.97)


def _drawnAndLit(effect: showEffects.LightEffect, atTime: float, rotation: float) -> float:
    from PySide6.QtGui import QImage, QPainter

    from mpfmanager.ui.playfieldView import effectPath

    size = 400
    image = QImage(size, size, QImage.Format.Format_RGB32)
    image.fill(QColor("black"))
    painter = QPainter(image)
    painter.translate(effect.placeAt(atTime).centerX * size, effect.placeAt(atTime).centerY * size)
    painter.rotate(rotation)
    painter.fillPath(effectPath(effect, atTime, size), QColor("white"))
    painter.end()
    agree = total = 0
    for column in range(2, 98, 2):
        for row in range(2, 98, 2):
            x, y = column / 100, row / 100
            drawn = QColor(image.pixel(int(x * size), int(y * size))).red() > 128
            agree += drawn == (effect.lightAt(atTime, x, y)[0] > 0)
            total += 1
    return agree / total


@pytest.mark.parametrize("starShape", showEffects.STAR_SHAPES)
@pytest.mark.parametrize("motion", showEffects.STAR_MOTIONS)
def test_starfieldsLightWhatTheirStarsAreDrawnOver(qtbot, starShape, motion):
    # What a starfield's stars are drawn over is what they light, for every star shape and motion
    effect = showEffects.LightEffect(
        "stars",
        showEffects.SHAPE_STARFIELD,
        showEffects.ShapePlace(0.5, 0.5, 0.8, 0.7, 30.0),
        starShape=starShape,
        starMotion=motion,
        starSize=0.08,
        starSpeed=0.2,
        starDensity=1.0,
        duration=2.0,
    )
    assert _drawnAndLit(effect, 0.7, 30.0) > 0.98


def test_rainbowAndStarfieldSettings(qtbot, tmp_path):
    window = _effectsWindow(qtbot, tmp_path)
    panel = window.effectsPanel
    effect = window.addEffect("ellipse", 0.1, 0.1, 0.9, 0.9)
    assert not panel.rainbowBandsSpin.isEnabled() and not panel.starShapeOption.isEnabled()

    # Rainbows color the effect, and are drawn on its shape
    panel.colorModeOption.setCurrentIndex(panel.colorModeOption.findData(showEffects.COLOR_RAINBOW_OUTWARD))
    panel.rainbowBandsSpin.setValue(3)
    panel.rainbowCyclesSpin.setValue(-1.5)
    assert (effect.colorMode, effect.rainbowBands, effect.rainbowCycles) == ("rainbow outward", 3, -1.5)
    assert panel.rainbowBandsSpin.isEnabled()
    assert window.playfieldView.effectItems[0].brush().gradient() is not None

    # A starfield has its stars' settings
    window.effectToolActions[showEffects.SHAPE_STARFIELD].trigger()
    assert window.playfieldView.drawShape == showEffects.SHAPE_STARFIELD
    stars = window.addEffect("starfield", 0.1, 0.1, 0.9, 0.9)
    assert panel.starShapeOption.isEnabled() and panel.starAngleSpin.isEnabled()
    panel.starShapeOption.setCurrentIndex(panel.starShapeOption.findData(showEffects.STAR_SPARKLE))
    panel.starSizeSpin.setValue(6)
    panel.starDensitySpin.setValue(2)
    panel.starColoringOption.setCurrentText(showEffects.STARS_RANDOM_COLORS)
    panel.starSeedSpin.setValue(7)
    panel.starSpeedSpin.setValue(40)
    panel.starAngleSpin.setValue(45)
    panel.twinkleSpin.setValue(50)
    panel.twinkleRateSpin.setValue(2)
    panel.starMotionOption.setCurrentText(showEffects.STARS_WARP)
    assert (stars.starShape, stars.starSize, stars.starDensity, stars.starSeed) == ("sparkle", 0.06, 2, 7)
    assert (stars.starColoring, stars.starSpeed, stars.starAngle) == ("random colors", 0.4, 45)
    assert (stars.twinkle, stars.twinkleRate, stars.starMotion) == (0.5, 2, "warp")
    # Warping stars fly out from the middle, so they have no way to drift
    assert not panel.starAngleSpin.isEnabled()
    starItem = window.playfieldView.effectItems[1]
    assert starItem.fieldRect is not None and not starItem.path().isEmpty()
    # Stars with colors of their own are drawn in their colors
    assert len(starItem.coloredStars) == len(stars.starsAt(window.playTime))
    assert {color.name() for _path, color in starItem.coloredStars} == {
        QColor(*showEffects.starColor(star.star)).name() for star in stars.starsAt(window.playTime)
    }
    assert starItem.shape().contains(starItem.fieldRect.center())

    # Patterns are grouped, and make rainbows and starfields too
    sections = [action.text() for action in window.patternMenu.actions() if action.isSeparator()]
    assert sections == ["Pinwheels", "Spirals", "Rainbows", "Starfields"]
    window.patternActions["Warp speed"].trigger()
    assert (stars.shape, stars.starMotion) == ("starfield", "warp")
    window.patternActions["Rainbow wheel"].trigger()
    assert (stars.shape, stars.colorMode) == ("ellipse", "rainbow round")
    assert panel.colorModeOption.currentData() == "rainbow round"

    # They are previewed and applied like any other effect
    window.patternActions["Rainbow stars"].trigger()
    panel.starSizeSpin.setValue(40)
    window.setPlayTime(0.5)
    assert window.applyCurrentEffect()


def test_previewIsWorkedOutOnceChangesPause(qtbot, tmp_path):
    window = _effectsWindow(qtbot, tmp_path)
    window.ribbon.setColor((255, 0, 0))
    aspect = window.playfieldView.aspect()
    effect = window.addEffect("rectangle", 0.1, 0.1 * aspect, 0.3, 0.3 * aspect)
    window.setPlayTime(0.1)
    assert _lightColor(window, "l_a") == (255, 0, 0)
    builds = window.previewBuilds

    # Several quick changes move the shape straight away, and work the lights out once, after they pause
    panel = window.effectsPanel
    for step in range(1, 7):
        panel.centerXSpin.setValue(10 + step * 10)
        assert window.playfieldView.effectItems[0].pos().x() > 0
    assert window.previewBuilds == builds and window.effectPreviewDebounce.isActive()
    assert effect.place.centerX == 0.7
    qtbot.waitUntil(lambda: not window.effectPreviewDebounce.isActive(), timeout=2000)
    assert window.previewBuilds == builds + 1
    assert _lightColor(window, "l_b") is None or _lightColor(window, "l_a") != (255, 0, 0)

    # Another effect, or another show, is worked out straight away, not shown with the last one's lights
    other = window.addEffect("rectangle", 0.7, 0.7 * aspect, 0.9, 0.9 * aspect)
    assert window._previewFor == (window.selectedShow(), other)
    assert window.previewBuilds == builds + 2
