"""Regenerate docs/development/development_docs/dev-docs-index.yaml.

Run after adding or deleting any .md file in that directory:
    uv run python scripts/gen_docs_index.py
"""
from __future__ import annotations

import contextlib
import hashlib
import re
import sys
from pathlib import Path

import yaml


def _sha256(path: Path) -> str:
    # Normalize CRLF -> LF before hashing so the hash matches regardless of
    # the checkout's line-ending mode (core.autocrlf=true gives Windows
    # working trees CRLF while git stores LF; hashing raw bytes made every
    # doc's hash diverge on Windows and made this script's own output
    # unsafe to commit from there). Content is otherwise unaffected: no \r\n
    # in a normal LF checkout means this is a no-op there.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = REPO_ROOT / "docs" / "development" / "development_docs"
FOUNDATIONS_DIR = REPO_ROOT / "docs" / "NAME_ORIGIN"
OUT_FILE = DOCS_DIR / "dev-docs-index.yaml"

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "database": ["sqlite", "sql", "fts", "schema", "migration", "sqlcipher", "trigram", "query"],
    "bridge": ["bridge", "comfyui", "nai", "sd webui", "prompt param", "weight regex"],
    "hardware": ["hailo", "cuda", "onnx", "pyvips", "nvidia", "directml", "rocm"],
    "video-media": ["video", "thumbnail", "media", "streaming", "mp4", "ffmpeg"],
    "ui-frontend": [
        "ui ", "css", " js ", "typescript", "modal", "scroll", "button", "dialog",
        "widget", "frontend", "browser", "virtual", "script tag",
    ],
    "auth-security": ["auth", "security", "sandbox", "gateway", "csrf", "apikey", "permission", "audit"],
    "api-protocol": ["api", "openai compat", "mcp", "http", "endpoint", "qr ", "response", "batch"],
    "devops": ["docker", "tauri", "git ", "release", "deploy", "hook", "worktree", "tmux", "pre-push"],
    "coding-standards": [
        "convention", "guideline", "style", "standard", "rule", "policy",
        "import", "refactor", "line count", "code size", "module safety",
    ],
    "features": [
        "spec", "roadmap", "lora", "ocr", "scheduler", "notification",
        "drag", "cowork", "lan ", "vlm", "chatlog", "parity",
    ],
    "performance": ["performance", "perf", "optim", "cache", "speed", "slow", "fast", "benchmark", "throughput"],
    "architecture": [
        "architecture", "design", "philosophy", "module", "extension", "distributed",
        "agent integration", "mesh", "structure", "entrypoint",
    ],
    "ai-dev": ["codex", "claude", "ai-driven", "delegation", "subagent", "covenant", "agents.md"],
}

