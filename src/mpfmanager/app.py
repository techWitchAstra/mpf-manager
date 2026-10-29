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
from mpfmanager.ui.mainWindow import MainWindow


# The following defines the main application activity or routine
def main() -> None:
    """Main Window Activity"""

    # The following defines the main application
    managerApplication = QApplication(sys.argv)
    managerApplication.setApplicationName("mpf-Manager")

    # The following defines the main window for users
    managerWindow = MainWindow()
    managerWindow.show()

    # Once the event loop has started, run the startup run profile if running one at startup is enabled
    QTimer.singleShot(0, managerWindow.runStartupProfile)

    # Qt Closing line to pass exit code on exit
    sys.exit(managerApplication.exec())


# Prevent the main routine from being called upon import instead of upon execution
if __name__ == "__main__":
    main()
