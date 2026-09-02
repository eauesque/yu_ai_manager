# API エンドポイント一覧（自動生成）

> このファイルは `scripts/gen_api_docs.py` で自動生成されます。手動編集しないでください。
> 生成元: `routes/`, `extensions/`, `core/lan_share/`

**合計**: 702 エンドポイント

## 目次

- [検索](#検索) (9件)
- [ファイル](#ファイル) (23件)
- [スキャン](#スキャン) (27件)
- [タグ](#タグ) (6件)
- [レーティング・お気に入り](#レーティングお気に入り) (9件)
- [コレクション](#コレクション) (9件)
- [WD-Tagger](#wd-tagger) (35件)
- [AI 分析](#ai-分析) (33件)
- [エージェント](#エージェント) (30件)
- [LLM ルータ](#llm-ルータ) (4件)
- [Bridge](#bridge) (1件)
- [設定](#設定) (31件)
- [拡張機能](#拡張機能) (27件)
- [管理](#管理) (20件)
- [SSE・ログ](#sseログ) (2件)
- [メッシュ推論](#メッシュ推論) (4件)
- [Hailo](#hailo) (19件)
- [LAN 共有](#lan-共有) (6件)
- [統計](#統計) (8件)
- [プロンプト管理](#プロンプト管理) (12件)
- [チャット](#チャット) (19件)
- [SNS・ストリーム](#snsストリーム) (55件)
- [MCP・内部 API](#mcp内部-api) (313件)

## 検索

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `GET` | `/api/search` | — | `routes/search.py` |
| `GET` | `/api/search-count` | — | `routes/search.py` |
| `GET` | `/api/search-grouped` | — | `routes/search.py` |
| `GET` | `/api/search-grouped/warm` | — | `routes/search.py` |
| `POST` | `/api/search-union` | — | `routes/search.py` |
| `GET` | `/api/server-info` | — | `routes/search.py` |
| `GET` | `/api/suggest` | — | `routes/search.py` |
| `GET` | `/api/suggest/embedding` | — | `routes/search.py` |
| `GET` | `/api/suggest/lora` | — | `routes/search.py` |

## ファイル

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `GET` | `/api/container-thumb-ids` | — | `routes/files.py` |
| `POST` | `/api/convert` | — | `routes/files.py` |
| `GET` | `/api/file-info/<int:file_id>` | File detail info (including ZIP-related info). | `routes/zip_files.py` |
| `GET` | `/api/file/<int:file_id>` | — | `routes/files.py` |
| `GET` | `/api/files` | — | `extensions/builtin_md_viewer/core_impl/api_routes_files.py` |
| `GET` | `/api/files/<int:file_id>` | — | `extensions/builtin_md_viewer/core_impl/api_routes_files.py` |
| `GET` | `/api/files/<int:file_id>/analysis-trace` | — | `routes/file_trace.py` |
| `GET` | `/api/folders` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api_routes_folders.py` |
| `POST` | `/api/folders` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api_routes_folders.py` |
| `DELETE` | `/api/folders/<int:fid>` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api_routes_folders.py` |
| `PUT` | `/api/folders/<int:fid>` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api_routes_folders.py` |
| `GET` | `/api/group-members` | — | `routes/files.py` |
| `GET` | `/api/groups-index` | — | `routes/files.py` |
| `GET` | `/api/groups-index/warm` | — | `routes/files.py` |
| `POST` | `/api/open-folder/<int:file_id>` | Open file location in Explorer/Finder. | `routes/zip_files.py` |
| `GET` | `/api/original/<int:file_id>` | — | `routes/files.py` |
| `GET` | `/api/outputs` | — | `extensions/builtin_freeze_pullback/core_impl/api_output_routes.py` |
| `DELETE` | `/api/outputs/<filename>` | — | `extensions/builtin_freeze_pullback/core_impl/api_output_routes.py` |
| `GET` | `/api/outputs/<filename>` | — | `extensions/builtin_freeze_pullback/core_impl/api_output_routes.py` |
| `GET` | `/api/preview/<int:file_id>` | — | `routes/files.py` |
| `GET` | `/api/thumbnail/<int:file_id>` | — | `routes/files.py` |
| `POST` | `/api/thumbnails/batch` | — | `routes/files.py` |
| `POST` | `/api/thumbnails/warmup` | — | `routes/files.py` |

## スキャン

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `POST` | `/api/scan` | — | `extensions/builtin_cross_search/core_impl/api.py` |
| `POST` | `/api/scan-all` | Scan all scan roots (background). | `routes/scan_roots_api/routes_scan.py` |
| `GET` | `/api/scan-errors` | List scan errors (encoding/timeout/FS). | `routes/scan.py` |
| `POST` | `/api/scan-errors/<int:error_id>/resolve` | Mark a scan error as resolved. | `routes/scan.py` |
| `POST` | `/api/scan-errors/clear` | Bulk-delete resolved scan errors. | `routes/scan.py` |
| `GET` | `/api/scan-roots` | Get list of registered scan roots. | `routes/scan_roots_api/routes_config.py` |
| `POST` | `/api/scan-roots` | Add a scan root. | `routes/scan_roots_api/routes_config.py` |
| `DELETE` | `/api/scan-roots/<int:idx>` | — | `extensions/builtin_cross_search/core_impl/api.py` |
| `DELETE` | `/api/scan-roots/<int:index>` | Remove a scan root. | `routes/scan_roots_api/routes_config.py` |
| `PUT` | `/api/scan-roots/<int:index>` | Edit scan root path. | `routes/scan_roots_api/routes_config.py` |
| `POST` | `/api/scan-roots/<int:index>/toggle` | Toggle scan root enabled/disabled. | `routes/scan_roots_api/routes_config.py` |
| `POST` | `/api/scan-roots/batch-toggle` | Enable or disable all scan roots at once. | `routes/scan_roots_api/routes_config.py` |
| `POST` | `/api/scan-roots/reorder` | Reorder scan roots. | `routes/scan_roots_api/routes_config.py` |
| `POST` | `/api/scan/cancel` | Cancel scan API. | `routes/scan.py` |
| `POST` | `/api/scan/dismiss` | Dismiss interrupted scan state. | `routes/scan.py` |
| `GET` | `/api/scan/history` | Return persistent scan history (newest first). | `routes/scan.py` |
| `POST` | `/api/scan/history/clear` | Clear all scan history entries. | `routes/scan.py` |
| `GET` | `/api/scan/interrupted` | Get previously interrupted scan info. | `routes/scan.py` |
| `GET` | `/api/scan/queue` | List scan queue items. | `routes/scan.py` |
| `DELETE` | `/api/scan/queue/<queue_id>` | Remove individual item from the queue. | `routes/scan.py` |
| `POST` | `/api/scan/queue/clear` | Clear all items from the queue. | `routes/scan.py` |
| `POST` | `/api/scan/resume` | Resume interrupted scan (force=False). | `routes/scan.py` |
| `POST` | `/api/scan/start` | Start scan API. | `routes/scan.py` |
| `GET` | `/api/scan/status` | Get scan progress API (backward-compatible + job manager integration). | `routes/scan.py` |
| `POST` | `/api/scan/stop` | — | `extensions/builtin_cross_search/core_impl/api.py` |
| `GET` | `/api/scanned-roots` | Extract root directories from files registered in the DB. | `routes/debug.py` |
| `POST` | `/api/scanned-roots/purge` | Permanently delete file records under the specified path from the DB. | `routes/debug.py` |

## タグ

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `GET` | `/api/tags` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api_routes_tags.py` |
| `POST` | `/api/tags` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api_routes_tags.py` |
| `DELETE` | `/api/tags/<int:tid>` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api_routes_tags.py` |
| `POST` | `/api/tags/batch-set` | — | `routes/tags.py` |
| `POST` | `/api/tags/dedup` | — | `routes/tags.py` |
| `GET` | `/api/tags/suggest` | Return tag suggestions for autocomplete. | `routes/tags.py` |

## レーティング・お気に入り

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `GET` | `/api/favorites/check` | — | `routes/favorites.py` |
| `GET` | `/api/favorites/check_collections` | Return which collections a file belongs to. | `routes/favorites.py` |
| `GET` | `/api/favorites/list` | — | `routes/favorites.py` |
| `POST` | `/api/favorites/toggle` | — | `routes/favorites.py` |
| `POST` | `/api/ratings/batch` | — | `routes/ratings.py` |
| `POST` | `/api/ratings/batch-set` | — | `routes/ratings.py` |
| `GET` | `/api/ratings/get` | — | `routes/ratings.py` |
| `POST` | `/api/ratings/set` | — | `routes/ratings.py` |
| `GET` | `/api/ratings/stats` | — | `routes/ratings.py` |

## コレクション

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `GET` | `/api/collections` | — | `routes/collections.py` |
| `POST` | `/api/collections` | — | `routes/collections.py` |
| `DELETE` | `/api/collections/<int:collection_id>` | — | `routes/collections.py` |
| `PUT` | `/api/collections/<int:collection_id>` | — | `routes/collections.py` |
| `POST` | `/api/collections/<int:collection_id>/batch-add` | — | `routes/collections.py` |
| `POST` | `/api/collections/<int:collection_id>/batch-remove` | — | `routes/collections.py` |
| `GET` | `/api/collections/<int:collection_id>/export` | Export collection with format query param: recipe_csv \| recipe_json. | `routes/collections.py` |
| `GET` | `/api/collections/<int:collection_id>/export/csv` | Export collection files as CSV. | `routes/collections.py` |
| `POST` | `/api/collections/reorder` | — | `routes/collections.py` |

## WD-Tagger

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `GET` | `/api/tagger-servers` | — | `routes/tagger_servers.py` |
| `POST` | `/api/tagger-servers/batch` | — | `routes/tagger_servers.py` |
| `POST` | `/api/tagger-servers/batch/cancel` | Cancel running tagger cluster batch job. | `routes/tagger_servers.py` |
| `GET` | `/api/tagger-servers/health` | Check health of all mesh tagger peers. | `routes/tagger_servers.py` |
| `GET` | `/api/tagger-servers/stats` | — | `routes/tagger_servers.py` |
| `DELETE` | `/api/tagger-servers/tags/<int:file_id>` | — | `routes/tagger_servers.py` |
| `GET` | `/api/tagger-servers/tags/<int:file_id>` | — | `routes/tagger_servers.py` |
| `GET` | `/api/wd-tagger/active-model` | — | `routes/wd_tagger_admin_routes.py` |
| `PUT` | `/api/wd-tagger/active-model` | — | `routes/wd_tagger_admin_routes.py` |
| `POST` | `/api/wd-tagger/batch` | Legacy batch endpoint — shim over retag_jobs.start_batch. | `routes/wd_tagger_batch_routes.py` |
| `POST` | `/api/wd-tagger/batch/cancel` | — | `routes/wd_tagger_batch_routes.py` |
| `GET` | `/api/wd-tagger/config` | — | `routes/wd_tagger_config_routes.py` |
| `POST` | `/api/wd-tagger/config` | — | `routes/wd_tagger_config_routes.py` |
| `POST` | `/api/wd-tagger/model/download` | — | `routes/wd_tagger_admin_routes.py` |
| `GET` | `/api/wd-tagger/model/status` | — | `routes/wd_tagger_admin_routes.py` |
| `GET` | `/api/wd-tagger/profiles` | — | `routes/wd_tagger_admin_routes.py` |
| `POST` | `/api/wd-tagger/profiles` | — | `routes/wd_tagger_admin_routes.py` |
| `DELETE` | `/api/wd-tagger/profiles/<id_>` | — | `routes/wd_tagger_admin_routes.py` |
| `GET` | `/api/wd-tagger/profiles/<id_>` | — | `routes/wd_tagger_admin_routes.py` |
| `PUT` | `/api/wd-tagger/profiles/<id_>` | — | `routes/wd_tagger_admin_routes.py` |
| `POST` | `/api/wd-tagger/profiles/<id_>/test` | — | `routes/wd_tagger_admin_routes.py` |
| `POST` | `/api/wd-tagger/retag/backfill` | — | `routes/wd_tagger_retag_routes.py` |
| `POST` | `/api/wd-tagger/retag/batch` | — | `routes/wd_tagger_retag_routes.py` |
| `POST` | `/api/wd-tagger/retag/cancel` | — | `routes/wd_tagger_retag_routes.py` |
| `POST` | `/api/wd-tagger/retag/query` | — | `routes/wd_tagger_retag_routes.py` |
| `POST` | `/api/wd-tagger/retag/single` | — | `routes/wd_tagger_retag_routes.py` |
| `GET` | `/api/wd-tagger/stats` | — | `routes/wd_tagger_batch_routes.py` |
| `POST` | `/api/wd-tagger/tag/<int:file_id>` | — | `routes/wd_tagger_tag_routes.py` |
| `DELETE` | `/api/wd-tagger/tags/<int:file_id>` | — | `routes/wd_tagger_tag_routes.py` |
| `GET` | `/api/wd-tagger/tags/<int:file_id>` | — | `routes/wd_tagger_tag_routes.py` |
| `DELETE` | `/api/wd-tagger/tags/batch` | — | `routes/wd_tagger_tag_routes.py` |
| `GET` | `/api/wd-tagger/untagged` | — | `routes/wd_tagger_batch_routes.py` |
| `GET` | `/api/wd-tagger/vlm/models` | — | `routes/wd_tagger_admin_routes.py` |
| `GET` | `/api/wd-tagger/vlm/test` | — | `routes/wd_tagger_admin_routes.py` |
| `GET` | `/api/wd-tagger/xmp/<int:file_id>` | — | `routes/wd_tagger_admin_routes.py` |

## AI 分析

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `POST` | `/api/analysis/analyze/<int:file_id>` | — | `routes/analysis_job_routes.py` |
| `GET` | `/api/analysis/available-engines` | — | `routes/analysis_config_routes.py` |
| `POST` | `/api/analysis/batch` | — | `routes/analysis_job_routes.py` |
| `POST` | `/api/analysis/batch/cancel` | — | `routes/analysis_job_routes.py` |
| `GET` `POST` | `/api/analysis/config` | — | `routes/analysis_config_routes.py` |
| `GET` | `/api/analysis/ollama/models` | — | `routes/analysis_config_routes.py` |
| `POST` | `/api/analysis/ollama/test` | — | `routes/analysis_config_routes.py` |
| `GET` | `/api/analysis/openai-compat/models` | — | `routes/analysis_config_routes.py` |
| `POST` | `/api/analysis/openai-compat/test` | — | `routes/analysis_config_routes.py` |
| `GET` | `/api/analysis/result/<int:file_id>` | — | `routes/analysis_job_routes.py` |
| `GET` | `/api/analysis/servers` | — | `routes/analysis_server_routes.py` |
| `POST` | `/api/analysis/servers` | — | `routes/analysis_server_routes.py` |
| `DELETE` | `/api/analysis/servers/<server_id>` | — | `routes/analysis_server_routes.py` |
| `PUT` | `/api/analysis/servers/<server_id>` | — | `routes/analysis_server_routes.py` |
| `POST` | `/api/analysis/servers/<server_id>/activate` | — | `routes/analysis_server_routes.py` |
| `POST` | `/api/analysis/servers/<server_id>/test` | — | `routes/analysis_server_routes.py` |
| `GET` | `/api/analysis/servers/discovered` | — | `routes/analysis_server_routes.py` |
| `DELETE` | `/api/analysis/servers/discovered/ignore` | — | `routes/analysis_server_routes.py` |
| `POST` | `/api/analysis/servers/discovered/ignore` | — | `routes/analysis_server_routes.py` |
| `DELETE` | `/api/analysis/servers/discovered/match` | — | `routes/analysis_server_routes.py` |
| `POST` | `/api/analysis/servers/discovered/match` | — | `routes/analysis_server_routes.py` |
| `POST` | `/api/analysis/servers/discovered/register` | — | `routes/analysis_server_routes.py` |
| `POST` | `/api/analysis/servers/discovered/test` | — | `routes/analysis_server_routes.py` |
| `POST` | `/api/analysis/servers/migrate` | — | `routes/analysis_server_routes.py` |
| `PUT` | `/api/analysis/servers/reorder` | — | `routes/analysis_server_routes.py` |
| `GET` | `/api/analysis/stats` | — | `routes/analysis_job_routes.py` |
| `POST` | `/api/analysis/trends` | — | `routes/analysis_job_routes.py` |
| `GET` | `/api/analysis/trends/history` | — | `routes/analysis_server_routes.py` |
| `DELETE` | `/api/analysis/trends/history/<int:history_id>` | — | `routes/analysis_server_routes.py` |
| `POST` | `/api/video-analysis/analyze/<int:file_id>` | Analyze video file via multi-keyframe vision analysis. | `extensions/builtin_video_analysis/video_analysis_ext.py` |
| `GET` | `/api/video-analysis/config` | — | `routes/video_analysis.py` |
| `POST` | `/api/video-analysis/config` | — | `routes/video_analysis.py` |
| `GET` | `/api/video-analysis/status` | Return video analysis status info (ffmpeg availability, counts). | `routes/video_analysis.py` |

## エージェント

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `GET` | `/api/agent/anomaly` | — | `routes/agent_governance_audit.py` |
| `GET` | `/api/agent/anomaly/alerts` | — | `routes/agent_governance_audit.py` |
| `POST` | `/api/agent/anomaly/reset` | — | `routes/agent_governance_audit.py` |
| `GET` | `/api/agent/approval` | — | `routes/agent_governance_approval.py` |
| `POST` | `/api/agent/approval/<request_id>` | — | `routes/agent_governance_approval.py` |
| `GET` | `/api/agent/approval/history` | — | `routes/agent_governance_approval.py` |
| `GET` | `/api/agent/audit` | — | `routes/agent_governance_audit.py` |
| `POST` | `/api/agent/audit/acknowledge/<int:audit_id>` | — | `routes/agent_governance_audit.py` |
| `GET` | `/api/agent/audit/log` | — | `routes/agent_governance_audit.py` |
| `POST` | `/api/agent/audit/report` | — | `routes/agent_governance_audit.py` |
| `GET` | `/api/agent/audit/verify` | Verify the hash chain integrity of the audit_log table. | `routes/agent_governance_audit.py` |
| `GET` | `/api/agent/auto-approve` | — | `routes/agent_governance_scope.py` |
| `POST` | `/api/agent/auto-approve` | — | `routes/agent_governance_scope.py` |
| `DELETE` | `/api/agent/auto-approve/<int:index>` | — | `routes/agent_governance_scope.py` |
| `GET` | `/api/agent/budget` | Get budget remaining. | `routes/agent_api_core.py` |
| `POST` | `/api/agent/budget/reset` | Reset budget counter. | `routes/agent_api_core.py` |
| `GET` | `/api/agent/circuit-breaker` | Get Circuit Breaker state. | `routes/agent_api_core.py` |
| `POST` | `/api/agent/circuit-breaker/reset` | Reset Circuit Breaker to closed state. | `routes/agent_api_core.py` |
| `GET` | `/api/agent/journal` | Search Action Journal. | `routes/agent_api_core.py` |
| `GET` | `/api/agent/journal/stats` | Get Action Journal statistics. | `routes/agent_api_core.py` |
| `POST` | `/api/agent/kill` | Activate Kill Switch. | `routes/agent_api_core.py` |
| `POST` | `/api/agent/resume` | Deactivate Kill Switch. | `routes/agent_api_core.py` |
| `GET` | `/api/agent/scope` | — | `routes/agent_governance_scope.py` |
| `DELETE` | `/api/agent/scope/<session_id>` | — | `routes/agent_governance_scope.py` |
| `GET` | `/api/agent/scope/<session_id>` | — | `routes/agent_governance_scope.py` |
| `POST` | `/api/agent/scope/<session_id>` | — | `routes/agent_governance_scope.py` |
| `GET` | `/api/agent/status` | Unified status: Kill Switch + Circuit Breaker + Budget + per-process states. | `routes/agent_api_core.py` |
| `GET` | `/api/agent/tool-levels` | — | `routes/agent_governance_scope.py` |
| `POST` | `/api/agent/undo/<int:journal_id>` | — | `routes/agent_governance_approval.py` |
| `GET` | `/api/agent/undoable` | — | `routes/agent_governance_approval.py` |

## LLM ルータ

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `POST` | `/api/llm_router/backends/<alias>/disable` | — | `routes/llm_router_admin.py` |
| `POST` | `/api/llm_router/backends/<alias>/enable` | — | `routes/llm_router_admin.py` |
| `POST` | `/api/llm_router/refresh` | Force a fresh probe for one or all backends. | `routes/llm_router_admin.py` |
| `GET` | `/api/llm_router/status` | Single snapshot used to populate the entire dashboard. | `routes/llm_router_admin.py` |

## Bridge

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `GET` `POST` | `/sdapi/v1/<path:subpath>` | — | `routes/gateway_sd.py` |

## 設定

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `GET` | `/api/connections` | — | `extensions/builtin_mcp_client/mcp_client_ext.py` |
| `POST` | `/api/connections` | — | `extensions/builtin_mcp_client/mcp_client_ext.py` |
| `DELETE` | `/api/connections/<conn_id>` | — | `extensions/builtin_mcp_client/mcp_client_ext.py` |
| `PUT` | `/api/connections/<conn_id>` | — | `extensions/builtin_mcp_client/mcp_client_ext.py` |
| `POST` | `/api/connections/<conn_id>/call-tool` | — | `extensions/builtin_mcp_client/mcp_client_ext.py` |
| `POST` | `/api/connections/<conn_id>/connect` | — | `extensions/builtin_mcp_client/mcp_client_ext.py` |
| `POST` | `/api/connections/<conn_id>/disconnect` | — | `extensions/builtin_mcp_client/mcp_client_ext.py` |
| `GET` | `/api/connections/<conn_id>/tools` | — | `extensions/builtin_mcp_client/mcp_client_ext.py` |
| `GET` | `/api/settings/<path:key>` | Return a single setting value (secrets are masked). | `routes/settings_manage.py` |
| `PUT` | `/api/settings/<path:key>` | Update a setting value. Secrets are auto-encrypted. Supports op_uri. | `routes/settings_manage.py` |
| `GET` | `/api/settings/all` | Return all setting values (secrets are masked). | `routes/settings_manage.py` |
| `DELETE` | `/api/settings/bw-mapping/<path:key>` | Remove a key from bw_secrets mapping (revert to local encryption). | `routes/settings_manage_vault_bw.py` |
| `GET` | `/api/settings/bw-status` | Return Bitwarden CLI status. | `routes/settings_manage_vault_bw.py` |
| `GET` | `/api/settings/llm-endpoints` | — | `routes/llm_endpoints.py` |
| `PUT` | `/api/settings/llm-endpoints` | — | `routes/llm_endpoints.py` |
| `DELETE` | `/api/settings/llm-endpoints/<category>` | — | `routes/llm_endpoints.py` |
| `POST` | `/api/settings/llm-endpoints/test` | — | `routes/llm_endpoints.py` |
| `DELETE` | `/api/settings/op-mapping/<path:key>` | Remove a key from op_secrets mapping (revert to local encryption). | `routes/settings_manage_vault_op.py` |
| `GET` | `/api/settings/op-status` | Return 1Password CLI status. | `routes/settings_manage_vault_op.py` |
| `GET` | `/api/settings/schema` | Return the full settings schema. | `routes/settings_manage.py` |
| `GET` | `/api/settings/secrets/bw-folders` | Return available Bitwarden folders. | `routes/settings_manage_vault_bw.py` |
| `POST` | `/api/settings/secrets/export` | Export encryption key as password-protected JSON. | `routes/settings_manage_secrets.py` |
| `POST` | `/api/settings/secrets/import` | Import encryption key from exported data. | `routes/settings_manage_secrets.py` |
| `GET` | `/api/settings/secrets/keyring` | Return the list of key_ids in the ring and the active key_id. | `routes/settings_manage_secrets.py` |
| `POST` | `/api/settings/secrets/migrate` | Encrypt all plaintext secrets in config.json. | `routes/settings_manage_secrets.py` |
| `POST` | `/api/settings/secrets/migrate-keychain` | Migrate encryption key from file backend to OS keychain. | `routes/settings_manage_secrets.py` |
| `GET` | `/api/settings/secrets/op-vaults` | Return available 1Password vaults. | `routes/settings_manage_vault_op.py` |
| `POST` | `/api/settings/secrets/push-to-bw` | Batch-write secrets to Bitwarden and save bw_secrets mapping. | `routes/settings_manage_vault_bw.py` |
| `POST` | `/api/settings/secrets/push-to-op` | Batch-write secrets to 1Password and save op_secrets mapping. | `routes/settings_manage_vault_op.py` |
| `POST` | `/api/settings/secrets/rotate` | Rotate the active Fernet key and re-encrypt all secret fields. | `routes/settings_manage_secrets.py` |
| `GET` | `/api/settings/secrets/status` | Return encryption key backend status. | `routes/settings_manage_secrets.py` |

## 拡張機能

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `GET` | `/api/extensions` | — | `routes/extensions_api/routes.py` |
| `GET` | `/api/extensions/<name>` | — | `routes/extensions_api/routes.py` |
| `GET` `POST` | `/api/extensions/<name>/config` | — | `routes/extensions_api/routes.py` |
| `GET` | `/api/extensions/<name>/integrity` | — | `routes/extensions_api/routes.py` |
| `GET` `POST` | `/api/extensions/<name>/permissions` | — | `routes/extensions_api/routes.py` |
| `POST` | `/api/extensions/<name>/rescan` | — | `routes/extensions_api/routes.py` |
| `GET` | `/api/extensions/<name>/scan-results` | — | `routes/extensions_api/routes.py` |
| `POST` | `/api/extensions/<name>/toggle` | — | `routes/extensions_api/routes.py` |
| `GET` | `/api/extensions/<name>/tokens` | — | `routes/extensions_api/routes.py` |
| `DELETE` | `/api/extensions/<name>/uninstall` | — | `routes/extensions_api/routes.py` |
| `POST` | `/api/extensions/<name>/update` | — | `routes/extensions_api/routes.py` |
| `GET` | `/api/extensions/author/<name>/files` | — | `routes/extensions_api/routes.py` |
| `GET` | `/api/extensions/author/<name>/read` | — | `routes/extensions_api/routes.py` |
| `POST` | `/api/extensions/author/<name>/validate` | — | `routes/extensions_api/routes.py` |
| `POST` | `/api/extensions/author/<name>/write` | — | `routes/extensions_api/routes.py` |
| `POST` | `/api/extensions/author/create` | — | `routes/extensions_api/routes.py` |
| `GET` | `/api/extensions/hooks` | — | `routes/extensions_api/routes.py` |
| `POST` | `/api/extensions/install` | — | `routes/extensions_api/routes.py` |
| `GET` | `/api/extensions/isolation` | — | `routes/extensions_api/routes.py` |
| `GET` | `/api/extensions/marketplace` | — | `routes/extensions_api/routes.py` |
| `POST` | `/api/extensions/marketplace/refresh` | — | `routes/extensions_api/routes.py` |
| `GET` | `/api/extensions/os-isolation` | — | `routes/extensions_api/routes.py` |
| `POST` | `/api/extensions/update-all` | — | `routes/extensions_api/routes.py` |
| `DELETE` | `/api/ui/<name>/uninstall` | Uninstall a UI. Localhost only. | `routes/ui_api.py` |
| `POST` | `/api/ui/install` | Install a UI from URL. Localhost only. | `routes/ui_api.py` |
| `GET` | `/api/ui/list` | List all installed UIs. | `routes/ui_api.py` |
| `POST` | `/api/ui/switch` | Switch active UI. Requires restart. | `routes/ui_api.py` |

## 管理

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `POST` | `/api/admin/shutdown` | Stop the server. | `routes/shutdown_api.py` |
| `GET` | `/api/admin/shutdown/info` | Tell the WebUI whether the current request needs a PIN to shut down. | `routes/shutdown_api.py` |
| `GET` | `/api/help/content/<section>` | Section content JSON. | `routes/help.py` |
| `GET` | `/api/help/search` | Help content search. | `routes/help.py` |
| `GET` | `/api/help/toc` | Table of contents JSON (with categories, language-aware). | `routes/help.py` |
| `POST` | `/api/maintenance/analyze` | — | `routes/maintenance.py` |
| `GET` | `/api/maintenance/db-stats` | — | `routes/maintenance.py` |
| `GET` | `/api/maintenance/scan-error-stats` | — | `routes/maintenance.py` |
| `POST` | `/api/maintenance/vacuum` | — | `routes/maintenance.py` |
| `GET` | `/api/scheduler/history` | Return execution history (newest first, max 100). | `routes/scheduler_api.py` |
| `GET` | `/api/scheduler/jobs` | List all scheduled jobs. | `routes/scheduler_api.py` |
| `POST` | `/api/scheduler/jobs` | Add a custom job. | `routes/scheduler_api.py` |
| `DELETE` | `/api/scheduler/jobs/<job_id>` | Remove a job. | `routes/scheduler_api.py` |
| `POST` | `/api/scheduler/jobs/<job_id>/pause` | Pause a job. | `routes/scheduler_api.py` |
| `POST` | `/api/scheduler/jobs/<job_id>/resume` | Resume a paused job. | `routes/scheduler_api.py` |
| `POST` | `/api/scheduler/jobs/<job_id>/trigger` | Trigger immediate execution of a job. | `routes/scheduler_api.py` |
| `GET` | `/api/scheduler/status` | Return scheduler status and all jobs. | `routes/scheduler_api.py` |
| `GET` | `/api/schedulers` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_info_routes.py` |
| `GET` | `/api/server/mode` | — | `routes/server_info.py` |
| `GET` | `/api/server/subsystems` | — | `routes/server_info.py` |

## SSE・ログ

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `GET` | `/api/logs/recent` | Return recent log entries as JSON. | `routes/logs_api.py` |
| `GET` | `/api/logs/stream` | SSE endpoint for real-time log streaming. | `routes/logs_api.py` |

## メッシュ推論

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `POST` | `/api/mesh-inference/bulk` | — | `routes/mesh_inference_api.py` |
| `POST` | `/api/mesh-inference/refresh` | Re-read the peer list and return the fresh matrix. | `routes/mesh_inference_api.py` |
| `GET` | `/api/mesh-inference/state` | — | `routes/mesh_inference_api.py` |
| `POST` | `/api/mesh-inference/toggle` | — | `routes/mesh_inference_api.py` |

## Hailo

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `POST` | `/api/hailo-tagger/batch` | — | `routes/hailo_tagger.py` |
| `GET` | `/api/hailo-tagger/config` | — | `routes/hailo_tagger.py` |
| `POST` | `/api/hailo-tagger/config` | — | `routes/hailo_tagger.py` |
| `GET` | `/api/hailo-tagger/status` | — | `routes/hailo_tagger.py` |
| `POST` | `/api/hailo-tagger/tag/<int:file_id>` | — | `routes/hailo_tagger.py` |
| `DELETE` | `/api/hailo-tagger/tags/<int:file_id>` | — | `routes/hailo_tagger.py` |
| `GET` | `/api/hailo-tagger/tags/<int:file_id>` | — | `routes/hailo_tagger.py` |
| `GET` | `/ext/hailo-yolo/api/stream/devices` | List stream devices. | `crates/yu-server/src/routes/hailo_yolo_stream/handlers.rs` |
| `GET` | `/ext/hailo-yolo/api/stream/recordings` | List stream recordings. | `crates/yu-server/src/routes/hailo_yolo_stream/handlers.rs` |
| `GET` `POST` | `/ext/hailo-yolo/api/stream/rules` | List or create stream rules. | `crates/yu-server/src/routes/hailo_yolo_stream/handlers.rs` |
| `PUT` `DELETE` | `/ext/hailo-yolo/api/stream/rules/{rule_id}` | Update or delete a stream rule. | `crates/yu-server/src/routes/hailo_yolo_stream/handlers.rs` |
| `GET` | `/ext/hailo-yolo/api/stream/snapshot/{filename}` | Get a stream snapshot. | `crates/yu-server/src/routes/hailo_yolo_stream/handlers.rs` |
| `GET` `POST` | `/ext/hailo-yolo/api/stream/sources` | List or add stream sources. | `crates/yu-server/src/routes/hailo_yolo_stream/handlers.rs` |
| `DELETE` | `/ext/hailo-yolo/api/stream/sources/{source_id}` | Delete a stream source. | `crates/yu-server/src/routes/hailo_yolo_stream/handlers.rs` |
| `POST` | `/ext/hailo-yolo/api/stream/sources/{source_id}/start` | Start a stream source. | `crates/yu-server/src/routes/hailo_yolo_stream/handlers.rs` |
| `POST` | `/ext/hailo-yolo/api/stream/sources/{source_id}/stop` | Stop a stream source. | `crates/yu-server/src/routes/hailo_yolo_stream/handlers.rs` |
| `POST` | `/ext/hailo-yolo/api/stream/sources/{source_id}/test` | Test a stream source. | `crates/yu-server/src/routes/hailo_yolo_stream/handlers.rs` |
| `GET` | `/ext/hailo-yolo/api/stream/status` | Get stream status. | `crates/yu-server/src/routes/hailo_yolo_stream/handlers.rs` |
| `GET` | `/ext/hailo-yolo/api/stream/{source_id}/mjpeg` | Stream MJPEG output. | `crates/yu-server/src/routes/hailo_yolo_stream/handlers.rs` |

## LAN 共有

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `POST` | `/api/lan-share/create` | Create a LAN share token for a collection. | `extensions/builtin_lan_share/core_impl/share_routes.py` |
| `POST` | `/api/lan-share/revoke` | Revoke a LAN share token. | `extensions/builtin_lan_share/core_impl/share_routes.py` |
| `GET` | `/api/languages` | — | `extensions/builtin_md_viewer/core_impl/api_routes_files.py` |
| `GET` | `/api/mdns/identity` | — | `routes/mdns_identity.py` |
| `GET` | `/api/mdns/peers` | Debug: expose the live core.mdns MdnsService peer list + status. | `routes/mdns_identity.py` |
| `GET` | `/api/share/<int:file_id>` | Generate prompt data for QR code sharing. | `routes/share.py` |

## 統計

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `GET` | `/api/stats` | — | `routes/stats.py` |
| `GET` | `/api/stats/all` | Return all stats results in one response (cached). | `routes/stats.py` |
| `GET` | `/api/stats/hourly` | — | `routes/stats.py` |
| `GET` | `/api/stats/models` | — | `routes/stats.py` |
| `GET` | `/api/stats/monthly-report` | Return monthly report data. | `routes/monthly_report.py` |
| `GET` | `/api/stats/resolutions` | — | `routes/stats.py` |
| `GET` | `/api/stats/story` | — | `routes/stats.py` |
| `GET` | `/api/stats/timeline` | — | `routes/stats.py` |

## プロンプト管理

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `GET` | `/api/prompts` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api.py` |
| `POST` | `/api/prompts` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api.py` |
| `DELETE` | `/api/prompts/<int:pid>` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api.py` |
| `GET` | `/api/prompts/<int:pid>` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api.py` |
| `PUT` | `/api/prompts/<int:pid>` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api.py` |
| `DELETE` | `/api/prompts/<int:pid>/folder` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api_routes_folders.py` |
| `POST` | `/api/prompts/<int:pid>/folder` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api_routes_folders.py` |
| `POST` | `/api/prompts/<int:pid>/tags` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api_routes_tags.py` |
| `POST` | `/api/prompts/bulk-delete` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api_routes_bulk.py` |
| `POST` | `/api/prompts/bulk-move` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api_routes_bulk.py` |
| `POST` | `/api/prompts/bulk-tag` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api_routes_bulk.py` |
| `POST` | `/api/prompts/from-file` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api_routes_from_file.py` |

## チャット

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `GET` | `/api/chat/active` | — | `extensions/builtin_hailo_genai/hailo_chat_routes_conversations.py` |
| `GET` | `/api/chat/conversations` | — | `extensions/builtin_hailo_genai/hailo_chat_routes_conversations.py` |
| `DELETE` | `/api/chat/conversations/<int:conv_id>` | — | `extensions/builtin_hailo_genai/hailo_chat_routes_conversations.py` |
| `GET` | `/api/chat/conversations/<int:conv_id>` | — | `extensions/builtin_hailo_genai/hailo_chat_routes_conversations.py` |
| `PATCH` | `/api/chat/conversations/<int:conv_id>/title` | — | `extensions/builtin_hailo_genai/hailo_chat_routes_conversations.py` |
| `GET` | `/api/chat/decisions` | — | `extensions/builtin_chatlog/core_impl/api.py` |
| `GET` | `/api/chat/decisions/search` | — | `extensions/builtin_chatlog/core_impl/api.py` |
| `POST` | `/api/chat/new` | — | `extensions/builtin_hailo_genai/hailo_chat_routes_conversations.py` |
| `POST` | `/api/chat/reprocess` | — | `extensions/builtin_chatlog/core_impl/api.py` |
| `GET` | `/api/chat/reprocess/status` | — | `extensions/builtin_chatlog/core_impl/api.py` |
| `POST` | `/api/chat/search` | — | `extensions/builtin_hailo_genai/hailo_chat_routes_send.py` |
| `POST` | `/api/chat/send` | — | `extensions/builtin_hailo_genai/hailo_chat_routes_send.py` |
| `GET` | `/api/chat/topics/search` | — | `extensions/builtin_chatlog/core_impl/api.py` |
| `GET` | `/api/conversations` | — | `extensions/builtin_chatlog/core_impl/api.py` |
| `DELETE` | `/api/conversations/<int:conv_id>` | — | `extensions/builtin_chatlog/core_impl/api.py` |
| `GET` | `/api/conversations/<int:conv_id>` | — | `extensions/builtin_chatlog/core_impl/api.py` |
| `GET` | `/api/conversations/<int:conv_id>/entities` | — | `extensions/builtin_chatlog/core_impl/api.py` |
| `GET` | `/api/conversations/<int:conv_id>/related` | — | `extensions/builtin_chatlog/core_impl/api.py` |
| `GET` | `/api/conversations/<int:conv_id>/summary` | — | `extensions/builtin_chatlog/core_impl/api.py` |

## SNS・ストリーム

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `GET` | `/api/github/accounts` | List registered GitHub accounts (tokens masked). | `extensions/builtin_github_integration/core_impl/api_accounts.py` |
| `POST` | `/api/github/accounts` | Add a new GitHub account. | `extensions/builtin_github_integration/core_impl/api_accounts.py` |
| `DELETE` | `/api/github/accounts/<label>` | Remove a GitHub account. | `extensions/builtin_github_integration/core_impl/api_accounts.py` |
| `PUT` | `/api/github/accounts/<label>` | Update a GitHub account. | `extensions/builtin_github_integration/core_impl/api_accounts.py` |
| `GET` | `/api/github/discussions/<label>` | Fetch discussions for an account's repositories. | `extensions/builtin_github_integration/core_impl/api_repos.py` |
| `GET` | `/api/github/issue/<label>/<path:repo>/<int:number>` | Get detailed issue info formatted for Claude Code consumption. | `extensions/builtin_github_integration/core_impl/api_issues.py` |
| `GET` | `/api/github/issues/<label>` | Fetch issues for a specific account's repositories. | `extensions/builtin_github_integration/core_impl/api_issues.py` |
| `POST` | `/api/github/issues/<label>` | Create a new issue. | `extensions/builtin_github_integration/core_impl/api_issues.py` |
| `GET` | `/api/github/notifications/<label>` | Fetch notifications for an account. | `extensions/builtin_github_integration/core_impl/api_repos.py` |
| `PATCH` | `/api/github/notifications/<label>/<thread_id>` | Mark a notification as read. | `extensions/builtin_github_integration/core_impl/api_repos.py` |
| `POST` | `/api/github/notifications/<label>/mark-all-read` | Mark all notifications as read. | `extensions/builtin_github_integration/core_impl/api_repos.py` |
| `GET` | `/api/github/pull/<label>/<path:repo>/<int:number>` | Get detailed PR info including diff stats and changed files. | `extensions/builtin_github_integration/core_impl/api_repos.py` |
| `GET` | `/api/github/pulls/<label>` | Fetch pull requests for an account's repositories. | `extensions/builtin_github_integration/core_impl/api_repos.py` |
| `GET` | `/api/github/queue` | Get issue queue items. | `extensions/builtin_github_integration/core_impl/api_queue.py` |
| `POST` | `/api/github/queue/<int:queue_id>/dismiss` | Dismiss a queue item (auto-close if configured). | `extensions/builtin_github_integration/core_impl/api_queue.py` |
| `PUT` | `/api/github/queue/<int:queue_id>/status` | Update queue item status. | `extensions/builtin_github_integration/core_impl/api_queue.py` |
| `POST` | `/api/github/queue/<int:queue_id>/triage` | Set triage result for a queue item. | `extensions/builtin_github_integration/core_impl/api_queue.py` |
| `GET` | `/api/github/queue/config` | Get issue queue configuration. | `extensions/builtin_github_integration/core_impl/api_queue.py` |
| `PUT` | `/api/github/queue/config` | Update issue queue configuration. | `extensions/builtin_github_integration/core_impl/api_queue.py` |
| `GET` | `/api/github/queue/pending` | Get pending issues for MCP notification. | `extensions/builtin_github_integration/core_impl/api_queue.py` |
| `POST` | `/api/github/queue/poll` | Trigger immediate issue polling for all accounts. | `extensions/builtin_github_integration/core_impl/api_queue.py` |
| `GET` | `/api/github/rate-limit/<label>` | Check GitHub API rate limit for an account. | `extensions/builtin_github_integration/core_impl/api_accounts.py` |
| `GET` | `/api/github/releases/<label>` | Fetch latest releases for an account's repositories. | `extensions/builtin_github_integration/core_impl/api_repos.py` |
| `GET` | `/api/github/repo-stats-all/<label>` | Get stats for all repositories in an account. | `extensions/builtin_github_integration/core_impl/api_repos.py` |
| `GET` | `/api/github/repo-stats/<label>/<path:repo>` | Get repository statistics. | `extensions/builtin_github_integration/core_impl/api_repos.py` |
| `GET` | `/api/github/triage-prompts` | Get triage prompts with optional per-repo resolution. | `extensions/builtin_github_integration/core_impl/api_issues.py` |
| `PUT` | `/api/github/triage-prompts` | Update triage prompts (global or per-repo). | `extensions/builtin_github_integration/core_impl/api_issues.py` |
| `POST` | `/api/github/triage/<label>` | Fetch and triage issues for an account. | `extensions/builtin_github_integration/core_impl/api_issues.py` |
| `POST` | `/api/sns/bluesky/post` | Post to Bluesky. | `routes/sns_share.py` |
| `POST` | `/api/sns/bluesky/test` | Bluesky connection test. | `routes/sns_share.py` |
| `GET` | `/api/sns/bsky/monitor/config` | — | `routes/sns_share.py` |
| `PUT` | `/api/sns/bsky/monitor/config` | — | `routes/sns_share.py` |
| `GET` | `/api/sns/bsky/monitor/triage-prompts` | — | `routes/sns_share.py` |
| `PUT` | `/api/sns/bsky/monitor/triage-prompts` | — | `routes/sns_share.py` |
| `GET` | `/api/sns/bsky/queue` | — | `routes/sns_share.py` |
| `POST` | `/api/sns/bsky/queue/<int:queue_id>/respond` | — | `routes/sns_share.py` |
| `PUT` | `/api/sns/bsky/queue/<int:queue_id>/status` | — | `routes/sns_share.py` |
| `POST` | `/api/sns/bsky/queue/<int:queue_id>/triage` | — | `routes/sns_share.py` |
| `GET` | `/api/sns/bsky/queue/pending` | — | `routes/sns_share.py` |
| `POST` | `/api/sns/bsky/queue/poll` | — | `routes/sns_share.py` |
| `GET` | `/api/sns/config` | Get SNS settings (passwords masked). | `routes/sns_share.py` |
| `POST` | `/api/sns/config` | Save SNS settings. | `routes/sns_share.py` |
| `GET` | `/api/sns/preview` | Template expansion preview + grapheme count. | `routes/sns_share.py` |
| `GET` | `/api/sns/x/intent` | Return X (Twitter) Web Intent URL. | `routes/sns_share.py` |
| `GET` | `/api/webhooks` | — | `extensions/builtin_webhook/core_impl/webhook_routes.py` |
| `POST` | `/api/webhooks` | — | `extensions/builtin_webhook/core_impl/webhook_routes.py` |
| `DELETE` | `/api/webhooks/<wh_id>` | — | `extensions/builtin_webhook/core_impl/webhook_routes.py` |
| `PUT` | `/api/webhooks/<wh_id>` | — | `extensions/builtin_webhook/core_impl/webhook_routes.py` |
| `POST` | `/api/webhooks/<wh_id>/test` | — | `extensions/builtin_webhook/core_impl/webhook_routes.py` |
| `GET` | `/api/webhooks/deliveries` | — | `extensions/builtin_webhook/core_impl/webhook_routes.py` |
| `GET` | `/api/webhooks/inbound` | — | `extensions/builtin_webhook/core_impl/webhook_routes.py` |
| `POST` | `/api/webhooks/inbound` | — | `extensions/builtin_webhook/core_impl/webhook_routes.py` |
| `DELETE` | `/api/webhooks/inbound/<wh_id>` | — | `extensions/builtin_webhook/core_impl/webhook_routes.py` |
| `PUT` | `/api/webhooks/inbound/<wh_id>` | — | `extensions/builtin_webhook/core_impl/webhook_routes.py` |
| `POST` | `/api/webhooks/receive/<token>` | Receive an external webhook trigger. Token-authenticated, no PIN session required. | `extensions/builtin_webhook/core_impl/webhook_inbound.py` |

## MCP・内部 API

| メソッド | パス | 説明 | ファイル |
|---------|------|------|---------|
| `GET` | `/` | Main page. | `routes/pages.py` |
| `GET` | `/<int:file_id>` | — | `extensions/builtin_annotations/annotations_ext.py` |
| `GET` `POST` `PUT` `DELETE` `HEAD` `PATCH` | `/<name>/<path:subpath>` | — | `routes/gateway_gradio.py` |
| `GET` `POST` | `/<path:subpath>` | Proxy agentmemory requests for the dashboard page. | `routes/gateway_agentmemory.py` |
| `GET` `POST` `PUT` `DELETE` | `/<path:subpath>` | — | `routes/gateway_headroom_llm.py` |
| `POST` | `/_internal/bridge/import-paths` | Rust bridge からの保存画像 import API。loopback 限定。 | `routes/scan.py` |
| `GET` | `/_internal/file/detail/<int:file_id>` | — | `routes/files.py` |
| `POST` | `/_internal/lan_cowork/fleet-allowlists-changed` | Internal notify endpoint called by Rust after fleet allowlists config mutations. | `extensions/builtin_lan_cowork/routes/settings_api.py` |
| `POST` | `/_internal/lan_cowork/fleet-chief-changed` | Internal notify endpoint called by Rust after fleet chief config mutations. | `extensions/builtin_lan_cowork/routes/settings_api.py` |
| `POST` | `/_internal/lan_cowork/registry-peer-changed` | Internal notify called by the Rust server after peer registry | `extensions/builtin_lan_cowork/routes/peer_api.py` |
| `POST` | `/_internal/mcp/dispatch` | Internal bridge: Rust MCP native handler → Python JSON-RPC dispatch. | `routes/mcp_endpoint.py` |
| `POST` | `/_internal/scan-roots-changed` | Internal notify endpoint called by Rust after scan_roots mutations. | `routes/scan_roots_api/routes_config.py` |
| `POST` | `/_internal/scan/queue/consume` | Rust bridge からの内部 API。loopback 限定。 | `routes/scan.py` |
| `POST` | `/_internal/wd-tagger/profiles-changed` | — | `routes/wd_tagger_admin_routes.py` |
| `POST` | `/_internal/webhooks-changed` | Internal notify endpoint called by Rust after webhook config mutations. | `extensions/builtin_webhook/core_impl/webhook_routes.py` |
| `GET` | `/admin-token` | — | `routes/gateway_admin_token.py` |
| `GET` | `/agent-journal` | Agent operation journal page. | `routes/pages.py` |
| `GET` | `/agent-memory` | Agent Memory dashboard — read-only view of agentmemory state. | `routes/pages.py` |
| `GET` | `/agent_journal` | Legacy underscore URL → canonical hyphen URL. | `routes/pages.py` |
| `GET` | `/agent_memory` | Legacy underscore URL → canonical hyphen URL. | `routes/pages.py` |
| `GET` | `/agentmemory/config` | — | `routes/gateway_agentmemory.py` |
| `PUT` | `/agentmemory/config` | — | `routes/gateway_agentmemory.py` |
| `POST` | `/analyze` | Server-side syntax analysis (simple analysis on Python side) | `extensions/builtin_prompt_syntax/prompt_syntax.py` |
| `GET` `POST` | `/api/<path:subpath>` | — | `routes/gateway_comfy.py` |
| `GET` | `/api/ai-context` | Return AI-navigable self-description of this YU AI Manager instance. | `routes/ai_context.py` |
| `GET` | `/api/anlas` | — | `extensions/builtin_nai_bridge/core_impl/nai_api.py` |
| `GET` | `/api/audio-analysis/status` | Check audio analysis availability. | `extensions/builtin_audio_analysis/audio_analysis_ext.py` |
| `POST` | `/api/audio-analysis/transcribe/<int:file_id>` | Transcribe audio/video file and save to analysis table. | `extensions/builtin_audio_analysis/audio_analysis_ext.py` |
| `GET` | `/api/backends` | — | `extensions/builtin_hailo_semantic_search/hailo_semantic_search_status_routes.py` |
| `POST` | `/api/batch-add` | — | `extensions/builtin_favorites_manager/core_impl/favorites_manager_api.py` |
| `POST` | `/api/batch-remove` | — | `extensions/builtin_favorites_manager/core_impl/favorites_manager_api.py` |
| `POST` | `/api/cancel` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_info_routes.py` |
| `POST` | `/api/caption/start` | — | `extensions/builtin_hailo_semantic_search/hailo_semantic_search_search_routes.py` |
| `GET` | `/api/caption/status` | — | `extensions/builtin_hailo_semantic_search/hailo_semantic_search_search_routes.py` |
| `POST` | `/api/caption/stop` | — | `extensions/builtin_hailo_semantic_search/hailo_semantic_search_search_routes.py` |
| `GET` | `/api/check` | — | `extensions/builtin_freeze_pullback/core_impl/api_generate_routes.py` |
| `POST` | `/api/check-workflow-from-file` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_workflow_routes.py` |
| `GET` | `/api/checkpoint-info` | Inspect a checkpoint's safetensors header to identify model family. | `extensions/builtin_comfyui_bridge/core_impl/comfyui_discovery_api.py` |
| `GET` | `/api/checkpoints` | List available checkpoints (models). | `routes/scan_roots_api/routes_config.py` |
| `GET` | `/api/clip-types` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_discovery_api.py` |
| `GET` | `/api/config` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_config_routes.py` |
| `POST` | `/api/config` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_config_routes.py` |
| `GET` | `/api/container-members/<int:file_id>` | Return list of members in a ZIP container. | `routes/zip_files.py` |
| `GET` | `/api/controlnets` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_discovery_api.py` |
| `GET` | `/api/custom-nodes` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_discovery_api.py` |
| `GET` | `/api/debug/enabled` | Report whether YU_DEBUG_MODE is enabled (no 403 noise on tools page probe). | `routes/debug.py` |
| `GET` | `/api/debug/file-meta/<int:file_id>` | Inspect file metadata details (internal debug API -- no frontend UI). | `routes/debug.py` |
| `GET` | `/api/debug/model-check` | Check templates.model_name storage status (internal debug API -- no frontend UI). | `routes/debug.py` |
| `POST` | `/api/debug/query` | Execute a readonly SQL query (requires YU_DEBUG_MODE=1). | `routes/debug.py` |
| `POST` | `/api/detect/clear` | Delete all YOLO detection annotations. | `extensions/builtin_hailo_yolo_detect/yolo_routes_search.py` |
| `GET` | `/api/detect/results/<int:file_id>` | Get detection results for a single file. | `extensions/builtin_hailo_yolo_detect/yolo_routes_search.py` |
| `GET` | `/api/detect/search` | Search for files containing a detected class. | `extensions/builtin_hailo_yolo_detect/yolo_routes_search.py` |
| `POST` | `/api/detect/start` | Start batch object detection. | `extensions/builtin_hailo_yolo_detect/hailo_yolo_detect.py` |
| `GET` | `/api/detect/status` | Get detection progress. | `extensions/builtin_hailo_yolo_detect/hailo_yolo_detect.py` |
| `POST` | `/api/detect/stop` | Stop detection. | `extensions/builtin_hailo_yolo_detect/hailo_yolo_detect.py` |
| `POST` | `/api/diagnostics/bug-report` | — | `routes/diagnostics.py` |
| `POST` | `/api/diagnostics/cleanup-update-pending` | Delete update_pending JSON entries older than 7 days. | `routes/diagnostics.py` |
| `POST` | `/api/diagnostics/doctor` | — | `routes/diagnostics.py` |
| `GET` | `/api/diagnostics/doctor/<job_id>` | — | `routes/diagnostics.py` |
| `POST` | `/api/diagnostics/open-repair-folder` | — | `routes/diagnostics.py` |
| `GET` | `/api/diagnostics/safe-mode` | — | `routes/diagnostics.py` |
| `POST` | `/api/diagnostics/zip-repair` | — | `routes/diagnostics.py` |
| `GET` | `/api/diffusion-models` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_discovery_api.py` |
| `GET` | `/api/discovery/models` | Generic model discovery endpoint — returns models for any loader type. | `extensions/builtin_comfyui_bridge/core_impl/comfyui_discovery_api.py` |
| `GET` | `/api/embeddings` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_discovery_api.py` |
| `POST` | `/api/entities/reindex` | — | `extensions/builtin_chatlog/core_impl/api.py` |
| `GET` | `/api/entities/search` | — | `extensions/builtin_chatlog/core_impl/api.py` |
| `POST` | `/api/error-report/enrich` | — | `routes/server_info.py` |
| `GET` | `/api/export` | — | `extensions/builtin_prompt_library/core_impl/prompt_library_api_routes_bulk.py` |
| `POST` | `/api/export/folder` | — | `extensions/builtin_favorites_manager/core_impl/favorites_manager_api.py` |
| `GET` | `/api/export/zip` | — | `extensions/builtin_favorites_manager/core_impl/favorites_manager_api.py` |
| `POST` | `/api/extract-from-zip` | Extract file from archive. | `routes/zip_files.py` |
| `POST` | `/api/extract-workflow` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_workflow_routes.py` |
| `POST` | `/api/generate` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api.py` |
| `GET` | `/api/has-node` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_info_routes.py` |
| `POST` | `/api/hash-backfill/cancel` | Cancel hash backfill job. | `routes/scan.py` |
| `POST` | `/api/hash-backfill/start` | Start hash backfill job. | `routes/scan.py` |
| `GET` | `/api/hash-backfill/status` | Query hash backfill progress. | `routes/scan.py` |
| `GET` | `/api/headroom/health` | — | `routes/headroom_api.py` |
| `GET` | `/api/headroom/livez` | — | `routes/headroom_api.py` |
| `GET` | `/api/headroom/metrics` | — | `routes/headroom_api.py` |
| `GET` | `/api/headroom/readyz` | — | `routes/headroom_api.py` |
| `GET` | `/api/headroom/stats` | — | `routes/headroom_api.py` |
| `GET` | `/api/headroom/stats-history` | — | `routes/headroom_api.py` |
| `GET` | `/api/images` | Return image list for manager grid with thumbnail URLs. | `extensions/builtin_favorites_manager/core_impl/favorites_manager_api.py` |
| `POST` | `/api/import` | — | `extensions/builtin_chatlog/core_impl/api_import.py` |
| `POST` | `/api/import-path` | — | `extensions/builtin_chatlog/core_impl/api_import.py` |
| `GET` | `/api/import/status` | — | `extensions/builtin_chatlog/core_impl/api_import.py` |
| `POST` | `/api/index/clear` | — | `extensions/builtin_hailo_semantic_search/hailo_semantic_search_status_routes.py` |
| `POST` | `/api/index/start` | — | `extensions/builtin_hailo_semantic_search/hailo_semantic_search_status_routes.py` |
| `GET` | `/api/index/status` | — | `extensions/builtin_hailo_semantic_search/hailo_semantic_search_status_routes.py` |
| `POST` | `/api/index/stop` | — | `extensions/builtin_hailo_semantic_search/hailo_semantic_search_status_routes.py` |
| `POST` | `/api/internal/log` | Accept a log entry from a local subprocess (e.g. MCP) and write to log_ring. | `routes/logs_api.py` |
| `GET` | `/api/jobs/status` | All background job statuses (for banner UI). | `routes/scan.py` |
| `GET` | `/api/labels` | Return all COCO class labels for autocomplete. | `extensions/builtin_hailo_yolo_detect/yolo_routes_search.py` |
| `POST` | `/api/llm/agent` | — | `routes/llm_endpoints.py` |
| `GET` | `/api/llm/agent/capabilities` | — | `routes/llm_endpoints.py` |
| `POST` | `/api/llm/chat` | — | `routes/llm_endpoints.py` |
| `POST` | `/api/llm/clear-context` | — | `extensions/builtin_hailo_genai/hailo_llm_routes.py` |
| `POST` | `/api/llm/generate` | — | `extensions/builtin_hailo_genai/hailo_llm_routes.py` |
| `GET` | `/api/loras` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_discovery_api.py` |
| `GET` | `/api/market/quotes` | — | `routes/search.py` |
| `GET` | `/api/model-registry` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_model_registry_routes.py` |
| `POST` | `/api/model-registry` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_model_registry_routes.py` |
| `DELETE` | `/api/model-registry/<entry_id>` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_model_registry_routes.py` |
| `POST` | `/api/model/download` | — | `extensions/builtin_hailo_genai/hailo_genai_ext.py` |
| `GET` | `/api/model/status` | — | `extensions/builtin_hailo_genai/hailo_genai_ext.py` |
| `POST` | `/api/model/unload` | — | `extensions/builtin_hailo_genai/hailo_genai_ext.py` |
| `GET` | `/api/models` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_info_routes.py` |
| `POST` | `/api/models/switch` | — | `extensions/builtin_sd_webui_bridge/core_impl/sd_webui_api_model_routes.py` |
| `GET` | `/api/noise-schedules` | — | `extensions/builtin_nai_bridge/core_impl/nai_api.py` |
| `POST` | `/api/open-file` | — | `extensions/builtin_cross_search/core_impl/api.py` |
| `POST` | `/api/parse-workflow-params` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_workflow_routes.py` |
| `GET` | `/api/peer/pair/requests/<rid>/_test_pin` | — | `extensions/builtin_lan_cowork/routes/pair_api.py` |
| `GET` | `/api/progress` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_info_routes.py` |
| `POST` | `/api/queue-workflow-from-file` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_workflow_routes.py` |
| `GET` | `/api/recipe/export/<int:file_id>` | — | `routes/recipe.py` |
| `POST` | `/api/recipe/export/batch` | Bulk recipe export for search-result selections. | `routes/recipe.py` |
| `POST` | `/api/recipe/import` | — | `routes/recipe.py` |
| `POST` | `/api/recipe/import/batch` | — | `routes/recipe.py` |
| `POST` | `/api/refresh-assets` | Re-query ComfyUI's loader nodes so its mtime-based file cache | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_info_routes.py` |
| `GET` | `/api/runtime` | — | `extensions/builtin_hailo_genai/hailo_genai_ext.py` |
| `POST` | `/api/s2t/batch-transcribe` | Start batch video transcription in background. | `extensions/builtin_hailo_genai/hailo_s2t_batch.py` |
| `GET` | `/api/s2t/status` | Return backend status and available backends. | `extensions/builtin_speech_to_text/s2t_routes.py` |
| `GET` | `/api/s2t/stream/audio` | Stream audio as MP3 for browser playback. | `extensions/builtin_speech_to_text/s2t_stream_media_routes.py` |
| `GET` | `/api/s2t/stream/export/srt` | Export transcript as SRT subtitle format. | `extensions/builtin_speech_to_text/s2t_stream_export_routes.py` |
| `GET` | `/api/s2t/stream/export/txt` | Export transcript as plain text. | `extensions/builtin_speech_to_text/s2t_stream_export_routes.py` |
| `POST` | `/api/s2t/stream/llm-process` | Send transcript to LLM for refinement/translation. | `extensions/builtin_speech_to_text/s2t_stream_llm_routes.py` |
| `GET` | `/api/s2t/stream/media` | Stream as fMP4 (video+audio) for browser <video> playback. | `extensions/builtin_speech_to_text/s2t_stream_media_routes.py` |
| `POST` | `/api/s2t/stream/start` | Start real-time stream transcription. | `extensions/builtin_speech_to_text/s2t_stream_control_routes.py` |
| `GET` | `/api/s2t/stream/status` | Return current stream transcription status. | `extensions/builtin_speech_to_text/s2t_stream_control_routes.py` |
| `POST` | `/api/s2t/stream/stop` | Stop the running stream transcription. | `extensions/builtin_speech_to_text/s2t_stream_control_routes.py` |
| `GET` | `/api/s2t/stream/transcript` | Return accumulated transcript segments. | `extensions/builtin_speech_to_text/s2t_stream_control_routes.py` |
| `GET` | `/api/s2t/stream/video` | Stream video as MJPEG for browser preview. | `extensions/builtin_speech_to_text/s2t_stream_media_routes.py` |
| `POST` | `/api/s2t/transcribe` | — | `extensions/builtin_hailo_genai/hailo_s2t_routes.py` |
| `POST` | `/api/s2t/transcribe-video` | Transcribe a single video file by file_id. | `extensions/builtin_hailo_genai/hailo_s2t_routes.py` |
| `GET` | `/api/s2t/transcript/<int:file_id>` | Get saved transcript for a file. | `extensions/builtin_hailo_genai/hailo_s2t_batch.py` |
| `GET` | `/api/samplers` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_info_routes.py` |
| `POST` | `/api/save-batch` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api.py` |
| `GET` | `/api/save-state-diag` | — | `extensions/builtin_sd_webui_bridge/core_impl/sd_webui_api_diag_routes.py` |
| `GET` | `/api/script-info` | — | `extensions/builtin_sd_webui_bridge/core_impl/sd_webui_discovery_api.py` |
| `GET` | `/api/scripts` | — | `extensions/builtin_sd_webui_bridge/core_impl/sd_webui_discovery_api.py` |
| `GET` | `/api/source/read` | Read file contents with line numbers. | `routes/source_api.py` |
| `GET` | `/api/source/search` | Search text within source code. | `routes/source_api.py` |
| `GET` | `/api/source/tree` | Get directory tree. | `routes/source_api.py` |
| `GET` | `/api/status` | — | `extensions/builtin_freeze_pullback/core_impl/api_generate_routes.py` |
| `GET` | `/api/svg/info` | Check SVG rasterization availability. | `routes/svg_api.py` |
| `POST` | `/api/svg/rasterize` | Rasterize an SVG to PNG/WebP bitmap. | `routes/svg_api.py` |
| `GET` | `/api/system/cma` | Return CMA snapshot for the warning banner. | `extensions/builtin_hailo_genai/hailo_genai_ext.py` |
| `GET` | `/api/system/inference-info` | Return GPU info and ORT provider status. | `routes/inference_info.py` |
| `POST` | `/api/system/update/apply` | Apply an update (git or portable installs). | `routes/update_api.py` |
| `GET` | `/api/system/update/check` | Check for available updates from GitHub releases. | `routes/update_api.py` |
| `GET` | `/api/system/update/status` | Return current install type, update state, and version. | `routes/update_api.py` |
| `POST` | `/api/system/update/unified-apply` | Apply updates for system and/or extensions. | `routes/update_api.py` |
| `GET` | `/api/system/update/unified-check` | Check update status for system and all extensions at once. | `routes/update_api.py` |
| `GET` | `/api/tauri-shell/tabs` | Return tabs.json merged with dynamically registered extension tabs. | `routes/extensions_api/routes.py` |
| `POST` | `/api/test-connection` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_info_routes.py` |
| `GET` | `/api/text-encoders` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_discovery_api.py` |
| `GET` | `/api/text-search` | — | `extensions/builtin_chatlog/core_impl/api.py` |
| `GET` | `/api/trophies` | List all trophies (earned + unearned silhouettes). | `routes/trophies.py` |
| `GET` | `/api/txt/<int:file_id>` | — | `extensions/builtin_cross_search/core_impl/api.py` |
| `POST` | `/api/update/apply` | — | `routes/update_package.py` |
| `POST` | `/api/update/rollback` | — | `routes/update_package.py` |
| `POST` | `/api/update/verify` | — | `routes/update_package.py` |
| `POST` | `/api/upload-controlnet-image` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_api_workflow_routes.py` |
| `GET` | `/api/upscale-models` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_discovery_api.py` |
| `GET` | `/api/upscalers` | — | `extensions/builtin_sd_webui_bridge/core_impl/sd_webui_api_info_routes.py` |
| `POST` | `/api/vibe/download` | Encode (or reuse the cache for) every active reference image and | `extensions/builtin_nai_bridge/core_impl/nai_api.py` |
| `POST` | `/api/vibe/upload` | Accept a .naiv4vibe file, inject all encodings into the cache. | `extensions/builtin_nai_bridge/core_impl/nai_api.py` |
| `POST` | `/api/vlm/generate` | — | `extensions/builtin_hailo_genai/hailo_vlm_routes.py` |
| `GET` | `/api/weight-dtypes` | — | `extensions/builtin_comfyui_bridge/core_impl/comfyui_discovery_api.py` |
| `GET` | `/api/workflow-gen-params/<int:file_id>` | — | `routes/workflow_params.py` |
| `POST` | `/auth/reload` | — | `routes/gateway_admin.py` |
| `GET` | `/backends` | — | `routes/gateway_backends.py` |
| `POST` | `/backends` | — | `routes/gateway_backends.py` |
| `DELETE` | `/backends/<backend_id>` | — | `routes/gateway_backends.py` |
| `PATCH` | `/backends/<backend_id>` | — | `routes/gateway_backends.py` |
| `POST` | `/backends/scan` | — | `routes/gateway_backends.py` |
| `DELETE` | `/backends/scan/<scan_id>` | — | `routes/gateway_backends.py` |
| `GET` | `/backends/scan/<scan_id>/stream` | — | `routes/gateway_backends.py` |
| `POST` | `/batch` | — | `extensions/builtin_sd_nai_convert/core_impl/sd_nai_convert_api.py` |
| `POST` | `/batch-delete` | — | `extensions/builtin_annotations/annotations_ext.py` |
| `POST` | `/batch-set` | — | `extensions/builtin_annotations/annotations_ext.py` |
| `POST` | `/batch-zip` | Download selected images as a ZIP archive. | `extensions/builtin_download/download_ext.py` |
| `POST` | `/call/<api_name>` | Gradio4 generation submit. api_name must be in allowlist. | `routes/gateway_sd.py` |
| `GET` | `/call/<api_name>/<event_id>` | SSE result fetch. ?backend_id query used for routing (EventSource compatible). | `routes/gateway_sd.py` |
| `POST` | `/cancel` | Gradio4 cancel. | `routes/gateway_sd.py` |
| `GET` | `/chat` | — | `extensions/builtin_hailo_genai/hailo_genai_ext.py` |
| `POST` | `/chat/completions` | — | `routes/llm_router.py` |
| `GET` | `/checkpoints` | Scan checkpoint directory for model files. | `extensions/builtin_lora_dataset_manager/core_impl/api_train.py` |
| `DELETE` | `/clear` | Delete all entries from the dictionary. | `extensions/builtin_tag_dictionary/tag_dict_ext.py` |
| `GET` | `/config` | Gradio4 schema/info/ping - needed for API type detection. | `routes/gateway_sd.py` |
| `POST` | `/convert` | — | `extensions/builtin_prompt_simulator/core_impl/prompt_sim_routes.py` |
| `GET` | `/crypto-tools` | — | `routes/crypto_tools.py` |
| `GET` | `/crypto_tools` | Legacy underscore URL → canonical hyphen URL. | `routes/pages.py` |
| `GET` | `/danbooru-ac` | — | `extensions/builtin_prompt_simulator/core_impl/prompt_sim_routes.py` |
| `GET` | `/defaults` | — | `routes/gateway_backends.py` |
| `PATCH` | `/defaults` | — | `routes/gateway_backends.py` |
| `GET` | `/diagnostics` | Diagnostics and bug report export page. | `routes/pages.py` |
| `POST` | `/dp-analyze` | — | `extensions/builtin_prompt_simulator/core_impl/prompt_sim_routes.py` |
| `POST` | `/emphasis` | — | `extensions/builtin_prompt_simulator/core_impl/prompt_sim_routes.py` |
| `GET` | `/engine.js` | — | `extensions/builtin_prompt_syntax/prompt_syntax.py` |
| `GET` | `/ext/github` | Main GitHub Integration WebUI. | `extensions/builtin_github_integration/core_impl/api.py` |
| `GET` | `/extensions` | Extension Manager page. | `routes/pages.py` |
| `GET` | `/favicon.ico` | favicon.ico → SVG or PNG fallback (checks active UI then default) | `routes/pages.py` |
| `GET` | `/file=<path:filepath>` | Image file fetch. Path traversal protected. | `routes/gateway_sd.py` |
| `GET` | `/fleet/peer-allowlist-status` | — | `extensions/builtin_lan_cowork/core_impl/fleet/fleet_routes_allowlists.py` |
| `POST` | `/fleet/peer-grant` | — | `extensions/builtin_lan_cowork/core_impl/fleet/fleet_routes_allowlists.py` |
| `POST` | `/fleet/peer-revoke` | — | `extensions/builtin_lan_cowork/core_impl/fleet/fleet_routes_allowlists.py` |
| `GET` | `/fleet/peers` | — | `extensions/builtin_lan_cowork/core_impl/fleet/fleet_routes_core.py` |
| `POST` | `/fleet/restart/dispatch` | — | `extensions/builtin_lan_cowork/core_impl/fleet/fleet_routes_restart.py` |
| `GET` | `/fleet/static/<path:filename>` | — | `extensions/builtin_lan_cowork/core_impl/fleet/fleet_routes_static.py` |
| `GET` | `/fleet/ui` | — | `extensions/builtin_lan_cowork/core_impl/fleet/fleet_routes_core.py` |
| `POST` | `/fleet/update/dispatch` | — | `extensions/builtin_lan_cowork/core_impl/fleet/fleet_routes_update_dispatch.py` |
| `GET` | `/fleet/update/dispatch/status` | — | `extensions/builtin_lan_cowork/core_impl/fleet/fleet_routes_update_dispatch.py` |
| `GET` | `/gateway` | Gateway backend management page. | `routes/pages.py` |
| `GET` | `/github` | Legacy URL → GitHub Integration extension page. | `routes/pages.py` |
| `GET` | `/groups` | — | `routes/gateway_backends.py` |
| `POST` | `/groups` | — | `routes/gateway_backends.py` |
| `DELETE` | `/groups/<group_id>` | — | `routes/gateway_backends.py` |
| `PATCH` | `/groups/<group_id>` | — | `routes/gateway_backends.py` |
| `GET` | `/headroom` | Headroom proxy statistics page. | `routes/pages.py` |
| `GET` | `/headroom/config` | — | `routes/headroom_api.py` |
| `PUT` | `/headroom/config` | — | `routes/headroom_api.py` |
| `GET` | `/help` | Help top page (show first section of user guide). | `routes/help.py` |
| `GET` | `/help/<section>` | Section page. | `routes/help.py` |
| `POST` | `/import` | Upload and import a CSV file. | `extensions/builtin_tag_dictionary/tag_dict_ext.py` |
| `GET` | `/info` | Gradio4 schema/info/ping - needed for API type detection. | `routes/gateway_sd.py` |
| `GET` | `/inspect` | Metadata inspection page. | `routes/pages.py` |
| `GET` | `/internal/ping` | Gradio4 schema/info/ping - needed for API type detection. | `routes/gateway_sd.py` |
| `POST` | `/internal/progress` | Gradio4 progress check. | `routes/gateway_sd.py` |
| `GET` | `/keys` | — | `routes/gateway_admin.py` |
| `POST` | `/keys` | — | `routes/gateway_admin.py` |
| `DELETE` | `/keys/<key_id>` | — | `routes/gateway_admin.py` |
| `PATCH` | `/keys/<key_id>` | — | `routes/gateway_admin.py` |
| `GET` | `/lan-cowork` | LAN Cowork peer import dashboard. | `routes/pages.py` |
| `GET` | `/lan-cowork/peers` | Redirect legacy URL to extension blueprint. | `routes/pages.py` |
| `GET` | `/lan_cowork` | Legacy underscore URL → canonical hyphen URL. | `routes/pages.py` |
| `GET` | `/llm-router` | LLM Router admin dashboard. | `routes/pages.py` |
| `GET` | `/llm_router` | Legacy underscore URL → canonical hyphen URL. | `routes/pages.py` |
| `POST` | `/load-wildcards-zip` | — | `extensions/builtin_prompt_simulator/core_impl/prompt_sim_wildcards.py` |
| `GET` | `/local/status` | — | `routes/gateway_backends.py` |
| `GET` | `/manager` | — | `extensions/builtin_prompt_simulator/core_impl/prompt_sim_routes.py` |
| `GET` | `/mcp` | SSE stream — establish an MCP session. | `routes/mcp_endpoint.py` |
| `POST` | `/mcp` | POST /mcp — stateless JSON-RPC (single request). | `routes/mcp_endpoint.py` |
| `POST` | `/mcp/message` | Receive an MCP message — process JSON-RPC request. | `routes/mcp_endpoint.py` |
| `GET` | `/memories/<memory_id>` | — | `routes/gateway_agentmemory.py` |
| `GET` | `/mesh-inference` | Mesh inference disable matrix dashboard. | `routes/pages.py` |
| `GET` | `/mesh_inference` | Legacy underscore URL → canonical hyphen URL. | `routes/pages.py` |
| `POST` | `/messages` | — | `routes/llm_router.py` |
| `GET` | `/models` | — | `routes/llm_router_meta.py` |
| `POST` | `/nai-to-sd` | — | `extensions/builtin_sd_nai_convert/core_impl/sd_nai_convert_api.py` |
| `GET` | `/notes` | — | `extensions/builtin_annotations/annotations_ext.py` |
| `GET` | `/notes-data` | — | `extensions/builtin_annotations/annotations_ext.py` |
| `GET` | `/peers` | — | `extensions/builtin_lan_cowork/lan_cowork_ext.py` |
| `GET` | `/projects` | — | `extensions/builtin_lora_dataset_manager/core_impl/api_projects.py` |
| `POST` | `/projects` | — | `extensions/builtin_lora_dataset_manager/core_impl/api_projects.py` |
| `DELETE` | `/projects/<int:pid>` | — | `extensions/builtin_lora_dataset_manager/core_impl/api_projects.py` |
| `GET` | `/projects/<int:pid>` | — | `extensions/builtin_lora_dataset_manager/core_impl/api_projects.py` |
| `PUT` | `/projects/<int:pid>` | — | `extensions/builtin_lora_dataset_manager/core_impl/api_projects.py` |
| `GET` | `/projects/<int:pid>/caption-preview` | Preview caption for a specific file in the project. | `extensions/builtin_lora_dataset_manager/core_impl/api_projects.py` |
| `POST` | `/projects/<int:pid>/export` | — | `extensions/builtin_lora_dataset_manager/core_impl/api_export.py` |
| `GET` | `/projects/<int:pid>/export/status` | — | `extensions/builtin_lora_dataset_manager/core_impl/api_export.py` |
| `GET` | `/projects/<int:pid>/tags` | Get aggregated tag summary for project files. | `extensions/builtin_lora_dataset_manager/core_impl/api_projects.py` |
| `POST` | `/projects/<int:pid>/train` | — | `extensions/builtin_lora_dataset_manager/core_impl/api_train.py` |
| `GET` | `/projects/<int:pid>/train/status` | — | `extensions/builtin_lora_dataset_manager/core_impl/api_train.py` |
| `GET` | `/report` | Monthly report page. | `routes/pages.py` |
| `GET` | `/router/capabilities/<path:target>` | — | `routes/llm_router_meta.py` |
| `POST` | `/router/estimate` | — | `routes/llm_router_meta.py` |
| `GET` | `/router/health` | — | `routes/llm_router_meta.py` |
| `POST` | `/router/refresh` | Force a fresh /v1/models poll for one or all backends. | `routes/llm_router_meta.py` |
| `GET` | `/s/<token>` | Guest collection view page. | `extensions/builtin_lan_share/core_impl/share_routes.py` |
| `GET` | `/s/<token>/download.zip` | ZIP download for guest — uses existing export logic. | `extensions/builtin_lan_share/core_impl/share_routes.py` |
| `GET` | `/s/<token>/thumb/<int:file_id>` | Proxy thumbnail for guest — scoped to allowed_file_ids. | `extensions/builtin_lan_share/core_impl/share_routes.py` |
| `GET` | `/scan-jobs` | Scan history and active jobs page. | `routes/pages.py` |
| `GET` | `/scan_jobs` | Legacy underscore URL → canonical hyphen URL. | `routes/pages.py` |
| `GET` | `/scheduler` | Task scheduler page. | `routes/pages.py` |
| `POST` | `/sd-to-nai` | — | `extensions/builtin_sd_nai_convert/core_impl/sd_nai_convert_api.py` |
| `GET` | `/search` | Search page (for dashboard UI; other UIs redirect to /). | `routes/pages.py` |
| `GET` | `/settings` | Settings page. | `routes/pages.py` |
| `GET` | `/share` | Display page for shared data after QR code scan. | `routes/share.py` |
| `POST` | `/split` | Return split candidates for comma-less tags. | `extensions/builtin_tag_dictionary/tag_dict_ext.py` |
| `POST` | `/start` | — | `extensions/builtin_auto_scan_watcher/auto_scan_watcher.py` |
| `GET` | `/stats` | Stats page. | `routes/pages.py` |
| `POST` | `/stop` | — | `extensions/builtin_auto_scan_watcher/auto_scan_watcher.py` |
| `GET` | `/story` | Story page. | `routes/pages.py` |
| `GET` | `/style.css` | — | `extensions/builtin_prompt_syntax/prompt_syntax.py` |
| `GET` | `/sw.js` | Service Worker — parity with Rust frontend.rs serve_sw(). | `routes/pages.py` |
| `GET` | `/sweep-axes` | — | `extensions/builtin_prompt_simulator/core_impl/prompt_sim_sweep_axes.py` |
| `GET` | `/sweep-axes-manager` | — | `extensions/builtin_prompt_simulator/core_impl/prompt_sim_sweep_axes.py` |
| `POST` | `/sweep-axis-config` | — | `extensions/builtin_prompt_simulator/core_impl/prompt_sim_sweep_axes.py` |
| `GET` | `/sweep/<sweep_id>` | Dedicated comparison view for a single Sweep run. | `routes/pages.py` |
| `GET` | `/tag-presets` | — | `extensions/builtin_lora_dataset_manager/core_impl/api_presets.py` |
| `POST` | `/tag-presets` | — | `extensions/builtin_lora_dataset_manager/core_impl/api_presets.py` |
| `DELETE` | `/tag-presets/<int:preset_id>` | — | `extensions/builtin_lora_dataset_manager/core_impl/api_presets.py` |
| `PUT` | `/tag-presets/<int:preset_id>` | — | `extensions/builtin_lora_dataset_manager/core_impl/api_presets.py` |
| `GET` | `/tauri-shell` | — | `routes/tauri_shell.py` |
| `GET` | `/tools` | Tools page. | `routes/pages.py` |
| `GET` | `/update` | Signed update package page. | `routes/pages.py` |
| `GET` | `/v1` | — | `extensions/builtin_hailo_genai/openai_chat_route_handlers.py` |
| `GET` | `/v1/` | — | `extensions/builtin_hailo_genai/openai_chat_route_handlers.py` |
| `POST` | `/v1/audio/transcriptions` | — | `extensions/builtin_hailo_genai/openai_media_routes.py` |
| `POST` | `/v1/chat/completions` | — | `extensions/builtin_hailo_genai/openai_chat_route_handlers.py` |
| `POST` | `/v1/embeddings` | — | `extensions/builtin_hailo_genai/openai_media_routes.py` |
| `GET` | `/v1/models` | — | `extensions/builtin_hailo_genai/openai_chat_route_handlers.py` |
| `GET` | `/v1/node/services` | — | `routes/gateway_status.py` |
| `GET` | `/v1/router/capabilities` | — | `routes/gateway_status.py` |
| `GET` | `/widget.js` | — | `extensions/builtin_prompt_syntax/prompt_syntax.py` |
| `POST` | `/wildcard-delete` | — | `extensions/builtin_prompt_simulator/core_impl/prompt_sim_wildcards.py` |
| `POST` | `/wildcard-dirs` | — | `extensions/builtin_prompt_simulator/core_impl/prompt_sim_wildcards.py` |
| `POST` | `/wildcard-file` | — | `extensions/builtin_prompt_simulator/core_impl/prompt_sim_wildcards.py` |
| `POST` | `/wildcard-rename` | — | `extensions/builtin_prompt_simulator/core_impl/prompt_sim_wildcards.py` |
| `GET` | `/wildcards` | — | `extensions/builtin_prompt_simulator/core_impl/prompt_sim_wildcards.py` |
