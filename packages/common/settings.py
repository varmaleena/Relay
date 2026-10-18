"""Fail-fast, mode-specific settings. No inferred live model IDs or credentials."""

import re
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    environment: Literal["local", "dev", "staging", "prod"] = "local"
    service: Literal["api", "live", "worker", "mcp", "a2a", "eval", "synth"] = "api"
    demo_mode: bool = True
    genai_mode: Literal["fake", "replay", "live"] = "fake"
    gcp_project_id: str = ""
    genai_project_id: str = ""
    auth_mode: Literal["firebase", "emulator"] = "firebase"
    auth_emulator_host: str = "127.0.0.1:9099"
    intake_enabled: bool = False
    planning_enabled: bool = False
    packets_enabled: bool = False
    receiver_enabled: bool = False
    sources_enabled: bool = False
    packstudio_enabled: bool = False
    uk_pack_enabled: bool = False
    linking_enabled: bool = False
    live_enabled: bool = False
    live_capabilities_verified: bool = False
    genai_live_location: str = ""
    a2a_receiver_url: str = ""
    allow_draft_pack_preview: bool = False
    deployed_demo_preview: bool = False
    storage_signing_email: str = ""
    pack_directory: str = "packs"
    intake_storage_mode: Literal["local", "gcs"] = "local"
    intake_data_directory: str = ".local/intake"
    api_base_url: str = "http://127.0.0.1:8000"
    gcp_region: str = "asia-south1"
    genai_location: str = ""
    firestore_db: str = "(default)"
    model_reasoning: str = ""
    packet_thinking_level: Literal["LOW"] | None = None
    model_fast: str = ""
    model_live: str = ""
    model_pro: str = ""
    bucket_evidence: str = ""
    bucket_exports: str = ""
    bucket_sources: str = ""
    bucket_eval: str = ""
    pubsub_topic_jobs: str = ""
    hmac_secret_name: str = ""
    allowed_fetch_domains: str = ""
    allowed_origins: str = "http://localhost:5173"
    supported_languages: str = "en,hi"
    default_language: Literal["en", "hi"] = "en"
    default_timezone: str = "Asia/Kolkata"
    urgent_minutes: int = Field(default=120, gt=0)
    high_hours: int = Field(default=72, gt=0)
    max_session_seconds: int = Field(default=600, gt=0, le=3600)
    max_model_concurrency: int = Field(default=4, gt=0, le=100)
    git_sha: str = "development"
    built_at: str = "unbuilt"

    @field_validator("gcp_project_id")
    @classmethod
    def project_format(cls, value: str) -> str:
        if value and not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", value):
            raise ValueError("invalid Google Cloud project ID")
        return value

    @field_validator("genai_project_id")
    @classmethod
    def model_project_format(cls, value: str) -> str:
        return cls.project_format(value)

    @field_validator("default_timezone")
    @classmethod
    def timezone_valid(cls, value: str) -> str:
        ZoneInfo(value)
        return value

    @field_validator("supported_languages")
    @classmethod
    def required_languages(cls, value: str) -> str:
        languages = [x.strip() for x in value.split(",")]
        if set(languages) != {"en", "hi"} or len(languages) != 2:
            raise ValueError("M0 supports exactly English and Hindi")
        return ",".join(languages)

    @field_validator("allowed_origins")
    @classmethod
    def origins_valid(cls, value: str) -> str:
        from urllib.parse import urlsplit

        for origin in value.split(","):
            parsed = urlsplit(origin.strip())
            if (
                "*" in origin
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path not in {"", "/"}
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS requires explicit origins")
        return value

    @model_validator(mode="after")
    def mode_requirements(self) -> "Settings":
        import os

        if self.auth_mode == "emulator":
            if (
                self.environment != "local"
                or not self.gcp_project_id.startswith("demo-")
                or self.auth_emulator_host not in {"127.0.0.1:9099", "localhost:9099"}
            ):
                raise ValueError(
                    "auth emulator requires local mode, demo project and loopback host"
                )
        elif os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):
            raise ValueError("emulator environment cannot be used with Firebase production auth")
        if self.intake_enabled and self.intake_storage_mode == "local":
            if self.environment != "local":
                raise ValueError("local intake storage is local-only")
        if self.intake_enabled and self.intake_storage_mode == "gcs":
            if (
                not self.bucket_evidence
                or not self.bucket_exports
                or not re.fullmatch(
                    r"[a-z][a-z0-9-]*@[a-z][a-z0-9-]*\.iam\.gserviceaccount\.com",
                    self.storage_signing_email,
                )
            ):
                raise ValueError(
                    "GCS requires evidence/export buckets and explicit signing identity"
                )
        if (
            self.environment != "local"
            and self.intake_enabled
            and not re.fullmatch(
                r"projects/[a-z][a-z0-9-]+/topics/[A-Za-z][A-Za-z0-9._~+%-]{2,254}",
                self.pubsub_topic_jobs,
            )
        ):
            raise ValueError("cloud intake requires a fully qualified job topic")
        if self.planning_enabled and not self.intake_enabled:
            raise ValueError("planning requires intake")
        if self.packets_enabled and not self.planning_enabled:
            raise ValueError("packets require planning")
        if self.receiver_enabled and not self.packets_enabled:
            raise ValueError("receiver requires packets")
        if self.packstudio_enabled and (not self.sources_enabled or not self.planning_enabled):
            raise ValueError("pack studio requires source ingestion and planning catalog")
        if self.uk_pack_enabled and not self.planning_enabled:
            raise ValueError("UK pack requires planning")
        if self.linking_enabled and (
            not self.receiver_enabled or (self.environment != "local" and not self.hmac_secret_name)
        ):
            raise ValueError("linking requires receiver and explicit private HMAC configuration")
        if self.live_enabled and (
            not self.intake_enabled
            or not self.live_capabilities_verified
            or not self.model_live
            or not self.genai_live_location
        ):
            raise ValueError("live requires intake and explicitly verified model/location")
        if self.sources_enabled and (
            not self.intake_enabled
            or not self.allowed_fetch_domains.strip()
            or (self.intake_storage_mode == "gcs" and not self.bucket_sources)
        ):
            raise ValueError("sources require intake, official domains and private cloud storage")
        if self.deployed_demo_preview and (
            self.environment != "dev"
            or not self.demo_mode
            or self.auth_mode != "firebase"
            or self.intake_storage_mode != "gcs"
        ):
            raise ValueError("deployed demo preview requires dev, Firebase auth and GCS")
        if self.allow_draft_pack_preview and not (
            self.demo_mode and (self.environment == "local" or self.deployed_demo_preview)
        ):
            raise ValueError("draft pack preview requires explicit local or deployed dev demo mode")
        if not self.demo_mode:
            raise ValueError("Relay hackathon build supports DEMO_MODE=true only")
        if self.environment != "local":
            if self.genai_mode == "fake":
                raise ValueError("fake inference is local-only")
            if any(not x.strip().startswith("https://") for x in self.allowed_origins.split(",")):
                raise ValueError("deployed CORS origins require HTTPS")
        if self.genai_mode == "live" or self.environment != "local":
            required = ["gcp_project_id", "genai_location"]
            fields_by_service = {
                "api": [
                    "bucket_evidence",
                    "bucket_exports",
                    "pubsub_topic_jobs",
                    "model_reasoning",
                ],
                "live": ["model_live", "model_fast", "pubsub_topic_jobs"],
                "worker": [
                    "model_reasoning",
                    "model_fast",
                    "bucket_evidence",
                    "bucket_sources",
                    "bucket_exports",
                    "hmac_secret_name",
                ],
                "mcp": [],
                "a2a": ["model_reasoning"],
                "eval": ["model_reasoning", "model_fast", "bucket_eval"],
                "synth": ["model_fast", "bucket_eval"],
            }
            if self.environment == "local" and self.intake_enabled:
                required += ["model_reasoning"]
            elif self.service == "worker" and self.intake_enabled:
                # Current M1–M3 worker uses image-bound sources and no entity
                # linking secret. Do not provision unused future dependencies.
                required += [
                    "model_reasoning",
                    "bucket_evidence",
                    "bucket_exports",
                    "pubsub_topic_jobs",
                ]
            else:
                required += fields_by_service[self.service]
            missing = [name for name in required if not getattr(self, name)]
            if missing:
                raise ValueError("missing required configuration: " + ", ".join(missing))
        for model in [self.model_reasoning, self.model_fast, self.model_live, self.model_pro]:
            if model and not re.fullmatch(r"gemini-3[.\w-]*", model):
                raise ValueError("model must be a verified Gemini 3.x ID")
        return self

    @property
    def origins(self) -> list[str]:
        return [x.strip().rstrip("/") for x in self.allowed_origins.split(",")]
