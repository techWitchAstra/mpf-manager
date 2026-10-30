import sys

import PySide6
import pytest
from PySide6.QtCore import QCoreApplication, QObject, Signal

# None, True and False are immortal from Python 3.12, so a PySide6 reference leak only crashes older pythons
pytestmark = pytest.mark.skipif(
    sys.version_info >= (3, 12), reason="None/True/False are immortal from Python 3.12, so refcounts can't drift"
)

ROUNDS = 2000

# A leaking PySide6 loses one reference per call (-ROUNDS); a few references either way is unrelated noise
TOLERANCE = 50


class _Emitter(QObject):
    boolSignal = Signal(bool)


def _ignore(_value: bool) -> None:
    pass


def test_processEventsKeepsNoneReferences(qtbot):
    QCoreApplication.processEvents()
    before = sys.getrefcount(None)
    for _ in range(ROUNDS):
        QCoreApplication.processEvents()
    assert abs(sys.getrefcount(None) - before) < TOLERANCE, (
        f"PySide6 {PySide6.__version__} drops references to None in processEvents, "
        "which crashes Python 3.10/3.11 (see the pyside6 pin in pyproject.toml)"
    )


def test_signalEmitKeepsBoolReferences(qtbot):
    emitter = _Emitter()
    emitter.boolSignal.connect(_ignore)
    emitter.boolSignal.emit(True)
    before = sys.getrefcount(True)
    for _ in range(ROUNDS):
        emitter.boolSignal.emit(True)
    assert abs(sys.getrefcount(True) - before) < TOLERANCE, (
        f"PySide6 {PySide6.__version__} drops references to True when emitting signals, "
        "which crashes Python 3.10/3.11 (see the pyside6 pin in pyproject.toml)"
    )
