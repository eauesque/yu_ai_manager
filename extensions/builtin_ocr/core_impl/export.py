"""OCR result export (txt / md / json / pdf).

When translations are provided, exports include translated text.
translations is a dict of region_id -> translated_text.
translated_full_text is a full-text translation fallback.

PDF export and utility functions are in export_pdf.py.
"""

from __future__ import annotations

import json
import logging
import tempfile
import zipfile

# Re-export from export_pdf for backward compatibility
from .export_pdf import (  # noqa: F401
    _dict_table_to_md,
    _wrap_line,
)
from .types import OcrResult

logger = logging.getLogger(__name__)

EXPORT_FORMATS = ("txt", "md", "json", "pdf")
_SPOOL_MAX_MEMORY = 16 * 1024 * 1024  # 16 MB before ZIP output spills to disk


def export_ocr(
    ocr: OcrResult,
    format: str = "md",
    *,
    translations: dict[int, str] | None = None,
    translated_full_text: str = "",
    target_lang: str = "",
) -> tuple[bytes, str, str]:
    """Export OCR result.

    Args:
        ocr: OCR result
        format: Output format (txt, md, json, pdf)
        translations: region_id -> translated text dict
        translated_full_text: Full-text translation fallback
        target_lang: Target language code (for filename suffix)

    Returns:
        (content_bytes, filename, content_type)
    """
    fid = ocr.file_id or 0
    suffix = f"_{target_lang}" if target_lang else ""
    if format == "txt":
        return _export_txt(ocr, fid, translations, translated_full_text, suffix)
    elif format == "md":
        return _export_md(ocr, fid, translations, translated_full_text, suffix)
    elif format == "json":
        return _export_json(ocr, fid, translations, translated_full_text, suffix)
    elif format == "pdf":
        from .export_pdf import _export_pdf
        return _export_pdf(
            ocr, fid, translations, translated_full_text, suffix,
            _export_md_fn=_export_md,
        )
    else:
        raise ValueError(f"Unsupported format: {format}")


def export_ocr_batch(
    ocr_results: list[OcrResult],
    format: str = "md",
    *,
    translations_map: dict[int, dict[int, str]] | None = None,
    full_text_map: dict[int, str] | None = None,
    target_lang: str = "",
) -> tuple[bytes, str]:
    """Export multiple OCR results as a ZIP archive.

    Args:
        translations_map: file_id -> {region_id -> translated_text}
        full_text_map: file_id -> translated_full_text
    """
    buf = open_ocr_batch_stream(
        ocr_results,
        format=format,
        translations_map=translations_map,
        full_text_map=full_text_map,
        target_lang=target_lang,
    )
    suffix = f"_{target_lang}" if target_lang else ""
    try:
        return buf.read(), f"ocr_export_{format}{suffix}.zip"
    finally:
        buf.close()


def open_ocr_batch_stream(
    ocr_results: list[OcrResult],
    format: str = "md",
    *,
    translations_map: dict[int, dict[int, str]] | None = None,
    full_text_map: dict[int, str] | None = None,
    target_lang: str = "",
):
    """Build OCR export ZIP into a spooled file and return it at position 0."""
    buf = tempfile.SpooledTemporaryFile(max_size=_SPOOL_MAX_MEMORY, mode="w+b")  # noqa: SIM115 — intentional: file lives beyond context
    try:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for ocr in ocr_results:
                try:
                    fid = ocr.file_id or 0
                    trans = (translations_map or {}).get(fid)
                    full = (full_text_map or {}).get(fid, "")
                    content, filename, _ = export_ocr(
                        ocr, format,
                        translations=trans,
                        translated_full_text=full,
                        target_lang=target_lang,
                    )
                    zf.writestr(filename, content)
                except Exception as exc:
                    logger.warning("Export skipped for file_id=%s: %s", ocr.file_id, exc)
                    continue
    except Exception:
        buf.close()
        raise
    buf.seek(0)
    return buf


# ── Format handlers ──


