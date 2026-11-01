from pathlib import Path

import pytest

from mpfmanager.core import monitorManager, showManager
from mpfmanager.core.monitorManager import MonitorLayout, MonitorLight, PlayfieldLights

MONITOR_CONFIG = """\
device_size: 0.03
device_alpha: 200
light:
  l_a:
    x: 0.25
    y: 0.5
  l_b:
    x: '0.75'
    y: 0.5
    size: 0.06
    shape: TRIANGLE
    rotation: 90
    alpha: 100
  l_custom:
    x: 0.5
    y: 0.5
    shape: CUSTOM
    custom_shape_points: [[0, 0], [1, 0], [0, 1]]
  l_bad_custom:
    x: 0.5
    y: 0.5
    shape: CUSTOM
    custom_shape_points: nope
  l_odd:
    x: wide
    y: 0.1
    shape: BLOB
  l_unplaced: {}
  not_a_light: 5
switch:
  s_start:
    x: 0.5
    y: 0.9
"""


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_loadMonitorLayout(tmp_path):
    _write(tmp_path / "monitor" / "monitor.yaml", MONITOR_CONFIG)
    (tmp_path / "monitor" / "playfield.jpg").write_bytes(b"")
    layout = monitorManager.loadMonitorLayout(tmp_path)
    assert layout is not None
    assert layout.imagePath == tmp_path / "monitor" / "playfield.jpg"
    assert set(layout.lights) == {"l_a", "l_b", "l_custom", "l_bad_custom", "l_odd"}
    assert layout.lights["l_a"] == MonitorLight("l_a", 0.25, 0.5, 0.03, "CIRCLE", 0.0, 200)
    assert layout.lights["l_b"] == MonitorLight("l_b", 0.75, 0.5, 0.06, "TRIANGLE", 90.0, 100)
    # An unknown shape is drawn as a circle, as MPF-Monitor draws lights, and a number that cannot be read is 0
    assert (layout.lights["l_odd"].x, layout.lights["l_odd"].shape) == (0.0, "CIRCLE")
    assert layout.lights["l_custom"].customPoints == [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    assert layout.lights["l_bad_custom"].customPoints is None

    # Another layout file can be chosen, and a png playfield is used when there is no jpg
    _write(tmp_path / "monitor" / "monitor_gi.yaml", "light:\n  gi_1:\n    x: 0.1\n    y: 0.2\n")
    (tmp_path / "monitor" / "playfield.jpg").unlink()
    (tmp_path / "monitor" / "playfield.png").write_bytes(b"")
    giLayout = monitorManager.loadMonitorLayout(tmp_path, "monitor_gi.yaml")
    assert giLayout is not None and list(giLayout.lights) == ["gi_1"]
    assert giLayout.imagePath == tmp_path / "monitor" / "playfield.png"
    assert giLayout.lights["gi_1"].size == monitorManager.DEFAULT_DEVICE_SIZE


def test_loadMonitorLayoutWithoutOne(tmp_path):
    assert monitorManager.loadMonitorLayout(tmp_path) is None
    _write(tmp_path / "monitor" / "monitor.yaml", "- not a layout\n")
    assert monitorManager.loadMonitorLayout(tmp_path) is None
    _write(tmp_path / "monitor" / "monitor.yaml", "light: [\n")
    assert monitorManager.loadMonitorLayout(tmp_path) is None
    _write(tmp_path / "monitor" / "monitor.yaml", "light: none\n")
    layout = monitorManager.loadMonitorLayout(tmp_path)
    assert layout == MonitorLayout(None, {})


def test_shapePoints():
    assert MonitorLight("c", 0, 0).shapePoints() is None
    assert MonitorLight("s", 0, 0, shape="SQUARE").shapePoints() == [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)]
    rotated = MonitorLight("t", 0, 0, shape="TRIANGLE", rotation=90).shapePoints()
    assert rotated is not None
    assert rotated[0] == pytest.approx((0.6, 0.0))
    assert MonitorLight("x", 0, 0, shape="CUSTOM").shapePoints() == monitorManager.CUSTOM_SHAPE_FALLBACK
    assert MonitorLight("x", 0, 0, shape="CUSTOM", customPoints=[(0.0, 1.0)]).shapePoints() == [(0.0, 1.0)]
    assert MonitorLight("u", 0, 0, shape="UNKNOWN").shapePoints() == monitorManager.SHAPE_POINTS["SQUARE"]


