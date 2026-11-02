import pytest

from mpfmanager.core import showEditor, showManager
from mpfmanager.core.showManager import parseShow


def _show(steps=None, library=None) -> showManager.MPFShow:
    show = parseShow(
        steps
        or [
            {"duration": "1s", "lights": {"l_a": "red", "l_b": "blue"}},
            {"duration": "1s", "lights": {"l_a": "lime"}},
        ],
        "edit",
    )
    show.buildTimeline({}, library or {})
    return show


def _colors(show, light, times, library=None):
    show.buildTimeline({}, library or {})
    return [show.channelState(light, atTime).rgb for atTime in times]


def _layout(show):
    return [
        (step.startTime, step.duration, {name: setting.value for name, setting in step.lights.items()})
        for step in show.steps
    ]


def test_namesLight():
    assert showEditor.namesLight("l_a", "l_a")
    assert showEditor.namesLight("l_b, l_a", "l_a")
    assert not showEditor.namesLight("l_ab", "l_a")
    assert not showEditor.namesLight("(leds)", "leds")
    assert showEditor.namesLight("(leds)", "(leds)")


def test_splitStepAt():
    show = _show()
    assert showEditor.splitStepAt(show, 1.0) is show.steps[1]
    assert showEditor.splitStepAt(show, 1.0004) is show.steps[1]
    newStep = showEditor.splitStepAt(show, 0.25)
    assert (newStep.stepNumber, newStep.startTime, newStep.duration, newStep.lights) == (0, 0.25, 0.75, {})
    assert show.steps[0].duration == 0.25
    assert showEditor.splitStepAt(show, 2.0) is None
    assert showEditor.splitStepAt(show, -1) is None

    # A step that holds keeps holding after the split
    holdShow = _show([{"duration": "1s", "lights": {"l_a": "red"}}, {"duration": -1, "lights": {"l_a": "blue"}}])
    second = showEditor.splitStepAt(holdShow, 1.5)
    assert (holdShow.steps[1].isHold, second.isHold) == (False, True)
    assert holdShow.totalDuration == 1.0 + showManager.HOLD_DISPLAY_SECONDS


def test_paintLightOverPartOfAStep():
    show = _show()
    assert showEditor.paintLight(show, "l_a", 0.25, 0.5, showEditor.paintSetting((255, 255, 255), 50))

    # The step is split where the paint starts and ends, and the light goes back to its color after it
    assert _layout(show) == [
        (0.0, 0.25, {"l_a": "red", "l_b": "blue"}),
        (0.25, 0.25, {"l_a": "white%50"}),
        (0.5, 0.5, {"l_a": "red"}),
        (1.0, 1.0, {"l_a": "lime"}),
    ]
    assert _colors(show, "l_a", (0.1, 0.3, 0.6, 1.5)) == [(255, 0, 0), (127, 127, 127), (255, 0, 0), (0, 255, 0)]
    assert _colors(show, "l_b", (0.3, 1.5)) == [(0, 0, 255), (0, 0, 255)]


def test_paintLightAcrossSteps():
    show = _show()
    showEditor.paintLight(show, "l_a", 0.5, 1.5, showEditor.paintSetting((0, 0, 255)))

    # Settings inside the span are taken out, and the light goes back to the last of them after it
    assert _layout(show) == [
        (0.0, 0.5, {"l_a": "red", "l_b": "blue"}),
        (0.5, 0.5, {"l_a": "blue"}),
        (1.0, 0.5, {}),
        (1.5, 0.5, {"l_a": "lime"}),
    ]
    assert _colors(show, "l_a", (0.25, 0.75, 1.25, 1.75)) == [(255, 0, 0), (0, 0, 255), (0, 0, 255), (0, 255, 0)]


def test_paintLightToTheEndAndOutside():
    show = _show()
    assert showEditor.paintLight(show, "l_b", 1.5, 9.0, showEditor.paintSetting((255, 0, 0)))
    assert _layout(show)[-1] == (1.5, 0.5, {"l_b": "red"})
    assert not showEditor.paintLight(show, "l_b", 5.0, 6.0, showEditor.paintSetting((255, 0, 0)))
    assert not showEditor.paintLight(show, "l_b", 1.0, 1.0, showEditor.paintSetting((255, 0, 0)))


