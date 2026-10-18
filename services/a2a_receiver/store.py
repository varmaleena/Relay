"""Repository-backed SDK task storage and immutable addressed handoffs."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

from a2a.server.context import ServerCallContext
from a2a.server.tasks import TaskStore
from a2a.types import Artifact, Message, Part, Role, Task, TaskState, TaskStatus
from a2a.utils.errors import InvalidParamsError, TaskNotFoundError, UnsupportedOperationError
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Struct, Value
from pydantic import Field, ValidationError

from packages.common.identifiers import canonical_hash, new_id
from packages.intake.service import IntakeError, stamp
from packages.safety import Actor
from packages.schemas import Model


class HandoffReference(Model):
    org_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    case_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    packet_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,128}$")
    packet_version: int = Field(ge=1, le=10000)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


def task_identifier(scope: str, reference: HandoffReference, message_id: str) -> str:
    return "a2a_" + canonical_hash(
        {"scope": scope, "reference": reference.model_dump(), "messageId": message_id}
    )


def data_part(data: dict[str, Any]) -> Part:
    value = Struct()
    value.update(data)
    return Part(data=Value(struct_value=value), media_type="application/json")


class RepositoryTaskStore(TaskStore):
    """Only registered handoffs can be persisted; access rechecks projection expiry."""

    def __init__(self, repository: Any, receiver: Any, *, scope: str, allowed_orgs: set[str]):
        if (
            not scope
            or not allowed_orgs
            or not allowed_orgs.issubset(set(receiver.recipient_orgs.values()))
        ):
            raise ValueError("Explicit trusted caller scope and organization map are required")
        self.repository, self.receiver = repository, receiver
        self.scope, self.allowed_orgs = scope, frozenset(allowed_orgs)

    def _load(self, tx: Any, reference: HandoffReference):
        if reference.org_id not in self.allowed_orgs:
            raise TaskNotFoundError("Handoff not found")
        # This internal actor is only used by read methods; no decision API is exposed here.
        actor = Actor("a2a-read-only", "receiver", reference.org_id)
        try:
            projection, _, _, _ = self.receiver._load(
                tx, actor, reference.case_id, reference.packet_id
            )
        except IntakeError:
            raise TaskNotFoundError("Handoff not found") from None
        packet = projection["packet"]
        if (
            packet["version"] != reference.packet_version
            or packet["contentHash"] != reference.content_hash
            or packet.get("stale")
            or packet["status"] not in {"SENT", "ACKNOWLEDGED", "NEEDS_INFO", "ACTIONED"}
            or packet.get("verification", {}).get("passed") is not True
        ):
            raise TaskNotFoundError("Handoff not current")
        return actor, projection

    def _record(self, tx: Any, task_id: str):
        if not re.fullmatch(r"a2a_[a-f0-9]{64}", task_id):
            raise TaskNotFoundError("Handoff not found")
        record = tx.get("a2aTasks/" + task_id)
        if not record or record["scope"] != self.scope:
            raise TaskNotFoundError("Handoff not found")
        reference = HandoffReference.model_validate(record["reference"])
        self._load(tx, reference)
        return record, reference

    async def get(self, task_id: str, context: ServerCallContext) -> Task | None:
        record, _ = self.repository.atomic(lambda tx: self._record(tx, task_id))
        return ParseDict(record["task"], Task())

    async def save(self, task: Task, context: ServerCallContext) -> None:
        def write(tx):
            record, _ = self._record(tx, task.id)
            if record.get("state") == "done":
                if record["task"] != MessageToDict(task):
                    raise InvalidParamsError("Completed handoff is immutable")
                return
            raise UnsupportedOperationError("Use the guarded handoff dispatcher")

        self.repository.atomic(write)

    async def list(self, params, context):
        raise UnsupportedOperationError("Task enumeration is unavailable")

    async def delete(self, task_id, context):
        raise UnsupportedOperationError("Deletion is handled by case retention")

    async def send(self, message: Message) -> Task:
        if (
            message.role != Role.ROLE_USER
            or not message.message_id
            or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", message.message_id)
            or message.metadata
            or message.extensions
            or message.reference_task_ids
            or message.task_id
            or message.context_id
            or len(message.parts) != 1
            or message.parts[0].WhichOneof("content") != "data"
        ):
            raise InvalidParamsError("Expected one immutable handoff reference")
        try:
            reference = HandoffReference.model_validate(MessageToDict(message.parts[0].data))
        except ValidationError:
            raise InvalidParamsError("Invalid handoff reference") from None
        task_id = task_identifier(self.scope, reference, message.message_id)
        message_key = canonical_hash(
            {"scope": self.scope, "org": reference.org_id, "messageId": message.message_id}
        )
        request_hash = canonical_hash(reference.model_dump())
        token = new_id("handoff")

        def reserve(tx):
            _, projection = self._load(tx, reference)
            mapping = tx.get("a2aMessages/" + message_key)
            if mapping and mapping["requestHash"] != request_hash:
                raise InvalidParamsError("Message identifier was already used")
            previous = tx.get("a2aTasks/" + task_id)
            if previous and (
                previous["state"] == "done" or previous["leaseUntil"] > stamp(self.receiver.clock())
            ):
                return previous, False
            if previous and previous["attempts"] >= 3:
                raise InvalidParamsError("Handoff attempt budget exhausted")
            task = Task(
                id=task_id,
                context_id=task_id,
                status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
            )
            record = {
                "scope": self.scope,
                "reference": reference.model_dump(by_alias=True),
                "messageKey": message_key,
                "requestHash": request_hash,
                "task": MessageToDict(task),
                "state": "working",
                "claimToken": token,
                "attempts": (previous or {}).get("attempts", 0) + 1,
                "leaseUntil": stamp(self.receiver.clock() + timedelta(seconds=35)),
                "accessExpiresAtMs": projection["accessExpiresAtMs"],
            }
            tx.set("a2aMessages/" + message_key, {"taskId": task_id, "requestHash": request_hash})
            tx.set("a2aTasks/" + task_id, record)
            return record, True

        record, claimed = self.repository.atomic(reserve)
        if not claimed:
            return ParseDict(record["task"], Task())
        actor, _ = self._load(self.repository, reference)
        dossier = await self.receiver.get_case(actor, reference.case_id, reference.packet_id)
        missing = dossier["brief"]["missingItems"]
        artifact = {
            "simulated": True,
            "transportStatus": "needs_info" if missing else "received",
            "humanAcknowledged": False,
            "briefStatus": dossier["briefStatus"],
            "receiverBrief": dossier["brief"],
            "message": "Simulated agent handoff; a human decision is still required.",
        }
        task = Task(
            id=task_id,
            context_id=task_id,
            status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED),
            artifacts=[
                Artifact(
                    artifact_id="receiver-handoff",
                    name="Simulated handoff",
                    parts=[data_part(artifact)],
                )
            ],
        )

        def finish(tx):
            current, _ = self._record(tx, task_id)
            if current.get("claimToken") != token:
                raise InvalidParamsError("Handoff claim changed")
            current.update(task=MessageToDict(task), state="done", leaseUntil="")
            tx.set("a2aTasks/" + task_id, current)

        self.repository.atomic(finish)
        return task


def cleanup_case(tx: Any, case_id: str, refs: list[dict[str, str]]) -> None:
    """Known references only; no arbitrary query or caller-selected deletion."""
    for ref in refs:
        task_id = ref["taskId"]
        if not re.fullmatch(r"a2a_[a-f0-9]{64}", task_id):
            raise ValueError("Invalid task reference")
        record = tx.get("a2aTasks/" + task_id)
        if record:
            if record["reference"]["caseId"] != case_id:
                raise ValueError("Case handoff mismatch")
            tx.delete("a2aMessages/" + record["messageKey"])
            tx.delete("a2aTasks/" + task_id)