WHEN_TO_READ_HINTS: dict[str, str] = {
    "SQLITE_FTS5_TRIGRAM_ESCAPE_PITFALL": "FTS5 検索クエリを書く時・EXPLAIN QUERY PLAN で full scan が出た時",
    "BRIDGE_BLOCKING_EXECUTOR": "Bridge generate ハンドラを実装する時・thumbnail が固まる症状が出た時",
    "ONNXRUNTIME_GPU_VARIANT_SETUP": "onnxruntime GPU セットアップ時・CPUExecutionProvider ⚠ が出た時",
    "FRONTEND_DEBUGGING_PITFALLS": "JS 動的テキストが戻る・API 結果が空・script 分割時・CSS ルール確認時",
    "PERF_DEBUG_METHODOLOGY": "パフォーマンス問題を調査する時・debug ログを分析する時",
    "MODULE_SCRIPT_TIMING": "type=module スクリプトとインライン IIFE を組み合わせる時",
    "MODAL_LOADING_OPTIMIZATION": "モーダル開閉が遅い時・画像ロード最適化する時",
    "CODING_CONVENTIONS": "新機能実装前・コードレビュー時・Blueprint/フォーム/API/ポートを変更する時",
    "GATEWAY_AUTH_DUAL_SYSTEM": "Gateway / API 認証を実装・デバッグする時",
    "CODEX_DELEGATION_GUIDE": "Codex に実装を委譲する時",
    "FEATURE_PARITY": "新 API / MCP ツール / WebUI 機能を追加する時",
    "AGENT_SAFETY_MCP_ARCH": "MCP サーバー・COVENANT 監査を実装する時",
    "HAILO_10H_ECOSYSTEM_ASSESSMENT": "Hailo-10H を使う実装・デバッグ時",
    "WINDOWS_CUDA_DLL_HIJACK": "Windows CUDA / GPU 環境の問題が出た時",
    "RELEASE_PROCEDURE": "リリース作業時",
    "GIT_PARALLEL_WORKTREE_WORKFLOW": "複数 session で同リポジトリを操作する時",
    "UI_DIALOG_POLICY": "confirm / alert / prompt を使おうとした時",
    "LARGE_SCALE_150K_PERF_OVERHAUL": "150K+ 件のクエリ・描画最適化時",
    "DISTRIBUTED_INFERENCE": "分散推論・Mesh Inference を実装する時",
    "BRIDGE_RECEIVE_PROMPT_PARAM_FLOW": "Bridge にパラメータを追加する時・初期化チェーンを変更する時",
    "STATUS_API_PERF_PATTERN": "status API を実装・最適化する時",
    "ASYNC_EVENT_LOOP_BLOCKING_FIX": "非同期ルートで同期 IO を呼ぶ実装を変更する時",
    "UI_BUTTON_PRIORITY_GUIDELINES": "新規 UI ボタンを追加・配置する時",
    "EXTENSION_SANDBOX_SPEC": "Extension のセキュリティ境界を変更する時",
    "THUMBNAIL_AND_CV_PANEL_INCIDENTS_2026_04": "キャッシュ汚染・VirtualGrid パフォーマンス問題が出た時",
    "VIRTUAL_SCROLL_PITFALLS": "VirtualGrid / VirtualScroll を実装・修正する時",
    "BROWSER_GLOBAL_POLICY": "window グローバルを使う実装を追加する時",
    "MCP_DEBUG_TOOLS": "MCP サーバーをデバッグする時",
    "MULTIAGENT_TMUX": "tmux / psmux でマルチエージェント開発する時",
    "DOCKER_SETUP": "Docker 環境を構築・変更する時",
    "TAURI_DESKTOP_APP": "Tauri デスクトップアプリを実装・デバッグする時",
    "LARGE_SCALE_QUERY_OPTIMIZATION": "大規模検索クエリを最適化する時",
    "DEV_OVERVIEW_MAINTENANCE": "dev-overview.html を更新する時",
    "AGENTS_MD_SYNC": "AGENTS.md と CLAUDE.md の同期手順を確認する時",
}

CATEGORY_DEFAULTS: dict[str, str] = {
    "database": "SQLite クエリを書く / DB 設計を変更する時",
    "bridge": "Bridge 系機能を実装・デバッグする時",
    "hardware": "ハードウェアアクセラレータを使う実装時",
    "video-media": "動画・サムネイル処理を実装する時",
    "ui-frontend": "フロントエンド UI を実装・デバッグする時",
    "auth-security": "認証・セキュリティ境界を変更する時",
    "api-protocol": "API エンドポイントを追加・変更する時",
    "devops": "ビルド・デプロイ・CI 設定を変更する時",
    "coding-standards": "新機能実装前・コードレビュー時",
    "features": "その機能を実装・修正する時",
    "performance": "パフォーマンス問題を調査・修正する時",
    "architecture": "システム設計・モジュール構造を変更する時",
    "ai-dev": "AI ワークフロー・Codex/Claude 連携を使う時",
}


def guess_category(title: str, summary: str, fname: str) -> str:
    text = (title + " " + summary + " " + fname.replace("_", " ")).lower()
    scores = {cat: 0 for cat in CATEGORY_KEYWORDS}
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw.lower() in text:
                scores[cat] += 1
    best = max(scores, key=lambda c: scores[c])
    return best if scores[best] > 0 else "architecture"


