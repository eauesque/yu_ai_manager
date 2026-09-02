# Riferimento degli strumenti MCP

Elenco completo degli strumenti forniti dal server MCP (Model Context Protocol) di YU AI Manager.
Da Claude Desktop o altri client MCP è possibile richiamare questi strumenti per automatizzare la gestione, l'analisi e la generazione della libreria.

**Numero totale di strumenti: 521**

## Indice

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

### Variabili d'ambiente

| Variabile | Descrizione | Default |
|------|------|-----------|
| `YU_BASE_URL` | URL del server YU AI Manager | `http://localhost:5000` |
| `YU_API_KEY` | API Key (autenticazione Bearer) | (nessuna) |
| `YU_DEBUG_MODE` | Con `1` abilita gli strumenti di debug | `0` |

### Esempio di configurazione di Claude Desktop (`claude_desktop_config.json`)

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

### Notifiche di progresso

Gli strumenti `wait_for_scan` / `wait_for_batch` supportano le MCP Notifications:
- **Client compatibili con progressToken**: ricevono il progresso in tempo reale tramite `notifications/progress`
- **Client non compatibili**: attesa bloccante, al completamento restituiscono il risultato finale

---

## Search & Browse (10)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `search_images` | Ricerca immagini con vari filtri | `query`: str = '', `sort`: str = 'date', `limit`: int = 20, `cursor`: str = '', `from_date`: str = '', `to_date`: str = '', `file_format`: str = 'all', `min_rating`: str = '', `max_rating`: str = '', `in_prompt`: str = '', `fav_only`: bool = False, `collection_id`: int = 0, `also_path`: bool = False |
| `search_images_grouped` | Ricerca immagini con raggruppamento per directory | `query`: str = '', `sort`: str = 'date', `limit`: int = 20, `from_date`: str = '', `to_date`: str = '' |
| `search_union` | Ricerca di unione di più query | `queries`: list |
| `get_image_detail` | Recupera tutti i metadati di un'immagine | `file_id`: int |
| `get_library_stats` | Statistiche della libreria | — |
| `get_file_info` | Informazioni su percorso file e metadati | `file_id`: int |
| `get_groups_index` | Indice dei gruppi di directory | — |
| `get_group_members` | Elenco membri di un gruppo | `group`: str |
| `get_container_members` | Elenco membri dentro un container ZIP/RAR | `file_id`: int |
| `file_search` | Ricerca file nel database per percorso/nome | `query`: str, `meta_filter`: str = "all", `limit`: int = 100 |

## Collections (7)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `list_collections` | Elenco di tutte le collezioni | — |
| `create_collection` | Crea una collezione | `name`: str |
| `rename_collection` | Rinomina una collezione | `collection_id`: int, `name`: str |
| `delete_collection` | Elimina una collezione | `collection_id`: int |
| `reorder_collections` | Cambia l'ordine delle collezioni | `order`: list |
| `add_to_collection` | Aggiunge immagini alla collezione | `collection_id`: int, `file_ids`: list, `expected_count`: int = 0 |
| `remove_from_collection` | Rimuove immagini dalla collezione | `collection_id`: int, `file_ids`: list, `expected_count`: int = 0 |

## Ratings & Tags (5)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `rate_images` | Imposta il rating di più immagini in blocco | `items`: list, `expected_count`: int = 0 |
| `get_ratings` | Recupera i rating dei file | `file_ids`: str |
| `get_ratings_stats` | Statistiche sui rating | — |
| `set_tags` | Aggiunge/rimuove user tag di più immagini | `items`: list, `expected_count`: int = 0 |
| `normalize_tags` | Normalizzazione dei tag nel DB | — |

## Favorites (8)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `toggle_favorite` | Attiva/disattiva preferito | `file_id`: int |
| `check_favorite` | Verifica lo stato di preferito | `file_id`: int |
| `check_favorite_collections` | Verifica l'appartenenza a collezioni per un file preferito | `file_id`: int |
| `list_favorites` | Elenco dei preferiti | `limit`: int = 50, `offset`: int = 0 |
| `fav_batch_add` | Aggiunge più file ai preferiti in blocco | `file_ids`: list, `collection_id`: int = 1 |
| `fav_batch_remove` | Rimuove più file dai preferiti in blocco | `file_ids`: list, `collection_id`: int = 0 |
| `fav_export_folder` | Esporta i preferiti in una cartella sul server | `dest_path`: str, `collection_id`: int = 0 |
| `fav_images` | Elenco delle immagini di una collezione di preferiti | `collection_id`: int = 0 |

## Annotations (4)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `set_annotations` | Salva annotazioni (upsert) | `items`: list, `expected_count`: int = 0 |
| `get_annotations` | Recupera annotazioni di un'immagine | `file_id`: int, `source`: str = '', `key`: str = '' |
| `search_annotations` | Ricerca trasversale delle annotazioni | `source`: str = '', `key`: str = '', `min_confidence`: str = '', `max_confidence`: str = '', `limit`: int = 100, `offset`: int = 0 |
| `delete_annotations` | Elimina annotazioni | `source`: str, `file_ids`: Optional = None, `key`: str = '' |

## Scanning (14)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `trigger_scan` | Avvia la scansione di tutte le scan root | — |
| `start_scan` | Avvia la scansione di un percorso o di tutte le root | `path`: str = '' |
| `get_scan_status` | Recupera il progresso della scansione | — |
| `cancel_scan` | Annulla la scansione | — |
| `resume_scan` | Riprende una scansione interrotta | — |
| `dismiss_interrupted_scan` | Scarta lo stato di interruzione | — |
| `get_scan_interrupted` | Informazioni sulla scansione interrotta | — |
| `get_scan_errors` | Elenco errori di scansione | `error_type`: str = '', `resolved`: str = 'false', `limit`: int = 50 |
| `resolve_scan_error` | Marca l'errore come risolto | `error_id`: int |
| `clear_scan_errors` | Pulisce gli errori risolti | — |
| `get_scanned_roots` | Elenco delle root scansionate | — |
| `scan_queue_list` | Elenco degli elementi in attesa nella coda di scansione | -- |
| `scan_queue_remove` | Rimuove un elemento dalla coda di scansione | `queue_id`: str |
| `scan_queue_clear` | Svuota completamente la coda di scansione | -- |

## Scan Roots (9)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `list_scan_roots` | Elenco delle scan root | — |
| `add_scan_root` | Aggiunge una scan root | `path`: str |
| `edit_scan_root` | Modifica il percorso di una scan root | `index`: int, `path`: str |
| `remove_scan_root` | Rimuove una scan root | `index`: int |
| `toggle_scan_root` | Abilita/disabilita una scan root | `index`: int |
| `reorder_scan_roots` | Cambia l'ordine delle scan root | `order`: list |
| `scan_directory` | Scansiona una directory specifica | `path`: str |
| `get_checkpoints` | Checkpoint di modelli disponibili | — |
| `purge_scanned_roots` | Purga i record delle root scansionate | — |

