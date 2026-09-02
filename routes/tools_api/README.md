# routes/tools_api

`routes/tools.py` から登録される Tools API 群。

- `routes_ops.py`: 操作系 API ルート登録
- `routes_misc.py`: 補助 API ルート登録
- `ops.py`: 共通ファサード
- `*_ops.py`: 機能別オペレーション

依存方向: `routes/tools.py` -> `routes/tools_api/*` -> `core/*`
