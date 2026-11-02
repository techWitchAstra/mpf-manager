"""Manager tabs: the tabs down the left edge of MPF-Manager that switch between its managers"""

#   managerTabs - Responsible for the tabs down the left edge of the window:
#       the Project Manager (running the open project), the Show Manager,
#       and the Hardware and Game Managers still to come
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTabBar, QWidget

# The following are the managers listed on the window's left edge.  The Hardware and Game Managers are still to come
MANAGER_TABS = ("Project Manager", "Show Manager", "Hardware Manager", "Game Manager")
PROJECT_MANAGER_TAB, SHOW_MANAGER_TAB, HARDWARE_MANAGER_TAB, GAME_MANAGER_TAB = range(len(MANAGER_TABS))
MANAGER_TOOLTIPS = {
    PROJECT_MANAGER_TAB: "The open project: running it, its run profiles and its environment",
    SHOW_MANAGER_TAB: "View and edit the machine's shows",
    HARDWARE_MANAGER_TAB: "Coming soon",
    GAME_MANAGER_TAB: "Coming soon",
}
COMING_SOON_TABS = (HARDWARE_MANAGER_TAB, GAME_MANAGER_TAB)


# The following is the column of manager tabs, with the window's own manager chosen.  Clicking a manager tells the
# window, which switches to it and chooses its tab
class ManagerTabBar(QTabBar):
    managerChosen = Signal(int)

    def __init__(self, current: int, parent: QWidget | None = None):
        super().__init__(parent)
        # The tabs are named for the theme, and their labels are bold
        self.setObjectName("managerTabs")
        boldFont = self.font()
        boldFont.setBold(True)
        self.setFont(boldFont)
        self.setShape(QTabBar.Shape.RoundedWest)
        self.setExpanding(False)
        for index, managerName in enumerate(MANAGER_TABS):
            self.addTab(managerName)
            self.setTabToolTip(index, MANAGER_TOOLTIPS[index])
        for comingTab in COMING_SOON_TABS:
            self.setTabEnabled(comingTab, False)
        self.setCurrentIndex(current)
        self.tabBarClicked.connect(self._tabClicked)

    def _tabClicked(self, index: int) -> None:
        if 0 <= index < self.count() and self.isTabEnabled(index):
            self.managerChosen.emit(index)
