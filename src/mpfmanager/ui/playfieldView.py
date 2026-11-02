"""Playfield view: draws the playfield image with each light in the color a show gives it"""

#   playfieldView - Responsible for drawing MPF-Monitor's playfield layout, the playfield image
#       with its lights placed on it, colored as a show sets them at the current playback time
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QConicalGradient,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPixmap,
    QPolygonF,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QStyleOptionGraphicsItem,
    QWidget,
)

from mpfmanager.core import showEffects
from mpfmanager.core.monitorManager import MonitorLayout, MonitorLight, gammaCorrected
from mpfmanager.core.showEffects import ShapePlace

# The following is the size of the playfield drawn when the layout has no image, as MPF-Monitor's positions are
# fractions of the image's width and height
NO_IMAGE_SIZE = (600, 1200)
NO_IMAGE_BACKGROUND = QColor(24, 26, 32)

# The following is how lights the show is not setting are drawn, so their places can still be seen
UNSET_LIGHT_BRUSH = QBrush(QColor(0, 0, 0, 120))
UNSET_LIGHT_PEN = QPen(QColor(255, 255, 255, 170), 1.2)
LIGHT_PEN = QPen(QColor(255, 255, 255), 1.2)
# The following is the outline of lights chosen on the playfield
SELECTED_LIGHT_PEN = QPen(QColor(255, 200, 0), 3)
# The outlines keep the same width on screen however far the playfield is scaled down
UNSET_LIGHT_PEN.setCosmetic(True)
LIGHT_PEN.setCosmetic(True)
SELECTED_LIGHT_PEN.setCosmetic(True)

# The following are how lights clicked or boxed are chosen: in place of the lights chosen, added to them, taken away
# from them, or a light clicked added or taken away as it is chosen or not
CHOOSE_REPLACE = "replace"
CHOOSE_ADD = "add"
CHOOSE_REMOVE = "remove"
CHOOSE_TOGGLE = "toggle"

# The following are how effect shapes are drawn over the playfield: the effect being edited brightly, the others faintly
EFFECT_SHAPE_Z = 10
CURRENT_EFFECT_PEN = QPen(QColor(255, 255, 255), 2, Qt.PenStyle.DashLine)
OTHER_EFFECT_PEN = QPen(QColor(255, 255, 255, 110), 1, Qt.PenStyle.DotLine)
DRAWING_PEN = QPen(QColor(255, 200, 0), 2, Qt.PenStyle.DashLine)
CURRENT_EFFECT_PEN.setCosmetic(True)
OTHER_EFFECT_PEN.setCosmetic(True)
DRAWING_PEN.setCosmetic(True)
# A click without a drag draws a shape this wide, as a fraction of the playfield's width
CLICKED_SHAPE_SIZE = 0.15
MINIMUM_DRAG = 0.01


# The following are how many arms a pinwheel or spiral is drawn with, how many times a spiral winds, and how much of
# the pinwheel each blade fills, when an effect does not say
DEFAULT_ARMS = (4, 1.0, 0.5)
SPIRAL_POINTS = 72
# A rainbow drawn over a shape changes color this many times along it
RAINBOW_STOPS = 24


