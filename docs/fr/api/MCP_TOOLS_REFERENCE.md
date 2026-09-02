# Référence des Outils MCP

Liste de tous les outils fournis par le serveur MCP (Model Context Protocol) de YU AI Manager.
Depuis Claude Desktop ou d'autres clients MCP, vous pouvez appeler ces outils pour automatiser la gestion, l'analyse et la génération de votre bibliothèque.

**Nombre total d'outils : 521**

## Table des Matières

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

## Configuration

### Variables d'Environnement

| Variable | Description | Défaut |
|------|------|-----------|
| `YU_BASE_URL` | URL du serveur YU AI Manager | `http://localhost:5000` |
| `YU_API_KEY` | Clé API (authentification Bearer) | (aucune) |
| `YU_DEBUG_MODE` | `1` pour activer les outils de debug | `0` |

### Exemple de Configuration Claude Desktop (`claude_desktop_config.json`)

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

### Notifications de Progression

Les outils `wait_for_scan` / `wait_for_batch` supportent les MCP Notifications :
- **Clients supportant progressToken** : réception de la progression en temps réel via `notifications/progress`
- **Clients non supportés** : attente bloquante, retour du résultat final à la fin

---

## Search & Browse (10)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `search_images` | Rechercher des images avec divers filtres | `query`: str = '', `sort`: str = 'date', `limit`: int = 20, `cursor`: str = '', `from_date`: str = '', `to_date`: str = '', `file_format`: str = 'all', `min_rating`: str = '', `max_rating`: str = '', `in_prompt`: str = '', `fav_only`: bool = False, `collection_id`: int = 0, `also_path`: bool = False |
| `search_images_grouped` | Rechercher avec groupes de répertoires | `query`: str = '', `sort`: str = 'date', `limit`: int = 20, `from_date`: str = '', `to_date`: str = '' |
| `search_union` | Recherche union de plusieurs requêtes | `queries`: list |
| `get_image_detail` | Obtenir toutes les métadonnées d'image | `file_id`: int |
| `get_library_stats` | Statistiques de la bibliothèque | — |
| `get_file_info` | Chemin et métadonnées de fichier | `file_id`: int |
| `get_groups_index` | Index des groupes de répertoires | — |
| `get_group_members` | Liste des membres d'un groupe | `group`: str |
| `get_container_members` | Liste des membres d'un conteneur ZIP/RAR | `file_id`: int |
| `file_search` | Rechercher des fichiers par chemin/nom dans la DB | `query`: str, `meta_filter`: str = "all", `limit`: int = 100 |

## Collections (7)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `list_collections` | Liste de toutes les collections | — |
| `create_collection` | Créer une collection | `name`: str |
| `rename_collection` | Renommer une collection | `collection_id`: int, `name`: str |
| `delete_collection` | Supprimer une collection | `collection_id`: int |
| `reorder_collections` | Réordonner les collections | `order`: list |
| `add_to_collection` | Ajouter des images à une collection | `collection_id`: int, `file_ids`: list, `expected_count`: int = 0 |
| `remove_from_collection` | Retirer des images d'une collection | `collection_id`: int, `file_ids`: list, `expected_count`: int = 0 |

## Ratings & Tags (5)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `rate_images` | Définir les notes de plusieurs images en lot | `items`: list, `expected_count`: int = 0 |
| `get_ratings` | Obtenir les notes de fichiers | `file_ids`: str |
| `get_ratings_stats` | Statistiques des notes | — |
| `set_tags` | Ajouter/supprimer les tags utilisateur de plusieurs images | `items`: list, `expected_count`: int = 0 |
| `normalize_tags` | Normaliser les tags en DB | — |

## Favorites (8)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `toggle_favorite` | Basculer favori | `file_id`: int |
| `check_favorite` | Vérifier l'état favori | `file_id`: int |
| `check_favorite_collections` | Vérifier l'appartenance de favoris aux collections | `file_id`: int |
| `list_favorites` | Liste des favoris | `limit`: int = 50, `offset`: int = 0 |
| `fav_batch_add` | Ajouter plusieurs fichiers aux favoris en lot | `file_ids`: list, `collection_id`: int = 1 |
| `fav_batch_remove` | Retirer plusieurs fichiers des favoris en lot | `file_ids`: list, `collection_id`: int = 0 |
| `fav_export_folder` | Exporter les favoris vers un dossier sur le serveur | `dest_path`: str, `collection_id`: int = 0 |
| `fav_images` | Liste d'images dans la collection favoris | `collection_id`: int = 0 |

## Annotations (4)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `set_annotations` | Enregistrer des annotations (upsert) | `items`: list, `expected_count`: int = 0 |
| `get_annotations` | Obtenir les annotations d'une image | `file_id`: int, `source`: str = '', `key`: str = '' |
| `search_annotations` | Recherche transversale d'annotations | `source`: str = '', `key`: str = '', `min_confidence`: str = '', `max_confidence`: str = '', `limit`: int = 100, `offset`: int = 0 |
| `delete_annotations` | Supprimer des annotations | `source`: str, `file_ids`: Optional = None, `key`: str = '' |

## Scanning (14)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `trigger_scan` | Démarrer le scan de toutes les racines | — |
| `start_scan` | Démarrer le scan d'un chemin ou toutes les racines | `path`: str = '' |
| `get_scan_status` | Obtenir la progression du scan | — |
| `cancel_scan` | Annuler le scan | — |
| `resume_scan` | Reprendre un scan interrompu | — |
| `dismiss_interrupted_scan` | Ignorer l'état interrompu | — |
| `get_scan_interrupted` | Obtenir les infos de scan interrompu | — |
| `get_scan_errors` | Liste des erreurs de scan | `error_type`: str = '', `resolved`: str = 'false', `limit`: int = 50 |
| `resolve_scan_error` | Marquer une erreur comme résolue | `error_id`: int |
| `clear_scan_errors` | Effacer les erreurs résolues | — |
| `get_scanned_roots` | Liste des racines scannées | — |
| `scan_queue_list` | Liste des items en file d'attente de scan | -- |
| `scan_queue_remove` | Retirer un item de la file d'attente | `queue_id`: str |
| `scan_queue_clear` | Vider la file d'attente de scan | -- |

## Scan Roots (9)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `list_scan_roots` | Liste des racines de scan | — |
| `add_scan_root` | Ajouter une racine de scan | `path`: str |
| `edit_scan_root` | Éditer le chemin d'une racine | `index`: int, `path`: str |
| `remove_scan_root` | Supprimer une racine de scan | `index`: int |
| `toggle_scan_root` | Activer/désactiver une racine | `index`: int |
| `reorder_scan_roots` | Réordonner les racines | `order`: list |
| `scan_directory` | Scanner un répertoire spécifique | `path`: str |
| `get_checkpoints` | Checkpoints de modèle disponibles | — |
| `purge_scanned_roots` | Purger les enregistrements de racines scannées | — |

