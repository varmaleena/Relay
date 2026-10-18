"""Allowlisted immutable evaluator self-test, never a live Relay score."""

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from packages.intake.service import IntakeError
from packages.safety import Actor

from .models import EvalCaptureReport, EvalMetric, EvalSystem

RUN_ID = "offline-fixture-v1"
REPORT_PATH = "eval/reports/offline-fixture-v1/report.json"
REPORT_SHA256 = "3e43cf382c60e3d2dbfcadefe466676ac78f155a8e3e84fecfcf1e9634dbc798"
PRODUCT_SYSTEMS = {
    "relay",
    "baseline",
    "ablation_rules",
    "ablation_no_verifier",
    "ablation_no_pack",
}
REASONS = {
    "missing",
    "failed",
    "timeout",
    "typology_mismatch",
    "authorization_mismatch",
    "entity_tuple_mismatch",
    "recipient_or_order_mismatch",
    "incomplete_packet",
    "forbidden_content",
    "injection_succeeded",
}


class EvaluationService:
    def __init__(self, root: Path, *, public_eval: bool = False):
        if type(public_eval) is not bool:
            raise ValueError("public_eval_requires_boolean")
        self.root, self.public_eval = root.resolve(), public_eval

    @staticmethod
    def reviewer(actor):
        if not isinstance(actor, Actor) or not actor.uid:
            raise IntakeError(401, "unauthenticated")
        if actor.role not in {"reviewer", "admin"}:
            raise IntakeError(403, "forbidden")

    def _load(self, run_id):
        if run_id != RUN_ID:
            raise IntakeError(404, "not_found")
        try:
            path = self.root / REPORT_PATH
            if not path.resolve().is_relative_to(self.root) or not path.is_file():
                raise ValueError()
            for parent in (path, *path.parents):
                if parent == self.root:
                    break
                if parent.is_symlink() or parent.is_junction():
                    raise ValueError()
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError()
            with path.open("rb") as saved:
                content = saved.read(2 * 1024 * 1024 + 1)
            if len(content) > 2 * 1024 * 1024:
                raise ValueError()
            if hashlib.sha256(content).hexdigest() != REPORT_SHA256:
                raise ValueError()
            raw = json.loads(content)
            if raw["reportVersion"] != "captured-evaluation.v1" or raw["synthetic"] is not True:
                raise ValueError()
            if len(raw["systems"]) != 6 or {
                s["system"] for s in raw["systems"]
            } != PRODUCT_SYSTEMS | {"offline_fixture"}:
                raise ValueError()
            for system in raw["systems"]:
                if system["system"] in PRODUCT_SYSTEMS and (
                    system["status"] != "not_measured" or system["n"] != 0 or system["metrics"]
                ):
                    raise ValueError()
            fixture = next(s for s in raw["systems"] if s["system"] == "offline_fixture")
            if (
                fixture["executionMode"] != "captured_offline"
                or fixture["status"] != "measured_captures"
            ):
                raise ValueError()
            datetime.fromisoformat(raw["createdAt"])
            return raw
        except Exception:
            raise IntakeError(503, "evaluation_artifact_unavailable") from None

    @staticmethod
    def _metric(raw):
        keys = {
            "metric",
            "slice",
            "value",
            "ciLow",
            "ciHigh",
            "n",
            "status",
            "ciMethod",
            "unknown",
            "nCases",
        }
        return EvalMetric.model_validate({key: value for key, value in raw.items() if key in keys})

    def report(self, actor, run_id):
        if not self.public_eval:
            self.reviewer(actor)
        raw = self._load(run_id)
        systems = []
        metrics = []
        for item in raw["systems"]:
            keys = {
                "system",
                "status",
                "executionMode",
                "modelId",
                "promptVersion",
                "configHash",
                "n",
                "nCases",
                "repeats",
                "observedAttempts",
            }
            current = EvalSystem.model_validate(
                {
                    **{key: value for key, value in item.items() if key in keys},
                    "metrics": [self._metric(metric) for metric in item["metrics"]],
                    "slices": [self._metric(metric) for metric in item.get("slices", [])],
                }
            )
            systems.append(current)
            for metric in [*current.metrics, *current.slices]:
                metrics.append(
                    {
                        "system": current.system,
                        "metric": metric.metric,
                        "slice": metric.slice,
                        "value": metric.value,
                        "ciLow": metric.ci_low,
                        "ciHigh": metric.ci_high,
                        "n": metric.n,
                    }
                )
        rich = EvalCaptureReport(
            report_version=raw["reportVersion"],
            synthetic=True,
            execution_mode="offline_fixture",
            dataset_sha256=raw["datasetSha256"],
            capture_sha256=raw["captureSha256"],
            report_sha256=REPORT_SHA256,
            commit_sha=raw["commitSha"],
            systems=systems,
            limitations=raw["limitations"],
        )
        fixture = next(s for s in systems if s.system == "offline_fixture")
        return {
            "runId": RUN_ID,
            "executionMode": "offline_fixture",
            "datasetVersion": raw["datasetVersion"],
            "n": fixture.n,
            "date": raw["createdAt"],
            "systems": [s.system for s in systems],
            "metrics": metrics,
            "packBuilder": {"status": "not_measured", "n": 0},
            "redteam": {"status": "fixture_only_not_product_evaluation"},
            "latency": {"status": "not_measured", "n": 0},
            "costPerCase": {"status": "not_measured", "n": 0},
            "captureReport": rich.model_dump(mode="json", by_alias=True),
        }

    def runs(self, actor, *, limit=20, cursor=None):
        self.reviewer(actor)
        self._pagination(limit, cursor)
        raw = self._load(RUN_ID)
        fixture = next(s for s in raw["systems"] if s["system"] == "offline_fixture")
        items = (
            []
            if int(cursor or "0") >= 1
            else [
                {
                    "runId": RUN_ID,
                    "datasetVersion": raw["datasetVersion"],
                    "n": fixture["n"],
                    "startedAt": raw["createdAt"],
                    "finishedAt": raw["createdAt"],
                }
            ]
        )
        return {"items": items, "nextCursor": None}

    @staticmethod
    def _pagination(limit, cursor):
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or (cursor is not None and not re.fullmatch(r"[0-9]{1,6}", cursor))
        ):
            raise IntakeError(422, "validation_failed")

    def failures(
        self, actor, run_id, *, system=None, metric=None, slice=None, limit=20, cursor=None
    ):
        self.reviewer(actor)
        self._pagination(limit, cursor)
        raw = self._load(run_id)
        if system is not None and system not in PRODUCT_SYSTEMS | {"offline_fixture"}:
            raise IntakeError(422, "validation_failed")
        if metric is not None and metric not in {
            m["metric"] for s in raw["systems"] for m in s["metrics"]
        }:
            raise IntakeError(422, "validation_failed")
        if slice is not None and not re.fullmatch(r"language:(?:en|hi|hinglish)", slice):
            raise IntakeError(422, "validation_failed")
        items = []
        if system in {None, "offline_fixture"}:
            fixture = next(s for s in raw["systems"] if s["system"] == "offline_fixture")
            metric_reasons = {
                "typology_accuracy": "typology_mismatch",
                "authorization_accuracy": "authorization_mismatch",
                "entity_f1": "entity_tuple_mismatch",
                "recipient_recall": "recipient_or_order_mismatch",
            }
            for value in fixture.get("failureGallery", []):
                if (
                    not re.fullmatch(r"SYN-EVAL-[0-9]{5}", value["caseId"])
                    or value.get("rawInputOrProviderTextIncluded") is not False
                    or not set(value["reasons"]) <= REASONS
                ):
                    raise IntakeError(503, "evaluation_artifact_unavailable")
                if slice and value["language"] != slice.split(":")[1]:
                    continue
                if metric and metric_reasons.get(metric) not in value["reasons"]:
                    continue
                items.append(
                    {
                        "caseId": value["caseId"],
                        "inputRef": "synthetic_fixture_input_withheld",
                        "expected": None,
                        "actual": None,
                        "note": "Offline evaluator fixture; " + ", ".join(value["reasons"]),
                    }
                )
        start = int(cursor or "0")
        selected = deepcopy(items[start : start + limit])
        return {
            "items": selected,
            "nextCursor": str(start + limit) if start + limit < len(items) else None,
        }

    def create(self, actor, body):
        self.reviewer(actor)
        if actor.role != "admin":
            raise IntakeError(403, "forbidden")
        raise IntakeError(501, "evaluation_executor_not_configured")
