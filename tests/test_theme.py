import pytest
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication, QLabel

from mpfmanager.core import compatibilityManager, projectManager, uvManager
from mpfmanager.core.compatibilityManager import PyPIRelease
from mpfmanager.core.storageManager import Project, Settings, StorageProcessor
from mpfmanager.ui import theme
from mpfmanager.ui.dialogs import SettingsDialog
from mpfmanager.ui.mainWindow import MainWindow
from mpfmanager.ui.projectPicker import ProjectPickerDialog
from mpfmanager.ui.showViewer import ShowViewerWindow


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MPF_MANAGER_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(compatibilityManager, "pypiReleaseRetriever", lambda _package: [PyPIRelease("0.80.0", ">=3.8")])
    monkeypatch.setattr(uvManager, "listPythonVersions", lambda: {"3.13"})


@pytest.fixture
def app(qapp):
    # The theme is the application's, so it is put back for the other tests
    style, palette = qapp.style().name(), QPalette(qapp.palette())
    yield qapp
    qapp.setStyleSheet("")
    qapp.setStyle(style)
    qapp.setPalette(palette)


def test_themeNames():
    assert theme.themeName("purple dark") == "purple dark"
    assert theme.themeName("neon") == theme.DEFAULT_THEME == "purple"
    assert theme.themeName(None) == "purple"
    assert theme.themeColors("system") is None
    assert theme.themeColors("purple").background == "#5d4075"
    assert list(theme.THEME_LABELS.values()) == ["Purple", "Purple dark", "System"]


@pytest.mark.parametrize("name", [theme.THEME_PURPLE, theme.THEME_PURPLE_DARK])
def test_themesColorTheApplication(app, name):
    colors = theme.THEMES[name]
    assert theme.applyTheme(app, name) == name
    sheet = app.styleSheet()
    assert f"QMainWindow, QDialog {{ background: {colors.background}; }}" in sheet
    assert "QTabWidget#ribbon::pane" in sheet and "QTabBar#managerTabs::tab:selected" in sheet
    assert app.palette().color(QPalette.ColorRole.Window).name() == colors.background
    # Icons drawn from symbols are drawn in the color of the text on the panels they sit on
    assert app.palette().color(QPalette.ColorRole.WindowText).name() == colors.panelText


def test_systemThemeTakesTheThemeOff(app):
    theme.applyTheme(app, theme.THEME_PURPLE)
    assert theme.applyTheme(app, theme.THEME_SYSTEM) == "system"
    assert app.styleSheet() == ""


def test_darkThemeIsDarker():
    def lightness(color: str) -> int:
        return sum(int(color[index : index + 2], 16) for index in (1, 3, 5))

    light, dark = theme.THEMES["purple"], theme.THEMES["purple dark"]
    for role in ("background", "panel", "panelAlt", "input"):
        assert lightness(getattr(dark, role)) < lightness(getattr(light, role))
    # Text on the dark panels is light
    assert lightness(dark.panelText) > lightness(dark.panel) * 3


def test_headingsAndBadges(qtbot):
    heading = theme.sectionHeading("Show files")
    qtbot.addWidget(heading)
    assert heading.objectName() == "sectionHeading" and heading.text() == "Show files"
    badge = QLabel("OK")
    qtbot.addWidget(badge)
    theme.setStatusBadge(badge, "ok")
    assert badge.objectName() == "statusBadge" and badge.property("state") == "ok"
    theme.setStatusBadge(badge, "warn")
    assert badge.property("state") == "warn"


def test_widgetsAreNamedForTheTheme(qtbot, tmp_path):
    store = StorageProcessor()
    store.addProject(Project("machine", str(projectManager.createNewMPFProject(tmp_path / "machine"))))
    window = MainWindow(store)
    qtbot.addWidget(window)
    window.openProject(store.projectList[0])
    assert window.ribbon.objectName() == "ribbon" and window.ribbon.tabBar().font().bold()
    assert window.managerTabs.objectName() == "managerTabs" and window.managerTabs.font().bold()
    assert window.projectHeading.objectName() == "projectHeading"
    assert window.projectHeading.parentWidget().objectName() == "overviewCard"
    assert window.promptOpenButton.objectName() == "primary"
    status = window.overviewLabels["status"]
    assert status.objectName() == "statusBadge" and status.property("state") == "ok"
    assert window.environmentsDialog.buttons[0].parentWidget().objectName() == "toolCard"
    # A project that is missing shows its status as a warning
    (tmp_path / "machine" / "config" / "config.yaml").unlink()
    window.refreshMainWindow()
    assert status.property("state") == "warn"

    viewer = ShowViewerWindow(tmp_path / "machine")
    qtbot.addWidget(viewer)
    assert viewer.transportCard.objectName() == "toolCard"
    assert viewer.playButton.parentWidget() is viewer.transportCard
    headings = [label.text() for label in viewer.findChildren(QLabel) if label.objectName() == "sectionHeading"]
    assert sorted(headings) == ["Effects", "Show files", "Show token values"]
    assert viewer.effectsPanel.applyButton.objectName() == "primary"
    captions = [label.text() for label in viewer.ribbon.findChildren(QLabel) if label.objectName() == "ribbonCaption"]
    assert "Show file" in captions

    picker = ProjectPickerDialog(store, lambda: None, lambda: None, lambda _project: "OK")
    qtbot.addWidget(picker)
    assert picker.openButton.objectName() == "primary"


def test_preferencesChooseTheTheme(qtbot, app, monkeypatch):
    settings = Settings(theme="purple dark")
    dialog = SettingsDialog(settings)
    qtbot.addWidget(dialog)
    assert dialog.themeOption.currentData() == "purple dark"
    assert [dialog.themeOption.itemText(index) for index in range(3)] == ["Purple", "Purple dark", "System"]
    dialog.themeOption.setCurrentIndex(dialog.themeOption.findData("system"))
    dialog.applySettings(settings)
    assert settings.theme == "system"
    # A theme that is not known shows the default one
    unknown = SettingsDialog(Settings(theme="neon"))
    qtbot.addWidget(unknown)
    assert unknown.themeOption.currentData() == "purple"

    # Choosing a theme in the preferences gives it straight away, and keeps it
    window = MainWindow(StorageProcessor())
    qtbot.addWidget(window)

    def choose(dialog):
        dialog.themeOption.setCurrentIndex(dialog.themeOption.findData("purple dark"))
        return 1

    monkeypatch.setattr(SettingsDialog, "exec", choose)
    window.edit_settings()
    assert StorageProcessor().settings.theme == "purple dark"
    assert theme.THEMES["purple dark"].background in QApplication.instance().styleSheet()
    assert "Now using the Purple dark theme" in window.outputViewer.toPlainText()


def test_checkBoxesAreDrawnWithACheckMark(app):
    path = theme.checkMarkPath()
    assert path.endswith("check-ffffff.svg") and "<svg" in open(path).read()
    theme.applyTheme(app, theme.THEME_PURPLE_DARK)
    assert f"image: url({path})" in app.styleSheet()
