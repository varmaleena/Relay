"""Evaluate supplied captured observations. This module never calls a model."""

from __future__ import annotations

import itertools
import random
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from eval.captures import Captures, SystemCapture
from eval.metrics import bootstrap_f1, distribution, proportion
from eval.synth import TYPOLOGIES, sha256, validate_dataset

SYSTEMS = ("relay", "baseline", "ablation_rules", "ablation_no_verifier", "ablation_no_pack")
UNMEASURED = ("deadline_correctness", "packet_faithfulness", "citation_validity", "pack_builder_f1")


def entity_set(entities) -> set[tuple[str, str, str]]:
    return {(item["type"], item["normalizedValue"], item["role"]) for item in entities}


def normalized_rows(capture: SystemCapture, cases: dict[str, Any]) -> list[dict[str, Any]]:
    if len(set(capture.caseIds)) != len(capture.caseIds) or any(
        case_id not in cases for case_id in capture.caseIds
    ):
        raise ValueError("Capture includes duplicated or unknown case IDs")
    if any(cases[case_id]["split"] != "evaluation" for case_id in capture.caseIds):
        raise ValueError("Held-out live-built-pack cases are not yet eligible for evaluation")
    observed = {}
    for attempt in capture.attempts:
        key = (attempt.caseId, attempt.repeat)
        if (
            key in observed
            or attempt.caseId not in capture.caseIds
            or attempt.repeat >= capture.repeats
        ):
            raise ValueError("Attempt is duplicated or outside the declared case/repeat plan")
        if (attempt.status == "completed") != (attempt.prediction is not None):
            raise ValueError("Only completed attempts may contain a prediction")
        if attempt.prediction and len(set(attempt.prediction.recipients)) != len(
            attempt.prediction.recipients
        ):
            raise ValueError("Recipient predictions must not contain duplicates")
        if (
            attempt.prediction
            and (
                attempt.prediction.forbiddenContent is not None
                or attempt.prediction.injectionSucceeded is not None
            )
            and not capture.behaviorScorerVersion
        ):
            raise ValueError("Behavior annotations require an identified scorer version")
        observed[key] = attempt.model_dump()
    rows = []
    for case_id in capture.caseIds:
        for repeat in range(capture.repeats):
            row = observed.get(
                (case_id, repeat),
                {
                    "caseId": case_id,
                    "repeat": repeat,
                    "status": "missing",
                    "prediction": None,
                    "latencyMs": None,
                    "costUsd": None,
                },
            )
            rows.append({**row, "case": cases[case_id]})
    return rows


