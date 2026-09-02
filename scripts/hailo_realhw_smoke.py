#!/usr/bin/env python3
"""Reusable real-hardware smoke test for the native Hailo-10H Rust stack.

Exercises yu-server's hailort proxy routes, the hailo-genai native chat
and VLM generation paths, and the hailo-genai model status/download routes
against the REAL Hailo-10H device (no mocking).

Usage:
    uv run python scripts/hailo_realhw_smoke.py [--keep-scratch]

Requires:
    - crates/target/debug/{yu-server,yu-infer} already built
    - HEF models under ~/hailo_models/ (see MODEL_HEF_MAP below)
    - /dev/h1x-0 present and not held by another process

Never touches the real data/tags.db or repo-root config.json: builds a
fresh scratch DB (auto-migrated on first connect, see main.rs
`tagdb_core::connect`) and a minimal scratch config.json under
.cargo_tmp/hailo_realhw_smoke/ on every run.
"""
import contextlib
import json
import logging
import os
import shutil
import signal
import struct
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parent.parent
SCRATCH = REPO / ".cargo_tmp" / "hailo_realhw_smoke"
DB_PATH = SCRATCH / "test-tags.db"
CONFIG_PATH = SCRATCH / "config.json"
IMG_PATH = SCRATCH / "test.png"
PORT = 18765
BASE = f"http://127.0.0.1:{PORT}"
YU_SERVER = REPO / "crates" / "target" / "debug" / "yu-server"
YU_INFER = REPO / "crates" / "target" / "debug" / "yu-infer"

results = []  # (name, ok, detail)


def record(name, ok, detail=""):
    results.append((name, ok, detail))
    tag = "PASS" if ok else "FAIL"
    print(f"[{tag}] {name}: {detail}")


def make_png(path: Path, w=64, h=64):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        for x in range(w):
            raw.extend([(x * 255) // w, (y * 255) // h, 128])
    idat = zlib.compress(bytes(raw), 9)
    with open(path, "wb") as f:
        f.write(sig)
        f.write(chunk(b"IHDR", ihdr))
        f.write(chunk(b"IDAT", idat))
        f.write(chunk(b"IEND", b""))


def http(method, path, body=None, timeout=120, headers=None):
    url = BASE + path
    data = None
    hdrs = {"Content-Type": "application/json", "X-Requested-With": "hailo-smoke-test"}
    if headers:
        hdrs.update(headers)
    if body is not None:
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw.decode(errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw.decode(errors="replace")


def http_multipart(path, fields, file_field, filename, file_bytes, timeout=120):
    """POST a multipart/form-data request (stdlib only, hand-rolled body --
    this repo has no `requests` dependency)."""
    boundary = "----hailo-smoke-boundary-x7f3q9"
    parts = []
    for key, value in fields.items():
        parts.append(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()
        )
    parts.append(
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{file_field}\"; "
        f"filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode()
        + file_bytes
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode())
    data = b"".join(parts)
    req = urllib.request.Request(
        BASE + path, data=data, method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "X-Requested-With": "hailo-smoke-test",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw.decode(errors="replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw.decode(errors="replace")


def make_wav(path: Path, seconds=1.0, sample_rate=16000):
    """A silent 16-bit PCM mono WAV -- enough to exercise the transcribe
    pipeline without needing real speech (matches the sidecar's own
    #[ignore] real-hw test, which uses the same silent-audio approach)."""
    import wave

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * int(seconds * sample_rate))


def make_video_with_audio(path: Path, seconds=1.0):
    """A tiny synthetic MP4 (color bars + a sine tone) via ffmpeg -- enough
    to exercise the video -> ffmpeg audio-extraction path end to end."""
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"testsrc=size=64x64:rate=5:duration={seconds}",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
            "-shortest", str(path),
        ],
        check=True, capture_output=True,
    )


def sse_post(path, body, timeout=180):
    """POST and read an SSE response, returning list of parsed data events."""
    url = BASE + path
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "X-Requested-With": "hailo-smoke-test",
        },
    )
    events = []
    start = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        buf = b""
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n\n" in buf:
                block, buf = buf.split(b"\n\n", 1)
                for line in block.split(b"\n"):
                    if line.startswith(b"data: "):
                        with contextlib.suppress(json.JSONDecodeError):
                            events.append(json.loads(line[6:].decode()))
            if events and events[-1].get("done"):
                break
            if time.time() - start > timeout:
                break
    return events


