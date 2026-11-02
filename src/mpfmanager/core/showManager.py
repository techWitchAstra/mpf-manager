"""showManager reads MPF show files and works out what each light does over time"""

#   showManager - Responsible for parsing MPF show files into a timeline of
#       light colors that the show viewer can display
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq

from mpfmanager.core import yamlInterfacer

# The following are the show sections that set light colors
LIGHT_SECTIONS = ("lights", "leds")

# The following is how long a hold step (duration -1) is drawn for, since it never ends on its own
HOLD_DISPLAY_SECONDS = 1.0

# The following limits the automatic time resolution of the viewer grid
MIN_RESOLUTION_SECONDS = 0.01
MAX_RESOLUTION_SECONDS = 1.0

# The following is the default color for a light in the full (dictionary) form when no color is given
DEFAULT_LIGHT_COLOR = "white"

# The following is the show section that plays sounds, and the audio files a sound can be
SOUND_SECTION = "sounds"
AUDIO_SUFFIXES = (".wav", ".ogg", ".mp3", ".flac", ".opus", ".m4a", ".aiff", ".aif")

# The following is the color tokens are drawn in when no value has been given for them
DEFAULT_PREVIEW_RGB = (255, 255, 255)

# The following stops shows that play each other from nesting forever
MAX_SHOW_DEPTH = 10

_TOKEN_RE = re.compile(r"\(([^)]+)\)")
_HEX_RE = re.compile(r"[a-fA-F0-9]{6,8}")

# The following are the named colors MPF understands, taken from mpf/core/rgb_color.py (MIT license)
NAMED_RGB_COLORS: dict[str, tuple[int, int, int]] = dict(
    off=(0, 0, 0), aliceblue=(240, 248, 255), antiquewhite=(250, 235, 215), aqua=(0, 255, 255),
    aquamarine=(127, 255, 212), azure=(240, 255, 255), beige=(245, 245, 220), bisque=(255, 228, 196),
    black=(0, 0, 0), blanchedalmond=(255, 235, 205), blue=(0, 0, 255), blueviolet=(138, 43, 226),
    brown=(165, 42, 42), burlywood=(222, 184, 135), cadetblue=(95, 158, 160), chartreuse=(127, 255, 0),
    chocolate=(210, 105, 30), coral=(255, 127, 80), cornflowerblue=(100, 149, 237), cornsilk=(255, 248, 220),
    crimson=(220, 20, 60), cyan=(0, 255, 255), darkblue=(0, 0, 139), darkcyan=(0, 139, 139),
    darkgoldenrod=(184, 134, 11), darkgray=(169, 169, 169), darkgreen=(0, 100, 0), darkkhaki=(189, 183, 107),
    darkmagenta=(139, 0, 139), darkolivegreen=(85, 107, 47), darkorange=(255, 140, 0), darkorchid=(153, 50, 204),
    darkred=(139, 0, 0), darksalmon=(233, 150, 122), darkseagreen=(143, 188, 143), darkslateblue=(72, 61, 139),
    darkslategray=(47, 79, 79), darkturquoise=(0, 206, 209), darkviolet=(148, 0, 211), deeppink=(255, 20, 147),
    deepskyblue=(0, 191, 255), dimgray=(105, 105, 105), dodgerblue=(30, 144, 255), firebrick=(178, 34, 34),
    floralwhite=(255, 250, 240), forestgreen=(34, 139, 34), fuchsia=(255, 0, 255), gainsboro=(220, 220, 220),
    ghostwhite=(248, 248, 255), gold=(255, 215, 0), goldenrod=(218, 165, 32), gray=(128, 128, 128),
    green=(0, 128, 0), greenyellow=(173, 255, 47), honeydew=(240, 255, 240), hotpink=(255, 105, 180),
    indianred=(205, 92, 92), indigo=(75, 0, 130), ivory=(255, 255, 240), khaki=(240, 230, 140),
    lavender=(230, 230, 250), lavenderblush=(255, 240, 245), lawngreen=(124, 252, 0), lemonchiffon=(255, 250, 205),
    lightblue=(173, 216, 230), lightcoral=(240, 128, 128), lightcyan=(224, 255, 255),
    lightgoldenrodyellow=(250, 250, 210), lightgray=(211, 211, 211), lightgreen=(144, 238, 144),
    lightpink=(255, 182, 193), lightsalmon=(255, 160, 122), lightseagreen=(32, 178, 170),
    lightskyblue=(135, 206, 250), lightslategray=(119, 136, 153), lightsteelblue=(176, 196, 222),
    lightyellow=(255, 255, 224), lime=(0, 255, 0), limegreen=(50, 205, 50), linen=(250, 240, 230),
    magenta=(255, 0, 255), maroon=(128, 0, 0), mediumaquamarine=(102, 205, 170), mediumblue=(0, 0, 205),
    mediumorchid=(186, 85, 211), mediumpurple=(147, 112, 219), mediumseagreen=(60, 179, 113),
    mediumslateblue=(123, 104, 238), mediumspringgreen=(0, 250, 154), mediumturquoise=(72, 209, 204),
    mediumvioletred=(199, 21, 133), midnightblue=(25, 25, 112), mintcream=(245, 255, 250),
    mistyrose=(255, 228, 225), moccasin=(255, 228, 181), navajowhite=(255, 222, 173), navy=(0, 0, 128),
    oldlace=(253, 245, 230), olive=(128, 128, 0), olivedrab=(107, 142, 35), orange=(255, 165, 0),
    orangered=(255, 69, 0), orchid=(218, 112, 214), palegoldenrod=(238, 232, 170), palegreen=(152, 251, 152),
    paleturquoise=(175, 238, 238), palevioletred=(219, 112, 147), papayawhip=(255, 239, 213),
    peachpuff=(255, 218, 185), peru=(205, 133, 63), pink=(255, 192, 203), plum=(221, 160, 221),
    powderblue=(176, 224, 230), purple=(128, 0, 128), red=(255, 0, 0), rosybrown=(188, 143, 143),
    royalblue=(65, 105, 225), saddlebrown=(139, 69, 19), salmon=(250, 128, 114), sandybrown=(244, 164, 96),
    seagreen=(46, 139, 87), seashell=(255, 245, 238), sienna=(160, 82, 45), silver=(192, 192, 192),
    skyblue=(135, 206, 235), slateblue=(106, 90, 205), slategray=(112, 128, 144), snow=(255, 250, 250),
    springgreen=(0, 255, 127), steelblue=(70, 130, 180), tan=(210, 180, 140), teal=(0, 128, 128),
    thistle=(216, 191, 216), tomato=(255, 99, 71), turquoise=(64, 224, 208), violet=(238, 130, 238),
    wheat=(245, 222, 179), white=(255, 255, 255), whitesmoke=(245, 245, 245), yellow=(255, 255, 0),
    yellowgreen=(154, 205, 50),
)  # fmt: skip


# The following data class holds one light entry of a show step
@dataclass
class LightSetting:
    """A color given to a light or token in one show step"""

    value: str
    rgb: tuple[int, int, int] | None
    fadeMs: int = 0
    kind: str = "color"  # color, preview (a token drawn in a preview color), token, stop, invalid or cleared
    fadeText: str = ""
    fullForm: dict[str, Any] | None = None  # the settings as written when the full (dictionary) form is used

    @property
    def isToken(self) -> bool:
        return self.kind in ("token", "preview")


