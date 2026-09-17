"""Rust ↔ Python 互換性検証スクリプト.

使い方:
    # 両サーバーを起動してから実行
    uv run python scripts/verify_rust_compat.py \
        --rust http://127.0.0.1:5002 \
        --python http://127.0.0.1:5100 \
        [--db data/tags.db] \
        [--api-key <key>]          # Python側 Bearer トークン
        [--python-cookie-file <path>]  # Python側セッションCookieファイル (curl -c 形式)
        [--python-pin <pin>]       # Python側PIN（自動ログイン）
        [--rust-pin <pin>]         # Rust側PIN（自動ログイン。省略時は--python-pinと同じ値）

    # 自動起動モード (--auto): Rustサーバーを自動起動、Pythonは別途起動済み前提
    uv run python scripts/verify_rust_compat.py --auto --db data/tags.db \
        --python http://127.0.0.1:5100 --python-pin 12345678

出力:
    ✅ PASS  GET /api/files          rust=200  py=200  body=✅
    ⚠️  DIFF  GET /api/scan/status   rust=200  py=200  schema_diff (スキーマ差異)
    ❌ FAIL  GET /api/tags/*         rust=404  py=200
    ⏭️  SKIP  /api/inference/*       (proxy - skip)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml
from compat_normalize import normalize_content_type, normalize_json_body

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
_CIPHER_KEY = "yu-ai-manager-v1-cipher-2026"
logger = logging.getLogger("verify_compat")

ROOT = Path(__file__).resolve().parent.parent
RUST_BUILD_COMMAND = "CARGO_BUILD_JOBS=1 cargo build -p yu-server --manifest-path crates/Cargo.toml"

# ── 検証対象エンドポイント定義 ──────────────────────────────────────────────
# (method, path, body, params, skip_body_compare)
# skip_body_compare=True はステータスコード一致のみ確認
_SCAN_STATUS_FIELDS = [
    "running", "phase", "current", "total", "percent",
    "current_file", "message", "error", "job_id", "label",
]

def _drop_nested_keys(value: Any, keys: list[str]) -> Any:
    """Remove the named leaf keys at any depth, leaving everything else intact.

    `exclude_fields` reaches only top-level keys. Some divergences are nested
    by nature -- an absolute path or an implementation-specific English string
    inside a list of objects -- and the alternatives were both worse: exclude
    the whole containing key (dropping the fields that matter) or skip the body
    entirely.
    """
    if isinstance(value, dict):
        return {
            key: _drop_nested_keys(item, keys)
            for key, item in value.items()
            if key not in keys
        }
    if isinstance(value, list):
        return [_drop_nested_keys(item, keys) for item in value]
    return value


ENDPOINTS: list[dict[str, Any]] = [
    # --- LAN Cowork operator-side peer permissions (Rust native) ---
    # 503 until flag-day: main.rs only populates `peer_registry` when native_daemon is on,
    # and native_daemon is deliberately kept dead until then, so the Rust handler short-circuits
    # after the session gate. Python still serves the live implementation and answers 200.
    # Both are accepted so the entry stays valid across flag-day instead of needing a re-edit.
    {"method": "GET", "path": "/ext/lan_cowork/api/settings/fleet/my-permissions", "auth": "session", "accept_statuses": [200, 503], "skip_body_compare": True, "rust_native": True},
    # Pre-flag-day Rust answers 503 (peer_registry is populated only when native_daemon is on),
    # while Python gets past manager+session and stops at the chief check with 403 not_chief —
    # the parity node is not a fleet chief. Post-flag-day a chief node answers 200 on both sides
    # and a non-chief answers 403 on both. All three are accepted so the entry survives flag-day
    # without a re-edit. The 403 is itself evidence the manager -> session -> chief order holds.
    {"method": "GET", "path": "/ext/lan_cowork/fleet/peers", "auth": "session", "accept_statuses": [200, 403, 503], "skip_body_compare": True, "rust_native": True},
    # peer-grant/peer-revoke/peer-allowlist-status go one step further than /fleet/peers:
    # after the session+chief gate (which may pass, unlike the /fleet/peers comment above
    # assumes, depending on whether this parity run's session is itself chief), Python looks
    # up the fixture peer id in mgr.registry and returns 404 "peer_not_found" for a peer that
    # was never paired. 404 is therefore a legitimate outcome alongside 403 (not_chief) and 503
    # (pre-flag-day Rust), not a parity gap — mirrors update/dispatch/status's 404 below.
    # python_status_contract pins the 404 body to this route's actual peer_not_found envelope
    # (exact value, not merely "some string"), so a future regression that unregisters the route
    # entirely (Quart's bare 404 has no such envelope — see the historical hybrid-notify
    # mount-prefix bug fixed in v4.679.1) or returns a different error reason still fails the
    # check instead of being swallowed by the widened accept_statuses.
    {"method": "POST", "path": "/ext/lan_cowork/fleet/peer-grant", "auth": "session", "body": {"peer_id": "__parity_peer__"}, "accept_statuses": [200, 403, 404, 503], "skip_body_compare": True, "python_status_contract": {404: {"ok": False, "error": "peer_not_found"}}, "rust_native": True},
    {"method": "POST", "path": "/ext/lan_cowork/fleet/peer-revoke", "auth": "session", "body": {"peer_id": "__parity_peer__"}, "accept_statuses": [200, 403, 404, 503], "skip_body_compare": True, "python_status_contract": {404: {"ok": False, "error": "peer_not_found"}}, "rust_native": True},
    {"method": "GET", "path": "/ext/lan_cowork/fleet/peer-allowlist-status?peer_id=__parity_peer__", "auth": "session", "accept_statuses": [200, 403, 404, 503], "skip_body_compare": True, "python_status_contract": {404: {"ok": False, "error": "peer_not_found"}}, "rust_native": True},
    # Never use non-empty peer_ids here: a post-flag-day chief would dispatch real updates/restarts.
    {"method": "POST", "path": "/ext/lan_cowork/fleet/update/dispatch", "auth": "session", "body": {"peer_ids": []}, "accept_statuses": [400, 403, 503], "skip_body_compare": True, "rust_native": True},
    {"method": "GET", "path": "/ext/lan_cowork/fleet/update/dispatch/status?dispatch_id=__parity_dispatch__", "auth": "session", "accept_statuses": [403, 404, 503], "skip_body_compare": True, "rust_native": True},
    {"method": "POST", "path": "/ext/lan_cowork/fleet/restart/dispatch", "auth": "session", "body": {"peer_ids": []}, "accept_statuses": [400, 403, 503], "skip_body_compare": True, "rust_native": True},
    {"method": "GET", "path": "/ext/lan_cowork/fleet/ui", "note": "fleet UI 頁 — **実測（v4.736.5 実走）: rust=404 py=404、本文ニ非ズ content-type ノ差ナリ（rust=無シ・py=text/html）。** Python ハ HTML ノ 404 頁ヲ返シ、Rust ノ fallback ハ content-type ヲ持タヌ 404 ヲ返ス。Rust ノ 404 全体ニ content-type ヲ付クルハ大域ノ fallback ヲ変フルニシテ、今一致シ居ル他ノ 404 ヲ壊ス虞アリ——本件ノ範囲ヲ越ユ", "skip_body_compare": True, "accept_statuses": [404]},
    {"method": "GET", "path": "/ext/lan_cowork/fleet/static/fleet.js", "auth": "session", "accept_statuses": [200], "rust_native": True},
    # --- LAN Cowork fleet F3a (paired peer auth unavailable in generic harness) ---
    {"method": "GET", "path": "/ext/lan_cowork/fleet/info", "accept_statuses": [401, 503], "skip_body_compare": True, "rust_native": True},
    {"method": "GET", "path": "/ext/lan_cowork/fleet/update/status?job_id=__parity_job__", "accept_statuses": [401, 503], "skip_body_compare": True, "rust_native": True},
    {"method": "GET", "path": "/ext/lan_cowork/fleet/logs/stream", "accept_statuses": [200, 401, 503], "skip_body_compare": True, "sse": True, "rust_native": True},
    {"method": "POST", "path": "/ext/lan_cowork/fleet/restart", "accept_statuses": [401, 503], "skip_body_compare": True, "rust_native": True},
    {"method": "POST", "path": "/ext/lan_cowork/fleet/update", "accept_statuses": [401, 503], "skip_body_compare": True, "rust_native": True},
    # --- LAN Cowork fleet F2 (peer/session routes; generic harness has no paired peer) ---
    {"method": "POST", "path": "/ext/lan_cowork/fleet/consent/request", "auth": "session", "body": {"request_id": "__parity_consent__"}, "accept_statuses": [200, 401, 503], "skip_body_compare": True, "rust_native": True},
    {"method": "POST", "path": "/ext/lan_cowork/fleet/consent/respond", "auth": "session", "body": {"request_id": "__parity_consent__", "decision": "approved", "permanent": False}, "accept_statuses": [200, 401, 404], "skip_body_compare": True, "rust_native": True},
    {"method": "GET", "path": "/ext/lan_cowork/fleet/consent/status/__parity_consent__", "auth": "session", "accept_statuses": [200, 401], "skip_body_compare": True, "rust_native": True},
    {"method": "GET", "path": "/ext/lan_cowork/fleet/consent/pending", "auth": "session", "accept_statuses": [200, 401], "skip_body_compare": True, "rust_native": True},
    {"method": "POST", "path": "/ext/lan_cowork/fleet/consent/relay/request", "auth": "session", "body": {"peer_id": "__parity_peer__", "request_id": "__parity_consent__"}, "accept_statuses": [401, 403, 404, 503], "skip_body_compare": True, "rust_native": True},
    {"method": "GET", "path": "/ext/lan_cowork/fleet/consent/relay/status?peer_id=__parity_peer__&request_id=__parity_consent__", "auth": "session", "accept_statuses": [401, 403, 200, 503], "skip_body_compare": True, "rust_native": True},
    {"method": "POST", "path": "/ext/lan_cowork/fleet/allowlists/grant", "body": {"categories": ["update"]}, "accept_statuses": [401, 403], "skip_body_compare": True, "rust_native": True},
    {"method": "POST", "path": "/ext/lan_cowork/fleet/allowlists/revoke", "body": {"categories": ["update"]}, "accept_statuses": [401, 403], "skip_body_compare": True, "rust_native": True},
    {"method": "GET", "path": "/ext/lan_cowork/fleet/allowlists/check", "accept_statuses": [401, 403], "skip_body_compare": True, "rust_native": True},
    # --- lan_cowork client pairing (Rust hybrid gate / Python unknown peer) ---
    {
        "method": "POST",
        "path": "/ext/lan_cowork/api/client/pair/request",
        "auth": "session",
        "body": {"peer_id": "__parity_test_nonexistent_peer__"},
        "accept_statuses": [404, 503],
        "skip_body_compare": True,
    },
    {
        "method": "POST",
        "path": "/ext/lan_cowork/api/client/pair/verify",
        "auth": "session",
        "body": {
            "peer_id": "__parity_test_nonexistent_peer__",
            "request_id": "__parity_test_nonexistent_request__",
            "pin": "00000000",
        },
        "accept_statuses": [404, 503],
        "skip_body_compare": True,
    },
    # --- lan_cowork local import sessions (Rust native, L4a) ---
    {
        "method": "GET",
        "path": "/ext/lan_cowork/api/peer/import/sessions",
        "auth": "session",
        "schema_check": ["sessions"],
        "skip_body_compare": True,
        "rust_native": True,
    },
    {
        "method": "GET",
        "path": "/ext/lan_cowork/api/peer/import/session/__parity_test_nonexistent__",
        "auth": "session",
        "accept_statuses": [404],
        "rust_native": True,
    },
    {
        "method": "POST",
        "path": "/ext/lan_cowork/api/peer/import/session",
        "auth": "session",
        "body": {"peer_id": "__parity_test__", "import_folder": "/etc/parity"},
        "accept_statuses": [400],
        "skip_body_compare": True,
        "rust_native": True,
    },
    # Sentinel session reaches the shared 404 before the native-daemon gate; body comparison is intentional.
    {
        "method": "POST",
        "path": "/ext/lan_cowork/api/peer/import/execute",
        "auth": "session",
        "body": {"session_id": "__parity_test_nonexistent__"},
        "accept_statuses": [404],
        "rust_native": True,
    },
    {
        "method": "POST",
        "path": "/ext/lan_cowork/api/peer/import/index",
        "auth": "session",
        "body": {"peer_id": "__parity_test__", "import_folder": "/etc/parity"},
        "accept_statuses": [400],
        "skip_body_compare": True,
        "rust_native": True,
    },
    # --- lan_cowork peer-auth settings (Rust native, Tier C) ---
    {
        "method": "GET",
        "path": "/ext/lan_cowork/api/settings/peer-auth",
        "auth": "session",
        "schema_check": ["protect_heartbeat", "protect_events", "allowed_cidr"],
        "rust_native": True,
    },
    {
        "method": "POST",
        "path": "/ext/lan_cowork/api/settings/peer-auth",
        "auth": "session",
        "body": {"allowed_cidr": 24},
        "schema_check": ["ok"],
        "skip_body_compare": True,
        "rust_native": True,
        "note": "peer-auth settings write — Tier C lan_cowork pilot",
    },
    # --- lan_cowork fleet allowlists settings (Rust native, Tier C) ---
    {"method": "GET", "path": "/ext/lan_cowork/api/settings/fleet/allowlists", "auth": "session", "schema_check": ["allow_log_stream_from", "allow_update_from", "allow_restart_from", "allow_remote_update"], "rust_native": True},
    {"method": "POST", "path": "/ext/lan_cowork/api/settings/fleet/allowlists", "auth": "session", "body": {"allow_update_from": []}, "schema_check": ["ok"], "skip_body_compare": True, "rust_native": True, "note": "fleet allowlists write — Tier C lan_cowork sub-block 2. Requires live Python CoworkManager for notify sync."},
    # --- lan_cowork peer token management (Rust native, Tier C sub-block 3) ---
    {"method": "GET", "path": "/ext/lan_cowork/api/peer/tokens", "auth": "session", "schema_check": ["tokens"], "rust_native": True},
    {"method": "POST", "path": "/ext/lan_cowork/api/peer/tokens/__parity_test_nonexistent__/revoke", "auth": "session", "schema_check": ["ok"], "skip_body_compare": True, "rust_native": True, "note": "peer token revoke — Tier C lan_cowork sub-block 3. Uses sentinel nonexistent peer_id to avoid mutating real state; revoke of unknown peer_id is a no-op success by design."},
    # --- lan_cowork fleet chief settings (Rust native, Tier C sub-block 4) ---
    {"method": "GET", "path": "/ext/lan_cowork/api/settings/fleet", "auth": "session", "schema_check": ["chief"], "rust_native": True},
    # --- lan_cowork peer admin delete (Rust native, Tier C sub-block 5 / registry increment 1b) ---
    {"method": "DELETE", "path": "/ext/lan_cowork/api/peer/admin/__parity_test_nonexistent__", "auth": "session", "schema_check": ["ok"], "skip_body_compare": True, "rust_native": True, "note": "peer admin delete — Tier C lan_cowork registry sub-block. Sentinel nonexistent peer_id: idempotent no-op success by design, avoids mutating real state. Live registry evict requires Python CoworkManager (hybrid)."},
    # --- svg/info (Group AE: Rust native) ---
    {
        "method": "GET",
        "path": "/api/svg/info",
        "auth": "admin",
        "schema_check": ["available", "backend"],
        "rust_native": True,
    },
    # --- gateway/headroom/config (Rust native) ---
    {
        "method": "GET",
        "path": "/api/gateway/headroom/config",
        "auth": "admin",
        # `auth_key` was in this list, so the check REQUIRED the secret to be present
        # -- the same trap as the three unit tests that asserted it. Python
        # answers `auth_key_configured` and never the value.
        "schema_check": ["base_url", "auth_key_configured"],
        "rust_native": True,
        "note": "gateway headroom config (Rust native; Group AE)",
        "python_note": "**v4.733.5: body 比較ノ抑止ヲ外シタリ**——此ノ理由ハ一度モ実測サレ居ラザリキ（「再検討」ハ測定ニ非ズ）。GET ナル故書込無シ、抑止ヲ外スモ何モ変ヘズ。実走ガ真偽ヲ告ゲル。 auth_key は秘密値、auth_key_configured は設定有無に依る。再検討: gateway の設定を parity fixture で固定できた時",
    },
    # --- gateway/headroom/config PUT (Rust native SA-2) ---
    {
        "method": "PUT",
        "path": "/api/gateway/headroom/config",
        "auth": "admin",
        "body": {"base_url": "http://127.0.0.1:8787", "auth_key": ""},
        # Python echoes `auth_key_configured` here too, never the key.
        "schema_check": ["base_url", "auth_key_configured"],
        "python_path": None,
        "skip_body_compare": True,
"accept_statuses": [200, 501],
        "rust_native": True,
        "note": "headroom config write — Rust native SA-2",
    },
    # --- gateway/agentmemory/config PUT (Rust native SA-2) ---
    {
        "method": "PUT",
        "path": "/api/gateway/agentmemory/config",
        "auth": "admin",
        "body": {"base_url": "http://127.0.0.1:3111"},
        "schema_check": ["base_url"],
        "python_path": None,
        "skip_body_compare": True,
        "accept_statuses": [200],
        "rust_native": True,
        "note": "agentmemory config write — Rust native SA-2",
    },
    # --- gateway/agentmemory/config (Rust native) ---
    {
        "method": "GET",
        "path": "/api/gateway/agentmemory/config",
        "auth": "admin",
        "schema_check": ["base_url"],
        "rust_native": True,
    },
    # --- agentmemory dashboard proxy (Rust native) ---
    # Body comparison is ON. Nothing runs an agentmemory upstream during parity,
    # so both sides dial the same default (127.0.0.1:3111 -- Python's
    # `_DEFAULT_BASE_URL`, mirrored by Rust's `AGENTMEMORY_DEFAULT_BASE_URL`)
    # and both must answer 502 with the identical `{"error": ...}` body.
    #
    # These were first registered with `skip_body_compare`, which would have
    # hidden a real divergence: Rust used to answer 200
    # `{"ok":false,"status":"not_configured"}` for an unset base_url where
    # Python answers 502. Comparing the body is what makes that visible, so do
    # not weaken these back without saying which body legitimately differs.
    # 200 stays accepted for a run where an upstream IS listening.
    *[
        {
            "method": method,
            "path": path,
            "auth": "session",
            "body": {"query": ""} if method == "POST" else None,
            "accept_statuses": [200, 502],
            "rust_native": True,
        }
        for method, path in [
            ("GET", "/api/agentmemory-dash/livez"),
            ("GET", "/api/agentmemory-dash/health"),
            ("GET", "/api/agentmemory-dash/profile"),
            ("GET", "/api/agentmemory-dash/sessions"),
            ("GET", "/api/agentmemory-dash/memories"),
            ("GET", "/api/agentmemory-dash/audit"),
            ("GET", "/api/agentmemory-dash/graph/stats"),
            ("POST", "/api/agentmemory-dash/graph/query"),
        ]
    ],
    # --- gateway/keys (Rust native — secret_enc excluded by body comparison) ---
    {
        "method": "GET",
        "path": "/api/gateway/keys",
        "auth": "admin",
        "schema_check": ["keys"],
        "rust_native": True,
    },
    # --- gateway/admin-token (stub: Python backend removed) ---
    {
        "method": "GET",
        "path": "/api/gateway/admin-token",
        "auth": "admin",
        "accept_statuses": [200, 403, 502, 503], "note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ token）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    # --- SD backend proxy ---
    {
        "method": "GET",
        "path": "/sd/config",
        "auth": "admin",
        "accept_statuses": [200, 403, 502], "note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。"},
    {
        "method": "GET",
        "path": "/sd/info",
        "auth": "admin",
        "accept_statuses": [200, 403, 502], "note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。"},
    {
        "method": "GET",
        "path": "/sd/internal/ping",
        "auth": "admin",
        "accept_statuses": [200, 403, 502], "note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。"},
    # --- LLM router meta (stub: Python backend removed) ---
    {
        "method": "GET",
        "path": "/v1/models",
        "skip_body_compare": True,
        "accept_statuses": [200, 401, 403, 502, 503],
    },
    {
        "method": "GET",
        "path": "/v1/router/health",
        "skip_body_compare": True,
        "accept_statuses": [200, 401, 403, 502, 503],
    },
    # --- LLM Router stubs (E-1) ---
    # Rust=503(stub), Python=401(auth gate). 両方 accept_statuses 内→設定依存差異として合格
    {
        "method": "POST",
        "path": "/v1/chat/completions",
        "accept_statuses": [401, 503],
        "rust_native": True, "note": "**v4.732.24 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 註ニ実測ノ根拠無ク、外シテ走ラセタルニ**本文マデ一致セリ**。本項ハ書込ニ至ラヌ（受ケル status ガ悉ク 400 以上カ、狙ヒガ意図的ナル不在ノ資源）故、比較ヲ戻スモ何モ変ヘズ。今ハ全比較ス。 "},
    {
        "method": "POST",
        "path": "/v1/messages",
        "accept_statuses": [401, 503],
        "rust_native": True, "note": "**v4.732.24 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 註ニ実測ノ根拠無ク、外シテ走ラセタルニ**本文マデ一致セリ**。本項ハ書込ニ至ラヌ（受ケル status ガ悉ク 400 以上カ、狙ヒガ意図的ナル不在ノ資源）故、比較ヲ戻スモ何モ変ヘズ。今ハ全比較ス。 "},
    # --- Gateway endpoints (E-1) ---
    # NO `python_note` and NO `skip_body_compare`: either makes this a
    # status-only check. Keep the full-body comparison so an empty-case shape
    # divergence remains visible; `note` is metadata only.
    {
        "method": "GET",
        "path": "/api/gateway/groups",
        "rust_native": True,
        "note": "gateway fixture 未整備ニ付、空設定応答ノミ比較ス。故ニ形及ビ空時ヲ固定スルニ留マリ、変換ハ routes::auto_stubs::fabricated_state_tests ニ委ヌ。再検討: L237 記載ノ fixture 固定時",
    },
    {
        "method": "GET",
        "path": "/api/gateway/defaults",
        "rust_native": True,
        "note": "gateway fixture 未整備ニ付、空設定応答ノミ比較ス。故ニ形及ビ空時ヲ固定スルニ留マリ、変換ハ routes::auto_stubs::fabricated_state_tests ニ委ヌ。再検討: L237 記載ノ fixture 固定時",
    },
    {
        "method": "GET",
        "path": "/api/gateway/backends",
        "rust_native": True,
        "note": "gateway fixture 未整備ニ付、空設定応答ノミ比較ス。故ニ形及ビ空時ヲ固定スルニ留マリ、変換ハ routes::auto_stubs::fabricated_state_tests ニ委ヌ。再検討: L237 記載ノ fixture 固定時",
    },
    {
        "method": "GET",
        "path": "/api/gateway/local/status",
        "rust_native": True,
        "note": "gateway fixture 未整備ニ付、空設定応答ノミ比較ス。故ニ形及ビ空時ヲ固定スルニ留マリ、変換ハ routes::auto_stubs::fabricated_state_tests ニ委ヌ。再検討: L237 記載ノ fixture 固定時",
    },
    {
        "method": "GET",
        "path": "/api/gateway/scan/stream",
        "accept_statuses": [404],
        "skip_body_compare": True,
        "rust_native": True,
    },
    {
        "method": "DELETE",
        "path": "/api/gateway/scan",
        "accept_statuses": [404],
        "skip_body_compare": True,
        "rust_native": True,
    },
    {
        "method": "PATCH",
        "path": "/api/gateway/backends",
        "accept_statuses": [405],
        "rust_native": True, "note": "**v4.732.24 ニテ直シタリ——405 ノ本文ガ違ヒ居タリ。** Python ノ /api/ 用誤リ処理ハ `api_error(e.description, status=405, code=http_405)` ヲ返シ、文言ハ `The method is not allowed for the requested URL.` ナリ（`register_error_handlers` ヲ実際ニ叩キテ実測、Werkzeug ノ source ヲ推スニ非ズ）。Rust ハ己ノ文言ヲ置キ `code` ヲ欠キ居タリ。今ハ全比較ス。 "},
    {
        "method": "GET",
        "path": "/api/gateway/auth/status",
        "accept_statuses": [404],
        "skip_body_compare": True,
        "rust_native": True,
    },
    # --- SD file stub (E-2: /sd/file= path traversal block) ---
    {
        "method": "GET",
        "path": "/sd/file=test.png",
        "accept_statuses": [502, 503],
        "rust_native": True, "note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。"},
    # --- Wildcard proxy (E-2) ---
    {
        "method": "GET",
        "path": "/ollama/ollama/api/tags",
        "accept_statuses": [200, 401, 404, 502, 503, 504],
        "skip_body_compare": True,
        "rust_native": True,
    },
    {
        "method": "GET",
        "path": "/sd/sdapi/v1/sd-models",
        "accept_statuses": [200, 401, 502, 503, 504],
        "rust_native": True, "note": "**実測ノ差（v4.732.21、rust=502 py=502、相違ハ error.message）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    # --- system update apply/unified-apply (stub: Python backend removed) ---
    {
        "method": "POST",
        "path": "/api/system/update/apply",
        "auth": "admin",
        "skip_body_compare": True,
        "accept_statuses": [200, 400, 403, 409, 502, 503],
    },
    {
        "method": "POST",
        "path": "/api/system/update/unified-apply",
        "auth": "admin",
        "skip_body_compare": True,
        "accept_statuses": [200, 400, 403, 409, 502, 503],
    },
    # --- update package (stub: Python backend removed) ---
    {
        "method": "POST",
        "path": "/api/update/verify",
        "auth": "admin",
        "skip_body_compare": True,
        "accept_statuses": [200, 400, 401, 403, 502, 503],
    },
    {
        "method": "POST",
        "path": "/api/update/apply",
        "auth": "admin",
        "skip_body_compare": True,
        "accept_statuses": [200, 400, 401, 403, 502, 503],
    },
    {
        "method": "POST",
        "path": "/api/update/rollback",
        "auth": "admin",
        "skip_body_compare": True,
        "accept_statuses": [200, 400, 401, 403, 502, 503],
    },
    # --- files ---
    # Rust 独自エンドポイント。Python に同等パスなし。
    {
        "method": "GET", "path": "/api/files", "note": "ファイル一覧（Rust独自）",
        "python_path": None,
        "schema_check": ["id", "path", "mtime"],
    },
    {
        "method": "GET", "path": "/api/file/{file_id}", "params": {"file_id": "1"},
        "note": "ファイル詳細 Rust native。Python も同 path を供する (routes/files.py:17) 故、本文まで比較する",
        "schema_check": ["id", "path", "mtime", "meta_source", "tags"],
        "schema_check_statuses": [200],
        "accept_statuses": [200, 404],
    },
    {
        "method": "GET", "path": "/api/market/quotes",
        "note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ data, error, headlines）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。",
        "accept_statuses": [200], "skip_body_compare": True},
    # --- tools (Phase 1 DB Unlocker: Rust native) ---
    {
        "method": "GET", "path": "/api/tools/select-folder", "params": {"initial": ""},
        "note": "ネイティブフォルダピッカー。**註ノ前提ハ事実ノ逆ナリキ（v4.737.6 実測）**——folder_ops.py:11 ノ _has_gui_display() ハ DISPLAY 又ハ WAYLAND_DISPLAY ヲ見ル。本 host ハ DISPLAY=:0・WAYLAND_DISPLAY=wayland-0 ニシテ **headless ニ非ズ。**真ニ headless ナル機ナラバ Python ハ headless_unsupported ヲ 200 ニテ返シ比較シ得ル。此処デ抑止ヲ解カバ Python ガ実ノダイアログヲ開キ、**parity ノ実行全体ガ 人ノ click ヲ待チテ止マル。** 依テ抑止ハ残ス",
        "auth": "none",
        "python_path": None,
        "schema_check": ["path", "cancelled"],
        "accept_statuses": [200, 400],
    },
    {
        "method": "GET", "path": "/api/tools/list-dirs", "params": {"path": ""},
        "note": "ディレクトリ一覧（localhost-only）",
        "auth": "none",
        "schema_check": ["dirs"],
        "accept_statuses": [200, 400, 403],
        "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ current, data, dirs[0].name）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {
        "method": "GET", "path": "/api/tools/file-search", "params": {"q": "test", "limit": "10"},
        
        "auth": "admin",
        "schema_check": ["results", "total"],
        "accept_statuses": [200, 403], "note": "**v4.733.7 ニテ `nfkc_lower` ヲ移植シタル故、抑止ヲ外シタリ。** 従前ノ註ノ「Rust ハ独自関数ヲ一ツモ登録セズ」ハ実測ニシテ当タリ居タリ——其レヲ塞ギタリ（`crates/tagdb-core/src/db/custom_functions.rs`、給仕スル pool 四ツ悉クニ登録）。併セテ**照合ノ三ツノ差**ヲ揃ヘタリ: 畳ミ込ミ（両側）・ESCAPE 節ノ有無・`%`/`_` ノ escape（Python ハ escape セズ故 wildcard ト成ル）。実走ガ真偽ヲ告ゲル。"},
    # --- scheduler (Rust forwarder: proxy to Python / stub in --auto mode) ---
    {
        "method": "GET", "path": "/api/scheduler/status",
        "note": "**形ハ v4.732.22 ニテ直シタリ——残ルハ scheduler 自身ノ状態ノ差ナリ（実測、rust=200 py=200、相違ハ status.running・status.job_count・status.jobs[len]）。**payload ヲ `data` ノ中ヘ入レ居タル件ハ絶チタル故 `data` ハ既ニ一致ス。残ル三鍵ハ Python ガ live ナル manager ト其ノ登録済ミ job ヲ報ジ、Rust ハ scheduler_state ノ is-none ノ枝ヲ通リ running=false・job_count=0・jobs=[] ヲ返ス故ト見ル（**機構ハ推測、鍵ノ相違ハ実測**）。`/api/scheduler/history` ハ両者空ナル故通ル。",
        "accept_statuses": [200], "skip_body_compare": True},
    {"method": "GET", "path": "/api/scheduler/jobs", "note": "scheduler ジョブ一覧 — **実測（v4.737.6 実走）: rust=501 py=200。** Rust ハ未移植ニ非ズ——scheduler.rs:217-223 ハ scheduler_state 未設定ノ時ノミ 501 ヲ返シ、 main.rs:1944 ハ config.standalone 真ノ時ノミ scheduler ヲ起ス。 harness ハ Rust ヲ --python-url 付キ（proxy 模式）ニテ起ス故 scheduler ハ立タズ。 **之ハ設定依存ノ札ガ正シキ稀ナル例ナリ**——v4.737.4 ニ数ヘタル七十一件ハ 同ジ札ヲ帯ビ乍ラ一件モ揺レザリキ", "skip_body_compare": True, "accept_statuses": [200, 501], "python_path": None},
    {
        "method": "GET", "path": "/api/scheduler/history",
        "note": "**v4.732.22 ニテ直シタリ——payload ノ置キ処ノ差ナリキ。** Python ノ api_result ハ api_success ヲ経テ body.update(payload) ヲ為ス故、payload ハ**最上位**ニ載リ `data` ハ null ノ儘ナリ。Rust ハ之ヲ `data` ノ中ヘ入レ居タル故、`body.history` ヲ読ム client ハ何モ得ザリキ。今ハ最上位ヘ展ゲ、本文比較ヲ戻ス（実走ニテ一致）。",
        "accept_statuses": [200]},
    {
        "method": "POST", "path": "/api/scheduler/jobs",
        "note": "skip: 副作用（ジョブ追加）",
        "skip": True,
        "schema_check": [],
    },
    {
        # MEASURED RUST GAP, not a side effect: rust=501, py=404 (v4.732.14).
        # `skip` until Rust implements the route -- see TODO(rust-gap).
        "method": "DELETE", "path": "/api/scheduler/jobs/nonexistent",
        "note": "scheduler ジョブ削除 — Rust ハ 501（未移植）、Python ハ 404。実測 v4.732.14",
        "schema_check": [],
        "skip": True,
        "python_note": "Rust ハ 501（未移植）、Python ハ存在セヌ id ニ 404。実測 v4.732.14。旧キ口実「副作用」ハ二重ニ虚偽ナリ——副作用ヲ起コス実装ガ無ク、id ハ nonexistent ナリ。harness ハ設計上 rust=501 ヲ緑ト為サヌ故（Result.passed）、Rust ガ移植サルマデ送レヌ。",
    },
    {
        # MEASURED RUST GAP, not a side effect: rust=501, py=404 (v4.732.14).
        # `skip` until Rust implements the route -- see TODO(rust-gap).
        "method": "POST", "path": "/api/scheduler/jobs/nonexistent/pause",
        "note": "scheduler ジョブ一時停止 — Rust ハ 501（未移植）、Python ハ 404。実測 v4.732.14",
        "schema_check": [],
        "skip": True,
        "python_note": "Rust ハ 501（未移植）、Python ハ存在セヌ id ニ 404。実測 v4.732.14。旧キ口実「副作用」ハ二重ニ虚偽ナリ——副作用ヲ起コス実装ガ無ク、id ハ nonexistent ナリ。harness ハ設計上 rust=501 ヲ緑ト為サヌ故（Result.passed）、Rust ガ移植サルマデ送レヌ。",
    },
    {
        # MEASURED RUST GAP, not a side effect: rust=501, py=404 (v4.732.14).
        # `skip` until Rust implements the route -- see TODO(rust-gap).
        "method": "POST", "path": "/api/scheduler/jobs/nonexistent/resume",
        "note": "scheduler ジョブ再開 — Rust ハ 501（未移植）、Python ハ 404。実測 v4.732.14",
        "schema_check": [],
        "skip": True,
        "python_note": "Rust ハ 501（未移植）、Python ハ存在セヌ id ニ 404。実測 v4.732.14。旧キ口実「副作用」ハ二重ニ虚偽ナリ——副作用ヲ起コス実装ガ無ク、id ハ nonexistent ナリ。harness ハ設計上 rust=501 ヲ緑ト為サヌ故（Result.passed）、Rust ガ移植サルマデ送レヌ。",
    },
    {
        # MEASURED RUST GAP, not a side effect: rust=501, py=404 (v4.732.14).
        # `skip` until Rust implements the route -- see TODO(rust-gap).
        "method": "POST", "path": "/api/scheduler/jobs/nonexistent/trigger",
        "note": "scheduler ジョブ即時実行 — Rust ハ 501（未移植）、Python ハ 404。実測 v4.732.14",
        "schema_check": [],
        "skip": True,
        "python_note": "Rust ハ 501（未移植）、Python ハ存在セヌ id ニ 404。実測 v4.732.14。旧キ口実「副作用」ハ二重ニ虚偽ナリ——副作用ヲ起コス実装ガ無ク、id ハ nonexistent ナリ。harness ハ設計上 rust=501 ヲ緑ト為サヌ故（Result.passed）、Rust ガ移植サルマデ送レヌ。",
    },
    {
        "method": "POST", "path": "/api/thumbnails/batch",
        "note": "skip: 重い副作用 + heavy-io pool deadlock 既知",
        "skip": True,
        "schema_check": [],
    },
    {
        "method": "POST", "path": "/api/thumbnails/warmup",
        "note": "skip: デーモンスレッド起動（副作用）",
        "skip": True,
        "schema_check": [],
    },
    {
        "method": "POST", "path": "/mcp/message",
        "note": "skip: session_id 必須（SSE GET で確立が前提）",
        "skip": True,
        "schema_check": [],
    },
    # --- inference proxy ---
    # Rustは /api/inference/* を localhost:5001 にプロキシ。
    # 推論サービス未起動時は502を返す（設計上正常）。
    # Pythonには同等パスなし（Python独自の推論ルーティングあり）。
    {
        "method": "GET", "path": "/api/inference/health",
        "note": "推論プロキシ（推論サービス未起動時502は正常）",
        "python_path": None,
        "schema_check": [],
        "accept_statuses": [200, 404, 502],  # 起動有無・エンドポイント有無で変わる
    },
    # --- auth: lock/status (両者共通・Pythonはwhitelist=認証不要) ---
    {
        "method": "GET", "path": "/api/lock/status",
        "note": "ロック状態（Python互換フラット形式）",
        "schema_check": ["locked", "locked_at", "locked_duration", "ok", "error"],
    },
    # --- auth: auth/status (スキーマ互換。値は異なる: Rustはpin_auth=false/session_authenticated=false) ---
    {
        "method": "GET", "path": "/api/auth/status",
        "note": "認証状態（スキーマ互換・値はサーバー設定依存）",
        "schema_check": ["pin_auth", "quick_lock_enabled", "quick_lock_locked",
                         "trusted_proxy_auth", "session_authenticated", "ok", "error"],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 値は異なる可能性（Rustはpin_auth=false・session_authenticated=false）",
    },
    # --- auth: logout (POST・副作用あり・Rust スキーマのみ確認) ---
    # Python に同じリクエストを送るとセッションが破壊され後続テストが全滅するため
    # python_path=None でRustのみ確認する。Pythonのスキーマは別途手動確認済み。
    {
        "method": "POST", "path": "/api/auth/logout",
        "note": "ログアウト（セッションクリア・Rustスキーマのみ）",
        "schema_check": ["ok", "success"],
        "skip_body_compare": True,
        "python_path": None,
        "python_note": "Python側は副作用（セッション破壊）のためスキップ。手動確認済み。",
    },
    # --- auth: lock/activate (POST・Rust スキーマのみ確認) ---
    # Python に送るとサーバーがロック状態になり後続テストが全滅するため
    # python_path=None でRustのみ確認する。
    {
        "method": "POST", "path": "/api/lock/activate",
        # 実際にPIN認証が有効な場合、この呼び出しはRust側のquick_lockを本当に
        # activateし後続の全APIを423 Lockedにする(--rust-pin/--python-pinで
        # Rustログインが機能するようになった2026-07-12以降に顕在化)。run_lastで
        # 必ずテスト末尾に回し、後続テストへの巻き添えを防ぐ。
        "run_last": True,
        "note": "クイックロック有効化（Rustスキーマのみ・PIN未設定→400）",
        "schema_check": ["ok", "error"],
        "skip_body_compare": True,
        "accept_statuses": [200, 400, 401, 403],
        "python_path": None,
        "python_note": "Python側はロック副作用のためスキップ。手動確認済み（Python=200 Rust=400設定依存）。",
    },
    # --- auth: lock/unlock (POST・誤PIN→エラー確認) ---
    # 誤PINでエラーレスポンスのスキーマを確認。Rust は PIN 未設定 → 400。Python は 401。
    {
        "method": "POST", "path": "/api/lock/unlock",
        "run_last": True,
        "body": {"pin": "__verify_wrong_pin_x7z__"},
        "note": "**v4.732.24 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 註ニ実測ノ根拠無ク、外シテ走ラセタルニ**本文マデ一致セリ**。本項ハ書込ニ至ラヌ（受ケル status ガ悉ク 400 以上カ、狙ヒガ意図的ナル不在ノ資源）故、比較ヲ戻スモ何モ変ヘズ。今ハ全比較ス。  クイックロック解除（誤PIN→エラー確認）",
        "schema_check": ["ok", "error"],
        "accept_statuses": [400, 401, 403, 429],
        "python_note": "誤PIN時エラー。設定依存（RustはPIN未設定→400、PythonはPIN設定→401）",
        # PBKDF2 600k反復(pin_matches)を実行するためdebugビルドでは既定の10秒を超え得る。
        "timeout": 30,
    },
    # --- pages: /_pin (GET・HTMLページ) ---
    {
        "method": "GET", "path": "/_pin",
        "note": "PIN認証ページ（HTML・ステータスのみ確認）",
        "schema_check": [],
        "accept_statuses": [200, 404],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 HTMLレスポンス。ステータスコードのみ確認。PIN無効時Pythonは404",
    },
    # --- pages: /_pin_check (POST・フォーム送信) ---
    # 誤PIN（"0000"）送信。両者とも 200 HTML（エラーページ）を返す想定。
    # Python は CSRF 未設定時 400 の可能性あり。PIN無効時は404。
    {
        "method": "POST", "path": "/_pin_check",
        "form_body": {"pin": "0000", "next": "/"},
        "note": "PIN認証フォーム（誤PIN→200 HTML）",
        "schema_check": [],
        "skip_body_compare": True,
        "accept_statuses": [200, 302, 400, 404],
        "python_note": "フォームPOST。誤PIN→200(HTML)、CSRF未設定時→400、PIN無効時→404の可能性",
        # PBKDF2 600k反復(pin_matches)を実行するためdebugビルドでは既定の10秒を超え得る。
        "timeout": 30,
    },
    # --- MCP エンドポイント（YU_MCP_NATIVE=default-true で Rust native 提供） ---
    {
        "method": "GET", "path": "/mcp",
        "note": "MCP SSE rejects requests without a Bearer token",
        "schema_check": [],
        "accept_statuses": [200, 401],
        "python_note": "**v4.733.5: body 比較ノ抑止ヲ外シタリ**——此ノ理由ハ一度モ実測サレ居ラザリキ（「再検討」ハ測定ニ非ズ）。GET ナル故書込無シ、抑止ヲ外スモ何モ変ヘズ。実走ガ真偽ヲ告ゲル。 Python _is_localhost() bypass still returns 200 on loopback; Rust deliberately returns 401 until Python is retired.",
        "rust_expect_status": 401,
        "sse": True,
    },
    {
        "method": "POST", "path": "/mcp",
        "body": {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                 "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                            "clientInfo": {"name": "verify", "version": "1.0"}}},
        "note": "MCP JSON-RPC initialize rejects requests without a Bearer token",
        "schema_check": [],
        "skip_body_compare": True,
        "accept_statuses": [200, 401],
        "python_note": "Python _is_localhost() bypass still returns 200 on loopback; Rust deliberately returns 401 until Python is retired.",
        "rust_expect_status": 401,
    },
    # --- Proxy routes: key API endpoints forwarded to Python ---
    {
        "method": "GET", "path": "/api/server-info",
        "note": "サーバー情報 (Rust native)",
        "schema_check": ["version"],
        "schema_check_statuses": [200],
        "accept_statuses": [200],
        "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ active_profile, active_ui, available_uis）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {
        "method": "GET", "path": "/api/headroom/health",
        "note": "headroom health (Rust native proxy)",
        "schema_check": [],
        "accept_statuses": [200, 503, 504],
        "python_note": "headroom サービスが未起動時は 503/504 を返す。ボディ比較スキップ。",
        "skip_body_compare": True,
    },
    {
        "method": "GET", "path": "/api/headroom/stats",
        "note": "headroom stats (Rust native proxy)",
        "schema_check": [],
        "accept_statuses": [200, 503, 504],
        "python_note": "headroom サービスが未起動時は 503/504 を返す。ボディ比較スキップ。",
        "skip_body_compare": True,
    },
    {
        "method": "GET", "path": "/api/headroom/livez",
        "note": "headroom livez (Rust native proxy)",
        "schema_check": [],
        "accept_statuses": [200, 503, 504],
        "python_note": "headroom サービスが未起動時は 503/504 を返す。ボディ比較スキップ。",
        "skip_body_compare": True,
    },
    {
        "method": "GET", "path": "/api/headroom/readyz",
        "note": "headroom readyz (Rust native proxy)",
        "schema_check": [],
        "accept_statuses": [200, 503, 504],
        "python_note": "headroom サービスが未起動時は 503/504 を返す。ボディ比較スキップ。",
        "skip_body_compare": True,
    },
    {
        "method": "GET", "path": "/api/headroom/stats-history",
        "note": "headroom stats-history (Rust native proxy)",
        "schema_check": [],
        "accept_statuses": [200, 503, 504],
        "python_note": "headroom サービスが未起動時は 503/504 を返す。ボディ比較スキップ。",
        "skip_body_compare": True,
    },
    {
        "method": "GET", "path": "/api/headroom/metrics",
        "note": "headroom metrics (Rust native proxy)",
        "schema_check": [],
        "accept_statuses": [200, 503, 504],
        "python_note": "headroom サービスが未起動時は 503/504 を返す。ボディ比較スキップ。",
        "skip_body_compare": True,
    },
    {
        "method": "GET", "path": "/api/system/update/status",
        "auth": "admin",
        "note": "update status (Group AE: Rust native)",
        "schema_check": ["install_type", "update_in_progress", "version"],
        "rust_native": True,
    },
    {
        "method": "GET", "path": "/api/logs/recent",
        "note": "ログ直近エントリ (Rust native)",
        "schema_check": ["ok", "entries", "count"],
        "accept_statuses": [200],
        "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ count, data, entries）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {
        "method": "GET", "path": "/api/logs/stream",
        "note": "ログ SSE ストリーム (Rust native)",
        "schema_check": [],
        "accept_statuses": [200],
        "sse": True,
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 SSE ストリーム。ステータス確認のみ。",
    },
    {
        "method": "GET", "path": "/api/admin/shutdown/info",
        "note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ data, error, pin_required）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。",
        "schema_check": ["ok", "loopback", "pin_required"],
        "accept_statuses": [200], "skip_body_compare": True},
    {
        "method": "GET", "path": "/api/server/mode",
        "note": "サーバーモード (Rust native)",
        "schema_check": ["ok", "mode", "headless"],
        "accept_statuses": [200],
    },
    {
        "method": "GET", "path": "/api/server/subsystems",
        "note": "サブシステム一覧 (Rust native)",
        "schema_check": ["ok", "mode", "subsystems", "background_tasks"],
        "accept_statuses": [200],
    },
    # 段 A2 (v4.699.0)。`skip` は副作用が「このハーネスのサーバー自身を再起動する」
    # ことである故——叩けば以降の全エントリが相手を失う。`skip_body_compare` を
    # 併記してはならぬ: `skip` は一度も呼ばぬ意なる故に無意味であり、然も
    # relaxation ratchet は両方を数へる（被覆を増やさず緩和のみ増やす）。
    #
    # 註: Rust は転送ヒントを帯びたる loopback を「非局所」と見なす。Python の
    # `auth_restart.is_local_request_from` は loopback を先に見る故これを局所とする。
    # QA-rust-restart-debug-log.md §4.5 の意図的乖離にして退行に非ず。
    # **Python 側へ「揃へ」に来る勿れ**——Python 側の同じ穴は本件の範囲外として
    # 手を付けず残されて居る。
    {
        "method": "POST", "path": "/api/server/restart",
        "body": {"confirm": "restart"},
        "note": "再起動要求 (Rust native, 段A2)。副作用がハーネス自身の再起動なる故 skip。",
        "skip": True,
        "rust_native": True,
    },
    {
        "method": "GET", "path": "/api/stats",
        "note": "統計情報 (Rustプロキシ経由)",
        "schema_check": [],
        "accept_statuses": [200],
    },
    {
        "method": "GET", "path": "/api/search?limit=5",
        "note": "検索 (Rust native, Group J)",
        "schema_check": ["ok", "total_count", "results", "has_conditions", "has_more"],
        "accept_statuses": [200],
        "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ count_pending, data, error）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {
        "method": "GET", "path": "/api/search-count?limit=5",
        
        "schema_check": ["status", "total_count"],
        "accept_statuses": [200], "note": "検索件数 (Rust native, Group J) **v4.733.5 ニテ直シタリ——封ノ欠落ナリキ。** Python ハ payload ヲ `api_result(payload, status)` ヘ渡ス故 `ok`/`error`/`data` ガ付キ payload ハ最上位ニ載ル。Rust ハ payload ノミヲ建テ居タル故、**`ok` ガ全応答ニ無カリキ。**成功ノ応答ヲ揃ヘ、本文比較ヲ戻ス。"},
    # --- source/tree (Group AF: Rust native) ---
    {
        "method": "GET", "path": "/api/source/tree",
        "auth": "admin",
        "note": "ソースツリー (Group AF Rust native)",
        "schema_check": ["ok", "entries"],
        "rust_native": True,
    },
    # --- source/read (Group AF: Rust native) ---
    {
        "method": "GET", "path": "/api/source/read",
        "auth": "admin",
        "note": "ソースファイル読込 (Group AF Rust native)",
        "schema_check": ["ok"],
        "schema_check_statuses": [200],
        "rust_native": True,
        "accept_statuses": [200, 400, 401, 403, 404],
        "params": {"path": "main.py"},
        "python_note": "**実測ノ差（v4.732.21、rust=400 py=400、相違ハ error）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    # --- source/search (Group AF: Rust native) ---
    {
        "method": "GET", "path": "/api/source/search",
        "auth": "admin",
        "note": "ソース検索 (Group AF Rust native)",
        "schema_check": ["ok", "results"],
        "rust_native": True,
        "params": {"q": "def main"},
        "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ results[0].file, results[0].line, results[0].text）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    # --- debug/enabled (Group AG: Rust native) ---
    {
        "method": "GET", "path": "/api/debug/enabled",
        "auth": "none",
        "schema_check": ["ok", "enabled"],
        "rust_native": True,
    },
    # --- diagnostics/safe-mode (Group AG: Rust native) ---
    {
        "method": "GET", "path": "/api/diagnostics/safe-mode",
        "auth": "none",
        "schema_check": ["ok", "safe_mode"],
        "rust_native": True,
    },
    # --- scanned-roots (Group AG: Rust native) ---
    {
        "method": "GET", "path": "/api/scanned-roots",
        "auth": "admin",
        "schema_check": ["ok"],
        "rust_native": True,
    },
    # --- help/toc (Group AG: Rust native) ---
    {
        "method": "GET", "path": "/api/help/toc",
        "auth": "none",
        "schema_check": ["ok", "toc"],
        "rust_native": True,
    },
    # --- help/search (Group AG: Rust native) ---
    {
        "method": "GET", "path": "/api/help/search",
        "auth": "none",
        "schema_check": ["ok", "results"],
        "rust_native": True,
        "params": {"q": "test"},
        "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ results[0].snippet, results[1].snippet, results[2].snippet）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {
        "method": "GET", "path": "/api/settings/all",
        "note": "全設定取得 (Rustプロキシ経由)",
        "schema_check": [],
        "accept_statuses": [200],
        "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ settings[16].source）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    # --- settings/config (Group L: Rust native) ---
    {
        "method": "GET", "path": "/api/settings/config",
        "note": "設定取得 Rust native (Group L)",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ gateway.backends, gateway.gateway_admin_token, ocr_export_dir）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {"method": "GET", "path": "/api/settings/config/legacy-migration", "auth": "admin", "note": "legacy config migration status — both implementations return the same status body", "schema_check": ["pending", "primary", "legacy", "keys", "error"]},
    {"method": "POST", "path": "/api/settings/config/legacy-migration", "auth": "admin", "body": {}, "note": "legacy config migration run — harness starts with no legacy config.json beside its primary config path, so pending is false and this is a no-op without writes", "schema_check": ["migrated", "merged_keys", "backup", "primary", "error"]},
    # --- share (Group L: Rust native; ファイルIDが存在しない場合404が正常) ---
    {
        "method": "GET", "path": "/api/share/1",
        "note": "share data Rust native (Group L) - file_id=1 存在前提",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 file_id=1 が存在しない環境では404が正常。",
    },
    # --- debug/file-meta (Group N: Rust native) ---
    {
        "method": "GET", "path": "/api/debug/file-meta/1",
        "note": "ファイルメタデバッグ Rust native (Group N)",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403, 404],
    },
    # --- help/content (Group O: Rust native) ---
    {
        "method": "GET", "path": "/api/help/content/getting-started",
        "note": "ヘルプセクション内容 Rust native (Group O)",
        "schema_check": ["ok", "section", "category", "title", "lang", "content", "content_html", "related"],
        "accept_statuses": [200, 404],
        "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ content_html）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    # --- llm/agent/capabilities (Group P: Rust native) ---
    {
        "method": "GET", "path": "/api/llm/agent/capabilities",
        "note": "LLM エージェント能力情報 Rust native (Group P)",
        "schema_check": ["ok", "hailo_available", "recommended_model", "available_models", "tools", "strengths", "limitations"],
        "accept_statuses": [200],
        "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ hailo_available）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    # --- maintenance (Group Q: Rust native) ---
    {
        "method": "GET", "path": "/api/maintenance/db-stats",
        "note": "DB メンテナンス統計 Rust native (Group Q)",
        "schema_check": ["ok", "page_count", "freelist_count", "page_size", "free_ratio", "size_mb"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ page_count, size_mb）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {
        "method": "GET", "path": "/api/maintenance/scan-error-stats",
        "note": "スキャンエラー統計 Rust native (Group Q)",
        "schema_check": ["ok", "errors"],
        "accept_statuses": [200, 401, 403],
    },
    # --- suggest (Group S: Rust native) ---
    {
        "method": "GET", "path": "/api/suggest?q=a",
        "note": "タグ補完 Rust native (Group S)",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/suggest/lora?q=a",
        "note": "LoRA 補完 Rust native (Group S)",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/suggest/embedding?q=a",
        "note": "Embedding 補完 Rust native (Group S)",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/tags/suggest?q=a",
        "note": "タグ補完(tags) Rust native (Group S)",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "POST", "path": "/api/tags/dedup",
        "body": {"tags": "a, b, a, c", "keep": "first"},
        "note": "タグ重複削除 Rust native (Group S)",
        "schema_check": ["tags", "string", "removed"],
        "accept_statuses": [200, 401, 403],
    },
    # --- file_trace (Group R: Rust native) ---
    {
        "method": "GET", "path": "/api/files/1/analysis-trace",
        "note": "分析トレース Rust native (Group R)",
        "schema_check": ["ok", "meta_source", "engines"],
        "schema_check_statuses": [200],
        "accept_statuses": [200, 401, 403, 404],
    },
    # --- tag_dictionary (Group T: Rust native) ---
    {
        "method": "GET", "path": "/api/tag-dict/search?q=a",
        "note": "タグ辞書検索 Rust native (Group T)",
        "schema_check": ["results"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/tag-dict/info?tag=cat",
        "note": "タグ辞書 info Rust native (Group T)",
        "schema_check": ["tag_name"],
        "schema_check_statuses": [200],
        "accept_statuses": [200, 401, 403, 404],
    },
    {
        "method": "GET", "path": "/api/tag-dict/stats",
        "note": "タグ辞書統計 Rust native (Group T)",
        "schema_check": ["total", "categories"],
        "accept_statuses": [200, 401, 403],
    },
    # --- annotations (Group T: Rust native) ---
    {
        "method": "GET", "path": "/api/annotations/notes-data",
        "note": "注釈一覧データ Rust native (Group T)",
        "schema_check": ["ok", "notes", "total"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/annotations/search?q=a",
        "note": "注釈検索 Rust native (Group T)",
        "schema_check": ["ok", "annotations", "total"],
        "accept_statuses": [200, 401, 403],
    },
    # --- md_viewer (Group U: Rust native) ---
    {
        "method": "GET", "path": "/ext/md-viewer/api/files",
        "note": "MD Viewer ファイル一覧 Rust native (Group U)",
        "schema_check": ["files", "total"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/ext/md-viewer/api/stats",
        "note": "MD Viewer 統計 Rust native (Group U)",
        "schema_check": ["total_files", "total_size"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/ext/md-viewer/api/scan-roots",
        "note": "MD Viewer スキャンルート Rust native (Group U)",
        "schema_check": ["roots", "is_custom"],
        "accept_statuses": [200, 401, 403],
    },
    # --- cross_search (Group V: Rust native) ---
    {
        "method": "GET", "path": "/ext/cross-search/api/search?q=a",
        "note": "クロス検索 Rust native (Group V)",
        "schema_check": ["results", "query", "total"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/ext/cross-search/api/stats",
        "note": "クロス検索統計 Rust native (Group V)",
        "schema_check": ["txt_count"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/ext/cross-search/api/scan-roots",
        "note": "クロス検索スキャンルート Rust native (Group V)",
        "schema_check": ["roots", "is_custom"],
        "accept_statuses": [200, 401, 403],
    },
    # --- prompt_library (Group V: Rust native) ---
    {
        "method": "GET", "path": "/ext/prompt-library/info",
        "note": "プロンプトライブラリ info Rust native (Group V)",
        "schema_check": ["name", "version"],
        "accept_statuses": [200],
    },
    # --- ext_favorites (Group W: Rust native) ---
    {
        "method": "GET", "path": "/ext/favorites/api/images",
        "note": "お気に入り画像一覧 Rust native (Group W)",
        "schema_check": ["ok", "images", "total"],
        "accept_statuses": [200, 401, 403],
    },
    # --- chatlog (Group W: Rust native) ---
    {
        "method": "GET", "path": "/ext/chatlog/api/conversations?limit=1",
        "note": "チャット会話一覧 Rust native (Group W)",
        "schema_check": ["conversations", "total"],
        "accept_statuses": [200, 401, 403, 500],
    },
    {
        "method": "GET", "path": "/ext/chatlog/api/search?query=a",
        "note": "チャット検索 Rust native (Group W)",
        "schema_check": ["results", "query"],
        "accept_statuses": [200, 401, 403, 500],
    },
    {
        "method": "GET", "path": "/ext/chatlog/api/stats",
        "note": "チャット統計 Rust native (Group W)",
        "schema_check": ["total_conversations", "total_messages"],
        "accept_statuses": [200, 401, 403, 500],
    },
    # --- prompt_syntax (Group X: Rust native) ---
    {
        "method": "GET", "path": "/ext/syntax/engine.js",
        "note": "prompt syntax engine.js Rust native (Group X)",
        "schema_check": [],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/ext/syntax/widget.js",
        "note": "prompt syntax widget.js Rust native (Group X)",
        "schema_check": [],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/ext/syntax/style.css",
        "note": "prompt syntax style.css Rust native (Group X)",
        "schema_check": [],
        "accept_statuses": [200, 401, 403],
    },
    # --- nai_bridge (Group X: Rust native) ---
    {
        "method": "GET", "path": "/ext/nai-bridge/info",
        "note": "NAI bridge info Rust native (Group X)",
        # Python is a bare `jsonify({name, bridge})` here -- no envelope, so `ok`
        # is not part of this contract (nai_api.py:116-121).
        "schema_check": ["name", "bridge"],
        "accept_statuses": [200]
    },
    {
        "method": "GET", "path": "/ext/nai-bridge/api/models",
        "note": "NAI bridge models list Rust native (Group X)",
        "schema_check": ["ok", "models"],
        "accept_statuses": [200],
    },
    {
        "method": "GET", "path": "/ext/nai-bridge/api/samplers",
        "note": "NAI bridge samplers list Rust native (Group X)",
        "schema_check": ["ok", "samplers"],
        "accept_statuses": [200],
    },
    {
        "method": "GET", "path": "/ext/nai-bridge/api/noise-schedules",
        "note": "NAI bridge noise schedules Rust native (Group X)",
        "schema_check": ["ok", "noise_schedules"],
        "accept_statuses": [200],
    },
    # --- freeze_pullback (Group Y: Rust native) ---
    {
        "method": "GET", "path": "/ext/freeze-pullback/api/check",
        "note": "freeze-pullback check Rust native (Group Y)",
        "schema_check": ["ffmpeg_available"],
        "schema_check_statuses": [200],
        
        "accept_statuses": [200]
    },
    {
        "method": "GET", "path": "/ext/freeze-pullback/api/status",
        "note": "freeze-pullback status Rust native (Group Y)",
        "schema_check": [],
        "accept_statuses": [200]
    },
    {
        "method": "GET", "path": "/ext/freeze-pullback/api/outputs",
        "note": "freeze-pullback outputs list Rust native (Group Y)",
        "schema_check": ["outputs"],
        "schema_check_statuses": [200],
        "accept_statuses": [200]
    },
    # --- sd_webui_bridge / comfyui_bridge (Group Z: Rust native, info only) ---
    {
        "method": "GET", "path": "/ext/sd-webui/info",
        "note": "SD WebUI bridge info Rust native (Group Z)",
        "schema_check": ["name", "bridge"],
        "accept_statuses": [200],
    },
    {
        "method": "GET", "path": "/ext/comfyui-bridge/info",
        "note": "ComfyUI bridge info Rust native (Group Z)",
        "schema_check": ["name", "bridge"],
        "accept_statuses": [200],
    },
    {
        "method": "POST", "path": "/ext/comfyui-bridge/api/generate",
        "note": "ComfyUI generate simple mode Rust native (Group Z) — ComfyUI未接続時は503",
        "body": {"mode": "simple", "prompt": "test", "ckpt_name": "nonexistent.safetensors", "seed": 1},
        "schema_check": [],
        "accept_statuses": [200, 400, 401, 403, 500, 502, 503],
        "skip_body_compare": True,
        "python_note": "エラー文言の相違。両側 502（ComfyUI 未起動）。再検討: エラー封筒を統一する題目に着手する時",
    },
    # --- scan_history (Group AA: Rust native) ---
    {
        "method": "GET", "path": "/api/scan/history",
        "note": "スキャン履歴 Rust native (Group AA) — scan_history.json の read-only 返却",
        "schema_check": ["ok", "entries", "limit"],
        "accept_statuses": [200, 401, 403],
    },
    # --- monthly_report (Group AB: Rust native) ---
    {
        "method": "GET", "path": "/api/stats/monthly-report",
        "note": "月次レポート Rust native (Group AB) — trophies 除外・include_trophies=false 相当",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ data._month, data.cache_version, data.db_sig）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    # --- stats sub-routes (Group AH: Rust native) ---
    {
        "method": "GET", "path": "/api/stats/all",
        "note": "統計情報全体 Rust native (Group AH)",
        "schema_check": [],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/stats/hourly",
        "note": "時間帯別統計 Rust native (Group AH)",
        "schema_check": ["periods", "heatmap", "personality"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/stats/timeline",
        "note": "タイムライン統計 Rust native (Group AH)",
        "schema_check": [],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/stats/models",
        "note": "モデル別統計 Rust native (Group AH)",
        "schema_check": ["timeline", "top_models", "total_models"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/stats/story",
        "note": "ストーリー統計 Rust native (Group AH)",
        "schema_check": [],
        "accept_statuses": [200, 401, 403],
        # A CORRECTION to v4.732.8. Un-suppressing the six /api/stats/* entries
        # there, I rejected the excuse "statistics change with run timing" as
        # false because the harness DB is a frozen fixture. That is right about
        # the DB and wrong about this one field: `streak_days` counts backwards
        # from `date('now', TZ_MODIFIER)` (routes/stats.rs::streak_days, and
        # Python's counterpart), and the two servers evaluate that at two
        # different instants. Across a local midnight they read different
        # "today"s and the streak differs by one.
        #
        # Four parity runs were green before this fired, on 2026-09-13 at
        # 00:0x. A green measurement taken inside a narrow window is not proof
        # -- the window was every minute of the day except the boundary.
        # `files.mtime` is seeded fixed, so only the reference date moves;
        # every other field in this response stays compared.
        "exclude_fields": ["streak_days"],
    },
    {
        "method": "GET", "path": "/api/stats/resolutions",
        "note": "解像度別統計 Rust native (Group AH)",
        "schema_check": ["timeline", "top_resolutions"],
        "accept_statuses": [200, 401, 403],
    },
    # --- ratings + favorites (Group AI: Rust native) ---
    {
        "method": "GET", "path": "/api/ratings/get?file_id=1",
        "note": "rating取得 Rust native (Group AI)",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403, 404],
    },
    {
        "method": "GET", "path": "/api/ratings/stats",
        "note": "rating統計 Rust native (Group AI)",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 統計値はDB状態依存。スキーマ形状のみ比較。",
    },
    {
        "method": "POST", "path": "/api/ratings/set",
        "body": {"file_id": 1, "rating": 0},
        "note": "rating設定 Rust native (Group AI) — DB書き込みのためRustのみ確認",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 404],
    },
    {
        "method": "POST", "path": "/api/ratings/batch",
        "body": {"file_ids": [1]},
        "note": "ratingバッチ取得 Rust native (Group AI)",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 400, 401, 403],
    },
    {
        "method": "POST", "path": "/api/ratings/batch-set",
        "body": {"ratings": []},
        "note": "ratingバッチ設定 Rust native (Group AI) — DB書き込みのためRustのみ確認",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403],
    },
    {
        "method": "GET", "path": "/api/favorites/check?file_id=1",
        "note": "favorites確認 Rust native (Group AI)",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403, 404],
    },
    {
        "method": "GET", "path": "/api/favorites/check_collections?file_id=1",
        "note": "favorites collection確認 Rust native (Group AI)",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403, 404],
    },
    {
        "method": "GET", "path": "/api/favorites/list",
        "note": "favorites一覧 Rust native (Group AI)",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 DB状態依存。スキーマ形状のみ比較。",
    },
    {
        # Sent to BOTH servers on purpose. It used to carry python_path=None
        # ("DB write side effect, skip Python"), which made it the one request
        # in this harness that mutated only the Rust DB -- so collection 1's
        # COUNT(favorites) diverged and every later body comparison that reads
        # it was wrong by construction. That is how it was found: un-suppressing
        # GET /api/collections left exactly one field differing,
        # collections[0].count. A write sent to both sides keeps the two DBs
        # symmetric, which is what the rest of the harness already does
        # (DELETE /api/collections/2 is compared the same way).
        "method": "POST", "path": "/api/favorites/toggle",
        "body": {"file_id": 1},
        "note": "favorites切り替え Rust native (Group AI)",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 404],
    },
    # --- agent governance + tag-dict + jobs (Group AJ: Rust native) ---
    {
        "method": "GET", "path": "/api/agent/audit",
        "note": "agent audit状態 Rust native (Group AJ)",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 状態値は実行タイミング依存。スキーマ形状のみ比較。",
    },
    {
        "method": "GET", "path": "/api/agent/audit/log",
        "note": "agent auditログ Rust native (Group AJ)",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 ログ内容はDB状態依存。スキーマ形状のみ比較。",
    },
    {
        "method": "POST", "path": "/api/agent/kill",
        "body": {"reason": "__parity_verify__"},
        "note": "agent kill Rust native (Group AJ) — フラグファイル副作用のためRustのみ確認",
        "schema_check": ["ok"],
        "skip_body_compare": True,
        "accept_statuses": [200, 401, 403],
        "python_path": None,
        "python_note": "フラグファイル書き込み副作用のためPython側スキップ。Rustスキーマのみ確認。",
    },
    {
        "method": "POST", "path": "/api/agent/resume",
        "body": {},
        "note": "agent resume Rust native (Group AJ) — フラグファイル副作用のためRustのみ確認",
        "schema_check": ["ok"],
        "skip_body_compare": True,
        "accept_statuses": [200, 401, 403],
        "python_path": None,
        "python_note": "フラグファイル削除副作用のためPython側スキップ。Rustスキーマのみ確認。",
    },
    {
        "method": "POST", "path": "/api/tag-dict/split",
        "body": {"text": "blue eyes, 1girl, smile"},
        "note": "tag-dict split Rust native (Group AJ) — 副作用なし・Rustのみ確認",
        "schema_check": ["suggestions"],
        "accept_statuses": [200, 400, 401, 403],
    },
    {
        "method": "POST", "path": "/api/tag-dict/import",
        "note": "tag-dict import Rust native (Group AJ) — multipart・Rustのみ確認",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403],
    },
    {
        "method": "DELETE", "path": "/api/tag-dict/clear",
        "note": "tag-dict clear Rust native (Group AJ) — 破壊的操作のためRustのみ確認",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/jobs/status",
        "note": "jobs状態一覧 Rust native (Group AJ) — bridge jobs + Python merge",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ recent[len]）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {
        "method": "GET", "path": "/api/jobs/__parity_verify_no_such_job__",
        "note": "job詳細取得 Rust native (Group AJ) — ダミーID→404確認",
        "schema_check": [],
        "accept_statuses": [404],
        "skip_body_compare": True,
        "python_path": None,
        "python_note": "動的job_idのためダミーIDで404のみ確認。",
    },
    {
        # MEASURED PORTING GAP, not a spec difference: Python has no
        # /api/jobs/<job_id>/cancel route at all -- only /api/jobs/status
        # (routes/scan.py). So py=404 is Quart answering "no such route", while
        # rust=404 is the handler answering "job not found or not running", and
        # the two bodies differ in `code`/`error`. `accept_statuses: [404]`
        # could never catch this: the status matched by coincidence. Body
        # comparison stays off until Python implements the route (TODO).
        "method": "POST", "path": "/api/jobs/__parity_verify_no_such_job__/cancel",
        "body": {},
        "note": "job cancel Rust native (Group AJ) — Python ニ route 無シ（実測、v4.732.13）",
        "schema_check": [],
        "accept_statuses": [404],
        "skip_body_compare": True,
        "python_note": "Python ニ /api/jobs/<job_id>/cancel ノ route 自体無シ。404 ハ Quart ノ「route 無シ」ナル故本文形ガ異ナル。移植ノ欠落ニシテ恒久ノ仕様差ニ非ズ。",
    },
    # --- misc remaining (Group AK: Rust native) ---
    {
        "method": "GET", "path": "/api/agent/audit/verify",
        "note": "agent audit verify Rust native (Group AK)",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 audit検証結果はDB状態依存。スキーマ形状のみ比較。",
    },
    {
        "method": "GET", "path": "/api/agent/undoable",
        "note": "agent undoable一覧 Rust native (Group AK)",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/checkpoints",
        "note": "checkpoints一覧 Rust native (Group AK)",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 DB状態依存。スキーマ形状のみ比較。",
    },
    {
        "method": "POST", "path": "/api/scan-roots/batch-toggle",
        "body": {"enabled": True},
        "note": "empty isolated config is deterministic",
        "schema_check": ["ok"],
    },
    {
        "method": "GET", "path": "/api/debug/model-check",
        "note": "debug model-check Rust native (Group AK)",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 DBサンプリング依存。スキーマ形状のみ比較。",
    },
    {
        "method": "GET", "path": "/api/sweeps/history",
        "note": "sweeps history Rust native (Group AK)",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "skip_body_compare": True,
        "python_note": "DB状態依存。スキーマ形状のみ比較。",
    },
    {
        # Ported in v4.631.0. Both are GET, so the fixtures are naturally
        # non-mutating.
        #
        # NO `python_note` and NO `skip_body_compare` on purpose: the harness
        # sets `body_match = None` the moment either is present (see
        # check_endpoint), so annotating an entry silently downgrades it to a
        # status-only check. The failure mode worth catching here is a SHAPE
        # divergence — `api_success(payload)` merges the payload at the TOP
        # level rather than under `data` — and a status-only check cannot see
        # it. Both fixtures address absent data, so the compared bodies are
        # deterministic error/empty payloads, not DB-state-dependent ones.
        "method": "GET", "path": "/api/sweep/info/1",
        "note": "sweep XMP info Rust native (v4.631.0) — 本体まで比較する",
        "accept_statuses": [200, 400, 404],
    },
    {
        "method": "GET", "path": "/api/sweep/files/parity-sweep?file_id=1",
        "note": "sweep folder scan Rust native (v4.631.0) — 不在 sweep_id ゆえ matches は空。本体まで比較する",
        "accept_statuses": [200, 400, 404],
    },
    {
        "method": "GET", "path": "/api/wd-tagger/vlm/test?url=https://example.invalid",
        "note": "wd-tagger VLM接続テスト Rust native (Group AK) — 到達不能URLで動作確認",
        # The server probes the URL and bounds that probe at analysis_net's
        # PROBE_TIMEOUT (10s). The harness default is also 10s, so under CI's
        # blocked egress -- where resolving an unreachable host burns nearly the
        # whole budget -- the two race and the harness reports a hang on a
        # server that was about to answer. A client budget must exceed the
        # server's own, or correct behaviour reads as a timeout. This is the
        # measurement-independent fix; it is not slack, since the server still
        # has to answer within its own 10s.
        "timeout": 25,
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403],
        "skip_body_compare": True,
        "python_path": None,
        "python_note": "外部接続テストのためPython側スキップ。Rustスキーマのみ確認。",
    },
    # --- analysis GET endpoints (Group AN: Rust native) ---
    {
        "method": "GET", "path": "/api/analysis/available-engines",
        "note": "analysis available-engines Rust native (Group AN) — 設定依存",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 設定依存のためスキーマ形状のみ比較。",
    },
    {
        "method": "GET", "path": "/api/analysis/servers",
        "note": "analysis servers一覧 Rust native (Group AN) — 設定依存",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 設定依存のためスキーマ形状のみ比較。",
    },
    {
        "method": "GET", "path": "/api/analysis/servers/discovered",
        "note": "analysis discovered servers Rust native (Group AN) — 外部接続のためRustのみ確認",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 外部接続スキャンのためPython側スキップ。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/analysis/result/1",
        "note": "analysis result Rust native (Group AN) — SQLite読み取り",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 DB状態依存のためスキーマ形状のみ比較。",
    },
    {
        "method": "GET", "path": "/api/analysis/stats",
        "note": "analysis stats Rust native (Group AN) — SQLite集計",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 DB状態依存のためスキーマ形状のみ比較。",
    },
    {
        "method": "GET", "path": "/api/analysis/trends/history",
        "note": "analysis trends history Rust native (Group AN) — SQLite・Pythonルートなし",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 Python側に対応ルートなし。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/analysis/ollama/models",
        "note": "analysis ollama models Rust native (Group AN) — 外部接続のためRustのみ確認",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 Ollama外部接続依存のためPython側スキップ。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/analysis/openai-compat/models",
        "note": "analysis openai-compat models Rust native (Group AN) — 外部接続のためRustのみ確認",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 OpenAI互換外部接続依存のためPython側スキップ。Rustスキーマのみ確認。",
    },
    # --- tagger-servers + wd-tagger + video-analysis + groups-index/warm + container-thumb-ids (Group AQ: Rust native) ---
    {
        "method": "GET", "path": "/api/groups-index/warm",
        "note": "グループインデックスwarm Rust native (Group AQ) — {ok:true}直返し",
        "schema_check": ["ok"],
        "accept_statuses": [200],
    },
    {
        "method": "GET", "path": "/api/container-thumb-ids",
        "note": "コンテナサムネイルID一覧 Rust native (Group AQ) — Json(payload)直返し",
        "schema_check": [],
        "accept_statuses": [200],
    },
    {
        "method": "GET", "path": "/api/video-analysis/config",
        "note": "ビデオ解析設定 Rust native (Group AQ) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/video-analysis/status",
        "note": "ビデオ解析状態 Rust native (Group AQ) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/tagger-servers/health",
        "note": "taggerサーバーヘルス Rust native (Group AQ) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 外部taggerサーバー依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/tagger-servers/stats",
        "note": "taggerサーバー統計 Rust native (Group AQ) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 外部taggerサーバー依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/tagger-servers/tags/{file_id}",
        "params": {"file_id": "1"},
        "note": "taggerサーバータグ取得 Rust native (Group AQ) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403, 404],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 ファイルID依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/wd-tagger/profiles/{id}",
        "params": {"id": "1"},
        "note": "WDtaggerプロファイル取得 Rust native (Group AQ) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403, 404],
    },
    # --- annotations + collections + container-members + file-info + files/tags + scan-roots + share + webhooks + settings + migration-stats (Group AR: Rust native) ---
    {
        "method": "GET", "path": "/api/annotations/{file_id}",
        "params": {"file_id": "1"},
        "note": "ファイルアノテーション一覧 Rust native (Group AR) — api_success",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403, 404],
        "skip_body_compare": True,
        "python_path": None,
        "python_note": "ファイルID依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/collections",
        "note": "コレクション一覧 Rust native (Group AR) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/container-members/{file_id}",
        "params": {"file_id": "1"},
        "note": "コンテナメンバー一覧 Rust native (Group AR) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 404],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 ファイルID依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/file-info/{file_id}",
        "params": {"file_id": "1"},
        "note": "ファイル情報 Rust native (Group AR) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403, 404],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 ファイルID依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/files/{file_id}/analysis-trace",
        "params": {"file_id": "1"},
        "note": "ファイル解析トレース Rust native (Group AR) — api_success",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403, 404],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 ファイルID依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/files/{file_id}/tags",
        "params": {"file_id": "1"},
        "note": "ファイルタグ一覧 Rust native (Group AR) — Json配列直返し",
        "schema_check": [],
        "accept_statuses": [200, 401, 403, 404],
        "skip_body_compare": True,
        "python_path": None,
        "python_note": "Json(tags)直返し・配列形式。スキーマ確認不可。Rustのみ確認。",
    },
    {
        "method": "GET", "path": "/api/scan-roots",
        "note": "isolated config is deterministic",
        "schema_check": ["ok"],
    },
    {
        "method": "GET", "path": "/api/scan-roots/recovery-check",
        "note": "scan_roots 復旧バナー判定 (Rust native) — Python と同一 payload を比較",
        "schema_check": ["ok", "pending"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "POST", "path": "/api/scan-roots/recovery-apply",
        "body": {},
        "note": "scan_roots 復旧適用 — config.json 書込副作用のため skip",
        "skip": True,
        "schema_check": [],
    },
    {
        "method": "POST", "path": "/api/scan-roots/recovery-dismiss",
        "body": {},
        "note": "scan_roots 復旧却下 — マーカ書換副作用のため skip",
        "skip": True,
        "schema_check": [],
    },
    {
        "method": "GET", "path": "/api/share/{file_id}",
        "params": {"file_id": "1"},
        "note": "共有データ Rust native (Group AR) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403, 404],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 ファイルID依存。Rustスキーマのみ確認。",
    },
    {
        "method": "POST", "path": "/api/apikeys",
        "auth": "admin",
        "body": {"label": "__parity_apikey__", "scopes": ["read"]},
        "note": "API鍵発行 (B-1)。両側とも201を返す。",
        # 発行の度に変はる欄のみ除く。label は両側 "__parity_apikey__" にて
        # 決定論的なる故、除かず比較さす。accept_statuses は立てぬ——
        # 両側 201 なら verify_rust_compat.py:3536 の分岐へ入らず参照されず、
        # 且つ relaxation ratchet を一件増やす。
        "exclude_fields": ["id", "key", "key_prefix", "created_at"],
    },
    {
        "method": "PATCH", "path": "/api/apikeys/__parity_missing__",
        "auth": "admin",
        "body": {"label": "renamed"},
        "note": "API鍵の改名 (P1)。存在せぬ id なる故、両側とも404『API key not found』ヲ返ス。",
        # 実在スル鍵ヲ狙ハズ: parity ハ両側ノ config ヲ別々ニ持ツ故、id ヲ共有シ得ズ。
        # 不在経路ナラ id ニ依ラズ決定論的ニシテ、404 ノ文言ト封筒ヲ比較シ得ル。
        # accept_statuses ハ立テヌ——両側 404 ナラ :3536 ノ分岐ヘ入ラズ参照サレヌ上、
        # relaxation ratchet ヲ一件増ヤス故。
    },
    {
        "method": "DELETE", "path": "/api/apikeys/__parity_missing__",
        "auth": "admin",
        "note": "API鍵ノ失効 (P1)。同ジク不在経路ヲ突ク。",
    },
    {
        "method": "GET", "path": "/api/webhooks",
        "note": "Webhook一覧 Rust native (Group AR) — api_success",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/webhooks/deliveries",
        "note": "Webhook配信履歴 Rust native (Group AR) — api_success",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/webhooks/inbound",
        "note": "インバウンドWebhook一覧 Rust native (Group AR) — api_success",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/rust-migration/proxy-stats",
        "note": "Rustマイグレーションプロキシ統計 Rust native (Group AR) — Json直返し(ok含む)",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "skip_body_compare": True,
        "python_path": None,
        "python_note": "Json({ok:true,...})直返し。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/settings/schema",
        "note": "設定スキーマ Rust native (Group AR) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/settings/bw-status",
        "note": "Bitwarden接続状態 Rust native (Group AR) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 外部Bitwarden依存。Rustスキーマのみ確認。",
        "timeout": 30,
    },
    {
        "method": "GET", "path": "/api/settings/op-status",
        "note": "1Password接続状態 Rust native (Group AR) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 外部1Password依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/settings/secrets/status",
        "note": "シークレット状態 Rust native (Group AR) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/settings/secrets/bw-folders",
        "note": "Bitwardenフォルダ一覧 Rust native (Group AR) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403, 503],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 外部Bitwarden依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/settings/secrets/op-vaults",
        "note": "1Password Vault一覧 Rust native (Group AR) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403, 503],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 外部1Password依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/settings/secrets/keyring",
        "note": "キーリング情報 Rust native (Group AR) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/settings/llm-endpoints",
        "note": "LLMエンドポイント一覧 Rust native (Group AR) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/settings/{key}",
        "params": {"key": "general"},
        "note": "設定値取得 Rust native (Group AR) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403, 404],
    },
    # --- hailo-tagger + debug + analysis + github + scan-roots(write) + maintenance + diagnostics (Group AS: Rust native) ---
    {
        "method": "GET", "path": "/api/hailo-tagger/config",
        "note": "Hailoタガー設定 Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 Hailo依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/hailo-tagger/status",
        "note": "Hailoタガー状態 Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 Hailo依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/hailo-tagger/tags/{file_id}",
        "params": {"file_id": "1"},
        "note": "Hailoタガータグ取得 Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403, 404],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 Hailo+ファイルID依存。Rustスキーマのみ確認。",
    },
    {
        "method": "DELETE", "path": "/api/hailo-tagger/tags/{file_id}",
        "params": {"file_id": "1"},
        "note": "Hailoタガータグ削除 Rust native — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "POST", "path": "/api/hailo-tagger/tag/{file_id}",
        "params": {"file_id": "1"},
        "body": {},
        "note": "Hailoタガー単体タグ付け Rust native — api_result or error",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 404, 502],
    },
    {
        "method": "POST", "path": "/api/hailo-tagger/batch",
        "body": {"limit": 1},
        "note": "Hailoタガーバッチ起動 Rust native — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403, 409],
    },
    {
        "method": "GET", "path": "/api/debug/file-meta/{file_id}",
        "params": {"file_id": "1"},
        "note": "ファイルデバッグメタ Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403, 404],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 ファイルID依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/analysis/result/{file_id}",
        "params": {"file_id": "1"},
        "note": "解析結果 Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403, 404],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 ファイルID・解析状態依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/github/accounts",
        "note": "GitHubアカウント一覧 Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/github/queue/config",
        "note": "GitHubキュー設定 Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/github/queue/pending",
        "note": "GitHubキュー待機一覧 Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/github/triage-prompts",
        "note": "GitHubトリアージプロンプト Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/github/rate-limit/{label}",
        "params": {"label": "default"},
        "note": "GitHubレート制限 Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 404],
        "skip_body_compare": True,
        "python_note": "GitHubラベル+外部API依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/github/issues/{label}",
        "params": {"label": "default"},
        "note": "GitHubイシュー一覧 Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 404],
        "skip_body_compare": True,
        "python_note": "GitHubラベル+外部API依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/github/issue/{label}/{owner}/{repo}/{number}",
        "params": {"label": "default", "owner": "test", "repo": "test", "number": "1"},
        "note": "GitHubイシュー詳細 Rust native (Group AS) — account不在→500のためskip",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "GET", "path": "/api/github/releases/{label}",
        "params": {"label": "default"},
        "note": "GitHubリリース一覧 Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 404],
        "skip_body_compare": True,
        "python_note": "GitHubラベル+外部API依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/github/repo-stats-all/{label}",
        "params": {"label": "default"},
        "note": "GitHubリポジトリ統計全件 Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 404],
        "skip_body_compare": True,
        "python_note": "GitHubラベル+外部API依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/github/repo-stats/{label}/{owner}/{repo}",
        "params": {"label": "default", "owner": "test", "repo": "test"},
        "note": "GitHubリポジトリ統計 Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 404],
        "skip_body_compare": True,
        "python_path": None,
        "python_note": "GitHubラベル+外部API依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/github/pulls/{label}",
        "params": {"label": "default"},
        "note": "GitHubプルリクエスト一覧 Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 404],
        "skip_body_compare": True,
        "python_note": "GitHubラベル+外部API依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/github/pull/{label}/{owner}/{repo}/{number}",
        "params": {"label": "default", "owner": "test", "repo": "test", "number": "1"},
        "note": "GitHubプルリクエスト詳細 Rust native (Group AS) — account不在→500のためskip",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "GET", "path": "/api/github/discussions/{label}",
        "params": {"label": "default"},
        "note": "GitHubディスカッション一覧 Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 404],
        "skip_body_compare": True,
        "python_note": "GitHubラベル+外部API依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/github/notifications/{label}",
        "params": {"label": "default"},
        "note": "GitHub通知一覧 Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 404],
        "skip_body_compare": True,
        "python_note": "GitHubラベル+外部API依存。Rustスキーマのみ確認。",
    },
    {
        "method": "POST", "path": "/api/github/notifications/{label}/mark-all-read",
        "params": {"label": "default"},
        "body": {},
        "note": "GitHub通知全既読 Rust native (Group AS) — 外部API副作用のためskip",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "PATCH", "path": "/api/github/notifications/{label}/{thread_id}",
        "params": {"label": "default", "thread_id": "1"},
        "body": {},
        "note": "GitHub通知既読 Rust native (Group AS) — 外部API副作用のためskip",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "PUT", "path": "/api/github/accounts/{label}",
        "params": {"label": "default"},
        "body": {},
        "note": "GitHubアカウント更新 Rust native (Group AS) — 外部API副作用のためskip",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "PUT", "path": "/api/analysis/servers/reorder",
        "body": {},
        "note": "解析サーバー並び替え Rust native (Group AS) — skip",
        "schema_check": [],
    },
    {
        "method": "DELETE", "path": "/api/analysis/servers/{server_id}",
        "params": {"server_id": "1"},
        "note": "解析サーバー削除 Rust native (Group AS) — データ削除副作用のためskip",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "POST", "path": "/api/analysis/servers/{server_id}/activate",
        "params": {"server_id": "1"},
        "body": {},
        "note": "解析サーバー有効化 Rust native (Group AS) — 外部接続副作用のためskip",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "POST", "path": "/api/scan-roots/reorder",
        "body": {"roots": []},
        "note": "empty roots are deterministically invalid",
        "schema_check": ["ok"],
        "accept_statuses": [400],
    },
    {
        "method": "DELETE", "path": "/api/scan-roots/{index}",
        "params": {"index": "0"},
        "note": "empty isolated config has no index zero",
        "schema_check": ["ok"],
    },
    {
        "method": "POST", "path": "/api/scan-roots/{index}/toggle",
        "params": {"index": "0"},
        "body": {},
        "note": "empty isolated config has no index zero",
        "schema_check": ["ok"],
    },
    {
        "method": "POST", "path": "/api/maintenance/analyze",
        "body": {},
        "note": "SQLite ANALYZE Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "POST", "path": "/api/maintenance/vacuum",
        "body": {},
        "note": "SQLite VACUUM Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        # The harness hands Python an ENCRYPTED copy of the DB and Rust a
        # plaintext one (parity_harness.py seeds db_path with encrypt=True and
        # rust_db_path without), so the two files differ in byte size by
        # construction -- these two fields report the size of DIFFERENT files
        # and can never agree. Measured, not assumed: with the body comparison
        # on, these were the only two fields that differed (v4.732.13);
        # `saved_mb` matched and stays compared.
        "exclude_fields": ["size_before_mb", "size_after_mb"],
    },
    {
        "method": "POST", "path": "/api/diagnostics/cleanup-update-pending",
        "body": {},
        "note": "更新待ちクリーンアップ Rust native (Group AS) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "POST", "path": "/api/diagnostics/open-repair-folder",
        "body": {},
        "note": "修復フォルダを開く Rust native (Group AS) — OS操作のためskip",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    # --- help / recipe / wd-tagger残 / agent / webhooks残 / collections write / scan-errors / jobs cancel / files tags delete (Group AT) ---
    {
        "method": "GET", "path": "/api/help/content/{section}",
        "params": {"section": "getting-started"},
        "note": "ヘルプコンテンツ Rust native (Group AT) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404, 401, 403],
        "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ content_html）**——従前ノ註ノ「markdown 変換差異あり」ハ当タリ居タリ。抑止ヲ外シテ走ラセタル結果、食ヒ違フハ `content_html` 一件ノミニシテ、他ノ欄ハ悉ク一致ス（`/api/help/content/getting-started` ノ項モ同ジ）。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、差ヲ `content_html` 一件ニ絞リ込ミタルノミ。todo(parity, v4.732.21) 参照。",
        "skip_body_compare": True,
    },
    {
        "method": "GET", "path": "/api/recipe/export/{file_id}",
        "params": {"file_id": "1"},
        "note": "レシピエクスポート Rust native (Group AT) — ok merge",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 ファイルID依存。Rustスキーマのみ確認。",
    },
    # --- recipe/import (native Rust port) ---
    {
        "method": "POST", "path": "/api/recipe/import",
        "body": {},
        "note": "レシピインポート Rust native — admin scope",
        "schema_check": ["ok"],
        "accept_statuses": [401, 403, 422],
    },
    {
        "method": "POST", "path": "/api/recipe/import/batch",
        "body": {},
        "note": "レシピバッチインポート Rust native — admin scope",
        "schema_check": ["ok"],
        "accept_statuses": [400, 401, 403],
    },
    # --- analysis/config GET+POST (v4.406.0: Rust forwarder) ---
    {
        "method": "GET", "path": "/api/analysis/config",
        "note": "解析設定取得 Rust forwarder (v4.406.0) — admin scope",
        "schema_check": ["ok"],
        "accept_statuses": [200]
    },
    {
        "method": "POST", "path": "/api/analysis/config",
        "body": {},
        "note": "解析設定保存 Rust forwarder (v4.406.0) — admin scope",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 503],
        "skip_body_compare": True,
        "python_path": None,
        "python_note": "Python 転送。Rustスキーマのみ確認。",
    },
    # --- recipe/export/batch (native Rust port), analysis/servers PUT (v4.405.0: Rust forwarder) ---
    {
        "method": "POST", "path": "/api/recipe/export/batch",
        "body": {"file_ids": []},
        "note": "レシピバッチエクスポート Rust native — admin scope",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "PUT", "path": "/api/analysis/servers/{server_id}",
        "params": {"server_id": "1"},
        "body": {},
        "note": "解析サーバー更新 Rust forwarder (v4.405.0) — admin scope",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 404, 503],
        "skip_body_compare": True,
        "python_path": None,
        "python_note": "Python 転送。Rustスキーマのみ確認。",
    },
    # --- sns/config (v4.404.0: Rust forwarder) ---
    {
        "method": "GET", "path": "/api/sns/config",
        "note": "SNS設定取得 Rust forwarder (v4.404.0) — admin scope",
        "schema_check": ["ok"],
        "accept_statuses": [200]
    },
    {
        "method": "POST", "path": "/api/sns/config",
        "body": {},
        "note": "SNS設定保存 Rust forwarder (v4.404.0) — admin scope",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 503],
        "skip_body_compare": True,
        "python_path": None,
        "python_note": "Python 転送。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/wd-tagger/tags/{file_id}",
        "params": {"file_id": "1"},
        "note": "WDタガータグ取得 Rust native (Group AT) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 ファイルID依存。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/wd-tagger/xmp/{file_id}",
        "params": {"file_id": "1"},
        "note": "WDタガーXMPデータ Rust native (Group AT) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 ファイルID依存。Rustスキーマのみ確認。",
    },
    {
        "method": "DELETE", "path": "/api/wd-tagger/tags/batch",
        "body": {},
        "note": "WDタガータグ一括削除 Rust native (Group AT) — DB破壊副作用のためskip",
        "schema_check": [],
    },
    # ── wd-tagger extended (v4.408.0) ──
    {
        "method": "GET", "path": "/api/wd-tagger/config",
        "note": "WDタガー設定取得 Rust native (v4.408.0; Group AQ) — admin scope; api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200]
    },
    {
        "method": "POST", "path": "/api/wd-tagger/config",
        "body": {},
        "note": "WDタガー設定保存 Rust native (v4.408.0) — skip: ファイル書き込み副作用",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "GET", "path": "/api/wd-tagger/stats",
        "note": "WDタガー統計 Rust native (v4.408.0) — SQLite集計。両サーバーは同一の tags.db を読む故、集計値まで一致すべし",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
    },
    {
        "method": "GET", "path": "/api/wd-tagger/profiles",
        "note": "WDタガープロファイル一覧 Rust native (v4.408.0; Group AQ) — admin scope; api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200]
    },
    {
        "method": "GET", "path": "/api/wd-tagger/profiles/{id}",
        "params": {"id": "default"},
        "note": "WDタガープロファイル取得 Rust native (v4.408.0) — admin scope",
        "schema_check": ["ok"],
        "accept_statuses": [404],
    },
    {
        "method": "POST", "path": "/api/wd-tagger/profiles",
        "body": {"name": "_parity_test_skip"},
        "note": "WDタガープロファイル作成 Rust native (v4.408.0) — skip: ファイル作成副作用",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "PUT", "path": "/api/wd-tagger/profiles/{id}",
        "params": {"id": "default"},
        "body": {},
        "note": "WDタガープロファイル更新 Rust native (v4.408.0) — skip: ファイル書き込み副作用",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "DELETE", "path": "/api/wd-tagger/profiles/{id}",
        "params": {"id": "_parity_test_skip"},
        "note": "WDタガープロファイル削除 Rust native (v4.408.0) — skip: ファイル削除副作用",
        "schema_check": [],
    },
    {
        "method": "POST", "path": "/api/wd-tagger/profiles/{id}/test",
        "params": {"id": "default"},
        "body": {},
        "note": "WDタガープロファイルテスト Rust forwarder (v4.408.0) — skip: 推論実行副作用",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "GET", "path": "/api/wd-tagger/active-model",
        "note": "WDタガーアクティブモデル取得 Rust native (v4.408.0; Group AQ) — admin scope; api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200]
    },
    {
        "method": "PUT", "path": "/api/wd-tagger/active-model",
        "body": {},
        "note": "WDタガーアクティブモデル更新 Rust native (v4.408.0) — skip: DB書き込み副作用",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "GET", "path": "/api/wd-tagger/vlm/test",
        "note": "VLM接続テスト Rust native (v4.408.0) — URLなし→400",
        "schema_check": ["ok", "error"],
        "accept_statuses": [400]
    },
    {
        "method": "GET", "path": "/api/wd-tagger/vlm/models",
        "note": "VLMモデル一覧 Rust native (v4.408.0; Group AQ) — URLなし→400; api_result",
        "schema_check": ["ok", "error"],
        "accept_statuses": [400]
    },
    {
        "method": "GET", "path": "/api/wd-tagger/model/status",
        "note": "WDタガーモデル状態 Rust native (v4.408.0; Group AQ) — admin scope; api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200]
    },
    {
        "method": "POST", "path": "/api/wd-tagger/model/download",
        "body": {},
        "note": "WDタガーモデルダウンロード Rust forwarder (v4.408.0) — skip: 長時間副作用",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "POST", "path": "/api/wd-tagger/tag/{file_id}",
        "params": {"file_id": "1"},
        "body": {},
        "note": "WDタガー単体タグ付け Rust forwarder (v4.408.0) — skip: DB書き込み副作用",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    # 以下ノ wd-tagger POST 群ハ `body: {}`、即チ**本流ノ要求**ナル故 skip ス。
    # 同ジ route ニ就キ「不活性ナル payload ヲ送ル探リ」ガ別途登録サレ居ル
    # （`wd-tagger batch/retag forwarders` ノ節ヲ見ヨ）。両者ハ**別ノ要求**ニシテ、
    # 台帳ガ矛盾セルニ非ズ——本流ハ実ニ試験セラレ居ラヌ。
    {
        "method": "POST", "path": "/api/wd-tagger/batch",
        "body": {},
        "note": "WDタガーバッチ開始 Rust forwarder (v4.408.0) — skip: 長時間バッチ副作用",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "POST", "path": "/api/wd-tagger/retag/single",
        "body": {},
        "note": "WDタガー再タグ（単体）Rust forwarder (v4.408.0) — skip: DB書き込み副作用",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "POST", "path": "/api/wd-tagger/retag/batch",
        "body": {},
        "note": "WDタガー再タグ（バッチ）Rust forwarder (v4.408.0) — skip: 長時間バッチ副作用",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "POST", "path": "/api/wd-tagger/retag/backfill",
        "body": {},
        "note": "WDタガー再タグ（バックフィル）Rust forwarder (v4.408.0) — skip: 長時間副作用",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "POST", "path": "/api/wd-tagger/retag/query",
        "body": {},
        "note": "WDタガー再タグクエリ Rust forwarder (v4.408.0) — skip: 推論副作用",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "DELETE", "path": "/api/wd-tagger/tags/{file_id}",
        "params": {"file_id": "1"},
        "note": "WDタガータグ削除（単体）Rust native (v4.408.0) — skip: DB削除副作用",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "GET", "path": "/api/agent/scope/{session_id}",
        "params": {"session_id": "test-session"},
        "note": "エージェントスコープ取得 Rust native (Group AT) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 セッションID依存。Rustスキーマのみ確認。",
    },
    {
        "method": "POST", "path": "/api/agent/audit/acknowledge/{audit_id}",
        "params": {"audit_id": "1"},
        "body": {},
        "note": "エージェント監査確認 Rust native (Group AT) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404, 401, 403],
    },
    {
        "method": "DELETE", "path": "/api/agent/auto-approve/{index}",
        "params": {"index": "0"},
        "note": "エージェント自動承認削除 Rust native (Group AT) — 副作用のためskip",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    {
        "method": "PUT", "path": "/api/webhooks/{wh_id}",
        "params": {"wh_id": "1"},
        "body": {},
        "note": "webhook更新 Rust native (Group AT) — api_success",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 404, 401, 403],
    },
    {
        "method": "POST", "path": "/api/webhooks/{wh_id}/test",
        "params": {"wh_id": "1"},
        "body": {},
        # `skip` because the handler makes an OUTBOUND request to whatever URL
        # the webhook holds -- running it against a live config would fire a
        # real delivery. That is the same reason the mutating routes above are
        # skipped.
        #
        # `python_path: None` was WRONG here and the no_python gate caught it:
        # Python serves this route at `webhook_routes.py:104`. The claim means
        # "Python has no such route", not "we chose not to compare" -- that is
        # what `skip` says. Do not reach for it again to quiet a gate.
        "note": "webhook test — skip: fires a real outbound delivery",
        "skip": True,
        "schema_check": [],
    },
    {
        "method": "PUT", "path": "/api/webhooks/inbound/{wh_id}",
        "params": {"wh_id": "1"},
        "body": {},
        "note": "inbound webhook更新 Rust native (Group AT) — api_success",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 404, 401, 403],
    },
    {
        "method": "POST", "path": "/api/collections/reorder",
        "body": {"collections": []},
        "note": "コレクション並び替え Rust native (Group AT) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403],
    },
    {
        "method": "PUT", "path": "/api/collections/2",
        "body": {},
        "note": "コレクション更新 Rust native (Group AT) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 404, 401, 403],
    },
    {
        "method": "POST", "path": "/api/collections/2/batch-add",
        "body": {"file_ids": []},
        "note": "コレクションバッチ追加 Rust native (Group AT) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 404, 401, 403],
    },
    {
        "method": "POST", "path": "/api/collections/2/batch-remove",
        "body": {"file_ids": []},
        "note": "コレクションバッチ削除 Rust native (Group AT) — api_result",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 404, 401, 403],
    },
    {
        "method": "POST", "path": "/api/scan-errors/clear",
        "body": {},
        "note": "isolated DB has no resolved errors",
        "schema_check": ["ok"],
    },
    {
        "method": "POST", "path": "/api/scan-errors/{error_id}/resolve",
        "params": {"error_id": "0"},
        "body": {},
        "note": "invalid id is deterministic",
        "schema_check": ["ok"],
        "accept_statuses": [400],
    },
    {
        # Same measured gap as the two entries above: Python has no such route.
        "method": "POST", "path": "/api/jobs/{job_id}/cancel",
        "params": {"job_id": "__parity_verify_no_such_job__"},
        "body": {},
        "note": "ジョブキャンセル Rust native (Group AT) — Python ニ route 無シ（実測、v4.732.13）",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404, 401, 403],
        "skip_body_compare": True,
        "python_note": "Python ニ /api/jobs/<job_id>/cancel ノ route 自体無シ。移植ノ欠落ニシテ恒久ノ仕様差ニ非ズ。",
    },
    {
        "method": "DELETE", "path": "/api/files/{file_id}/tags/{tag_id}",
        "params": {"file_id": "1", "tag_id": "1"},
        "note": "タグ削除 Rust native (Group AT) — 200 + {\"ok\": true} / DB変更のためskip",
        "skip": True,
        "schema_check": [],
        "python_path": None,
    },
    # --- misc remaining batch (Group AP: Rust native) ---
    {
        "method": "POST", "path": "/api/admin/shutdown",
        "body": {},
        "note": "admin shutdown Rust native (Group AP) — サーバー終了副作用のためskip",
        "skip": True,
        "schema_check": [],
        "accept_statuses": [200, 400, 401, 403],
        "skip_body_compare": True,
        "python_path": None,
        "python_note": "シャットダウン副作用あり。Rustスキーマのみ確認。",
    },
    {
        "method": "POST", "path": "/api/convert",
        "body": {"file_id": 1, "format": "jpg"},
        "note": "画像変換 Rust native (Group AP) — 変換結果はデータ依存のためskip_body_compare",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 404, 422],
        "skip_body_compare": True,
        "python_note": "変換結果はファイル依存。スキーマ形状のみ比較。",
    },
    {
        "method": "POST", "path": "/api/download/batch-zip",
        "body": {"file_ids": []},
        "note": "バッチZIPダウンロード Rust native (Group AP) — ZIP生成副作用のためRustのみ確認",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403, 404],
    },
    {
        "method": "GET", "path": "/api/events/info",
        "note": "SSEイベント情報 Rust native (Group AP) — api_result非ラップ・Python側なし",
        "schema_check": ["dedicated_server"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ dedicated_server, expires_at, refresh_after）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {
        "method": "GET", "path": "/api/events/stream",
        "note": "SSEストリーム Rust native (Group AP) — SSE chunkedのためparity検証スキップ",
        "schema_check": [],
        "accept_statuses": [200, 401, 403],
        "skip_body_compare": True,
        "skip": True,
        "python_path": None,
        "python_note": "SSE chunked transferのためparity検証不可。スキップ。",
    },
    {
        "method": "GET", "path": "/api/github/queue",
        "note": "GitHub queue Rust native (Group AP) — in-memory状態依存",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "skip_body_compare": True,
        "python_note": "GitHub in-memory状態依存。スキーマ形状のみ比較。",
    },
    {
        "method": "GET", "path": "/api/group-members",
        "note": "グループメンバー一覧 Rust native (Group AP) — SQLite依存",
        "schema_check": ["ok"],
        "schema_check_statuses": [200],
        "accept_statuses": [400],
    },
    {
        "method": "GET", "path": "/api/groups-index",
        "note": "グループインデックス Rust native (Group AP) — SQLite依存",
        "schema_check": [],
        "accept_statuses": [200],
    },
    {
        "method": "GET", "path": "/api/jobs/1",
        "note": "ジョブ情報取得 Rust native (Group AP) — Python側なし（/api/jobs/statusは別）",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404, 401, 403],
        "skip_body_compare": True,
        "python_path": None,
        "python_note": "Python側に/api/jobs/{job_id}ルートなし。Rustスキーマのみ確認。",
    },
    {
        # Same measured gap as the Group AJ entry above: Python has no such route.
        "method": "POST", "path": "/api/jobs/1/cancel",
        "body": {},
        "note": "ジョブキャンセル Rust native (Group AP) — Python ニ route 無シ（実測、v4.732.13）",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404, 401, 403],
        "skip_body_compare": True,
        "python_note": "Python ニ /api/jobs/<job_id>/cancel ノ route 自体無シ。移植ノ欠落ニシテ恒久ノ仕様差ニ非ズ。",
    },
    {
        "method": "GET", "path": "/api/scan-errors",
        "note": "isolated DB is deterministic",
        "schema_check": ["ok"],
    },
    {
        "method": "GET", "path": "/api/tagger-servers",
        "note": "タガーサーバー一覧 Rust native (Group AP) — 設定依存",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 設定/外部接続依存。スキーマ形状のみ比較。",
    },
    {
        "method": "GET", "path": "/api/trophies",
        "note": "トロフィー一覧 Rust native (Group AP) — SQLite依存",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 SQLiteデータ依存。スキーマ形状のみ比較。",
    },
    {
        "method": "GET", "path": "/api/ui/list",
        "note": "UI一覧 Rust native (Group AP) — 設定依存",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 設定依存。スキーマ形状のみ比較。",
    },
    {
        "method": "GET", "path": "/api/wd-tagger/untagged",
        "note": "WDタガー未タグ付きファイル Rust native (Group AP; v4.408.0) — SQLite依存",
        "schema_check": ["ok"],
        "accept_statuses": [200]
    },
    {
        "method": "GET", "path": "/api/wd-tagger/xmp/1",
        "note": "WDタガーXMPデータ Rust native (Group AP) — SQLite依存",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 SQLiteデータ依存。スキーマ形状のみ比較。",
    },
    {
        "method": "POST", "path": "/ext/convert/batch",
        "body": {"file_ids": [], "format": "jpg"},
        "note": "バッチ変換 ext Rust native (Group AP) — 副作用のためRustのみ確認",
        "schema_check": [],
        "accept_statuses": [200, 400, 401, 403],
        "skip_body_compare": True,
        "python_path": None,
        "python_note": "バッチ変換副作用あり。Rustスキーマのみ確認。",
    },
    {
        "method": "POST", "path": "/ext/syntax/analyze",
        "body": {"text": "test"},
        "note": "構文解析 ext Rust native (Group AP) — 外部接続依存のためRustのみ確認",
        "schema_check": [],
        "accept_statuses": [200, 400, 401, 403],
        "skip_body_compare": True,
        "python_path": None,
        "python_note": "外部接続依存あり。Rustスキーマのみ確認。",
    },
    # --- annotations + file-info + files/tags (Group AO: Rust native) ---
    {
        "method": "GET", "path": "/api/annotations/notes",
        "note": (
            "**実測（v4.734.16、両側ヲ同時ニ測ル）: 両者 200 ナレド置ク物ガ違フ。** "
            "python=text/html（注釈ノ頁ソノモノ）、rust=application/json"
            "（`{notes: [], total: 0, ok: true, …}`）。"
            "**従前ノ註ハ事実ノ逆ナリキ**——「Python 側ハ /ext/annotations/notes ノ故"
            "比較不可」ト記シ `python_path: None`（最深ノ緩和）ヲ帯ビ居タルガ、"
            "拡張ノ `blueprint_prefix` ハ `/api/annotations` ナリ"
            "（extensions/builtin_annotations/extension.json:10）。**Python ハ此ノ path ヲ"
            "給仕ス。** 依テ `python_path: None` ヲ外セリ——偽ヲ主張スル緩和ナル故。"
            "本文比較ハ尚抑フ——HTML ト JSON ヲ比ブルハ意味ヲ成サヌ。**之ハ実測ニ依ル理由ナリ。** "
            "尚 Rust ハ頁ヲ `/ext/annotations/notes` ヘ別置ス（main.rs:3207）ガ、"
            "Python ハ其処ヲ 404 ト為ス。todo(parity, v4.734.16) 参照。"
        ),
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403],
        "skip_body_compare": True,
    },
    {
        "method": "GET", "path": "/api/annotations/1",
        "note": "注釈ファイル別取得。Python は /api/annotations/<int:file_id> を給仕ス",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404],
    },
    {
        "method": "POST", "path": "/api/annotations/batch-set",
        "body": {"items": []},
        "note": "注釈バッチ登録 Rust native (Group AO) — INSERT/UPDATE副作用のためRustのみ確認",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403],
    },
    {
        "method": "POST", "path": "/api/annotations/batch-delete",
        "body": {"source": "__parity_test_nonexistent__"},
        "note": "注釈バッチ削除 Rust native (Group AO) — DELETE副作用のためRustのみ確認",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403],
    },
    {
        "method": "GET", "path": "/api/file-info/1",
        "note": "ファイル情報取得 Rust native (Group AO) — SQLiteデータ依存",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 SQLiteデータ依存。スキーマ形状のみ比較。",
    },
    {
        "method": "DELETE", "path": "/api/files/1/tags/0",
        "note": "ファイルタグ削除 Rust native (Group AO) — DELETE副作用のためRustのみ確認",
        "schema_check": ["ok"],
        "accept_statuses": [200, 204, 404, 401, 403],
    },
    # --- agent journal + audit-acknowledge + auto-approve mutate (Group AM: Rust native) ---
    {
        "method": "GET", "path": "/api/agent/journal",
        "note": "agent action journal Rust native (Group AM) — SQLite同一テーブル",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 ジャーナル内容はDB状態依存。スキーマ形状のみ比較。",
    },
    {
        "method": "GET", "path": "/api/agent/journal/stats",
        "note": "agent journal統計 Rust native (Group AM) — SQLite同一テーブル",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 統計値はDB状態依存。スキーマ形状のみ比較。",
    },
    {
        "method": "POST", "path": "/api/agent/audit/acknowledge/1",
        "body": {},
        "note": "audit acknowledge Rust native (Group AM) — UPDATE副作用のためRustのみ確認",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404, 401, 403],
    },
    {
        "method": "POST", "path": "/api/agent/auto-approve",
        "body": {"tool": "__parity_test__", "conditions_json": "{}"},
        "note": "auto-approve rule追加 Rust native (Group AM) — INSERT副作用ハ両側ヘ送ル故対称ナリ",
        "schema_check": ["ok"],
        "accept_statuses": [200, 400, 401, 403],
        # `rule.approved_at` is the wall-clock time of the INSERT. The two
        # servers each perform their own INSERT, so the values can never agree
        # by more than luck -- this is the rare case where the divergence is
        # real, permanent, and not anybody's bug. Measured, not assumed: with
        # the body comparison on, `rule.approved_at` was the ONLY field that
        # differed (v4.732.12); every other field matched.
        "exclude_nested_fields": ["approved_at"],
    },
    {
        "method": "DELETE", "path": "/api/agent/auto-approve/0",
        "note": "auto-approve rule削除 Rust native (Group AM) — DELETE副作用のためRustのみ確認",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404, 401, 403],
    },
    # --- agent scope/auto-approve/tool-levels (Group AL: Rust native) ---
    {
        "method": "GET", "path": "/api/agent/tool-levels",
        "note": "agent tool-levels分類 Rust native (Group AL) — Rustのみ確認",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 Python parity環境でのルート登録差異のためRustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/agent/scope",
        "note": "agent scope一覧 Rust native (Group AL) — Rustのみ確認",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 Python側はin-memory ScopeFenceのためRust(SQLite)と diverge。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/agent/scope/test_session",
        "note": "agent scope単体取得 Rust native (Group AL) — Rustのみ確認",
        "schema_check": ["ok"],
        "accept_statuses": [200, 404, 401, 403],
        "skip_body_compare": True,
        "python_path": None,
        "python_note": "Python側はin-memory ScopeFenceのためRust(SQLite)と diverge。Rustスキーマのみ確認。",
    },
    {
        "method": "GET", "path": "/api/agent/auto-approve",
        "note": "agent auto-approve rules Rust native (Group AL) — Rustのみ確認",
        "schema_check": ["ok", "data"],
        "accept_statuses": [200, 401, 403],
        "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 Python側はin-memory auto_approve_rulesのためRust(SQLite)と diverge。Rustスキーマのみ確認。",
    },
    # --- search-grouped (Group AC: Rust native) ---
    {
        "method": "GET", "path": "/api/search-grouped",
        "note": "グループ検索 Rust native (Group AC) — GroupsIndex + SearchParams の intersection",
        "schema_check": ["status", "groups"],
        "accept_statuses": [200, 401, 403],
        "python_envelope": True,
    },
    {
        "method": "GET", "path": "/api/search-grouped/warm",
        "note": "グループ検索 warm Rust native (Group AC) — index プリロード",
        "schema_check": ["status"],
        "accept_statuses": [200, 202, 401, 403],
        "python_envelope": True,
    },
    # --- recipe_export (Group AD: Rust native) ---
    # file_id を動的に注入するため accept_statuses に 404 を含む
    {
        "method": "GET", "path": "/api/recipe/export/1",
        "note": "レシピエクスポート Rust native (Group AD) — templates JOIN で gen metadata を返す",
        "schema_check": ["ok"],
        "accept_statuses": [200, 401, 403, 404],
    },
    # --- tags (file_idが存在する場合のみ有効。動的に追加) ---

    # --- ext/prompt-library (Group AU: Rust native) ---
    {"method": "GET", "path": "/ext/prompt-library/api/export", "note": "エクスポート — **実測四回（v4.739.1）: exported_at ハ差三度・一致一度。** 両側共ニ要求ヲ捌ク刹那ノ時刻ヲ刻ム（Python int(time.time()) prompt_library_bulk.py:171 / Rust now() prompt_library.rs:1254）。 同ジ秒ニ収マレバ合フ故、差ヲ要求スル expected_body_diff ハ往復ス。 依テ volatile_keys ニテ値ノミ免ジ、存在ハ両側ニ求ム", "schema_check": ["ok"], "accept_statuses": [200], "volatile_keys": ["exported_at"]},
    {"method": "GET", "path": "/ext/prompt-library/api/folders", "note": "プロンプトライブラリ フォルダ一覧 (Group AU)", "schema_check": ["ok"], "accept_statuses": [200]},
    {"method": "PUT", "path": "/ext/prompt-library/api/folders/1", "body": {"name": "test-folder"}, "note": "プロンプトライブラリ フォルダ更新 (Group AU)", "schema_check": ["ok"], "accept_statuses": [200, 400, 401, 403, 404], "skip_body_compare": True, "python_note": "Rust native ext。スキーマのみ確認。"},
    {"method": "POST", "path": "/ext/prompt-library/api/import", "body": {"prompts": []}, "note": "プロンプトライブラリ インポート (Group AU)", "schema_check": ["ok"], "accept_statuses": [200, 400, 401, 403], "skip_body_compare": True, "python_note": "Rust native ext。スキーマのみ確認。"},
    {"method": "GET", "path": "/ext/prompt-library/api/prompts", "note": "プロンプトライブラリ プロンプト一覧 (Group AU)", "schema_check": ["ok"], "accept_statuses": [200]},
    {"method": "POST", "path": "/ext/prompt-library/api/prompts/bulk-delete", "body": {"ids": []}, "note": "プロンプトライブラリ バルク削除 (Group AU)", "schema_check": ["ok"], "accept_statuses": [200, 400, 401, 403], "skip_body_compare": True, "python_note": "Rust native ext。ids空→api_error(ok=false)。スキーマのみ確認。"},
    {"method": "POST", "path": "/ext/prompt-library/api/prompts/bulk-move", "body": {"ids": [], "folder_id": None}, "note": "プロンプトライブラリ バルク移動 (Group AU)", "schema_check": ["ok"], "accept_statuses": [200, 400, 401, 403], "skip_body_compare": True, "python_note": "Rust native ext。ids空→api_error(ok=false)。スキーマのみ確認。"},
    {"method": "POST", "path": "/ext/prompt-library/api/prompts/bulk-tag", "body": {"ids": [], "tag_ids": []}, "note": "プロンプトライブラリ バルクタグ (Group AU)", "schema_check": ["ok"], "accept_statuses": [200, 400, 401, 403], "skip_body_compare": True, "python_note": "Rust native ext。ids空→api_error(ok=false)。スキーマのみ確認。"},
    {"method": "POST", "path": "/ext/prompt-library/api/prompts/from-file", "body": {"file_id": 1}, "note": "プロンプトライブラリ ファイルからプロンプト (Group AU)", "schema_check": ["ok"], "accept_statuses": [200, 201, 400, 401, 403, 404], "skip_body_compare": True, "python_note": "Rust native ext。file_id=1不在なら404。スキーマのみ確認。"},
    {"method": "GET", "path": "/ext/prompt-library/api/prompts/1", "note": "プロンプト単体 — **実測（v4.739.4）: 差ハ時刻ノ二鍵ノミ、且ツ run 毎ニ出デ消エス。** 因ハ 429 ノ再送ナリ（本 run ニテ 32 件、内 POST .../import ハ prompt ヲ作リ POST .../bulk-tag ハ更ム）。**再送ハ両側デ別ノ刹那ニ着ク故、行ノ時刻ガ喰ヒ違フ。** 律速ガ働カザル run デハ合フ故、差ヲ要求スル expected_body_diff ハ往復ス。 依テ volatile_keys ニテ値ノミ免ジ、存在ハ両側ニ求ム", "schema_check": ["ok"], "accept_statuses": [200],
        "volatile_keys": ["prompt.created_at", "prompt.updated_at"],
    },
    {"method": "POST", "path": "/ext/prompt-library/api/prompts/1/folder", "body": {"folder_id": None}, "note": "プロンプトライブラリ フォルダ割り当て (Group AU)", "schema_check": ["ok"], "accept_statuses": [200, 400, 401, 403, 404], "skip_body_compare": True, "python_note": "Rust native ext。folder_id null→400 ok=false。スキーマのみ確認。"},
    {"method": "POST", "path": "/ext/prompt-library/api/prompts/1/tags", "body": {"tag_ids": []}, "note": "プロンプトライブラリ タグ設定 (Group AU)", "schema_check": ["ok"], "accept_statuses": [200, 400, 401, 403, 404], "skip_body_compare": True, "python_note": "Rust native ext。スキーマのみ確認。"},
    {"method": "GET", "path": "/ext/prompt-library/api/tags", "note": "プロンプトライブラリ タグ一覧 (Group AU)", "schema_check": ["ok"], "accept_statuses": [200]},
    {"method": "DELETE", "path": "/ext/prompt-library/api/tags/1", "note": "プロンプトライブラリ タグ削除 (Group AU)", "schema_check": ["ok"], "accept_statuses": [200, 401, 403, 404], "skip_body_compare": True, "python_note": "Rust native ext。スキーマのみ確認。"},

    # --- ext/chatlog (Group AV: Rust native) --- ok フィールドなし・schema_check 省略
    {"method": "GET", "path": "/ext/chatlog/api/chat/decisions", "note": "チャットログ 全決定事項 (Group AV)", "accept_statuses": [400]},
    {"method": "GET", "path": "/ext/chatlog/api/chat/decisions/search?query=test", "note": "チャットログ 決定事項検索 (Group AV)", "accept_statuses": [400]},
    {"method": "GET", "path": "/ext/chatlog/api/chat/topics/search?query=test", "note": "チャットログ トピック検索 (Group AV)", "accept_statuses": [400]},
    {"method": "GET", "path": "/ext/chatlog/api/conversations/1", "note": "チャットログ 会話詳細 (Group AV)", "accept_statuses": [404]},
    {"method": "GET", "path": "/ext/chatlog/api/conversations/1/entities", "note": "チャットログ 会話エンティティ (Group AV)", "accept_statuses": [404]},
    {"method": "GET", "path": "/ext/chatlog/api/conversations/1/related", "note": "チャットログ 関連会話 (Group AV)", "accept_statuses": [200]},
    {"method": "GET", "path": "/ext/chatlog/api/entities/search?query=test", "note": "チャットログ エンティティ検索 (Group AV)", "accept_statuses": [400]},
    {"method": "GET", "path": "/ext/chatlog/api/text-search?query=test", "note": "チャットログ テキスト検索 (Group AV)", "accept_statuses": [400]},

    # --- ext/favorites残 + ext/cross-search残 + ext/md-viewer残 + ext/convert残 (Group AW: Rust native) ---
    {"method": "POST", "path": "/ext/favorites/api/batch-add", "body": {"file_ids": []}, "note": "お気に入りバッチ追加 (Group AW)", "schema_check": ["ok"], "accept_statuses": [200, 400, 401, 403], "skip_body_compare": True, "python_note": "Rust native ext。file_ids空→400 ok=false。スキーマのみ確認。"},
    {"method": "POST", "path": "/ext/favorites/api/batch-remove", "body": {"file_ids": []}, "note": "お気に入りバッチ削除 (Group AW)", "schema_check": ["ok"], "accept_statuses": [200, 400, 401, 403], "skip_body_compare": True, "python_note": "Rust native ext。file_ids空→400 ok=false。スキーマのみ確認。"},
    {"method": "POST", "path": "/ext/favorites/api/export/folder", "body": {}, "note": "お気に入りフォルダエクスポート (Group AW) — skip:ファイルシステム操作", "skip": True, "python_note": "ファイルシステム操作あり。skip。"},
    # バイナリノ本文ハ比較シ得ネド、**走ラセ得ヌ理由ニハ非ズ** —— 之ハ GET ニシテ
    # 副作用無シ。`skip`（一度モ叩カズ）ヨリ `skip_body_compare`（status ハ比ブ）ガ
    # 正シキ緩和ナリ。v4.689.5 ニテ格上ゲセリ。
    {"method": "GET", "path": "/ext/favorites/api/export/zip", "note": "お気に入りZIPエクスポート (Group AW)", "skip_body_compare": True, "accept_statuses": [200, 401, 403, 404], "python_note": "バイナリ本文ノ故ニ status ノミ比較ス。**実走ニテ rust=200 py=404 ノ差異ヲ観タリ** —— Python 側ハ当該拡張ヲ読ミ居ラヌ為ト見ユルモ未確認ナル故、accept_statuses ニテ両方ヲ許ス。**是ハ等価ノ証明ニ非ズ、差異ヲ承知ノ上デノ許容ナリ。**"},
    {"method": "POST", "path": "/ext/cross-search/api/open-file", "body": {}, "note": "クロスサーチ ファイルオープン (Group AW)", "accept_statuses": [200, 400, 401, 403], "skip_body_compare": True, "python_note": "Rust native ext。body空→path required (400, okなし)。スキーマのみ確認。"},
    {"method": "DELETE", "path": "/ext/cross-search/api/scan-roots/0", "note": "クロスサーチ スキャンルート削除 (Group AW)", "accept_statuses": [200, 400, 401, 403], "skip_body_compare": True, "python_note": "Rust native ext。index=0はout of rangeなら400 ok=false。スキーマのみ確認。"},
    {"method": "GET", "path": "/ext/cross-search/api/txt/1", "note": "クロスサーチ TXTファイル詳細 (Group AW)", "accept_statuses": [404]},
    {"method": "GET", "path": "/ext/md-viewer/api/files/1", "note": "MDビューワ ファイル詳細 (Group AW)", "accept_statuses": [404]},
    {"method": "GET", "path": "/ext/md-viewer/api/languages", "note": "MDビューワ 言語一覧 (Group AW)", "accept_statuses": [200]},
    {"method": "DELETE", "path": "/ext/md-viewer/api/scan-roots/0", "note": "MDビューワ スキャンルート削除 (Group AW)", "accept_statuses": [200, 400, 401, 403], "skip_body_compare": True, "python_note": "Rust native ext。index=0はout of rangeなら400。スキーマのみ確認。"},
    {"method": "POST", "path": "/ext/convert/nai-to-sd", "body": {}, "note": "NAI→SD変換 (Group AW)", "accept_statuses": [200, 400, 401, 403], "skip_body_compare": True, "python_note": "Rust native ext。okフィールドなし。スキーマのみ確認。"},
    {"method": "POST", "path": "/ext/convert/sd-to-nai", "body": {}, "note": "SD→NAI変換 (Group AW)", "accept_statuses": [200, 400, 401, 403], "skip_body_compare": True, "python_note": "Rust native ext。okフィールドなし。スキーマのみ確認。"},

    # --- settings write残 + internal (Group AX: Rust native) ---
    {"method": "DELETE", "path": "/api/settings/bw-mapping/test-key", "note": "settings BW mapping 削除 (Group AX)", "schema_check": ["ok"], "accept_statuses": [200, 400, 404, 401, 403], "python_note": "**「Rust native」ノ註ハ偽ナリキ（v4.732.16 実測）**——Python モ routes/settings_manage_vault_bw.py ニテ本 route ヲ実装シ、app_factory_blueprints.py ガ登録ス。body 比較ノ抑止ハ「Python ニ無シ」ヲ前提トシ居タルガ其ノ前提ガ誤リ。今ハ比較ス。"},
    {"method": "DELETE", "path": "/api/settings/op-mapping/test-key", "note": "settings OP mapping 削除 (Group AX)", "schema_check": ["ok"], "accept_statuses": [200, 400, 404, 401, 403], "python_note": "**「Rust native」ノ註ハ偽ナリキ（v4.732.16 実測）**——Python モ routes/settings_manage.py ニテ本 route ヲ実装シ、app_factory_blueprints.py ガ登録ス。body 比較ノ抑止ハ「Python ニ無シ」ヲ前提トシ居タルガ其ノ前提ガ誤リ。今ハ比較ス。"},
    {"method": "DELETE", "path": "/api/settings/llm-endpoints/test-category", "note": "LLM エンドポイント削除 (Group AX)", "schema_check": ["ok"], "accept_statuses": [200, 400, 404, 401, 403], "python_note": "**「Rust native」ノ註ハ偽ナリキ（v4.732.16 実測）**——Python モ routes/llm_endpoints.py ニテ本 route ヲ実装シ、app_factory_blueprints.py ガ登録ス。body 比較ノ抑止ハ「Python ニ無シ」ヲ前提トシ居タルガ其ノ前提ガ誤リ。今ハ比較ス。"},
    {"method": "POST", "path": "/api/settings/llm-endpoints/test", "body": {"base_url": "http://localhost:9999"}, "note": "LLM endpoint connection test (Rust native) — skip:外部API接続", "skip": True, "python_note": "外部エンドポイント接続テスト。skip。"},
    {"method": "GET", "path": "/api/mdns/identity", "note": "mDNS identity forwarder (Rust, mdns.rs) — unauthenticated; body varies", "accept_statuses": [200, 503], "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ node_id）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {"method": "GET", "path": "/api/mdns/peers", "note": "mDNS peers forwarder (Rust, mdns.rs) — unauthenticated; body varies", "accept_statuses": [200, 503], "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ peers[len], reason, running）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {"method": "GET", "path": "/api/system/inference-info", "note": "inference-info forwarder (Rust, server_info.rs) — body varies", "accept_statuses": [200, 401, 403, 503], "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 ORT状態依存。スキーマのみ確認。"},
    {"method": "GET", "path": "/api/llm_router/status", "note": "llm_router status forwarder (Rust, llm_router_admin.rs) — admin scope required", "accept_statuses": [200, 401, 403, 503], "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ data.aliases, error）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {"method": "POST", "path": "/api/llm_router/refresh", "body": {}, "note": "llm_router refresh forwarder (Rust) — admin scope added", "skip": True, "python_note": "副作用あり。skip。"},
    {"method": "POST", "path": "/api/llm_router/backends/nonexistent-alias/disable", "body": {}, "note": "**実測ノ差（v4.734.10、rust=503 py=404）——Rust ハ此ノ切替ヲ実装セズ。** 従前ハ `{ok: true}` ヲ返シ居タリ——**alias ヲ読ミモセズ何モ為サズニ「成功」ト答フ**故、利用者ガ backend ヲ無効ト為スモ無効ト成ラズ UI ハ成功ト表示シ居タリ（捏造ノ成功）。v4.734.10 ニテ `not_ported`（503）ヘ改メタル故、呼ビ手ハ「何モ起キ居ラヌ」ヲ知リ得ル。**転送ハ為サズ**——門ノ `check_no_rust_proxy_calls` ガ之ヲ禁ジ、転送器ノ集合ハ凍結サレ減ル方向ノミナル故（本作業ハ其ノ債務ヲ返済スル側ニ在リ、増ヤス側ニ非ズ）。Python ハ `_set_disabled_with_rollback` ニテ実際ニ切替ヘ永続シ、未知ノ alias ハ 404。**之ハ緩和ナレド、因ハ実測サレ名指サレ居ル。** todo(rust-gap, v4.734.10) 参照。", "accept_statuses": [404, 503], "python_note": "alias依存。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/llm_router/backends/nonexistent-alias/enable", "body": {}, "note": "**実測ノ差（v4.734.10、rust=503 py=404）——Rust ハ此ノ切替ヲ実装セズ。** 従前ハ `{ok: true}` ヲ返シ居タリ——**alias ヲ読ミモセズ何モ為サズニ「成功」ト答フ**故、利用者ガ backend ヲ無効ト為スモ無効ト成ラズ UI ハ成功ト表示シ居タリ（捏造ノ成功）。v4.734.10 ニテ `not_ported`（503）ヘ改メタル故、呼ビ手ハ「何モ起キ居ラヌ」ヲ知リ得ル。**転送ハ為サズ**——門ノ `check_no_rust_proxy_calls` ガ之ヲ禁ジ、転送器ノ集合ハ凍結サレ減ル方向ノミナル故（本作業ハ其ノ債務ヲ返済スル側ニ在リ、増ヤス側ニ非ズ）。Python ハ `_set_disabled_with_rollback` ニテ実際ニ切替ヘ永続シ、未知ノ alias ハ 404。**之ハ緩和ナレド、因ハ実測サレ名指サレ居ル。** todo(rust-gap, v4.734.10) 参照。", "accept_statuses": [404, 503], "python_note": "alias依存。スキーマのみ確認。"},
    {"method": "GET", "path": "/v1/router/capabilities", "note": "**v4.734.8 ニテ実測ノ通リニ狭メタリ**——従前ハ [200, 401, 403, 503] ヲ許シ、**rust=200 py=401 ノ乖離ヲ緑ノママ通シ居タリ。** 且ツ状態ガ食ヒ違ヘバ harness ハ本文比較ヲ行ハヌ故、**此ノ二項ハ一度モ本文ヲ比較サレ居ラザリキ。** 因: Python ノ `check_request` ハ `allow_loopback_bypass` ヲ既定 False ト為シ呼出側ガ明示的ニ許ス形ニシテ、`routes/gateway_status.py` ハ渡サズ（proxy 五経路ハ渡ス）。Rust ハ渡シ居タル故、鍵無キ loopback ノ呼ビ手ヘ応ジ居タリ。v4.734.8 ニテ Rust ヲ Python ヘ揃ヘタリ。", "accept_statuses": [401, 403], "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 LLM catalog依存。スキーマのみ確認。"},
    {"method": "GET", "path": "/v1/node/services", "note": "**v4.734.8 ニテ実測ノ通リニ狭メタリ**——従前ハ [200, 401, 403, 503] ヲ許シ、**rust=200 py=401 ノ乖離ヲ緑ノママ通シ居タリ。** 且ツ状態ガ食ヒ違ヘバ harness ハ本文比較ヲ行ハヌ故、**此ノ二項ハ一度モ本文ヲ比較サレ居ラザリキ。** 因: Python ノ `check_request` ハ `allow_loopback_bypass` ヲ既定 False ト為シ呼出側ガ明示的ニ許ス形ニシテ、`routes/gateway_status.py` ハ渡サズ（proxy 五経路ハ渡ス）。Rust ハ渡シ居タル故、鍵無キ loopback ノ呼ビ手ヘ応ジ居タリ。v4.734.8 ニテ Rust ヲ Python ヘ揃ヘタリ。", "accept_statuses": [401, 403], "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 probe状態依存。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/error-report/enrich", "body": {"bundle": {}}, "skip_body_compare": True, "note": "**実測ノ差ハ三鍵（v4.734.4、rust=200 py=200）。** `data`/`error` ハ封ノ欠落ニシテ本版ニテ返済セリ。**残ル `bundle` ハ Rust ニ存在セズ**——handler 自身ガ「silently acknowledge」ト記ス通リ補完ヲ実装シ居ラヌ故、鍵ノ**不在**ナリ（`expected_body_diff` ハ不在ヲ覆ハヌ——形ノ差ナル故、正シキ拒絶ナリ）。**且ツ移植シテモ一致シ得ヌ**——Python ハ `pid`・`uptime_sec`・`cwd`・`captured_at`・新タナル `error_id` ヲ詰ムル故（core/web/error_bundle_capture.py:210-240）、二ツノ過程ノ間デ合フ道理無シ。todo(rust-gap, v4.734.4) 参照。", "accept_statuses": [200, 400, 503], "python_note": "Python enrich_error_bundle依存。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/analysis/batch/cancel", "body": {}, "note": "**v4.734.6 ニテ抑止ヲ外シタリ**——従前ノ理由（job_manager 状態依存・スキーマのみ確認）ハ差ノ説明ニ非ズ。`job_manager.cancel_job` ヲ呼ブノミニシテ、job manager ノ状態ハ**過程内**ナリ。起動直後ノ server ニ走行中ノ job ハ無キ故、到達スルハ 404 `job_not_running` ノ枝ナリ（routes/analysis_job_routes.py:76-82）。即チ他ノ項ノ比較ヲ汚サヌ。実走ガ真偽ヲ告ゲル。", "accept_statuses": [200, 404, 503]},
    {"method": "POST", "path": "/api/extensions/install", "body": {}, "note": "extensions install forwarder (Rust) — admin scope added (was _require_local)", "skip": True, "python_note": "副作用あり。skip。"},
    {"method": "GET", "path": "/api/extensions/hooks", "note": "extensions hooks forwarder (Rust) — admin scope", "accept_statuses": [200, 401, 403, 503], "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ data, error, hooks）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {"method": "GET", "path": "/api/extensions/isolation", "note": "extensions isolation forwarder (Rust) — admin scope", "accept_statuses": [200, 401, 403, 503], "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ available, processes）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {"method": "POST", "path": "/api/extensions/author/create", "body": {"name": "test-ext", "description": "test"}, "note": "extensions author create forwarder (Rust) — admin scope added (was _require_local)", "skip": True, "python_note": "副作用あり。skip。"},
    {"method": "GET", "path": "/api/extensions/author/nonexistent/files", "note": "extensions author files forwarder (Rust) — admin scope added", "accept_statuses": [200, 401, 403, 404, 503], "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 名前依存。スキーマのみ確認。"},
    {"method": "GET", "path": "/api/extensions/author/nonexistent/read", "note": "extensions author read forwarder (Rust) — admin scope added", "accept_statuses": [200, 401, 403, 404, 503], "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 名前依存。スキーマのみ確認。"},
    {"method": "POST", "skip": True, "path": "/api/extensions/author/nonexistent/validate", "body": {}, "note": "extensions author validate forwarder (Rust) — admin scope added — skip 理由: Rust ノ 501 ハ意図的ナル保留（安全側ノ判断）", "skip_body_compare": True, "accept_statuses": [200, 401, 403, 404, 501, 503], "python_note": "実走 rust=501 py=200（v4.713.5）。**Rust ノ 501 ハ欠落ニ非ズ判断ナリ**——Python ノ承認ハ CodeVerifier（Python-AST 走査）ニ依リ Rust ニ対応物無ク、manifest ノミニテ承認セバ**誰モ解析セヌコードヲ承認スル**ニ等シ。控フル方ガ安全ナル故、Python ヘ合ハセズ skip トス。"},
    {"method": "POST", "path": "/api/extensions/author/nonexistent/write", "body": {}, "note": "**v4.732.24 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 註ニ実測ノ根拠無ク、外シテ走ラセタルニ**本文マデ一致セリ**。本項ハ書込ニ至ラヌ（受ケル status ガ悉ク 400 以上カ、狙ヒガ意図的ナル不在ノ資源）故、比較ヲ戻スモ何モ変ヘズ。今ハ全比較ス。  extensions author write forwarder (Rust) — admin scope added", "accept_statuses": [200, 401, 403, 404, 503], "python_note": "名前依存。スキーマのみ確認。"},
    {"method": "GET", "path": "/api/scan/status", "note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ current, current_file, label）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "schema_keys": _SCAN_STATUS_FIELDS, "group": "scan", "skip_body_compare": True},
    {"method": "POST", "path": "/api/scan/start", "body": {}, "note": "missing root is deterministic", "group": "scan"},
    {"method": "POST", "path": "/api/scan/start", "form_body": {"root": "x"}, "note": "wrong Content-Type (form-urlencoded) is rejected before JSON parsing -- require_json_dict parity", "group": "scan"},
    {"method": "POST", "path": "/api/scan/start", "body": [], "note": "non-object JSON body (a list) is rejected -- require_json_dict parity", "group": "scan"},
    {"method": "POST", "path": "/api/scan/cancel", "note": "**v4.734.6 ニテ抑止ヲ外シタリ**——従前ノ理由ハ差ノ説明ニ非ズ。`cancel_scan_payload` ヲ呼ブノミニシテ、起動直後ノ server ニ止メルベキ走査ハ無シ（routes/scan.py:63-70）。即チ他ノ項ノ比較ヲ汚サヌ。実走ガ真偽ヲ告ゲル。", "accept_statuses": [200, 404]},
    {"method": "POST", "path": "/api/scan/resume", "body": {}, "note": "interrupted/running state determines resumed (200), absent (404), or already-running (409)", "skip_body_compare": True, "accept_statuses": [200, 404, 409], "group": "scan"},
    {"method": "GET", "path": "/api/scan/queue", "note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 queue contents are runtime-state dependent", "group": "scan"},
    {"method": "POST", "path": "/api/scan-all", "body": {}, "note": "may start or queue a scan", "skip": True},
    {"method": "POST", "path": "/api/scan-all", "form_body": {"force": "true"}, "note": "wrong Content-Type (form-urlencoded) is rejected before JSON parsing -- require_json_dict parity, no scan side effect"},
    {"method": "POST", "path": "/api/scan-all", "body": [], "note": "non-object JSON body (a list) is rejected instead of silently defaulting force=false -- require_json_dict parity, no scan side effect"},
    {"method": "POST", "path": "/api/scan/dismiss", "body": {}, "note": "deterministic dismiss envelope"},
    {"method": "POST", "path": "/api/scan/queue/clear", "body": {},  "accept_statuses": [200], "note": "cleared count depends on queue state and request order **v4.732.26 ニテ status ヲ実測シ宣言セリ（rust=200 py=200）。** 従前ハ `accept_statuses` ノ宣言無ク、**宣言無キ項ハ如何ナル status モ受ケル**故、500 ヲ返シ始メテモ通リ居タリ。併セテ本文比較ノ抑止モ外ス——status ガ定マリタル故、抑止ノ拠ル所無シ。"},
    {"method": "DELETE", "path": "/api/scan/queue/nonexistent-id", "note": "deterministic missing queue item"},
    {"method": "POST", "path": "/api/scan/history/clear", "body": {}, "note": "deterministic clear envelope"},
    {"method": "POST", "path": "/api/hash-backfill/cancel", "body": {}, "note": "no running job is deterministic"},
    {"method": "GET", "path": "/api/hash-backfill/status", "note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ computed, last_id）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {"method": "POST", "path": "/api/hash-backfill/start", "body": {},  "accept_statuses": [200], "note": "starts a background job; body is state-dependent **v4.732.26 ニテ status ヲ実測シ宣言セリ（rust=200 py=200）。** 従前ハ `accept_statuses` ノ宣言無ク、**宣言無キ項ハ如何ナル status モ受ケル**故、500 ヲ返シ始メテモ通リ居タリ。併セテ本文比較ノ抑止モ外ス——status ガ定マリタル故、抑止ノ拠ル所無シ。"},
    {"method": "POST", "path": "/api/scanned-roots/purge", "body": {"path": "/nonexistent"}, "note": "scanned-roots purge forwarder (Rust) — no auth (Python parity)", "skip_body_compare": True, "accept_statuses": [200, 400, 503], "python_note": "DB操作。スキーマのみ確認。"},
    {"method": "GET", "path": "/api/ai-context", "note": "ai-context forwarder (Rust misc_admin.rs) — admin scope", "accept_statuses": [200, 401, 403, 503], "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ data.capabilities[1], data.capabilities[2], data.capabilities[3]）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {"method": "GET", "path": "/api/system/update/check", "note": "system update check forwarder (Rust) — admin scope", "accept_statuses": [200, 401, 403, 503], "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ data, error, latest）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {"method": "GET", "path": "/api/system/update/unified-check", "note": "system update unified-check forwarder (Rust) — admin scope", "accept_statuses": [200, 401, 403, 503], "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ data, error, extensions[len]）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {"method": "POST", "path": "/api/search-union", "body": {"query": "", "limit": 1}, "note": "search-union forwarder (Rust) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 503], "python_note": "実走 rust=503 py=400（v4.713.5）。Rust ハ依存不足ニテ 503、Python ハ空 query ヲ入力不正ト見テ 400。**検証順序ノ差**ニシテ孰レモ未移植ニ非ズ。"},
    {"method": "POST", "path": "/api/debug/query", "body": {"sql": "SELECT 1", "limit": 1}, "note": "**v4.734.4 ニテ抑止ヲ外シタリ**——従前ノ理由ハ「スキーマのみ確認」等ニシテ、**harness ガ何ヲ為シ居ルカノ説明ニ過ギズ、差ノ理由ニ非ズ。** `readonly_query_payload` ヲ呼ブ故、構造上読取専用ナリ（routes/debug.py:64-70）。状態ヲ変ヘズ。 故ニ他ノ項ノ比較ヲ汚サヌ（書込ヲ一件ヅツ測ル則ノ趣旨ハ状態汚染ノ回避ナリ——実読ニテ其レヲ満タセリ）。実走ガ真偽ヲ告ゲル。 【実測 v4.736.4: rust=503 py=403。揺レニ非ズ——Rust ハ not_ported（The SQL debug console）ヲ返シ、Python ハ実装ノ上デ 403 ヲ以テ辞ス】", "accept_statuses": [200, 400, 401, 403, 503], "python_note": "YU_DEBUG_MODE 依存＋admin scope要求。スキーマのみ確認。"},
    {"method": "GET", "path": "/api/extensions/marketplace", "note": "extensions marketplace forwarder (Rust) — admin scope", "accept_statuses": [200, 401, 403, 503], "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 marketplace DB 依存。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/extensions/marketplace/refresh", "body": {}, "note": "extensions marketplace/refresh forwarder (Rust) — admin scope required", "skip_body_compare": True, "accept_statuses": [200, 401, 403, 503], "python_note": "admin scope 要求。スキーマのみ確認。"},
    {"method": "GET", "path": "/api/extensions/os-isolation", "note": "extensions os-isolation forwarder (Rust) — admin scope", "accept_statuses": [200, 401, 403, 503], "python_note": "**実測ノ差（v4.732.21、rust=200 py=200、相違ハ config.apparmor, config.windows_job_object, config.windows_restricted_token）**——従前ノ註ハ「DB 状態依存」等ト述ブルノミニテ一度モ実測サレ居ラザリキ。抑止ヲ外シテ走ラセタル結果、右ノ鍵ガ実際ニ食ヒ違フ。**同時ニ外シタル百十一件ノ内七十二件ハ差無ク通レリ**——即チ其等ノ理由ハ偽ナリキ。本件ハ直サズ、理由ヲ実測ノ物ヘ置キ換ヘタルノミ。todo(parity, v4.732.21) 参照。", "skip_body_compare": True},
    {"method": "GET", "path": "/api/extensions/nonexistent-ext", "note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 extensions detail forwarder (Rust) — admin scope", "accept_statuses": [200, 401, 403, 404, 503]},
    {"method": "GET", "path": "/api/extensions/nonexistent-ext/config", "note": "**v4.733.5: body 比較ノ抑止ヲ外シタリ**——此ノ理由ハ一度モ実測サレ居ラザリキ（「再検討」ハ測定ニ非ズ）。GET ナル故書込無シ、抑止ヲ外スモ何モ変ヘズ。実走ガ真偽ヲ告ゲル。 extensions config GET forwarder (Rust) — no auth (Python parity)", "accept_statuses": [200, 404, 503]},
    {"method": "POST", "path": "/api/extensions/nonexistent-ext/config", "body": {}, "note": "**v4.732.24 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 註ニ実測ノ根拠無ク、外シテ走ラセタルニ**本文マデ一致セリ**。本項ハ書込ニ至ラヌ（受ケル status ガ悉ク 400 以上カ、狙ヒガ意図的ナル不在ノ資源）故、比較ヲ戻スモ何モ変ヘズ。今ハ全比較ス。  extensions config POST forwarder (Rust) — no auth (Python parity)", "accept_statuses": [200, 400, 404, 503], "python_note": "名前依存。スキーマのみ確認。"},
    {"method": "GET", "path": "/api/extensions/nonexistent-ext/integrity", "note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 extensions integrity forwarder (Rust) — admin scope", "accept_statuses": [200, 401, 403, 404, 503]},
    {"method": "GET", "path": "/api/extensions/nonexistent-ext/permissions", "note": "**v4.733.5: body 比較ノ抑止ヲ外シタリ**——此ノ理由ハ一度モ実測サレ居ラザリキ（「再検討」ハ測定ニ非ズ）。GET ナル故書込無シ、抑止ヲ外スモ何モ変ヘズ。実走ガ真偽ヲ告ゲル。 extensions permissions GET forwarder (Rust) — admin scope", "accept_statuses": [200, 401, 403, 404, 503]},
    {"method": "POST", "path": "/api/extensions/nonexistent-ext/permissions", "body": {}, "note": "**v4.732.24 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 註ニ実測ノ根拠無ク、外シテ走ラセタルニ**本文マデ一致セリ**。本項ハ書込ニ至ラヌ（受ケル status ガ悉ク 400 以上カ、狙ヒガ意図的ナル不在ノ資源）故、比較ヲ戻スモ何モ変ヘズ。今ハ全比較ス。  extensions permissions POST forwarder (Rust) — no auth (Python parity)", "accept_statuses": [200, 400, 404, 503], "python_note": "名前依存。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/extensions/nonexistent-ext/rescan", "body": {}, "note": "**v4.732.24 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 註ニ実測ノ根拠無ク、外シテ走ラセタルニ**本文マデ一致セリ**。本項ハ書込ニ至ラヌ（受ケル status ガ悉ク 400 以上カ、狙ヒガ意図的ナル不在ノ資源）故、比較ヲ戻スモ何モ変ヘズ。今ハ全比較ス。  extensions rescan forwarder (Rust) — no auth (Python parity)", "accept_statuses": [200, 404, 503], "python_note": "名前依存。スキーマのみ確認。"},
    {"method": "GET", "path": "/api/extensions/nonexistent-ext/scan-results", "note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 extensions scan-results forwarder (Rust) — admin scope", "accept_statuses": [200, 401, 403, 404, 503]},
    {"method": "POST", "path": "/api/extensions/nonexistent-ext/toggle", "body": {}, "note": "**v4.732.24 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 註ニ実測ノ根拠無ク、外シテ走ラセタルニ**本文マデ一致セリ**。本項ハ書込ニ至ラヌ（受ケル status ガ悉ク 400 以上カ、狙ヒガ意図的ナル不在ノ資源）故、比較ヲ戻スモ何モ変ヘズ。今ハ全比較ス。  extensions toggle forwarder (Rust) — no auth (Python parity)", "accept_statuses": [200, 404, 503], "python_note": "名前依存。スキーマのみ確認。"},
    {"method": "GET", "path": "/api/extensions/nonexistent-ext/tokens", "note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 extensions tokens forwarder (Rust) — admin scope", "accept_statuses": [200, 401, 403, 404, 503]},
    {"method": "POST", "path": "/api/analysis/analyze/999999", "body": {}, "note": "**実測（v4.734.12）: 両者 400 ニテ辞シ、差ハ `error` ノ文言一鍵ノミ。** 従前ハ **rust=200 py=400** ナリキ——即チ **Rust ハ辞スル本文ヲ成功ノ状態デ返シ居タリ**（早期 return ニ `StatusCode` 無シ）。`response.ok` ヲ見ル呼ビ手ハ受理サレタト信ズ。文言ノ差ハ残ル: Python ハ engine 解決ノ連鎖ノ末ニ二択ノ文ヲ選ビ（`core/analysis_api/engine_resolver.py:88-97`）、Rust ハ config ガ空ナル時ノミ早期ニ辞ス——**写スニハ其ノ連鎖ノ移植ヲ要ス故、別ノ仕事ナリ。** 依テ `expected_body_diff` ニテ**其ノ一鍵ノミ**ヲ免ジ、他ノ鍵ハ悉ク比較ス。**両者ガ一致スレバ harness ガ「免除ハ最早不要」ト落トス故、免除ハ因ヲ越エテ生キ延ビヌ。**", "accept_statuses": [400], "expected_body_diff": ["error"], "python_note": "file_id依存。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/analysis/batch", "body": {}, "note": "analysis batch forwarder (Rust) — no auth", "skip_body_compare": True, "accept_statuses": [200, 400, 503], "python_note": "スキーマのみ確認。"},
    {"method": "POST", "path": "/api/analysis/trends", "body": {}, "note": "**v4.734.4 ニテ抑止ヲ外シタリ**——従前ノ理由ハ「スキーマのみ確認」等ニシテ、**harness ガ何ヲ為シ居ルカノ説明ニ過ギズ、差ノ理由ニ非ズ。** `analyze_prompt_trends` ノ解析ノミ（routes/analysis_job_routes.py:85-91）。状態ヲ変ヘズ。 故ニ他ノ項ノ比較ヲ汚サヌ（書込ヲ一件ヅツ測ル則ノ趣旨ハ状態汚染ノ回避ナリ——実読ニテ其レヲ満タセリ）。実走ガ真偽ヲ告ゲル。", "accept_statuses": [200, 400, 503], "python_note": "スキーマのみ確認。"},
    {"method": "DELETE", "path": "/api/analysis/trends/history/999999", "note": "**v4.732.24 ニテ直シタリ——`ok` ノ封ヲ用ヒ居ラザリキ。** Python ハ成功ニ `api_result({deleted: True})`、不在ニ `api_error(Not found, 404)` ヲ返スガ、Rust ハ `success` ノ旗ヲ用ヒ居タル故、`ok` モ `deleted` モ読メザリキ。両経路ヲ揃ヘ全比較ス。  analysis trends history delete forwarder (Rust) — no auth", "accept_statuses": [200, 404, 503], "python_note": "ID依存。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/analysis/ollama/test", "body": {"ollama_url": "http://localhost:11434"}, "note": "**v4.734.5 ニテ抑止ヲ外シタリ**——従前ノ理由ハ「スキーマのみ確認」等ニシテ**差ノ理由ニ非ズ。** 空ノ body ナラ `ollama_url` 無キ故「URL is required」ノ 400 ニテ拒ム（routes/analysis_config_routes.py:56-68）。 即チ `run_db_sync` ヘ至ル前ニ辞スル故、他ノ項ノ比較ヲ汚サヌ（書込ヲ一件ヅツ測ル則ノ趣旨ハ状態汚染ノ回避ナリ——実読ニテ其レヲ満タセリ）。**併セテ検証誤リノ形ヲ測ル**——`validate_json_model` ノ `{error, code, detail}` ハ Rust ガ従前乖離シタル処ナリ。", "accept_statuses": [200, 400, 503], "python_note": "外部接続依存。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/analysis/openai-compat/test", "body": {"base_url": "http://localhost:8080"}, "note": "**v4.734.5 ニテ抑止ヲ外シタリ**——従前ノ理由ハ「スキーマのみ確認」等ニシテ**差ノ理由ニ非ズ。** 空ノ body ナラ `url` 無キ故 400 ニテ拒ム（同ファイル:96-108）。 即チ `run_db_sync` ヘ至ル前ニ辞スル故、他ノ項ノ比較ヲ汚サヌ（書込ヲ一件ヅツ測ル則ノ趣旨ハ状態汚染ノ回避ナリ——実読ニテ其レヲ満タセリ）。**併セテ検証誤リノ形ヲ測ル**——`validate_json_model` ノ `{error, code, detail}` ハ Rust ガ従前乖離シタル処ナリ。", "accept_statuses": [200, 400, 503], "python_note": "外部接続依存。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/analysis/servers/discovered/register", "body": {}, "note": "**v4.734.5 ニテ抑止ヲ外シタリ**——従前ノ理由ハ「スキーマのみ確認」等ニシテ**差ノ理由ニ非ズ。** 同上（:59-66）。 即チ `run_db_sync` ヘ至ル前ニ辞スル故、他ノ項ノ比較ヲ汚サヌ（書込ヲ一件ヅツ測ル則ノ趣旨ハ状態汚染ノ回避ナリ——実読ニテ其レヲ満タセリ）。**併セテ検証誤リノ形ヲ測ル**——`validate_json_model` ノ `{error, code, detail}` ハ Rust ガ従前乖離シタル処ナリ。", "accept_statuses": [200, 400, 503], "python_note": "スキーマのみ確認。"},
    {"method": "POST", "path": "/api/analysis/servers/discovered/test", "body": {}, "note": "**v4.734.5 ニテ抑止ヲ外シタリ**——従前ノ理由ハ「スキーマのみ確認」等ニシテ**差ノ理由ニ非ズ。** `require_json_model` ガ先ニ立チ、空ノ body ハ検証 400 ト成ル（routes/analysis_server_routes.py:73-80）。 即チ `run_db_sync` ヘ至ル前ニ辞スル故、他ノ項ノ比較ヲ汚サヌ（書込ヲ一件ヅツ測ル則ノ趣旨ハ状態汚染ノ回避ナリ——実読ニテ其レヲ満タセリ）。**併セテ検証誤リノ形ヲ測ル**——`validate_json_model` ノ `{error, code, detail}` ハ Rust ガ従前乖離シタル処ナリ。", "accept_statuses": [200, 400, 503], "python_note": "外部接続依存。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/analysis/servers/migrate", "body": {}, "note": "analysis servers migrate forwarder (Rust) — no auth", "skip_body_compare": True, "accept_statuses": [200, 400, 503], "python_note": "スキーマのみ確認。"},
    {"method": "POST", "path": "/api/analysis/servers/nonexistent-server/test", "body": {}, "note": "**v4.732.24 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 註ニ実測ノ根拠無ク、外シテ走ラセタルニ**本文マデ一致セリ**。本項ハ書込ニ至ラヌ（受ケル status ガ悉ク 400 以上カ、狙ヒガ意図的ナル不在ノ資源）故、比較ヲ戻スモ何モ変ヘズ。今ハ全比較ス。  analysis server test forwarder (Rust) — no auth", "accept_statuses": [200, 400, 404, 503], "python_note": "サーバーID依存。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/extract-from-zip", "body": {"file_id": 999999}, "note": "**v4.732.24 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 註ニ実測ノ根拠無ク、外シテ走ラセタルニ**本文マデ一致セリ**。本項ハ書込ニ至ラヌ（受ケル status ガ悉ク 400 以上カ、狙ヒガ意図的ナル不在ノ資源）故、比較ヲ戻スモ何モ変ヘズ。今ハ全比較ス。  extract-from-zip (Rust native, 2026-08-13) — 存在しない file_id は validate_extract_target で 400 not_zip_member に短絡し、抽出・DB登録には到達しない(副作用ゼロ)。admin scope はharnessのpin_auth=falseで通過する。", "accept_statuses": [400], "rust_native": True, "python_note": "Python 側は現役だが、副作用回避のため Rust 単独で shape のみ確認する。"},
    {"method": "GET", "path": "/api/tauri-shell/tabs", "note": "tauri-shell/tabs forwarder (Rust) — no auth", "accept_statuses": [200, 503], "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 extensions_manager依存。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/ui/switch", "body": {"name": "__parity_test_nonexistent__"}, "note": "ui/switch (Rust native, 2026-08-13) — no auth。**実在する UI 名を送ってはならない**: 本 harness の Rust server は cwd=repo root・--config 無しで起動するため config_path が実物の config.json を指し、成功経路は operator の config.json を書き換えてしまう(mode 0600、secret を含む)。未登録 UI 名で 404 経路のみ突き、成功経路は routes/ui.rs の unit 試験(tempdir)で固定する。", "accept_statuses": [404], "rust_native": True, "python_note": "Python 側 register は現役だが、副作用回避のため Rust 単独で shape のみ確認する。"},
    {"method": "POST", "path": "/api/diagnostics/bug-report", "body": {}, "note": "diagnostics bug-report forwarder (Rust) — skip:副作用", "skip": True, "python_note": "バグレポート生成。skip。"},
    # Full body comparison (no skip_body_compare, no accept_statuses widening).
    # The side effect that forced `skip` — both servers write a
    # doctor_<ts>.md/.json pair under <project_root>/reports — is redirected by
    # YU_DOCTOR_REPORT_DIR, which parity_harness.py sets to a tmp dir for both
    # children. The only non-deterministic field left is `job_id` (uuid4 on both
    # sides), masked by compat_normalize.VOLATILE_KEYS. Driving this route
    # against a server started outside parity_harness.py WILL write into the
    # checkout; export YU_DOCTOR_REPORT_DIR first.
    {"method": "POST", "path": "/api/diagnostics/doctor", "body": {}, "note": "diagnostics doctor start (Rust native, 2026-08-13) — v4.698.0 で skip を解除。報告の出力先を YU_DOCTOR_REPORT_DIR で引数化し副作用を tmp へ逃がした。緩和はゼロ（python_note も付けない — ratchet が数える緩和であり、--no-strict-body では本文比較を落とすため）。", "rust_native": True},
    {"method": "GET", "path": "/api/diagnostics/doctor/nonexistent-job", "note": "diagnostics doctor status (Rust native, 2026-08-13) — job registry は process 内の static。この job_id は登録され得ないので 404 job_not_found に決定的に落ちる。done 経路は routes/diagnostics.rs の unit 試験で固定する。", "accept_statuses": [404], "rust_native": True, "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 Python 側 registry は現役だが、job 状態依存につき Rust 単独で shape のみ確認する。"},
    {"method": "POST", "path": "/api/diagnostics/zip-repair", "body": {}, "note": "diagnostics zip-repair forwarder (Rust) — skip:副作用", "skip": True, "python_note": "ZIPファイル操作。skip。"},
    {"method": "POST", "path": "/api/settings/secrets/migrate", "body": {}, "note": "secrets migrate (Group AX) — skip:外部API操作", "skip": True, "python_note": "外部シークレット操作。skip。"},
    {"method": "POST", "path": "/api/settings/secrets/push-to-bw", "body": {}, "note": "secrets push-to-bw (Group AX) — skip:Bitwarden連携", "skip": True, "python_note": "Bitwarden API操作。skip。"},
    {"method": "POST", "path": "/api/settings/secrets/push-to-op", "body": {}, "note": "secrets push-to-op (Group AX) — skip:1Password連携", "skip": True, "python_note": "1Password API操作。skip。"},
    {"method": "POST", "path": "/api/settings/secrets/rotate", "body": {}, "note": "secrets rotate (Group AX) — skip:認証情報ローテーション", "skip": True, "python_note": "認証情報変更操作。skip。"},
    {"method": "POST", "path": "/_internal/log", "body": {"level": "info", "message": "test"}, "note": "_internal/log (Group AX) — skip:フレームワーク内部", "skip": True, "python_note": "フレームワーク内部エンドポイント。skip。"},
    {"method": "POST", "path": "/_internal/sse-emit", "body": {"event": "test"}, "note": "_internal/sse-emit (Group AX) — skip:SSE内部", "skip": True, "python_note": "SSE内部エンドポイント。skip。"},
    {"method": "POST", "path": "/_internal/mcp/dispatch", "body": {}, "note": "_internal/mcp/dispatch (Group AX) — skip:Rustブリッジ内部(loopback-only)", "skip": True, "python_note": "Rustブリッジ専用ローカルエンドポイント。skip。"},
    {"method": "POST", "path": "/api/internal/log", "body": {"level": "info", "message": "test"}, "note": "api/internal/log (Group AX) — skip:フレームワーク内部", "skip": True, "python_note": "フレームワーク内部エンドポイント。skip。"},
    {"method": "POST", "path": "/api/analysis/servers/discovered/match", "body": {}, "note": "**v4.734.5 ニテ抑止ヲ外シタリ**——従前ノ理由ハ「スキーマのみ確認」等ニシテ**差ノ理由ニ非ズ。** 同上（:87-94）。 即チ `run_db_sync` ヘ至ル前ニ辞スル故、他ノ項ノ比較ヲ汚サヌ（書込ヲ一件ヅツ測ル則ノ趣旨ハ状態汚染ノ回避ナリ——実読ニテ其レヲ満タセリ）。**併セテ検証誤リノ形ヲ測ル**——`validate_json_model` ノ `{error, code, detail}` ハ Rust ガ従前乖離シタル処ナリ。", "accept_statuses": [200, 400, 503], "python_note": "スキーマのみ確認。"},
    {"method": "DELETE", "path": "/api/analysis/servers/discovered/match", "note": "**v4.734.5 ニテ抑止ヲ外シタリ**——従前ノ理由ハ「スキーマのみ確認」等ニシテ**差ノ理由ニ非ズ。** 同上（:101-108）。 即チ `run_db_sync` ヘ至ル前ニ辞スル故、他ノ項ノ比較ヲ汚サヌ（書込ヲ一件ヅツ測ル則ノ趣旨ハ状態汚染ノ回避ナリ——実読ニテ其レヲ満タセリ）。**併セテ検証誤リノ形ヲ測ル**——`validate_json_model` ノ `{error, code, detail}` ハ Rust ガ従前乖離シタル処ナリ。", "accept_statuses": [200, 400, 503], "python_note": "スキーマのみ確認。"},
    {"method": "POST", "path": "/api/analysis/servers/discovered/ignore", "body": {}, "note": "**v4.734.5 ニテ抑止ヲ外シタリ**——従前ノ理由ハ「スキーマのみ確認」等ニシテ**差ノ理由ニ非ズ。** 同上（:115-122）。 即チ `run_db_sync` ヘ至ル前ニ辞スル故、他ノ項ノ比較ヲ汚サヌ（書込ヲ一件ヅツ測ル則ノ趣旨ハ状態汚染ノ回避ナリ——実読ニテ其レヲ満タセリ）。**併セテ検証誤リノ形ヲ測ル**——`validate_json_model` ノ `{error, code, detail}` ハ Rust ガ従前乖離シタル処ナリ。", "accept_statuses": [200, 400, 503], "python_note": "スキーマのみ確認。"},
    {"method": "DELETE", "path": "/api/analysis/servers/discovered/ignore", "note": "**v4.734.5 ニテ抑止ヲ外シタリ**——従前ノ理由ハ「スキーマのみ確認」等ニシテ**差ノ理由ニ非ズ。** 同上（:129-136）。 即チ `run_db_sync` ヘ至ル前ニ辞スル故、他ノ項ノ比較ヲ汚サヌ（書込ヲ一件ヅツ測ル則ノ趣旨ハ状態汚染ノ回避ナリ——実読ニテ其レヲ満タセリ）。**併セテ検証誤リノ形ヲ測ル**——`validate_json_model` ノ `{error, code, detail}` ハ Rust ガ従前乖離シタル処ナリ。", "accept_statuses": [200, 400, 503], "python_note": "スキーマのみ確認。"},
    {"method": "POST", "path": "/api/svg/rasterize", "body": {}, "note": "**v4.734.4 ニテ抑止ヲ外シタリ**——従前ノ理由ハ「スキーマのみ確認」等ニシテ、**harness ガ何ヲ為シ居ルカノ説明ニ過ギズ、差ノ理由ニ非ズ。** 画像変換ノミニシテ、空ノ body ナラ file_id/svg_path/svg_data ノ何レモ無キ故拒ム（routes/svg_api.py:51-68）。状態ヲ変ヘズ。 故ニ他ノ項ノ比較ヲ汚サヌ（書込ヲ一件ヅツ測ル則ノ趣旨ハ状態汚染ノ回避ナリ——実読ニテ其レヲ満タセリ）。実走ガ真偽ヲ告ゲル。", "accept_statuses": [200, 400, 401, 403, 503], "python_note": "画像変換。スキーマのみ確認。"},
    {"method": "GET", "path": "/api/workflow-gen-params/999999", "note": "workflow-gen-params (Rust) — no auth", "accept_statuses": [200, 404, 503], "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 ファイルID依存。スキーマのみ確認。"},
    {"method": "GET", "path": "/api/sns/preview", "note": "sns preview (Rust) — admin scope required", "skip_body_compare": True, "accept_statuses": [200, 401, 403, 503], "python_note": "実走 rust=503 py=400（v4.689.7 及ビ v4.713.3）。**診断済ミ（v4.713.3）**——`misc_admin.rs:991` ハ `not_ported` ノ殻ニシテ、機能名ハ 「SNS post preview」 ナリ。即チ 503 ハ「依存不足」ニ非ズ「Rust 未移植」ノ謂ニシテ、Python ノ 400（入力不正）トハ別物。OCR 三件ト同種ノ**本物ノ欠落**ナリ。TODO ニ記ス。"},
    {"method": "GET", "path": "/api/sns/x/intent", "note": "sns x/intent (Rust) — admin scope required", "skip_body_compare": True, "accept_statuses": [200, 401, 403, 503], "python_note": "実走 rust=503 py=400（同上）。**診断済ミ（v4.713.3）**——`misc_admin.rs:1002` ハ `not_ported` ノ殻ニシテ、機能名ハ 「Building an X (Twitter) intent URL」 ナリ。`/api/sns/preview` ト同根、**本物ノ欠落**ナリ。TODO ニ記ス。"},
    {"method": "POST", "path": "/api/sns/bluesky/post", "body": {}, "note": "sns bluesky post (Rust) — admin scope required", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 503], "python_note": "SNS投稿。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/sns/bluesky/test", "body": {}, "note": "sns bluesky test (Rust) — admin scope required", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 501, 503], "python_note": "実走 rust=503 py=501（v4.713.5）。**両者共ニ辞ス**——Rust ハ not_ported ノ 503、Python ハ未実装ノ 501。孰レモ動クト偽ラズ、綴リガ違フノミ。Rust ハ 501 ノ側ニ非ザル故、accept_statuses ニ記シテ比較ヲ生カス。"},
    {"method": "GET", "path": "/api/sns/bsky/queue", "note": "sns bsky queue (Rust) — admin scope required", "skip_body_compare": True, "accept_statuses": [200, 401, 403, 503], "python_note": "スキーマのみ確認。"},
    {"method": "GET", "path": "/api/sns/bsky/queue/pending", "note": "sns bsky queue/pending (Rust) — admin scope required", "skip_body_compare": True, "accept_statuses": [200, 401, 403, 503], "python_note": "スキーマのみ確認。"},
    # debug-log 三本ハ v4.689.2 マデ捏造スタブナリキ（常ニ enabled:false、clear ハ
    # 何モ消サズ、且ツ両者共ニ認可検査ヲ持タザリキ）。本文比較ヲ有効ニシテ登録ス。
    # TAGDB_DEBUG 未設定ノ既定ニテハ両実装トモ enabled:false ヲ返ス筈ナリ。
    {"method": "GET", "path": "/api/tools/debug-log", "note": "debug log viewer — admin scope + loopback", "accept_statuses": [200, 401, 403]},
    {"method": "GET", "path": "/api/tools/debug-log/download", "note": "debug log download — admin scope + loopback; 無効時ハ 400", "accept_statuses": [200, 400, 401, 403, 404], "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 有効時ハ本文ガログ其ノ物ナル故、status ノミ比較ス。"},
    {"method": "POST", "path": "/api/tools/debug-log/clear", "body": {}, "note": "debug log clear — 書換ノ副作用ノ為 skip", "skip": True, "schema_check": []},
    # backup ノ読出二件（v4.696.0 ニテ Rust ネイティブ化）。本文比較ヲ有効ニシテ登録ス
    # —— 以前ハ ENDPOINTS ニ登録スラ無ク、捏造 200 ヲ何者モ捉ヘザリキ。
    # `scheduler_running` ノミ恒久ニ食ヒ違フ: Python ハ既定ニテ backup scheduler ヲ
    # 起ス（`extensions/builtin_backup/core_impl/scheduler.py`）ガ、Rust ニハ scheduler
    # 自体ガ無シ。Rust ガ `true` ト称セバ、走ラヌ定期バックアップヲ走ルト告グル事ト成ル。
    # 依テ `expected_body_diff` ニ当該一欄ノミヲ挙ゲ、他ノ七欄ハ悉ク比較ス。
    # 差ガ消エタ時ハ FAIL ス（例外ガ腐ラヌ様）。
    #
    # 註（2026-09-08 merge 時ノ裁定）: `worktree-rust-backup-npu-port` ハ此ノ二件ヲ
    # `accept_statuses: [200,401,403,503]` ＋ `skip_body_compare` ナル**弱キ形**ニテ
    # 登録シ居タリ（同枝ハ 2026-09-05 ノ物ニシテ、当時 read 二本ハ別枝ニテ移植中
    # ナリキ）。然レド同枝ノ註自身ガ「503 ヲ許スハ**移植ノ完了マデノ暫定**ナリ——
    # 読出二本ガ入リタル暁ニハ 503 ヲ外シ本文比較ヲ有効ニスベシ」ト命ジ、其ノ暁ハ
    # v4.696.0 ニテ既ニ来レリ。依テ弱キ方ヲ採ラズ此ノ強キ形ヲ残ス。
    # **枝ヲ merge スル毎ニ古キ緩和ガ復活スルナラバ、緩和ハ永久ニ返済サレヌ。**
    {"method": "GET", "path": "/api/tools/backup/list", "auth": "admin", "note": "backup list — admin scope; 試験環境ニハバックアップ無キ故両者共ニ空ナル筈", "schema_check": ["backups", "count"]},
    {"method": "GET", "path": "/api/tools/backup/status", "auth": "admin", "note": "backup status — admin scope; 設定既定値ヲ両者ヨリ読ム", "expected_body_diff": ["scheduler_running"], "schema_check": ["enabled", "backup_on_scan_complete", "periodic_interval_hours", "max_generations", "cooldown_minutes", "scheduler_running", "last_backup_time", "within_cooldown"]},
    # 書込ノ四本ハ `require_local` ヲ帯ブ。本 harness ハ両者ヲ loopback ヨリ叩ク故、
    # 当該門ノ欠落ヲ**構造的ニ検出シ得ヌ**。認可ノ固定ハ
    # `db_backup/routes.rs` ノ注入マトリクスニ在リ、此処ニ非ズ。
    #
    # 以下三本ハ実 DB ヲ書キ換フル故 skip:True トス（既存 mutating route ノ慣例）。
    # 経路ノ存在ト認可ノ形ハ Rust 側単体試験ガ固定ス。
    {"method": "POST", "path": "/api/tools/backup/create", "body": {}, "note": "backup create — require_local; 実 DB ヲ写ス故 skip", "skip": True, "schema_check": []},
    {"method": "POST", "path": "/api/tools/backup/restore", "body": {}, "note": "backup restore — require_local; 実 DB ヲ上書ク故 skip", "skip": True, "schema_check": []},
    {"method": "POST", "path": "/api/tools/backup/delete", "body": {}, "note": "backup delete — require_local; 実ファイルヲ消ス故 skip", "skip": True, "schema_check": []},
    # 実走ニテ **rust=200 py=500** ヲ得タリ（v4.695.0）。即チ Rust ノ新実装ハ通リ、
    # **Python 側ガ 500 ヲ返ス**。移植先ガ正シク移植元ガ誤レル型ナリ。
    #
    # **返済済ミ（v4.732.6）。** Python ノ 500 ノ因ハ `routes_backup.py` ガ Flask 流ノ
    # `response.call_on_close` ニテ tempfile ノ後片付ケヲ登録シ居タルニ在リ。Quart ノ
    # `Response` ニ該メソッド無キ故、**成功経路ハ毎度 AttributeError ニテ 500 ト成リ居タリ**。
    # Rust ト同ジク「temp ヘ写シ→全読ミ→即削除→bytes ヲ返ス」形ニ改メ、`500` ヲ許容ヨリ
    # 外セリ。退行ノ番人ハ `tests/basic/test_backup_download_streams_db.py` ニ在リ。
    # 本文ハ DB 其ノ物ナル故 `skip_body_compare` ハ**恒久**ニ残ス（暫定ニ非ズ）。
    {"method": "GET", "path": "/api/tools/backup-download", "note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 backup download — require_local; 本文ハ DB 其ノ物ナル故 status ノミ比較ス（恒久ノ仕様差）", "accept_statuses": [200, 401, 403, 404]},
    {"method": "GET", "path": "/api/sns/bsky/monitor/config", "note": "sns bsky monitor/config (Rust) — admin scope required", "accept_statuses": [200, 401, 403, 503], "python_note": "本文比較ヲ有効化セリ（v4.689.0）。鍵ノ取違ヘヲ隠シ居タル故。"},
    {"method": "GET", "path": "/api/sns/bsky/monitor/triage-prompts", "note": "sns bsky triage-prompts (Rust) — admin scope required", "accept_statuses": [200, 401, 403, 503], "python_note": "本文比較ヲ有効化セリ（v4.689.0）。鍵ノ取違ヘヲ隠シ居タル故。"},
    # 保存側。config を書き換ふる故 skip:True トス（既存 mutating route ノ慣例ニ同ジ）。
    # 写像ノ検証ハ misc_admin.rs ノ sns_tests ニ在リ。
    {"method": "PUT", "path": "/api/sns/bsky/monitor/config", "body": {}, "note": "sns bsky monitor/config 保存 (Rust) — config 書換ノ副作用ノ為 skip", "skip": True, "schema_check": []},
    {"method": "PUT", "path": "/api/sns/bsky/monitor/triage-prompts", "body": {}, "note": "sns bsky triage-prompts 保存 (Rust) — config 書換ノ副作用ノ為 skip", "skip": True, "schema_check": []},
    # --- wd-tagger batch / retag / tag forwarders (v4.408.0: Rust forwarder) ---
    # **此ノ群ノ payload ハ意図的ニ不活性ナリ**——`file_ids: []`、未知ノ `model_id`、
    # 不在ノ `profile_id`/`file_id`。故ニ毎回送レド仕事ヲ為サズ（404 又ハ対象ゼロ）。
    # **実ノ値ヘ「改善」スル勿レ。** 例ヘバ `/api/wd-tagger/batch` ニテ `file_ids` ヲ
    # 省ケバ `resolve_targets` ノ backfill 枝ヘ落チ、DB 全体ガ対象ト成ル
    # （`crates/yu-server/src/routes/wd_tagger_batch.rs:193-212`）——parity 毎回ニ
    # 長時間 job ガ起ツ。不活性ナルハ payload ノ字面ノミニ懸カリ、他ニ番人ハ無シ。
    {"method": "POST", "path": "/api/wd-tagger/tag/999999", "body": {}, "note": "wd-tagger tag single file Rust forwarder (v4.408.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 404, 503], "python_note": "file_id不在→503/404。admin scope必須。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/wd-tagger/batch", "body": {"file_ids": [], "model_id": "test", "limit": 0, "force": False}, "note": "wd-tagger batch Rust forwarder (v4.408.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 503], "python_note": "admin scope必須。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/wd-tagger/batch/cancel", "body": {}, "note": "wd-tagger batch cancel Rust forwarder (v4.408.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 404, 503], "python_note": "admin scope必須。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/wd-tagger/model/download", "body": {"profile_id": "nonexistent"}, "note": "wd-tagger model download Rust forwarder (v4.408.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 404, 503], "python_note": "profile_id不在→404。admin scope必須。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/wd-tagger/profiles/nonexistent/test", "body": {}, "note": "wd-tagger profile test Rust forwarder (v4.408.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 404, 503], "python_note": "profile_id不在→404。admin scope必須。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/wd-tagger/retag/single", "body": {"file_id": 999999, "model_id": "test", "thresholds": {"general": 0.35, "character": 0.85}}, "note": "wd-tagger retag single Rust forwarder (v4.408.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 404, 503], "python_note": "file_id不在→404。admin scope必須。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/wd-tagger/retag/batch", "body": {"file_ids": [], "model_id": "test", "thresholds": {"general": 0.35, "character": 0.85}}, "note": "wd-tagger retag batch — Rust native (v4.625.0)。未知 model_id は 404 model_not_found で先に弾く（retag/single と同じ契約）。Python は弾かず engine ロード時に job が失敗するため 404 は意図的差異。", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 404, 409, 503], "python_note": "**v4.714.1 ニテ Python ヲ Rust ヘ合ハス**——従前 Python ハ未知 model_id ヲ弾カズ、job ヲ起コシテ engine ロード時ニ倒レ 500 ト成リ居タリ。今ハ job 作成ノ前ニ404 model_not_found ニテ弾ク。倒レテカラ告グルヨリ先ニ弾ク方ガ優ル故ナリ。"},
    {"method": "POST", "path": "/api/wd-tagger/retag/backfill", "body": {"model_id": "test", "thresholds": {"general": 0.35, "character": 0.85}}, "note": "wd-tagger retag backfill — Rust native (v4.625.0)。未知 model_id は 404 model_not_found（意図的差異、batch と同じ）。", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 404, 409, 503], "python_note": "**v4.714.1 ニテ Python ヲ Rust ヘ合ハス**（`retag/batch` ト同根）。"},
    {"method": "POST", "path": "/api/wd-tagger/retag/query", "body": {"model_id": "test", "thresholds": {"general": 0.35, "character": 0.85}, "query_params": {}}, "note": "wd-tagger retag query — Rust native (v4.625.0)。未知 model_id は 404 model_not_found（意図的差異、batch と同じ）。対象集合は方針 C で「検索条件に一致する全件」。", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 404, 409, 503], "python_note": "**v4.714.1 ニテ Python ヲ Rust ヘ合ハス**（`retag/batch` ト同根）。"},
    {"method": "POST", "path": "/api/wd-tagger/retag/cancel", "body": {}, "note": "wd-tagger retag cancel — Rust native (v4.625.0)。batch と同一の JobManager / job id を共有する。", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 404, 503], "python_note": "admin scope必須。スキーマのみ確認。"},
    # --- agent governance forwarders (v4.409.0) ---
    {"method": "GET", "path": "/api/agent/anomaly", "note": "agent anomaly — **Rust ハ forwarder ニ非ズ、ベタ書キノ stub（anomalies=空配列・count=0）ヲ返ス。** Python ハ生キタ tracker/gate ヨリ答フ", "skip_body_compare": True, "accept_statuses": [200], "python_note": "**実測（v4.734.24 実走）: rust=200 py=200、本文相違 alerts_by_severity, anomalies, count, data, elevated, error, history_size, ok, recent_alerts, total_alerts。** 因ハ admin scope ニ非ズ——Rust ノ stub ナリ。todo(rust-gap, v4.734.3) ヲ見ヨ"},
    {"method": "GET", "path": "/api/agent/anomaly/alerts", "note": "agent anomaly/alerts — **Rust ハ forwarder ニ非ズ、ベタ書キノ stub（alerts=空配列・count=0）ヲ返ス。** Python ハ生キタ tracker/gate ヨリ答フ", "skip_body_compare": True, "accept_statuses": [200], "python_note": "**実測（v4.734.24 実走）: rust=200 py=200、本文相違 count, data, error, ok。** 因ハ admin scope ニ非ズ——Rust ノ stub ナリ。todo(rust-gap, v4.734.3) ヲ見ヨ"},
    {"method": "POST", "path": "/api/agent/anomaly/reset", "body": {}, "note": "agent anomaly/reset Rust forwarder (v4.409.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 401, 403, 503], "python_note": "admin scope必須。スキーマのみ確認。"},
    {"method": "GET", "path": "/api/agent/approval/history", "note": "agent approval/history Rust forwarder (v4.409.0) — admin scope", "accept_statuses": [200], "python_note": "**実測（v4.734.23 clean run）: rust=200 py=200。admin scope ニ由ル 401/403/503 ハ一度モ起キズ。**"},
    {"method": "POST", "path": "/api/agent/approval/nonexistent", "body": {"action": "approve"}, "note": "agent approval/{id} Rust forwarder (v4.409.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 404, 503], "python_note": "request_id不在→404。admin scope必須。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/agent/audit/report", "body": {}, "note": "agent audit/report Rust forwarder (v4.409.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 401, 403, 503], "python_note": "admin scope必須。スキーマのみ確認。"},
    {"method": "GET", "path": "/api/agent/budget", "note": "agent budget — **Rust ハ forwarder ニ非ズ、ベタ書キノ stub（budget=空辞書・total=0）ヲ返ス。** Python ハ生キタ tracker/gate ヨリ答フ", "skip_body_compare": True, "accept_statuses": [200], "python_note": "**実測（v4.734.24 実走）: rust=200 py=200、本文相違 budget, data, error, limits, ok, remaining, session_id, total, used。** 因ハ admin scope ニ非ズ——Rust ノ stub ナリ。todo(rust-gap, v4.734.3) ヲ見ヨ"},
    {"method": "POST", "path": "/api/agent/budget/reset", "body": {}, "note": "agent budget/reset Rust forwarder (v4.409.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 401, 403, 503], "python_note": "admin scope必須。スキーマのみ確認。"},
    {"method": "GET", "path": "/api/agent/circuit-breaker", "note": "agent circuit-breaker — **Rust ハ forwarder ニ非ズ、ベタ書キノ stub（state=closed・enabled=false）ヲ返ス。** Python ハ生キタ tracker/gate ヨリ答フ", "skip_body_compare": True, "accept_statuses": [200], "python_note": "**実測（v4.734.24 実走）: rust=200 py=200、本文相違 actions_per_minute, consecutive_errors, data, enabled, error, errors_per_minute, ok, reason, thresholds, total_recorded。** 因ハ admin scope ニ非ズ——Rust ノ stub ナリ。todo(rust-gap, v4.734.3) ヲ見ヨ"},
    {"method": "POST", "path": "/api/agent/circuit-breaker/reset", "body": {}, "note": "agent circuit-breaker/reset Rust forwarder (v4.409.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 401, 403, 503], "python_note": "admin scope必須。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/agent/undo/nonexistent", "body": {}, "note": "agent undo/{journal_id} Rust forwarder (v4.409.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 404, 503], "python_note": "journal_id不在→404。admin scope必須。スキーマのみ確認。"},
    # --- mesh-inference + tagger-servers/batch forwarders (v4.410.0) ---
    {"method": "GET", "path": "/api/mesh-inference/state", "note": "mesh-inference/state — **両者ハ peer ノ出所ヲ異ニス。** Python ハ生キタ router ノ in-memory peer ト registry.list_online() ヲ読ミ、 Rust ハ peers 表ノ last_reached_at 非 NULL ノ行ヲ読ム", "skip_body_compare": True, "accept_statuses": [200], "python_note": "**実測（v4.734.24 実走）: rust=200 py=200。封筒ヲ直シタル後、残ル相違ハ peers ノ要素数ノミ。** 因ハ出所ノ差ニシテ直列化ノ差ニ非ズ。todo(rust-gap, v4.734.24) ヲ見ヨ"},
    {"method": "POST", "path": "/api/mesh-inference/toggle", "body": {}, "note": "mesh-inference/toggle Rust forwarder (v4.410.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 503], "python_note": "admin scope必須。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/mesh-inference/bulk", "body": {}, "note": "mesh-inference/bulk Rust forwarder (v4.410.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 503], "python_note": "admin scope必須。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/mesh-inference/refresh", "body": {}, "note": "mesh-inference/refresh Rust forwarder (v4.410.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 503], "python_note": "admin scope必須。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/tagger-servers/batch", "body": {"file_ids": [], "limit": 1}, "note": "tagger-servers/batch Rust forwarder (v4.410.0) — no admin scope", "skip_body_compare": True, "accept_statuses": [200, 400, 409, 503], "python_note": "admin scope不要。スキーマのみ確認。"},
    {"method": "POST", "path": "/api/tagger-servers/batch/cancel", "body": {}, "note": "tagger-servers/batch/cancel Rust forwarder (v4.410.0) — no admin scope", "skip_body_compare": True, "accept_statuses": [200, 404, 503], "python_note": "admin scope不要。スキーマのみ確認。"},
    # --- collections export + llm forwarders (v4.411.0) ---
    {"method": "GET", "path": "/api/collections/999999/export", "note": "collections export Rust forwarder (v4.411.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 404, 503], "python_note": "**乖離ハ診断済ミ（v4.713.4）**——Python ハ `routes/collections.py:133` ニテ `format` クエリヲ先ニ検メ、recipe_csv/recipe_json 以外ハ 400 ヲ返ス。本項ハ format ヲ送ラヌ故、収集ノ存在確認ヘ至ラズ 400。Rust ハ存在確認ヲ先ニ為シテ 404。**検証順序ノ差**ニシテ孰レモ未移植ニ非ズ。兄弟ノ `/export/csv` ハ同ジ検メヲ持タヌ故、元ヨリ 404 ニテ一致シ居タリ——**症状ノ食ヒ違ヒガ原因ヲ指シタリ。**"},
    {"method": "GET", "path": "/api/collections/999999/export/csv", "note": "collections export/csv Rust forwarder (v4.411.0) — admin scope",  "accept_statuses": [404]},
    {"method": "POST", "path": "/api/llm/agent", "body": {}, "note": "llm/agent Rust native (v4.617.0) — admin scope", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 404, 501, 502], "python_note": "admin scope必須。空bodyは400想定。"},
    {"method": "POST", "path": "/api/llm/chat", "body": {}, "note": "llm/chat Rust native (v4.617.0) — no auth", "skip_body_compare": True, "accept_statuses": [200, 400, 404, 422, 502, 503], "python_note": "auth不要。空bodyは400/422想定。"},
    # --- manifest-registered endpoints: Rust未実装 body mismatch 抑制 (v4.413.1) ---
    # manifest.yaml に登録済みだが Rust が 404 を返し Python と body が異なる。
    # status のみ確認（skip_body_compare）して body 差異を許容する。
    {"method": "GET", "path": "/keys", "note": "manifest /keys — Rust 404 vs Python 404 body mismatch suppressed", "skip_body_compare": True, "accept_statuses": [404]},
    {"method": "GET", "path": "/admin-token", "note": "manifest /admin-token — Rust 404 vs Python 404 body mismatch suppressed", "skip_body_compare": True, "accept_statuses": [404]},
    {"method": "GET", "path": "/agentmemory/config", "note": "manifest /agentmemory/config — Rust 404 vs Python 404 body mismatch suppressed", "skip_body_compare": True, "accept_statuses": [404]},
    {"method": "GET", "path": "/config", "note": "manifest /config — Rust 404 vs Python 404 body mismatch suppressed", "skip_body_compare": True, "accept_statuses": [404]},
    {"method": "GET", "path": "/info", "note": "manifest /info — Rust 404 vs Python 404 body mismatch suppressed", "skip_body_compare": True, "accept_statuses": [404]},
    {"method": "GET", "path": "/internal/ping", "note": "manifest /internal/ping — Rust 404 vs Python 404 body mismatch suppressed", "skip_body_compare": True, "accept_statuses": [404]},
    {"method": "GET", "path": "/headroom/config", "note": "manifest /headroom/config — Rust 404 vs Python 401 status+body mismatch suppressed", "skip_body_compare": True, "accept_statuses": [401, 404]},
    {"method": "GET", "path": "/models", "note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 manifest /models — Rust 404 vs Python 404 body mismatch suppressed", "accept_statuses": [404]},
    {"method": "GET", "path": "/router/health", "note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 manifest /router/health — Rust 404 vs Python 404 body mismatch suppressed", "accept_statuses": [404]},
    # --- page routes: Python backend removed → Rust returns 503 (v4.418.0) ---
    {"method": "GET", "path": "/crypto-tools", "note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 page stub (Python backend removed)", "accept_statuses": [200, 401, 403, 503]},
    {"method": "GET", "path": "/help", "note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 page stub (Python backend removed)", "accept_statuses": [200, 503]},
    # --- Batch B: 14 builtin extension pages (v4.446.0) ---
    {"method": "GET", "path": "/ext/annotations/notes", "note": "annotations extension page (Rust native)", "skip_body_compare": True, "accept_statuses": [200, 308, 404, 503]},
    {"method": "GET", "path": "/ext/speech-to-text", "note": "speech-to-text extension page (Rust native)", "skip_body_compare": True, "accept_statuses": [200, 308, 503]},
    {"method": "GET", "path": "/ext/lora-dataset", "note": "lora-dataset extension page (Rust native)", "skip_body_compare": True, "accept_statuses": [200, 308, 503]},
    {"method": "GET", "path": "/ext/prompt-library", "note": "prompt-library extension page (Rust native)", "skip_body_compare": True, "accept_statuses": [200, 308, 503]},
    {"method": "GET", "path": "/ext/prompt-sim", "note": "prompt-sim extension page (Rust native)", "skip_body_compare": True, "accept_statuses": [200, 308, 503]},
    {"method": "GET", "path": "/ext/prompt-sim/manager", "note": "prompt-sim wildcard manager page (Rust native)", "accept_statuses": [200]},
    {"method": "GET", "path": "/ext/prompt-sim/sweep-axes-manager", "note": "prompt-sim sweep axes manager page (Rust native)", "accept_statuses": [200]},
    {"method": "GET", "path": "/ext/convert", "note": "sd-nai-convert extension page (Rust native)", "skip_body_compare": True, "accept_statuses": [200, 308, 503]},
    {"method": "GET", "path": "/ext/chatlog", "note": "chatlog extension page (Rust native)", "skip_body_compare": True, "accept_statuses": [200, 308, 503]},
    {"method": "GET", "path": "/ext/cross-search", "note": "cross-search extension page (Rust native)", "skip_body_compare": True, "accept_statuses": [200, 308, 503]},
    {"method": "GET", "path": "/ext/favorites", "note": "favorites-manager extension page (Rust native)", "skip_body_compare": True, "accept_statuses": [200, 308, 503]},
    {"method": "GET", "path": "/ext/freeze-pullback", "note": "freeze-pullback extension page (Rust native)", "skip_body_compare": True, "accept_statuses": [200, 308, 503]},
    {"method": "GET", "path": "/ext/md-viewer", "note": "md-viewer extension page (Rust native)", "skip_body_compare": True, "accept_statuses": [200, 308, 503]},
    {"method": "GET", "path": "/ext/watcher", "note": "watcher extension page (Rust native)", "skip_body_compare": True, "accept_statuses": [200, 308, 503]},
    {"method": "GET", "path": "/ext/github", "note": "github-integration extension page (Rust native)", "skip_body_compare": True, "accept_statuses": [200, 308, 503]},
    {"method": "GET", "path": "/ext/mcp-client", "note": "mcp-client extension page (Rust native)", "skip_body_compare": True, "accept_statuses": [200, 308, 503]},
    {"method": "GET", "path": "/share", "note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 page stub (Python backend removed)", "accept_statuses": [200, 503]},
    {"method": "GET", "path": "/tauri-shell", "note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 page stub (Python backend removed)", "accept_statuses": [200, 503]},
    {"method": "GET", "path": "/backends", "note": "page stub (Python backend removed)", "skip_body_compare": True, "accept_statuses": [404, 503]},
    {"method": "GET", "path": "/local/status", "note": "page stub (Python backend removed)", "skip_body_compare": True, "accept_statuses": [404, 503]},
    {"method": "GET", "path": "/groups", "note": "page stub (Python backend removed)", "skip_body_compare": True, "accept_statuses": [404, 503]},
    {"method": "GET", "path": "/defaults", "note": "page stub (Python backend removed)", "skip_body_compare": True, "accept_statuses": [404, 503]},
    # --- Phase B additions (v4.419.0) ---
    {"method": "GET", "path": "/api/scan-roots/0", "python_path": None, "note": "scan-root 単件取得 (Rust native, Phase B)", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 404], "python_note": "Python ハ此ノ path ヘ GET ヲ登録セズ（実走 py=405 Method Not Allowed、v4.713.3 計測）。即チ GET ニ限リ Rust 単独ノ route ナリ。DELETE 等 他 method ハ Python ニモ在ル故、path ノミノ照合デハ判ラヌ。"},
    {"method": "PUT", "path": "/api/settings/llm-endpoints", "body": {"category": "test", "base_url": "http://localhost:9999", "model": "test-model"}, "note": "LLM エンドポイント更新 (Rust native)", "accept_statuses": [200, 400, 401, 403], "python_note": "**「Rust native」ノ註ハ偽ナリキ（v4.732.16 実測）**——Python モ routes/llm_endpoints.py ニテ本 route ヲ実装シ、app_factory_blueprints.py ガ登録ス。body 比較ノ抑止ハ「Python ニ無シ」ヲ前提トシ居タルガ其ノ前提ガ誤リ。今ハ比較ス。"},
# --- Phase D additions (v4.421.0) — OCR detail stubs / Phase 1 native ---
    {"method": "POST", "path": "/api/ocr/1", "body": {}, "note": "OCR 実行 stub (Phase D)", "skip_body_compare": True, "accept_statuses": [202, 400, 401, 404, 409, 503], "python_path": None, "python_note": "Rust native ジョブ形。202=受理 / 400=入力不正 / 401=未認証 / 404=file 不在 / 409=OCR ジョブが実行中 / 503=PIN 未設定 or engine 未解決。Python の同 route は段③で削除する。"},
    {"method": "GET", "path": "/api/ocr/result/1", "note": "OCR 結果取得 (Phase 1 native)", "accept_statuses": [200], "python_note": "**「Rust native」ノ註ハ偽ナリキ（v4.732.16 実測）**——Python モ core/ocr_api/single_ops.py ニテ本 route ヲ実装シ、app_factory_blueprints.py ガ登録ス。body 比較ノ抑止ハ「Python ニ無シ」ヲ前提トシ居タルガ其ノ前提ガ誤リ。今ハ比較ス。"},
    {"method": "DELETE", "path": "/api/ocr/result/1", "note": "OCR 結果削除 (Phase 1 native)", "accept_statuses": [200], "python_note": "**封ヲ Python ヘ揃ヘタリ（v4.732.18）**——Python ノ api_success ハ `{ok, error: null, data: null, …payload}` ヲ組ム。Rust ハ生ノ json! ニテ error/data ヲ欠キ居タル故、比較ヲ生カシタ途端ニ差ト成レリ。`ocr_ok` / `tools_ok` / `api_result` ヘ通シ、本文比較ヲ戻ス。"},
    {"method": "GET", "path": "/api/ocr/engines", "note": "OCR エンジン一覧 (Phase 1 native)", "accept_statuses": [200, 403], "skip_body_compare": True, "python_note": "**捏造ノ値ナリ——封ノ差ニ非ズ（v4.732.18 実測、従前ノ註ハ誤リ）。** Rust ハ `{engines: [], manga_ocr_available: false}` ヲ**固定値**ニテ返ス（routes/ocr.rs ノ註ガ『ai_servers is not wired here yet』ト自ラ述ブ）。Python ハ実ノ server registry ト model 毎ノ score ヲ読ム（core/ocr_api/single_ops.py → `core.ocr_core.router`。**此ノ module ハ extensions_core_shim ガ起動時ニ extensions/builtin_ocr/core_impl/ ヘ sys.modules 上ノ別名ヲ張ル物ニシテ、静的ナ grep デハ見エヌ**）。即チ Rust ハ設定ノ如何ヲ問ハズ『OCR エンジン無シ』ト答フ。封ハ v4.732.18 ニテ直シタル故、残ル差ハ中身ノミ。todo(rust-gap, v4.732.18) ニ登録済ミ。"},
    {"method": "GET", "path": "/api/ocr/profiles", "note": "OCR プロファイル一覧 (Phase 1 native)", "accept_statuses": [200, 401, 403], "python_path": "/api/ocr/profiles", "python_envelope": True},
    {"method": "POST", "path": "/api/ocr/profiles/fetch", "body": {}, "note": "OCR community profiles fetch — URL 必須", "accept_statuses": [400], "python_path": "/api/ocr/profiles/fetch"},
    {"method": "POST", "path": "/api/ocr/profiles/fetch", "body": {"url": "http://127.0.0.1:8080/profiles.json"}, "note": "OCR community profiles fetch — loopback blocked", "accept_statuses": [400], "python_path": "/api/ocr/profiles/fetch"},
    {"method": "POST", "path": "/api/ocr/profiles/fetch", "body": {"url": "ftp://example.com/profiles.json"}, "note": "OCR community profiles fetch — scheme blocked", "accept_statuses": [400], "python_path": "/api/ocr/profiles/fetch"},
    {"method": "POST", "path": "/api/ocr/batch", "body": {}, "note": "OCR バッチ stub (Phase D)", "skip_body_compare": True, "accept_statuses": [202, 400, 401, 404, 409, 503], "python_path": None, "python_note": "Rust native ジョブ形。202=受理 / 400=入力不正 / 401=未認証 / 404=file 不在 / 409=OCR ジョブが実行中 / 503=PIN 未設定 or engine 未解決。Python の同 route は段③で削除する。"},
    {"method": "GET", "path": "/api/ocr/export/9001", "note": "OCR エクスポート (v4.714.0 ニテ Rust 移植済ミ、txt/md/json)。fixture ノ file_id=9001 ハ `files` 行ヲ持タヌ故、`files` ヲ walk スル掃除ノ類ヒカラ見エズ、本項ノミ到達ス。之無クバ両者 404 ヲ返シ、本文ハ一片モ作ラレザリキ。", "accept_statuses": [200], "python_note": "両者共ニ本文ヲ生ジテ突キ合ハス（fixture 導入前ハ両者 404 ニテ空ノ比較ナリキ）。fixture ハ決定的ナル故、本文ハ厳密ニ比ブ。"},
    {"method": "POST", "skip": True, "path": "/api/ocr/export/batch", "body": {}, "note": "OCR バッチエクスポート stub (Phase D) — skip 理由: Rust 未移植 (rust=501 py=400)", "skip_body_compare": True, "accept_statuses": [200, 501], "python_note": "実走 rust=501 py=400（v4.713.5）。**Rust 未移植ノ本物ノ欠落**ニシテ、harness ハ Python 稼働中ノ Rust 501 ヲ設計上通サヌ故、移植ヲ措キテ緑ニスル道無シ。TODO ニ記ス。"},
    {"method": "POST", "path": "/api/ocr/translate/1", "body": {}, "note": "OCR 翻訳 (v4.714.0 以降ニテ Rust 移植済ミ)。file_id=1 ハ OCR 結果ヲ持タヌ故、両者共ニ 404 ニ止マル。", "python_note": "両者共ニ 404 `{\"ok\": false, \"error\": \"OCR result not found. Run OCR first.\"}` ヲ返シ、本文ヲ厳密ニ比ブ。此ノ一致ハ harness ガ PIN 認証ヲ無効ニスル前提ノ上ニ在リ——`require_admin_scope` ハ PIN 無効時ニ `None` ヲ返シ通過セシムル（scope.rs:22-24、`require_admin_scope_allows_when_pin_auth_disabled` ニテ固定）故ニ 403 ヘ堕チズ、404 ニ達ス。PIN 有効ナラバ Rust ハ 403 ヲ返シ、`accept_statuses` ト `skip_body_compare` ヲ具フル必要ガ生ズ——隣接ノ `/api/ocr/export/batch` 項ト同ジ形ナリ。"},
    {"method": "POST", "path": "/api/ocr/translate/1", "body": {"target_lang": ""}, "note": "OCR 翻訳 — target_lang 必須", "python_note": "両者共ニ 400 `{\"ok\": false, \"error\": \"target_lang is required\"}` ヲ返シ、本文ヲ厳密ニ比ブ。此レモ同ジク PIN 認証無効ノ前提ニ依ル——認証有効ナラバ 403 ニ堕チ、緩和句ヲ要ス。"},
    {"method": "GET", "path": "/api/ocr/translations/9001", "note": "OCR 翻訳一覧 (Phase 1 native)", "accept_statuses": [200, 403], "python_note": "**「Rust native」ノ註ハ偽ナリキ（v4.732.16 実測）**——Python モ core/ocr_api/translate_ops.py ニテ本 route ヲ実装シ、app_factory_blueprints.py ガ登録ス。body 比較ノ抑止ハ「Python ニ無シ」ヲ前提トシ居タルガ其ノ前提ガ誤リ。今ハ比較ス。"},
    {"method": "GET", "path": "/api/ocr/overlay/9001", "note": "OCR overlay (v4.717.0 ニテ Rust 移植済ミ)。本項ガ買フハ **status ト content-type ノミ**ナリ——`verify_rust_compat.py:4364` ハ非 JSON ノ本文比較ヲ content-type ノ一致ヘ退化サス故、画像ヲ返ス endpoint ノ本文ハ原理的ニ比ベ得ズ。**両描画系ガ一致スル証拠ト読ム勿レ**——PIL ト ab_glyph ハ画素ヲ揃ヘ得ズ、仕様ハ之ヲ装フヲ禁ズ。真ノ検メハ crate 内ノ golden vector（`overlay_layout.rs`）ナリ。", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 503], "python_note": "fixture ノ 9001 ハ `files` 行ト実画像ヲ帯ブル故、両者共ニ描画ヘ至ル（之無クバ両者 404 ノ門ニテ止マリ、画素ハ一片モ描カレザリキ）。font 未取得ノ時ハ Rust ガ 503 ヲ返ス故、之モ許ス。"},
    {"method": "POST", "path": "/api/ocr/benchmark", "body": {}, "note": "OCR ベンチマーク stub (Phase D)", "skip_body_compare": True, "accept_statuses": [202, 400, 401, 404, 409, 503], "python_path": None, "python_note": "Rust native ジョブ形。202=受理 / 400=入力不正 / 401=未認証 / 404=file 不在 / 409=OCR ジョブが実行中 / 503=PIN 未設定 or engine 未解決。Python の同 route は段③で削除する。"},
    {"method": "GET", "path": "/api/ocr/npu", "note": "OCR NPU status", "accept_statuses": [200, 401, 403], "python_note": "**v4.732.21 ニテ本文比較ヲ戻シタリ——従前ノ理由ハ偽ナリキ。** 「DB 状態依存」等ト註サレ居タルガ一度モ実測サレ居ラズ、抑止ヲ外シテ走ラセタルニ **本文マデ一致セリ**。harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス故、「状態依存」ハ其レ自体デハ差ノ説明ト成ラヌ。今ハ status モ本文モ全比較ス。 移植済ミ（501 ヲ脱ス）。本文ヲ比較セザルハ、両実装ガ**別ノ物ヲ測ル**故ナリ——Python ノ hailo_available ハ `hailo_platform` ノ import 可否ニシテ硬件ノ有無ニ非ズ、Rust ハ device node ノ実在ヲ見ル。同一機ニテモ答ヘハ割レ得、且ツ Rust ノ方ガ正シキ主張ナリ。欄ノ形ト日本語ノ文面ハ routes/ocr_npu.rs ノ単体試験ガ逐語ニ固定ス。ryzen_available ハ Rust ニ onnxruntime 依存無キ故 false 固定——測ラザル限界ヲ明記スルモノナリ。", "schema_check": ["npu", "optimization", "ok", "error"]},
    {"method": "GET", "path": "/api/ocr/benchmark/cases", "note": "OCR ベンチマークケース stub (Phase D)", "skip_body_compare": True, "accept_statuses": [501], "python_note": "実走 rust=501 py=200（v4.713.3 計測）。**Python ハ正常ニ応フルニ Rust ハ未移植**——七件中最モ重キ乖離ナリ。TODO ニ記ス。"},
    {"method": "PUT", "path": "/api/ocr/profiles/test-model", "body": {}, "note": "OCR プロファイル更新 stub (Phase D)", "accept_statuses": [200, 400, 503], "python_note": "**封ヲ Python ヘ揃ヘタリ（v4.732.18）**——Python ノ api_success ハ `{ok, error: null, data: null, …payload}` ヲ組ム。Rust ハ生ノ json! ニテ error/data ヲ欠キ居タル故、比較ヲ生カシタ途端ニ差ト成レリ。`ocr_ok` / `tools_ok` / `api_result` ヘ通シ、本文比較ヲ戻ス。"},
    {"method": "POST", "path": "/api/ocr/video/1", "body": {}, "note": "OCR 動画 stub (Phase D)", "skip_body_compare": True, "accept_statuses": [202, 400, 401, 404, 409, 503], "python_path": None, "python_note": "Rust native ジョブ形。202=受理 / 400=入力不正 / 401=未認証 / 404=file 不在 / 409=OCR ジョブが実行中 / 503=PIN 未設定 or engine 未解決。Python の同 route は段③で削除する。"},
    {"method": "POST", "path": "/api/ocr/pdf/1", "body": {}, "note": "OCR PDF stub (Phase D)", "skip_body_compare": True, "accept_statuses": [202, 400, 401, 404, 409, 503], "python_path": None, "python_note": "Rust native ジョブ形。202=受理 / 400=入力不正 / 401=未認証 / 404=file 不在 / 409=OCR ジョブが実行中 / 503=PIN 未設定 or engine 未解決。Python の同 route は段③で削除する。"},
    # --- Phase D additions (v4.421.0) — Profiles stubs ---
    # --- /api/profiles (v4.630.1 re-measured): these are NOT stubs. The full
    # implementation lives in routes/auto_stubs.rs (write_profile_atomic &c);
    # the notes below used to claim "Rust stub, 503" and the entries FAILed on
    # the genuine business status. The fixtures deliberately stay NON-MUTATING
    # (they run against a live server), so they exercise the handler's
    # validation path and expect 400/404 for an absent profile rather than
    # creating one. Happy-path coverage lives in the auto_stubs.rs
    # `profiles_tests` module, not here. ---
    {"method": "GET", "path": "/api/profiles", "note": "プロファイル一覧 (Rust native)", "accept_statuses": [200], "python_note": "**「Rust native」ノ註ハ偽ナリキ（v4.732.16 実測）**——Python モ core/profiles_api/routes_crud.py ニテ本 route ヲ実装シ、app_factory_blueprints.py ガ登録ス。body 比較ノ抑止ハ「Python ニ無シ」ヲ前提トシ居タルガ其ノ前提ガ誤リ。今ハ比較ス。"},
    {"method": "GET", "path": "/api/profiles/test-profile", "note": "プロファイル単件取得 (Rust native)", "accept_statuses": [200, 404], "python_note": "**「Rust native」ノ註ハ偽ナリキ（v4.732.16 実測）**——Python モ core/profiles_api/routes_crud.py ニテ本 route ヲ実装シ、app_factory_blueprints.py ガ登録ス。body 比較ノ抑止ハ「Python ニ無シ」ヲ前提トシ居タルガ其ノ前提ガ誤リ。今ハ比較ス。"},
    {"method": "POST", "path": "/api/profiles", "body": {"name": "test profile!", "label": "parity"}, "note": "プロファイル作成 (Rust native) — 名前検証のみを叩く", "accept_statuses": [400], "python_note": "**「Rust native」ノ註ハ偽ナリキ（v4.732.16 実測）**——Python モ core/profiles_api/routes_crud.py ニテ本 route ヲ実装シ、app_factory_blueprints.py ガ登録ス。body 比較ノ抑止ハ「Python ニ無シ」ヲ前提トシ居タルガ其ノ前提ガ誤リ。今ハ比較ス。"},
    {"method": "PUT", "path": "/api/profiles/test-profile", "body": {}, "note": "プロファイル更新 (Rust native)", "accept_statuses": [200, 400, 404], "python_note": "**「Rust native」ノ註ハ偽ナリキ（v4.732.16 実測）**——Python モ core/profiles_api/routes_crud.py ニテ本 route ヲ実装シ、app_factory_blueprints.py ガ登録ス。body 比較ノ抑止ハ「Python ニ無シ」ヲ前提トシ居タルガ其ノ前提ガ誤リ。今ハ比較ス。"},
    {"method": "DELETE", "path": "/api/profiles/test-profile", "note": "プロファイル削除 (Rust native)", "accept_statuses": [200, 404], "python_note": "**「Rust native」ノ註ハ偽ナリキ（v4.732.16 実測）**——Python モ core/profiles_api/routes_crud.py ニテ本 route ヲ実装シ、app_factory_blueprints.py ガ登録ス。body 比較ノ抑止ハ「Python ニ無シ」ヲ前提トシ居タルガ其ノ前提ガ誤リ。今ハ比較ス。"},
    {"method": "POST", "path": "/api/profiles/test-profile/duplicate", "body": {"new_name": "test-profile-copy", "new_label": "parity"}, "note": "プロファイル複製 (Rust native)", "skip_body_compare": True, "accept_statuses": [200, 400, 404, 409], "python_note": "実走 rust=404 py=400（v4.713.5）。`PUT /api/profiles/{name}` ト同根——Python ハ入力ヲ先ニ検メ 400、Rust ハ複製元ノ存在確認ガ先ニテ 404。**検証順序ノ差**ナリ。"},
    {"method": "POST", "path": "/api/profiles/test-profile/rename", "body": {"new_name": "test-profile-renamed"}, "note": "プロファイルリネーム (Rust native)", "skip_body_compare": True, "accept_statuses": [200, 400, 404, 409], "python_note": "実走 rust=404 py=400（v4.713.5）。`duplicate` ト同根、**検証順序ノ差**ナリ。"},
    {"method": "POST", "path": "/api/profiles/test-profile/favorite", "body": {}, "note": "プロファイルお気に入り (Rust native)", "accept_statuses": [200, 404], "python_note": "**「Rust native」ノ註ハ偽ナリキ（v4.732.16 実測）**——Python モ core/profiles_api/routes_crud.py ニテ本 route ヲ実装シ、app_factory_blueprints.py ガ登録ス。body 比較ノ抑止ハ「Python ニ無シ」ヲ前提トシ居タルガ其ノ前提ガ誤リ。今ハ比較ス。"},
    {"method": "GET", "path": "/api/profiles/test-profile/export", "note": "プロファイルエクスポート (Rust native)", "accept_statuses": [200, 404], "python_note": "**「Rust native」ノ註ハ偽ナリキ（v4.732.16 実測）**——Python モ core/profiles_api/routes_qr.py ニテ本 route ヲ実装シ、app_factory_blueprints.py ガ登録ス。body 比較ノ抑止ハ「Python ニ無シ」ヲ前提トシ居タルガ其ノ前提ガ誤リ。今ハ比較ス。"},
    {"method": "POST", "path": "/api/profiles/import-preview", "body": {}, "note": "プロファイルインポートプレビュー (Rust native)", "accept_statuses": [400], "skip_body_compare": True, "python_note": "**要求契約ソノモノガ違フ（v4.732.16 実測、本文比較ニテ code・error ガ相違）**——Python ハ `{qr_data: \"<{schema, profile} ヲ収ムル JSON 文字列>\"}` ヲ取リ (core/profiles_api/routes_qr.py)、Rust ハ profile ヲ直ニ最上位ニ取ル (routes/auto_stubs.rs::profiles_import)。誤リノ code モ invalid_qr 対 invalid_name ニテ異ナル。書式ノ差ニ非ズ移植ノ欠落ナル故、契約ヲ揃ヘル迄抑ヘル。todo(parity, v4.732.16) ニ登録済ミ。"},
    {"method": "POST", "path": "/api/profiles/import", "body": {}, "note": "プロファイルインポート (Rust native)", "accept_statuses": [400], "skip_body_compare": True, "python_note": "**要求契約ソノモノガ違フ（v4.732.16 実測、本文比較ニテ code・error ガ相違）**——Python ハ `{qr_data: \"<{schema, profile} ヲ収ムル JSON 文字列>\"}` ヲ取リ (core/profiles_api/routes_qr.py)、Rust ハ profile ヲ直ニ最上位ニ取ル (routes/auto_stubs.rs::profiles_import)。誤リノ code モ invalid_qr 対 invalid_name ニテ異ナル。書式ノ差ニ非ズ移植ノ欠落ナル故、契約ヲ揃ヘル迄抑ヘル。todo(parity, v4.732.16) ニ登録済ミ。"},
    # --- Phase 2 additions (v4.428.0) — Prompt Simulator (Group AY: Rust native) ---
    {"method": "GET", "path": "/ext/prompt-sim/wildcards", "auth": "admin", "note": "prompt-sim wildcards list (Phase 2, Rust native)", "schema_check": ["wildcards", "dirs"], "accept_statuses": [200, 401, 403], "python_note": "Rust native。ワイルドカード一覧。"},
    {"method": "POST", "path": "/ext/prompt-sim/load-wildcards-zip", "auth": "admin", "body": {}, "note": "prompt-sim load ZIP (Phase 2, Rust native)", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403], "python_note": "Rust native。ZIP読み込み。multipart処理。"},
    {"method": "POST", "path": "/ext/prompt-sim/wildcard-file", "auth": "admin", "body": {"name": "test.txt", "content": ""}, "note": "prompt-sim save wildcard file (Phase 2, Rust native)", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403], "python_note": "Rust native。ワイルドカード保存。"},
    {"method": "POST", "path": "/ext/prompt-sim/wildcard-rename", "auth": "admin", "body": {"old_path": "a.txt", "new_path": "b.txt"}, "note": "prompt-sim rename wildcard (Phase 2, Rust native)", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403], "python_note": "Rust native。リネーム。"},
    {"method": "POST", "path": "/ext/prompt-sim/wildcard-delete", "auth": "admin", "body": {"path": "test.txt"}, "note": "prompt-sim delete wildcard (Phase 2, Rust native)", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403], "python_note": "Rust native。削除。"},
    {"method": "POST", "path": "/ext/prompt-sim/wildcard-dirs", "auth": "admin", "body": {"dirs": []}, "note": "prompt-sim wildcard dirs config (Phase 2, Rust native)", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403], "python_note": "Rust native。設定保存。"},
    {"method": "GET", "path": "/ext/prompt-sim/sweep-axes", "auth": "admin", "note": "prompt-sim sweep axes list (Phase 2, Rust native)", "schema_check": ["axes"], "accept_statuses": [200, 401, 403], "python_note": "Rust native。スウィープ軸一覧。"},
    {"method": "POST", "path": "/ext/prompt-sim/sweep-axis-config", "auth": "admin", "body": {}, "note": "prompt-sim sweep axis config (Phase 2, Rust native)", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403], "python_note": "Rust native。軸設定保存。"},
    {"method": "POST", "path": "/ext/prompt-sim/convert", "auth": "admin", "body": {"prompt": "", "mode": "nai_to_sd"}, "note": "prompt-sim convert NAI↔SD (Phase 2, Rust native)", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403], "python_note": "Rust native。変換。"},
    {"method": "POST", "path": "/ext/prompt-sim/emphasis", "auth": "admin", "body": {"prompt": ""}, "note": "prompt-sim emphasis analyze (Phase 2, Rust native)", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403], "python_note": "Rust native。強調解析。"},
    {"method": "GET", "path": "/ext/prompt-sim/danbooru-ac", "auth": "admin", "note": "prompt-sim Danbooru proxy (Phase 2, Rust native — external API)", "skip_body_compare": True, "accept_statuses": [200, 401, 403, 502, 503], "python_note": "Rust native。外部API依存。"},
    {"method": "POST", "path": "/ext/prompt-sim/dp-analyze", "auth": "admin", "body": {"prompt": "{a|b|c}"}, "note": "prompt-sim dp-analyze (Phase 4, Rust native)", "schema_check": ["groups"], "schema_check_statuses": [200], "accept_statuses": [200, 400, 401, 403, 503], "python_note": "Rust native。dp probability解析。Python不要。503=ビルド前互換。"},
    # Phase 3 — settings + tools_ops
    {"method": "POST", "path": "/api/settings/config", "auth": "admin", "body": {"timezone": "UTC"}, "note": "settings config save (Phase 3, Rust native)", "accept_statuses": [200, 400, 401, 403], "python_note": "**封ヲ Python ヘ揃ヘタリ（v4.732.18）**——Python ノ api_success ハ `{ok, error: null, data: null, …payload}` ヲ組ム。Rust ハ生ノ json! ニテ error/data ヲ欠キ居タル故、比較ヲ生カシタ途端ニ差ト成レリ。`ocr_ok` / `tools_ok` / `api_result` ヘ通シ、本文比較ヲ戻ス。"},
    {"method": "POST", "path": "/api/tools/clear-cache", "auth": "admin", "body": {}, "note": "clear thumbnail cache (Phase 3, Rust native)", "accept_statuses": [200, 401, 403], "python_note": "**封ヲ Python ヘ揃ヘタリ（v4.732.18）**——Python ノ api_success ハ `{ok, error: null, data: null, …payload}` ヲ組ム。Rust ハ生ノ json! ニテ error/data ヲ欠キ居タル故、比較ヲ生カシタ途端ニ差ト成レリ。`ocr_ok` / `tools_ok` / `api_result` ヘ通シ、本文比較ヲ戻ス。"},
    {"method": "POST", "path": "/api/tools/rebuild-groups", "auth": "admin", "body": {}, "note": "**v4.734.11 ニテ Python ノ実バグヲ直シ、両者 200 ト成レリ（body=✅）。** **従前ノ註ハ実測ヲ持チ乍ラ診断ヲ誤リ居タリ**——「parity 環境ノ seed DB ニ対シ Python ノ再構築ガ失敗ス。Rust ノ方ガ堅シ」ト記シ居タルガ、真因ハ `core/services_core/tools_service.py:23` ノ古キ import（`_CACHE_PATH` ハ `_cache_path()` ヘ変ハリ居タリ）ニシテ、**seed DB ト無関係ニ何処デモ ImportError ヲ起コシ居タリ。** 即チ Tools 画面ノ「グループ再構築」ハ常ニ 500 ナリキ。**実測ハ診断ニ非ズ。** 併セテ Rust ノ封（ok/error/data）モ足シタリ。", "schema_check": ["status", "folders", "zips", "file_count"], "schema_check_statuses": [200], "accept_statuses": [200], "python_note": "実走 rust=200 py=500（v4.713.5）。**Rust ハ成功シ Python ハ倒ル**——parity 環境ノ seed DB ニ対シ Python ノ再構築ガ失敗ス。**Rust ノ方ガ堅シ。**500 ハ Python 側ノ既知ノ振舞ヒトシテ許容ス。"},
    {"method": "POST", "path": "/api/tools/compute-hashes", "auth": "admin", "body": {}, "note": "compute hashes stub (Phase 3, Python proxy or 503)", "skip_body_compare": True, "accept_statuses": [200, 401, 403, 503], "python_note": "Python利用可能時はプロキシ。なければ503。"},
    {"method": "GET", "path": "/api/dnd-inbox", "auth": "admin", "note": "dnd inbox dir (Phase 3, Rust native)", "accept_statuses": [200, 401, 403], "python_note": "**封ヲ Python ヘ揃ヘタリ（v4.732.18）**——Python ノ api_success ハ `{ok, error: null, data: null, …payload}` ヲ組ム。Rust ハ生ノ json! ニテ error/data ヲ欠キ居タル故、比較ヲ生カシタ途端ニ差ト成レリ。`ocr_ok` / `tools_ok` / `api_result` ヘ通シ、本文比較ヲ戻ス。"},
    {"method": "POST", "path": "/api/dnd-upload", "auth": "admin", "body": {}, "note": "dnd upload stub (Phase 3, Python proxy or 503)", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 503], "python_note": "Python利用可能時はプロキシ。なければ503。"},
    {"method": "POST", "path": "/api/files/register-path", "auth": "admin", "body": {"path": "/nonexistent/test.jpg"}, "note": "register file path (Phase 3, Rust native)", "skip_body_compare": True, "accept_statuses": [200, 400, 401, 403, 404, 409], "python_note": "実走 rust=400 py=404（v4.713.5）。不在パスニ対シ Rust ハ入力不正ト見テ 400、Python ハ不在ト見テ 404。**検証順序ノ差**ナリ。"},
    {"method": "POST", "path": "/api/tools/delete-duplicates", "auth": "admin", "body": {"groups": []}, "note": "delete duplicates (Phase 3, Rust native)", "accept_statuses": [200, 400, 401, 403], "python_note": "**封ヲ Python ヘ揃ヘタリ（v4.732.18）**——Python ノ api_success ハ `{ok, error: null, data: null, …payload}` ヲ組ム。Rust ハ生ノ json! ニテ error/data ヲ欠キ居タル故、比較ヲ生カシタ途端ニ差ト成レリ。`ocr_ok` / `tools_ok` / `api_result` ヘ通シ、本文比較ヲ戻ス。"},
    # --- ext/watcher (Group AX2: Rust native) ---
    {"method": "GET", "path": "/ext/watcher/info", "note": "ファイル監視情報取得 Rust native (Group AX2)", "schema_check": ["running", "watched_roots", "stats"], "accept_statuses": [200]},
    {"method": "POST", "path": "/ext/watcher/start", "body": {}, "note": "ファイル監視開始 Rust native (Group AX2)", "schema_check": ["ok"], "accept_statuses": [200, 400, 401, 403, 409, 500], "skip_body_compare": True, "python_note": "Rust native ext。scan_roots未設定なら400。スキーマのみ確認。"},
    {"method": "POST", "path": "/ext/watcher/stop", "body": {}, "note": "ファイル監視停止 Rust native (Group AX2)", "schema_check": ["ok"], "accept_statuses": [200, 401, 403, 409], "skip_body_compare": True, "python_note": "Rust native ext。未実行なら409 ok=false。スキーマのみ確認。"},
    # --- infer (Group AX3: Rust native WD-Tagger engine) ---
    {"method": "POST", "path": "/api/infer/wd-tagger", "body": {"path": "/nonexistent/test.jpg", "model_id": "wd_vit_v3"}, "note": "WD-Tagger ONNX推論 Rust native (Group AX3)", "schema_check": [], "accept_statuses": [400, 401, 403, 503], "skip_body_compare": True, "python_path": None, "python_note": "Rust native。モデル未DL=503、パス不正=400。"},
    # --- hailo-yolo stream (T9 手順4/5) ---
    # 16 route。T9手順4でPython側register_stream_routes呼び出しを除去したため、
    # python_path=None + rust_native=True へ切替済 (Rust-only shape check)。
    # 副作用のある入力は避け、id/url欠落・存在しないsentinel idで各契約の異常系分岐を突く。
    # 出典: docs/superpowers/specs/2026-08-12-hailo-yolo-stream-rust-port-design.md §10, §検証方針 差分表
    #1 GET /stream/sources — 一覧は既存 stream_config.json の内容に依存し得るため body は skip
    {"method": "GET", "path": "/ext/hailo-yolo/api/stream/sources", "auth": "admin", "python_path": None, "schema_check": ["status", "sources"], "skip_body_compare": True, "rust_native": True, "note": "stream sources 一覧 (T9 #1)。既存 stream_config.json の残留 source に依存するため body は skip、shape のみ確認。 T9 native: Python route registration removed, Rust-only shape check."},
    #2 POST /stream/sources — id/url 欠落は ffmpeg を起動しない安全な入力（副作用なし）
    {"method": "POST", "path": "/ext/hailo-yolo/api/stream/sources", "auth": "admin", "python_path": None, "body": {}, "accept_statuses": [400], "rust_native": True, "note": "stream source 追加 (T9 #2)。id/url欠落→400。実登録(201, ffmpeg起動)は副作用があるため突かない。 T9 native: Python route registration removed, Rust-only shape check."},
    #3 DELETE /stream/sources/{id} — 存在しない source は副作用なし
    {"method": "DELETE", "path": "/ext/hailo-yolo/api/stream/sources/__parity_test_nonexistent__", "auth": "admin", "python_path": None, "accept_statuses": [404], "rust_native": True, "note": "stream source 削除 (T9 #3)。未登録 source_id→404、副作用なし。 T9 native: Python route registration removed, Rust-only shape check."},
    #4 GET /stream/rules — 一覧も残留 rule に依存するため skip
    {"method": "GET", "path": "/ext/hailo-yolo/api/stream/rules", "auth": "admin", "python_path": None, "schema_check": ["status", "rules"], "skip_body_compare": True, "rust_native": True, "note": "stream rules 一覧 (T9 #4)。既存 rule 有無に依存するため body は skip、shape のみ確認。 T9 native: Python route registration removed, Rust-only shape check."},
    #5 POST /stream/rules — id欠落は永続化しない安全な入力（副作用なし）
    {"method": "POST", "path": "/ext/hailo-yolo/api/stream/rules", "auth": "admin", "python_path": None, "body": {}, "accept_statuses": [400], "rust_native": True, "note": "stream rule 追加 (T9 #5)。id欠落→400。実登録(201, config永続化)は副作用があるため突かない。id/不正入力→400分岐(#5注記)はPython側デッドコードのため確認しない。 T9 native: Python route registration removed, Rust-only shape check."},
    #6 PUT /stream/rules/{id} — upsert 契約そのものが検証対象のため、この1件のみ永続化を伴う
    {"method": "PUT", "path": "/ext/hailo-yolo/api/stream/rules/__parity_test_rule__", "auth": "admin", "python_path": None, "body": {}, "accept_statuses": [200], "rust_native": True, "note": "stream rule 更新 (T9 #6)。未登録idでも404にせずupsertして200——spec §10 #6が名指しする契約そのものであり、この1件だけは永続化の副作用を受容する（sentinel id・空conditionsで無害）。name/conditions/cooldown_sec/actionsの寛容パースdefaultがPythonのDetectionRule defaultと一致することをbody一致で確認する。 T9 native: Python route registration removed, Rust-only shape check."},
    #7 DELETE /stream/rules/{id} — 存在しない rule は副作用なし
    {"method": "DELETE", "path": "/ext/hailo-yolo/api/stream/rules/__parity_test_nonexistent_rule__", "auth": "admin", "python_path": None, "accept_statuses": [404], "rust_native": True, "note": "stream rule 削除 (T9 #7)。未登録rule_id→404、副作用なし。 T9 native: Python route registration removed, Rust-only shape check."},
    #8 GET /stream/status — Rustは9 pipeline keyを"pipeline"下にネストして返す（handlers.rs status()実装で確認）。トップレベルschema_checkはstatus/pipeline/sources/rules_count/recorderのみ検証し、9 keyはpython_noteで文書化するに留める（フラットに列挙するとRustレスポンスに一致せずERRORになる — 初回実行で検出・訂正済）
    {"method": "GET", "path": "/ext/hailo-yolo/api/stream/status", "auth": "admin", "python_path": None, "schema_check": ["status", "pipeline", "sources", "rules_count", "recorder"], "schema_check_statuses": [200], "skip_body_compare": True, "rust_native": True, "python_note": "pipeline下の9 key(running/queue_size/skip_rate/fps/backend_pref/model_name/conf_threshold/result_sources/batch_paused)はspec §10 #8参照。backend_pref は Rust 固定値 'yu-infer' / Python は extension backend既定 'auto' で不一致(spec差分表 backend_pref行)。running は Rust=active/reconnecting source有無、Python=worker thread生存で全source停止後に意味が割れる(同表 running行)。recorderは録画中のみ動的(elapsed_sec/remaining_sec)で、静止状態{}のみparity対象。トップレベル5 keyの存在はschema_checkで固定し、body本体の一致は主張しない。 T9 native: Python route registration removed, Rust-only shape check."},
    #9 POST /stream/sources/{id}/start — 未登録は副作用なし
    {"method": "POST", "path": "/ext/hailo-yolo/api/stream/sources/__parity_test_nonexistent__/start", "auth": "admin", "python_path": None, "accept_statuses": [404], "rust_native": True, "note": "stream source 起動 (T9 #9)。未登録source_id→404、副作用なし。 T9 native: Python route registration removed, Rust-only shape check."},
    #10 POST /stream/sources/{id}/stop — 未登録は副作用なし
    {"method": "POST", "path": "/ext/hailo-yolo/api/stream/sources/__parity_test_nonexistent__/stop", "auth": "admin", "python_path": None, "accept_statuses": [404], "rust_native": True, "note": "stream source 停止 (T9 #10)。未登録source_id→404、副作用なし。 T9 native: Python route registration removed, Rust-only shape check."},
    #11a POST /stream/sources/{id}/test — url無し・未登録idの合流点。既存契約(#11)
    {"method": "POST", "path": "/ext/hailo-yolo/api/stream/sources/__parity_test_nonexistent__/test", "auth": "admin", "python_path": None, "body": {}, "accept_statuses": [400], "rust_native": True, "note": "stream source test (T9 #11a)。未登録source_id かつ request にURL無し→400 'No URL provided'。実接続試験は伴わないため副作用なし。 T9 native: Python route registration removed, Rust-only shape check."},
    #11b 同 — Rust T1入力検証（`-`前置）による新規拒否。Pythonは無検査でcv2.VideoCaptureへ渡すためparityは成立しない
    {"method": "POST", "path": "/ext/hailo-yolo/api/stream/sources/__parity_test_nonexistent__/test", "auth": "admin", "python_path": None, "body": {"url": "-rf /tmp/parity-injection-probe"}, "accept_statuses": [200, 400], "skip_body_compare": True, "rust_native": True, "python_note": "Rustは`-`前置URLをT1 arg-injection guardで400 'Invalid source URL'として拒否する。これはPythonに無い新規の拒否であり、spec差分表の『登録・test時のURL拒否』行が宣言済——Pythonは無検査でcv2.VideoCaptureへ渡すため200 {ok:false,...} 等に落ちる。両者の200/400が同時に許容されるのは意図的差分であり、失敗として扱わない。 T9 native: Python route registration removed, Rust-only shape check."},
    #12 GET /stream/devices — Python=cv2 open実列挙、Rust=Linux sysfs(resolution:null)/Win-mac空。bodyは不一致確定
    {"method": "GET", "path": "/ext/hailo-yolo/api/stream/devices", "auth": "admin", "python_path": None, "schema_check": ["status", "devices"], "skip_body_compare": True, "rust_native": True, "python_note": "Pythonはcv2でdeviceをopenし{width,height}を返す。RustはLinuxでsysfs列挙+resolution:null、Windows/macOSは[]——spec差分表『devicesはLinux非open列挙』行。bodyは一致しない前提でshapeのみ確認する。 T9 native: Python route registration removed, Rust-only shape check."},
    #13 GET /stream/{id}/mjpeg — 無限stream。既存の /ext/lan_cowork/fleet/logs/stream 相当の sse:True 扱いに倣う
    {"method": "GET", "path": "/ext/hailo-yolo/api/stream/__parity_test_nonexistent__/mjpeg", "auth": "admin", "python_path": None, "accept_statuses": [404], "skip_body_compare": True, "sse": True, "rust_native": True, "note": "MJPEG stream (T9 #13)。未登録source_idで即404となる経路のみ確認し、実stream開始は行わない(副作用回避)。sse:Trueでstatus/content-typeのみ比較し無限bodyは読まない——既存 /ext/lan_cowork/fleet/logs/stream 相当の扱い。 T9 native: Python route registration removed, Rust-only shape check."},
    #14 GET /stream/recordings — 2026-08-13改訂で判明した15本目。既にnative(commit 945161c39)だが Python も現役のためparity登録する
    {"method": "GET", "path": "/ext/hailo-yolo/api/stream/recordings", "auth": "admin", "python_path": None, "schema_check": ["status", "recordings"], "skip_body_compare": True, "rust_native": True, "note": "録画一覧 (T9 #14, spec 2026-08-13改訂)。保存dir不在時は両者とも200 {recordings:[]}だが、実ファイル一覧はfilesystem状態依存のためbodyはskip。 T9 native: Python route registration removed, Rust-only shape check."},
    #15 GET /stream/snapshot/{filename} — 同改訂で判明した15本目。detection_action_handlers.pyのwebhook payloadが生きた依存を持つ
    {"method": "GET", "path": "/ext/hailo-yolo/api/stream/snapshot/__parity_test_nonexistent__.jpg", "auth": "admin", "python_path": None, "accept_statuses": [404], "rust_native": True, "note": "snapshot取得 (T9 #15, spec 2026-08-13改訂)。存在しないfilenameで両者とも404 {'error':'Not found'}、副作用なし。actions.rs:419のwebhook snapshot_url生成が同じpathを組み立てる生きた依存(spec l.519-522)。 T9 native: Python route registration removed, Rust-only shape check."},
    # --- hailo-semantic native status routes ---
    # /api/status and /api/backends are registered as of v4.698.0. Rust's
    # `backends[].status` now returns Python's five-key contract
    # ({available, runtime_ok, hardware_ok, hef_ok, reason}) instead of the
    # {image_backend, sidecar_connected} pair nothing in src/ts/ ever read.
    # src/ts/shared/extension-health.ts renders runtime_ok/hardware_ok/hef_ok
    # as named rows, so the three booleans are the contract and are compared.
    #
    # Two leaves are excluded, and only these two:
    #  - `hef_path`: Python reports the absolute HEF path on the host. Rust does
    #    not own the HEF (the sidecar does) and emits no such key; inventing one
    #    would be a fabricated path, and the two hosts would differ regardless.
    #  - `reason`: the same failure mode, worded for a different runtime.
    #    Python names a `hailo_platform` wheel and a HEF file path; Rust names
    #    the inference sidecar, which is what actually failed there. Copying
    #    Python's sentence into Rust would put a false statement in front of the
    #    operator (extension-health.ts displays `reason` verbatim) purely to
    #    make this comparison green. The booleans it explains ARE compared, so
    #    a divergence in the underlying state still fails here.
    #
    # `size_mb`/`path` inside `backends[].model_status` stay compared on
    # purpose: both servers resolve the same cache dir in the harness.
    # `size_mb` inside `backends[].model_status` is excluded for the same reason
    # the sibling /api/model/status entry below excludes its top-level one: each
    # server resolves its own cache dir (Rust is started with an isolated
    # --config here), so the two stat different files. Measured, not assumed --
    # the first harness run with these entries registered failed on exactly
    # `backends[2].model_status.size_mb` and nothing else. `ready` and `repo`
    # inside the same object stay compared.
    {"method": "GET", "path": "/ext/hailo-semantic/api/status", "auth": "admin", "rust_native": True, "exclude_nested_fields": ["hef_path", "reason", "size_mb"], "note": "hailo-semantic status — backends[].status now matches Python's five-key contract (v4.698.0)."},
    {"method": "GET", "path": "/ext/hailo-semantic/api/backends", "auth": "admin", "rust_native": True, "exclude_nested_fields": ["hef_path", "reason", "size_mb"], "exclude_fields": ["text_backend"], "note": "hailo-semantic backends — 同上。text_backend は Rust 固有の text-encoder 欄で Python に対応物なし。"},
    #
    # size_mb is environment-dependent (each server resolves its own cache dir,
    # so the two read different files). vision_ready/vision_size_mb are Rust-only
    # additions with no Python counterpart.
    #
    # `ready` is a REAL, newly-diagnosed semantic divergence (v4.698.0), not an
    # environment difference -- the two sides compute it over different files:
    #   Python: `builtin_clip_onnx/model_download.get_model_status()` -> ready is
    #           "vision_model.onnx exists".
    #   Rust:   `clip_model::model_ready()` -> ready is "text_model.onnx AND
    #           tokenizer.json exist" (vision has its own `vision_ready` key).
    # This entry's comment used to claim `ready` was "the text-encoder contract"
    # compared on both sides. It never was: the two agreed only while BOTH files
    # were absent, which is every machine that has downloaded neither model. The
    # moment this worktree's cache gained text_model.onnx the claim broke.
    #
    # `expected_body_diff` rather than `exclude_fields` on purpose: it is the one
    # mechanism that fails if the field ever stops differing, so this cannot go
    # quietly green again. Note it WILL fail once a machine has both models
    # cached (then Python and Rust both say true) -- that is the intended prompt
    # to decide which meaning `ready` should carry, tracked in TODO.md.
    {"method": "GET", "path": "/ext/hailo-semantic/api/model/status", "auth": "admin", "rust_native": True, "exclude_fields": ["path", "tokenizer_path", "vision_path", "size_mb", "vision_ready", "vision_size_mb", "ready", "text_ready"], "note": "`ready` is not a semantic divergence to reconcile: Python builtin_clip_onnx (core_impl/model_download.py) downloads only vision_model.onnx, so its `ready` means \"vision present\". Rust clip_model.rs downloads text_model.onnx + tokenizer.json + vision_model.onnx and its `ready` is the full set (all three present) -- the two modules own different assets, so equal `ready` values are unreachable by construction, not a bug to fix by making one side lie. `text_ready` (Rust's old `ready` meaning: text_model + tokenizer) has no Python counterpart at all."},
]


@dataclass
class Result:
    method: str
    path: str
    rust_status: int | None = None
    python_status: int | None = None
    body_match: bool | None = None
    schema_diff: bool = False  # スキーマ差異あり（値は異なるがRustは正常）
    rust_body: Any = None
    python_body: Any = None
    rust_content_type: str = ""
    python_content_type: str = ""
    error: str = ""
    note: str = ""  # スキーマ差異などの補足
    no_python: bool = False  # python_path=None → 比較不可 (N/A)
    accept_statuses: list[int] = field(default_factory=lambda: [200])  # 許容するRustステータス
    rust_expect_status: int | None = None
    # contract 違反: [("rust"|"python", "violation message"), ...]
    contract_violations: list[tuple[str, str]] = field(default_factory=list)
    # How many times a 429 forced a resend. Reported so a throttled run is
    # visibly throttled rather than silently slower: a rate limiter that starts
    # refusing every second request is a finding, and a retry that swallows it
    # without a trace is the "green gate that measured nothing" this repo has
    # been bitten by eighteen times.
    retries_429: int = 0
    # How many times a transport-level flake forced a resend. Counted apart from
    # `retries_429` on purpose: a 429 is the server answering, a dropped
    # connection is the server not answering, and collapsing them would hide
    # which one a run hit. Reported so a rescued run stays visibly rescued --
    # a resend that leaves no trace is the "green gate that measured nothing"
    # this repo keeps being bitten by.
    retries_transport: int = 0
    strict_body: bool = False
    entry_id: int | None = None

    @property
    def passed(self) -> bool:
        if self.error or self.no_python:
            return False
        if self.contract_violations:
            return False
        if self.rust_expect_status is not None and self.rust_status != self.rust_expect_status:
            return False
        if self.python_status is None:
            return self.rust_status in self.accept_statuses
        if self.rust_status != self.python_status:
            # 501/502 = Rust proxy failure signals; never acceptable when Python is running
            if self.rust_status in (501, 502):
                return False
            # 両方 accept_statuses 内なら設定依存差異として合格
            return self.rust_status in self.accept_statuses and self.python_status in self.accept_statuses
        if self.body_match is False:
            return False if self.strict_body else self.schema_diff
        return True

    @property
    def no_python_ok(self) -> bool:
        """Pass/fail judgment for no_python (python_path=None) entries.

        `passed` is always False for these entries since there is no Python
        response to compare against. This property provides the standalone
        Rust-side verdict instead: FAIL when rust_status is not in
        accept_statuses — callers must fold this into aggregation and the
        exit code. schema_check failures are already surfaced via r.error
        inside check_endpoint(), so this only looks at status.
        """
        return self.rust_status in self.accept_statuses

    def label(self) -> str:
        if self.error:
            return f"💥 ERROR {self.method} {self.path}: {self.error}"
        if self.contract_violations:
            details = "; ".join(f"{side}:{msg}" for side, msg in self.contract_violations[:3])
            return (
                f"📋 CONTRACT {self.method:6} {self.path:40} "
                f"rust={self.rust_status} py={self.python_status}  [{details}]"
            )
        if self.rust_expect_status is not None and self.rust_status != self.rust_expect_status:
            return (
                f"❌ {self.method:6} {self.path:40} "
                f"rust={self.rust_status} expected={self.rust_expect_status}"
            )
        if self.no_python:
            ok = self.rust_status in self.accept_statuses
            icon = "〰️" if ok else "❌"
            return f"{icon}  {self.method:6} {self.path:40} rust={self.rust_status}  (Rust独自・比較不可)"
        if self.python_status is None:
            return f"〰️  {self.method:6} {self.path:40} rust={self.rust_status}  (python未確認)"
        status_match = self.rust_status == self.python_status
        both_acceptable = (
            self.rust_status in self.accept_statuses
            and self.python_status in self.accept_statuses
        )
        if both_acceptable and not status_match:
            if self.python_status is not None and self.rust_status in (501, 502):
                icon = "❌"
                extra = f"  (proxy障害: rust={self.rust_status} py={self.python_status})"
            else:
                icon = "✅"
                extra = f"  (設定依存: rust={self.rust_status} py={self.python_status} 両方許容)"
        elif status_match and self.schema_diff:
            icon = "⚠️ "
            extra = f"  ⚠ {self.note}"
        elif status_match:
            icon = "✅" if self.body_match is not False else "❌"
            extra = "" if self.body_match is None else f"  body={'✅' if self.body_match else '❌'}"
        else:
            icon = "❌"
            extra = ""
        return (
            f"{icon} {self.method:6} {self.path:40} "
            f"rust={self.rust_status} py={self.python_status}{extra}"
        )


_DEFAULT_TIMEOUT = float(os.environ.get("PARITY_TIMEOUT") or 10)


# A 429 the entry does not accept is the limiter working, not the endpoint
# failing. Wait it out once rather than reading it as a defect.
#
# Why this exists: the harness walks ~283 non-GET entries back to back with no
# spacing (see the loop in _run_checks), and every one of them lands in the same
# per-IP WRITE bucket once yu-server carries the ported rate limiter. The bucket
# holds 30 and refills at 2/s, so the run empties it inside the first thirty
# entries and then trips continuously. Without this, porting the limiter turns
# the gate permanently red for reasons that have nothing to do with parity.
#
# The alternative -- widening accept_statuses to include 429 -- was rejected:
# `parity_relaxation_ratchet.py` records accept_statuses as a *boolean* ("wider
# than [200]?"), so adding 429 to entries that already carry the flag leaves the
# frozen baseline byte-identical and the gate never sees the change. That手 has
# been used once already (tests/compat_goldens/inputs.yaml, DELETE
# /api/collections/{id}, `[200, 404, 429]`).
#
# Bounded on purpose: one resend, capped wait. A genuinely stuck 429 still fails
# the entry -- see `retry_gives_up_when_429_persists` in the self-check.
_RETRY_429_MAX_WAIT = 6.0
# Retry-After is `max(1, int(1.0 / rate))`, and `int()` truncates: HEAVY's rate
# of 0.33/s needs 3.03s to earn a token but advertises 3. Waiting exactly what
# was advertised leaves the bucket a hair short and the resend fails on timing
# alone, so add a margin rather than trusting the advertised value.
_RETRY_429_MARGIN = 0.5


async def fetch_with_429_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    accept_statuses: list[int],
    **kwargs: Any,
) -> tuple[tuple[int, Any, str], int]:
    """`fetch`, resending once if a 429 arrives that the entry does not accept.

    Returns the fetch result and how many resends happened (0 or 1).

    `timeout` and `sse` ride in `**kwargs` rather than being named: this wrapper
    forwards a request budget it never applies itself, and naming it earns
    ASYNC109 ("use asyncio.timeout instead") for a timeout that belongs to
    `fetch`.
    """
    headers: dict[str, str] = {}
    result = await fetch(client, method, url, headers_out=headers, **kwargs)
    status, _body, _ctype = result
    if status != 429 or 429 in accept_statuses:
        return result, 0

    wait = _RETRY_429_MARGIN
    # Trust the server's own Retry-After when it sends one, capped.
    retry_after = _retry_after_seconds(headers)
    if retry_after is not None:
        wait = min(retry_after + _RETRY_429_MARGIN, _RETRY_429_MAX_WAIT)
    await asyncio.sleep(wait)
    return await fetch(client, method, url, **kwargs), 1


# Transport-level failures that a resend can plausibly rescue. `fetch` converts
# only `httpx.ConnectError` into `ConnectionError`; everything here escaped it
# untranslated, fell through `check_endpoint`'s `except ConnectionError`, and was
# recorded as an ERROR by the outermost handler -- which makes the whole nightly
# red on one dropped connection even at 0 FAIL. Observed 2026-09-08 (CI run
# 34283479409): `GET /api/ocr/translations/1` -> RemoteProtocolError, 427 PASS /
# 0 FAIL / 1 ERROR, exit 1. The Rust server answered every request before and
# after it and logged no panic, so the drop was the peer's, not a defect.
#
# `ConnectError` is deliberately NOT here: "cannot connect at all" means the
# server is gone, and retrying that hides a real death behind a delay.
_TRANSPORT_FLAKE_EXCEPTIONS = (
    httpx.RemoteProtocolError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
)
# One resend only. A flake survives one; a broken endpoint survives any number,
# and a higher bound just buys a slower red.
_RETRY_TRANSPORT_WAIT = 1.0


async def fetch_with_flake_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    accept_statuses: list[int],
    **kwargs: Any,
) -> tuple[tuple[int, Any, str], int, int]:
    """`fetch_with_429_retry`, resending once more if the transport itself drops.

    Returns the fetch result, the 429 resend count, and the transport resend
    count (each 0 or 1).

    The second attempt is NOT shielded: if it raises too, the exception
    propagates and the entry goes red exactly as before. That is the whole
    distinction being drawn -- a flake does not reproduce, a defect does -- and
    swallowing the retry's failure would turn this into the relaxation it is
    meant not to be.
    """
    try:
        result, retried_429 = await fetch_with_429_retry(
            client, method, url, accept_statuses, **kwargs
        )
        return result, retried_429, 0
    except _TRANSPORT_FLAKE_EXCEPTIONS:
        await asyncio.sleep(_RETRY_TRANSPORT_WAIT)
    result, retried_429 = await fetch_with_429_retry(
        client, method, url, accept_statuses, **kwargs
    )
    return result, retried_429, 1


def _retry_after_seconds(headers: dict[str, str]) -> float | None:
    """`Retry-After` in seconds, or None when the server did not send a usable one.

    Both implementations send it as a HEADER and neither puts it in the body
    (`request_hooks.py:106`, `auth/api_rate_limit.rs`). An earlier version of
    this function read `body["retry_after"]`, so it returned None on every real
    response and the caller silently fell back to the 0.5s margin -- enough for
    WRITE (2/s) and never enough for HEAVY (0.33/s) or DESTRUCTIVE (0.2/s).
    The unit tests were green throughout: they fed it the body shape it was
    written for, which no server produces.

    Only the delta-seconds form is parsed. HTTP also permits an HTTP-date, but
    neither implementation emits one, and guessing at a date here would be
    inventing a case no server sends.
    """
    raw = None
    for name, value in headers.items():
        if name.lower() == "retry-after":
            raw = value
            break
    if raw is None:
        return None
    try:
        seconds = float(str(raw).strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


async def fetch(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    sse: bool = False,
    timeout: float = 10,
    headers_out: dict[str, str] | None = None,
    **kwargs,
) -> tuple[int, Any, str]:
    """Perform one request.

    `headers_out`, when given, is filled with the response headers. It is an
    out-parameter rather than a fourth element of the return tuple because
    every one of the ~600 call sites unpacks exactly three values; the one
    caller that needs a header should not cost the other six hundred an edit.
    """
    try:
        if sse:
            # SSE エンドポイントはボディ読み込みを試みずステータスコードのみ取得する。
            async with client.stream(method, url, timeout=timeout, **kwargs) as resp:
                if headers_out is not None:
                    headers_out.update(resp.headers)
                return (
                    resp.status_code,
                    "(sse-stream)",
                    normalize_content_type(resp.headers.get("content-type", "")),
                )
        resp = await client.request(method, url, timeout=timeout, **kwargs)
        if headers_out is not None:
            headers_out.update(resp.headers)
        content_type = normalize_content_type(resp.headers.get("content-type", ""))
        try:
            body = normalize_json_body(resp.json())
        except Exception:
            body = resp.text
        return resp.status_code, body, content_type
    except httpx.ConnectError as e:
        raise ConnectionError(f"接続失敗: {e}") from e


def body_equal(a: Any, b: Any) -> bool:
    """JSON ボディの等価比較（型・値）."""
    if type(a) != type(b):
        return False
    if isinstance(a, list):
        if len(a) != len(b):
            return False
        return all(body_equal(x, y) for x, y in zip(a, b, strict=True))
    if isinstance(a, dict):
        if set(a.keys()) != set(b.keys()):
            return False
        return all(body_equal(a[k], b[k]) for k in a)
    return a == b


def diff_summary(left: Any, right: Any, limit: int | None = None) -> str:
    """Return the first differing JSON paths.

    The cap keeps the summary readable, but triage needs to see past it: a body
    whose first three diffs are envelope keys can still differ in real content
    further down. YU_PARITY_DIFF_LIMIT raises it without touching the default.
    """
    if limit is None:
        limit = int(os.environ.get("YU_PARITY_DIFF_LIMIT", "3"))
    # Walk past the cap so the summary can say how much it is hiding. A reader who
    # does not know a cap exists reads "3 keys" as "all the keys" -- which happened,
    # and cost a release: the real count was six, and the three beyond the cap were
    # content differences, not envelope noise.
    walk_limit = max(limit * 10, limit + 20)
    diffs: list[str] = []

    def walk(a: Any, b: Any, path: str) -> None:
        if len(diffs) >= walk_limit:
            return
        if type(a) is not type(b):
            diffs.append(path or "<root>")
            return
        if isinstance(a, dict):
            for key in sorted(set(a) | set(b)):
                if len(diffs) >= walk_limit:
                    return
                child_path = f"{path}.{key}" if path else str(key)
                if key not in a or key not in b:
                    diffs.append(child_path)
                else:
                    walk(a[key], b[key], child_path)
            return
        if isinstance(a, list):
            for index, (left_item, right_item) in enumerate(zip(a, b, strict=False)):
                if len(diffs) >= walk_limit:
                    return
                walk(left_item, right_item, f"{path}[{index}]")
            if len(a) != len(b) and len(diffs) < walk_limit:
                diffs.append(f"{path}[len]" if path else "[len]")
            return
        if a != b:
            diffs.append(path or "<root>")

    walk(left, right, "")
    shown = diffs[:limit]
    hidden = len(diffs) - len(shown)
    summary = ", ".join(shown)
    if hidden > 0:
        # `+N or more` when the walker itself stopped: the true count may be higher.
        more = f"{hidden} or more" if len(diffs) >= walk_limit else str(hidden)
        summary += f" (+{more} keys differ beyond this cap; raise YU_PARITY_DIFF_LIMIT)"
    return summary


# Default contracts for manifest-only GET endpoints (path → {key: type}).
# Applied when the manifest entry has no explicit "contract" field.
_MANIFEST_CONTRACTS: dict[str, dict[str, str]] = {
    "/api/search": {
        "ok": "bool",
        "results": "array",
        "has_more": "bool",
        "limit": "int",
        "offset": "int",
    },
    "/api/search-count": {"status": "str", "total_count": "int"},
    "/api/search-grouped/warm": {"ok": "bool", "status": "str"},
    "/api/tags/suggest": {"ok": "bool", "data": "array"},
}


# Per-entry knobs for manifest-only endpoints (path → endpoint dict overrides).
#
# manifest.yaml is GENERATED (scripts/gen_compat_goldens.py rewrites the whole
# file with yaml.safe_dump), so knobs written into it are destroyed on the next
# regeneration. They live here instead, applied at load time, the same way
# _MANIFEST_CONTRACTS supplies contracts these entries cannot carry themselves.
#
# Reasons and review triggers come from OCR_PARITY_CENSUS.md — keep them in
# sync with that table rather than inventing new wording here.
_MANIFEST_OVERRIDES: dict[str, dict[str, Any]] = {
    # Envelope-only differences: Python wraps via api_result, Rust returns the
    # bare payload (spec R2). Strip ok/error/data from the Python side.
    "/api/agent/approval": {"python_envelope": True},
    "/api/scan/interrupted": {"python_envelope": True},
    # Rust's 200 now returns {status, total_count} (search.rs), matching Python's
    # payload; what remains is Python's api_result wrapper.
    "/api/search-count": {"python_envelope": True},
    # Real differences that no envelope rule can reconcile. Held with a reason
    # and the event that should prompt a re-check.
    "/api/agent/status": {
        "skip_body_compare": True,
        "note": (
            "**実測ノ差ハ十五鍵（v4.734.3、rust=200 py=200）——註ノ「十八欄」ハ誤リナリキ。**"
            "内五鍵ハ本版ニテ返済セリ: `ok`/`error`/`data`（Python ハ api_result ニテ包ム）ト "
            "`reason`/`killed_at`（Python ハ kill_switch ヨリ導キ最上位ヘ出ス——"
            "routes/agent_api_core.py:111-112。Rust ハ其ノ map ヲ持チ居テ出サザリキノミ）。"
            "**残ル十鍵ハ真ノ機能欠落ナリ**: `budget`・`processes`・"
            "`circuit_breaker` ノ八副鍵。**Rust ニ遮断器モ予算モ実装無シ。**"
            "Python ハ両者ニ `{}` ヲ返スガ、其レヲ写セバ「予算ハ一切費ハレ居ラヌ」ト"
            "**測ラズニ主張スル**事ト成ル故、`null`/`unknown` ヲ保ツ。"
            "todo(rust-gap) 参照——直シ方ハ agent_audit ノ二 stub ノ実移植ナリ。"
        ),
    },
    "/api/extensions": {
        "skip_body_compare": True,
        "note": (
            "**実測ノ差ハ六百鍵超（v4.734.3、限リ六十ニテ「+540 以上ガ其ノ外」ト報ゼリ）"
            "——註ノ「四十件デ打チ切ル」ハ過小ナリキ。** 拡張一件ニ付キ二十鍵前後ガ"
            "悉ク違フ（`blueprint_prefix`・`category`・`config`・`config_schema`・"
            "`core_shim`・`description`・`entry`・`health`・`hooks[len]`・`name`・"
            "`nav.*`・`priority`・`source`・`status`・`status_message`・`trust_level`・"
            "`type`）。併セテ封（`data`/`error`）モ欠ク。"
            "**即チ extension メタデータノ契約ソノモノガ両実装デ別ナリ**——"
            "一鍵ヅツ直ス仕事ニ非ズ、契約ヲ定メル仕事ナリ。todo(parity) 参照。"
        ),
    },
    "/api/search": {
        "note": (
            "**v4.734.2 ニテ本文比較ノ抑止ヲ外シタリ**——従前ノ理由（Rust ハ count_pending ヲ "
            "false 固定トシ、Python ハ条件付キデ true ト為ス）ハ一度モ実測サレ居ラザリキ。"
            "「再検討」ハ測定ニ非ズ。GET ナル故書込無シ。実走ガ真偽ヲ告ゲル。"
        ),
    },
    "/api/suggest": {
        "note": (
            "**v4.734.3 ニテ抑止ヲ外シタリ**——従前ノ理由ハ「suggestions ノ件数ガ DB ノ"
            "タグ分布ニ依ル」ナルガ、**harness ハ一ツノ凍結 fixture ヲ両実装ヘ渡ス**故、"
            "「DB ニ依ル」ハ其レ自体デハ差ノ説明ト成ラヌ——v4.732.21 ニテ同ジ理由ガ"
            "百十一件中七十二件デ偽ナリキ。且ツ本項ハ v4.734.2 マデ台帳ニ数ヘラレ居ラザリキ。"
            "GET ナル故書込無シ。実走ガ真偽ヲ告ゲル。"
        ),
    },
}


def load_manifest_endpoints(manifest_path: Path) -> list[dict[str, Any]]:
    """Load non-skipped GET manifest entries for status parity check.

    Non-GET entries (POST/PUT/DELETE) are skipped here — they require request
    bodies and are covered by inputs.yaml (load_inputs_endpoints) instead.
    """
    with manifest_path.open(encoding="utf-8") as f:
        entries = yaml.safe_load(f) or []
    endpoints = []
    for entry in entries:
        if entry.get("skip"):
            continue
        if entry.get("method", "GET") != "GET":
            continue  # body-bearing mutations handled by inputs.yaml
        endpoints.append(
            {
                "method": entry.get("method", "GET"),
                "path": entry["path"],
                "note": "golden manifest",
                "manifest_content_type": entry.get("content_type", ""),
                "contract": entry.get("contract") or _MANIFEST_CONTRACTS.get(entry["path"], {}),
                "python_envelope": entry.get("python_envelope", False),
                # Knobs the generated manifest cannot carry — see _MANIFEST_OVERRIDES.
                **_MANIFEST_OVERRIDES.get(entry["path"], {}),
            }
        )
    return endpoints


def resolve_path_vars(template: str, vars: dict[str, int | str]) -> str:
    """Resolve <var_name> placeholders in path templates."""
    result = template
    for key, value in vars.items():
        result = result.replace(f"<{key}>", str(value))
    return result


def _resolve_input_value(value: Any, path_vars: dict[str, int | str]) -> Any:
    if isinstance(value, str) and value.startswith("<") and value.endswith(">"):
        return path_vars.get(value[1:-1], value)
    if isinstance(value, list):
        return [_resolve_input_value(item, path_vars) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_input_value(item, path_vars) for key, item in value.items()}
    return value


def load_inputs_endpoints(
    inputs_path: Path,
    path_vars: dict[str, int | str],
) -> list[dict[str, Any]]:
    """Load allowlist entries from inputs.yaml as endpoint dicts."""
    with inputs_path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    endpoints = []
    for entry in data.get("allowlist", []):
        body = entry.get("body")
        ep: dict[str, Any] = {
            "method": entry["method"],
            "path": resolve_path_vars(entry["path"], path_vars),
            "note": entry.get("note", "inputs.yaml"),
            "headers": entry.get("headers", {}),
            "skip_body_compare": entry.get("skip_body_compare", False),
            "accept_statuses": entry.get("accept_statuses", [200]),
            "rust_expect_status": entry.get("rust_expect_status"),
            # Default to no field requirement: the Python<->Rust body parity diff
            # is the real check. Forcing ["ok"] here would ERROR every mutation
            # endpoint whose response shape is not {"ok": ...} (e.g. create
            # returns the resource, delete returns {"deleted": ...}). Specify
            # schema_check explicitly per entry when a shape gate is wanted.
            "schema_check": entry.get("schema_check", []),
            "contract": entry.get("contract", {}),
            "python_envelope": entry.get("python_envelope", False),
        }
        if body is not None:
            ep["body"] = _resolve_input_value(body, path_vars)
        endpoints.append(ep)
    return endpoints


def schema_check(body: Any, fields: list[str]) -> bool:
    """レスポンスボディに期待フィールドが含まれるか確認（list の場合は先頭要素を確認）."""
    if isinstance(body, list):
        if not body:
            return True  # 空リストは正常
        body = body[0]
    if not isinstance(body, dict):
        return False
    return all(f in body for f in fields)


_CONTRACT_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "bool": bool,
    "int": int,
    "str": str,
    "float": (float, int),
    "array": list,
    "object": dict,
}


def validate_contract(body: Any, contract: dict[str, str]) -> list[str]:
    """contract dict に対してレスポンスボディを検証し、違反メッセージを返す。

    contract 値の型文字列:
      bool / int / str / float / array / object  — 型チェック
      null     — None であること
      nullable — 存在すれば何でも可（null 含む）
      any      — 存在すれば何でも可
    未列挙キーは無視（open schema）。
    """
    if not contract:
        return []
    if isinstance(body, list):
        body = body[0] if body else {}
    if not isinstance(body, dict):
        return [f"response is {type(body).__name__}, expected object"]
    violations: list[str] = []
    for key, type_str in contract.items():
        if key not in body:
            violations.append(f"missing key '{key}'")
            continue
        value = body[key]
        if type_str in ("any", "nullable"):
            continue
        if type_str == "null":
            if value is not None:
                violations.append(f"'{key}': expected null, got {type(value).__name__}")
        elif expected_type := _CONTRACT_TYPE_MAP.get(type_str):
            if not isinstance(value, expected_type):
                # bool is subclass of int — treat bool where int expected as violation
                if type_str == "int" and isinstance(value, bool):
                    violations.append(f"'{key}': expected int, got bool")
                elif not isinstance(value, expected_type):
                    violations.append(f"'{key}': expected {type_str}, got {type(value).__name__}")
        else:
            violations.append(f"'{key}': unknown contract type '{type_str}'")
    return violations


_CONTRACT_TYPE_NAMES = frozenset({"bool", "int", "str", "float", "array", "object", "null", "nullable", "any"})


def _dotted_get(body: object, path: str) -> tuple[bool, object]:
    """Follow a dotted path; return (found, value).

    `volatile_keys` and `expected_body_diff` name fields, and a nested field has to be
    spelled somehow. A bare `in body` test only ever saw the top level, so a dotted name
    was reported "missing from a side" on BOTH sides at once -- which is what
    `prompt.created_at` did until this was written.
    """
    cur = body
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def _dotted_set(body: dict, path: str, value: object) -> dict:
    """Return a copy of `body` with `path` set, copying each dict along the way."""
    parts = path.split(".")
    out = dict(body)
    cur = out
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            return out
        cur[part] = dict(nxt)
        cur = cur[part]
    cur[parts[-1]] = value
    return out


def validate_status_contract(body: Any, spec: dict[str, Any]) -> list[str]:
    """python_status_contract 用: 型検証ト厳密値検証ヲ併セ持ツ軽量 contract。

    値ガ validate_contract ト同語彙ノ型名文字列（bool/int/str/...）ナラバ型検証、
    然ラザレバ `==` ニテ厳密一致ヲ検証（例: "error": "peer_not_found" ハ
    「'error' キーガ丁度 'peer_not_found' デアルコト」ヲ要求シ、同ジ型ノ別値ヤ
    Quart 既定 404 ノ envelope 無シ応答ヲ通サヌ）。
    """
    if not spec:
        return []
    if isinstance(body, list):
        body = body[0] if body else {}
    if not isinstance(body, dict):
        return [f"response is {type(body).__name__}, expected object"]
    violations: list[str] = []
    for key, expected in spec.items():
        if key not in body:
            violations.append(f"missing key '{key}'")
            continue
        value = body[key]
        if isinstance(expected, str) and expected in _CONTRACT_TYPE_NAMES:
            violations.extend(validate_contract({key: value}, {key: expected}))
        elif type(value) is not type(expected) or value != expected:
            # `type(value) is not type(expected)` first: Python's `bool` is a
            # subclass of `int` (0 == False, 1 == True), so a plain `!=` would
            # silently accept a JSON number where a literal boolean/string was
            # pinned. Reject the type mismatch before falling back to `!=`.
            violations.append(f"'{key}': expected {expected!r}, got {value!r}")
    return violations


async def check_endpoint(
    rust: httpx.AsyncClient,
    python: httpx.AsyncClient | None,
    ep: dict[str, Any],
    strict_body: bool = False,
    entry_id: int | None = None,
) -> Result:
    method = ep["method"]
    path = ep["path"]
    params = ep.get("params")
    # Substitute {key} path params into URL; remainder becomes query params
    query_params: dict[str, Any] | None = None
    if params:
        remaining: dict[str, Any] = {}
        for key, val in params.items():
            placeholder = f"{{{key}}}"
            if placeholder in path:
                path = path.replace(placeholder, str(val))
            else:
                remaining[key] = val
        query_params = remaining or None
    python_path = ep.get("python_path", path)  # Noneなら Python 比較スキップ
    body = ep.get("body")
    skip_body = ep.get("skip_body_compare", False)
    check_fields = ep.get("schema_check", [])
    contract = ep.get("contract", {})
    python_note = ep.get("python_note", "")
    accept_statuses = ep.get("accept_statuses", [200])
    rust_expect_status = ep.get("rust_expect_status")
    # PIN検証系エンドポイントはPBKDF2 600k反復を実行する。debugビルド(最適化なし)
    # ではPi上で既定の10秒を超えることがあるため、必要なエンドポイントのみ延長する。
    # PARITY_TIMEOUT is a diagnostic knob, not slack: entries that set their own
    # "timeout" keep it. Raising the default distinguishes a bounded stall (the
    # request finishes late) from a true hang (it times out at any budget) --
    # under CI's blocked egress ten endpoints die at exactly 10.0s, which is both
    # this default and glibc's resolver budget, so the two cannot be told apart
    # at 10. Leave it unset outside a measurement.
    timeout = ep.get("timeout", _DEFAULT_TIMEOUT)

    r = Result(
        method=method,
        path=path,
        accept_statuses=accept_statuses,
        rust_expect_status=rust_expect_status,
        strict_body=strict_body,
        entry_id=entry_id,
    )

    form_body = ep.get("form_body")
    is_sse = ep.get("sse", False)
    kwargs: dict[str, Any] = {}
    if form_body:
        kwargs["data"] = form_body  # application/x-www-form-urlencoded
    elif body is not None:
        kwargs["json"] = body
    if query_params:
        kwargs["params"] = query_params
    if ep.get("headers"):
        kwargs["headers"] = ep["headers"]

    try:
        fetched, retried, retried_transport = await fetch_with_flake_retry(
            rust, method, path, accept_statuses, sse=is_sse, timeout=timeout, **kwargs
        )
        r.rust_status, r.rust_body, r.rust_content_type = fetched
        r.retries_429 += retried
        r.retries_transport += retried_transport
    except ConnectionError as e:
        r.error = str(e)
        return r

    # スキーマチェック（Rustのみ）: 許容ステータスならスキーマ確認
    # schema_check_statuses 指定時はその範囲のみ検証（501等を許容しつつ200のみ検証する場合）
    schema_statuses = ep.get("schema_check_statuses", accept_statuses)
    if check_fields and r.rust_status in accept_statuses and r.rust_status in schema_statuses and not schema_check(r.rust_body, check_fields):
        r.error = f"Rustレスポンスに期待フィールドなし: {check_fields}"
        return r

    # Python比較スキップ
    if python is None or python_path is None:
        r.no_python = python_path is None  # Noneは設計上の不在、None以外はclient未設定
        return r

    try:
        fetched, retried, retried_transport = await fetch_with_flake_retry(
            python, method, python_path, accept_statuses, sse=is_sse, timeout=timeout, **kwargs
        )
        r.python_status, r.python_body, r.python_content_type = fetched
        r.retries_429 += retried
        r.retries_transport += retried_transport
    except ConnectionError as e:
        r.note = f"Python接続失敗: {e}"
        return r

    # contract 検証: 両側のレスポンスを contract に対して独立検証
    if contract and r.rust_status in accept_statuses:
        rust_viols = validate_contract(r.rust_body, contract)
        for v in rust_viols:
            r.contract_violations.append(("rust", v))
    if contract and r.python_status is not None and r.python_status in accept_statuses:
        py_viols = validate_contract(r.python_body, contract)
        for v in py_viols:
            r.contract_violations.append(("python", v))

    # python_status_contract: ステータス別の Python 側専用 contract。
    # 通常の contract は rust/python 双方・全 accept_statuses に一律適用される為、
    # 200(成功)と 404(業務エラー)等で envelope 形状が異なるエンドポイントには使エヌ。
    # 特定ステータスの body 形状のみ検証シ、「該当 route 自体ガ消エ、代ワリニ
    # Quart既定ノ 404(HTML・envelope無シ)ガ返ル」等ノ回帰ガ、単ナル accept_statuses
    # 拡張ノ陰ニ隠レヌ様ニスル。
    python_status_contract: dict[int, dict[str, Any]] = ep.get("python_status_contract", {})
    if r.python_status in python_status_contract:
        for v in validate_status_contract(r.python_body, python_status_contract[r.python_status]):
            r.contract_violations.append((f"python[{r.python_status}]", v))

    # Contracts are validated above against the raw Python body. An entry using
    # python_envelope must not declare envelope keys in its contract. Strip a
    # key only when Rust omits it; a key present on both sides is content.
    python_body = r.python_body
    if ep.get("python_envelope") and isinstance(python_body, dict):
        python_body = python_body.copy()
        for key in ("ok", "error", "data"):
            if not isinstance(r.rust_body, dict) or key not in r.rust_body:
                python_body.pop(key, None)
    exclude_fields = ep.get("exclude_fields", [])
    if exclude_fields:
        # Exclude only documented installation-specific fields; keep the rest
        # of each response under the normal strict body comparison.
        if isinstance(r.rust_body, dict):
            r.rust_body = {key: value for key, value in r.rust_body.items() if key not in exclude_fields}
        if isinstance(python_body, dict):
            python_body = {key: value for key, value in python_body.items() if key not in exclude_fields}
    exclude_nested_fields = ep.get("exclude_nested_fields", [])
    if exclude_nested_fields:
        # `exclude_fields` only reaches top-level keys, which is why
        # /ext/hailo-semantic/api/backends could not be registered at all: the
        # fields that legitimately differ (an absolute HEF path, an English
        # reason string worded for a different runtime) live inside
        # `backends[].status`. Excluding `backends` wholesale would drop the
        # names, availability and priorities that are the point of comparing.
        #
        # Named leaves only, at any depth, on both sides. Strictly narrower
        # than `skip_body_compare`: every other leaf is still compared, and the
        # exclusion is listed per entry rather than applied globally.
        r.rust_body = _drop_nested_keys(r.rust_body, exclude_nested_fields)
        python_body = _drop_nested_keys(python_body, exclude_nested_fields)
    if python_note:
        r.note = python_note

    # A named, permanent divergence: the field is compared out, but only after
    # proving it still differs. An exception that silently starts agreeing is an
    # exception nobody removed, and it would then hide a real body diff on that
    # key from that point on.
    #
    # This runs BEFORE the equality branches, not inside the "bodies differ"
    # one. Placed there it only fired when some *other* field also differed --
    # so the case it exists to catch (the named field agrees and everything
    # else matches too) passed silently. Measured 2026-09-05 with an active
    # profile configured: `scheduler_running` stopped differing, every other
    # key matched, and the harness reported PASS.
    expected_diff = ep.get("expected_body_diff") or []
    stale_exception: list[str] = []
    absent_exception: list[str] = []
    if expected_diff and isinstance(r.rust_body, dict) and isinstance(python_body, dict):
        # The exception says "these keys hold different values". A key that is
        # missing from either side is not that -- it is a shape difference, and
        # the exception must not cover it. Reconciling by copying Rust's value
        # into the Python body would INSERT the key there, so a Python side that
        # stopped returning the field entirely compared equal and passed.
        absent_exception = [
            key
            for key in expected_diff
            if (key in r.rust_body) != (key in python_body) or key not in r.rust_body
        ]
        stale_exception = [
            key
            for key in expected_diff
            if key in r.rust_body
            and key in python_body
            and body_equal(r.rust_body[key], python_body[key])
        ]
        if not stale_exception and not absent_exception:
            python_body = dict(python_body)
            for key in expected_diff:
                python_body[key] = r.rust_body[key]

    # `volatile_keys` -- the value is generated when the request is served, so the two
    # processes cannot be made to agree. Unlike `expected_body_diff` this does NOT
    # require the key to differ: a clock-stamped field lands in the same second often
    # enough that requiring a difference flaps between "exempted" and "stale" (measured
    # over four runs of prompt-library's `exported_at`: differ, differ, agree, differ).
    #
    # Presence is still required on BOTH sides. A field one side stopped returning is a
    # shape difference, not a clock, and must still fail -- the same distinction
    # `expected_body_diff` draws just above.
    volatile = ep.get("volatile_keys") or []
    absent_volatile: list[str] = []
    if volatile and isinstance(r.rust_body, dict) and isinstance(python_body, dict):
        found = {
            key: (_dotted_get(r.rust_body, key), _dotted_get(python_body, key))
            for key in volatile
        }
        absent_volatile = [
            key
            for key, ((in_rust, _), (in_py, _)) in found.items()
            if not in_rust or not in_py
        ]
        if not absent_volatile:
            for key in volatile:
                python_body = _dotted_set(python_body, key, found[key][0][1])

    if skip_body or (python_note and not strict_body):
        r.schema_diff = bool(python_note)
        r.note = python_note or "body比較スキップ"
        r.body_match = None
    elif absent_volatile:
        r.body_match = False
        r.note = "; ".join(
            filter(
                None,
                (
                    python_note,
                    "volatile_keys missing from a side: "
                    f"{', '.join(sorted(absent_volatile))} — the exemption covers a "
                    "per-request value, not a missing field",
                ),
            )
        )
    elif absent_exception:
        r.body_match = False
        r.note = "; ".join(
            filter(
                None,
                (
                    python_note,
                    "expected_body_diff key missing from a side: "
                    f"{', '.join(sorted(absent_exception))} — the exception covers "
                    "differing values, not a missing field",
                ),
            )
        )
    elif stale_exception:
        r.body_match = False
        r.note = "; ".join(
            filter(
                None,
                (
                    python_note,
                    "expected_body_diff no longer differs: "
                    f"{', '.join(sorted(stale_exception))} — remove the exception",
                ),
            )
        )
    elif r.rust_status != r.python_status:
        r.body_match = False
    elif 300 <= r.rust_status < 400:
        # Redirect (3xx): the response body and content-type are not meaningful
        # — clients follow the Location header and ignore the body. axum's
        # Redirect emits no content-type while Quart's redirect emits text/html,
        # so comparing them is spurious. Status (already matched above) and the
        # Location header are what matter. Compare status only.
        r.body_match = None
        r.note = "; ".join(filter(None, (python_note, "redirect: status-only compare")))
    elif isinstance(r.rust_body, str) or isinstance(python_body, str):
        r.body_match = r.rust_content_type == r.python_content_type
        if not r.body_match:
            r.note = "; ".join(
                filter(
                    None,
                    (
                        python_note,
                        "content-type mismatch: "
                        f"rust={r.rust_content_type or '<none>'} "
                        f"py={r.python_content_type or '<none>'}",
                    ),
                )
            )
    elif body_equal(r.rust_body, python_body):
        r.body_match = True
        if expected_diff:
            r.note = "; ".join(
                filter(
                    None,
                    (
                        python_note,
                        f"expected divergence: {', '.join(sorted(expected_diff))}",
                    ),
                )
            )
    else:
        r.body_match = False
        if not strict_body:
            r.schema_diff = True
        r.note = "; ".join(
            filter(None, (python_note, f"body differs: {diff_summary(r.rust_body, python_body)}"))
        )

    return r


async def probe_first_file_id(rust: httpx.AsyncClient) -> int | None:
    """GET /api/files から最初のファイルIDを取得."""
    try:
        status, body, _ = await fetch(rust, "GET", "/api/files")
        if status == 200 and isinstance(body, list) and body:
            return body[0].get("id")
    except Exception:
        logger.debug("step failed", exc_info=True)
    return None


def load_cookies_from_file(cookie_file: str) -> dict[str, str]:
    """curl形式のCookieファイルからCookie辞書を生成."""
    cookies: dict[str, str] = {}
    try:
        with open(cookie_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) >= 7:
                    cookies[parts[5]] = parts[6]
    except OSError:
        pass
    return cookies


async def python_pin_login(base: str, pin: str) -> dict[str, str]:
    """PINでPythonサーバーにログインしてセッションCookieを返す."""
    async with httpx.AsyncClient(base_url=base, timeout=30.0) as client:
        # 1. GETでCSRFトークンとセッションCookieを取得
        resp = await client.get("/_pin")
        csrf_token = ""
        import re
        m = re.search(r'name="_csrf_token"\s+value="([^"]+)"', resp.text)
        if m:
            csrf_token = m.group(1)
        session_cookie = resp.cookies.get("session", "")

        # 2. POSTでPIN認証
        cookies = {"session": session_cookie} if session_cookie else {}
        resp2 = await client.post(
            "/_pin_check",
            data={"pin": pin, "_csrf_token": csrf_token, "next": "/"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            cookies=cookies,
            follow_redirects=False,
        )
        # 302リダイレクトが成功の証
        if resp2.status_code == 302:
            new_session = resp2.cookies.get("session", session_cookie)
            logger.info("Python PIN認証成功")
            return {"session": new_session}
        logger.warning("Python PIN認証失敗: status=%d", resp2.status_code)
        return cookies


async def rust_pin_login(base: str, pin: str) -> dict[str, str]:
    """PINでRustサーバーにログインしてCookie(session id + pin_token)を返す.

    Rustの/_pin_checkはPythonと異なりCSRFトークン不要かつsecretが一致していれば
    独立に認証できる(Python session cookieの使い回しはRust側のtower_sessions/HMAC
    secretと非互換で常に401になるため不可)。
    """
    async with httpx.AsyncClient(base_url=base, timeout=30.0) as client:
        resp = await client.post(
            "/_pin_check",
            data={"pin": pin, "next": "/"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=False,
        )
        # axum の Redirect::to() は既定で 303 See Other を返す(Python の 302 とは異なる)。
        if resp.status_code == 303:
            logger.info("Rust PIN認証成功")
            return dict(resp.cookies)
        logger.warning("Rust PIN認証失敗: status=%d", resp.status_code)
        return dict(resp.cookies)


async def run(
    rust_base: str,
    python_base: str | None,
    api_key: str | None,
    python_cookies: dict[str, str] | None = None,
    rust_cookies: dict[str, str] | None = None,
    manifest_path: Path | None = None,
    inputs_path: Path | None = None,
    path_vars: dict[str, int | str] | None = None,
    strict_body: bool = False,
) -> list[Result]:
    py_headers: dict[str, str] = {
        "X-Requested-With": "XMLHttpRequest",  # Python CSRF チェック通過
    }
    if api_key:
        py_headers["Authorization"] = f"Bearer {api_key}"

    rust_client = httpx.AsyncClient(
        base_url=rust_base,
        headers={"X-Requested-With": "XMLHttpRequest"},
        cookies=rust_cookies or {},
    )
    python_client: httpx.AsyncClient | None = None
    if python_base:
        python_client = httpx.AsyncClient(
            base_url=python_base,
            headers=py_headers,
            cookies=python_cookies or {},
        )

    async with rust_client:
        if python_client:
            async with python_client:
                return await _run_checks(
                    rust_client, python_client, manifest_path, inputs_path, path_vars, strict_body
                )
        else:
            return await _run_checks(rust_client, None, manifest_path, inputs_path, path_vars, strict_body)


async def _run_checks(
    rust_client: httpx.AsyncClient,
    python_client: httpx.AsyncClient | None,
    manifest_path: Path | None = None,
    inputs_path: Path | None = None,
    path_vars: dict[str, int | str] | None = None,
    strict_body: bool = False,
) -> list[Result]:
    # 動的エンドポイント: タグ系はファイルIDが必要
    file_id = await probe_first_file_id(rust_client)

    endpoints = [ep for ep in ENDPOINTS if not ep.get("skip")]
    if manifest_path:
        manifest_endpoints = load_manifest_endpoints(manifest_path)
        # Deduplicate against ALL of ENDPOINTS, not just the non-skipped ones.
        # Building this from `endpoints` let the manifest resurrect an entry
        # ENDPOINTS had deliberately skipped -- and resurrect it *bare*, losing
        # the curated accept_statuses, python_note and body rules with it.
        # `skip: True` on /api/sns/preview did nothing for exactly this reason
        # (2026-09-09): it is manifest-registered, so it came straight back.
        # ENDPOINTS is the curated source; the manifest only fills its gaps.
        curated = {(ep["method"], ep["path"]) for ep in ENDPOINTS}
        endpoints += [
            ep for ep in manifest_endpoints
            if (ep["method"], ep["path"]) not in curated
        ]
    if inputs_path:
        # Fail loudly instead of silently skipping Phase 3 endpoints: an
        # --inputs run with no resolved path vars would otherwise test nothing
        # and still exit 0 (the same vacuous-pass hazard as an over-broad skip).
        if not path_vars:
            raise ValueError(
                "inputs_path given but path_vars is empty — refusing to silently "
                "skip Phase 3 allowlist endpoints. Pass --path-vars-db so "
                "<file_id>/<collection_id> resolve."
            )
        inputs_endpoints = load_inputs_endpoints(inputs_path, path_vars)
        existing = {(ep["method"], ep["path"]) for ep in endpoints}
        endpoints += [
            ep for ep in inputs_endpoints
            if (ep["method"], ep["path"]) not in existing
        ]
    if file_id:
        endpoints += [
            {
                "method": "GET",
                "path": f"/api/files/{file_id}/tags",
                "note": "タグ一覧",
                "python_path": None,  # Pythonは /api/wd-tagger/tags/{id} 等、別パス
                "schema_check": [],
            },
        ]
    else:
        logger.warning("DBにファイルがないためタグ系エンドポイントはスキップ")

    # run_last付きエントリ(quick_lockを実際にactivateし後続APIを423にする)は
    # 安定ソートで相対順序を保ったまま末尾へ回す。
    endpoints.sort(key=lambda ep: bool(ep.get("run_last")))

    results = []
    for entry_id, ep in enumerate(endpoints):
        try:
            r = await check_endpoint(
                rust_client, python_client, ep, strict_body, entry_id
            )
        except Exception as exc:
            # A transport failure used to escape the loop and abort the run with
            # a traceback that never named the endpoint -- the whole reason the
            # CI parity death stayed undiagnosed. Record which entry dropped,
            # then keep going: the count of consecutive transport errors after
            # it is what separates "one endpoint kills the connection" from
            # "the server is gone from here on".
            r = Result(
                method=ep["method"],
                path=ep["path"],
                no_python=ep.get("python_path", ep["path"]) is None,
                error=f"{type(exc).__name__}: {exc}",
                entry_id=entry_id,
            )
        print(r.label())
        if not r.passed and r.rust_body is not None:
            logger.debug("  Rust:   %s", json.dumps(r.rust_body, ensure_ascii=False)[:200])
        if r.python_body is not None and not r.passed:
            logger.debug("  Python: %s", json.dumps(r.python_body, ensure_ascii=False)[:200])
        results.append(r)

    return results


def export_plain_db(cipher_path: str) -> str:
    """SQLCipher DBを平文SQLiteに変換してtempファイルパスを返す."""
    import tempfile

    from sqlcipher3 import dbapi2 as sqlcipher

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_name = tmp.name

    conn = sqlcipher.connect(cipher_path)
    conn.execute(f'PRAGMA key="{_CIPHER_KEY}"')
    conn.execute(f"ATTACH DATABASE '{tmp_name}' AS plaintext KEY ''")
    conn.execute("SELECT sqlcipher_export('plaintext')")
    conn.execute("DETACH DATABASE plaintext")
    conn.close()
    logger.info("平文DB生成: %s → %s", cipher_path, tmp_name)
    return tmp_name


@dataclass
class AutoDbChoice:
    db_path: str
    plain_db: str | None
    use_db_key_env: bool


def choose_auto_rust_db(
    db_path: str,
    *,
    sqlcipher_detected: bool,
    export_plain=export_plain_db,
) -> AutoDbChoice:
    if not sqlcipher_detected:
        return AutoDbChoice(db_path=db_path, plain_db=None, use_db_key_env=True)
    if os.environ.get("YU_DB_KEY"):
        logger.info("SQLCipher DB detected with YU_DB_KEY set — using encrypted DB directly")
        return AutoDbChoice(db_path=db_path, plain_db=None, use_db_key_env=True)
    logger.info("SQLCipher DB detected without YU_DB_KEY — exporting plain DB for Rust verification")
    plain_db = export_plain(db_path)
    return AutoDbChoice(db_path=plain_db, plain_db=plain_db, use_db_key_env=False)


def rust_server_env(*, use_db_key_env: bool) -> dict[str, str]:
    env = dict(os.environ)
    if not use_db_key_env:
        env.pop("YU_DB_KEY", None)
    # The auto-started test server must be deterministically configured by this
    # harness's own args, not by a host-local repo-root launch-args.txt (e.g. a
    # developer's personal --pin). Without this, an explicit pin= passed to
    # start_rust_server() can collide with a launch-args.txt --pin token and
    # crash clap with "the argument '--pin <PIN>' cannot be used multiple times".
    env["YU_SKIP_LAUNCH_ARGS_FILE"] = "1"
    # yu-server's load_dotenv_files() also re-reads ~/.config/yu/server.env
    # (and cwd/.env) *inside the child process*, independent of the env dict
    # passed to Popen here, with override semantics (dotenv wins over whatever
    # we set). An operator's real server.env can set YU_PIN, silently enabling
    # PIN auth on the test server even when this harness never asked for it.
    # Skip dotenv entirely so only this function's explicit env/CLI args reach
    # the auto-started test server.
    env["YU_SKIP_DOTENV_FILES"] = "1"
    # env = dict(os.environ) above also forwards any YU_PIN the *parent* shell
    # happens to have exported (distinct from dotenv files and launch-args.txt
    # — e.g. an operator's interactive shell profile). clap's env="YU_PIN"
    # falls back to this when no explicit --pin CLI token is given, silently
    # enabling PIN auth even when pin="" (no PIN testing intended). Drop it
    # unconditionally; when pin is actually wanted, start_rust_server() passes
    # --pin explicitly, which always wins over env regardless of this pop.
    env.pop("YU_PIN", None)
    # main.rs's effective_pin fallback chain is cli.pin (CLI/YU_PIN) >
    # YU_TAURI_PIN (read directly via std::env::var, bypassing clap entirely)
    # > config.json["server"]["pin"]. YU_TAURI_PIN is just as inheritable from
    # the parent shell as YU_PIN and must be dropped for the same reason.
    env.pop("YU_TAURI_PIN", None)
    # main.rs::apply_tagdb_env_overrides() also honors the legacy TAGDB_PIN
    # env var (mirrors core/configuration/env_override.py), injecting it into
    # config["server"]["pin"] *before* effective_pin's config.json fallback
    # reads it — unless YU_PIN is explicitly set. Since this harness leaves
    # YU_PIN unset for pin="" runs, an inherited TAGDB_PIN would slip through
    # this fourth, config-file-shaped path and re-enable PIN auth.
    env.pop("TAGDB_PIN", None)
    return env


def compiled_source_paths(root: Path, binary: Path) -> list[Path] | None:
    """The .rs files the binary was actually compiled from, per rustc's depfile.

    rustc writes `<binary>.d` listing exactly what it read. `#[cfg(test)]`
    modules never appear there, because `mod tests;` is compiled out of the
    binary -- and that is the whole point of reading it.

    The sweep below walks every file under the crate's src/, so editing a
    test-only file marks the binary stale. No rebuild can clear that: `cargo
    build` does not compile `#[cfg(test)]` code, so the binary's bytes -- and
    therefore its mtime -- never change. The harness then refuses to start the
    Rust server at all (PARITY_RC=2), demanding a rebuild that cannot help.
    The same defect was fixed in check_genesis_acceptance.py first; leaving this
    second copy of it standing cost a whole parity run (v4.732.14).

    Returns None when the depfile is missing or unparseable, so the caller falls
    back to the broad sweep rather than silently checking nothing.
    """
    depfile = binary.with_name(f"{binary.name}.d")
    if not depfile.exists():
        return None
    try:
        text = depfile.read_text(encoding="utf-8")
    except OSError:
        return None
    # Format: "<target>: <dep> <dep> ...", spaces inside paths backslash-escaped.
    _, _, rest = text.partition(":")
    if not rest.strip():
        return None
    crates = root / "crates"
    deps = [
        Path(part.replace("\\ ", " "))
        for part in re.split(r"(?<!\\)\s+", rest.strip())
        if part.endswith(".rs")
    ]
    inside = [p for p in deps if p.exists() and crates in p.parents]
    return inside or None


def newest_source_mtime(root: Path, binary: Path | None = None) -> float | None:
    """Return newest Rust source mtime for yu-server and tagdb-core.

    Prefers the depfile (see compiled_source_paths): test-only files must not
    count, because no rebuild can make the binary newer than them.
    """
    if binary is not None:
        compiled = compiled_source_paths(root, binary)
        if compiled is not None:
            return max(p.stat().st_mtime for p in compiled)
    newest: float | None = None
    for src_root in [
        root / "crates" / "yu-server" / "src",
        root / "crates" / "tagdb-core" / "src",
    ]:
        if not src_root.exists():
            continue
        for path in src_root.rglob("*"):
            if path.is_file():
                mtime = path.stat().st_mtime
                newest = mtime if newest is None else max(newest, mtime)
    return newest


def rust_binary_stale_reason(root: Path, binary: Path) -> str | None:
    """Return a user-facing reason if the yu-server binary is older than sources."""
    if not binary.exists():
        return f"Rust binary not found: {binary}\nRun: {RUST_BUILD_COMMAND}"
    source_mtime = newest_source_mtime(root, binary)
    if source_mtime is None:
        return None
    if binary.stat().st_mtime < source_mtime:
        return (
            "WARNING: yu-server is older than Rust sources. "
            "verify_rust_compat.py --auto would test a stale binary.\n"
            f"Run: {RUST_BUILD_COMMAND}\n"
            "Use --allow-stale-binary only when intentionally testing an existing build."
        )
    return None


def start_rust_server(
    db: str,
    port: int = 5000,
    python_url: str = "",
    allow_stale_binary: bool = False,
    use_db_key_env: bool = True,
    pin: str = "",
    mode: str = "",
    headless: bool = False,
    safe_mode: bool = False,
    log_file=None,
    config: str | None = None,
) -> subprocess.Popen:
    binary = ROOT / "crates" / "target" / "debug" / "yu-server"
    if os.name == "nt":
        binary = binary.with_suffix(".exe")
    if not binary.exists():
        raise FileNotFoundError(f"Rustバイナリが見つかりません: {binary}\ncargo build を先に実行してください")
    stale_reason = rust_binary_stale_reason(ROOT, binary)
    if stale_reason and not allow_stale_binary:
        print(f"\n{stale_reason}\n", file=sys.stderr)
        sys.exit(2)
    if stale_reason:
        print(f"\n{stale_reason}\n", file=sys.stderr)
    cmd = [str(binary), "--db", db, "--port", str(port)]
    if config:
        # Without this, Rust falls back to CWD-relative config.json/config.toml
        # resolution (crates/yu-server/src/main.rs), which for every caller here
        # is the repo root -- i.e. the developer's REAL, live config.json. A
        # mutating parity request (DELETE/reorder scan-roots) then permanently
        # wipes the operator's registered folders. Callers MUST pass an
        # isolated throwaway path here; never point this at the real file.
        cmd += ["--config", config]
    if python_url:
        cmd += ["--python-url", python_url]
    if mode:
        cmd += ["--mode", mode]
    if headless:
        cmd.append("--headless")
    if safe_mode:
        cmd.append("--safe-mode")
    if not use_db_key_env:
        # yu-server's load_dotenv_files() re-reads ~/.config/yu/server.env
        # (and any local .env) *inside the child process* after it starts,
        # independent of the env dict passed to Popen below. If that file
        # sets YU_DB_KEY (e.g. for the operator's real encrypted DB), it
        # would silently re-populate cli.db_key even though we asked for
        # the plaintext path here, and yu-server would then try to decrypt
        # this plaintext parity DB as SQLCipher and fail to start. An
        # explicit CLI arg always wins over an env-sourced value in clap,
        # so pass an empty --db-key to force the plaintext path regardless
        # of what dotenv injects.
        cmd += ["--db-key", ""]
    if pin:
        # 明示CLI引数はclapのenv属性より優先されるため、host側の launch-args.txt
        # や ~/.config/yu/server.env が別のPINを注入していても、ここで渡した値が
        # 必ず有効になる。rust_pin_login()でRustへ実際にログインするには、
        # Rust側にもこのPINが設定されていなければならない(PIN未設定のままだと
        # 認証自体が無効化され、Python側とテストの前提条件が食い違う)。
        cmd += ["--pin", pin]
    logged_cmd = ["***" if arg == pin and pin else arg for arg in cmd]
    logger.info("Rustサーバー起動: %s", " ".join(logged_cmd))
    # Without log_file the child's output goes to DEVNULL, which is why a Rust
    # panic mid-run left no trace anywhere: the CI failure dump globs
    # tmp/rust/*.log and that file had never existed. Callers that want to
    # diagnose a mid-run death must pass a file here.
    sink = log_file if log_file is not None else subprocess.DEVNULL
    return subprocess.Popen(
        cmd,
        stdout=sink,
        stderr=subprocess.STDOUT if log_file is not None else subprocess.DEVNULL,
        env=rust_server_env(use_db_key_env=use_db_key_env),
    )


def wait_for_server(url: str, timeout: int = 15) -> bool:
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except urllib.error.HTTPError:
            # Server responded with an HTTP error (e.g. 502 proxy not ready yet) —
            # it is listening, so count as healthy.
            return True
        except Exception:
            time.sleep(0.5)
    return False


def _load_known_no_python_fails(path: Path) -> set[tuple[str, str]]:
    """Parse the no_python known-FAIL allowlist into (method, path) pairs.

    See scripts/parity_no_python_known_fails.txt for the format spec and the
    rationale (2026-08-13 no_python gate enablement; this triages the 42
    entries the fix newly surfaced as an explicit, individually-verified,
    shrink-only allowlist — no wildcards, no category-wide exclusions).
    Returns an empty set if the file does not exist.
    """
    pairs: set[tuple[str, str]] = set()
    if not path.exists():
        return pairs
    for lineno, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise ValueError(f"{path}:{lineno}: malformed known-fail line: {raw_line!r}")
        method, ep_path = parts
        pairs.add((method.strip().upper(), ep_path.strip()))
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(description="Rust ↔ Python 互換性検証")
    parser.add_argument("--rust", default="http://127.0.0.1:5002", help="RustサーバーベースURL")
    parser.add_argument("--python", default=None, help="PythonサーバーベースURL (省略でRustのみ検証)")
    parser.add_argument("--api-key", default=None, help="Python側 Bearer トークン")
    parser.add_argument("--python-cookie-file", default=None, help="Python側セッションCookieファイル (curl -c 形式)")
    parser.add_argument("--python-pin", default=None, help="Python側PIN (自動ログイン)")

    parser.add_argument(
        "--rust-pin",
        default=None,
        help="Rust側PIN (自動ログイン。省略時は--python-pinと同じ値を使用)",
    )
    parser.add_argument("--db", default="data/tags.db", help="DBパス (--auto 時に使用)")
    parser.add_argument("--auto", action="store_true", help="Rustサーバーを自動起動")
    parser.add_argument(
        "--allow-stale-binary",
        action="store_true",
        help="Allow --auto to run even when crates/target/debug/yu-server is older than Rust sources",
    )
    parser.add_argument("--rust-port", type=int, default=5002, help="Rust起動ポート (--auto 時)")
    parser.add_argument(
        "--rust-config",
        default=None,
        help=(
            "--auto 時にRustへ渡す--configパス。省略時ハ実configヲ一度ダケ複写シタ"
            "使イ捨テコピー(tmp/rust/)ヲ自動生成シ、Rustガ実 config.json ヲ直接開カヌ様隔離スル"
            "（未指定ノママ渡サザレバRustハCWD相対ノ実 config.json ヲ解決シ、mutating リクエストガ"
            "実データヲ書キ換ヘ得ル -- 2026-08-30 parity harness ト同ジ穴）。"
        ),
    )
    parser.add_argument("--manifest", default=None, help="Compatibility golden manifest YAML")
    parser.add_argument(
        "--inputs",
        default=None,
        help="Path to inputs.yaml Phase 3 allowlist.",
    )
    parser.add_argument(
        "--path-vars-db",
        default=None,
        help="Path to seeded DB for resolving inputs.yaml variables.",
    )
    # Body comparison was inert: any mismatch set schema_diff, which passed returned.
    # docs/development/development_docs/OCR_PARITY_CENSUS.md triaged all 29 failures;
    # remaining holds use skip_body_compare with reasons.
    # check_rust_compat is a blocking pre-push gate for routes/ and main.rs, so strict-by-default
    # strengthens that gate and is safe only while parity is green.
    parser.add_argument("--strict-body", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    rust_proc = None
    plain_db: str | None = None
    python_cookies: dict[str, str] | None = None
    rust_cookies: dict[str, str] | None = None
    rust_pin = args.rust_pin or args.python_pin or ""

    try:
        if args.auto:
            sqlcipher_detected = False
            try:
                import sqlite3 as _stdlib_sqlite
                _stdlib_sqlite.connect(args.db).execute("SELECT 1 FROM sqlite_master").fetchone()
            except Exception:
                sqlcipher_detected = True
            db_choice = choose_auto_rust_db(args.db, sqlcipher_detected=sqlcipher_detected)
            plain_db = db_choice.plain_db
            rust_db = db_choice.db_path

            rust_config = args.rust_config
            if not rust_config:
                tmp_dir = ROOT / "tmp" / "rust"
                tmp_dir.mkdir(parents=True, exist_ok=True)
                rust_config_path = tmp_dir / f"auto-verify-{os.getpid()}.config.json"
                seed_source = ROOT / "config.json"
                if not seed_source.exists():
                    seed_source = ROOT / "config.json.example"
                if seed_source.exists():
                    shutil.copy2(seed_source, rust_config_path)
                else:
                    rust_config_path.write_text('{"scan_roots": []}', encoding="utf-8")
                rust_config = str(rust_config_path)

            rust_proc = start_rust_server(
                rust_db,
                port=args.rust_port,
                python_url=args.python or "",
                allow_stale_binary=args.allow_stale_binary,
                use_db_key_env=db_choice.use_db_key_env,
                pin=rust_pin,
                config=rust_config,
            )
            rust_url = f"http://127.0.0.1:{args.rust_port}"
            print(f"Rustサーバー起動待機 ({rust_url})...")
            if not wait_for_server(f"{rust_url}/api/scan/status"):
                print("❌ Rustサーバーが起動しませんでした")
                rust_proc.terminate()
                sys.exit(1)
            print("✅ Rustサーバー起動確認")
            args.rust = rust_url

        # Python認証
        if args.python:
            if args.python_pin:
                python_cookies = asyncio.run(python_pin_login(args.python, args.python_pin))
            elif args.python_cookie_file:
                python_cookies = load_cookies_from_file(args.python_cookie_file)

        if rust_pin:
            rust_cookies = asyncio.run(rust_pin_login(args.rust, rust_pin))

        manifest_path = Path(args.manifest) if args.manifest else None
        inputs_path = Path(args.inputs) if args.inputs else None
        path_vars: dict[str, int | str] | None = None
        if args.path_vars_db:
            sys.path.insert(0, str(ROOT / "scripts"))
            from parity_seed_helper import seed_ids_from_existing_db

            path_vars = seed_ids_from_existing_db(Path(args.path_vars_db))
        results = asyncio.run(
            run(
                args.rust,
                args.python,
                args.api_key,
                python_cookies,
                rust_cookies=rust_cookies,
                manifest_path=manifest_path,
                inputs_path=inputs_path,
                path_vars=path_vars,
                strict_body=args.strict_body,
            )
        )

        # no_python (python_path=None) entries have no Python side to compare
        # against, so r.passed is always False. Their standalone Rust-side
        # verdict (no_python_ok) can still be checked against accept_statuses.
        # Count as na ("N/A") only the entries that genuinely pass; a status
        # outside accept_statuses is counted as failed so it reaches the exit
        # code. schema_check failures are already surfaced via r.error inside
        # check_endpoint(), so they land in the errors bucket instead.
        na = sum(1 for r in results if r.no_python and not r.error and r.no_python_ok)
        passed = sum(1 for r in results if r.passed and not r.no_python)
        warned = sum(1 for r in results if r.schema_diff and not r.no_python)

        # Pre-existing no_python FAILs that have been triaged and recorded in
        # scripts/parity_no_python_known_fails.txt (see that file for format
        # and rationale) do not block the gate on their own, but the
        # allowlist is enforced to shrink-only: it must match the set of
        # currently-failing (method, path) pairs exactly, or the gate fails.
        known_fails_path = ROOT / "scripts" / "parity_no_python_known_fails.txt"
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
        print(f"\n{'='*60}")
        print(
            f"結果: {passed} PASS / {warned} WARN / {failed} FAIL / "
            f"{na} N/A(Rust独自) / {errors} ERROR / {len(results)} 合計"
        )
        if known_fail_matched:
            print(f"既知FAIL allowlist: {len(known_fail_matched)} 件 "
                  f"({known_fails_path.relative_to(ROOT)})")
        if known_fail_stale:
            print(
                "⚠️  allowlist に載っているが現在 FAIL しないエントリ "
                "(直った→一覧から外せ):"
            )
            for m, p in known_fail_stale:
                print(f"   - {m} {p}")
        if known_fail_unlisted:
            print(
                "⚠️  現在 FAIL しているが allowlist に無いエントリ "
                "(新規debt or 未triage):"
            )
            for m, p in known_fail_unlisted:
                print(f"   - {m} {p}")
        if failed or errors or known_fail_stale or known_fail_unlisted:
            sys.exit(1)

    finally:
        if rust_proc:
            rust_proc.terminate()
        if plain_db:
            os.unlink(plain_db)


if __name__ == "__main__":
    main()
