"""The way effects were painted into shows before they were painted in one pass, kept to check the two agree"""

from mpfmanager.core import showEditor
from mpfmanager.core.showEffects import LightEffect, effectLightFrames
from mpfmanager.core.showManager import MPFShow


# The following paints each run of an effect's frames as a span of its own, as applyEffect once did
def applyEffectByRuns(
    show: MPFShow,
    effect: LightEffect,
    lightPositions: dict[str, tuple[float, float]],
    namedColors: dict[str, tuple[int, int, int]] | None = None,
    lightReaches: dict[str, float] | None = None,
) -> bool:
    if effect.duration <= 0 or not lightPositions:
        return False
    showEditor.extendShow(show, effect.endTime)
    fadeMs = round(effect.stepTime * 1000) if effect.smooth else 0
    changed = False
    for lightName, lights in effectLightFrames(effect, lightPositions, lightReaches).items():
        frame = 0
        while frame < len(lights):
            intensity, frameColor = lights[frame]
            runEnd = frame + 1
            while runEnd < len(lights) and (
                lights[runEnd] == lights[frame] or (not intensity and not lights[runEnd][0])
            ):
                runEnd += 1
            runStart = effect.startTime + frame * effect.stepTime
            runStop = min(effect.startTime + runEnd * effect.stepTime, effect.endTime)
            if intensity:
                setting = showEditor.paintSetting(frameColor, intensity, fadeMs, namedColors)
                changed |= showEditor.paintLight(show, lightName, runStart, runStop, setting)
            elif effect.offOutside:
                setting = showEditor.paintSetting((0, 0, 0), 100, fadeMs, namedColors)
                changed |= showEditor.paintLight(show, lightName, runStart, runStop, setting)
            frame = runEnd
    return changed