## Hash & Duplicates (7)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `find_duplicates` | Détecter les fichiers dupliqués | `method`: str = 'hash' |
| `find_similar` | Rechercher images similaires via hash perceptuel | `file_id`: int, `threshold`: int = 5 |
| `compute_hashes` | Démarrer un job de calcul de hash | `hash_type`: str = 'both' |
| `delete_duplicates` | Supprimer les fichiers dupliqués | `groups`: list, `mode`: str = 'soft' |
| `start_hash_backfill` | Démarrer le calcul en masse des hashs manquants | — |
| `cancel_hash_backfill` | Annuler le calcul de hash | — |
| `get_hash_backfill_status` | Progression du calcul de hash | — |

## Wait / Progress (2)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `wait_for_scan` | Attendre la fin du scan (notifications supportées) | `timeout`: int = 600 |
| `wait_for_batch` | Attendre la fin d'un job batch (notifications supportées) | `job_id`: str = 'ai_analysis', `timeout`: int = 600 |

## AI Analysis (25)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `analyze_image` | Analyse IA d'une image unique | `file_id`: int |
| `analyze_batch` | Analyse IA en lot de plusieurs images | `file_ids`: list, `expected_count`: int = 0, `server_ids`: list = None |
| `analyze_batch_cancel` | Annuler un job d'analyse IA en cours | -- |
| `get_analysis_result` | Obtenir les résultats d'analyse | `file_id`: int |
| `get_analysis_stats` | Statistiques d'analyse | — |
| `get_analysis_config` | Obtenir la configuration d'analyse | — |
| `save_analysis_config` | Enregistrer la configuration d'analyse | `config`: dict |
| `get_available_engines` | Liste des moteurs disponibles | — |
| `get_ollama_models` | Liste des modèles Ollama | — |
| `test_ollama_connection` | Tester la connexion Ollama | — |
| `get_openai_compat_models` | Liste des modèles API compatibles OpenAI | — |
| `test_openai_compat_connection` | Tester la connexion API compatible OpenAI | — |
| `list_ai_servers` | Liste des serveurs IA enregistrés | — |
| `add_ai_server` | Enregistrer un serveur IA | `name`: str, `type`: str, `config`: dict, `priority`: int = 50, `enabled`: bool = True |
| `update_ai_server` | Mettre à jour un serveur IA | `server_id`: str, `name`: str = '', `config`: dict = None, `priority`: int = -1, `enabled`: bool = True |
| `remove_ai_server` | Supprimer un serveur IA | `server_id`: str |
| `set_active_ai_server` | Changer le serveur actif | `server_id`: str |
| `test_ai_server` | Tester la connexion d'un serveur IA | `server_id`: str |
| `reorder_ai_servers` | Réordonner la priorité des serveurs | `order`: list |
| `migrate_ai_servers` | Migration depuis l'ancienne config | — |
| `analyze_prompt_trends` | Analyse des tendances de prompts | `limit`: int = 100 |
| `get_trend_history` | Historique d'analyse de tendances | `limit`: int = 20 |
| `delete_trend_history` | Supprimer un historique de tendances | `history_id`: int |
| `analyze_video` | Analyse vidéo multi-keyframe (Vision LLM) | `file_id`: int, `engine`: str = "", `model`: str = "", `keyframe_count`: int = 4 |
| `transcribe_audio` | Transcription de fichier audio/vidéo avec Whisper | `file_id`: int, `engine`: str = "", `model`: str = "", `language`: str = "" |
| `get_audio_analysis_status` | Vérifier la disponibilité de l'analyse audio (ffmpeg, whisper) | -- |

## WD-Tagger (15)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `wd_tagger_tag_file` | Inférence de tags sur un fichier unique | `file_id`: int |
| `wd_tagger_batch` | Inférence de tags en lot sur plusieurs fichiers | `file_ids`: list, `expected_count`: int = 0 |
| `wd_tagger_batch_cancel` | Annuler un job batch WD-Tagger en cours | -- |
| `wd_tagger_get_tags` | Obtenir les tags WD-Tagger d'un fichier | `file_id`: int |
| `wd_tagger_delete_tags` | Supprimer les tags WD-Tagger d'un fichier | `file_id`: int |
| `wd_tagger_delete_tags_batch` | Supprimer en lot les tags WD-Tagger de plusieurs fichiers | `file_ids`: list, `expected_count`: int = 0 |
| `wd_tagger_get_xmp` | Obtenir les métadonnées XMP | `file_id`: int |
| `wd_tagger_stats` | Statistiques de tags | — |
| `wd_tagger_untagged` | Liste des fichiers non étiquetés | `limit`: int = 50, `offset`: int = 0 |
| `wd_tagger_get_config` | Obtenir la configuration | — |
| `wd_tagger_save_config` | Enregistrer la configuration | `config`: dict |
| `wd_tagger_model_status` | État de téléchargement du modèle | — |
| `wd_tagger_download_model` | Télécharger le modèle | — |
| `wd_tagger_vlm_test` | Tester la connexion au serveur VLM | `url`: str |
| `wd_tagger_vlm_models` | Liste des modèles du serveur VLM | `url`: str |

## Semantic Search / CLIP (12)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `semantic_search` | Rechercher des images en langage naturel | `query`: str, `limit`: int = 50, `threshold`: float = 0.2 |
| `semantic_status` | État de l'Extension | — |
| `semantic_backend_info` | Informations du backend CLIP | — |
| `semantic_model_status` | État du modèle | — |
| `semantic_model_download` | Télécharger le modèle CLIP | — |
| `semantic_index_start` | Démarrer la construction d'index | `batch_size`: int = 32, `backend`: str = 'auto' |
| `semantic_index_status` | Progression de l'index | — |
| `semantic_index_stop` | Arrêter la construction d'index | — |
| `semantic_index_clear` | Effacer l'index | — |
| `semantic_caption_start` | Démarrer la génération batch de captions | `batch_size`: int = 50 |
| `semantic_caption_status` | Progression des captions | — |
| `semantic_caption_stop` | Arrêter les captions | — |

## YOLO Object Detection (17)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `yolo_status` | État de l'Extension | — |
| `yolo_detect_start` | Démarrer la détection d'objets | `file_ids`: list = None, `undetected_only`: bool = True |
| `yolo_detect_status` | Progression du job de détection | — |
| `yolo_detect_stop` | Arrêter la détection | — |
| `yolo_get_results` | Obtenir les résultats de détection d'un fichier | `file_id`: int |
| `yolo_search` | Rechercher des images par label détecté | `labels`: str = '', `min_confidence`: float = 0.0, `limit`: int = 50, `offset`: int = 0 |
| `yolo_clear_results` | Effacer les résultats de détection | `file_ids`: list = None |
| `yolo_model_status` | État du modèle | — |
| `yolo_model_download` | Télécharger le modèle HEF YOLO | — |
| `yolo_list_labels` | Liste des labels détectés | — |
| `yolo_stream_sources` | Obtenir la liste/état des sources de stream | — |
| `yolo_stream_start` | Démarrer une source de stream | `source_id`: str |
| `yolo_stream_stop` | Arrêter une source de stream | `source_id`: str |
| `yolo_stream_add_source` | Ajouter une source de stream | `id`: str, `url`: str, `name`: str = "" |
| `yolo_stream_rules` | Obtenir la liste des règles de détection | — |
| `yolo_stream_add_rule` | Ajouter une règle de détection | `id`: str, `name`: str, `classes`: list, `min_confidence`: float = 0.7, `cooldown_sec`: int = 60, `actions`: list = [] |
| `yolo_stream_status` | État global du stream (pipeline, sources, règles, enregistrement) | — |

