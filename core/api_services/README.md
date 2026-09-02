# core/api_services

Route 層向け API サービス集約（薄いファサード）。

- `analysis_api_service.py` -> `core.analysis_api.*`
- `search_api_service.py` -> `core.search_api.*`
- `stats_api_data.py` -> `core.stats_api.*`

依存方向: `routes/*` -> `core/api_services/*` -> `core/{analysis_api,search_api,stats_api}/*`
