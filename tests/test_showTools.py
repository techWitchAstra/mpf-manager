from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel

from mpfmanager.ui import showTools
from mpfmanager.ui.showTools import ShowRibbon


def test_toolsAreChosenOneAtATime(qtbot):
    ribbon = ShowRibbon()
    qtbot.addWidget(ribbon)
    assert ribbon.currentTool == showTools.TOOL_SELECT
    chosen = []
    ribbon.toolChanged.connect(chosen.append)
    ribbon.setTool(showTools.TOOL_PAINT)
    ribbon.toolButtons[showTools.TOOL_ERASE].click()
    assert chosen == [showTools.TOOL_PAINT, showTools.TOOL_ERASE]
    assert ribbon.currentTool == showTools.TOOL_ERASE
    assert not ribbon.toolButtons[showTools.TOOL_PAINT].isChecked()


def test_paintColorIntensityAndFade(qtbot, monkeypatch):
    ribbon = ShowRibbon()
    qtbot.addWidget(ribbon)
    assert ribbon.colorButton.text() == "red"

    # The slider and the number move together, and the color button shows the color at that intensity
    ribbon.intensitySlider.setValue(50)
    assert ribbon.intensity == 50
    assert ribbon.colorButton.text() == "red%50"
    assert "#7f0000" in ribbon.colorButton.styleSheet()
    ribbon.intensitySpin.setValue(20)
    assert ribbon.intensitySlider.value() == 20

    # Swatches and the color dialog choose the color, and a cancelled dialog keeps it
    ribbon.swatchButtons["blue"].click()
    assert ribbon.paintRGB == (0, 0, 255)
    monkeypatch.setattr(showTools.QColorDialog, "getColor", lambda *args: QColor("#123456"))
    ribbon.colorButton.click()
    assert ribbon.paintRGB == (0x12, 0x34, 0x56)
    monkeypatch.setattr(showTools.QColorDialog, "getColor", lambda *args: QColor())
    ribbon.chooseColor()
    assert ribbon.paintRGB == (0x12, 0x34, 0x56)

    # The setting is written with the project's color names, with the fade
    ribbon.setColor((255, 102, 17), 100)
    ribbon.fadeSpin.setValue(250)
    setting = ribbon.paintSetting({"grunt": (255, 102, 17)})
    assert (setting.value, setting.fadeMs, setting.rgb) == ("grunt", 250, (255, 102, 17))
    assert ribbon.paintSetting().value == "ff6611"


def test_editButtons(qtbot):
    ribbon = ShowRibbon()
    qtbot.addWidget(ribbon)
    ribbon.setEditState(True, False, False, True)
    assert [
        button.isEnabled() for button in (ribbon.undoButton, ribbon.redoButton, ribbon.saveButton, ribbon.saveAsButton)
    ] == [True, False, False, True]


def test_chaseDialog(qtbot):
    dialog = showTools.ChaseDialog(4, 250, "red%50", True)
    qtbot.addWidget(dialog)
    assert (dialog.order, dialog.pattern, dialog.stepTime, dialog.litCount) == ("grid order", "forward", 0.25, 1)
    assert dialog.widthSpin.maximum() == 4

    # Between lit, the lights are off, fading for the time chosen, or left as they were
    dialog.fadeOutSpin.setValue(100)
    between = dialog.betweenSetting()
    assert (between.value, between.fadeMs) == ("off", 100)
    dialog.betweenOption.setCurrentText(showTools.ChaseDialog.BETWEEN_UNCHANGED)
    assert dialog.betweenSetting() is None
    assert not dialog.fadeOutSpin.isEnabled()

    dialog.orderOption.setCurrentText("clockwise")
    dialog.patternOption.setCurrentText("bounce")
    dialog.stepSpin.setValue(40)
    dialog.widthSpin.setValue(3)
    assert (dialog.order, dialog.pattern, dialog.stepTime, dialog.litCount) == ("clockwise", "bounce", 0.04, 3)


def test_chaseDialogWithoutAPlayfield(qtbot):
    dialog = showTools.ChaseDialog(2, 0, "red", False)
    qtbot.addWidget(dialog)
    orderModel = dialog.orderOption.model()
    assert orderModel.item(0).isEnabled()
    assert not any(orderModel.item(row).isEnabled() for row in range(1, dialog.orderOption.count()))
    assert dialog.stepSpin.value() == 1


def test_reusableShowDialog(qtbot):
    dialog = showTools.ReusableShowDialog("attract_part", 3)
    qtbot.addWidget(dialog)
    okButton = dialog.buttons.button(showTools.QDialogButtonBox.StandardButton.Ok)
    assert (dialog.showName, dialog.tokenizeColors, okButton.isEnabled()) == ("attract_part", True, True)
    for name, isValid in (("", False), ("has space", False), ("../up", False), ("ok_name-2.v", True)):
        dialog.nameEdit.setText(name)
        assert okButton.isEnabled() == isValid
    dialog.tokenizeColorsCheckBox.setChecked(False)
    assert not dialog.tokenizeColors


def test_ribbonTabsHoldTheToolsForEachTypeOfItem(qtbot):
    ribbon = ShowRibbon()
    qtbot.addWidget(ribbon)
    assert [ribbon.tabText(index) for index in range(ribbon.count())] == ["Home", "Cells"]
    assert list(ribbon.ribbonTab("Home").groups) == ["Show file", "Clipboard", "History"]
    assert list(ribbon.ribbonTab("Cells").groups) == [
        "Tools",
        "Color",
        "Brightness and fade",
        "Patterns",
        "Reuse",
        "Rows",
    ]

    # Each button is its action, so disabling the action disables the button, and clicking it runs the action
    ribbon.setEditState(False, False, False, False)
    assert not ribbon.undoButton.isEnabled() and not ribbon.saveAsButton.isEnabled()
    triggered = []
    ribbon.copyAction.triggered.connect(lambda: triggered.append("copy"))
    ribbon.copyButton.click()
    assert triggered == ["copy"]
    assert all(not action.icon().isNull() for action in ribbon.toolActions.values())


def test_ribbonGroupsStackSmallControls():
    from mpfmanager.ui.ribbon import SMALL_ROWS, RibbonGroup

    group = RibbonGroup("Group")
    for _ in range(SMALL_ROWS + 1):
        group.addSmallWidget(QLabel("control"))
    # A fourth small control starts a second column
    assert group.contentLayout.count() == 2
