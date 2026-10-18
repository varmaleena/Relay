"""Durable approved-delivery → private A2A transport handoff, never human ACK."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from pydantic import ValidationError

from packages.common.identifiers import canonical_hash, new_id
from packages.intake.service import IntakeError, stamp
from packages.safety import Actor
from services.a2a_receiver.store import HandoffReference, task_identifier


class ReceiverHandoffService:
    def __init__(self, intake: Any, client: Any, *, scope: str = "victim-api"):
        if not scope or intake.receiver is None:
            raise ValueError("Explicit addressed receiver and caller scope required")
        self.intake, self.client, self.scope = intake, client, scope
        self.repository = intake.repository

    def _validate(self, tx: Any, uid: str, reference: HandoffReference):
        actor = Actor(uid, "victim")
        case = self.intake._case(tx, reference.case_id, actor)
        packet = tx.get(f"cases/{reference.case_id}/packets/{reference.packet_id}")
        expires = case.get("accessExpiresAtMs")
        if (
            type(expires) is not int
            or expires <= int(self.intake.clock().timestamp() * 1000)
            or case.get("flags", {}).get("distress")
            or not packet
            or packet["version"] != reference.packet_version
            or packet["contentHash"] != reference.content_hash
            or packet["status"] not in {"SENT", "ACKNOWLEDGED", "NEEDS_INFO", "ACTIONED"}
            or not packet.get("verification", {}).get("passed")
            or not packet.get("delivery", {}).get("simulated")
            or self.intake.receiver.recipient_orgs.get(packet["recipientId"]) != reference.org_id
            or not case.get("plan")
            or case["plan"]["planId"] != packet["planId"]
            or self.intake.planning.input_hash(tx, case) != packet["inputHash"]
        ):
            raise IntakeError(409, "version_conflict")
        plan = self.intake.planning.get_plan(actor, reference.case_id)
        if plan["stale"]:
            raise IntakeError(409, "version_conflict")
        # Independent receiver projection expiry/version check before and after RPC.
        _, projection = self._projection(tx, reference)
        return case, packet, projection

    def _projection(self, tx: Any, reference: HandoffReference):
        actor = Actor("a2a-read-only", "receiver", reference.org_id)
        projection, _, _, _ = self.intake.receiver._load(
            tx, actor, reference.case_id, reference.packet_id
        )
        if (
            projection["packet"]["version"] != reference.packet_version
            or projection["packet"]["contentHash"] != reference.content_hash
        ):
            raise IntakeError(409, "version_conflict")
        return actor, projection

    def enqueue(
        self,
        tx: Any,
        *,
        case: dict[str, Any],
        packet: dict[str, Any],
        projection_ref: dict[str, str],
    ) -> str:
        reference = HandoffReference(
            org_id=projection_ref["orgId"],
            case_id=case["caseId"],
            packet_id=packet["packetId"],
            packet_version=packet["version"],
            content_hash=packet["contentHash"],
        )
        message_id = "handoff_" + canonical_hash(
            {"uid": case["victimUid"], "reference": reference.model_dump(), "scope": self.scope}
        )
        task_id = task_identifier(self.scope, reference, message_id)
        job_id = "job_" + canonical_hash({"type": "handoff_receiver", "taskId": task_id})[:32]
        previous = tx.get("jobs/" + job_id)
        if previous:
            if previous["uid"] != case["victimUid"] or previous[
                "reference"
            ] != reference.model_dump(by_alias=True):
                raise IntakeError(409, "version_conflict")
            return job_id
        if len(case.get("jobIds", [])) >= 80 or len(case.get("a2aTaskRefs", [])) >= 40:
            raise IntakeError(429, "rate_limited")
        # Reserve task references in the same owner transaction before any network call.
        case.setdefault("a2aTaskRefs", []).append({"taskId": task_id})
        case.setdefault("jobIds", []).append(job_id)
        tx.set("cases/" + case["caseId"], case)
        self._validate(tx, case["victimUid"], reference)
        tx.set(
            "jobs/" + job_id,
            {
                "jobId": job_id,
                "type": "handoff_receiver",
                "uid": case["victimUid"],
                "caseId": case["caseId"],
                "packetId": packet["packetId"],
                "reference": reference.model_dump(by_alias=True),
                "taskId": task_id,
                "messageId": message_id,
                "state": "queued",
                "attempts": 0,
                "progress": {"step": 0, "total": 1},
                "createdAt": stamp(self.intake.clock()),
                "leaseUntil": None,
                "retryAfter": None,
                "error": None,
            },
        )
        return job_id

    async def process(self, job_id: str) -> None:
        def claim(tx):
            job = tx.get("jobs/" + job_id)
            if (
                not job
                or job.get("type") != "handoff_receiver"
                or job["state"] not in {"queued", "running"}
            ):
                return None
            now = stamp(self.intake.clock())
            if any(job.get(key) and job[key] > now for key in ("leaseUntil", "retryAfter")):
                return None
            try:
                reference = HandoffReference.model_validate(job["reference"])
                case, _, _ = self._validate(tx, job["uid"], reference)
                if {"taskId": job["taskId"]} not in case.get("a2aTaskRefs", []):
                    raise IntakeError(409, "version_conflict")
            except (IntakeError, ValidationError):
                job.update(state="failed", leaseUntil=None, error=self._problem("version_conflict"))
                tx.set("jobs/" + job_id, job)
                return None
            if job["attempts"] >= 3:
                job.update(
                    state="failed", leaseUntil=None, error=self._problem("adapter_unavailable")
                )
                tx.set("jobs/" + job_id, job)
                return None
            job.update(
                state="running",
                attempts=job["attempts"] + 1,
                claimToken=new_id("handoffclaim"),
                leaseUntil=stamp(self.intake.clock() + timedelta(seconds=60)),
            )
            tx.set("jobs/" + job_id, job)
            return job

        job = self.repository.atomic(claim)
        if job is None:
            return
        try:
            receipt = await asyncio.wait_for(
                self.client.send(job["reference"], job["messageId"]), 32
            )
            if (
                receipt.get("taskId") != job["taskId"]
                or receipt.get("simulated") is not True
                or receipt.get("humanAcknowledged") is not False
                or receipt.get("transportStatus") not in {"received", "needs_info"}
                or receipt.get("briefStatus") not in {"generated", "unavailable"}
            ):
                raise ValueError("Invalid transport receipt")
            receipt = {
                key: receipt[key]
                for key in (
                    "taskId",
                    "simulated",
                    "humanAcknowledged",
                    "transportStatus",
                    "briefStatus",
                )
            }

            def finish(tx):
                current = tx.get("jobs/" + job_id)
                if not current or current.get("claimToken") != job["claimToken"]:
                    return
                reference = HandoffReference.model_validate(job["reference"])
                case, _, _ = self._validate(tx, job["uid"], reference)
                if {"taskId": job["taskId"]} not in case.get("a2aTaskRefs", []):
                    raise IntakeError(409, "version_conflict")
                current.update(
                    state="succeeded",
                    leaseUntil=None,
                    retryAfter=None,
                    progress={"step": 1, "total": 1},
                    receipt=receipt,
                    error=None,
                )
                tx.set("jobs/" + job_id, current)
                self.intake._event(
                    tx,
                    job["caseId"],
                    Actor("A2AReceiver", "system"),
                    "receiver.handoff_simulated",
                    receipt,
                )

            self.repository.atomic(finish)
        except Exception:

            def fail(tx):
                current = tx.get("jobs/" + job_id)
                if not current or current.get("claimToken") != job["claimToken"]:
                    return
                try:
                    self._validate(
                        tx, job["uid"], HandoffReference.model_validate(job["reference"])
                    )
                    retry = current["attempts"] < 3
                except (IntakeError, ValidationError):
                    retry = False
                current.update(
                    state="queued" if retry else "failed",
                    leaseUntil=None,
                    retryAfter=stamp(self.intake.clock() + timedelta(seconds=10))
                    if retry
                    else None,
                    error=self._problem("adapter_unavailable"),
                )
                tx.set("jobs/" + job_id, current)

            self.repository.atomic(fail)

    @staticmethod
    def _problem(code: str) -> dict[str, Any]:
        return {
            "type": "https://relay.example/errors/" + code,
            "title": "Receiver handoff unavailable",
            "code": code,
            "status": 409 if code == "version_conflict" else 503,
            "detail": "The simulated agent handoff could not complete.",
            "requestId": new_id("req"),
            "fieldErrors": [],
            "retryable": code == "adapter_unavailable",
        }
