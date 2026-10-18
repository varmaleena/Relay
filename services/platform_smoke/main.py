"""One synthetic Gemini request from a workload identity; no business data or secrets."""

import json
import os
import re

from google import genai
from google.genai import types


def main() -> None:
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ["GENAI_LOCATION"]
    model = os.environ["MODEL_FAST"]
    if not re.fullmatch(r"gemini-3[\w.-]*", model):
        raise ValueError("M0 smoke requires a discovered Gemini 3 model ID")
    with genai.Client(
        vertexai=True,
        project=project,
        location=location,
        http_options=types.HttpOptions(
            timeout=60000, retry_options=types.HttpRetryOptions(attempts=1)
        ),
    ) as client:
        response = client.models.generate_content(
            model=model,
            contents="Synthetic connectivity test. Reply with only RELAY_SMOKE_OK.",
            config=types.GenerateContentConfig(temperature=0, max_output_tokens=256),
        )
    success = bool(response.text and "RELAY_SMOKE_OK" in response.text)
    print(json.dumps({"event": "platform.smoke", "model": model, "success": success}))
    if not success:
        raise SystemExit("Synthetic response marker missing; smoke failed")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Remote error bodies can contain request metadata. Never emit them.
        print(json.dumps({"event": "platform.smoke", "success": False, "error": "call_failed"}))
        raise SystemExit(1) from None
