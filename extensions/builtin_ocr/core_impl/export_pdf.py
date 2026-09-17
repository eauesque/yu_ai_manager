"""PDF export and utility functions for OCR results.

Separated from export.py for maintainability.
"""

from __future__ import annotations

import io
import logging

from .types import OcrResult

logger = logging.getLogger(__name__)


def _export_pdf(
    ocr: OcrResult, fid: int,
    translations: dict[int, str] | None = None,
    translated_full_text: str = "",
    suffix: str = "",
    *,
    _export_md_fn=None,
) -> tuple[bytes, str, str]:
    """PDF output using reportlab (BSD license)."""
    try:
        from reportlab.lib.colors import HexColor
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            HRFlowable,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
        )
    except ImportError as exc:
        raise RuntimeError(
            "PDF export requires reportlab. Install: uv pip install reportlab"
        ) from exc

    # Import md exporter lazily to avoid circular import
    if _export_md_fn is None:
        from .export import _export_md
        _export_md_fn = _export_md

    md_bytes, _, _ = _export_md_fn(ocr, fid, translations, translated_full_text, suffix)
    text = md_bytes.decode("utf-8")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    style_normal = ParagraphStyle(
        "OcrNormal", parent=styles["Normal"],
        fontSize=9, leading=13, alignment=TA_LEFT,
    )
    style_heading = ParagraphStyle(
        "OcrHeading", parent=styles["Heading2"],
        fontSize=13, leading=18, textColor=HexColor("#191964"),
        spaceAfter=4,
    )
    style_quote = ParagraphStyle(
        "OcrQuote", parent=style_normal,
        leftIndent=15, textColor=HexColor("#3264C8"),
    )

    story: list = []

    def _esc(s: str) -> str:
        """Escape XML special chars for reportlab Paragraph."""
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    for line in text.split("\n"):
        line = line.rstrip()

        if line.startswith("## "):
            heading = _esc(line[3:].strip())
            story.append(Paragraph(heading, style_heading))
            continue

        if line.startswith("> "):
            quote = _esc(line[2:].strip())
            story.append(Paragraph(quote, style_quote))
            continue

        if line.strip() == "---":
            story.append(Spacer(1, 3))
            story.append(HRFlowable(
                width="100%", thickness=0.5,
                color=HexColor("#B0B0B0"), spaceAfter=3,
            ))
            continue

        if not line.strip():
            story.append(Spacer(1, 6))
            continue

        clean = _esc(line.replace("**", "").replace("*", ""))
        story.append(Paragraph(clean, style_normal))

    if not story:
        story.append(Paragraph("(empty)", style_normal))

    doc.build(story)
    return (buf.getvalue(), f"ocr_{fid}{suffix}.pdf", "application/pdf")


def _wrap_line(text: str, max_chars: int) -> list[str]:
    """Wrap text at max_chars character boundary."""
    if len(text) <= max_chars:
        return [text]
    lines = []
    while text:
        if len(text) <= max_chars:
            lines.append(text)
            break
        # Word-wrap (character-based for CJK)
        cut = max_chars
        # Break at ASCII space if present
        space_pos = text.rfind(" ", 0, max_chars)
        if space_pos > max_chars // 2:
            cut = space_pos + 1
        lines.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    return lines if lines else [""]


def _dict_table_to_md(table: dict) -> str:
    """Convert table dict to Markdown table format."""
    headers = table.get("headers", [])
    rows = table.get("rows", [])
    if not headers and not rows:
        return ""
    lines = []
    if headers:
        lines.append("| " + " | ".join(str(h) for h in headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)