## Hash & Duplicates (7)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `find_duplicates` | Rileva file duplicati | `method`: str = 'hash' |
| `find_similar` | Ricerca immagini simili via perceptual hash | `file_id`: int, `threshold`: int = 5 |
| `compute_hashes` | Avvia il job di calcolo hash dei file | `hash_type`: str = 'both' |
| `delete_duplicates` | Elimina file duplicati | `groups`: list, `mode`: str = 'soft' |
| `start_hash_backfill` | Avvia il calcolo massivo degli hash non ancora calcolati | — |
| `cancel_hash_backfill` | Annulla il calcolo degli hash | — |
| `get_hash_backfill_status` | Progresso del calcolo hash | — |

## Wait / Progress (2)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `wait_for_scan` | Attende il completamento della scansione (con notifiche di progresso) | `timeout`: int = 600 |
| `wait_for_batch` | Attende il completamento di un job batch (con notifiche di progresso) | `job_id`: str = 'ai_analysis', `timeout`: int = 600 |

## AI Analysis (25)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `analyze_image` | Analisi AI di una singola immagine | `file_id`: int |
| `analyze_batch` | Analisi AI in blocco di più immagini | `file_ids`: list, `expected_count`: int = 0, `server_ids`: list = None |
| `analyze_batch_cancel` | Annulla il job batch di analisi AI in corso | -- |
| `get_analysis_result` | Recupera il risultato dell'analisi | `file_id`: int |
| `get_analysis_stats` | Statistiche dell'analisi | — |
| `get_analysis_config` | Recupera la configurazione dell'analisi | — |
| `save_analysis_config` | Salva la configurazione dell'analisi | `config`: dict |
| `get_available_engines` | Elenco degli engine disponibili | — |
| `get_ollama_models` | Elenco dei modelli Ollama | — |
| `test_ollama_connection` | Test di connessione Ollama | — |
| `get_openai_compat_models` | Elenco modelli API compatibili OpenAI | — |
| `test_openai_compat_connection` | Test di connessione API compatibile OpenAI | — |
| `list_ai_servers` | Elenco dei server AI registrati | — |
| `add_ai_server` | Registra un server AI | `name`: str, `type`: str, `config`: dict, `priority`: int = 50, `enabled`: bool = True |
| `update_ai_server` | Aggiorna la configurazione di un server AI | `server_id`: str, `name`: str = '', `config`: dict = None, `priority`: int = -1, `enabled`: bool = True |
| `remove_ai_server` | Elimina un server AI | `server_id`: str |
| `set_active_ai_server` | Cambia il server attivo | `server_id`: str |
| `test_ai_server` | Test di connessione al server AI | `server_id`: str |
| `reorder_ai_servers` | Cambia la priorità dei server | `order`: list |
| `migrate_ai_servers` | Migrazione da vecchia configurazione | — |
| `analyze_prompt_trends` | Analisi delle tendenze dei prompt | `limit`: int = 100 |
| `get_trend_history` | Cronologia delle analisi di tendenza | `limit`: int = 20 |
| `delete_trend_history` | Elimina cronologia delle tendenze | `history_id`: int |
| `analyze_video` | Analisi video multi-keyframe (Vision LLM) | `file_id`: int, `engine`: str = "", `model`: str = "", `keyframe_count`: int = 4 |
| `transcribe_audio` | Trascrizione file audio/video con Whisper | `file_id`: int, `engine`: str = "", `model`: str = "", `language`: str = "" |
| `get_audio_analysis_status` | Verifica lo stato di disponibilità dell'analisi audio (ffmpeg, whisper) | -- |

## WD-Tagger (15)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `wd_tagger_tag_file` | Inferenza tag su un singolo file | `file_id`: int |
| `wd_tagger_batch` | Inferenza tag in blocco su più file | `file_ids`: list, `expected_count`: int = 0 |
| `wd_tagger_batch_cancel` | Annulla il job batch WD-Tagger in corso | -- |
| `wd_tagger_get_tags` | Recupera i tag WD-Tagger di un file | `file_id`: int |
| `wd_tagger_delete_tags` | Elimina i tag WD-Tagger di un file | `file_id`: int |
| `wd_tagger_delete_tags_batch` | Elimina in blocco i tag WD-Tagger di più file | `file_ids`: list, `expected_count`: int = 0 |
| `wd_tagger_get_xmp` | Recupera i metadati XMP | `file_id`: int |
| `wd_tagger_stats` | Statistiche dei tag | — |
| `wd_tagger_untagged` | Elenco dei file non taggati | `limit`: int = 50, `offset`: int = 0 |
| `wd_tagger_get_config` | Recupera configurazione | — |
| `wd_tagger_save_config` | Salva configurazione | `config`: dict |
| `wd_tagger_model_status` | Stato del download del modello | — |
| `wd_tagger_download_model` | Download del modello | — |
| `wd_tagger_vlm_test` | Test di connessione al server VLM | `url`: str |
| `wd_tagger_vlm_models` | Elenco modelli del server VLM | `url`: str |

## Semantic Search / CLIP (12)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `semantic_search` | Ricerca immagini con testo in linguaggio naturale | `query`: str, `limit`: int = 50, `threshold`: float = 0.2 |
| `semantic_status` | Stato dell'Extension | — |
| `semantic_backend_info` | Informazioni sul backend CLIP | — |
| `semantic_model_status` | Stato del modello | — |
| `semantic_model_download` | Download del modello CLIP | — |
| `semantic_index_start` | Avvia costruzione indice | `batch_size`: int = 32, `backend`: str = 'auto' |
| `semantic_index_status` | Progresso dell'indice | — |
| `semantic_index_stop` | Ferma la costruzione dell'indice | — |
| `semantic_index_clear` | Svuota l'indice | — |
| `semantic_caption_start` | Avvia generazione caption in batch | `batch_size`: int = 50 |
| `semantic_caption_status` | Progresso caption | — |
| `semantic_caption_stop` | Ferma la generazione di caption | — |

## YOLO Object Detection (17)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `yolo_status` | Stato dell'Extension | — |
| `yolo_detect_start` | Avvia il rilevamento oggetti | `file_ids`: list = None, `undetected_only`: bool = True |
| `yolo_detect_status` | Progresso del job di rilevamento | — |
| `yolo_detect_stop` | Ferma il rilevamento | — |
| `yolo_get_results` | Recupera i risultati di rilevamento di un file | `file_id`: int |
| `yolo_search` | Ricerca immagini per label rilevate | `labels`: str = '', `min_confidence`: float = 0.0, `limit`: int = 50, `offset`: int = 0 |
| `yolo_clear_results` | Cancella i risultati di rilevamento | `file_ids`: list = None |
| `yolo_model_status` | Stato del modello | — |
| `yolo_model_download` | Download del modello HEF YOLO | — |
| `yolo_list_labels` | Elenco delle label rilevate | — |
| `yolo_stream_sources` | Elenco e stato delle sorgenti stream | — |
| `yolo_stream_start` | Avvia una sorgente stream | `source_id`: str |
| `yolo_stream_stop` | Ferma una sorgente stream | `source_id`: str |
| `yolo_stream_add_source` | Aggiunge una sorgente stream | `id`: str, `url`: str, `name`: str = "" |
| `yolo_stream_rules` | Elenco delle regole di rilevamento | — |
| `yolo_stream_add_rule` | Aggiunge una regola di rilevamento | `id`: str, `name`: str, `classes`: list, `min_confidence`: float = 0.7, `cooldown_sec`: int = 60, `actions`: list = [] |
| `yolo_stream_status` | Stato complessivo dello stream (pipeline, sorgenti, regole, registrazione) | — |

