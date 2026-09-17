"""Migration 78: re-normalize tag_name_normalized for compatibility low-line codepoints.

Six Unicode compatibility low-line / fullwidth-underscore codepoints
(U+FE33, U+FE34, U+FE4D, U+FE4E, U+FE4F, U+FF3F) were previously
mis-normalized because the pipeline ran underscore->space BEFORE NFKC.
NFKC of those characters produces an ASCII underscore that was never
converted, leaving a bare underscore in the stored value.

This migration re-normalizes only the rows whose tag_name contains one of
the six affected characters using a targeted LIKE scan.
"""
from __future__ import annotations

import logging
import sqlite3

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)

# The six compatibility codepoints whose NFKC form is ASCII underscore U+005F.
AFFECTED = "︳︴﹍﹎﹏＿"


def apply_migration_78(con: sqlite3.Connection) -> None:
    logger.info(
        "  -> Migration 78: re-normalize tag_name_normalized for compatibility low-line codepoints"
    )

    from core.schema_core.schema_connect import table_has_column

    if (
        not table_has_column(con, "file_wd_tags", "tag_name")
        or not table_has_column(con, "file_wd_tags", "tag_name_normalized")
    ):
        # Column doesn't exist yet — nothing to fix; just stamp the version.
        row = con.execute(
            "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (78,)
        ).fetchone()
        if row is None:
            set_schema_version(
                con, 78, "re-normalize tag_name_normalized for compatibility low-line codepoints"
            )
        return

    from core.tagging.tag_normalize import normalize_tag

    clauses = " OR ".join(["tag_name LIKE ?"] * len(AFFECTED))
    params = [f"%{ch}%" for ch in AFFECTED]
    rows = con.execute(
        f"SELECT id, tag_name FROM file_wd_tags WHERE {clauses}", params
    ).fetchall()

    updates = [(normalize_tag(r[1]), r[0]) for r in rows]
    if updates:
        con.executemany(
            "UPDATE file_wd_tags SET tag_name_normalized = ? WHERE id = ?", updates
        )

    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (78,)
    ).fetchone()
    if row is None:
        set_schema_version(
            con, 78, "re-normalize tag_name_normalized for compatibility low-line codepoints"
        )