# The following data class holds one step of a show
@dataclass
class ShowStep:
    """A show step with when it starts, how long it lasts and what it does to the lights"""

    stepNumber: int
    startTime: float
    duration: float
    isHold: bool = False
    lights: dict[str, LightSetting] = field(default_factory=dict)
    shows: dict[str, Any] = field(default_factory=dict)
    sounds: dict[str, Any] = field(default_factory=dict)
    otherSections: list[str] = field(default_factory=list)
    showsFirst: bool = False
    otherData: dict[str, Any] = field(default_factory=dict)
    lightSections: dict[str, str] = field(default_factory=dict)
    sectionOrder: list[str] = field(default_factory=list)


# The following data class holds one play of a sound by a show
@dataclass
class SoundPlay:
    """A sound a show plays, when it starts, and how it is played"""

    soundName: str
    startTime: float
    startAt: float = 0.0
    loops: int = 0
    volume: float = 1.0
    fadeIn: float = 0.0
    fadeOut: float = 0.0
    stopTime: float | None = None
    stopLoopingTime: float | None = None
    showName: str = ""
    stepNumber: int = 0

    # The following returns when the play ends for a sound of a given length, None meaning it never ends
    def endTime(self, soundLength: float) -> float | None:
        firstPlayEnd = self.startTime + max(soundLength - self.startAt, 0.0)
        if self.stopLoopingTime is not None and soundLength > 0:
            # Stopping the looping lets the current time through the sound finish
            loopsDone = max(math.ceil((self.stopLoopingTime - firstPlayEnd) / soundLength), 0)
            naturalEnd: float | None = firstPlayEnd + loopsDone * soundLength
        elif self.loops < 0:
            naturalEnd = None
        else:
            naturalEnd = firstPlayEnd + self.loops * soundLength
        if self.stopTime is None:
            return naturalEnd
        return self.stopTime if naturalEnd is None else min(naturalEnd, self.stopTime)

    # The following returns where in the sound file the play is at a time, or None when it is not playing
    def positionAt(self, atTime: float, soundLength: float) -> float | None:
        endTime = self.endTime(soundLength)
        if atTime < self.startTime or (endTime is not None and atTime >= endTime) or soundLength <= 0:
            return None
        elapsed = atTime - self.startTime
        firstPlayLength = soundLength - self.startAt
        if elapsed < firstPlayLength:
            return self.startAt + elapsed
        return (elapsed - firstPlayLength) % soundLength

    # The following returns how loud the play is at a time, from its volume and fades
    def gainAt(self, atTime: float, soundLength: float) -> float:
        gain = self.volume
        if self.fadeIn > 0:
            gain *= min((atTime - self.startTime) / self.fadeIn, 1.0)
        endTime = self.endTime(soundLength)
        if self.fadeOut > 0 and endTime is not None and self.stopTime is not None and endTime == self.stopTime:
            gain *= min((endTime - atTime) / self.fadeOut, 1.0)
        return max(gain, 0.0)


# The following data class holds a row of the viewer, which is a light (or tag) or a show token
@dataclass
class ShowChannel:
    """A light, light tag or show token that the show sets"""

    name: str
    isToken: bool


# The following data class holds the color of a channel from one point in time until the next
@dataclass
class ChannelSegment:
    """The color of a channel from a step's start, including any fade into it"""

    startTime: float
    fadeEndTime: float
    fromRGB: tuple[int, int, int] | None
    setting: LightSetting
    step: ShowStep
    showName: str = ""
    showPath: tuple[str, ...] = ()

    @property
    def isFromOtherShow(self) -> bool:
        """Whether the color comes from a show this show plays, rather than from this show's own steps"""
        return bool(self.showPath)


# The following data class holds what a viewer cell shows
@dataclass
class ChannelState:
    """The color of a channel at one point in time"""

    rgb: tuple[int, int, int] | None
    segment: ChannelSegment | None
    isFading: bool = False


# The following data class holds a whole show worked out into a timeline
@dataclass
class MPFShow:
    """A parsed MPF show"""

    name: str
    sourcePath: Path | None
    steps: list[ShowStep] = field(default_factory=list)
    channels: list[ShowChannel] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    timelineErrors: list[str] = field(default_factory=list)
    soundPlays: list[SoundPlay] = field(default_factory=list)
    isInConfig: bool = False  # whether the show is in the shows: section of a config file, rather than a show file
    _segments: dict[str, list[ChannelSegment]] = field(default_factory=dict, repr=False)
    _segmentStarts: dict[str, list[float]] = field(default_factory=dict, repr=False)

    @property
    def totalDuration(self) -> float:
        if not self.steps:
            return 0.0
        return self.steps[-1].startTime + self.steps[-1].duration

    @property
    def tokens(self) -> list[str]:
        """Every show token used in the show, in light names, colors, and the shows it plays"""
        found: list[str] = []
        for step in self.steps:
            texts = [text for name, setting in step.lights.items() for text in (name, setting.value, setting.fadeText)]
            texts += [str(text) for name, settings in step.shows.items() for text in [name, *_flatten(settings)]]
            texts += [str(text) for name, settings in step.sounds.items() for text in [name, *_flatten(settings)]]
            for text in texts:
                for token in _TOKEN_RE.findall(text):
                    if token not in found:
                        found.append(token)
        return found

    # The following returns the color of a channel at a time into the show
    def channelState(self, channelName: str, atTime: float) -> ChannelState:
        segments = self._segments.get(channelName, [])
        index = bisect.bisect_right(self._segmentStarts.get(channelName, []), atTime) - 1
        if index < 0 or segments[index].setting.kind == "cleared":
            return ChannelState(None, None)
        segment = segments[index]
        targetRGB = segment.setting.rgb
        if targetRGB is None or atTime >= segment.fadeEndTime:
            return ChannelState(targetRGB, segment)

        # A fade starts at the color the light had and blends into the new color, starting from off if unset
        fraction = (atTime - segment.startTime) / (segment.fadeEndTime - segment.startTime)
        return ChannelState(blendRGB(segment.fromRGB or (0, 0, 0), targetRGB, fraction), segment, True)

    # The following returns the chains of shows, from the one this show plays down to the one setting the light, that
    # give a channel its colors, in the order they first set it.  It is empty when only this show's own steps set it
    def channelShowPaths(self, channelName: str) -> list[tuple[str, ...]]:
        paths = [segment.showPath for segment in self._segments.get(channelName, []) if segment.showPath]
        return list(dict.fromkeys(paths))

    # The following returns a sensible grid resolution for the show, from the gaps between changes and fades
    def suggestedResolution(self) -> float:
        changeTimes = sorted({time for starts in self._segmentStarts.values() for time in starts})
        changeTimes = sorted({*changeTimes, *(step.startTime for step in self.steps), self.totalDuration})
        intervals = [later - earlier for earlier, later in zip(changeTimes, changeTimes[1:], strict=False)]
        # Fades get several columns each so the blend between colors can be seen
        intervals += [
            (segment.fadeEndTime - segment.startTime) / 5
            for segments in self._segments.values()
            for segment in segments
            if segment.fadeEndTime > segment.startTime
        ]
        intervals = [interval for interval in intervals if interval > 1e-9]
        if not intervals:
            return MAX_RESOLUTION_SECONDS
        smallest = round(min(intervals), 3)
        return min(max(smallest, MIN_RESOLUTION_SECONDS), MAX_RESOLUTION_SECONDS)

    # The following works out every channel's colors over the show, filling in show tokens and playing nested shows
    def buildTimeline(
        self,
        tokenValues: dict[str, str] | None = None,
        library: dict[str, MPFShow] | None = None,
        previewRGB: tuple[int, int, int] | None = DEFAULT_PREVIEW_RGB,
        namedColors: dict[str, tuple[int, int, int]] | None = None,
    ) -> None:
        builder = _TimelineBuilder(library or {}, previewRGB, namedColors or {})
        builder.playShow(self, 0.0, self.totalDuration, dict(tokenValues or {}), 0, 1.0, "", 0, (), isTop=True)
        self.channels, self._segments, self._segmentStarts = builder.sweep()
        self.timelineErrors = builder.errors
        self.soundPlays = builder.soundPlays()


