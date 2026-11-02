"""Show effects: lighting effects made of shapes drawn on the playfield, moving over the lights in time"""

#   showEffects - Responsible for lighting effects: a shape (a line, a
#       rectangle, an ellipse, a ring, a pinwheel, a spiral or a field of
#       stars) placed on the playfield, which can move, spin, grow and change
#       color, or be colored in rainbows, over a span of the show.  The lights
#       the shape covers at each step of the effect are painted into the show
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

import bisect
import colorsys
import copy
import math
import random
from dataclasses import dataclass, field

from mpfmanager.core import showEditor
from mpfmanager.core.showManager import LightSetting, MPFShow, ShowStep, parseLightSetting

# The following are the shapes an effect can be.  A line is a long thin rectangle, drawn along the way it is dragged
SHAPE_LINE = "line"
SHAPE_RECTANGLE = "rectangle"
SHAPE_ELLIPSE = "ellipse"
SHAPE_RING = "ring"
# A pinwheel is blades fanning out from its center, and a spiral is arms winding out from its center.  Both fill the
# ellipse they are drawn in, and are usually turned with the effect's turn, so they spin
SHAPE_PINWHEEL = "pinwheel"
SHAPE_SPIRAL = "spiral"
# A starfield is stars scattered over the rectangle it is drawn in, which can drift, fly out from its middle as if
# travelling through them, and twinkle
SHAPE_STARFIELD = "starfield"
SHAPES = (SHAPE_LINE, SHAPE_RECTANGLE, SHAPE_ELLIPSE, SHAPE_RING, SHAPE_PINWHEEL, SHAPE_SPIRAL, SHAPE_STARFIELD)
# The following shapes are made of arms (blades or spiral arms), which have settings of their own
ARMED_SHAPES = (SHAPE_PINWHEEL, SHAPE_SPIRAL)

# The following are how an effect is colored: in its color, or in rainbows going round its middle, out from its
# middle, or across it from one side to the other
COLOR_SOLID = "solid"
COLOR_RAINBOW_ROUND = "rainbow round"
COLOR_RAINBOW_OUTWARD = "rainbow outward"
COLOR_RAINBOW_ACROSS = "rainbow across"
COLOR_MODES = (COLOR_SOLID, COLOR_RAINBOW_ROUND, COLOR_RAINBOW_OUTWARD, COLOR_RAINBOW_ACROSS)
# Rainbows are painted in this many hues, so lights are not given a new value for every small change in hue
RAINBOW_HUE_STEPS = 24

# The following are the shapes of stars, how they move, and how they are colored: in the effect's colors, or each in
# a color of its own
STAR_DOT = "dot"
STAR_DIAMOND = "diamond"
STAR_CROSS = "cross"
STAR_SPARKLE = "sparkle"
STAR_SHAPES = (STAR_DOT, STAR_DIAMOND, STAR_CROSS, STAR_SPARKLE)
STARS_STILL = "still"
STARS_DRIFT = "drift"
STARS_WARP = "warp"
STAR_MOTIONS = (STARS_STILL, STARS_DRIFT, STARS_WARP)
STARS_EFFECT_COLOR = "effect color"
STARS_RANDOM_COLORS = "random colors"
STAR_COLORINGS = (STARS_EFFECT_COLOR, STARS_RANDOM_COLORS)
# The most stars a starfield has, however dense, and the size of the square its density counts stars in
MAX_STARS = 400
DENSITY_AREA = 0.01

# The following are how an effect's movement runs over time: steadily, or starting and ending gently
EASING_LINEAR = "steady"
EASING_SMOOTH = "ease in and out"
EASINGS = (EASING_LINEAR, EASING_SMOOTH)

# The following is how thick a line or ring is when it is drawn, as a fraction of the playfield's width
DEFAULT_THICKNESS = 0.04

# The following are the steps of intensity an effect's soft edge is painted in, so lights are not given a new value
# for every small change in how much of them the shape covers
INTENSITY_STEP = 10


# The following is where a shape is at one moment: its center, size and rotation.  Positions and sizes are fractions
# of the playfield's width, with y measured down from the top in the same units, so circles stay round on a playfield
# that is taller than it is wide
@dataclass
class ShapePlace:
    """Where a shape is at one moment"""

    centerX: float
    centerY: float
    width: float
    height: float
    rotation: float = 0.0


# The following is one star of a starfield: where it starts, as a fraction of the field each way from its middle,
# when it twinkles, and its own hue
@dataclass
class Star:
    """One star of a starfield"""

    fieldX: float
    fieldY: float
    phase: float
    hue: float
    # How far out from the middle it starts when flying out from it, as a fraction of the way to the field's corner
    warpStart: float


# The following is one star at a moment: where it is from the field's middle, its size, and how brightly it shines
@dataclass
class StarPlace:
    """A star at one moment"""

    x: float
    y: float
    size: float
    brightness: float
    star: Star


