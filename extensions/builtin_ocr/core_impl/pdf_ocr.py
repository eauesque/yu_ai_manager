"""PDF OCR -- page rendering via pdf2image -> per-page OCR -> merged result.

Scanned PDFs (no text layer) are rendered to images for OCR.
Uses pdf2image (poppler) for page rendering.
"""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Any

from .types import OcrEngine, OcrRegion, OcrResult

logger = logging.getLogger(__name__)

# Rendering DPI
_DEFAULT_DPI = 200
_MAX_PAGES = 50


def is_pdf_file(path: Path) -> bool:
    """Determine if a file is a PDF."""
    return path.suffix.lower() == ".pdf"


def _get_total_pages(pdf_path: Path) -> int:
    """Get total page count of a PDF using pdfminer.six."""
    try:
        from pdfminer.pdfdocument import PDFDocument
        from pdfminer.pdfpage import PDFPage
        from pdfminer.pdfparser import PDFParser

        with open(pdf_path, "rb") as f:
            parser = PDFParser(f)
            doc = PDFDocument(parser)
            return sum(1 for _ in PDFPage.create_pages(doc))
    except Exception:
        return 0


def ocr_pdf(
    engine: OcrEngine,
    pdf_path: Path,
    task: str = "ocr_document",
    language: str = "auto",
    page_range: str = "",
    dpi: int = _DEFAULT_DPI,
) -> dict[str, Any]:
    """Rasterize each page of a PDF and run OCR.

    Args:
        engine: OCR engine
        pdf_path: PDF file path
        task: OCR task (ocr / ocr_document / ocr_manga)
        language: language hint
        page_range: page range ("1-5", "3", "" = all pages)
        dpi: rendering DPI

    Returns:
        { "pages": [...], "merged_text": str, "page_count": int, "total_pages": int }
    """
    from pdf2image import convert_from_path

    # DPI clamp (72 <= dpi <= 400)
    dpi = max(72, min(dpi, 400))

    total_pages = _get_total_pages(pdf_path)
    if total_pages == 0:
        return {"pages": [], "merged_text": "", "page_count": 0, "total_pages": 0}

    # Parse page range (0-based indices)
    pages_to_process = _parse_page_range(page_range, total_pages)
    if len(pages_to_process) > _MAX_PAGES:
        pages_to_process = pages_to_process[:_MAX_PAGES]
        logger.warning("PDF OCR: capped to %d pages", _MAX_PAGES)

    page_results: list[dict[str, Any]] = []

    for page_num in pages_to_process:
        t0 = time.monotonic()
        page_1based = page_num + 1

        try:
            images = convert_from_path(
                str(pdf_path),
                dpi=dpi,
                first_page=page_1based,
                last_page=page_1based,
            )
            if not images:
                raise RuntimeError("pdf2image returned no images")

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                images[0].save(tmp.name, "PNG")
                tmp_path = Path(tmp.name)

            try:
                result = engine.extract_text(tmp_path, task=task, language=language)
                elapsed = int((time.monotonic() - t0) * 1000)
                page_results.append({
                    "page": page_1based,
                    "full_text": result.full_text,
                    "regions_count": len(result.regions),
                    "regions": [r.to_dict() for r in result.regions],
                    "language": result.language,
                    "elapsed_ms": elapsed,
                })
            except Exception as exc:
                elapsed = int((time.monotonic() - t0) * 1000)
                logger.warning("OCR failed for page %d: %s", page_1based, exc)
                page_results.append({
                    "page": page_1based,
                    "full_text": "",
                    "error": str(exc),
                    "elapsed_ms": elapsed,
                })
            finally:
                tmp_path.unlink(missing_ok=True)

        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            logger.warning("Page render failed for page %d: %s", page_1based, exc)
            page_results.append({
                "page": page_1based,
                "full_text": "",
                "error": f"Render failed: {exc}",
                "elapsed_ms": elapsed,
            })

    merged = _merge_page_texts(page_results)

    return {
        "pages": page_results,
        "merged_text": merged,
        "page_count": len(page_results),
        "total_pages": total_pages,
    }


def ocr_pdf_to_result(
    engine: OcrEngine,
    pdf_path: Path,
    file_id: int | None = None,
    task: str = "ocr_document",
    language: str = "auto",
    page_range: str = "",
    dpi: int = _DEFAULT_DPI,
) -> OcrResult:
    """Convert PDF OCR results to OcrResult."""
    data = ocr_pdf(engine, pdf_path, task, language, page_range, dpi)

    regions = []
    for pr in data["pages"]:
        if pr.get("full_text"):
            regions.append(OcrRegion(
                region_id=pr["page"],
                text=pr["full_text"],
                label=f"page_{pr['page']}",
                direction="horizontal",
            ))

    return OcrResult(
        file_id=file_id,
        engine=engine.get_name(),
        task=task,
        regions=regions,
        full_text=data["merged_text"],
        language=language,
    )


def _parse_page_range(page_range: str, total: int) -> list[int]:
    """Convert page range string to index list.

    "1-5" → [0,1,2,3,4], "3" → [2], "" → [0..total-1]
    """
    if not page_range or not page_range.strip():
        return list(range(total))

    pages = set()
    for part in page_range.split(","):
        part = part.strip()
        if "-" in part:
            try:
                start, end = part.split("-", 1)
                s = max(1, int(start))
                e = min(total, int(end))
                pages.update(range(s - 1, e))
            except ValueError:
                continue
        else:
            try:
                p = int(part)
                if 1 <= p <= total:
                    pages.add(p - 1)
            except ValueError:
                continue

    return sorted(pages) if pages else list(range(total))


def _merge_page_texts(page_results: list[dict]) -> str:
    """Merge page results."""
    parts = []
    for pr in page_results:
        text = pr.get("full_text", "").strip()
        if text:
            page_num = pr.get("page", "?")
            parts.append(f"[Page {page_num}]\n{text}")
    return "\n\n".join(parts)
