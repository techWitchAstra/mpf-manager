import pytest

from mpfmanager.core.storageManager import StorageProcessor


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("MPF_MANAGER_HOME", str(tmp_path / "home"))


def test_configUsesIsolatedHome(tmp_path):
    # conftest.py points MPF_MANAGER_HOME at a temp folder, so the real config is never touched
    assert StorageProcessor().homePath == tmp_path / "home"
