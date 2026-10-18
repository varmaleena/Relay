"""Offline evaluation integrity, failure denominators and confidence interval checks."""

from collections import Counter
from copy import deepcopy

import pytest
from pydantic import ValidationError

from eval.captures import Captures
from eval.metrics import bootstrap_f1, distribution, proportion, wilson
from eval.offline_fixture import fixture_capture
from eval.runner import evaluate
from eval.synth import (
    AUTHORIZATIONS,
    JURISDICTIONS,
    LANGUAGES,
    TYPOLOGIES,
    generate,
    validate_dataset,
    write_dataset,
)


@pytest.fixture(scope="module")
def dataset():
    return generate()


def test_generator_is_reproducible_balanced_and_reserved(dataset):
    assert dataset == generate()
    assert dataset["datasetSha256"] != generate(seed=2)["datasetSha256"]
    assert dataset["n"] == 528
    for key, expected in [
        ("language", LANGUAGES),
        ("jurisdiction", JURISDICTIONS),
        ("typologyScenario", TYPOLOGIES),
    ]:
        counts = Counter(item[key] for item in dataset["cases"])
        assert set(counts) == set(expected) and len(set(counts.values())) == 1
    assert set(Counter(item["gold"]["authorizationType"] for item in dataset["cases"])) == set(
        AUTHORIZATIONS
    )
    assert sum(item["injection"] for item in dataset["cases"]) >= 40
    assert all(item["synthetic"] for item in dataset["cases"])
    assert all(
        item["gold"]["recipients"] is None
        for item in dataset["cases"]
        if item["split"] != "evaluation"
    )
    roles = {entity["role"] for item in dataset["cases"] for entity in item["gold"]["entities"]}
    assert roles == {"victim", "scammer", "merchant", "unknown"}
    assert all(
        "fictional.invalid" in entity["normalizedValue"]
        for item in dataset["cases"]
        for entity in item["gold"]["entities"]
        if entity["type"] == "email"
    )
    assert all(
        item["input"]["paymentMethod"] == "card"
        for item in dataset["cases"]
        if item["gold"]["authorizationType"] == "card_unauthorized"
    )


def test_corpus_size_hash_and_review_manifest(dataset, tmp_path):
    with pytest.raises(ValueError):
        generate(n=20)
    changed = deepcopy(dataset)
    changed["cases"][0]["input"]["bankName"] = "Tampered"
    with pytest.raises(ValueError):
        validate_dataset(changed)
    saved = write_dataset(tmp_path)
    import json

    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert saved == dataset and len(manifest["reviewSampleCaseIds"]) == 53
    assert manifest["humanReview"] == "pending"


def test_wilson_known_values_and_zero_denominator():
    low, high = wilson(0, 20)
    assert low == 0 and high == pytest.approx(0.161125158, abs=1e-8)
    assert wilson(20, 20)[0] == pytest.approx(0.838874842, abs=1e-8)
    assert wilson(0, 0) == (None, None)
    assert proportion("not_available", 0, 0)["value"] is None
    with pytest.raises(ValueError):
        wilson(2, 1)


def test_bootstrap_f1_case_clusters_and_latency_unknowns():
    result = bootstrap_f1([(3, 1, 2), (0, 0, 5)], samples=1000)
    assert result == bootstrap_f1([(3, 1, 2), (0, 0, 5)], samples=1000)
    assert result["value"] == pytest.approx(6 / 14)
    assert result["ciLow"] <= result["value"] <= result["ciHigh"]
    assert result["nCases"] == 2
    assert bootstrap_f1([])["value"] is None
    assert distribution([], metric="cost", unknown=3)["unknown"] == 3
    measured = distribution([100.0, 1000.0], metric="latency", unknown=1)
    assert measured["value"] == 550 and measured["p95"] == 1000 and measured["unknown"] == 1
    for bad in [float("nan"), float("inf"), -1.0]:
        with pytest.raises(ValueError):
            distribution([bad], metric="latency")


