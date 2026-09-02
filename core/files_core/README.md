# core/files_core

ファイル配信/サムネイル/メディア補助の実装本体。

- `media*.py`: メディア種別・プレースホルダ・ZIP解決
- `original*.py`: 原寸配信
- `thumbnail*.py`: サムネイル生成/ZIPハンドラ

依存方向: `core/files_*.py` (compat) -> `core/files_core/*`
