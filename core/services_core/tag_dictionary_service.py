"""Write helpers for tag dictionary persistence."""

from __future__ import annotations

from collections.abc import Callable


def clear_tag_dictionary(*, get_db_fn: Callable | None = None) -> int:
    if get_db_fn is None:
        from core.services_core.db_api import get_db as get_db_fn

    con = get_db_fn()
    count = con.execute("SELECT COUNT(*) FROM tag_dictionary").fetchone()[0]
    con.execute("DELETE FROM tag_dictionary")
    con.commit()
    return count


def import_tag_dictionary_batch(
    batch: list[tuple],
    *,
    get_db_fn: Callable | None = None,
) -> int:
    if get_db_fn is None:
        from core.services_core.db_api import get_db as get_db_fn

    con = get_db_fn()
    con.executemany(
        """INSERT INTO tag_dictionary (tag_name, category, post_count, aliases)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(tag_name) DO UPDATE SET
             category=excluded.category,
             post_count=excluded.post_count,
             aliases=excluded.aliases""",
        batch,
    )
    con.commit()
    return len(batch)