## OCR (19)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `ocr_extract` | Exécuter l'extraction OCR sur une image | `file_id`: int, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "" |
| `ocr_batch` | Exécuter l'OCR sur plusieurs fichiers | `file_ids`: list, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "", `expected_count`: int = 0 |
| `ocr_get_result` | Obtenir le résultat OCR d'un fichier | `file_id`: int, `task`: str = "", `engine`: str = "", `all_results`: bool = False |
| `ocr_delete` | Supprimer le résultat OCR d'un fichier | `file_id`: int, `task`: str = "", `engine`: str = "" |
| `ocr_export` | Exporter le résultat OCR dans un format spécifié | `file_id`: int, `format`: str = "md", `task`: str = "" |
| `ocr_translate` | Traduire le résultat OCR | `file_id`: int, `target_lang`: str = "en", `server_id`: str = "", `task`: str = "" |
| `ocr_get_translations` | Obtenir les traductions d'un fichier | `file_id`: int, `target_lang`: str = "" |
| `ocr_video` | Exécuter l'OCR sur les keyframes d'une vidéo | `file_id`: int, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "", `keyframe_count`: int = 4 |
| `ocr_bbox` | Détection des bounding boxes du résultat OCR | `file_id`: int, `task`: str = "", `server_id`: str = "" |
| `ocr_overlay` | Générer l'image d'overlay OCR | `file_id`: int, `mode`: str = "translated", `target_lang`: str = "", `format`: str = "png" |
| `ocr_export_batch` | Exporter en lot les résultats OCR | `file_ids`: list, `format`: str = "", `output_dir`: str = "", `overlay_mode`: str = "translated", `target_lang`: str = "" |
| `ocr_pdf` | Exécuter l'OCR sur un document PDF | `file_id`: int, `task`: str = "ocr_document", `language`: str = "auto", `server_id`: str = "", `page_range`: str = "" |
| `ocr_engines` | Liste des moteurs OCR disponibles et scores de capacité | -- |
| `ocr_profiles` | Liste de tous les profils de capacité de modèles | -- |
| `ocr_profiles_fetch` | Récupérer et fusionner les profils communautaires depuis une URL | `url`: str |
| `ocr_profile_update` | Mise à jour manuelle des scores de capacité d'un modèle | `model_prefix`: str, `scores`: dict |
| `ocr_benchmark` | Mesurer la précision via benchmark OCR | `task`: str = "ocr", `server_id`: str = "", `benchmark_dir`: str = "" |
| `ocr_benchmark_cases` | Liste des cas de test de benchmark disponibles | `benchmark_dir`: str = "" |
| `ocr_npu_status` | Vérifier la disponibilité du NPU et les suggestions d'optimisation | `task`: str = "ocr" |

## SD WebUI Bridge (14)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `sd_test_connection` | Tester la connexion | — |
| `sd_generate` | Génération d'image txt2img | `prompt`: str, `negative_prompt`: str = '', `steps`: int = 28, `sampler`: str = 'Euler a', `cfg_scale`: float = 7.0, `width`: int = 512, `height`: int = 768, `seed`: int = -1, `expand_wildcards`: bool = False |
| `sd_get_progress` | Progression de la génération | — |
| `sd_cancel` | Annuler la génération | — |
| `sd_list_models` | Liste des modèles checkpoint | — |
| `sd_list_samplers` | Liste des samplers | — |
| `sd_list_loras` | Liste des LoRA | `q`: str = '' |
| `sd_list_embeddings` | Liste des Embeddings | `q`: str = '' |
| `sd_list_scripts` | Liste des scripts | — |
| `sd_get_script_info` | Détails des scripts | — |
| `sd_list_extensions` | Liste des Extensions | — |
| `sd_list_upscalers` | Liste des upscalers | — |
| `sd_get_config` | Obtenir la configuration | — |
| `sd_save_config` | Enregistrer la configuration | `api_url`: str = '', `save_folder`: str = '', `auto_save`, `auto_import`, `default_sampler`: str = '' |

## ComfyUI Bridge (13)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `comfyui_test_connection` | Tester la connexion | — |
| `comfyui_generate` | Génération d'image txt2img | `prompt`: str, `negative_prompt`: str = '', `steps`: int = 20, `sampler_name`: str = 'euler', `scheduler`: str = 'normal', `cfg`: float = 7.0, `width`: int = 512, `height`: int = 768, `seed`: int = -1, `ckpt_name`: str = '', `expand_wildcards`: bool = False, `image_format`: str = 'png' |
| `comfyui_generate_json` | Générer avec un workflow JSON | `workflow`: str |
| `comfyui_get_progress` | Progression de la génération | — |
| `comfyui_cancel` | Annuler la génération | — |
| `comfyui_list_models` | Liste des modèles checkpoint | — |
| `comfyui_list_samplers` | Liste des samplers | — |
| `comfyui_list_schedulers` | Liste des schedulers | — |
| `comfyui_list_loras` | Liste des LoRA | `q`: str = '' |
| `comfyui_list_embeddings` | Liste des Embeddings | `q`: str = '' |
| `comfyui_list_custom_nodes` | Liste des nodes personnalisés | `q`: str = '' |
| `comfyui_get_config` | Obtenir la configuration | — |
| `comfyui_save_config` | Enregistrer la configuration | `api_url`: str = '', `save_folder`: str = '', `auto_save`, `auto_import`, `default_sampler`: str = '', `default_scheduler`: str = '' |

## NovelAI Bridge (8)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `nai_test_connection` | Tester la connexion | — |
| `nai_get_anlas` | Obtenir le solde Anlas | — |
| `nai_generate` | Génération d'image | `prompt`: str, `negative_prompt`: str = '', `width`: int = 832, `height`: int = 1216, `steps`: int = 28, `sampler`: str = '', `noise_schedule`: str = '', `seed`: int = -1, `model`: str = '', `cfg_scale`: float = 5.0 |
| `nai_list_models` | Liste des modèles | — |
| `nai_list_samplers` | Liste des samplers | — |
| `nai_list_noise_schedules` | Liste des noise schedules | — |
| `nai_get_config` | Obtenir la configuration | — |
| `nai_save_config` | Enregistrer la configuration | `api_key`: str = '', `save_folder`: str = '', `auto_save`: bool = True, `auto_import`: bool = True, `default_model`: str = '' |

