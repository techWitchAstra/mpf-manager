"""Theme: MPF-Manager's colors, in a purple theme with light or dark panels, or the system's own look"""

#   theme - Responsible for how MPF-Manager looks: a purple background with
#       its major parts (the ribbon, lists, grid, playfield and output log)
#       set apart on panels, in a light or a dark variant, or the system's
#       look.  Widgets the theme styles are named when they are made, e.g.
#       "ribbon", "managerTabs", "sectionHeading" and "primary"
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QLabel, QStyleFactory, QWidget

THEME_PURPLE = "purple"
THEME_PURPLE_DARK = "purple dark"
THEME_SYSTEM = "system"
DEFAULT_THEME = THEME_PURPLE
THEME_LABELS = {THEME_PURPLE: "Purple", THEME_PURPLE_DARK: "Purple dark", THEME_SYSTEM: "System"}


# The following are the colors of a theme: its background and the text on it, the panels its major parts sit on and
# their text, and the colors that pick things out
@dataclass(frozen=True)
class ThemeColors:
    """The colors of a theme"""

    background: str
    backgroundDeep: str
    backgroundEdge: str
    onBackground: str
    onBackgroundMuted: str
    panel: str
    panelAlt: str
    panelBorder: str
    panelText: str
    panelTextMuted: str
    panelDisabled: str
    gridLine: str
    input: str
    accent: str
    accentHover: str
    accentSoft: str
    highlight: str
    log: str
    logText: str
    okBadge: str
    okText: str
    warnBadge: str
    warnText: str
    scrollHandle: str


THEMES: dict[str, ThemeColors] = {
    # A purple background with light panels, so the major parts stand out from it
    THEME_PURPLE: ThemeColors(
        background="#5d4075",
        backgroundDeep="#4a3160",
        backgroundEdge="#3d2851",
        onBackground="#f6f1fb",
        onBackgroundMuted="#d7c8e6",
        panel="#fbf9fd",
        panelAlt="#f2ecf8",
        panelBorder="#cbb9dd",
        panelText="#241a2e",
        panelTextMuted="#6c5d7c",
        panelDisabled="#a99bb8",
        gridLine="#e3d9ee",
        input="#ffffff",
        accent="#7c4fb3",
        accentHover="#8d61c4",
        accentSoft="#e6dbf3",
        highlight="#f2c14e",
        log="#1f1729",
        logText="#e6dcf2",
        okBadge="#d9f2df",
        okText="#1d6b34",
        warnBadge="#fbe3c4",
        warnText="#8a4b00",
        scrollHandle="#b9a6cd",
    ),
    # The same purple made deep, with dark panels a shade lighter than it, for dim rooms and long sessions
    THEME_PURPLE_DARK: ThemeColors(
        background="#241930",
        backgroundDeep="#1b1225",
        backgroundEdge="#120c19",
        onBackground="#efe7f8",
        onBackgroundMuted="#b6a3c9",
        panel="#33254a",
        panelAlt="#3c2c55",
        panelBorder="#5d4075",
        panelText="#efe7f8",
        panelTextMuted="#b6a3c9",
        panelDisabled="#7d6b92",
        gridLine="#47355f",
        input="#2a1e3b",
        accent="#8f5fd0",
        accentHover="#a374e0",
        accentSoft="#4a3466",
        highlight="#f2c14e",
        log="#140e1b",
        logText="#ddd0ee",
        okBadge="#1f4a2c",
        okText="#9be3af",
        warnBadge="#55380f",
        warnText="#f7c97e",
        scrollHandle="#6e5490",
    ),
}


# The following writes the check mark ticked check boxes are drawn with, as style sheets take their images from files
def checkMarkPath(color: str = "#ffffff") -> str:
    folder = Path(tempfile.gettempdir()) / "mpf-manager-theme"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"check-{color.lstrip('#')}.svg"
    if not path.is_file():
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 14 14">'
            f'<path d="M3 7.4 5.8 10.2 11 4" fill="none" stroke="{color}" stroke-width="2.2" '
            'stroke-linecap="round" stroke-linejoin="round"/></svg>'
        )
    return path.as_posix()


