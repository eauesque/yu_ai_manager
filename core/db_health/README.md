# core/db_health

DBヘルスチェック/修復ロジックの実体。

- `integrity.py`: 整合性検査
- `repair.py`: 修復ファサード
- `repair_auto.py`: VACUUM/REINDEX/ANALYZE
- `repair_dump.py`: dump/restore
- `ops.py`: CLI/API向け公開オペレーション

依存方向: `core/db_health_*.py` (compat) -> `core/db_health/*`