# The following is an effect at one moment: where its shape is, its stars when it is a starfield, and its color.  It
# is worked out once for each step of the effect, rather than for each light
@dataclass
class EffectFrame:
    """An effect at one moment"""

    atTime: float
    place: ShapePlace
    color: tuple[int, int, int]
    stars: list[StarPlace] | None = None
    # The stars sorted from left to right, for finding those near a point quickly, worked out when first needed
    _starsAcross: StarsAcross | None = field(default=None, init=False, repr=False, compare=False)

    def starsAcross(self) -> StarsAcross:
        if self._starsAcross is None:
            self._starsAcross = StarsAcross(self.stars or [])
        return self._starsAcross


# The following is a starfield's stars at one moment sorted by how far across they are, so the stars that can be over
# a point are found without looking at every star.  Each is kept with its place in the field's own order, so the stars
# near a point are looked at in that order, and the same star lights a point as when every star is looked at
@dataclass
class StarsAcross:
    """A starfield's stars at one moment, sorted from left to right"""

    xs: list[float]
    order: list[int]
    stars: list[StarPlace]
    largest: float

    def __init__(self, stars: list[StarPlace]) -> None:
        self.stars = stars
        self.order = sorted(range(len(stars)), key=lambda index: stars[index].x)
        self.xs = [stars[index].x for index in self.order]
        self.largest = max((star.size for star in stars), default=0.0)

    # The following returns the stars within a distance across of a point, in the field's own order
    def near(self, x: float, distance: float) -> list[StarPlace]:
        first = bisect.bisect_left(self.xs, x - distance)
        last = bisect.bisect_right(self.xs, x + distance)
        return [self.stars[index] for index in sorted(self.order[first:last])]


