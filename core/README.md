# core

アプリ本体ロジックのディレクトリ。

## Layout

- `core/__init__.py` のみを root に置き、互換 import alias を初期化
- 実体ロジックは以下の下位ディレクトリに集約
  - `core/web/`, `core/api_services/`, `core/infra_core/`
  - `core/configuration/`, `core/services_core/`, `core/extensions_core/`
  - `core/files_core/`, `core/models_core/`, `core/scan_core/`, `core/schema_core/`
  - `core/sd_nai_core/`, `core/stats_core/`, `core/tagdb_core/`, `core/zip_core/`
  - `core/legacy/`, `core/legacy_compat/`
  - `core/extractors/`, `core/parsers/`, `core/prompt/`, `core/query/`, `core/scan/`

## Compatibility Policy

- 旧 `core.<module>` 互換は `core/compat/module_aliases.py` に追加して維持
- root 直下に薄い再エクスポートファイルは増やさない
- 新規実装は必ず実体ディレクトリ側に追加する

## Dependency Direction

- `routes/*` -> `core/*`（一方向）
- 上位オーケストレーション層 -> 下位実装層（逆参照禁止）
- `core/legacy/*` は既存入口の互換目的に限定
