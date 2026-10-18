"""Thin live intake tools; no delivery, approval or heavy model capability."""

import json
from typing import Any

from agents.intake.core import DISTRESS, FIRST_ACTION, _distress
from packages.common.identifiers import canonical_hash, new_id
from packages.intake.service import IntakeError, merge_facts, missing_minimum, stamp
from packages.safety import Actor, SafetyGuard, scrub_credentials


def safe_live_output(text: str) -> bool:
    return scrub_credentials(text) == text and SafetyGuard().inspect_output(text).allow


def live_tool_response(result: dict[str, Any]) -> dict[str, Any]:
    """Informative static control fields; no provider errors become instructions."""
    if result.get("reason_if_not") == "transcription_pending":
        return {
            **result,
            "status": "transcription_pending",
            "retryable": True,
            "message": "Wait for the final victim transcript before recording facts.",
        }
    if result.get("code") == "tool_limit":
        status, message = (
            "limit_reached",
            "Stop calling tools. Speak to the person before another tool.",
        )
    elif result.get("ok") is False or result.get("queued") is False:
        status = (
            "needs_input"
            if result.get("reason_if_not") == "minimum_facts_missing"
            else "unavailable"
        )
        message = "Ask one missing-fact question. Do not repeat this tool without new input."
        if result.get("reason_if_not") == "distress_paused":
            status, message = (
                "paused",
                "Pause all collection and offer the provided support message.",
            )
    else:
        status, message = (
            "ok",
            "The action completed. Report this result without repeating the call.",
        )
    return {**result, "status": status, "retryable": False, "message": message}


