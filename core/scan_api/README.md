# routes/scan_api

`routes/scan.py` の scan 制御ロジック。

- `ops.py`: 公開ファサード
- `ops_runtime.py`: ジョブ実行/状態連携
- `ops_state.py`: 中断状態/復旧系

依存方向: `routes/scan.py` -> `routes/scan_api/*` -> `core/jobs*`, `core/scanner*`
