"""
Batch migration script to compress existing DB data with zstd.

Run AFTER Migration 53 (schema BLOB column changes) to compress existing
TEXT / uncompressed bytes into zstd-compressed blobs.

Usage:
    cd /path/to/yu_ai_manager
    python scripts/db_compress_migrate.py --dry-run   # Show estimated savings only
    python scripts/db_compress_migrate.py             # Compress and write

Notes:
    - Always back up before running
    - VACUUM runs automatically at the end unless --no-vacuum is specified
    - Large DBs may take several minutes to tens of minutes
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
# tags.db is SQLCipher-encrypted; route through the cipher shim and apply_key().
from core.services_core.db_cipher import apply_key, sqlite3  # noqa: E402
from core.utils.zstd_blob import ZSTD_MAGIC, compress_text  # noqa: E402

BATCH_SIZE = 500


def _is_already_compressed(blob) -> bool:
    return isinstance(blob, bytes) and blob[:4] == ZSTD_MAGIC


def migrate_column(
    con: sqlite3.Connection,
    table: str,
    id_col: str,
    text_col: str,
    dry_run: bool,
) -> tuple[int, int, int]:
    """Returns (rows_processed, bytes_before, bytes_after)."""
    rows = con.execute(
        f"SELECT {id_col}, {text_col} FROM {table} WHERE {text_col} IS NOT NULL"
    ).fetchall()

    bytes_before = bytes_after = 0
    updates = []

    for row_id, value in rows:
        if _is_already_compressed(value):
            continue  # Already compressed, skip

        raw = value.encode("utf-8") if isinstance(value, str) else value
        text = value if isinstance(value, str) else value.decode("utf-8")
        compressed = compress_text(text)

        bytes_before += len(raw)
        bytes_after  += len(compressed) if compressed else 0

        if not dry_run and compressed:
            updates.append((compressed, row_id))

    if not dry_run and updates:
        for i in range(0, len(updates), BATCH_SIZE):
            batch = updates[i : i + BATCH_SIZE]
            con.executemany(
                f"UPDATE {table} SET {text_col} = ? WHERE {id_col} = ?", batch
            )
            con.commit()
            done = min(i + BATCH_SIZE, len(updates))
            print(f"  {table}.{text_col}: committed {done}/{len(updates)}")

    return len(rows), bytes_before, bytes_after


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-vacuum", action="store_true")
    parser.add_argument("--db", default="")
    args = parser.parse_args()

    if args.db:
        db_path = args.db
    else:
        # Fall back to tags.db in the project root when running standalone
        # (get_db_path() requires server runtime initialization)
        default_path = Path(__file__).parent.parent / "tags.db"
        if default_path.exists():
            db_path = str(default_path)
        else:
            try:
                from core.services_core.db_state import get_db_path
                db_path = str(get_db_path())
            except RuntimeError:
                print("ERROR: DB path not found. Use --db <path> to specify the database file.")
                print(f"  Example: python {Path(__file__).name} --db tags.db")
                sys.exit(1)

    print(f"Target DB: {db_path}")
    con = sqlite3.connect(db_path)
    # Auto-detect plaintext vs SQLCipher-encrypted via file magic header so the
    # script remains usable on both the live runtime DB and plain test DBs.
    from core.services_core.db_migrate_encrypt import _is_plaintext  # noqa: E402
    if not _is_plaintext(Path(db_path)):
        apply_key(con)
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA busy_timeout=30000;")

    # NOTE: chat_messages.content is excluded because FTS5 sync triggers exist.
    # Compressing it would index byte sequences, breaking full-text search.
    targets = [
        ("analysis",          "id", "raw_response"),
        ("analysis",          "id", "quality_notes"),
        ("analysis",          "id", "prompt_suggestion"),
        ("file_annotations",  "id", "value"),
        # webhook_deliveries.payload_json excluded: write path does not compress,
        # so migrating existing rows creates a mixed state without benefit.
    ]

    total_before = total_after = 0
    for table, id_col, col in targets:
        try:
            n, b, a = migrate_column(con, table, id_col, col, args.dry_run)
            pct = (b - a) / b * 100 if b > 0 else 0
            tag = "[DRY]" if args.dry_run else "[DONE]"
            print(
                f"{tag} {table}.{col}: {n} rows | "
                f"{b/1024/1024:.1f}MB -> {a/1024/1024:.1f}MB ({pct:.0f}% reduction)"
            )
            total_before += b
            total_after  += a
        except Exception as e:
            print(f"[SKIP] {table}.{col}: {e}")

    print(f"\nTotal: {total_before/1024/1024:.1f}MB -> {total_after/1024/1024:.1f}MB")
    print(f"Estimated saving: {(total_before-total_after)/1024/1024:.1f}MB")

    if not args.dry_run and not args.no_vacuum:
        print("\nRunning VACUUM (may take several minutes on large DBs)...")
        con.execute("VACUUM")
        print("VACUUM done.")

    con.close()


if __name__ == "__main__":
    main()
