from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent, QWheelEvent

from mpfmanager.core.monitorManager import MonitorLayout, MonitorLight
from mpfmanager.ui import playfieldView
from mpfmanager.ui.playfieldView import PlayfieldView


def writePlayfieldImage(path: Path, width: int = 200, height: int = 400) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(20, 40, 80))
    image.save(str(path))
    return path


def _layout(imagePath: Path | None) -> MonitorLayout:
    return MonitorLayout(
        imagePath,
        {
            "l_round": MonitorLight("l_round", 0.25, 0.5, 0.1),
            "l_star": MonitorLight("l_star", 0.75, 0.25, 0.1, "STAR", 45),
        },
    )


def test_playfieldViewDrawsTheLayout(qtbot, tmp_path):
    view = PlayfieldView()
    qtbot.addWidget(view)
    view.resize(300, 300)
    view.show()

    # Lights are placed at their fractions of the playfield image, sized from its width
    view.setMonitorLayout(_layout(writePlayfieldImage(tmp_path / "playfield.png")))
    assert view.hasImage
    assert view.scene().sceneRect().size().toTuple() == (200, 400)
    roundLight, starLight = view.lightItems["l_round"], view.lightItems["l_star"]
    assert roundLight.pos() == QPointF(50, 200)
    assert starLight.pos() == QPointF(150, 100)
    assert roundLight.boundingRect().width() > 19
    assert starLight.path().elementCount() > 10

    # Lights take the show's colors with MPF-Monitor's gamma correction, and are marked when not set
    view.setLightColors({"l_round": ((255, 0, 100), "gi"), "l_star": ((0, 255, 0), "l_star")})
    assert roundLight.brush().color().getRgb() == (255, 0, 180, 220)
    assert roundLight.toolTip() == "l_round\n#ff0064\nSet by gi"
    assert starLight.toolTip() == "l_star\n#00ff00"
    view.setLightColors({"l_round": ((255, 0, 100), "gi")})
    assert roundLight.toolTip() == "l_round\n#ff0064\nSet by gi"
    assert starLight.brush() == playfieldView.UNSET_LIGHT_BRUSH
    assert starLight.toolTip() == "l_star\nNot set by the show"
    view.grab()

    # Without an image a plain playfield is drawn, and without a layout nothing is
    view.setMonitorLayout(_layout(tmp_path / "missing.png"))
    assert not view.hasImage
    assert view.scene().sceneRect().size().toTuple() == playfieldView.NO_IMAGE_SIZE
    view.setMonitorLayout(None)
    assert view.lightItems == {} and view.scene().sceneRect().isEmpty()
    view.zoomBy(2)
    view.fitPlayfield()


def test_playfieldViewZooms(qtbot, tmp_path):
    view = PlayfieldView()
    qtbot.addWidget(view)
    view.resize(300, 300)
    view.show()
    view.setMonitorLayout(_layout(writePlayfieldImage(tmp_path / "playfield.png")))
    fittedScale = view.transform().m11()

    view.wheelEvent(
        QWheelEvent(
            QPointF(150, 150), QPointF(150, 150), QPoint(0, 0), QPoint(0, 240),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False,
        )
    )  # fmt: skip
    assert view.isZoomed
    assert view.transform().m11() > fittedScale
    view.resize(320, 320)
    qtbot.waitUntil(lambda: view.isZoomed)

    # Zooming out past the whole playfield fits it again, as does double clicking
    view.zoomBy(-10)
    assert not view.isZoomed
    assert abs(view.transform().m11() - fittedScale) < 0.1
    view.zoomBy(3)
    qtbot.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton)
    assert not view.isZoomed


def _selectView(qtbot, tmp_path) -> PlayfieldView:
    view = PlayfieldView()
    qtbot.addWidget(view)
    view.resize(300, 300)
    view.show()
    qtbot.waitExposed(view)
    view.setMonitorLayout(_layout(writePlayfieldImage(tmp_path / "playfield.png")))
    return view


def _lightPoint(view: PlayfieldView, lightName: str) -> QPoint:
    return view.mapFromScene(view.lightItems[lightName].scenePos())