# The following lists every value in nested show settings so tokens in them can be found
def _flatten(settings: Any) -> list[Any]:
    if isinstance(settings, dict):
        return [item for key, value in settings.items() for item in (key, *_flatten(value))]
    if isinstance(settings, list):
        return [item for value in settings for item in _flatten(value)]
    return [settings]


# The following replaces the show tokens in a text that have values, leaving the others as they are
def substituteTokens(text: str, tokenValues: dict[str, str]) -> str:
    return _TOKEN_RE.sub(lambda match: str(tokenValues.get(match.group(1), match.group(0))), text)


# The following works out the color of a light setting once its tokens are filled in
def resolveSetting(
    setting: LightSetting,
    tokenValues: dict[str, str],
    previewRGB: tuple[int, int, int] | None,
    namedColors: dict[str, tuple[int, int, int]] | None = None,
) -> LightSetting:
    value = substituteTokens(setting.value, tokenValues)
    rgb, kind = resolveColor(value, namedColors)
    if kind == "token" and previewRGB is not None:
        # A color token with no value is drawn in the preview color, keeping any brightness such as (color)%40
        rgb, previewKind = resolveColor(_TOKEN_RE.sub("{:02x}{:02x}{:02x}".format(*previewRGB), value), namedColors)
        kind = "preview" if previewKind == "color" else "token"
    fadeText = substituteTokens(setting.fadeText, tokenValues)
    return LightSetting(value, rgb, fadeTextToMs(fadeText) or 0, kind, fadeText)


# The following works out which lights a light name sets once its tokens are filled in
def resolveLightNames(name: str, tokenValues: dict[str, str], onlyGivenTokens: bool) -> list[str]:
    # A nested show only sets the token lights it was given, as MPF has no lights for the others
    if onlyGivenTokens and any(token not in tokenValues for token in _TOKEN_RE.findall(name)):
        return []
    resolvedName = substituteTokens(name, tokenValues)
    if _TOKEN_RE.search(resolvedName):
        return [resolvedName]
    return [lightName.strip() for lightName in resolvedName.split(",") if lightName.strip()]


# The following holds one change to a light while a timeline is worked out
@dataclass
class _LightEvent:
    time: float
    order: int
    rank: tuple[int, ...]
    instance: int
    channel: str = ""
    setting: LightSetting | None = None
    step: ShowStep | None = None
    showName: str = ""
    showPath: tuple[str, ...] = ()