## Hailo GenAI (10)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `hailo_genai_status` | État de l'Extension | — |
| `hailo_genai_model_status` | État de chargement des modèles | — |
| `hailo_genai_model_download` | Télécharger un modèle | `model_name`: str = '' |
| `hailo_genai_model_unload` | Décharger un modèle | — |
| `hailo_llm_generate` | Génération de texte LLM | `prompt`: str, `max_tokens`: int = 256, `temperature`: float = 0.7, `system_prompt`: str = '' |
| `hailo_llm_clear_context` | Effacer le contexte LLM | — |
| `hailo_vlm_generate` | Génération VLM image → texte | `file_id`: int, `prompt`: str = 'Describe this image.', `max_tokens`: int = 256 |
| `hailo_benchmark` | Exécuter un benchmark de performance LLM Hailo | `prompt`: str, `runs`: int = 3, `max_tokens`: int = 256, `temperature`: float = 0.7, `model`: str = "qwen2.5-1.5b-chat" |
| `hailo_benchmark_compare` | Comparer les performances LLM Hailo vs Ollama | `prompt`: str, `runs`: int = 3, `max_tokens`: int = 256, `hailo_model`: str, `ollama_model`: str |
| `hailo_genai_openai_info` | Obtenir les informations d'endpoint API compatible OpenAI de Hailo GenAI | -- |

## Hailo Chat (7)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `hailo_chat_new` | Créer une nouvelle conversation Hailo Chat | `model`: str = "qwen2.5-1.5b-chat" |
| `hailo_chat_list` | Liste des conversations Hailo Chat | `limit`: int = 50, `offset`: int = 0 |
| `hailo_chat_get` | Obtenir une conversation avec tous les messages | `conversation_id`: int |
| `hailo_chat_active` | Obtenir l'ID de la conversation active | -- |
| `hailo_chat_search` | Recherche Web via DuckDuckGo (injection de contexte) | `query`: str, `max_results`: int = 5 |
| `hailo_chat_rename` | Renommer une conversation | `conversation_id`: int, `title`: str |
| `hailo_chat_delete` | Supprimer une conversation | `conversation_id`: int |

## Hailo Remote Tagger (7)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `hailo_tagger_tag_file` | Étiqueter un fichier unique avec le tagger distant Hailo | `file_id`: int |
| `hailo_tagger_batch` | Étiqueter plusieurs fichiers en lot (max 500) | `file_ids`: list, `expected_count`: int = 0 |
| `hailo_tagger_status` | Vérifier l'état de connexion du tagger distant Hailo | — |
| `hailo_tagger_get_config` | Obtenir la configuration du tagger distant Hailo | — |
| `hailo_tagger_save_config` | Enregistrer la configuration du tagger distant Hailo | `config`: dict |
| `hailo_tagger_get_tags` | Obtenir les tags Hailo d'un fichier | `file_id`: int |
| `hailo_tagger_delete_tags` | Supprimer les tags Hailo d'un fichier | `file_id`: int |

## Tagger Server Registry (13)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `tagger_servers_list` | Liste des serveurs de tagger enregistrés et mode distribué | -- |
| `tagger_servers_add` | Ajouter un serveur de tagger | `name`: str, `type`: str, `config`: dict, `priority`: int = 50, `enabled`: bool = True |
| `tagger_servers_update` | Mettre à jour la configuration d'un serveur de tagger | `server_id`: str, `updates`: dict |
| `tagger_servers_remove` | Supprimer un serveur de tagger | `server_id`: str |
| `tagger_servers_test` | Tester la connexion d'un serveur de tagger | `server_id`: str |
| `tagger_servers_health` | Vérification santé de tous les serveurs activés | -- |
| `tagger_servers_set_mode` | Définir le mode distribué (single/parallel/idle_first) | `mode`: str |
| `tagger_servers_batch` | Tagging batch distribué (work-stealing sur file partagée) | `file_ids`: list = None, `limit`: int = 500, `force`: bool = False, `threshold`: float = None |
| `tagger_servers_batch_cancel` | Annuler un job batch cluster de tagger en cours | -- |
| `tagger_servers_tags` | Obtenir les tags de tagger d'un fichier | `file_id`: int |
| `tagger_servers_delete_tags` | Supprimer les tags de tagger d'un fichier | `file_id`: int |
| `tagger_servers_stats` | Statistiques tagger (nombre de fichiers non étiquetés) | -- |
| `tagger_servers_migrate_legacy` | Migrer l'ancienne configuration hailo_tagger vers le registre | -- |

## Prompt Library (21)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `search_prompts` | Rechercher des prompts | `query`: str = '', `folder_id`: int = 0, `tag_id`: int = 0, `sort`: str = 'updated_at', `order`: str = 'desc', `limit`: int = 50, `offset`: int = 0 |
| `get_prompt` | Obtenir le détail d'un prompt | `prompt_id`: int |
| `create_prompt` | Créer un prompt | `title`: str, `positive`: str = '', `negative`: str = '', `memo`: str = '', ... |
| `create_prompt_from_file` | Créer un prompt depuis les métadonnées d'image | `file_id`: int |
| `update_prompt` | Mise à jour partielle d'un prompt | `prompt_id`: int, ... |
| `delete_prompt` | Supprimer un prompt | `prompt_id`: int |
| `list_prompt_folders` | Liste des dossiers | — |
| `create_prompt_folder` | Créer un dossier | `name`: str |
| `update_prompt_folder` | Renommer un dossier | `folder_id`: int, `name`: str |
| `delete_prompt_folder` | Supprimer un dossier | `folder_id`: int |
| `move_prompt_to_folder` | Déplacer un prompt dans un dossier | `prompt_id`: int, `folder_id`: int |
| `remove_prompt_from_folder` | Retirer d'un dossier (vers la racine) | `prompt_id`: int |
| `list_prompt_tags` | Liste des tags | — |
| `create_prompt_tag` | Créer un tag | `name`: str |
| `delete_prompt_tag` | Supprimer un tag | `tag_id`: int |
| `set_prompt_tags` | Définir les tags d'un prompt | `prompt_id`: int, `tag_ids`: list |
| `bulk_delete_prompts` | Suppression en lot | `prompt_ids`: list |
| `bulk_move_prompts` | Déplacement en lot | `prompt_ids`: list, `folder_id`: int |
| `bulk_tag_prompts` | Étiquetage en lot | `prompt_ids`: list, `tag_ids`: list |
| `export_prompts` | Export JSON de tous les prompts | — |
| `import_prompts` | Import JSON de prompts | `data`: dict |

## Prompt Simulator (6)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `prompt_dp_analyze` | Analyse syntaxique Dynamic Prompts | `text`: str |
| `prompt_emphasis` | Conversion de syntaxe d'emphase | `text`: str, `format`: str = 'a1111' |
| `prompt_convert` | Conversion de format A1111 ↔ NAI | `text`: str, `from_format`: str = 'a1111', `to_format`: str = 'nai' |
| `prompt_list_wildcards` | Liste des wildcards | — |
| `prompt_set_wildcard_dirs` | Définir les répertoires de wildcards | `dirs`: list |
| `prompt_danbooru_autocomplete` | Autocomplétion de tags Danbooru | `q`: str |

## Prompt Syntax (1)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `analyze_prompt_syntax` | Analyse syntaxique de prompt (infos de tokens) | `text`: str, `engine`: str = 'a1111' |

## SD/NAI Conversion (3)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `convert_sd_to_nai` | Conversion de prompt SD → NAI | `text`: str |
| `convert_nai_to_sd` | Conversion de prompt NAI → SD | `text`: str |
| `convert_prompt_batch` | Conversion de prompts en lot | `items`: list, `direction`: str = 'sd-to-nai' |

