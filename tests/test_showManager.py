from pathlib import Path

import pytest

from mpfmanager.core import showManager
from mpfmanager.core.showManager import parseLightSetting, parseShow, resolveColor, timeToMs, timeToSeconds

SHOW_FILE = """\
#show_version=6
- time: 0
  lights:
    l_a: red
    (leds): (color)
- time: 500ms
  lights:
    l_a: 000000-f250ms
    l_b: on
- time: +1
  lights:
    l_a: blue%50
  events: foo
- duration: -1
  lights:
    l_b: stop
"""


def _writeShow(path: Path, text: str = SHOW_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("1", 1.0), (2, 2.0), ("0.5", 0.5), ("250ms", 0.25), ("2s", 2.0), ("+1.5", 1.5), ("1m", 60.0), ("2sec", 2.0)],
)
def test_timeToSeconds(value, seconds):
    assert timeToSeconds(value) == seconds


def test_timeToMsTreatsBareNumbersAsMilliseconds():
    assert timeToMs("500") == 500
    assert timeToMs(None) == 0
    assert timeToMs("None") == 0
    assert timeToMs("1h") == 3600000
    assert timeToMs("1d") == 86400000
    assert timeToMs("20msec") == 20


@pytest.mark.parametrize(
    ("value", "rgb", "kind"),
    [
        ("red", (255, 0, 0), "color"),
        ("RED", (255, 0, 0), "color"),
        ("off", (0, 0, 0), "color"),
        ("on", (255, 255, 255), "color"),
        ("ff8000", (255, 128, 0), "color"),
        ("#00ff00", (0, 255, 0), "color"),
        ("ff", (255, 255, 255), "color"),
        ("f", (15, 15, 15), "color"),
        ("white%50", (127, 127, 127), "color"),
        ("(color)", None, "token"),
        ("stop", None, "stop"),
        ("notacolor", None, "invalid"),
        ("red%half", None, "invalid"),
    ],
)
def test_resolveColor(value, rgb, kind):
    assert resolveColor(value) == (rgb, kind)


def test_parseLightSettingForms():
    assert parseLightSetting("red - f 200ms").fadeMs == 200
    fullForm = parseLightSetting({"color": "blue", "fade": "1s"})
    assert (fullForm.rgb, fullForm.fadeMs) == ((0, 0, 255), 1000)
    assert parseLightSetting({"fade": "100"}).rgb == (255, 255, 255)
    assert parseLightSetting("(color)").isToken


def test_loadShowFileBuildsTimeline(tmp_path):
    shows = showManager.loadShowFile(_writeShow(tmp_path / "sample.yaml"))
    assert len(shows) == 1
    show = shows[0]
    assert show.name == "sample"
    assert show.errors == []
    assert [(step.startTime, step.duration, step.isHold) for step in show.steps] == [
        (0.0, 0.5, False),
        (0.5, 1.0, False),
        (1.5, 1.0, False),
        (2.5, showManager.HOLD_DISPLAY_SECONDS, True),
    ]
    assert show.totalDuration == 3.5
    assert [(channel.name, channel.isToken) for channel in show.channels] == [
        ("l_a", False),
        ("(leds)", True),
        ("l_b", False),
    ]
    assert show.tokens == ["leds", "color"]
    assert show.steps[2].otherSections == ["events"]

    # Colors hold until changed, fades blend from the previous color, and stop and tokens have no color
    assert show.channelState("l_a", 0.25).rgb == (255, 0, 0)
    fading = show.channelState("l_a", 0.6)
    assert fading.isFading and fading.rgb == (153, 0, 0)
    assert show.channelState("l_a", 0.75).rgb == (0, 0, 0)
    assert show.channelState("l_a", 3.0).rgb == (0, 0, 127)
    assert show.channelState("l_b", 0.25).segment is None
    assert show.channelState("l_b", 2.0).rgb == (255, 255, 255)
    assert show.channelState("l_b", 3.0).segment.setting.kind == "stop"
    assert show.channelState("(leds)", 3.0).segment.setting.value == "(color)"


def test_fadeFromUnsetStartsAtOff():
    show = parseShow([{"lights": {"l_a": "ffffff-f1s"}}], "fade")
    assert show.channelState("l_a", 0.5).rgb == (127, 127, 127)


def test_timingRules():
    # A first step with a time adds an empty step before it, and an empty last step with only a time ends the show
    show = parseShow([{"time": "1s", "lights": {"l_a": "red"}}, {"time": "3s"}], "timed")
    assert [(step.startTime, step.duration) for step in show.steps] == [(0.0, 1.0), (1.0, 2.0)]

    # Steps without a duration last one second
    show = parseShow([{"lights": {"l_a": "red"}}, {"lights": {"l_a": "blue"}}], "plain")
    assert [step.duration for step in show.steps] == [1.0, 1.0]


def test_showProblemsAreReported():
    assert parseShow({}, "bad").errors
    show = parseShow(["text", {"duration": 0}, {"duration": "x"}, {"lights": {"l_a": "nope"}}], "bad")
    assert len(show.errors) == 3
    assert len(show.steps) == 2
    # Colors are checked when the timeline is worked out, as they can be named in the project's config
    assert show.timelineErrors == ["Step 4: l_a has an invalid color 'nope'"]


def test_suggestedResolution():
    assert parseShow([{"duration": "250ms", "lights": {"l_a": "red"}}], "s").suggestedResolution() == 0.25
    assert parseShow([{"duration": "5s"}], "s").suggestedResolution() == showManager.MAX_RESOLUTION_SECONDS
    assert parseShow([{"duration": "1ms"}], "s").suggestedResolution() == showManager.MIN_RESOLUTION_SECONDS
    assert parseShow([{"lights": {"l_a": "red-f500ms"}}], "s").suggestedResolution() == 0.1
    assert parseShow([{"duration": -1}], "s").suggestedResolution() == showManager.MAX_RESOLUTION_SECONDS


def test_loadConfigFileShows(tmp_path):
    configFile = _writeShow(
        tmp_path / "config.yaml",
        "shows:\n  flash:\n    - lights:\n        l_a: red\n  blink:\n    - lights:\n        l_b: blue\n",
    )
    assert [show.name for show in showManager.loadShowFile(configFile)] == ["flash", "blink"]


def test_loadShowFileProblems(tmp_path):
    assert showManager.loadShowFile(_writeShow(tmp_path / "empty.yaml", "a: 1\n"))[0].errors
    assert "Could not read" in showManager.loadShowFile(_writeShow(tmp_path / "bad.yaml", "- [\n"))[0].errors[0]


