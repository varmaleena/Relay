"""Signed, owner-scoped local capabilities and Google Cloud Storage implementation."""

import base64
import hashlib
import hmac
import json
import os
import re
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol


class BlobStore(Protocol):
    def upload_url(self, path: str, uid: str, mime: str, size: int) -> str: ...
    def preview_url(self, path: str, uid: str, mime: str) -> str: ...
    def read(self, path: str) -> bytes: ...
    def write(self, path: str, content: bytes, mime: str) -> None: ...
    def delete(self, path: str) -> None: ...


class LocalFileBlobStore:
    def __init__(self, root: Path, base_url: str, secret: bytes) -> None:
        if len(secret) < 32:
            raise ValueError("storage signing key must have 32 bytes")
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.base_url = base_url.rstrip("/")
        self.secret = secret

    def path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root) or path == self.root or "\\" in key:
            raise ValueError("invalid storage path")
        return path

    def _url(self, path: str, uid: str, mime: str, size: int, mode: str) -> str:
        payload = {
            "path": path,
            "uid": uid,
            "mime": mime,
            "size": size,
            "exp": int(time.time()) + (600 if mode == "upload" else 60),
            "mode": mode,
        }
        encoded = (
            base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode())
            .decode()
            .rstrip("=")
        )
        signature = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
        return f"{self.base_url}/api/v1/storage/{mode}/{encoded}.{signature}"

    def capability(self, token: str, uid: str, mode: str) -> dict[str, Any]:
        if len(token) > 2048:
            raise ValueError("invalid capability")
        encoded, signature = token.rsplit(".", 1)
        expected = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid capability")
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if payload["uid"] != uid or payload["mode"] != mode or payload["exp"] <= time.time():
            raise ValueError("expired or forbidden capability")
        self.path(payload["path"])
        return payload

    def upload_url(self, path: str, uid: str, mime: str, size: int) -> str:
        return self._url(path, uid, mime, size, "upload")

    def preview_url(self, path: str, uid: str, mime: str) -> str:
        return self._url(path, uid, mime, 0, "preview")

    def read(self, path: str) -> bytes:
        target = self.path(path)
        if target.stat().st_size > 10 * 1024 * 1024:
            raise ValueError("file exceeds maximum size")
        return target.read_bytes()

    def write(self, path: str, content: bytes, mime: str) -> None:
        if not 0 < len(content) <= 10 * 1024 * 1024:
            raise ValueError("invalid blob size")
        target = self.path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp-" + os.urandom(8).hex())
        try:
            temporary.write_bytes(content)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)

    def delete(self, path: str) -> None:
        self.path(path).unlink(missing_ok=True)


class GoogleBlobStore:
    def __init__(self, bucket: Any, signing_email: str) -> None:
        if not re.fullmatch(
            r"[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.iam\.gserviceaccount\.com", signing_email
        ):
            raise ValueError("explicit service account signing email required")
        self.bucket = bucket
        self.signing_email = signing_email

    def _sign(
        self, blob: Any, method: str, mime: str | None = None, size: int | None = None
    ) -> str:
        kwargs: dict[str, Any] = {
            "version": "v4",
            "expiration": timedelta(minutes=10 if method == "PUT" else 1),
            "method": method,
        }
        if mime:
            kwargs["content_type"] = mime
        if size is not None:
            kwargs["headers"] = {"Content-Length": str(size)}
        import google.auth
        from google.auth.transport.requests import Request

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(Request())
        if not credentials.token:
            raise ValueError("signing access token unavailable")
        # Explicit IAM signBlob path supports metadata ADC without private keys.
        # Failure propagates; never retry using an implicit private-key signer.
        kwargs.update(service_account_email=self.signing_email, access_token=credentials.token)
        return str(blob.generate_signed_url(**kwargs))

    def upload_url(self, path: str, uid: str, mime: str, size: int) -> str:
        return self._sign(self.bucket.blob(path), "PUT", mime, size)

    def preview_url(self, path: str, uid: str, mime: str) -> str:
        return self._sign(self.bucket.blob(path), "GET")

    def read(self, path: str) -> bytes:
        blob = self.bucket.blob(path)
        blob.reload()
        if not blob.size or blob.size > 10 * 1024 * 1024:
            raise ValueError("invalid blob size")
        return bytes(blob.download_as_bytes())

    def write(self, path: str, content: bytes, mime: str) -> None:
        self.bucket.blob(path).upload_from_string(content, content_type=mime)

    def delete(self, path: str) -> None:
        from google.api_core.exceptions import NotFound

        try:
            self.bucket.blob(path).delete()
        except NotFound:
            pass
