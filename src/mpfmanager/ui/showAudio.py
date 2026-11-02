"""Show audio: plays the sounds a show plays, in time with the show viewer's playback"""

#   showAudio - Responsible for hearing a show's sounds while it plays in
#       the show viewer.  Each sound the show plays has a player of its own,
#       started where the playhead is in it, kept in time with the playhead,
#       turned up and down with its volume and fades, and stopped when the
#       show pauses or the sound ends
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from PySide6.QtCore import QObject, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from mpfmanager.core.showManager import SoundPlay

# A player more than this far from where the playhead says it should be, in seconds, is moved there
DRIFT_LIMIT = 0.25
# A sound whose length is not known yet is taken to play for this long
UNKNOWN_LENGTH = 3600.0


# The following is what a sound's player does, which a real media player does, or a stand in for testing
class SoundPlayer(Protocol):
    def start(self, audioPath: Path, position: float, volume: float, rate: float) -> None: ...

    def position(self) -> float: ...

    def isPlaying(self) -> bool: ...

    def seek(self, position: float) -> None: ...

    def setVolume(self, volume: float) -> None: ...

    def setRate(self, rate: float) -> None: ...

    def stop(self) -> None: ...


# The following plays one sound through the computer's speakers
class MediaSoundPlayer(QObject):
    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self.output = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.output)
        self.audioPath: Path | None = None

    def start(self, audioPath: Path, position: float, volume: float, rate: float) -> None:
        if audioPath != self.audioPath:
            self.audioPath = audioPath
            self.player.setSource(QUrl.fromLocalFile(str(audioPath)))
        self.output.setVolume(volume)
        self.player.setPlaybackRate(rate)
        self.player.setPosition(int(position * 1000))
        self.player.play()

    def position(self) -> float:
        return self.player.position() / 1000

    def isPlaying(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def seek(self, position: float) -> None:
        self.player.setPosition(int(position * 1000))

    def setVolume(self, volume: float) -> None:
        self.output.setVolume(volume)

    def setRate(self, rate: float) -> None:
        self.player.setPlaybackRate(rate)

    def stop(self) -> None:
        self.player.stop()


# The following keeps a show's sounds playing in time with the playhead.  It is told the time each time the playhead
# moves while the show plays, and starts, moves and stops each sound's player to match
class ShowAudio(QObject):
    def __init__(self, playerFactory: Callable[[], SoundPlayer] | None = None, parent: QObject | None = None):
        super().__init__(parent)
        self.playerFactory = playerFactory or (lambda: MediaSoundPlayer(self))
        self.players: dict[int, SoundPlayer] = {}
        self.isEnabled = True
        self.volume = 1.0

    # The following turns hearing the show's sounds on or off
    def setEnabled(self, isEnabled: bool) -> None:
        self.isEnabled = isEnabled
        if not isEnabled:
            self.stopAll()

    # The following sets how loud the show's sounds are, from 0 to 1, along with each sound's own volume
    def setVolume(self, volume: float) -> None:
        self.volume = min(max(volume, 0.0), 1.0)

    # The following plays each sound that is playing at a time, where it is in the sound then, and stops the others.
    # Sounds are found by name, and their lengths are given once they are known
    def sync(
        self,
        plays: list[SoundPlay],
        soundFiles: dict[str, Path],
        soundLength: Callable[[Path], float | None],
        atTime: float,
        rate: float = 1.0,
    ) -> None:
        if not self.isEnabled:
            return
        playing: set[int] = set()
        for index, play in enumerate(plays):
            audioPath = soundFiles.get(play.soundName)
            if audioPath is None:
                continue
            length = soundLength(audioPath) or UNKNOWN_LENGTH
            position = play.positionAt(atTime, length)
            if position is None:
                continue
            playing.add(index)
            volume = play.gainAt(atTime, length) * self.volume
            player = self.players.get(index)
            if player is None:
                player = self.players[index] = self.playerFactory()
            if not player.isPlaying():
                player.start(audioPath, position, volume, rate)
                continue
            player.setVolume(volume)
            player.setRate(rate)
            if abs(player.position() - position) > DRIFT_LIMIT * max(rate, 1.0):
                player.seek(position)
        for index, player in self.players.items():
            if index not in playing and player.isPlaying():
                player.stop()

    # The following stops every sound, e.g. when the show pauses
    def stopAll(self) -> None:
        for player in self.players.values():
            player.stop()

    # The following forgets the players, e.g. when another show is chosen, whose sounds are different
    def reset(self) -> None:
        self.stopAll()
        self.players.clear()