## OCR (19)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `ocr_extract` | Esegue estrazione testo OCR dall'immagine | `file_id`: int, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "" |
| `ocr_batch` | Esegue OCR su più file | `file_ids`: list, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "", `expected_count`: int = 0 |
| `ocr_get_result` | Recupera il risultato OCR di un file | `file_id`: int, `task`: str = "", `engine`: str = "", `all_results`: bool = False |
| `ocr_delete` | Elimina il risultato OCR di un file | `file_id`: int, `task`: str = "", `engine`: str = "" |
| `ocr_export` | Esporta il risultato OCR in formato specificato | `file_id`: int, `format`: str = "md", `task`: str = "" |
| `ocr_translate` | Traduce il risultato OCR | `file_id`: int, `target_lang`: str = "en", `server_id`: str = "", `task`: str = "" |
| `ocr_get_translations` | Recupera le traduzioni di un file | `file_id`: int, `target_lang`: str = "" |
| `ocr_video` | Esegue OCR sui keyframe di un video | `file_id`: int, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "", `keyframe_count`: int = 4 |
| `ocr_bbox` | Esegue il rilevamento dei bounding box dal risultato OCR | `file_id`: int, `task`: str = "", `server_id`: str = "" |
| `ocr_overlay` | Genera un'immagine overlay OCR | `file_id`: int, `mode`: str = "translated", `target_lang`: str = "", `format`: str = "png" |
| `ocr_export_batch` | Esporta in blocco i risultati OCR | `file_ids`: list, `format`: str = "", `output_dir`: str = "", `overlay_mode`: str = "translated", `target_lang`: str = "" |
| `ocr_pdf` | Esegue OCR su documenti PDF | `file_id`: int, `task`: str = "ocr_document", `language`: str = "auto", `server_id`: str = "", `page_range`: str = "" |
| `ocr_engines` | Elenco degli engine OCR disponibili e punteggi di capacità | -- |
| `ocr_profiles` | Elenco di tutti i profili di capacità dei modelli | -- |
| `ocr_profiles_fetch` | Scarica e unisce i profili di modelli della community da URL | `url`: str |
| `ocr_profile_update` | Aggiorna manualmente i punteggi di capacità di un modello | `model_prefix`: str, `scores`: dict |
| `ocr_benchmark` | Misura la precisione con benchmark OCR | `task`: str = "ocr", `server_id`: str = "", `benchmark_dir`: str = "" |
| `ocr_benchmark_cases` | Elenco dei casi di test benchmark disponibili | `benchmark_dir`: str = "" |
| `ocr_npu_status` | Verifica disponibilità NPU e suggerimenti di ottimizzazione | `task`: str = "ocr" |

## SD WebUI Bridge (14)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `sd_test_connection` | Test di connessione | — |
| `sd_generate` | Generazione immagine txt2img | `prompt`: str, `negative_prompt`: str = '', `steps`: int = 28, `sampler`: str = 'Euler a', `cfg_scale`: float = 7.0, `width`: int = 512, `height`: int = 768, `seed`: int = -1, `expand_wildcards`: bool = False |
| `sd_get_progress` | Progresso di generazione | — |
| `sd_cancel` | Annulla la generazione | — |
| `sd_list_models` | Elenco dei modelli checkpoint | — |
| `sd_list_samplers` | Elenco dei sampler | — |
| `sd_list_loras` | Elenco dei LoRA | `q`: str = '' |
| `sd_list_embeddings` | Elenco degli embedding | `q`: str = '' |
| `sd_list_scripts` | Elenco degli script | — |
| `sd_get_script_info` | Dettagli di uno script | — |
| `sd_list_extensions` | Elenco delle extension | — |
| `sd_list_upscalers` | Elenco degli upscaler | — |
| `sd_get_config` | Recupera configurazione | — |
| `sd_save_config` | Salva configurazione | `api_url`: str = '', `save_folder`: str = '', `auto_save`, `auto_import`, `default_sampler`: str = '' |

## ComfyUI Bridge (13)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `comfyui_test_connection` | Test di connessione | — |
| `comfyui_generate` | Generazione immagine txt2img | `prompt`: str, `negative_prompt`: str = '', `steps`: int = 20, `sampler_name`: str = 'euler', `scheduler`: str = 'normal', `cfg`: float = 7.0, `width`: int = 512, `height`: int = 768, `seed`: int = -1, `ckpt_name`: str = '', `expand_wildcards`: bool = False, `image_format`: str = 'png' |
| `comfyui_generate_json` | Generazione tramite workflow JSON | `workflow`: str |
| `comfyui_get_progress` | Progresso di generazione | — |
| `comfyui_cancel` | Annulla la generazione | — |
| `comfyui_list_models` | Elenco dei modelli checkpoint | — |
| `comfyui_list_samplers` | Elenco dei sampler | — |
| `comfyui_list_schedulers` | Elenco degli scheduler | — |
| `comfyui_list_loras` | Elenco dei LoRA | `q`: str = '' |
| `comfyui_list_embeddings` | Elenco degli embedding | `q`: str = '' |
| `comfyui_list_custom_nodes` | Elenco dei custom node | `q`: str = '' |
| `comfyui_get_config` | Recupera configurazione | — |
| `comfyui_save_config` | Salva configurazione | `api_url`: str = '', `save_folder`: str = '', `auto_save`, `auto_import`, `default_sampler`: str = '', `default_scheduler`: str = '' |

## NovelAI Bridge (8)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `nai_test_connection` | Test di connessione | — |
| `nai_get_anlas` | Recupera il saldo Anlas | — |
| `nai_generate` | Generazione immagine | `prompt`: str, `negative_prompt`: str = '', `width`: int = 832, `height`: int = 1216, `steps`: int = 28, `sampler`: str = '', `noise_schedule`: str = '', `seed`: int = -1, `model`: str = '', `cfg_scale`: float = 5.0 |
| `nai_list_models` | Elenco dei modelli | — |
| `nai_list_samplers` | Elenco dei sampler | — |
| `nai_list_noise_schedules` | Elenco degli schedule di rumore | — |
| `nai_get_config` | Recupera configurazione | — |
| `nai_save_config` | Salva configurazione | `api_key`: str = '', `save_folder`: str = '', `auto_save`: bool = True, `auto_import`: bool = True, `default_model`: str = '' |

