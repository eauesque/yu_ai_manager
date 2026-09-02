# core/schema_core

DBスキーマ接続/初期化/マイグレーションの実装本体。

- `schema.py`: 公開集約
- `schema_connect.py`: DB接続と列存在チェック
- `schema_constants.py`: バージョン定数
- `schema_sql.py`: 初期化SQL（ベース/FTS）
- `schema_init.py`: 初期テーブル生成のエントリ
- `schema_migrate_version.py`: スキーマバージョン取得/更新
- `schema_migrate_steps.py`: 各マイグレーションステップ実装
- `schema_migrate.py`: スキーマ移行エントリ

依存方向: `core/schema*.py` (compat) -> `core/schema_core/*`