def extract_tags(title: str, fname: str, summary: str = "") -> list[str]:
    tags = set()
    text = (title + " " + fname.replace("_", " ").replace("-", " ") + " " + summary).lower()
    tag_patterns = [
        ("sqlite", r"sqlite|sql\b"), ("fts5", r"fts5|trigram"),
        ("performance", r"perf|optim|slow|speed\b|benchmark"),
        ("bridge", r"bridge\b"), ("comfyui", r"comfyui"), ("nai", r"\bnai\b|novel.?ai"),
        ("hailo", r"hailo"), ("cuda", r"cuda|nvidia|gpu\b"), ("onnxruntime", r"onnx"),
        ("typescript", r"typescript|tsc\b"), ("css", r"\bcss\b"),
        ("modal", r"\bmodal\b"), ("api", r"\bapi\b"), ("mcp", r"\bmcp\b"),
        ("auth", r"\bauth\b"), ("gateway", r"gateway"),
        ("docker", r"docker"), ("tauri", r"tauri"), ("git", r"\bgit\b"),
        ("extension", r"extension"), ("video", r"\bvideo\b|mp4\b|stream"),
        ("thumbnail", r"thumbnail"), ("i18n", r"i18n|translat"),
        ("codex", r"codex"), ("llm", r"\bllm\b"),
        ("debug", r"debug|pitfall|incident"),
        ("known_pitfalls", r"pitfall|gotcha|escape.pitfall|incident|hijack|既知.制限|known.limit|罠"),
        ("architecture", r"architect|design.?philosoph"),
        ("release", r"release\b"), ("ui", r"\bui\b"),
        ("large-scale", r"large.?scale|150k"),
        ("pyvips", r"pyvips"), ("vlm", r"\bvlm\b"),
        ("scheduler", r"scheduler"), ("lora", r"\blora\b"),
    ]
    for tag, pattern in tag_patterns:
        if re.search(pattern, text, re.I):
            tags.add(tag)
    return sorted(tags)[:6]


def get_when_to_read(stem: str, category: str) -> str:
    stem_upper = stem.upper()
    for key, hint in WHEN_TO_READ_HINTS.items():
        if key in stem_upper:
            return hint
    return CATEGORY_DEFAULTS.get(category, "必要に応じて参照")


def process_file(md_file: Path) -> dict:
    try:
        content = md_file.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = md_file.read_text(encoding="utf-8", errors="replace")

    lines = content.splitlines()

    # Parse YAML front-matter (if present) for explicit overrides
    frontmatter: dict = {}
    body_start = 0
    if lines and lines[0].strip() == "---":
        end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None)
        if end is not None:
            with contextlib.suppress(Exception):
                frontmatter = yaml.safe_load("\n".join(lines[1:end])) or {}
            body_start = end + 1
    body_lines = lines[body_start:]

    title = md_file.stem.replace("_", " ")
    summary = ""

    for line in body_lines[:20]:
        stripped = line.strip()
        if stripped.startswith("# ") and title == md_file.stem.replace("_", " "):
            title = stripped[2:].strip()
        elif (
            not summary
            and stripped
            and not stripped.startswith("#")
            and not stripped.startswith("---")
            and not stripped.startswith("作成日")
            and not stripped.startswith("更新日")
            and not stripped.startswith("最終更新")
            and not stripped.startswith("Date:")
            and not stripped.startswith("**作成")
            and not stripped.startswith("**更新")
            and len(stripped) > 10
        ):
            summary = stripped[:100]

    if not summary:
        for line in body_lines[20:50]:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("---") and len(stripped) > 15:
                summary = stripped[:100]
                break

    if not summary:
        summary = title[:80]

    category = frontmatter.get("index_category") or guess_category(title, summary, md_file.name)
    tags = extract_tags(title, md_file.name, summary)
    when_to_read = frontmatter.get("index_when_to_read") or get_when_to_read(md_file.stem, category)

    return {
        "file": str(md_file.relative_to(DOCS_DIR)).replace("\\", "/"),
        "title": title,
        "summary": summary,
        "category": category,
        "tags": tags,
        "when_to_read": when_to_read,
        "doc_sha256": _sha256(md_file),
    }


