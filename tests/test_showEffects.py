import copy
import math

import pytest

from mpfmanager.core import showEffects, showManager
from mpfmanager.core.showEffects import LightEffect, ShapePlace
from mpfmanager.core.showManager import parseShow


def _show(seconds: int = 2):
    show = parseShow([{"duration": "1s", "lights": {"l_x": "blue"}} for _ in range(seconds)], "effects")
    show.buildTimeline({}, {})
    return show


def _colors(show, light, times):
    show.buildTimeline({}, {})
    return [show.channelState(light, atTime).rgb for atTime in times]


def test_shapesCoverPoints():
    place = ShapePlace(0.5, 0.5, 0.4, 0.2)
    assert showEffects.shapeCoverage("rectangle", place, 0.5, 0.5, 0.04, 0) == 1.0
    assert showEffects.shapeCoverage("rectangle", place, 0.69, 0.59, 0.04, 0) == 1.0
    assert showEffects.shapeCoverage("rectangle", place, 0.75, 0.5, 0.04, 0) == 0.0
    # A soft edge lights points near it more dimly
    assert showEffects.shapeCoverage("rectangle", place, 0.75, 0.5, 0.04, 0.1) == pytest.approx(0.5)

    # Turning the shape turns what it covers
    turned = ShapePlace(0.5, 0.5, 0.4, 0.02, 90)
    assert showEffects.shapeCoverage("rectangle", turned, 0.5, 0.68, 0.04, 0) == 1.0
    assert showEffects.shapeCoverage("rectangle", turned, 0.68, 0.5, 0.04, 0) == 0.0

    # Ellipses are round, rings only light their band, and lines are as thick as their thickness
    circle = ShapePlace(0.5, 0.5, 0.4, 0.4)
    assert showEffects.shapeCoverage("ellipse", circle, 0.5, 0.69, 0.04, 0) == 1.0
    assert showEffects.shapeCoverage("ellipse", circle, 0.66, 0.66, 0.04, 0) == 0.0
    assert showEffects.shapeCoverage("ring", circle, 0.5, 0.5, 0.04, 0) == 0.0
    assert showEffects.shapeCoverage("ring", circle, 0.5, 0.71, 0.04, 0) == 1.0
    line = ShapePlace(0.5, 0.5, 0.6, 0.5)
    assert showEffects.shapeCoverage("line", line, 0.7, 0.51, 0.04, 0) == 1.0
    assert showEffects.shapeCoverage("line", line, 0.7, 0.6, 0.04, 0) == 0.0


def test_effectsMoveSpinGrowAndChangeColor():
    effect = LightEffect(
        "sweep",
        "rectangle",
        ShapePlace(0.5, 0.9, 1.0, 0.1),
        rgb=(255, 0, 0),
        endRGB=(0, 0, 255),
        startTime=1.0,
        duration=2.0,
        moveAngle=90,
        moveDistance=0.8,
        spin=90,
        endScale=2.0,
    )
    halfway = effect.placeAt(2.0)
    assert (halfway.centerX, halfway.centerY) == pytest.approx((0.5, 0.5))
    assert (halfway.width, halfway.height, halfway.rotation) == pytest.approx((1.5, 0.15, 45))
    assert effect.placeAt(0.0).centerY == pytest.approx(0.9)
    assert effect.placeAt(5.0).centerY == pytest.approx(0.1)
    assert effect.colorAt(2.0) == (128, 0, 128)

    # Repeats run the movement again, bouncing runs it back, and easing starts and ends it gently
    effect.repeats, effect.spin, effect.endScale = 2, 0, 1
    assert effect.progressAt(1.5) == pytest.approx(0.5)
    assert effect.progressAt(2.5) == pytest.approx(0.5)
    effect.repeats, effect.bounce = 1, True
    assert effect.progressAt(1.5) == pytest.approx(0.5)
    assert effect.progressAt(2.0) == pytest.approx(1.0)
    assert effect.progressAt(2.5) == pytest.approx(0.5)
    effect.bounce, effect.easing = False, showEffects.EASING_SMOOTH
    assert effect.progressAt(1.5) == pytest.approx(0.15625)


