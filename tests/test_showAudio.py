from pathlib import Path

import pytest

from mpfmanager.core.showManager import SoundPlay
from mpfmanager.ui.showAudio import MediaSoundPlayer, ShowAudio


class FakePlayer:
    def __init__(self):
        self.playing = False
        self.at = 0.0
        self.volume = 1.0
        self.rate = 1.0
        self.started: list[tuple[Path, float]] = []
        self.seeks: list[float] = []

    def start(self, audioPath, position, volume, rate):
        self.playing, self.at, self.volume, self.rate = True, position, volume, rate
        self.started.append((audioPath, position))

    def position(self):
        return self.at

    def isPlaying(self):
        return self.playing

    def seek(self, position):
        self.at = position
        self.seeks.append(position)

    def setVolume(self, volume):
        self.volume = volume

    def setRate(self, rate):
        self.rate = rate

    def stop(self):
        self.playing = False


@pytest.fixture
def audio(qtbot):
    players: list[FakePlayer] = []

    def factory():
        players.append(FakePlayer())
        return players[-1]

    showAudio = ShowAudio(factory)
    showAudio.madePlayers = players
    return showAudio


def test_soundsPlayInTimeWithThePlayhead(audio, tmp_path):
    files = {"boom": tmp_path / "boom.wav", "music": tmp_path / "music.ogg"}
    plays = [SoundPlay("boom", 0.5, volume=0.5), SoundPlay("music", 0.0, startAt=2.0), SoundPlay("gone", 0.0)]
    lengths = {files["boom"]: 1.0, files["music"]: 10.0}
    audio.setVolume(0.8)

    # Only the sounds playing at the time are started, where they are in their files, at their volume
    audio.sync(plays, files, lengths.get, 0.25)
    assert len(audio.madePlayers) == 1
    music = audio.madePlayers[0]
    assert music.started == [(files["music"], 2.25)] and music.volume == pytest.approx(0.8)
    audio.sync(plays, files, lengths.get, 0.75, rate=2.0)
    boom = audio.madePlayers[1]
    assert boom.started == [(files["boom"], 0.25)] and boom.volume == pytest.approx(0.4) and boom.rate == 2.0
    assert music.rate == 2.0

    # A player that has drifted from the playhead is moved back, and a sound that has ended is stopped
    music.at = 4.0
    audio.sync(plays, files, lengths.get, 1.0)
    assert music.seeks == [3.0]
    audio.sync(plays, files, lengths.get, 1.6)
    assert not boom.playing and music.playing

    # Pausing stops every sound, and turning sounds off keeps them stopped
    audio.stopAll()
    assert not music.playing
    audio.setEnabled(False)
    audio.sync(plays, files, lengths.get, 0.75)
    assert not music.playing and not boom.playing
    audio.setEnabled(True)
    audio.reset()
    assert audio.players == {}


def test_soundsOfUnknownLengthPlayOn(audio, tmp_path):
    files = {"long": tmp_path / "long.wav"}
    audio.sync([SoundPlay("long", 0.0)], files, lambda _path: None, 120.0)
    assert audio.madePlayers[0].started == [(files["long"], 120.0)]
    audio.setVolume(5)
    assert audio.volume == 1.0


def test_mediaPlayerPlaysAFile(qtbot, tmp_path):
    from test_audioWaveform import writeTone

    tone = writeTone(tmp_path / "tone.wav", 0.5)
    player = MediaSoundPlayer()
    player.start(tone, 0.1, 0.0, 1.0)
    assert player.audioPath == tone and player.output.volume() == 0.0
    player.setVolume(0.5)
    player.setRate(1.5)
    player.seek(0.2)
    assert player.player.playbackRate() == 1.5
    player.position()
    player.isPlaying()
    player.stop()
    assert not player.isPlaying()
