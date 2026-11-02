"""Audio waveforms: decodes the sounds a show plays into the peaks and energy the show viewer draws"""

#   audioWaveform - Responsible for reading audio files in the background and
#       reducing them to a waveform envelope for the show viewer's audio row
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

import math
from array import array
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat

# The following sets how the audio is decoded: mono, at a low rate that is plenty for drawing a waveform
DECODE_SAMPLE_RATE = 8000

# The following is how many waveform buckets are kept for each second of audio
BUCKETS_PER_SECOND = 200
_SAMPLES_PER_BUCKET = DECODE_SAMPLE_RATE // BUCKETS_PER_SECOND


# The following data class holds a sound reduced to its loudest sample (peak) and energy (rms) over short buckets
@dataclass
class Waveform:
    """The envelope of a decoded sound"""

    duration: float = 0.0
    peaks: array = field(default_factory=lambda: array("f"))
    energies: array = field(default_factory=lambda: array("f"))

    # The following returns the peak and energy of the sound from one time to another
    def envelope(self, startSeconds: float, endSeconds: float) -> tuple[float, float]:
        firstBucket = max(int(startSeconds * BUCKETS_PER_SECOND), 0)
        lastBucket = min(max(int(endSeconds * BUCKETS_PER_SECOND), firstBucket + 1), len(self.peaks))
        if firstBucket >= lastBucket:
            return 0.0, 0.0
        peak = max(self.peaks[firstBucket:lastBucket])
        energy = math.sqrt(
            sum(value * value for value in self.energies[firstBucket:lastBucket]) / (lastBucket - firstBucket)
        )
        return peak, energy


# The following collects decoded samples into waveform buckets
class _WaveformBuilder:
    def __init__(self):
        self.waveform = Waveform()
        self.pending = array("f")

    def addSamples(self, samples: array) -> None:
        self.pending.extend(samples)
        bucketCount = len(self.pending) // _SAMPLES_PER_BUCKET
        for bucket in range(bucketCount):
            self._addBucket(self.pending[bucket * _SAMPLES_PER_BUCKET : (bucket + 1) * _SAMPLES_PER_BUCKET])
        del self.pending[: bucketCount * _SAMPLES_PER_BUCKET]

    def finish(self, sampleCount: int) -> Waveform:
        if self.pending:
            self._addBucket(self.pending)
        self.waveform.duration = sampleCount / DECODE_SAMPLE_RATE
        return self.waveform

    def _addBucket(self, samples: array) -> None:
        self.waveform.peaks.append(min(max(abs(value) for value in samples), 1.0))
        self.waveform.energies.append(min(math.sqrt(sum(value * value for value in samples) / len(samples)), 1.0))


# The following decodes audio files in the background and keeps their waveforms, telling listeners when one is ready
class WaveformLoader(QObject):
    waveformReady = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.waveforms: dict[str, Waveform | None] = {}
        self.decoders: dict[str, QAudioDecoder] = {}
        self.finishedDecoders: list[QAudioDecoder] = []

    # The following returns a sound's waveform, None while it is being decoded, or if it could not be
    def waveform(self, audioPath: Path) -> Waveform | None:
        return self.waveforms.get(str(audioPath))

    def isLoading(self, audioPath: Path) -> bool:
        return str(audioPath) in self.decoders

    def hasFailed(self, audioPath: Path) -> bool:
        return str(audioPath) in self.waveforms and self.waveforms[str(audioPath)] is None

    # The following starts decoding a sound, unless it has been already
    def request(self, audioPath: Path) -> None:
        key = str(audioPath)
        if key in self.waveforms or key in self.decoders:
            return

        decodeFormat = QAudioFormat()
        decodeFormat.setSampleFormat(QAudioFormat.SampleFormat.Float)
        decodeFormat.setChannelCount(1)
        decodeFormat.setSampleRate(DECODE_SAMPLE_RATE)
        decoder = QAudioDecoder(self)
        decoder.setAudioFormat(decodeFormat)
        decoder.setSource(QUrl.fromLocalFile(key))
        builder = _WaveformBuilder()
        sampleCount = [0]

        def readBuffer() -> None:
            audioBuffer = decoder.read()
            samples = _samplesFrom(bytes(audioBuffer.constData()), audioBuffer.format())
            sampleCount[0] += len(samples)
            builder.addSamples(samples)

        decoder.bufferReady.connect(readBuffer)
        decoder.finished.connect(lambda: self._finished(key, builder.finish(sampleCount[0])))
        decoder.error.connect(lambda _error: self._finished(key, None))
        self.decoders[key] = decoder
        decoder.start()

    def _finished(self, key: str, waveform: Waveform | None) -> None:
        decoder = self.decoders.pop(key, None)
        if decoder is None:
            return
        self.waveforms[key] = waveform if waveform is None or waveform.duration > 0 else None
        # A finished decoder is kept (idle) rather than deleted, as deleting one straight after it finishes can crash
        self.finishedDecoders.append(decoder)
        self.waveformReady.emit(key)


# The following turns a decoded buffer into mono float samples, whatever sample format the decoder gave
def _samplesFrom(data: bytes, audioFormat: QAudioFormat) -> array:
    sampleFormat = audioFormat.sampleFormat()
    typeCode, scale = {
        QAudioFormat.SampleFormat.Float: ("f", 1.0),
        QAudioFormat.SampleFormat.Int16: ("h", 32768.0),
        QAudioFormat.SampleFormat.Int32: ("i", 2147483648.0),
        QAudioFormat.SampleFormat.UInt8: ("B", 128.0),
    }.get(sampleFormat, ("f", 1.0))
    rawSamples = array(typeCode)
    rawSamples.frombytes(data[: len(data) - len(data) % rawSamples.itemsize])
    channels = max(audioFormat.channelCount(), 1)
    if typeCode == "f" and channels == 1:
        return rawSamples
    offset = 128.0 if sampleFormat == QAudioFormat.SampleFormat.UInt8 else 0.0
    samples = array("f")
    for frame in range(0, len(rawSamples) - channels + 1, channels):
        samples.append(sum(rawSamples[frame : frame + channels]) / channels / scale - offset / scale)
    return samples
