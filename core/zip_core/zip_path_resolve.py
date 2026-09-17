"""ZIP path normalization, name resolution, and isal acceleration."""

import logging
import os
import sys
import unicodedata
import zipfile

from core.infra_core.encoding import repair_cp437_name

logger = logging.getLogger(__name__)

# Python 3.11+ supports metadata_encoding parameter for ZipFile.
_HAS_METADATA_ENCODING = sys.version_info >= (3, 11)


# ---------------------------------------------------------------------------
# isal acceleration -- 2-5x faster DEFLATE decompression for zipfile
# ---------------------------------------------------------------------------
def _accelerate_zipfile() -> bool:
    """Replace zipfile's internal zlib with isal (Intel ISA-L).

    isal releases the GIL during DEFLATE, enabling true multi-core
    parallel decompression with ThreadPoolExecutor.
    """
    try:
        from isal import isal_zlib
        if not all(hasattr(isal_zlib, a) for a in ('decompress', 'decompressobj', 'crc32')):
            return False
        zipfile.zlib = isal_zlib  # type: ignore[attr-defined]
        zipfile.crc32 = isal_zlib.crc32  # type: ignore[attr-defined]
        return True
    except (ImportError, Exception):
        return False


_ISAL_AVAILABLE = _accelerate_zipfile()
if _ISAL_AVAILABLE:
    logger.info("isal acceleration enabled for ZIP decompression")


def _normalize_separators(path: str) -> str:
    """Normalize ZIP internal path separators.

    Rejects null bytes and parent directory traversal (..).
    """
    p = str(path or "").replace("\\", "/")
    # Remove null bytes
    p = p.replace("\x00", "")
    # Remove leading "./"
    while p.startswith("./"):
        p = p[2:]
    # Remove leading "/" (prevent absolute paths)
    p = p.lstrip("/")
    # Remove parent directory traversal
    parts = p.split("/")
    safe_parts = [part for part in parts if part and part != ".."]
    return "/".join(safe_parts)


def _name_variants(name: str) -> list[str]:
    """Generate Unicode normalization + CP437 repair variants."""
    base = _normalize_separators(name)
    variants = {base}
    variants.add(unicodedata.normalize("NFC", base))
    variants.add(unicodedata.normalize("NFKC", base))

    for repaired in repair_cp437_name(base):
        repaired_norm = _normalize_separators(repaired)
        variants.add(repaired_norm)
        variants.add(unicodedata.normalize("NFC", repaired_norm))
        variants.add(unicodedata.normalize("NFKC", repaired_norm))
    return [v for v in variants if v]


def _resolve_entry_name(zf: zipfile.ZipFile, internal_path: str) -> str:
    """Resolve an internal path to the actual entry name in the ZIP.

    Tries exact match first, then Unicode normalization variants,
    and finally basename-only match as a last resort.
    """
    names = zf.namelist()
    if internal_path in names:
        return internal_path

    variant_to_actual = {}
    for actual in names:
        for variant in _name_variants(actual):
            variant_to_actual.setdefault(variant, actual)

    for variant in _name_variants(internal_path):
        resolved = variant_to_actual.get(variant)
        if resolved is not None:
            return resolved

    target_name = os.path.basename(_normalize_separators(internal_path))
    if target_name:
        candidates = [n for n in names if os.path.basename(_normalize_separators(n)) == target_name]
        if len(candidates) == 1:
            return candidates[0]

    sample = names[:5]
    detail = (
        f"Entry not found: {internal_path!r} "
        f"(variants tried: {len(_name_variants(internal_path))}, "
        f"zip has {len(names)} entries, sample: {sample!r})"
    )
    raise KeyError(detail)


def is_zip_path(path: str) -> tuple[bool, str | None, str | None]:
    """Check whether a path is in zip entry form ``zip_path!internal_path``."""
    from core.helpers_core.helpers_text_path import is_archive_member, split_archive_path
    if not is_archive_member(path) and "!" not in path:
        return (False, None, None)

    zip_path, internal_path = split_archive_path(path)

    if os.path.exists(zip_path) and zipfile.is_zipfile(zip_path):
        return (True, zip_path, internal_path)
    return (False, None, None)
