# routes/files_api

`routes/files.py` の補助実装。

- `detail_ops.py`, `detail_payload.py`: `/api/file/<id>` 応答組み立て
- `convert_ops.py`: `/api/convert` 応答組み立て

依存方向: `routes/files.py` -> `routes/files_api/*` -> `core/files_*`, `core/sd_nai_convert_*`
