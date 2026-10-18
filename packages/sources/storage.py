"""Bounded isolated parsing and immutable source blob adapters."""

import json
import os
import subprocess
import sys
from pathlib import Path

from packages.sources.fetch import MAX_BYTES, MIMES, SourceRejected


def parse_source(content: bytes, mime: str) -> list[tuple[int | None, str]]:
    if os.name != "posix":
        raise SourceRejected("Isolated parser hard limits unavailable on this platform")
    if mime not in MIMES or not 0 < len(content) <= MAX_BYTES:
        raise SourceRejected("Source format or size rejected")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "packages.sources.parse_worker", mime],
            input=content,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=7,
            check=False,
            cwd=Path(__file__).resolve().parents[2],
        )
        if result.returncode or len(result.stdout) > 4 * 1024 * 1024:
            raise ValueError()
        pages = json.loads(result.stdout)
        return [(page, text) for page, text in pages]
    except Exception:
        raise SourceRejected("Source parser rejected content or exceeded limits") from None


class LocalSourceStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root) or path == self.root or "\\" in key:
            raise SourceRejected("Invalid source storage key")
        return path

    def read(self, key: str) -> bytes:
        path = self._path(key)
        if not 0 < path.stat().st_size <= MAX_BYTES:
            raise SourceRejected("Source size rejected")
        return path.read_bytes()

    def put_once(self, key: str, content: bytes, mime: str) -> None:
        if mime not in MIMES or not 0 < len(content) <= MAX_BYTES:
            raise SourceRejected("Source format or size rejected")
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("xb") as stream:
                stream.write(content)
        except FileExistsError:
            if path.read_bytes() != content:
                raise SourceRejected("Immutable source collision") from None


class GoogleSourceStore:
    def __init__(self, bucket):
        self.bucket = bucket

    def read(self, key: str) -> bytes:
        value = self.bucket.blob(key).download_as_bytes(
            timeout=15, retry=None, start=0, end=MAX_BYTES
        )
        if not 0 < len(value) <= MAX_BYTES:
            raise SourceRejected("Source size rejected")
        return value

    def put_once(self, key: str, content: bytes, mime: str) -> None:
        from google.api_core.exceptions import PreconditionFailed

        if mime not in MIMES or not 0 < len(content) <= MAX_BYTES:
            raise SourceRejected("Source format or size rejected")
        blob = self.bucket.blob(key)
        try:
            blob.upload_from_string(
                content, content_type=mime, if_generation_match=0, timeout=15, retry=None
            )
        except PreconditionFailed:
            # Content-addressed path permits safe retry, but verify an existing object.
            existing = blob.download_as_bytes(timeout=15, retry=None, start=0, end=MAX_BYTES)
            if existing != content:
                raise SourceRejected("Immutable source collision") from None
