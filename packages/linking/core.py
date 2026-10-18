"""Deterministic HMAC indexing and the source specification's heuristic scores."""

import hashlib
import hmac
import re
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from math import prod
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit

import phonenumbers
from pydantic import BaseModel, ConfigDict, Field

WEIGHTS = dict(
    bank_account=0.9,
    upi_id=0.9,
    wallet_address=0.9,
    iban=0.9,
    phone=0.6,
    url=0.6,
    email=0.5,
    social_handle=0.5,
)
EXCLUDED = frozenset(
    {
        "amount",
        "transaction_ref",
        "timestamp",
        "currency",
        "bank_name",
        "app_name",
        "claimed_identity",
    }
)


class Sighting(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    case_ref: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    entity_type: str
    entity_hmac: str = Field(pattern=r"^[0-9a-f]{64}$")
    first_seen: datetime


class Link(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    link_id: str
    case_refs: tuple[str, str]
    shared_entity_types: list[str]
    strength: float
    confidence_band: Literal["possible", "likely"]
    hours_apart: float


class Cluster(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    cluster_id: str
    case_refs: list[str]
    entity_types: list[str]


def normalize(
    kind: str, value: str, country: str = "IN", *, case_sensitive_wallet: bool = True
) -> str:
    if kind not in WEIGHTS:
        raise ValueError("Unsupported linking type")
    value = value.strip()
    if not value or len(value) > 2048:
        raise ValueError("Invalid identifier")
    if kind == "phone":
        try:
            number = phonenumbers.parse(value, country)
        except phonenumbers.NumberParseException:
            raise ValueError("Invalid phone") from None
        if not phonenumbers.is_possible_number(number):
            raise ValueError("Invalid phone")
        return str(phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164))
    if kind in {"upi_id", "email", "social_handle"}:
        return value.lower()
    if kind in {"bank_account", "iban"}:
        result = re.sub(r"[\s-]", "", value).upper()
        if not re.fullmatch(r"[A-Z0-9]+", result):
            raise ValueError("Invalid account identifier")
        return result
    if kind == "wallet_address":
        return value if case_sensitive_wallet else value.lower()
    parsed = urlsplit(value if "://" in value else "https://" + value)
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Invalid URL")
    host = parsed.hostname.lower().removeprefix("www.")
    if parsed.port:
        host += ":" + str(parsed.port)
    query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if not k.lower().startswith("utm_") and k.lower() not in {"gclid", "fbclid", "msclkid"}
        ]
    )
    return host + parsed.path.rstrip("/") + ("?" + query if query else "")


class Hasher:
    def __init__(self, key: bytes, denylist: frozenset[str] = frozenset()) -> None:
        if len(key) < 32:
            raise ValueError("HMAC key must contain at least 32 bytes")
        self._key = key
        self.denylist = denylist

    def digest(
        self, kind: str, value: str, country: str = "IN", *, case_sensitive_wallet: bool = True
    ) -> str:
        normalized = normalize(kind, value, country, case_sensitive_wallet=case_sensitive_wallet)
        return hmac.new(self._key, f"{kind}|{normalized}".encode(), hashlib.sha256).hexdigest()

    def sighting(
        self,
        *,
        case_ref: str,
        entity_type: str,
        value: str,
        role: str,
        status: str,
        first_seen: datetime,
        country: str = "IN",
        case_sensitive_wallet: bool = True,
    ) -> Sighting | None:
        # Only confirmed scammer-side identifiers may create cross-case links.
        if role != "scammer" or status not in {"confirmed", "edited"} or entity_type not in WEIGHTS:
            return None
        if first_seen.tzinfo is None or first_seen.utcoffset() is None:
            raise ValueError("Timezone required")
        digest = self.digest(
            entity_type, value, country, case_sensitive_wallet=case_sensitive_wallet
        )
        if digest in self.denylist:
            return None
        return Sighting(
            case_ref=case_ref, entity_type=entity_type, entity_hmac=digest, first_seen=first_seen
        )


def compute(
    sightings: list[Sighting], denylist: frozenset[str] = frozenset()
) -> tuple[list[Link], list[Cluster]]:
    if len(sightings) > 2000:
        raise ValueError("Bounded computation accepts at most 2000 sightings")
    groups: dict[tuple[str, str], list[Sighting]] = defaultdict(list)
    for item in sightings:
        if item.entity_type in WEIGHTS and item.entity_hmac not in denylist:
            if item.first_seen.tzinfo is None:
                raise ValueError("Timezone required")
            groups[(item.entity_type, item.entity_hmac)].append(item)
    pairs: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for (kind, _), group in groups.items():
        for a, b in combinations(group, 2):
            if a.case_ref == b.case_ref:
                continue
            left, right = sorted((a.case_ref, b.case_ref))
            pair = (left, right)
            hours = abs((a.first_seen - b.first_seen).total_seconds()) / 3600
            pairs[pair][kind] = min(hours, pairs[pair].get(kind, float("inf")))
    links = []
    adjacency: dict[str, set[str]] = defaultdict(set)
    for pair, types in sorted(pairs.items()):
        hours = min(types.values())
        factor = 1.0 if hours <= 72 else 0.8 if hours <= 720 else 0.5
        strength = min(0.99, (1 - prod(1 - WEIGHTS[t] for t in types)) * factor)
        if strength < 0.60:
            continue
        links.append(
            Link(
                link_id="lnk_" + hashlib.sha256("|".join(pair).encode()).hexdigest()[:24],
                case_refs=pair,
                shared_entity_types=sorted(types),
                strength=strength,
                confidence_band="likely" if strength >= 0.85 else "possible",
                hours_apart=hours,
            )
        )
        adjacency[pair[0]].add(pair[1])
        adjacency[pair[1]].add(pair[0])
    clusters = []
    visited: set[str] = set()
    for start in sorted(adjacency):
        if start in visited:
            continue
        pending, component = [start], set()
        while pending:
            node = pending.pop()
            if node in component:
                continue
            component.add(node)
            pending.extend(adjacency[node] - component)
        visited.update(component)
        if len(component) >= 3:
            refs = sorted(component)
            kinds = sorted(
                {
                    t
                    for link in links
                    if set(link.case_refs) <= component
                    for t in link.shared_entity_types
                }
            )
            clusters.append(
                Cluster(
                    cluster_id="cl_" + hashlib.sha256("|".join(refs).encode()).hexdigest()[:24],
                    case_refs=refs,
                    entity_types=kinds,
                )
            )
    return links, clusters