## Chat Logs (16)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `search_chat_logs` | Recherche en texte intégral FTS5 | `query`: str = '', `source`: str = '', `model`: str = '', `limit`: int = 50, ... |
| `search_chat_logs_grouped` | Recherche groupée par conversation | `query`: str, `source`: str = '', `limit`: int = 20 |
| `get_conversation` | Détail de conversation (tous messages) | `conversation_id`: int |
| `get_chat_full` | Alias de get_conversation | `conversation_id`: int |
| `get_chat_summary` | Résumé généré par IA | `conversation_id`: int |
| `get_chat_decisions` | Décisions extraites par IA | `conversation_id`: int |
| `get_related_conversations` | Conversations liées | `conversation_id`: int, `limit`: int = 10 |
| `find_chat_by_entity` | Recherche de conversation par entité | `entity_type`: str, `entity_value`: str, `limit`: int = 50 |
| `search_chat_by_topic` | Recherche par sujet | `topic`: str, `limit`: int = 50 |
| `search_decisions` | Recherche transversale de décisions | `query`: str, `limit`: int = 50 |
| `import_chat_log` | Import depuis un fichier local | `source`: str, `json_path`: str |
| `get_chatlog_import_status` | Progression de l'import | — |
| `get_chatlog_stats` | Statistiques des chat logs | — |
| `delete_conversation` | Supprimer une conversation | `conversation_id`: int |
| `reprocess_chat_logs` | Retraitement IA | `target`: str = 'unprocessed' |
| `text_search` | Recherche transversale MD/chat/prompt | `query`: str, `target`: str = 'md,chat,prompt', `limit`: int = 20 |

## Markdown Viewer (8)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `search_md_files` | Rechercher des fichiers Markdown | `query`: str = '', `path_filter`: str = '', `limit`: int = 50, `offset`: int = 0 |
| `get_md_content` | Obtenir le contenu d'un fichier | `file_id`: int |
| `get_md_scan_roots` | Liste des racines de scan | — |
| `set_md_scan_roots` | Définir les racines de scan | `roots`: list |
| `remove_md_scan_root` | Supprimer une racine de scan | `index`: int |
| `trigger_md_scan` | Démarrer le scan | — |
| `get_md_scan_status` | Progression du scan | — |
| `get_md_stats` | Statistiques | — |

## Freeze & Pull-back (6)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `generate_freeze_pullback` | Génération de vidéo Ken Burns | `file_id`: int, `hold_seconds`: float = 2.0, `pull_seconds`: float = 5.0, `fps`: int = 30, ... |
| `get_fpb_status` | État du job de rendu | — |
| `fpb_check` | Vérification des prérequis (ffmpeg, etc.) | — |
| `fpb_cancel` | Annuler la génération | — |
| `fpb_list_outputs` | Liste des fichiers de sortie | — |
| `fpb_delete_output` | Supprimer un fichier de sortie | `filename`: str |

## Speech-to-Text (8)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `s2t_status` | État du backend | — |
| `s2t_transcribe_video` | Transcription vidéo/audio | `file_id`: int, `language`: str = '' |
| `s2t_batch_transcribe` | Transcription en lot | `file_ids`: list, `language`: str = '', `expected_count`: int = 0 |
| `s2t_get_transcript` | Obtenir la transcription stockée | `file_id`: int |
| `s2t_stream_start` | Démarrer la transcription en streaming | `source_url`: str, `language`: str = 'ja', `mode`: str = 'chunk' |
| `s2t_stream_stop` | Arrêter la transcription en streaming | — |
| `s2t_stream_status` | Obtenir l'état du stream | — |
| `s2t_stream_transcript` | Obtenir le résultat de transcription en streaming | — |

## Statistics (6)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `get_stats_timeline` | Statistiques timeline | `period`: str = 'daily' |
| `get_stats_hourly` | Statistiques par plage horaire | — |
| `get_stats_models` | Statistiques d'usage de modèles | — |
| `get_stats_resolutions` | Statistiques de distribution de résolution | — |
| `get_stats_story` | Narratif de l'histoire de la bibliothèque | — |
| `get_monthly_report` | Rapport mensuel | `month`: str = '' |

## Profiles (11)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `list_profiles` | Liste des profils | — |
| `get_profile` | Obtenir un profil | `name`: str |
| `create_profile` | Créer un profil | `name`: str, `description`: str = '' |
| `update_profile` | Mettre à jour un profil | `name`: str, `settings`: dict |
| `delete_profile` | Supprimer un profil | `name`: str |
| `duplicate_profile` | Dupliquer un profil | `name`: str, `new_name`: str |
| `rename_profile` | Renommer un profil | `name`: str, `new_name`: str |
| `toggle_profile_favorite` | Basculer favori | `name`: str |
| `export_profile` | Exporter un profil | `name`: str |
| `import_profile` | Importer un profil depuis des données exportées | `qr_data`: str, `mode`: str = "full" |
| `import_profile_preview` | Prévisualiser l'import de profil | `qr_data`: str |

## File Operations (4)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `convert_image` | Conversion de format d'image | `file_id`: int, `format`: str = 'webp' |
| `extract_from_zip` | Extraire un fichier d'un ZIP | `file_id`: int, `members`: list |
| `inspect_metadata` | Inspection des métadonnées brutes | `file_id`: int |
| `get_share_link` | Générer un lien de partage | `file_id`: int |

## SVG Rasterization (2)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `svg_info` | Obtenir disponibilité et infos backend de la rasterisation SVG | — |
| `svg_rasterize` | Rasteriser un SVG en PNG/WebP. Le base64 retourné est utilisable directement comme entrée img2img | `file_id`: int = 0, `svg_path`: str = '', `svg_data`: str = '', `width`: int = 1024, `height`: int = 1024, `format`: str = 'png', `background`: str = '' |

## Download (1)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `batch_download_zip` | Télécharger plusieurs images en ZIP | `file_ids`: list, `expected_count`: int = 0 |

## Video Analysis (3)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `get_video_analysis_config` | Obtenir la configuration d'analyse vidéo | — |
| `save_video_analysis_config` | Enregistrer la configuration d'analyse vidéo | `config`: dict |
| `get_video_analysis_status` | État de l'analyse vidéo | — |

## Backup (5)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `list_backups` | Liste des sauvegardes | — |
| `create_backup` | Créer une sauvegarde | — |
| `restore_backup` | Restaurer une sauvegarde | `filename`: str |
| `delete_backup` | Supprimer une sauvegarde | `filename`: str |
| `get_backup_status` | État de sauvegarde | — |

## Archive Cleanup (7)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `archive_cleanup_scan` | Scan des paires d'archives | `path`: str = '' |
| `archive_cleanup_execute` | Exécuter le nettoyage | `actions`: list, `expected_count`: int = 0 |
| `archive_cleanup_llm_verify` | Vérifier les actions avec LLM (unique) | `file_path`: str, `action`: str |
| `archive_cleanup_llm_verify_batch` | Vérifier les actions avec LLM (lot) | `items`: list |
| `archive_cleanup_get_llm_config` | Obtenir la configuration LLM | — |
| `archive_cleanup_save_llm_config` | Enregistrer la configuration LLM | `config`: dict |
| `archive_cleanup_list_models` | Liste des modèles LLM disponibles | — |

