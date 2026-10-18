"""Opaque IDs and actor-scoped hashes; no sequential-ID race or key leakage."""

import hashlib
import json
from decimal import Decimal
from uuid import uuid4


def new_id(prefix: str) -> str:
    if not prefix.isascii() or not prefix.isalpha() or len(prefix) > 16:
        raise ValueError("ID prefix must be short ASCII letters")
    return f"{prefix}_{uuid4().hex}"


def canonical_hash(payload: object) -> str:
    def serialize(value: object) -> str:
        if isinstance(value, Decimal):
            return format(value, "f")
        raise TypeError(f"unsupported hash type: {type(value).__name__}")

    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
        default=serialize,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def idempotency_scope(actor_uid: str, org_id: str | None, method: str, route: str, key: str) -> str:
    if not actor_uid or not key:
        raise ValueError("authenticated actor and key are required")
    return canonical_hash([actor_uid, org_id, method.upper(), route, key])