# The following is a lighting effect: a shape, its color, and how it moves over its span of the show
@dataclass
class LightEffect:
    """A shape drawn on the playfield that paints the lights it covers"""

    name: str
    shape: str
    place: ShapePlace
    rgb: tuple[int, int, int] = (255, 255, 255)
    intensity: int = 100
    # The color the effect changes to by its end, or None to keep its color
    endRGB: tuple[int, int, int] | None = None
    thickness: float = DEFAULT_THICKNESS
    # A pinwheel's blades or a spiral's arms, how many times a spiral's arms wind around its center, and how much of
    # the pinwheel each blade fills, from 0 to 1
    arms: int = 4
    turns: float = 1.0
    bladeFill: float = 0.5
    # How far past its edge the shape lights lights more dimly, as a fraction of the playfield's width
    softness: float = 0.0
    startTime: float = 0.0
    duration: float = 1.0
    stepTime: float = 0.05
    # The movement: the way it moves (degrees, 0 to the right and 90 up), how far, the turn and the size it ends at
    moveAngle: float = 90.0
    moveDistance: float = 0.0
    spin: float = 0.0
    endScale: float = 1.0
    repeats: int = 1
    bounce: bool = False
    easing: str = EASING_LINEAR
    # Whether lights are turned off while the shape is not over them, rather than left as the show sets them
    offOutside: bool = False
    # Whether each change fades over a step, so the effect looks smoother
    smooth: bool = False
    # Rainbow coloring: how the rainbow is laid over the shape, how many rainbows fit across it, and how many times its
    # colors go round over the effect, flowing one way, or the other when less than 0
    colorMode: str = COLOR_SOLID
    rainbowBands: float = 1.0
    rainbowCycles: float = 0.0
    # A starfield's stars: their shape, size across (a fraction of the playfield's width), how many there are in each
    # square a tenth of the playfield wide, their colors, and the number their places are shuffled by
    starShape: str = STAR_DOT
    starSize: float = 0.03
    starDensity: float = 0.5
    starColoring: str = STARS_EFFECT_COLOR
    starSeed: int = 1
    # How the stars move, how fast (fractions of the playfield's width each second), the way they drift (degrees, 0 to
    # the right and 90 up), and how much and how often they twinkle
    starMotion: str = STARS_DRIFT
    starSpeed: float = 0.1
    starAngle: float = 270.0
    twinkle: float = 0.0
    twinkleRate: float = 1.0
    # The show's steps before and after the effect was last applied, so applying it again replaces it
    appliedBefore: list[ShowStep] | None = field(default=None, repr=False, compare=False)
    appliedAfter: list[ShowStep] | None = field(default=None, repr=False, compare=False)
    _starCache: tuple[tuple, list[Star]] | None = field(default=None, repr=False, compare=False)

    @property
    def endTime(self) -> float:
        return self.startTime + self.duration

    @property
    def frameCount(self) -> int:
        return max(math.ceil(round(self.duration / max(self.stepTime, 0.001), 6)), 1)

    # The following returns how far through its movement the effect is at a time, from 0 to 1, with its repeats,
    # bouncing back and easing
    def progressAt(self, atTime: float) -> float:
        if self.duration <= 0:
            return 0.0
        fraction = min(max((atTime - self.startTime) / self.duration, 0.0), 1.0)
        cycles = max(self.repeats, 1)
        cycleFraction = 1.0 if fraction >= 1.0 else (fraction * cycles) % 1.0
        if fraction >= 1.0 and self.bounce:
            cycleFraction = 0.0
        if self.bounce:
            cycleFraction = cycleFraction * 2 if cycleFraction < 0.5 else 2 - cycleFraction * 2
        if self.easing == EASING_SMOOTH:
            cycleFraction = cycleFraction * cycleFraction * (3 - 2 * cycleFraction)
        return cycleFraction

    # The following returns where the shape is at a time
    def placeAt(self, atTime: float) -> ShapePlace:
        progress = self.progressAt(atTime)
        angle = math.radians(self.moveAngle)
        scale = 1 + (self.endScale - 1) * progress
        return ShapePlace(
            self.place.centerX + math.cos(angle) * self.moveDistance * progress,
            self.place.centerY - math.sin(angle) * self.moveDistance * progress,
            self.place.width * scale,
            self.place.height * scale,
            self.place.rotation + self.spin * progress,
        )

    # The following returns the effect's color at a time, changing to its end color over the effect
    def colorAt(self, atTime: float) -> tuple[int, int, int]:
        if self.endRGB is None or self.duration <= 0:
            return self.rgb
        fraction = min(max((atTime - self.startTime) / self.duration, 0.0), 1.0)
        red, green, blue = (
            round(start + (end - start) * fraction) for start, end in zip(self.rgb, self.endRGB, strict=True)
        )
        return red, green, blue

    # The following returns how much of a point the shape covers at a time, from 0 outside to 1 inside, fading over
    # its soft edge
    # A light reaches out from its middle, so a shape that covers part of it near its middle lights it
    def coverageAt(self, atTime: float, x: float, y: float, reach: float = 0.0) -> float:
        return shapeCoverage(
            self.shape,
            self.placeAt(atTime),
            x,
            y,
            self.thickness,
            self.softness,
            arms=self.arms,
            turns=self.turns,
            bladeFill=self.bladeFill,
            reach=reach,
        )

    # The following returns the intensity a point is lit at, at a time, in steps so soft edges change less often
    def intensityAt(self, atTime: float, x: float, y: float, reach: float = 0.0) -> int:
        return self.lightAt(atTime, x, y, reach)[0]

    # The following returns the effect at a time: where its shape is, its stars and its color
    def frameAt(self, atTime: float) -> EffectFrame:
        place = self.placeAt(atTime)
        stars = self.starsAt(atTime, place) if self.shape == SHAPE_STARFIELD else None
        return EffectFrame(atTime, place, self.colorAt(atTime), stars)

    # The following returns the intensity and color a point is lit in, at a time.  A starfield lights a point in the
    # color of the brightest star over it.  The effect at the time can be given, when it is worked out already
    def lightAt(
        self, atTime: float, x: float, y: float, reach: float = 0.0, frame: EffectFrame | None = None
    ) -> tuple[int, tuple[int, int, int]]:
        frame = frame or self.frameAt(atTime)
        place = frame.place
        if self.shape == SHAPE_STARFIELD:
            coverage, star = self._starCoverage(frame, place, x, y, reach)
            if star is not None and self.starColoring == STARS_RANDOM_COLORS:
                rgb = starColor(star)
            else:
                rgb = self.colorAtPoint(atTime, place, x, y, frame.color)
        else:
            coverage = shapeCoverage(
                self.shape,
                place,
                x,
                y,
                self.thickness,
                self.softness,
                arms=self.arms,
                turns=self.turns,
                bladeFill=self.bladeFill,
                reach=reach,
            )
            rgb = self.colorAtPoint(atTime, place, x, y, frame.color) if coverage > 0 else self.rgb
        intensity = self.intensity * coverage
        if 0 < coverage < 1:
            intensity = round(intensity / INTENSITY_STEP) * INTENSITY_STEP
        return int(min(max(intensity, 0), 100)), rgb

    # The following returns the color the effect lights a point in, at a time: its color, or the rainbow's color there.
    # A rainbow starts from the hue of the effect's color, and its colors flow over the effect as it cycles
    def colorAtPoint(
        self, atTime: float, place: ShapePlace, x: float, y: float, color: tuple[int, int, int] | None = None
    ) -> tuple[int, int, int]:
        if self.colorMode not in COLOR_MODES[1:]:
            return color or self.colorAt(atTime)
        localX, localY = _localPoint(place, x, y)
        halfWidth, halfHeight = max(abs(place.width) / 2, 1e-9), max(abs(place.height) / 2, 1e-9)
        acrossX, acrossY = localX / halfWidth, localY / halfHeight
        if self.colorMode == COLOR_RAINBOW_ROUND:
            rainbowPlace = (math.atan2(acrossY, acrossX) / (2 * math.pi)) % 1.0
        elif self.colorMode == COLOR_RAINBOW_OUTWARD:
            rainbowPlace = math.hypot(acrossX, acrossY)
        else:
            rainbowPlace = (acrossX + 1) / 2
        return self.rainbowColor(rainbowPlace, atTime)

    # The following returns the rainbow's color at a place along it, from 0 at its start to 1 at its end, at a time
    def rainbowColor(self, rainbowPlace: float, atTime: float) -> tuple[int, int, int]:
        timeFraction = min(max((atTime - self.startTime) / self.duration, 0.0), 1.0) if self.duration > 0 else 0.0
        startHue = colorsys.rgb_to_hsv(*(channel / 255 for channel in self.rgb))[0]
        return _hueRGB(startHue + rainbowPlace * self.rainbowBands + self.rainbowCycles * timeFraction)

    # The following returns the starfield's stars, worked out from its seed, so they are the same each time
    def stars(self) -> list[Star]:
        key = (self.starSeed, self.starDensity, round(self.place.width, 6), round(self.place.height, 6))
        if self._starCache is not None and self._starCache[0] == key:
            return self._starCache[1]
        area = abs(self.place.width * self.place.height)
        count = min(max(round(self.starDensity * area / DENSITY_AREA), 1 if self.starDensity > 0 else 0), MAX_STARS)
        shuffler = random.Random(self.starSeed)
        stars = [
            Star(
                shuffler.random() - 0.5,
                shuffler.random() - 0.5,
                shuffler.random(),
                shuffler.random(),
                shuffler.random(),
            )
            for _ in range(count)
        ]
        self._starCache = (key, stars)
        return stars

    # The following returns where each star is at a time, from the middle of the field, unturned with it.  Drifting
    # stars that leave the field come back in on its other side, and stars flying out grow as they near its edge
    def starsAt(self, atTime: float, place: ShapePlace | None = None) -> list[StarPlace]:
        place = place or self.placeAt(atTime)
        width, height = abs(place.width), abs(place.height)
        elapsed = max(atTime - self.startTime, 0.0)
        placed = []
        for star in self.stars():
            size = self.starSize
            if self.starMotion == STARS_DRIFT and width > 0 and height > 0:
                angle = math.radians(self.starAngle)
                x = (star.fieldX * width + math.cos(angle) * self.starSpeed * elapsed + width / 2) % width - width / 2
                y = (
                    star.fieldY * height - math.sin(angle) * self.starSpeed * elapsed + height / 2
                ) % height - height / 2
            elif self.starMotion == STARS_WARP:
                corner = math.hypot(width / 2, height / 2) or 1.0
                outward = (star.warpStart + self.starSpeed * elapsed / corner) % 1.0
                direction = math.atan2(star.fieldY * height, star.fieldX * width)
                x, y = math.cos(direction) * outward * corner, math.sin(direction) * outward * corner
                size *= 0.3 + 1.4 * outward
                if abs(x) > width / 2 or abs(y) > height / 2:
                    continue
            else:
                x, y = star.fieldX * width, star.fieldY * height
            brightness = 1 - self.twinkle * (
                0.5 + 0.5 * math.sin(2 * math.pi * (self.twinkleRate * elapsed + star.phase))
            )
            placed.append(StarPlace(x, y, size, min(max(brightness, 0.0), 1.0), star))
        return placed

    # The following returns how brightly the stars light a point, and the star lighting it most
    def _starCoverage(
        self, frame: EffectFrame, place: ShapePlace, x: float, y: float, reach: float
    ) -> tuple[float, Star | None]:
        localX, localY = _localPoint(place, x, y)
        best, bestStar = 0.0, None
        # Only the stars close enough across to reach the point can light it
        across = frame.starsAcross()
        for starPlace in across.near(localX, across.largest + reach + self.softness):
            offsetX, offsetY = localX - starPlace.x, localY - starPlace.y
            limit = starPlace.size + reach + self.softness
            if abs(offsetX) > limit or abs(offsetY) > limit:
                continue
            distance = starDistance(self.starShape, offsetX, offsetY, starPlace.size) - reach
            if distance <= 0:
                coverage = 1.0
            elif self.softness > 0:
                coverage = max(0.0, 1 - distance / self.softness)
            else:
                coverage = 0.0
            coverage *= starPlace.brightness
            if coverage > best:
                best, bestStar = coverage, starPlace.star
        return best, bestStar


