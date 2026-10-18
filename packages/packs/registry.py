"""Offline integrity-checked registry. Draft previews are explicitly local only."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from packages.common.identifiers import canonical_hash
from packages.schemas import Pack

from .validator import load_pack, validate_pack


class PackRegistryError(ValueError):
    """A pack is unavailable or its checked-in evidence is inconsistent."""


@dataclass(frozen=True)
class PackSelection:
    pack: Pack
    fallback: bool
    draft_preview: bool
    notices: tuple[str, ...]


class PackRegistry:
    def __init__(
        self,
        root: Path,
        source_root: Path | None = None,
        *,
        deployed_demo_preview: bool = False,
        studio_catalog=None,
    ) -> None:
        self._registrations: set[str] = set()
        self.studio_catalog = studio_catalog
        self.root = root.resolve()
        self.deployed_demo_preview = deployed_demo_preview
        self.source_root = (source_root or self.root.parent / "docs/pack-sources").resolve()

    def register_known(self, name: str) -> "PackRegistry":
        """Explicit source author registration; never recursively discover arbitrary packs."""
        if name != "uk":
            raise PackRegistryError("unknown_pack_registration")
        self._known(name)
        self._registrations.add(name)
        return self

    def _known(self, name: str) -> "PackRegistry":
        pack_root, source_root = self.root / name, self.source_root / name
        if (
            not pack_root.resolve().is_relative_to(self.root)
            or not source_root.resolve().is_relative_to(self.source_root)
            or not pack_root.is_dir()
            or not source_root.is_dir()
        ):
            raise PackRegistryError("invalid_registered_pack_root")
        return PackRegistry(
            pack_root, source_root, deployed_demo_preview=self.deployed_demo_preview
        )

    def _owner(self, pack: Pack) -> "PackRegistry":
        for name in sorted(self._registrations):
            registered = self._known(name)
            for path in sorted(registered.root.glob("*.yaml")):
                current = load_pack(path)
                if (current.pack_id, current.version) == (pack.pack_id, pack.version):
                    if canonical_hash(current.model_dump(mode="json")) != canonical_hash(
                        pack.model_dump(mode="json")
                    ):
                        raise PackRegistryError("registered_pack_snapshot_changed")
                    return registered
        return self

    def proof(self, pack: Pack) -> str:
        if self.studio_catalog is not None and self.studio_catalog.resolve(pack) is not None:
            return self.studio_catalog.proof(pack)
        owner = self._owner(pack)
        passages = owner.passages(pack)
        records = json.loads(owner._read("retrievals.json")) if pack.sources else []
        selected = [record for record in records if record["id"] in {s.id for s in pack.sources}]
        return canonical_hash(
            {"pack": pack.model_dump(mode="json"), "sources": selected, "passages": passages}
        )

    def catalog_hash(self, **options) -> str:
        return canonical_hash([self.proof(pack) for pack in self.available(**options)])

    @staticmethod
    def public_metadata(pack: Pack) -> dict:
        return {
            "packId": pack.pack_id,
            "version": pack.version,
            "status": pack.status,
            "jurisdiction": pack.jurisdiction.model_dump(mode="json", by_alias=True),
            "languages": pack.languages,
            "timezone": pack.timezone,
            "currency": pack.currency,
            "unverifiedRuleIds": [
                rule.id
                for section in (
                    pack.recipients,
                    pack.sequencing,
                    pack.deadlines,
                    pack.liability_rules,
                )
                for rule in section
                if rule.status == "unverified"
            ],
        }

    def _read(self, relative: str) -> bytes:
        target = (self.source_root / relative).resolve()
        if not target.is_relative_to(self.source_root) or not target.is_file():
            raise PackRegistryError("invalid_source_path")
        if target.stat().st_size > 25_000_000:
            raise PackRegistryError("source_size_limit")
        return target.read_bytes()

    def _passages(self, pack: Pack) -> set[str]:
        if not pack.sources:
            return set()
        records = json.loads(self._read("retrievals.json"))
        passages = json.loads(self._read("passages.json"))
        by_id = {r["id"]: r for r in records}
        if len(by_id) != len(records):
            raise PackRegistryError("duplicate_source_record")
        valid: set[str] = set()
        for source in pack.sources:
            record = by_id.get(source.id)
            if not record or record["url"] != source.url or record["sha256"] != source.sha256:
                raise PackRegistryError("source_record_mismatch")
            if hashlib.sha256(self._read(record["snapshot"])).hexdigest() != source.sha256:
                raise PackRegistryError("snapshot_hash_mismatch")
            extraction = self._read(record["extraction"])
            if hashlib.sha256(extraction).hexdigest() != record["extraction_sha256"]:
                raise PackRegistryError("extraction_hash_mismatch")
            for passage in passages:
                if passage["source_id"] != source.id:
                    continue
                text = passage["text"]
                if (
                    hashlib.sha256(text.encode()).hexdigest() != passage["sha256"]
                    or text not in extraction.decode("utf-8")
                    or passage["id"] in valid
                    or not passage["id"].startswith(source.id + ":")
                ):
                    raise PackRegistryError("passage_integrity_failure")
                valid.add(passage["id"])
        return valid

    def passages(self, pack: Pack) -> dict[str, str]:
        """Return source-grounded passages only after checking saved evidence."""
        if self.studio_catalog is not None:
            value = self.studio_catalog.resolve(pack)
            if value is not None:
                return value[1]
        owner = self._owner(pack)
        if owner is not self:
            return owner.passages(pack)
        valid = self._passages(pack)
        if not valid:
            return {}
        records = json.loads(self._read("passages.json"))
        return {record["id"]: record["text"] for record in records if record["id"] in valid}

    def available(
        self,
        *,
        allow_draft_preview: bool = False,
        environment: str = "production",
        demo_mode: bool = False,
    ) -> list[Pack]:
        if allow_draft_preview and not (
            demo_mode
            and (environment == "local" or (environment == "dev" and self.deployed_demo_preview))
        ):
            raise PackRegistryError("draft_preview_requires_local_demo")
        if not self.root.is_dir():
            raise PackRegistryError("pack_directory_missing")
        packs = []
        identities: set[tuple[str, str]] = set()
        for path in sorted(self.root.glob("*.yaml")):
            if not path.resolve().is_relative_to(self.root):
                raise PackRegistryError("invalid_pack_path")
            pack = load_pack(path)
            if pack.status != "published" and not (allow_draft_preview and pack.status == "draft"):
                continue
            passages = self._passages(pack)
            if validate_pack(pack, passages):
                raise PackRegistryError("pack_validation_failed")
            identity = (pack.jurisdiction.code, pack.version)
            if identity in identities:
                raise PackRegistryError("duplicate_jurisdiction_version")
            identities.add(identity)
            packs.append(pack)
        for name in sorted(self._registrations):
            for pack in self._known(name).available(
                allow_draft_preview=allow_draft_preview,
                environment=environment,
                demo_mode=demo_mode,
            ):
                identity = (pack.jurisdiction.code, pack.version)
                if identity in identities:
                    raise PackRegistryError("duplicate_jurisdiction_version")
                identities.add(identity)
                packs.append(pack)
        if self.studio_catalog is not None:
            for pack in self.studio_catalog.available():
                identity = (pack.jurisdiction.code, pack.version)
                if identity in identities or any(
                    (item.pack_id, item.version) == (pack.pack_id, pack.version) for item in packs
                ):
                    raise PackRegistryError("duplicate_jurisdiction_version")
                identities.add(identity)
                packs.append(pack)
        return packs

    def select(
        self,
        country: str | None,
        *,
        allow_draft_preview: bool = False,
        environment: str = "production",
        demo_mode: bool = False,
    ) -> PackSelection:
        if country is not None and not re.fullmatch(r"[A-Za-z]{2}", country):
            raise PackRegistryError("invalid_country_code")
        packs = self.available(
            allow_draft_preview=allow_draft_preview, environment=environment, demo_mode=demo_mode
        )
        country = country.upper() if country else None
        matches = [p for p in packs if p.jurisdiction.code == country]
        fallback = not matches
        if fallback:
            matches = [p for p in packs if p.jurisdiction.code == "GENERIC"]
        if not matches:
            raise PackRegistryError("no_published_pack")
        published = [p for p in matches if p.status == "published"]
        pack = max(published or matches, key=lambda p: tuple(int(x) for x in p.version.split(".")))
        draft = pack.status == "draft"
        notices: tuple[str, ...] = (
            ("DRAFT: unverified demonstration; human review pending.",) if draft else ()
        )
        if fallback:
            notices += ("No jurisdiction-specific pack selected; confirm your country.",)
        return PackSelection(pack, fallback, draft, notices)
