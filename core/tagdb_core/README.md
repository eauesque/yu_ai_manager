# core/tagdb_core

`tagdb_*` 系（非 legacy）の集約ディレクトリ。

- `tool/`: CLI入口/コマンド配線
- `search/`: 検索/重複検出
- `db_schema/`: 旧DBスキーマ補助
- `media/`: 旧メディア抽出補助
- `scan_metadata/`: 旧メタデータ抽出補助

依存方向:
- `tagdb_tool.py`, `cli/*` -> `core/tagdb_core/tool/tagdb_tool_impl.py`
- `core/tagdb_*.py` はトップレベル互換ラッパー
- `core/tagdb_*_legacy.py` は `core/legacy_compat/*` へ直結