class LiveIntakeTools:
    def __init__(
        self,
        intake: Any,
        actor: Actor,
        case_id: str,
        language: str,
        *,
        processing_options: dict[str, Any] | None = None,
    ):
        self.intake, self.actor, self.case_id = intake, actor, case_id
        self.language = language
        self.processing_options = dict(processing_options or {})
        self.guard = SafetyGuard()
        self.calls: dict[str, tuple[str, dict[str, Any]]] = {}
        self.statement_turn_id: str | None = None

    def begin_statement(self) -> None:
        """Invalidate the prior source at a new input/interrupt/response boundary."""
        self.statement_turn_id = None

    def case(self) -> dict[str, Any]:
        return self.intake._case(self.intake.repository, self.case_id, self.actor)

    def plan_ready(self, job_id: str) -> str | None:
        case = self.case()
        job = self.intake.repository.get(f"jobs/{job_id}")
        if (
            not job
            or job.get("uid") != self.actor.uid
            or job.get("caseId") != self.case_id
            or job.get("state") != "succeeded"
            or not case.get("plan")
            or self.intake.planning is None
        ):
            return None
        plan = self.intake.planning.get_plan(self.actor, self.case_id)
        return None if plan.get("stale") else plan["planId"]

    def caption(self, role: str, text: str) -> str:
        if role not in {"user", "assistant"} or not 1 <= len(text) <= 4000:
            raise IntakeError(422, "validation_failed")
        if role == "assistant" and not safe_live_output(text):
            raise IntakeError(422, "unsafe_content_blocked")
        safe = scrub_credentials(text)

        def save(tx: Any) -> str:
            case = self.intake._case(tx, self.case_id, self.actor)
            if len(case["transcript"]) >= 80:
                raise IntakeError(429, "budget_exceeded")
            turn_id = new_id("turn")
            turn = {
                "turnId": turn_id,
                "role": role,
                "text": safe,
                "lang": self.language,
                "ts": stamp(self.intake.clock()),
            }
            case["transcript"].append(turn)
            tx.set(f"cases/{self.case_id}", case)
            tx.set(f"cases/{self.case_id}/transcript/{turn_id}", turn)
            self.intake._event(
                tx, self.case_id, self.actor, "live.caption_saved", {"turnId": turn_id}
            )
            return turn_id

        turn_id = self.intake.repository.atomic(save)
        if role == "user":
            self.statement_turn_id = turn_id if safe == text and "[REDACTED" not in safe else None
        return turn_id

    def observe(self, text: str) -> dict[str, Any]:
        """Scrub before durable flags; raw audio is never stored by these tools."""
        if len(text) > 4000:
            raise IntakeError(422, "validation_failed")
        safe = scrub_credentials(text)
        distress = bool(_distress.search(safe))
        injection = bool(self.guard.inspect_input(safe).flags)
        if distress or injection:

            def flag(tx: Any) -> None:
                case = self.intake._case(tx, self.case_id, self.actor)
                changed = (distress and not case["flags"].get("distress")) or (
                    injection and not case["flags"].get("injectionAttempt")
                )
                case["flags"]["distress"] |= distress
                case["flags"]["injectionAttempt"] |= injection
                if changed:
                    tx.set(f"cases/{self.case_id}", case)
                    self.intake._event(
                        tx,
                        self.case_id,
                        self.actor,
                        "live.safety_flagged",
                        {"distress": distress, "injection": injection},
                    )

            self.intake.repository.atomic(flag)
        return {"text": safe, "distress": distress, "secret": safe != text, "injection": injection}

    def call(self, name: str, arguments: dict[str, Any], call_id: str) -> dict[str, Any]:
        if (
            type(arguments) is not dict
            or len(json.dumps(arguments)) > 16000
            or not call_id
            or len(call_id) > 128
        ):
            raise IntakeError(422, "validation_failed")
        digest = canonical_hash([name, arguments])
        if call_id in self.calls:
            previous_hash, result = self.calls[call_id]
            if previous_hash != digest:
                raise IntakeError(409, "idempotency_conflict")
            current_case = self.case()
            if current_case["flags"].get("distress") and name != "flag_distress":
                return {"ok": False, "reason_if_not": "distress_paused"}
            if result.get("reason_if_not") != "transcription_pending" or not self.statement_turn_id:
                return result
        if len(self.calls) >= 80:
            raise IntakeError(429, "budget_exceeded")
        case = self.case()
        if case["flags"].get("distress") and name != "flag_distress":
            return {"ok": False, "reason_if_not": "distress_paused"}
        if name == "record_facts":
            if set(arguments) != {"facts"} or type(arguments["facts"]) is not dict:
                raise IntakeError(422, "validation_failed")
            encoded = json.dumps(arguments["facts"], ensure_ascii=False)
            if scrub_credentials(encoded) != encoded:
                raise IntakeError(422, "unsafe_content_blocked")

            def record(tx: Any) -> dict[str, Any]:
                current = self.intake._case(tx, self.case_id, self.actor)
                if current["flags"].get("distress"):
                    return {"ok": False, "reason_if_not": "distress_paused"}
                turn_id = self.statement_turn_id
                turn = tx.get(f"cases/{self.case_id}/transcript/{turn_id}") if turn_id else None
                user_turns = [item for item in current["transcript"] if item.get("role") == "user"]
                if (
                    not turn
                    or turn.get("role") != "user"
                    or not user_turns
                    or user_turns[-1].get("turnId") != turn_id
                    or turn.get("turnId") != turn_id
                    or not turn.get("text")
                    or "[REDACTED" in turn["text"]
                ):
                    return {"ok": False, "reason_if_not": "transcription_pending"}
                reference = (
                    f"case:{self.case_id}:turn:{turn_id}:facts:{current['factsRevision'] + 1}"
                )
                facts = merge_facts(
                    current["facts"],
                    arguments["facts"],
                    confirmed=False,
                    now=self.intake.clock(),
                    statement_reference=reference,
                )
                if facts != current["facts"]:
                    current["facts"] = facts
                    current["factsRevision"] += 1
                    current["updatedAt"] = stamp(self.intake.clock())
                    tx.set(f"cases/{self.case_id}", current)
                    self.intake._event(tx, self.case_id, self.actor, "live.facts_recorded")
                return {
                    "ok": True,
                    "facts": current["facts"],
                    "missing_minimum": missing_minimum(current["facts"]),
                }

            result = self.intake.repository.atomic(record)
        elif name == "flag_distress":
            if set(arguments) != {"level"} or arguments["level"] not in {"concern", "urgent"}:
                raise IntakeError(422, "validation_failed")

            def flag(tx: Any) -> None:
                current = self.intake._case(tx, self.case_id, self.actor)
                current["flags"]["distress"] = True
                tx.set(f"cases/{self.case_id}", current)
                self.intake._event(tx, self.case_id, self.actor, "live.distress_flagged")

            self.intake.repository.atomic(flag)
            result = {"ok": True}
        elif name == "request_upload":
            if set(arguments) != {"kind"} or arguments["kind"] not in {
                "screenshot",
                "chat_export",
                "receipt",
                "other",
            }:
                raise IntakeError(422, "validation_failed")
            result = {"upload_prompt_shown": True, "kind": arguments["kind"]}
        elif name == "request_processing":
            if arguments or self.intake.planning is None:
                raise IntakeError(422, "validation_failed")
            missing = missing_minimum(case["facts"])
            if missing:
                result = {"queued": False, "reason_if_not": "minimum_facts_missing"}
            else:
                job = self.intake.planning.enqueue(
                    self.actor, self.case_id, self.processing_options
                )
                result = {"queued": True, "reason_if_not": None, "jobId": job["jobId"]}
        else:
            raise IntakeError(403, "forbidden")
        self.calls[call_id] = digest, result
        return result

    @property
    def first_action(self) -> str:
        return FIRST_ACTION[self.language]

    @property
    def distress_reply(self) -> str:
        return DISTRESS[self.language]
