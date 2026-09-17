"""Python→Rust移植カバレッジの実測レポート。

check_mcp_parity.py が収集する MCP 露出パス（mcp_server/*.py の client.METHOD(...)
呼出）と、check_rust_mcp_parity.py が収集する Rust axum ルート（crates/yu-server/
src/**/*.rs の .route(...) 登録）を突き合わせ、「MCP 経由で到達可能な機能のうち
何割が既に Rust ネイティブ実装を持つか」を計測する。

check_mcp_parity.py / check_rust_mcp_parity.py 自体は個々の不整合（ERROR/WARNING）
を検出する parity チェッカーであり、全体カバレッジ率は算出しない。本スクリプトは
両者の収集ロジックをそのまま再利用し、カバレッジという別の指標のみを追加算出する
（判定ロジックの重複実装を避けるため、マッチング関数は check_rust_mcp_parity.py の
ものをそのまま呼ぶ）。

Usage:
  uv run python scripts/rust_migration_coverage.py
  uv run python scripts/rust_migration_coverage.py --json
  uv run python scripts/rust_migration_coverage.py --by-prefix
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _import_module(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO / rel_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mcp = _import_module("check_mcp_parity", "scripts/check_mcp_parity.py")
_rust = _import_module("check_rust_mcp_parity", "scripts/check_rust_mcp_parity.py")


def _path_prefix(path: str, depth: int = 2) -> str:
    """`/api/tags/suggest` -> `/api/tags`（depthセグメントまで）。集計のグルーピング用。"""
    segments = [s for s in path.split("/") if s]
    if not segments:
        return "(unresolved path)"
    return "/" + "/".join(segments[:depth])


def compute_coverage() -> dict:
    exceptions = _mcp.load_exceptions()
    mcp_paths = _mcp.collect_mcp_paths()
    rust_routes = _rust.collect_rust_routes()

    # 1つの静的パスに複数 HTTP メソッドが張られることがあるため
    # (method, static_path) の組で重複排除する。
    seen: set[tuple[str, str]] = set()
    unique_mcp_paths = []
    for ep in mcp_paths:
        key = (ep.method.upper(), ep.static_path)
        if key in seen:
            continue
        seen.add(key)
        unique_mcp_paths.append(ep)

    covered = []
    uncovered = []
    for ep in unique_mcp_paths:
        if _mcp._is_excluded(ep.static_path, exceptions):
            continue
        has_rust_route = any(
            r.method.upper() == ep.method.upper()
            and _rust._route_matches_path(r, ep.static_path, ep.is_prefix)
            for r in rust_routes
        )
        (covered if has_rust_route else uncovered).append(ep)

    total = len(covered) + len(uncovered)
    pct = round(100 * len(covered) / total, 1) if total else 0.0

    by_prefix: dict[str, dict[str, int]] = {}
    for ep, bucket in [(e, "covered") for e in covered] + [(e, "uncovered") for e in uncovered]:
        prefix = _path_prefix(ep.static_path)
        by_prefix.setdefault(prefix, {"covered": 0, "uncovered": 0})
        by_prefix[prefix][bucket] += 1

    return {
        "total_mcp_paths": total,
        "covered": len(covered),
        "uncovered": len(uncovered),
        "coverage_pct": pct,
        "excluded_via_exceptions": len(unique_mcp_paths) - total,
        "by_prefix": by_prefix,
        "uncovered_paths": sorted({f"{e.method} {e.static_path}" for e in uncovered}),
    }


def format_report(report: dict, *, by_prefix: bool = False) -> str:
    lines = [
        "Python→Rust 移植カバレッジ（MCP露出パス基準）",
        "=" * 60,
        f"MCP露出パス総数（重複除去後、mcp_parity_exceptions.txt 適用後）: {report['total_mcp_paths']}",
        f"  Rustネイティブ実装あり: {report['covered']}",
        f"  Rustネイティブ実装なし: {report['uncovered']}",
        f"  カバレッジ: {report['coverage_pct']}%",
    ]
    if report["excluded_via_exceptions"]:
        lines.append(f"  (mcp_parity_exceptions.txt により除外: {report['excluded_via_exceptions']})")

    if by_prefix:
        lines.append("")
        lines.append("領域別内訳（/api/xxx or /ext/xxx 単位）:")
        lines.append("-" * 60)
        for prefix, counts in sorted(
            report["by_prefix"].items(),
            key=lambda kv: kv[1]["covered"] + kv[1]["uncovered"],
            reverse=True,
        ):
            c, u = counts["covered"], counts["uncovered"]
            t = c + u
            pct = round(100 * c / t, 0) if t else 0
            lines.append(f"  {prefix:<40} {c:>3}/{t:<3} ({pct:.0f}%)")

    lines.append("")
    lines.append(
        "注: 本指標は「MCPツールが参照するパスに Rust ネイティブ .route() が存在するか」"
        "の静的照合であり、実装の完全性（挙動の一致）までは検証しない。"
        "後方互換フォワーダー（call_python_bridge 相当）が残っている場合も「カバー済み」"
        "と判定されうる点に注意。"
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Python→Rust 移植カバレッジ計測")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--by-prefix", action="store_true", help="領域別内訳を表示")
    ap.add_argument("--show-uncovered", action="store_true", help="未カバーパス一覧を表示")
    args = ap.parse_args(argv)

    report = compute_coverage()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(format_report(report, by_prefix=args.by_prefix))
    if args.show_uncovered:
        print("\n未カバーパス一覧:")
        for p in report["uncovered_paths"]:
            print(f"  {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