def test_paintALightTheShowHadNotSet():
    show = _show()
    showEditor.paintLight(show, "l_new", 0.5, 1.0, showEditor.paintSetting((255, 255, 255)))

    # It is stopped afterwards, as the show had not set it
    assert _layout(show)[1:3] == [(0.5, 0.5, {"l_new": "white"}), (1.0, 1.0, {"l_a": "lime", "l_new": "stop"})]
    show.buildTimeline()
    assert show.channelState("l_new", 1.5).segment.setting.kind == "stop"

    # A light set by a show it plays shows that show again after the paint
    library = {"under": parseShow([{"duration": -1, "lights": {"l_u": "orange"}}], "under")}
    nested = _show([{"duration": "2s", "shows": {"under": "play"}}], library)
    showEditor.paintLight(nested, "l_u", 0.5, 1.0, showEditor.paintSetting((0, 0, 255)))
    assert _colors(nested, "l_u", (0.25, 0.75, 1.5), library) == [(255, 165, 0), (0, 0, 255), (255, 165, 0)]
    assert nested.channelState("l_u", 0.75).segment.showPath == ()


def test_paintLightInAListOfLights():
    show = _show(
        [{"duration": "1s", "lights": {"l_a, l_b": "red"}}, {"duration": "1s", "lights": {"l_a, l_b, l_c": "lime"}}]
    )
    showEditor.paintLight(show, "l_b", 0.5, 1.5, showEditor.paintSetting((0, 0, 255)))
    assert _layout(show) == [
        (0.0, 0.5, {"l_a, l_b": "red"}),
        (0.5, 0.5, {"l_b": "blue"}),
        (1.0, 0.5, {"l_a, l_c": "lime"}),
        (1.5, 0.5, {"l_b": "lime"}),
    ]
    assert _colors(show, "l_a", (1.25,)) == [(0, 255, 0)]
    assert _colors(show, "l_b", (0.25, 0.75, 1.25, 1.75)) == [(255, 0, 0), (0, 0, 255), (0, 0, 255), (0, 255, 0)]


def test_eraseLight():
    show = _show()
    showEditor.paintLight(show, "l_a", 0.5, 1.5, showEditor.paintSetting((0, 0, 255)))

    # Erasing takes out the light's settings, so it carries on with what it had, and added steps left empty are joined
    assert showEditor.paintLight(show, "l_a", 0.5, 1.5, None)
    assert _layout(show) == [(0.0, 1.0, {"l_a": "red", "l_b": "blue"}), (1.0, 0.5, {}), (1.5, 0.5, {"l_a": "lime"})]
    assert _colors(show, "l_a", (0.75, 1.25, 1.75)) == [(255, 0, 0), (255, 0, 0), (0, 255, 0)]
    assert showEditor.paintLight(show, "l_a", 1.0, 2.0, None)
    assert _layout(show) == [(0.0, 1.0, {"l_a": "red", "l_b": "blue"}), (1.0, 1.0, {})]
    assert _colors(show, "l_a", (1.5,)) == [(255, 0, 0)]


def test_joinEmptyStepsKeepsTheFilesSteps():
    show = _show([{"duration": "1s", "lights": {"l_a": "red"}}, {"duration": "1s"}, {"duration": -1}])
    show.steps.append(showManager.ShowStep(0, 3.0, 1.0))
    showEditor.joinEmptySteps(show)
    assert [(step.stepNumber, step.duration) for step in show.steps] == [(1, 1.0), (2, 1.0), (3, 1.0), (0, 1.0)]

    # A step added after a step that is not a hold is joined to it
    show.steps[2].isHold = False
    showEditor.joinEmptySteps(show)
    assert [(step.stepNumber, step.duration) for step in show.steps] == [(1, 1.0), (2, 1.0), (3, 2.0)]


def test_paintedFadesAndRestoredColors():
    show = _show([{"duration": "1s", "lights": {"l_a": "red-f500ms"}}, {"duration": "1s"}])
    showEditor.paintLight(show, "l_a", 1.0, 1.5, showEditor.paintSetting((0, 0, 255), fadeMs=200))
    assert show.steps[1].lights["l_a"].fadeText == "200ms"
    # The light goes straight back to its color, rather than fading into it again
    assert (show.steps[2].lights["l_a"].value, show.steps[2].lights["l_a"].fadeMs) == ("red", 0)
    assert show.steps[0].lights["l_a"].fadeMs == 500


