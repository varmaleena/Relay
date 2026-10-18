"""Packet versions are immutable; delivery uses a persisted, content-bound outbox."""

import asyncio
import base64
import json
from datetime import timedelta
from typing import Any

from agents.intake.clients import ModelFailure
from packages.common.identifiers import canonical_hash, new_id
from packages.intake.service import IntakeError, stamp
from packages.safety import Actor
from packages.safety.guard import scrub_credentials
from packages.safety.policy import Action, ActionPolicy, Approval, Context, Decision
from packages.schemas.models import CaseFacts, PacketContent, Plan, Provenance


class PacketService:
    def __init__(self, intake: Any, pipeline: Any, adapter: Any) -> None:
        self.intake, self.repository = intake, intake.repository
        self.pipeline, self.adapter = pipeline, adapter

    def _current_plan(self, actor: Actor, case_id: str) -> dict[str, Any]:
        plan = self.intake.planning.get_plan(actor, case_id)
        if plan["stale"]:
            raise IntakeError(409, "version_conflict", "Update the plan before preparing messages.")
        return plan

    def _packet(self, tx: Any, actor: Actor, case_id: str, packet_id: str) -> tuple[Any, Any]:
        case = self.intake._case(tx, case_id, actor)
        packet = tx.get(f"cases/{case_id}/packets/{packet_id}")
        if not packet:
            raise IntakeError(404, "not_found")
        return case, packet

    def _stale(self, case: Any, packet: Any) -> bool:
        return (
            not case.get("plan")
            or case["plan"]["planId"] != packet["planId"]
            or self.intake.planning.input_hash(self.repository, case) != packet["inputHash"]
        )

    def get(self, actor: Actor, case_id: str, packet_id: str) -> dict[str, Any]:
        case, packet = self._packet(self.repository, actor, case_id, packet_id)
        packet["stale"] = self._stale(case, packet)
        # Catalog changes invalidate the current plan as well as its messages.
        packet["stale"] |= self.intake.planning.get_plan(actor, case_id)["stale"]
        fields = {item["key"]: item["label"] for item in packet["content"]["fields"]}
        packet["informationRequests"] = []
        for request_id in case.get("informationRequestIds", []):
            requested = self.repository.get(f"cases/{case_id}/informationRequests/{request_id}")
            if requested and requested.get("packetId") == packet_id:
                packet["informationRequests"].append(
                    {
                        "requestId": requested["requestId"],
                        "packetVersion": requested["packetVersion"],
                        "requestedItems": [
                            {"key": key, "label": fields[key]}
                            for key in requested["requestedItems"]
                            if key in fields
                        ],
                        "message": requested.get("message", ""),
                        "state": requested["state"],
                        "createdAt": requested["createdAt"],
                        "answeredAt": requested.get("answeredAt"),
                        "answerVersion": requested.get("answerVersion"),
                    }
                )
        return packet

    def list(self, actor: Actor, case_id: str) -> dict[str, Any]:
        case = self.intake._case(self.repository, case_id, actor)
        return {
            "items": [
                {
                    key: packet[key]
                    for key in (
                        "packetId",
                        "recipientId",
                        "recipientName",
                        "version",
                        "status",
                        "planId",
                        "stale",
                        "delivery",
                    )
                }
                for packet_id in case.get("packetIds", [])
                for packet in [self.get(actor, case_id, packet_id)]
                if packet["planId"] == (case.get("plan") or {}).get("planId")
            ],
            "nextCursor": None,
        }

    @staticmethod
    def public(packet: Any) -> Any:
        return {
            key: packet[key]
            for key in (
                "packetId",
                "recipientId",
                "recipientName",
                "version",
                "status",
                "content",
                "verification",
                "delivery",
                "deadlines",
                "planId",
                "stale",
                "factsRevision",
                "contentHash",
            )
        } | {"informationRequests": packet.get("informationRequests", [])}

    def _job(self, tx: Any, case: Any, kind: str, **extra: Any) -> dict[str, str]:
        if len(case["jobIds"]) >= 80:
            raise IntakeError(429, "rate_limited")
        job_id = new_id("job")
        tx.set(
            f"jobs/{job_id}",
            {
                "jobId": job_id,
                "uid": case["victimUid"],
                "caseId": case["caseId"],
                "type": kind,
                "state": "queued",
                "attempts": 0,
                "error": None,
                "progress": {"step": 0, "total": 1},
                "createdAt": stamp(self.intake.clock()),
                **extra,
            },
        )
        case["jobIds"].append(job_id)
        tx.set(f"cases/{case['caseId']}", case)
        return {"jobId": job_id, "statusUrl": f"/api/v1/jobs/{job_id}"}

    def generate(self, actor: Actor, case_id: str, body: Any, key: str) -> Any:
        plan = self._current_plan(actor, case_id)
        if body["planId"] != plan["planId"]:
            raise IntakeError(409, "version_conflict")

        def queue(tx: Any) -> Any:
            case = self.intake._case(tx, case_id, actor)
            if case["flags"].get("distress"):
                raise IntakeError(409, "invalid_state_transition", "Pause and seek support first.")
            if not case.get("plan") or case["plan"]["planId"] != plan["planId"]:
                raise IntakeError(409, "version_conflict")
            existing = case.get("packetGeneration", {}).get(plan["planId"])
            if existing and (tx.get(f"jobs/{existing}") or {}).get("state") != "failed":
                return {"jobId": existing, "statusUrl": f"/api/v1/jobs/{existing}"}
            result = self._job(
                tx, case, "rebuild_packets", planId=plan["planId"], inputHash=plan["inputHash"]
            )
            case.setdefault("packetGeneration", {})[plan["planId"]] = result["jobId"]
            tx.set(f"cases/{case_id}", case)
            self.intake._event(tx, case_id, actor, "packets.queued")
            return result

        return self.intake._mutation(actor, f"/cases/{case_id}/packets/generate", key, body, queue)

    def _context(self, case: Any, plan: Any, recipient_id: str) -> dict[str, Any]:
        registry = self.intake.planning.workflow.registry
        packs = registry.available(
            allow_draft_preview=plan["draftPreview"],
            environment=self.intake.planning.workflow.environment,
            demo_mode=self.intake.planning.workflow.demo_mode,
        )
        pack = next(
            (
                item
                for item in packs
                if item.pack_id == plan["packId"] and item.version == plan["packVersion"]
            ),
            None,
        )
        if pack is None or canonical_hash(pack.model_dump(mode="json")) != plan["packHash"]:
            raise IntakeError(409, "version_conflict")
        step = next(
            (item for item in Plan.model_validate(plan).steps if item.recipient_id == recipient_id),
            None,
        )
        recipient = next((item for item in pack.recipients if item.id == recipient_id), None)
        if step is None or recipient is None:
            raise IntakeError(422, "validation_failed")
        evidence = []
        for evidence_id in case.get("evidenceIds", []):
            item = self.repository.get(f"cases/{case['caseId']}/evidence/{evidence_id}")
            if item and item["status"] == "ready" and item.get("extraction"):
                from packages.schemas.models import EvidenceExtraction

                evidence.append(EvidenceExtraction.model_validate(item["extraction"]))
        from agents.packets import anchor_confirmed_facts

        return dict(
            facts=anchor_confirmed_facts(
                CaseFacts.model_validate(case["facts"]),
                case_id=case["caseId"],
                facts_revision=case["factsRevision"],
            ),
            plan_step=step,
            recipient=recipient,
            pack=pack,
            source_passages=registry.passages(pack),
            evidence=evidence[:20],
            victim_language=case["language"],
            recipient_language=recipient.recipient_language,
            attachments=[],
        )

    def edit(self, actor: Actor, case_id: str, packet_id: str, body: Any) -> Any:
        current = self.get(actor, case_id, packet_id)
        if current["stale"]:
            raise IntakeError(409, "version_conflict", "Update the plan and messages first.")
        if len(json.dumps(body)) > 32_000 or scrub_credentials(json.dumps(body)) != json.dumps(
            body
        ):
            raise IntakeError(422, "unsafe_content_blocked")

        def update(tx: Any) -> Any:
            case, packet = self._packet(tx, actor, case_id, packet_id)
            if packet["version"] != body["ifVersion"] or packet.get("deliveryPending"):
                raise IntakeError(409, "version_conflict")
            content = PacketContent.model_validate(packet["content"])
            if body.get("message") is not None:
                content.message = body["message"]
            fields = {item.key: item for item in content.fields}
            for item in body.get("fields", []):
                if item["key"] not in fields:
                    raise IntakeError(422, "validation_failed")
                field = fields[item["key"]]
                original_value, original_availability = field.value, field.availability
                field.value = item["value"] if item.get("availability") != "not_available" else None
                field.availability = item.get("availability", "available")
                if field.value == original_value and field.availability == original_availability:
                    continue
                if original_value is not None and item["key"] not in packet.get(
                    "confirmedFields", {}
                ):
                    raise IntakeError(
                        422,
                        "validation_failed",
                        "Change recorded facts before changing this field.",
                    )
                field.provenance.source = "confirmed"
                if field.value is None:
                    packet.setdefault("confirmedFields", {}).pop(item["key"], None)
                elif original_value is None or item["key"] in packet.get("confirmedFields", {}):
                    packet.setdefault("confirmedFields", {})[item["key"]] = field.value
            packet.update(
                content=content.model_dump(mode="json", by_alias=True),
                version=packet["version"] + 1,
                status="DRAFT",
                delivery=None,
                verification={"passed": False, "checks": [], "iterations": 0},
            )
            packet["contentHash"] = canonical_hash(packet["content"])
            self._save(tx, case_id, packet)
            case["status"] = "IN_PROGRESS" if case.get("deliveryIds") else "PLAN_READY"
            job = self._job(
                tx,
                case,
                "verify_packet",
                packetId=packet_id,
                packetVersion=packet["version"],
                inputHash=packet["inputHash"],
            )
            self.intake._event(tx, case_id, actor, "packet.edited")
            return {
                "packetId": packet_id,
                "version": packet["version"],
                "status": "DRAFT",
                "jobId": job["jobId"],
            }

        return self.repository.atomic(update)

    def answer(self, actor: Actor, case_id: str, packet_id: str, body: Any, key: str) -> Any:
        """Answer one addressed receiver request; verification and sending stay separate."""
        from pydantic import ValidationError

        from agents.packets import prepare_content

        current = self.get(actor, case_id, packet_id)
        plan = self._current_plan(actor, case_id)
        if current["stale"]:
            raise IntakeError(409, "version_conflict")
        if (
            type(body) is not dict
            or set(body) != {"requestId", "answers", "ifVersion"}
            or type(body["requestId"]) is not str
            or not 1 <= len(body["requestId"]) <= 128
            or type(body["ifVersion"]) is not int
            or type(body["answers"]) is not list
            or not 1 <= len(body["answers"]) <= 20
        ):
            raise IntakeError(422, "validation_failed")
        for item in body["answers"]:
            if (
                type(item) is not dict
                or not {"itemKey", "value"} <= set(item) <= {"itemKey", "value", "availability"}
                or type(item["itemKey"]) is not str
                or type(item["value"]) is not str
                or len(item["value"]) > 250
                or item.get("availability", "available") not in {"available", "not_available"}
            ):
                raise IntakeError(422, "validation_failed")
        encoded = json.dumps(body, ensure_ascii=False)
        if len(encoded) > 12000 or scrub_credentials(encoded) != encoded:
            raise IntakeError(422, "unsafe_content_blocked")

        def update(tx: Any) -> Any:
            case, packet = self._packet(tx, actor, case_id, packet_id)
            expires = case.get("accessExpiresAtMs")
            workflow = self.intake.planning.workflow
            catalog_hash = workflow.registry.catalog_hash(
                allow_draft_preview=workflow.allow_draft_preview,
                environment=workflow.environment,
                demo_mode=workflow.demo_mode,
            )
            if (
                type(expires) is not int
                or expires <= int(self.intake.clock().timestamp() * 1000)
                or packet["version"] != body["ifVersion"]
                or packet.get("deliveryPending")
                or not case.get("plan")
                or case["plan"]["planId"] != plan["planId"]
                or self.intake.planning.input_hash(tx, case) != plan["inputHash"]
                or catalog_hash != plan["catalogHash"]
            ):
                raise IntakeError(409, "version_conflict")
            request_path = f"cases/{case_id}/informationRequests/{body['requestId']}"
            requested = (
                tx.get(request_path)
                if body["requestId"] in case.get("informationRequestIds", [])
                else None
            )
            if not requested or requested.get("state") != "open":
                raise IntakeError(
                    409,
                    "invalid_state_transition",
                    "There is no open receiver information request.",
                )
            receiver = self.intake.receiver
            if (
                receiver is None
                or receiver.recipient_orgs.get(packet["recipientId"]) != requested.get("orgId")
                or requested.get("packetId") != packet_id
                or requested.get("packetVersion") != packet["version"]
                or requested.get("contentHash") != packet["contentHash"]
                or packet["status"] != "NEEDS_INFO"
            ):
                raise IntakeError(409, "version_conflict")
            answers = {item["itemKey"]: item for item in body["answers"]}
            if len(answers) != len(body["answers"]) or set(answers) != set(
                requested["requestedItems"]
            ):
                raise IntakeError(422, "validation_failed")
            content = PacketContent.model_validate(packet["content"])
            fields = {item.key: item for item in content.fields}
            from agents.packets.core import confirmable_packet_fields

            context = self._context(case, plan, packet["recipientId"])
            allowed = confirmable_packet_fields(
                context["facts"], context["recipient"], context["pack"]
            )
            for field_key, item in answers.items():
                field = fields.get(field_key)
                if (
                    field_key not in allowed
                    or field is None
                    or field.value is not None
                    or field.availability == "not_available"
                ):
                    raise IntakeError(422, "validation_failed")
                unavailable = item.get("availability") == "not_available"
                value = item["value"].strip()
                if (unavailable and value) or (not unavailable and not value):
                    raise IntakeError(422, "validation_failed")
                field.value = None if unavailable else value
                field.availability = "not_available" if unavailable else "available"
                field.provenance.source = "confirmed"
                field.provenance.reference = f"packet_confirmation:{field_key}"
                if unavailable:
                    packet.setdefault("confirmedUnavailableFields", []).append(field_key)
                else:
                    packet.setdefault("confirmedFields", {})[field_key] = value
            context["confirmed_fields"] = packet.get("confirmedFields", {})
            context["facts"].unavailable_fields = list(
                dict.fromkeys(
                    context["facts"].unavailable_fields
                    + packet.get("confirmedUnavailableFields", [])
                )
            )
            for field_key in packet.get("confirmedUnavailableFields", []):
                context["facts"].field_provenance[field_key] = Provenance(
                    source="confirmed", reference=f"packet_confirmation:{field_key}"
                )
            # Validate all confirmations before persistence, including canonical financial formats.
            try:
                prepared = prepare_content(content, **context)
            except (ValueError, ValidationError):
                raise IntakeError(422, "validation_failed") from None
            packet.update(
                content=prepared.model_dump(mode="json", by_alias=True),
                version=packet["version"] + 1,
                status="DRAFT",
                delivery=None,
                deliveryPending=None,
                verification={"passed": False, "checks": [], "iterations": 0},
            )
            packet.pop("receiverDecisionId", None)
            packet["contentHash"] = canonical_hash(packet["content"])
            self._save(tx, case_id, packet)
            requested.update(
                state="answered",
                answeredAt=stamp(self.intake.clock()),
                answerVersion=packet["version"],
            )
            tx.set(request_path, requested)
            case["status"] = "IN_PROGRESS"
            job = self._job(
                tx,
                case,
                "verify_packet",
                packetId=packet_id,
                packetVersion=packet["version"],
                inputHash=packet["inputHash"],
            )
            self.intake._event(
                tx,
                case_id,
                actor,
                "packet.answered",
                {"requestId": body["requestId"], "packetVersion": packet["version"]},
            )
            return {
                "packetId": packet_id,
                "version": packet["version"],
                "status": "DRAFT",
                "requiresApproval": True,
                "jobId": job["jobId"],
            }

        return self.intake._mutation(
            actor, f"/cases/{case_id}/packets/{packet_id}/answer", key, body, update
        )

    @staticmethod
    def _save(tx: Any, case_id: str, packet: Any) -> None:
        path = f"cases/{case_id}/packets/{packet['packetId']}"
        tx.set(path, packet)
        tx.set(f"{path}/versions/{packet['version']}", packet)

    def _notify(self, tx: Any, case: Any, packet_id: str, kind: str, text: str) -> None:
        notification_id = new_id("notification")
        if case["language"] == "hi":
            text = {
                "packet.ready": "आपका संदेश जाँचने के लिए तैयार है।",
                "packet.sent": "आपका संदेश डेमो संस्था को भेजा गया है। किसी असली संस्था को नहीं भेजा गया।",
                "deadline.due_soon": "स्रोत में बताई समय-सीमा पास है। कृपया योजना जाँचें।",
                "deadline.overdue": "स्रोत में बताई समय-सीमा बीत गई है। कृपया योजना जाँचें।",
            }.get(kind, text)
        tx.set(
            f"cases/{case['caseId']}/notifications/{notification_id}",
            {
                "notificationId": notification_id,
                "packetId": packet_id,
                "kind": kind,
                "text": text,
                "createdAt": stamp(self.intake.clock()),
                "readAt": None,
            },
        )
        case.setdefault("notificationIds", []).append(notification_id)
        tx.set(f"cases/{case['caseId']}", case)

    def _generation_guard(self, tx: Any, job: Any, plan: Any, actor: Actor) -> Any:
        record = tx.get(f"jobs/{job['jobId']}")
        if (
            not record
            or record.get("claimToken") != job["claimToken"]
            or record.get("state") != "running"
            or not record.get("leaseUntil")
            or record["leaseUntil"] <= stamp(self.intake.clock())
        ):
            return None
        catalog_hash = self.intake.planning.workflow.registry.catalog_hash(
            allow_draft_preview=self.intake.planning.workflow.allow_draft_preview,
            environment=self.intake.planning.workflow.environment,
            demo_mode=self.intake.planning.workflow.demo_mode,
        )
        if catalog_hash != plan["catalogHash"]:
            raise IntakeError(409, "version_conflict")
        current = self.intake._case(tx, job["caseId"], actor)
        if (
            self.intake.planning.input_hash(tx, current) != job["inputHash"]
            or not current.get("plan")
            or current["plan"]["planId"] != plan["planId"]
            or current["plan"].get("packHash") != plan["packHash"]
        ):
            raise IntakeError(409, "version_conflict")
        return record, current

    @staticmethod
    def _generation_proof(plan: Any, packet: Any) -> Any:
        return {
            "planId": plan["planId"],
            "inputHash": plan["inputHash"],
            "catalogHash": plan["catalogHash"],
            "packHash": plan["packHash"],
            "factsRevision": plan["factsRevision"],
            "recipientId": packet["recipientId"],
            "packetVersion": 1,
            "contentHash": canonical_hash(packet["content"]),
        }

    def _retained_generation(
        self, tx: Any, job: Any, plan: Any, actor: Actor, recipient_id: str
    ) -> Any:
        guarded = self._generation_guard(tx, job, plan, actor)
        if guarded is None:
            return None
        _, current = guarded
        matching = [
            packet
            for packet_id in current.get("packetIds", [])
            if (packet := tx.get(f"cases/{job['caseId']}/packets/{packet_id}"))
            and packet["planId"] == plan["planId"]
            and packet["recipientId"] == recipient_id
        ]
        if not matching:
            return False
        if len(matching) != 1:
            raise IntakeError(409, "version_conflict")
        packet = matching[0]
        if (
            packet["version"] != 1
            or packet.get("inputHash") != plan["inputHash"]
            or packet.get("factsRevision") != plan["factsRevision"]
            or packet.get("contentHash") != canonical_hash(packet["content"])
            or packet.get("generationProof") != self._generation_proof(plan, packet)
        ):
            raise IntakeError(409, "version_conflict")
        return packet

    @staticmethod
    def _generation_case_status(current: Any, plan: Any, packets: Any) -> str:
        if any(packet.get("delivery") for packet in packets):
            return "IN_PROGRESS"
        required = {step["recipientId"] for step in plan["steps"]}
        ready = {
            packet["recipientId"]
            for packet in packets
            if packet["status"] == "VERIFIED" and packet.get("verification", {}).get("passed")
        }
        return "PACKETS_VERIFIED" if required and required <= ready else "PLAN_READY"

    def _generation_checkpoint(
        self,
        tx: Any,
        job: Any,
        plan: Any,
        actor: Actor,
        packet: Any,
        failures: Any,
        *,
        final: bool = False,
    ) -> bool:
        guarded = self._generation_guard(tx, job, plan, actor)
        if guarded is None:
            return False
        record, current = guarded
        if packet is not None:
            retained = self._retained_generation(tx, job, plan, actor, packet["recipientId"])
            if retained is None:
                return False
            if retained is not False:
                if retained["packetId"] != packet["packetId"]:
                    raise IntakeError(409, "version_conflict")
            else:
                packet["generationProof"] = self._generation_proof(plan, packet)
                self._save(tx, job["caseId"], packet)
                current.setdefault("packetIds", []).append(packet["packetId"])
                self._notify(
                    tx,
                    current,
                    packet["packetId"],
                    "packet.ready",
                    "Your message is ready to review.",
                )
        packets = [
            item
            for packet_id in current.get("packetIds", [])
            if (item := tx.get(f"cases/{job['caseId']}/packets/{packet_id}"))
            and item["planId"] == plan["planId"]
        ]
        current["status"] = self._generation_case_status(current, plan, packets)
        tx.set(f"cases/{job['caseId']}", current)
        record.update(
            progress={
                "step": len({p["recipientId"] for p in packets}),
                "total": len(plan["steps"]),
            },
            recipientFailures=dict(failures),
        )
        if final:
            record.update(
                state="failed" if failures else "succeeded",
                leaseUntil=None,
                error=self._problem("model_unavailable") if failures else None,
                resultRef=f"/api/v1/cases/{job['caseId']}/packets",
            )
        tx.set(f"jobs/{job['jobId']}", record)
        if packet is not None and retained is False:
            # Event indexing reads the final case; do not overwrite its eventIds afterward.
            self.intake._event(
                tx, job["caseId"], Actor("PacketWorkflow", "agent"), "packet.checked"
            )
        return True

    async def process(self, job_id: str) -> None:
        def claim(tx: Any) -> Any:
            job = tx.get(f"jobs/{job_id}")
            if not job or job["state"] not in {"queued", "running"}:
                return None
            now = stamp(self.intake.clock())
            if job.get("leaseUntil") and job["leaseUntil"] > now:
                return None
            case = self.intake._case(tx, job["caseId"], Actor(job["uid"], "victim"))
            if job["attempts"] >= 3:
                job.update(state="failed", error=self._problem("attempts_exhausted"))
                tx.set(f"jobs/{job_id}", job)
                return None
            job.update(
                state="running",
                attempts=job["attempts"] + 1,
                claimToken=new_id("claim"),
                leaseUntil=stamp(self.intake.clock() + timedelta(minutes=10)),
            )
            tx.set(f"jobs/{job_id}", job)
            return job, case

        claimed = self.repository.atomic(claim)
        if claimed is None:
            return
        job, case = claimed
        actor = Actor(job["uid"], "victim")
        try:
            plan = self._current_plan(actor, case["caseId"])
            if job["inputHash"] != plan["inputHash"]:
                raise IntakeError(409, "version_conflict")
            packets = []
            if job["type"] == "rebuild_packets":
                if job["planId"] != plan["planId"]:
                    raise IntakeError(409, "version_conflict")
                failures: dict[str, str] = {}
                for step in plan["steps"]:
                    retained = self.repository.atomic(
                        lambda tx, recipient_id=step["recipientId"]: self._retained_generation(
                            tx, job, plan, actor, recipient_id
                        )
                    )
                    if retained is None:
                        return
                    if retained is not False:
                        continue
                    context = self._context(case, plan, step["recipientId"])
                    try:
                        result = await asyncio.wait_for(self.pipeline.build(**context), timeout=120)
                    except (TimeoutError, ModelFailure):
                        failures[step["recipientId"]] = "model_unavailable"
                        if not self.repository.atomic(
                            lambda tx: self._generation_checkpoint(
                                tx, job, plan, actor, None, failures
                            )
                        ):
                            return
                        continue
                    if result.content is None:
                        failures[step["recipientId"]] = "model_unavailable"
                        if not self.repository.atomic(
                            lambda tx: self._generation_checkpoint(
                                tx, job, plan, actor, None, failures
                            )
                        ):
                            return
                        continue
                    content = result.content.model_dump(mode="json", by_alias=True)
                    packet = {
                        "packetId": new_id("packet"),
                        "recipientId": step["recipientId"],
                        "recipientName": step["recipientName"],
                        "version": 1,
                        "status": result.status,
                        "content": content,
                        "verification": {
                            "passed": result.status == "VERIFIED",
                            "checks": [
                                item.model_dump(mode="json", by_alias=True)
                                for item in result.checks
                            ],
                            "iterations": result.attempts,
                        },
                        "planId": plan["planId"],
                        "inputHash": plan["inputHash"],
                        "factsRevision": plan["factsRevision"],
                        "contentHash": canonical_hash(content),
                        "delivery": None,
                        "deadlines": [step["deadline"]] if step.get("deadline") else [],
                        "stale": False,
                    }
                    if not self.repository.atomic(
                        lambda tx, packet=packet: self._generation_checkpoint(
                            tx, job, plan, actor, packet, failures
                        )
                    ):
                        return
                self.repository.atomic(
                    lambda tx: self._generation_checkpoint(
                        tx, job, plan, actor, None, failures, final=True
                    )
                )
                return
            else:
                packet = self.get(actor, case["caseId"], job["packetId"])
                if packet["version"] != job["packetVersion"] or packet["stale"]:
                    raise IntakeError(409, "version_conflict")
                verification_context = self._context(case, plan, packet["recipientId"])
                verification_context["confirmed_fields"] = packet.get("confirmedFields", {})
                verification_context["facts"].unavailable_fields = list(
                    dict.fromkeys(
                        verification_context["facts"].unavailable_fields
                        + packet.get("confirmedUnavailableFields", [])
                    )
                )
                for field_key in packet.get("confirmedUnavailableFields", []):
                    verification_context["facts"].field_provenance[field_key] = Provenance(
                        source="confirmed", reference=f"packet_confirmation:{field_key}"
                    )
                from agents.packets import prepare_content

                prepared = prepare_content(
                    PacketContent.model_validate(packet["content"]), **verification_context
                )
                packet["content"] = prepared.model_dump(mode="json", by_alias=True)
                packet["contentHash"] = canonical_hash(packet["content"])
                checks = await asyncio.wait_for(
                    self.pipeline.verifier.verify(
                        prepared,
                        **verification_context,
                    ),
                    timeout=60,
                )
                passed = not any(not item.passed and item.severity == "blocker" for item in checks)
                packet.update(
                    status="VERIFIED" if passed else "NEEDS_HUMAN_REVIEW",
                    verification={
                        "passed": passed,
                        "checks": [item.model_dump(mode="json", by_alias=True) for item in checks],
                        "iterations": 1,
                    },
                )
                packets = [packet]

            def finish(tx: Any) -> None:
                record = tx.get(f"jobs/{job_id}")
                if not record or record.get("claimToken") != job["claimToken"]:
                    return
                catalog_hash = self.intake.planning.workflow.registry.catalog_hash(
                    allow_draft_preview=self.intake.planning.workflow.allow_draft_preview,
                    environment=self.intake.planning.workflow.environment,
                    demo_mode=self.intake.planning.workflow.demo_mode,
                )
                if catalog_hash != plan["catalogHash"]:
                    raise IntakeError(409, "version_conflict")
                current = self.intake._case(tx, case["caseId"], actor)
                if self.intake.planning.input_hash(tx, current) != job["inputHash"]:
                    raise IntakeError(409, "version_conflict")
                if not current.get("plan") or current["plan"]["planId"] != plan["planId"]:
                    raise IntakeError(409, "version_conflict")
                for packet in packets:
                    if job["type"] == "verify_packet":
                        latest = tx.get(f"cases/{case['caseId']}/packets/{packet['packetId']}")
                        if not latest or latest["version"] != packet["version"]:
                            raise IntakeError(409, "version_conflict")
                    self._save(tx, case["caseId"], packet)
                    if packet["packetId"] not in current.setdefault("packetIds", []):
                        current["packetIds"].append(packet["packetId"])
                    self._notify(
                        tx,
                        current,
                        packet["packetId"],
                        "packet.ready",
                        "Your message is ready to review.",
                    )
                current_packets = [
                    item
                    for packet_id in current.get("packetIds", [])
                    if (item := tx.get(f"cases/{case['caseId']}/packets/{packet_id}"))
                    and item["planId"] == plan["planId"]
                ]
                current["status"] = self._generation_case_status(current, plan, current_packets)
                tx.set(f"cases/{case['caseId']}", current)
                record.update(
                    state="succeeded",
                    progress={"step": 1, "total": 1},
                    leaseUntil=None,
                    resultRef=f"/api/v1/cases/{case['caseId']}/packets",
                )
                tx.set(f"jobs/{job_id}", record)
                self.intake._event(
                    tx, case["caseId"], Actor("PacketWorkflow", "agent"), "packets.checked"
                )

            self.repository.atomic(finish)
        except Exception as exc:
            failure_code = exc.code if isinstance(exc, IntakeError) else "model_unavailable"

            def fail(tx: Any) -> None:
                record = tx.get(f"jobs/{job_id}")
                if record and record.get("claimToken") == job["claimToken"]:
                    record.update(
                        state="failed",
                        leaseUntil=None,
                        error=self._problem(failure_code),
                    )
                    tx.set(f"jobs/{job_id}", record)

            self.repository.atomic(fail)

    @staticmethod
    def _problem(code: str) -> dict[str, Any]:
        return {
            "type": f"https://relay.example/errors/{code}",
            "title": code.replace("_", " "),
            "status": 503 if code == "model_unavailable" else 409,
            "code": code,
            "detail": "The operation could not complete. Review and try again.",
            "requestId": new_id("req"),
            "fieldErrors": [],
            "retryable": code == "model_unavailable",
        }

    async def approve(self, actor: Actor, case_id: str, packet_id: str, body: Any) -> Any:
        packet = self.get(actor, case_id, packet_id)
        if packet["stale"]:
            raise IntakeError(409, "version_conflict")
        if (
            body.get("confirm") is not True
            or body.get("confirmedRecipientId") != packet["recipientId"]
        ):
            raise IntakeError(403, "action_requires_approval")
        if body["packetVersion"] != packet["version"]:
            raise IntakeError(409, "version_conflict")

        def prepare(tx: Any) -> str:
            case, current = self._packet(tx, actor, case_id, packet_id)
            if case["flags"].get("distress"):
                raise IntakeError(409, "invalid_state_transition", "Pause and seek support first.")
            if current["version"] != body["packetVersion"] or self._stale(case, current):
                raise IntakeError(409, "version_conflict")
            if current.get("delivery"):
                return ""
            if current.get("deliveryPending"):
                pending = tx.get(f"jobs/{current['deliveryPending']}")
                if pending and pending["state"] != "failed":
                    return current["deliveryPending"]
            context = Context(
                packet_id,
                current["version"],
                current["contentHash"],
                owner_uid=actor.uid,
                recipient_id=current["recipientId"],
                verified=current["status"] == "VERIFIED" and current["verification"]["passed"],
                simulated=True,
            )
            if ActionPolicy.check(actor, Action.SEND, context) != Decision.REQUIRE_APPROVAL:
                raise IntakeError(
                    409, "invalid_state_transition", "The current message must pass verification."
                )
            approval = {
                "actorUid": actor.uid,
                "packetId": packet_id,
                "packetVersion": current["version"],
                "contentHash": current["contentHash"],
                "confirmedRecipientId": current["recipientId"],
                "approvedAt": stamp(self.intake.clock()),
                "expiresAt": stamp(self.intake.clock() + timedelta(minutes=10)),
            }
            approval_id = new_id("approval")
            tx.set(f"cases/{case_id}/approvals/{approval_id}", approval)
            case.setdefault("approvalIds", []).append(approval_id)
            job = self._job(
                tx,
                case,
                "send_packet",
                packetId=packet_id,
                packetVersion=current["version"],
                contentHash=current["contentHash"],
                approvalId=approval_id,
                inputHash=current["inputHash"],
                approvedAt=approval["approvedAt"],
            )
            delivery_id = "delivery_" + canonical_hash(
                {
                    "owner": actor.uid,
                    "case": case_id,
                    "packet": packet_id,
                    "version": current["version"],
                    "recipient": current["recipientId"],
                    "key": f"{packet_id}:{current['version']}",
                }
            )
            case.setdefault("deliveryIds", []).append(delivery_id)
            tx.set(f"cases/{case_id}", case)
            current["deliveryPending"] = job["jobId"]
            self._save(tx, case_id, current)
            self.intake._event(tx, case_id, actor, "packet.approved", approval)
            return job["jobId"]

        job_id = self.repository.atomic(prepare)
        if job_id:
            await self.process_delivery(job_id)
        latest = self.get(actor, case_id, packet_id)
        if not latest.get("delivery"):
            raise IntakeError(
                503, "adapter_unavailable", "Simulated delivery is pending. Check the tracker."
            )
        return {"packetId": packet_id, "status": "SENT", "delivery": latest["delivery"]}

    async def process_delivery(self, job_id: str) -> None:
        from datetime import datetime

        from packages.delivery import DeliveryProjection

        def claim(tx: Any) -> Any:
            job = tx.get(f"jobs/{job_id}")
            if not job or job["state"] not in {"queued", "running"}:
                return None
            now = stamp(self.intake.clock())
            if job.get("leaseUntil") and job["leaseUntil"] > now:
                return None
            if job.get("retryAfter") and job["retryAfter"] > now:
                return None
            actor = Actor(job["uid"], "victim")
            case, packet = self._packet(tx, actor, job["caseId"], job["packetId"])
            stored = tx.get(f"cases/{job['caseId']}/approvals/{job['approvalId']}")
            if not stored:
                raise IntakeError(403, "action_requires_approval")
            approval = Approval(
                actor.uid,
                Action.SEND,
                packet["packetId"],
                stored["packetVersion"],
                stored["contentHash"],
                stored["confirmedRecipientId"],
                datetime.fromisoformat(stored["approvedAt"].replace("Z", "+00:00")),
                datetime.fromisoformat(stored["expiresAt"].replace("Z", "+00:00")),
            )
            context = Context(
                packet["packetId"],
                packet["version"],
                packet["contentHash"],
                owner_uid=actor.uid,
                recipient_id=packet["recipientId"],
                verified=packet["verification"]["passed"] and packet["status"] == "VERIFIED",
            )
            if (
                ActionPolicy.check_with_approval(
                    actor, Action.SEND, context, approval, now=self.intake.clock()
                )
                != Decision.ALLOW
                or self._stale(case, packet)
                or case["flags"].get("distress")
                or job["attempts"] >= 3
            ):
                job.update(
                    state="failed", error=self._problem("action_requires_approval"), leaseUntil=None
                )
                packet["deliveryPending"] = None
                self._save(tx, case["caseId"], packet)
                tx.set(f"jobs/{job_id}", job)
                return None
            job.update(
                state="running",
                attempts=job["attempts"] + 1,
                claimToken=new_id("claim"),
                leaseUntil=stamp(self.intake.clock() + timedelta(seconds=45)),
            )
            tx.set(f"jobs/{job_id}", job)
            return job, case, packet

        claimed = self.repository.atomic(claim)
        if claimed is None:
            return
        job, case, packet = claimed
        try:
            actor = Actor(job["uid"], "victim")
            plan = self._current_plan(actor, case["caseId"])
            payment_time = CaseFacts.model_validate(case["facts"]).payment.timestamp
            approved_at = datetime.fromisoformat(job["approvedAt"].replace("Z", "+00:00"))
            minutes = (
                max(0, int((approved_at - payment_time).total_seconds() / 60))
                if payment_time
                else None
            )
            projection = DeliveryProjection.model_validate(
                {
                    "ownerUid": actor.uid,
                    "caseId": case["caseId"],
                    "caseRef": case["caseRef"],
                    "packetId": packet["packetId"],
                    "packetVersion": packet["version"],
                    "contentHash": packet["contentHash"],
                    "packId": plan["packId"],
                    "packVersion": plan["packVersion"],
                    "recipientId": packet["recipientId"],
                    "fields": {
                        item["key"]: item.get("value") for item in packet["content"]["fields"]
                    },
                    "typology": plan["classification"]["typology"],
                    "category": None,
                    "simulation": {
                        "bankMode": "auto",
                        "railMode": "normal",
                        "minutesSincePayment": minutes,
                    },
                }
            )
            key = f"{packet['packetId']}:{packet['version']}"
            receipt = await asyncio.wait_for(self.adapter.deliver(projection, key), timeout=20)
            data = receipt.model_dump(mode="json", by_alias=True)

            def finish(tx: Any) -> None:
                current_job = tx.get(f"jobs/{job_id}")
                if not current_job or current_job.get("claimToken") != job["claimToken"]:
                    return
                current, latest = self._packet(tx, actor, case["caseId"], packet["packetId"])
                if (
                    latest["version"] != packet["version"]
                    or latest["contentHash"] != packet["contentHash"]
                ):
                    raise IntakeError(409, "version_conflict")
                latest.update(
                    status="SENT",
                    deliveryPending=None,
                    delivery={
                        name: data[name]
                        for name in (
                            "adapter",
                            "ticketRef",
                            "status",
                            "simulated",
                            "sentAt",
                            "missingItems",
                        )
                    },
                )
                self._save(tx, case["caseId"], latest)
                if data["deliveryId"] not in current.setdefault("deliveryIds", []):
                    current["deliveryIds"].append(data["deliveryId"])
                current["status"] = "IN_PROGRESS"
                if self.intake.receiver is not None:
                    expires = current.get("accessExpiresAtMs")
                    if type(expires) is not int or expires <= int(
                        self.intake.clock().timestamp() * 1000
                    ):
                        raise IntakeError(409, "version_conflict")
                    reference = self.intake.receiver.project_delivery(
                        tx,
                        owner_uid=actor.uid,
                        case_id=case["caseId"],
                        case_ref=current["caseRef"],
                        packet=self.public(latest),
                        plan=plan,
                        receipt=data,
                        access_expires_at_ms=expires,
                        minutes_since_payment=minutes,
                    )
                    references = current.setdefault("receiverProjectionRefs", [])
                    if reference not in references:
                        references.append(reference)
                    if self.intake.linking is not None:
                        from packages.linking.delivery import index_approved_delivery

                        index_approved_delivery(self.intake.linking, tx, current, latest)
                    if self.intake.receiver_handoff is not None:
                        self.intake.receiver_handoff.enqueue(
                            tx, case=current, packet=latest, projection_ref=reference
                        )
                self._notify(
                    tx,
                    current,
                    packet["packetId"],
                    "packet.sent",
                    "Your message was delivered to a simulated institution.",
                )
                current_job.update(
                    state="succeeded", leaseUntil=None, progress={"step": 1, "total": 1}, error=None
                )
                tx.set(f"jobs/{job_id}", current_job)
                self.intake._event(
                    tx, case["caseId"], Actor("MockDelivery", "system"), "packet.sent", data
                )

            self.repository.atomic(finish)
        except Exception:

            def fail(tx: Any) -> None:
                record = tx.get(f"jobs/{job_id}")
                if record and record.get("claimToken") == job["claimToken"]:
                    record.update(
                        state="queued" if record["attempts"] < 3 else "failed",
                        leaseUntil=None,
                        retryAfter=stamp(self.intake.clock() + timedelta(seconds=10)),
                        error=self._problem("adapter_unavailable"),
                    )
                    tx.set(f"jobs/{job_id}", record)

            self.repository.atomic(fail)

    def notifications(self, actor: Actor, case_id: str, notification_id: str | None = None) -> Any:
        def read(tx: Any) -> Any:
            case = self.intake._case(tx, case_id, actor)
            if notification_id:
                path = f"cases/{case_id}/notifications/{notification_id}"
                if notification_id not in case.get("notificationIds", []):
                    raise IntakeError(404, "not_found")
                item = tx.get(path)
                item["readAt"] = item.get("readAt") or stamp(self.intake.clock())
                tx.set(path, item)
                return item
            return {
                "items": [
                    item
                    for item_id in case.get("notificationIds", [])
                    if (item := tx.get(f"cases/{case_id}/notifications/{item_id}"))
                ],
                "nextCursor": None,
            }

        return self.repository.atomic(read)

    def events(self, actor: Actor, case_id: str, limit: int = 50, cursor: str | None = None) -> Any:
        case = self.intake._case(self.repository, case_id, actor)
        ids = case.get("eventIds", [])
        if cursor and cursor not in ids:
            raise IntakeError(400, "bad_request")
        start = ids.index(cursor) + 1 if cursor else 0
        selected = ids[start : start + min(max(limit, 1), 100)]
        return {
            "items": [
                item
                for item_id in selected
                if (item := self.repository.get(f"cases/{case_id}/events/{item_id}"))
            ],
            "nextCursor": selected[-1] if selected and start + len(selected) < len(ids) else None,
        }

    def export(self, actor: Actor, case_id: str) -> Any:
        case = self.intake._case(self.repository, case_id, actor)
        return {
            "case": self.intake.get_case(actor, case_id),
            "packets": [
                self.public(self.get(actor, case_id, item)) for item in case.get("packetIds", [])
            ],
            "events": [
                item
                for item_id in case.get("eventIds", [])
                if (item := self.repository.get(f"cases/{case_id}/events/{item_id}"))
            ],
            "evidence": [],
            "pipeline": [],
        }

    def pdf(self, actor: Actor, case_id: str, packet_id: str) -> Any:
        from packages.intake.storage import LocalFileBlobStore
        from packages.packets.pdf import render_packet_pdf

        packet = self.get(actor, case_id, packet_id)
        path = f"packets/{case_id}/{packet_id}/{packet['version']}.pdf"
        data = render_packet_pdf(
            PacketContent.model_validate(packet["content"]), recipient_name=packet["recipientName"]
        )
        self.intake.export_storage.write(path, data, "application/pdf")
        try:

            def audit(tx: Any) -> None:
                _, current = self._packet(tx, actor, case_id, packet_id)
                if current["version"] != packet["version"]:
                    raise IntakeError(409, "version_conflict")
                self.intake._event(
                    tx,
                    case_id,
                    actor,
                    "packet.download_requested",
                    {
                        "packetId": packet_id,
                        "version": packet["version"],
                        "contentHash": packet["contentHash"],
                    },
                )

            self.repository.atomic(audit)
        except Exception:
            self.intake.export_storage.delete(path)
            raise
        if isinstance(self.intake.export_storage, LocalFileBlobStore):
            url = self.intake.export_storage._url(path, actor.uid, "application/pdf", 0, "packet")
        else:
            url = self.intake.export_storage.preview_url(path, actor.uid, "application/pdf")
        return {"downloadUrl": url, "expiresAt": stamp(self.intake.clock() + timedelta(seconds=60))}

    def pdf_bytes(self, token: str) -> bytes:
        try:
            encoded = token.split(".", 1)[0]
            if len(token) > 2048:
                raise ValueError()
            untrusted = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            cap = self.intake.export_storage.capability(token, untrusted["uid"], "packet")
            _, case_id, packet_id, filename = cap["path"].split("/")
            packet = self.get(Actor(cap["uid"], "victim"), case_id, packet_id)
            if filename != f"{packet['version']}.pdf":
                raise ValueError()
            return self.intake.export_storage.read(cap["path"])
        except (ValueError, KeyError, TypeError, FileNotFoundError) as exc:
            raise IntakeError(403, "forbidden") from exc