# The following makes the outline of an effect's shape around its center, in the scene's pixels
def effectShapePath(
    shape: str,
    place: ShapePlace,
    thickness: float,
    sceneWidth: float,
    arms: tuple[int, float, float] = DEFAULT_ARMS,
) -> QPainterPath:
    width, height = place.width * sceneWidth, place.height * sceneWidth
    path = QPainterPath()
    armCount, turns, bladeFill = max(int(arms[0]), 1), arms[1], min(max(arms[2], 0.0), 1.0)
    sector = 360 / armCount
    if shape == showEffects.SHAPE_PINWHEEL:
        # Each blade is a slice of the ellipse.  Qt measures angles the other way round to the effect's, as y is down
        bounds = QRectF(-width / 2, -height / 2, width, height)
        for arm in range(armCount):
            path.moveTo(0, 0)
            path.arcTo(bounds, -arm * sector, -sector * bladeFill)
            path.closeSubpath()
        return path
    if shape == showEffects.SHAPE_SPIRAL:
        # Each arm is drawn along its middle, as thick as the spiral's thickness
        for arm in range(armCount):
            for point in range(SPIRAL_POINTS + 1):
                radius = point / SPIRAL_POINTS
                angle = radius * turns * 2 * math.pi + math.radians(arm * sector)
                armPoint = QPointF(math.cos(angle) * width / 2 * radius, math.sin(angle) * height / 2 * radius)
                if point == 0:
                    path.moveTo(armPoint)
                else:
                    path.lineTo(armPoint)
        stroker = QPainterPathStroker()
        stroker.setWidth(max(thickness * sceneWidth, 1.0))
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        return stroker.createStroke(path).simplified()
    if shape == showEffects.SHAPE_LINE:
        lineThickness = thickness * sceneWidth
        path.addRect(QRectF(-width / 2, -lineThickness / 2, width, lineThickness))
    elif shape == showEffects.SHAPE_RECTANGLE:
        path.addRect(QRectF(-width / 2, -height / 2, width, height))
    elif shape == showEffects.SHAPE_RING:
        # A ring is a band along the ellipse's edge, as thick as its thickness, half inside the edge and half outside
        half = thickness * sceneWidth / 2
        path.addEllipse(QRectF(-width / 2 - half, -height / 2 - half, width + 2 * half, height + 2 * half))
        path.addEllipse(QRectF(-width / 2 + half, -height / 2 + half, width - 2 * half, height - 2 * half))
    else:
        path.addEllipse(QRectF(-width / 2, -height / 2, width, height))
    return path


# The following draws one star of a starfield, around its middle, in the scene's pixels
def addStarPath(path: QPainterPath, starShape: str, x: float, y: float, size: float) -> None:
    half = size / 2
    if starShape == showEffects.STAR_DIAMOND:
        path.addPolygon(
            QPolygonF([QPointF(x, y - half), QPointF(x + half, y), QPointF(x, y + half), QPointF(x - half, y)])
        )
        path.closeSubpath()
    elif starShape == showEffects.STAR_CROSS:
        bar = size / 5
        path.addRect(QRectF(x - half, y - bar / 2, size, bar))
        path.addRect(QRectF(x - bar / 2, y - half, bar, size))
    elif starShape == showEffects.STAR_SPARKLE:
        # A four pointed star whose sides curve in between its points, as the effect lights it
        points = []
        for step in range(48):
            angle = 2 * math.pi * step / 48
            cosine, sine = math.cos(angle), math.sin(angle)
            scale = half / (math.sqrt(abs(cosine)) + math.sqrt(abs(sine))) ** 2
            points.append(QPointF(x + cosine * scale, y + sine * scale))
        path.addPolygon(QPolygonF(points))
        path.closeSubpath()
    else:
        path.addEllipse(QRectF(x - half, y - half, size, size))


# The following makes the outline of an effect at a time, around its center, in the scene's pixels: its shape, or a
# starfield's stars where they are then
def effectPath(effect: showEffects.LightEffect, atTime: float, sceneWidth: float) -> QPainterPath:
    place = effect.placeAt(atTime)
    if effect.shape != showEffects.SHAPE_STARFIELD:
        return effectShapePath(
            effect.shape, place, effect.thickness, sceneWidth, (effect.arms, effect.turns, effect.bladeFill)
        )
    path = QPainterPath()
    path.setFillRule(Qt.FillRule.WindingFill)
    for starPlace in effect.starsAt(atTime, place):
        addStarPath(
            path, effect.starShape, starPlace.x * sceneWidth, starPlace.y * sceneWidth, starPlace.size * sceneWidth
        )
    return path


