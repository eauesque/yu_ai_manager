"""Schema migration steps 21-22: Scan exclude soft-delete + BUG-58/59/60 fixes."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version

# Directory names that should never contain user-generated AI images.
_TOOL_DIR_NAMES = [
    "venv", ".venv", "site-packages", "dist-packages",
    "node_modules", "__pycache__", ".git",
    "custom_nodes", "extensions-builtin", "extensions",
]


def apply_migration_21(con: sqlite3.Connection) -> None:
    """Soft-delete files in dev/tool directories (BUG-48).

    Marks files under venv, site-packages, custom_nodes, extensions,
    extensions-builtin, node_modules, .git, __pycache__ as is_deleted=1.
    Also adds 'extensions' to the default scan_exclude_dirs.
    """
    logger.info("  -> Migration 21: Soft-delete files in dev/tool directories (BUG-48)")

    total = 0
    for name in _TOOL_DIR_NAMES:
        # Match both Windows (\) and Unix (/) path separators
        for sep in ("\\", "/"):
            pat = f"%{sep}{name}{sep}%"
            count = con.execute(
                "UPDATE files SET is_deleted = 1 "
                "WHERE is_deleted = 0 AND path LIKE ?",
                (pat,),
            ).rowcount
            total += count

    if total:
        logger.info(f"     Soft-deleted {total} files in dev/tool directories")
    else:
        logger.info("     No dev/tool directory files found")

    set_schema_version(con, 21, f"Soft-delete dev/tool dir files ({total} files)")


def apply_migration_22(con: sqlite3.Connection) -> None:
    """BUG-58/59/60 data fixes.

    BUG-58: Restore meta_source for files incorrectly set to 'not_modified'.
            Infer correct meta_source from templates.format + file extension.
    BUG-59: Clear blocked A1111 parameter key namespaces (model, sampler, etc.)
    BUG-60: Delete space-joined garbage tags from <break> tag mis-processing.
    """
    import json as _json

    logger.info("  -> Migration 22: BUG-58/59/60 data fixes")

    # --- BUG-58: Restore meta_source='not_modified' records ---
    rows_58 = con.execute("""
        SELECT f.id, f.path, t.format, t.raw_meta_json
        FROM files f
        LEFT JOIN templates t ON t.id = f.id
        WHERE f.meta_source = 'not_modified' AND f.is_deleted = 0
    """).fetchall()

    fixed_58 = 0
    for fid, _path, fmt, raw_meta_json in rows_58:
        inferred = None
        # Try to infer from templates.format
        if fmt and fmt != "unknown":
            inferred = fmt
        # Try to infer from raw_meta_json
        if not inferred and raw_meta_json:
            try:
                obj = _json.loads(raw_meta_json)
                if isinstance(obj, dict) and (any(isinstance(v, dict) and "class_type" in v
                       for v in obj.values()) or "prompt" in obj or "workflow" in obj):
                    inferred = "comfy_png"
            except (_json.JSONDecodeError, TypeError):
                pass
        # Fallback: unknown (will be corrected on next rescan)
        if not inferred:
            inferred = "unknown"
        con.execute(
            "UPDATE files SET meta_source=? WHERE id=?", (inferred, fid)
        )
        fixed_58 += 1

    if fixed_58:
        logger.info(f"     BUG-58: Restored meta_source for {fixed_58} records")
    else:
        logger.info("     BUG-58: No 'not_modified' meta_source records found")

    # --- BUG-59: Clear blocked A1111 parameter key namespaces ---
    blocked_ns = [
        "model", "model hash", "sampler", "seed", "steps", "cfg scale",
        "clip skip", "size", "version", "vae", "vae hash",
        "denoising strength", "hires upscale", "hires steps",
        "hires upscaler", "rng", "schedule type", "token merging ratio",
    ]
    placeholders = ",".join("?" * len(blocked_ns))

    blocked_rows = con.execute(
        f"SELECT id, tag, namespace FROM tags "
        f"WHERE namespace IN ({placeholders})",
        blocked_ns,
    ).fetchall()

    fixed_59 = 0
    for tag_id, tag, _namespace in blocked_rows:
        # Check if a tag with namespace=NULL and same tag already exists
        existing = con.execute(
            "SELECT id FROM tags WHERE tag = ? AND namespace IS NULL LIMIT 1",
            (tag,),
        ).fetchone()
        if existing:
            # Merge: re-point file_tags to existing, then delete duplicate
            keep_id = existing[0]
            con.execute(
                "UPDATE file_tags SET tag_id = ? "
                "WHERE tag_id = ? AND NOT EXISTS ("
                "  SELECT 1 FROM file_tags ft2 "
                "  WHERE ft2.file_id = file_tags.file_id AND ft2.tag_id = ?)",
                (keep_id, tag_id, keep_id),
            )
            con.execute("DELETE FROM file_tags WHERE tag_id = ?", (tag_id,))
            con.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
        else:
            con.execute(
                "UPDATE tags SET namespace = NULL WHERE id = ?", (tag_id,)
            )
        fixed_59 += 1

    if fixed_59:
        logger.info(f"     BUG-59: Cleared {fixed_59} blocked namespace tags")

    # --- BUG-60: Delete space-joined garbage tags from <break> mis-processing ---
    garbage_rows = con.execute("""
        SELECT id FROM tags
        WHERE tag LIKE '%% %%'
        AND LENGTH(tag) > 30
        AND (tag LIKE '%% %% %%' OR LENGTH(tag) > 50)
    """).fetchall()

    garbage_ids = [r[0] for r in garbage_rows]
    if garbage_ids:
        ph = ",".join("?" * len(garbage_ids))
        deleted_ft = con.execute(
            f"DELETE FROM file_tags WHERE tag_id IN ({ph})", garbage_ids
        ).rowcount
        deleted_t = con.execute(
            f"DELETE FROM tags WHERE id IN ({ph})", garbage_ids
        ).rowcount
        logger.info(f"     BUG-60: Deleted {deleted_t} space-joined garbage tags "
              f"({deleted_ft} file_tags)")
    else:
        logger.info("     BUG-60: No space-joined garbage tags found")

    # Final orphan cleanup
    orphan_count = con.execute(
        "DELETE FROM tags WHERE id NOT IN "
        "(SELECT DISTINCT tag_id FROM file_tags)"
    ).rowcount
    if orphan_count:
        logger.info(f"     Cleaned {orphan_count} orphan tags")

    set_schema_version(con, 22, "BUG-58/59/60 data fixes")
