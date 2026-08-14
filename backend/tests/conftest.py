import pytest

from main import rig_mgr


@pytest.fixture(autouse=True)
def reset_rig_limits(tmp_path):
    rig_mgr.storage_dir = tmp_path / "output"
    rig_mgr.storage_dir.mkdir(parents=True, exist_ok=True)
    rig_mgr.rig_file = rig_mgr.storage_dir / "rig.json"
    rig_mgr.set_limits(0.0, 80.0)
    yield
    rig_mgr.set_limits(0.0, 80.0)
