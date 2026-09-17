# core/configuration

設定読み込み/修復ロジックの実体。

- `defaults.py`: 既定値
- `json_io.py`: I/O 集約
- `json_readers.py`: JSON/YAML 安全読み込み
- `json_repair.py`: 不正エスケープ修復
- `json_rw.py`: config.json 読み書き

依存方向: `core/config*.py` (compat) -> `core/configuration/*`