def _export_txt(
    ocr: OcrResult, fid: int,
    translations: dict[int, str] | None = None,
    translated_full_text: str = "",
    suffix: str = "",
) -> tuple[bytes, str, str]:
    has_trans = translations or translated_full_text
    if has_trans and translations and ocr.regions:
        # Per-region translation pairs
        lines = []
        for region in ocr.regions:
            lines.append(region.text)
            trans = translations.get(region.region_id, "")
            if trans:
                lines.append(f">> {trans}")
                lines.append("")
        content = "\n".join(lines).rstrip() + "\n"
    elif has_trans and translated_full_text:
        # Full text translation pairs
        content = (
            ocr.full_text + "\n\n"
            "--- Translation ---\n\n"
            + translated_full_text + "\n"
        )
    else:
        content = ocr.full_text + "\n"

    return (
        content.encode("utf-8"),
        f"ocr_{fid}{suffix}.txt",
        "text/plain; charset=utf-8",
    )


def _export_md(
    ocr: OcrResult, fid: int,
    translations: dict[int, str] | None = None,
    translated_full_text: str = "",
    suffix: str = "",
) -> tuple[bytes, str, str]:
    lines = []
    has_trans = translations or translated_full_text

    if ocr.task == "ocr_document":
        if ocr.regions:
            for region in ocr.regions:
                if region.label == "heading":
                    lines.append(f"## {region.text}")
                    if translations:
                        trans = translations.get(region.region_id, "")
                        if trans:
                            lines.append(f"*{trans}*")
                    lines.append("")
                elif region.label == "table":
                    lines.append(region.text)
                    lines.append("")
                else:
                    lines.append(region.text)
                    if translations:
                        trans = translations.get(region.region_id, "")
                        if trans:
                            lines.append("")
                            lines.append(f"> {trans}")
                    lines.append("")
        else:
            for h in ocr.headings:
                lines.append(f"## {h}")
                lines.append("")
            if ocr.full_text:
                lines.append(ocr.full_text)
                lines.append("")
        for table in ocr.tables:
            lines.append(_dict_table_to_md(table))
            lines.append("")
        if not lines:
            lines.append(ocr.full_text)
    elif ocr.task == "ocr_manga":
        for region in ocr.regions:
            label_str = f"[{region.label}] " if region.label else ""
            dir_str = " (vertical)" if region.direction == "vertical" else ""
            lines.append(f"{label_str}{region.text}{dir_str}")
            if translations:
                trans = translations.get(region.region_id, "")
                if trans:
                    lines.append(f"> {trans}")
        if not lines:
            lines.append(ocr.full_text)
    else:
        # Generic OCR
        if ocr.regions:
            for region in ocr.regions:
                lines.append(region.text)
                if translations:
                    trans = translations.get(region.region_id, "")
                    if trans:
                        lines.append(f"> {trans}")
                        lines.append("")
        else:
            lines.append(ocr.full_text)

    # Full text translation fallback
    if has_trans and not translations and translated_full_text:
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("**Translation:**")
        lines.append("")
        lines.append(translated_full_text)

    content = "\n".join(lines).rstrip() + "\n"
    return (
        content.encode("utf-8"),
        f"ocr_{fid}{suffix}.md",
        "text/markdown; charset=utf-8",
    )


def _export_json(
    ocr: OcrResult, fid: int,
    translations: dict[int, str] | None = None,
    translated_full_text: str = "",
    suffix: str = "",
) -> tuple[bytes, str, str]:
    data = ocr.to_dict()
    if translations or translated_full_text:
        data["translations"] = {}
        if translations:
            # Add per-region translations to regions array
            for region in data.get("regions", []):
                rid = region.get("region_id", 0)
                trans = translations.get(rid, "")
                if trans:
                    region["translated"] = trans
        if translated_full_text:
            data["translated_full_text"] = translated_full_text
    content = json.dumps(data, ensure_ascii=False, indent=2)
    return (
        content.encode("utf-8"),
        f"ocr_{fid}{suffix}.json",
        "application/json",
    )
