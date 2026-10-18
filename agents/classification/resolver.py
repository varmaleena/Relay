"""Reviewed/published pack selection is deterministic; no model guesses a country."""

import re
from dataclasses import dataclass

from packages.schemas.models import CaseFacts, Pack


@dataclass(frozen=True)
class ResolvedPack:
    pack: Pack
    confidence: float
    reason: str
    notice: str | None
    unverified: bool
    needs_country_confirmation: bool = False

    @property
    def pack_id(self) -> str:
        return self.pack.pack_id

    @property
    def version(self) -> str:
        return self.pack.version


def _version(pack: Pack) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", pack.version)
    if not match:
        raise ValueError("pack_version_requires_stable_semver")
    return int(match[1]), int(match[2]), int(match[3])


class JurisdictionResolver:
    def resolve(
        self,
        *,
        packs: list[Pack],
        facts: CaseFacts,
        selected_country: str | None = None,
        allow_draft_demo: bool = False,
        demo_pack_id: str | None = None,
        environment: str = "local",
        demo_mode: bool = True,
        deployed_demo_preview: bool = False,
    ) -> ResolvedPack:
        if allow_draft_demo and not (
            demo_mode
            and (environment == "local" or (environment == "dev" and deployed_demo_preview))
        ):
            raise ValueError("draft_demo_local_only")
        country = selected_country
        confidence = 1.0 if country else 0.0
        if not country and facts.country and facts.country.availability == "available":
            provenance = facts.country.provenance
            if provenance.source in {"selected", "confirmed", "victim_statement", "statement"}:
                country = str(facts.country.value or "")
                confidence = (
                    1.0
                    if provenance.source in {"selected", "confirmed"}
                    else provenance.confidence or 0.0
                )
        if country and not re.fullmatch(r"[A-Z]{2}", country):
            if selected_country is not None:
                raise ValueError("invalid_selected_country")
            country, confidence = None, 0.0
        if country in {"XX", "ZZ"}:
            country, confidence = None, 0.0
        if demo_pack_id and not allow_draft_demo:
            raise ValueError("draft_demo_requires_explicit_opt_in")
        if demo_pack_id and country and confidence >= 0.8:
            if not allow_draft_demo:
                raise ValueError("draft_demo_requires_explicit_opt_in")
            candidates = [
                pack
                for pack in packs
                if pack.pack_id == demo_pack_id
                and pack.status == "draft"
                and (not country or pack.jurisdiction.code == country)
            ]
            if not candidates:
                raise ValueError("draft_demo_pack_not_found")
            pack = max(candidates, key=_version)
            return ResolvedPack(
                pack,
                confidence,
                "explicit_draft_demo",
                "Unverified draft rules: demonstration only; no human review is recorded.",
                True,
            )
        candidates = [
            pack
            for pack in packs
            if pack.status == "published" and pack.jurisdiction.code == country
        ]
        if candidates and confidence >= 0.8:
            pack = max(candidates, key=_version)
            unverified = any(
                rule.status == "unverified"
                for rule in [
                    *pack.recipients,
                    *pack.sequencing,
                    *pack.deadlines,
                    *pack.liability_rules,
                ]
            )
            return ResolvedPack(
                pack,
                confidence,
                "published_country_match",
                "This published pack contains labeled unverified rules." if unverified else None,
                unverified,
            )
        generic = [
            pack
            for pack in packs
            if pack.pack_id == "pack_generic_fragmented"
            and (pack.status == "published" or (pack.status == "draft" and allow_draft_demo))
        ]
        if not generic:
            raise ValueError("generic_pack_missing")
        return ResolvedPack(
            max(generic, key=_version),
            confidence,
            "generic_fallback",
            (
                "Generic guidance: no published pack confidently matches this country. "
                "Rules are unverified; confirm channels with the institution."
            ),
            True,
            needs_country_confirmation=not country or confidence < 0.8,
        )