def test_applyingAnEffectPaintsTheLightsItPasses():
    show = _show()
    # A bar sweeping up the playfield lights the lower light first, then the upper one
    effect = LightEffect(
        "sweep",
        "rectangle",
        ShapePlace(0.5, 0.95, 1.0, 0.1),
        rgb=(255, 0, 0),
        duration=1.0,
        stepTime=0.1,
        moveDistance=0.9,
    )
    positions = {"l_low": (0.5, 0.9), "l_high": (0.5, 0.15), "l_x": (0.9, 0.5), "l_away": (5.0, 5.0)}
    frames = showEffects.effectFrames(effect, positions)
    assert set(frames) == {"l_low", "l_high", "l_x"}
    assert frames["l_low"][0] == 100 and frames["l_high"][0] == 0 and frames["l_high"][-1] == 100

    assert showEffects.applyEffect(show, effect, positions)
    assert _colors(show, "l_low", [0.05, 0.95]) == [(255, 0, 0), None]
    assert _colors(show, "l_high", [0.05, 0.95]) == [None, (255, 0, 0)]
    # A light the show sets goes back to its color where the effect is not over it
    assert _colors(show, "l_x", [0.05, 0.55, 1.5]) == [(0, 0, 255), (255, 0, 0), (0, 0, 255)]
    assert not showEffects.applyEffect(show, effect, {})


def test_effectsCanTurnLightsOffAndFade():
    show = _show()
    effect = LightEffect(
        "pulse",
        "ellipse",
        ShapePlace(0.5, 0.5, 0.2, 0.2),
        rgb=(0, 255, 0),
        duration=1.0,
        stepTime=0.5,
        offOutside=True,
        smooth=True,
        endScale=0.1,
    )
    assert showEffects.applyEffect(show, effect, {"l_x": (0.58, 0.5)})
    settings = [step.lights.get("l_x") for step in show.steps]
    assert (settings[0].value, settings[0].fadeMs) == ("lime", 500)
    assert (settings[1].value, settings[1].fadeMs) == ("off", 500)


def test_effectsGoPastTheEndOfTheShow():
    show = _show(1)
    effect = LightEffect("long", "rectangle", ShapePlace(0.5, 0.5, 1, 1), duration=3.0, stepTime=1.0)
    assert showEffects.applyEffect(show, effect, {"l_x": (0.5, 0.5)})
    assert show.totalDuration == pytest.approx(3.0)


def test_applyingAgainReplacesTheEffect():
    show = _show()
    positions = {"l_a": (0.2, 0.5), "l_b": (0.8, 0.5)}
    effect = LightEffect("block", "rectangle", ShapePlace(0.2, 0.5, 0.2, 0.2), rgb=(255, 0, 0), duration=1.0)
    assert showEffects.applyEffectInPlace(show, effect, positions)
    assert _colors(show, "l_a", [0.5]) == [(255, 0, 0)]

    # Moving the shape and applying it again takes out what it painted before
    effect.place.centerX = 0.8
    assert showEffects.applyEffectInPlace(show, effect, positions)
    assert _colors(show, "l_a", [0.5]) == [None]
    assert _colors(show, "l_b", [0.5]) == [(255, 0, 0)]

    # Once the show is changed some other way, the effect is applied on top instead
    show.steps[0].lights["l_c"] = show.steps[0].lights["l_b"]
    effect.place.centerX = 0.2
    assert showEffects.applyEffectInPlace(show, effect, positions)
    assert _colors(show, "l_a", [0.5]) == [(255, 0, 0)] and _colors(show, "l_b", [0.5]) == [(255, 0, 0)]


def test_effectsAreDrawnByDragging():
    line = showEffects.effectFromDrag("line", "line", 0.1, 0.1, 0.4, 0.5, rgb=(1, 2, 3))
    assert (line.place.centerX, line.place.centerY, line.place.width) == pytest.approx((0.25, 0.3, 0.5))
    assert line.place.rotation == pytest.approx(53.130102)
    assert line.rgb == (1, 2, 3)
    box = showEffects.effectFromDrag("box", "rectangle", 0.4, 0.5, 0.1, 0.1)
    assert (box.place.width, box.place.height, box.place.rotation) == pytest.approx((0.3, 0.4, 0))


