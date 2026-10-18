"""Deliberately imperfect canned captures for evaluator regression, never model results."""

import argparse
import json
from copy import deepcopy
from pathlib import Path

from eval.synth import sha256, validate_dataset


def fixture_capture(dataset: dict) -> dict:
    validate_dataset(dataset)
    cases = [case for case in dataset["cases"] if case["split"] == "evaluation"][:20]
    attempts = []
    for index, case in enumerate(cases):
        if index == 3:
            continue  # A planned but missing observation must count as a failure.
        record = {
            "caseId": case["caseId"],
            "repeat": 0,
            "status": "timeout" if index in {7, 12} else "completed",
            "latencyMs": None,
            "costUsd": None,
        }
        if record["status"] == "completed":
            gold = case["gold"]
            prediction = {
                key: deepcopy(gold[key])
                for key in [
                    "entities",
                    "typology",
                    "authorizationType",
                    "recipients",
                    "packetFields",
                ]
            }
            if index == 5:
                prediction["authorizationType"] = (
                    "unclear"
                    if gold["authorizationType"] != "unclear"
                    else "authorized_manipulated"
                )
                prediction["entities"] = prediction["entities"][:-1]
            prediction["forbiddenContent"] = False
            prediction["injectionSucceeded"] = False if case["injection"] else None
            record["prediction"] = prediction
        else:
            record["failureCode"] = "provider_timeout"
        attempts.append(record)
    return {
        "datasetSha256": dataset["datasetSha256"],
        "systems": [
            {
                "system": "offline_fixture",
                "executionMode": "captured_offline",
                "modelId": "none-canned-evaluator-fixture",
                "promptVersion": "none-canned-evaluator-fixture.v1",
                "configHash": sha256({"fixtureVersion": 1}),
                "budgetMs": 1,
                "repeats": 1,
                "caseIds": [case["caseId"] for case in cases],
                "attempts": attempts,
                "behaviorScorerVersion": "canned-fixture-annotations.v1",
            }
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(fixture_capture(dataset), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
