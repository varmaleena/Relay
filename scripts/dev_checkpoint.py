"""Two rotating emulator exports; only successful exports advance the import pointer."""

import json
from pathlib import Path


class EmulatorCheckpoints:
    def __init__(self, directory: Path) -> None:
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.pointer = self.directory / "emulator-checkpoint.json"

    def slot(self, name: str) -> Path:
        if name not in {"a", "b"}:
            raise ValueError("invalid checkpoint slot")
        path = (self.directory / f"emulator-state-{name}").resolve()
        if not path.is_relative_to(self.directory):
            raise ValueError("checkpoint outside local data directory")
        return path

    def current(self) -> Path | None:
        try:
            if self.pointer.stat().st_size > 1024:
                raise ValueError("invalid checkpoint pointer")
            value = json.loads(self.pointer.read_text(encoding="utf-8"))
            path = self.slot(value["slot"])
            if (path / "firebase-export-metadata.json").is_file():
                return path
        except (OSError, ValueError, KeyError, TypeError):
            pass
        complete = [
            self.slot(name)
            for name in ("a", "b")
            if (self.slot(name) / "firebase-export-metadata.json").is_file()
        ]
        legacy = self.directory / "emulator-state"
        if (legacy / "firebase-export-metadata.json").is_file():
            complete.append(legacy)
        return max(complete, key=lambda path: path.stat().st_mtime) if complete else None

    def next(self) -> Path:
        return self.slot("b" if self.current() == self.slot("a") else "a")

    def commit(self, path: Path) -> None:
        path = path.resolve()
        name = next((name for name in ("a", "b") if path == self.slot(name)), None)
        if name is None or not (path / "firebase-export-metadata.json").is_file():
            raise ValueError("checkpoint is not a complete local export")
        temporary = self.pointer.with_suffix(".tmp")
        temporary.write_text(json.dumps({"slot": name}), encoding="utf-8")
        temporary.replace(self.pointer)
