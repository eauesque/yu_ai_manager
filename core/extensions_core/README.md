# core/extensions_core

拡張機能システムの実装本体。

- `extensions_defs*.py`: マニフェスト型/定数/バリデーション
- `extensions_loader*.py`: manifest/module 読み込み
- `extensions_hooks*.py`: hook registry/invoke/view
- `extensions_manager*.py`: 拡張のライフサイクル管理
- `extensions_api_*.py`: API向け操作補助
- `extensions_admin.py`: install/enable など管理補助

依存方向: `core/extensions*.py` (compat) -> `core/extensions_core/extensions_*.py`
