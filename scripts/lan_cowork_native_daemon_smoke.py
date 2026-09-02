#!/usr/bin/env python3
"""Exercise the native LAN Cowork daemon across two real local servers."""
from __future__ import annotations

import argparse
import base64
import contextlib
import json
import logging
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parent.parent
RELEASE_SERVER = REPO / "crates/target/release/yu-server"
DEBUG_SERVER = REPO / "crates/target/debug/yu-server"
SKIP_WARN = "LAN Cowork discovery disabled (UDP bind failed)"
CSRF = {"X-Requested-With": "XMLHttpRequest"}
REDACTED = "<redacted>"
DEFAULT_OPENER = urllib.request.build_opener()
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
RELAYED_VALUE = re.compile(r"\brelayed\s*=\s*(\d+)\b")
LEG_ORDER = (
    "0 binary", "1 A startup", "2 B startup", "3 config activation",
    "4 config-absent control", "4b hybrid safety", "5 sessions", "6 discovery",
    "7 register", "8 pairing", "9 signed inbound", "9 token renew", "10 throttle",
    "11 teardown",
)


def json_or_empty(raw: bytes, content_type: str) -> dict:
    if "application/json" not in content_type.lower():
        return {}
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}


def private_lan_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
    finally:
        sock.close()
    if ip.startswith("127."):
        raise RuntimeError("private LAN IP is unavailable")
    return ip


def free_port(host: str) -> int:
    sock = socket.socket()
    sock.bind((host, 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def build_plain_scratch_db(db_path: Path) -> None:
    """Reuse the unencrypted init/migrate recipe used by hailo_realhw_smoke."""
    repo_str = str(REPO)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)
    from core import paths as core_paths
    from core.schema_core.schema_init import init_db
    from core.schema_core.schema_migrate import migrate_db

    root = db_path.parent
    core_paths.init_app_paths(
        data_dir=root / "app_data", cache_dir=root / "app_cache",
        log_dir=root / "app_logs", profiles_dir=root / "app_profiles",
    )
    con = sqlite3.connect(db_path)
    try:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA foreign_keys=ON;")
        init_db(con, enable_fts=True)
        migrate_db(con)
        con.commit()
    finally:
        con.close()
    for suffix in ("", "-wal", "-shm"):
        (root / f"vectors.db{suffix}").unlink(missing_ok=True)


def write_scratch_config(path: Path, enabled: bool) -> None:
    config = {"extensions": {"builtin-lan-cowork": {"enabled": True}}} if enabled else {}
    path.write_text(json.dumps(config), encoding="utf-8")


def http(url: str, method: str = "GET", body: bytes | None = None,
         headers: dict[str, str] | None = None, opener=None, timeout: float = 5) -> tuple[int, dict]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with (opener or DEFAULT_OPENER).open(request, timeout=timeout) as response:
            raw = response.read()
            return response.status, json_or_empty(raw, response.headers.get("Content-Type", ""))
    except urllib.error.HTTPError as error:
        raw = error.read()
        return error.code, json_or_empty(raw, error.headers.get("Content-Type", ""))


def json_post(base: str, path: str, value: dict, opener=None,
              headers: dict[str, str] | None = None, timeout: float = 5) -> tuple[int, dict]:
    merged = {"Content-Type": "application/json", **CSRF, **(headers or {})}
    return http(base + path, "POST", json.dumps(value, separators=(",", ":")).encode(), merged, opener, timeout)


def wait_ready(base: str, process: subprocess.Popen, timeout: float = 20) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if process.poll() is not None:
            raise RuntimeError("server exited before readiness")
        try:
            status, _ = http(base + "/ext/lan_cowork/api/peer/status")
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
            continue
        if status == 200:
            return
        time.sleep(0.2)
    raise RuntimeError("server readiness timed out")


def wait_listening(host: str, port: int, process: subprocess.Popen, timeout: float = 20) -> None:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if process.poll() is not None:
            raise RuntimeError("server exited before readiness")
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.2)
    raise RuntimeError("server readiness timed out")


