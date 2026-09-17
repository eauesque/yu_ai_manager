# scan_roots_api

責務: scan-roots 系 API のルート登録・設定操作・scan-all 実行。

## Files

- `routes.py`: ルート登録の入口
- `routes_config.py`: `/api/checkpoints`, `/api/scan-roots*`
- `routes_scan.py`: `/api/scan-all`
- `scan_all.py`: scan-all 実行オーケストレーション
- `ops.py`: 互換ファサード
- `ops_read.py`: 設定読み取り
- `ops_write.py`: 設定更新
- `checkpoints.py`: チェックポイント一覧取得

## Dependency

- `routes/scan_roots.py -> routes.py`
- `routes.py -> (routes_config.py, routes_scan.py)`
- `routes_scan.py -> scan_all.py -> ops.py`
- `ops.py -> (ops_read.py, ops_write.py)`

## Notes

- 更新系ロジックは `ops_write.py` に集約する。