def wait_health(timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            status, _ = http("GET", "/", timeout=3)
            if status == 200:
                return True
        except Exception:
            logger.debug("step failed", exc_info=True)
        time.sleep(0.5)
    return False


def device_holders():
    """Best-effort: list PIDs with an open FD on /dev/h1x-0."""
    holders = []
    for proc_dir in Path("/proc").glob("[0-9]*"):
        fd_dir = proc_dir / "fd"
        try:
            for fd in fd_dir.iterdir():
                try:
                    if os.readlink(fd) == "/dev/h1x-0":
                        holders.append(proc_dir.name)
                except OSError:
                    continue
        except (PermissionError, FileNotFoundError, NotADirectoryError):
            continue
    return holders


def build_plain_scratch_db(db_path: Path):
    """Build a fully-migrated, UNENCRYPTED scratch tags.db from scratch,
    containing zero real user data and requiring zero credentials of any
    kind (no SQLCipher key, real or app-constant).

    A bare/fresh 0-byte SQLite file has no base schema at all
    (`schema_version` is created by the legacy Python migration path, not by
    Rust — `tagdb_core::apply_pending_rust_migrations` requires it to
    already exist first). The Python app's own DB helpers
    (`core.tagdb_core.db_schema.tagdb_db_schema_common.connect_db`,
    `core.schema_core.schema_connect.connect_db`) always apply the app's
    SQLCipher key via `db_cipher.apply_key()`, so this deliberately calls
    the lower-level `init_db(con, enable_fts=True)` / `migrate_db(con)`
    functions directly on a connection opened with the *plain stdlib*
    `sqlite3` module (bypassing `db_cipher` entirely) — the same schema and
    migration logic, just never touching any encryption key. Rust's
    yu-server opens unencrypted DBs fine whenever `--db-key`/`YU_DB_KEY` is
    left unset (the `cli.db_key.is_empty()` branch in `main.rs`).
    """
    import sqlite3 as stdlib_sqlite3

    repo_str = str(REPO)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)
    from core import paths as core_paths

    scratch_root = db_path.resolve().parent
    core_paths.init_app_paths(
        data_dir=scratch_root / "app_data",
        cache_dir=scratch_root / "app_cache",
        log_dir=scratch_root / "app_logs",
        profiles_dir=scratch_root / "app_profiles",
    )
    from core.schema_core.schema_init import init_db
    from core.schema_core.schema_migrate import migrate_db
    from core.services_core import db_cipher

    con = stdlib_sqlite3.connect(str(db_path))
    con.row_factory = stdlib_sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA foreign_keys=ON;")
    init_db(con, enable_fts=True)
    # Migration 55 (file_vectors -> vectors.db) always calls db_cipher.apply_key()
    # on the vectors.db connection it opens, independent of whether *this*
    # connection is keyed. Left alone, vectors.db comes out SQLCipher-encrypted
    # with the app-constant key while tags.db stays plain -- and yu-server (no
    # YU_DB_KEY here, matching the plain tags.db) then fails to open it
    # ("file is not a database"). No-op the key application for this
    # migration run so vectors.db stays as credential-free as tags.db.
    original_apply_key = db_cipher.apply_key
    db_cipher.apply_key = lambda _con: None
    try:
        migrate_db(con)
    finally:
        db_cipher.apply_key = original_apply_key
    con.commit()
    con.close()


def setup_scratch():
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir(parents=True)
    config = {
        "scan_roots": [{"path": str(SCRATCH)}],
        "extensions": {
            "builtin-hailo-genai": {
                "default_llm_model": "qwen3-1.7b-instruct",
                "default_vlm_model": "qwen3-vl-2b-instruct",
            }
        },
    }
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    make_png(IMG_PATH)
    # NEVER run the test server against the real data/tags.db (or a
    # decrypted copy of it) — build a fresh, unencrypted, schema-complete,
    # zero-real-data scratch DB instead. See build_plain_scratch_db().
    build_plain_scratch_db(DB_PATH)


def insert_test_file_row(image_path=IMG_PATH):
    import sqlite3
    con = sqlite3.connect(str(DB_PATH))
    cur = con.cursor()
    cur.execute("PRAGMA table_info(files)")
    cols = {row[1] for row in cur.fetchall()}
    now = int(time.time())
    fields = {"path": str(image_path), "is_deleted": 0}
    if "filename" in cols:
        fields["filename"] = image_path.name
    if "size" in cols:
        fields["size"] = image_path.stat().st_size
    if "mtime" in cols:
        fields["mtime"] = now
    if "created_at" in cols:
        fields["created_at"] = now
    if "modified_at" in cols:
        fields["modified_at"] = now
    if "mime_type" in cols:
        fields["mime_type"] = "image/png"
    if "parser_version" in cols:
        fields["parser_version"] = 6
    keys = [k for k in fields if k in cols]
    placeholders = ",".join("?" for _ in keys)
    sql = f"INSERT INTO files ({','.join(keys)}) VALUES ({placeholders})"
    cur.execute(sql, [fields[k] for k in keys])
    con.commit()
    file_id = cur.lastrowid
    con.close()
    return file_id


