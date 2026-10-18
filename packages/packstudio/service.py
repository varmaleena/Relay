"""Reviewer-org jobs, explicit decisions and immutable published Pack versions."""

import asyncio
import json
import re
from datetime import timedelta
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from agents.packbuilder.models import PackBuildResult
from agents.packbuilder.workflow import checked_sources, validate_item
from packages.common.identifiers import canonical_hash, new_id
from packages.intake.service import IntakeError, stamp
from packages.safety.guard import scrub_credentials

from .adapter import PASSES, load_sources


def clean(value):
    if len(json.dumps(value, ensure_ascii=False)) > 250000:
        raise IntakeError(422, "unsafe_content_blocked")

    def visit(item, key=""):
        if isinstance(item, dict):
            for name, child in item.items():
                visit(child, name)
        elif isinstance(item, list):
            for child in item:
                visit(child, key)
        elif isinstance(item, str):
            # Structural hashes and reserved source IDs are not free-text credentials.
            # Validate their full shape; never exempt source quotes or human text.
            if key in {"sha256", "extractionHash", "passageSha256"} and re.fullmatch(
                r"[a-f0-9]{64}", item
            ):
                return
            if key in {"sourceIds", "id"} and re.fullmatch(r"src_[a-f0-9]{32}", item):
                return
            if key in {"sourceRefs", "passageId"} and re.fullmatch(
                r"src_[a-f0-9]{32}:p[0-9]{4}", item
            ):
                return
            if scrub_credentials(item) != item:
                raise IntakeError(422, "unsafe_content_blocked")

    visit(value)


