"""Durable planning jobs and proof-bound plans; only transactions mutate state."""

import asyncio
import re
import time
from datetime import datetime, timedelta
from typing import Any

from agents.intake.clients import ModelFailure
from packages.common.identifiers import canonical_hash, new_id
from packages.intake.service import (
    IntakeError,
    IntakeService,
    intake_history,
    missing_minimum,
    planning_input_hash,
    stamp,
)
from packages.packs.registry import PackRegistryError
from packages.safety import Actor
from packages.schemas.models import Plan


class PlanningService:
    def __init__(self, intake: IntakeService, workflow: Any) -> None:
        self.intake = intake
        self.repository = intake.repository
        self.workflow = workflow

    def enqueue(
        self, actor: Actor, case_id: str, body: dict[str, Any], *, rerun: bool = False
    ) -> dict[str, str]:
        self.intake._case(self.repository, case_id, actor, allow_admin=True)
        preview = bool(body.get("previewDraft", False))
        if preview and not self.workflow.allow_draft_preview:
            raise IntakeError(
                403, "forbidden", "Draft previews are available only in local demo mode."
            )
        country = body.get("jurisdictionCode")
        version = body.get("packVersion")
        if country and not re.fullmatch(r"[A-Z]{2}", country):
            raise IntakeError(422, "validation_failed", "Choose a two-letter country code.")
        if version and not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise IntakeError(422, "validation_failed", "Choose a known pack version.")
        available = self.workflow.registry.available(
            allow_draft_preview=preview,
            environment=self.workflow.environment,
            demo_mode=self.workflow.demo_mode,
        )
        if not available:
            raise IntakeError(
                422, "pack_review_required", self.problem("pack_review_required", 422)["detail"]
            )
        catalog_hash = self.workflow.registry.catalog_hash(
            allow_draft_preview=self.workflow.allow_draft_preview,
            environment=self.workflow.environment,
            demo_mode=self.workflow.demo_mode,
        )
        if version:
            if not any(pack.version == version for pack in available):
                raise IntakeError(
                    422, "validation_failed", "The requested pack version is unavailable."
                )

        def queue(tx: Any) -> dict[str, str]:
            case = self.intake._case(tx, case_id, actor, allow_admin=True)
            if case["flags"].get("distress"):
                raise IntakeError(
                    409, "invalid_state_transition", "Pause planning and seek support first."
                )
            if country:
                case["facts"]["country"] = {
                    "value": country,
                    "availability": "available",
                    "provenance": {"source": "selected"},
                }
                from packages.schemas.models import CaseFacts

                case["facts"] = CaseFacts.model_validate(case["facts"]).model_dump(
                    mode="json", by_alias=True
                )
                case["factsRevision"] += 1
            missing = missing_minimum(case["facts"])
            if missing:
                raise IntakeError(
                    422, "minimum_facts_missing", "Missing details: " + ", ".join(missing)
                )
            facts_hash = canonical_hash(case["facts"])
            input_hash = self.input_hash(tx, case)
            key = canonical_hash(
                {
                    "caseId": case_id,
                    "inputHash": input_hash,
                    "catalogHash": catalog_hash,
                    "previewDraft": preview,
                    "packVersion": version,
                }
            )
            path = f"planningRequests/{key}"
            previous = tx.get(path)
            if previous:
                job = tx.get(f"jobs/{previous['jobId']}")
                if (
                    job
                    and not (body.get("force") and job["state"] == "failed")
                    and not (rerun and job["state"] in {"succeeded", "failed"})
                ):
                    return {"jobId": job["jobId"], "statusUrl": f"/api/v1/jobs/{job['jobId']}"}
            if len(case["jobIds"]) >= 40:
                raise IntakeError(429, "budget_exceeded")
            job_id = new_id("job")
            now = self.intake.clock()
            tx.set(
                f"jobs/{job_id}",
                {
                    "jobId": job_id,
                    "type": "process_case",
                    "state": "queued",
                    "progress": {"step": 0, "total": 3},
                    "error": None,
                    "resultRef": None,
                    "caseId": case_id,
                    "uid": case["victimUid"],
                    "factsHash": facts_hash,
                    "inputHash": input_hash,
                    "catalogHash": catalog_hash,
                    "factsRevision": case["factsRevision"],
                    "previewDraft": preview,
                    "packVersion": version,
                    "createdAt": stamp(now),
                    "attempts": 0,
                },
            )
            tx.set(path, {"jobId": job_id, "caseId": case_id})
            case["jobIds"].append(job_id)
            case.setdefault("planningRequestIds", []).append(key)
            case["updatedAt"] = stamp(now)
            tx.set(f"cases/{case_id}", case)
            self.intake._event(
                tx, case_id, actor, "plan.rerun" if country or version else "plan.requested"
            )
            return {"jobId": job_id, "statusUrl": f"/api/v1/jobs/{job_id}"}

        return self.repository.atomic(queue)

    @staticmethod
    def input_hash(repository: Any, case: dict[str, Any]) -> str:
        evidence = [
            repository.get(f"cases/{case['caseId']}/evidence/{item}")
            for item in case["evidenceIds"]
        ]
        return planning_input_hash(case, evidence)

    def get_plan(self, actor: Actor, case_id: str) -> dict[str, Any]:
        case = self.intake._case(self.repository, case_id, actor, allow_admin=True)
        if not case.get("plan"):
            raise IntakeError(404, "not_found", "A plan is not ready yet.")
        plan = Plan.model_validate(case["plan"])
        plan.stale = plan.input_hash != self.input_hash(self.repository, case)
        try:
            catalog_hash = self.workflow.registry.catalog_hash(
                allow_draft_preview=self.workflow.allow_draft_preview,
                environment=self.workflow.environment,
                demo_mode=self.workflow.demo_mode,
            )
            plan.stale = plan.stale or plan.catalog_hash != catalog_hash
        except PackRegistryError:
            plan.stale = True
        return plan.model_dump(mode="json", by_alias=True)

    async def process_case(self, job_id: str) -> None:
        def claim(tx: Any) -> tuple[dict[str, Any], dict[str, Any]] | None:
            job = tx.get(f"jobs/{job_id}")
            if not job or job["state"] not in {"queued", "running"}:
                return None
            now = self.intake.clock()
            for field in ("leaseUntil", "retryAfter"):
                if (
                    job.get(field)
                    and datetime.fromisoformat(job[field].replace("Z", "+00:00")) > now
                ):
                    return None
            if job.get("attempts", 0) >= 3:
                job.update(state="failed", error=self.problem("budget_exceeded", 429))
                tx.set(f"jobs/{job_id}", job)
                return None
            try:
                case = self.intake._case(tx, job["caseId"], Actor(job["uid"], "victim"))
            except IntakeError as error:
                job.update(state="failed", error=self.problem(error.code, error.status))
                tx.set(f"jobs/{job_id}", job)
                return None
            if self.input_hash(tx, case) != job["inputHash"]:
                job.update(state="failed", error=self.problem("version_conflict", 409))
                tx.set(f"jobs/{job_id}", job)
                return None
            job.update(
                state="running",
                leaseUntil=stamp(now + timedelta(minutes=3)),
                claimToken=new_id("claim"),
            )
            job["attempts"] += 1
            tx.set(f"jobs/{job_id}", job)
            return job, case

        claimed = self.repository.atomic(claim)
        if claimed is None:
            return
        job, case = claimed
        started = time.monotonic()
        try:
            catalog_hash = self.workflow.registry.catalog_hash(
                allow_draft_preview=self.workflow.allow_draft_preview,
                environment=self.workflow.environment,
                demo_mode=self.workflow.demo_mode,
            )
            if catalog_hash != job["catalogHash"]:
                raise IntakeError(409, "version_conflict")
            evidence = []
            for evidence_id in case["evidenceIds"]:
                item = self.repository.get(f"cases/{case['caseId']}/evidence/{evidence_id}")
                if item and item["status"] == "ready" and item.get("extraction"):
                    evidence.append(item["extraction"])
            outcome = await asyncio.wait_for(
                self.workflow.execute(
                    uid=job["uid"],
                    facts=case["facts"],
                    facts_revision=case["factsRevision"],
                    history=intake_history(case, Actor(job["uid"], "victim")),
                    evidence=evidence[:20],
                    now=self.intake.clock(),
                    language=case["language"],
                    preview_draft=job["previewDraft"],
                    pack_version=job.get("packVersion"),
                ),
                timeout=30,
            )
            if outcome.get("plan"):
                plan = Plan.model_validate(outcome["plan"])
                plan.processing_ms = round((time.monotonic() - started) * 1000)
                plan.input_hash = job["inputHash"]
                plan.catalog_hash = job["catalogHash"]
                outcome["plan"] = plan.model_dump(mode="json", by_alias=True)
            catalog_hash = self.workflow.registry.catalog_hash(
                allow_draft_preview=self.workflow.allow_draft_preview,
                environment=self.workflow.environment,
                demo_mode=self.workflow.demo_mode,
            )
            if catalog_hash != job["catalogHash"]:
                raise IntakeError(409, "version_conflict")

            def finish(tx: Any) -> None:
                current_job = tx.get(f"jobs/{job_id}")
                current = tx.get(f"cases/{job['caseId']}")
                if (
                    not current_job
                    or not current
                    or current.get("deleting")
                    or current_job.get("state") != "running"
                    or current_job.get("claimToken") != job["claimToken"]
                ):
                    return
                self.intake._case(tx, job["caseId"], Actor(job["uid"], "victim"))
                if self.input_hash(tx, current) != job["inputHash"]:
                    current_job.update(state="failed", error=self.problem("version_conflict", 409))
                    tx.set(f"jobs/{job_id}", current_job)
                    return
                current["classification"] = outcome["classification"]
                current["classificationInputHash"] = job["inputHash"]
                current["flags"]["lowConfidence"] = bool(
                    outcome["classification"]["needsHumanReview"]
                )
                if outcome.get("plan"):
                    plan = outcome["plan"]
                    tx.set(f"cases/{job['caseId']}/plans/{plan['planId']}", plan)
                    current.setdefault("planIds", []).append(plan["planId"])
                    current["plan"] = plan
                    current["status"] = "PLAN_READY"
                else:
                    current["status"] = "INTAKE"
                    current["plan"] = None
                current["updatedAt"] = stamp(self.intake.clock())
                tx.set(f"cases/{job['caseId']}", current)
                current_job.update(
                    state="succeeded",
                    progress={"step": 3, "total": 3},
                    error=None,
                    resultRef=f"/api/v1/cases/{job['caseId']}",
                    leaseUntil=None,
                )
                tx.set(f"jobs/{job_id}", current_job)
                self.intake._event(
                    tx,
                    job["caseId"],
                    Actor("CasePlanningWorkflow", "agent"),
                    "plan.ready" if outcome.get("plan") else "plan.clarification_required",
                )

            self.repository.atomic(finish)
        except Exception as error:
            retryable = isinstance(error, (ModelFailure, TimeoutError))
            code = (
                "pack_review_required"
                if isinstance(error, PackRegistryError)
                else "model_unavailable"
            )
            if isinstance(error, ValueError) and not isinstance(
                error, (ModelFailure, PackRegistryError)
            ):
                code = "validation_failed"
            if isinstance(error, RuntimeError) and not isinstance(error, ModelFailure):
                code = "internal_error"
            if isinstance(error, IntakeError):
                code = error.code
            error_status = (
                error.status if isinstance(error, IntakeError) else (503 if retryable else 422)
            )

            def fail(tx: Any) -> None:
                current = tx.get(f"jobs/{job_id}")
                if not current or current.get("claimToken") != job["claimToken"]:
                    return
                retry = retryable and current["attempts"] < 3
                current.update(
                    state="queued" if retry else "failed",
                    error=self.problem(code, error_status),
                    leaseUntil=None,
                    retryAfter=stamp(
                        self.intake.clock() + timedelta(seconds=2 ** current["attempts"])
                    )
                    if retry
                    else None,
                )
                tx.set(f"jobs/{job_id}", current)

            self.repository.atomic(fail)

    @staticmethod
    def problem(code: str, status: int) -> dict[str, Any]:
        detail = (
            "No reviewed published pack is available. "
            "An explicitly enabled local draft preview is separate."
            if code == "pack_review_required"
            else "The plan could not be completed. Check your details and retry."
        )
        return {
            "type": f"https://relay.example/errors/{code}",
            "title": code.replace("_", " "),
            "status": status,
            "code": code,
            "detail": detail,
            "requestId": new_id("req"),
            "fieldErrors": [],
            "retryable": status == 503,
        }