def test_pinwheelsLightTheirBlades():
    place = ShapePlace(0.5, 0.5, 0.8, 0.8)

    def covered(x, y, **settings):
        return showEffects.shapeCoverage("pinwheel", place, x, y, 0.04, 0, **settings)

    # Four blades, each filling half its quarter, start along the right and go round
    assert covered(0.7, 0.51) == 1.0
    assert covered(0.7, 0.45) == 0.0
    assert covered(0.49, 0.7) == 1.0
    assert covered(0.51, 0.7) == 0.0
    assert covered(0.95, 0.5) == 0.0
    # One thin blade is a radar sweep, and blades filling all of the pinwheel light all of it
    assert covered(0.49, 0.7, arms=1, bladeFill=0.1) == 0.0
    assert covered(0.7, 0.51, arms=1, bladeFill=0.1) == 1.0
    assert covered(0.3, 0.45, arms=3, bladeFill=1.0) == 1.0
    # A soft edge lights points just past a blade more dimly
    assert 0 < showEffects.shapeCoverage("pinwheel", place, 0.7, 0.48, 0.04, 0.05) < 1


def test_spiralsWindOutFromTheirCenter():
    place = ShapePlace(0.5, 0.5, 1.0, 1.0)

    def armCrossing(rotation: float) -> float:
        turned = ShapePlace(0.5, 0.5, 1.0, 1.0, rotation)
        radii = [step / 400 for step in range(40, 160)]
        crossings = [
            radius
            for radius in radii
            if showEffects.shapeCoverage("spiral", turned, 0.5 + radius, 0.5, 0.02, 0, arms=1, turns=2) == 1.0
        ]
        assert crossings and max(crossings) - min(crossings) < 0.05
        return sum(crossings) / len(crossings)

    # One arm winding twice crosses the line to the right of the center halfway out, besides at the center
    assert armCrossing(0) == pytest.approx(0.25, abs=0.01)
    # Turning the spiral forwards draws the arm in towards the center, as the Spiral in preset does
    assert armCrossing(45) == pytest.approx(0.21875, abs=0.01)
    assert showEffects.shapeCoverage("spiral", place, 0.5, 0.5, 0.04, 0) == 1.0
    assert showEffects.shapeCoverage("spiral", place, 1.2, 0.5, 0.04, 0) == 0.0


def test_presetsGiveEffectsPatterns():
    effect = showEffects.effectFromDrag("line", "line", 0.1, 0.5, 0.9, 0.5, rgb=(1, 2, 3), duration=2.0)
    showEffects.applyPreset(effect, "Radar sweep")
    assert (effect.shape, effect.arms, effect.spin) == ("pinwheel", 1, 360.0)
    # Its place, color and timing stay, and a line becomes as tall as it is wide
    assert (effect.place.width, effect.place.height) == pytest.approx((0.8, 0.8))
    assert (effect.rgb, effect.duration) == ((1, 2, 3), 2.0)
    for presetName in showEffects.EFFECT_PRESETS:
        showEffects.applyPreset(effect, presetName)
        assert effect.shape in showEffects.SHAPES
    groups = showEffects.presetGroups()
    assert list(groups) == ["Pinwheels", "Spirals", "Rainbows", "Starfields"]
    assert "Radar sweep" in groups["Pinwheels"] and "Rainbow pinwheel" in groups["Rainbows"]
    assert sorted(name for names in groups.values() for name in names) == sorted(showEffects.EFFECT_PRESETS)


def test_lightsAreLitWhenTheShapeReachesThem():
    show = _show()
    # The bar's edge passes just short of the light's middle, but covers part of the light
    effect = LightEffect("bar", "rectangle", ShapePlace(0.5, 0.5, 1.0, 0.1), rgb=(255, 0, 0), duration=1.0)
    positions = {"l_big": (0.5, 0.57), "l_small": (0.5, 0.57)}
    frames = showEffects.effectFrames(effect, positions, {"l_big": 0.03, "l_small": 0.01})
    assert set(frames) == {"l_big"}
    assert showEffects.applyEffect(show, effect, positions, None, {"l_big": 0.03})
    assert _colors(show, "l_big", [0.5]) == [(255, 0, 0)]
    assert _colors(show, "l_small", [0.5]) == [None]