## Hailo GenAI (10)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `hailo_genai_status` | Stato dell'Extension | — |
| `hailo_genai_model_status` | Stato di caricamento del modello | — |
| `hailo_genai_model_download` | Download del modello | `model_name`: str = '' |
| `hailo_genai_model_unload` | Scarica il modello dalla memoria | — |
| `hailo_llm_generate` | Generazione testo LLM | `prompt`: str, `max_tokens`: int = 256, `temperature`: float = 0.7, `system_prompt`: str = '' |
| `hailo_llm_clear_context` | Pulisce il contesto LLM | — |
| `hailo_vlm_generate` | Generazione testo da immagine (VLM) | `file_id`: int, `prompt`: str = 'Describe this image.', `max_tokens`: int = 256 |
| `hailo_benchmark` | Esegue benchmark di performance dell'LLM Hailo | `prompt`: str, `runs`: int = 3, `max_tokens`: int = 256, `temperature`: float = 0.7, `model`: str = "qwen2.5-1.5b-chat" |
| `hailo_benchmark_compare` | Confronto di performance Hailo vs Ollama LLM | `prompt`: str, `runs`: int = 3, `max_tokens`: int = 256, `hailo_model`: str, `ollama_model`: str |
| `hailo_genai_openai_info` | Informazioni sugli endpoint API compatibili OpenAI di Hailo GenAI | -- |

## Hailo Chat (7)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `hailo_chat_new` | Crea una nuova conversazione Hailo Chat | `model`: str = "qwen2.5-1.5b-chat" |
| `hailo_chat_list` | Elenco delle conversazioni Hailo Chat | `limit`: int = 50, `offset`: int = 0 |
| `hailo_chat_get` | Recupera una conversazione con tutti i messaggi | `conversation_id`: int |
| `hailo_chat_active` | Recupera l'ID della conversazione attualmente attiva | -- |
| `hailo_chat_search` | Ricerca web via DuckDuckGo (per iniezione nel contesto) | `query`: str, `max_results`: int = 5 |
| `hailo_chat_rename` | Rinomina una conversazione | `conversation_id`: int, `title`: str |
| `hailo_chat_delete` | Elimina una conversazione | `conversation_id`: int |

## Hailo Remote Tagger (7)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `hailo_tagger_tag_file` | Tagga un singolo file con il tagger remoto Hailo | `file_id`: int |
| `hailo_tagger_batch` | Tagga in blocco più file (max 500) | `file_ids`: list, `expected_count`: int = 0 |
| `hailo_tagger_status` | Verifica stato di connessione del tagger remoto Hailo | — |
| `hailo_tagger_get_config` | Recupera la configurazione del tagger remoto Hailo | — |
| `hailo_tagger_save_config` | Salva la configurazione del tagger remoto Hailo | `config`: dict |
| `hailo_tagger_get_tags` | Recupera i tag Hailo di un file | `file_id`: int |
| `hailo_tagger_delete_tags` | Elimina i tag Hailo di un file | `file_id`: int |

## Tagger Server Registry (13)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `tagger_servers_list` | Elenco dei tagger server registrati e modalità distribuita | -- |
| `tagger_servers_add` | Aggiunge un tagger server | `name`: str, `type`: str, `config`: dict, `priority`: int = 50, `enabled`: bool = True |
| `tagger_servers_update` | Aggiorna la configurazione di un tagger server | `server_id`: str, `updates`: dict |
| `tagger_servers_remove` | Elimina un tagger server | `server_id`: str |
| `tagger_servers_test` | Test di connessione al tagger server | `server_id`: str |
| `tagger_servers_health` | Health check di tutti i server abilitati | -- |
| `tagger_servers_set_mode` | Imposta la modalità distribuita (single/parallel/idle_first) | `mode`: str |
| `tagger_servers_batch` | Tagging batch distribuito (work stealing su coda condivisa) | `file_ids`: list = None, `limit`: int = 500, `force`: bool = False, `threshold`: float = None |
| `tagger_servers_batch_cancel` | Annulla il job batch del cluster di tagger in corso | -- |
| `tagger_servers_tags` | Recupera i tag del tagger per un file | `file_id`: int |
| `tagger_servers_delete_tags` | Elimina i tag del tagger per un file | `file_id`: int |
| `tagger_servers_stats` | Statistiche del tagger (numero file non taggati) | -- |
| `tagger_servers_migrate_legacy` | Migra le vecchie impostazioni hailo_tagger al formato registry | -- |

## Prompt Library (21)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `search_prompts` | Ricerca prompt | `query`: str = '', `folder_id`: int = 0, `tag_id`: int = 0, `sort`: str = 'updated_at', `order`: str = 'desc', `limit`: int = 50, `offset`: int = 0 |
| `get_prompt` | Dettagli di un prompt | `prompt_id`: int |
| `create_prompt` | Crea un prompt | `title`: str, `positive`: str = '', `negative`: str = '', `memo`: str = '', ... |
| `create_prompt_from_file` | Crea prompt dai metadati di un'immagine | `file_id`: int |
| `update_prompt` | Aggiornamento prompt (aggiornamento parziale) | `prompt_id`: int, ... |
| `delete_prompt` | Elimina un prompt | `prompt_id`: int |
| `list_prompt_folders` | Elenco delle cartelle | — |
| `create_prompt_folder` | Crea una cartella | `name`: str |
| `update_prompt_folder` | Rinomina una cartella | `folder_id`: int, `name`: str |
| `delete_prompt_folder` | Elimina una cartella | `folder_id`: int |
| `move_prompt_to_folder` | Sposta prompt in una cartella | `prompt_id`: int, `folder_id`: int |
| `remove_prompt_from_folder` | Rimuove il prompt dalla cartella (torna alla root) | `prompt_id`: int |
| `list_prompt_tags` | Elenco dei tag | — |
| `create_prompt_tag` | Crea un tag | `name`: str |
| `delete_prompt_tag` | Elimina un tag | `tag_id`: int |
| `set_prompt_tags` | Imposta i tag di un prompt | `prompt_id`: int, `tag_ids`: list |
| `bulk_delete_prompts` | Eliminazione in blocco | `prompt_ids`: list |
| `bulk_move_prompts` | Spostamento in blocco | `prompt_ids`: list, `folder_id`: int |
| `bulk_tag_prompts` | Tagging in blocco | `prompt_ids`: list, `tag_ids`: list |
| `export_prompts` | Esporta tutti i prompt in JSON | — |
| `import_prompts` | Importa prompt da JSON | `data`: dict |

## Prompt Simulator (6)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `prompt_dp_analyze` | Analisi sintattica Dynamic Prompts | `text`: str |
| `prompt_emphasis` | Conversione sintassi di enfasi | `text`: str, `format`: str = 'a1111' |
| `prompt_convert` | Conversione formato A1111 ↔ NAI | `text`: str, `from_format`: str = 'a1111', `to_format`: str = 'nai' |
| `prompt_list_wildcards` | Elenco dei wildcard | — |
| `prompt_set_wildcard_dirs` | Imposta directory dei wildcard | `dirs`: list |
| `prompt_danbooru_autocomplete` | Autocomplete tag Danbooru | `q`: str |

## Prompt Syntax (1)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `analyze_prompt_syntax` | Analisi sintattica del prompt (informazioni sui token) | `text`: str, `engine`: str = 'a1111' |

## SD/NAI Conversion (3)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `convert_sd_to_nai` | Conversione prompt SD → NAI | `text`: str |
| `convert_nai_to_sd` | Conversione prompt NAI → SD | `text`: str |
| `convert_prompt_batch` | Conversione prompt in batch | `items`: list, `direction`: str = 'sd-to-nai' |

