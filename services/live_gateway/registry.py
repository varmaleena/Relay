"""Transactional per-user leases and opaque, owner/case-bound resumptions."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from packages.common.identifiers import canonical_hash, new_id
from packages.intake.service import IntakeError, stamp
from packages.safety import Actor


class LiveSessionRegistry:
    def __init__(self, intake: Any):
        self.intake = intake
        self.repository = intake.repository

    def acquire(
        self, actor: Any, case_id: str, language: str, resume: str | None = None
    ) -> dict[str, Any]:
        now = self.intake.clock()

        def reserve(tx: Any) -> dict[str, Any]:
            case = self.intake._case(tx, case_id, actor)
            access = case.get("accessExpiresAtMs")
            if type(access) is not int or access <= int(now.timestamp() * 1000):
                raise IntakeError(403, "forbidden")
            expires = min(
                now + timedelta(seconds=600),
                datetime.fromtimestamp(access / 1000, UTC),
                datetime.fromisoformat(case["ttlAt"].replace("Z", "+00:00")),
            )
            provider_handle = None
            reconnects = 0
            if resume:
                path = "liveResumptions/" + canonical_hash(resume)
                saved = tx.get(path)
                if (
                    not saved
                    or saved["uid"] != actor.uid
                    or saved["caseId"] != case_id
                    or saved["language"] != language
                    or saved["expiresAt"] <= stamp(now)
                    or saved["reconnects"] >= 3
                ):
                    raise IntakeError(403, "forbidden")
                active_session = tx.get(f"liveSessions/{saved['sessionId']}")
                if active_session and active_session["expiresAt"] > stamp(now):
                    raise IntakeError(409, "version_conflict")
                expires = min(
                    expires,
                    datetime.fromisoformat(saved["sessionExpiresAt"].replace("Z", "+00:00")),
                )
                if expires <= now:
                    raise IntakeError(403, "forbidden")
                provider_handle, reconnects = saved["providerHandle"], saved["reconnects"] + 1
                tx.delete(path)  # one use: replay cannot fork an upstream session
                reference = path.split("/")[1]
                case["liveResumeRefs"] = [
                    item for item in case.get("liveResumeRefs", []) if item != reference
                ]
            user_path = "liveUsers/" + canonical_hash(actor.uid)
            user = tx.get(user_path) or {"sessions": []}
            active = []
            for session_id in user["sessions"]:
                record = tx.get(f"liveSessions/{session_id}")
                if record and record["expiresAt"] > stamp(now):
                    active.append(session_id)
            if len(active) >= 3:
                raise IntakeError(429, "session_limit")
            session_id = new_id("live")
            references = case.setdefault("liveSessionRefs", [])
            if len(references) >= 80:
                raise IntakeError(429, "session_limit")
            references.append(session_id)
            tx.set(f"cases/{case_id}", case)
            record = {
                "sessionId": session_id,
                "uid": actor.uid,
                "caseId": case_id,
                "language": language,
                "expiresAt": stamp(expires),
                "reconnects": reconnects,
                "providerHandle": provider_handle,
            }
            tx.set(f"liveSessions/{session_id}", record)
            tx.set(user_path, {"sessions": active + [session_id]})
            return record

        return self.repository.atomic(reserve)

    def release(self, record: dict[str, Any]) -> None:
        def remove(tx: Any) -> None:
            tx.delete(f"liveSessions/{record['sessionId']}")
            path = "liveUsers/" + canonical_hash(record["uid"])
            user = tx.get(path)
            if user:
                user["sessions"] = [sid for sid in user["sessions"] if sid != record["sessionId"]]
                if user["sessions"]:
                    tx.set(path, user)
                else:
                    tx.delete(path)
            case_path = f"cases/{record['caseId']}"
            case = tx.get(case_path)
            if case:
                case["liveSessionRefs"] = [
                    sid for sid in case.get("liveSessionRefs", []) if sid != record["sessionId"]
                ]
                tx.set(case_path, case)

        self.repository.atomic(remove)

    def resumption(self, record: dict[str, Any], provider_handle: str) -> dict[str, str]:
        if type(provider_handle) is not str or not provider_handle or len(provider_handle) > 4096:
            raise IntakeError(422, "validation_failed")
        token = secrets.token_urlsafe(32)
        expires = min(stamp(self.intake.clock() + timedelta(seconds=120)), record["expiresAt"])
        saved = {
            **record,
            "sessionExpiresAt": record["expiresAt"],
            "expiresAt": expires,
            "providerHandle": provider_handle,
        }
        reference = canonical_hash(token)

        def save(tx: Any) -> None:
            case = self.intake._case(tx, record["caseId"], Actor(record["uid"], "victim"))
            active = tx.get(f"liveSessions/{record['sessionId']}")
            if not active or active["expiresAt"] <= stamp(self.intake.clock()):
                raise IntakeError(403, "forbidden")
            references = case.setdefault("liveResumeRefs", [])
            if len(references) >= 80:
                raise IntakeError(429, "session_limit")
            references.append(reference)
            tx.set(f"cases/{record['caseId']}", case)
            tx.set("liveResumptions/" + reference, saved)

        self.repository.atomic(save)
        return {"handle": token, "expiresAt": expires}

    @staticmethod
    def cleanup_case(tx: Any, case_id: str, refs: dict[str, list[str]]) -> None:
        """Use only references indexed in the trusted case being deleted."""
        for session_id in refs.get("sessions", []):
            path = f"liveSessions/{session_id}"
            record = tx.get(path)
            if record and record["caseId"] == case_id:
                user_path = "liveUsers/" + canonical_hash(record["uid"])
                user = tx.get(user_path)
                if user:
                    user["sessions"] = [sid for sid in user["sessions"] if sid != session_id]
                    if user["sessions"]:
                        tx.set(user_path, user)
                    else:
                        tx.delete(user_path)
                tx.delete(path)
        for reference in refs.get("resumptions", []):
            path = f"liveResumptions/{reference}"
            record = tx.get(path)
            if record and record["caseId"] == case_id:
                tx.delete(path)
