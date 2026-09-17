# core/zip_core

ZIPパス/ZIP内メタデータ抽出の実装本体。

- `zip_support.py`: 公開集約
- `zip_support_core.py`: ZIP I/O・パス判定
- `zip_support_extract.py`: ZIP内メタデータ抽出
- `zip_support_extract_dispatch.py`: 拡張子別ディスパッチ

依存方向: `core/zip_support*.py` (compat) -> `core/zip_core/*`