# The following returns how much of a point a shape covers, from 0 outside to 1 inside, fading over the soft edge
def shapeCoverage(
    shape: str,
    place: ShapePlace,
    x: float,
    y: float,
    thickness: float,
    softness: float,
    arms: int = 4,
    turns: float = 1.0,
    bladeFill: float = 0.5,
    reach: float = 0.0,
) -> float:
    distance = _distanceOutside(shape, place, x, y, thickness, arms, turns, bladeFill) - reach
    if distance <= 0:
        return 1.0
    if softness <= 0:
        return 0.0
    return max(0.0, 1 - distance / softness)


# The following returns how far a point is outside a shape, or 0 inside it, in fractions of the playfield's width
def _distanceOutside(
    shape: str,
    place: ShapePlace,
    x: float,
    y: float,
    thickness: float,
    arms: int = 4,
    turns: float = 1.0,
    bladeFill: float = 0.5,
) -> float:
    localX, localY = _localPoint(place, x, y)
    halfWidth, halfHeight = abs(place.width) / 2, abs(place.height) / 2
    if shape == SHAPE_LINE:
        halfHeight = thickness / 2
    # A starfield's stars are found by the effect, and the field is a rectangle
    if shape in (SHAPE_LINE, SHAPE_RECTANGLE, SHAPE_STARFIELD):
        outsideX, outsideY = abs(localX) - halfWidth, abs(localY) - halfHeight
        return math.hypot(max(outsideX, 0.0), max(outsideY, 0.0))

    # An ellipse's distance is measured along the way to its center, which is close enough for lighting lights
    if halfWidth <= 0 or halfHeight <= 0:
        return math.hypot(localX, localY)
    radius = math.hypot(localX / halfWidth, localY / halfHeight)
    pointDistance = math.hypot(localX, localY)
    edgeDistance = pointDistance / radius if radius > 0 else min(halfWidth, halfHeight)
    if shape == SHAPE_RING:
        return max(abs(pointDistance - edgeDistance) - thickness / 2, 0.0)
    if shape in ARMED_SHAPES and radius <= 1:
        return _armDistance(
            shape, localX / halfWidth, localY / halfHeight, pointDistance, thickness, arms, turns, bladeFill
        )
    return max(pointDistance - edgeDistance, 0.0)