def test_fixture_failures_and_missing_stay_in_denominator_and_no_fake_systems(dataset):
    report = evaluate(dataset, Captures.model_validate(fixture_capture(dataset)))
    fixture = next(system for system in report["systems"] if system["system"] == "offline_fixture")
    metrics = {metric["metric"]: metric for metric in fixture["metrics"]}
    assert fixture["n"] == 20 and fixture["observedAttempts"] == 19
    assert fixture["outcomes"] == {"completed": 17, "missing": 1, "timeout": 2}
    assert metrics["authorization_accuracy"]["successes"] == 16
    assert metrics["authorization_accuracy"]["n"] == 20
    assert metrics["entity_f1"]["falseNegative"] > 0
    assert metrics["cost_usd"]["value"] is None and metrics["cost_usd"]["unknown"] == 20
    assert metrics["latency_ms"]["value"] is None and metrics["latency_ms"]["unknown"] == 20
    assert metrics["forbidden_content_rate"]["unknown"] == 3
    assert all(not row["rawInputOrProviderTextIncluded"] for row in fixture["failureGallery"])
    assert all(
        system["status"] == "not_measured"
        for system in report["systems"]
        if system["system"] != "offline_fixture"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "unknown",
        "outside_repeat",
        "held_out",
        "hash",
        "completed_without_output",
        "failure_with_output",
        "behavior_without_scorer",
        "duplicated_recipient",
    ],
)
def test_invalid_captures_refuse_silent_miscount(dataset, mutation):
    capture = fixture_capture(dataset)
    system = capture["systems"][0]
    if mutation == "duplicate":
        system["attempts"].append(deepcopy(system["attempts"][0]))
    elif mutation == "unknown":
        system["caseIds"][0] = "SYN-EVAL-99999"
    elif mutation == "outside_repeat":
        system["attempts"][0]["repeat"] = 1
    elif mutation == "held_out":
        system["caseIds"][0] = next(
            item["caseId"] for item in dataset["cases"] if item["split"] != "evaluation"
        )
    elif mutation == "hash":
        capture["datasetSha256"] = "a" * 64
    elif mutation == "completed_without_output":
        system["attempts"][0]["prediction"] = None
    elif mutation == "failure_with_output":
        system["attempts"][0]["status"] = "failed"
    elif mutation == "behavior_without_scorer":
        del system["behaviorScorerVersion"]
    else:
        system["attempts"][0]["prediction"]["recipients"] = ["bank", "bank"]
    with pytest.raises(ValueError):
        evaluate(dataset, Captures.model_validate(capture))


def test_strict_capture_rejects_extra_provider_error_text(dataset):
    capture = fixture_capture(dataset)
    capture["systems"][0]["attempts"][0]["rawError"] = "sensitive provider error"
    with pytest.raises(ValidationError):
        Captures.model_validate(capture)


def test_paired_comparisons_require_same_model_budget_and_repeats_and_scrub_labels(dataset):
    capture = fixture_capture(dataset)
    first = capture["systems"][0]
    first["system"] = "relay"
    first["repeats"] = 3
    second = deepcopy(first)
    second["system"] = "baseline"
    second["caseIds"].reverse()
    capture["systems"].append(second)
    result = evaluate(dataset, Captures.model_validate(capture))
    pair = result["pairedComparisons"][0]
    assert not pair["comparisonClaimAllowed"] and pair["n"] == 60 and pair["nCases"] == 20
    # Merely declaring three repeats must not turn unobserved runs into evidence.
    assert pair["authorizationAccuracyDifference"]["value"] == 0
    assert len(pair["samplePairs"]) == 20
    second["modelId"] = "different-model"
    pair = evaluate(dataset, Captures.model_validate(capture))["pairedComparisons"][0]
    assert not pair["comparisonClaimAllowed"]


def test_full_observed_pair_has_reproducible_paired_interval(dataset):
    capture = fixture_capture(dataset)
    original = capture["systems"][0]
    original["system"] = "relay"
    original["repeats"] = 3
    observed = {row["caseId"]: row for row in original["attempts"]}
    original["attempts"] = []
    for case_id in original["caseIds"]:
        for repeat in range(3):
            item = deepcopy(observed.get(case_id, {"caseId": case_id, "status": "failed"}))
            item["repeat"] = repeat
            original["attempts"].append(item)
    second = deepcopy(original)
    second["system"] = "baseline"
    second["caseIds"].reverse()
    capture["systems"].append(second)
    pair = evaluate(dataset, Captures.model_validate(capture))["pairedComparisons"][0]
    assert pair["comparisonClaimAllowed"]
    assert pair["authorizationAccuracyDifference"]["value"] == 0
    assert pair["authorizationAccuracyDifference"]["ciLow"] == 0
    assert pair["authorizationAccuracyDifference"]["ciHigh"] == 0


def test_cli_invalid_capture_does_not_print_raw_error_or_output(
    dataset, tmp_path, monkeypatch, capsys
):
    import json

    from scripts.evaluate import main

    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
    capture = fixture_capture(dataset)
    capture["systems"][0]["attempts"][0]["rawError"] = "SECRET-PROVIDER-ERROR"
    capture_path = tmp_path / "capture.json"
    capture_path.write_text(json.dumps(capture), encoding="utf-8")
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate",
            "score",
            "--dataset",
            str(dataset_path),
            "--captures",
            str(capture_path),
            "--output",
            str(tmp_path / "report"),
        ],
    )
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2
    output = capsys.readouterr()
    assert "SECRET-PROVIDER-ERROR" not in output.out + output.err
    assert "Evaluation refused" in output.err