class PackStudioService:
    def __init__(self, sources, builder):
        self.sources, self.repository, self.builder = sources, sources.repository, builder
        self.clock = sources.clock

    def reviewer(self, actor):
        return self.sources.reviewer(actor)

    def _build(self, tx, actor, build_id):
        org = self.reviewer(actor)
        if not re.fullmatch(r"build_[a-f0-9]{32}", build_id):
            raise IntakeError(404, "not_found")
        build = tx.get(f"packBuilds/{build_id}")
        if not build or build["orgId"] != org:
            raise IntakeError(404, "not_found")
        return build

    def _mutate(self, actor, route, key, body, callback):
        org = self.reviewer(actor)
        try:
            key = str(UUID(key))
        except (ValueError, TypeError):
            raise IntakeError(400, "bad_request") from None
        clean(body)
        path = "studioRequests/" + canonical_hash([org, actor.uid, route, key])
        digest = canonical_hash(body)

        def write(tx):
            previous = tx.get(path)
            if previous:
                if previous["bodyHash"] != digest:
                    raise IntakeError(409, "idempotency_conflict")
                return previous["result"]
            result = callback(tx)
            tx.set(
                path,
                {
                    "bodyHash": digest,
                    "result": result,
                    "orgId": org,
                    "createdAt": stamp(self.clock()),
                },
            )
            return result

        return self.repository.atomic(write)

    def _event(self, tx, actor, build, action, details=None):
        event_id = new_id("event")
        tx.set(
            f"packBuilds/{build['buildId']}/events/{event_id}",
            {
                "eventId": event_id,
                "actorUid": actor.uid,
                "orgId": actor.org_id,
                "action": action,
                "at": stamp(self.clock()),
                "details": details or {},
            },
        )

    def create(self, actor, body, key):
        self.reviewer(actor)
        ids = body.get("sourceIds", [])
        if (
            set(body) - {"sourceIds", "jurisdictionCode", "name", "archetype", "goldPackId"}
            or type(ids) is not list
            or not 1 <= len(ids) <= 8
            or len(set(ids)) != len(ids)
            or not re.fullmatch(r"[A-Z]{2,12}", body.get("jurisdictionCode", ""))
            or not 1 <= len(body.get("name", "")) <= 200
            or body.get("archetype")
            not in {"centralized_rail", "mandatory_reimbursement", "fragmented"}
        ):
            raise IntakeError(422, "validation_failed")
        _, proofs = load_sources(self.sources, actor, ids)

        def create(tx):
            self._proof_guard(tx, actor, proofs)
            build_id, job_id = new_id("build"), new_id("job")
            build = {
                "buildId": build_id,
                "orgId": actor.org_id,
                "createdBy": actor.uid,
                "createdAt": stamp(self.clock()),
                "state": "queued",
                "revision": 1,
                "request": body,
                "sourceProofs": proofs,
                "jobId": job_id,
                "reviews": {},
                "passes": [{"name": p, "state": "queued", "itemCount": None} for p in PASSES],
            }
            tx.set(f"packBuilds/{build_id}", build)
            tx.set(
                f"jobs/{job_id}",
                {
                    "jobId": job_id,
                    "type": "pack_build",
                    "resourceId": build_id,
                    "uid": actor.uid,
                    "orgId": actor.org_id,
                    "state": "queued",
                    "attempts": 0,
                    "createdAt": stamp(self.clock()),
                    "progress": {"step": 0, "total": 5},
                    "error": None,
                },
            )
            self._event(tx, actor, build, "pack.build_requested")
            return {"buildId": build_id, "jobId": job_id, "statusUrl": f"/api/v1/jobs/{job_id}"}

        return self._mutate(actor, "create", key, body, create)

    def _proof_guard(self, tx, actor, proofs):
        for proof in proofs:
            source = self.sources._source(tx, actor, proof["sourceId"])
            if source.get("state") != "ready" or any(
                source.get(field) != proof[field]
                for field in ("sha256", "extractionHash", "storagePath")
            ):
                raise IntakeError(409, "source_proof_invalid")
            meta = proof["metadata"]
            if (
                source["title"] != meta["title"]
                or source["publisher"] != meta["publisher"]
                or (source.get("finalUrl") or source.get("url")) != meta["url"]
            ):
                raise IntakeError(409, "source_proof_invalid")

    async def process(self, job_id):
        from packages.safety import Actor

        def claim(tx):
            job = tx.get(f"jobs/{job_id}")
            if (
                not job
                or job.get("type") != "pack_build"
                or job["state"] not in {"queued", "running"}
            ):
                return None
            if job.get("leaseUntil", "") > stamp(self.clock()) or job["attempts"] >= 3:
                return None
            actor = Actor(job["uid"], "reviewer", job["orgId"])
            build = self._build(tx, actor, job["resourceId"])
            token = new_id("claim")
            job.update(
                state="running",
                attempts=job["attempts"] + 1,
                claimToken=token,
                leaseUntil=stamp(self.clock() + timedelta(seconds=240)),
            )
            build["state"] = "running"
            tx.set(f"jobs/{job_id}", job)
            tx.set(f"packBuilds/{build['buildId']}", build)
            return job, build, actor

        claimed = self.repository.atomic(claim)
        if not claimed:
            return
        job, build, actor = claimed

        def guard(tx):
            latest = tx.get(f"jobs/{job_id}")
            if (
                not latest
                or latest.get("claimToken") != job["claimToken"]
                or latest["state"] != "running"
            ):
                raise IntakeError(409, "version_conflict")
            current = self._build(tx, actor, build["buildId"])
            self._proof_guard(tx, actor, current["sourceProofs"])
            return latest, current

        def progress(name, state):
            def write(tx):
                latest, current = guard(tx)
                next(p for p in current["passes"] if p["name"] == name)["state"] = state
                latest["progress"]["step"] = sum(
                    p["state"] == "completed" for p in current["passes"]
                )
                tx.set(f"jobs/{job_id}", latest)
                tx.set(f"packBuilds/{build['buildId']}", current)

            self.repository.atomic(write)

        try:
            sources, proofs = await asyncio.to_thread(
                load_sources, self.sources, actor, build["request"]["sourceIds"]
            )
            if proofs != build["sourceProofs"]:
                raise IntakeError(409, "source_proof_invalid")
            _, _, proof_hash = checked_sources(sources)
            request = build["request"]
            result = await asyncio.wait_for(
                self.builder.build(
                    sources=sources,
                    jurisdiction_code=request["jurisdictionCode"],
                    name=request["name"],
                    archetype=request["archetype"],
                    progress=progress,
                ),
                timeout=185,
            )
            result = PackBuildResult.model_validate(result.model_dump(mode="json", by_alias=True))

            if (
                result.source_proof_hash != proof_hash
                or result.jurisdiction_code != request["jurisdictionCode"]
                or result.name != request["name"]
                or result.archetype != request["archetype"]
                or result.sources != [s.source for s in sources]
            ):
                raise IntakeError(409, "source_proof_invalid")

            def finish(tx):
                latest, current = guard(tx)
                current.update(
                    state="draft", revision=1, result=result.model_dump(mode="json", by_alias=True)
                )
                for p in current["passes"]:
                    p.update(state="completed", itemCount=len(getattr(result, p["name"]).items))
                latest.update(
                    state="succeeded", leaseUntil=None, progress={"step": 5, "total": 5}, error=None
                )
                tx.set(f"jobs/{job_id}", latest)
                tx.set(f"packBuilds/{build['buildId']}", current)

            self.repository.atomic(finish)
        except Exception:

            def fail(tx):
                latest = tx.get(f"jobs/{job_id}")
                if latest and latest.get("claimToken") == job["claimToken"]:
                    latest.update(
                        state="failed",
                        leaseUntil=None,
                        error={"code": "pack_build_unavailable", "retryable": False},
                    )
                    current = tx.get(f"packBuilds/{build['buildId']}")
                    if current:
                        current.update(state="failed")
                        tx.set(f"packBuilds/{build['buildId']}", current)
                    tx.set(f"jobs/{job_id}", latest)

            self.repository.atomic(fail)

    @staticmethod
    def _items(build):
        result = PackBuildResult.model_validate(build["result"])
        return {item.id: (name, item) for name in PASSES for item in getattr(result, name).items}

    def get(self, actor, build_id):
        build = self._build(self.repository, actor, build_id)
        draft: dict[str, Any] = {
            "recipients": [],
            "deadlines": [],
            "liabilityRules": [],
            "sequencing": [],
            "forms": [],
            "crisisSupport": [],
            "conflicts": [],
        }
        verdicts = []
        if build.get("result"):
            for name, item in self._items(build).values():
                target = {"remedies": "liabilityRules", "support": "crisisSupport"}.get(name, name)
                draft[target].append(
                    {
                        "id": item.id,
                        "body": item.model_dump(mode="json", by_alias=True),
                        "sourceRefs": item.source_refs,
                        "supportingParaphrase": " ".join(
                            span.paraphrase for span in item.evidence_spans
                        ),
                        "status": "unverified",
                        "conflict": item.conflict,
                    }
                )
            verdicts = [item["verdict"] for item in build["result"]["review"]]
        blockers = [
            "canonical_pack_required",
            "explicit_conditions_required",
            "human_checklist_required",
        ]
        if build.get("result") and set(self._items(build)) - set(build["reviews"]):
            blockers.append("unreviewed_items")
        return {
            "state": build["state"],
            "passes": build["passes"],
            "draft": draft,
            "verdicts": verdicts,
            "evalVsGold": None,
            "revision": build["revision"],
            "reviews": build["reviews"],
            "publicationBlockers": [] if build["state"] == "published" else blockers,
            "sourceIds": build["request"]["sourceIds"],
        }

    def review(self, actor, build_id, rule_id, body, key):
        existing = self._build(self.repository, actor, build_id)
        sources, proofs = load_sources(self.sources, actor, existing["request"]["sourceIds"])
        _, indexed, _ = checked_sources(sources)

        def write(tx):
            build = self._build(tx, actor, build_id)
            if build["state"] not in {"draft", "reviewed"}:
                raise IntakeError(409, "invalid_state_transition")
            self._proof_guard(tx, actor, proofs)
            if (
                proofs != build["sourceProofs"]
                or type(body.get("ifRevision")) is not int
                or body["ifRevision"] != build["revision"]
            ):
                raise IntakeError(409, "version_conflict")
            items = self._items(build)
            if rule_id not in items:
                raise IntakeError(404, "not_found")
            name, item = items[rule_id]
            action = body.get("action")
            if set(body) - {"action", "edit", "note", "ifRevision"} or action not in {
                "accept",
                "edit",
                "reject",
            }:
                raise IntakeError(422, "validation_failed")
            if action == "edit":
                try:
                    edited = type(item).model_validate(body.get("edit"))
                    if (
                        edited.id != rule_id
                        or edited.source_refs != item.source_refs
                        or edited.evidence_spans != item.evidence_spans
                    ):
                        raise ValueError()
                    validate_item(edited, indexed)
                except (ValueError, ValidationError):
                    raise IntakeError(422, "validation_failed") from None
                entries = build["result"][name]["items"]
                entries[next(i for i, value in enumerate(entries) if value["id"] == rule_id)] = (
                    edited.model_dump(mode="json", by_alias=True)
                )
            elif body.get("edit") is not None:
                raise IntakeError(422, "validation_failed")
            build["reviews"][rule_id] = {
                "state": {"accept": "accepted", "edit": "edited", "reject": "rejected"}[action],
                "note": body.get("note") or "",
                "edited": action == "edit"
                or build["reviews"].get(rule_id, {}).get("edited", False),
                "actorUid": actor.uid,
                "at": stamp(self.clock()),
            }
            build["revision"] += 1
            build["state"] = "reviewed" if set(items) <= set(build["reviews"]) else "draft"
            tx.set(f"packBuilds/{build_id}", build)
            self._event(
                tx,
                actor,
                build,
                "pack.rule_reviewed",
                {"ruleId": rule_id, "state": build["reviews"][rule_id]["state"]},
            )
            return {
                "ruleId": rule_id,
                "state": build["reviews"][rule_id]["state"],
                "revision": build["revision"],
            }

        return self._mutate(actor, f"review/{build_id}/{rule_id}", key, body, write)

    def publish(self, actor, build_id, body, key):
        from .publication import prepare_publication

        existing = self._build(self.repository, actor, build_id)
        sources, proofs = load_sources(self.sources, actor, existing["request"]["sourceIds"])

        def write(tx):
            build = self._build(tx, actor, build_id)
            self._proof_guard(tx, actor, proofs)
            if (
                proofs != build["sourceProofs"]
                or build["state"] != "reviewed"
                or type(body.get("ifRevision")) is not int
                or body["ifRevision"] != build["revision"]
            ):
                raise IntakeError(409, "version_conflict")
            pack = prepare_publication(build, body, sources, stamp(self.clock()))
            path = f"packs/{pack.pack_id}/versions/{pack.version}"
            registration = tx.get(f"packRegistrations/{pack.pack_id}")
            if tx.get(path) or (registration and registration["orgId"] != actor.org_id):
                raise IntakeError(409, "version_conflict")
            versions = (registration or {}).get("versions", [])
            if versions and tuple(map(int, pack.version.split("."))) <= max(
                tuple(map(int, v.split("."))) for v in versions
            ):
                raise IntakeError(409, "version_conflict")
            published = {
                "pack": pack.model_dump(mode="json", by_alias=True),
                "orgId": actor.org_id,
                "buildId": build_id,
                "sourceProofs": proofs,
                "evidenceReview": build["result"],
                "humanReviews": build["reviews"],
                "reviewChecklist": body["reviewChecklist"],
                "publishedBy": actor.uid,
                "publishedAt": stamp(self.clock()),
            }
            tx.set(path, published)
            tx.set(
                f"packRegistrations/{pack.pack_id}",
                {"orgId": actor.org_id, "versions": versions + [pack.version]},
            )
            build.update(
                state="published",
                revision=build["revision"] + 1,
                packId=pack.pack_id,
                version=pack.version,
            )
            tx.set(f"packBuilds/{build_id}", build)
            self._event(
                tx,
                actor,
                build,
                "pack.published",
                {"packId": pack.pack_id, "version": pack.version},
            )
            return {"packId": pack.pack_id, "version": pack.version, "status": "published"}

        return self._mutate(actor, f"publish/{build_id}", key, body, write)

    def retire(self, actor, pack_id, version, body, key):
        self.reviewer(actor)
        if (
            not re.fullmatch(r"pack_[a-z][a-z0-9_-]{0,79}", pack_id)
            or not re.fullmatch(r"\d+\.\d+\.\d+", version)
            or not isinstance(body.get("reason"), str)
            or not body["reason"].strip()
            or len(body["reason"]) > 2000
        ):
            raise IntakeError(422, "validation_failed")

        def write(tx):
            publication = tx.get(f"packs/{pack_id}/versions/{version}")
            if not publication or publication["orgId"] != actor.org_id:
                raise IntakeError(404, "not_found")
            path = f"packRetirements/{pack_id}_{version}"
            if not tx.get(path):
                tx.set(
                    path,
                    {
                        "orgId": actor.org_id,
                        "by": actor.uid,
                        "at": stamp(self.clock()),
                        "reason": body["reason"],
                    },
                )
            build = self._build(tx, actor, publication["buildId"])
            self._event(tx, actor, build, "pack.retired", {"packId": pack_id, "version": version})
            return {"packId": pack_id, "version": version, "status": "retired"}

        return self._mutate(actor, f"retire/{pack_id}/{version}", key, body, write)
