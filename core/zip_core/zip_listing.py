"""ZIP image listing with multi-encoding fallback and timeout."""

import logging
import zipfile

from core.infra_core.encoding import ZIP_METADATA_ENCODINGS
from core.infra_core.timeout import ARCHIVE_LIST_TIMEOUT, ARCHIVE_MAX_ENTRY_SIZE, run_with_timeout

from .zip_path_resolve import _HAS_METADATA_ENCODING
from .zip_read_single import _read_zip_entry_checked

logger = logging.getLogger(__name__)


def _collect_images(zf: zipfile.ZipFile, extensions: tuple[str, ...]) -> list[str]:
    """Extract image entry names from an opened ZipFile.

    Skips password-protected entries (flag bit 0x1) since they cannot
    be read without a password.

    Nested ZIPs (ZIP-in-ZIP) are also scanned recursively.
    Nested entries use ``inner.zip!path/image.png`` notation so the
    final DB path becomes ``outer.zip!inner.zip!path/image.png``.
    """
    import io

    images: list[str] = []
    nested_zips: list[str] = []
    for info in zf.infolist():
        if info.filename.endswith("/"):
            continue
        if info.flag_bits & 0x1:
            logger.debug("Skipping encrypted entry: %s", info.filename)
            continue
        lower = info.filename.lower()
        if lower.endswith(extensions):
            images.append(info.filename)
        elif lower.endswith(".zip"):
            nested_zips.append(info.filename)

    # Recursively expand nested ZIPs (1 level only, prevent infinite recursion)
    for nested_name in nested_zips:
        try:
            nested_data = _read_zip_entry_checked(zf, nested_name, ARCHIVE_MAX_ENTRY_SIZE)
            with zipfile.ZipFile(io.BytesIO(nested_data), "r") as inner_zf:
                inner_images = _collect_images_flat(inner_zf, extensions)
                for inner_path in inner_images:
                    images.append(f"{nested_name}!{inner_path}")
            logger.debug("Nested ZIP %s: %d images", nested_name, len(inner_images))
        except Exception as exc:
            logger.debug("Cannot read nested ZIP %s: %s", nested_name, exc)
    return images


def _collect_images_flat(zf: zipfile.ZipFile, extensions: tuple[str, ...]) -> list[str]:
    """Extract image entries from a ZipFile (non-recursive, no nested ZIP)."""
    images: list[str] = []
    for info in zf.infolist():
        if info.filename.endswith("/"):
            continue
        if info.flag_bits & 0x1:
            continue
        if info.filename.lower().endswith(extensions):
            images.append(info.filename)
    return images


def _list_images_sync(
    zip_path: str,
    extensions: tuple[str, ...],
) -> list[str]:
    """Synchronous image listing with multi-encoding fallback.

    Tries multiple ``metadata_encoding`` values (Python 3.11+) so that
    Shift-JIS, EUC-JP, GBK, EUC-KR, Big5 archives all get correctly
    decoded filenames.  Falls back to default CP437 if all fail or if
    running on Python < 3.11.

    Handles corrupted, truncated, and password-protected ZIPs gracefully.
    """
    # Quick pre-check: reject obviously non-ZIP files
    if not zipfile.is_zipfile(zip_path):
        logger.debug("Not a valid ZIP: %s", zip_path)
        return []

    if _HAS_METADATA_ENCODING:
        encodings_tried: list[str] = []
        for enc in ZIP_METADATA_ENCODINGS:
            try:
                with zipfile.ZipFile(zip_path, "r", metadata_encoding=enc) as zf:
                    images = _collect_images(zf, extensions)
                logger.debug(
                    "ZIP listed OK with metadata_encoding=%s: %s (%d images)",
                    enc, zip_path, len(images),
                )
                return images
            except (zipfile.BadZipFile, zipfile.LargeZipFile) as e:
                # Structural ZIP problem -- no point trying more encodings
                logger.debug("ZIP structurally broken (%s): %s: %s", enc, zip_path, e)
                break
            except Exception as e:
                encodings_tried.append(enc)
                logger.debug("ZIP listing failed with %s: %s: %s", enc, zip_path, e)
                continue
        else:
            # All metadata_encoding attempts failed; fall through to default
            logger.debug(
                "ZIP metadata_encoding exhausted (%s), trying default: %s",
                encodings_tried, zip_path,
            )

    # Default: CP437 / UTF-8 (flag bit 11)
    with zipfile.ZipFile(zip_path, "r") as zf:
        return _collect_images(zf, extensions)


def list_images_in_zip(
    zip_path: str,
    extensions: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".webp", ".svg"),
    timeout: float = ARCHIVE_LIST_TIMEOUT,
) -> list[str]:
    """List image entries in ZIP archive with timeout protection.

    If the ZIP cannot be opened within *timeout* seconds (e.g. slow or
    dying drive, corrupted central directory), an empty list is returned
    and a warning is printed so the scan can continue.

    Handles: BadZipFile, password-protected, truncated, timeout,
    PermissionError, and any other exception.
    """
    try:
        return run_with_timeout(
            lambda: _list_images_sync(zip_path, extensions),
            timeout=timeout,
            label=zip_path,
        )
    except TimeoutError:
        logger.warning(f"ZIP listing timed out ({timeout}s): {zip_path}")
    except zipfile.BadZipFile as e:
        logger.warning(f"Corrupted ZIP (BadZipFile): {zip_path}: {e}")
    except PermissionError:
        logger.warning(f"Permission denied for ZIP: {zip_path}")
    except Exception as e:
        logger.warning(f"Failed to list ZIP contents: {zip_path}: {type(e).__name__}: {e}")
    return []