@pytest.mark.parametrize(
    ("rgb", "intensity", "value"),
    [
        ((255, 0, 0), 100, "red"),
        ((255, 0, 0), 40, "red%40"),
        ((0, 0, 0), 100, "off"),
        ((18, 52, 86), 100, "123456"),
        ((18, 52, 86), 150, "123456"),
        ((255, 102, 17), 0, "ff6611%0"),
    ],
)
def test_colorValue(rgb, intensity, value):
    assert showEditor.colorValue(rgb, intensity) == value


def test_paintSettingUsesTheProjectsColors():
    namedColors = {"grunt": (255, 102, 17)}
    assert showEditor.colorValue((255, 102, 17), 50, namedColors) == "grunt%50"
    setting = showEditor.paintSetting((255, 102, 17), 50, 100, namedColors)
    assert (setting.value, setting.fadeMs, setting.rgb, setting.kind) == ("grunt%50", 100, (127, 51, 8), "color")


def test_splitColorValue():
    assert showEditor.splitColorValue("red%40") == ((255, 0, 0), 40)
    assert showEditor.splitColorValue("ff6611") == ((255, 102, 17), 100)
    assert showEditor.splitColorValue("grunt", {"grunt": (1, 2, 3)}) == ((1, 2, 3), 100)
    assert showEditor.splitColorValue("(color)") is None
    assert showEditor.splitColorValue("stop") is None
    assert showEditor.splitColorValue("red%x") is None


def test_editHistory():
    show = _show()
    history = showEditor.EditHistory(limit=2)
    assert not history.undo(show) and not history.redo(show)
    original = _layout(show)
    for start in (0.0, 0.25, 0.5):
        history.remember(show)
        showEditor.paintLight(show, "l_a", start, start + 0.1, showEditor.paintSetting((0, 0, 255)))
    painted = _layout(show)

    # Only the latest changes are kept, and they can be undone and redone
    assert history.undo(show) and history.undo(show) and not history.undo(show)
    assert _layout(show) != original
    assert history.redo(show) and history.redo(show) and not history.redo(show)
    assert _layout(show) == painted
    history.undo(show)
    history.remember(show)
    assert not history.redo(show)
    history.clear()
    assert not history.undo(show)


def test_paintedShowsAreWrittenBack(tmp_path):
    showFile = tmp_path / "shows" / "edit.yaml"
    showFile.parent.mkdir()
    showFile.write_text("#show_version=6\n- duration: 1s  # first\n  lights:\n    l_a: red\n")
    show = showManager.loadShowFile(showFile)[0]
    showEditor.paintLight(show, "l_a", 0.5, 0.75, showEditor.paintSetting((0, 0, 255), 25))
    showManager.exportShowFile(show, showFile)
    assert showFile.read_text() == (
        "#show_version=6\n"
        "- duration: 500ms # first\n"
        "  lights:\n"
        "    l_a: red\n"
        "- duration: 250ms\n"
        "  lights:\n"
        "    l_a: blue%25\n"
        "- duration: 250ms\n"
        "  lights:\n"
        "    l_a: red\n"
    )
    assert _colors(showManager.loadShowFile(showFile)[0], "l_a", (0.6,)) == [(0, 0, 63)]


def test_showsInConfigsAreMarked(tmp_path):
    configFile = tmp_path / "config" / "config.yaml"
    configFile.parent.mkdir()
    configFile.write_text("shows:\n  pulse:\n    - lights:\n        l_a: red\n")
    assert showManager.loadShowFile(configFile)[0].isInConfig
    assert showManager.loadConfigShows(tmp_path)[0].isInConfig
    assert not _show().isInConfig


def _rgbs(show, lights, atTime, library=None):
    show.buildTimeline({}, library or {})
    return [show.channelState(light, atTime).rgb for light in lights]