## Chat Logs (16)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `search_chat_logs` | Ricerca full-text FTS5 | `query`: str = '', `source`: str = '', `model`: str = '', `limit`: int = 50, ... |
| `search_chat_logs_grouped` | Ricerca raggruppata per conversazione | `query`: str, `source`: str = '', `limit`: int = 20 |
| `get_conversation` | Dettagli di una conversazione (tutti i messaggi) | `conversation_id`: int |
| `get_chat_full` | Alias di get_conversation | `conversation_id`: int |
| `get_chat_summary` | Riassunto generato da AI | `conversation_id`: int |
| `get_chat_decisions` | Decisioni estratte da AI | `conversation_id`: int |
| `get_related_conversations` | Conversazioni correlate | `conversation_id`: int, `limit`: int = 10 |
| `find_chat_by_entity` | Ricerca conversazioni per entità | `entity_type`: str, `entity_value`: str, `limit`: int = 50 |
| `search_chat_by_topic` | Ricerca per argomento | `topic`: str, `limit`: int = 50 |
| `search_decisions` | Ricerca trasversale delle decisioni | `query`: str, `limit`: int = 50 |
| `import_chat_log` | Importa da file locale | `source`: str, `json_path`: str |
| `get_chatlog_import_status` | Progresso dell'import | — |
| `get_chatlog_stats` | Statistiche dei chat log | — |
| `delete_conversation` | Elimina una conversazione | `conversation_id`: int |
| `reprocess_chat_logs` | Rielaborazione AI | `target`: str = 'unprocessed' |
| `text_search` | Ricerca trasversale MD/chat/prompt | `query`: str, `target`: str = 'md,chat,prompt', `limit`: int = 20 |

## Markdown Viewer (8)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `search_md_files` | Ricerca file Markdown | `query`: str = '', `path_filter`: str = '', `limit`: int = 50, `offset`: int = 0 |
| `get_md_content` | Recupera il contenuto di un file | `file_id`: int |
| `get_md_scan_roots` | Elenco delle scan root | — |
| `set_md_scan_roots` | Imposta le scan root | `roots`: list |
| `remove_md_scan_root` | Rimuove una scan root | `index`: int |
| `trigger_md_scan` | Avvia la scansione | — |
| `get_md_scan_status` | Progresso della scansione | — |
| `get_md_stats` | Statistiche | — |

## Freeze & Pull-back (6)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `generate_freeze_pullback` | Generazione video Ken Burns | `file_id`: int, `hold_seconds`: float = 2.0, `pull_seconds`: float = 5.0, `fps`: int = 30, ... |
| `get_fpb_status` | Stato del job di render | — |
| `fpb_check` | Verifica prerequisiti (ffmpeg ecc.) | — |
| `fpb_cancel` | Annulla la generazione | — |
| `fpb_list_outputs` | Elenco dei file di output | — |
| `fpb_delete_output` | Elimina un file di output | `filename`: str |

## Speech-to-Text (8)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `s2t_status` | Stato del backend | — |
| `s2t_transcribe_video` | Trascrizione di video/audio | `file_id`: int, `language`: str = '' |
| `s2t_batch_transcribe` | Trascrizione batch | `file_ids`: list, `language`: str = '', `expected_count`: int = 0 |
| `s2t_get_transcript` | Recupera la trascrizione salvata | `file_id`: int |
| `s2t_stream_start` | Avvia trascrizione stream | `source_url`: str, `language`: str = 'ja', `mode`: str = 'chunk' |
| `s2t_stream_stop` | Ferma la trascrizione stream | — |
| `s2t_stream_status` | Stato dello stream | — |
| `s2t_stream_transcript` | Recupera il risultato della trascrizione stream | — |

## Statistics (6)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `get_stats_timeline` | Statistiche temporali | `period`: str = 'daily' |
| `get_stats_hourly` | Statistiche per fascia oraria | — |
| `get_stats_models` | Statistiche di utilizzo dei modelli | — |
| `get_stats_resolutions` | Statistiche di distribuzione delle risoluzioni | — |
| `get_stats_story` | Narrazione storica della libreria | — |
| `get_monthly_report` | Report mensile | `month`: str = '' |

## Profiles (11)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `list_profiles` | Elenco profili | — |
| `get_profile` | Recupera profilo | `name`: str |
| `create_profile` | Crea profilo | `name`: str, `description`: str = '' |
| `update_profile` | Aggiorna profilo | `name`: str, `settings`: dict |
| `delete_profile` | Elimina profilo | `name`: str |
| `duplicate_profile` | Duplica profilo | `name`: str, `new_name`: str |
| `rename_profile` | Rinomina profilo | `name`: str, `new_name`: str |
| `toggle_profile_favorite` | Alterna preferito | `name`: str |
| `export_profile` | Esporta profilo | `name`: str |
| `import_profile` | Importa profilo da dati esportati | `qr_data`: str, `mode`: str = "full" |
| `import_profile_preview` | Anteprima dell'import del profilo | `qr_data`: str |

## File Operations (4)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `convert_image` | Conversione formato immagine | `file_id`: int, `format`: str = 'webp' |
| `extract_from_zip` | Estrae file da ZIP | `file_id`: int, `members`: list |
| `inspect_metadata` | Ispezione dei metadati grezzi | `file_id`: int |
| `get_share_link` | Genera link di condivisione | `file_id`: int |

## SVG Rasterization (2)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `svg_info` | Recupera disponibilità e informazioni sul backend di rasterizzazione SVG | — |
| `svg_rasterize` | Rasterizza SVG in PNG/WebP. Il base64 restituito è utilizzabile direttamente come input di img2img | `file_id`: int = 0, `svg_path`: str = '', `svg_data`: str = '', `width`: int = 1024, `height`: int = 1024, `format`: str = 'png', `background`: str = '' |

## Download (1)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `batch_download_zip` | Scarica più immagini in ZIP | `file_ids`: list, `expected_count`: int = 0 |

## Video Analysis (3)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `get_video_analysis_config` | Recupera la configurazione dell'analisi video | — |
| `save_video_analysis_config` | Salva la configurazione dell'analisi video | `config`: dict |
| `get_video_analysis_status` | Stato dell'analisi video | — |

## Backup (5)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `list_backups` | Elenco dei backup | — |
| `create_backup` | Crea backup | — |
| `restore_backup` | Ripristina backup | `filename`: str |
| `delete_backup` | Elimina backup | `filename`: str |
| `get_backup_status` | Stato del backup | — |

## Archive Cleanup (7)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `archive_cleanup_scan` | Scansione coppie di archivio | `path`: str = '' |
| `archive_cleanup_execute` | Esegue la pulizia | `actions`: list, `expected_count`: int = 0 |
| `archive_cleanup_llm_verify` | Verifica azione con LLM (singola) | `file_path`: str, `action`: str |
| `archive_cleanup_llm_verify_batch` | Verifica azioni con LLM (batch) | `items`: list |
| `archive_cleanup_get_llm_config` | Recupera configurazione LLM | — |
| `archive_cleanup_save_llm_config` | Salva configurazione LLM | `config`: dict |
| `archive_cleanup_list_models` | Elenco dei modelli LLM disponibili | — |

