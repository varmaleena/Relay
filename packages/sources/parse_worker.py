"""Isolated parser entrypoint; raw source bytes arrive on stdin, never argv."""

import importlib
import io
import json
import re
import sys
from html.parser import HTMLParser
from typing import Any

MAX_TEXT = 500000


class VisibleHTML(HTMLParser):
    BLOCKED = {
        "script",
        "style",
        "noscript",
        "iframe",
        "object",
        "embed",
        "svg",
        "math",
        "template",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts = []
        self.size = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCKED or self.depth:
            self.depth += 1
        elif tag in {"p", "br", "div", "li", "h1", "h2", "h3", "tr"}:
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        if not self.depth and tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.depth:
            self.depth -= 1
        elif tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.depth:
            self.size += len(data)
            if self.size > MAX_TEXT:
                raise ValueError("Text limit exceeded")
            self.parts.append(data)


def extract(content: bytes, mime: str) -> list[tuple[int | None, str]]:
    pages: list[tuple[int | None, str]]
    if mime == "application/pdf":
        from pypdf import PdfReader

        if not content.startswith(b"%PDF-"):
            raise ValueError("Invalid PDF")
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted or len(reader.pages) > 200:
            raise ValueError("PDF limits exceeded")
        pages = [(index + 1, page.extract_text() or "") for index, page in enumerate(reader.pages)]
    else:
        text = content.decode("utf-8-sig", errors="strict")
        if mime == "text/html":
            parser = VisibleHTML()
            parser.feed(text)
            parser.close()
            text = "".join(parser.parts)
        elif mime != "text/plain":
            raise ValueError("Unsupported MIME")
        pages = [(None, text)]
    normalized = [(page, re.sub(r"[^\S\n]+", " ", text).strip()) for page, text in pages]
    if sum(len(text) for _, text in normalized) > MAX_TEXT or any(
        "\x00" in text for _, text in normalized
    ):
        raise ValueError("Text limits exceeded")
    if not any(text for _, text in normalized):
        raise ValueError("No extractable source text")
    return normalized


def main():
    # Production parser is Linux-only: fail closed if OS hard limits are unavailable.
    resource: Any = importlib.import_module("resource")

    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (4, 4))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    raw = sys.stdin.buffer.read(25 * 1024 * 1024 + 1)
    if len(raw) > 25 * 1024 * 1024:
        raise ValueError("Size exceeded")
    result = extract(raw, sys.argv[1])
    sys.stdout.write(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(1)
