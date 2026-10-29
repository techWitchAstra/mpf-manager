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