def test_findShowFiles(tmp_path):
    machineShow = _writeShow(tmp_path / "shows" / "a.yaml")
    nestedShow = _writeShow(tmp_path / "shows" / "sub" / "b.yml")
    modeShow = _writeShow(tmp_path / "modes" / "attract" / "shows" / "c.yaml")
    _writeShow(tmp_path / "shows" / "notes.txt")
    assert showManager.findShowFiles(tmp_path) == [machineShow, nestedShow, modeShow]
    assert showManager.findShowFiles(tmp_path / "missing") == []


def _library(**shows) -> dict[str, showManager.MPFShow]:
    return {name: parseShow(steps, name) for name, steps in shows.items()}


def _colors(show, channel, times):
    return [show.channelState(channel, time).rgb for time in times]


def test_substituteTokensAndLightNames():
    assert showManager.substituteTokens("(color)%40", {"color": "red"}) == "red%40"
    assert showManager.substituteTokens("(color)", {}) == "(color)"
    assert showManager.resolveLightNames("(leds)", {"leds": "l_a, l_b,"}, False) == ["l_a", "l_b"]
    assert showManager.resolveLightNames("(leds)", {}, False) == ["(leds)"]
    assert showManager.resolveLightNames("(leds)", {}, True) == []
    assert showManager.resolveLightNames("(leds)", {"leds": "(lights)"}, True) == ["(lights)"]


def test_resolveSettingPreviewsTokens():
    setting = parseLightSetting("(color)%40")
    preview = showManager.resolveSetting(setting, {}, (255, 255, 255))
    assert (preview.rgb, preview.kind, preview.isToken) == ((102, 102, 102), "preview", True)
    assert showManager.resolveSetting(setting, {}, None).kind == "token"
    filled = showManager.resolveSetting(setting, {"color": "blue"}, (255, 255, 255))
    assert (filled.value, filled.rgb, filled.kind) == ("blue%40", (0, 0, 102), "color")
    assert showManager.resolveSetting(parseLightSetting("(a)(b)x"), {}, (1, 2, 3)).kind == "token"


def test_buildTimelineWithTokenValues():
    show = parseShow([{"lights": {"(leds)": "(color)", "l_a": "(color)%50"}}], "tokens")
    show.buildTimeline({"leds": "l_x, l_y", "color": "red"})
    assert [channel.name for channel in show.channels] == ["l_x", "l_y", "l_a"]
    assert show.channelState("l_y", 0.5).rgb == (255, 0, 0)
    assert show.channelState("l_a", 0.5).rgb == (127, 0, 0)


def test_nestedShowsPlayWithTheirTokens():
    library = _library(
        scan=[
            {"duration": "100ms", "lights": {"(light1)": "(color)", "(light2)": "off", "(unused)": "red"}},
            {"duration": "100ms", "lights": {"(light1)": "off", "(light2)": "(color)"}},
        ]
    )
    wrapper = parseShow(
        [
            {
                "time": 0,
                "shows": {"scan": {"loops": 0, "show_tokens": {"light1": "l_a", "light2": "l_b", "color": "red"}}},
            },
            {"time": "+1s", "shows": {"scan": {"show_tokens": {"light1": "l_b", "light2": "l_a", "color": "(tint)"}}}},
            {"time": "+1s"},
        ],
        "wrapper",
    )
    wrapper.buildTimeline({"tint": "blue"}, library)
    assert [channel.name for channel in wrapper.channels] == ["l_a", "l_b"]
    assert wrapper.tokens == ["tint"]

    # The first play runs once and then its colors are removed
    assert _colors(wrapper, "l_a", (0.05, 0.15, 0.5)) == [(255, 0, 0), (0, 0, 0), None]
    assert wrapper.channelState("l_a", 0.05).segment.showName == "scan"

    # The second play has different tokens so it starts again, looping until its player ends
    assert _colors(wrapper, "l_b", (1.05, 1.15, 1.25)) == [(0, 0, 255), (0, 0, 0), (0, 0, 255)]
    assert wrapper.timelineErrors == []


def test_nestedShowReplayRules():
    library = _library(
        blink=[{"duration": "100ms", "lights": {"l_a": "red"}}, {"duration": "100ms", "lights": {"l_a": "off"}}],
        hold=[{"duration": -1, "lights": {"l_h": "green"}}],
        single=[{"duration": "100ms", "lights": {"l_s": "white"}}],
    )
    show = parseShow(
        [
            {"duration": "150ms", "shows": {"blink": {"speed": 1}, "hold": "play", "single": {"loops": 5}}},
            {"duration": "150ms", "shows": {"blink": {"speed": 1}}},
            {"duration": "500ms", "shows": {"hold": "stop", "blink": {"speed": "fast", "loops": "x"}}},
        ],
        "replays",
    )
    show.buildTimeline({}, library)

    # Playing again with the same settings keeps the show running, rather than starting it again
    assert _colors(show, "l_a", (0.05, 0.15, 0.25)) == [(255, 0, 0), (0, 0, 0), (255, 0, 0)]
    # A hold step lasts until the show is stopped
    assert _colors(show, "l_h", (0.25, 0.35)) == [(0, 128, 0), None]
    # A one step show plays once whatever its loops are
    assert _colors(show, "l_s", (0.05, 0.15)) == [(255, 255, 255), None]


def test_stopRevealsTheColorBelow():
    library = _library(under=[{"duration": -1, "lights": {"l_a": "blue"}}])
    show = parseShow(
        [{"duration": "1s", "shows": {"under": "play"}, "lights": {"l_a": "red"}}, {"lights": {"l_a": "stop"}}],
        "layers",
    )
    show.buildTimeline({}, library)
    assert _colors(show, "l_a", (0.5, 1.5)) == [(255, 0, 0), (0, 0, 255)]

    # With nothing below, stop leaves the light unset by the show
    show.buildTimeline({}, {})
    assert show.channelState("l_a", 1.5).segment.setting.kind == "stop"
    assert show.timelineErrors == ["Show under is not in this project"]


def test_nestedShowsDepthLimit():
    library = _library(loop=[{"duration": "1s", "shows": {"loop": {"show_tokens": {"n": "(n)x"}}}}])
    library["loop"].buildTimeline({"n": "1"}, library)
    assert library["loop"].timelineErrors == ["Shows play each other too deeply to show them all"]


