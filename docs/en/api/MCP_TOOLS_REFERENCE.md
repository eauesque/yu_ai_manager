# MCP Tools Reference

This is a complete list of tools provided by the YU AI Manager MCP (Model Context Protocol) server.
Claude Desktop and other MCP clients can call these tools to automate library management, analysis, and generation.

**Total tools: 521**

## Table of Contents

- [Search & Browse (10)](#search--browse-10)
- [Collections (7)](#collections-7)
- [Ratings & Tags (5)](#ratings--tags-5)
- [Favorites (8)](#favorites-8)
- [Annotations (4)](#annotations-4)
- [Scanning (14)](#scanning-14)
- [Scan Roots (9)](#scan-roots-9)
- [Hash & Duplicates (7)](#hash--duplicates-7)
- [Wait / Progress (2)](#wait--progress-2)
- [AI Analysis (25)](#ai-analysis-25)
- [WD-Tagger (15)](#wd-tagger-14)
- [Semantic Search / CLIP (12)](#semantic-search--clip-12)
- [YOLO Object Detection (17)](#yolo-object-detection-17)
- [OCR (19)](#ocr-19)
- [SD WebUI Bridge (14)](#sd-webui-bridge-14)
- [ComfyUI Bridge (13)](#comfyui-bridge-13)
- [NovelAI Bridge (8)](#novelai-bridge-8)
- [Hailo GenAI (10)](#hailo-genai-10)
- [Hailo Chat (7)](#hailo-chat-7)
- [Hailo Remote Tagger (7)](#hailo-remote-tagger-7)
- [Tagger Server Registry (13)](#tagger-server-registry-13)
- [Prompt Library (21)](#prompt-library-21)
- [Prompt Simulator (6)](#prompt-simulator-6)
- [Prompt Syntax (1)](#prompt-syntax-1)
- [SD/NAI Conversion (3)](#sdnai-conversion-3)
- [Chat Logs (16)](#chat-logs-16)
- [Markdown Viewer (8)](#markdown-viewer-8)
- [Freeze & Pull-back (6)](#freeze--pull-back-6)
- [Speech-to-Text (8)](#speech-to-text-8)
- [Statistics (6)](#statistics-6)
- [Profiles (11)](#profiles-11)
- [File Operations (4)](#file-operations-4)
- [SVG Rasterization (2)](#svg-rasterization-2)
- [Download (1)](#download-1)
- [Video Analysis (3)](#video-analysis-3)
- [Backup (5)](#backup-5)
- [Archive Cleanup (7)](#archive-cleanup-7)
- [Auto Scan Watcher (3)](#auto-scan-watcher-3)
- [Scheduler (6)](#scheduler-6)
- [Webhooks (9)](#webhooks-9)
- [Extensions (25)](#extensions-25)
- [UI Management (4)](#ui-management-4)
- [Settings (18)](#settings-18)
- [SNS Sharing (15)](#sns-sharing-15)
- [LAN Share (2)](#lan-share-2)
- [MCP Client (8)](#mcp-client-8)
- [Cross Search (9)](#cross-search-9)
- [Tag Dictionary (6)](#tag-dictionary-6)
- [Trophies (1)](#trophies-1)
- [Source Code Browsing (3)](#source-code-browsing-3)
- [Help (3)](#help-3)
- [System Info (3)](#system-info-3)
- [System Update (5)](#system-update-5)
- [Suggestions (4)](#suggestions-4)
- [Logs & Debug (9)](#logs--debug-9)
- [Agent Safety Gateway (25)](#agent-safety-gateway-25)
- [GitHub Integration (12)](#github-integration-12)
- [Debug Tools (9)](#debug-tools-9)
- [LoRA Dataset Manager (15)](#lora-dataset-manager-14)
- [LLM Endpoints (5)](#llm-endpoints-5)
- [LLM Chat (1)](#llm-chat-1)
- [Server Mode (1)](#server-mode-1)

---

## Setup

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `YU_BASE_URL` | YU AI Manager server URL | `http://localhost:5000` |
| `YU_API_KEY` | API Key (Bearer authentication) | (none) |
| `YU_DEBUG_MODE` | Set to `1` to enable debug tools | `0` |

### Claude Desktop Configuration Example (`claude_desktop_config.json`)

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "/path/to/venv/bin/python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

### Progress Notifications

The `wait_for_scan` / `wait_for_batch` tools support MCP Notifications:
- **Clients with progressToken support**: Real-time progress is received via `notifications/progress`.
- **Clients without support**: The call blocks until completion, then returns the final result.

---

## Search & Browse (10)

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_images` | Search images with various filters | `query`: str = '', `sort`: str = 'date', `limit`: int = 20, `cursor`: str = '', `from_date`: str = '', `to_date`: str = '', `file_format`: str = 'all', `min_rating`: str = '', `max_rating`: str = '', `in_prompt`: str = '', `fav_only`: bool = False, `collection_id`: int = 0, `also_path`: bool = False |
| `search_images_grouped` | Search images with directory grouping | `query`: str = '', `sort`: str = 'date', `limit`: int = 20, `from_date`: str = '', `to_date`: str = '' |
| `search_union` | Union search across multiple queries | `queries`: list |
| `get_image_detail` | Retrieve all metadata for an image | `file_id`: int |
| `get_library_stats` | Library statistics | -- |
| `get_file_info` | File path and metadata information | `file_id`: int |
| `get_groups_index` | Directory group index | -- |
| `get_group_members` | List members within a group | `group`: str |
| `get_container_members` | List members within a ZIP/RAR container | `file_id`: int |
| `file_search` | Search files by path/name in the database | `query`: str, `meta_filter`: str = "all", `limit`: int = 100 |

## Collections (7)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_collections` | List all collections | -- |
| `create_collection` | Create a collection | `name`: str |
| `rename_collection` | Rename a collection | `collection_id`: int, `name`: str |
| `delete_collection` | Delete a collection | `collection_id`: int |
| `reorder_collections` | Change collection order | `order`: list |
| `add_to_collection` | Add images to a collection | `collection_id`: int, `file_ids`: list, `expected_count`: int = 0 |
| `remove_from_collection` | Remove images from a collection | `collection_id`: int, `file_ids`: list, `expected_count`: int = 0 |

## Ratings & Tags (5)

| Tool | Description | Parameters |
|------|-------------|------------|
| `rate_images` | Set ratings for multiple images at once | `items`: list, `expected_count`: int = 0 |
| `get_ratings` | Retrieve file ratings | `file_ids`: str |
| `get_ratings_stats` | Rating statistics | -- |
| `set_tags` | Add/remove user tags for multiple images | `items`: list, `expected_count`: int = 0 |
| `normalize_tags` | Normalize tags in the database | -- |

## Favorites (8)

| Tool | Description | Parameters |
|------|-------------|------------|
| `toggle_favorite` | Toggle favorite status | `file_id`: int |
| `check_favorite` | Check favorite status | `file_id`: int |
| `check_favorite_collections` | Check collection membership of a favorited file | `file_id`: int |
| `list_favorites` | List favorites | `limit`: int = 50, `offset`: int = 0 |
| `fav_batch_add` | Add multiple files to favorites | `file_ids`: list, `collection_id`: int = 1 |
| `fav_batch_remove` | Remove multiple files from favorites | `file_ids`: list, `collection_id`: int = 0 |
| `fav_export_folder` | Export favorites to a server folder | `dest_path`: str, `collection_id`: int = 0 |
| `fav_images` | List images in a favorites collection | `collection_id`: int = 0 |

## Annotations (4)

| Tool | Description | Parameters |
|------|-------------|------------|
| `set_annotations` | Save annotations (upsert) | `items`: list, `expected_count`: int = 0 |
| `get_annotations` | Retrieve annotations for an image | `file_id`: int, `source`: str = '', `key`: str = '' |
| `search_annotations` | Search annotations across files | `source`: str = '', `key`: str = '', `min_confidence`: str = '', `max_confidence`: str = '', `limit`: int = 100, `offset`: int = 0 |
| `delete_annotations` | Delete annotations | `source`: str, `file_ids`: Optional = None, `key`: str = '' |

## Scanning (14)

| Tool | Description | Parameters |
|------|-------------|------------|
| `trigger_scan` | Start a scan of all scan roots | -- |
| `start_scan` | Start a scan for a specified path or all roots | `path`: str = '' |
| `get_scan_status` | Retrieve scan progress | -- |
| `cancel_scan` | Cancel a scan | -- |
| `resume_scan` | Resume an interrupted scan | -- |
| `dismiss_interrupted_scan` | Discard interrupted state | -- |
| `get_scan_interrupted` | Retrieve interrupted scan information | -- |
| `get_scan_errors` | List scan errors | `error_type`: str = '', `resolved`: str = 'false', `limit`: int = 50 |
| `resolve_scan_error` | Mark an error as resolved | `error_id`: int |
| `clear_scan_errors` | Clear resolved errors | -- |
| `get_scanned_roots` | List scanned roots | -- |
| `scan_queue_list` | List pending items in the scan queue | -- |
| `scan_queue_remove` | Remove an item from the scan queue | `queue_id`: str |
| `scan_queue_clear` | Clear all items from the scan queue | -- |

## Scan Roots (9)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_scan_roots` | List scan roots | -- |
| `add_scan_root` | Add a scan root | `path`: str |
| `edit_scan_root` | Edit a scan root path | `index`: int, `path`: str |
| `remove_scan_root` | Remove a scan root | `index`: int |
| `toggle_scan_root` | Toggle scan root enabled/disabled | `index`: int |
| `reorder_scan_roots` | Change scan root order | `order`: list |
| `scan_directory` | Scan a specific directory | `path`: str |
| `get_checkpoints` | List available model checkpoints | -- |
| `purge_scanned_roots` | Purge scanned root records | -- |

## Hash & Duplicates (7)

| Tool | Description | Parameters |
|------|-------------|------------|
| `find_duplicates` | Detect duplicate files | `method`: str = 'hash' |
| `find_similar` | Search similar images by perceptual hash | `file_id`: int, `threshold`: int = 5 |
| `compute_hashes` | Start a file hash computation job | `hash_type`: str = 'both' |
| `delete_duplicates` | Delete duplicate files | `groups`: list, `mode`: str = 'soft' |
| `start_hash_backfill` | Start batch computation of uncalculated hashes | -- |
| `cancel_hash_backfill` | Cancel hash computation | -- |
| `get_hash_backfill_status` | Retrieve hash computation progress | -- |

## Wait / Progress (2)

| Tool | Description | Parameters |
|------|-------------|------------|
| `wait_for_scan` | Wait until scan completion (progress notifications supported) | `timeout`: int = 600 |
| `wait_for_batch` | Wait until batch job completion (progress notifications supported) | `job_id`: str = 'ai_analysis', `timeout`: int = 600 |

## AI Analysis (25)

| Tool | Description | Parameters |
|------|-------------|------------|
| `analyze_image` | AI analysis of a single image | `file_id`: int |
| `analyze_batch` | Batch AI analysis of multiple images | `file_ids`: list, `expected_count`: int = 0, `server_ids`: list = None |
| `analyze_batch_cancel` | Cancel a running AI analysis batch job | -- |
| `get_analysis_result` | Retrieve analysis result | `file_id`: int |
| `get_analysis_stats` | Analysis statistics | -- |
| `get_analysis_config` | Retrieve analysis configuration | -- |
| `save_analysis_config` | Save analysis configuration | `config`: dict |
| `get_available_engines` | List available engines | -- |
| `get_ollama_models` | List Ollama models | -- |
| `test_ollama_connection` | Test Ollama connection | -- |
| `get_openai_compat_models` | List OpenAI-compatible API models | -- |
| `test_openai_compat_connection` | Test OpenAI-compatible API connection | -- |
| `list_ai_servers` | List registered AI servers | -- |
| `add_ai_server` | Register an AI server | `name`: str, `type`: str, `config`: dict, `priority`: int = 50, `enabled`: bool = True |
| `update_ai_server` | Update AI server settings | `server_id`: str, `name`: str = '', `config`: dict = None, `priority`: int = -1, `enabled`: bool = True |
| `remove_ai_server` | Remove an AI server | `server_id`: str |
| `set_active_ai_server` | Switch active server | `server_id`: str |
| `test_ai_server` | Test AI server connection | `server_id`: str |
| `reorder_ai_servers` | Change server priority order | `order`: list |
| `migrate_ai_servers` | Migrate from legacy settings | -- |
| `analyze_prompt_trends` | Analyze prompt trends | `limit`: int = 100 |
| `get_trend_history` | Retrieve trend analysis history | `limit`: int = 20 |
| `delete_trend_history` | Delete trend history | `history_id`: int |
| `analyze_video` | Multi-keyframe video analysis via vision LLM | `file_id`: int, `engine`: str = "", `model`: str = "", `keyframe_count`: int = 4 |
| `transcribe_audio` | Transcribe audio/video file using Whisper | `file_id`: int, `engine`: str = "", `model`: str = "", `language`: str = "" |
| `get_audio_analysis_status` | Check audio analysis availability (ffmpeg, whisper) | -- |

## WD-Tagger (15)

| Tool | Description | Parameters |
|------|-------------|------------|
| `wd_tagger_tag_file` | Run tag inference on a single file | `file_id`: int |
| `wd_tagger_batch` | Run batch tag inference on multiple files | `file_ids`: list, `expected_count`: int = 0 |
| `wd_tagger_batch_cancel` | Cancel a running WD-Tagger batch job | -- |
| `wd_tagger_get_tags` | Retrieve WD-Tagger tags for a file | `file_id`: int |
| `wd_tagger_delete_tags` | Delete WD-Tagger tags for a file | `file_id`: int |
| `wd_tagger_delete_tags_batch` | Delete WD-Tagger tags for multiple files at once | `file_ids`: list, `expected_count`: int = 0 |
| `wd_tagger_get_xmp` | Retrieve XMP metadata | `file_id`: int |
| `wd_tagger_stats` | Tag statistics | -- |
| `wd_tagger_untagged` | List untagged files | `limit`: int = 50, `offset`: int = 0 |
| `wd_tagger_get_config` | Retrieve configuration | -- |
| `wd_tagger_save_config` | Save configuration | `config`: dict |
| `wd_tagger_model_status` | Model download status | -- |
| `wd_tagger_download_model` | Download model | -- |
| `wd_tagger_vlm_test` | Test VLM server connection | `url`: str |
| `wd_tagger_vlm_models` | List VLM server models | `url`: str |

## Semantic Search / CLIP (12)

| Tool | Description | Parameters |
|------|-------------|------------|
| `semantic_search` | Search images with natural language text | `query`: str, `limit`: int = 50, `threshold`: float = 0.2 |
| `semantic_status` | Extension status | -- |
| `semantic_backend_info` | CLIP backend information | -- |
| `semantic_model_status` | Model status | -- |
| `semantic_model_download` | Download CLIP model | -- |
| `semantic_index_start` | Start index building | `batch_size`: int = 32, `backend`: str = 'auto' |
| `semantic_index_status` | Index progress | -- |
| `semantic_index_stop` | Stop index building | -- |
| `semantic_index_clear` | Clear index | -- |
| `semantic_caption_start` | Start batch caption generation | `batch_size`: int = 50 |
| `semantic_caption_status` | Caption progress | -- |
| `semantic_caption_stop` | Stop captioning | -- |

## YOLO Object Detection (17)

| Tool | Description | Parameters |
|------|-------------|------------|
| `yolo_status` | Extension status | -- |
| `yolo_detect_start` | Start object detection | `file_ids`: list = None, `undetected_only`: bool = True |
| `yolo_detect_status` | Detection job progress | -- |
| `yolo_detect_stop` | Stop detection | -- |
| `yolo_get_results` | Retrieve detection results for a file | `file_id`: int |
| `yolo_search` | Search images by detection labels | `labels`: str = '', `min_confidence`: float = 0.0, `limit`: int = 50, `offset`: int = 0 |
| `yolo_clear_results` | Clear detection results | `file_ids`: list = None |
| `yolo_model_status` | Model status | -- |
| `yolo_model_download` | Download YOLO HEF model | -- |
| `yolo_list_labels` | List detected labels | -- |
| `yolo_stream_sources` | List stream sources and status | -- |
| `yolo_stream_start` | Start stream source | `source_id`: str |
| `yolo_stream_stop` | Stop stream source | `source_id`: str |
| `yolo_stream_add_source` | Add stream source | `id`: str, `url`: str, `name`: str = "" |
| `yolo_stream_rules` | List detection rules | -- |
| `yolo_stream_add_rule` | Add detection rule | `id`: str, `name`: str, `classes`: list, `min_confidence`: float = 0.7, `cooldown_sec`: int = 60, `actions`: list = [] |
| `yolo_stream_status` | Overall stream status (pipeline, sources, rules, recorder) | -- |

## OCR (19)

| Tool | Description | Parameters |
|------|-------------|------------|
| `ocr_extract` | Run OCR text extraction on an image | `file_id`: int, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "" |
| `ocr_batch` | Run OCR on multiple files | `file_ids`: list, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "", `expected_count`: int = 0 |
| `ocr_get_result` | Get OCR result for a file | `file_id`: int, `task`: str = "", `engine`: str = "", `all_results`: bool = False |
| `ocr_delete` | Delete OCR result for a file | `file_id`: int, `task`: str = "", `engine`: str = "" |
| `ocr_export` | Export OCR result in specified format | `file_id`: int, `format`: str = "md", `task`: str = "" |
| `ocr_translate` | Translate OCR result | `file_id`: int, `target_lang`: str = "en", `server_id`: str = "", `task`: str = "" |
| `ocr_get_translations` | Get translation results for a file | `file_id`: int, `target_lang`: str = "" |
| `ocr_video` | Run OCR on video keyframes | `file_id`: int, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "", `keyframe_count`: int = 4 |
| `ocr_bbox` | Run bounding-box detection on OCR result | `file_id`: int, `task`: str = "", `server_id`: str = "" |
| `ocr_overlay` | Generate OCR overlay image | `file_id`: int, `mode`: str = "translated", `target_lang`: str = "", `format`: str = "png" |
| `ocr_export_batch` | Batch export OCR results | `file_ids`: list, `format`: str = "", `output_dir`: str = "", `overlay_mode`: str = "translated", `target_lang`: str = "" |
| `ocr_pdf` | Run OCR on PDF document | `file_id`: int, `task`: str = "ocr_document", `language`: str = "auto", `server_id`: str = "", `page_range`: str = "" |
| `ocr_engines` | List available OCR engines with capability scores | -- |
| `ocr_profiles` | List all model capability profiles | -- |
| `ocr_profiles_fetch` | Fetch and merge community model profiles from URL | `url`: str |
| `ocr_profile_update` | Manually update a model's capability scores | `model_prefix`: str, `scores`: dict |
| `ocr_benchmark` | Run OCR benchmark for accuracy measurement | `task`: str = "ocr", `server_id`: str = "", `benchmark_dir`: str = "" |
| `ocr_benchmark_cases` | List available benchmark test cases | `benchmark_dir`: str = "" |
| `ocr_npu_status` | Check NPU availability and optimization suggestions | `task`: str = "ocr" |

## SD WebUI Bridge (14)

| Tool | Description | Parameters |
|------|-------------|------------|
| `sd_test_connection` | Test connection | -- |
| `sd_generate` | txt2img image generation | `prompt`: str, `negative_prompt`: str = '', `steps`: int = 28, `sampler`: str = 'Euler a', `cfg_scale`: float = 7.0, `width`: int = 512, `height`: int = 768, `seed`: int = -1, `expand_wildcards`: bool = False |
| `sd_get_progress` | Generation progress | -- |
| `sd_cancel` | Cancel generation | -- |
| `sd_list_models` | List checkpoint models | -- |
| `sd_list_samplers` | List samplers | -- |
| `sd_list_loras` | List LoRAs | `q`: str = '' |
| `sd_list_embeddings` | List embeddings | `q`: str = '' |
| `sd_list_scripts` | List scripts | -- |
| `sd_get_script_info` | Script details | -- |
| `sd_list_extensions` | List extensions | -- |
| `sd_list_upscalers` | List upscalers | -- |
| `sd_get_config` | Retrieve configuration | -- |
| `sd_save_config` | Save configuration | `api_url`: str = '', `save_folder`: str = '', `auto_save`, `auto_import`, `default_sampler`: str = '' |

## ComfyUI Bridge (13)

| Tool | Description | Parameters |
|------|-------------|------------|
| `comfyui_test_connection` | Test connection | -- |
| `comfyui_generate` | txt2img image generation | `prompt`: str, `negative_prompt`: str = '', `steps`: int = 20, `sampler_name`: str = 'euler', `scheduler`: str = 'normal', `cfg`: float = 7.0, `width`: int = 512, `height`: int = 768, `seed`: int = -1, `ckpt_name`: str = '', `expand_wildcards`: bool = False, `image_format`: str = 'png' |
| `comfyui_generate_json` | Generate from a JSON workflow | `workflow`: str |
| `comfyui_get_progress` | Generation progress | -- |
| `comfyui_cancel` | Cancel generation | -- |
| `comfyui_list_models` | List checkpoint models | -- |
| `comfyui_list_samplers` | List samplers | -- |
| `comfyui_list_schedulers` | List schedulers | -- |
| `comfyui_list_loras` | List LoRAs | `q`: str = '' |
| `comfyui_list_embeddings` | List embeddings | `q`: str = '' |
| `comfyui_list_custom_nodes` | List custom nodes | `q`: str = '' |
| `comfyui_get_config` | Retrieve configuration | -- |
| `comfyui_save_config` | Save configuration | `api_url`: str = '', `save_folder`: str = '', `auto_save`, `auto_import`, `default_sampler`: str = '', `default_scheduler`: str = '' |

## NovelAI Bridge (8)

| Tool | Description | Parameters |
|------|-------------|------------|
| `nai_test_connection` | Test connection | -- |
| `nai_get_anlas` | Retrieve Anlas balance | -- |
| `nai_generate` | Image generation | `prompt`: str, `negative_prompt`: str = '', `width`: int = 832, `height`: int = 1216, `steps`: int = 28, `sampler`: str = '', `noise_schedule`: str = '', `seed`: int = -1, `model`: str = '', `cfg_scale`: float = 5.0 |
| `nai_list_models` | List models | -- |
| `nai_list_samplers` | List samplers | -- |
| `nai_list_noise_schedules` | List noise schedules | -- |
| `nai_get_config` | Retrieve configuration | -- |
| `nai_save_config` | Save configuration | `api_key`: str = '', `save_folder`: str = '', `auto_save`: bool = True, `auto_import`: bool = True, `default_model`: str = '' |

## Hailo GenAI (10)

| Tool | Description | Parameters |
|------|-------------|------------|
| `hailo_genai_status` | Extension status | -- |
| `hailo_genai_model_status` | Model load status | -- |
| `hailo_genai_model_download` | Download model | `model_name`: str = '' |
| `hailo_genai_model_unload` | Unload model | -- |
| `hailo_llm_generate` | LLM text generation | `prompt`: str, `max_tokens`: int = 256, `temperature`: float = 0.7, `system_prompt`: str = '' |
| `hailo_llm_clear_context` | Clear LLM context | -- |
| `hailo_vlm_generate` | VLM image-to-text generation | `file_id`: int, `prompt`: str = 'Describe this image.', `max_tokens`: int = 256 |
| `hailo_benchmark` | Run Hailo LLM performance benchmark | `prompt`: str, `runs`: int = 3, `max_tokens`: int = 256, `temperature`: float = 0.7, `model`: str = "qwen2.5-1.5b-chat" |
| `hailo_benchmark_compare` | Compare Hailo vs Ollama LLM performance | `prompt`: str, `runs`: int = 3, `max_tokens`: int = 256, `hailo_model`: str, `ollama_model`: str |
| `hailo_genai_openai_info` | Get OpenAI-compatible API endpoint info for Hailo GenAI | -- |

## Hailo Chat (7)

| Tool | Description | Parameters |
|------|-------------|------------|
| `hailo_chat_new` | Create a new Hailo Chat conversation | `model`: str = "qwen2.5-1.5b-chat" |
| `hailo_chat_list` | List Hailo Chat conversations | `limit`: int = 50, `offset`: int = 0 |
| `hailo_chat_get` | Get a conversation with all messages | `conversation_id`: int |
| `hailo_chat_active` | Get the currently active conversation ID | -- |
| `hailo_chat_search` | Web search via DuckDuckGo for context injection | `query`: str, `max_results`: int = 5 |
| `hailo_chat_rename` | Rename a conversation | `conversation_id`: int, `title`: str |
| `hailo_chat_delete` | Delete a conversation | `conversation_id`: int |

## Hailo Remote Tagger (7)

| Tool | Description | Parameters |
|------|-------------|------------|
| `hailo_tagger_tag_file` | Run Hailo remote tagger on a single file | `file_id`: int |
| `hailo_tagger_batch` | Batch tag multiple files (max 500) | `file_ids`: list, `expected_count`: int = 0 |
| `hailo_tagger_status` | Check Hailo remote tagger connection status | -- |
| `hailo_tagger_get_config` | Get Hailo remote tagger configuration | -- |
| `hailo_tagger_save_config` | Save Hailo remote tagger configuration | `config`: dict |
| `hailo_tagger_get_tags` | Get Hailo tags for a file | `file_id`: int |
| `hailo_tagger_delete_tags` | Delete Hailo tags for a file | `file_id`: int |

## Tagger Server Registry (13)

| Tool | Description | Parameters |
|------|-------------|------------|
| `tagger_servers_list` | List registered tagger servers and distribution mode | -- |
| `tagger_servers_add` | Add a tagger server | `name`: str, `type`: str, `config`: dict, `priority`: int = 50, `enabled`: bool = True |
| `tagger_servers_update` | Update tagger server settings | `server_id`: str, `updates`: dict |
| `tagger_servers_remove` | Remove a tagger server | `server_id`: str |
| `tagger_servers_test` | Test tagger server connectivity | `server_id`: str |
| `tagger_servers_health` | Health check all enabled servers | -- |
| `tagger_servers_set_mode` | Set distribution mode (single/parallel/idle_first) | `mode`: str |
| `tagger_servers_batch` | Distributed batch tagging (shared-queue work-stealing) | `file_ids`: list = None, `limit`: int = 500, `force`: bool = False, `threshold`: float = None |
| `tagger_servers_batch_cancel` | Cancel a running tagger cluster batch job | -- |
| `tagger_servers_tags` | Get tagger tags for a file | `file_id`: int |
| `tagger_servers_delete_tags` | Delete tagger tags for a file | `file_id`: int |
| `tagger_servers_stats` | Tagger statistics (untagged file count) | -- |
| `tagger_servers_migrate_legacy` | Migrate legacy hailo_tagger config to registry format | -- |

## Prompt Library (21)

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_prompts` | Search prompts | `query`: str = '', `folder_id`: int = 0, `tag_id`: int = 0, `sort`: str = 'updated_at', `order`: str = 'desc', `limit`: int = 50, `offset`: int = 0 |
| `get_prompt` | Retrieve prompt details | `prompt_id`: int |
| `create_prompt` | Create a prompt | `title`: str, `positive`: str = '', `negative`: str = '', `memo`: str = '', ... |
| `create_prompt_from_file` | Create a prompt from image metadata | `file_id`: int |
| `update_prompt` | Update a prompt (partial update) | `prompt_id`: int, ... |
| `delete_prompt` | Delete a prompt | `prompt_id`: int |
| `list_prompt_folders` | List folders | -- |
| `create_prompt_folder` | Create a folder | `name`: str |
| `update_prompt_folder` | Rename a folder | `folder_id`: int, `name`: str |
| `delete_prompt_folder` | Delete a folder | `folder_id`: int |
| `move_prompt_to_folder` | Move a prompt to a folder | `prompt_id`: int, `folder_id`: int |
| `remove_prompt_from_folder` | Remove from folder (move to root) | `prompt_id`: int |
| `list_prompt_tags` | List tags | -- |
| `create_prompt_tag` | Create a tag | `name`: str |
| `delete_prompt_tag` | Delete a tag | `tag_id`: int |
| `set_prompt_tags` | Set tags for a prompt | `prompt_id`: int, `tag_ids`: list |
| `bulk_delete_prompts` | Bulk delete | `prompt_ids`: list |
| `bulk_move_prompts` | Bulk move | `prompt_ids`: list, `folder_id`: int |
| `bulk_tag_prompts` | Bulk tag | `prompt_ids`: list, `tag_ids`: list |
| `export_prompts` | Export all prompts as JSON | -- |
| `import_prompts` | Import prompts from JSON | `data`: dict |

## Prompt Simulator (6)

| Tool | Description | Parameters |
|------|-------------|------------|
| `prompt_dp_analyze` | Dynamic Prompts syntax analysis | `text`: str |
| `prompt_emphasis` | Emphasis syntax conversion | `text`: str, `format`: str = 'a1111' |
| `prompt_convert` | A1111 <-> NAI format conversion | `text`: str, `from_format`: str = 'a1111', `to_format`: str = 'nai' |
| `prompt_list_wildcards` | List wildcards | -- |
| `prompt_set_wildcard_dirs` | Set wildcard directories | `dirs`: list |
| `prompt_danbooru_autocomplete` | Danbooru tag autocomplete | `q`: str |

## Prompt Syntax (1)

| Tool | Description | Parameters |
|------|-------------|------------|
| `analyze_prompt_syntax` | Prompt syntax analysis (token information) | `text`: str, `engine`: str = 'a1111' |

## SD/NAI Conversion (3)

| Tool | Description | Parameters |
|------|-------------|------------|
| `convert_sd_to_nai` | SD to NAI prompt conversion | `text`: str |
| `convert_nai_to_sd` | NAI to SD prompt conversion | `text`: str |
| `convert_prompt_batch` | Batch prompt conversion | `items`: list, `direction`: str = 'sd-to-nai' |

## Chat Logs (16)

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_chat_logs` | FTS5 full-text search | `query`: str = '', `source`: str = '', `model`: str = '', `limit`: int = 50, ... |
| `search_chat_logs_grouped` | Search grouped by conversation | `query`: str, `source`: str = '', `limit`: int = 20 |
| `get_conversation` | Conversation detail (all messages) | `conversation_id`: int |
| `get_chat_full` | Alias for get_conversation | `conversation_id`: int |
| `get_chat_summary` | AI-generated summary | `conversation_id`: int |
| `get_chat_decisions` | AI-extracted decisions | `conversation_id`: int |
| `get_related_conversations` | Related conversations | `conversation_id`: int, `limit`: int = 10 |
| `find_chat_by_entity` | Search conversations by entity | `entity_type`: str, `entity_value`: str, `limit`: int = 50 |
| `search_chat_by_topic` | Search by topic | `topic`: str, `limit`: int = 50 |
| `search_decisions` | Search decisions across conversations | `query`: str, `limit`: int = 50 |
| `import_chat_log` | Import from a local file | `source`: str, `json_path`: str |
| `get_chatlog_import_status` | Import progress | -- |
| `get_chatlog_stats` | Chat log statistics | -- |
| `delete_conversation` | Delete a conversation | `conversation_id`: int |
| `reprocess_chat_logs` | AI reprocessing | `target`: str = 'unprocessed' |
| `text_search` | Cross-search across MD/chat/prompt | `query`: str, `target`: str = 'md,chat,prompt', `limit`: int = 20 |

## Markdown Viewer (8)

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_md_files` | Search Markdown files | `query`: str = '', `path_filter`: str = '', `limit`: int = 50, `offset`: int = 0 |
| `get_md_content` | Retrieve file content | `file_id`: int |
| `get_md_scan_roots` | List scan roots | -- |
| `set_md_scan_roots` | Set scan roots | `roots`: list |
| `remove_md_scan_root` | Remove a scan root | `index`: int |
| `trigger_md_scan` | Start a scan | -- |
| `get_md_scan_status` | Scan progress | -- |
| `get_md_stats` | Statistics | -- |

## Freeze & Pull-back (6)

| Tool | Description | Parameters |
|------|-------------|------------|
| `generate_freeze_pullback` | Generate a Ken Burns video | `file_id`: int, `hold_seconds`: float = 2.0, `pull_seconds`: float = 5.0, `fps`: int = 30, ... |
| `get_fpb_status` | Render job status | -- |
| `fpb_check` | Prerequisite check (ffmpeg, etc.) | -- |
| `fpb_cancel` | Cancel generation | -- |
| `fpb_list_outputs` | List output files | -- |
| `fpb_delete_output` | Delete an output file | `filename`: str |

## Speech-to-Text (8)

| Tool | Description | Parameters |
|------|-------------|------------|
| `s2t_status` | Backend status | -- |
| `s2t_transcribe_video` | Transcribe video/audio | `file_id`: int, `language`: str = '' |
| `s2t_batch_transcribe` | Batch transcription | `file_ids`: list, `language`: str = '', `expected_count`: int = 0 |
| `s2t_get_transcript` | Retrieve saved transcript | `file_id`: int |
| `s2t_stream_start` | Start stream transcription | `source_url`: str, `language`: str = 'ja', `mode`: str = 'chunk' |
| `s2t_stream_stop` | Stop stream transcription | -- |
| `s2t_stream_status` | Get stream status | -- |
| `s2t_stream_transcript` | Get stream transcript | -- |

## Statistics (6)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_stats_timeline` | Timeline statistics | `period`: str = 'daily' |
| `get_stats_hourly` | Hourly statistics | -- |
| `get_stats_models` | Model usage statistics | -- |
| `get_stats_resolutions` | Resolution distribution statistics | -- |
| `get_stats_story` | Library story narrative | -- |
| `get_monthly_report` | Monthly report | `month`: str = '' |

## Profiles (11)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_profiles` | List profiles | -- |
| `get_profile` | Retrieve a profile | `name`: str |
| `create_profile` | Create a profile | `name`: str, `description`: str = '' |
| `update_profile` | Update a profile | `name`: str, `settings`: dict |
| `delete_profile` | Delete a profile | `name`: str |
| `duplicate_profile` | Duplicate a profile | `name`: str, `new_name`: str |
| `rename_profile` | Rename a profile | `name`: str, `new_name`: str |
| `toggle_profile_favorite` | Toggle favorite | `name`: str |
| `export_profile` | Export a profile | `name`: str |
| `import_profile` | Import a profile from exported data | `qr_data`: str, `mode`: str = "full" |
| `import_profile_preview` | Preview a profile import before applying | `qr_data`: str |

## File Operations (4)

| Tool | Description | Parameters |
|------|-------------|------------|
| `convert_image` | Convert image format | `file_id`: int, `format`: str = 'webp' |
| `extract_from_zip` | Extract files from a ZIP | `file_id`: int, `members`: list |
| `inspect_metadata` | Inspect raw metadata | `file_id`: int |
| `get_share_link` | Generate a share link | `file_id`: int |

## SVG Rasterization (2)

| Tool | Description | Parameters |
|------|-------------|------------|
| `svg_info` | Check SVG rasterization availability and backend info | — |
| `svg_rasterize` | Rasterize an SVG to PNG/WebP bitmap. The returned base64 can be used directly as img2img input | `file_id`: int = 0, `svg_path`: str = '', `svg_data`: str = '', `width`: int = 1024, `height`: int = 1024, `format`: str = 'png', `background`: str = '' |

## Download (1)

| Tool | Description | Parameters |
|------|-------------|------------|
| `batch_download_zip` | Download multiple images as a ZIP | `file_ids`: list, `expected_count`: int = 0 |

## Video Analysis (3)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_video_analysis_config` | Retrieve video analysis configuration | -- |
| `save_video_analysis_config` | Save video analysis configuration | `config`: dict |
| `get_video_analysis_status` | Video analysis status | -- |

## Backup (5)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_backups` | List backups | -- |
| `create_backup` | Create a backup | -- |
| `restore_backup` | Restore a backup | `filename`: str |
| `delete_backup` | Delete a backup | `filename`: str |
| `get_backup_status` | Backup status | -- |

## Archive Cleanup (7)

| Tool | Description | Parameters |
|------|-------------|------------|
| `archive_cleanup_scan` | Scan for archive pairs | `path`: str = '' |
| `archive_cleanup_execute` | Execute cleanup | `actions`: list, `expected_count`: int = 0 |
| `archive_cleanup_llm_verify` | Verify action with LLM (single) | `file_path`: str, `action`: str |
| `archive_cleanup_llm_verify_batch` | Verify actions with LLM (batch) | `items`: list |
| `archive_cleanup_get_llm_config` | Retrieve LLM configuration | -- |
| `archive_cleanup_save_llm_config` | Save LLM configuration | `config`: dict |
| `archive_cleanup_list_models` | List available LLM models | -- |

## Auto Scan Watcher (3)

| Tool | Description | Parameters |
|------|-------------|------------|
| `auto_scan_info` | Watcher status | -- |
| `auto_scan_start` | Start file watching | -- |
| `auto_scan_stop` | Stop file watching | -- |

## Scheduler (6)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_scheduler_status` | Get task scheduler status and registered jobs | -- |
| `list_scheduled_jobs` | List all scheduled jobs with triggers and next run times | -- |
| `trigger_scheduled_job` | Trigger immediate execution of a scheduled job | `job_id`: str |
| `pause_scheduled_job` | Pause a scheduled job | `job_id`: str |
| `resume_scheduled_job` | Resume a paused scheduled job | `job_id`: str |
| `get_scheduler_history` | Get recent execution history of scheduled jobs | -- |

## Webhooks (9)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_webhooks` | List webhooks | -- |
| `create_webhook` | Create a webhook | `url`: str, `events`: list, `name`: str = '' |
| `update_webhook` | Update a webhook | `webhook_id`: str, `url`: str = '', `events`: list = None, `name`: str = '', `enabled`: bool = True |
| `delete_webhook` | Delete a webhook | `webhook_id`: str |
| `test_webhook` | Send a test event | `webhook_id`: str |
| `get_webhook_deliveries` | Delivery history | `webhook_id`: str = '', `limit`: int = 50 |
| `create_inbound_webhook` | Create an inbound webhook for external triggers. Returns a token URL. | `label`: str, `allowed_events`: list |
| `list_inbound_webhooks` | Get a list of registered inbound webhooks. | — |
| `delete_inbound_webhook` | Delete an inbound webhook. | `webhook_id`: str |

## Extensions (25)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_extensions` | List extensions | -- |
| `get_extension_detail` | Extension details | `name`: str |
| `toggle_extension` | Toggle enabled/disabled | `name`: str, `enabled`: bool |
| `install_extension` | Install from a Git repository | `url`: str |
| `update_extension` | Update an extension | `name`: str |
| `update_all_extensions` | Update all extensions at once | -- |
| `uninstall_extension` | Uninstall an extension | `name`: str |
| `search_marketplace` | Search the marketplace | `query`: str = '' |
| `refresh_marketplace` | Refresh marketplace catalog | -- |
| `get_extension_config` | Retrieve configuration | `name`: str |
| `set_extension_config` | Update configuration | `name`: str, `values`: dict |
| `get_extension_permissions` | Retrieve permission information | `name`: str |
| `approve_extension_permissions` | Approve/deny permissions | `name`: str, `granted`: list = None, `denied`: list = None, `action`: str = 'approve' |
| `scan_extension_code` | Static code analysis | `name`: str |
| `rescan_extension` | Rescan code | `name`: str |
| `get_extension_tokens` | Capability token status | `name`: str |
| `get_extension_integrity` | File integrity and monitoring status | `name`: str |
| `get_extension_hooks` | List registered hooks | -- |
| `get_extension_isolation_status` | Process isolation status | -- |
| `get_extension_os_isolation_status` | OS-level isolation status | -- |
| `create_extension` | Create a new custom extension with scaffold files | `name`: str, `description`: str = "" |
| `validate_extension` | Validate extension manifest and code | `extension_name`: str |
| `list_extension_files` | List files in a custom extension directory | `extension_name`: str |
| `read_extension_file` | Read a file from a custom extension | `extension_name`: str, `file_type`: str, `filename`: str |
| `write_extension_file` | Write a file to a custom extension | `extension_name`: str, `file_type`: str, `filename`: str, `content`: str |

## UI Management (4)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_uis` | List UIs | -- |
| `switch_ui` | Switch active UI | `name`: str |
| `install_ui` | Install a UI | `url`: str |
| `uninstall_ui` | Uninstall a UI | `name`: str |

## Settings (18)

| Tool | Description | Parameters |
|------|-------------|------------|
| `settings_get_schema` | Retrieve settings schema | -- |
| `settings_get_all` | Retrieve all settings | -- |
| `settings_get` | Retrieve a single setting | `key`: str |
| `settings_set` | Update a setting | `key`: str, `value`: str, `op_uri`: str = '' |
| `get_legacy_config` | Retrieve legacy config.json | -- |
| `save_legacy_config` | Save legacy config.json | `config`: dict |
| `secrets_status` | Encryption key status | -- |
| `secrets_export` | Export encryption key | `password`: str |
| `secrets_import` | Import encryption key | `export_json`: str, `password`: str |
| `get_op_status` | 1Password CLI status | -- |
| `delete_op_mapping` | Delete a 1Password mapping | `key`: str |
| `migrate_secrets_to_keychain` | Migrate to OS keychain | -- |
| `get_bw_status` | Get Bitwarden CLI integration status | -- |
| `list_bw_folders` | List available Bitwarden folders | -- |
| `delete_bw_mapping` | Delete a Bitwarden field mapping | `key`: str |
| `list_op_vaults` | List available 1Password vaults | -- |
| `push_secrets_to_1password` | Push all secrets to 1Password and auto-link op_secrets mappings | `vault`: str, `item_title`: str = "YU AI Manager" |
| `push_secrets_to_bitwarden` | Push all secrets to Bitwarden and auto-link mappings | `item_name`: str = "YU AI Manager", `folder_id`: str = "" |

## SNS Sharing (15)

| Tool | Description | Parameters |
|------|-------------|------------|
| `share_to_bluesky` | Post to Bluesky | `file_id`: int, `text`: str = '', `attach_image`: bool = True |
| `test_bluesky_connection` | Test Bluesky connection | -- |
| `get_x_share_url` | Retrieve X (Twitter) share URL | `file_id`: int |
| `get_sns_preview` | SNS share preview | `file_id`: int |
| `get_sns_config` | Retrieve SNS configuration | -- |
| `save_sns_config` | Save SNS configuration | `config`: dict |
| `bsky_get_pending_notifications` | Get pending Bluesky notifications from queue | -- |
| `bsky_get_notification_queue` | Get notification queue items with filters | `status`: str = "", `notification_type`: str = "" |
| `bsky_poll_notifications` | Trigger immediate Bluesky notification polling | -- |
| `bsky_triage_notification` | Set triage result for a notification | `queue_id`: int, `result`: str |
| `bsky_send_auto_response` | Send auto-response to a mention/reply/quote | `queue_id`: int, `text`: str |
| `bsky_get_monitor_config` | Get Bluesky monitor configuration | -- |
| `bsky_save_monitor_config` | Save Bluesky monitor configuration | `poll_interval_minutes`: int = 0, `auto_dismiss_follow`: bool = True, `auto_dismiss_like`: bool = True, `auto_dismiss_repost`: bool = True, `auto_respond_enabled`: bool = False |
| `bsky_get_triage_prompts` | Get Bluesky triage prompts and templates | -- |
| `bsky_save_triage_prompts` | Save Bluesky triage prompts | `triage_mention`: str = "", `triage_reply`: str = "", `triage_quote`: str = "", `response_mention`: str = "", `response_reply`: str = "" |

## LAN Share (2)

| Tool | Description | Parameters |
|------|-------------|------------|
| `create_lan_share` | Create a LAN share token | `collection_id`: int, `expires_hours`: int = 24 |
| `revoke_lan_share` | Revoke a share token | `token`: str |

## MCP Client (8)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_mcp_connections` | List MCP connections | -- |
| `create_mcp_connection` | Create an MCP connection | `name`: str, `command`: str, `args`: list = None, `env`: dict = None |
| `update_mcp_connection` | Update an MCP connection | `connection_id`: str, `name`: str = '', `command`: str = '', `args`: list = None, `env`: dict = None |
| `delete_mcp_connection` | Delete an MCP connection | `connection_id`: str |
| `connect_mcp_server` | Connect to an MCP server | `connection_id`: str |
| `disconnect_mcp_server` | Disconnect from an MCP server | `connection_id`: str |
| `get_mcp_connection_tools` | List tools from a connected server | `connection_id`: str |
| `call_mcp_tool` | Call a tool on a connected server | `connection_id`: str, `tool_name`: str, `arguments`: dict = None |

## Cross Search (9)

| Tool | Description | Parameters |
|------|-------------|------------|
| `cross_search_get_scan_roots` | Get cross-search scan root directories | -- |
| `cross_search_set_scan_roots` | Set cross-search scan root directories | `roots`: list |
| `cross_search_delete_scan_root` | Remove a cross-search scan root by index | `index`: int |
| `cross_search_scan` | Start a cross-search text file scan | -- |
| `cross_search_scan_stop` | Stop a running cross-search scan | -- |
| `cross_search_scan_status` | Get cross-search scan progress status | -- |
| `cross_search_get_txt` | Get text content of a cross-search indexed file | `file_id`: int |
| `cross_search_open_file` | Open a file in the system file manager | `path`: str |
| `cross_search_stats` | Get cross-search statistics | -- |

## Tag Dictionary (6)

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_tag_dictionary` | Search the tag dictionary | `query`: str, `limit`: int = 20, `fuzzy`: bool = False |
| `get_tag_dict_stats` | Tag dictionary statistics | -- |
| `split_tags` | Split concatenated tags | `text`: str |
| `import_tag_dictionary` | Import tag dictionary | `data`: dict |
| `clear_tag_dictionary` | Clear tag dictionary | -- |
| `get_tag_dict_info` | Get detailed info for a single tag | `tag`: str |

## Trophies (1)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_trophies` | List trophies | -- |

## Source Code Browsing (3)

Tools for safely browsing project source code in read-only mode.
Three security layers protect access: path normalization, extension whitelist, and sensitive file blocklist.
See [`docs/api/source.md`](source.md) for details.

| Tool | Description | Parameters |
|------|-------------|------------|
| `source_tree` | Display directory tree | `path`: str = '', `depth`: int = 3 |
| `source_read` | Read file contents (with line numbers) | `path`: str, `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | Search source code by text | `query`: str, `glob`: str = '', `limit`: int = 30 |

## Help (3)

| Tool | Description | Parameters |
|------|-------------|------------|
| `help_toc` | Help table of contents | -- |
| `help_get_section` | Retrieve section content | `section`: str |
| `help_search` | Search help | `query`: str, `limit`: int = 5 |

## System Info (3)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_server_info` | Server information | -- |
| `get_inference_info` | Inference engine information | -- |
| `get_market_quotes` | Market information | -- |

## System Update (5)

| Tool | Description | Parameters |
|------|-------------|------------|
| `check_for_update` | Check if a new version is available on GitHub | -- |
| `get_update_status` | Get current installation type and version | -- |
| `apply_system_update` | Apply available update (git/portable only) | `confirm`: str |
| `check_unified_updates` | Check update status for system + all extensions at once | `force`: bool (optional) |
| `apply_unified_updates` | Update system + extensions at once (auto-backup configs) | `update_system`: bool, `update_extensions`: bool, `extension_names`: list (optional) |

## Suggestions (4)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_suggestions` | Tag/prompt autocomplete | `q`: str, `limit`: int = 10 |
| `suggest_tags` | Tag autocomplete | `q`: str, `limit`: int = 10 |
| `suggest_lora` | LoRA name autocomplete | `q`: str = '' |
| `suggest_embedding` | Embedding name autocomplete | `q`: str = '' |

## Logs & Debug (9)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_recent_logs` | Retrieve recent logs | `limit`: int = 100 |
| `get_debug_log` | Output debug log | `lines`: int = 200 |
| `clear_debug_log` | Clear debug log | -- |
| `get_cache_info` | Cache statistics | -- |
| `clear_cache` | Clear cache | -- |
| `rebuild_groups` | Rebuild directory groups | -- |
| `list_dirs` | List directories | `path`: str = '' |
| `debug_file_meta` | File debug metadata | `file_id`: int |
| `debug_model_check` | Model availability check | -- |

## Agent Safety Gateway (25)

| Tool | Description | Parameters |
|------|-------------|------------|
| `agent_status` | Overall safety feature status | -- |
| `agent_kill` | Activate Kill Switch (block all tools immediately) | `reason`: str = 'Manual kill via MCP' |
| `agent_resume` | Deactivate Kill Switch | -- |
| `agent_circuit_breaker_status` | Circuit Breaker status | -- |
| `agent_circuit_breaker_reset` | Reset Circuit Breaker | -- |
| `agent_budget_status` | Budget Tracker status | -- |
| `agent_budget_reset` | Reset Budget Tracker | -- |
| `agent_approval_status` | List pending approval requests | -- |
| `agent_approval_respond` | Respond to an approval request | `request_id`: str, `action`: str |
| `agent_approval_history` | Approval history | `limit`: int = 50 |
| `agent_scope_status` | Scope Fence status | -- |
| `agent_scope_get` | Retrieve session scope | `session_id`: str |
| `agent_scope_set` | Set session scope | `preset`: str = 'organizer', `duration_hours`: float = 0 |
| `agent_scope_delete` | Delete session scope | `session_id`: str |
| `agent_tool_level` | Check tool safety level | `tool_name`: str = '' |
| `agent_auto_approve_list` | List auto-approve rules | -- |
| `agent_auto_approve_add` | Add an auto-approve rule | `tool_name`: str |
| `agent_auto_approve_remove` | Remove an auto-approve rule | `index`: int |
| `agent_undo` | Undo an action | `journal_id`: int |
| `agent_undoable` | List undoable actions | `session_id`: str = '', `limit`: int = 50 |
| `agent_journal` | Search the action journal | `tool_name`: str = '', `status`: str = '', `session_id`: str = '', `limit`: int = 50, `offset`: int = 0 |
| `agent_journal_stats` | Journal statistics | -- |
| `agent_anomaly_status` | Anomaly detection status | -- |
| `agent_anomaly_alerts` | Anomaly alert history | `limit`: int = 50 |
| `agent_anomaly_reset` | Reset anomaly detection | -- |

---

## GitHub Integration (12)

GitHub account issue monitoring, triage, and reporting.

| Tool | Description | Parameters |
|------|-------------|------------|
| `github_list_accounts` | List registered GitHub accounts (tokens masked) | — |
| `github_fetch_issues` | Fetch issues for an account's repositories | `account_label`: str, `state`: str = 'open', `since`: str = '' |
| `github_triage_issues` | Fetch and classify issues (valid_bug / skip / needs_info) with priority report | `account_label`: str, `state`: str = 'open', `since`: str = '' |
| `github_get_issue_detail` | Get issue detail formatted for Claude Code analysis, with comments | `account_label`: str, `repo`: str, `issue_number`: int |
| `github_rate_limit` | Check GitHub API rate limit for an account | `account_label`: str |
| `github_get_pending_issues` | Get pending issues from the local issue queue | -- |
| `github_get_issue_queue` | Get issue queue items with optional status filter | `status`: str = "" |
| `github_poll_issues` | Trigger immediate polling of GitHub issues | -- |
| `github_triage_queue_item` | Set triage result for a queued issue | `queue_id`: int, `result`: str |
| `github_dismiss_queue_item` | Dismiss a queued issue, optionally auto-close | `queue_id`: int, `auto_close`: bool = False, `account_label`: str = "" |
| `github_get_triage_prompts` | Get triage prompts for issue/PR/discussion | `repo`: str = "" |
| `github_save_triage_prompts` | Save triage prompts | `issue`: str = "", `pr`: str = "", `discussion`: str = "", `repo`: str = "" |

## Debug Tools (9)

Tools for system validation and debugging. Only available when `YU_DEBUG_MODE=1`.

| Tool | Description | Parameters |
|------|-------------|------------|
| `debug_health_check` | Check system health: Flask, DB tables, schema | -- |
| `debug_validate_counts` | Cross-validate API stats against DB counts | -- |
| `debug_validate_search` | Validate search API with test patterns | `patterns`: str = "all" |
| `debug_validate_collection` | Validate collection cached counts vs DB | -- |
| `debug_validate_annotations` | Validate annotation data integrity | -- |
| `debug_sample_files` | Sample random files and report field completeness | `n`: int = 50, `fields`: str = "meta_source,width,height" |
| `debug_roundtrip_test` | Write-read-upsert-delete roundtrip test | -- |
| `debug_readonly_query` | Execute readonly SQL query | `sql`: str, `limit`: int = 100 |
| `debug_full_report` | Run all debug validations combined | -- |

---

## LoRA Dataset Manager (15)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_lora_projects` | List all projects | -- |
| `get_lora_project` | Get project details | `project_id`: int |
| `create_lora_project` | Create a project | `name`: str, `concept`: str, `base_model`: str = 'sdxl', `repeat`: int = 10, `model_scope`: str = 'active' |
| `update_lora_project` | Update a project | `project_id`: int, `file_ids`: list = None, `tag_exclude`: list = None, `model_scope`: str = 'active' / 'all' / '<model_id>' |
| `delete_lora_project` | Delete a project | `project_id`: int |
| `get_lora_project_tags` | Get aggregated tag summary | `project_id`: int, `limit`: int = 200 |
| `preview_lora_caption` | Preview caption for a file | `project_id`: int, `file_id`: int = None |
| `export_lora_dataset` | Export dataset to kohya_ss folder | `project_id`: int, `output_dir`: str = '' |
| `get_lora_export_status` | Get export progress/result | `project_id`: int |
| `list_lora_checkpoints` | List available checkpoint files | -- |
| `preview_lora_train_command` | Preview training command (dry run) | `project_id`: int, `checkpoint`: str |
| `start_lora_training` | Start LoRA training | `project_id`: int, `checkpoint`: str |
| `get_lora_train_status` | Get training status and logs | `project_id`: int, `tail`: int = 50 |
| `list_lora_tag_presets` | List tag exclusion presets | -- |
| `create_lora_tag_preset` | Create a tag exclusion preset | `name`: str, `tags`: list |

## LLM Endpoints (5)

| Tool | Description | Parameters |
|------|-------------|------------|
| `llm-endpoints-list` | List configured LLM endpoints | — |
| `llm-endpoints-set` | Add or update an LLM endpoint | `category`: str, `base_url`: str, `model`: str, `api_key`: str = '', `timeout`: int = 60 |
| `llm-endpoints-remove` | Remove an LLM endpoint | `category`: str |
| `llm-endpoints-test` | Test connection to an LLM endpoint | `category`: str |
| `llm-chat` | Delegate chat to a configured LLM | `category`: str, `message`: str, `system_prompt`: str = '', `max_tokens`: int = 1024, `temperature`: float = 0.7 |

## Server Mode (2)

| Tool | Description | Parameters |
|------|-------------|------------|
| `server-mode-get` | Get current server mode | — |
| `server-subsystems-status` | List subsystem status | — |

## Features Not Available via MCP

The following features are not exposed as tools due to MCP limitations:

- **Binary responses**: Thumbnails (`/api/thumbnail/`), original images (`/api/original/`), ZIP downloads, video files
- **OS dialogs**: Folder selection dialog (`/api/tools/select-folder`), file manager launch (`/api/open-folder/`)
- **SSE streams**: Log streaming (`/api/logs/stream`)
- **Authentication pages**: PIN entry screen, LAN Share guest page
