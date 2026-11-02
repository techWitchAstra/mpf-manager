from mpfmanager.core import lightGroups, showEditor
from mpfmanager.core.lightGroups import LightGroup
from mpfmanager.core.showManager import parseShow


def test_lightGroupsAreKeptWithTheMachine(tmp_path):
    assert lightGroups.loadLightGroups(tmp_path) == [] and lightGroups.loadLightGroups(None) == []
    groups = [
        LightGroup("left ramp", ["l_ramp_1", "l_ramp_2"]),
        LightGroup("inserts", ["l_a"]),
        LightGroup("gi", ["l_gi_1"], isTag=True),
    ]
    lightGroups.saveLightGroups(tmp_path, groups)
    path = tmp_path / ".mpf-manager" / "light_groups.yaml"
    assert path.read_text().startswith("# Light groups made in MPF-Manager")
    # Groups come back in the order they were made, without the groups MPF's tags make
    assert lightGroups.loadLightGroups(tmp_path) == groups[:2]

    path.write_text("left ramp: [l_a, l_a, l_b]\nbroken: not a list\n")
    assert lightGroups.loadLightGroups(tmp_path) == [LightGroup("left ramp", ["l_a", "l_b"]), LightGroup("broken")]
    path.write_text("- just a list\n")
    assert lightGroups.loadLightGroups(tmp_path) == []


def test_tagsMakeGroups():
    groups = lightGroups.tagGroups({"l_b": {"gi", "playfield"}, "l_a": {"gi"}, "l_c": set()})
    assert [(group.label, group.lights, group.isTag) for group in groups] == [
        ("tag: gi", ["l_a", "l_b"], True),
        ("tag: playfield", ["l_b"], True),
    ]
    assert LightGroup("inserts").label == "inserts"


def test_lightsAreTakenOutOfAShow():
    show = parseShow(
        [
            {"duration": "1s", "lights": {"l_a": "red", "l_a, l_b": "blue"}},
            {"duration": "1s", "lights": {"l_b": "lime"}},
        ],
        "remove",
    )
    assert showEditor.removeLightFromShow(show, "l_a")
    assert [dict(step.lights) and list(step.lights) for step in show.steps] == [["l_b"], ["l_b"]]
    assert not showEditor.removeLightFromShow(show, "l_missing")
