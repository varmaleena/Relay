"""Backend message-key helpers; UI translation and human review arrive in M1."""

from datetime import datetime
from zoneinfo import ZoneInfo

SUPPORTED = frozenset({"en", "hi"})
MESSAGES = {
    "en": {
        "not_implemented": "This feature will be available in a later build phase.",
        "unauthenticated": "Sign in to continue.",
        "app_check_failed": "Refresh the page and try again.",
        "forbidden": "You do not have access to this action.",
    },
    "hi": {
        "not_implemented": "यह सुविधा अगले निर्माण चरण में उपलब्ध होगी।",
        "unauthenticated": "आगे बढ़ने के लिए साइन इन करें।",
        "app_check_failed": "पेज रीफ़्रेश करके फिर कोशिश करें।",
        "forbidden": "आपको इस कार्रवाई की अनुमति नहीं है।",
    },
}


def resolve_language(accept_language: str) -> str:
    choices: list[tuple[float, int, str]] = []
    for i, raw in enumerate(accept_language[:1000].split(",")):
        parts = raw.strip().split(";")
        language = parts[0].lower().split("-")[0]
        try:
            quality = float(parts[1].strip().removeprefix("q=")) if len(parts) > 1 else 1.0
        except ValueError:
            continue
        if language in SUPPORTED and 0 < quality <= 1:
            choices.append((quality, -i, language))
    return max(choices)[2] if choices else "en"


def message(key: str, language: str) -> str:
    return MESSAGES.get(language, MESSAGES["en"])[key]


def in_timezone(value: datetime, timezone: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timezone-aware timestamp required")
    return value.astimezone(ZoneInfo(timezone))