def test_extendShow():
    show = _show()
    assert showEditor.extendShow(show, 1.5) and show.totalDuration == 2.0
    assert showEditor.extendShow(show, 3.25) and show.totalDuration == 3.25
    assert show.steps[-1].duration == 2.25
    empty = showManager.MPFShow("empty", None)
    assert showEditor.extendShow(empty, 1.0) and empty.totalDuration == 1.0
    held = _show([{"duration": -1, "lights": {"l_a": "red"}}])
    assert not showEditor.extendShow(held, 5.0)


@pytest.mark.parametrize(
    ("pattern", "width", "frames"),
    [
        ("forward", 1, [{0}, {1}, {2}, {0}]),
        ("reverse", 1, [{2}, {1}, {0}, {2}]),
        ("bounce", 1, [{0}, {1}, {2}, {1}, {0}, {1}]),
        ("fill", 1, [{0}, {0, 1}, {0, 1, 2}, {0}]),
        ("forward", 2, [{0}, {0, 1}, {1, 2}, {2, 0}]),
    ],
)
def test_chaseFrame(pattern, width, frames):
    assert [showEditor.chaseFrame(frame, 3, pattern, width) for frame in range(len(frames))] == frames


def test_chaseFrameEdgeCases():
    assert showEditor.chaseFrame(3, 0) == set()
    assert showEditor.chaseFrame(5, 1, "bounce") == {0}


def test_chaseLights():
    show = _show([{"duration": "1s", "lights": {"l_a": "red", "l_b": "red", "l_c": "red"}}, {"duration": "1s"}])
    lights = ["l_a", "l_b", "l_c"]
    assert showEditor.chaseLights(
        show,
        lights,
        0,
        0.75,
        showEditor.paintSetting((0, 0, 255)),
        0.25,
        betweenSetting=showEditor.paintSetting((0, 0, 0)),
    )
    blue, off, red = (0, 0, 255), (0, 0, 0), (255, 0, 0)
    assert _rgbs(show, lights, 0.1) == [blue, off, off]
    assert _rgbs(show, lights, 0.4) == [off, blue, off]
    assert _rgbs(show, lights, 0.6) == [off, off, blue]
    # After the chase the lights go back to what they were
    assert _rgbs(show, lights, 0.9) == [red, red, red]


def test_chaseLeavesLightsBetweenAsTheyWere():
    show = _show([{"duration": "1s", "lights": {"l_a": "red", "l_b": "lime"}}])
    showEditor.chaseLights(show, ["l_a", "l_b"], 0, 1, showEditor.paintSetting((0, 0, 255)), 0.5)
    assert _rgbs(show, ["l_a", "l_b"], 0.25) == [(0, 0, 255), (0, 255, 0)]
    assert _rgbs(show, ["l_a", "l_b"], 0.75) == [(255, 0, 0), (0, 0, 255)]
    # A chase with nothing to do changes nothing
    setting = showEditor.paintSetting((0, 0, 255))
    assert not showEditor.chaseLights(show, [], 0, 1, setting, 0.5)
    assert not showEditor.chaseLights(show, ["l_a"], 0, 1, setting, 0)
    assert not showEditor.chaseLights(show, ["l_a"], 1, 1, setting, 0.5)


def test_orderLights():
    positions = {"top": (0.5, 0.1), "right": (0.9, 0.5), "bottom": (0.5, 0.9), "left": (0.1, 0.5)}
    names = ["bottom", "unplaced", "left", "top", "right"]
    assert showEditor.orderLights(names, positions, "grid order") == names
    assert showEditor.orderLights(names, positions, "left to right")[:2] == ["left", "bottom"]
    assert showEditor.orderLights(names, positions, "right to left")[0] == "right"
    assert showEditor.orderLights(names, positions, "top to bottom")[0] == "top"
    assert showEditor.orderLights(names, positions, "bottom to top")[0] == "bottom"
    assert showEditor.orderLights(names, positions, "clockwise") == ["top", "right", "bottom", "left", "unplaced"]
    assert showEditor.orderLights(names, positions, "counterclockwise") == [
        "top",
        "left",
        "bottom",
        "right",
        "unplaced",
    ]
    assert showEditor.orderLights(["a", "b"], {}, "clockwise") == ["a", "b"]


