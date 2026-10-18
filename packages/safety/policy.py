"""Pure decisions on server-constructed authorization context, never request JSON."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Decision(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


class Action(StrEnum):
    READ_EVIDENCE = "read_evidence"
    EXTRACT = "extract"
    CLASSIFY = "classify"
    PLAN = "plan"
    DRAFT = "draft"
    VERIFY = "verify"
    TRANSLATE = "translate"
    SEND = "send_packet"
    SHARE = "share_packet"
    DOWNLOAD = "download_packet"
    ACKNOWLEDGE = "acknowledge"
    REQUEST_INFO = "request_info"
    HOLD = "place_hold_simulated"
    REJECT = "reject"
    ESCALATE = "escalate"
    PUBLISH = "publish_pack"
    CONTACT_SCAMMER = "contact_scammer"
    STORE_SECRET = "store_secret"
    REAL_SUBMISSION = "real_submission"
    PROMISE_RECOVERY = "promise_recovery"
    LEGAL_CONCLUSION = "legal_conclusion"
    REVEAL_PROMPT = "reveal_prompt"


@dataclass(frozen=True)
class Actor:
    uid: str
    role: str
    org_id: str | None = None


@dataclass(frozen=True)
class Context:
    resource_id: str
    version: int
    content_hash: str
    owner_uid: str | None = None
    recipient_id: str | None = None
    recipient_org_id: str | None = None
    reviewer_org_id: str | None = None
    verified: bool = False
    simulated: bool = True


@dataclass(frozen=True)
class Approval:
    """Record loaded from a trusted server repository, not client-provided approval."""

    actor_uid: str
    action: Action
    resource_id: str
    version: int
    content_hash: str
    recipient_id: str | None
    created_at: datetime
    expires_at: datetime
    revoked: bool = False


class ActionPolicy:
    """No I/O or audit persistence. API must authenticate and load all inputs.

    check() decides eligibility; check_with_approval() checks a repository-loaded
    approval record. Neither method authenticates an Actor or trusts a request.
    """

    _automatic = frozenset(
        {
            Action.READ_EVIDENCE,
            Action.EXTRACT,
            Action.CLASSIFY,
            Action.PLAN,
            Action.DRAFT,
            Action.VERIFY,
            Action.TRANSLATE,
        }
    )
    _victim = frozenset({Action.SEND, Action.SHARE, Action.DOWNLOAD})
    _receiver = frozenset(
        {Action.ACKNOWLEDGE, Action.REQUEST_INFO, Action.HOLD, Action.REJECT, Action.ESCALATE}
    )

    @classmethod
    def check(cls, actor: Actor, action: Action | str, context: Context) -> Decision:
        if (
            not actor.uid
            or not context.resource_id
            or not context.content_hash
            or context.version < 1
        ):
            return Decision.DENY
        if action in cls._automatic:
            if actor.role == "system":
                return Decision.ALLOW
            if actor.role == "victim" and actor.uid == context.owner_uid:
                return Decision.ALLOW
            if (
                action == Action.READ_EVIDENCE
                and actor.role == "receiver"
                and actor.org_id
                and actor.org_id == context.recipient_org_id
            ):
                return Decision.ALLOW
            return Decision.DENY
        if action in cls._victim:
            if actor.role != "victim" or actor.uid != context.owner_uid:
                return Decision.DENY
            if action == Action.SEND and (
                not context.verified or not context.simulated or not context.recipient_id
            ):
                return Decision.DENY
            return Decision.REQUIRE_APPROVAL
        if action in cls._receiver:
            if (
                actor.role != "receiver"
                or not actor.org_id
                or actor.org_id != context.recipient_org_id
                or not context.simulated
            ):
                return Decision.DENY
            return Decision.REQUIRE_APPROVAL
        if action == Action.PUBLISH:
            if actor.role == "admin" or (
                actor.role == "reviewer"
                and actor.org_id
                and actor.org_id == context.reviewer_org_id
            ):
                return Decision.REQUIRE_APPROVAL
        return Decision.DENY

    @classmethod
    def check_with_approval(
        cls,
        actor: Actor,
        action: Action | str,
        context: Context,
        persisted_approval: Approval | None,
        *,
        now: datetime,
    ) -> Decision:
        decision = cls.check(actor, action, context)
        if decision != Decision.REQUIRE_APPROVAL:
            return decision
        record = persisted_approval
        if record is None:
            return decision
        dates = (now, record.created_at, record.expires_at)
        if any(date.tzinfo is None or date.utcoffset() is None for date in dates):
            return Decision.DENY
        if record.revoked or not (record.created_at <= now < record.expires_at):
            return Decision.DENY
        actual = (
            actor.uid,
            action,
            context.resource_id,
            context.version,
            context.content_hash,
            context.recipient_id,
        )
        expected = (
            record.actor_uid,
            record.action,
            record.resource_id,
            record.version,
            record.content_hash,
            record.recipient_id,
        )
        return Decision.ALLOW if actual == expected else Decision.DENY
