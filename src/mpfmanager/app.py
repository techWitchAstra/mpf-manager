"""mpf-Manager applicaton launch script"""

#   app.py - Responsible for launching the application and its GUI
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human by a human at all stages

from __future__ import annotations

# Import System Module
import sys

# Import QApplication and QTimer from PySide6
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

# Import UI from UI folder
from mpfmanager.core.storageManager import StorageProcessor
from mpfmanager.ui.mainWindow import MainWindow
from mpfmanager.ui.theme import applyTheme


# The following defines the main application activity or routine
def main() -> None:
    """Main Window Activity"""

    # The following defines the main application
    managerApplication = QApplication(sys.argv)
    managerApplication.setApplicationName("mpf-Manager")

    # The following gives the application its theme, before its windows are made, and the main window for users
    storedData = StorageProcessor()
    applyTheme(managerApplication, storedData.settings.theme)
    managerWindow = MainWindow(storedData)
    managerWindow.show()

    # Once the event loop has started, run the startup run profile, or ask which project to open
    QTimer.singleShot(0, managerWindow.startUp)

    # Qt Closing line to pass exit code on exit
    sys.exit(managerApplication.exec())


# Prevent the main routine from being called upon import instead of upon execution
if __name__ == "__main__":
    main()
