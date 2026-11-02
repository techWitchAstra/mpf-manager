"""showEditor changes MPF shows, such as painting a light with a color over a span of time"""

#   showEditor - Responsible for changing the steps of a parsed MPF show, so
#       that the show viewer can be used to paint lights and write the show
#       back to its file
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

import copy
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mpfmanager.core.showManager import (
    NAMED_RGB_COLORS,
    LightSetting,
    MPFShow,
    ShowStep,
    formatDuration,
    lightSettingToData,
    parseLightSetting,
    parseShow,
    resolveColor,
)

# The following is how close two times are to be the same time, as MPF times are whole milliseconds
TIME_TOLERANCE = 0.0005

_TOKEN_RE = re.compile(r"\(([^)]+)\)")


# The following rounds a time to whole milliseconds, which is all MPF times can be
def _toMilliseconds(seconds: float) -> float:
    return round(seconds, 3)


# The following returns whether a light name of a step sets a light, either by its name or in a list of lights
def namesLight(lightKey: str, lightName: str) -> bool:
    if lightKey == lightName:
        return True
    if _TOKEN_RE.search(lightKey):
        return False
    return lightName in (name.strip() for name in lightKey.split(","))


# The following returns the step that starts at a time, splitting the step the time is in if it does not start there.
# The new step after the split sets nothing, as lights keep their colors until they are changed, and a fade carries
# on across the split.  It returns None for a time outside the show
def splitStepAt(show: MPFShow, atTime: float) -> ShowStep | None:
    atTime = _toMilliseconds(atTime)
    for index, step in enumerate(show.steps):
        stepEnd = step.startTime + step.duration
        if abs(step.startTime - atTime) <= TIME_TOLERANCE:
            return step
        if step.startTime < atTime < stepEnd - TIME_TOLERANCE:
            # A step that holds until it is advanced keeps holding after the split, as that is where it waits
            newStep = ShowStep(0, atTime, stepEnd - atTime, step.isHold)
            step.duration = atTime - step.startTime
            step.isHold = False
            show.steps.insert(index + 1, newStep)
            return newStep
    return None


# The following returns the setting a show's own steps last gave a light before a time, or None if they did not
def settingBefore(show: MPFShow, lightName: str, atTime: float) -> LightSetting | None:
    setting = None
    for step in show.steps:
        if step.startTime >= atTime - TIME_TOLERANCE:
            break
        for lightKey, lightSetting in step.lights.items():
            if namesLight(lightKey, lightName):
                setting = lightSetting
    return setting


# The following takes a light out of a step, taking it out of a list of lights it is in rather than the whole list
def removeLight(step: ShowStep, lightName: str) -> None:
    lights: dict[str, LightSetting] = {}
    lightSections: dict[str, str] = {}
    for lightKey, setting in step.lights.items():
        newKey = lightKey
        if namesLight(lightKey, lightName):
            if lightKey == lightName:
                continue
            newKey = ", ".join(name.strip() for name in lightKey.split(",") if name.strip() != lightName)
        lights[newKey] = setting
        if lightKey in step.lightSections:
            lightSections[newKey] = step.lightSections[lightKey]
    step.lights = lights
    step.lightSections = lightSections


# The following returns whether a step does nothing, so it can be joined to the step before it
def _isEmpty(step: ShowStep) -> bool:
    return not (step.lights or step.shows or step.sounds or step.otherData or step.otherSections)


# The following joins steps added by editing that no longer do anything into the step before them.  Steps read from
# the show's file are kept, as they may be there on purpose, such as a pause
def joinEmptySteps(show: MPFShow) -> None:
    steps: list[ShowStep] = []
    for step in show.steps:
        if steps and step.stepNumber == 0 and _isEmpty(step) and not steps[-1].isHold:
            steps[-1].duration = step.startTime + step.duration - steps[-1].startTime
            steps[-1].isHold = step.isHold
            continue
        steps.append(step)
    show.steps = steps