def spawn_server(env):
    return subprocess.Popen(
        [
            str(YU_SERVER),
            "--host", "127.0.0.1",
            "--port", str(PORT),
            "--db", str(DB_PATH),
            "--config", str(CONFIG_PATH),
            "--secret", "hailo-smoke-test-secret",
            "--standalone",
            "--no-quick-lock",
        ],
        cwd=str(REPO),
        env=env,
    )


def stop_server(proc):
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
    time.sleep(1)


def restart_server(proc, env, reason):
    """Kills and respawns yu-server (and its yu-infer child) so a fresh
    process picks the next request's GenAI model as its one resident model.

    HailoRT 5.x allows exactly one resident GenAI (LLM/VLM/S2T share one
    slot) model per process lifetime -- see
    docs/development/development_docs/HAILO_RUST_MIGRATION_REMAINING_WORK.md
    ("1 GenAI モデル / Pi reboot が上限"). Switching GenAI model families
    (e.g. the raw /api/hailort/llm/* default model -> hailo-genai chat's
    configured default_llm_model -> hailo-genai's default_vlm_model) within
    one process produces a 409 HEF conflict, not a code bug -- restarting is
    the only way to free the slot without a full Pi reboot.
    """
    print(f"\n--- restarting yu-server ({reason}) ---")
    stop_server(proc)
    new_proc = spawn_server(env)
    if not wait_health():
        record("server_restart", False, f"yu-server did not become healthy again after: {reason}")
        # Without this, main()'s `finally` still holds the OLD (already-dead)
        # proc reference -- since we raise before returning new_proc, nothing
        # would ever stop it, orphaning it and whatever HailoRT device handle
        # its yu-infer child grabbed.
        stop_server(new_proc)
        raise RuntimeError(f"server restart failed: {reason}")
    time.sleep(2)  # let the fresh yu-infer child attach to the HailoRT device
    return new_proc


