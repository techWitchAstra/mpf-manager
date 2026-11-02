"""monitorManager reads an MPF-Monitor playfield layout and works out each playfield light's color during a show"""

#   monitorManager - Responsible for reading monitor/monitor.yaml, where MPF-Monitor keeps the
#       playfield image and the position, size and shape of each light, and for finding which
#       lights each channel of a show (a light, a light tag or a light stripe or ring) reaches
#
#   Written by techWitchAstra
#
#   Code in this file may be adapted, re-written, or re-architected
#       from code from Claude.  None of the code in this file is a direct
#       result of AI agents, and has been overseen by a human at all stages

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mpfmanager.core import showManager, yamlInterfacer
from mpfmanager.core.showManager import MPFShow

# The following are MPF-Monitor's defaults: the light size, as a fraction of the playfield width, and how opaque it is
DEFAULT_DEVICE_SIZE = 0.02
DEFAULT_DEVICE_ALPHA = 220
PLAYFIELD_IMAGE_NAMES = ("playfield.jpg", "playfield.png")

# The following are the outlines of MPF-Monitor's light shapes, around the light's center, scaled by its size
# (from mpfmonitor/core/playfield.py, MIT license).  A circle has no points as it is drawn as an ellipse
SHAPE_POINTS: dict[str, list[tuple[float, float]] | None] = {
    "CIRCLE": None,
    "SQUARE": [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)],
    "RECTANGLE": [(-0.2, -0.5), (0.2, -0.5), (0.2, 0.5), (-0.2, 0.5)],
    "TRIANGLE": [(0, -0.6), (-0.6, 0.3), (0.6, 0.3)],
    "ARROW": [(0, -0.7), (-0.4, 0), (-0.2, 0), (-0.2, 0.4), (0.2, 0.4), (0.2, 0), (0.4, 0)],
    "FLIPPER": [(0, -0.3), (-0.3, 0.7), (0.3, 0.7)],
    "PENTAGON": [(0, 0.5), (-0.48, 0.15), (-0.29, -0.4), (0.29, -0.4), (0.48, 0.15)],
    "HEXAGON": [(0.5, 0), (0.25, 0.43), (-0.25, 0.43), (-0.5, 0), (-0.25, -0.43), (0.25, -0.43)],
    "OCTAGON": [(0.5, 0), (0.35, 0.35), (0, 0.5), (-0.35, 0.35), (-0.5, 0), (-0.35, -0.35), (0, -0.5), (0.35, -0.35)],
    "STAR": [
        (0, -0.5), (-0.11, -0.15), (-0.48, -0.15), (-0.18, 0.06), (-0.29, 0.4),
        (0, 0.19), (0.29, 0.4), (0.18, 0.06), (0.48, -0.15), (0.11, -0.15),
    ],
}  # fmt: skip
CUSTOM_SHAPE_FALLBACK = [(0.36, 0.36), (0, 0.19), (-0.36, 0.36), (-0.19, 0), (-0.36, -0.36), (0, -0.19), (0.36, -0.36)]


# The following data class holds where MPF-Monitor draws a light, and how
@dataclass
class MonitorLight:
    """A light placed on the playfield in MPF-Monitor"""

    name: str
    x: float
    y: float
    size: float = DEFAULT_DEVICE_SIZE
    shape: str = "CIRCLE"
    rotation: float = 0.0
    alpha: int = DEFAULT_DEVICE_ALPHA
    customPoints: list[tuple[float, float]] | None = None

    # The following returns the light's outline around its center as fractions of its size, rotated, or None for a circle
    def shapePoints(self) -> list[tuple[float, float]] | None:
        if self.shape == "CUSTOM":
            points: list[tuple[float, float]] | None = self.customPoints or CUSTOM_SHAPE_FALLBACK
        else:
            points = SHAPE_POINTS.get(self.shape, SHAPE_POINTS["SQUARE"])
        if points is None:
            return None
        angle = math.radians(self.rotation % 360)
        cosAngle, sinAngle = math.cos(angle), math.sin(angle)
        return [(x * cosAngle - y * sinAngle, x * sinAngle + y * cosAngle) for x, y in points]


# The following data class holds a machine's MPF-Monitor layout
@dataclass
class MonitorLayout:
    """The playfield image and the lights placed on it"""

    imagePath: Path | None
    lights: dict[str, MonitorLight] = field(default_factory=dict)