# The following paints a light with a setting from one time to another, or with no setting to take out what the
# show's own steps set it to there, so it carries on with what it had before.  Afterwards the light goes back to what
# it was, or is stopped if the show had not set it, so any show below it is seen again.  It returns whether the show
# was changed, which it is not for a time outside the show
def paintLight(show: MPFShow, lightName: str, startTime: float, endTime: float, setting: LightSetting | None) -> bool:
    startTime = _toMilliseconds(max(startTime, 0.0))
    endTime = _toMilliseconds(min(endTime, show.totalDuration))
    if endTime - startTime < TIME_TOLERANCE:
        return False

    settingAfter = settingBefore(show, lightName, endTime)
    startStep = splitStepAt(show, startTime)
    endStep = splitStepAt(show, endTime)
    if startStep is None:
        return False
    for step in show.steps:
        if startTime - TIME_TOLERANCE <= step.startTime < endTime - TIME_TOLERANCE:
            removeLight(step, lightName)
    if setting is not None:
        startStep.lights[lightName] = setting

    # The light goes back to what it was after the span, unless the step there sets it anyway
    if endStep is not None and not any(namesLight(lightKey, lightName) for lightKey in endStep.lights):
        settingNow = settingBefore(show, lightName, endTime)
        if settingNow is not settingAfter:
            restored = parseLightSetting("stop") if settingAfter is None else copy.copy(settingAfter)
            # The color it goes back to is set straight away, rather than fading into it again
            restored.fadeText, restored.fadeMs = "", 0
            endStep.lights[lightName] = restored
    joinEmptySteps(show)
    return True


# The following works out the light value a color and intensity are written as, using the project's color names or
# MPF's for a color that has one, e.g. red%50, or a hex value such as ff8000
def colorValue(
    rgb: tuple[int, int, int], intensity: int = 100, namedColors: dict[str, tuple[int, int, int]] | None = None
) -> str:
    colorName = next((name for name, namedRGB in (namedColors or {}).items() if namedRGB == rgb), None)
    colorName = colorName or next((name for name, namedRGB in NAMED_RGB_COLORS.items() if namedRGB == rgb), None)
    value = colorName or "{:02x}{:02x}{:02x}".format(*rgb)
    intensity = min(max(int(intensity), 0), 100)
    return value if intensity == 100 else f"{value}%{intensity}"


# The following makes the setting a light is painted with, from a color, an intensity and a fade into it
def paintSetting(
    rgb: tuple[int, int, int],
    intensity: int = 100,
    fadeMs: int = 0,
    namedColors: dict[str, tuple[int, int, int]] | None = None,
) -> LightSetting:
    value = colorValue(rgb, intensity, namedColors)
    setting = parseLightSetting(f"{value}-f{fadeMs}ms" if fadeMs > 0 else value)
    # The color is worked out with the project's colors too, as the setting was read without them
    setting.rgb, setting.kind = resolveColor(setting.value, namedColors)
    return setting


# The following works out the color and intensity of a light value, e.g. red%50 is red at 50, or None for a value
# that is not a color, such as a show token or stop
def splitColorValue(
    value: str, namedColors: dict[str, tuple[int, int, int]] | None = None
) -> tuple[tuple[int, int, int], int] | None:
    colorText, _, intensityText = value.partition("%")
    rgb, kind = resolveColor(colorText, namedColors)
    if kind != "color" or rgb is None:
        return None
    try:
        intensity = int(intensityText) if intensityText else 100
    except ValueError:
        return None
    return rgb, min(max(intensity, 0), 100)


# The following makes the show last until a time, by making its last step longer, so something can be pasted past
# its end.  A show whose last step holds until it is advanced cannot be made longer, so it returns whether it was
def extendShow(show: MPFShow, endTime: float) -> bool:
    endTime = _toMilliseconds(endTime)
    if endTime <= show.totalDuration + TIME_TOLERANCE:
        return True
    if not show.steps:
        show.steps.append(ShowStep(0, 0.0, endTime))
        return True
    if show.steps[-1].isHold:
        return False
    show.steps[-1].duration = _toMilliseconds(endTime - show.steps[-1].startTime)
    return True


# The following are the patterns a chase can run in: along the lights, back along them, along and back again, or
# filling them one at a time
CHASE_FORWARD = "forward"
CHASE_REVERSE = "reverse"
CHASE_BOUNCE = "bounce"
CHASE_FILL = "fill"
CHASE_PATTERNS = (CHASE_FORWARD, CHASE_REVERSE, CHASE_BOUNCE, CHASE_FILL)


# The following returns the lights lit in one frame of a chase, by their place in the chase
def chaseFrame(frame: int, lightCount: int, pattern: str = CHASE_FORWARD, width: int = 1) -> set[int]:
    if lightCount <= 0:
        return set()
    if pattern == CHASE_FILL:
        return set(range(frame % lightCount + 1))

    def head(atFrame: int) -> int:
        if pattern == CHASE_REVERSE:
            return lightCount - 1 - atFrame % lightCount
        if pattern == CHASE_BOUNCE and lightCount > 1:
            period = 2 * lightCount - 2
            position = atFrame % period
            return position if position < lightCount else period - position
        return atFrame % lightCount

    # The lights lit are where the chase is and where it was in the frames before, for a chase wider than one light
    return {head(frame - back) for back in range(max(width, 1)) if frame - back >= 0}


