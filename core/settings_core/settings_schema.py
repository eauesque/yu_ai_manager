"""Settings schema definition: typed metadata for reading/writing settings from AI/MCP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SettingDef:
    """Definition of an individual setting item."""

    key: str  # Dot-notation key (e.g. "server.pin")
    type: str  # "str" | "int" | "float" | "bool" | "list"
    description: str
    default: Any = None
    secret: bool = False  # Subject to masking
    category: str = "general"
    op_eligible: bool = False  # Eligible for 1Password CLI integration
    options: list[str] | None = None  # Choices (enum-style)


# ── Schema Definitions ──────────────────────────────────────────────────

SETTINGS_SCHEMA: list[SettingDef] = [
    # -- Server --
    SettingDef("server.host", "str", "バインドホスト", "127.0.0.1", category="server"),
    SettingDef("server.port", "int", "ポート番号", 5000, category="server"),
    SettingDef("server.lan", "bool", "LAN アクセス有効", False, category="server"),
    SettingDef(
        "server.pin", "str", "PIN 認証コード", None,
        secret=True, category="server", op_eligible=True,
    ),
    SettingDef("server.pin_boss_login_ui", "bool", "ボスログイン UI", True, category="server"),
    SettingDef("server.quick_lock_enabled", "bool", "クイックロック有効", True, category="server"),
    SettingDef("server.allow_restart", "bool", "再起動 API 有効", False, category="server"),
    SettingDef("server.allow_remote_restart", "bool", "リモート再起動 API 有効", False, category="server"),
    SettingDef(
        "server.restart_token", "str", "リモート再起動トークン", None,
        secret=True, category="server", op_eligible=True,
    ),
    SettingDef(
        "fast_mode_source",
        "str",
        "高速モード: Rust サーバーの取得方法 — "
        "download（既定）配布バイナリを落とす。この端末ではビルドしない。 / "
        "build この端末でビルドする。ダウンロードはしない。 / "
        "auto 落として、駄目ならビルドする。"
        "【配布バイナリがある環境】どれを選んでも高速モードは働きます。"
        "build を選ぶ理由は、配布物を使いたくない・取得が塞がれている等の場合のみ。"
        "【ビルドを選ぶときの資源】cargo build は CPU とメモリを大きく使います。"
        "空きディスクが 8GB 以上必要です（ツールチェーンと中間生成物）。"
        "メモリが少ない環境ではスワップを使い尽くしシステムごと落ちる可能性があります"
        "（Raspberry Pi など）。コンパイル中も全機能を利用できます。"
        "【負荷の抑制】端末が忙しい間は自動で一時停止し、空いたら再開します。"
        "優先度も下げて走ります。"
        "【ツールチェーン】cargo が無い端末では、公式の rustup を取得して"
        "プロジェクト配下（.rust-toolchain/）に導入します。チェックサムは"
        "リポジトリに固定してあり、一致しなければ中止します。"
        "既存の Rust 環境は変更しません。不要になれば当該ディレクトリを消すだけです。"
        "Windows では MSVC 版ツールチェーンを使う都合上、Visual Studio の"
        "ビルドツール（リンカ）が別途必要です。"
        "【失敗時】3 回続けて失敗した端末では以後試みません",
        "download",
        category="server",
    ),
    # -- Extract --
    SettingDef("extract_a1111", "bool", "A1111 メタデータ抽出", True, category="extract"),
    SettingDef("extract_comfyui", "bool", "ComfyUI メタデータ抽出", True, category="extract"),
    SettingDef("enable_fts", "bool", "全文検索 (FTS5) 有効 — CLI 専用。サーバーは常に有効", True, category="extract"),
    SettingDef("lowercase_tags", "bool", "タグ小文字化", True, category="extract"),
    SettingDef("compute_hash", "bool", "pHash 計算", False, category="extract"),
    # -- UI --
    SettingDef("timezone", "str", "タイムゾーン", None, category="ui"),
    SettingDef("ui", "str", "UI テーマ (default/custom)", None, category="ui"),
    SettingDef("direct_prompt_convert", "bool", "プロンプト直接変換", False, category="ui"),
    SettingDef("preserve_templates", "bool", "テンプレート保持", True, category="ui"),
    SettingDef("brace_choice", "bool", "波括弧選択", False, category="ui"),

    # -- SNS --
    SettingDef("sns.bluesky.handle", "str", "Bluesky ハンドル", "", category="sns"),
    SettingDef(
        "sns.bluesky.app_password", "str", "Bluesky アプリパスワード", "",
        secret=True, category="sns", op_eligible=True,
    ),
    SettingDef("sns.post_template", "str", "投稿テンプレート", "", category="sns"),
    # -- Backup --
    SettingDef("backup.enabled", "bool", "自動バックアップ有効", True, category="backup"),
    SettingDef("backup.backup_dir", "str", "バックアップ先ディレクトリ", "", category="backup"),
    SettingDef("backup.max_generations", "int", "最大世代数", 5, category="backup"),
    SettingDef(
        "backup.periodic_interval_hours", "int",
        "定期バックアップ間隔 (時間)", 24, category="backup",
    ),
    SettingDef(
        "backup.backup_on_scan_complete", "bool",
        "スキャン完了時にバックアップ", True, category="backup",
    ),
    SettingDef("backup.cooldown_minutes", "int", "クールダウン (分)", 5, category="backup"),
    # -- AI Analysis API Keys --
    SettingDef(
        "ai_analysis.api_key", "str", "Anthropic (Claude) API key", "",
        secret=True, category="ai_analysis", op_eligible=True,
    ),
    SettingDef(
        "ai_analysis.openai_api_key", "str", "OpenAI API key", "",
        secret=True, category="ai_analysis", op_eligible=True,
    ),
    SettingDef(
        "ai_analysis.openai_compat_api_key", "str", "OpenAI Compatible API key", "",
        secret=True, category="ai_analysis", op_eligible=True,
    ),
    # -- Archive Cleanup LLM API Keys --
    SettingDef(
        "archive_cleanup_llm.api_key", "str", "Archive Cleanup Anthropic API key", "",
        secret=True, category="archive_cleanup_llm", op_eligible=True,
    ),
    SettingDef(
        "archive_cleanup_llm.openai_api_key", "str", "Archive Cleanup OpenAI API key", "",
        secret=True, category="archive_cleanup_llm", op_eligible=True,
    ),
    SettingDef(
        "archive_cleanup_llm.openai_compat_api_key", "str", "Archive Cleanup OpenAI Compat API key", "",
        secret=True, category="archive_cleanup_llm", op_eligible=True,
    ),
    # -- NovelAI --
    SettingDef(
        "extensions.builtin_nai_bridge.api_token", "str", "NovelAI API トークン", "",
        secret=True, category="nai_bridge", op_eligible=True,
    ),
    # -- Webhook --
    SettingDef(
        "webhook_secret", "str", "Webhook 署名シークレット", None,
        secret=True, category="webhook", op_eligible=True,
    ),
    # -- Video --
    SettingDef("video_analysis.enabled", "bool", "動画解析有効", True, category="video"),
    SettingDef("video_analysis.keyframe_count", "int", "キーフレーム数", 4, category="video"),
    SettingDef(
        "video_analysis.strategy", "str", "キーフレーム戦略", "uniform",
        category="video", options=["uniform", "scene"],
    ),
    SettingDef("video_analysis.scene_threshold", "float", "シーン閾値", 0.4, category="video"),
    # -- Archive --
    SettingDef("archive_throttle_ms", "int", "アーカイブスロットル (ms)", 20, category="extract"),
    # -- Agent Safety --
    SettingDef(
        "agent_safety.circuit_breaker.enabled", "bool",
        "Circuit Breaker 有効", True, category="agent_safety",
    ),
    SettingDef(
        "agent_safety.circuit_breaker.max_actions_per_minute", "int",
        "毎分最大アクション数", 60, category="agent_safety",
    ),
    SettingDef(
        "agent_safety.circuit_breaker.max_identical_consecutive", "int",
        "同一呼び出し連続最大回数", 3, category="agent_safety",
    ),
    SettingDef(
        "agent_safety.circuit_breaker.max_same_tool_per_minute", "int",
        "同一ツール毎分最大回数", 15, category="agent_safety",
    ),
    SettingDef(
        "agent_safety.circuit_breaker.max_consecutive_errors", "int",
        "連続エラー最大回数", 10, category="agent_safety",
    ),
    SettingDef(
        "agent_safety.circuit_breaker.error_rate_threshold", "float",
        "エラーレート閾値 (0.0-1.0)", 0.5, category="agent_safety",
    ),
    SettingDef(
        "agent_safety.circuit_breaker.cooldown_seconds", "int",
        "Circuit Breaker クールダウン (秒)", 60, category="agent_safety",
    ),
    SettingDef(
        "agent_safety.budget.preset", "str",
        "Budget プリセット", "standard",
        category="agent_safety",
        options=["conservative", "standard", "power_user", "unlimited"],
    ),
    # -- Hailo Remote Tagger --
    SettingDef("hailo_tagger.enabled", "bool", "Hailo Remote Tagger 有効", False, category="hailo_tagger"),
    SettingDef("hailo_tagger.endpoint_url", "str", "Hailo Tagger Pi エンドポイント URL", "", category="hailo_tagger"),
    SettingDef("hailo_tagger.threshold", "float", "タグ信頼度閾値", 0.35, category="hailo_tagger"),
    SettingDef("hailo_tagger.timeout", "int", "リクエストタイムアウト (秒)", 30, category="hailo_tagger"),
]

# Reverse lookup map: key -> SettingDef
_SCHEMA_MAP: dict[str, SettingDef] = {s.key: s for s in SETTINGS_SCHEMA}


def register_dynamic_setting(setting: SettingDef) -> None:
    """Dynamically register a SettingDef (overwrites on duplicate)."""
    _SCHEMA_MAP[setting.key] = setting
    # Avoid duplicates in list
    for i, s in enumerate(SETTINGS_SCHEMA):
        if s.key == setting.key:
            SETTINGS_SCHEMA[i] = setting
            return
    SETTINGS_SCHEMA.append(setting)


def unregister_dynamic_setting(key: str) -> None:
    """Remove a dynamically registered SettingDef."""
    _SCHEMA_MAP.pop(key, None)
    SETTINGS_SCHEMA[:] = [s for s in SETTINGS_SCHEMA if s.key != key]


def get_schema_def(key: str) -> SettingDef | None:
    """Return the SettingDef for the given key."""
    return _SCHEMA_MAP.get(key)


def get_schema() -> list[dict[str, Any]]:
    """Serialize the schema for API responses."""
    result = []
    for s in SETTINGS_SCHEMA:
        d: dict[str, Any] = {
            "key": s.key,
            "type": s.type,
            "description": s.description,
            "default": s.default,
            "secret": s.secret,
            "category": s.category,
            "op_eligible": s.op_eligible,
        }
        if s.options:
            d["options"] = s.options
        result.append(d)
    return result


# ── Dot-notation <-> Nested dict Conversion ────────────────────────────────


def resolve_dotted_key(config: dict[str, Any], key: str) -> Any:
    """Get a value from a nested dict using dot-notation key.

    Example: resolve_dotted_key(cfg, "server.pin") -> cfg["server"]["pin"]
    Returns None if the key does not exist.
    """
    parts = key.split(".")
    current = config
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def set_dotted_key(config: dict[str, Any], key: str, value: Any) -> None:
    """Set a value in a nested dict using dot-notation key.

    Example: set_dotted_key(cfg, "server.pin", "1234") -> cfg["server"]["pin"] = "1234"
    Automatically creates intermediate dicts if they don't exist.
    """
    parts = key.split(".")
    current = config
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value
