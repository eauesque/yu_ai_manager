# core/scan_core

スキャナ実装本体。

- `scanner.py`: 入口（通常/ZIP切替）
- `scanner_io.py`: 列挙/解像度抽出
- `scanner_regular*.py`: 通常ファイルの抽出/永続化処理
- `scanner_state.py`: extension manager 連携状態
- `scan_state.py`: 中断再開用の状態永続化

依存方向: `core/scanner*.py`, `core/scan_state.py` (compat) -> `core/scan_core/*`

内部コードは compat facade より `core/scan_core/*` の実装モジュールを直接参照する。
