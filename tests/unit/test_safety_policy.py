from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from packages.safety import Action, ActionPolicy, Actor, Approval, Context, Decision

NOW = datetime(2026, 10, 13, tzinfo=UTC)
CONTEXT = Context(
    "packet-1",
    2,
    "sha256-current",
    owner_uid="victim-1",
    recipient_id="bank",
    recipient_org_id="org-bank",
    verified=True,
)
VICTIM = Actor("victim-1", "victim")


def approval() -> Approval:
    return Approval(
        VICTIM.uid,
        Action.SEND,
        CONTEXT.resource_id,
        CONTEXT.version,
        CONTEXT.content_hash,
        CONTEXT.recipient_id,
        NOW - timedelta(minutes=1),
        NOW + timedelta(minutes=5),
    )


@pytest.mark.parametrize("role", ["admin", "receiver", "reviewer", "system", "unknown"])
def test_only_owner_victim_can_send(role):
    assert (
        ActionPolicy.check(Actor("victim-1", role, "org-bank"), Action.SEND, CONTEXT)
        == Decision.DENY
    )


def test_approval_is_required_and_bound():
    assert ActionPolicy.check(VICTIM, Action.SEND, CONTEXT) == Decision.REQUIRE_APPROVAL
    assert (
        ActionPolicy.check_with_approval(VICTIM, Action.SEND, CONTEXT, None, now=NOW)
        == Decision.REQUIRE_APPROVAL
    )
    assert (
        ActionPolicy.check_with_approval(VICTIM, Action.SEND, CONTEXT, approval(), now=NOW)
        == Decision.ALLOW
    )


@pytest.mark.parametrize(
    "change",
    [
        {"version": 3},
        {"content_hash": "edited"},
        {"recipient_id": "other"},
        {"resource_id": "other"},
        {"revoked": True},
        {"actor_uid": "other"},
        {"action": Action.SHARE},
        {"expires_at": NOW},
        {"created_at": NOW + timedelta(seconds=1)},
        {"expires_at": NOW.replace(tzinfo=None)},
    ],
)
def test_invalid_approval_denied(change):
    assert (
        ActionPolicy.check_with_approval(
            VICTIM, Action.SEND, CONTEXT, replace(approval(), **change), now=NOW
        )
        == Decision.DENY
    )


@pytest.mark.parametrize(
    "change",
    [
        {"owner_uid": "other"},
        {"verified": False},
        {"simulated": False},
        {"recipient_id": None},
        {"content_hash": ""},
        {"version": 0},
    ],
)
def test_ineligible_send(change):
    assert ActionPolicy.check(VICTIM, Action.SEND, replace(CONTEXT, **change)) == Decision.DENY


@pytest.mark.parametrize("action", list(ActionPolicy._receiver))
def test_receiver_scope_and_no_admin_override(action):
    assert (
        ActionPolicy.check(Actor("staff", "receiver", "org-bank"), action, CONTEXT)
        == Decision.REQUIRE_APPROVAL
    )
    assert (
        ActionPolicy.check(Actor("staff", "receiver", "other-org"), action, CONTEXT)
        == Decision.DENY
    )
    assert ActionPolicy.check(Actor("staff", "admin", "org-bank"), action, CONTEXT) == Decision.DENY


@pytest.mark.parametrize(
    "action",
    [
        Action.CONTACT_SCAMMER,
        Action.STORE_SECRET,
        Action.REAL_SUBMISSION,
        Action.PROMISE_RECOVERY,
        Action.LEGAL_CONCLUSION,
        Action.REVEAL_PROMPT,
        "unknown",
    ],
)
def test_forbidden_denied_even_for_admin(action):
    assert ActionPolicy.check(Actor("admin", "admin"), action, CONTEXT) == Decision.DENY


def test_auto_scope_and_publish_scope():
    assert ActionPolicy.check(Actor("worker", "system"), Action.EXTRACT, CONTEXT) == Decision.ALLOW
    assert ActionPolicy.check(Actor("other", "victim"), Action.EXTRACT, CONTEXT) == Decision.DENY
    assert (
        ActionPolicy.check(Actor("staff", "receiver", "org-bank"), Action.READ_EVIDENCE, CONTEXT)
        == Decision.ALLOW
    )
    assert (
        ActionPolicy.check(Actor("staff", "receiver", "org-bank"), Action.DRAFT, CONTEXT)
        == Decision.DENY
    )
    pack = replace(CONTEXT, reviewer_org_id="review-org")
    assert (
        ActionPolicy.check(Actor("r", "reviewer", "review-org"), Action.PUBLISH, pack)
        == Decision.REQUIRE_APPROVAL
    )
    assert (
        ActionPolicy.check(Actor("r", "reviewer", "other"), Action.PUBLISH, pack) == Decision.DENY
    )
    assert (
        ActionPolicy.check(Actor("a", "admin"), Action.PUBLISH, pack) == Decision.REQUIRE_APPROVAL
    )