# The following plays a show and the shows it plays into a list of light changes, then works out each light's colors
class _TimelineBuilder:
    def __init__(
        self,
        library: dict[str, MPFShow],
        previewRGB: tuple[int, int, int] | None,
        namedColors: dict[str, tuple[int, int, int]],
    ):
        self.library = library
        self.previewRGB = previewRGB
        self.namedColors = namedColors
        self.events: list[_LightEvent] = []
        self.errors: list[str] = []
        self.soundEvents: list[tuple[float, int, str, dict[str, Any], str, int]] = []
        self.instanceCount = 0
        self.rankCount = 0

    # The following numbers light changes and show plays in the order MPF makes them
    def _nextRank(self, startRank: tuple[int, ...], isAtStart: bool) -> tuple[int, ...]:
        self.rankCount += 1
        # Changes made as a nested show starts come where the show was played in its parent's step
        return (*startRank, self.rankCount) if isAtStart else (self.rankCount,)

    # The following plays one run of a show from startTime until it finishes or endTime, whichever is first
    def playShow(
        self,
        show: MPFShow,
        startTime: float,
        endTime: float,
        tokenValues: dict[str, str],
        loops: int,
        speed: float,
        showName: str,
        depth: int,
        startRank: tuple[int, ...] = (),
        isTop: bool = False,
        showPath: tuple[str, ...] = (),
    ) -> None:
        self.instanceCount += 1
        instance = self.instanceCount
        speed = speed if speed > 0 else 1.0
        # MPF plays a show with only one step once, whatever its loops are
        loops = 0 if len(show.steps) == 1 else loops
        showPlays: list[tuple[float, str, Any, tuple[int, ...]]] = []
        currentTime = startTime

        while currentTime < endTime:
            for step in show.steps:
                if currentTime >= endTime:
                    break
                isAtStart = currentTime == startTime
                for section in ("shows", "lights") if step.showsFirst else ("lights", "shows"):
                    if section == "shows":
                        for playedName, playSettings in step.shows.items():
                            playRank = self._nextRank(startRank, isAtStart)
                            playedName = substituteTokens(str(playedName), tokenValues)
                            showPlays.append((currentTime, playedName, playSettings, playRank))
                        continue
                    for lightName, setting in step.lights.items():
                        resolvedSetting = resolveSetting(setting, tokenValues, self.previewRGB, self.namedColors)
                        if resolvedSetting.kind == "invalid":
                            # Colors are checked here, once the project's named colors and token values are known
                            stepName = f"Show {showName} step" if showName else "Step"
                            self._addError(
                                f"{stepName} {step.stepNumber}: {lightName} has an invalid color '{resolvedSetting.value}'"
                            )
                        for channel in resolveLightNames(lightName, tokenValues, not isTop):
                            rank = self._nextRank(startRank, isAtStart)
                            self.events.append(
                                _LightEvent(
                                    currentTime, 1, rank, instance, channel, resolvedSetting, step, showName, showPath
                                )
                            )
                # A hold step in a nested show lasts until the show is stopped
                for soundName, soundSettings in step.sounds.items():
                    self._addSoundEvent(currentTime, soundName, soundSettings, tokenValues, showName, step)
                currentTime = endTime if step.isHold and not isTop else currentTime + step.duration / speed
            if loops == 0:
                break
            loops -= 1

        finishTime = min(currentTime, endTime)
        if not isTop:
            # When a show stops, the colors it gave its lights are removed
            self.events.append(_LightEvent(finishTime, 0, (), instance))
        self._playNestedShows(showPlays, finishTime, tokenValues, depth, showPath)

    def _addError(self, error: str) -> None:
        if error not in self.errors:
            self.errors.append(error)

    # The following records a sound a step plays or stops, once its delay has passed
    def _addSoundEvent(
        self,
        stepTime: float,
        soundName: str,
        soundSettings: Any,
        tokenValues: dict[str, str],
        showName: str,
        step: ShowStep,
    ) -> None:
        settings = soundSettings if isinstance(soundSettings, dict) else {"action": str(soundSettings or "play")}
        settings = {str(key): substituteTokens(str(value), tokenValues) for key, value in settings.items()}
        delay = _toSeconds(settings.get("delay"), 0.0)
        self.rankCount += 1
        resolvedName = substituteTokens(soundName, tokenValues)
        self.soundEvents.append((stepTime + delay, self.rankCount, resolvedName, settings, showName, step.stepNumber))

    # The following works out each sound play from the sound events, applying stops and replaces
    def soundPlays(self) -> list[SoundPlay]:
        plays: list[SoundPlay] = []
        playKeys: list[str] = []
        for eventTime, _rank, soundName, settings, showName, stepNumber in sorted(self.soundEvents):
            action = settings.get("action", "play")
            soundKey = settings.get("key") or soundName
            openPlays = [
                play for play, key in zip(plays, playKeys, strict=True) if key == soundKey and play.stopTime is None
            ]
            if action in ("stop", "replace"):
                for play in openPlays:
                    play.stopTime = eventTime
            elif action == "stop_looping":
                for play in openPlays:
                    play.stopLoopingTime = eventTime
            if action in ("play", "replace"):
                plays.append(
                    SoundPlay(
                        soundName,
                        eventTime,
                        _toSeconds(settings.get("start_at"), 0.0),
                        _toNumber(settings.get("loops"), 0, int),
                        _toGain(settings.get("volume")),
                        _toSeconds(settings.get("fade_in"), 0.0),
                        _toSeconds(settings.get("fade_out"), 0.0),
                        showName=showName,
                        stepNumber=stepNumber,
                    )
                )
                playKeys.append(soundKey)
        return plays

    # The following plays the shows a show's steps play, each running until it is replaced, stopped or its player ends
    def _playNestedShows(
        self,
        showPlays: list[tuple[float, str, Any, tuple[int, ...]]],
        finishTime: float,
        tokenValues: dict[str, str],
        depth: int,
        showPath: tuple[str, ...] = (),
    ) -> None:
        if showPlays and depth >= MAX_SHOW_DEPTH:
            self.errors.append("Shows play each other too deeply to show them all")
            return

        # Plays are grouped by their key, which is the show's name unless a key is given to run several copies of a show
        playsByName: dict[str, list[tuple[float, Any, tuple[int, ...], str]]] = {}
        for playTime, playedName, playSettings, playRank in showPlays:
            settings = playSettings if isinstance(playSettings, dict) else {"action": str(playSettings or "play")}
            playKey = str(settings.get("key") or settings.get("show") or playedName)
            plays = playsByName.setdefault(playKey, [])
            # Playing a show again with the same settings leaves it running, as MPF does
            if not plays or plays[-1][1] != settings:
                plays.append((playTime, settings, playRank, playedName))

        for plays in playsByName.values():
            for playIndex, (playTime, settings, playRank, playedName) in enumerate(plays):
                if str(settings.get("action", "play")) != "play":
                    continue
                stopTime = plays[playIndex + 1][0] if playIndex + 1 < len(plays) else finishTime
                showName = substituteTokens(str(settings.get("show") or playedName), tokenValues)
                nestedShow = self.library.get(showName)
                if nestedShow is None:
                    if f"Show {showName} is not in this project" not in self.errors:
                        self.errors.append(f"Show {showName} is not in this project")
                    continue
                showTokens = settings.get("show_tokens") or {}
                nestedTokens = {
                    str(token): substituteTokens(str(value), tokenValues) for token, value in showTokens.items()
                }
                self.playShow(
                    nestedShow,
                    playTime,
                    stopTime,
                    nestedTokens,
                    _toNumber(settings.get("loops"), -1, int),
                    _toNumber(settings.get("speed"), 1.0, float),
                    showName,
                    depth + 1,
                    playRank,
                    showPath=(*showPath, showName),
                )

    # The following works out each channel's colors from the light changes, keeping a stack of the shows setting it
    def sweep(self) -> tuple[list[ShowChannel], dict[str, list[ChannelSegment]], dict[str, list[float]]]:
        timeline = MPFShow("", None)
        stacks: dict[str, list[_LightEvent]] = {}
        instanceChannels: dict[int, list[str]] = {}

        def addSegment(time: float, event: _LightEvent | None, fades: bool) -> None:
            if event is None or event.setting is None or event.step is None:
                setting, step, showName = LightSetting("", None, 0, "cleared"), ShowStep(0, time, 0.0), ""
                showPath: tuple[str, ...] = ()
            else:
                setting, step, showName, showPath = event.setting, event.step, event.showName, event.showPath
            fromRGB = timeline.channelState(channel, time).rgb
            fadeEndTime = time + (setting.fadeMs / 1000 if fades else 0)
            if channel not in timeline._segments:
                timeline._segments[channel] = []
                timeline._segmentStarts[channel] = []
                timeline.channels.append(ShowChannel(channel, bool(_TOKEN_RE.search(channel))))
            timeline._segments[channel].append(
                ChannelSegment(time, fadeEndTime, fromRGB, setting, step, showName, showPath)
            )
            timeline._segmentStarts[channel].append(time)

        for event in sorted(self.events, key=lambda event: (event.time, event.order, event.rank)):
            if event.setting is None:
                for channel in instanceChannels.pop(event.instance, []):
                    stack = stacks[channel]
                    wasTop = bool(stack) and stack[-1].instance == event.instance
                    stack[:] = [entry for entry in stack if entry.instance != event.instance]
                    if wasTop:
                        addSegment(event.time, stack[-1] if stack else None, False)
                continue

            channel = event.channel
            stack = stacks.setdefault(channel, [])
            stack[:] = [entry for entry in stack if entry.instance != event.instance]
            channels = instanceChannels.setdefault(event.instance, [])
            if channel not in channels:
                channels.append(channel)
            if event.setting.kind == "stop" and stack:
                # Stop removes this show's color, showing what is below it
                addSegment(event.time, stack[-1], False)
                continue
            stack.append(event)
            addSegment(event.time, event, True)

        return timeline.channels, timeline._segments, timeline._segmentStarts


# The following reads a time in seconds from a sound setting, using a default when it is missing or invalid
def _toSeconds(value: Any, default: float) -> float:
    if value is None or str(value).strip().lower() in ("", "none"):
        return default
    try:
        return timeToSeconds(value)
    except ValueError:
        return default


# The following reads a sound volume, either a gain such as 0.5 or decibels such as -6db
def _toGain(value: Any) -> float:
    text = str(value).strip().lower() if value is not None else ""
    try:
        if text.endswith("db"):
            return 10 ** (float(text[:-2]) / 20)
        return float(text) if text not in ("", "none") else 1.0
    except ValueError:
        return 1.0


# The following reads a number from a show setting, using a default when it is missing or not a number
def _toNumber(value: Any, default: Any, numberType: type) -> Any:
    try:
        return numberType(value) if value is not None else default
    except ValueError:
        return default


# The following blends two colors as a fade does
def blendRGB(startRGB: tuple[int, int, int], endRGB: tuple[int, int, int], fraction: float) -> tuple[int, int, int]:
    fraction = min(max(fraction, 0.0), 1.0)
    red, green, blue = (int(start + (end - start) * fraction) for start, end in zip(startRGB, endRGB, strict=True))
    return red, green, blue


# The following converts an MPF time string to seconds the same way MPF does, e.g. 200ms, 2s, 1.5 or +1
def timeToSeconds(timeValue: Any) -> float:
    timeString = str(timeValue).strip().lstrip("+")
    if not any(character.isalpha() for character in timeString):
        timeString += "s"
    return timeToMs(timeString) / 1000.0


# The following limits a timebase typed in for the viewer grid
MIN_TIMEBASE_SECONDS = 0.001
MAX_TIMEBASE_SECONDS = 60.0
_TIMEBASE_RE = re.compile(r"^(\d+(?:\.\d*)?|\.\d+)\s*(ms|msec|s|sec|fps)?$")


# The following reads a timebase, the time each column of the viewer grid covers, typed as a time such as 40ms or
# 0.5s, a bare number of milliseconds as MPF reads times, or a frame rate such as 30fps.  It returns the timebase in
# seconds, or None if the text is not a timebase or is outside 1ms to 60s
def parseTimebase(text: str) -> float | None:
    timebaseMatch = _TIMEBASE_RE.match(text.strip().lower())
    if timebaseMatch is None:
        return None
    number, unit = float(timebaseMatch.group(1)), timebaseMatch.group(2) or "ms"
    if unit == "fps":
        seconds = 1 / number if number > 0 else 0.0
    else:
        seconds = number if unit in ("s", "sec") else number / 1000
    # A tiny tolerance lets the limits themselves through, e.g. 1000fps
    if not MIN_TIMEBASE_SECONDS - 1e-12 <= seconds <= MAX_TIMEBASE_SECONDS + 1e-12:
        return None
    return seconds