# The following returns how far a point inside a pinwheel or spiral is from its nearest blade or arm, measured around
# the center.  The point is given within the shape's ellipse, as a fraction of its size each way, and its distance from
# the center in fractions of the playfield's width
def _armDistance(
    shape: str,
    ellipseX: float,
    ellipseY: float,
    pointDistance: float,
    thickness: float,
    arms: int,
    turns: float,
    bladeFill: float,
) -> float:
    armCount = max(int(arms), 1)
    sector = 2 * math.pi / armCount
    angle = math.atan2(ellipseY, ellipseX)
    if shape == SHAPE_PINWHEEL:
        bladeAngle = sector * min(max(bladeFill, 0.0), 1.0)
        intoSector = angle % sector
        if intoSector <= bladeAngle:
            return 0.0
        gap = min(intoSector - bladeAngle, sector - intoSector)
        return gap * pointDistance

    # A spiral's arms wind once around the center for each turn, from the center out to the ellipse's edge.  An arm
    # crosses each circle around the center at a slant, so the point's distance from it comes from both how far round
    # and how far out the arm is from the point
    radius = math.hypot(ellipseX, ellipseY)
    offset = (angle - radius * turns * 2 * math.pi) % sector
    gap = min(offset, sector - offset)
    around = gap * pointDistance
    if turns <= 0:
        return max(around - thickness / 2, 0.0)
    outward = gap / (turns * 2 * math.pi) * (pointDistance / radius if radius > 0 else 0.0)
    if around <= 0 or outward <= 0:
        return max(min(around, outward) - thickness / 2, 0.0)
    return max(around * outward / math.hypot(around, outward) - thickness / 2, 0.0)


# The following returns a point from a shape's center, turned with the shape, so the shape can be treated as unturned
def _localPoint(place: ShapePlace, x: float, y: float) -> tuple[float, float]:
    angle = math.radians(-place.rotation)
    offsetX, offsetY = x - place.centerX, y - place.centerY
    return offsetX * math.cos(angle) - offsetY * math.sin(angle), offsetX * math.sin(angle) + offsetY * math.cos(angle)


# The following returns the full color of a hue, from 0 to 1 round the color wheel, in the hues rainbows are painted in
def _hueRGB(hue: float) -> tuple[int, int, int]:
    steppedHue = round((hue % 1.0) * RAINBOW_HUE_STEPS) / RAINBOW_HUE_STEPS
    red, green, blue = colorsys.hsv_to_rgb(steppedHue % 1.0, 1.0, 1.0)
    return round(red * 255), round(green * 255), round(blue * 255)


# The following returns the color of a star that has a color of its own
def starColor(star: Star) -> tuple[int, int, int]:
    return _hueRGB(star.hue)


