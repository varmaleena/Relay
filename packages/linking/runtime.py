"""Explicit HMAC key loading; no key enters browser configuration or logs."""

import base64
import re


def catalog_hasher(key: bytes, packs):
    """Exclude configured institutional channels even if mislabeled scammer-side."""
    from .core import Hasher

    initial = Hasher(key)
    excluded = set()
    for pack in packs:
        for recipient in pack.recipients:
            for channel in recipient.channels:
                kind = {"phone": "phone", "email": "email", "website": "url", "portal": "url"}.get(
                    channel.type
                )
                if kind is None:
                    continue
                try:
                    excluded.add(initial.digest(kind, channel.value, pack.jurisdiction.code))
                except ValueError:
                    # Descriptive channels such as 'use your own bank app' are
                    # not linkable identifiers; no guessed normalization occurs.
                    continue
    return Hasher(key, frozenset(excluded))


def load_cloud_key(resource: str, *, session=None) -> bytes:
    if not re.fullmatch(
        r"projects/[a-z][a-z0-9-]{4,28}[a-z0-9]/secrets/[A-Za-z0-9_-]{1,255}/versions/[1-9][0-9]*",
        resource,
    ):
        raise ValueError("An immutable Secret Manager version is required")
    if session is None:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        session = AuthorizedSession(credentials)
    try:
        response = session.get(
            "https://secretmanager.googleapis.com/v1/" + resource + ":access", timeout=5
        )
        response.raise_for_status()
        data = response.json()["payload"]["data"]
        if not isinstance(data, str) or len(data) > 256:
            raise ValueError()
        key = base64.b64decode(data, validate=True)
        if not 32 <= len(key) <= 128:
            raise ValueError()
        return key
    except Exception:
        raise ValueError("Linking key unavailable") from None
