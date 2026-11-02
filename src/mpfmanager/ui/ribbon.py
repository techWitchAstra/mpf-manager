"""Ribbon: a tabbed tool bar, with the tools for each type of item on a tab of their own"""

#   ribbon - Responsible for a ribbon style tool bar: tabs, each with groups
#       of large and small buttons and other controls, captioned underneath
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QAction, QFont, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

LARGE_ICON_SIZE = 32
SMALL_ICON_SIZE = 16
SMALL_ROWS = 3


# The following returns an icon from the desktop's icon theme, or one drawn from a symbol where the theme has none
def ribbonIcon(themeIcon: QIcon.ThemeIcon | None, symbol: str) -> QIcon:
    if themeIcon is not None and QIcon.hasThemeIcon(themeIcon):
        return QIcon.fromTheme(themeIcon)
    return symbolIcon(symbol)


# The following draws a symbol, such as ✎, as an icon in the color of the window's text
def symbolIcon(symbol: str) -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    font = QFont(QApplication.font())
    font.setPixelSize(46)
    painter.setFont(font)
    painter.setPen(QApplication.palette().color(QPalette.ColorRole.WindowText))
    painter.drawText(QRect(0, 0, 64, 64), Qt.AlignmentFlag.AlignCenter, symbol)
    painter.end()
    return QIcon(pixmap)


# The following makes a tool button for an action, sized for the ribbon
def actionButton(action: QAction, large: bool = False) -> QToolButton:
    button = QToolButton()
    button.setDefaultAction(action)
    button.setAutoRaise(True)
    if large:
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        button.setIconSize(QSize(LARGE_ICON_SIZE, LARGE_ICON_SIZE))
        button.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        button.setMinimumWidth(52)
    else:
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setIconSize(QSize(SMALL_ICON_SIZE, SMALL_ICON_SIZE))
        button.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    return button


# The following is a group of controls on a ribbon tab, captioned underneath.  Large buttons take the group's full
# height, and small buttons and other controls are stacked in columns of up to three rows
class RibbonGroup(QWidget):
    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.title = title
        # A group keeps to its own width, so controls that stretch, such as sliders, do not widen it
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 0)
        layout.setSpacing(0)
        self.contentLayout = QHBoxLayout()
        self.contentLayout.setSpacing(2)
        layout.addLayout(self.contentLayout, 1)
        self.caption = QLabel(title)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setEnabled(False)
        self.caption.setObjectName("ribbonCaption")
        layout.addWidget(self.caption)
        self._column: QVBoxLayout | None = None

    def addLargeAction(self, action: QAction) -> QToolButton:
        button = actionButton(action, large=True)
        self.addLargeWidget(button)
        return button

    def addLargeWidget(self, widget: QWidget) -> None:
        self._column = None
        self.contentLayout.addWidget(widget)

    def addSmallAction(self, action: QAction) -> QToolButton:
        button = actionButton(action)
        self.addSmallWidget(button)
        return button

    # The following adds a control to the current column, starting a new column when it is full
    def addSmallWidget(self, widget: QWidget, label: str | None = None) -> None:
        if self._column is None or self._column.count() >= SMALL_ROWS:
            self.newColumn()
        assert self._column is not None
        if label is None:
            self._column.addWidget(widget)
            return
        row = QHBoxLayout()
        row.setSpacing(4)
        row.addWidget(QLabel(label))
        row.addWidget(widget, 1)
        self._column.addLayout(row)

    # The following adds controls laid out in a grid, such as color swatches, as one column of the group
    def addGrid(self, widgets: list[QWidget], columns: int) -> None:
        self._column = None
        grid = QGridLayout()
        grid.setSpacing(2)
        for position, widget in enumerate(widgets):
            grid.addWidget(widget, position // columns, position % columns)
        holder = QVBoxLayout()
        holder.addStretch()
        holder.addLayout(grid)
        holder.addStretch()
        self.contentLayout.addLayout(holder)

    def newColumn(self) -> None:
        self._column = QVBoxLayout()
        self._column.setSpacing(1)
        self.contentLayout.addLayout(self._column)
        self._column.setAlignment(Qt.AlignmentFlag.AlignTop)


# The following is a tab of the ribbon, holding its groups side by side with a line between each
class RibbonTab(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.groups: dict[str, RibbonGroup] = {}
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._layout.setSpacing(2)
        self._layout.addStretch()

    def addGroup(self, title: str) -> RibbonGroup:
        if self.groups:
            line = QFrame()
            line.setFrameShape(QFrame.Shape.VLine)
            line.setFrameShadow(QFrame.Shadow.Sunken)
            self._layout.insertWidget(self._layout.count() - 1, line)
        group = RibbonGroup(title)
        self._layout.insertWidget(self._layout.count() - 1, group)
        self.groups[title] = group
        return group


# The following is the ribbon: a tab for each type of item, each with its groups of tools
class Ribbon(QTabWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        # The ribbon is named for the theme, which draws its tabs over a panel; its tab labels are bold
        self.setObjectName("ribbon")
        self.setUsesScrollButtons(True)
        boldFont = self.tabBar().font()
        boldFont.setBold(True)
        self.tabBar().setFont(boldFont)
        self.tabBar().setObjectName("ribbonTabs")
        self.tabBar().setDrawBase(False)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.ribbonTabs: dict[str, RibbonTab] = {}

    def addRibbonTab(self, title: str, index: int | None = None) -> RibbonTab:
        tab = RibbonTab()
        if index is None:
            self.addTab(tab, title)
        else:
            self.insertTab(index, tab, title)
        self.ribbonTabs[title.replace("&", "")] = tab
        return tab

    def ribbonTab(self, title: str) -> RibbonTab:
        return self.ribbonTabs[title]

    # The ribbon is as tall as its tallest tab, so it does not change height as tabs are chosen
    def sizeHint(self) -> QSize:  # noqa: N802 - Qt override
        hint = super().sizeHint()
        tallest = max((tab.sizeHint().height() for tab in self.ribbonTabs.values()), default=0)
        return QSize(hint.width(), max(hint.height(), tallest + self.tabBar().sizeHint().height() + 4))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt override
        return QSize(super().minimumSizeHint().width(), self.sizeHint().height())
