"""Schema migration 29: FTS5 rebuild with raw_negative + custom tokenizer."""

import logging
import sqlite3

logger = logging.getLogger(__name__)

from .schema_migrate_version import set_schema_version


def apply_migration_29(con: sqlite3.Connection) -> None:
    """Rebuild FTS5 table: add raw_negative + customize tokenizer."""
    logger.info("  -> Migration 29: Rebuilding FTS5 with raw_negative + custom tokenizer")

    # 1. Drop existing triggers
    con.execute("DROP TRIGGER IF EXISTS templates_ai")
    con.execute("DROP TRIGGER IF EXISTS templates_ad")
    con.execute("DROP TRIGGER IF EXISTS templates_au")

    # 2. Drop existing FTS table
    con.execute("DROP TABLE IF EXISTS templates_fts")

    # 3. Create new FTS table (added raw_negative + custom tokenizer)
    # tokenchars "_:." -- treat lora:name:0.8, 1girl etc. as intra-token chars
    # NOTE: tokenize outer quotes must be double-quotes, tokenchars value must use single-quotes
    #       (SQLite FTS5 parser constraint: outer single + inner double causes parse error)
    con.execute(
        '''
        CREATE VIRTUAL TABLE templates_fts
        USING fts5(
            raw_prompt,
            raw_negative,
            content='templates',
            content_rowid='id',
            tokenize="unicode61 tokenchars '_:.'"
        )
        '''
    )

    # 4. Create new triggers (sync both raw_prompt + raw_negative)
    con.execute(
        """
        CREATE TRIGGER templates_ai AFTER INSERT ON templates BEGIN
            INSERT INTO templates_fts(rowid, raw_prompt, raw_negative)
            VALUES (new.id, new.raw_prompt, new.raw_negative);
        END
        """
    )
    con.execute(
        """
        CREATE TRIGGER templates_ad AFTER DELETE ON templates BEGIN
            INSERT INTO templates_fts(templates_fts, rowid, raw_prompt, raw_negative)
            VALUES ('delete', old.id, old.raw_prompt, old.raw_negative);
        END
        """
    )
    con.execute(
        """
        CREATE TRIGGER templates_au AFTER UPDATE ON templates BEGIN
            INSERT INTO templates_fts(templates_fts, rowid, raw_prompt, raw_negative)
            VALUES ('delete', old.id, old.raw_prompt, old.raw_negative);
            INSERT INTO templates_fts(rowid, raw_prompt, raw_negative)
            VALUES (new.id, new.raw_prompt, new.raw_negative);
        END
        """
    )

    # 5. Rebuild FTS index from existing data
    con.execute("INSERT INTO templates_fts(templates_fts) VALUES('rebuild')")

    # 6. Record version
    set_schema_version(con, 29, "FTS5 rebuild: raw_negative + custom tokenizer")
