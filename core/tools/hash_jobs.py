"""Hash computation job processing."""

import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger(__name__)

from core.infra_core.file_hash import bytes_etag, file_etag, stream_etag
from core.jobs_core.jobs import job_manager
from core.services_core.db_api import get_raw_db, get_readonly_db
from core.services_core.db_write import submit_db_write
from core.tools.helpers import compute_phash

_BATCH_SIZE = 200
_MAX_WORKERS = min(8, (os.cpu_count() or 4))


def _ensure_phash_column_write() -> None:
    con = get_raw_db()
    try:
        con.execute("ALTER TABLE files ADD COLUMN phash TEXT")
        con.commit()
    except Exception as exc:
        logger.debug("phash column already exists or alter failed: %s", exc)


def _flush_hash_updates(updates: list[tuple[int, dict]]) -> None:
    """Apply a batch of hash/phash updates on the writer thread."""
    if not updates:
        return
    con = get_raw_db()
    for fid, fields in updates:
        set_clause = ", ".join(f"{k}=?" for k in fields)
        con.execute(
            f"UPDATE files SET {set_clause} WHERE id=?",
            (*fields.values(), fid),
        )
    con.commit()


def _compute_one(fid: int, path_str: str, hash_type: str, existing: dict) -> dict:
    """Compute hash/phash for one file. Pure I/O — no DB writes."""
    updates: dict = {}
    from core.helpers_core.helpers_text_path import is_archive_member, split_archive_path

    if is_archive_member(path_str) and hash_type in ("hash", "both"):
        if not existing.get("hash"):
            arc, entry = split_archive_path(path_str)
            try:
                if arc.lower().endswith(".zip"):
                    import zipfile

                    from core.zip_core.zip_path_resolve import _resolve_entry_name

                    with zipfile.ZipFile(arc, "r") as zf:
                        resolved = _resolve_entry_name(zf, entry)
                        info = zf.getinfo(resolved)
                        with zf.open(resolved) as src:
                            updates["hash"] = stream_etag(src, entry, size=info.file_size)
                elif arc.lower().endswith(".7z"):
                    from core.sevenz_core import sevenz_cli
                    from core.sevenz_core.sevenz_support_core import _resolve_entry_name

                    resolved = _resolve_entry_name(sevenz_cli.list_names(arc), entry)
                    with tempfile.TemporaryDirectory() as tmpdir:
                        sevenz_cli.extract_to_dir(arc, tmpdir, targets=[resolved])
                        extracted = Path(tmpdir, *resolved.split("/"))
                        if extracted.exists():
                            updates["hash"] = file_etag(extracted)
                elif arc.lower().endswith(".rar"):
                    import rarfile

                    from core.rar_core.rar_support_core import _resolve_entry_name

                    with rarfile.RarFile(arc, "r") as rf:
                        resolved = _resolve_entry_name(rf.namelist(), entry)
                        info = rf.getinfo(resolved)
                        with rf.open(resolved) as src:
                            updates["hash"] = stream_etag(src, entry, size=info.file_size)
                else:
                    from core.zip_core.zip_read_single import read_bytes_from_zip

                    file_bytes = read_bytes_from_zip(arc, entry)
                    updates["hash"] = bytes_etag(file_bytes, entry)
            except Exception:
                logger.warning("tools step failed", exc_info=True)
        # phash not supported for archive members
        return updates

    p = Path(path_str)
    if not p.exists():
        return updates

    if hash_type in ("hash", "both") and not existing.get("hash"):
        updates["hash"] = file_etag(p)

    if hash_type in ("phash", "both") and not existing.get("phash"):
        ph = compute_phash(p)
        if ph:
            updates["phash"] = ph

    return updates


def start_compute_hashes_job(db_path: Path, hash_type: str, limit: int):
    """Start a hash/phash computation job for files with missing hashes."""
    def compute_in_background():
        try:
            job = job_manager.start("hash", "ハッシュ計算")
        except ValueError:
            return

        try:
            if hash_type in ("phash", "both"):
                submit_db_write(_ensure_phash_column_write)

            conditions = []
            if hash_type == "hash":
                conditions.append("(hash IS NULL OR hash = '')")
            elif hash_type == "phash":
                conditions.append("(phash IS NULL OR phash = '')")
            else:
                conditions.append("(hash IS NULL OR hash = '' OR phash IS NULL OR phash = '')")

            ro = get_readonly_db()
            rows = ro.execute(
                f"SELECT id, path, hash, "
                f"{'phash' if hash_type in ('phash', 'both') else 'NULL'} AS phash "
                f"FROM files WHERE is_deleted=0 AND ({' OR '.join(conditions)}) LIMIT ?",
                (limit,),
            ).fetchall()

            total = len(rows)
            job.update(phase="computing_hashes", message=f"ハッシュ計算中... 0/{total}")
            job.progress(0, total)

            computed = 0
            done = 0
            pending: list[tuple[int, dict]] = []

            def _row_to_args(row):
                fid = row[0] if not hasattr(row, "keys") else row["id"]
                path_str = row[1] if not hasattr(row, "keys") else row["path"]
                existing = {
                    "hash": (row[2] if not hasattr(row, "keys") else row["hash"]),
                    "phash": (row[3] if not hasattr(row, "keys") else row["phash"]),
                }
                return fid, path_str, existing

            with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
                futures = {}
                for row in rows:
                    fid, path_str, existing = _row_to_args(row)
                    fut = ex.submit(_compute_one, fid, path_str, hash_type, existing)
                    futures[fut] = (fid, path_str)

                for fut in as_completed(futures):
                    fid, path_str = futures[fut]
                    try:
                        updates = fut.result()
                        if updates:
                            pending.append((fid, updates))
                            computed += 1
                    except Exception:
                        logger.warning("tools step failed", exc_info=True)
                    done += 1
                    if len(pending) >= _BATCH_SIZE:
                        submit_db_write(_flush_hash_updates, pending)
                        pending = []
                    if done % _BATCH_SIZE == 0 or done == total:
                        job.progress(done, total, path_str)
                        job.update(message=f"ハッシュ計算中... {done}/{total}")

            if pending:
                submit_db_write(_flush_hash_updates, pending)
            job.complete(f"完了: {computed}/{total} ファイルのハッシュを計算")
        except Exception as e:
            job.fail(str(e))

    import threading
    thread = threading.Thread(target=compute_in_background, daemon=True)
    thread.start()
