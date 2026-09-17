# core/cleanup_core

DBクリーンアップ処理の実装本体。

- `cleanup.py`: 公開集約
- `cleanup_files.py`: files/path 整理
- `cleanup_tags.py`: tag 正規化入口
- `cleanup_tag_*.py`: 正規化 split/merge 各フェーズ

依存方向: `core/cleanup*.py` (compat) -> `core/cleanup_core/*`