# The following paints a chase over lights in their order, from one time to another, moving on every stepTime.  Lights
# are painted with the setting while lit and with the between setting while not, or left as they were if there is none
def chaseLights(
    show: MPFShow,
    lightNames: list[str],
    startTime: float,
    endTime: float,
    setting: LightSetting,
    stepTime: float,
    pattern: str = CHASE_FORWARD,
    width: int = 1,
    betweenSetting: LightSetting | None = None,
) -> bool:
    startTime = _toMilliseconds(max(startTime, 0.0))
    endTime = _toMilliseconds(min(endTime, show.totalDuration))
    stepTime = _toMilliseconds(stepTime)
    if not lightNames or stepTime < 0.001 or endTime - startTime < TIME_TOLERANCE:
        return False
    frameCount = math.ceil(round((endTime - startTime) / stepTime, 6))
    litFrames = [chaseFrame(frame, len(lightNames), pattern, width) for frame in range(frameCount)]

    changed = False
    for place, lightName in enumerate(lightNames):
        # Each run of frames the light is lit, or not, is painted as one span
        frame = 0
        while frame < frameCount:
            isLit = place in litFrames[frame]
            runEnd = frame
            while runEnd < frameCount and (place in litFrames[runEnd]) == isLit:
                runEnd += 1
            runSetting = setting if isLit else betweenSetting
            if runSetting is not None:
                runStart, runStop = startTime + frame * stepTime, min(startTime + runEnd * stepTime, endTime)
                changed |= paintLight(show, lightName, runStart, runStop, copy.copy(runSetting))
            frame = runEnd
    return changed


# The following are the orders lights can be put in from where they are on the playfield, as MPF-Monitor places them
# with x from the left and y from the top
ORDER_GRID = "grid order"
LIGHT_ORDERS = (
    ORDER_GRID,
    "left to right",
    "right to left",
    "top to bottom",
    "bottom to top",
    "clockwise",
    "counterclockwise",
)


# The following orders lights from where they are on the playfield, keeping the lights that are not placed after the
# others in the order they were given.  Clockwise and counterclockwise go around the middle of the lights from the top
def orderLights(lightNames: list[str], positions: dict[str, tuple[float, float]], order: str) -> list[str]:
    placed = [name for name in lightNames if name in positions]
    unplaced = [name for name in lightNames if name not in positions]
    if order == ORDER_GRID or not placed:
        return list(lightNames)
    centerX = sum(positions[name][0] for name in placed) / len(placed)
    centerY = sum(positions[name][1] for name in placed) / len(placed)

    def angleFromTop(name: str) -> float:
        x, y = positions[name]
        # The y of the playfield is down, so the angle grows clockwise on the playfield
        return (math.atan2(y - centerY, x - centerX) + math.pi / 2) % (2 * math.pi)

    sortKeys = {
        "left to right": lambda name: positions[name][0],
        "right to left": lambda name: -positions[name][0],
        "top to bottom": lambda name: positions[name][1],
        "bottom to top": lambda name: -positions[name][1],
        "clockwise": angleFromTop,
        "counterclockwise": lambda name: -angleFromTop(name) % (2 * math.pi),
    }
    return sorted(placed, key=sortKeys[order]) + unplaced


# The following data class holds lights copied from a show: what the show's own steps set each of them to, at times
# from the start of what was copied
@dataclass
class LightClip:
    """Lights copied from a span of a show"""

    lightNames: list[str]
    duration: float
    changes: dict[str, list[tuple[float, LightSetting | None]]] = field(default_factory=dict)


# The following copies what a show's own steps set lights to from one time to another.  Each light starts with what it
# was set to at the start, or None if the show had not set it, with a fade it was part way through left out
def copyLights(show: MPFShow, lightNames: list[str], startTime: float, endTime: float) -> LightClip:
    startTime = _toMilliseconds(max(startTime, 0.0))
    endTime = _toMilliseconds(min(endTime, show.totalDuration))
    clip = LightClip(list(lightNames), max(endTime - startTime, 0.0))
    for lightName in lightNames:
        startSetting = copy.deepcopy(settingBefore(show, lightName, startTime + 2 * TIME_TOLERANCE))
        startsHere = any(
            abs(step.startTime - startTime) <= TIME_TOLERANCE and any(namesLight(key, lightName) for key in step.lights)
            for step in show.steps
        )
        if startSetting is not None and not startsHere:
            startSetting.fadeText, startSetting.fadeMs = "", 0
        changes: list[tuple[float, LightSetting | None]] = [(0.0, startSetting)]
        for step in show.steps:
            if startTime + TIME_TOLERANCE < step.startTime < endTime - TIME_TOLERANCE:
                for lightKey, setting in step.lights.items():
                    if namesLight(lightKey, lightName):
                        changes.append((_toMilliseconds(step.startTime - startTime), copy.deepcopy(setting)))
        clip.changes[lightName] = changes
    return clip


