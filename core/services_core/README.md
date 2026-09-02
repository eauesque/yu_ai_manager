# core/services_core

単独ユーティリティ系サービス実装の集約。

- `db_state.py`: アプリDB状態
- `db_scan_progress.py`: スキャン進捗共有状態
- `market_quotes.py`: 市況取得（ボスモード向け）
- `search_cli.py`: 旧CLI検索補助

依存方向:
- `core/db.py` -> `core/services_core/{db_state,db_scan_progress}.py`
- `routes/search.py` -> `core/services_core/market_quotes.py`
- 互換: `core/{db_state,db_scan_progress,market_quotes,search_cli}.py` は再エクスポート
