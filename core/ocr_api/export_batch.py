"""OCR API -- batch export and overlay helpers."""

from __future__ import annotations

import logging

from quart import send_file

from core.infra_core.api_errors import api_error, api_result
from core.ocr_api.helpers import resolve_image_path
from core.services_core.app_runtime_state import get_config

logger = logging.getLogger(__name__)


def _resolve_export_dir(output_dir):
    """Return an export directory only when it remains under its configured root."""
    from pathlib import Path

    if not isinstance(output_dir, str) or "\0" in output_dir:
        return None, "output_dir contains a null byte"

    root_value = get_config().get("ocr_export_dir", "")
    if not isinstance(root_value, str) or not root_value or "\0" in root_value:
        return None, "Server-side OCR export directory is not configured"

    try:
        root = Path(root_value).resolve(strict=True)
        if not root.is_dir():
            return None, "Server-side OCR export directory is not a directory"
        candidate = Path(output_dir).resolve(strict=False)
        candidate.relative_to(root)
    except (OSError, ValueError):
        return None, "output_dir must remain under the configured OCR export directory"
    return candidate, None


def batch_export_to_dir(
    ocr_results, fmt, output_dir, file_paths, *,
    overlay_mode="translated", target_lang="", con=None,
    translations_map=None, full_text_map=None,
):
    """Save OCR results directly to a server-side directory."""
    from core.ocr_core.export import export_ocr

    out, err = _resolve_export_dir(output_dir)
    if err:
        return api_error(err, 403)
    try:
        out.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return api_error(f"Cannot create output directory: {exc}", 500)

    saved = []
    errors = []
    is_overlay = fmt == "overlay"

    for ocr in ocr_results:
        fid = ocr.file_id or 0
        try:
            if is_overlay:
                save_overlay_to_dir(
                    ocr,
                    fid,
                    out,
                    file_paths,
                    overlay_mode,
                    target_lang,
                    translations=(translations_map or {}).get(fid),
                    translated_full_text=(full_text_map or {}).get(fid, ""),
                )
                saved.append({"file_id": fid, "format": "overlay"})
            else:
                trans = (translations_map or {}).get(fid)
                full = (full_text_map or {}).get(fid, "")
                content, filename, _ = export_ocr(
                    ocr, fmt,
                    translations=trans,
                    translated_full_text=full,
                    target_lang=target_lang,
                )
                dest = out / filename
                dest.write_bytes(content)
                saved.append({"file_id": fid, "path": str(dest)})
        except Exception as exc:
            logger.warning("Batch export failed for file_id=%d: %s", fid, exc)
            errors.append({"file_id": fid, "error": str(exc)})

    return api_result({
        "saved": len(saved),
        "errors": len(errors),
        "output_dir": str(out),
        "results": saved,
        "error_details": errors,
    })


def save_overlay_to_dir(
    ocr,
    fid,
    out_dir,
    file_paths,
    mode,
    target_lang,
    *,
    translations=None,
    translated_full_text="",
):
    """Save a single overlay image to a directory."""
    from core.ocr_core.overlay import generate_overlay

    src_path = file_paths.get(fid)
    if not src_path:
        raise RuntimeError("Source file path not found")

    with resolve_image_path(src_path) as (image_path, path_err):
        if path_err:
            raise RuntimeError(path_err)
        img_bytes = generate_overlay(
            image_path, ocr,
            translations=translations if translations else None,
            mode=mode,
            output_format="PNG",
            translated_full_text=translated_full_text,
            target_lang=target_lang,
        )

    dest = out_dir / f"ocr_overlay_{fid}.png"
    dest.write_bytes(img_bytes)


async def batch_overlay_download(
    ocr_results,
    file_paths,
    mode,
    target_lang,
    translations_map=None,
    full_text_map=None,
):
    """Generate overlay images and return as a ZIP download."""
    import io
    import zipfile

    from core.ocr_core.overlay import generate_overlay

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for ocr in ocr_results:
            fid = ocr.file_id or 0
            src_path = file_paths.get(fid)
            if not src_path:
                continue
            try:
                translations = (translations_map or {}).get(fid)
                translated_full_text = (full_text_map or {}).get(fid, "")

                with resolve_image_path(src_path) as (image_path, path_err):
                    if path_err:
                        continue
                    img_bytes = generate_overlay(
                        image_path, ocr,
                        translations=translations if translations else None,
                        mode=mode,
                        output_format="PNG",
                        translated_full_text=translated_full_text,
                        target_lang=target_lang,
                    )
                zf.writestr(f"ocr_overlay_{fid}.png", img_bytes)
            except Exception as exc:
                logger.warning("Overlay generation skipped for file_id=%d: %s", fid, exc)

    return await send_file(
        io.BytesIO(buf.getvalue()),
        mimetype="application/zip",
        as_attachment=True,
        attachment_filename="ocr_overlay_batch.zip",
    )
