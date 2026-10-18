"""M1 use cases. Models suggest facts; trusted transactions own every mutation."""

import hashlib
import json
import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from packages.common.identifiers import canonical_hash, idempotency_scope, new_id
from packages.safety import Actor
from packages.safety.guard import SafetyGuard, scrub_credentials
from packages.schemas import CaseFacts, EvidenceExtraction

from .files import validate_file
from .repository import Repository, Transaction
from .storage import BlobStore


class IntakeError(ValueError):
    def __init__(
        self, status: int, code: str, detail: str = "The operation could not be completed"
    ) -> None:
        self.status, self.code, self.detail = status, code, detail
        self.retry_after: int | None = None
        super().__init__(code)


def stamp(now: datetime) -> str:
    return now.astimezone(UTC).isoformat().replace("+00:00", "Z")


def missing_minimum(facts: dict[str, Any]) -> list[str]:
    payment, contact = facts.get("payment", {}), facts.get("contact", {})
    required = {
        "country": bool((facts.get("country") or {}).get("value")),
        "payment.method": bool(payment.get("method")),
        "payment.amount": bool(payment.get("amount")),
        "payment.timestamp": bool(payment.get("timestamp")),
        "contact.channel": bool(contact.get("channel")),
        "ongoingContact": facts.get("ongoingContact") is not None,
    }
    return [key for key, present in required.items() if not present]


def intake_history(case: dict[str, Any], actor: Actor) -> list[dict[str, str]]:
    """Complete recent victim statements only, with original reporting times.

    Never accept request-provided history or assistant output as fact evidence.
    Keep the newest contiguous statements within six turns and 16,000 chars.
    """
    if case.get("victimUid") != actor.uid or actor.role != "victim":
        raise IntakeError(403, "forbidden")
    history: list[dict[str, str]] = []
    characters = 0
    for turn in reversed(case.get("transcript", [])):
        if turn.get("role") != "user":
            continue
        text, reported_at = turn.get("text"), turn.get("ts")
        if type(text) is not str or type(reported_at) is not str:
            continue
        safe = scrub_credentials(text)
        if len(history) >= 6 or characters + len(safe) > 16_000:
            break
        characters += len(safe)
        history.append({"text": safe, "at": reported_at})
    return list(reversed(history))


def planning_input_hash(case: dict[str, Any], evidence: list[dict[str, Any] | None]) -> str:
    """A new statement or extraction invalidates analysis even if facts were omitted."""
    return canonical_hash(
        {
            "facts": case["facts"],
            "history": intake_history(case, Actor(case["victimUid"], "victim")),
            "evidence": [
                item["extraction"]
                for item in evidence
                if item and item["status"] == "ready" and item.get("extraction")
            ],
        }
    )


def merge_facts(
    current: dict[str, Any],
    delta: dict[str, Any],
    *,
    confirmed: bool,
    now: datetime,
    statement_reference: str | None = None,
) -> dict[str, Any]:
    # Only a server transaction that persists the actual victim turn may supply this.
    if statement_reference is not None and (
        confirmed
        or not re.fullmatch(
            r"case:case_[A-Za-z0-9_-]{1,100}:turn:turn_[A-Za-z0-9_-]{1,100}:facts:[1-9][0-9]{0,8}",
            statement_reference,
        )
    ):
        raise IntakeError(422, "validation_failed")
    if len(json.dumps(delta, ensure_ascii=False)) > 32_000:
        raise IntakeError(413, "payload_too_large")
    # Model/client provenance metadata is never authoritative.
    delta = {
        key: value
        for key, value in delta.items()
        if key not in {"fieldProvenance", "unavailableFields"}
    }
    updated = {**current}
    provenance = dict(current.get("fieldProvenance", {}))

    def walk(target: dict[str, Any], changes: dict[str, Any], prefix: str = "") -> dict[str, Any]:
        result = dict(target)
        for key, value in changes.items():
            path = f"{prefix}.{key}" if prefix else key
            if key == "provenance":
                continue
            prior = provenance.get(path, {})
            if not confirmed and prior.get("source") == "confirmed":
                continue
            if isinstance(value, dict):
                result[key] = walk(result.get(key) or {}, value, path)
            elif value is not None or confirmed:
                if isinstance(value, str):
                    if len(value) > 4000 or scrub_credentials(value) != value:
                        raise IntakeError(422, "unsafe_content_blocked")
                unchanged = key in result and result[key] == value
                result[key] = value
                # Repeated output cannot replace an earlier origin or launder legacy gaps.
                if not confirmed and unchanged and prior:
                    continue
                provenance[path] = {"source": "confirmed" if confirmed else "victim_statement"}
                if not confirmed and statement_reference:
                    provenance[path]["reference"] = statement_reference
        return result

    updated = walk(updated, delta)
    if updated.get("country") and "country" in delta:
        prior_country = (current.get("country") or {}).get("provenance", {})
        updated["country"]["provenance"] = {
            "source": "confirmed"
            if confirmed
            else ("confirmed" if prior_country.get("source") == "confirmed" else "victim_statement")
        }
    for parent, parts in {
        "payment.amount": ("value", "currency"),
        "payment.recipientIdentifier": ("value", "type"),
    }.items():
        components = [provenance.get(f"{parent}.{part}", {}) for part in parts]
        if any(components):
            provenance.pop(parent, None)
            if (
                all(part and part.get("source") == "victim_statement" for part in components)
                and components[0].get("reference")
                and all(part.get("reference") == components[0]["reference"] for part in components)
            ):
                provenance[parent] = {
                    "source": "victim_statement",
                    "reference": components[0]["reference"],
                }
    updated["fieldProvenance"] = provenance
    try:
        result = CaseFacts.model_validate(updated)
        if result.payment.timestamp and result.payment.timestamp > now:
            raise IntakeError(422, "validation_failed", "Payment time cannot be in the future")
        return result.model_dump(mode="json", by_alias=True)
    except ValidationError as exc:
        raise IntakeError(422, "validation_failed") from exc