## Auto Scan Watcher (3)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `auto_scan_info` | Stato del monitoraggio | — |
| `auto_scan_start` | Avvia monitoraggio file | — |
| `auto_scan_stop` | Ferma monitoraggio file | — |

## Scheduler (6)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `get_scheduler_status` | Recupera lo stato del task scheduler e i job registrati | -- |
| `list_scheduled_jobs` | Elenco di tutti i job schedulati con trigger e prossimo orario di esecuzione | -- |
| `trigger_scheduled_job` | Attiva l'esecuzione immediata di un job schedulato | `job_id`: str |
| `pause_scheduled_job` | Sospende un job schedulato | `job_id`: str |
| `resume_scheduled_job` | Riprende un job schedulato in pausa | `job_id`: str |
| `get_scheduler_history` | Recupera la cronologia recente di esecuzione dei job schedulati | -- |

## Webhooks (9)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `list_webhooks` | Elenco dei webhook | — |
| `create_webhook` | Crea webhook | `url`: str, `events`: list, `name`: str = '' |
| `update_webhook` | Aggiorna webhook | `webhook_id`: str, `url`: str = '', `events`: list = None, `name`: str = '', `enabled`: bool = True |
| `delete_webhook` | Elimina webhook | `webhook_id`: str |
| `test_webhook` | Invia evento di test | `webhook_id`: str |
| `get_webhook_deliveries` | Cronologia consegne | `webhook_id`: str = '', `limit`: int = 50 |
| `create_inbound_webhook` | Crea un inbound webhook per trigger esterni. Restituisce URL con token. | `label`: str, `allowed_events`: list |
| `list_inbound_webhooks` | Elenco degli inbound webhook registrati. | — |
| `delete_inbound_webhook` | Elimina un inbound webhook. | `webhook_id`: str |

## Extensions (25)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `list_extensions` | Elenco delle Extension | — |
| `get_extension_detail` | Dettagli di una Extension | `name`: str |
| `toggle_extension` | Abilita/disabilita | `name`: str, `enabled`: bool |
| `install_extension` | Installa da repository Git | `url`: str |
| `update_extension` | Aggiorna Extension | `name`: str |
| `update_all_extensions` | Aggiorna tutte le Extension in blocco | — |
| `uninstall_extension` | Disinstalla Extension | `name`: str |
| `search_marketplace` | Ricerca nel marketplace | `query`: str = '' |
| `refresh_marketplace` | Aggiorna catalogo marketplace | — |
| `get_extension_config` | Recupera configurazione | `name`: str |
| `set_extension_config` | Aggiorna configurazione | `name`: str, `values`: dict |
| `get_extension_permissions` | Recupera informazioni permessi | `name`: str |
| `approve_extension_permissions` | Approva/rifiuta permessi | `name`: str, `granted`: list = None, `denied`: list = None, `action`: str = 'approve' |
| `scan_extension_code` | Analisi statica del codice | `name`: str |
| `rescan_extension` | Rianalizza il codice | `name`: str |
| `get_extension_tokens` | Stato dei Capability Token | `name`: str |
| `get_extension_integrity` | Integrità file e stato di monitoraggio | `name`: str |
| `get_extension_hooks` | Elenco hook registrati | — |
| `get_extension_isolation_status` | Stato isolamento di processo | — |
| `get_extension_os_isolation_status` | Stato isolamento a livello OS | — |
| `create_extension` | Crea una nuova Extension personalizzata con scaffolding | `name`: str, `description`: str = "" |
| `validate_extension` | Valida manifest e codice di un'Extension | `extension_name`: str |
| `list_extension_files` | Elenco file di una Extension personalizzata | `extension_name`: str |
| `read_extension_file` | Legge un file di una Extension personalizzata | `extension_name`: str, `file_type`: str, `filename`: str |
| `write_extension_file` | Scrive un file in una Extension personalizzata | `extension_name`: str, `file_type`: str, `filename`: str, `content`: str |

## UI Management (4)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `list_uis` | Elenco UI | — |
| `switch_ui` | Cambia UI attiva | `name`: str |
| `install_ui` | Installa UI | `url`: str |
| `uninstall_ui` | Disinstalla UI | `name`: str |

## Settings (18)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `settings_get_schema` | Recupera schema impostazioni | — |
| `settings_get_all` | Recupera tutte le impostazioni | — |
| `settings_get` | Recupera singola impostazione | `key`: str |
| `settings_set` | Aggiorna impostazione | `key`: str, `value`: str, `op_uri`: str = '' |
| `get_legacy_config` | Recupera legacy config.json | — |
| `save_legacy_config` | Salva legacy config.json | `config`: dict |
| `secrets_status` | Stato della chiave di crittografia | — |
| `secrets_export` | Esporta chiave di crittografia | `password`: str |
| `secrets_import` | Importa chiave di crittografia | `export_json`: str, `password`: str |
| `get_op_status` | Stato di 1Password CLI | — |
| `delete_op_mapping` | Elimina mapping 1Password | `key`: str |
| `migrate_secrets_to_keychain` | Migra al keychain del sistema operativo | — |
| `get_bw_status` | Recupera stato dell'integrazione Bitwarden CLI | -- |
| `list_bw_folders` | Elenco cartelle Bitwarden | -- |
| `delete_bw_mapping` | Elimina mapping di campo Bitwarden | `key`: str |
| `list_op_vaults` | Elenco dei Vault 1Password | -- |
| `push_secrets_to_1password` | Push di tutti i secret su 1Password e collegamento automatico del mapping op_secrets | `vault`: str, `item_title`: str = "YU AI Manager" |
| `push_secrets_to_bitwarden` | Push di tutti i secret su Bitwarden e collegamento automatico del mapping | `item_name`: str = "YU AI Manager", `folder_id`: str = "" |

## SNS Sharing (15)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `share_to_bluesky` | Pubblica su Bluesky | `file_id`: int, `text`: str = '', `attach_image`: bool = True |
| `test_bluesky_connection` | Test di connessione Bluesky | — |
| `get_x_share_url` | Recupera URL di condivisione X (Twitter) | `file_id`: int |
| `get_sns_preview` | Anteprima di condivisione SNS | `file_id`: int |
| `get_sns_config` | Recupera configurazione SNS | — |
| `save_sns_config` | Salva configurazione SNS | `config`: dict |
| `bsky_get_pending_notifications` | Recupera dalla coda le notifiche Bluesky non lette | -- |
| `bsky_get_notification_queue` | Recupera elementi della coda notifiche con filtri | `status`: str = "", `notification_type`: str = "" |
| `bsky_poll_notifications` | Esegue un polling immediato delle notifiche Bluesky | -- |
| `bsky_triage_notification` | Imposta il risultato di triage per una notifica | `queue_id`: int, `result`: str |
| `bsky_send_auto_response` | Invia risposta automatica a menzioni/reply/quote | `queue_id`: int, `text`: str |
| `bsky_get_monitor_config` | Recupera la configurazione del monitor Bluesky | -- |
| `bsky_save_monitor_config` | Salva la configurazione del monitor Bluesky | `poll_interval_minutes`: int = 0, `auto_dismiss_follow`: bool = True, `auto_dismiss_like`: bool = True, `auto_dismiss_repost`: bool = True, `auto_respond_enabled`: bool = False |
| `bsky_get_triage_prompts` | Recupera i prompt e i template di triage Bluesky | -- |
| `bsky_save_triage_prompts` | Salva i prompt di triage Bluesky | `triage_mention`: str = "", `triage_reply`: str = "", `triage_quote`: str = "", `response_mention`: str = "", `response_reply`: str = "" |