# The following returns how far a point is outside a star, from the star's middle, for a star of a size across
def starDistance(starShape: str, offsetX: float, offsetY: float, size: float) -> float:
    half = size / 2
    acrossX, acrossY = abs(offsetX), abs(offsetY)
    if starShape == STAR_DIAMOND:
        return (acrossX + acrossY - half) / math.sqrt(2)
    if starShape == STAR_CROSS:
        # Two bars, each a fifth of the star's size thick
        barHalf = size / 10
        alongX = math.hypot(max(acrossX - half, 0.0), max(acrossY - barHalf, 0.0))
        alongY = math.hypot(max(acrossX - barHalf, 0.0), max(acrossY - half, 0.0))
        return min(alongX, alongY)
    if starShape == STAR_SPARKLE:
        # A four pointed star, its sides curving in between its points
        return ((math.sqrt(acrossX) + math.sqrt(acrossY)) ** 2 - half) / 2
    return math.hypot(acrossX, acrossY) - half


# The following returns, for each light, the intensity the effect lights it at in each of its steps
# Lights can be given how far they reach out from their middle, so a shape covering part of one lights it
def effectFrames(
    effect: LightEffect,
    lightPositions: dict[str, tuple[float, float]],
    lightReaches: dict[str, float] | None = None,
) -> dict[str, list[int]]:
    return {
        lightName: [intensity for intensity, _rgb in lights]
        for lightName, lights in effectLightFrames(effect, lightPositions, lightReaches).items()
    }


# The following returns, for each light, the intensity and color the effect lights it in, in each of its steps
def effectLightFrames(
    effect: LightEffect,
    lightPositions: dict[str, tuple[float, float]],
    lightReaches: dict[str, float] | None = None,
) -> dict[str, list[tuple[int, tuple[int, int, int]]]]:
    # Each step of the effect is worked out once, for all the lights
    effectFrames = [effect.frameAt(effect.startTime + frame * effect.stepTime) for frame in range(effect.frameCount)]
    frames: dict[str, list[tuple[int, tuple[int, int, int]]]] = {}
    for lightName, (x, y) in lightPositions.items():
        reach = (lightReaches or {}).get(lightName, 0.0)
        lights = [effect.lightAt(frame.atTime, x, y, reach, frame) for frame in effectFrames]
        if any(intensity for intensity, _rgb in lights):
            frames[lightName] = lights
    return frames


# The following paints an effect into a show: each light the shape passes over is lit with the effect's color while
# it is covered, and turned off or left as the show sets it while it is not.  Lights are given as their places on the
# playfield, in the same units as the shape.  It returns whether the show was changed.
#
# Each run of steps a light is lit the same in is painted as showEditor.paintLight paints a span: the light is taken
# out of the show's steps in the run, given the run's setting where the run starts, and given back what the show set
# it to before where the run ends, unless the step there sets it.  The show is split and read once for all the runs,
# rather than once for each, so effects with many lights and steps, such as rainbows, are painted quickly
def applyEffect(
    show: MPFShow,
    effect: LightEffect,
    lightPositions: dict[str, tuple[float, float]],
    namedColors: dict[str, tuple[int, int, int]] | None = None,
    lightReaches: dict[str, float] | None = None,
) -> bool:
    if effect.duration <= 0 or not lightPositions:
        return False
    showEditor.extendShow(show, effect.endTime)
    showEnd = show.totalDuration
    runs = _effectRuns(effect, lightPositions, lightReaches, namedColors, showEnd)
    if not runs:
        return False

    # What the show set each light to before it is painted, for giving it back after each run
    paintedLights = {lightName for lightName, *_rest in runs}
    original: dict[str, list[tuple[float, LightSetting]]] = {lightName: [] for lightName in paintedLights}
    for step in show.steps:
        for lightKey, setting in step.lights.items():
            for lightName in _lightsNamed(lightKey) & paintedLights:
                original[lightName].append((step.startTime, setting))
    originalTimes = {lightName: [time for time, _setting in settings] for lightName, settings in original.items()}

    # The show is split once where every run starts and ends
    for boundary in sorted({time for _name, start, stop, _setting in runs for time in (start, stop)}):
        if boundary < showEnd - showEditor.TIME_TOLERANCE:
            showEditor.splitStepAt(show, boundary)
    stepsByStart = {_timeKey(step.startTime): step for step in show.steps}
    startKeys = sorted(stepsByStart)

    for lightName, start, stop, setting in runs:
        startKey, stopKey = _timeKey(start), _timeKey(stop)
        for key in startKeys[bisect.bisect_left(startKeys, startKey) : bisect.bisect_left(startKeys, stopKey)]:
            showEditor.removeLight(stepsByStart[key], lightName)
        stepsByStart[startKey].lights[lightName] = setting
        endStep = stepsByStart.get(stopKey) if stop < showEnd - showEditor.TIME_TOLERANCE else None
        if endStep is not None and not any(showEditor.namesLight(key, lightName) for key in endStep.lights):
            before = bisect.bisect_left(originalTimes[lightName], stop - showEditor.TIME_TOLERANCE)
            settingAfter = original[lightName][before - 1][1] if before else None
            restored = parseLightSetting("stop") if settingAfter is None else copy.copy(settingAfter)
            # The color it goes back to is set straight away, rather than fading into it again
            restored.fadeText, restored.fadeMs = "", 0
            endStep.lights[lightName] = restored
    showEditor.joinEmptySteps(show)
    return True


