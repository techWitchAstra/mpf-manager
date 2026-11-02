import math
import struct
import wave
from array import array
from pathlib import Path

import pytest
from PySide6.QtMultimedia import QAudioFormat

from mpfmanager.ui import audioWaveform
from mpfmanager.ui.audioWaveform import Waveform, WaveformLoader


def writeTone(path: Path, seconds: float, amplitude: float = 0.5, sampleRate: int = 16000) -> Path:
    """Writes a stereo wav whose left channel is a sine wave that gets louder"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as waveFile:
        waveFile.setnchannels(2)
        waveFile.setsampwidth(2)
        waveFile.setframerate(sampleRate)
        frames = int(seconds * sampleRate)
        waveFile.writeframes(
            b"".join(
                struct.pack("<hh", int(32767 * amplitude * (i / frames) * math.sin(i * 0.3)), 0) for i in range(frames)
            )
        )
    return path


def test_loaderDecodesWaveforms(qtbot, tmp_path):
    loader = WaveformLoader()
    tone = writeTone(tmp_path / "tone.wav", 1.0)
    assert loader.waveform(tone) is None
    with qtbot.waitSignal(loader.waveformReady, timeout=20000) as signal:
        loader.request(tone)
        assert loader.isLoading(tone)
        loader.request(tone)
    assert signal.args == [str(tone)]
    waveform = loader.waveform(tone)
    assert waveform is not None
    assert not loader.isLoading(tone) and not loader.hasFailed(tone)
    assert abs(waveform.duration - 1.0) < 0.05
    assert len(waveform.peaks) == len(waveform.energies) == round(waveform.duration * audioWaveform.BUCKETS_PER_SECOND)

    # The tone gets louder, and the left channel is mixed with the silent right one
    quietPeak, _quietEnergy = waveform.envelope(0.0, 0.1)
    loudPeak, loudEnergy = waveform.envelope(0.85, 0.95)
    assert quietPeak < loudPeak
    assert 0.15 < loudPeak < 0.5
    assert 0 < loudEnergy < loudPeak


def test_loaderReportsFilesThatCannotBeRead(qtbot, tmp_path):
    loader = WaveformLoader()
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"not audio")
    with qtbot.waitSignal(loader.waveformReady, timeout=20000):
        loader.request(broken)
    assert loader.waveform(broken) is None
    assert loader.hasFailed(broken)
    loader._finished(str(broken), None)


def test_waveformEnvelope():
    waveform = Waveform(1.0, array("f", [0.5, 1.0, 0.25]), array("f", [0.3, 0.4, 0.0]))
    assert waveform.envelope(0.0, 0.0) == pytest.approx((0.5, 0.3))
    assert waveform.envelope(0.0, 0.011) == pytest.approx((1.0, math.sqrt((0.09 + 0.16) / 2)))
    assert waveform.envelope(5.0, 6.0) == (0.0, 0.0)


def test_samplesFromOtherFormats():
    def audioFormat(sampleFormat, channels):
        result = QAudioFormat()
        result.setSampleFormat(sampleFormat)
        result.setChannelCount(channels)
        return result

    int16 = array("h", [16384, -16384, 32767, 32767]).tobytes()
    assert list(audioWaveform._samplesFrom(int16, audioFormat(QAudioFormat.SampleFormat.Int16, 2))) == [
        0.0,
        32767 / 32768,
    ]
    uint8 = bytes([128, 255, 0])
    samples = audioWaveform._samplesFrom(uint8, audioFormat(QAudioFormat.SampleFormat.UInt8, 1))
    assert [round(value, 2) for value in samples] == [0.0, 0.99, -1.0]
    int32 = array("i", [1073741824]).tobytes() + b"\x00"
    assert list(audioWaveform._samplesFrom(int32, audioFormat(QAudioFormat.SampleFormat.Int32, 1))) == [0.5]
