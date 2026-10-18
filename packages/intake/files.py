"""Actual file decoding and conservative credential rejection before promotion."""

import io
import warnings
from dataclasses import dataclass

from packages.safety.guard import SafetyGuard, scrub_credentials


@dataclass(frozen=True)
class ValidatedFile:
    content: bytes
    mime: str
    text: str | None
    flags: tuple[str, ...]


def validate_file(content: bytes, mime: str) -> ValidatedFile:
    if mime not in SafetyGuard.ALLOWED_MIMES or not 0 < len(content) <= SafetyGuard.MAX_BYTES:
        raise ValueError("invalid file type or size")
    text = None
    if mime == "text/plain":
        text = content.decode("utf-8", errors="strict")
        if "\x00" in text:
            raise ValueError("binary content is not plain text")
    elif mime.startswith("image/"):
        from PIL import Image

        expected = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}[mime]
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format != expected or image.width * image.height > 20_000_000:
                    raise ValueError("image does not match declared type or pixel limit")
                image.load()
                clean = image.convert("RGB" if expected == "JPEG" else "RGBA")
                clean.info.clear()
                output = io.BytesIO()
                clean.save(output, format=expected)
                content = output.getvalue()
    else:
        from pypdf import PdfReader, PdfWriter

        if not content.startswith(b"%PDF-"):
            raise ValueError("file does not match PDF declaration")
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 20:
            raise ValueError("unsupported encrypted PDF or page count")
        writer = PdfWriter()
        texts = []
        for page in reader.pages:
            if any(key in page for key in ["/AA", "/Annots"]):
                raise ValueError("active or annotated PDFs are not accepted")
            texts.append(page.extract_text() or "")
            writer.add_page(page)
        text = "\n".join(texts)
        output = io.BytesIO()
        writer.add_metadata({})
        writer.write(output)
        content = output.getvalue()
    if text is not None and scrub_credentials(text) != text:
        raise ValueError("file contains sensitive credentials; use a synthetic redacted copy")
    if len(content) > SafetyGuard.MAX_BYTES:
        raise ValueError("decoded file exceeds size bound")
    flags = SafetyGuard().inspect_input(text).flags if text is not None else ()
    return ValidatedFile(content, mime, text, flags)
