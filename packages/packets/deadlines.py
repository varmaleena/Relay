"""Idempotent in-app deadline notices; no external send or invented due dates."""

from datetime import datetime, timedelta
from typing import Any

from packages.intake.service import IntakeError
from packages.safety import Actor


def check_case_deadlines(service: Any, case_id: str) -> int:
    candidate = service.repository.get(f"cases/{case_id}")
    if not candidate:
        return 0
    actor = Actor(candidate["victimUid"], "victim")
    try:
        plan = service._current_plan(actor, case_id)
    except IntakeError:
        return 0
    # Unreviewed preview data never authorizes a regulatory countdown.
    if plan["packStatus"] != "published":
        return 0

    def notify(tx: Any) -> int:
        case = service.intake._case(tx, case_id, actor)
        if not case.get("plan") or case["plan"]["planId"] != plan["planId"]:
            return 0
        emitted = 0
        for step in plan["steps"]:
            deadline = step.get("deadline")
            if not deadline or not deadline.get("dueAt"):
                continue
            due = datetime.fromisoformat(deadline["dueAt"].replace("Z", "+00:00"))
            now = service.intake.clock()
            state = (
                "overdue" if due <= now else "due_soon" if due - now <= timedelta(hours=1) else None
            )
            if state is None:
                continue
            key = f"{plan['planId']}:{step['recipientId']}:{deadline['ruleId']}:{state}"
            if key in case.setdefault("deadlineNoticeKeys", []):
                continue
            packet_id = next(
                (
                    item
                    for item in case.get("packetIds", [])
                    if (
                        (packet := tx.get(f"cases/{case_id}/packets/{item}"))
                        and packet["recipientId"] == step["recipientId"]
                        and packet["planId"] == plan["planId"]
                    )
                ),
                "",
            )
            service._notify(
                tx,
                case,
                packet_id,
                f"deadline.{state}",
                "A sourced timing reminder needs your attention. Review the plan.",
            )
            case["deadlineNoticeKeys"].append(key)
            emitted += 1
        tx.set(f"cases/{case_id}", case)
        return emitted

    return service.repository.atomic(notify)
