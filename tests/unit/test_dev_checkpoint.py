import json

import pytest

from scripts.dev import checkpoint_environment
from scripts.dev_checkpoint import EmulatorCheckpoints


def complete(path):
    path.mkdir(parents=True)
    (path / "firebase-export-metadata.json").write_text("{}")


def test_interrupted_export_keeps_previous_checkpoint_and_rotates_after_success(tmp_path):
    checkpoints = EmulatorCheckpoints(tmp_path)
    assert checkpoints.current() is None
    first = checkpoints.next()
    complete(first)
    checkpoints.commit(first)
    assert checkpoints.current() == first
    second = checkpoints.next()
    assert second != first
    second.mkdir()
    (second / "partial").write_text("incomplete")
    with pytest.raises(ValueError):
        checkpoints.commit(second)
    assert checkpoints.current() == first
    (second / "firebase-export-metadata.json").write_text("{}")
    checkpoints.commit(second)
    assert checkpoints.current() == second and checkpoints.next() == first


def test_checkpoint_pointer_cannot_escape_local_root_and_legacy_export_is_recoverable(tmp_path):
    checkpoints = EmulatorCheckpoints(tmp_path)
    legacy = tmp_path / "emulator-state"
    complete(legacy)
    checkpoints.pointer.write_text(json.dumps({"slot": "../../outside"}))
    assert checkpoints.current() == legacy
    with pytest.raises(ValueError):
        checkpoints.slot("../../outside")
    with pytest.raises(ValueError):
        checkpoints.commit(tmp_path.parent)


def test_reused_emulator_exports_use_original_hub_locator_temp_without_mutating_runtime():
    runtime = {"TEMP": "workspace-temp", "TMP": "workspace-temp", "PATH": "node-path"}
    original = {"TEMP": "system-temp", "TMP": "system-temp"}
    exported = checkpoint_environment(runtime, original, reuse_emulators=True)
    assert exported == {"TEMP": "system-temp", "TMP": "system-temp", "PATH": "node-path"}
    assert runtime["TEMP"] == "workspace-temp"
    assert checkpoint_environment(runtime, original, reuse_emulators=False) == runtime


def test_unset_inherited_temp_does_not_leave_workspace_locator_override():
    exported = checkpoint_environment(
        {"TEMP": "workspace", "TMP": "workspace", "TMPDIR": "workspace", "PATH": "node"},
        {},
        reuse_emulators=True,
    )
    assert exported == {"PATH": "node"}
