"""Special media handling: video keyframe extraction and archive member analysis."""

import contextlib
import shutil
import tempfile
from pathlib import Path

from core.helpers_core.helpers_text_path import is_archive_member, split_archive_path


def _extract_archive_member_to_temp(arc_path: str, inner: str, suffix: str, prefix: str) -> tuple[str, str]:
    """Extract one archive member to a dedicated temp dir and return (tmp_dir, path)."""
    tmp_dir = tempfile.mkdtemp(prefix=prefix)
    out_path = str(Path(tmp_dir) / f"payload{suffix}")
    lower = arc_path.lower()

    if lower.endswith(".7z"):
        from core.sevenz_core.sevenz_cli import extract_to_dir, list_names
        from core.sevenz_core.sevenz_support_core import _resolve_entry_name

        resolved = _resolve_entry_name(list_names(arc_path), inner)
        extract_to_dir(arc_path, tmp_dir, targets=[resolved])
        final = Path(tmp_dir).joinpath(*resolved.split("/"))
    elif lower.endswith(".rar"):
        import rarfile

        from core.rar_core.rar_support_core import _resolve_entry_name

        with rarfile.RarFile(arc_path, "r") as rf:
            resolved = _resolve_entry_name(rf.namelist(), inner)
            with rf.open(resolved) as src, open(out_path, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
        return tmp_dir, out_path
    else:
        import zipfile

        from core.zip_core.zip_path_resolve import _resolve_entry_name

        with zipfile.ZipFile(arc_path, "r") as zf:
            resolved = _resolve_entry_name(zf, inner)
            with zf.open(resolved) as src, open(out_path, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
        return tmp_dir, out_path

    # 7z extracts using original member path; move it to a stable filename.
    if not final.exists():
        raise FileNotFoundError(f"Failed to extract archive member: {inner}")
    final.replace(out_path)
    return tmp_dir, out_path


def _analyze_video(engine, file_path_str, existing_tags, existing_prompt, config, archive):
    """Analyze a video file (regular or archive member) via keyframe extraction."""
    if archive:
        arc_path, inner = split_archive_path(file_path_str)
        suffix = Path(inner).suffix or ".webm"
        tmp_dir, video_path = _extract_archive_member_to_temp(
            arc_path, inner, suffix, "yu_vid_"
        )
    else:
        tmp_dir = None
        video_path = file_path_str

    from core.files_core.video_keyframes import video_keyframes_context

    va_cfg = config.get("video_analysis", {})
    try:
        with video_keyframes_context(
            video_path,
            count=va_cfg.get("keyframe_count", 4),
            strategy=va_cfg.get("strategy", "uniform"),
            scene_threshold=va_cfg.get("scene_threshold", 0.4),
        ) as frames:
            if not frames:
                raise RuntimeError("Failed to extract keyframes from video")
            return engine.analyze_image(frames[0], existing_tags, existing_prompt)
    finally:
        if tmp_dir:
            import shutil
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _analyze_archive_image(engine, file_path_str, existing_tags, existing_prompt):
    """Extract image from ZIP/7z/RAR to a temp file, then analyze."""
    arc_path, inner = split_archive_path(file_path_str)
    suffix = Path(inner).suffix or ".jpg"
    tmp_dir, tmp_path_str = _extract_archive_member_to_temp(
        arc_path, inner, suffix, "yu_img_"
    )
    tmp_path = Path(tmp_path_str)
    try:
        return engine.analyze_image(tmp_path, existing_tags, existing_prompt)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _analyze_one_in_subprocess(file_id: int, file_path_str: str, config: dict):
    """Run single-file Hailo VLM analysis in a separate process.

    Uses multiprocessing.Pipe to receive the result without blocking
    the main process GIL during NPU inference.
    """
    import multiprocessing

    from core.hailo_device_core.hailo_npu_lock import HailoNpuLock
    from core.services_core.db_state import get_db_path

    # Acquire NPU lock before spawning subprocess
    npu_lock = HailoNpuLock(timeout=5.0)
    if not npu_lock.try_acquire():
        return (
            {"error": "Hailo NPUが別のプロセスで使用中です。後でもう一度お試しください。"},
            503,
        )

    result_conn, child_conn = multiprocessing.Pipe(duplex=False)

    try:
        proc = multiprocessing.Process(
            target=_subprocess_single_entry,
            args=(child_conn, file_id, file_path_str, str(get_db_path()), config),
            daemon=True,
            name="hailo-single-analysis",
        )
        proc.start()
        child_conn.close()

        # Timeout 120 seconds (VLM inference is slow)
        if result_conn.poll(timeout=120):
            data = result_conn.recv()
        else:
            proc.terminate()
            return {"error": "Hailo VLM 分析がタイムアウトしました (120秒)"}, 504

        proc.join(timeout=5)
        # Ensure process is terminated if join timed out
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=2)
            if proc.is_alive():
                proc.kill()
        result_conn.close()

        if "error" in data:
            return data, data.get("status", 500)
        return data, 200
    finally:
        # Always release lock after subprocess completes
        try:
            npu_lock.release()
        except Exception as e:
            import logging
            logging.error(f"Error releasing NPU lock: {e}")


def _subprocess_single_entry(
    conn, file_id: int, file_path_str: str, db_path: str, config: dict,
) -> None:
    """Execute single-file Hailo VLM analysis in a child process."""
    import ai_analysis
    from core.analysis_api.engine_resolver import _resolve_with_fallback
    from core.services_core.db_cipher import apply_key as _apply_key
    from core.services_core.db_cipher import sqlite3 as _cipher_sqlite3

    read_con = None
    write_con = None
    try:
        ai_config = config.get("ai_analysis", {})
        engine_type, engine_kwargs, err = _resolve_with_fallback(ai_config)
        if err:
            conn.send({"error": err, "status": 400})
            return

        engine = ai_analysis.get_engine(engine_type, **engine_kwargs)
        read_con = _cipher_sqlite3.connect(db_path, timeout=5.0)
        _apply_key(read_con)
        read_con.row_factory = _cipher_sqlite3.Row
        read_con.execute("PRAGMA query_only=ON")
        read_con.execute("PRAGMA journal_mode=WAL")
        write_con = _cipher_sqlite3.connect(db_path, timeout=30.0)
        _apply_key(write_con)
        write_con.row_factory = _cipher_sqlite3.Row
        write_con.execute("PRAGMA journal_mode=WAL")
        write_con.execute("PRAGMA busy_timeout=30000")
        write_con.execute("PRAGMA synchronous=NORMAL")

        tags_rows = read_con.execute(
            "SELECT t.tag FROM tags t "
            "JOIN file_tags ft ON t.id=ft.tag_id "
            "WHERE ft.file_id=?",
            (file_id,),
        )
        existing_tags = [r[0] for r in tags_rows]
        tmpl = read_con.execute(
            "SELECT raw_prompt FROM templates WHERE file_id=?",
            (file_id,),
        ).fetchone()
        existing_prompt = tmpl["raw_prompt"] if tmpl else None

        archive = is_archive_member(file_path_str)

        from core.files_core.media_types import is_video_file

        if is_video_file(file_path_str):
            result = _analyze_video(
                engine, file_path_str, existing_tags, existing_prompt,
                config, archive,
            )
        elif archive:
            result = _analyze_archive_image(
                engine, file_path_str, existing_tags, existing_prompt,
            )
        else:
            result = engine.analyze_image(
                Path(file_path_str), existing_tags, existing_prompt,
            )

        ai_analysis.save_analysis(write_con, file_id, engine.get_name(), result)

        conn.send({
            "success": True,
            "result": result.to_dict(),
            "engine": engine.get_name(),
        })
    except Exception as exc:
        import logging as _log
        _log.getLogger(__name__).error("Hailo VLM single analysis failed: %s", exc)
        conn.send({"error": "AI分析中にエラーが発生しました", "status": 500})
    finally:
        if read_con is not None:
            with contextlib.suppress(Exception):
                read_con.close()
        if write_con is not None:
            with contextlib.suppress(Exception):
                write_con.close()