def test_builtInShows():
    shows = showManager.builtInShows()
    assert {"flash", "on", "off", "led_color", "flash_color"} <= set(shows)
    tracker = parseShow([{"shows": {"led_color": {"show_tokens": {"lights": "l_a", "color": "purple"}}}}], "tracker")
    tracker.buildTimeline({}, shows)
    assert [channel.name for channel in tracker.channels] == ["l_a"]
    assert tracker.channelState("l_a", 0.5).rgb == (128, 0, 128)


def test_suggestedResolutionFollowsNestedShows():
    library = _library(
        fast=[{"duration": "20ms", "lights": {"l_a": "red"}}, {"duration": "20ms", "lights": {"l_a": "off"}}]
    )
    show = parseShow([{"duration": "1s", "shows": {"fast": "play"}}], "slow")
    show.buildTimeline({}, library)
    assert show.suggestedResolution() == 0.02


def test_laterSectionInAStepIsOnTop():
    library = _library(under=[{"duration": -1, "lights": {"l_a": "blue"}}])
    show = parseShow([{"duration": "1s", "lights": {"l_a": "red"}, "shows": {"under": "play"}}], "order")
    show.buildTimeline({}, library)
    assert show.channelState("l_a", 0.5).rgb == (0, 0, 255)


def test_soundPlaysFromShowSteps():
    show = parseShow(
        [
            {"time": 0, "sounds": {"music": {"start_at": "30s", "fade_in": "1s", "volume": "-6db"}, "(fx)": "play"}},
            {"time": "+1s", "sounds": {"zap": {"loops": "2", "delay": "250ms", "fade_out": "x"}}},
            {"time": "+1s", "sounds": {"music": {"action": "stop"}, "zap": "stop_looping", "fx": {"volume": "loud"}}},
            {"time": "+1s", "sounds": {"fx": {"action": "replace", "volume": "0.5"}}},
            {"time": "+1s"},
        ],
        "sounds",
    )
    show.buildTimeline({"fx": "boom"})
    plays = {(play.soundName, play.startTime): play for play in show.soundPlays}
    music = plays[("music", 0.0)]
    assert (music.startAt, music.fadeIn, round(music.volume, 3), music.stopTime) == (30.0, 1.0, 0.501, 2.0)
    zap = plays[("zap", 1.25)]
    assert (zap.loops, zap.fadeOut, zap.stopLoopingTime) == (2, 0.0, 2.0)
    assert plays[("boom", 0.0)].stepNumber == 1
    # Replacing a sound stops the plays of it already going, and a sound with no tokens filled in keeps its name
    assert plays[("fx", 2.0)].stopTime == 3.0
    assert plays[("fx", 2.0)].volume == 1.0
    assert plays[("fx", 3.0)].volume == 0.5
    assert show.tokens == ["fx"]
    assert "sounds" not in show.steps[0].otherSections


def test_soundPlayTiming():
    play = showManager.SoundPlay("music", 1.0, startAt=2.0)
    assert play.endTime(10.0) == 9.0
    assert play.positionAt(0.5, 10.0) is None
    assert play.positionAt(1.5, 10.0) == 2.5
    assert play.positionAt(9.0, 10.0) is None
    assert play.positionAt(1.0, 0.0) is None

    looping = showManager.SoundPlay("loop", 0.0, loops=-1)
    assert looping.endTime(2.0) is None
    assert looping.positionAt(5.5, 2.0) == 1.5
    looping.stopLoopingTime = 3.0
    assert looping.endTime(2.0) == 4.0
    assert showManager.SoundPlay("twice", 0.0, loops=1).endTime(2.0) == 4.0
    assert showManager.SoundPlay("stopped", 0.0, loops=-1, stopTime=3.0).endTime(2.0) == 3.0

    fading = showManager.SoundPlay("fade", 0.0, volume=0.5, fadeIn=1.0, fadeOut=1.0, stopTime=4.0)
    assert fading.gainAt(0.5, 10.0) == 0.25
    assert fading.gainAt(2.0, 10.0) == 0.5
    assert fading.gainAt(3.5, 10.0) == 0.25
    # A fade out only applies when the sound is stopped
    assert showManager.SoundPlay("natural", 0.0, fadeOut=1.0).gainAt(9.5, 10.0) == 1.0


def test_nestedShowSoundsArePlayed():
    library = _library(jingle=[{"duration": "1s", "sounds": {"(tune)": {"loops": 0}}}])
    show = parseShow([{"time": "500ms", "shows": {"jingle": {"show_tokens": {"tune": "chime"}}}}], "parent")
    show.buildTimeline({}, library)
    assert [(play.soundName, play.startTime, play.showName) for play in show.soundPlays] == [("chime", 0.5, "jingle")]


def test_findSoundFiles(tmp_path):
    music = tmp_path / "sounds" / "music" / "theme.ogg"
    effect = tmp_path / "modes" / "base" / "sounds" / "zap.WAV"
    for path in (music, effect, tmp_path / ".godot" / "imported" / "theme.ogg", tmp_path / "sounds" / "notes.txt"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "config.yaml").write_text(
        "sounds:\n  intro:\n    file: theme.ogg\n  gone:\n    file: x.wav\n"
    )
    (tmp_path / "config" / "bad.yaml").write_text("- [\n")
    (tmp_path / "modes" / "base" / "config").mkdir(parents=True)
    (tmp_path / "modes" / "base" / "config" / "base.yaml").write_text("sounds: none\n")
    assert showManager.findSoundFiles(tmp_path) == {"zap": effect, "theme": music, "intro": music}
    assert showManager.findSoundFiles(tmp_path / "missing") == {}


def test_fadeTokensAndInvalidFades():
    # A fade can be a show token, in the short or full form, which fades once the show is given a value for it
    for lightValue in ("red-f(fade)", {"color": "red", "fade": "(fade)"}):
        show = parseShow([{"lights": {"l_a": lightValue}}], "fades")
        assert show.errors == []
        assert show.tokens == ["fade"]
        setting = show.steps[0].lights["l_a"]
        assert (setting.fadeText, setting.fadeMs) == ("(fade)", 0)
        assert show.channelState("l_a", 0.25).rgb == (255, 0, 0)
        show.buildTimeline({"fade": "500ms"})
        assert show.channelState("l_a", 0.25).rgb == (127, 0, 0)
        show.buildTimeline({"fade": "soon"})
        assert show.channelState("l_a", 0.25).rgb == (255, 0, 0)

    # A fade that is not a time is drawn as no fade and reported
    show = parseShow([{"lights": {"l_a": "red-fabc", "l_b": {"color": "blue", "fade": None}}}], "bad fades")
    assert show.errors == ["Step 1: l_a has an invalid fade 'abc'"]
    assert show.steps[0].lights["l_a"].fadeMs == 0
    assert showManager.fadeTextToMs("") == 0
    assert showManager.fadeTextToMs("(fade)") is None