## LAN Share (2)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `create_lan_share` | Crea token di condivisione LAN | `collection_id`: int, `expires_hours`: int = 24 |
| `revoke_lan_share` | Revoca token di condivisione | `token`: str |

## MCP Client (8)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `list_mcp_connections` | Elenco delle connessioni MCP | — |
| `create_mcp_connection` | Crea connessione MCP | `name`: str, `command`: str, `args`: list = None, `env`: dict = None |
| `update_mcp_connection` | Aggiorna connessione MCP | `connection_id`: str, `name`: str = '', `command`: str = '', `args`: list = None, `env`: dict = None |
| `delete_mcp_connection` | Elimina connessione MCP | `connection_id`: str |
| `connect_mcp_server` | Connetti al server MCP | `connection_id`: str |
| `disconnect_mcp_server` | Disconnetti dal server MCP | `connection_id`: str |
| `get_mcp_connection_tools` | Elenco strumenti della connessione | `connection_id`: str |
| `call_mcp_tool` | Invoca strumento della connessione | `connection_id`: str, `tool_name`: str, `arguments`: dict = None |

## Cross Search (9)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `cross_search_get_scan_roots` | Recupera le directory scan root di Cross Search | -- |
| `cross_search_set_scan_roots` | Imposta le directory scan root di Cross Search | `roots`: list |
| `cross_search_delete_scan_root` | Elimina scan root di Cross Search per indice | `index`: int |
| `cross_search_scan` | Avvia la scansione di file di testo di Cross Search | -- |
| `cross_search_scan_stop` | Ferma la scansione di Cross Search in corso | -- |
| `cross_search_scan_status` | Stato di progresso della scansione Cross Search | -- |
| `cross_search_get_txt` | Recupera il contenuto testuale di un file indicizzato in Cross Search | `file_id`: int |
| `cross_search_open_file` | Apre un file nel file manager di sistema | `path`: str |
| `cross_search_stats` | Recupera informazioni statistiche di Cross Search | -- |

## Tag Dictionary (6)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `search_tag_dictionary` | Ricerca nel dizionario dei tag | `query`: str, `limit`: int = 20, `fuzzy`: bool = False |
| `get_tag_dict_stats` | Statistiche del dizionario dei tag | — |
| `split_tags` | Separazione di tag concatenati | `text`: str |
| `import_tag_dictionary` | Import del dizionario dei tag | `data`: dict |
| `clear_tag_dictionary` | Svuota il dizionario dei tag | — |
| `get_tag_dict_info` | Informazioni dettagliate su un singolo tag | `tag`: str |

## Trophies (1)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `list_trophies` | Elenco dei trofei | — |

## Source Code Browsing (3)

