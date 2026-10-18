"""Cross-platform entry points for approved Relay milestones."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = (
    "bootstrap dev seed reset lint typecheck test e2e openapi synth eval "
    "eval-packbuilder eval-redteam report build deploy-dev deploy-prod preflight rollback clean"
).split()


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def coverage_gates() -> None:
    report = json.loads((ROOT / ".tmp/coverage.json").read_text())
    for prefix, minimum in (("packages/", 85), ("services/", 70)):
        summaries = [
            entry["summary"]
            for name, entry in report["files"].items()
            if name.replace("\\", "/").startswith(prefix)
        ]
        total = sum(s["num_statements"] for s in summaries)
        covered = sum(s["covered_lines"] for s in summaries)
        if total and covered / total * 100 < minimum:
            raise SystemExit(f"{prefix} coverage {covered / total * 100:.1f}% below {minimum}%")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("--service")
    args = parser.parse_args()
    os.chdir(ROOT)
    temporary = ROOT / ".tmp"
    temporary.mkdir(exist_ok=True)
    os.environ["TMP"] = os.environ["TEMP"] = str(temporary)
    os.environ["PYTHONPATH"] = str(ROOT)
    python = sys.executable
    if args.target == "bootstrap":
        if sys.version_info[:2] != (3, 12):
            raise SystemExit("Use Python 3.12 for bootstrap.")
        venv_python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not venv_python.exists():
            run(python, "-m", "venv", str(ROOT / ".venv"))
        run(str(venv_python), "-m", "pip", "install", "-r", "requirements.lock")
        run("npm.cmd" if os.name == "nt" else "npm", "ci")
    elif args.target == "lint":
        run(
            python,
            "-m",
            "ruff",
            "check",
            "packages",
            "services",
            "agents",
            "scripts",
            "tests",
            "infra/scripts",
        )
        run(
            python,
            "-m",
            "ruff",
            "format",
            "--check",
            "packages",
            "services",
            "agents",
            "scripts",
            "tests",
            "infra/scripts",
        )
    elif args.target == "typecheck":
        run(python, "-m", "mypy", "packages", "services", "agents", "scripts", "infra/scripts")
        compiler = ROOT / "node_modules" / ".bin" / ("tsc.cmd" if os.name == "nt" else "tsc")
        run(
            str(compiler),
            "--noEmit",
            "--strict",
            "--target",
            "ES2022",
            "--module",
            "ESNext",
            "--moduleResolution",
            "bundler",
            "--lib",
            "ES2022,DOM",
            "apps/web/src/generated/contracts.ts",
            "apps/web/src/generated/client.ts",
        )
        run(str(compiler), "--noEmit", "-p", "apps/web/tsconfig.json")
    elif args.target == "test":
        run(
            python,
            "-m",
            "pytest",
            "--cov=packages",
            "--cov=services",
            "--cov=agents",
            "--cov-report=term-missing",
            "--cov-report=json:.tmp/coverage.json",
        )
        coverage_gates()
        run("node", "--test", "apps/web/tests/content.test.mjs")
    elif args.target == "e2e":
        run(
            str(
                ROOT / "node_modules/.bin" / ("playwright.cmd" if os.name == "nt" else "playwright")
            ),
            "test",
            "--config=apps/web/playwright.config.ts",
        )
    elif args.target == "openapi":
        run(python, "scripts/export_contracts.py")
    elif args.target == "dev":
        run(python, "-m", "scripts.dev")
    elif args.target == "preflight":
        from scripts.preflight import main as preflight

        raise SystemExit(
            preflight(
                [
                    "--api",
                    os.environ.get("RELAY_PREFLIGHT_API", "http://127.0.0.1:8000"),
                    "--web",
                    os.environ.get("RELAY_PREFLIGHT_WEB", "http://127.0.0.1:5173"),
                    "--output",
                    ".tmp/preflight.json",
                ]
            )
        )
    elif args.target == "synth":
        run(python, "-m", "scripts.evaluate", "synth", "--output", ".tmp/eval-dataset")
    elif args.target in {"eval", "report"}:
        captures = os.environ.get("RELAY_EVAL_CAPTURES")
        if not captures:
            raise SystemExit(
                "Set RELAY_EVAL_CAPTURES to actual captured outputs. This command does not "
                "invent or execute baseline/model results. Offline fixture captures may be "
                "selected explicitly and remain labeled as fixtures."
            )
        run(
            python,
            "-m",
            "scripts.evaluate",
            "score",
            "--dataset",
            os.environ.get("RELAY_EVAL_DATASET", "eval/datasets/v1/cases.json"),
            "--captures",
            captures,
            "--output",
            ".tmp/evaluation-report",
            "--commit-sha",
            os.environ.get("RELAY_BUILD_SHA", "uncommitted-workspace"),
        )
    elif args.target == "build":
        run(
            str(ROOT / "node_modules/.bin" / ("vite.cmd" if os.name == "nt" else "vite")),
            "build",
            "apps/web",
        )
    elif args.target == "clean":
        print("Clean is intentionally non-destructive. Remove local caches manually if needed.")
    else:
        raise SystemExit(
            f"{args.target}: not implemented in the current milestone. No action performed; "
            "awaiting its approved implementation phase."
        )


if __name__ == "__main__":
    main()