def test_copyLights():
    show = _show(
        [
            {"duration": "1s", "lights": {"l_a": "red-f500ms"}},
            {"duration": "500ms", "lights": {"l_a": "blue"}},
            {"duration": "500ms", "lights": {"l_a": "lime-f100ms"}},
        ]
    )
    clip = showEditor.copyLights(show, ["l_a", "l_unset"], 0.5, 1.75)
    assert clip.duration == 1.25
    assert [(changeTime, setting.value, setting.fadeText) for changeTime, setting in clip.changes["l_a"]] == [
        (0.0, "red", ""),
        (0.5, "blue", ""),
        (1.0, "lime", "100ms"),
    ]
    assert clip.changes["l_unset"] == [(0.0, None)]

    # A fade that starts where the copy starts is kept
    assert showEditor.copyLights(show, ["l_a"], 0, 1).changes["l_a"][0][1].fadeText == "500ms"
    # The copy is its own, so changing the show leaves it as it was
    show.steps[1].lights["l_a"].value = "white"
    assert clip.changes["l_a"][1][1].value == "blue"


def test_pasteLights():
    show = _show(
        [
            {"duration": "500ms", "lights": {"l_a": "red", "l_b": "lime"}},
            {"duration": "500ms", "lights": {"l_a": "blue"}},
        ]
    )
    clip = showEditor.copyLights(show, ["l_a"], 0, 1)

    # Pasting onto the same light, past the end of the show, makes the show longer
    assert showEditor.pasteLights(show, clip, 1.0)
    assert show.totalDuration == 2.0
    assert _rgbs(show, ["l_a"], 1.25) == [(255, 0, 0)]
    assert _rgbs(show, ["l_a"], 1.75) == [(0, 0, 255)]

    # Pasting onto another light paints it the same way
    assert showEditor.pasteLights(show, clip, 0, ["l_b"])
    assert _rgbs(show, ["l_b"], 0.25) + _rgbs(show, ["l_b"], 0.75) == [(255, 0, 0), (0, 0, 255)]

    # A show that holds at its end leaves out what goes past it
    held = _show([{"duration": "1s", "lights": {"l_a": "red"}}, {"duration": -1}])
    assert not showEditor.pasteLights(held, clip, 5.0)
    assert showEditor.pasteLights(held, clip, 1.5)
    assert held.totalDuration == 2.0
    assert not showEditor.pasteLights(show, showEditor.LightClip(["l_a"], 0.0), 0)


def test_pastingAnUnsetLightErasesIt():
    show = _show([{"duration": "1s", "lights": {"l_a": "red"}}, {"duration": "1s", "lights": {"l_b": "blue"}}])
    clip = showEditor.copyLights(show, ["l_b"], 0, 1)
    showEditor.pasteLights(show, clip, 1.0)
    assert _rgbs(show, ["l_b"], 1.5) == [None]


def test_repeatLights():
    show = _show([{"duration": "250ms", "lights": {"l_a": "red"}}, {"duration": "250ms", "lights": {"l_a": "off"}}])
    assert showEditor.repeatLights(show, ["l_a"], 0, 0.5, 3)
    assert show.totalDuration == 2.0
    assert [_rgbs(show, ["l_a"], atTime)[0] for atTime in (1.1, 1.4, 1.6, 1.9)] == [
        (255, 0, 0),
        (0, 0, 0),
        (255, 0, 0),
        (0, 0, 0),
    ]


def test_makeReusableShow():
    show = _show(
        [
            {"duration": "500ms", "lights": {"l_a": "red%50", "l_b": "blue"}},
            {"duration": "500ms", "lights": {"l_a": "off", "l_b": "(other)"}},
        ]
    )
    newShow, showTokens = showEditor.makeReusableShow(show, ["l_a", "l_b", "l_unset"], 0, 1, "part")
    assert showTokens == {
        "light1": "l_a",
        "light2": "l_b",
        "light3": "l_unset",
        "color1": "red",
        "color2": "blue",
        "color3": "off",
    }
    assert showManager.showToData(newShow) == [
        {"duration": "500ms", "lights": {"(light1)": "(color1)%50", "(light2)": "(color2)"}},
        {"duration": "500ms", "lights": {"(light1)": "(color3)", "(light2)": "(other)"}},
    ]

    # Without tokens for colors, and with one light, the light is the token (light)
    single, singleTokens = showEditor.makeReusableShow(show, ["l_a"], 0, 0.5, "single", tokenizeColors=False)
    assert singleTokens == {"light": "l_a"}
    assert showManager.showToData(single) == [{"duration": "500ms", "lights": {"(light)": "red%50"}}]