def test_rainbowsColorEffects():
    effect = LightEffect("rainbow", "ellipse", ShapePlace(0.5, 0.5, 0.8, 0.8), rgb=(255, 0, 0), duration=1.0)
    place = effect.placeAt(0)
    assert effect.colorAtPoint(0, place, 0.3, 0.3) == (255, 0, 0)

    # Round the middle, the rainbow starts from the effect's hue to the right and goes round
    effect.colorMode = showEffects.COLOR_RAINBOW_ROUND
    assert effect.colorAtPoint(0, place, 0.8, 0.5) == (255, 0, 0)
    assert effect.colorAtPoint(0, place, 0.5, 0.8) == (128, 255, 0)
    assert effect.colorAtPoint(0, place, 0.2, 0.5) == (0, 255, 255)
    # Out from the middle, two rainbows fit between the middle and the edge
    effect.colorMode, effect.rainbowBands = showEffects.COLOR_RAINBOW_OUTWARD, 2.0
    assert effect.colorAtPoint(0, place, 0.5, 0.5) == effect.colorAtPoint(0, place, 0.7, 0.5) == (255, 0, 0)
    assert effect.colorAtPoint(0, place, 0.6, 0.5) == (0, 255, 255)
    # Across, from one side to the other, with its colors flowing over the effect
    effect.colorMode, effect.rainbowBands, effect.rainbowCycles = showEffects.COLOR_RAINBOW_ACROSS, 1.0, 1.0
    assert effect.colorAtPoint(0, place, 0.1, 0.5) == (255, 0, 0)
    assert effect.colorAtPoint(0.5, effect.placeAt(0.5), 0.1, 0.5) == (0, 255, 255)
    # Rainbows are painted in steps of hue, and lit lights get the rainbow's color
    assert effect.lightAt(0, 0.5, 0.5) == (100, (0, 255, 255))
    assert effect.lightAt(0, 0.95, 0.5)[0] == 0


def test_applyingARainbowPaintsEachLightItsColor():
    show = _show()
    effect = LightEffect(
        "wheel",
        "ellipse",
        ShapePlace(0.5, 0.5, 0.8, 0.8),
        rgb=(255, 0, 0),
        duration=1.0,
        stepTime=0.5,
        colorMode=showEffects.COLOR_RAINBOW_ROUND,
        spin=180,
    )
    positions = {"l_right": (0.8, 0.5), "l_left": (0.2, 0.5)}
    assert showEffects.applyEffect(show, effect, positions)
    # Halfway through, the wheel has turned a quarter of the way round, so the light on the right is three quarters
    # of the way round the rainbow
    assert _colors(show, "l_right", [0.1, 0.6]) == [(255, 0, 0), (128, 0, 255)]
    assert _colors(show, "l_left", [0.1]) == [(0, 255, 255)]


def _starfield(**settings) -> LightEffect:
    return LightEffect("stars", "starfield", ShapePlace(0.5, 0.5, 0.4, 0.4), duration=2.0, **settings)


def test_starfieldsScatterStars():
    effect = _starfield(starDensity=0.5)
    stars = effect.stars()
    # Half a star in each square a tenth wide, over a field 0.4 by 0.4, is 8 stars, the same ones each time
    assert len(stars) == 8 and effect.stars() is stars
    assert all(-0.5 <= star.fieldX < 0.5 and -0.5 <= star.fieldY < 0.5 for star in stars)
    assert [star.fieldX for star in _starfield(starDensity=0.5).stars()] == [star.fieldX for star in stars]
    assert [star.fieldX for star in _starfield(starDensity=0.5, starSeed=2).stars()] != [star.fieldX for star in stars]
    assert len(_starfield(starDensity=1000).stars()) == showEffects.MAX_STARS
    assert _starfield(starDensity=0).stars() == []


