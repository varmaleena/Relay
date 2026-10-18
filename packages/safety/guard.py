"""Conservative v0 text controls, not a claim of complete injection protection."""

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SafetyResult:
    allow: bool
    flags: tuple[str, ...]
    action: str


@dataclass(frozen=True)
class UploadMetadata:
    mime: str
    size_bytes: int
    pages: int | None = None
    decoded: bool = False


def _normalize(text: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKC", text).lower()
        if unicodedata.category(char) != "Cf"
    )


def scrub_credentials(text: str) -> str:
    """Scrub labeled values and card-shaped numbers before persistence/logging.

    This cannot identify arbitrary unlabeled credentials or secrets inside images.
    """
    text = re.sub(
        r"(?i)((?:otp|pin|password|cvv|ओटीपी|पिन|पासवर्ड|सीवीवी)(?:\s*(?:is|है|:|=)\s*|\s+))[\w!@#$%&*.-]+",
        r"\1[REDACTED]",
        text,
    )
    return re.sub(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)", "[REDACTED CARD]", text)


class SafetyGuard:
    MAX_BYTES = 10 * 1024 * 1024
    ALLOWED_MIMES = frozenset(
        {"image/png", "image/jpeg", "image/webp", "application/pdf", "text/plain"}
    )
    _injection = re.compile(
        r"ignore (?:all |the |previous )*(?:instructions|rules)|system\s*:|you are now|"
        r"reveal.{0,30}(?:system prompt|instructions)|"
        r"(?:निर्देश|नियम).{0,20}(?:अनदेखा|भूल)",
        re.I,
    )

    def __init__(self) -> None:
        directory = Path(__file__).parent / "patterns"
        self.patterns = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(directory.glob("*.json"))
        ]

    def inspect_input(self, text: str) -> SafetyResult:
        normalized = _normalize(text)
        flags = ("injection",) if self._injection.search(normalized) else ()
        # Flagging does not authorize instruction execution or make the input safe.
        return SafetyResult(True, flags, "flag" if flags else "pass")

    def inspect_output(self, text: str) -> SafetyResult:
        normalized = _normalize(text)
        flags: set[str] = set()
        for sentence in re.split(r"[.!?।;,\n]+|\b(?:but|however|then)\b|लेकिन|परंतु", normalized):
            for language in self.patterns:
                for category in ("solicitation", "promise", "legal"):
                    for pattern in language[category]:
                        for match in re.finditer(pattern, sentence):
                            prefix = sentence[: match.start()]
                            suffix = sentence[match.end() :]
                            negated = bool(
                                re.search(
                                    r"(?:do not|don't|never|must not|should not|cannot|can't|"
                                    r"will not|won't|no one should)\s+$",
                                    prefix,
                                )
                            )
                            negated = negated or bool(
                                re.search(r"(?:मत|नहीं|mat|nahi|nahin)\s*$", prefix)
                            )
                            negated = negated or bool(
                                re.search(
                                    r"(?:मत|नहीं|mat|nahi|nahin)\s+"
                                    r"(?:बताइए|बताओ|भेजें|भेजो|दें|batao|bhejo|share karo)",
                                    match.group(),
                                )
                            )
                            # Hindi places negation after the credential/action.
                            negated = negated or bool(
                                re.match(r"\s*(?:मत|नहीं|mat|nahi|nahin)\b", suffix)
                            )
                            if category != "legal" and negated:
                                continue
                            flags.add(category)
        if re.search(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)", normalized):
            flags.add("credential_value")
        if re.search(
            r"(?:otp|pin|cvv|ओटीपी|पिन|सीवीवी)\s*(?:is|है|:|=)?\s*\d{3,8}\b|"
            r"(?:password|पासवर्ड)\s*[:=]\s*\S+",
            normalized,
        ):
            flags.add("credential_value")
        return SafetyResult(not flags, tuple(sorted(flags)), "block" if flags else "pass")

    def validate_upload(self, metadata: UploadMetadata) -> SafetyResult:
        flags: list[str] = []
        if metadata.mime not in self.ALLOWED_MIMES:
            flags.append("unsupported_mime")
        if not 0 < metadata.size_bytes <= self.MAX_BYTES:
            flags.append("invalid_size")
        if metadata.mime.startswith("image/") and not metadata.decoded:
            flags.append("image_decode_required")
        if metadata.mime == "application/pdf" and (
            metadata.pages is None or not 1 <= metadata.pages <= 20
        ):
            flags.append("pdf_page_limit")
        return SafetyResult(not flags, tuple(flags), "block" if flags else "quarantine")
