"""Bounded read-only Vertex publisher-model discovery using ADC; no inference."""

import argparse
import json
import re
from typing import Any

from google import genai
from google.genai import types


def discover_models(
    project: str, location: str, *, page_size: int, max_pages: int, timeout_seconds: int
) -> dict[str, Any]:
    """List metadata only. A listing does not prove generate-content access."""
    models: list[dict[str, Any]] = []
    with genai.Client(
        vertexai=True,
        project=project,
        location=location,
        http_options=types.HttpOptions(
            # Publisher Model Garden listing is documented under v1beta1.
            api_version="v1beta1",
            timeout=timeout_seconds * 1000,
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    ) as client:
        pager = client.models.list(
            config=types.ListModelsConfig(page_size=page_size, query_base=True)
        )
        pages = 0
        while True:
            pages += 1
            for model in pager.page:
                models.append(
                    {
                        "name": model.name,
                        "version": model.version,
                        "supportedActions": model.supported_actions,
                        "inputTokenLimit": model.input_token_limit,
                        "outputTokenLimit": model.output_token_limit,
                    }
                )
            has_more = bool(pager.config.get("page_token"))
            if not has_more or pages >= max_pages:
                break
            pager.next_page()
    return {
        "mode": "read_only_publisher_model_discovery",
        "project": project,
        "location": location,
        "pagesFetched": pages,
        "truncated": has_more,
        "inferencePerformed": False,
        "accessValidatedByInference": False,
        "models": models,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--page-size", type=int, default=50)
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=15)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,61}[a-z0-9]", args.project):
        parser.error("project must be a Google Cloud project ID")
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,40}", args.location):
        parser.error("location must be a Google Cloud location identifier")
    if not 1 <= args.page_size <= 100 or not 1 <= args.max_pages <= 10:
        parser.error("page-size must be 1..100 and max-pages 1..10")
    if not 1 <= args.timeout_seconds <= 30:
        parser.error("timeout-seconds must be 1..30")
    try:
        report = discover_models(
            args.project,
            args.location,
            page_size=args.page_size,
            max_pages=args.max_pages,
            timeout_seconds=args.timeout_seconds,
        )
    except Exception as error:
        # Error bodies may contain headers/request metadata: never print them.
        code = getattr(error, "code", None)
        status = getattr(error, "status", None)
        safe_status = (
            status if isinstance(status, str) and re.fullmatch(r"[A-Z_]{1,60}", status) else None
        )
        print(
            json.dumps(
                {
                    "mode": "read_only_publisher_model_discovery",
                    "errorType": type(error).__name__,
                    "httpCode": code if isinstance(code, int) else None,
                    "status": safe_status,
                    "inferencePerformed": False,
                    "detail": "Discovery failed; check ADC, enabled API, project IAM and location.",
                }
            )
        )
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
