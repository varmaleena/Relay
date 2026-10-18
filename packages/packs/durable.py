"""Read-only, bounded catalog of explicitly human-published Studio versions."""

import re
from types import SimpleNamespace

from packages.common.identifiers import canonical_hash
from packages.schemas import Pack

from .registry import PackRegistryError


class StudioCatalog:
    """Reuse Studio's immutable publication records; never publish or infer review."""

    def __init__(self, sources):
        self.sources = sources
        self.repository = sources.repository

    def _registrations(self):
        repository = self.repository
        if hasattr(repository, "client"):
            values = [
                (item.id, item.to_dict())
                for item in repository.client.collection("packRegistrations").limit(51).stream()
            ]
        elif hasattr(repository, "documents"):
            values = [
                (path.split("/")[1], value)
                for path, value in sorted(repository.documents.items())
                if path.startswith("packRegistrations/") and path.count("/") == 1
            ][:51]
        else:
            raise PackRegistryError("unsupported_catalog_repository")
        if len(values) > 50:
            raise PackRegistryError("catalog_size_limit")
        return values

    def _load(self):
        from packages.packstudio.adapter import load_sources
        from packages.packstudio.publication import prepare_publication

        loaded = {}
        try:
            for pack_id, registration in self._registrations():
                if not re.fullmatch(r"pack_[a-z][a-z0-9_-]{0,79}", pack_id):
                    raise ValueError()
                versions = registration["versions"]
                if (
                    not isinstance(versions, list)
                    or len(versions) > 20
                    or len(set(versions)) != len(versions)
                ):
                    raise ValueError()
                for version in versions:
                    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
                        raise ValueError()
                    record = self.repository.get(f"packs/{pack_id}/versions/{version}")
                    if not record or record["orgId"] != registration["orgId"]:
                        raise ValueError()
                    retirement = self.repository.get(f"packRetirements/{pack_id}_{version}")
                    if retirement is not None:
                        if (
                            retirement["orgId"] != registration["orgId"]
                            or not retirement.get("by")
                            or not retirement.get("at")
                            or not retirement.get("reason", "").strip()
                        ):
                            raise ValueError()
                        continue
                    pack = Pack.model_validate(record["pack"])
                    if (pack.pack_id, pack.version, pack.status) != (pack_id, version, "published"):
                        raise ValueError()
                    actor = SimpleNamespace(
                        role="reviewer", uid=record["publishedBy"], org_id=record["orgId"]
                    )
                    sources, proofs = load_sources(
                        self.sources, actor, [source.id for source in pack.sources]
                    )
                    if proofs != record["sourceProofs"]:
                        raise ValueError()
                    build = self.repository.get("packBuilds/" + record["buildId"])
                    if (
                        not build
                        or build["orgId"] != record["orgId"]
                        or build["result"] != record["evidenceReview"]
                        or build["reviews"] != record["humanReviews"]
                        or build["sourceProofs"] != proofs
                    ):
                        raise ValueError()
                    draft = pack.model_dump(mode="json", by_alias=True)
                    draft["status"] = "draft"
                    rebuilt = prepare_publication(
                        build,
                        {
                            "packDraft": draft,
                            "reviewChecklist": record["reviewChecklist"],
                            "reviewerName": pack.review.reviewer,
                            "notes": pack.review.notes,
                            "acceptUnverifiedRuleIds": pack.review.accepted_unverified_rule_ids,
                        },
                        sources,
                        record["publishedAt"],
                    )
                    if rebuilt != pack:
                        raise ValueError()
                    passages = {
                        passage.passage_id: passage.text
                        for source in sources
                        for passage in source.passages
                    }
                    loaded[(pack_id, version)] = (pack, passages, proofs)
            return loaded
        except PackRegistryError:
            raise
        except Exception:
            # Stored reviewer names, notes and underlying storage exceptions stay private.
            raise PackRegistryError("durable_catalog_integrity_failure") from None

    def available(self):
        return [value[0] for value in self._load().values()]

    def resolve(self, pack):
        value = self._load().get((pack.pack_id, pack.version))
        registration = self.repository.get("packRegistrations/" + pack.pack_id)
        if value is None and registration and pack.version in registration.get("versions", []):
            raise PackRegistryError("published_pack_unavailable")
        if value is not None and value[0] != pack:
            raise PackRegistryError("published_pack_snapshot_changed")
        return value

    def proof(self, pack):
        value = self.resolve(pack)
        if value is None:
            raise PackRegistryError("published_pack_unavailable")
        return canonical_hash(
            {"pack": pack.model_dump(mode="json"), "passages": value[1], "sources": value[2]}
        )