def test_starsMove():
    still = _starfield(starMotion=showEffects.STARS_STILL)
    assert [(star.x, star.y) for star in still.starsAt(0)] == [(star.x, star.y) for star in still.starsAt(1)]

    # Drifting stars move the way they drift, and come back in on the other side of the field
    drift = _starfield(starMotion=showEffects.STARS_DRIFT, starAngle=0, starSpeed=0.1)
    before, after = drift.starsAt(0), drift.starsAt(1)
    for start, end in zip(before, after, strict=True):
        assert end.y == pytest.approx(start.y)
        assert (end.x - start.x) % 0.4 == pytest.approx(0.1)
        assert -0.2 <= end.x < 0.2
    upward = _starfield(starMotion=showEffects.STARS_DRIFT, starAngle=90, starSpeed=0.1)
    start, end = upward.starsAt(0)[0], upward.starsAt(0.5)[0]
    assert (start.y - end.y) % 0.4 == pytest.approx(0.05)

    # Warping stars fly out from the middle, growing as they go
    warp = _starfield(starMotion=showEffects.STARS_WARP, starSpeed=0.05)
    first, later = warp.starsAt(0)[0], warp.starsAt(0.1)[0]
    assert math.hypot(later.x, later.y) > math.hypot(first.x, first.y) and later.size > first.size
    assert all(abs(star.x) <= 0.2 and abs(star.y) <= 0.2 for star in warp.starsAt(1.3))

    # Twinkling stars dim and brighten
    twinkling = _starfield(twinkle=0.8, twinkleRate=1.0)
    brightness = [twinkling.starsAt(time / 10)[0].brightness for time in range(10)]
    assert min(brightness) == pytest.approx(0.2, abs=0.05) and max(brightness) == pytest.approx(1.0, abs=0.05)
    assert all(star.brightness == 1.0 for star in _starfield().starsAt(0.3))


@pytest.mark.parametrize("starShape", showEffects.STAR_SHAPES)
def test_starShapes(starShape):
    # A star covers its middle, its points, and not past its size
    assert showEffects.starDistance(starShape, 0, 0, 0.1) <= 0
    assert showEffects.starDistance(starShape, 0.049, 0, 0.1) <= 0.0001
    assert showEffects.starDistance(starShape, 0.06, 0, 0.1) > 0
    # Between its points, a diamond, cross and sparkle cover less than a dot
    inBetween = showEffects.starDistance(starShape, 0.03, 0.03, 0.1)
    assert (inBetween < 0) == (starShape == showEffects.STAR_DOT)


def test_starfieldsLightTheLightsUnderTheirStars():
    effect = _starfield(starMotion=showEffects.STARS_STILL, starSize=0.06, rgb=(0, 0, 255))
    star = effect.starsAt(0)[0]
    starX, starY = 0.5 + star.x, 0.5 + star.y
    assert effect.lightAt(0, starX, starY) == (100, (0, 0, 255))
    assert effect.lightAt(0, 2.0, 2.0)[0] == 0
    # Each star can be its own color, and a twinkling star lights its lights more dimly
    effect.starColoring = showEffects.STARS_RANDOM_COLORS
    assert effect.lightAt(0, starX, starY)[1] == showEffects._hueRGB(star.star.hue)
    effect.twinkle = 1.0
    dimmest = min(effect.lightAt(time / 20, starX, starY)[0] for time in range(20))
    assert dimmest < 30

    show = _show()
    assert showEffects.applyEffect(show, effect, {"l_star": (starX, starY), "l_empty": (2.0, 2.0)})
    assert "l_empty" not in {name for step in show.steps for name in step.lights}


def _equivalenceShow():
    # A show that sets the lights the effects paint, inside and around their spans, by name, in a list, and by tag
    return parseShow(
        [
            {"duration": "300ms", "lights": {"l_0_0": "blue-f100ms", "l_1_1, l_2_2": "lime", "gi": "white"}},
            {"duration": "250ms", "lights": {"l_0_1": "red"}},
            {"duration": "450ms", "lights": {"l_0_0": "off", "l_3_3": "orange%50"}},
            {"duration": "500ms", "lights": {"l_1_1": "purple", "(leds)": "(color)"}},
        ],
        "equivalence",
    )


_EQUIVALENCE_LIGHTS = {
    f"l_{row}_{column}": (0.1 + 0.2 * column, 0.2 + 0.3 * row) for row in range(5) for column in range(5)
}
_EQUIVALENCE_EFFECTS = {
    "rainbow wheel": dict(shape="ellipse", colorMode="rainbow round", spin=360.0),
    "solid sweep": dict(shape="rectangle", moveAngle=90.0, moveDistance=1.0),
    "color change": dict(shape="ring", endRGB=(0, 0, 255), endScale=2.0),
    "off outside, fading": dict(shape="pinwheel", spin=180.0, offOutside=True, smooth=True),
    "soft spiral": dict(shape="spiral", spin=-360.0, softness=0.05, colorMode="rainbow outward"),
    "starfield": dict(shape="starfield", starMotion="warp", starSpeed=0.4, starDensity=2.0, starSize=0.08, twinkle=0.5),
    "past the end": dict(shape="rectangle", startTime=1.2, duration=0.9),
}