class IntakeService:
    CONSENT_VERSION = "1.0"

    def __init__(
        self,
        repository: Repository,
        storage: BlobStore,
        intake_agent: Any,
        evidence_agent: Any,
        *,
        clock: Any = None,
    ) -> None:
        self.repository, self.storage = repository, storage
        self.export_storage = storage
        self.receiver: Any = None
        self.receiver_handoff: Any = None
        self.sources: Any = None
        self.packstudio: Any = None
        self.linking: Any = None
        self.receiver_links: Any = None
        self.intake_agent, self.evidence_agent = intake_agent, evidence_agent
        self.clock = clock or (lambda: datetime.now(UTC))
        self.guard = SafetyGuard()
        self.planning: Any = None
        self.packets: Any = None

    def _case(
        self, tx: Transaction | Repository, case_id: str, actor: Actor, *, allow_admin: bool = False
    ) -> dict[str, Any]:
        case = tx.get(f"cases/{case_id}")
        if not case or case.get("deleted") or case.get("deleting"):
            raise IntakeError(404, "not_found")
        if datetime.fromisoformat(case["ttlAt"].replace("Z", "+00:00")) <= self.clock():
            raise IntakeError(404, "not_found")
        if not (actor.role == "victim" and case["victimUid"] == actor.uid) and not (
            allow_admin and actor.role == "admin"
        ):
            raise IntakeError(403, "forbidden")
        return case

    def _event(
        self, tx: Transaction, case_id: str, actor: Actor, action: str, payload: Any = None
    ) -> None:
        event_id = new_id("event")
        tx.set(
            f"cases/{case_id}/events/{event_id}",
            {
                "eventId": event_id,
                "ts": stamp(self.clock()),
                "actorType": actor.role,
                "actorId": actor.uid,
                "action": action,
                "targetType": "case",
                "targetId": case_id,
                "payloadHash": canonical_hash(payload),
                "traceId": new_id("trace"),
                "details": {},
            },
        )
        case = tx.get(f"cases/{case_id}")
        if case:
            if action in {
                "facts.updated",
                "intake.message_received",
                "evidence.confirmed",
                "live.facts_recorded",
                "plan.ready",
                "evidence.extracted",
                "plan.clarification_required",
            }:
                # Only trusted victim-side mutations touch these known references.
                # Receiver queries never fetch the full case to detect stale facts.
                for reference in case.get("receiverProjectionRefs", []):
                    projection_path = (
                        f"receiverViews/{reference['orgId']}/cases/{case_id}"
                        f"/packets/{reference['packetId']}"
                    )
                    projection = tx.get(projection_path)
                    if projection:
                        projection["packet"]["stale"] = True
                        tx.set(projection_path, projection)
            case.setdefault("eventIds", []).append(event_id)
            case["updatedAt"] = stamp(self.clock())
            tx.set(f"cases/{case_id}", case)

    def _mutation(self, actor: Actor, route: str, key: str, payload: Any, callback: Any) -> Any:
        try:
            UUID(key)
        except ValueError as exc:
            raise IntakeError(400, "bad_request", "Idempotency-Key must be a UUID") from exc
        scoped = idempotency_scope(actor.uid, actor.org_id, "POST", route, key)
        path, digest, now = f"idempotency/{scoped}", canonical_hash(payload), self.clock()

        def apply(tx: Transaction) -> Any:
            previous = tx.get(path)
            if previous and previous["expiresAt"] > stamp(now):
                if previous["bodyHash"] != digest:
                    raise IntakeError(409, "idempotency_conflict")
                return previous["result"]
            result = callback(tx)
            tx.set(
                path,
                {
                    "bodyHash": digest,
                    "result": result,
                    "expiresAt": stamp(now + timedelta(hours=24)),
                    "uid": actor.uid,
                },
            )
            case_id = result.get("caseId") if isinstance(result, dict) else None
            if not case_id and route.startswith("/cases/"):
                case_id = route.split("/")[2]
            if case_id:
                case = tx.get(f"cases/{case_id}")
                if case:
                    case.setdefault("idempotencyIds", []).append(scoped)
                    tx.set(f"cases/{case_id}", case)
            return result

        return self.repository.atomic(apply)

    def rate_limit(
        self, actor: Actor, *, create: bool = False, client_key: str = "", deletion: bool = False
    ) -> dict[str, int]:
        now = self.clock().timestamp()
        scopes = (
            [(f"deletion:{actor.uid}", 60, 5)] if deletion else [(f"session:{actor.uid}", 60, 30)]
        )
        if create:
            scopes.append((f"creation:{client_key or actor.uid}", 3600, 10))

        def consume(tx: Transaction) -> dict[str, int]:
            result = {"limit": 30, "remaining": 29}
            for scope, window, maximum in scopes:
                path = "rateLimits/" + canonical_hash(scope)
                row = tx.get(path) or {"timestamps": []}
                hits = [item for item in row["timestamps"] if item > now - window]
                if len(hits) >= maximum:
                    error = IntakeError(429, "rate_limited")
                    error.retry_after = max(1, math.ceil(min(hits) + window - now))
                    raise error
                tx.set(
                    path,
                    {
                        "timestamps": hits + [now],
                        "expiresAt": stamp(self.clock() + timedelta(seconds=window)),
                    },
                )
                result = {"limit": maximum, "remaining": maximum - len(hits) - 1}
            return result

        return self.repository.atomic(consume)

    def create_case(self, actor: Actor, body: dict[str, Any], key: str) -> dict[str, Any]:
        if actor.role != "victim":
            raise IntakeError(403, "forbidden")
        if body["consentVersion"] != self.CONSENT_VERSION:
            raise IntakeError(403, "consent_required")
        if body.get("countryHint") and not re.fullmatch(r"[A-Z]{2}", body["countryHint"]):
            raise IntakeError(422, "validation_failed")
        case_id, now = new_id("case"), self.clock()
        case_ref = f"RLY-{now.year}-{int(case_id[-8:], 16) % 1000000:06d}"

        def create(tx: Transaction) -> dict[str, Any]:
            facts = CaseFacts().model_dump(mode="json", by_alias=True)
            if body.get("countryHint"):
                facts["country"] = {
                    "value": body["countryHint"],
                    "availability": "available",
                    "provenance": {"source": "selected"},
                }
            case = {
                "caseId": case_id,
                "caseRef": case_ref,
                "victimUid": actor.uid,
                "language": body["language"],
                "status": "INTAKE",
                "facts": facts,
                "factsRevision": 0,
                "createdAt": stamp(now),
                "updatedAt": stamp(now),
                "ttlAt": stamp(now + timedelta(hours=72)),
                "accessExpiresAtMs": int((now + timedelta(hours=72)).timestamp() * 1000),
                "consentVersion": self.CONSENT_VERSION,
                "consentedAt": stamp(now),
                "flags": {"distress": False, "injectionAttempt": False, "lowConfidence": False},
                "evidenceIds": [],
                "transcript": [],
                "jobIds": [],
                "eventIds": [],
            }
            tx.set(f"cases/{case_id}", case)
            self._event(tx, case_id, actor, "case.created")
            return {name: case[name] for name in ["caseId", "caseRef", "status", "createdAt"]}

        return self._mutation(actor, "/cases", key, body, create)

    def get_case(self, actor: Actor, case_id: str) -> dict[str, Any]:
        case = self._case(self.repository, case_id, actor, allow_admin=True)
        evidence = [
            self.repository.get(f"cases/{case_id}/evidence/{item}") for item in case["evidenceIds"]
        ]
        return {
            **{
                name: case[name]
                for name in [
                    "caseId",
                    "caseRef",
                    "status",
                    "facts",
                    "flags",
                    "factsRevision",
                    "createdAt",
                    "updatedAt",
                    "ttlAt",
                    "transcript",
                ]
            },
            "classification": (
                case.get("classification")
                if case.get("classificationInputHash") == planning_input_hash(case, evidence)
                else None
            ),
            "plan": (
                {
                    **case["plan"],
                    "stale": case["plan"].get("inputHash") != planning_input_hash(case, evidence),
                }
                if case.get("plan")
                else None
            ),
            "packets": self.packets.list(actor, case_id)["items"] if self.packets else [],
            "evidence": [
                {"evidenceId": item["evidenceId"], "type": item["type"], "status": item["status"]}
                for item in evidence
                if item
            ],
        }

    def update_facts(self, actor: Actor, case_id: str, body: dict[str, Any]) -> dict[str, Any]:
        def update(tx: Transaction) -> dict[str, Any]:
            case = self._case(tx, case_id, actor)
            if body.get("ifRevision") is not None and case["factsRevision"] != body["ifRevision"]:
                raise IntakeError(409, "version_conflict")
            case["facts"] = merge_facts(
                case["facts"], body["facts"], confirmed=True, now=self.clock()
            )
            case["factsRevision"] += 1
            case["updatedAt"] = stamp(self.clock())
            tx.set(f"cases/{case_id}", case)
            self._event(tx, case_id, actor, "facts.updated", body)
            return {
                "facts": case["facts"],
                "factsRevision": case["factsRevision"],
                "missingMinimum": missing_minimum(case["facts"]),
                "reprocessRecommended": bool(case.get("plan") or case.get("classification")),
            }

        return self.repository.atomic(update)

    async def message(
        self, actor: Actor, case_id: str, body: dict[str, Any], key: str
    ) -> dict[str, Any]:
        reported_at = self.clock()
        case = self._case(self.repository, case_id, actor)
        text = scrub_credentials(body["text"])
        language = body.get("lang") or case["language"]
        if language not in {"en", "hi"}:
            raise IntakeError(422, "validation_failed")
        for evidence_id in body.get("evidenceIds", []):
            if evidence_id not in case["evidenceIds"]:
                raise IntakeError(403, "forbidden")
        # Reserve by actor/key to avoid generating a second turn on successful retries.
        try:
            UUID(key)
        except ValueError as exc:
            raise IntakeError(400, "bad_request") from exc
        scope = idempotency_scope(
            actor.uid, actor.org_id, "POST", f"/cases/{case_id}/messages", key
        )
        idem = self.repository.get(f"idempotency/{scope}")
        digest = canonical_hash(body)
        if idem and idem["expiresAt"] > stamp(self.clock()):
            if idem["bodyHash"] != digest:
                raise IntakeError(409, "idempotency_conflict")
            return idem["result"]
        reservation_path = f"messageRequests/{scope}"

        def reserve(tx: Transaction) -> None:
            pending = tx.get(reservation_path)
            if pending and pending["leaseUntil"] > stamp(self.clock()):
                if pending["bodyHash"] != digest:
                    raise IntakeError(409, "idempotency_conflict")
                raise IntakeError(
                    409, "invalid_state_transition", "This message is already being processed"
                )
            fresh = self._case(tx, case_id, actor)
            if fresh["factsRevision"] != case["factsRevision"]:
                raise IntakeError(409, "version_conflict")
            fresh.setdefault("messageRequestIds", []).append(scope)
            tx.set(f"cases/{case_id}", fresh)
            tx.set(
                reservation_path,
                {
                    "bodyHash": digest,
                    "caseId": case_id,
                    "uid": actor.uid,
                    "leaseUntil": stamp(self.clock() + timedelta(seconds=30)),
                },
            )

        self.repository.atomic(reserve)
        import asyncio

        try:
            result = await asyncio.wait_for(
                self.intake_agent.respond(
                    text=text,
                    facts=CaseFacts.model_validate(case["facts"]),
                    language=language,
                    now=self.clock(),
                    first_turn=not case["transcript"],
                    history=intake_history(case, actor),
                ),
                timeout=20,
            )
        except TimeoutError as exc:
            self.repository.atomic(lambda tx: tx.delete(reservation_path))
            raise IntakeError(504, "timeout") from exc
        except Exception as exc:
            self.repository.atomic(lambda tx: tx.delete(reservation_path))
            raise IntakeError(503, "model_unavailable") from exc
        reply = scrub_credentials(result.text)
        if not self.guard.inspect_output(reply).allow:
            reply = (
                "Please do not share codes or passwords. Contact your bank using its official app."
                if language == "en"
                else "कोई कोड या पासवर्ड साझा न करें। बैंक के आधिकारिक ऐप से संपर्क करें।"
            )
        turn_id = new_id("turn")

        def save(tx: Transaction) -> dict[str, Any]:
            current = self._case(tx, case_id, actor)
            if current["factsRevision"] != case["factsRevision"]:
                raise IntakeError(
                    409, "version_conflict", "Your details changed; retry with the current details"
                )
            if len(current["transcript"]) >= 80 or len(reply) > 4000:
                raise IntakeError(429, "budget_exceeded")
            distress = bool(result.distress)
            delta = {} if distress else result.facts_delta
            current["facts"] = merge_facts(
                current["facts"],
                delta,
                confirmed=False,
                now=self.clock(),
                statement_reference=(
                    f"case:{case_id}:turn:{turn_id}:facts:{current['factsRevision'] + 1}"
                ),
            )
            current["factsRevision"] += 1
            current["flags"]["distress"] = current["flags"]["distress"] or distress
            current["flags"]["injectionAttempt"] = current["flags"]["injectionAttempt"] or bool(
                self.guard.inspect_input(text).flags
            )
            current["transcript"] += [
                {
                    "turnId": turn_id,
                    "role": "user",
                    "text": text,
                    "lang": language,
                    "ts": stamp(reported_at),
                },
                {
                    "turnId": turn_id + "_reply",
                    "role": "assistant",
                    "text": reply,
                    "lang": language,
                    "ts": stamp(self.clock()),
                },
            ]
            for turn in current["transcript"][-2:]:
                tx.set(f"cases/{case_id}/transcript/{turn['turnId']}", turn)
            current["updatedAt"] = stamp(self.clock())
            pipeline_id = new_id("step")
            current.setdefault("pipelineIds", []).append(pipeline_id)
            tx.set(
                f"cases/{case_id}/pipeline/{pipeline_id}",
                {
                    "step": "intake_text",
                    "modelId": getattr(result, "model", "test-fixture"),
                    "promptVersion": getattr(result, "prompt_version", "fixture.v1"),
                    "mode": getattr(result, "mode", "fake"),
                    "createdAt": stamp(self.clock()),
                    "factsRevision": current["factsRevision"],
                    "degraded": bool(getattr(result, "degraded", False)),
                },
            )
            tx.set(f"cases/{case_id}", current)
            self._event(tx, case_id, actor, "intake.message_received", {"turnId": turn_id})
            return {
                "turnId": turn_id,
                "reply": {"text": reply, "lang": language},
                "factsDelta": current["facts"],
                "missingMinimum": missing_minimum(current["facts"]),
                "processingQueued": False,
                "flags": current["flags"],
                "factsRevision": current["factsRevision"],
            }

        try:
            return self._mutation(actor, f"/cases/{case_id}/messages", key, body, save)
        finally:
            self.repository.atomic(lambda tx: tx.delete(reservation_path))

    def request_upload(
        self, actor: Actor, case_id: str, body: dict[str, Any], key: str
    ) -> dict[str, Any]:
        evidence_id, now = new_id("evidence"), self.clock()
        path = f"quarantine/{case_id}/{evidence_id}"
        self._case(self.repository, case_id, actor)
        upload_url = self.storage.upload_url(path, actor.uid, body["mime"], body["sizeBytes"])

        def save(tx: Transaction) -> dict[str, Any]:
            case = self._case(tx, case_id, actor)
            if len(case["evidenceIds"]) >= 20:
                raise IntakeError(429, "budget_exceeded")
            evidence = {
                "evidenceId": evidence_id,
                "type": body["kind"],
                "status": "awaiting_upload",
                "mime": body["mime"],
                "expectedSize": body["sizeBytes"],
                "expectedSha256": body.get("sha256"),
                "quarantinePath": path,
                "storagePath": None,
                "createdAt": stamp(now),
                "safety": {"flagged": False, "reasons": []},
            }
            tx.set(f"cases/{case_id}/evidence/{evidence_id}", evidence)
            case["evidenceIds"].append(evidence_id)
            tx.set(f"cases/{case_id}", case)
            self._event(
                tx, case_id, actor, "evidence.upload_requested", {"evidenceId": evidence_id}
            )
            return {
                "evidenceId": evidence_id,
                "uploadUrl": upload_url,
                "method": "PUT",
                "headers": {"Content-Type": body["mime"]},
                "expiresAt": stamp(now + timedelta(minutes=10)),
            }

        return self._mutation(actor, f"/cases/{case_id}/uploads", key, body, save)

    def _evidence(
        self, tx: Transaction | Repository, actor: Actor, case_id: str, evidence_id: str
    ) -> dict[str, Any]:
        case = self._case(tx, case_id, actor)
        if evidence_id not in case["evidenceIds"]:
            raise IntakeError(404, "not_found")
        evidence = tx.get(f"cases/{case_id}/evidence/{evidence_id}")
        if evidence is None:
            raise IntakeError(404, "not_found")
        return evidence

    def finalize_upload(
        self, actor: Actor, case_id: str, evidence_id: str, key: str
    ) -> dict[str, Any]:
        evidence = self._evidence(self.repository, actor, case_id, evidence_id)
        job_id = new_id("job")

        # Idempotency callback never reads the object: durable job owns validation.
        def queue(tx: Transaction) -> dict[str, Any]:
            current = self._evidence(tx, actor, case_id, evidence_id)
            if current["status"] != "awaiting_upload":
                if current.get("jobId"):
                    return {
                        "jobId": current["jobId"],
                        "statusUrl": f"/api/v1/jobs/{current['jobId']}",
                    }
                raise IntakeError(409, "invalid_state_transition")
            current.update(status="queued", jobId=job_id)
            tx.set(f"cases/{case_id}/evidence/{evidence_id}", current)
            tx.set(
                f"jobs/{job_id}",
                {
                    "jobId": job_id,
                    "type": "process_evidence",
                    "state": "queued",
                    "uid": actor.uid,
                    "caseId": case_id,
                    "evidenceId": evidence_id,
                    "progress": {"step": 0, "total": 2},
                    "error": None,
                    "resultRef": None,
                    "createdAt": stamp(self.clock()),
                    "leaseUntil": None,
                },
            )
            case = self._case(tx, case_id, actor)
            case["jobIds"].append(job_id)
            tx.set(f"cases/{case_id}", case)
            self._event(tx, case_id, actor, "evidence.processing_queued", {"jobId": job_id})
            return {"jobId": job_id, "statusUrl": f"/api/v1/jobs/{job_id}"}

        # Validate bytes before accepting extraction; never expose quarantine.
        if evidence["status"] == "awaiting_upload":
            try:
                raw = self.storage.read(evidence["quarantinePath"])
                if len(raw) != evidence["expectedSize"]:
                    raise IntakeError(422, "validation_failed")
                original_hash = hashlib.sha256(raw).hexdigest()
                if evidence.get("expectedSha256") and evidence["expectedSha256"] != original_hash:
                    raise IntakeError(422, "validation_failed")
                clean = validate_file(raw, evidence["mime"])
                self.storage.write(evidence["quarantinePath"], clean.content, clean.mime)
                clean_hash = hashlib.sha256(clean.content).hexdigest()

                def metadata(tx: Transaction) -> None:
                    current = self._evidence(tx, actor, case_id, evidence_id)
                    current.update(
                        originalSha256=original_hash,
                        quarantineSha256=clean_hash,
                        expectedSize=len(clean.content),
                    )
                    tx.set(f"cases/{case_id}/evidence/{evidence_id}", current)

                self.repository.atomic(metadata)
            except (FileNotFoundError, KeyError) as exc:
                raise IntakeError(
                    409, "invalid_state_transition", "Upload the file before completing it"
                ) from exc
            except (ValueError, OSError) as exc:
                self.storage.delete(evidence["quarantinePath"])

                def reject(tx: Transaction) -> None:
                    current = self._evidence(tx, actor, case_id, evidence_id)
                    current.update(
                        status="rejected",
                        safety={"flagged": True, "reasons": ["validation_failed"]},
                    )
                    tx.set(f"cases/{case_id}/evidence/{evidence_id}", current)
                    self._event(
                        tx, case_id, actor, "evidence.rejected", {"evidenceId": evidence_id}
                    )

                self.repository.atomic(reject)
                raise IntakeError(
                    422, "validation_failed", "Use a clear synthetic file without credentials"
                ) from exc
        return self._mutation(
            actor, f"/cases/{case_id}/evidence/{evidence_id}/complete", key, {}, queue
        )

    def get_evidence(self, actor: Actor, case_id: str, evidence_id: str) -> dict[str, Any]:
        evidence = self._evidence(self.repository, actor, case_id, evidence_id)
        preview = (
            self.storage.preview_url(evidence["storagePath"], actor.uid, evidence["mime"])
            if evidence.get("storagePath")
            else ""
        )
        return {
            "evidenceId": evidence_id,
            "type": evidence["type"],
            "status": evidence["status"],
            "extraction": evidence.get("extraction"),
            "safety": evidence["safety"],
            "previewUrl": preview,
        }

    def get_job(self, actor: Actor, job_id: str) -> dict[str, Any]:
        job = self.repository.get(f"jobs/{job_id}")
        if not job:
            raise IntakeError(404, "not_found")
        if job.get("type") == "pack_ingest" and self.sources is not None:
            self.sources._source(self.repository, actor, job["resourceId"])
        elif job.get("type") == "pack_build" and self.packstudio is not None:
            self.packstudio.get(actor, job["resourceId"])
        else:
            if job["uid"] != actor.uid and actor.role != "admin":
                raise IntakeError(403, "forbidden")
            self._case(self.repository, job["caseId"], actor, allow_admin=True)
        return {
            key: job.get(key)
            for key in ["jobId", "type", "state", "progress", "error", "resultRef"]
        }

    def confirm_evidence(
        self, actor: Actor, case_id: str, evidence_id: str, body: dict[str, Any], key: str
    ) -> dict[str, Any]:
        def confirm(tx: Transaction) -> dict[str, Any]:
            evidence = self._evidence(tx, actor, case_id, evidence_id)
            if evidence["status"] != "ready":
                raise IntakeError(409, "invalid_state_transition")
            extraction = EvidenceExtraction.model_validate(evidence["extraction"])
            entities = {item.entity_id: item for item in extraction.entities}
            if len({item["entityId"] for item in body["items"]}) != len(body["items"]):
                raise IntakeError(422, "validation_failed")
            case = self._case(tx, case_id, actor)
            delta: dict[str, Any] = {}
            confirmed_amount = None
            confirmed_currency = None
            field_refs: dict[str, str] = {}
            for decision in body["items"]:
                entity = entities.get(decision["entityId"])
                if entity is None:
                    raise IntakeError(422, "validation_failed")
                choice = decision["decision"]
                if choice == "edit":
                    value = decision.get("value")
                    if not value or len(value) > 4000 or scrub_credentials(value) != value:
                        raise IntakeError(422, "unsafe_content_blocked")
                    entity.raw_value = entity.normalized_value = value
                    entity.status = "edited"
                else:
                    entity.status = "confirmed" if choice == "confirm" else "unrelated"
                reference = f"{evidence_id}/{entity.entity_id}"
                if choice == "unrelated":
                    # Only withdraw values sourced from this item; preserve a
                    # later manually confirmed correction from another source.
                    for path, provenance in list(case["facts"].get("fieldProvenance", {}).items()):
                        if provenance.get("reference") != reference:
                            continue
                        parts = path.split(".")
                        if path.startswith("payment.amount."):
                            case["facts"]["payment"]["amount"] = None
                        elif path.startswith("payment.recipientIdentifier."):
                            case["facts"]["payment"]["recipientIdentifier"] = None
                        else:
                            target = case["facts"]
                            for part in parts[:-1]:
                                target = target.get(part) or {}
                            target[parts[-1]] = None
                        case["facts"]["fieldProvenance"].pop(path, None)
                if entity.status != "unrelated" and entity.role != "victim":
                    mappings = {"transaction_ref": "transactionRef", "timestamp": "timestamp"}
                    if entity.type in mappings:
                        delta.setdefault("payment", {})[mappings[entity.type]] = (
                            entity.normalized_value
                        )
                        field_refs["payment." + mappings[entity.type]] = reference
                    elif entity.type == "upi_id":
                        delta.setdefault("payment", {})["recipientIdentifier"] = {
                            "type": "upi_id",
                            "value": entity.normalized_value,
                        }
                        field_refs["payment.recipientIdentifier.type"] = reference
                        field_refs["payment.recipientIdentifier.value"] = reference
                    elif entity.type == "amount":
                        confirmed_amount = entity.normalized_value
                        field_refs["payment.amount.value"] = reference
                    elif entity.type == "currency":
                        confirmed_currency = entity.normalized_value.upper()
                        field_refs["payment.amount.currency"] = reference
            currency = confirmed_currency or (case["facts"]["payment"].get("amount") or {}).get(
                "currency"
            )
            if confirmed_amount is not None and currency:
                number = confirmed_amount.replace(currency, "").replace(",", "").strip(" ₹£$€")
                if not re.fullmatch(r"\d+(?:\.\d{1,8})?", number):
                    raise IntakeError(422, "validation_failed")
                delta.setdefault("payment", {})["amount"] = {"value": number, "currency": currency}
            case["facts"] = merge_facts(case["facts"], delta, confirmed=True, now=self.clock())
            for path, reference in field_refs.items():
                if path in case["facts"]["fieldProvenance"]:
                    case["facts"]["fieldProvenance"][path]["reference"] = reference
            case["factsRevision"] += 1
            case["updatedAt"] = stamp(self.clock())
            evidence["extraction"] = extraction.model_dump(mode="json", by_alias=True)
            tx.set(f"cases/{case_id}", case)
            tx.set(f"cases/{case_id}/evidence/{evidence_id}", evidence)
            self._event(tx, case_id, actor, "evidence.confirmed", {"evidenceId": evidence_id})
            return {
                "entities": evidence["extraction"]["entities"],
                "missingMinimum": missing_minimum(case["facts"]),
            }

        return self._mutation(
            actor, f"/cases/{case_id}/evidence/{evidence_id}/confirm", key, body, confirm
        )

    async def process_evidence(self, job_id: str) -> None:
        now = self.clock()

        def claim(tx: Transaction) -> dict[str, Any] | None:
            job = tx.get(f"jobs/{job_id}")
            if not job or job["state"] in {"succeeded", "failed"}:
                return None
            if job.get("leaseUntil") and job["leaseUntil"] > stamp(now):
                return None
            if job.get("retryAfter") and job["retryAfter"] > stamp(now):
                return None
            try:
                self._evidence(tx, Actor(job["uid"], "victim"), job["caseId"], job["evidenceId"])
            except IntakeError as exc:
                if exc.status not in {403, 404, 409, 410}:
                    raise
                job.update(state="failed", error={"code": "resource_unavailable"})
                tx.set(f"jobs/{job_id}", job)
                return None
            job.update(state="running", leaseUntil=stamp(now + timedelta(minutes=3)))
            tx.set(f"jobs/{job_id}", job)
            return job

        job = self.repository.atomic(claim)
        if job is None:
            return
        actor, case_id, evidence_id = Actor(job["uid"], "victim"), job["caseId"], job["evidenceId"]
        evidence = self._evidence(self.repository, actor, case_id, evidence_id)
        validated_path = f"validated/{case_id}/{evidence_id}"
        permanent = True
        cleanup_quarantine = True
        try:
            raw = self.storage.read(evidence["quarantinePath"])
            if len(raw) != evidence["expectedSize"] or (
                evidence.get("quarantineSha256")
                and hashlib.sha256(raw).hexdigest() != evidence["quarantineSha256"]
            ):
                raise ValueError("file size/hash differs")
            clean = validate_file(raw, evidence["mime"])
            case = self._case(self.repository, case_id, actor)
            permanent = False
            extraction = await self.evidence_agent.extract(
                evidence_id=evidence_id,
                mime=clean.mime,
                content=clean.text if clean.mime == "text/plain" else clean.content,
                case_language=case["language"],
            )
            permanent = True
            extraction = EvidenceExtraction.model_validate(extraction)
            # Reject secret-bearing extraction; do not store even sanitized inference.
            serialized = extraction.model_dump_json(by_alias=True)
            if scrub_credentials(serialized) != serialized:
                raise ValueError("sensitive values in file")
            self.storage.write(validated_path, clean.content, clean.mime)

            def success(tx: Transaction) -> None:
                current = self._evidence(tx, actor, case_id, evidence_id)
                current_job = tx.get(f"jobs/{job_id}")
                if current_job is None or current_job["state"] != "running":
                    raise IntakeError(409, "invalid_state_transition")
                current.update(
                    status="ready",
                    storagePath=validated_path,
                    sha256=hashlib.sha256(clean.content).hexdigest(),
                    extraction=extraction.model_dump(mode="json", by_alias=True),
                    safety={
                        "flagged": bool(clean.flags) or extraction.injection_suspected,
                        "reasons": list(clean.flags)
                        + (["injection"] if extraction.injection_suspected else []),
                    },
                )
                current_job.update(
                    state="succeeded",
                    leaseUntil=None,
                    progress={"step": 2, "total": 2},
                    resultRef=f"cases/{case_id}/evidence/{evidence_id}",
                )
                tx.set(f"cases/{case_id}/evidence/{evidence_id}", current)
                tx.set(f"jobs/{job_id}", current_job)
                if current["safety"]["flagged"]:
                    latest_case = self._case(tx, case_id, actor)
                    latest_case["flags"]["injectionAttempt"] = True
                    tx.set(f"cases/{case_id}", latest_case)
                    self._event(
                        tx,
                        case_id,
                        actor,
                        "evidence.injection_flagged",
                        {"evidenceId": evidence_id},
                    )
                self._event(tx, case_id, actor, "evidence.extracted", {"evidenceId": evidence_id})

            self.repository.atomic(success)
        except Exception as error:
            if (
                error.args
                and type(error.args[0]) is str
                and error.args[0]
                in {
                    "evidence_secret_rejected",
                    "unsafe_extraction_text",
                    "unsupported_entity_type",
                    "entity_not_in_evidence",
                    "model_secret_output",
                }
            ):
                permanent = True
            self.storage.delete(validated_path)

            def fail(tx: Transaction) -> None:
                current_job = tx.get(f"jobs/{job_id}")
                if not current_job:
                    return
                attempts = current_job.get("attempts", 0) + 1
                retryable = not permanent and attempts < 3
                current_job.update(
                    state="queued" if retryable else "failed",
                    attempts=attempts,
                    leaseUntil=None,
                    retryAfter=stamp(self.clock() + timedelta(seconds=2**attempts)),
                    error={
                        "type": "https://relay.example/errors/validation_failed",
                        "title": "Evidence could not be processed",
                        "status": 503 if retryable else 422,
                        "code": "model_unavailable" if retryable else "validation_failed",
                        "detail": "Try again later"
                        if retryable
                        else "Use a clear synthetic file without credentials",
                        "requestId": new_id("req"),
                        "fieldErrors": [],
                        "retryable": retryable,
                    },
                )
                tx.set(f"jobs/{job_id}", current_job)
                current = tx.get(f"cases/{case_id}/evidence/{evidence_id}")
                if current:
                    current.update(
                        status="queued" if retryable else "rejected",
                        storagePath=None,
                        safety={
                            "flagged": not retryable,
                            "reasons": [] if retryable else ["validation_failed"],
                        },
                    )
                    tx.set(f"cases/{case_id}/evidence/{evidence_id}", current)

            self.repository.atomic(fail)
            cleanup_quarantine = (
                permanent or (self.repository.get(f"jobs/{job_id}") or {}).get("state") != "queued"
            )
        finally:
            if cleanup_quarantine:
                self.storage.delete(evidence["quarantinePath"])

    def delete_case(
        self, actor: Actor, case_id: str, *, expected_demo_marker: dict | None = None
    ) -> None:
        def mark(tx: Transaction) -> dict[str, Any]:
            case = tx.get(f"cases/{case_id}")
            if not case:
                raise IntakeError(404, "not_found")
            if (
                not (actor.role == "victim" and case["victimUid"] == actor.uid)
                and actor.role != "admin"
            ):
                raise IntakeError(403, "forbidden")
            if expected_demo_marker is not None and case.get("demoFixture") != expected_demo_marker:
                raise IntakeError(409, "version_conflict")
            case["deleting"] = True
            tx.set(f"cases/{case_id}", case)
            return case

        case = self.repository.atomic(mark)
        for packet_id in case.get("packetIds", []):
            packet = self.repository.get(f"cases/{case_id}/packets/{packet_id}")
            if packet:
                for version in range(1, packet["version"] + 1):
                    self.export_storage.delete(f"packets/{case_id}/{packet_id}/{version}.pdf")
        for evidence_id in case["evidenceIds"]:
            evidence = self.repository.get(f"cases/{case_id}/evidence/{evidence_id}")
            if evidence:
                for path in [evidence.get("storagePath"), evidence.get("quarantinePath")]:
                    if path:
                        self.storage.delete(path)

        def remove(tx: Transaction) -> None:
            for evidence_id in case["evidenceIds"]:
                tx.delete(f"cases/{case_id}/evidence/{evidence_id}")
            for job_id in case["jobIds"]:
                tx.delete(f"jobs/{job_id}")
            for event_id in case.get("eventIds", []):
                tx.delete(f"cases/{case_id}/events/{event_id}")
            for turn in case.get("transcript", []):
                tx.delete(f"cases/{case_id}/transcript/{turn['turnId']}")
            for idem_id in case.get("idempotencyIds", []):
                tx.delete(f"idempotency/{idem_id}")
            for request_id in case.get("messageRequestIds", []):
                tx.delete(f"messageRequests/{request_id}")
            for pipeline_id in case.get("pipelineIds", []):
                tx.delete(f"cases/{case_id}/pipeline/{pipeline_id}")
            for plan_id in case.get("planIds", []):
                tx.delete(f"cases/{case_id}/plans/{plan_id}")
            for request_id in case.get("planningRequestIds", []):
                tx.delete(f"planningRequests/{request_id}")
            for packet_id in case.get("packetIds", []):
                path = f"cases/{case_id}/packets/{packet_id}"
                packet = tx.get(path)
                if packet:
                    for version in range(1, packet["version"] + 1):
                        tx.delete(f"{path}/versions/{version}")
                tx.delete(path)
            for approval_id in case.get("approvalIds", []):
                tx.delete(f"cases/{case_id}/approvals/{approval_id}")
            for notification_id in case.get("notificationIds", []):
                tx.delete(f"cases/{case_id}/notifications/{notification_id}")
            if self.packets:
                from packages.delivery import MockDeliveryService

                MockDeliveryService.cleanup_case(
                    tx, case["victimUid"], case_id, case.get("deliveryIds", [])
                )
            if self.receiver:
                self.receiver.cleanup_case(tx, case_id, case.get("receiverProjectionRefs", []))
            if self.linking:
                self.linking.cleanup_case(tx, case["caseRef"])
            if case.get("a2aTaskRefs"):
                from services.a2a_receiver.store import cleanup_case

                cleanup_case(tx, case_id, case["a2aTaskRefs"])
            if case.get("liveSessionRefs") or case.get("liveResumeRefs"):
                from services.live_gateway.registry import LiveSessionRegistry

                LiveSessionRegistry.cleanup_case(
                    tx,
                    case_id,
                    {
                        "sessions": case.get("liveSessionRefs", []),
                        "resumptions": case.get("liveResumeRefs", []),
                    },
                )
            for request_id in case.get("informationRequestIds", []):
                tx.delete(f"cases/{case_id}/informationRequests/{request_id}")
            tx.delete(f"cases/{case_id}")
            tx.set(
                f"deletionAudit/{new_id('event')}",
                {
                    "action": "case.deleted",
                    "caseHash": canonical_hash(case_id),
                    "ts": stamp(self.clock()),
                },
            )

        self.repository.atomic(remove)
