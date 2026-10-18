"""Real, bounded PDF export; never substitutes HTML or silently drops glyphs."""

from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from packages.schemas import PacketContent


class PacketPDFError(ValueError):
    """Export unavailable or unsafe; the UI must offer the textual draft."""


FIELD_LABELS = {
    "payment.amount": "Amount and currency",
    "payment.timestamp": "Payment date and time",
    "payment.transaction_ref": "Transaction reference",
    "payment.recipient_identifier": "Who you paid",
    "payment.method": "Payment method",
    "victim_bank": "Your bank",
    "contact.identifier": "Caller or sender",
    "contact.claimed_identity": "Who they claimed to represent",
}


def render_packet_pdf(
    content: PacketContent, *, recipient_name: str, font_path: str | Path | None = None
) -> bytes:
    """Export the recipient document and its separately labeled victim translation.

    Non-Latin content requires an explicitly provisioned Unicode TrueType font and
    HarfBuzz shaping. Missing dependencies fail explicitly, never render tofu.
    Caller must verify current packet status/ownership before allowing export.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (
            KeepTogether,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise PacketPDFError("pdf_dependency_unavailable") from exc

    values = [
        recipient_name,
        content.subject,
        content.summary,
        content.message,
        content.footer,
        *content.requested_actions,
        *content.victim_copy.values(),
        *[f"{f.label}: {f.value or 'Not provided'}" for f in content.fields],
        *[str(v) for c in content.citations + content.attachments for v in c.values()],
    ]
    text = "\n".join(values)
    if len(text) > 32000 or any(len(v) > 7000 for v in values):
        raise PacketPDFError("pdf_content_bounds")
    font_path = font_path or Path(__file__).parent / "fonts/NotoSansDevanagari.ttf"
    font = "Helvetica"
    if any(ord(char) > 255 for char in text):
        if not font_path or not Path(font_path).is_file():
            raise PacketPDFError("pdf_unicode_font_required")
        try:
            import uharfbuzz  # noqa: F401
        except ImportError as exc:
            raise PacketPDFError("pdf_shaping_unavailable") from exc
        font = "RelayPacketUnicode"
        try:
            pdfmetrics.registerFont(TTFont(font, str(font_path), shapable=True))
        except Exception as exc:
            raise PacketPDFError("pdf_font_invalid") from exc
        face = pdfmetrics.getFont(font).face
        if any(ord(char) not in face.charToGlyph for char in text if not char.isspace()):
            raise PacketPDFError("pdf_font_missing_glyph")
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "RelayBody",
        fontName=font,
        fontSize=10,
        leading=15,
        spaceAfter=9,
        alignment=TA_LEFT,
        splitLongWords=True,
        shaping=True,
    )
    title = ParagraphStyle("RelayTitle", parent=body, fontSize=19, leading=24, spaceAfter=14)
    small = ParagraphStyle("RelaySmall", parent=body, fontSize=8, leading=12)
    del styles

    def para(value: str, style=body):
        return Paragraph(escape(value).replace("\n", "<br/>"), style)

    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=(210 * mm, 297 * mm),
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title="Relay recipient draft",
        author="Relay",
        pageCompression=1,
    )
    story = [
        para("SIMULATED DEMONSTRATION - no real institution receives this document.", small),
        para("RELAY / RECIPIENT DRAFT - Review before use", small),
        para(content.subject, title),
        para(f"Recipient: {recipient_name}"),
        para(content.summary),
        Spacer(1, 5 * mm),
    ]
    rows = [[para("Field", small), para("Victim statement / evidence value", small)]]
    rows.extend(
        [
            [para(FIELD_LABELS.get(f.key, f.label), small), para(f.value or "Not provided", small)]
            for f in content.fields
        ]
    )
    table = Table(rows, colWidths=[60 * mm, 110 * mm], repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F2F4")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.grey),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([table, Spacer(1, 7 * mm), para(content.message)])
    for action in content.requested_actions:
        story.append(para(f"Request: {action}"))
    for citation in content.citations:
        story.append(para("Source: " + "; ".join(f"{k}: {v}" for k, v in citation.items()), small))
    for attachment in content.attachments:
        story.append(
            para("Attachment: " + "; ".join(f"{k}: {v}" for k, v in attachment.items()), small)
        )
    story.extend([Spacer(1, 7 * mm), para("Victim language copy", title)])
    for key, value in content.victim_copy.items():
        story.extend(
            [para({"summary": "Summary", "message": "Report"}.get(key, key), small), para(value)]
        )
    story.append(KeepTogether([Spacer(1, 5 * mm), para(content.footer, small)]))

    def page_number(canvas, doc):
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor("#45566A"))
        canvas.drawRightString(190 * mm, 11 * mm, f"Relay draft | {doc.page}")

    try:
        document.build(story, onFirstPage=page_number, onLaterPages=page_number)
    except Exception as exc:
        raise PacketPDFError("pdf_render_failed") from exc
    result = output.getvalue()
    if not result.startswith(b"%PDF-") or len(result) > 5_000_000:
        raise PacketPDFError("pdf_output_bounds")
    return result
