# core/helpers_core

共通ヘルパの実装本体。

- `helpers.py`: 互換用の公開集約。内部コードはなるべく個別モジュールを直接参照する
- `helpers_runtime.py`: 起動時ユーティリティの公開窓口（互換レイヤー）
- `runtime_vendor_libs.py`: vendor JS の取得処理
- `core/services_core/thumbnail_cache_cleanup.py`: サムネキャッシュ掃除本体
- `helpers_text_path.py`: 文字列/パス正規化

依存方向: `core/helpers*.py` (compat) -> `core/helpers_core/*`