def detect_pairs() -> dict[str, dict]:
    """Find .claude/*.yaml with both criteria: and rationale_ref: keys (ref-primary detection)."""
    claude_dir = REPO_ROOT / ".claude"
    pairs: dict[str, dict] = {}
    for yml_file in sorted(claude_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(yml_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[warn] skip {yml_file.name}: {e}", file=sys.stderr)
            continue
        if not isinstance(data, dict):
            continue
        if "criteria" in data and "rationale_ref" in data:
            ref = data["rationale_ref"]
            if not isinstance(ref, str):
                continue
            stem = yml_file.stem
            yml_rel = str(yml_file.relative_to(REPO_ROOT)).replace("\\", "/")
            pairs[stem] = {
                "yml": yml_rel,
                "md": ref,
            }
    return pairs


def main() -> None:
    import datetime

    pairs = detect_pairs()
    paired_md_refs = {info["md"].replace("\\", "/") for info in pairs.values()}

    # Libraries: principles/ subdirectory (empty initially)
    principles_dir = DOCS_DIR / "principles"
    libraries: dict[str, dict] = {}
    if principles_dir.exists():
        for md_file in sorted(principles_dir.glob("*.md")):
            md_rel = str(md_file.relative_to(REPO_ROOT)).replace("\\", "/")
            libraries[md_file.stem] = {"md": md_rel}

    # Foundations: docs/NAME_ORIGIN/ — constitutional / design-philosophy docs
    foundations: list[dict] = []
    if FOUNDATIONS_DIR.exists():
        foundations_when: dict[str, str] = {
            "COVENANT": "Extension境界・Agent安全・監査ログ・Scope制限・Circuit Breaker・ノード間契約・継承順位を設計・変更する時",
            "CLASSICAL": "プロジェクトの本質・命名根拠・設計哲学を理解したい時、新機能の方向性が哲学に沿うか判断する時",
        }
        for md_file in sorted(FOUNDATIONS_DIR.glob("*.md")):
            if md_file.name == "README.md":
                continue
            md_rel = str(md_file.relative_to(REPO_ROOT)).replace("\\", "/")
            stem_upper = md_file.stem.upper()
            when = next(
                (v for k, v in foundations_when.items() if k in stem_upper),
                "設計の根本原則を確認する時",
            )
            foundations.append({"file": md_rel, "when_to_read": when, "doc_sha256": _sha256(md_file)})

    # Standalone: all docs/**/*.md not in paired refs or principles/
    # Sort by the posix-style relative path, not the raw Path object: on
    # Windows Path sorts using "\" separators, which interleaves
    # subdirectory entries (e.g. "specs/x.md") differently than the "/"
    # sort every other platform uses, producing pure reorder-noise diffs.
    standalone = []
    for md_file in sorted(
        DOCS_DIR.rglob("*.md"),
        key=lambda p: str(p.relative_to(DOCS_DIR)).replace("\\", "/"),
    ):
        if principles_dir in md_file.parents:
            continue
        md_rel = str(md_file.relative_to(REPO_ROOT)).replace("\\", "/")
        if md_rel in paired_md_refs:
            continue
        standalone.append(process_file(md_file))

    category_files: dict[str, list[str]] = {}
    tag_files: dict[str, list[str]] = {}
    for entry in standalone:
        category_files.setdefault(entry["category"], []).append(entry["file"])
        for tag in entry["tags"]:
            tag_files.setdefault(tag, []).append(entry["file"])

    categories = {
        category: sorted(files)
        for category, files in sorted(category_files.items())
    }
    tags_map = {
        tag: sorted(files)
        for tag, files in sorted(tag_files.items())
        if len(files) >= 2
    }

    index = {
        "version": 2,
        # Local calendar date, same value `date.today()` gave.
        "updated": datetime.datetime.now(tz=datetime.UTC)
        .astimezone()
        .date()
        .isoformat(),
        "note": "AI 参照用索引。どの doc を読むべきか不明な時はこの YAML を Read して when_to_read で絞り込む。",
        "categories": categories,
        "tags_map": tags_map,
        "sets": pairs,
        "libraries": libraries,
        "foundations": foundations,
        "standalone": standalone,
    }

    header = (
        "# dev-docs-index.yaml — AI 参照用索引（自動生成）\n"
        "# どの doc を読むべきか不明な時はこのファイルを Read して when_to_read で絞り込む。\n"
        "# categories / tags_map で候補を絞ってから該当 doc を読む（全 entry 走査不要）。\n"
        "# 再生成: uv run python scripts/gen_docs_index.py\n\n"
    )
    body = yaml.dump(index, allow_unicode=True, default_flow_style=False, sort_keys=False)
    OUT_FILE.write_text(header + body, encoding="utf-8")
    n_standalone = len(standalone)
    n_sets = len(pairs)
    n_libs = len(libraries)
    n_foundations = len(foundations)
    print(
        f"Written {n_standalone} standalone + {n_sets} sets + {n_libs} libraries"
        f" + {n_foundations} foundations to {OUT_FILE}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
