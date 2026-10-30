"""Runs external commands and blocking calls so the UI does not freeze"""

#   uiWorkers - Manager of external commands and blocking calls
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human by a human at all stages

from __future__ import annotations

# Importation of necessary functions
import shlex
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QProcess, QRunnable, QThreadPool, QTimer, Signal, Slot


# The following creates a Command Queue class for queueing commands
class CommandQueue(QObject):
    """Run Commands uing QProcess"""

    # The following sets up the queue control signals
    outputSignal = Signal(str)
    busyChangedSignal = Signal(bool)

    # The following function sets up the queue
    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._pendingCommands: list[list[str]] = []
        self._onDone: Callable[[bool], None] | None = None
        self._running = False

        # One process is reused for every command and never deleted while its own signals are being handled,
        # which avoids a double delete when a deleted process releases the last reference to the queue
        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._read)
        self._process.finished.connect(self._finished)
        self._process.errorOccurred.connect(self._errored)

    # The following sets up the busy property check
    @property
    def isBusy(self) -> bool:
        return self._running

    # The following runs a set of commands
    def run(self, commands: list[list[str]], onDone: Callable[[bool], None] | None = None) -> None:
        if self.isBusy:
            raise RuntimeError("Another operation is still running")
        self._pendingCommands = list(commands)
        self._onDone = onDone
        self._running = True
        self.busyChangedSignal.emit(True)
        self._next()

    # The following runs the next command in the queue
    def _next(self) -> None:
        if not self._pendingCommands:
            self._finish(True)
            return

        nextCMD = self._pendingCommands.pop(0)
        self.outputSignal.emit(f"$ {shlex.join(nextCMD)}")
        self._process.start(nextCMD[0], nextCMD[1:])

    # The following function reads the output from a process
    def _read(self) -> None:
        readText = bytes(self._process.readAllStandardOutput().data()).decode(errors="replace").rstrip()
        if readText:
            self.outputSignal.emit(readText)

    # The following function reads the exit of a process to check for errors
    def _finished(self, exitCode: int, exitStatus: QProcess.ExitStatus) -> None:
        self._read()
        if exitStatus != QProcess.ExitStatus.NormalExit or exitCode != 0:
            self.outputSignal.emit(f"Command failed with exit code {exitCode}")
            self._finish(False)
        else:
            # The next command is started once the process has finished handling its own finished signal
            QTimer.singleShot(0, self, self._next)

    # The following is called if a process errors out before starting
    def _errored(self, processError: QProcess.ProcessError) -> None:
        if processError == QProcess.ProcessError.FailedToStart and self._running:
            self.outputSignal.emit(f"Failed to start: {self._process.program()}")
            self._finish(False)

    # The following processes if the queue is complete
    def _finish(self, ok: bool) -> None:
        self._running = False
        self._pendingCommands = []
        callback, self._onDone = self._onDone, None
        self.busyChangedSignal.emit(False)
        if callback:
            callback(ok)


# The following class is used as a QObject for long running processes like mpf or godot
class RunningProcess(QObject):
    """The following handles long running processes that transmit outputs line by line"""

    # The following sets up signals for long running processes
    outputSignal = Signal(str)
    stoppedSignal = Signal(int)

    # The following function sets up the process when it is initialized
    def __init__(self, runningProcessCMD: list[str], commandWorkingPath: Path, parentObject: QObject | None = None):
        super().__init__(parentObject)
        self.runningProcessCMD = runningProcessCMD
        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(commandWorkingPath))
        self.process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.finished.connect(lambda code, _status: self.stoppedSignal.emit(code))
        self.process.errorOccurred.connect(self._errored)

    # The following starts the running process
    def startProcess(self) -> None:
        self.outputSignal.emit(f"$ {shlex.join(self.runningProcessCMD)}")
        self.process.start(self.runningProcessCMD[0], self.runningProcessCMD[1:])

    # The following stops the running process
    def stopProcess(self) -> None:
        self.process.terminate()
        if not self.process.waitForFinished(3000):
            self.process.kill()

    # The following reads the output of the process
    def _read(self) -> None:
        text = bytes(self.process.readAllStandardOutput().data()).decode(errors="replace").rstrip()
        if text:
            self.outputSignal.emit(text)

    # The following processes an errored out process
    def _errored(self, erroredProcess: QProcess.ProcessError) -> None:
        if erroredProcess == QProcess.ProcessError.FailedToStart:
            self.outputSignal.emit(f"Failed to start: {self.runningProcessCMD[0]}")
            self.stoppedSignal.emit(-1)


# The following slots the done and failed signal to the GUI
class _Signals(QObject):
    """A Class to hold signals to be called by the GUI"""

    # The following sets up signals to be read by the GUI
    doneSignal = Signal(object)
    failedSignal = Signal(str)

    # The following sets the signals up at initialization
    def __init__(self, onDone: Callable[[Any], None], onError: Callable[[str], None] | None):
        super().__init__()
        self._onDone = onDone
        self._onError = onError
        self.doneSignal.connect(self._handle_done)
        self.failedSignal.connect(self._handle_failed)

    # The following slots the done signal
    @Slot(object)
    def _handle_done(self, result: Any) -> None:
        _live.discard(self)
        self._onDone(result)

    # The following slots the error signal
    @Slot(str)
    def _handle_failed(self, message: str) -> None:
        _live.discard(self)
        if self._onError:
            self._onError(message)


# The following creates a task object
class _Task(QRunnable):
    def __init__(self, callableFunction: Callable[[], Any], signals: _Signals):
        super().__init__()
        self.callableFunction = callableFunction
        self.signals = signals

    # The following runs the task
    def run(self) -> None:
        try:
            result = self.callableFunction()
        except Exception as taskException:  # noqa: BLE001 - reported back to the GUI
            self.signals.failedSignal.emit(str(taskException) or type(taskException).__name__)
        else:
            self.signals.doneSignal.emit(result)


# The following keeps the signal objects alive until they can report back
_live: set[_Signals] = set()


# The following function runs a callable function in the global thread pool
def runInThread(
    callableFunction: Callable[[], Any],
    onDone: Callable[[Any], None],
    onError: Callable[[str], None] | None = None,
) -> None:
    """Calls the function on the global thread pool and delivers its result on the GUI thread."""
    signals = _Signals(onDone, onError)
    _live.add(signals)
    QThreadPool.globalInstance().start(_Task(callableFunction, signals))