def session(base: str, pin: str):
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    body = urllib.parse.urlencode({"pin": pin}).encode()
    status, _ = http(base + "/_pin_check", "POST", body,
                     {"Content-Type": "application/x-www-form-urlencoded"}, opener)
    if status not in (200, 303):
        raise RuntimeError("PIN session was not established")
    status, auth = http(base + "/api/auth/status", opener=opener)
    if status != 200 or auth.get("session_authenticated") is not True:
        raise RuntimeError("PIN session authentication was not confirmed")
    return opener


def signed_headers(seed: bytes, peer_id: str, path: str, body: bytes, nonce: str = "",
                   token: str | None = None) -> dict[str, str]:
    from core.crypto_identity.keypair import sign
    from core.crypto_identity.request_signer import build_canonical_message

    timestamp = str(int(time.time()))
    signature = sign(seed, build_canonical_message("POST", path, "", timestamp, body))
    headers = {**CSRF, "Content-Type": "application/json", "X-Peer-Id": peer_id,
               "X-Peer-Ts": timestamp,
               "X-Peer-Sig": base64.urlsafe_b64encode(signature).decode()}
    if nonce:
        headers["X-Peer-Nonce"] = nonce
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def signed_post(base: str, seed: bytes, peer_id: str, path: str, value: dict,
                nonce: str = "", token: str | None = None, timeout: float = 180) -> tuple[int, dict]:
    body = json.dumps(value, separators=(",", ":")).encode()
    return http(base + path, "POST", body, signed_headers(seed, peer_id, path, body, nonce, token), timeout=timeout)


def db_peer(db: Path, peer_id: str):
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT token, api_port FROM peers WHERE peer_id=?", (peer_id,)).fetchone()
    finally:
        con.close()


def identity_seed(db: Path) -> bytes:
    con = sqlite3.connect(db)
    try:
        row = con.execute("SELECT value FROM lan_cowork_identity WHERE key='ed25519_seed'").fetchone()
        if not row:
            raise RuntimeError("identity seed is unavailable")
        return bytes(row[0])
    finally:
        con.close()


def log_matches(log_path: Path) -> list[str]:
    return [clean for line in log_path.read_text(errors="replace").splitlines()
            if "accepted peer events" in (clean := ANSI_ESCAPE.sub("", line))]


def relayed_count(line: str) -> int | None:
    match = RELAYED_VALUE.search(line)
    return int(match.group(1)) if match else None


class SseSubscriber:
    """Hold an open `/api/events/stream` subscription for the duration of a leg.

    `peer_event` branches on `sse_receiver_count() > 0`
    (`lan_cowork_inbound_read.rs:568`): with no subscriber the handler logs the
    *dropped* summary instead of the *relayed* one. The throttle leg asserts on
    the relayed line, so it must actually hold a consumer — without this the leg
    fails with `expected relayed=1, found None` no matter how the product behaves.

    The body is drained on a daemon thread so the server never blocks writing to
    a full socket buffer.
    """

    def __init__(self, base: str, opener) -> None:
        self._response = None
        self._thread = None
        request = urllib.request.Request(base + "/api/events/stream", headers=dict(CSRF))
        self._response = opener.open(request, timeout=10)

        def drain() -> None:
            try:
                for _ in self._response:
                    pass
            except Exception:
                logger.debug("step failed", exc_info=True)

        self._thread = threading.Thread(target=drain, daemon=True)
        self._thread.start()

    def close(self) -> None:
        if self._response is not None:
            with contextlib.suppress(Exception):
                self._response.close()
            self._response = None