def test_firstStepTimeToken():
    show = parseShow([{"time": "(start)", "lights": {"l_a": "red"}}, {"time": "+1s"}], "token time")
    assert show.errors == ["Step 1 has an invalid time '(start)'"]
    assert [(step.startTime, step.duration) for step in show.steps] == [(0.0, 1.0)]


def _writeConfig(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_loadNamedColorsFollowsConfigIncludes(tmp_path):
    configFolder = tmp_path / "config"
    _writeConfig(
        configFolder / "config.yaml",
        "config:\n  - common.yaml\n  - hardware_fast.yaml\n  - missing.yaml\nnamed_colors:\n  color_main: ff0000\n"
        "  board_color: '000001'\n",
    )
    _writeConfig(
        configFolder / "common.yaml",
        "config: colors.yaml, common.yaml\nnamed_colors:\n  board_color: '000002'\n",
    )
    _writeConfig(
        configFolder / "colors.yaml",
        "named_colors:\n  color_grunt: FF6611\n  Color_Space: 0044aa\n  color_dim_grunt: color_grunt%50\n"
        "  color_bad: notacolor\n  board_color: '000003'\n",
    )
    _writeConfig(configFolder / "hardware_fast.yaml", "named_colors:\n  board_color: ff6611\n")
    _writeConfig(configFolder / "hardware_spike.yaml", "named_colors:\n  board_color: ffffff\n")
    _writeConfig(configFolder / "broken.yaml", "- [\n")

    namedColors = showManager.loadNamedColors(tmp_path)
    # Included files override the file including them, later files override earlier ones, and files that are not
    # included (like another platform's hardware config) are not used
    assert namedColors == {
        "color_main": (255, 0, 0),
        "board_color": (255, 102, 17),
        "color_grunt": (255, 102, 17),
        "color_space": (0, 68, 170),
        "color_dim_grunt": (127, 51, 8),
    }
    assert showManager.loadNamedColors(tmp_path / "missing") == {}

    # Without config.yaml every config file is read, in name order, without following includes
    (configFolder / "config.yaml").unlink()
    _writeConfig(configFolder / "list.yaml", "- not a config\n")
    assert showManager.loadNamedColors(tmp_path)["board_color"] == (255, 255, 255)


def test_namedColorsInShows():
    namedColors = {"color_grunt": (255, 102, 17), "red": (200, 0, 0)}
    assert resolveColor("color_grunt", namedColors) == ((255, 102, 17), "color")
    assert resolveColor("COLOR_GRUNT%50", namedColors) == ((127, 51, 8), "color")
    assert resolveColor("color_grunt") == (None, "invalid")
    # The project's colors are used before MPF's own color names, as MPF adds them to its own
    assert resolveColor("red", namedColors) == ((200, 0, 0), "color")

    show = parseShow([{"lights": {"l_a": "color_grunt", "(leds)": "(color)%40"}}], "named")
    assert show.timelineErrors == ["Step 1: l_a has an invalid color 'color_grunt'"]
    show.buildTimeline({"leds": "l_b", "color": "color_grunt"}, namedColors=namedColors)
    assert show.timelineErrors == []
    assert show.channelState("l_a", 0.5).rgb == (255, 102, 17)
    assert show.channelState("l_b", 0.5).rgb == (102, 40, 6)

    # A nested show's invalid colors name the show they are in
    library = {"inner": parseShow([{"lights": {"l_c": "color_unknown"}}], "inner")}
    outer = parseShow([{"shows": {"inner": "play"}}], "outer")
    outer.buildTimeline({}, library, namedColors=namedColors)
    assert outer.timelineErrors == ["Show inner step 1: l_c has an invalid color 'color_unknown'"]


def test_nestedShowKeysRunSeveralCopies():
    library = _library(flash=[{"duration": -1, "lights": {"(leds)": "(color)"}}])
    show = parseShow(
        [
            {
                "duration": "1s",
                "shows": {"flash": {"key": "flash_a", "show_tokens": {"leds": "l_a", "color": "red"}}},
            },
            {
                "duration": "1s",
                "shows": {
                    "flash": {"key": "flash_b", "show_tokens": {"leds": "l_b", "color": "blue"}},
                    "other": {"key": "flash_a", "show": "flash", "show_tokens": {"leds": "l_c", "color": "lime"}},
                },
            },
        ],
        "keys",
    )
    show.buildTimeline({}, library)
    assert show.timelineErrors == []
    # A key names the running copy, not the show, so both copies of flash run, and playing under flash_a again
    # replaces the first copy
    assert [show.channelState(light, 1.5).rgb for light in ("l_a", "l_b", "l_c")] == [None, (0, 0, 255), (0, 255, 0)]
    assert show.channelState("l_a", 0.5).rgb == (255, 0, 0)


def test_loadConfigShows(tmp_path):
    _writeConfig(
        tmp_path / "config" / "config.yaml",
        "config: shows_fast.yaml\nshows:\n  pulse:\n    - lights:\n        l_a: red\n  replaced:\n    - lights:\n"
        "        l_a: red\n",
    )
    _writeConfig(tmp_path / "config" / "shows_fast.yaml", "shows:\n  replaced:\n    - lights:\n        l_a: blue\n")
    _writeConfig(tmp_path / "config" / "shows_spike.yaml", "shows:\n  spike_only:\n    - lights:\n        l_a: lime\n")
    # A mode's shows come from its own config file and the files it includes
    _writeConfig(
        tmp_path / "modes" / "base" / "config" / "base.yaml",
        "config:\n  - base_shows.yaml\nmode:\n  priority: 100\n",
    )
    _writeConfig(
        tmp_path / "modes" / "base" / "config" / "base_shows.yaml",
        "shows:\n  color_flashing_fast:\n    - duration: 100ms\n      lights:\n        (leds): (color)\n"
        "    - duration: 100ms\n      lights:\n        (leds): off\n  not_a_show: 5\n",
    )
    # A mode without its own config file has all its config files read
    _writeConfig(tmp_path / "modes" / "loose" / "config" / "extra.yaml", "shows:\n  loose_show:\n    - lights: {}\n")
    (tmp_path / "modes" / "README.md").write_text("not a mode")

    shows = {show.name: show for show in showManager.loadConfigShows(tmp_path)}
    assert set(shows) == {"pulse", "replaced", "color_flashing_fast", "not_a_show", "loose_show"}
    assert shows["replaced"].steps[0].lights["l_a"].value == "blue"
    assert shows["replaced"].sourcePath == tmp_path / "config" / "shows_fast.yaml"
    assert shows["color_flashing_fast"].sourcePath == tmp_path / "modes" / "base" / "config" / "base_shows.yaml"
    assert shows["not_a_show"].errors
    assert [path.name for path, _data in showManager.machineConfigs(tmp_path)] == ["config.yaml", "shows_fast.yaml"]
    assert [path.name for path, _data in showManager.modeConfigs(tmp_path)] == [
        "base.yaml",
        "base_shows.yaml",
        "extra.yaml",
    ]
    assert showManager.loadConfigShows(tmp_path / "missing") == []

    # A show file can play a show defined in a mode's config
    ladder = parseShow(
        [{"duration": "1s", "shows": {"color_flashing_fast": {"show_tokens": {"leds": "l_x"}}}}], "ladder"
    )
    ladder.buildTimeline({}, shows)
    assert ladder.timelineErrors == []
    assert ladder.channelState("l_x", 0.05).rgb == (255, 255, 255)
    assert ladder.channelState("l_x", 0.15).rgb == (0, 0, 0)


def test_filesAreReadAgainOnlyWhenTheyChange(tmp_path, monkeypatch):
    showFile = tmp_path / "shows" / "pulse.yaml"
    _writeShow(showFile, "- lights:\n    l_a: red\n")
    configFile = tmp_path / "config" / "config.yaml"
    _writeConfig(configFile, "named_colors:\n  color_a: ff0000\n")
    reads = []
    loadText = showManager.yamlInterfacer.loadYAMLText
    loadSections = showManager.yamlInterfacer.loadYAMLTextSections
    monkeypatch.setattr(showManager.yamlInterfacer, "loadYAMLText", lambda path: reads.append(path) or loadText(path))
    monkeypatch.setattr(
        showManager.yamlInterfacer,
        "loadYAMLTextSections",
        lambda path, sections: reads.append(path) or loadSections(path, sections),
    )

    for _ in range(2):
        assert showManager.loadShowFile(showFile)[0].steps[0].lights["l_a"].value == "red"
        assert showManager.loadNamedColors(tmp_path) == {"color_a": (255, 0, 0)}
    assert reads == [showFile, configFile]

    # A changed file is read again
    showFile.write_text("- lights:\n    l_a: blue\n    l_b: lime\n")
    configFile.write_text("named_colors:\n  color_a: 00ff00\n  color_b: 0000ff\n")
    assert showManager.loadShowFile(showFile)[0].steps[0].lights["l_a"].value == "blue"
    assert showManager.loadNamedColors(tmp_path)["color_a"] == (0, 255, 0)
    assert reads == [showFile, configFile, showFile, configFile]

    # A file that cannot be read is reported each time without being read again
    brokenFile = tmp_path / "shows" / "broken.yaml"
    brokenFile.write_text("- [\n")
    for _ in range(2):
        assert "Could not read" in showManager.loadShowFile(brokenFile)[0].errors[0]
    assert reads.count(brokenFile) == 1
    assert "Could not read" in showManager.loadShowFile(tmp_path / "shows" / "missing.yaml")[0].errors[0]


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("40ms", 0.04),
        (" 40 MS ", 0.04),
        ("33", 0.033),
        ("12.5msec", 0.0125),
        ("0.5s", 0.5),
        ("2sec", 2.0),
        (".25s", 0.25),
        ("30fps", 1 / 30),
        ("1000fps", 0.001),
        ("1ms", 0.001),
        ("60s", 60.0),
        ("0.5ms", None),
        ("61s", None),
        ("0fps", None),
        ("0", None),
        ("fast", None),
        ("-40ms", None),
        ("40 minutes", None),
        ("", None),
    ],
)
def test_parseTimebase(text, seconds):
    result = showManager.parseTimebase(text)
    assert result == (pytest.approx(seconds) if seconds is not None else None)


