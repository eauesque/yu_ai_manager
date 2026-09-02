# core/infra_core

横断的に使う低レイヤーユーティリティ実装。

- `api_errors.py`: APIエラー応答整形
- `debug_log.py`: 構造化デバッグログ
- `file_hash.py`: ファイルETag相当計算
- `progress.py`: 進捗コールバック実装

依存方向: 各 feature -> `core/infra_core/*`
互換: `core/{api_errors,debug_log,file_hash,progress}.py` は薄い再エクスポート
