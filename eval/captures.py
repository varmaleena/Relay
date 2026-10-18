"""Strict normalized capture format. Adapters must preserve provider failures."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Entity(Strict):
    type: Annotated[str, Field(min_length=1, max_length=64)]
    normalizedValue: Annotated[str, Field(min_length=1, max_length=512)]
    role: Literal["victim", "scammer", "merchant", "unknown"]


class Prediction(Strict):
    entities: list[Entity] = Field(default_factory=list, max_length=100)
    typology: Annotated[str, Field(max_length=64)] | None = None
    authorizationType: (
        Literal["authorized_manipulated", "unauthorized_access", "card_unauthorized", "unclear"]
        | None
    ) = None
    recipients: list[Annotated[str, Field(min_length=1, max_length=128)]] = Field(
        default_factory=list, max_length=30
    )
    packetFields: dict[str, Annotated[str, Field(max_length=1000)]] = Field(
        default_factory=dict, max_length=100
    )
    forbiddenContent: bool | None = None
    injectionSucceeded: bool | None = None


class Attempt(Strict):
    caseId: Annotated[str, Field(pattern=r"^SYN-EVAL-[0-9]{5}$")]
    repeat: Annotated[int, Field(ge=0, le=9)]
    status: Literal["completed", "failed", "timeout"]
    prediction: Prediction | None = None
    latencyMs: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    costUsd: Annotated[float, Field(ge=0, allow_inf_nan=False)] | None = None
    failureCode: (
        Literal["provider_timeout", "provider_error", "schema_invalid", "safety_blocked", "unknown"]
        | None
    ) = None


class SystemCapture(Strict):
    system: Literal[
        "relay",
        "baseline",
        "ablation_rules",
        "ablation_no_verifier",
        "ablation_no_pack",
        "offline_fixture",
    ]
    executionMode: Literal["captured_live", "captured_offline"]
    modelId: Annotated[str, Field(min_length=1, max_length=128)]
    promptVersion: Annotated[str, Field(min_length=1, max_length=128)]
    configHash: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    budgetMs: Annotated[int, Field(ge=1, le=3600000)]
    repeats: Annotated[int, Field(ge=1, le=10)]
    caseIds: list[Annotated[str, Field(pattern=r"^SYN-EVAL-[0-9]{5}$")]] = Field(
        min_length=1, max_length=10000
    )
    attempts: list[Attempt] = Field(max_length=100000)
    behaviorScorerVersion: Annotated[str, Field(min_length=1, max_length=128)] | None = None


class Captures(Strict):
    datasetSha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    systems: list[SystemCapture] = Field(min_length=1, max_length=6)
