"""Public report projection excludes captures, raw facts and provider text."""

from typing import Annotated, Literal

from pydantic import Field

from packages.schemas.models import Model

SystemName = Literal[
    "relay",
    "baseline",
    "ablation_rules",
    "ablation_no_verifier",
    "ablation_no_pack",
    "offline_fixture",
]
Finite = Annotated[float, Field(allow_inf_nan=False)]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]


class EvalMetric(Model):
    metric: Identifier
    slice: str = Field(default="all", max_length=128)
    value: Finite | None
    ci_low: Finite | None
    ci_high: Finite | None
    n: int = Field(ge=0, le=10000000)
    status: Literal["measured", "not_measured", "partial"]
    ci_method: str | None = Field(default=None, max_length=128)
    unknown: int | None = Field(default=None, ge=0, le=10000000)
    n_cases: int | None = Field(default=None, ge=0, le=10000)


class EvalSystem(Model):
    system: SystemName
    status: Literal["measured_captures", "not_measured"]
    execution_mode: Literal["captured_offline"] | None = None
    model_id: str | None = Field(default=None, max_length=128)
    prompt_version: str | None = Field(default=None, max_length=128)
    config_hash: Digest | None = None
    n: int = Field(ge=0, le=100000)
    n_cases: int | None = Field(default=None, ge=0, le=10000)
    repeats: int | None = Field(default=None, ge=1, le=10)
    observed_attempts: int | None = Field(default=None, ge=0, le=100000)
    metrics: list[EvalMetric] = Field(max_length=100)
    slices: list[EvalMetric] = Field(default_factory=list, max_length=1000)


class EvalCaptureReport(Model):
    report_version: Literal["captured-evaluation.v1"]
    synthetic: Literal[True]
    execution_mode: Literal["offline_fixture"]
    dataset_sha256: Digest
    capture_sha256: Digest
    report_sha256: Digest
    commit_sha: str = Field(min_length=1, max_length=200)
    systems: list[EvalSystem] = Field(min_length=6, max_length=6)
    limitations: list[str] = Field(min_length=1, max_length=30)
