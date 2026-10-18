"""CLI for synthetic templates and captured-output scoring; never invokes providers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from eval.captures import Captures
from eval.runner import evaluate
from eval.synth import write_dataset


def markdown(report: dict) -> str:
    lines = [
        "# Synthetic captured-output evaluation",
        "",
        f"Dataset: `{report['datasetVersion']}` / `{report['datasetSha256']}`.",
        f"Generated: {report['createdAt']}. Commit: `{report['commitSha']}`.",
        "",
        "This scores supplied captures; it does not execute Relay, a baseline or an ablation.",
        "",
        "| System | Mode | Metric | Value | n | Unknown | 95% CI |",
        "|---|---|---|---:|---:|---:|---|",
    ]
    for system in report["systems"]:
        if not system.get("metrics"):
            lines.append(f"| {system['system']} | not measured | — | — | 0 | — |")
        for metric in system.get("metrics", []):
            value = "not measured" if metric["value"] is None else f"{metric['value']:.4f}"
            ci = (
                "—"
                if metric["ciLow"] is None
                else f"[{metric['ciLow']:.4f}, {metric['ciHigh']:.4f}]"
            )
            lines.append(
                f"| {system['system']} | {system.get('executionMode')} | {metric['metric']} "
                f"| {value} | {metric['n']} | {metric.get('unknown', 0)} | {ci} |"
            )
    lines += ["", "## Limitations", ""] + ["- " + text for text in report["limitations"]]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    synth = commands.add_parser("synth")
    synth.add_argument("--output", type=Path, required=True)
    synth.add_argument("--n", type=int, default=528)
    synth.add_argument("--seed", type=int, default=20261018)
    score = commands.add_parser("score")
    score.add_argument("--dataset", type=Path, required=True)
    score.add_argument("--captures", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)
    score.add_argument("--commit-sha", default="unknown")
    args = parser.parse_args()
    if args.command == "synth":
        dataset = write_dataset(args.output, n=args.n, seed=args.seed)
        print(
            json.dumps(
                {
                    "n": dataset["n"],
                    "datasetSha256": dataset["datasetSha256"],
                    "mode": "synthetic_templates",
                }
            )
        )
        return
    if args.dataset.stat().st_size > 50_000_000 or args.captures.stat().st_size > 50_000_000:
        parser.error("Input artifact is larger than the bounded offline evaluator accepts")
    try:
        dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
        captures = Captures.model_validate_json(args.captures.read_text(encoding="utf-8"))
        report = evaluate(dataset, captures, commit_sha=args.commit_sha)
    except (ValueError, KeyError, TypeError):
        parser.exit(2, "Evaluation refused: invalid synthetic dataset or capture artifact.\n")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (args.output / "report.md").write_text(markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {"reportVersion": report["reportVersion"], "nSystemsCaptured": len(captures.systems)}
        )
    )


if __name__ == "__main__":
    main()