def system_report(
    capture: SystemCapture, cases: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = normalized_rows(capture, cases)
    totals: Counter = Counter()
    entity_clusters: dict[str, list[int]] = {}
    confusion: dict[str, Counter] = {}
    gallery = []
    slices: dict[str, list[bool]] = {}
    for row in rows:
        gold = row["case"]["gold"]
        prediction = row["prediction"] or {}
        entities = entity_set(prediction.get("entities", []))
        expected = entity_set(gold["entities"])
        cluster = entity_clusters.setdefault(row["caseId"], [0, 0, 0])
        for index, count in enumerate(
            (len(entities & expected), len(entities - expected), len(expected - entities))
        ):
            cluster[index] += count
        typology_ok = prediction.get("typology") == gold["typology"]
        authorization_ok = prediction.get("authorizationType") == gold["authorizationType"]
        totals["typology"] += typology_ok
        totals["authorization"] += authorization_ok
        confusion.setdefault(gold["authorizationType"], Counter())[
            prediction.get("authorizationType") or "missing_or_failed"
        ] += 1
        recipients = prediction.get("recipients", [])
        required = gold["recipients"]
        totals["recipient_tp"] += len(set(recipients) & set(required))
        totals["recipient_predicted"] += len(recipients)
        totals["recipient_required"] += len(required)
        for first, second in itertools.combinations(required, 2):
            totals["order_pairs"] += 1
            totals["order_correct"] += (
                first in recipients
                and second in recipients
                and recipients.index(first) < recipients.index(second)
            )
        for field, value in gold["packetFields"].items():
            totals["fields_required"] += 1
            totals["fields_correct"] += prediction.get("packetFields", {}).get(field) == value
        if prediction.get("forbiddenContent") is not None:
            totals["forbidden_scored"] += 1
            totals["forbidden_positive"] += prediction["forbiddenContent"]
        if row["case"]["injection"]:
            totals["injection_cases"] += 1
            if prediction.get("injectionSucceeded") is not None:
                totals["injection_scored"] += 1
                totals["injection_positive"] += prediction["injectionSucceeded"]
        for dimension in ("language", "jurisdiction", "typologyScenario", "noise", "modality"):
            slices.setdefault(dimension + ":" + row["case"][dimension], []).append(authorization_ok)
        reasons = []
        if row["status"] != "completed":
            reasons.append(row["status"])
        if not typology_ok:
            reasons.append("typology_mismatch")
        if not authorization_ok:
            reasons.append("authorization_mismatch")
        if entities != expected:
            reasons.append("entity_tuple_mismatch")
        if recipients != required:
            reasons.append("recipient_or_order_mismatch")
        if reasons:
            gallery.append(
                {
                    "caseId": row["caseId"],
                    "repeat": row["repeat"],
                    "language": row["case"]["language"],
                    "reasons": reasons,
                    "failureCode": row.get("failureCode"),
                    "rawInputOrProviderTextIncluded": False,
                }
            )
    metrics = [
        proportion("typology_accuracy", totals["typology"], len(rows)),
        proportion("authorization_accuracy", totals["authorization"], len(rows)),
        bootstrap_f1([tuple(value) for value in entity_clusters.values()]),
        proportion("recipient_recall", totals["recipient_tp"], totals["recipient_required"]),
        proportion("recipient_precision", totals["recipient_tp"], totals["recipient_predicted"]),
        proportion("order_pair_accuracy", totals["order_correct"], totals["order_pairs"]),
        proportion("packet_field_correctness", totals["fields_correct"], totals["fields_required"]),
        proportion(
            "forbidden_content_rate",
            totals["forbidden_positive"],
            totals["forbidden_scored"],
            unknown=len(rows) - totals["forbidden_scored"],
        ),
        proportion(
            "injection_success_rate",
            totals["injection_positive"],
            totals["injection_scored"],
            unknown=totals["injection_cases"] - totals["injection_scored"],
        ),
    ]
    metrics += [
        {
            "metric": name,
            "status": "not_measured",
            "value": None,
            "ciLow": None,
            "ciHigh": None,
            "n": 0,
        }
        for name in UNMEASURED
    ]
    metrics += [
        distribution(
            [row[key] for row in rows if row[key] is not None],
            metric=name,
            unknown=sum(row[key] is None for row in rows),
        )
        for key, name in [("latencyMs", "latency_ms"), ("costUsd", "cost_usd")]
    ]
    return {
        "system": capture.system,
        "status": "measured_captures",
        "executionMode": capture.executionMode,
        "modelId": capture.modelId,
        "promptVersion": capture.promptVersion,
        "configHash": capture.configHash,
        "budgetMs": capture.budgetMs,
        "repeats": capture.repeats,
        "n": len(rows),
        "nCases": len(capture.caseIds),
        "observedAttempts": len(capture.attempts),
        "outcomes": dict(Counter(row["status"] for row in rows)),
        "behaviorScorerVersion": capture.behaviorScorerVersion,
        "metrics": metrics,
        "authorizationConfusion": {key: dict(value) for key, value in confusion.items()},
        "slices": [
            proportion("authorization_accuracy", sum(values), len(values), slice=key)
            for key, values in sorted(slices.items())
        ],
        "failureGallery": gallery,
    }, rows


def safe_pair_prediction(prediction):
    prediction = prediction or {}
    typology = prediction.get("typology")
    return {
        "typology": typology if typology in (*TYPOLOGIES, "other") else "unknown_label",
        "authorizationType": prediction.get("authorizationType"),
        "recipients": [
            item
            if item in {"bank", "cyber", "payment-app", "police", "report-fraud", "ombudsman"}
            else "unrecognized_recipient"
            for item in prediction.get("recipients", [])
        ],
    }


def paired_report(first, second, rows_first, rows_second) -> dict[str, Any]:
    left = {(row["caseId"], row["repeat"]): row for row in rows_first}
    right = {(row["caseId"], row["repeat"]): row for row in rows_second}
    matching = sorted(set(left) & set(right))
    fair = (
        set(first.caseIds) == set(second.caseIds)
        and first.repeats == second.repeats
        and first.budgetMs == second.budgetMs
        and first.modelId == second.modelId
        and first.executionMode == second.executionMode
    )
    differences: dict[str, list[float]] = {}
    for key in matching:
        expected = left[key]["case"]["gold"]["authorizationType"]
        a = (left[key]["prediction"] or {}).get("authorizationType") == expected
        b = (right[key]["prediction"] or {}).get("authorizationType") == expected
        differences.setdefault(key[0], []).append(float(a) - float(b))
    values = [sum(items) / len(items) for items in differences.values()]
    rng = random.Random(20261018)
    draws = (
        sorted(sum(rng.choices(values, k=len(values))) / len(values) for _ in range(1000))
        if values
        else []
    )
    selected = random.Random(20261018).sample(matching, min(20, len(matching)))
    return {
        "systems": [first.system, second.system],
        "fairnessChecksPassed": fair,
        "comparisonClaimAllowed": fair
        and first.repeats >= 3
        and all(row["status"] != "missing" for row in rows_first + rows_second),
        "n": len(matching),
        "nCases": len(values),
        "authorizationAccuracyDifference": {
            "value": sum(values) / len(values) if values else None,
            "ciLow": draws[25] if draws else None,
            "ciHigh": draws[974] if draws else None,
            "ciMethod": "paired_case_cluster_bootstrap95" if draws else None,
        },
        "samplePairs": [
            {
                "caseId": key[0],
                "repeat": key[1],
                "left": safe_pair_prediction(left[key]["prediction"]),
                "right": safe_pair_prediction(right[key]["prediction"]),
            }
            for key in selected
        ],
    }


def evaluate(
    dataset: dict[str, Any], captures: Captures, *, commit_sha: str = "unknown"
) -> dict[str, Any]:
    validate_dataset(dataset)
    if captures.datasetSha256 != dataset["datasetSha256"]:
        raise ValueError("Capture dataset hash does not match")
    if len({capture.system for capture in captures.systems}) != len(captures.systems):
        raise ValueError("System captures must be unique")
    cases = {case["caseId"]: case for case in dataset["cases"]}
    reports: dict[str, dict[str, Any]] = {}
    rows: dict[str, list[dict[str, Any]]] = {}
    for capture in captures.systems:
        reports[capture.system], rows[capture.system] = system_report(capture, cases)
    pairs = [
        paired_report(first, second, rows[first.system], rows[second.system])
        for first, second in itertools.combinations(captures.systems, 2)
    ]
    return {
        "reportVersion": "captured-evaluation.v1",
        "synthetic": True,
        "datasetVersion": dataset["datasetVersion"],
        "datasetSha256": dataset["datasetSha256"],
        "captureSha256": sha256(captures.model_dump()),
        "createdAt": datetime.now(UTC).isoformat(),
        "commitSha": commit_sha,
        "systems": [
            reports.get(name, {"system": name, "status": "not_measured", "n": 0, "metrics": []})
            for name in SYSTEMS + (("offline_fixture",) if "offline_fixture" in reports else ())
        ],
        "pairedComparisons": pairs,
        "limitations": [
            (
                "Synthetic template data, not human plausibility reviewed or representative "
                "prevalence."
            ),
            (
                "Draft-pack recipient gold is an engineering expectation, not independently "
                "reviewed regulatory truth."
            ),
            "Unobserved planned attempts remain failures for accuracy/F1/recall/completeness.",
            (
                "Unknown behavior annotations, latency and usage remain unknown; known-subset "
                "values are not full-run totals."
            ),
            (
                "Wilson intervals describe scored units; repeated attempts/fields are correlated "
                "and do not establish independent population coverage."
            ),
            (
                "F1 and paired differences resample whole cases; baseline fairness needs same "
                "cases/model/budget and at least three repeats."
            ),
            (
                "Deadline, faithfulness, citation and Pack Builder results require separate actual "
                "reviewed annotations."
            ),
        ],
    }
