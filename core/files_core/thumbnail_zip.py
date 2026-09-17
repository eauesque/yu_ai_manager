"""ZIP-backed thumbnail generation."""

import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from core.infra_core.debug_log import dlog
from core.infra_core.timeout import ARCHIVE_MAX_ENTRY_SIZE

from .media import (
    corrupt_file_placeholder,
    resolve_zip_target,
    zip_error_text,
)
from .response_types import FileError, FileResult
from .thumbnail_zip_handlers import handle_zip_target


def serve_zip_thumbnail(file_id: int, file_path_str: str, cache_path: Path, image_module, image_error) -> FileResult:
    import zipfile

    from core.helpers_core.helpers_text_path import split_archive_path
    zip_path_str, inner_path = split_archive_path(file_path_str)
    zip_path = Path(zip_path_str)

    logger.debug(f"ZIP thumbnail request: ZIP={zip_path} Internal={inner_path} ZIP exists={zip_path.exists()}")

    if not zip_path.exists():
        dlog("files", "thumbnail.zip_not_found", file_id=file_id, zip_path=str(zip_path), entry=inner_path)
        return FileError(
            zip_error_text(
                "ZIPファイルが見つかりません",
                zip_path=zip_path,
                internal_path=inner_path,
                hint="元ZIPが移動/削除されていないか確認してください",
            ), 404)

    try:
        # Nested ZIP detection: inner_path is in "inner.zip!file.jpg" format
        _is_nested = "!" in inner_path and inner_path.split("!", 1)[0].lower().endswith(".zip")

        if _is_nested:
            nested_zip_name, nested_file = inner_path.split("!", 1)
            from core.zip_core.zip_read_single import _read_zip_entry_checked
            with zipfile.ZipFile(zip_path, "r") as outer_zf, zipfile.ZipFile(
                io.BytesIO(_read_zip_entry_checked(outer_zf, nested_zip_name, ARCHIVE_MAX_ENTRY_SIZE)),
                "r",
            ) as inner_zf:
                inner_namelist = inner_zf.namelist()
                target = resolve_zip_target(inner_namelist, nested_file)
                if not target:
                    # Diagnostic: dump first few namelist entries so the user
                    # can see whether the DB-recorded inner_path matches what
                    # the archive actually contains (encoding / normalization).
                    dlog(
                        "files",
                        "thumbnail.zip_target_missing",
                        file_id=file_id,
                        zip_path=str(zip_path),
                        inner_path=inner_path,
                        nested=True,
                        namelist_size=len(inner_namelist),
                        namelist_sample=inner_namelist[:8],
                    )
                    return FileError(
                        zip_error_text(
                            "ネストZIP内に対象ファイルが見つかりません",
                            zip_path=zip_path,
                            internal_path=inner_path,
                            hint="再スキャンでZIP内エントリを更新してください",
                        ), 404)
                return handle_zip_target(inner_zf, zip_path, target, cache_path, image_module, image_error)
        else:
            with zipfile.ZipFile(zip_path, "r") as zf:
                namelist = zf.namelist()
                target = resolve_zip_target(namelist, inner_path)
                if not target:
                    dlog(
                        "files",
                        "thumbnail.zip_target_missing",
                        file_id=file_id,
                        zip_path=str(zip_path),
                        inner_path=inner_path,
                        nested=False,
                        namelist_size=len(namelist),
                        namelist_sample=namelist[:8],
                    )
                    return FileError(
                        zip_error_text(
                            "ZIP内に対象ファイルが見つかりません",
                            zip_path=zip_path,
                            internal_path=inner_path,
                            hint="再スキャンでZIP内エントリを更新してください",
                        ), 404)

                return handle_zip_target(zf, zip_path, target, cache_path, image_module, image_error)
    except zipfile.BadZipFile:
        logger.error(f"Bad ZIP file: {zip_path}")
        dlog("files", "thumbnail.bad_zip", file_id=file_id, zip_path=str(zip_path))
        return corrupt_file_placeholder(cache_path, "corrupt ZIP file")
    except Exception as e:
        logger.error(f"ZIP processing error: {e}")
        dlog("files", "thumbnail.zip_error", file_id=file_id, exc_type=type(e).__name__, detail=str(e))
        return corrupt_file_placeholder(cache_path, "ZIP read error")