def test_segmentsKnowWhichShowsSetThem():
    library = _library(
        middle=[{"duration": "1s", "lights": {"l_m": "red"}, "shows": {"inner": "play"}}],
        inner=[{"duration": -1, "lights": {"l_i": "blue"}}],
    )
    show = parseShow([{"duration": "1s", "lights": {"l_own": "white"}, "shows": {"middle": "play"}}], "top")
    show.buildTimeline({}, library)

    # The show's own steps set its lights directly, while shows it plays are named down to the one setting the light
    ownSegment = show.channelState("l_own", 0.5).segment
    assert (ownSegment.showPath, ownSegment.isFromOtherShow) == ((), False)
    assert show.channelState("l_m", 0.5).segment.showPath == ("middle",)
    assert show.channelState("l_i", 0.5).segment.showPath == ("middle", "inner")
    assert show.channelState("l_i", 0.5).segment.showName == "inner"
    assert show.channelShowPaths("l_own") == []
    assert show.channelShowPaths("l_i") == [("middle", "inner")]
    assert show.channelShowPaths("missing") == []


def test_channelShowPathsListsEachShowOnce():
    library = _library(
        first=[{"duration": "100ms", "lights": {"l_a": "red"}}, {"duration": "100ms", "lights": {"l_a": "off"}}],
        second=[{"duration": "100ms", "lights": {"l_a": "blue"}}],
    )
    show = parseShow(
        [
            {"duration": "1s", "shows": {"first": {"loops": 2}}},
            {"duration": "1s", "shows": {"second": "play"}, "lights": {"l_a": "lime"}},
        ],
        "both",
    )
    show.buildTimeline({}, library)
    assert show.channelShowPaths("l_a") == [("first",), ("second",)]
    # Where the show's own steps set the light last, it is set directly
    assert show.channelState("l_a", 1.5).segment.showPath == ()


@pytest.mark.parametrize(
    ("seconds", "text"),
    [(1.0, "1s"), (2.0, "2s"), (0.5, "500ms"), (1.25, "1250ms"), (0.0, "0ms"), (0.0126, "13ms"), (60.0, "60s")],
)
def test_formatDuration(seconds, text):
    assert showManager.formatDuration(seconds) == text
    assert timeToSeconds(text) == pytest.approx(seconds, abs=0.0005)