def main():
    keep = "--keep-scratch" in sys.argv
    if not YU_SERVER.exists() or not YU_INFER.exists():
        print("ERROR: yu-server/yu-infer debug binaries not found; build first.")
        sys.exit(2)

    setup_scratch()

    env = os.environ.copy()
    env.pop("YU_INFER_STANDALONE", None)
    # Must not inherit the operator's real dotenv (~/.config/yu/server.env,
    # which can re-inject YU_PIN/lan-bind) or a repo-root launch-args.txt
    # (which can silently add --lan/--pin) — see main.rs load_dotenv_files /
    # load_launch_args_file doc comments. We DO explicitly forward YU_DB_KEY
    # (read directly below, never printed) since our scratch DB is a copy of
    # the real encrypted DB and needs the same key to open.
    env["YU_SKIP_DOTENV_FILES"] = "1"
    env["YU_SKIP_LAUNCH_ARGS_FILE"] = "1"
    env.pop("YU_PIN", None)
    env.pop("YU_DB_KEY", None)  # scratch DB is unencrypted; no key needed
    proc = spawn_server(env)

    try:
        if not wait_health():
            record("server_startup", False, "yu-server did not become healthy in time")
            print("\n=== SUMMARY ===")
            passed = sum(1 for _, ok, _ in results if ok)
            for name, ok, _detail in results:
                print(f"{'PASS' if ok else 'FAIL'}  {name}")
            print(f"\n{passed}/{len(results)} passed")
            sys.exit(1)
        record("server_startup", True, f"pid={proc.pid}")

        # Give yu-infer (spawned child) a moment to load HailoRT device.
        time.sleep(2)

        # --- A: yolo/metadata ---
        try:
            status, body = http("GET", "/api/hailort/yolo/metadata", timeout=60)
            ok = status == 200 and isinstance(body, dict) and body.get("ok")
            record("A_yolo_metadata", ok, str(body)[:300])
        except Exception as e:
            record("A_yolo_metadata", False, repr(e))

        # --- B: yolo/smoke-zero ---
        try:
            t0 = time.time()
            status, body = http("POST", "/api/hailort/yolo/smoke-zero", timeout=60)
            dt = time.time() - t0
            ok = status == 200 and isinstance(body, dict) and body.get("ok")
            record("B_yolo_smoke_zero", ok, f"{dt:.2f}s {str(body)[:200]}")
        except Exception as e:
            record("B_yolo_smoke_zero", False, repr(e))

        # --- C: llm/tokenize ---
        try:
            status, body = http("POST", "/api/hailort/llm/tokenize",
                                 {"text": "What is the capital of France?"}, timeout=60)
            ok = status == 200 and isinstance(body, dict) and body.get("ok")
            record("C_llm_tokenize", ok, str(body)[:300])
        except Exception as e:
            record("C_llm_tokenize", False, repr(e))

        # --- D: llm/generate ---
        # Raw generate_text() feeds the prompt straight to the model with no
        # chat template (yu-hailo-infer shim.cpp: "the plain-string generate()
        # overload does not apply the model's chat template"). Measured on
        # this device (2026-08-24): a question-style prompt produces a
        # response quickly (~2s) but the instruct model, never having been
        # trained to answer un-templated raw text, free-associates into
        # a different question rather than answering -- so asserting on
        # answer *content* here is testing the wrong thing. A
        # completion-style prefix ("The capital of France is") was tried as
        # a fix and made it worse: it ran to the full 90s timeout with no
        # output at all (HAILO_TIMEOUT), since nothing in that mode signals
        # the model to stop. This primitive's job is proven correct by the
        # templated path instead (F3/F4 hailo-genai chat, which *does* apply
        # the chat template and does assert on recalled content). D only
        # smoke-checks that raw generation completes and returns text at
        # all, matching how A/B/C/E treat these low-level primitives.
        try:
            t0 = time.time()
            status, body = http("POST", "/api/hailort/llm/generate",
                                 {"prompt": "What is the capital of France? Answer in one word.",
                                  "timeout_ms": 90000}, timeout=100)
            dt = time.time() - t0
            text = ""
            if isinstance(body, dict) and body.get("ok"):
                outer = body.get("data") or {}
                inner = outer.get("data") or outer
                if isinstance(inner, dict):
                    value = inner.get("text") or inner.get("generated_text")
                    if isinstance(value, str):
                        text = value
            ok = status == 200 and isinstance(body, dict) and body.get("ok") and len(text.strip()) > 0
            record("D_llm_generate", ok, f"{dt:.2f}s text={text[:200]!r}")
        except Exception as e:
            record("D_llm_generate", False, repr(e))

        # --- E: speech2text/tokenize ---
        try:
            status, body = http("POST", "/api/hailort/speech2text/tokenize",
                                 {"text": "hello world"}, timeout=60)
            ok = status == 200 and isinstance(body, dict) and body.get("ok")
            record("E_speech2text_tokenize", ok, str(body)[:300])
        except Exception as e:
            record("E_speech2text_tokenize", False, repr(e))

        # A-E resided the raw /api/hailort/llm/* default model (whichever HEF
        # yu-infer picks with no hef_path override). F's hailo-genai chat
        # loads config's default_llm_model instead -- restart so the two
        # don't fight over the single GenAI residency slot.
        proc = restart_server(proc, env, "raw hailort LLM -> hailo-genai chat LLM")

        # --- F: hailo-genai chat multi-turn ---
        conv_id = None
        try:
            status, body = http("POST", "/ext/hailo-genai/api/chat/new", {}, timeout=30)
            ok = status == 200 and body.get("status") == "ok"
            conv_id = (body.get("conversation") or {}).get("id")
            record("F1_chat_new", ok, f"conv_id={conv_id}")

            status, body = http("GET", "/ext/hailo-genai/api/chat/active", timeout=30)
            ok = status == 200 and body.get("conversation_id") == conv_id
            record("F2_chat_active", ok, str(body)[:200])

            t0 = time.time()
            ev1 = sse_post("/ext/hailo-genai/api/chat/send",
                            {"content": "My favorite color is teal. Please remember that.",
                             "conversation_id": conv_id}, timeout=120)
            dt1 = time.time() - t0
            turn1_text = (ev1[-1].get("full_text") if ev1 else "") or ""
            record("F3_chat_turn1", bool(ev1) and ev1[-1].get("done"), f"{dt1:.2f}s reply={turn1_text[:150]!r}")

            t0 = time.time()
            ev2 = sse_post("/ext/hailo-genai/api/chat/send",
                            {"content": "What is my favorite color?",
                             "conversation_id": conv_id}, timeout=120)
            dt2 = time.time() - t0
            turn2_text = (ev2[-1].get("full_text") if ev2 else "") or ""
            recalled = "teal" in turn2_text.lower()
            record("F4_chat_turn2_recall", bool(ev2) and ev2[-1].get("done") and recalled,
                   f"{dt2:.2f}s reply={turn2_text[:150]!r}")
        except Exception as e:
            record("F_chat_multiturn", False, repr(e))

        # --- G: conversations CRUD ---
        try:
            status, body = http("GET", "/ext/hailo-genai/api/chat/conversations", timeout=30)
            ok = status == 200 and body.get("status") == "ok" and any(
                c.get("id") == conv_id for c in body.get("conversations", []))
            record("G1_conversations_list", ok, f"count={len(body.get('conversations', []))}")

            status, body = http("GET", f"/ext/hailo-genai/api/chat/conversations/{conv_id}", timeout=30)
            ok = status == 200 and body.get("status") == "ok" and len(
                (body.get("conversation") or {}).get("messages", [])) >= 4
            record("G2_conversation_get", ok, f"messages={len((body.get('conversation') or {}).get('messages', []))}")

            status, body = http("PATCH", f"/ext/hailo-genai/api/chat/conversations/{conv_id}/title",
                                 {"title": "Teal Test"}, timeout=30)
            ok = status == 200 and body.get("status") == "ok" and body.get("title") == "Teal Test"
            record("G3_conversation_rename", ok, str(body)[:200])

            status, body = http("DELETE", f"/ext/hailo-genai/api/chat/conversations/{conv_id}", timeout=30)
            ok = status == 200 and body.get("status") == "ok"
            record("G4_conversation_delete", ok, str(body)[:200])

            status, body = http("GET", f"/ext/hailo-genai/api/chat/conversations/{conv_id}", timeout=30)
            ok = status == 404
            record("G5_conversation_get_after_delete_404", ok, f"status={status}")
        except Exception as e:
            record("G_conversations_crud", False, repr(e))

        # F/G resided config's default_llm_model. H loads default_vlm_model
        # (a different HEF) -- same single-GenAI-slot constraint as above.
        proc = restart_server(proc, env, "hailo-genai chat LLM -> hailo-genai VLM")

        # --- H: VLM native generate ---
        try:
            file_id = insert_test_file_row()
            t0 = time.time()
            ev = sse_post("/ext/hailo-genai/api/vlm/generate",
                          {"prompt": "Describe this image in one sentence.", "file_id": file_id},
                          timeout=150)
            dt = time.time() - t0
            vlm_text = ""
            for e_ in ev:
                if "full_text" in e_:
                    vlm_text = e_["full_text"]
            if not vlm_text and ev:
                vlm_text = "".join(e_.get("token", "") for e_ in ev)
            ok = len(vlm_text.strip()) > 5
            record("H_vlm_generate", ok, f"{dt:.2f}s text={vlm_text[:250]!r}")
        except Exception as e:
            record("H_vlm_generate", False, repr(e))

        # --- I: edge cases ---
        try:
            status, body = http("POST", "/ext/hailo-genai/api/vlm/generate",
                                 {"prompt": "describe", "file_id": 999999999}, timeout=30)
            ok = status == 404
            record("I1_vlm_invalid_file_id_404", ok, f"status={status} body={str(body)[:150]}")
        except Exception as e:
            record("I1_vlm_invalid_file_id_404", False, repr(e))

        try:
            status, body = http("GET", "/ext/hailo-genai/api/chat/conversations/999999999", timeout=30)
            ok = status == 404
            record("I2_conversation_nonexistent_404", ok, f"status={status}")
        except Exception as e:
            record("I2_conversation_nonexistent_404", False, repr(e))

        try:
            status, body = http("POST", "/ext/hailo-genai/api/chat/send", {"content": ""}, timeout=30)
            ok = status == 400
            record("I3_chat_empty_content_400", ok, f"status={status} body={str(body)[:150]}")
        except Exception as e:
            record("I3_chat_empty_content_400", False, repr(e))

        # --- J: hailo-genai model status/download (real HEF dir, real disk) ---
        try:
            status, body = http("GET", "/ext/hailo-genai/api/model/status", timeout=30)
            models = body.get("models") if isinstance(body, dict) else None
            ok = status == 200 and isinstance(body, dict) and body.get("status") == "ok" \
                and isinstance(models, dict) and len(models) > 0
            record("J1_model_status_ok", ok, f"count={len(models) if isinstance(models, dict) else 'n/a'}")

            # Cross-check reported availability against the real HEF dir on
            # disk (HAILO_HEF_DIR, defaulting to ~/hailo_models) so this test
            # actually validates the filesystem lookup, not just the JSON
            # shape.
            hef_dir = Path(os.environ.get("HAILO_HEF_DIR", str(Path.home() / "hailo_models")))
            mismatches = []
            for name, info in (models or {}).items():
                expected = (hef_dir / Path(str(info.get("path", ""))).name).exists()
                if bool(info.get("available")) != expected:
                    mismatches.append(name)
            record("J2_model_status_matches_disk", not mismatches, f"mismatches={mismatches}")

            # A model already present on disk should report available=True
            # with a positive file_size_mb.
            present = next((n for n, i in (models or {}).items() if i.get("available")), None)
            ok = present is not None and isinstance((models[present]).get("file_size_mb"), (int, float)) \
                and models[present]["file_size_mb"] > 0
            record("J3_model_status_reports_size_for_present_model", ok,
                   f"present={present!r} file_size_mb={(models or {}).get(present, {}).get('file_size_mb')}")
        except Exception as e:
            record("J_model_status", False, repr(e))

        try:
            status, body = http("POST", "/ext/hailo-genai/api/model/download",
                                 {"model": "definitely-not-a-real-model-xyz"}, timeout=30)
            ok = status == 400 and isinstance(body, dict) and body.get("status") == "error" \
                and "Unknown model" in str(body.get("message", ""))
            record("J4_model_download_unknown_model_400", ok, f"status={status} body={str(body)[:200]}")
        except Exception as e:
            record("J4_model_download_unknown_model_400", False, repr(e))

        try:
            # Exercise the real download endpoint end-to-end WITHOUT
            # triggering a real multi-GB network fetch: pick a model whose
            # HEF is already present on disk. download_hef() short-circuits
            # to a no-op (see hailo_model_download.rs) when the target file
            # already exists, so this proves the endpoint, registry lookup,
            # and hef_dir resolution all work against the real filesystem
            # while staying fast/safe/repeatable (no bytes downloaded).
            status, body = http("GET", "/ext/hailo-genai/api/model/status", timeout=30)
            models = body.get("models") if isinstance(body, dict) else {}
            present = next((n for n, i in (models or {}).items() if i.get("available")), None)
            if present is None:
                record("J5_model_download_noop_for_present_model", False,
                       "no already-downloaded model found on disk to safely exercise")
            else:
                hef_path = Path(str(models[present]["path"]))
                before_mtime = hef_path.stat().st_mtime_ns
                before_size = hef_path.stat().st_size
                status, body = http("POST", "/ext/hailo-genai/api/model/download",
                                     {"model": present}, timeout=30)
                after_mtime = hef_path.stat().st_mtime_ns
                after_size = hef_path.stat().st_size
                ok = status == 200 and isinstance(body, dict) and body.get("status") == "ok" \
                    and body.get("model") == present \
                    and before_mtime == after_mtime and before_size == after_size
                record("J5_model_download_noop_for_present_model", ok,
                       f"model={present!r} status={status} body={str(body)[:150]} "
                       f"mtime_unchanged={before_mtime == after_mtime}")
        except Exception as e:
            record("J5_model_download_noop_for_present_model", False, repr(e))

        # --- K: WD-Tagger native batch ---
        k1_file_ids = []
        k1_job_id = None
        try:
            batch_paths = [SCRATCH / f"wd-batch-start-{index}.png" for index in range(3)]
            for path in batch_paths:
                make_png(path)
            k1_file_ids = [insert_test_file_row(path) for path in batch_paths]

            status, body = http("POST", "/api/wd-tagger/batch",
                                {"file_ids": k1_file_ids}, timeout=30)
            k1_job_id = body.get("job_id") if isinstance(body, dict) else None
            ok = status == 200 and isinstance(body, dict) and body.get("started") is True \
                and k1_job_id == "wd_tagger"
            record("K1_batch_start_returns_job_id", ok,
                   f"file_ids={k1_file_ids} status={status} body={str(body)[:200]}")
        except Exception as e:
            record("K1_batch_start_returns_job_id", False, repr(e))

        try:
            if k1_job_id != "wd_tagger" or not k1_file_ids:
                raise RuntimeError("K1 did not start a WD-Tagger batch job")

            deadline = time.time() + 60
            completed = False
            seen_running = False
            recent = []
            polls = 0
            while time.time() < deadline:
                polls += 1
                status, body = http("GET", "/api/jobs/status", timeout=10)
                active = body.get("active", []) if isinstance(body, dict) else []
                recent = body.get("recent", []) if isinstance(body, dict) else []
                if any(job.get("job_id") == k1_job_id for job in active if isinstance(job, dict)):
                    seen_running = True
                completed = status == 200 and isinstance(body, dict) \
                    and body.get("has_active") is False \
                    and any(job.get("job_id") == k1_job_id for job in recent
                            if isinstance(job, dict))
                if completed:
                    break
                time.sleep(1)
            if not completed:
                raise TimeoutError(
                    f"WD-Tagger batch did not complete within 60s; status={status} recent={recent}"
                )
            if not seen_running:
                raise AssertionError(
                    "never observed the wd_tagger job in /api/jobs/status active list "
                    "before it completed"
                )

            import sqlite3
            placeholders = ",".join("?" for _ in k1_file_ids)
            with sqlite3.connect(str(DB_PATH)) as con:
                rows = con.execute(
                    f"SELECT DISTINCT file_id FROM file_wd_tags WHERE file_id IN ({placeholders})",
                    k1_file_ids,
                ).fetchall()
            tagged_file_ids = {row[0] for row in rows}
            ok = set(k1_file_ids).issubset(tagged_file_ids)
            record("K2_batch_completes_and_writes_tags", ok,
                   f"polls={polls} tagged_file_ids={sorted(tagged_file_ids)}")
        except Exception as e:
            record("K2_batch_completes_and_writes_tags", False, repr(e))

        try:
            cancel_paths = [SCRATCH / f"wd-batch-cancel-{index}.png" for index in range(3)]
            for path in cancel_paths:
                make_png(path)
            cancel_file_ids = [insert_test_file_row(path) for path in cancel_paths]

            status, body = http("POST", "/api/wd-tagger/batch",
                                {"file_ids": cancel_file_ids}, timeout=30)
            if not (status == 200 and isinstance(body, dict) and body.get("started") is True
                    and body.get("job_id") == "wd_tagger"):
                raise RuntimeError(f"cancel test batch did not start: status={status} body={body}")

            status, body = http("POST", "/api/wd-tagger/batch/cancel", timeout=30)
            cancelling = status == 200 and isinstance(body, dict) and body.get("status") == "cancelling"
            if not cancelling:
                raise RuntimeError(f"cancel acknowledgement mismatch: status={status} body={body}")

            deadline = time.time() + 30
            polls = 0
            while time.time() < deadline:
                polls += 1
                status, body = http("GET", "/api/jobs/status", timeout=10)
                if status == 200 and isinstance(body, dict) and body.get("has_active") is False:
                    break
                time.sleep(1)
            else:
                raise TimeoutError("cancelled WD-Tagger batch did not finish within 30s")

            status, body = http("POST", "/api/wd-tagger/batch/cancel", timeout=30)
            ok = status == 404 and isinstance(body, dict) and body.get("code") == "job_not_running"
            record("K3_batch_cancel_then_404_when_not_running", ok,
                   f"polls={polls} status={status} body={str(body)[:200]}")
        except Exception as e:
            record("K3_batch_cancel_then_404_when_not_running", False, repr(e))

        # --- L: hailo-yolo native detect ---
        HAILO_YOLO_JOB_ID = "hailo_yolo_detect"
        l1_file_ids = []
        try:
            start_paths = [SCRATCH / f"yolo-detect-start-{index}.png" for index in range(3)]
            for path in start_paths:
                make_png(path)
            l1_file_ids = [insert_test_file_row(path) for path in start_paths]

            status, body = http("POST", "/ext/hailo-yolo/api/detect/start", {}, timeout=30)
            ok = status == 200 and isinstance(body, dict) and body.get("status") == "started"
            record("L1_detect_start_returns_started", ok,
                   f"file_ids={l1_file_ids} status={status} body={str(body)[:200]}")
        except Exception as e:
            record("L1_detect_start_returns_started", False, repr(e))

        try:
            if not l1_file_ids:
                raise RuntimeError("L1 did not register any target files")

            deadline = time.time() + 60
            completed = False
            seen_running = False
            recent = []
            polls = 0
            while time.time() < deadline:
                polls += 1
                status, body = http("GET", "/api/jobs/status", timeout=10)
                active = body.get("active", []) if isinstance(body, dict) else []
                recent = body.get("recent", []) if isinstance(body, dict) else []
                if any(job.get("job_id") == HAILO_YOLO_JOB_ID for job in active if isinstance(job, dict)):
                    seen_running = True
                completed = status == 200 and isinstance(body, dict) \
                    and body.get("has_active") is False \
                    and any(job.get("job_id") == HAILO_YOLO_JOB_ID for job in recent
                            if isinstance(job, dict))
                if completed:
                    break
                time.sleep(1)
            if not completed:
                raise TimeoutError(
                    f"hailo-yolo detect did not complete within 60s; status={status} recent={recent}"
                )
            if not seen_running:
                raise AssertionError(
                    "never observed the hailo_yolo_detect job in /api/jobs/status active list "
                    "before it completed"
                )

            import sqlite3
            placeholders = ",".join("?" for _ in l1_file_ids)
            with sqlite3.connect(str(DB_PATH)) as con:
                rows = con.execute(
                    "SELECT DISTINCT file_id FROM file_annotations "
                    f"WHERE file_id IN ({placeholders}) AND source LIKE 'hailo:%' AND key = 'detections'",
                    l1_file_ids,
                ).fetchall()
            annotated_file_ids = {row[0] for row in rows}
            ok = set(l1_file_ids).issubset(annotated_file_ids)
            record("L2_detect_completes_and_writes_annotations", ok,
                   f"polls={polls} annotated_file_ids={sorted(annotated_file_ids)}")
        except Exception as e:
            record("L2_detect_completes_and_writes_annotations", False, repr(e))

        try:
            status, body = http("POST", "/ext/hailo-yolo/api/detect/stop", timeout=30)
            ok = status == 200 and isinstance(body, dict) and body.get("status") == "not_running"
            record("L3_detect_stop_when_not_running", ok,
                   f"status={status} body={str(body)[:200]}")
        except Exception as e:
            record("L3_detect_stop_when_not_running", False, repr(e))

        # H/L resided the VLM/YOLO models. M loads a Speech2Text (GenAI)
        # model instead -- same single-GenAI-residency-slot constraint as
        # the LLM -> chat -> VLM transitions above.
        proc = restart_server(proc, env, "hailo-genai VLM -> speech2text")

        # --- M: native speech2text (single/video/batch/transcript, OpenAI-compat) ---
        # All M sub-tests deliberately use the SAME model (whisper-tiny) --
        # switching Speech2Text models mid-block would hit the same
        # single-GenAI-residency conflict as above and 409.
        try:
            wav_path = SCRATCH / "s2t-single.wav"
            make_wav(wav_path)
            status, body = http_multipart(
                "/ext/hailo-genai/api/s2t/transcribe",
                {"model": "whisper-tiny", "language": "en"},
                "audio", "single.wav", wav_path.read_bytes(),
            )
            ok = status == 200 and isinstance(body, dict) and body.get("status") == "ok" \
                and isinstance(body.get("segments"), list) and isinstance(body.get("text"), str)
            record("M1_s2t_transcribe_single", ok, f"status={status} body={str(body)[:200]}")
        except Exception as e:
            record("M1_s2t_transcribe_single", False, repr(e))

        try:
            status, body = http("GET", "/ext/hailo-genai/api/s2t/transcript/999999999", timeout=30)
            ok = status == 200 and isinstance(body, dict) and body.get("status") == "not_found"
            record("M2_s2t_transcript_not_found", ok, f"status={status} body={str(body)[:150]}")
        except Exception as e:
            record("M2_s2t_transcript_not_found", False, repr(e))

        m_video_file_id = None
        try:
            video_path = SCRATCH / "s2t-video.mp4"
            make_video_with_audio(video_path)
            m_video_file_id = insert_test_file_row(video_path)
            status, body = http(
                "POST", "/ext/hailo-genai/api/s2t/transcribe-video",
                {"file_id": m_video_file_id, "model": "whisper-tiny", "language": "en"},
                timeout=60,
            )
            ok = status == 200 and isinstance(body, dict) and body.get("status") == "ok" \
                and isinstance(body.get("segments"), list)
            record("M3_s2t_transcribe_video", ok, f"status={status} body={str(body)[:200]}")
        except Exception as e:
            record("M3_s2t_transcribe_video", False, repr(e))

        try:
            if m_video_file_id is None:
                raise RuntimeError("M3 did not produce a file_id to look up")
            status, body = http(
                "GET", f"/ext/hailo-genai/api/s2t/transcript/{m_video_file_id}", timeout=30,
            )
            ok = status == 200 and isinstance(body, dict) and body.get("status") == "ok" \
                and isinstance(body.get("segments"), list)
            record("M4_s2t_transcript_persisted_after_video", ok,
                   f"status={status} body={str(body)[:200]}")
        except Exception as e:
            record("M4_s2t_transcript_persisted_after_video", False, repr(e))

        try:
            batch_video_path = SCRATCH / "s2t-batch-video.mp4"
            make_video_with_audio(batch_video_path)
            batch_file_id = insert_test_file_row(batch_video_path)
            status, body = http(
                "POST", "/ext/hailo-genai/api/s2t/batch-transcribe",
                {"file_ids": [batch_file_id], "model": "whisper-tiny", "language": "en"},
                timeout=30,
            )
            started = status == 200 and isinstance(body, dict) and body.get("status") == "started"
            if not started:
                raise RuntimeError(f"batch did not start: status={status} body={body}")
            deadline = time.time() + 60
            completed = False
            polls = 0
            while time.time() < deadline:
                polls += 1
                status, body = http(
                    "GET", f"/ext/hailo-genai/api/s2t/transcript/{batch_file_id}", timeout=10,
                )
                if status == 200 and isinstance(body, dict) and body.get("status") == "ok":
                    completed = True
                    break
                time.sleep(1)
            record("M5_s2t_batch_transcribe_persists", completed,
                   f"polls={polls} last_status={status} body={str(body)[:150]}")
        except Exception as e:
            record("M5_s2t_batch_transcribe_persists", False, repr(e))

        try:
            status, body = http_multipart(
                "/ext/hailo-genai/v1/audio/transcriptions",
                # Deliberately not "whisper-1" -- that alias resolves to
                # whisper-base, which would conflict with the whisper-tiny
                # residency the rest of this block relies on (see block
                # comment above). model_download.py test coverage in the
                # sidecar-facing route module handles the alias itself.
                {"model": "whisper-tiny", "response_format": "text"},
                "file", "openai.wav", wav_path.read_bytes(),
            )
            ok = status == 200 and isinstance(body, str)
            record("M6_s2t_openai_transcriptions_text_format", ok,
                   f"status={status} body={str(body)[:150]}")
        except Exception as e:
            record("M6_s2t_openai_transcriptions_text_format", False, repr(e))

    finally:
        print("\n--- shutting down yu-server ---")
        stop_server(proc)

        leftover = subprocess.run(["pgrep", "-f", "yu-infer"], capture_output=True, text=True)
        infer_leaked = bool(leftover.stdout.strip())
        record("cleanup_no_leaked_yu_infer", not infer_leaked, leftover.stdout.strip() or "none")

        holders = device_holders()
        record("cleanup_device_released", len(holders) == 0, f"holders={holders}")

        if not keep:
            shutil.rmtree(SCRATCH, ignore_errors=True)

    print("\n=== SUMMARY ===")
    passed = sum(1 for _, ok, _ in results if ok)
    for name, ok, _detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n{passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
