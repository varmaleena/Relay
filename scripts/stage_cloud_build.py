"""Create a fresh explicit application build context; never upload the checkout."""

import argparse
import hashlib
import json
import re
from pathlib import Path


def safe_file(root: Path, relative: str) -> Path:
    path = root / relative
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("build source escapes repository")
    current = path
    while current != root:
        if current.is_symlink() or current.is_junction():
            raise ValueError("linked build source forbidden")
        current = current.parent
    if not path.is_file():
        raise ValueError(f"missing build source: {relative}")
    return path


def selected_files(root: Path) -> list[str]:
    selected = {
        "requirements.lock",
        "infra/cloudbuild.app.yaml",
        "services/api/Dockerfile",
        "services/worker/Dockerfile",
        "services/a2a_receiver/Dockerfile",
    }
    if (root / "services/__init__.py").exists():
        selected.add("services/__init__.py")
    for folder in (
        "packages",
        "agents",
        "services/api",
        "services/worker",
        "services/mcp_bank_mock",
        "services/mcp_rail_mock",
        "services/a2a_receiver",
        "services/live_gateway",
        "services/api/sources",
    ):
        for path in (root / folder).rglob("*.py"):
            if "__pycache__" not in path.parts:
                selected.add(path.relative_to(root).as_posix())
    for folder, pattern in (
        ("agents/prompts", "*.md"),
        ("agents/receiver", "*.md"),
        ("packs", "*.yaml"),
        ("packages/safety/patterns", "*.json"),
        ("packages/packets/fonts", "*.ttf"),
    ):
        selected.update(p.relative_to(root).as_posix() for p in (root / folder).glob(pattern))
    selected.add("packages/packets/fonts/OFL.txt")
    # Only the named, reviewed-layout UK registration is eligible; no recursive
    # discovery of arbitrary source folders or attachments.
    uk_pack = root / "packs/uk/pack_uk_reimbursement.yaml"
    if uk_pack.exists():
        selected.add("packs/uk/pack_uk_reimbursement.yaml")
        for name in ("retrievals.json", "passages.json"):
            selected.add("docs/pack-sources/uk/" + name)
        uk_records = json.loads(
            safe_file(root, "docs/pack-sources/uk/retrievals.json").read_text("utf-8")
        )
        for record in uk_records:
            for key, digest_key in (("snapshot", "sha256"), ("extraction", "extraction_sha256")):
                relative = record[key]
                if (
                    not isinstance(relative, str)
                    or Path(relative).is_absolute()
                    or ".." in Path(relative).parts
                ):
                    raise ValueError("invalid UK snapshot path")
                relative = "docs/pack-sources/uk/" + relative
                if (
                    hashlib.sha256(safe_file(root, relative).read_bytes()).hexdigest()
                    != record[digest_key]
                ):
                    raise ValueError("UK source snapshot integrity mismatch")
                selected.add(relative)
    selected.update({"docs/pack-sources/retrievals.json", "docs/pack-sources/passages.json"})
    records = json.loads(safe_file(root, "docs/pack-sources/retrievals.json").read_text("utf-8"))
    for record in records:
        for key, digest_key in (("snapshot", "sha256"), ("extraction", "extraction_sha256")):
            relative = record[key]
            if (
                not isinstance(relative, str)
                or Path(relative).is_absolute()
                or ".." in Path(relative).parts
            ):
                raise ValueError("invalid source snapshot path")
            relative = "docs/pack-sources/" + relative
            data = safe_file(root, relative).read_bytes()
            if hashlib.sha256(data).hexdigest() != record[digest_key]:
                raise ValueError("source snapshot integrity mismatch")
            selected.add(relative)
    return sorted(selected)


def stage(root: Path, destination: Path) -> dict:
    root, destination = root.resolve(), destination.absolute()
    # A fresh destination prevents stale credentials/unlisted files surviving a restage.
    if destination.exists() or not destination.resolve().is_relative_to(root / ".tmp"):
        raise ValueError("destination must be a fresh directory under repository .tmp")
    for parent in (destination, *destination.parents):
        if parent == root:
            break
        if parent.is_symlink() or parent.is_junction():
            raise ValueError("linked staging destination forbidden")
    contents = {}
    for relative in selected_files(root):
        data = safe_file(root, relative).read_bytes()
        if re.search(
            rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
            rb'"type"\s*:\s*"service_account"',
            data,
        ):
            raise ValueError(f"credential marker in build source: {relative}")
        contents[relative] = data
    records = [
        {"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in sorted(contents.items())
    ]
    fingerprint = hashlib.sha256(json.dumps(records, separators=(",", ":")).encode()).hexdigest()
    manifest = {"schemaVersion": 1, "fingerprint": fingerprint, "files": records}
    for name, data in contents.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (destination / "BUILD_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    result = stage(Path(__file__).resolve().parents[1], args.destination)
    print(json.dumps({"fingerprint": result["fingerprint"], "files": len(result["files"])}))


if __name__ == "__main__":
    main()