def test_lightSettingToData():
    assert showManager.lightSettingToData(parseLightSetting("red")) == "red"
    assert showManager.lightSettingToData(parseLightSetting("red - f 200ms")) == "red-f200ms"
    assert showManager.lightSettingToData(parseLightSetting("(color)-f(fade)")) == "(color)-f(fade)"

    # The full form is written back as it was, keeping settings the viewer does not use
    fullForm = parseLightSetting({"color": "blue", "fade": "1s", "priority": "2"})
    assert showManager.lightSettingToData(fullForm) == {"color": "blue", "fade": "1s", "priority": "2"}
    assert showManager.lightSettingToData(parseLightSetting({"fade": "100"})) == {"fade": "100", "color": "white"}

    # Changes made to a setting are written, and a fade that is taken away is left out
    fullForm.value, fullForm.fadeText = "green", ""
    assert showManager.lightSettingToData(fullForm) == {"color": "green", "priority": "2"}


def test_stepToData():
    show = parseShow(
        [
            {
                "time": 0,
                "shows": {"blink": {"loops": "0"}},
                "leds": {"l_x": "red"},
                "lights": {"l_a": "blue-f1s"},
                "events": ["started", "go"],
                "slides": {"my_slide": {"priority": "100"}},
            },
            {"time": "+1", "sounds": {"tone": {"loops": "1"}}, "lights": {"l_a": "stop"}},
            {"duration": -1, "lights": {"l_a": "off"}},
        ],
        "steps",
    )
    first, second, hold = (showManager.stepToData(step) for step in show.steps)

    # Every section is written back in the order it was read, with its duration first
    assert list(first) == ["duration", "shows", "leds", "lights", "events", "slides"]
    assert first == {
        "duration": "1s",
        "shows": {"blink": {"loops": "0"}},
        "leds": {"l_x": "red"},
        "lights": {"l_a": "blue-f1s"},
        "events": ["started", "go"],
        "slides": {"my_slide": {"priority": "100"}},
    }
    assert second == {"duration": "1s", "sounds": {"tone": {"loops": "1"}}, "lights": {"l_a": "stop"}}
    assert hold == {"duration": -1, "lights": {"l_a": "off"}}


def test_stepToDataWithNewSections():
    step = showManager.ShowStep(1, 0.0, 0.25)
    step.lights["l_a"] = parseLightSetting("red")
    step.shows["blink"] = "play"
    step.sounds["tone"] = "play"
    assert list(showManager.stepToData(step)) == ["duration", "lights", "shows", "sounds"]

    # Shows that set the lights first are written before the lights
    step.showsFirst = True
    assert list(showManager.stepToData(step)) == ["duration", "shows", "lights", "sounds"]
    assert showManager.stepToData(showManager.ShowStep(1, 0.0, 0.5)) == {"duration": "500ms"}


def test_showToDataStartsWithTheFirstStepsTime():
    show = parseShow([{"time": "2s", "lights": {"l_a": "red"}}, {"time": "3s", "lights": {"l_a": "off"}}], "late")
    assert showManager.showToData(show) == [
        {"duration": "2s"},
        {"duration": "1s", "lights": {"l_a": "red"}},
        {"duration": "1s", "lights": {"l_a": "off"}},
    ]
    assert showManager.showToData(showManager.MPFShow("empty", None)) == []


def _sameTimeline(first: showManager.MPFShow, second: showManager.MPFShow) -> None:
    assert first.totalDuration == pytest.approx(second.totalDuration)
    assert [channel.name for channel in first.channels] == [channel.name for channel in second.channels]
    for step in first.steps:
        for channel in first.channels:
            for atTime in (step.startTime, step.startTime + step.duration / 2):
                firstState, secondState = (
                    first.channelState(channel.name, atTime),
                    second.channelState(channel.name, atTime),
                )
                assert firstState.rgb == secondState.rgb
                assert (firstState.segment is None) == (secondState.segment is None)
                if firstState.segment is not None:
                    assert firstState.segment.setting.kind == secondState.segment.setting.kind


def test_exportShowFileRoundTrip(tmp_path):
    original = showManager.loadShowFile(_writeShow(tmp_path / "shows" / "sample.yaml"))[0]
    exported = tmp_path / "exported" / "sample.yaml"
    showManager.exportShowFile(original, exported)

    # The file starts with the show version MPF looks for, and its steps start at the start of the line
    text = exported.read_text()
    assert text.startswith("#show_version=6\n- duration: 500ms\n  lights:\n    l_a: red\n")
    assert "l_a: 000000-f250ms" in text
    assert "- duration: -1\n" in text
    assert not list(exported.parent.glob("*.tmp"))

    # Reading the exported file gives the same show
    reloaded = showManager.loadShowFile(exported)[0]
    assert reloaded.errors == original.errors
    assert [(step.startTime, step.duration, step.isHold) for step in reloaded.steps] == [
        (step.startTime, step.duration, step.isHold) for step in original.steps
    ]
    assert [step.otherData for step in reloaded.steps] == [step.otherData for step in original.steps]
    _sameTimeline(original, reloaded)

    # Exporting the exported show gives the same file
    showManager.exportShowFile(reloaded, tmp_path / "again.yaml")
    assert (tmp_path / "again.yaml").read_text() == text


def test_exportShowFileHeader(tmp_path):
    show = parseShow([{"lights": {"l_a": "on"}}], "plain")
    showManager.exportShowFile(show, tmp_path / "plain.yaml", headerString=None)
    assert (tmp_path / "plain.yaml").read_text() == "- duration: 1s\n  lights:\n    l_a: on\n"
    showManager.exportShowFile(show, tmp_path / "custom.yaml", headerString="#show_version=6\n# made by hand")
    assert (tmp_path / "custom.yaml").read_text().startswith("#show_version=6\n# made by hand\n- duration: 1s\n")


def test_exportedNestedShowsPlayTheSame(tmp_path):
    library = _library(
        scan=[
            {"duration": "100ms", "lights": {"(light1)": "(color)"}},
            {"duration": "100ms", "lights": {"(light1)": {"color": "off", "fade": "50ms"}}},
        ]
    )
    wrapper = parseShow(
        [
            {"time": 0, "shows": {"scan": {"loops": "2", "show_tokens": {"light1": "l_a", "color": "red"}}}},
            {"time": "+1s", "lights": {"l_b": "blue"}, "sounds": {"tone": {"volume": "0.5"}}},
            {"time": "+1s"},
        ],
        "wrapper",
    )
    showManager.exportShowFile(library["scan"], tmp_path / "shows" / "scan.yaml")
    showManager.exportShowFile(wrapper, tmp_path / "shows" / "wrapper.yaml")
    reloadedLibrary = {
        show.name: show for path in tmp_path.glob("shows/*.yaml") for show in showManager.loadShowFile(path)
    }

    wrapper.buildTimeline({}, library)
    reloadedWrapper = reloadedLibrary["wrapper"]
    reloadedWrapper.buildTimeline({}, reloadedLibrary)
    _sameTimeline(wrapper, reloadedWrapper)
    assert reloadedWrapper.channelState("l_a", 0.15).isFading
    assert [play.volume for play in reloadedWrapper.soundPlays] == [0.5]


