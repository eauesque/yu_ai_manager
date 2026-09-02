# routes/debug_api

`routes/debug.py` から呼ばれるデバッグ系 API 実装。

- `ops.py`: 公開ファサード
- `file_meta_ops.py`: ファイルメタ確認
- `model_ops.py`: model_name 監視
- `roots_ops.py`: scanned roots 取得

依存方向: `routes/debug.py` -> `routes/debug_api/*` -> `core/*`