# The following pastes copied lights at a time, onto the lights they were copied from or onto other lights in the same
# order.  The show is made longer if the paste goes past its end, where it can be
def pasteLights(show: MPFShow, clip: LightClip, atTime: float, targetNames: list[str] | None = None) -> bool:
    atTime = _toMilliseconds(max(atTime, 0.0))
    if clip.duration < TIME_TOLERANCE:
        return False
    # A show that cannot be made longer has what goes past its end left out
    if not extendShow(show, atTime + clip.duration) and atTime >= show.totalDuration - TIME_TOLERANCE:
        return False
    changed = False
    for lightName, targetName in zip(clip.lightNames, targetNames or clip.lightNames, strict=False):
        changes = clip.changes.get(lightName, [])
        for index, (changeTime, setting) in enumerate(changes):
            changeEnd = changes[index + 1][0] if index + 1 < len(changes) else clip.duration
            changed |= paintLight(show, targetName, atTime + changeTime, atTime + changeEnd, copy.deepcopy(setting))
    return changed


# The following repeats lights from one time to another a number of times straight after themselves
def repeatLights(show: MPFShow, lightNames: list[str], startTime: float, endTime: float, count: int) -> bool:
    clip = copyLights(show, lightNames, startTime, endTime)
    changed = False
    for repeat in range(1, count + 1):
        changed |= pasteLights(show, clip, startTime + repeat * clip.duration)
    return changed


# The following returns the show token each of several lights or colors is given: the name alone for one, e.g.
# (light), or numbered for several, e.g. (light1) and (light2)
def _tokenNames(baseName: str, count: int) -> list[str]:
    return [baseName] if count == 1 else [f"{baseName}{number}" for number in range(1, count + 1)]


# The following makes a show that plays what lights do from one time to another, with each light as a show token, and
# each color as a show token too if asked, so the show can be played on other lights and in other colors.  It returns
# the new show and the show_tokens that play it as it was
def makeReusableShow(
    show: MPFShow,
    lightNames: list[str],
    startTime: float,
    endTime: float,
    newName: str,
    tokenizeColors: bool = True,
) -> tuple[MPFShow, dict[str, str]]:
    clip = copyLights(show, lightNames, startTime, endTime)
    lightTokens = dict(zip(lightNames, _tokenNames("light", len(lightNames)), strict=True))
    showTokens = {token: lightName for lightName, token in lightTokens.items()}

    # Each color that is set is found in the order the colors are first set, without the brightness it is set at,
    # e.g. red of red%50
    colorTexts: list[str] = []
    settingsInOrder = sorted(
        (
            (changeTime, place, setting)
            for place, changes in enumerate(clip.changes.values())
            for changeTime, setting in changes
        ),
        key=lambda change: change[:2],
    )
    for _changeTime, _place, setting in settingsInOrder:
        colorText = setting.value.partition("%")[0] if setting is not None else ""
        if setting is not None and setting.kind == "color" and colorText not in colorTexts:
            colorTexts.append(colorText)
    colorTokens = dict(zip(colorTexts, _tokenNames("color", len(colorTexts)), strict=True)) if tokenizeColors else {}
    showTokens.update({token: colorText for colorText, token in colorTokens.items()})

    # The show has a step at every time a light changes, setting the lights that change then
    changeTimes = sorted({changeTime for changes in clip.changes.values() for changeTime, _setting in changes})
    steps: list[dict] = []
    for index, changeTime in enumerate(changeTimes):
        stepEnd = changeTimes[index + 1] if index + 1 < len(changeTimes) else clip.duration
        lights: dict[str, object] = {}
        for lightName, changes in clip.changes.items():
            for settingTime, setting in changes:
                if settingTime != changeTime or setting is None:
                    continue
                newSetting = copy.deepcopy(setting)
                colorText, percent, brightness = setting.value.partition("%")
                if setting.kind == "color" and colorText in colorTokens:
                    newSetting.value = f"({colorTokens[colorText]})" + percent + brightness
                lights[f"({lightTokens[lightName]})"] = lightSettingToData(newSetting)
        steps.append({"duration": formatDuration(stepEnd - changeTime), **({"lights": lights} if lights else {})})
    return parseShow(steps, newName), showTokens