def test_playShowInPlace():
    show = _show(
        [
            {"duration": "500ms", "lights": {"l_a": "red", "l_b": "blue"}},
            {"duration": "500ms", "lights": {"l_a": "lime"}},
            {"duration": "1s", "lights": {"l_a": "white"}},
        ]
    )
    before = [_rgbs(show, ["l_a", "l_b"], atTime) for atTime in (0.25, 0.75, 1.5)]
    newShow, showTokens = showEditor.makeReusableShow(show, ["l_a", "l_b"], 0, 1, "part")
    assert showEditor.playShowInPlace(show, ["l_a", "l_b"], 0, 1, "part", showTokens)

    # The show plays the new show with the tokens, and looks as it did
    assert show.steps[0].shows == {"part": {"loops": "0", "show_tokens": showTokens}}
    assert not any(step.lights.get("l_a") and step.startTime < 1 for step in show.steps)
    library = {"part": newShow}
    assert [_rgbs(show, ["l_a", "l_b"], atTime, library) for atTime in (0.25, 0.75, 1.5)] == before
    assert show.channelState("l_a", 0.25).segment.showPath == ("part",)

    # The new show can be played on other lights in other colors
    other = _show(
        [
            {
                "duration": "1s",
                "shows": {"part": {"show_tokens": {"light1": "l_x", "light2": "l_y", "color1": "orange"}}},
            }
        ],
        library,
    )
    assert other.channelState("l_x", 0.25).rgb == (255, 165, 0)
    assert not showEditor.playShowInPlace(show, ["l_a"], 9, 10, "part", {})


def test_newShowIsOneBlankStep(tmp_path):
    show = showEditor.newShow("intro", 2.5, tmp_path / "intro.yaml")
    assert (show.name, show.sourcePath, show.totalDuration) == ("intro", tmp_path / "intro.yaml", 2.5)
    assert len(show.steps) == 1 and not show.steps[0].lights
    showManager.exportShowFile(show, tmp_path / "intro.yaml")
    reloaded = showManager.loadShowFile(tmp_path / "intro.yaml")[0]
    assert reloaded.name == "intro" and reloaded.totalDuration == 2.5


def test_soundsAreAddedAndRemoved():
    show = _show()
    assert showEditor.addSound(show, "boom", 0.5, {"volume": 0.8, "loops": 0, "start_at": 0.0, "fade_in": 0.25})
    # The step is split where the sound plays, and only settings that are not MPF's own are written
    assert [step.startTime for step in show.steps] == [0.0, 0.5, 1.0]
    assert show.steps[1].sounds == {"boom": {"action": "play", "volume": 0.8, "fade_in": 0.25}}
    assert showEditor.addSound(show, "intro", 0.0)
    assert show.steps[0].sounds == {"intro": {"action": "play"}}
    assert showManager.stepToData(show.steps[1])["sounds"] == {
        "boom": {"action": "play", "volume": 0.8, "fade_in": 0.25}
    }
    show.buildTimeline({}, {})
    assert [(play.soundName, play.startTime, play.volume) for play in show.soundPlays] == [
        ("intro", 0.0, 1.0),
        ("boom", 0.5, 0.8),
    ]
    assert showEditor.soundEntries(show) == [(0.0, "intro"), (0.5, "boom")]

    # A sound at the show's end makes the show longer, so it plays within it
    assert showEditor.addSound(show, "outro", show.totalDuration)
    assert show.totalDuration == 3.0 and showEditor.soundEntries(show)[-1] == (2.0, "outro")
    assert not showEditor.addSound(show, " ", 0.2) and not showEditor.addSound(show, "x", -1)

    # Taking a sound out joins the step it was in back to the one before, when it was made by editing
    assert showEditor.removeSound(show, 0.5, "boom")
    assert [step.startTime for step in show.steps] == [0.0, 1.0, 2.0]
    assert not showEditor.removeSound(show, 0.5, "boom")
