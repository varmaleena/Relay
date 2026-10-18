"""Build context privacy/integrity boundaries without Docker or cloud mutation."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts.stage_cloud_build import safe_file, stage


def fixture(root: Path) -> None:
    names = [
        "requirements.lock",
        "infra/cloudbuild.app.yaml",
        "services/api/Dockerfile",
        "services/worker/Dockerfile",
        "services/a2a_receiver/Dockerfile",
        "services/a2a_receiver/http.py",
        "services/a2a_receiver/client.py",
        "agents/receiver/README.md",
        "packages/__init__.py",
        "agents/__init__.py",
        "packages/packets/fonts/OFL.txt",
        "docs/pack-sources/passages.json",
    ]
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]" if name.endswith(".json") else "synthetic", "utf-8")
    data = b"synthetic source"
    snapshot = root / "docs/pack-sources/snapshots/source.txt"
    snapshot.parent.mkdir(parents=True)
    snapshot.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    (root / "docs/pack-sources/retrievals.json").write_text(
        json.dumps(
            [
                {
                    "snapshot": "snapshots/source.txt",
                    "extraction": "snapshots/source.txt",
                    "sha256": digest,
                    "extraction_sha256": digest,
                }
            ]
        ),
        "utf-8",
    )


def test_stage_is_deterministic_and_excludes_nonruntime_files(tmp_path):
    fixture(tmp_path)
    for name in (
        ".env",
        "docs/sources/dossier.pdf",
        ".local/credentials.json",
        "packages/__pycache__/leak.pyc",
        "tests/test_secret.py",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("must never upload", "utf-8")
    first = stage(tmp_path, tmp_path / ".tmp/first")
    second = stage(tmp_path, tmp_path / ".tmp/second")
    assert first == second
    runtime_files = {record["path"] for record in first["files"]}
    assert {
        "services/api/Dockerfile",
        "services/worker/Dockerfile",
        "services/a2a_receiver/Dockerfile",
        "services/a2a_receiver/http.py",
        "services/a2a_receiver/client.py",
        "agents/receiver/README.md",
    } <= runtime_files
    assert not (tmp_path / ".tmp/first/.env").exists()
    assert not (tmp_path / ".tmp/first/tests").exists()
    assert "docs/pack-sources/snapshots/source.txt" in {r["path"] for r in first["files"]}
    with pytest.raises(ValueError, match="fresh"):
        stage(tmp_path, tmp_path / ".tmp/first")


def test_credentials_and_corrupt_sources_fail_before_staging(tmp_path):
    fixture(tmp_path)
    (tmp_path / "packages/__init__.py").write_text('"-----BEGIN PRIVATE KEY-----"')
    with pytest.raises(ValueError, match="credential marker"):
        stage(tmp_path, tmp_path / ".tmp/blocked")
    assert not (tmp_path / ".tmp/blocked").exists()
    (tmp_path / "packages/__init__.py").write_text("")
    (tmp_path / "docs/pack-sources/snapshots/source.txt").write_text("corrupt")
    with pytest.raises(ValueError, match="integrity"):
        stage(tmp_path, tmp_path / ".tmp/blocked")


def test_path_escape_and_destination_outside_workspace_rejected(tmp_path):
    fixture(tmp_path)
    with pytest.raises(ValueError, match="escapes"):
        safe_file(tmp_path, "../outside.py")
    with pytest.raises(ValueError, match="under repository"):
        stage(tmp_path, tmp_path / "upload")


def test_symlink_source_rejected_even_inside_repository(tmp_path):
    fixture(tmp_path)
    path = tmp_path / "packages/link.py"
    try:
        path.symlink_to(tmp_path / "packages/__init__.py")
    except OSError:
        pytest.skip("OS does not grant symlink creation")
    with pytest.raises(ValueError, match="linked"):
        stage(tmp_path, tmp_path / ".tmp/blocked")


def test_link_guard_runs_without_os_symlink_privilege(tmp_path, monkeypatch):
    fixture(tmp_path)
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda path: path.name == "packages" or original(path))
    with pytest.raises(ValueError, match="linked"):
        stage(tmp_path, tmp_path / ".tmp/blocked")


def test_optional_a2a_build_preserves_existing_api_worker_images():
    import yaml

    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((root / "infra/cloudbuild.app.yaml").read_text())
    assert config["steps"][0]["args"] == [
        "build",
        "-f",
        "services/api/Dockerfile",
        "-t",
        "${_API_IMAGE}",
        ".",
    ]
    assert config["steps"][1]["args"] == [
        "build",
        "-f",
        "services/worker/Dockerfile",
        "-t",
        "${_WORKER_IMAGE}",
        ".",
    ]
    assert config["images"] == ["${_API_IMAGE}", "${_WORKER_IMAGE}"]
    assert config["substitutions"]["_BUILD_A2A"] == "false"
    step = config["steps"][2]
    assert "RELAY_BUILD_A2A=${_BUILD_A2A}" in step["env"]
    assert 'if [ "$$RELAY_BUILD_A2A" = "true" ]' in step["args"][1]
    assert "docker build -f services/a2a_receiver/Dockerfile" in step["args"][1]
    assert 'docker push "$$RELAY_A2A_IMAGE"' in step["args"][1]
