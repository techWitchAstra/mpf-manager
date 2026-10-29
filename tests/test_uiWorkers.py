import sys

import pytest

from mpfmanager.ui.uiWorkers import CommandQueue, RunningProcess, runInThread


def _python(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def _runQueue(qtbot, queue: CommandQueue, commands: list[list[str]]) -> tuple[list[bool], list[str]]:
    results: list[bool] = []
    output: list[str] = []
    queue.outputSignal.connect(output.append)
    queue.run(commands, results.append)
    qtbot.waitUntil(lambda: bool(results), timeout=15000)
    return results, output


def test_commandQueueRunsCommandsInOrder(qtbot):
    queue = CommandQueue()
    busyChanges: list[bool] = []
    queue.busyChangedSignal.connect(busyChanges.append)
    results, output = _runQueue(qtbot, queue, [_python("print('first')"), _python("print('second')")])
    assert results == [True]
    assert busyChanges == [True, False]
    assert not queue.isBusy
    joinedOutput = "\n".join(output)
    assert joinedOutput.index("first") < joinedOutput.index("second")


def test_commandQueueStopsAtFailure(qtbot):
    results, output = _runQueue(
        qtbot, CommandQueue(), [_python("import sys; sys.exit(3)"), _python("print('never runs')")]
    )
    assert results == [False]
    assert "Command failed with exit code 3" in output
    assert "never runs" not in "\n".join(output)


def test_commandQueueReportsFailedStart(qtbot, tmp_path):
    results, output = _runQueue(qtbot, CommandQueue(), [[str(tmp_path / "does-not-exist")]])
    assert results == [False]
    assert any(line.startswith("Failed to start") for line in output)


def test_commandQueueRefusesSecondRunWhileBusy(qtbot):
    queue = CommandQueue()
    results: list[bool] = []
    queue.run([_python("import time; time.sleep(0.5)")], results.append)
    with pytest.raises(RuntimeError):
        queue.run([_python("pass")])
    qtbot.waitUntil(lambda: bool(results), timeout=15000)


def test_commandQueueWithoutCallback(qtbot):
    queue = CommandQueue()
    busyChanges: list[bool] = []
    queue.busyChangedSignal.connect(busyChanges.append)
    queue.run([_python("pass")])
    qtbot.waitUntil(lambda: busyChanges == [True, False], timeout=15000)


def test_runningProcessOutputAndStop(qtbot, tmp_path):
    process = RunningProcess(_python("import time; print('ready', flush=True); time.sleep(60)"), tmp_path)
    output: list[str] = []
    process.outputSignal.connect(output.append)
    process.startProcess()
    qtbot.waitUntil(lambda: "ready" in output, timeout=15000)
    assert output[0].startswith("$ ")
    with qtbot.waitSignal(process.stoppedSignal, timeout=15000):
        process.stopProcess()


def test_runningProcessReportsExitCode(qtbot, tmp_path):
    process = RunningProcess(_python("import sys; sys.exit(4)"), tmp_path)
    with qtbot.waitSignal(process.stoppedSignal, timeout=15000) as stopped:
        process.startProcess()
    assert stopped.args == [4]


def test_runningProcessFailedStart(qtbot, tmp_path):
    process = RunningProcess([str(tmp_path / "does-not-exist")], tmp_path)
    output: list[str] = []
    process.outputSignal.connect(output.append)
    with qtbot.waitSignal(process.stoppedSignal, timeout=15000) as stopped:
        process.startProcess()
    assert stopped.args == [-1]
    assert any(line.startswith("Failed to start") for line in output)


def test_runInThreadDeliversResult(qtbot):
    results = []
    runInThread(lambda: 21 * 2, results.append)
    qtbot.waitUntil(lambda: results == [42])


def test_runInThreadDeliversError(qtbot):
    def failing():
        raise ValueError("broken")

    errors = []
    runInThread(failing, lambda _result: None, errors.append)
    qtbot.waitUntil(lambda: errors == ["broken"])


def test_runInThreadIgnoresErrorWithoutHandler(qtbot):
    finished = []

    def failing():
        finished.append(True)
        raise ValueError("")

    runInThread(failing, lambda _result: None)
    qtbot.waitUntil(lambda: finished == [True])