def test_gammaCorrected():
    assert monitorManager.gammaCorrected((0, 255, 100)) == (0, 255, 180)
    assert monitorManager.gammaCorrected((-5, 1, 400)) == (0, 18, 255)


def test_loadLightTags(tmp_path):
    configFolder = tmp_path / "config"
    _write(
        configFolder / "config.yaml",
        "config: hardware.yaml\nlights:\n  l_a:\n    tags: gi, gi_top\n  l_b:\n    tags: [inserts]\n",
    )
    _write(
        configFolder / "hardware.yaml",
        "lights:\n  l_a:\n    tags: gi\n  l_c: {}\n  l_d: none\n"
        "light_stripes:\n  l_ladder:\n    count: 3\n    tags: ladder\n    light_template:\n      tags: ladder_lights, rgb\n"
        "  l_bad:\n    count: many\n"
        "light_rings:\n  l_relay:\n    count: 2\n    light_template: none\n",
    )
    assert monitorManager.loadLightTags(tmp_path) == {
        "l_a": {"gi"},
        "l_b": {"inserts"},
        "l_c": set(),
        "l_d": set(),
        "l_ladder_light_0": {"l_ladder", "ladder", "ladder_lights", "rgb"},
        "l_ladder_light_1": {"l_ladder", "ladder", "ladder_lights", "rgb"},
        "l_ladder_light_2": {"l_ladder", "ladder", "ladder_lights", "rgb"},
        "l_relay_light_0": {"l_relay"},
        "l_relay_light_1": {"l_relay"},
    }


def test_playfieldLightsFollowTheShow():
    layout = MonitorLayout(
        None,
        {name: MonitorLight(name, 0.5, 0.5) for name in ("l_a", "l_ladder_light_0", "l_ladder_light_1", "l_other")},
    )
    lightTags = {
        "l_a": {"gi"},
        "l_ladder_light_0": {"l_ladder", "gi"},
        "l_ladder_light_1": {"l_ladder"},
        "l_unplaced": {"gi"},
        "l_other": set(),
    }
    playfieldLights = PlayfieldLights(layout, lightTags)
    show = showManager.parseShow(
        [
            {"duration": "1s", "lights": {"gi": "red", "(leds)": "blue", "l_unplaced": "lime", "l_missing": "lime"}},
            {"duration": "1s", "lights": {"l_ladder": "blue-f1s", "l_a": "lime"}},
        ],
        "playfield",
    )
    playfieldLights.setShow(show)
    assert playfieldLights.lightsForChannel("gi") == ["l_a", "l_ladder_light_0"]
    assert playfieldLights.lightsForChannel("l_unplaced") == []
    assert playfieldLights.unplacedChannels == ["(leds)", "l_unplaced", "l_missing"]

    assert playfieldLights.lightColors(0.5) == {
        "l_a": ((255, 0, 0), "gi"),
        "l_ladder_light_0": ((255, 0, 0), "gi"),
        "l_ladder_light_1": (None, ""),
    }
    # The channel that set a light last wins, and a fade starts from the light's own color, even when another channel
    # set it, so l_ladder_light_0 fades from the red gi gave it
    assert playfieldLights.lightColors(1.5) == {
        "l_a": ((0, 255, 0), "l_a"),
        "l_ladder_light_0": ((127, 0, 127), "l_ladder"),
        "l_ladder_light_1": ((0, 0, 127), "l_ladder"),
    }

    playfieldLights.setShow(None)
    assert playfieldLights.lightColors(0.5) == {}
    assert playfieldLights.unplacedChannels == []
    assert PlayfieldLights(None, lightTags).lightsForChannel("gi") == []
