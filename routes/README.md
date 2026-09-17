# routes

HTTP API / page ルートの入口ディレクトリ。

## Entrypoints

- `routes/pages.py`, `routes/search.py`, `routes/files.py`, `routes/tools.py`, `routes/stats.py`, `routes/share.py`, `routes/scan.py`, `routes/scan_roots.py`

## Feature Subdirs

- `routes/share_ops/`: share payload 生成ロジック
- `routes/scan_roots_api/`: scan-roots 系 API の登録/操作/scan-all
- `routes/debug_api/`: debug 系 API
- `routes/files_api/`: files/detail/media 系 API
- `routes/scan_api/`: scan 実行系 API
- `routes/tools_api/`: tools 系 API
- `routes/zip_files_api/`: zip member / extract 系 API

## Rule

- ルート定義は入口ファイルに置き、複雑ロジックは `*_ops` / feature dir に退避する。
- 新規 feature はまずサブディレクトリ化を検討する。
- 依存方向は `routes/*.py` -> `routes/<feature>_api/*.py` -> `core/*.py` を守る。