# The following converts an MPF time string to milliseconds, where a bare number means milliseconds
def timeToMs(timeValue: Any) -> int:
    if timeValue is None or str(timeValue).strip().lower() in ("", "none"):
        return 0
    timeString = str(timeValue).strip().upper()
    for suffix, multiplier in (("MSEC", 1), ("MS", 1), ("SEC", 1000), ("D", 86400000), ("H", 3600000)):
        if timeString.endswith(suffix):
            return int(float(timeString[: -len(suffix)]) * multiplier)
    for suffix, multiplier in (("M", 60000), ("S", 1000)):
        if timeString.endswith(suffix):
            return int(float(timeString[:-1]) * multiplier)
    return int(float(timeString))


# The following works out a light value (a color name, hex value, token, on or stop) as MPF would
def resolveColor(
    value: str, namedColors: dict[str, tuple[int, int, int]] | None = None
) -> tuple[tuple[int, int, int] | None, str]:
    """Return the color a light value gives and its kind: color, token, stop or invalid, using the project's
    named colors (from named_colors: in its config) before MPF's own color names"""
    value = value.strip()
    if "(" in value:
        return None, "token"
    if value == "stop":
        return None, "stop"
    if value == "on":
        return (255, 255, 255), "color"

    # One and two character values are short hex values, e.g. ff is a dim white of ffffff
    if len(value) == 1:
        value = f"0{value}" * 3
    elif len(value) == 2:
        value = value * 3

    brightness = None
    if "%" in value:
        value, brightness = value.split("%", 1)

    rgb = (namedColors or {}).get(value.lower()) or NAMED_RGB_COLORS.get(value.lower())
    if rgb is None and _HEX_RE.fullmatch(value.strip("#")):
        hexValue = value.strip("#")
        width = len(hexValue) // 3
        rgb = (
            int(hexValue[:width], 16),
            int(hexValue[width : 2 * width], 16),
            int(hexValue[2 * width : 3 * width], 16),
        )
    if rgb is None:
        return None, "invalid"

    if brightness:
        try:
            factor = int(brightness) / 100
        except ValueError:
            return None, "invalid"
        red, green, blue = (min(int(channel * factor), 255) for channel in rgb)
        rgb = (red, green, blue)
    return rgb, "color"


# The following reads a fade time, returning None when it is a show token or not a time, which is drawn as no fade
def fadeTextToMs(fadeText: str) -> int | None:
    if _TOKEN_RE.search(fadeText):
        return None
    try:
        return timeToMs(fadeText)
    except ValueError:
        return None


# The following reads one light entry, in either the short form (red-f500ms) or the full form (color: red);
# the fade is kept as written too, as it can be a show token that is only known when the show is played
def parseLightSetting(rawValue: Any) -> LightSetting:
    fadeText = ""
    fullForm = None
    if isinstance(rawValue, dict):
        fullForm = dict(rawValue)
        value = str(rawValue.get("color", DEFAULT_LIGHT_COLOR))
        fade = rawValue.get("fade")
        fadeText = "" if fade is None else str(fade).strip()
    else:
        value = str(rawValue).replace(" ", "")
        if "-f" in value:
            value, fadeText = value.split("-f", 1)
    rgb, kind = resolveColor(value)
    return LightSetting(value, rgb, fadeTextToMs(fadeText) or 0, kind, fadeText, fullForm)


# The following works out the length of a step the same way MPF does
def _stepDuration(showData: list, stepIndex: int, elapsedTime: float) -> float | None:
    step = showData[stepIndex]
    if "duration" in step:
        return timeToSeconds(step["duration"])
    if stepIndex == len(showData) - 1:
        # An empty last step that only has a time just marks the end of the show
        if "time" in step and len(step) == 1 and stepIndex != 0:
            return None
        return 1.0
    if "time" in showData[stepIndex + 1]:
        nextTime = str(showData[stepIndex + 1]["time"]).strip()
        if nextTime.startswith("+"):
            return timeToSeconds(nextTime)
        return timeToSeconds(nextTime) - elapsedTime
    return 1.0


# The following parses a show (a list of steps) into an MPFShow
def parseShow(showData: Any, name: str, sourcePath: Path | None = None) -> MPFShow:
    show = MPFShow(name, sourcePath)
    if not isinstance(showData, list) or not showData:
        show.errors.append("A show should be a list of steps, each starting with a hyphen")
        return show

    elapsedTime = 0.0
    stepNumber = 0

    # A show whose first step has a time other than zero starts with an empty step
    if isinstance(showData[0], dict) and "time" in showData[0]:
        try:
            elapsedTime = max(timeToSeconds(showData[0]["time"]), 0.0)
        except ValueError:
            show.errors.append(f"Step 1 has an invalid time '{showData[0]['time']}'")
        if elapsedTime > 0:
            show.steps.append(ShowStep(0, 0.0, elapsedTime))

    for stepIndex, rawStep in enumerate(showData):
        stepNumber = stepIndex + 1
        if not isinstance(rawStep, dict):
            show.errors.append(f"Step {stepNumber} is not a list of settings")
            continue
        try:
            duration = _stepDuration(showData, stepIndex, elapsedTime)
        except ValueError as error:
            show.errors.append(f"Step {stepNumber} has an invalid time: {error}")
            duration = 1.0
        if duration is None:
            break
        if duration == 0:
            show.errors.append(f"Step {stepNumber} has 0 duration")
            continue

        # A duration of -1 holds the step until the show is advanced, so it is drawn with a fixed length
        isHold = duration < 0
        step = ShowStep(stepNumber, elapsedTime, HOLD_DISPLAY_SECONDS if isHold else duration, isHold)
        for section, sectionValue in rawStep.items():
            # The order of the sections is kept so the step can be written back as it was
            if section not in ("duration", "time"):
                step.sectionOrder.append(str(section))
            if section in LIGHT_SECTIONS and isinstance(sectionValue, dict):
                for lightName, rawValue in sectionValue.items():
                    setting = parseLightSetting(rawValue)
                    step.lights[str(lightName)] = setting
                    step.lightSections[str(lightName)] = str(section)
                    if fadeTextToMs(setting.fadeText) is None and not _TOKEN_RE.search(setting.fadeText):
                        show.errors.append(f"Step {stepNumber}: {lightName} has an invalid fade '{setting.fadeText}'")
            elif section == SOUND_SECTION and isinstance(sectionValue, dict):
                step.sounds = {str(soundName): settings for soundName, settings in sectionValue.items()}
            elif section == "shows" and isinstance(sectionValue, dict):
                step.shows = {str(showName): settings for showName, settings in sectionValue.items()}
                # Whichever of lights and shows comes later in the step sets the lights last
                step.showsFirst = not step.lights
            elif section not in ("duration", "time"):
                step.otherSections.append(str(section))
                step.otherData[str(section)] = sectionValue
        show.steps.append(step)
        elapsedTime += step.duration

    show.buildTimeline()
    return show


