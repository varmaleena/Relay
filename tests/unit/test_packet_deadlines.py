"""Timing fixtures are synthetic and never become shipped pack guidance."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from packages.intake.repository import MemoryRepository
from packages.packets.deadlines import check_case_deadlines


def fixture(status="published"):
    repository = MemoryRepository()
    now = datetime(2026, 10, 15, 12, tzinfo=UTC)
    plan = {
        "planId": "synthetic-plan",
        "packStatus": status,
        "steps": [
            {
                "recipientId": "synthetic-bank",
                "deadline": {
                    "ruleId": "synthetic-only",
                    "dueAt": (now + timedelta(minutes=30)).isoformat(),
                },
            }
        ],
    }
    case = {"victimUid": "synthetic", "caseId": "synthetic-case", "plan": plan}
    repository.set("cases/synthetic-case", case)
    notices = []

    def notify(tx, current, packet_id, kind, text):
        notices.append(kind)
        current.setdefault("notificationIds", []).append(kind)

    service = SimpleNamespace(
        repository=repository,
        _current_plan=lambda *_: plan,
        intake=SimpleNamespace(
            clock=lambda: now, _case=lambda tx, *_: tx.get("cases/synthetic-case")
        ),
        _notify=notify,
    )
    return service, plan, notices


def test_draft_or_missing_numeric_date_never_gets_a_deadline_notification():
    service, plan, notices = fixture("draft")
    assert check_case_deadlines(service, "synthetic-case") == 0
    plan["packStatus"] = "published"
    plan["steps"][0]["deadline"]["dueAt"] = None
    assert check_case_deadlines(service, "synthetic-case") == 0
    assert not notices


def test_sourced_numeric_reminder_is_idempotent_and_rechecks_current_plan():
    service, plan, notices = fixture()
    assert check_case_deadlines(service, "synthetic-case") == 1
    assert check_case_deadlines(service, "synthetic-case") == 0
    assert notices == ["deadline.due_soon"]
    plan["planId"] = "other-plan"
    assert check_case_deadlines(service, "synthetic-case") == 0
