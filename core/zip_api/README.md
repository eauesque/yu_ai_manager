# routes/zip_files_api

`routes/zip_files.py` の ZIP 関連実装。

- `ops.py`: 公開ファサード
- `info_ops.py`: ZIPメンバー情報/フォルダオープン
- `extract_ops.py`: 解凍処理

依存方向: `routes/zip_files.py` -> `routes/zip_files_api/*` -> `core/zip_support*`, `core/db`