# The following are the shows built into MPF, which shows can play without them being in the project
BUILT_IN_SHOWS_YAML = """\
flash:
  - time: 0
    lights: {(light): on, (lights): on, (led): on, (leds): on}
  - time: 1
    lights: {(light): off, (lights): off, (led): off, (leds): off}
  - time: 2
on:
  - duration: -1
    lights: {(light): on, (lights): on, (led): on, (leds): on}
off:
  - duration: -1
    lights: {(light): off, (lights): off, (led): off, (leds): off}
led_color:
  - duration: -1
    lights: {(led): (color), (leds): (color), (light): (color), (lights): (color)}
flash_color:
  - duration: 1
    lights: {(light): (color), (lights): (color), (led): (color), (leds): (color)}
  - duration: 1
    lights: {(light): off, (lights): off, (led): off, (leds): off}
"""


# The following returns MPF's built in shows
def builtInShows() -> dict[str, MPFShow]:
    showData = YAML(typ="base").load(BUILT_IN_SHOWS_YAML)
    return {name: parseShow(steps, name) for name, steps in showData.items()}


# The following loads every show in a yaml file, which is either a show file or a config file with a shows section
def loadShowFile(filePath: Path) -> list[MPFShow]:
    try:
        fileData = _readYAMLCached(filePath, "show")
    except Exception as error:  # any yaml problem is shown to the user rather than raised
        failedShow = MPFShow(filePath.stem, filePath)
        failedShow.errors.append(f"Could not read the file: {error}")
        return [failedShow]

    if isinstance(fileData, list):
        return [parseShow(fileData, filePath.stem, filePath)]
    if isinstance(fileData, dict) and isinstance(fileData.get("shows"), dict):
        shows = [parseShow(showData, str(showName), filePath) for showName, showData in fileData["shows"].items()]
        for show in shows:
            show.isInConfig = True
        return shows

    emptyShow = MPFShow(filePath.stem, filePath)
    emptyShow.errors.append("This file has no shows in it")
    return [emptyShow]


# The following is the first line of a show file, which tells MPF which show format the file is written in
SHOW_FILE_HEADER = "#show_version=6"


