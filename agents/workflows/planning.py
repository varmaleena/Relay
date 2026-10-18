"""ADK coordinates readers and deterministic rules; it has no mutation/send tools."""

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import START, FunctionNode, Workflow
from google.genai import types

from agents.classification import JurisdictionResolver
from agents.intake.clients import ModelFailure
from packages.common.identifiers import canonical_hash, new_id
from packages.packs.registry import PackRegistry
from packages.planning import compute
from packages.schemas.models import CaseFacts, Classification, EvidenceExtraction, Pack, Plan

Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def planning_stage(name: str, handler: Handler) -> FunctionNode:
    async def stage(ctx: Any) -> None:
        delta = await handler(ctx.state.to_dict())
        ctx.state.update(delta)

    return FunctionNode(func=stage, name=name)


class PlanningWorkflow:
    def __init__(
        self,
        classifier: Any,
        registry: PackRegistry,
        *,
        environment: str = "local",
        demo_mode: bool = True,
        allow_draft_preview: bool = False,
    ) -> None:
        self.classifier = classifier
        self.registry = registry
        self.environment = environment
        self.demo_mode = demo_mode
        self.allow_draft_preview = allow_draft_preview

    async def classify(self, state: dict[str, Any]) -> dict[str, Any]:
        result = await self.classifier.classify(
            facts=CaseFacts.model_validate(state["facts"]),
            evidence=[EvidenceExtraction.model_validate(item) for item in state["evidence"]],
            history=state["history"],
            now=datetime.fromisoformat(state["now"]),
            language=state["language"],
        )
        if result.degraded:
            raise ModelFailure(result.failure_code or "model_unavailable")
        return {
            "classification": result.model_dump(mode="json", by_alias=True),
            "outcome": "clarification" if result.needs_human_review else "classified",
        }

    async def resolve(self, state: dict[str, Any]) -> dict[str, Any]:
        if state["outcome"] == "clarification":
            return {}
        facts = CaseFacts.model_validate(state["facts"])
        preview = self.allow_draft_preview and state["previewDraft"]
        packs = self.registry.available(
            allow_draft_preview=preview,
            environment=self.environment,
            demo_mode=self.demo_mode,
        )
        if state.get("packVersion"):
            packs = [pack for pack in packs if pack.version == state["packVersion"]]
        country = str(facts.country.value) if facts.country and facts.country.value else None
        # Only explicit local preview selects a draft, and only after the country
        # is established by the victim. A demo override cannot bypass that check.
        trusted_country = bool(
            facts.country
            and (
                facts.country.provenance.source in {"selected", "confirmed"}
                or (
                    facts.country.provenance.source in {"statement", "victim_statement"}
                    and (facts.country.provenance.confidence or 0) >= 0.8
                )
            )
        )
        matching_drafts = [
            pack for pack in packs if pack.status == "draft" and pack.jurisdiction.code == country
        ]
        has_published = any(
            pack.status == "published" and pack.jurisdiction.code == country for pack in packs
        )
        demo_pack_id = None
        if preview and trusted_country and matching_drafts and not has_published:
            demo_pack_id = matching_drafts[0].pack_id
        resolved = JurisdictionResolver().resolve(
            packs=packs,
            facts=facts,
            allow_draft_demo=preview,
            demo_pack_id=demo_pack_id,
            environment=self.environment,
            demo_mode=self.demo_mode,
            deployed_demo_preview=self.registry.deployed_demo_preview,
        )
        result: dict[str, Any] = {
            "pack": resolved.pack.model_dump(mode="json"),
            "resolution": {
                "country": country,
                "confidence": resolved.confidence,
                "reason": resolved.reason,
                "notice": resolved.notice,
                "unverified": resolved.unverified,
            },
        }
        if resolved.needs_country_confirmation:
            classification = Classification.model_validate(state["classification"])
            classification.needs_human_review = True
            classification.clarifying_question = (
                "Please confirm your country using Change beside Country."
                if state["language"] == "en"
                else "देश के पास बदलें दबाकर कृपया अपना देश पक्का करें।"
            )
            result.update(
                classification=classification.model_dump(mode="json", by_alias=True),
                outcome="clarification",
            )
        else:
            result["outcome"] = "resolved"
        return result

    async def plan(self, state: dict[str, Any]) -> dict[str, Any]:
        if state["outcome"] == "clarification":
            return {}
        pack = Pack.model_validate(state["pack"])
        passages = self.registry.passages(pack)
        result = compute(
            pack=pack,
            facts=CaseFacts.model_validate(state["facts"]),
            classification=Classification.model_validate(state["classification"]),
            now=datetime.fromisoformat(state["now"]),
            language=state["language"],
            source_passages=passages,
        )
        result.plan_id = new_id("plan")
        result.facts_revision = state["factsRevision"]
        result.facts_hash = canonical_hash(state["facts"])
        result.pack_hash = canonical_hash(pack.model_dump(mode="json"))
        result.classification = Classification.model_validate(state["classification"])
        result.country_code = state["resolution"]["country"]
        result.resolution_reason = state["resolution"]["reason"]
        result.resolution_confidence = state["resolution"]["confidence"]
        result.generic_guidance = state["resolution"]["reason"] == "generic_fallback"
        result.draft_preview = pack.status == "draft"
        if state["resolution"]["notice"]:
            result.unverified_notices.append(
                {"code": "resolution_notice", "text": state["resolution"]["notice"]}
            )
        recipients = {item.id: item for item in pack.recipients}
        references: set[str] = set()
        for step in result.steps:
            step.recipient_name = recipients[step.recipient_id].name
            step.recipient_type = recipients[step.recipient_id].type
            step.additional_channels = [
                channel.model_copy(
                    update={
                        "verified": (
                            pack.status in {"reviewed", "published"}
                            and recipients[step.recipient_id].status == "verified"
                            and channel.verified
                        )
                    }
                )
                for channel in recipients[step.recipient_id].channels[1:]
            ]
            references.update(step.source_refs)
        sources = {item.id: item for item in pack.sources}
        from packages.schemas.models import PlanSourceCitation

        result.source_citations = [
            PlanSourceCitation(
                reference=reference,
                title=sources[reference.split(":", 1)[0]].title,
                publisher=sources[reference.split(":", 1)[0]].publisher,
                url=sources[reference.split(":", 1)[0]].url,
                passage=passages[reference][:4000],
                retrieved_at=sources[reference.split(":", 1)[0]].retrieved_at,
                snapshot_hash=sources[reference.split(":", 1)[0]].sha256,
                status="unverified",
            )
            for reference in sorted(references)
            if reference in passages and reference.split(":", 1)[0] in sources
        ]
        return {"plan": result.model_dump(mode="json", by_alias=True), "outcome": "planned"}

    async def execute(
        self,
        *,
        uid: str,
        facts: dict[str, Any],
        facts_revision: int,
        history: list[dict[str, str]],
        evidence: list[dict[str, Any]],
        now: datetime,
        language: str,
        preview_draft: bool = False,
        pack_version: str | None = None,
    ) -> dict[str, Any]:
        sessions = InMemorySessionService()
        session_id = new_id("workflow")
        await sessions.create_session(
            app_name="relay_planning",
            user_id=uid,
            session_id=session_id,
            state={
                "facts": facts,
                "factsRevision": facts_revision,
                "history": history,
                "evidence": evidence,
                "now": now.isoformat(),
                "language": language,
                "previewDraft": preview_draft,
                "packVersion": pack_version,
            },
        )
        classifier = planning_stage("ClassifierAgent", self.classify)
        resolver = planning_stage("JurisdictionResolver", self.resolve)
        planner = planning_stage("PlannerAgent", self.plan)
        workflow = Workflow(
            name="CasePlanningWorkflow",
            edges=[(START, classifier), (classifier, resolver), (resolver, planner)],
            max_concurrency=1,
            timeout=30,
        )
        runner = Runner(app_name="relay_planning", node=workflow, session_service=sessions)
        try:
            async for _ in runner.run_async(
                user_id=uid,
                session_id=session_id,
                new_message=types.Content(
                    role="user", parts=[types.Part(text="Build a draft plan.")]
                ),
            ):
                pass
            completed = await sessions.get_session(
                app_name="relay_planning", user_id=uid, session_id=session_id
            )
            if completed is None:
                raise RuntimeError("workflow_session_missing")
            # Session is ephemeral; only typed results are persisted by the service.
            result: dict[str, Any] = {
                "outcome": completed.state["outcome"],
                "classification": completed.state["classification"],
            }
            if completed.state.get("plan"):
                result["plan"] = Plan.model_validate(completed.state["plan"]).model_dump(
                    mode="json", by_alias=True
                )
            return result
        finally:
            await runner.close()