# The following takes what lights do from one time to another out of a show and plays a show there instead, once,
# with show tokens, such as a show made by makeReusableShow
def playShowInPlace(
    show: MPFShow, lightNames: list[str], startTime: float, endTime: float, showName: str, showTokens: dict[str, str]
) -> bool:
    for lightName in lightNames:
        paintLight(show, lightName, startTime, endTime, None)
    startStep = splitStepAt(show, startTime)
    if startStep is None:
        return False
    startStep.shows[showName] = {"loops": "0", "show_tokens": dict(showTokens)}
    return True


# The following keeps the steps of shows before each change, so changes can be undone and redone
class EditHistory:
    def __init__(self, limit: int = 200):
        self.limit = limit
        self.undoSteps: list[list[ShowStep]] = []
        self.redoSteps: list[list[ShowStep]] = []

    # The following remembers a show's steps before it is changed
    def remember(self, show: MPFShow) -> None:
        self.record(copy.deepcopy(show.steps))

    # The following remembers steps copied before a change, for a change that is only kept if it changed something
    def record(self, steps: list[ShowStep]) -> None:
        self.undoSteps.append(steps)
        del self.undoSteps[: -self.limit]
        self.redoSteps.clear()

    @property
    def canUndo(self) -> bool:
        return bool(self.undoSteps)

    @property
    def canRedo(self) -> bool:
        return bool(self.redoSteps)

    def undo(self, show: MPFShow) -> bool:
        if not self.undoSteps:
            return False
        self.redoSteps.append(show.steps)
        show.steps = self.undoSteps.pop()
        return True

    def redo(self, show: MPFShow) -> bool:
        if not self.redoSteps:
            return False
        self.undoSteps.append(show.steps)
        show.steps = self.redoSteps.pop()
        return True

    def clear(self) -> None:
        self.undoSteps.clear()
        self.redoSteps.clear()


# The following makes a new, blank show: one step lasting the show's length, which its lights and sounds can be put in
def newShow(showName: str, duration: float, sourcePath: Path | None = None) -> MPFShow:
    return MPFShow(showName, sourcePath, [ShowStep(1, 0.0, _toMilliseconds(max(duration, 0.001)))])


# The following are the settings a sound is played with in a show, with the values MPF uses when they are not given
SOUND_DEFAULTS: dict[str, Any] = {"action": "play", "volume": 1.0, "loops": 0, "start_at": 0.0, "fade_in": 0.0}


# The following makes a show play a sound at a time, in the step starting then, with its settings written only where
# they are not MPF's own.  A sound played at the show's end makes the show last until a moment after it, so it starts
# within the show.  It returns whether the show was changed
def addSound(show: MPFShow, soundName: str, atTime: float, settings: dict[str, Any] | None = None) -> bool:
    soundName = soundName.strip()
    if not soundName or atTime < 0:
        return False
    atTime = _toMilliseconds(atTime)
    if atTime >= show.totalDuration - TIME_TOLERANCE and not extendShow(show, atTime + 1.0):
        return False
    step = splitStepAt(show, atTime)
    if step is None:
        return False
    written = {
        key: value
        for key, value in (settings or {}).items()
        if key != "action" and value != SOUND_DEFAULTS.get(key) and value is not None
    }
    step.sounds[soundName] = {"action": "play", **written}
    return True


# The following returns the sounds the show's own steps play, as when each starts and its name
def soundEntries(show: MPFShow) -> list[tuple[float, str]]:
    return [(step.startTime, soundName) for step in show.steps for soundName in step.sounds]


# The following takes a sound out of the step starting at a time, joining the step to the one before when it was
# added by editing and now does nothing.  It returns whether the show was changed
def removeSound(show: MPFShow, atTime: float, soundName: str) -> bool:
    for step in show.steps:
        if abs(step.startTime - atTime) <= TIME_TOLERANCE and soundName in step.sounds:
            del step.sounds[soundName]
            joinEmptySteps(show)
            return True
    return False


# The following takes a light, light tag or show token out of every step of a show, taking it out of lists of lights
# rather than the whole list.  Steps added by editing that are left doing nothing are joined to the step before.  It
# returns whether the show set the light anywhere
def removeLightFromShow(show: MPFShow, lightName: str) -> bool:
    changed = False
    for step in show.steps:
        if any(namesLight(lightKey, lightName) for lightKey in step.lights):
            removeLight(step, lightName)
            changed = True
    if changed:
        joinEmptySteps(show)
    return changed