Strumenti per consultare in modo sicuro e in sola lettura il codice sorgente del progetto.
Protetti da una sicurezza a 3 livelli (normalizzazione percorso + whitelist di estensioni + blocklist di file sensibili).
Dettagli: [`docs/api/source.md`](source.md)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `source_tree` | Visualizzazione albero directory | `path`: str = '', `depth`: int = 3 |
| `source_read` | Lettura del contenuto del file (con numeri di riga) | `path`: str, `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | Ricerca testuale nel codice sorgente | `query`: str, `glob`: str = '', `limit`: int = 30 |

## Help (3)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `help_toc` | Indice dell'help | — |
| `help_get_section` | Recupera il contenuto di una sezione | `section`: str |
| `help_search` | Ricerca nell'help | `query`: str, `limit`: int = 5 |

## System Info (3)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `get_server_info` | Informazioni sul server | — |
| `get_inference_info` | Informazioni sul motore di inferenza | — |
| `get_market_quotes` | Informazioni di mercato | — |

## System Update (5)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `check_for_update` | Verifica su GitHub la disponibilità di una nuova versione | — |
| `get_update_status` | Recupera metodo di installazione e versione attuali | — |
| `apply_system_update` | Applica gli aggiornamenti disponibili (solo git/portable) | `confirm`: str |
| `check_unified_updates` | Verifica in blocco lo stato di aggiornamento del sistema + tutte le Extension | `force`: bool (optional) |
| `apply_unified_updates` | Aggiorna in blocco sistema + Extension (con backup automatico della configurazione) | `update_system`: bool, `update_extensions`: bool, `extension_names`: list (optional) |

## Suggestions (4)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `get_suggestions` | Suggerimenti per tag/prompt | `q`: str, `limit`: int = 10 |
| `suggest_tags` | Suggerimenti per tag | `q`: str, `limit`: int = 10 |
| `suggest_lora` | Suggerimenti per nomi di LoRA | `q`: str = '' |
| `suggest_embedding` | Suggerimenti per nomi di Embedding | `q`: str = '' |

## Logs & Debug (9)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `get_recent_logs` | Recupera log recenti | `limit`: int = 100 |
| `get_debug_log` | Output del debug log | `lines`: int = 200 |
| `clear_debug_log` | Pulisce il debug log | — |
| `get_cache_info` | Statistiche della cache | — |
| `clear_cache` | Pulisce la cache | — |
| `rebuild_groups` | Ricostruisce i gruppi di directory | — |
| `list_dirs` | Elenco delle directory | `path`: str = '' |
| `debug_file_meta` | Metadati di debug di un file | `file_id`: int |
| `debug_model_check` | Verifica disponibilità del modello | — |

## Agent Safety Gateway (25)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `agent_status` | Stato complessivo delle funzionalità di sicurezza | — |
| `agent_kill` | Attiva il Kill Switch (blocco immediato di tutti gli strumenti) | `reason`: str = 'Manual kill via MCP' |
| `agent_resume` | Rimuove il Kill Switch | — |
| `agent_circuit_breaker_status` | Stato del Circuit Breaker | — |
| `agent_circuit_breaker_reset` | Reset del Circuit Breaker | — |
| `agent_budget_status` | Stato del Budget Tracker | — |
| `agent_budget_reset` | Reset del Budget Tracker | — |
| `agent_approval_status` | Elenco delle richieste in attesa di approvazione | — |
| `agent_approval_respond` | Risponde a una richiesta di approvazione | `request_id`: str, `action`: str |
| `agent_approval_history` | Cronologia delle approvazioni | `limit`: int = 50 |
| `agent_scope_status` | Stato dello Scope Fence | — |
| `agent_scope_get` | Recupera Scope della sessione | `session_id`: str |
| `agent_scope_set` | Imposta Scope della sessione | `preset`: str = 'organizer', `duration_hours`: float = 0 |
| `agent_scope_delete` | Elimina Scope della sessione | `session_id`: str |
| `agent_tool_level` | Verifica il livello di sicurezza di uno strumento | `tool_name`: str = '' |
| `agent_auto_approve_list` | Elenco delle regole di auto-approvazione | — |
| `agent_auto_approve_add` | Aggiunge regola di auto-approvazione | `tool_name`: str |
| `agent_auto_approve_remove` | Rimuove regola di auto-approvazione | `index`: int |
| `agent_undo` | Annulla un'azione | `journal_id`: int |
| `agent_undoable` | Elenco delle azioni annullabili | `session_id`: str = '', `limit`: int = 50 |
| `agent_journal` | Ricerca nell'action journal | `tool_name`: str = '', `status`: str = '', `session_id`: str = '', `limit`: int = 50, `offset`: int = 0 |
| `agent_journal_stats` | Statistiche del journal | — |
| `agent_anomaly_status` | Stato del rilevamento anomalie | — |
| `agent_anomaly_alerts` | Cronologia degli alert di anomalia | `limit`: int = 50 |
| `agent_anomaly_reset` | Reset del rilevamento anomalie | — |

---

## GitHub Integration (12)

Monitoraggio, triage e reportistica degli issue di account GitHub.

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `github_list_accounts` | Elenco account GitHub registrati (i token sono mascherati) | — |
| `github_fetch_issues` | Recupera gli issue dai repository dell'account | `account_label`: str, `state`: str = 'open', `since`: str = '' |
| `github_triage_issues` | Recupera e classifica gli issue (valid_bug / skip / needs_info). Restituisce un report prioritizzato | `account_label`: str, `state`: str = 'open', `since`: str = '' |
| `github_get_issue_detail` | Output strutturato dei dettagli dell'issue per Claude Code. Include commenti | `account_label`: str, `repo`: str, `issue_number`: int |
| `github_rate_limit` | Verifica il rate limit residuo dell'API GitHub | `account_label`: str |
| `github_get_pending_issues` | Recupera dalla coda locale gli Issue non ancora elaborati | -- |
| `github_get_issue_queue` | Recupera elementi della coda Issue con filtro di stato | `status`: str = "" |
| `github_poll_issues` | Esegue un polling immediato degli Issue GitHub | -- |
| `github_triage_queue_item` | Imposta il risultato di triage per un Issue in coda | `queue_id`: int, `result`: str |
| `github_dismiss_queue_item` | Scarta un Issue in coda (opzionalmente auto close) | `queue_id`: int, `auto_close`: bool = False, `account_label`: str = "" |
| `github_get_triage_prompts` | Recupera i prompt di triage Issue/PR/Discussion | `repo`: str = "" |
| `github_save_triage_prompts` | Salva i prompt di triage | `issue`: str = "", `pr`: str = "", `discussion`: str = "", `repo`: str = "" |

## Debug Tools (9)

Strumenti di verifica del sistema e debug. Abilitati con `YU_DEBUG_MODE=1`.

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `debug_health_check` | Health check del sistema: Flask, tabelle DB, versione dello schema | -- |
| `debug_validate_counts` | Verifica incrociata tra statistiche API e conteggi DB | -- |
| `debug_validate_search` | Verifica l'API di ricerca con pattern di test | `patterns`: str = "all" |
| `debug_validate_collection` | Verifica il conteggio in cache delle collezioni e DB | -- |
| `debug_validate_annotations` | Verifica la coerenza dei dati di annotation | -- |
| `debug_sample_files` | Campiona file in modo casuale e riporta la completezza dei campi | `n`: int = 50, `fields`: str = "meta_source,width,height" |
| `debug_roundtrip_test` | Test di roundtrip write-read-update-delete | -- |
| `debug_readonly_query` | Esegue query SQL in sola lettura | `sql`: str, `limit`: int = 100 |
| `debug_full_report` | Esegue in blocco tutte le verifiche di debug | -- |

---

## LoRA Dataset Manager (15)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `list_lora_projects` | Elenco dei progetti | — |
| `get_lora_project` | Dettagli del progetto | `project_id`: int |
| `create_lora_project` | Crea un progetto | `name`: str, `concept`: str, `base_model`: str = 'sdxl', `repeat`: int = 10, `model_scope`: str = 'active' |
| `update_lora_project` | Aggiorna un progetto | `project_id`: int, `file_ids`: list = None, `tag_exclude`: list = None, `model_scope`: str = 'active' / 'all' / '<model_id>' |
| `delete_lora_project` | Elimina un progetto | `project_id`: int |
| `get_lora_project_tags` | Recupera aggregazione tag | `project_id`: int, `limit`: int = 200 |
| `preview_lora_caption` | Anteprima della caption | `project_id`: int, `file_id`: int = None |
| `export_lora_dataset` | Esporta il dataset | `project_id`: int, `output_dir`: str = '' |
| `get_lora_export_status` | Verifica del progresso di esportazione | `project_id`: int |
| `list_lora_checkpoints` | Elenco dei checkpoint | — |
| `preview_lora_train_command` | Anteprima del comando di training (dry run) | `project_id`: int, `checkpoint`: str |
| `start_lora_training` | Avvio del training LoRA | `project_id`: int, `checkpoint`: str |
| `get_lora_train_status` | Recupera stato e log del training | `project_id`: int, `tail`: int = 50 |
| `list_lora_tag_presets` | Elenco dei preset di esclusione tag | — |
| `create_lora_tag_preset` | Crea preset di esclusione tag | `name`: str, `tags`: list |

## LLM Endpoints (5)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `llm-endpoints-list` | Elenco degli endpoint LLM configurati | — |
| `llm-endpoints-set` | Aggiunta/aggiornamento di endpoint LLM | `category`: str, `base_url`: str, `model`: str, `api_key`: str = '', `timeout`: int = 60 |
| `llm-endpoints-remove` | Rimozione di endpoint LLM | `category`: str |
| `llm-endpoints-test` | Test di connessione dell'endpoint LLM | `category`: str |
| `llm-chat` | Delega una chat all'LLM configurato | `category`: str, `message`: str, `system_prompt`: str = '', `max_tokens`: int = 1024, `temperature`: float = 0.7 |

## Server Mode (2)

| Tool | Descrizione | Parametri |
|------|-------------|------------|
| `server-mode-get` | Recupera la modalità server attuale | — |
| `server-subsystems-status` | Elenco dello stato dei sottosistemi | — |

## Funzionalità non supportate da MCP

Per vincoli di MCP, le seguenti funzionalità non sono fornite come strumenti:

- **Restituzione di binari**: miniature (`/api/thumbnail/`), immagini originali (`/api/original/`), download ZIP, file video
- **Finestre di dialogo OS**: dialog di selezione cartelle (`/api/tools/select-folder`), avvio del file manager (`/api/open-folder/`)
- **Stream SSE**: streaming dei log (`/api/logs/stream`)
- **Pagine di autenticazione**: schermata di inserimento PIN, pagina guest di LAN Share