# The following returns the runs of an effect's steps each light is painted in: the light, when the run starts and
# ends, and its setting.  Steps lit the same make one run, and steps the light is not lit in are only painted when the
# effect turns lights off outside it
def _effectRuns(
    effect: LightEffect,
    lightPositions: dict[str, tuple[float, float]],
    lightReaches: dict[str, float] | None,
    namedColors: dict[str, tuple[int, int, int]] | None,
    showEnd: float,
) -> list[tuple[str, float, float, LightSetting]]:
    fadeMs = round(effect.stepTime * 1000) if effect.smooth else 0
    settings: dict[tuple[tuple[int, int, int], int], LightSetting] = {}
    runs: list[tuple[str, float, float, LightSetting]] = []
    for lightName, lights in effectLightFrames(effect, lightPositions, lightReaches).items():
        frame = 0
        while frame < len(lights):
            intensity, frameColor = lights[frame]
            runEnd = frame + 1
            while runEnd < len(lights) and (
                lights[runEnd] == lights[frame] or (not intensity and not lights[runEnd][0])
            ):
                runEnd += 1
            runStart = showEditor._toMilliseconds(max(effect.startTime + frame * effect.stepTime, 0.0))
            runStop = showEditor._toMilliseconds(
                min(effect.startTime + runEnd * effect.stepTime, effect.endTime, showEnd)
            )
            frame = runEnd
            if runStop - runStart < showEditor.TIME_TOLERANCE or not (intensity or effect.offOutside):
                continue
            look = (frameColor, intensity) if intensity else ((0, 0, 0), 100)
            if look not in settings:
                settings[look] = showEditor.paintSetting(look[0], look[1], fadeMs, namedColors)
            runs.append((lightName, runStart, runStop, copy.copy(settings[look])))
    return runs


# The following returns the lights a light key of a step names: the light, or each light of a list
def _lightsNamed(lightKey: str) -> set[str]:
    names = {lightKey}
    if not showEditor._TOKEN_RE.search(lightKey):
        names.update(name.strip() for name in lightKey.split(","))
    return names


# The following returns a time as whole milliseconds, which show steps start on, for finding a step by its start
def _timeKey(seconds: float) -> int:
    return round(seconds * 1000)


# The following applies an effect, first taking out what it painted when it was last applied, as long as the show has
# not been changed since.  This lets an effect's settings be changed and applied again in its place
def applyEffectInPlace(
    show: MPFShow,
    effect: LightEffect,
    lightPositions: dict[str, tuple[float, float]],
    namedColors: dict[str, tuple[int, int, int]] | None = None,
    lightReaches: dict[str, float] | None = None,
) -> bool:
    isReplacing = effect.appliedBefore is not None and effect.appliedAfter == show.steps
    if isReplacing and effect.appliedBefore is not None:
        show.steps = copy.deepcopy(effect.appliedBefore)
    stepsBefore = copy.deepcopy(show.steps)
    changed = applyEffect(show, effect, lightPositions, namedColors, lightReaches)
    effect.appliedBefore = stepsBefore
    effect.appliedAfter = copy.deepcopy(show.steps)
    return changed or isReplacing