# The following builds the style sheet of a theme from its colors
def styleSheet(colors: ThemeColors) -> str:
    c = colors
    checkMark = checkMarkPath()
    return f"""
QMainWindow, QDialog {{ background: {c.background}; }}
QWidget {{ color: {c.panelText}; }}
QMainWindow > QWidget, QStackedWidget, QSplitter {{ background: {c.background}; }}
QLabel {{ color: {c.onBackground}; background: transparent; }}
QLabel#sectionHeading {{ color: {c.onBackground}; font-weight: 700; font-size: 11pt; padding: 6px 2px 2px 2px; }}
QLabel#projectHeading {{ color: {c.onBackground}; font-weight: 800; font-size: 18pt; }}

QMenuBar {{ background: {c.backgroundDeep}; color: {c.onBackground}; padding: 2px 4px; }}
QMenuBar::item {{ background: transparent; padding: 4px 10px; border-radius: 4px; }}
QMenuBar::item:selected {{ background: {c.accent}; color: white; }}
QMenu {{ background: {c.panel}; color: {c.panelText}; border: 1px solid {c.panelBorder}; padding: 4px; }}
QMenu::item {{ padding: 5px 24px 5px 20px; border-radius: 4px; }}
QMenu::item:selected {{ background: {c.accent}; color: white; }}
QMenu::item:disabled {{ color: {c.panelDisabled}; }}
QMenu::separator {{ height: 1px; background: {c.panelBorder}; margin: 4px 8px; }}
QStatusBar {{ background: {c.backgroundDeep}; color: {c.onBackground}; }}
QStatusBar QLabel {{ color: {c.onBackground}; }}

QTabBar#managerTabs {{ background: {c.background}; }}
QTabBar#managerTabs::tab {{
    background: {c.backgroundDeep}; color: {c.onBackgroundMuted}; padding: 14px 7px; margin: 2px 0 2px 3px;
    border-top-left-radius: 8px; border-bottom-left-radius: 8px;
}}
QTabBar#managerTabs::tab:selected {{ background: {c.panel}; color: {c.panelText}; border-left: 4px solid {c.highlight}; }}
QTabBar#managerTabs::tab:hover:!selected {{ background: {c.accent}; color: white; }}
QTabBar#managerTabs::tab:disabled {{ color: {c.panelDisabled}; background: transparent; }}

QTabWidget#ribbon::pane {{ background: {c.panel}; border: 1px solid {c.panelBorder}; border-radius: 8px; top: -1px; }}
QTabWidget#ribbon > QTabBar, QTabBar#ribbonTabs {{ background: {c.background}; }}
QTabBar#ribbonTabs::tab {{
    background: {c.background}; color: {c.onBackground}; padding: 6px 16px; margin-right: 2px; border: none;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
}}
QTabBar#ribbonTabs::tab:selected {{
    background: {c.panel}; color: {c.panelText}; border: 1px solid {c.panelBorder}; border-bottom: 2px solid {c.panel};
}}
QTabBar#ribbonTabs::tab:hover:!selected {{ background: {c.backgroundDeep}; }}
QTabWidget#ribbon QStackedWidget, QTabWidget#ribbon QStackedWidget QWidget {{ background: {c.panel}; }}
QTabWidget#ribbon QLabel, QTabWidget#ribbon QCheckBox {{ color: {c.panelText}; }}
QTabWidget#ribbon QLabel#ribbonCaption, QTabWidget#ribbon QLabel#ribbonCaption:disabled {{
    color: {c.panelTextMuted}; font-size: 8pt;
}}
QToolButton {{ color: {c.panelText}; border-radius: 6px; padding: 3px; }}
QToolButton:hover {{ background: {c.panelAlt}; border: 1px solid {c.panelBorder}; }}
QToolButton:checked {{ background: {c.accentSoft}; border: 1px solid {c.accent}; }}
QToolButton:disabled {{ color: {c.panelDisabled}; }}

QTreeView, QTableView, QTableWidget, QListWidget, QScrollArea {{
    background: {c.panel}; alternate-background-color: {c.panelAlt}; color: {c.panelText};
    border: 1px solid {c.panelBorder}; border-radius: 8px; selection-background-color: {c.accent};
    selection-color: white; gridline-color: {c.gridLine};
}}
QScrollArea > QWidget > QWidget {{ background: {c.panel}; }}
QScrollArea QLabel, QScrollArea QCheckBox {{ color: {c.panelText}; }}
QHeaderView::section {{
    background: {c.panelAlt}; color: {c.panelText}; border: none; border-right: 1px solid {c.gridLine};
    border-bottom: 1px solid {c.panelBorder}; padding: 4px 6px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {c.panelAlt}; border: none; }}

QPlainTextEdit {{
    background: {c.log}; color: {c.logText}; border: 1px solid {c.backgroundEdge}; border-radius: 8px; padding: 6px;
    selection-background-color: {c.accent};
}}
QGraphicsView {{ border: 2px solid {c.backgroundEdge}; border-radius: 8px; background: #17121d; }}

QWidget#overviewCard, QWidget#toolCard {{
    background: {c.panel}; border: 1px solid {c.panelBorder}; border-radius: 10px;
}}
QWidget#overviewCard QLabel, QWidget#toolCard QLabel {{ color: {c.panelText}; }}
QWidget#overviewCard QLabel#projectHeading {{ color: {c.panelText}; }}
QLabel#statusBadge {{ border-radius: 9px; padding: 2px 10px; font-weight: 700; }}
QLabel#statusBadge[state="ok"] {{ background: {c.okBadge}; color: {c.okText}; }}
QLabel#statusBadge[state="warn"] {{ background: {c.warnBadge}; color: {c.warnText}; }}

QComboBox, QLineEdit, QAbstractSpinBox {{
    background: {c.input}; color: {c.panelText}; border: 1px solid {c.panelBorder}; border-radius: 5px;
    padding: 2px 4px; selection-background-color: {c.accent};
}}
QComboBox:focus, QLineEdit:focus, QAbstractSpinBox:focus {{ border: 2px solid {c.highlight}; }}
QComboBox:disabled, QLineEdit:disabled, QAbstractSpinBox:disabled {{ color: {c.panelDisabled}; }}
QComboBox QAbstractItemView {{ background: {c.input}; color: {c.panelText}; selection-background-color: {c.accent}; }}
QCheckBox {{ color: {c.onBackground}; }}
QCheckBox:disabled {{ color: {c.panelDisabled}; }}
QCheckBox::indicator {{
    width: 14px; height: 14px; border: 1px solid {c.scrollHandle}; border-radius: 4px; background: {c.input};
}}
QCheckBox::indicator:hover {{ border-color: {c.accent}; }}
QCheckBox::indicator:checked {{ background: {c.accent}; border-color: {c.accent}; image: url({checkMark}); }}
QCheckBox::indicator:disabled {{ border-color: {c.gridLine}; background: {c.panelAlt}; }}
QCheckBox::indicator:checked:disabled {{ background: {c.panelDisabled}; border-color: {c.panelDisabled}; }}

QPushButton {{
    background: {c.panel}; color: {c.panelText}; border: 1px solid {c.panelBorder}; border-radius: 6px;
    padding: 5px 14px; font-weight: 600;
}}
QPushButton:hover {{ background: {c.panelAlt}; border-color: {c.accent}; }}
QPushButton#primary {{ background: {c.accent}; color: white; border: 1px solid {c.accent}; }}
QPushButton#primary:hover {{ background: {c.accentHover}; }}
QPushButton:disabled {{ color: {c.panelDisabled}; background: {c.panelAlt}; border-color: {c.gridLine}; }}

QSplitter::handle:horizontal {{
    width: 8px; border-left: 3px solid {c.background}; border-right: 3px solid {c.background};
    background: {c.panelBorder};
}}
QSplitter::handle:vertical {{
    height: 8px; border-top: 3px solid {c.background}; border-bottom: 3px solid {c.background};
    background: {c.panelBorder};
}}
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {c.scrollHandle}; border-radius: 4px; min-height: 24px; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {c.scrollHandle}; border-radius: 4px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QSlider::groove:horizontal {{ height: 6px; background: {c.gridLine}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: {c.highlight}; border-radius: 3px; }}
QSlider::handle:horizontal {{
    background: white; border: 2px solid {c.highlight}; width: 14px; margin: -6px 0; border-radius: 8px;
}}
QToolTip {{ background: {c.panel}; color: {c.panelText}; border: 1px solid {c.panelBorder}; padding: 4px; }}
"""