def test_exportShowsSection(tmp_path):
    shows = [
        parseShow([{"lights": {"l_a": "red"}}], "first"),
        parseShow([{"duration": -1, "leds": {"l_b": "on"}}], "hold"),
    ]
    configFile = tmp_path / "config" / "shows.yaml"
    showManager.exportShowsSection(shows, configFile, "#config_version=6")
    assert configFile.read_text().startswith("#config_version=6\nshows:\n  first:\n")

    reloaded = showManager.loadShowFile(configFile)
    assert [show.name for show in reloaded] == ["first", "hold"]
    assert reloaded[1].steps[0].isHold
    assert reloaded[1].steps[0].lightSections == {"l_b": "leds"}
    _sameTimeline(shows[0], reloaded[0])


COMMENTED_SHOW = """\
#show_version=6
# Attract mode sweep
- time: 0  # start
  # the lights
  lights:
    l_a: red  # red one
    l_b: red - f 200ms
    (leds): 000000
  shows:
    blink:
      loops: 0  # once
# between steps
- time: 500ms
  lights:
    l_a: off
  events: foo  # ev
# before end
- time: 1s  # end of show
# trailing
"""


def test_exportKeepsComments(tmp_path):
    show = showManager.loadShowFile(_writeShow(tmp_path / "shows" / "sweep.yaml", COMMENTED_SHOW))[0]
    showManager.exportShowFile(show, tmp_path / "out.yaml")

    # Times are written as durations, keeping their comments, and values that are the same are kept as written.  The
    # last step only marks the end of the show so it is left out, with its comments kept where it was
    assert (tmp_path / "out.yaml").read_text() == (
        "#show_version=6\n"
        "# Attract mode sweep\n"
        "- duration: 500ms # start\n"
        "  # the lights\n"
        "  lights:\n"
        "    l_a: red  # red one\n"
        "    l_b: red - f 200ms\n"
        "    (leds): 000000\n"
        "  shows:\n"
        "    blink:\n"
        "      loops: 0  # once\n"
        "# between steps\n"
        "- duration: 500ms\n"
        "  lights:\n"
        "    l_a: off\n"
        "  events: foo  # ev\n"
        "# before end\n"
        "# end of show\n"
        "# trailing\n"
    )
    reloaded = showManager.loadShowFile(tmp_path / "out.yaml")[0]
    _sameTimeline(show, reloaded)

    # Exporting the exported file changes nothing
    showManager.exportShowFile(reloaded, tmp_path / "again.yaml")
    assert (tmp_path / "again.yaml").read_text() == (tmp_path / "out.yaml").read_text()

    # Without keeping comments the show is written plainly, with the show version line
    showManager.exportShowFile(show, tmp_path / "plain.yaml", keepComments=False)
    plainText = (tmp_path / "plain.yaml").read_text()
    assert plainText.startswith("#show_version=6\n- duration: 500ms\n")
    assert "#" not in plainText.split("\n", 1)[1]


def test_exportKeepsCommentsOfChangedShows(tmp_path):
    show = showManager.loadShowFile(_writeShow(tmp_path / "shows" / "sweep.yaml", COMMENTED_SHOW))[0]
    firstStep, secondStep = show.steps
    firstStep.lights["l_a"] = parseLightSetting("blue")
    firstStep.lights.pop("(leds)")
    firstStep.shows["blink"] = {"loops": "3"}
    secondStep.lights["l_new"] = parseLightSetting("lime-f1s")
    secondStep.otherData.pop("events")
    secondStep.duration = 0.25
    showManager.exportShowFile(show, tmp_path / "out.yaml")

    # Changed values keep the comments on their lines, and the comments after what was taken out are kept
    assert (tmp_path / "out.yaml").read_text() == (
        "#show_version=6\n"
        "# Attract mode sweep\n"
        "- duration: 500ms # start\n"
        "  # the lights\n"
        "  lights:\n"
        "    l_a: blue # red one\n"
        "    l_b: red - f 200ms\n"
        "  shows:\n"
        "    blink:\n"
        "      loops: '3' # once\n"
        "# between steps\n"
        "- duration: 250ms\n"
        "  lights:\n"
        "    l_a: off\n"
        "    l_new: lime-f1s\n"
        "# before end\n"
        "# end of show\n"
        "# trailing\n"
    )


def test_exportAddsStepsAndHeader(tmp_path):
    showFile = _writeShow(
        tmp_path / "late.yaml", "# starts late\n- time: 2s  # first\n  lights:\n    l_a: red\n- time: 3s\n"
    )
    show = showManager.loadShowFile(showFile)[0]
    show.steps.append(showManager.ShowStep(9, 3.0, 0.5, lights={"l_b": parseLightSetting("on")}))
    showManager.exportShowFile(show, tmp_path / "out.yaml")

    # The empty step a late first step starts with is added, and the show version line goes above the file's comments
    assert (tmp_path / "out.yaml").read_text() == (
        "#show_version=6\n"
        "# starts late\n"
        "- duration: 2s\n"
        "- duration: 1s # first\n"
        "  lights:\n"
        "    l_a: red\n"
        "- duration: 500ms\n"
        "  lights:\n"
        "    l_b: on\n"
    )


def test_exportKeepsCommentsOfStepsLeftOut(tmp_path):
    showFile = _writeShow(
        tmp_path / "bad.yaml",
        "#show_version=6\n- not a step  # junk\n# real start\n- duration: 1s\n  lights:\n    l_a: red  # keep\n",
    )
    showManager.exportShowFile(showManager.loadShowFile(showFile)[0], tmp_path / "out.yaml")
    assert (tmp_path / "out.yaml").read_text() == (
        "#show_version=6\n# junk\n# real start\n- duration: 1s\n  lights:\n    l_a: red  # keep\n"
    )


def test_exportWithoutItsFile(tmp_path):
    # A show whose file has gone, or that has no file, or whose file no longer has its steps, is written plainly
    showFile = _writeShow(tmp_path / "gone.yaml", "# comment\n- lights:\n    l_a: red\n")
    show = showManager.loadShowFile(showFile)[0]
    showFile.write_text("# comment\n- not: a show\n- lights: {}\n")
    assert showManager.showToCommentedData(show) == [{"duration": "1s", "lights": {"l_a": "red"}}]
    showFile.write_text(": bad yaml : [")
    assert showManager.showToCommentedData(show) == [{"duration": "1s", "lights": {"l_a": "red"}}]
    showFile.unlink()
    assert showManager.showToCommentedData(show) == [{"duration": "1s", "lights": {"l_a": "red"}}]
    assert showManager.showToCommentedData(parseShow([{"lights": {"l_a": "on"}}], "new")) == [
        {"duration": "1s", "lights": {"l_a": "on"}}
    ]