# The following returns the fill an effect is drawn with: its color, or its rainbow laid over it the way it lights the
# lights, so the colors seen on the shape are the colors it lights
def effectBrush(effect: showEffects.LightEffect, atTime: float, sceneWidth: float, alpha: int) -> QBrush:
    place = effect.placeAt(atTime)
    mode = effect.colorMode
    if mode not in showEffects.COLOR_MODES[1:]:
        rgb = (
            (255, 255, 255)
            if effect.starColoring == showEffects.STARS_RANDOM_COLORS and effect.shape == showEffects.SHAPE_STARFIELD
            else effect.colorAt(atTime)
        )
        return QBrush(QColor(*rgb, alpha))
    halfWidth, halfHeight = abs(place.width) * sceneWidth / 2, abs(place.height) * sceneWidth / 2
    if mode == showEffects.COLOR_RAINBOW_ROUND:
        gradient: QConicalGradient | QRadialGradient | QLinearGradient = QConicalGradient(0, 0, 0)
    elif mode == showEffects.COLOR_RAINBOW_OUTWARD:
        gradient = QRadialGradient(0, 0, max(halfWidth, halfHeight, 1.0))
    else:
        gradient = QLinearGradient(-halfWidth, 0, halfWidth, 0)
    for step in range(RAINBOW_STOPS + 1):
        position = step / RAINBOW_STOPS
        # Qt goes round a conical gradient the other way to the effect, as y is down
        rainbowPlace = 1 - position if mode == showEffects.COLOR_RAINBOW_ROUND else position
        gradient.setColorAt(position, QColor(*effect.rainbowColor(rainbowPlace, atTime), alpha))
    return QBrush(gradient)


# The following is an effect's shape drawn over the playfield, where it is at the playhead.  A starfield's stars are
# drawn within the outline of its field
class EffectShapeItem(QGraphicsPathItem):
    def __init__(self, effectIndex: int, isCurrent: bool):
        super().__init__()
        self.effectIndex = effectIndex
        self.isCurrent = isCurrent
        self.fieldRect: QRectF | None = None
        # Stars that each have a color of their own are drawn one by one in their colors
        self.coloredStars: list[tuple[QPainterPath, QColor]] = []
        self.setZValue(EFFECT_SHAPE_Z + (1 if isCurrent else 0))
        self.setPen(CURRENT_EFFECT_PEN if isCurrent else OTHER_EFFECT_PEN)

    def shape(self) -> QPainterPath:  # noqa: N802 - Qt override
        if self.fieldRect is None:
            return super().shape()
        fieldShape = QPainterPath()
        fieldShape.addRect(self.fieldRect)
        return fieldShape

    def boundingRect(self) -> QRectF:  # noqa: N802 - Qt override
        bounds = super().boundingRect()
        return bounds.united(self.fieldRect.adjusted(-2, -2, 2, 2)) if self.fieldRect is not None else bounds

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self.coloredStars:
            painter.setPen(self.pen())
            for starPath, starColor in self.coloredStars:
                painter.setBrush(starColor)
                painter.drawPath(starPath)
        else:
            super().paint(painter, option, widget)
        if self.fieldRect is not None:
            painter.setPen(self.pen())
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.fieldRect)