def test_choosingLightsByClicking(qtbot, tmp_path):
    view = _selectView(qtbot, tmp_path)
    chosen = []
    view.lightsSelected.connect(chosen.append)

    # Lights are only chosen in select mode, as otherwise dragging moves the playfield
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=_lightPoint(view, "l_round"))
    assert chosen == [] and view.chosenLights == []
    view.setSelectMode(True)
    assert view.dragMode() == PlayfieldView.DragMode.RubberBandDrag
    assert "choose them" in view.toolTip()
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=_lightPoint(view, "l_round"))
    assert chosen[-1] == ["l_round"]
    assert view.lightItems["l_round"].isChosen and not view.lightItems["l_star"].isChosen

    # Ctrl adds a light to those chosen, or takes it away, and clicking away from the lights chooses none
    ctrl = Qt.KeyboardModifier.ControlModifier
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, ctrl, _lightPoint(view, "l_star"))
    assert chosen[-1] == ["l_round", "l_star"]
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, ctrl, _lightPoint(view, "l_round"))
    assert chosen[-1] == ["l_star"]
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.RightButton, pos=_lightPoint(view, "l_round"))
    assert chosen[-1] == ["l_star"]
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(2, 2))
    assert chosen[-1] == []
    view.grab()

    # Leaving select mode keeps the lights chosen, and drawing the layout again does too
    view.selectLights(["l_star", "l_star"])
    view.setSelectMode(False)
    assert view.dragMode() == PlayfieldView.DragMode.ScrollHandDrag
    view.setMonitorLayout(_layout(None))
    assert view.lightItems["l_star"].isChosen
    assert chosen[-1] == []


def test_choosingLightsInABox(qtbot, tmp_path):
    view = _selectView(qtbot, tmp_path)
    view.setSelectMode(True)
    chosen = []
    view.lightsSelected.connect(chosen.append)
    assert view.lightsIn(QRectF(0, 0, 200, 400)) == ["l_round", "l_star"]
    view.selectLightsIn(QRectF(0, 150, 100, 100))
    assert chosen[-1] == ["l_round"]
    view.selectLightsIn(QRectF(100, 50, 100, 100), playfieldView.CHOOSE_ADD)
    assert chosen[-1] == ["l_round", "l_star"]

    # Dragging a box chooses the lights in it
    view._rubberBandChanged(QRect(0, 0, 10, 10), QPointF(120, 60), QPointF(180, 140))
    view._rubberBandChanged(QRect(), QPointF(), QPointF())
    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(5, 5),
        QPointF(5, 5),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mouseReleaseEvent(release)
    assert chosen[-1] == ["l_star"]


def _releaseBox(view, fromPoint, toPoint, modifiers):
    view._rubberBandChanged(QRect(0, 0, 10, 10), fromPoint, toPoint)
    view._rubberBandChanged(QRect(), QPointF(), QPointF())
    view.mouseReleaseEvent(
        QMouseEvent(
            QEvent.Type.MouseButtonRelease,
            QPointF(5, 5),
            QPointF(5, 5),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.NoButton,
            modifiers,
        )
    )


def test_shiftAddsBoxesAndAltTakesThemAway(qtbot, tmp_path):
    view = _selectView(qtbot, tmp_path)
    view.setSelectMode(True)
    chosen = []
    view.lightsSelected.connect(chosen.append)
    roundBox = (QPointF(0, 150), QPointF(100, 250))
    starBox = (QPointF(120, 60), QPointF(180, 140))

    # A box drawn with Shift adds its lights to the ones chosen, even ones outside the first box
    _releaseBox(view, *roundBox, Qt.KeyboardModifier.NoModifier)
    assert chosen[-1] == ["l_round"]
    _releaseBox(view, *starBox, Qt.KeyboardModifier.ShiftModifier)
    assert chosen[-1] == ["l_round", "l_star"]
    # Ctrl adds a box too, without choosing a light twice
    _releaseBox(view, *starBox, Qt.KeyboardModifier.ControlModifier)
    assert chosen[-1] == ["l_round", "l_star"]
    # A box drawn with Alt takes its lights away
    _releaseBox(view, *roundBox, Qt.KeyboardModifier.AltModifier)
    assert chosen[-1] == ["l_star"]
    # A box without a key chooses only its lights
    _releaseBox(view, *roundBox, Qt.KeyboardModifier.NoModifier)
    assert chosen[-1] == ["l_round"]
    assert "Shift adds" in view.toolTip()


def test_shiftAndAltClicks(qtbot, tmp_path):
    view = _selectView(qtbot, tmp_path)
    view.setSelectMode(True)
    view.show()
    roundPoint = view.mapFromScene(view.lightItems["l_round"].scenePos())
    starPoint = view.mapFromScene(view.lightItems["l_star"].scenePos())
    view.selectLightAt(roundPoint)
    view.selectLightAt(starPoint, playfieldView.CHOOSE_ADD)
    assert view.chosenLights == ["l_round", "l_star"]
    # Clicking away from the lights with Shift keeps them chosen
    view.selectLightAt(QPoint(1, 1), playfieldView.CHOOSE_ADD)
    assert view.chosenLights == ["l_round", "l_star"]
    view.selectLightAt(roundPoint, playfieldView.CHOOSE_REMOVE)
    assert view.chosenLights == ["l_star"]
    # Ctrl clicking adds a light, or takes it away when it is chosen
    view.selectLightAt(roundPoint, playfieldView.CHOOSE_TOGGLE)
    view.selectLightAt(starPoint, playfieldView.CHOOSE_TOGGLE)
    assert view.chosenLights == ["l_round"]