# The following reads a number from the monitor config, using a default when it is missing or not a number
def _number(value: Any, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


# The following reads a custom shape's points, which are pairs of numbers, or None if they cannot be read
def _customPoints(value: Any) -> list[tuple[float, float]] | None:
    try:
        return [(float(point[0]), float(point[1])) for point in value] or None
    except (TypeError, ValueError, IndexError):
        return None


# The following reads MPF-Monitor's layout of a machine from monitor/monitor.yaml, or None when it has none
def loadMonitorLayout(machinePath: Path, configName: str = "monitor.yaml") -> MonitorLayout | None:
    monitorFolder = machinePath / "monitor"
    try:
        monitorConfig = yamlInterfacer.loadYAMLText(monitorFolder / configName)
    except Exception:  # a monitor config that cannot be read is treated as no layout
        return None
    if not isinstance(monitorConfig, dict):
        return None

    imagePath = next((monitorFolder / name for name in PLAYFIELD_IMAGE_NAMES if (monitorFolder / name).is_file()), None)
    defaultSize = _number(monitorConfig.get("device_size"), DEFAULT_DEVICE_SIZE)
    defaultAlpha = int(_number(monitorConfig.get("device_alpha"), DEFAULT_DEVICE_ALPHA))
    layout = MonitorLayout(imagePath)
    lightsConfig = monitorConfig.get("light")
    for lightName, lightConfig in (lightsConfig if isinstance(lightsConfig, dict) else {}).items():
        if not isinstance(lightConfig, dict) or "x" not in lightConfig or "y" not in lightConfig:
            continue
        shape = str(lightConfig.get("shape", "DEFAULT")).upper()
        layout.lights[str(lightName)] = MonitorLight(
            str(lightName),
            _number(lightConfig.get("x"), 0.0),
            _number(lightConfig.get("y"), 0.0),
            _number(lightConfig.get("size"), defaultSize),
            # MPF-Monitor draws lights as circles unless a shape is chosen
            "CIRCLE" if shape == "DEFAULT" or (shape not in SHAPE_POINTS and shape != "CUSTOM") else shape,
            _number(lightConfig.get("rotation"), 0.0),
            int(_number(lightConfig.get("alpha"), defaultAlpha)),
            _customPoints(lightConfig.get("custom_shape_points")) if shape == "CUSTOM" else None,
        )
    return layout


# The following applies MPF-Monitor's gamma correction, which makes dim colors look as they do on a real playfield
def gammaCorrected(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    red, green, blue = (min(int(math.sqrt(max(value, 0)) * 18), 255) for value in rgb)
    return red, green, blue


# The following splits an MPF list setting, which is either a list or a comma separated string
def _toList(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


# The following reads every light of the machine config with its tags: the lights: section, and the lights MPF makes
# for each light stripe and ring, named <name>_light_<number> and tagged with the stripe's name
def loadLightTags(machinePath: Path) -> dict[str, set[str]]:
    lightConfigs: dict[str, dict] = {}
    groupConfigs: dict[str, dict] = {}
    for _configFile, configData in showManager.machineConfigs(machinePath):
        for section, configs in (
            ("lights", lightConfigs),
            ("light_stripes", groupConfigs),
            ("light_rings", groupConfigs),
        ):
            sectionData = configData.get(section)
            for name, deviceConfig in (sectionData if isinstance(sectionData, dict) else {}).items():
                # Like MPF, a later config file's settings for a device are merged over the earlier ones
                configs.setdefault(str(name), {}).update(deviceConfig if isinstance(deviceConfig, dict) else {})

    lightTags = {name: set(_toList(lightConfig.get("tags"))) for name, lightConfig in lightConfigs.items()}
    for groupName, groupConfig in groupConfigs.items():
        try:
            count = int(str(groupConfig.get("count", 0)))
        except ValueError:
            count = 0
        template = groupConfig.get("light_template")
        templateTags = _toList(template.get("tags")) if isinstance(template, dict) else []
        for index in range(count):
            lightTags[f"{groupName}_light_{index}"] = {groupName, *_toList(groupConfig.get("tags")), *templateTags}
    return lightTags


# The following works out which of the placed lights each channel of a show reaches, and the lights' colors over time
class PlayfieldLights:
    def __init__(self, layout: MonitorLayout | None, lightTags: dict[str, set[str]]):
        self.layout = layout
        self.lightTags = lightTags
        self.show: MPFShow | None = None
        self.lightChannels: dict[str, list[str]] = {}

    # The following returns the lights a show channel sets: the light of that name, or else every light with that tag
    def lightsForChannel(self, channelName: str) -> list[str]:
        if self.layout is None:
            return []
        if channelName in self.layout.lights or channelName in self.lightTags:
            return [channelName] if channelName in self.layout.lights else []
        return [name for name in self.layout.lights if channelName in self.lightTags.get(name, set())]

    # The following works out, for the show, which channels set each placed light
    def setShow(self, show: MPFShow | None) -> None:
        self.show = show
        self.lightChannels = {}
        for channel in show.channels if show else []:
            for lightName in self.lightsForChannel(channel.name):
                self.lightChannels.setdefault(lightName, []).append(channel.name)

    @property
    def unplacedChannels(self) -> list[str]:
        """The show's channels that reach none of the placed lights"""
        placed = {channel for channels in self.lightChannels.values() for channel in channels}
        return [channel.name for channel in self.show.channels if channel.name not in placed] if self.show else []

    # The following returns each placed light's color at a time, None meaning the show is not setting it, together with
    # the channel that set it.  When several channels set a light, such as a tag and the light itself, the latest wins
    def lightColors(self, atTime: float) -> dict[str, tuple[tuple[int, int, int] | None, str]]:
        return {lightName: self._lightColor(lightName, atTime) for lightName in self.lightChannels} if self.show else {}

    def _lightColor(self, lightName: str, atTime: float, depth: int = 0) -> tuple[tuple[int, int, int] | None, str]:
        assert self.show is not None
        latestStart, latestState, latestChannel = -1.0, None, ""
        for channel in self.lightChannels.get(lightName, []):
            state = self.show.channelState(channel, atTime)
            if state.segment is not None and state.segment.startTime >= latestStart:
                latestStart, latestState, latestChannel = state.segment.startTime, state, channel
        if latestState is None or latestState.segment is None:
            return None, ""
        segment = latestState.segment
        if latestState.isFading and segment.setting.rgb is not None and depth < 8:
            # A fade starts from the light's own color, which another channel may have set, such as a tag
            fromRGB, _channel = self._lightColor(lightName, segment.startTime - 1e-9, depth + 1)
            fraction = (atTime - segment.startTime) / (segment.fadeEndTime - segment.startTime)
            return showManager.blendRGB(fromRGB or (0, 0, 0), segment.setting.rgb, fraction), latestChannel
        return latestState.rgb, latestChannel