# The following writes a time in seconds as MPF reads it, in whole seconds where it can be, e.g. 2s or 250ms.
# MPF times are whole milliseconds, so the time is rounded to the nearest millisecond
def formatDuration(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    return f"{milliseconds // 1000}s" if milliseconds and milliseconds % 1000 == 0 else f"{milliseconds}ms"


# The following writes a light entry back in the form it was written in: the short form (red-f500ms), or the full
# form (color: red) keeping any other settings it was given
def lightSettingToData(setting: LightSetting) -> Any:
    if setting.fullForm is None:
        return setting.value + (f"-f{setting.fadeText}" if setting.fadeText else "")
    lightData = dict(setting.fullForm)
    lightData["color"] = setting.value
    if setting.fadeText:
        lightData["fade"] = setting.fadeText
    else:
        lightData.pop("fade", None)
    return lightData


# The following writes a show step back as a step of a show file, its duration first and then its sections in the
# order they were written.  Every step is written with a duration, which MPF plays the same as the time it was given
def stepToData(step: ShowStep) -> dict[str, Any]:
    stepData: dict[str, Any] = {"duration": -1 if step.isHold else formatDuration(step.duration)}
    lightSections: dict[str, dict[str, Any]] = {}
    for lightName, setting in step.lights.items():
        lightSections.setdefault(step.lightSections.get(lightName, "lights"), {})[lightName] = lightSettingToData(
            setting
        )
    sections: dict[str, Any] = {**lightSections, **step.otherData}
    if step.shows:
        sections["shows"] = step.shows
    if step.sounds:
        sections[SOUND_SECTION] = step.sounds

    # Sections made since the show was read come after the ones it was read with, with shows before lights when the
    # shows set the lights first
    order = [section for section in step.sectionOrder if section in sections]
    newSections = [section for section in sections if section not in order]
    if step.showsFirst and "shows" in newSections:
        newSections.remove("shows")
        firstLights = next((index for index, section in enumerate(order) if section in LIGHT_SECTIONS), len(order))
        order.insert(firstLights, "shows")
    for section in order + newSections:
        stepData[section] = sections[section]
    return stepData


# The following writes a show back as the list of steps a show file holds
def showToData(show: MPFShow) -> list[dict[str, Any]]:
    return [stepToData(step) for step in show.steps]


# The following returns whether a value read from a show file says the same as the value it would be written back as,
# so the value can be kept as it was written, e.g. "red - f 200ms" rather than red-f200ms, or 1 rather than 1s
def _isSameValue(textValue: Any, newValue: Any, kind: str) -> bool:
    try:
        if kind == "light":
            return lightSettingToData(parseLightSetting(textValue)) == newValue
        if kind == "time":
            return str(textValue).strip() == str(newValue) or timeToSeconds(textValue) == timeToSeconds(newValue)
    except (ValueError, AttributeError):
        return False
    return textValue == newValue


# The following merges a value written back into the value as it was read with its comments: what is the same is kept
# as it was written, with its comments, and what changed is replaced
def _mergeValue(readValue: Any, textValue: Any, newValue: Any, kind: str) -> Any:
    if _isSameValue(textValue, newValue, kind):
        return readValue
    if isinstance(readValue, CommentedMap) and isinstance(textValue, dict) and isinstance(newValue, dict):
        return _mergeMapping(readValue, textValue, newValue, lambda _key: "light" if kind == "lights" else "")
    if isinstance(readValue, CommentedSeq) and isinstance(textValue, list) and isinstance(newValue, list):
        return _mergeList(readValue, textValue, newValue)
    return newValue


# The following merges a mapping written back into the mapping as it was read.  Its keys stay in the order they were
# written, with new keys after the key they follow, and the comments of keys taken out stay where they were
def _mergeMapping(
    readMap: CommentedMap,
    textMap: dict,
    newMap: dict[str, Any],
    childKind: Any,
    renames: dict[str, str] | None = None,
) -> CommentedMap:
    renames = renames or {}
    sources: dict[str, Any] = {}
    readKeys = {str(key): key for key in readMap}
    for key in newMap:
        readKey = renames.get(key, key) if renames.get(key, key) in readKeys else key
        if readKey in readKeys and readKeys[readKey] not in sources.values():
            sources[key] = readKeys[readKey]
    keysByReadKey = {readKey: key for key, readKey in sources.items()}

    order = [keysByReadKey[readKey] for readKey in readMap if readKey in keysByReadKey]
    newKeys = list(newMap)
    for position, key in enumerate(newKeys):
        if key not in order:
            order.insert(order.index(newKeys[position - 1]) + 1 if position else 0, key)

    # The comments after the mapping go after its last key, whichever key that is now
    followingComments = yamlInterfacer.takeFollowingComments(readMap, list(readMap)[-1]) if readMap else []
    movedComments: dict[str | None, list[str]] = {}
    lastKept: str | None = None
    for readKey in readMap:
        if readKey in keysByReadKey:
            lastKept = keysByReadKey[readKey]
        else:
            movedComments.setdefault(lastKept, []).extend(yamlInterfacer.itemComments(readMap, readKey, False))

    merged = CommentedMap()
    if readMap.fa.flow_style():
        merged.fa.set_flow_style()
    for key in order:
        if key not in sources:
            merged[key] = newMap[key]
            continue
        readKey = sources[key]
        isRenamed = str(readKey) != key
        textValue = textMap.get(str(readKey)) if isinstance(textMap, dict) else None
        merged[key] = (
            newMap[key] if isRenamed else _mergeValue(readMap[readKey], textValue, newMap[key], childKind(key))
        )
        if readKey in readMap.ca.items:
            merged.ca.items[key] = readMap.ca.items[readKey]
    for key, lines in movedComments.items():
        if merged:
            yamlInterfacer.appendComments(merged, key if key is not None else order[0], lines)
    if merged:
        yamlInterfacer.appendComments(merged, list(merged)[-1], followingComments)
    return merged


# The following merges a list written back into the list as it was read, item by item
def _mergeList(readList: CommentedSeq, textList: list, newList: list) -> CommentedSeq:
    followingComments = yamlInterfacer.takeFollowingComments(readList, len(readList) - 1) if readList else []
    merged = CommentedSeq()
    if readList.fa.flow_style():
        merged.fa.set_flow_style()
    for index, newValue in enumerate(newList):
        if index >= len(readList):
            merged.append(newValue)
            continue
        textValue = textList[index] if index < len(textList) else None
        merged.append(_mergeValue(readList[index], textValue, newValue, ""))
        if index in readList.ca.items:
            merged.ca.items[index] = readList.ca.items[index]
    if merged:
        for index in range(len(newList), len(readList)):
            yamlInterfacer.appendComments(merged, len(merged) - 1, yamlInterfacer.itemComments(readList, index, False))
        yamlInterfacer.appendComments(merged, len(merged) - 1, followingComments)
    return merged


# The following returns what each section of a step holds, so light values can be compared as lights and durations
# as times
def _stepSectionKind(section: str) -> str:
    if section in LIGHT_SECTIONS:
        return "lights"
    return "time" if section == "duration" else ""


# The following data class holds the steps of a show read again from its file, with their comments and as text
@dataclass
class _ShowSource:
    readSteps: CommentedSeq
    textSteps: list
    leadingComments: list[str] = field(default_factory=list)
    isInConfig: bool = False


# The following reads the steps of a show from its file again, with their comments and as text, or returns None if
# the file has gone or no longer has the show's steps in it.  For a show in a config file, the comments written above
# the show's name are read too
def _readShowSource(show: MPFShow) -> _ShowSource | None:
    sourcePath = show.sourcePath
    if sourcePath is None or not sourcePath.is_file():
        return None
    try:
        readData = yamlInterfacer.loadYAML(sourcePath)
        textData = yamlInterfacer.loadYAMLText(sourcePath)
    except Exception:  # a file that cannot be read is written without its comments
        return None
    leadingComments: list[str] = []
    isInConfig = isinstance(readData, dict) and isinstance(textData, dict)
    if isInConfig:
        # A show in a config file is under its shows: section, and the comments above its name are kept above the
        # first show, or after the show before it
        readShows, textShows = readData.get("shows"), textData.get("shows")
        if not isinstance(readShows, CommentedMap) or not isinstance(textShows, dict):
            return None
        showNames = [name for name in readShows if str(name) == show.name]
        if not showNames:
            return None
        position = list(readShows).index(showNames[0])
        if position == 0:
            leadingComments = yamlInterfacer.startComments(readShows)
        else:
            leadingComments = yamlInterfacer.followingComments(readShows, list(readShows)[position - 1])
        readData, textData = readShows[showNames[0]], textShows.get(show.name)
    if not isinstance(readData, CommentedSeq) or not isinstance(textData, list) or len(readData) != len(textData):
        return None
    return _ShowSource(readData, textData, leadingComments, isInConfig)


# The following writes a show back as the list of steps a show file holds, keeping the comments of the file it was
# read from, and writing the values that have not changed as they were written.  Each step is matched to the step of
# the file with its step number, so steps added to a show are numbered 0, or after the file's steps.  Steps that are
# left out, such as an empty last step that only marks the end of the show, keep their comments after the step before
def showToCommentedData(show: MPFShow) -> list[Any]:
    stepsData = showToData(show)
    source = _readShowSource(show)
    if source is None:
        return stepsData
    readSteps, textSteps = source.readSteps, source.textSteps

    # The comments after a show in a config file are above whatever comes next in the file, so they are left there
    followingComments = yamlInterfacer.takeFollowingComments(readSteps, len(readSteps) - 1) if readSteps else []
    if source.isInConfig:
        followingComments = []
    merged = CommentedSeq()
    yamlInterfacer.setStartComments(merged, source.leadingComments + yamlInterfacer.startComments(readSteps))
    mergedIndexes: dict[int, int] = {}
    for step, stepData in zip(show.steps, stepsData, strict=True):
        readIndex = step.stepNumber - 1
        readStep = readSteps[readIndex] if 0 <= readIndex < len(readSteps) else None
        if (
            isinstance(readStep, CommentedMap)
            and isinstance(textSteps[readIndex], dict)
            and readIndex not in mergedIndexes
        ):
            mergedIndexes[readIndex] = len(merged)
            # A step's time is written as its duration, keeping the time's comments
            stepData = _mergeMapping(readStep, textSteps[readIndex], stepData, _stepSectionKind, {"duration": "time"})
        merged.append(stepData)

    leadingComments: list[str] = []
    lastMerged: int | None = None
    for readIndex in range(len(readSteps)):
        if readIndex in mergedIndexes:
            lastMerged = mergedIndexes[readIndex]
            continue
        comments = yamlInterfacer.itemComments(readSteps, readIndex, True)
        if lastMerged is None:
            leadingComments += comments
        else:
            yamlInterfacer.appendComments(merged, lastMerged, comments)
    if merged:
        yamlInterfacer.appendComments(merged, len(merged) - 1, followingComments)
    else:
        leadingComments += followingComments
    yamlInterfacer.setStartComments(merged, yamlInterfacer.startComments(merged) + leadingComments)
    return merged


# The following writes a show to a show file, starting with the show format line MPF looks for unless the file it was
# read from already starts with it.  The comments of the file the show was read from are kept unless asked not to
def exportShowFile(
    show: MPFShow, filePath: Path, headerString: str | None = SHOW_FILE_HEADER, keepComments: bool = True
) -> None:
    showData = showToCommentedData(show) if keepComments else showToData(show)
    startText = "".join(yamlInterfacer.startComments(showData))
    if headerString and headerString.strip() in startText:
        headerString = None
    yamlInterfacer.writeYAML(showData, filePath, headerString, yamlInterfacer.showYAML())


# The following is the start of the format lines of show and config files, which are not kept above a show in a config
_FORMAT_LINE_RE = re.compile(r"^\s*#\s*(show|config)_version\s*=")


# The following writes several shows to one yaml file, under a shows: section as a machine or mode config has them.
# The comments of the files the shows were read from are kept, with the comments at the start of a show file written
# above its show's name
def exportShowsSection(
    shows: list[MPFShow], filePath: Path, headerString: str | None = None, keepComments: bool = True
) -> None:
    showsSection = CommentedMap()
    for show in shows:
        showData = showToCommentedData(show) if keepComments else showToData(show)
        showsSection[show.name] = showData
        if isinstance(showData, CommentedSeq):
            lines = [line for line in yamlInterfacer.startComments(showData) if not _FORMAT_LINE_RE.match(line)]
            yamlInterfacer.setStartComments(showData, [])
            if lines:
                yamlInterfacer.setCommentsBefore(showsSection, show.name, lines, 2)
    yamlInterfacer.writeYAML({"shows": showsSection}, filePath, headerString)


# The following finds the show files of an MPF machine folder, in its shows folder and its modes' shows folders
def findShowFiles(machinePath: Path) -> list[Path]:
    showFolders = [machinePath / "shows", *sorted(machinePath.glob("modes/*/shows"))]
    showFiles: list[Path] = []
    for showFolder in showFolders:
        if showFolder.is_dir():
            showFiles += sorted(path for path in showFolder.rglob("*") if path.suffix in (".yaml", ".yml"))
    return showFiles


# The following are the files that make a folder part of an MPF machine: configs and shows, sounds, playfield images
# and video, and GMC's scenes.  Folders that are hidden, or hold the machine's logs, caches or environments, are not
MPF_FILE_SUFFIXES = (".yaml", ".yml", *AUDIO_SUFFIXES, ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm")
MPF_FILE_SUFFIXES += (".tscn", ".gd")
SKIPPED_FOLDERS = {"logs", "__pycache__", "node_modules", "venv", "env", "build", "dist", "addons"}
MACHINE_FOLDER_DEPTH = 4


# The following finds the folders of an MPF machine folder that hold MPF files, e.g. config, shows, sounds, monitor
# and modes/<mode>/config, so they can be listed with the shows.  The folders that lead to them are listed too
def findMachineFolders(machinePath: Path) -> list[Path]:
    folders: set[Path] = set()
    if not machinePath.is_dir():
        return []

    def search(folder: Path, depth: int) -> None:
        try:
            entries = sorted(folder.iterdir())
        except OSError:
            return
        for entry in entries:
            if entry.name.startswith(".") or entry.is_symlink():
                continue
            if entry.is_dir():
                if depth < MACHINE_FOLDER_DEPTH and entry.name.lower() not in SKIPPED_FOLDERS:
                    search(entry, depth + 1)
            elif entry.suffix.lower() in MPF_FILE_SUFFIXES and folder != machinePath:
                path = folder
                while path != machinePath and path not in folders:
                    folders.add(path)
                    path = path.parent

    search(machinePath, 1)
    return sorted(folders, key=lambda path: [part.lower() for part in path.relative_to(machinePath).parts])


# The following finds the audio files of an MPF machine folder by sound name, which is the file name without its
# extension, or a name given to a file in a sounds: section of the machine or mode config
def findSoundFiles(machinePath: Path) -> dict[str, Path]:
    soundFiles: dict[str, Path] = {}
    filesByName: dict[str, Path] = {}
    if not machinePath.is_dir():
        return soundFiles
    for path in sorted(machinePath.rglob("*")):
        relativeParts = path.relative_to(machinePath).parts
        if path.suffix.lower() not in AUDIO_SUFFIXES or any(part.startswith(".") for part in relativeParts):
            continue
        soundFiles.setdefault(path.stem, path)
        filesByName.setdefault(path.name, path)

    for configFile in [*sorted(machinePath.glob("config/*.yaml")), *sorted(machinePath.glob("modes/*/config/*.yaml"))]:
        configData = readConfig(configFile)
        soundsSection = configData.get("sounds") if configData is not None else None
        if not isinstance(soundsSection, dict):
            continue
        for soundName, soundConfig in soundsSection.items():
            fileName = soundConfig.get("file") if isinstance(soundConfig, dict) else None
            if fileName and Path(str(fileName)).name in filesByName:
                soundFiles[str(soundName)] = filesByName[Path(str(fileName)).name]
    return soundFiles


# The following returns the machine's config files with their contents, in the order MPF merges them: it starts from
# config/config.yaml and follows its config: list of included files, with an included file overriding the file that
# includes it and later files overriding earlier ones.  Without config/config.yaml every config file is used, by name
def machineConfigs(machinePath: Path, configName: str = "config.yaml") -> list[tuple[Path, dict]]:
    return _configsFrom(machinePath / "config", configName)


# The following returns each mode's config files with their contents, in the same order, starting from the mode's
# own config file, modes/<mode>/config/<mode>.yaml
def modeConfigs(machinePath: Path) -> list[tuple[Path, dict]]:
    configs: list[tuple[Path, dict]] = []
    for modeFolder in sorted(path for path in (machinePath / "modes").glob("*") if path.is_dir()):
        configs += _configsFrom(modeFolder / "config", f"{modeFolder.name}.yaml")
    return configs


def _configsFrom(configFolder: Path, mainConfigName: str) -> list[tuple[Path, dict]]:
    mainConfig = configFolder / mainConfigName
    if mainConfig.is_file():
        return _configsInMergeOrder(mainConfig, set())
    configs: list[tuple[Path, dict]] = []
    for configFile in sorted(configFolder.glob("*.yaml")):
        configs += _configsInMergeOrder(configFile, set(), followIncludes=False)
    return configs


# The following are the config sections the show viewer uses, which are the only ones read from config files
CONFIG_SECTIONS = {"config", "named_colors", "shows", "sounds", "lights", "light_stripes", "light_rings"}

# The following keeps yaml files already read, by how they were read and the file's path, modification time and size,
# so a file is only read again when it changes
_YAML_CACHE: dict[tuple[str, str, int, int], Any] = {}


# The following reads a yaml file as text through the cache, raising the error again if it could not be read
def _readYAMLCached(filePath: Path, readAs: str) -> Any:
    fileStat = filePath.stat()
    cacheKey = (readAs, str(filePath), fileStat.st_mtime_ns, fileStat.st_size)
    if cacheKey not in _YAML_CACHE:
        try:
            if readAs == "config":
                _YAML_CACHE[cacheKey] = yamlInterfacer.loadYAMLTextSections(filePath, CONFIG_SECTIONS)
            else:
                _YAML_CACHE[cacheKey] = yamlInterfacer.loadYAMLText(filePath)
        except Exception as error:  # the error is kept so an unreadable file is reported each time, not read again
            _YAML_CACHE[cacheKey] = error
    cachedData = _YAML_CACHE[cacheKey]
    if isinstance(cachedData, Exception):
        raise cachedData
    return cachedData


# The following reads the sections of a config file the show viewer uses, or returns None if it cannot be read
def readConfig(configFile: Path) -> dict | None:
    try:
        configData = _readYAMLCached(configFile, "config")
    except Exception:  # a config that cannot be read is left out
        return None
    return configData if isinstance(configData, dict) else None


def _configsInMergeOrder(configFile: Path, visited: set[Path], followIncludes: bool = True) -> list[tuple[Path, dict]]:
    if configFile in visited or not configFile.is_file():
        return []
    visited.add(configFile)
    configData = readConfig(configFile)
    if configData is None:
        return []
    configs = [(configFile, configData)]
    includes = configData.get("config") if followIncludes else None
    if isinstance(includes, str):
        includes = includes.split(",")
    for include in includes if isinstance(includes, list) else []:
        configs += _configsInMergeOrder(configFile.parent / str(include).strip(), visited)
    return configs


# The following reads the colors a machine names in the named_colors: section of its config, e.g. color_grunt: FF6611
def loadNamedColors(machinePath: Path, configName: str = "config.yaml") -> dict[str, tuple[int, int, int]]:
    colorTexts: dict[str, str] = {}
    for _configFile, configData in machineConfigs(machinePath, configName):
        colorsSection = configData.get("named_colors")
        if isinstance(colorsSection, dict):
            colorTexts.update({str(name): str(color) for name, color in colorsSection.items()})

    namedColors: dict[str, tuple[int, int, int]] = {}
    for name, colorText in colorTexts.items():
        rgb, kind = resolveColor(colorText, namedColors)
        if kind == "color" and rgb is not None:
            namedColors[name.lower()] = rgb
    return namedColors


# The following reads the shows defined in the shows: sections of the machine's and its modes' configs, where a show
# defined again by a later machine config file replaces the earlier one, as MPF merges them
def loadConfigShows(machinePath: Path) -> list[MPFShow]:
    shows: dict[str, MPFShow] = {}
    for configFile, configData in machineConfigs(machinePath) + modeConfigs(machinePath):
        showsSection = configData.get("shows")
        if isinstance(showsSection, dict):
            for showName, showData in showsSection.items():
                shows[str(showName)] = parseShow(showData, str(showName), configFile)
                shows[str(showName)].isInConfig = True
    return list(shows.values())
