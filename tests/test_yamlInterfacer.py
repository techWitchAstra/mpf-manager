import io

import pytest

from mpfmanager.core import yamlInterfacer


def test_loadMissingFile(tmp_path):
    assert yamlInterfacer.loadYAML(tmp_path / "missing.yaml") is None


def test_roundTripWithHeaderKeepsComments(tmp_path):
    configFile = tmp_path / "nested" / "config.yaml"
    yamlInterfacer.writeYAML({"settings": {"a": 1}, "items": ["x", "y"]}, configFile, headerString="# Header\n")
    assert configFile.read_text().startswith("# Header\n")

    configFile.write_text("# Header\nsettings:\n  a: 1  # keep me\nitems:\n  - x\n")
    data = yamlInterfacer.loadYAML(configFile)
    data["settings"]["a"] = 2
    yamlInterfacer.writeYAML(data, configFile)
    assert "a: 2  # keep me" in configFile.read_text()
    assert not configFile.with_suffix(".yaml.tmp").exists()


def test_failedWriteKeepsOriginalAndRemovesTempFile(tmp_path):
    configFile = tmp_path / "config.yaml"
    yamlInterfacer.writeYAML({"a": 1}, configFile)

    class Unrepresentable:
        pass

    with pytest.raises(Exception):  # noqa: B017 - ruamel raises its own representer error type
        yamlInterfacer.writeYAML({"a": Unrepresentable()}, configFile)
    assert yamlInterfacer.loadYAML(configFile) == {"a": 1}
    assert not configFile.with_suffix(".yaml.tmp").exists()


def test_loadYAMLTextKeepsValuesAsText(tmp_path):
    assert yamlInterfacer.loadYAMLText(tmp_path / "missing.yaml") is None
    showFile = tmp_path / "show.yaml"
    showFile.write_text("- duration: 1\n  lights:\n    l_a: 000000\n    l_b: on\n")
    assert yamlInterfacer.loadYAMLText(showFile) == [{"duration": "1", "lights": {"l_a": "000000", "l_b": "on"}}]


def test_loadYAMLTextSectionsKeepsOnlyNamedSections(tmp_path):
    assert yamlInterfacer.loadYAMLTextSections(tmp_path / "missing.yaml", {"shows"}) is None
    configFile = tmp_path / "config.yaml"
    configFile.write_text(
        "#config_version=6\n"
        "config:\n- colors.yaml\n"
        "slide_player:\n  big: {slides: [1, 2, 3]}\n"
        "shows:\n  # a comment\n  pulse:\n    - lights:\n        l_a: 000000\n"
        '"quoted": 1\n  still_quoted: 2\n'
        "named_colors:\n  color_grunt: FF6611\n"
        "---\n"
        "sounds: ignored\n"
    )
    assert yamlInterfacer.loadYAMLTextSections(configFile, {"config", "shows", "named_colors"}) == {
        "config": ["colors.yaml"],
        "shows": {"pulse": [{"lights": {"l_a": "000000"}}]},
        "named_colors": {"color_grunt": "FF6611"},
    }
    assert yamlInterfacer.loadYAMLTextSections(configFile, {"widgets"}) == {}


COMMENTED = """\
# header
- a: 1  # one
  b:
    c: 2  # two
# between
- d: 3
  e: {f: 4}  # flow
# end
"""


def _dump(data) -> str:
    stream = io.StringIO()
    yamlInterfacer.showYAML().dump(data, stream)
    return stream.getvalue()


def _commented(tmp_path):
    (tmp_path / "commented.yaml").write_text(COMMENTED)
    return yamlInterfacer.loadYAML(tmp_path / "commented.yaml")


def test_showYAMLWritesStepsFromTheStartOfTheLine(tmp_path):
    assert _dump([{"duration": "1s", "events": ["a"]}]) == "- duration: 1s\n  events:\n  - a\n"
    yamlInterfacer.writeYAML([{"a": 1}], tmp_path / "show.yaml", "#show_version=6", yamlInterfacer.showYAML())
    assert (tmp_path / "show.yaml").read_text() == "#show_version=6\n- a: 1\n"


def test_followingComments(tmp_path):
    data = _commented(tmp_path)
    # The comments after an item are kept at the deepest last item under it, but a flow mapping is one item
    assert yamlInterfacer.followingComments(data, 0) == ["# between\n"]
    assert yamlInterfacer.followingComments(data[0], "b") == ["# between\n"]
    assert yamlInterfacer.followingComments(data[0], "a") == []
    assert yamlInterfacer.followingComments(data, 1) == ["# end\n"]

    # Taking them leaves the comment at the end of the line
    assert yamlInterfacer.takeFollowingComments(data, 0) == ["# between\n"]
    assert yamlInterfacer.followingComments(data, 0) == []
    assert "c: 2  # two\n- d: 3" in _dump(data)
    assert yamlInterfacer.takeFollowingComments(data[0], "a") == []


def test_itemComments(tmp_path):
    data = _commented(tmp_path)
    assert yamlInterfacer.itemComments(data, 0, keepEndOfLine=False) == ["# between\n"]
    assert yamlInterfacer.itemComments(data, 0, keepEndOfLine=True) == ["# one\n", "# two\n", "# between\n"]
    assert yamlInterfacer.itemComments(data, 1, keepEndOfLine=True) == ["# flow\n", "# end\n"]


def test_appendComments(tmp_path):
    data = _commented(tmp_path)
    yamlInterfacer.appendComments(data, 0, ["# added\n"])
    yamlInterfacer.appendComments(data[0], "a", ["# after a\n"])
    yamlInterfacer.appendComments(data, 1, [])
    text = _dump(data)
    assert "- a: 1  # one\n# after a\n  b:" in text
    assert "c: 2  # two\n# between\n# added\n- d: 3" in text

    # An item without comments is given them
    plain = yamlInterfacer.showYAML().load("- x: 1\n- y: 2\n")
    yamlInterfacer.appendComments(plain, 0, ["# after x\n"])
    assert _dump(plain) == "- x: 1\n# after x\n- y: 2\n"


def test_startComments(tmp_path):
    data = _commented(tmp_path)
    assert yamlInterfacer.startComments(data) == ["# header\n"]
    assert yamlInterfacer.startComments(data[0]) == []
    assert yamlInterfacer.startComments(["plain"]) == []

    yamlInterfacer.setStartComments(data, ["  # indented\n", "\n", "# second\n"])
    assert _dump(data).startswith("# indented\n\n# second\n- a: 1")
    yamlInterfacer.setStartComments(data, [])
    assert yamlInterfacer.startComments(data) == []
    assert _dump(data).startswith("- a: 1")


def test_setCommentsBefore():
    data = yamlInterfacer.showYAML().load("shows:\n  first:\n    - a: 1\n  second:\n    - b: 2\n")
    yamlInterfacer.setCommentsBefore(data["shows"], "second", ["# about second\n"], 2)
    assert "  - a: 1\n  # about second\n  second:" in _dump(data)
    yamlInterfacer.setCommentsBefore(data["shows"], "second", [], 2)
    assert "# about second" not in _dump(data)