def start_server(server: Path, db: Path, config: Path, host: str, port: int, pin: str, log: Path,
                 rust_log: str, standalone: bool = True):
    args = [str(server), "--db", str(db), "--config", str(config), "--host", host,
            "--port", str(port), "--pin", pin, "--project-root", str(REPO), "--headless"]
    if standalone:
        args.insert(1, "--standalone")
    handle = log.open("w")
    env = os.environ.copy()
    # Ignore ambient RUST_LOG so the throttle INFO evidence is always observable.
    env["RUST_LOG"] = rust_log
    env["YU_SKIP_DOTENV_FILES"] = "1"
    env["YU_SKIP_LAUNCH_ARGS_FILE"] = "1"
    env.pop("YU_LAN_COWORK_NATIVE_DAEMON", None)
    env.pop("YU_STANDALONE", None)
    try:
        process = subprocess.Popen(
            args, stdout=handle, stderr=subprocess.STDOUT, cwd=REPO, env=env,
        )
    except Exception:
        handle.close()
        raise
    return process, handle


def stop(process: subprocess.Popen | None, handle) -> None:
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    if handle:
        handle.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-temp", action="store_true")
    parser.add_argument("--skip-slow", action="store_true", help="skip the two >60 second waits")
    parser.add_argument("--burst", type=int, default=50, help="maximum throttle events to send (default: 50)")
    parser.add_argument("--server", type=Path, help="path to a yu-server binary")
    parser.add_argument(
        "--rust-log",
        default="yu_server=info,lan_cowork=info",
        help="RUST_LOG value for child servers; overrides ambient RUST_LOG",
    )
    args = parser.parse_args()
    if args.burst < 1:
        parser.error("--burst must be positive")
    server = args.server or (RELEASE_SERVER if RELEASE_SERVER.is_file() else DEBUG_SERVER)
    debug_binary = server.resolve() == DEBUG_SERVER.resolve()
    binary_detail = "debug (evidence not valid for cutover)" if debug_binary else "release"
    if args.server and not debug_binary:
        binary_detail = f"custom: {server}"
    if debug_binary:
        print("WARNING: debug yu-server is unsuitable for cutover evidence: pairing and signed/throttle "
              "legs may fail or be slow because the initiator's 10s outbound timeout is shorter than "
              "debug-build scrypt. Build release evidence with: cargo build --release -p yu-server "
              "--no-default-features")
    if args.skip_slow:
        print("WARNING: --skip-slow is not valid cutover evidence: token-renew and throttle legs did not execute.")
    results: list[tuple[str, str, str, float]] = []
    processes: list[tuple[subprocess.Popen | None, object]] = []
    scratch_parent = REPO / "tmp"
    scratch_parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="lan-cowork-native-smoke-", dir=scratch_parent))
    pin = "123456"
    current_step = "setup"
    step_started = time.monotonic()
    renew_status: int | None = None
    throttle_event_status: int | None = None
    throttle_log_error: str | None = None
    renewed_peer_token: str | None = None

    def set_step(name: str) -> None:
        nonlocal current_step, step_started
        if name not in LEG_ORDER:
            raise RuntimeError("unknown leg name")
        current_step = name
        step_started = time.monotonic()

    def record(outcome: str, detail: str) -> None:
        results.append((current_step, outcome, detail, time.monotonic() - step_started))

    try:
        set_step("0 binary")
        if not server.is_file():
            raise RuntimeError("built yu-server is unavailable")
        record("PASS", binary_detail)
        host = private_lan_ip()
        db_a, db_b, db_c, db_hybrid = (
            temp / "a.db", temp / "b.db", temp / "c.db", temp / "hybrid.db",
        )
        for db in (db_a, db_b, db_c, db_hybrid):
            build_plain_scratch_db(db)
        config_enabled = temp / "config-enabled.json"
        config_disabled = temp / "config-disabled.json"
        write_scratch_config(config_enabled, enabled=True)
        write_scratch_config(config_disabled, enabled=False)
        port_a, port_b, port_c, port_hybrid = (
            free_port(host), free_port(host), free_port(host), free_port(host),
        )
        base_a = f"http://{host}:{port_a}"
        base_b = f"http://{host}:{port_b}"
        base_c = f"http://{host}:{port_c}"
        base_hybrid = f"http://{host}:{port_hybrid}"

        set_step("1 A startup")
        process_a, handle_a = start_server(
            server, db_a, config_enabled, host, port_a, pin, temp / "a.log", args.rust_log,
        )
        processes.append((process_a, handle_a))
        wait_ready(base_a, process_a)
        record("PASS", "ready")
        set_step("2 B startup")
        process_b, handle_b = start_server(
            server, db_b, config_enabled, host, port_b, pin, temp / "b.log", args.rust_log,
        )
        processes.append((process_b, handle_b))
        b_started = time.monotonic()
        wait_ready(base_b, process_b)
        record("PASS", "ready")
        discovery_skip = SKIP_WARN in (temp / "a.log").read_text(errors="replace") or SKIP_WARN in (temp / "b.log").read_text(errors="replace")

        set_step("3 config activation")
        status_code_a, status_a = http(base_a + "/ext/lan_cowork/api/peer/status")
        status_code_b, status_b = http(base_b + "/ext/lan_cowork/api/peer/status")
        if status_code_a != 200 or status_code_b != 200:
            raise AssertionError("peer status was not 200")
        peer_a, peer_b = status_a["peer"], status_b["peer"]
        if not all(peer_a.get(key) for key in ("peer_id", "pubkey", "x25519_pk")) or not all(peer_b.get(key) for key in ("peer_id", "pubkey", "x25519_pk")):
            raise AssertionError("peer descriptor is incomplete")
        record("PASS", "config enabled descriptors complete")

        set_step("4 config-absent control")
        process_c, handle_c = start_server(
            server, db_c, config_disabled, host, port_c, pin, temp / "c.log", args.rust_log,
        )
        processes.append((process_c, handle_c))
        wait_listening(host, port_c, process_c)
        control, _ = http(base_c + "/ext/lan_cowork/api/peer/status")
        if control == 200:
            raise AssertionError("config-absent status was 200")
        record("PASS", f"config key absent; status {control}")
        stop(process_c, handle_c)
        processes.pop()

        set_step("4b hybrid safety")
        process_hybrid, handle_hybrid = start_server(
            server, db_hybrid, config_enabled, host, port_hybrid, pin, temp / "hybrid.log",
            args.rust_log, standalone=False,
        )
        processes.append((process_hybrid, handle_hybrid))
        if process_hybrid.poll() == 1:
            raise AssertionError("hybrid server exited 1")
        wait_listening(host, port_hybrid, process_hybrid)
        if process_hybrid.poll() == 1:
            raise AssertionError("hybrid server exited 1")
        hybrid_status, _ = http(base_hybrid + "/ext/lan_cowork/api/peer/status")
        if hybrid_status != 405:
            raise AssertionError("hybrid status was not 405")
        record("PASS", "config ignored; daemon not started")
        stop(process_hybrid, handle_hybrid)
        processes.pop()

        set_step("5 sessions")
        session_a = session(base_a, pin)
        session_b = session(base_b, pin)
        record("PASS", "A and B authenticated")
        set_step("6 discovery")
        if discovery_skip:
            record("SKIP", "UDP bind unavailable")
        else:
            time.sleep(26)
            _, peers_a = http(base_a + "/ext/lan_cowork/api/peer/discover")
            _, peers_b = http(base_b + "/ext/lan_cowork/api/peer/discover")
            if not any(p.get("peer_id") == peer_b["peer_id"] for p in peers_a.get("peers", [])):
                raise AssertionError("A did not discover B")
            if not any(p.get("peer_id") == peer_a["peer_id"] for p in peers_b.get("peers", [])):
                raise AssertionError("B did not discover A")
            record("PASS", "mutual TOFU")

        set_step("7 register")
        before = db_peer(db_a, peer_b["peer_id"])
        status, _ = json_post(base_a, "/ext/lan_cowork/api/peer/register", {"host": host, "port": port_b})
        after = db_peer(db_a, peer_b["peer_id"])
        if status != 200 or not after or after[1] != port_b:
            raise AssertionError("peer registration failed")
        if discovery_skip:
            record("SKIP", "UDP unavailable; initial registration, no M7 update")
        else:
            if not before or before[0] != after[0]:
                raise AssertionError("peer token was not retained")
            record("PASS", "known-peer update; token retained")

        set_step("8 pairing")
        status, _ = json_post(base_a, "/ext/lan_cowork/api/client/pair/request", {"peer_id": peer_b["peer_id"]}, session_a, timeout=180)
        if status != 202:
            raise AssertionError("pair request was not accepted")
        status, requests = http(base_b + "/ext/lan_cowork/api/peer/pair/requests", opener=session_b, timeout=180)
        if status != 200 or not requests.get("requests"):
            raise AssertionError("pair request is unavailable")
        request_id = requests["requests"][0]["request_id"]
        status, approval = json_post(base_b, "/ext/lan_cowork/api/peer/pair/approve", {"request_id": request_id}, session_b, timeout=180)
        pairing_pin = approval.get("pin")
        if status != 200 or not pairing_pin:
            raise AssertionError("pair approval did not provide a PIN")
        status, _ = json_post(base_a, "/ext/lan_cowork/api/client/pair/verify", {"peer_id": peer_b["peer_id"], "request_id": request_id, "pin": pairing_pin}, session_a, timeout=180)
        pairing_pin = REDACTED
        if status != 200:
            raise AssertionError("pair verification failed")
        record("PASS", "request, approve, verify")

        set_step("9 signed inbound")
        paired_peer = db_peer(db_a, peer_b["peer_id"])
        if not paired_peer or not paired_peer[0]:
            raise RuntimeError("paired peer token is unavailable")
        peer_token = paired_peer[0]
        seed = identity_seed(db_a)
        heartbeat = {"generating": False, "queue_depth": 0, "bridges": [], "inference_types": []}
        allowed = {"event_type": "generation.progress", "event_data": {}}
        denied = {"event_type": "not.allowlisted", "event_data": {}}
        if signed_post(base_b, seed, peer_a["peer_id"], "/ext/lan_cowork/api/peer/heartbeat", heartbeat, token=peer_token)[0] != 200:
            raise AssertionError("heartbeat failed")
        if signed_post(base_b, seed, peer_a["peer_id"], "/ext/lan_cowork/api/peer/event", allowed, token=peer_token)[0] != 200:
            raise AssertionError("allowlisted event failed")
        if signed_post(base_b, seed, peer_a["peer_id"], "/ext/lan_cowork/api/peer/event", denied, token=peer_token)[0] != 403:
            raise AssertionError("non-allowlisted event was not forbidden")
        record("PASS", "heartbeat and event allowlist verified")
        set_step("9 token renew")
        if args.skip_slow:
            record("SKIP", "--skip-slow")
        else:
            time.sleep(max(0, 60 - (time.monotonic() - b_started)))
            deadline = time.monotonic() + 120
            while True:
                renew_status, renewed = signed_post(
                    base_b, seed, peer_a["peer_id"], "/ext/lan_cowork/api/peer/token/renew", {},
                    nonce=os.urandom(16).hex(),
                )
                if renew_status == 200:
                    renewed_peer_token = renewed.get("token")
                    if not renewed_peer_token:
                        raise AssertionError("renew response missing token")
                    record("PASS", "renewed token")
                    break
                if renew_status != 503 or time.monotonic() >= deadline:
                    raise AssertionError
                time.sleep(3)

        set_step("10 throttle")
        if args.skip_slow:
            record("SKIP", "--skip-slow")
        else:
            if not renewed_peer_token:
                raise RuntimeError("renewed peer token is unavailable")
            # The signed allowlisted event above deliberately exercises the same
            # process-global throttle. Restart B so this leg starts with its
            # required empty window rather than inheriting that event.
            stop(process_b, handle_b)
            processes.pop()
            process_b, handle_b = start_server(
                server, db_b, config_enabled, host, port_b, pin, temp / "b.log", args.rust_log,
            )
            processes.append((process_b, handle_b))
            wait_ready(base_b, process_b)
            # The restart above dropped B's session, so re-authenticate before
            # subscribing. A live SSE consumer is required: without one the
            # handler takes the "no local consumer" branch and logs the dropped
            # summary, which carries `dropped=` and never `relayed=`.
            subscriber = SseSubscriber(base_b, session(base_b, pin))
            time.sleep(1)
            burst_started = None
            sent = 0
            for _ in range(args.burst):
                if burst_started is not None and time.monotonic() - burst_started > 30:
                    break
                if burst_started is None:
                    burst_started = time.monotonic()
                throttle_event_status = signed_post(
                    base_b, seed, peer_a["peer_id"], "/ext/lan_cowork/api/peer/event", allowed,
                    token=renewed_peer_token,
                )[0]
                if throttle_event_status != 200:
                    raise AssertionError("throttle event failed")
                sent += 1
            if sent <= 0:
                raise AssertionError("throttle burst sent no events")
            first = log_matches(temp / "b.log")
            if len(first) != 1:
                throttle_log_error = f"expected 1 summary line, found {len(first)}"
                raise AssertionError
            if relayed_count(first[0]) != 1:
                throttle_log_error = f"expected relayed=1, found {relayed_count(first[0])}"
                raise AssertionError
            time.sleep(61)
            throttle_event_status = signed_post(
                base_b, seed, peer_a["peer_id"], "/ext/lan_cowork/api/peer/event", allowed,
                token=renewed_peer_token,
            )[0]
            if throttle_event_status != 200:
                raise AssertionError("post-window throttle event failed")
            second = log_matches(temp / "b.log")
            if len(second) != 2:
                throttle_log_error = f"expected 2 summary lines, found {len(second)}"
                raise AssertionError
            if relayed_count(second[1]) != sent:
                throttle_log_error = f"expected relayed={sent}, found {relayed_count(second[1])}"
                raise AssertionError
            subscriber.close()
            record("PASS", f"relayed 1 then {sent}")
    except Exception as error:
        detail = type(error).__name__
        if current_step == "8 pairing" and debug_binary:
            detail = "debug binary: initiator 10s outbound timeout is shorter than debug scrypt"
        elif current_step == "9 token renew" and renew_status is not None:
            detail = (f"unexpected status {renew_status}" if renew_status != 200
                      else "renew response missing token")
        elif current_step == "10 throttle" and throttle_event_status not in (None, 200):
            detail = f"event returned {throttle_event_status}"
        elif current_step == "10 throttle" and throttle_log_error:
            detail = throttle_log_error
        record("FAIL", detail)
    finally:
        set_step("11 teardown")
        for process, handle in reversed(processes):
            stop(process, handle)
        if args.keep_temp:
            record("SKIP", "--keep-temp")
        else:
            import shutil
            shutil.rmtree(temp, ignore_errors=True)
            record("PASS", "processes stopped; temp removed")
        completed_steps = {step for step, _, _, _ in results}
        for step in LEG_ORDER:
            if step not in completed_steps:
                results.append((step, "NOT RUN", "run aborted", 0.0))
        order = {step: index for index, step in enumerate(LEG_ORDER)}
        results.sort(key=lambda result: order.get(result[0], len(LEG_ORDER)))
    print(f"{'STEP':<20} {'RESULT':<6} {'ELAPSED':>8} DETAIL")
    for step, result, detail, elapsed in results:
        print(f"{step:<20} {result:<6} {elapsed:>7.1f}s {detail}")
    return 1 if any(result == "FAIL" for _, result, _, _ in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