@pytest.mark.parametrize("effectName", list(_EQUIVALENCE_EFFECTS))
def test_effectsArePaintedAsTheyWereRunByRun(effectName):
    from effectsReference import applyEffectByRuns

    settings = {"startTime": 0.1, "duration": 1.3, "stepTime": 0.05, **_EQUIVALENCE_EFFECTS[effectName]}
    shape = settings.pop("shape")
    effect = LightEffect(effectName, shape, ShapePlace(0.5, 0.8, 0.9, 1.4), rgb=(255, 0, 0), **settings)
    reaches = {name: 0.02 for name in _EQUIVALENCE_LIGHTS}
    fast, reference = _equivalenceShow(), _equivalenceShow()
    assert showEffects.applyEffect(fast, effect, _EQUIVALENCE_LIGHTS, {"grunt": (255, 102, 17)}, reaches)
    assert applyEffectByRuns(reference, effect, _EQUIVALENCE_LIGHTS, {"grunt": (255, 102, 17)}, reaches)
    assert showManager.showToData(fast) == showManager.showToData(reference)

    # Applying again in its place gives the same as painting the changed effect on the show as it was
    inPlace = _equivalenceShow()
    assert showEffects.applyEffectInPlace(inPlace, effect, _EQUIVALENCE_LIGHTS, None, reaches)
    effect.place.centerX = 0.3
    assert showEffects.applyEffectInPlace(inPlace, effect, _EQUIVALENCE_LIGHTS, None, reaches)
    moved = _equivalenceShow()
    applyEffectByRuns(moved, copy.deepcopy(effect), _EQUIVALENCE_LIGHTS, None, reaches)
    assert showManager.showToData(inPlace) == showManager.showToData(moved)


def test_effectsThatPaintNothingLeaveTheShow():
    show = _equivalenceShow()
    before = showManager.showToData(show)
    effect = LightEffect("far", "rectangle", ShapePlace(9.0, 9.0, 0.1, 0.1), duration=1.0)
    assert not showEffects.applyEffect(show, effect, _EQUIVALENCE_LIGHTS)
    assert showManager.showToData(show) == before


def test_framesAreWorkedOutOnce():
    effect = LightEffect(
        "stars",
        "starfield",
        ShapePlace(0.5, 0.5, 0.6, 0.6),
        duration=2.0,
        starMotion="drift",
        spin=90.0,
        endRGB=(0, 0, 255),
    )
    frame = effect.frameAt(0.7)
    assert frame.place == effect.placeAt(0.7) and frame.color == effect.colorAt(0.7)
    assert [(star.x, star.y) for star in frame.stars] == [(star.x, star.y) for star in effect.starsAt(0.7)]
    star = frame.stars[0]
    point = (0.5 + star.x * math.cos(math.radians(frame.place.rotation)), 0.5)
    assert effect.lightAt(0.7, *point, frame=frame) == effect.lightAt(0.7, *point)
    assert LightEffect("box", "rectangle", ShapePlace(0.5, 0.5, 1, 1)).frameAt(0).stars is None


def test_bigEffectsArePaintedQuickly():
    import time

    lights = {f"l_{row}_{column}": ((column + 0.5) / 8, (row + 0.5) / 6) for row in range(12) for column in range(8)}
    show = parseShow([{"duration": "250ms", "lights": {"l_0_0": "red"}} for _ in range(8)], "big")
    rainbow = LightEffect(
        "rainbow",
        "ellipse",
        ShapePlace(0.5, 1.0, 0.9, 1.8),
        duration=4.0,
        stepTime=0.025,
        colorMode="rainbow round",
        spin=360.0,
    )
    started = time.perf_counter()
    assert showEffects.applyEffect(show, rainbow, lights)
    assert time.perf_counter() - started < 0.6

    stars = LightEffect(
        "stars", "starfield", ShapePlace(0.5, 1.0, 0.9, 1.8), duration=4.0, stepTime=0.025, starDensity=0.5
    )
    started = time.perf_counter()
    showEffects.effectLightFrames(stars, lights)
    assert time.perf_counter() - started < 0.6