# The following is one light on the playfield, in MPF-Monitor's shape for it
class PlayfieldLightItem(QGraphicsPathItem):
    def __init__(self, light: MonitorLight, sceneWidth: float):
        super().__init__()
        self.light = light
        size = light.size * sceneWidth
        path = QPainterPath()
        points = light.shapePoints()
        if points is None:
            path.addEllipse(QRectF(-size / 2, -size / 2, size, size))
        else:
            path.addPolygon(QPolygonF([QPointF(x * size, y * size) for x, y in points]))
            path.closeSubpath()
        self.setPath(path)
        self.setPen(UNSET_LIGHT_PEN)
        self.setBrush(UNSET_LIGHT_BRUSH)
        self.rgb: tuple[int, int, int] | None = None
        self.isChosen = False
        self.setToolTip(light.name)

    def setChosen(self, isChosen: bool) -> None:
        if isChosen != self.isChosen:
            self.isChosen = isChosen
            self.update()

    # The following colors the light, with MPF-Monitor's gamma correction and opacity, or marks it as not set
    def setColor(self, rgb: tuple[int, int, int] | None, channelName: str = "") -> None:
        if rgb == self.rgb:
            return
        self.rgb = rgb
        if rgb is None:
            self.setPen(UNSET_LIGHT_PEN)
            self.setBrush(UNSET_LIGHT_BRUSH)
            self.setToolTip(f"{self.light.name}\nNot set by the show")
            return
        self.setPen(LIGHT_PEN)
        self.setBrush(QBrush(QColor(*gammaCorrected(rgb), self.light.alpha)))
        setBy = f"\nSet by {channelName}" if channelName and channelName != self.light.name else ""
        self.setToolTip(f"{self.light.name}\n#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}{setBy}")

    # The following draws the light, with a bright outline when it is chosen
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        super().paint(painter, option, widget)
        if self.isChosen:
            painter.setPen(SELECTED_LIGHT_PEN)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self.path())


