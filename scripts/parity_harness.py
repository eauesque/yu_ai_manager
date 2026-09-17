"""Parity harness: start Python + Rust servers, run verify_rust_compat, teardown.

Usage (CI):
    UV_CACHE_DIR=tmp/.uv-cache uv run python scripts/parity_harness.py \
        --db tmp/parity-test.db \
        --python-port 5110 \
        --rust-port 5130 \
        --pin test1234

Exit 0 = all native routes pass, 1 = failures, 2 = setup error.

The script:
1. Seeds a fresh SQLite DB from fixture files.
2. Starts the Python server.
3. Waits for Python /api/scan/status to become healthy.
4. Starts the Rust server via start_rust_server() in auto mode.
5. Runs verify_rust_compat.run() with the Python server as oracle.
6. Tears down both servers.
7. Prints wall-time elapsed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))


def _seed_db(db_path: Path, *, encrypt: bool = False) -> None:
    """Delegate to the shared Phase 1/3 seed helper."""
    from parity_seed_helper import seed_parity_db

    for path in (
        db_path,
        db_path.with_suffix(db_path.suffix + "-wal"),
        db_path.with_suffix(db_path.suffix + "-shm"),
        db_path.with_suffix(".db.encrypting"),
        db_path.with_suffix(".db.plain_bak"),
    ):
        path.unlink(missing_ok=True)
    ids = seed_parity_db(db_path)
    if encrypt:
        from core.services_core.db_migrate_encrypt import migrate_plaintext_to_cipher

        migrate_plaintext_to_cipher(db_path)
    print(f"seeded DB: {db_path} (file_id={ids['file_id']}, collection_id={ids['collection_id']})")


def _start_python_server(db: str, port: int, pin: str | None, config_path: str, log_file) -> subprocess.Popen:
    _bin_uv = REPO / "bin" / "uv"
    uv_exe = str(_bin_uv) if _bin_uv.exists() else shutil.which("uv") or "uv"
    cmd = [
        uv_exe,
        "run",
        "python",
        "web_ui.py",
        "--db",
        db,
        "--port",
        str(port),
        # Without this, web_ui.py resolves config.json relative to CWD (the
        # repo root), i.e. the developer's REAL config -- and a mutating
        # scan-roots parity request then wipes their registered folders.
        "--config",
        config_path,
    ]
    if pin:
        cmd += ["--pin", pin]
    env = {**os.environ, "UV_CACHE_DIR": str(REPO / "tmp" / ".uv-cache"), "PYTHONUTF8": "1"}
    print(f"Starting Python server: {' '.join(cmd)}")
    # stdout/stderr must not be an unread PIPE: once the OS pipe buffer
    # (~64KB) fills, the child's write() blocks forever mid-request,
    # freezing the whole harness run. Redirect to a file instead (still
    # inspectable, never backpressures the child).
    return subprocess.Popen(
        cmd,
        cwd=str(REPO),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
    )


def _wait(url: str, timeout: int = 30) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except urllib.error.HTTPError:
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _responder_server_header(url: str) -> str:
    """Return the `Server:` header of whatever answers `url` ("" if none)."""
    import urllib.error
    import urllib.request

    try:
        # noqa S310 (audit URL open): the caller builds this as
        # f"http://127.0.0.1:{port}/..." -- the scheme is a literal and the host
        # is loopback, so there is no attacker-controlled scheme or target here.
        with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310
            return resp.headers.get("Server", "") or ""
    except urllib.error.HTTPError as exc:  # an error response still carries headers
        return exc.headers.get("Server", "") or ""
    except Exception:
        return ""


def _confirm_rust_owns_port(
    proc: subprocess.Popen, log_path: Path, rust_base: str, settle: float = 3.0
) -> bool:
    """Reject a healthy-looking Rust port that belongs to someone else.

    Two independent checks, because neither alone is sufficient:

    * **Identity.** Python's stdlib `http.server` -- which is what the SSE server
      is -- announces itself in `Server:` (`BaseHTTP/x.y Python/z`). yu-server
      (axum/hyper) sends no `Server` header at all. So a Python-flavoured header
      on this port means we are about to diff against the wrong process.
    * **Liveness, after a settle.** The squatter answers the readiness probe
      instantly, while yu-server needs ~1s of yu-infer spawn retries before it
      reaches bind() and panics with AddrInUse. Polling immediately therefore
      sees a live child and passes; wait out that window first.

    Do NOT try to confirm ownership by grepping the log for yu-server's
    "listening on" line: that is emitted at INFO, and the default RUST_LOG here
    keeps only WARN and above, so the line never appears even on a healthy run.
    """
    header = _responder_server_header(f"{rust_base}/api/scan/status")
    if any(token in header for token in ("BaseHTTP", "SimpleHTTP", "Python")):
        print(
            f"ERROR: {rust_base} is answered by a Python http.server "
            f"(Server: {header!r}), not yu-server. Python's SSE server binds "
            "python_port+1..+9, so use --rust-port >= --python-port + 10.",
            file=sys.stderr,
        )
        return False

    time.sleep(settle)
    if proc.poll() is not None:
        print(
            f"ERROR: the Rust server exited (code {proc.returncode}) yet "
            f"{rust_base} still answers -- another process holds that port.",
            file=sys.stderr,
        )
        if log_path.exists():
            print(f"----- tail of {log_path} -----", file=sys.stderr)
            tail = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in tail[-20:]:
                print(line, file=sys.stderr)
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Parity harness: both servers + verify_rust_compat")
    parser.add_argument("--db", default="tmp/parity-test.db")
    parser.add_argument("--python-port", type=int, default=5110)
    # Rust port must be >= python-port + 10 to avoid the SSE server (binds
    # flask_port+1 through flask_port+9) claiming the Rust port first.
    parser.add_argument("--rust-port", type=int, default=5120)
    parser.add_argument("--pin", default=None, help="PIN for Python server (omit to disable)")
    parser.add_argument("--allow-stale-binary", action="store_true")
    # Body comparison was inert: any mismatch set schema_diff, which passed returned.
    # docs/development/development_docs/OCR_PARITY_CENSUS.md triaged all 29 failures;
    # remaining holds use skip_body_compare with reasons.
    # check_rust_compat is a blocking pre-push gate for routes/ and main.rs, so strict-by-default
    # strengthens that gate and is safe only while parity is green.
    parser.add_argument("--strict-body", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument(
        "--manifest",
        default=str(Path(__file__).parent.parent / "tests" / "compat_goldens" / "manifest.yaml"),
        help=(
            "Path to compat_goldens manifest.yaml "
            "(default: tests/compat_goldens/manifest.yaml). Pass empty string to disable."
        ),
    )
    parser.add_argument(
        "--inputs",
        default=str(Path(__file__).parent.parent / "tests" / "compat_goldens" / "inputs.yaml"),
        help="Path to inputs.yaml Phase 3 allowlist. Pass empty string to disable.",
    )
    parser.add_argument(
        "--path-vars-db",
        default=None,
        help=(
            "Path to a *plaintext* seeded DB for variable resolution. Defaults to the "
            "Rust-side copy, which is the only one that stays plaintext -- --db is "
            "migrated to SQLCipher for the Python server, so passing it here fails "
            "with 'file is not a database'."
        ),
    )
    args = parser.parse_args()

    # The Python server binds python_port+1..+9 for SSE. A --rust-port inside
    # that band is taken before yu-server can bind it, and the squatter answers
    # every probe (404 for GET, 501 for POST) -- which reads as "Rust has not
    # ported anything". Refuse the overlap instead of only warning about it
    # after the fact.
    if args.python_port <= args.rust_port <= args.python_port + 9:
        parser.error(
            f"--rust-port {args.rust_port} collides with the Python server's SSE "
            f"band ({args.python_port + 1}..{args.python_port + 9}); "
            f"use --rust-port >= {args.python_port + 10}"
        )

    from verify_rust_compat import (
        _load_known_no_python_fails,
        run,
        start_rust_server,
        wait_for_server,
    )

    db_path = REPO / args.db
    # Python server may convert the DB to SQLCipher; give Rust a separate plain copy.
    # The plain copy lives in its own subdirectory (not next to db_path) because
    # both Python's and Rust's tags.db resolve a sibling "vectors.db" from the
    # same parent directory (core.services_core.app_runtime_state.get_vectors_db_path
    # / crates/yu-server/src/state.rs::vectors_db_path both use a fixed sibling
    # filename). If db_path and rust_db_path shared a directory, both processes
    # would race to create/open the *same* vectors.db file — Python encrypts its
    # copy with the real cipher key while Rust's parity run intentionally opens
    # its copy unencrypted (--db-key ""), so the shared file would fail to open
    # on whichever side connects second ("file is not a database").
    rust_dir = db_path.parent / "rust"
    rust_dir.mkdir(parents=True, exist_ok=True)
    rust_db_path = rust_dir / db_path.with_suffix(".rust.db").name
    manifest_path = Path(args.manifest) if args.manifest else None
    inputs_path = Path(args.inputs) if args.inputs else None
    _seed_db(db_path, encrypt=True)
    _seed_db(rust_db_path)

    # Isolated throwaway config for BOTH servers. Neither web_ui.py nor
    # yu-server is told a config path elsewhere in this harness, so without
    # this they each resolve config.json relative to CWD (the repo root) --
    # the operator's REAL config -- and a mutating scan-roots parity request
    # (DELETE/reorder) permanently wipes their registered folders. Seed from
    # the real config (falling back to the example template) so the servers
    # still boot with realistic settings, but every write during this run
    # lands only in this throwaway copy.
    config_path = rust_dir / f"{db_path.stem}.config.json"
    _seed_source = REPO / "config.json"
    if not _seed_source.exists():
        _seed_source = REPO / "config.json.example"
    if _seed_source.exists():
        shutil.copy2(_seed_source, config_path)
    else:
        config_path.write_text('{"scan_roots": []}', encoding="utf-8")
    # `server.trusted_proxy_auth` must not be inherited from the live config.json this
    # was copied from: that file is rewritten while the suite runs, so Rust reported
    # true or false depending on its state at seed time while Python (below) was always
    # true -- which is what made `/api/auth/status` differ intermittently. Declare it
    # here so both sides start from the same value.
    #
    # `trusted_proxy_ips` is deliberately NOT set on Rust's copy: see the note below on
    # the rate-limit bucket key. The flag alone grants nothing while --trusted-ips is
    # empty.
    _rust_config = json.loads(config_path.read_text(encoding="utf-8"))
    _rust_config.setdefault("server", {})["trusted_proxy_auth"] = True
    # `backup.backup_dir` defaults to `<db_parent>/backup/`, and the two servers are
    # given DBs in different directories -- so each listed its OWN backups and
    # `/api/tools/backup/list` differed on `backups[len], count` (measured v4.734.24:
    # tmp/backup held 2, tmp/rust/backup held 0). Name one directory for both.
    _shared_backup_dir = rust_dir / "shared-backup"
    _shared_backup_dir.mkdir(parents=True, exist_ok=True)
    _rust_config.setdefault("backup", {})["backup_dir"] = str(_shared_backup_dir)
    config_path.write_text(json.dumps(_rust_config), encoding="utf-8")

    python_config_dir = rust_dir / "python-config"
    python_config_dir.mkdir(exist_ok=True)
    python_config_path = python_config_dir / config_path.name
    shutil.copy2(config_path, python_config_path)
    # Rust forwards to this isolated Python process from loopback with
    # X-Remote-User. Keep this trust relationship in Python's separate copy:
    # sharing it changes Rust's rate-limit client-IP bucket key.
    config = json.loads(python_config_path.read_text(encoding="utf-8"))
    server = config.setdefault("server", {})
    server["trusted_proxy_auth"] = True
    trusted_ips = server.setdefault("trusted_proxy_ips", [])
    if "127.0.0.1" not in trusted_ips:
        trusted_ips.append("127.0.0.1")
    python_config_path.write_text(json.dumps(config), encoding="utf-8")

    # POST /api/diagnostics/doctor really runs the checks and writes a
    # doctor_<ts>.md/.json pair. Both servers resolve that directory from
    # PROJECT_ROOT (= the checkout, since cwd is REPO here), so without this
    # redirect the route can only be `skip`ped -- i.e. never exercised at all.
    # Both child env dicts are built from os.environ, so setting it here
    # reaches Python (_start_python_server) and Rust (rust_server_env) alike.
    doctor_report_dir = rust_dir / f"{db_path.stem}.doctor-reports"
    doctor_report_dir.mkdir(parents=True, exist_ok=True)
    os.environ["YU_DOCTOR_REPORT_DIR"] = str(doctor_report_dir)

    path_vars_db = Path(args.path_vars_db) if args.path_vars_db else rust_db_path
    if not path_vars_db.is_absolute():
        path_vars_db = REPO / path_vars_db

    python_proc = None
    rust_proc = None
    results = None
    python_log_file = None
    rust_log_file = None
    rust_log_path = rust_dir / f"{db_path.stem}.rust-server.log"
    t0 = time.monotonic()

    try:
        python_log_path = db_path.with_suffix(".python-server.log")
        python_log_file = python_log_path.open("wb")
        print(f"Python server log: {python_log_path}")
        python_proc = _start_python_server(str(db_path), args.python_port, args.pin, str(python_config_path), python_log_file)
        python_base = f"http://127.0.0.1:{args.python_port}"
        print(f"Waiting for Python server ({python_base})...")
        if not _wait(f"{python_base}/api/scan/status", timeout=150):
            print("ERROR: Python server did not become healthy", file=sys.stderr)
            sys.exit(2)
        print("Python server ready.")

        rust_log_file = rust_log_path.open("wb")
        print(f"Rust server log: {rust_log_path}")
        rust_proc = start_rust_server(
            str(rust_db_path),
            port=args.rust_port,
            python_url=python_base,
            allow_stale_binary=args.allow_stale_binary,
            use_db_key_env=False,
            pin=args.pin or "",
            log_file=rust_log_file,
            config=str(config_path),
        )
        rust_base = f"http://127.0.0.1:{args.rust_port}"
        print(f"Waiting for Rust server ({rust_base})...")
        if not wait_for_server(f"{rust_base}/api/scan/status", timeout=60):
            print("ERROR: Rust server did not become healthy", file=sys.stderr)
            sys.exit(2)
        # Confirm the responder is yu-server and not something else that grabbed
        # the port. Python's SSE server binds python_port+1..+9, and when the
        # caller picked an adjacent --rust-port it answered every request here:
        # 404 for GET and `501 Unsupported method` for POST, which read as 527
        # parity failures against routes that were in fact implemented.
        # 2026-09-12: the same trap produced 49 PASS / 556 FAIL with every Rust
        # route apparently "not ported", after the bare poll() check below passed
        # by winning a race it should not have been in. See the helper.
        if not _confirm_rust_owns_port(rust_proc, rust_log_path, rust_base):
            sys.exit(2)
        print("Rust server ready.")

        python_cookies: dict = {}
        if args.pin:
            from verify_rust_compat import python_pin_login

            python_cookies = asyncio.run(python_pin_login(python_base, args.pin))

        rust_cookies: dict = {}
        if args.pin:
            from verify_rust_compat import rust_pin_login

            # start_rust_server() above was given the same pin=args.pin, so Rust
            # is deterministically PIN-configured here too (not dependent on
            # host launch-args.txt/env leakage).
            rust_cookies = asyncio.run(rust_pin_login(rust_base, args.pin))

        from parity_seed_helper import seed_ids_from_existing_db

        path_vars = seed_ids_from_existing_db(path_vars_db)
        results = asyncio.run(
            run(
                rust_base,
                python_base,
                None,
                python_cookies or None,
                rust_cookies=rust_cookies or None,
                manifest_path=manifest_path,
                inputs_path=inputs_path,
                path_vars=path_vars,
                strict_body=args.strict_body,
            )
        )

        elapsed = time.monotonic() - t0
        # no_python (python_path=None) entries have no Python side to compare
        # against, so r.passed is always False. Their standalone Rust-side
        # verdict is r.no_python_ok (rust_status in accept_statuses). A status
        # outside accept_statuses is counted as failed so it reaches the exit
        # code. schema_check failures are already surfaced via r.error inside
        # check_endpoint(), so they land in the errors bucket instead.
        passed = sum(1 for r in results if r.passed and not r.no_python)
        na = sum(1 for r in results if r.no_python and not r.error and r.no_python_ok)

        # Pre-existing no_python FAILs triaged into
        # scripts/parity_no_python_known_fails.txt do not block the gate on
        # their own, but the allowlist must match the currently-failing set
        # exactly (shrink-only enforcement) — see verify_rust_compat.py's
        # main() for the identical logic and that file's header for format.
        known_fails_path = REPO / "scripts" / "parity_no_python_known_fails.txt"
        known_fails = _load_known_no_python_fails(known_fails_path)
        no_python_failing = {
            (r.method, r.path)
            for r in results
            if not r.error and r.no_python and not r.no_python_ok
        }
        known_fail_stale = sorted(known_fails - no_python_failing)
        known_fail_unlisted = sorted(no_python_failing - known_fails)
        known_fail_matched = no_python_failing & known_fails

        failed = sum(
            1
            for r in results
            if not r.error
            and (
                (not r.no_python and not r.passed)
                or (
                    r.no_python
                    and not r.no_python_ok
                    and (r.method, r.path) not in known_fail_matched
                )
            )
        )
        errors = sum(1 for r in results if r.error)
        print(f"\nParity result: {passed} PASS / {failed} FAIL / {na} N/A(Rust独自) / {errors} ERROR")

        # The retry count was recorded per result and printed nowhere, so the
        # only question the rate-limiter port needed the harness to answer --
        # "did the limiter actually fire, and how often did a resend rescue a
        # run?" -- could not be read off a run at all. A zero here after the
        # limiter landed means the limiter is not in the binary under test.
        retries = sum(r.retries_429 for r in results)
        retried_rows = [r for r in results if r.retries_429]
        print(f"429 resends: {retries} across {len(retried_rows)} endpoint(s)")
        for r in retried_rows:
            print(f"   - resent {r.method} {r.path}")

        # Printed unconditionally, zero included. A silent rescue is worse than
        # no rescue: the run reads clean while the peer is dropping connections,
        # and the next person cannot tell a stable green from a rescued one.
        flakes = sum(r.retries_transport for r in results)
        flake_rows = [r for r in results if r.retries_transport]
        print(
            f"transport resends: {flakes} across {len(flake_rows)} endpoint(s)"
        )
        for r in flake_rows:
            print(f"   - transport flake, resent {r.method} {r.path}")

        # List exactly what `failed` counted. The per-entry glyph lines above do
        # not cover every result, so without this the number cannot be acted on:
        # a run reporting 5 FAIL printed only one ❌.
        failing_rows = [
            r
            for r in results
            if not r.error
            and (
                (not r.no_python and not r.passed)
                or (
                    r.no_python
                    and not r.no_python_ok
                    and (r.method, r.path) not in known_fail_matched
                )
            )
        ]
        if failing_rows:
            print("FAIL の内訳:")
            for r in failing_rows:
                kind = "no_python" if r.no_python else "python比較"
                print(
                    f"   - [{kind} #{r.entry_id}] {r.method} {r.path} "
                    f"rust={r.rust_status} py={r.python_status}"
                )
                if r.note:
                    # The note carries diff_summary() for body mismatches; without
                    # it the breakdown says which entry failed but not why.
                    print(f"       {r.note}")
        print(f"Wall time: {elapsed:.1f}s")
        if known_fail_matched:
            print(f"既知FAIL allowlist: {len(known_fail_matched)} 件 ({known_fails_path.relative_to(REPO)})")
        if known_fail_stale:
            print("⚠️  allowlist に載っているが現在 FAIL しないエントリ (直った→一覧から外せ):")
            for m, p in known_fail_stale:
                print(f"   - {m} {p}")
        if known_fail_unlisted:
            print("⚠️  現在 FAIL しているが allowlist に無いエントリ (新規debt or 未triage):")
            for m, p in known_fail_unlisted:
                print(f"   - {m} {p}")

        if failed or errors or known_fail_stale or known_fail_unlisted:
            sys.exit(1)

    finally:
        # A mid-run death of the Rust server surfaces to the caller as an
        # httpx.ReadError with no hint of which side dropped. Say so plainly,
        # and show the tail of the log the server actually wrote — the CI
        # failure dump globs tmp/rust/*.log, which never existed while
        # start_rust_server sent the child's output to DEVNULL.
        transport_errors = [
            r for r in (results or []) if getattr(r, "error", "").startswith((
                "RemoteProtocolError", "ReadError", "ConnectError", "ConnectTimeout",
                "ReadTimeout", "PoolTimeout",
            ))
        ]
        died = rust_proc is not None and rust_proc.poll() is not None
        if died:
            print(
                f"\nThe Rust server is no longer running (exit code "
                f"{rust_proc.returncode}). Anything after its death fails as a "
                f"connection error, not as a parity difference.",
                file=sys.stderr,
            )
        elif transport_errors:
            # The first version of this notice only fired when the process was
            # gone, so a run that lost connections while the server stayed up
            # printed nothing at all -- the log was written and never read.
            # Which of the two it is decides where to look, so say it either way.
            print(
                f"\nThe Rust server is still running, yet {len(transport_errors)} "
                f"request(s) failed at the transport. The process did not die; "
                f"look at the endpoint(s) below, not at a crash.",
                file=sys.stderr,
            )
            for r in transport_errors:
                print(f"   - {r.method} {r.path}: {r.error}", file=sys.stderr)
        if died or transport_errors:
            if rust_log_file:
                rust_log_file.flush()
            try:
                tail = rust_log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
            except OSError:
                tail = []
            if tail:
                print(f"----- tail of {rust_log_path} -----", file=sys.stderr)
                for line in tail:
                    print(line, file=sys.stderr)
        if rust_proc:
            rust_proc.terminate()
            try:
                rust_proc.wait(timeout=5)
            except Exception:
                rust_proc.kill()
        if python_proc:
            python_proc.terminate()
            try:
                python_proc.wait(timeout=5)
            except Exception:
                python_proc.kill()
        if python_log_file:
            python_log_file.close()
        if rust_log_file:
            rust_log_file.close()
        # On Windows file handles may linger briefly after terminate(); retry unlink.
        for _db in (db_path, rust_db_path):
            for _attempt in range(5):
                try:
                    _db.unlink(missing_ok=True)
                    break
                except PermissionError:
                    time.sleep(0.5)


if __name__ == "__main__":
    main()