# The following are ready-made pattern effects, as the settings they give an effect.  They keep where the effect is,
# its color and its timing, and give it its shape and how it moves
EFFECT_PRESETS: dict[str, dict[str, object]] = {
    "Spinning pinwheel": {
        "shape": SHAPE_PINWHEEL,
        "arms": 4,
        "bladeFill": 0.5,
        "spin": 360.0,
        "endScale": 1.0,
        "softness": 0.0,
    },
    "Radar sweep": {
        "shape": SHAPE_PINWHEEL,
        "arms": 1,
        "bladeFill": 0.12,
        "spin": 360.0,
        "endScale": 1.0,
        "softness": 0.04,
    },
    "Pinwheel burst": {
        "shape": SHAPE_PINWHEEL,
        "arms": 8,
        "bladeFill": 0.35,
        "spin": 90.0,
        "endScale": 2.0,
        "softness": 0.0,
    },
    "Spiral in": {
        "shape": SHAPE_SPIRAL,
        "arms": 2,
        "turns": 1.5,
        "spin": 360.0,
        "endScale": 1.0,
        "thickness": 0.08,
    },
    "Spiral out": {
        "shape": SHAPE_SPIRAL,
        "arms": 2,
        "turns": 1.5,
        "spin": -360.0,
        "endScale": 1.0,
        "thickness": 0.08,
    },
    "Rainbow wheel": {
        "shape": SHAPE_ELLIPSE,
        "colorMode": COLOR_RAINBOW_ROUND,
        "rainbowBands": 1.0,
        "rainbowCycles": 0.0,
        "spin": 360.0,
        "endScale": 1.0,
    },
    "Rainbow rings": {
        "shape": SHAPE_ELLIPSE,
        "colorMode": COLOR_RAINBOW_OUTWARD,
        "rainbowBands": 2.0,
        "rainbowCycles": -2.0,
        "spin": 0.0,
        "endScale": 1.0,
    },
    "Rainbow sweep": {
        "shape": SHAPE_RECTANGLE,
        "colorMode": COLOR_RAINBOW_ACROSS,
        "rainbowBands": 1.0,
        "rainbowCycles": -2.0,
        "spin": 0.0,
        "endScale": 1.0,
    },
    "Rainbow pinwheel": {
        "shape": SHAPE_PINWHEEL,
        "arms": 6,
        "bladeFill": 0.6,
        "colorMode": COLOR_RAINBOW_ROUND,
        "rainbowBands": 1.0,
        "rainbowCycles": 0.0,
        "spin": 360.0,
        "endScale": 1.0,
    },
    "Starfield drift": {
        "shape": SHAPE_STARFIELD,
        "starShape": STAR_DOT,
        "starMotion": STARS_DRIFT,
        "starAngle": 270.0,
        "starSpeed": 0.3,
        "starDensity": 0.4,
        "twinkle": 0.3,
        "spin": 0.0,
        "endScale": 1.0,
    },
    "Warp speed": {
        "shape": SHAPE_STARFIELD,
        "starShape": STAR_DOT,
        "starMotion": STARS_WARP,
        "starSpeed": 0.6,
        "starDensity": 0.6,
        "starSize": 0.025,
        "twinkle": 0.0,
        "spin": 0.0,
        "endScale": 1.0,
    },
    "Twinkling sky": {
        "shape": SHAPE_STARFIELD,
        "starShape": STAR_SPARKLE,
        "starMotion": STARS_STILL,
        "starDensity": 0.5,
        "starSize": 0.05,
        "twinkle": 0.9,
        "twinkleRate": 1.5,
        "spin": 0.0,
        "endScale": 1.0,
    },
    "Rainbow stars": {
        "shape": SHAPE_STARFIELD,
        "starShape": STAR_DIAMOND,
        "starMotion": STARS_DRIFT,
        "starAngle": 0.0,
        "starSpeed": 0.2,
        "starColoring": STARS_RANDOM_COLORS,
        "twinkle": 0.4,
        "spin": 0.0,
        "endScale": 1.0,
    },
    "Galaxy twist": {
        "shape": SHAPE_SPIRAL,
        "arms": 3,
        "turns": 0.75,
        "spin": 180.0,
        "endScale": 1.4,
        "thickness": 0.08,
        "softness": 0.03,
    },
}


# The following sorts the ready-made patterns into groups, for choosing them from: rainbows, starfields, pinwheels and
# spirals
def presetGroups() -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {"Pinwheels": [], "Spirals": [], "Rainbows": [], "Starfields": []}
    for presetName, settings in EFFECT_PRESETS.items():
        if settings.get("shape") == SHAPE_STARFIELD:
            groups["Starfields"].append(presetName)
        elif settings.get("colorMode", COLOR_SOLID) != COLOR_SOLID:
            groups["Rainbows"].append(presetName)
        elif settings.get("shape") == SHAPE_SPIRAL:
            groups["Spirals"].append(presetName)
        else:
            groups["Pinwheels"].append(presetName)
    return groups


# The following gives an effect a ready-made pattern's settings.  A pattern's shape fills the ellipse it is drawn in,
# so an effect drawn as a line is made as wide as it is long
def applyPreset(effect: LightEffect, presetName: str) -> None:
    for setting, value in EFFECT_PRESETS[presetName].items():
        setattr(effect, setting, value)
    if effect.place.height < effect.place.width / 4:
        effect.place.height = effect.place.width


# The following makes an effect from a shape dragged out on the playfield, from one corner (or end of a line) to the
# other, in fractions of the playfield's width
def effectFromDrag(
    name: str, shape: str, startX: float, startY: float, endX: float, endY: float, **settings
) -> LightEffect:
    if shape == SHAPE_LINE:
        place = ShapePlace(
            (startX + endX) / 2,
            (startY + endY) / 2,
            math.hypot(endX - startX, endY - startY),
            DEFAULT_THICKNESS,
            math.degrees(math.atan2(endY - startY, endX - startX)),
        )
    else:
        place = ShapePlace((startX + endX) / 2, (startY + endY) / 2, abs(endX - startX), abs(endY - startY))
    return LightEffect(name, shape, place, **settings)