## Auto Scan Watcher (3)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `auto_scan_info` | État de surveillance | — |
| `auto_scan_start` | Démarrer la surveillance de fichiers | — |
| `auto_scan_stop` | Arrêter la surveillance de fichiers | — |

## Scheduler (6)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `get_scheduler_status` | Obtenir le statut du planificateur et les jobs enregistrés | -- |
| `list_scheduled_jobs` | Liste des déclencheurs et prochaines exécutions de tous les jobs | -- |
| `trigger_scheduled_job` | Déclencher l'exécution immédiate d'un job planifié | `job_id`: str |
| `pause_scheduled_job` | Mettre en pause un job planifié | `job_id`: str |
| `resume_scheduled_job` | Reprendre un job planifié en pause | `job_id`: str |
| `get_scheduler_history` | Obtenir l'historique d'exécution récent des jobs | -- |

## Webhooks (9)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `list_webhooks` | Liste des Webhooks | — |
| `create_webhook` | Créer un Webhook | `url`: str, `events`: list, `name`: str = '' |
| `update_webhook` | Mettre à jour un Webhook | `webhook_id`: str, `url`: str = '', `events`: list = None, `name`: str = '', `enabled`: bool = True |
| `delete_webhook` | Supprimer un Webhook | `webhook_id`: str |
| `test_webhook` | Envoyer un événement de test | `webhook_id`: str |
| `get_webhook_deliveries` | Historique des livraisons | `webhook_id`: str = '', `limit`: int = 50 |
| `create_inbound_webhook` | Créer un inbound webhook pour déclencheur externe. Retourne l'URL token. | `label`: str, `allowed_events`: list |
| `list_inbound_webhooks` | Obtenir la liste des inbound webhooks enregistrés. | — |
| `delete_inbound_webhook` | Supprimer un inbound webhook. | `webhook_id`: str |

## Extensions (25)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `list_extensions` | Liste des Extensions | — |
| `get_extension_detail` | Détail d'une Extension | `name`: str |
| `toggle_extension` | Activer/désactiver | `name`: str, `enabled`: bool |
| `install_extension` | Installer depuis un dépôt Git | `url`: str |
| `update_extension` | Mettre à jour une Extension | `name`: str |
| `update_all_extensions` | Mettre à jour toutes les Extensions | — |
| `uninstall_extension` | Désinstaller une Extension | `name`: str |
| `search_marketplace` | Rechercher dans le marketplace | `query`: str = '' |
| `refresh_marketplace` | Mettre à jour le catalogue du marketplace | — |
| `get_extension_config` | Obtenir la configuration | `name`: str |
| `set_extension_config` | Mettre à jour la configuration | `name`: str, `values`: dict |
| `get_extension_permissions` | Obtenir les informations de permissions | `name`: str |
| `approve_extension_permissions` | Approuver/refuser des permissions | `name`: str, `granted`: list = None, `denied`: list = None, `action`: str = 'approve' |
| `scan_extension_code` | Analyse statique du code | `name`: str |
| `rescan_extension` | Rescanner le code | `name`: str |
| `get_extension_tokens` | État des Capability Tokens | `name`: str |
| `get_extension_integrity` | Intégrité des fichiers et état de surveillance | `name`: str |
| `get_extension_hooks` | Liste des hooks enregistrés | — |
| `get_extension_isolation_status` | État d'isolation de processus | — |
| `get_extension_os_isolation_status` | État d'isolation niveau OS | — |
| `create_extension` | Créer une Extension personnalisée avec scaffolding | `name`: str, `description`: str = "" |
| `validate_extension` | Valider le manifeste et le code d'une Extension | `extension_name`: str |
| `list_extension_files` | Liste des fichiers d'une Extension personnalisée | `extension_name`: str |
| `read_extension_file` | Lire un fichier d'une Extension personnalisée | `extension_name`: str, `file_type`: str, `filename`: str |
| `write_extension_file` | Écrire un fichier dans une Extension personnalisée | `extension_name`: str, `file_type`: str, `filename`: str, `content`: str |

## UI Management (4)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `list_uis` | Liste des UI | — |
| `switch_ui` | Changer l'UI active | `name`: str |
| `install_ui` | Installer une UI | `url`: str |
| `uninstall_ui` | Désinstaller une UI | `name`: str |

## Settings (18)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `settings_get_schema` | Obtenir le schéma des paramètres | — |
| `settings_get_all` | Obtenir tous les paramètres | — |
| `settings_get` | Obtenir un paramètre individuel | `key`: str |
| `settings_set` | Mettre à jour un paramètre | `key`: str, `value`: str, `op_uri`: str = '' |
| `get_legacy_config` | Obtenir l'ancienne config.json | — |
| `save_legacy_config` | Enregistrer l'ancienne config.json | `config`: dict |
| `secrets_status` | État de la clé de chiffrement | — |
| `secrets_export` | Exporter la clé de chiffrement | `password`: str |
| `secrets_import` | Importer la clé de chiffrement | `export_json`: str, `password`: str |
| `get_op_status` | État du CLI 1Password | — |
| `delete_op_mapping` | Supprimer un mapping 1Password | `key`: str |
| `migrate_secrets_to_keychain` | Migrer vers le keychain OS | — |
| `get_bw_status` | Obtenir le statut d'intégration du CLI Bitwarden | -- |
| `list_bw_folders` | Liste des dossiers Bitwarden | -- |
| `delete_bw_mapping` | Supprimer un mapping de champ Bitwarden | `key`: str |
| `list_op_vaults` | Liste des Vaults 1Password | -- |
| `push_secrets_to_1password` | Pousser tous les secrets vers 1Password et auto-lier le mapping op_secrets | `vault`: str, `item_title`: str = "YU AI Manager" |
| `push_secrets_to_bitwarden` | Pousser tous les secrets vers Bitwarden et auto-lier le mapping | `item_name`: str = "YU AI Manager", `folder_id`: str = "" |

## SNS Sharing (15)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `share_to_bluesky` | Publier sur Bluesky | `file_id`: int, `text`: str = '', `attach_image`: bool = True |
| `test_bluesky_connection` | Tester la connexion Bluesky | — |
| `get_x_share_url` | Obtenir l'URL de partage X (Twitter) | `file_id`: int |
| `get_sns_preview` | Prévisualisation du partage SNS | `file_id`: int |
| `get_sns_config` | Obtenir la configuration SNS | — |
| `save_sns_config` | Enregistrer la configuration SNS | `config`: dict |
| `bsky_get_pending_notifications` | Obtenir les notifications Bluesky non lues depuis la file | -- |
| `bsky_get_notification_queue` | Obtenir les items de file avec filtre | `status`: str = "", `notification_type`: str = "" |
| `bsky_poll_notifications` | Déclencher le polling immédiat des notifications Bluesky | -- |
| `bsky_triage_notification` | Définir le résultat de triage d'une notification | `queue_id`: int, `result`: str |
| `bsky_send_auto_response` | Envoyer une réponse automatique à mention/réponse/citation | `queue_id`: int, `text`: str |
| `bsky_get_monitor_config` | Obtenir la configuration du monitor Bluesky | -- |
| `bsky_save_monitor_config` | Enregistrer la configuration du monitor Bluesky | `poll_interval_minutes`: int = 0, `auto_dismiss_follow`: bool = True, `auto_dismiss_like`: bool = True, `auto_dismiss_repost`: bool = True, `auto_respond_enabled`: bool = False |
| `bsky_get_triage_prompts` | Obtenir les prompts et templates de triage Bluesky | -- |
| `bsky_save_triage_prompts` | Enregistrer les prompts de triage Bluesky | `triage_mention`: str = "", `triage_reply`: str = "", `triage_quote`: str = "", `response_mention`: str = "", `response_reply`: str = "" |

