"""Read-only local SDK inspection: no credentials, client instances or network calls."""

import argparse
import importlib
import inspect
import json
from importlib import metadata
from pathlib import Path
from typing import Any

PACKAGES = ("google-genai", "google-adk", "pydantic", "mcp", "a2a-sdk")
SYMBOLS = (
    ("google.genai", "Client"),
    ("google.genai.models", "Models.list"),
    ("google.genai.models", "Models.generate_content"),
    ("google.genai.live", "AsyncLive.connect"),
    ("google.adk.runners", "Runner.run_live"),
    ("google.adk.agents", "LlmAgent"),
    ("google.adk.agents", "SequentialAgent"),
    ("google.adk.agents", "ParallelAgent"),
    ("google.adk.agents", "LoopAgent"),
    ("google.adk.agents.run_config", "RunConfig"),
    ("google.adk.agents.run_config", "StreamingMode"),
    ("google.adk.tools.mcp_tool", "McpToolset"),
    ("google.adk.tools.mcp_tool", "StreamableHTTPConnectionParams"),
    ("google.adk.a2a.utils.agent_to_a2a", "to_a2a"),
    ("google.genai.types", "LiveConnectConfig"),
    ("google.genai.types", "SessionResumptionConfig"),
    ("google.genai.types", "ContextWindowCompressionConfig"),
    ("google.genai.types", "GenerateContentConfig"),
)


def inspect_symbol(module_name: str, dotted_name: str) -> dict[str, Any]:
    """Inspect names only; never serialize client/config instances or exception text."""
    result: dict[str, Any] = {"symbol": f"{module_name}.{dotted_name}"}
    try:
        symbol = importlib.import_module(module_name)
        for part in dotted_name.split("."):
            symbol = getattr(symbol, part)
        result["available"] = True
        if callable(symbol):
            try:
                # Parameter names avoid rendering defaults containing environment data.
                result["parameters"] = list(inspect.signature(symbol).parameters)
            except (TypeError, ValueError):
                result["parameters"] = []
        fields = getattr(symbol, "model_fields", None)
        if isinstance(fields, dict):
            result["schema_fields"] = sorted(fields)
    except Exception as error:
        result.update(available=False, error_type=type(error).__name__)
    return result


def inspect_platform(lock_path: Path) -> dict[str, Any]:
    pins: dict[str, str] = {}
    if lock_path.exists():
        for line in lock_path.read_text(encoding="utf-8").splitlines():
            if "==" in line and not line.startswith("#"):
                name, version = line.split("==", 1)
                pins[name.lower().replace("_", "-")] = version
    versions: dict[str, Any] = {}
    for name in PACKAGES:
        try:
            installed = metadata.version(name)
        except metadata.PackageNotFoundError:
            installed = None
        pin = pins.get(name)
        versions[name] = {
            "installed": installed,
            "lock_pin": pin,
            "matches_lock": installed == pin if pin else None,
        }
    legacy: dict[str, str | None] = {}
    for name in ("google-generativeai",):
        try:
            legacy[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            legacy[name] = None
    return {
        "mode": "local_inspection_only",
        "network_calls": False,
        "model_calls": False,
        "credentials_inspected": False,
        "versions": versions,
        "legacy_packages": legacy,
        "adk_optional_dependencies": [
            requirement
            for requirement in metadata.metadata("google-adk").get_all("Requires-Dist", [])
            if requirement.startswith(("mcp", "a2a-sdk"))
        ],
        "symbols": [inspect_symbol(module, symbol) for module, symbol in SYMBOLS],
        "pending": [
            "Project/region model access and API backend compatibility",
            "Authenticated model discovery",
            "Live audio/latency/resumption integration",
            "MCP/A2A authenticated interoperability",
            "Model Armor/Search residency and feature decision",
            "Official pack fact review",
            "Actual quotas and budget limits",
            "Deployed Cloud Run Gemini smoke",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict", action="store_true", help="Fail on missing symbols or SDK drift"
    )
    args = parser.parse_args()
    report = inspect_platform(Path(__file__).resolve().parents[1] / "requirements.lock")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    sdk_names = PACKAGES
    sdk_drift = any(report["versions"][name]["matches_lock"] is not True for name in sdk_names)
    missing = any(not symbol["available"] for symbol in report["symbols"])
    return int(args.strict and (sdk_drift or missing))


if __name__ == "__main__":
    raise SystemExit(main())