CONFIG_WITH_SHOWS = """\
#config_version=6
lights:
  l_a: {number: 1}
shows:
  # the pulse show
  pulse:
    - duration: 1s  # one
      lights:
        l_a: red
    # second step
    - lights:
        l_a: off
  # the other show
  other:
    - lights: {l_b: on}
"""


def test_exportShowsFromConfigsKeepComments(tmp_path):
    configFile = _writeShow(tmp_path / "config" / "config.yaml", CONFIG_WITH_SHOWS)
    pulse, other = showManager.loadShowFile(configFile)

    # A show from a config is written to a show file with the comments above its name, but not those after it, which
    # are above the next show
    showManager.exportShowFile(pulse, tmp_path / "pulse.yaml")
    pulseText = (tmp_path / "pulse.yaml").read_text()
    assert pulseText.startswith("#show_version=6\n# the pulse show\n- duration: 1s")
    assert "# second step" in pulseText
    assert "other show" not in pulseText

    # Written back to a shows: section, each show's comments are above its name again
    pulse.steps[0].lights["l_a"].value = "blue"
    showManager.exportShowsSection([pulse, other], tmp_path / "shows.yaml", "#config_version=6")
    assert (tmp_path / "shows.yaml").read_text() == (
        "#config_version=6\n"
        "shows:\n"
        "  # the pulse show\n"
        "  pulse:\n"
        "    - duration: 1s  # one\n"
        "      lights:\n"
        "        l_a: blue\n"
        "    # second step\n"
        "    - duration: 1s\n"
        "      lights:\n"
        "        l_a: off\n"
        "  # the other show\n"
        "  other:\n"
        "    - duration: 1s\n"
        "      lights: {l_b: on}\n"
    )


def test_exportShowsSectionFromShowFiles(tmp_path):
    showFile = _writeShow(tmp_path / "shows" / "sweep.yaml", "#show_version=6\n# a sweep\n- lights:\n    l_a: red\n")
    showManager.exportShowsSection([showManager.loadShowFile(showFile)[0]], tmp_path / "shows.yaml")

    # The show version line is left out, as it is only for show files
    assert (tmp_path / "shows.yaml").read_text() == (
        "shows:\n  # a sweep\n  sweep:\n    - duration: 1s\n      lights:\n        l_a: red\n"
    )


def test_exportMergesListsAndFlowMappings(tmp_path):
    showFile = _writeShow(
        tmp_path / "lists.yaml",
        "- duration: 1  # a bare number of seconds\n"
        "  lights: {l_a: red, l_b: blue}  # flow\n"
        "  events:\n"
        "    - first  # one\n"
        "    # before second\n"
        "    - second\n"
        "    - third  # three\n"
        "# after\n"
        "- duration: 1s\n"
        "  lights: {l_c: on}\n",
    )
    show = showManager.loadShowFile(showFile)[0]
    show.steps[0].lights["l_b"] = parseLightSetting("green")
    show.steps[0].otherData["events"] = ["first", "changed"]
    show.steps[1].otherData["events"] = ["added"]
    showManager.exportShowFile(show, tmp_path / "out.yaml", headerString=None)

    # A duration that is the same keeps how it was written, a flow mapping stays a flow mapping, and a list keeps the
    # comments of the items still in it, with the comments of items taken out kept after them
    assert (tmp_path / "out.yaml").read_text() == (
        "- duration: 1  # a bare number of seconds\n"
        "  lights: {l_a: red, l_b: green} # flow\n"
        "  events:\n"
        "  - first    # one\n"
        "    # before second\n"
        "  - changed\n"
        "# after\n"
        "- duration: 1s\n"
        "  lights: {l_c: on}\n"
        "  events:\n"
        "  - added\n"
    )

    # A list made longer keeps the items it had, and a duration that changes from a token is written as a time
    show.steps[0].otherData["events"] = ["first", "second", "third", "fourth"]
    merged = showManager.showToCommentedData(show)
    assert list(merged[0]["events"]) == ["first", "second", "third", "fourth"]
    assert showManager._isSameValue("(time)", "1s", "time") is False


def test_exportConfigShowsThatCannotBeFound(tmp_path):
    configFile = _writeShow(tmp_path / "config.yaml", "shows:\n  pulse:\n    - lights:\n        l_a: red\n")
    show = showManager.loadShowFile(configFile)[0]
    for changedConfig in ("shows:\n  renamed:\n    - lights: {}\n", "lights: {}\n", "shows: [nope]\n"):
        configFile.write_text(changedConfig)
        assert showManager.showToCommentedData(show) == [{"duration": "1s", "lights": {"l_a": "red"}}]

    # A show with no steps left keeps the comments of its file
    configFile.write_text("shows:\n  pulse:\n    - time: 0  # only a time\n")
    emptyShow = showManager.loadShowFile(configFile)[0]
    emptyShow.steps = []
    merged = showManager.showToCommentedData(emptyShow)
    assert list(merged) == []
    assert showManager.yamlInterfacer.startComments(merged) == ["# only a time\n"]


def test_machineFoldersWithMPFFiles(tmp_path):
    machine = tmp_path / "machine"
    for folder, fileName in [
        ("config", "config.yaml"),
        ("shows/attract", "wave.yaml"),
        ("sounds/music", "theme.ogg"),
        ("monitor", "playfield.jpg"),
        ("modes/base/config", "base.yaml"),
        ("logs", "mpf.yaml"),
        (".git/objects", "x.yaml"),
        ("docs", "notes.txt"),
        ("a/b/c/d/e", "deep.yaml"),
    ]:
        (machine / folder).mkdir(parents=True, exist_ok=True)
        (machine / folder / fileName).write_text("")
    (machine / "readme.yaml").write_text("")
    folders = [path.relative_to(machine).as_posix() for path in showManager.findMachineFolders(machine)]
    assert folders == [
        "config",
        "modes",
        "modes/base",
        "modes/base/config",
        "monitor",
        "shows",
        "shows/attract",
        "sounds",
        "sounds/music",
    ]
    assert showManager.findMachineFolders(tmp_path / "missing") == []