## LAN Share (2)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `create_lan_share` | Créer un token de partage LAN | `collection_id`: int, `expires_hours`: int = 24 |
| `revoke_lan_share` | Révoquer un token de partage | `token`: str |

## MCP Client (8)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `list_mcp_connections` | Liste des connexions MCP | — |
| `create_mcp_connection` | Créer une connexion MCP | `name`: str, `command`: str, `args`: list = None, `env`: dict = None |
| `update_mcp_connection` | Mettre à jour une connexion MCP | `connection_id`: str, `name`: str = '', `command`: str = '', `args`: list = None, `env`: dict = None |
| `delete_mcp_connection` | Supprimer une connexion MCP | `connection_id`: str |
| `connect_mcp_server` | Se connecter à un serveur MCP | `connection_id`: str |
| `disconnect_mcp_server` | Se déconnecter d'un serveur MCP | `connection_id`: str |
| `get_mcp_connection_tools` | Liste des outils du serveur connecté | `connection_id`: str |
| `call_mcp_tool` | Appeler un outil du serveur connecté | `connection_id`: str, `tool_name`: str, `arguments`: dict = None |

## Cross Search (9)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `cross_search_get_scan_roots` | Obtenir les répertoires racines Cross Search | -- |
| `cross_search_set_scan_roots` | Définir les répertoires racines Cross Search | `roots`: list |
| `cross_search_delete_scan_root` | Supprimer une racine Cross Search par index | `index`: int |
| `cross_search_scan` | Démarrer le scan de fichiers texte Cross Search | -- |
| `cross_search_scan_stop` | Arrêter le scan Cross Search en cours | -- |
| `cross_search_scan_status` | Obtenir la progression du scan Cross Search | -- |
| `cross_search_get_txt` | Obtenir le contenu texte des fichiers indexés Cross Search | `file_id`: int |
| `cross_search_open_file` | Ouvrir un fichier dans le gestionnaire système | `path`: str |
| `cross_search_stats` | Obtenir les statistiques Cross Search | -- |

## Tag Dictionary (6)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `search_tag_dictionary` | Rechercher dans le dictionnaire de tags | `query`: str, `limit`: int = 20, `fuzzy`: bool = False |
| `get_tag_dict_stats` | Statistiques du dictionnaire de tags | — |
| `split_tags` | Diviser des tags concaténés | `text`: str |
| `import_tag_dictionary` | Importer un dictionnaire de tags | `data`: dict |
| `clear_tag_dictionary` | Vider le dictionnaire de tags | — |
| `get_tag_dict_info` | Obtenir le détail d'un tag unique | `tag`: str |

## Trophies (1)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `list_trophies` | Liste des trophées | — |

## Source Code Browsing (3)