# The following view draws the playfield and its lights, scaled to fit.  In select mode, lights are chosen by clicking
# them or dragging a box around them, rather than the playfield being moved
class PlayfieldView(QGraphicsView):
    lightsSelected = Signal(list)
    # The following tell the window about effect shapes: one drawn (its shape, and the corners or ends it was dragged
    # between), one clicked to edit it, and the one being edited dragged to a new place, in fractions of the width
    shapeDrawn = Signal(str, float, float, float, float)
    effectClicked = Signal(int)
    effectMoved = Signal(float, float)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        # The lights chosen are kept here rather than as Qt's selection, so they stay chosen while the playfield is
        # moved, and when the layout is drawn again
        self.chosenLights: list[str] = []
        self.isSelectMode = False
        self._rubberBandRect: QRectF | None = None
        self.rubberBandChanged.connect(self._rubberBandChanged)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setBackgroundBrush(QColor(40, 42, 48))
        self.lightItems: dict[str, PlayfieldLightItem] = {}
        self.hasImage = False
        # The playfield fits the view until it is zoomed with the mouse wheel; double clicking fits it again
        self.isZoomed = False
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setToolTip("Scroll to zoom, drag to move, double click to fit the playfield")
        # In effects mode, effect shapes are drawn over the playfield, and new ones drawn by dragging with a shape tool
        self.isEffectsMode = False
        self.drawShape: str | None = None
        self.effectItems: list[EffectShapeItem] = []
        self._drawStart: QPointF | None = None
        self._drawingItem: QGraphicsPathItem | None = None
        self._movingItem: EffectShapeItem | None = None
        self._moveStart: QPointF | None = None
        self._movedBy = QPointF()

    # The following draws a layout: its playfield image, or a plain playfield without one, and its lights
    def setMonitorLayout(self, layout: MonitorLayout | None) -> None:
        scene = self.scene()
        scene.clear()
        self.lightItems = {}
        self.effectItems = []
        self._drawingItem = None
        if layout is None:
            self.hasImage = False
            scene.setSceneRect(QRectF())
            return
        pixmap = QPixmap(str(layout.imagePath)) if layout.imagePath else QPixmap()
        self.hasImage = not pixmap.isNull()
        if self.hasImage:
            scene.addPixmap(pixmap)
            width, height = pixmap.width(), pixmap.height()
        else:
            width, height = NO_IMAGE_SIZE
            scene.addRect(QRectF(0, 0, width, height), QPen(Qt.PenStyle.NoPen), QBrush(NO_IMAGE_BACKGROUND))
        scene.setSceneRect(QRectF(0, 0, width, height))
        for light in layout.lights.values():
            lightItem = PlayfieldLightItem(light, width)
            lightItem.setChosen(light.name in self.chosenLights)
            lightItem.setPos(light.x * width, light.y * height)
            scene.addItem(lightItem)
            self.lightItems[light.name] = lightItem
        self.fitPlayfield()

    # The following colors each light, from the light colors a show gives at a time
    def setLightColors(self, lightColors: dict[str, tuple[tuple[int, int, int] | None, str]]) -> None:
        for lightName, lightItem in self.lightItems.items():
            lightItem.setColor(*lightColors.get(lightName, (None, "")))

    # The following switches between choosing lights and moving the playfield, keeping the lights chosen
    def setSelectMode(self, isSelectMode: bool) -> None:
        self.isSelectMode = isSelectMode
        self.setDragMode(
            QGraphicsView.DragMode.RubberBandDrag if isSelectMode else QGraphicsView.DragMode.ScrollHandDrag
        )
        self.setToolTip(
            "Click lights, or drag a box around them, to choose them. Shift adds to the lights chosen, Alt takes "
            "lights away from them, and Ctrl adds or takes away a light clicked"
            if isSelectMode
            else "Scroll to zoom, drag to move, double click to fit the playfield"
        )

    # The following chooses lights, and says which are chosen when asked to, as choosing them on the playfield does
    def selectLights(self, lightNames: list[str], notify: bool = False) -> None:
        self.chosenLights = list(dict.fromkeys(lightNames))
        for name, lightItem in self.lightItems.items():
            lightItem.setChosen(name in self.chosenLights)
        if notify:
            self.lightsSelected.emit(list(self.chosenLights))

    # The following returns the lights within a part of the playfield, in the order they are in the layout
    def lightsIn(self, sceneRect: QRectF) -> list[str]:
        return [
            name for name, lightItem in self.lightItems.items() if lightItem.sceneBoundingRect().intersects(sceneRect)
        ]

    # The following chooses the lights within a part of the playfield: in place of the lights chosen, or added to them
    # (as a box drawn with Ctrl does too), or taken away from them
    def selectLightsIn(self, sceneRect: QRectF, mode: str | bool = CHOOSE_REPLACE) -> None:
        self._chooseLights(self.lightsIn(sceneRect), CHOOSE_ADD if mode is True or mode == CHOOSE_TOGGLE else mode)

    # The following chooses the light clicked: in place of the lights chosen, added to them, taken away from them, or
    # with Ctrl added to or taken from them.  Clicking away from the lights chooses none, unless adding or taking away
    def selectLightAt(self, viewPoint: QPoint, mode: str | bool = CHOOSE_REPLACE) -> None:
        clickedItem = next(
            (item for item in self.items(viewPoint) if isinstance(item, PlayfieldLightItem)),
            None,
        )
        clicked = [clickedItem.light.name] if clickedItem is not None else []
        if mode is True or mode == CHOOSE_TOGGLE:
            mode = CHOOSE_REMOVE if clicked and clicked[0] in self.chosenLights else CHOOSE_ADD
        self._chooseLights(clicked, mode)

    def _chooseLights(self, lightNames: list[str], mode: str | bool) -> None:
        if mode == CHOOSE_ADD:
            self.selectLights([*self.chosenLights, *lightNames], notify=True)
        elif mode == CHOOSE_REMOVE:
            self.selectLights([name for name in self.chosenLights if name not in lightNames], notify=True)
        else:
            self.selectLights(lightNames, notify=True)

    def _rubberBandChanged(self, viewportRect: QRect, fromScenePoint: QPointF, toScenePoint: QPointF) -> None:
        # The box is kept while it is dragged, as it is cleared before the mouse is let go
        if not viewportRect.isNull():
            self._rubberBandRect = QRectF(fromScenePoint, toScenePoint).normalized()

    # The following returns how many of the playfield's width its height is, as effect shapes are measured in widths
    def aspect(self) -> float:
        sceneRect = self.scene().sceneRect()
        width, height = (sceneRect.width(), sceneRect.height()) if not sceneRect.isEmpty() else NO_IMAGE_SIZE
        return height / width

    def _sceneWidth(self) -> float:
        sceneRect = self.scene().sceneRect()
        return sceneRect.width() if not sceneRect.isEmpty() else NO_IMAGE_SIZE[0]

    # The following turns on effects mode, where effect shapes are drawn and edited on the playfield
    def setEffectsMode(self, isEffectsMode: bool) -> None:
        self.isEffectsMode = isEffectsMode
        if not isEffectsMode:
            self.setEffectShapes([])
        self.setDrawShape(self.drawShape if isEffectsMode else None)

    # The following chooses the shape new effects are drawn as, or None to click and move the effect shapes
    def setDrawShape(self, shape: str | None) -> None:
        self.drawShape = shape
        if self.isEffectsMode and shape is not None:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.CrossCursor)
            self.setToolTip(f"Drag to draw a {shape} effect")
        else:
            self.setSelectMode(self.isSelectMode)
            self.viewport().unsetCursor()
            if self.isEffectsMode:
                self.setToolTip("Click an effect's shape to edit it, and drag the shape being edited to move it")

    # The following draws the effects' shapes, each where it is at the playhead, with the one being edited brightest
    def setEffectShapes(
        self, effects: list[showEffects.LightEffect], atTime: float = 0.0, currentIndex: int | None = None
    ) -> None:
        scene = self.scene()
        for item in self.effectItems:
            scene.removeItem(item)
        self.effectItems = []
        sceneWidth = self._sceneWidth()
        for index, effect in enumerate(effects):
            place = effect.placeAt(atTime)
            isCurrent = index == currentIndex
            item = EffectShapeItem(index, isCurrent)
            item.setPath(effectPath(effect, atTime, sceneWidth))
            if effect.shape == showEffects.SHAPE_STARFIELD:
                width, height = abs(place.width) * sceneWidth, abs(place.height) * sceneWidth
                item.fieldRect = QRectF(-width / 2, -height / 2, width, height)
                alpha = 230 if isCurrent else 120
                if effect.starColoring == showEffects.STARS_RANDOM_COLORS:
                    for starPlace in effect.starsAt(atTime, place):
                        starPath = QPainterPath()
                        addStarPath(
                            starPath,
                            effect.starShape,
                            starPlace.x * sceneWidth,
                            starPlace.y * sceneWidth,
                            starPlace.size * sceneWidth,
                        )
                        starColor = QColor(*showEffects.starColor(starPlace.star), alpha)
                        item.coloredStars.append((starPath, starColor))
            else:
                alpha = 70 if isCurrent else 30
            item.setBrush(effectBrush(effect, atTime, sceneWidth, alpha))
            item.setPos(place.centerX * sceneWidth, place.centerY * sceneWidth)
            item.setRotation(place.rotation)
            scene.addItem(item)
            self.effectItems.append(item)

    def _effectItemAt(self, viewPoint: QPoint) -> EffectShapeItem | None:
        items = [item for item in self.items(viewPoint) if isinstance(item, EffectShapeItem)]
        return next((item for item in items if item.isCurrent), items[0] if items else None)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt override
        if self.isEffectsMode and event.button() == Qt.MouseButton.LeftButton:
            scenePoint = self.mapToScene(event.position().toPoint())
            if self.drawShape is not None:
                self._drawStart = scenePoint
                self._drawingItem = QGraphicsPathItem()
                self._drawingItem.setPen(DRAWING_PEN)
                self._drawingItem.setZValue(EFFECT_SHAPE_Z + 2)
                self.scene().addItem(self._drawingItem)
                return
            clickedItem = self._effectItemAt(event.position().toPoint())
            if clickedItem is not None:
                if not clickedItem.isCurrent:
                    self.effectClicked.emit(clickedItem.effectIndex)
                    return
                self._movingItem, self._moveStart = clickedItem, scenePoint
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt override
        scenePoint = self.mapToScene(event.position().toPoint())
        if self._drawStart is not None and self._drawingItem is not None and self.drawShape is not None:
            sceneWidth = self._sceneWidth()
            startX, startY = self._drawStart.x() / sceneWidth, self._drawStart.y() / sceneWidth
            effect = showEffects.effectFromDrag("", self.drawShape, startX, startY, *self._toWidths(scenePoint))
            self._drawingItem.setPath(effectShapePath(effect.shape, effect.place, effect.thickness, sceneWidth))
            self._drawingItem.setPos(effect.place.centerX * sceneWidth, effect.place.centerY * sceneWidth)
            self._drawingItem.setRotation(effect.place.rotation)
            return
        if self._movingItem is not None and self._moveStart is not None:
            offset = scenePoint - self._moveStart
            self._movingItem.moveBy(offset.x(), offset.y())
            self._moveStart = scenePoint
            self._movedBy = self._movedBy + offset
            return
        super().mouseMoveEvent(event)

    def _toWidths(self, scenePoint: QPointF) -> tuple[float, float]:
        sceneWidth = self._sceneWidth()
        return scenePoint.x() / sceneWidth, scenePoint.y() / sceneWidth

    # The following finishes drawing a shape, or moving one.  A click without a drag draws a shape of a set size
    def _finishEffectDrag(self, scenePoint: QPointF) -> bool:
        if self._drawStart is not None and self.drawShape is not None:
            if self._drawingItem is not None:
                self.scene().removeItem(self._drawingItem)
                self._drawingItem = None
            startX, startY = self._toWidths(self._drawStart)
            endX, endY = self._toWidths(scenePoint)
            self._drawStart = None
            if abs(endX - startX) < MINIMUM_DRAG and abs(endY - startY) < MINIMUM_DRAG:
                half = CLICKED_SHAPE_SIZE / 2
                startX, startY, endX, endY = startX - half, startY - half, startX + half, startY + half
            self.shapeDrawn.emit(self.drawShape, startX, startY, endX, endY)
            return True
        if self._movingItem is not None:
            movedBy = self._movedBy
            self._movingItem, self._moveStart, self._movedBy = None, None, QPointF()
            sceneWidth = self._sceneWidth()
            if not movedBy.isNull():
                self.effectMoved.emit(movedBy.x() / sceneWidth, movedBy.y() / sceneWidth)
            return True
        return False

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt override
        if event.button() == Qt.MouseButton.LeftButton and self._finishEffectDrag(
            self.mapToScene(event.position().toPoint())
        ):
            return
        super().mouseReleaseEvent(event)
        if not self.isSelectMode or event.button() != Qt.MouseButton.LeftButton:
            return
        # Shift adds the lights to the ones chosen, Alt takes them away, and Ctrl adds a box of them, or adds or takes
        # away a light clicked
        modifiers = event.modifiers()
        if modifiers & Qt.KeyboardModifier.AltModifier:
            mode = CHOOSE_REMOVE
        elif modifiers & Qt.KeyboardModifier.ShiftModifier:
            mode = CHOOSE_ADD
        elif modifiers & Qt.KeyboardModifier.ControlModifier:
            mode = CHOOSE_TOGGLE
        else:
            mode = CHOOSE_REPLACE
        if self._rubberBandRect is not None:
            self.selectLightsIn(self._rubberBandRect, mode)
        else:
            self.selectLightAt(event.position().toPoint(), mode)
        self._rubberBandRect = None

    def fitPlayfield(self) -> None:
        self.isZoomed = False
        if not self.scene().sceneRect().isEmpty():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    # The following zooms in or out by a number of mouse wheel steps, never smaller than the whole playfield
    def zoomBy(self, steps: float) -> None:
        if self.scene().sceneRect().isEmpty():
            return
        self.scale(1.25**steps, 1.25**steps)
        visibleRect = self.mapToScene(self.viewport().rect()).boundingRect()
        sceneRect = self.scene().sceneRect()
        if visibleRect.width() >= sceneRect.width() and visibleRect.height() >= sceneRect.height():
            self.fitPlayfield()
        else:
            self.isZoomed = True

    def wheelEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.zoomBy(event.angleDelta().y() / 120)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 - Qt override
        if not self.isSelectMode:
            self.fitPlayfield()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        if not self.isZoomed:
            self.fitPlayfield()