# The following returns the theme's name, or the default theme for a name that is not one
def themeName(name: str | None) -> str:
    return name if name in THEME_LABELS else DEFAULT_THEME


# The following returns the colors of a theme, or None for the system's own look
def themeColors(name: str | None) -> ThemeColors | None:
    return THEMES.get(themeName(name))


# The following gives the application a theme.  Icons drawn from symbols take the color of the text on the panels,
# where the ribbon and other buttons sit, so they are made after the theme is given
def applyTheme(app: QApplication, name: str | None) -> str:
    chosen = themeName(name)
    colors = THEMES.get(chosen)
    if colors is None:
        app.setStyleSheet("")
        app.setPalette(app.style().standardPalette())
        return chosen
    if "Fusion" in QStyleFactory.keys():
        app.setStyle("Fusion")
    palette = QPalette(app.palette())
    palette.setColor(QPalette.ColorRole.Window, QColor(colors.background))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors.panelText))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors.panel))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors.panelAlt))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors.panelText))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors.panel))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors.panelText))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors.accent))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors.panel))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors.panelText))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors.panelTextMuted))
    app.setPalette(palette)
    app.setStyleSheet(styleSheet(colors))
    return chosen


# The following makes a heading for a part of a window, such as a list, which the theme makes bold
def sectionHeading(text: str) -> QLabel:
    heading = QLabel(text)
    heading.setObjectName("sectionHeading")
    return heading


# The following shows a status as a badge: "ok" in green, or "warn" in amber, e.g. a project's status
def setStatusBadge(label: QWidget, state: str) -> None:
    label.setObjectName("statusBadge")
    label.setProperty("state", state)
    label.style().unpolish(label)
    label.style().polish(label)