Outils pour consulter en lecture seule et en toute sécurité le code source du projet.
Protégés par 3 couches de sécurité (normalisation de chemin + whitelist d'extensions + blocklist de fichiers sensibles).
Détails : [`docs/api/source.md`](source.md)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `source_tree` | Afficher l'arborescence | `path`: str = '', `depth`: int = 3 |
| `source_read` | Lire le contenu d'un fichier (avec numéros de ligne) | `path`: str, `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | Rechercher du texte dans le code source | `query`: str, `glob`: str = '', `limit`: int = 30 |

## Help (3)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `help_toc` | Table des matières de l'aide | — |
| `help_get_section` | Obtenir le contenu d'une section | `section`: str |
| `help_search` | Rechercher dans l'aide | `query`: str, `limit`: int = 5 |

## System Info (3)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `get_server_info` | Informations serveur | — |
| `get_inference_info` | Informations du moteur d'inférence | — |
| `get_market_quotes` | Informations de marché | — |

## System Update (5)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `check_for_update` | Vérifier la disponibilité d'une nouvelle version sur GitHub | — |
| `get_update_status` | Obtenir la méthode d'installation et la version actuelle | — |
| `apply_system_update` | Appliquer une mise à jour disponible (git/portable uniquement) | `confirm`: str |
| `check_unified_updates` | Vérifier en lot l'état des mises à jour système + toutes Extensions | `force`: bool (optional) |
| `apply_unified_updates` | Mettre à jour en lot système + Extensions (avec sauvegarde automatique) | `update_system`: bool, `update_extensions`: bool, `extension_names`: list (optional) |

## Suggestions (4)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `get_suggestions` | Autocomplétion tag/prompt | `q`: str, `limit`: int = 10 |
| `suggest_tags` | Autocomplétion de tags | `q`: str, `limit`: int = 10 |
| `suggest_lora` | Autocomplétion de nom LoRA | `q`: str = '' |
| `suggest_embedding` | Autocomplétion de nom Embedding | `q`: str = '' |

## Logs & Debug (9)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `get_recent_logs` | Obtenir les logs récents | `limit`: int = 100 |
| `get_debug_log` | Sortie de log de debug | `lines`: int = 200 |
| `clear_debug_log` | Effacer le log de debug | — |
| `get_cache_info` | Statistiques de cache | — |
| `clear_cache` | Vider le cache | — |
| `rebuild_groups` | Reconstruire les groupes de répertoires | — |
| `list_dirs` | Liste des répertoires | `path`: str = '' |
| `debug_file_meta` | Métadonnées de debug d'un fichier | `file_id`: int |
| `debug_model_check` | Vérification de disponibilité des modèles | — |

## Agent Safety Gateway (25)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `agent_status` | État global des fonctions de sécurité | — |
| `agent_kill` | Activer le Kill Switch (blocage immédiat de tous les outils) | `reason`: str = 'Manual kill via MCP' |
| `agent_resume` | Lever le Kill Switch | — |
| `agent_circuit_breaker_status` | État du Circuit Breaker | — |
| `agent_circuit_breaker_reset` | Réinitialiser le Circuit Breaker | — |
| `agent_budget_status` | État du Budget Tracker | — |
| `agent_budget_reset` | Réinitialiser le Budget Tracker | — |
| `agent_approval_status` | Liste des demandes en attente d'approbation | — |
| `agent_approval_respond` | Répondre à une demande d'approbation | `request_id`: str, `action`: str |
| `agent_approval_history` | Historique d'approbation | `limit`: int = 50 |
| `agent_scope_status` | État du Scope Fence | — |
| `agent_scope_get` | Obtenir le Scope de session | `session_id`: str |
| `agent_scope_set` | Définir le Scope de session | `preset`: str = 'organizer', `duration_hours`: float = 0 |
| `agent_scope_delete` | Supprimer le Scope de session | `session_id`: str |
| `agent_tool_level` | Vérifier le niveau de sécurité d'un outil | `tool_name`: str = '' |
| `agent_auto_approve_list` | Liste des règles d'auto-approbation | — |
| `agent_auto_approve_add` | Ajouter une règle d'auto-approbation | `tool_name`: str |
| `agent_auto_approve_remove` | Supprimer une règle d'auto-approbation | `index`: int |
| `agent_undo` | Annuler une action | `journal_id`: int |
| `agent_undoable` | Liste des actions annulables | `session_id`: str = '', `limit`: int = 50 |
| `agent_journal` | Recherche dans le journal d'actions | `tool_name`: str = '', `status`: str = '', `session_id`: str = '', `limit`: int = 50, `offset`: int = 0 |
| `agent_journal_stats` | Statistiques du journal | — |
| `agent_anomaly_status` | État de détection d'anomalie | — |
| `agent_anomaly_alerts` | Historique des alertes d'anomalie | `limit`: int = 50 |
| `agent_anomaly_reset` | Réinitialiser la détection d'anomalie | — |

---

## GitHub Integration (12)

Surveillance, triage et rapports des issues de comptes GitHub.

| Outil | Description | Paramètres |
|------|-------------|------------|
| `github_list_accounts` | Liste des comptes GitHub enregistrés (tokens masqués) | — |
| `github_fetch_issues` | Obtenir les issues des dépôts d'un compte | `account_label`: str, `state`: str = 'open', `since`: str = '' |
| `github_triage_issues` | Obtenir et classer les issues (valid_bug / skip / needs_info). Retourne un rapport priorisé | `account_label`: str, `state`: str = 'open', `since`: str = '' |
| `github_get_issue_detail` | Sortie structurée des détails d'issue pour Claude Code (avec commentaires) | `account_label`: str, `repo`: str, `issue_number`: int |
| `github_rate_limit` | Vérifier le quota de rate limit de l'API GitHub | `account_label`: str |
| `github_get_pending_issues` | Obtenir les Issues non traitées depuis la file locale | -- |
| `github_get_issue_queue` | Obtenir les items de file d'Issues avec filtre de statut | `status`: str = "" |
| `github_poll_issues` | Déclencher le polling immédiat des Issues GitHub | -- |
| `github_triage_queue_item` | Définir le résultat de triage d'un Issue de la file | `queue_id`: int, `result`: str |
| `github_dismiss_queue_item` | Rejeter un Issue de la file (option auto-close) | `queue_id`: int, `auto_close`: bool = False, `account_label`: str = "" |
| `github_get_triage_prompts` | Obtenir les prompts de triage pour Issue/PR/Discussion | `repo`: str = "" |
| `github_save_triage_prompts` | Enregistrer les prompts de triage | `issue`: str = "", `pr`: str = "", `discussion`: str = "", `repo`: str = "" |

## Debug Tools (9)

Outils de validation système et de débogage. Activés avec `YU_DEBUG_MODE=1`.

| Outil | Description | Paramètres |
|------|-------------|------------|
| `debug_health_check` | Vérification santé système : Flask, tables DB, version de schéma | -- |
| `debug_validate_counts` | Validation croisée des statistiques API et comptes DB | -- |
| `debug_validate_search` | Valider l'API de recherche avec des patterns de test | `patterns`: str = "all" |
| `debug_validate_collection` | Validation du compte de cache de collection vs DB | -- |
| `debug_validate_annotations` | Validation de l'intégrité des données d'annotations | -- |
| `debug_sample_files` | Échantillonner des fichiers aléatoires et rapporter l'intégrité des champs | `n`: int = 50, `fields`: str = "meta_source,width,height" |
| `debug_roundtrip_test` | Test roundtrip écriture-lecture-update-suppression | -- |
| `debug_readonly_query` | Exécuter une requête SQL en lecture seule | `sql`: str, `limit`: int = 100 |
| `debug_full_report` | Exécuter toute la validation de debug en lot | -- |

---

## LoRA Dataset Manager (15)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `list_lora_projects` | Liste des projets | — |
| `get_lora_project` | Obtenir les détails d'un projet | `project_id`: int |
| `create_lora_project` | Créer un projet | `name`: str, `concept`: str, `base_model`: str = 'sdxl', `repeat`: int = 10, `model_scope`: str = 'active' |
| `update_lora_project` | Mettre à jour un projet | `project_id`: int, `file_ids`: list = None, `tag_exclude`: list = None, `model_scope`: str = 'active' / 'all' / '<model_id>' |
| `delete_lora_project` | Supprimer un projet | `project_id`: int |
| `get_lora_project_tags` | Obtenir l'agrégation de tags | `project_id`: int, `limit`: int = 200 |
| `preview_lora_caption` | Prévisualiser les captions | `project_id`: int, `file_id`: int = None |
| `export_lora_dataset` | Exporter le dataset | `project_id`: int, `output_dir`: str = '' |
| `get_lora_export_status` | Vérifier la progression d'export | `project_id`: int |
| `list_lora_checkpoints` | Liste des checkpoints | — |
| `preview_lora_train_command` | Prévisualiser la commande d'entraînement (dry run) | `project_id`: int, `checkpoint`: str |
| `start_lora_training` | Démarrer l'entraînement LoRA | `project_id`: int, `checkpoint`: str |
| `get_lora_train_status` | Obtenir le statut/log d'entraînement | `project_id`: int, `tail`: int = 50 |
| `list_lora_tag_presets` | Liste des presets d'exclusion de tags | — |
| `create_lora_tag_preset` | Créer un preset d'exclusion de tags | `name`: str, `tags`: list |

## LLM Endpoints (5)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `llm-endpoints-list` | Liste des endpoints LLM configurés | — |
| `llm-endpoints-set` | Ajouter/mettre à jour un endpoint LLM | `category`: str, `base_url`: str, `model`: str, `api_key`: str = '', `timeout`: int = 60 |
| `llm-endpoints-remove` | Supprimer un endpoint LLM | `category`: str |
| `llm-endpoints-test` | Tester la connexion d'un endpoint LLM | `category`: str |
| `llm-chat` | Déléguer un chat au LLM configuré | `category`: str, `message`: str, `system_prompt`: str = '', `max_tokens`: int = 1024, `temperature`: float = 0.7 |

## Server Mode (2)

| Outil | Description | Paramètres |
|------|-------------|------------|
| `server-mode-get` | Obtenir le mode serveur actuel | — |
| `server-subsystems-status` | Liste des statuts des sous-systèmes | — |

## Fonctionnalités Non Supportées par MCP

Les éléments suivants ne sont pas mis en outil pour des contraintes MCP :

- **Retour binaire** : miniatures (`/api/thumbnail/`), images originales (`/api/original/`), téléchargement ZIP, fichiers vidéo
- **Dialogues OS** : dialogue de sélection de dossier (`/api/tools/select-folder`), lancement du gestionnaire de fichiers (`/api/open-folder/`)
- **Streams SSE** : streaming de logs (`/api/logs/stream`)
- **Pages d'authentification** : écran de saisie PIN, page invité LAN Share
