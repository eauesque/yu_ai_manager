# Referência de Ferramentas MCP

Lista completa de ferramentas fornecidas pelo servidor MCP (Model Context Protocol) do YU AI Manager.
Você pode chamar essas ferramentas a partir do Claude Desktop ou de outros clientes MCP para automatizar o gerenciamento, análise e geração de bibliotecas.

**Total de ferramentas: 521**

## Índice

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

## Configuração

### Variáveis de Ambiente

| Variável | Descrição | Padrão |
|------|------|-----------|
| `YU_BASE_URL` | URL do servidor YU AI Manager | `http://localhost:5000` |
| `YU_API_KEY` | Chave de API (autenticação Bearer) | (nenhuma) |
| `YU_DEBUG_MODE` | `1` para habilitar ferramentas de depuração | `0` |

### Exemplo de configuração do Claude Desktop (`claude_desktop_config.json`)

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

### Notificações de Progresso

As ferramentas `wait_for_scan` / `wait_for_batch` suportam MCP Notifications:
- **Clientes com suporte a progressToken**: Recebem progresso em tempo real via `notifications/progress`
- **Clientes sem suporte**: Aguardam em modo bloqueante e retornam o resultado final ao concluir

---

## Search & Browse (10)

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_images` | Pesquisar imagens com vários filtros | `query`: str = '', `sort`: str = 'date', `limit`: int = 20, `cursor`: str = '', `from_date`: str = '', `to_date`: str = '', `file_format`: str = 'all', `min_rating`: str = '', `max_rating`: str = '', `in_prompt`: str = '', `fav_only`: bool = False, `collection_id`: int = 0, `also_path`: bool = False |
| `search_images_grouped` | Pesquisar imagens agrupadas por diretório | `query`: str = '', `sort`: str = 'date', `limit`: int = 20, `from_date`: str = '', `to_date`: str = '' |
| `search_union` | Pesquisa por união de múltiplas consultas | `queries`: list |
| `get_image_detail` | Obter todos os metadados de uma imagem | `file_id`: int |
| `get_library_stats` | Estatísticas da biblioteca | — |
| `get_file_info` | Informações de caminho e metadados do arquivo | `file_id`: int |
| `get_groups_index` | Índice de grupos de diretórios | — |
| `get_group_members` | Lista de membros dentro de um grupo | `group`: str |
| `get_container_members` | Lista de membros dentro de contêineres ZIP/RAR | `file_id`: int |
| `file_search` | Pesquisar arquivos no banco de dados por caminho/nome | `query`: str, `meta_filter`: str = "all", `limit`: int = 100 |

## Collections (7)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_collections` | Listar todas as coleções | — |
| `create_collection` | Criar coleção | `name`: str |
| `rename_collection` | Renomear coleção | `collection_id`: int, `name`: str |
| `delete_collection` | Excluir coleção | `collection_id`: int |
| `reorder_collections` | Reordenar coleções | `order`: list |
| `add_to_collection` | Adicionar imagens à coleção | `collection_id`: int, `file_ids`: list, `expected_count`: int = 0 |
| `remove_from_collection` | Remover imagens da coleção | `collection_id`: int, `file_ids`: list, `expected_count`: int = 0 |

## Ratings & Tags (5)

| Tool | Description | Parameters |
|------|-------------|------------|
| `rate_images` | Definir avaliações de múltiplas imagens em lote | `items`: list, `expected_count`: int = 0 |
| `get_ratings` | Obter avaliações de arquivos | `file_ids`: str |
| `get_ratings_stats` | Estatísticas de avaliações | — |
| `set_tags` | Adicionar/remover tags de usuário de múltiplas imagens | `items`: list, `expected_count`: int = 0 |
| `normalize_tags` | Normalizar tags no banco de dados | — |

## Favorites (8)

| Tool | Description | Parameters |
|------|-------------|------------|
| `toggle_favorite` | Alternar favorito | `file_id`: int |
| `check_favorite` | Verificar status de favorito | `file_id`: int |
| `check_favorite_collections` | Verificar pertencimento de coleções de favoritos | `file_id`: int |
| `list_favorites` | Listar favoritos | `limit`: int = 50, `offset`: int = 0 |
| `fav_batch_add` | Adicionar múltiplos arquivos aos favoritos em lote | `file_ids`: list, `collection_id`: int = 1 |
| `fav_batch_remove` | Remover múltiplos arquivos dos favoritos em lote | `file_ids`: list, `collection_id`: int = 0 |
| `fav_export_folder` | Exportar favoritos para uma pasta no servidor | `dest_path`: str, `collection_id`: int = 0 |
| `fav_images` | Lista de imagens na coleção de favoritos | `collection_id`: int = 0 |

## Annotations (4)

| Tool | Description | Parameters |
|------|-------------|------------|
| `set_annotations` | Salvar anotações (upsert) | `items`: list, `expected_count`: int = 0 |
| `get_annotations` | Obter anotações de uma imagem | `file_id`: int, `source`: str = '', `key`: str = '' |
| `search_annotations` | Pesquisa cruzada de anotações | `source`: str = '', `key`: str = '', `min_confidence`: str = '', `max_confidence`: str = '', `limit`: int = 100, `offset`: int = 0 |
| `delete_annotations` | Excluir anotações | `source`: str, `file_ids`: Optional = None, `key`: str = '' |

## Scanning (14)

| Tool | Description | Parameters |
|------|-------------|------------|
| `trigger_scan` | Iniciar varredura em todas as raízes de varredura | — |
| `start_scan` | Iniciar varredura no caminho especificado ou em todas as raízes | `path`: str = '' |
| `get_scan_status` | Obter progresso da varredura | — |
| `cancel_scan` | Cancelar varredura | — |
| `resume_scan` | Retomar varredura interrompida | — |
| `dismiss_interrupted_scan` | Descartar estado de interrupção | — |
| `get_scan_interrupted` | Obter informações de varredura interrompida | — |
| `get_scan_errors` | Listar erros de varredura | `error_type`: str = '', `resolved`: str = 'false', `limit`: int = 50 |
| `resolve_scan_error` | Marcar erro como resolvido | `error_id`: int |
| `clear_scan_errors` | Limpar erros resolvidos | — |
| `get_scanned_roots` | Listar raízes varridas | — |
| `scan_queue_list` | Listar itens em espera na fila de varredura | -- |
| `scan_queue_remove` | Remover item da fila de varredura | `queue_id`: str |
| `scan_queue_clear` | Limpar toda a fila de varredura | -- |

## Scan Roots (9)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_scan_roots` | Listar raízes de varredura | — |
| `add_scan_root` | Adicionar raiz de varredura | `path`: str |
| `edit_scan_root` | Editar caminho da raiz de varredura | `index`: int, `path`: str |
| `remove_scan_root` | Remover raiz de varredura | `index`: int |
| `toggle_scan_root` | Habilitar/desabilitar raiz de varredura | `index`: int |
| `reorder_scan_roots` | Reordenar raízes de varredura | `order`: list |
| `scan_directory` | Varrer diretório específico | `path`: str |
| `get_checkpoints` | Checkpoints de modelos disponíveis | — |
| `purge_scanned_roots` | Purgar registros de raízes varridas | — |

## Hash & Duplicates (7)

| Tool | Description | Parameters |
|------|-------------|------------|
| `find_duplicates` | Detectar arquivos duplicados | `method`: str = 'hash' |
| `find_similar` | Pesquisar imagens similares por hash perceptual | `file_id`: int, `threshold`: int = 5 |
| `compute_hashes` | Iniciar job de cálculo de hash | `hash_type`: str = 'both' |
| `delete_duplicates` | Excluir arquivos duplicados | `groups`: list, `mode`: str = 'soft' |
| `start_hash_backfill` | Iniciar cálculo em lote de hashes não calculados | — |
| `cancel_hash_backfill` | Cancelar cálculo de hash | — |
| `get_hash_backfill_status` | Progresso do cálculo de hash | — |

## Wait / Progress (2)

| Tool | Description | Parameters |
|------|-------------|------------|
| `wait_for_scan` | Aguardar conclusão da varredura (suporte a notificações de progresso) | `timeout`: int = 600 |
| `wait_for_batch` | Aguardar conclusão de job em lote (suporte a notificações de progresso) | `job_id`: str = 'ai_analysis', `timeout`: int = 600 |

## AI Analysis (25)

| Tool | Description | Parameters |
|------|-------------|------------|
| `analyze_image` | Análise de IA de uma única imagem | `file_id`: int |
| `analyze_batch` | Análise de IA em lote de múltiplas imagens | `file_ids`: list, `expected_count`: int = 0, `server_ids`: list = None |
| `analyze_batch_cancel` | Cancelar job de análise de IA em lote em execução | -- |
| `get_analysis_result` | Obter resultado de análise | `file_id`: int |
| `get_analysis_stats` | Estatísticas de análise | — |
| `get_analysis_config` | Obter configuração de análise | — |
| `save_analysis_config` | Salvar configuração de análise | `config`: dict |
| `get_available_engines` | Listar engines disponíveis | — |
| `get_ollama_models` | Listar modelos Ollama | — |
| `test_ollama_connection` | Testar conexão com Ollama | — |
| `get_openai_compat_models` | Listar modelos da API compatível com OpenAI | — |
| `test_openai_compat_connection` | Testar conexão com API compatível com OpenAI | — |
| `list_ai_servers` | Listar servidores de IA registrados | — |
| `add_ai_server` | Registrar servidor de IA | `name`: str, `type`: str, `config`: dict, `priority`: int = 50, `enabled`: bool = True |
| `update_ai_server` | Atualizar configuração do servidor de IA | `server_id`: str, `name`: str = '', `config`: dict = None, `priority`: int = -1, `enabled`: bool = True |
| `remove_ai_server` | Remover servidor de IA | `server_id`: str |
| `set_active_ai_server` | Alternar servidor ativo | `server_id`: str |
| `test_ai_server` | Testar conexão com servidor de IA | `server_id`: str |
| `reorder_ai_servers` | Alterar prioridade dos servidores | `order`: list |
| `migrate_ai_servers` | Migrar de configurações legadas | — |
| `analyze_prompt_trends` | Analisar tendências de prompts | `limit`: int = 100 |
| `get_trend_history` | Histórico de análise de tendências | `limit`: int = 20 |
| `delete_trend_history` | Excluir histórico de tendências | `history_id`: int |
| `analyze_video` | Análise de vídeo com múltiplos keyframes (Vision LLM) | `file_id`: int, `engine`: str = "", `model`: str = "", `keyframe_count`: int = 4 |
| `transcribe_audio` | Transcrever arquivo de áudio/vídeo com Whisper | `file_id`: int, `engine`: str = "", `model`: str = "", `language`: str = "" |
| `get_audio_analysis_status` | Verificar disponibilidade de análise de áudio (ffmpeg, whisper) | -- |

## WD-Tagger (15)

| Tool | Description | Parameters |
|------|-------------|------------|
| `wd_tagger_tag_file` | Inferência de tags em um único arquivo | `file_id`: int |
| `wd_tagger_batch` | Inferência de tags em lote em múltiplos arquivos | `file_ids`: list, `expected_count`: int = 0 |
| `wd_tagger_batch_cancel` | Cancelar job de lote do WD-Tagger em execução | -- |
| `wd_tagger_get_tags` | Obter tags do WD-Tagger de um arquivo | `file_id`: int |
| `wd_tagger_delete_tags` | Excluir tags do WD-Tagger de um arquivo | `file_id`: int |
| `wd_tagger_delete_tags_batch` | Excluir tags do WD-Tagger de múltiplos arquivos em lote | `file_ids`: list, `expected_count`: int = 0 |
| `wd_tagger_get_xmp` | Obter metadados XMP | `file_id`: int |
| `wd_tagger_stats` | Estatísticas de tags | — |
| `wd_tagger_untagged` | Listar arquivos sem tags | `limit`: int = 50, `offset`: int = 0 |
| `wd_tagger_get_config` | Obter configuração | — |
| `wd_tagger_save_config` | Salvar configuração | `config`: dict |
| `wd_tagger_model_status` | Status de download do modelo | — |
| `wd_tagger_download_model` | Baixar modelo | — |
| `wd_tagger_vlm_test` | Testar conexão com servidor VLM | `url`: str |
| `wd_tagger_vlm_models` | Listar modelos do servidor VLM | `url`: str |

## Semantic Search / CLIP (12)

| Tool | Description | Parameters |
|------|-------------|------------|
| `semantic_search` | Pesquisar imagens por texto em linguagem natural | `query`: str, `limit`: int = 50, `threshold`: float = 0.2 |
| `semantic_status` | Status da Extension | — |
| `semantic_backend_info` | Informações do backend CLIP | — |
| `semantic_model_status` | Status do modelo | — |
| `semantic_model_download` | Baixar modelo CLIP | — |
| `semantic_index_start` | Iniciar construção de índice | `batch_size`: int = 32, `backend`: str = 'auto' |
| `semantic_index_status` | Progresso do índice | — |
| `semantic_index_stop` | Parar construção do índice | — |
| `semantic_index_clear` | Limpar índice | — |
| `semantic_caption_start` | Iniciar geração de legendas em lote | `batch_size`: int = 50 |
| `semantic_caption_status` | Progresso de legendas | — |
| `semantic_caption_stop` | Parar geração de legendas | — |

## YOLO Object Detection (17)

| Tool | Description | Parameters |
|------|-------------|------------|
| `yolo_status` | Status da Extension | — |
| `yolo_detect_start` | Iniciar detecção de objetos | `file_ids`: list = None, `undetected_only`: bool = True |
| `yolo_detect_status` | Progresso do job de detecção | — |
| `yolo_detect_stop` | Parar detecção | — |
| `yolo_get_results` | Obter resultados de detecção de um arquivo | `file_id`: int |
| `yolo_search` | Pesquisar imagens por rótulos de detecção | `labels`: str = '', `min_confidence`: float = 0.0, `limit`: int = 50, `offset`: int = 0 |
| `yolo_clear_results` | Limpar resultados de detecção | `file_ids`: list = None |
| `yolo_model_status` | Status do modelo | — |
| `yolo_model_download` | Baixar modelo YOLO HEF | — |
| `yolo_list_labels` | Listar rótulos detectados | — |
| `yolo_stream_sources` | Listar e obter status das fontes de stream | — |
| `yolo_stream_start` | Iniciar fonte de stream | `source_id`: str |
| `yolo_stream_stop` | Parar fonte de stream | `source_id`: str |
| `yolo_stream_add_source` | Adicionar fonte de stream | `id`: str, `url`: str, `name`: str = "" |
| `yolo_stream_rules` | Obter lista de regras de detecção | — |
| `yolo_stream_add_rule` | Adicionar regra de detecção | `id`: str, `name`: str, `classes`: list, `min_confidence`: float = 0.7, `cooldown_sec`: int = 60, `actions`: list = [] |
| `yolo_stream_status` | Status geral do stream (pipeline, fontes, regras, gravação) | — |

## OCR (19)

| Tool | Description | Parameters |
|------|-------------|------------|
| `ocr_extract` | Executar extração de texto OCR de uma imagem | `file_id`: int, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "" |
| `ocr_batch` | Executar OCR em múltiplos arquivos | `file_ids`: list, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "", `expected_count`: int = 0 |
| `ocr_get_result` | Obter resultado de OCR de um arquivo | `file_id`: int, `task`: str = "", `engine`: str = "", `all_results`: bool = False |
| `ocr_delete` | Excluir resultado de OCR de um arquivo | `file_id`: int, `task`: str = "", `engine`: str = "" |
| `ocr_export` | Exportar resultado de OCR no formato especificado | `file_id`: int, `format`: str = "md", `task`: str = "" |
| `ocr_translate` | Traduzir resultado de OCR | `file_id`: int, `target_lang`: str = "en", `server_id`: str = "", `task`: str = "" |
| `ocr_get_translations` | Obter resultados de tradução de um arquivo | `file_id`: int, `target_lang`: str = "" |
| `ocr_video` | Executar OCR em keyframes de vídeo | `file_id`: int, `task`: str = "ocr", `language`: str = "auto", `server_id`: str = "", `keyframe_count`: int = 4 |
| `ocr_bbox` | Executar detecção de bounding box nos resultados de OCR | `file_id`: int, `task`: str = "", `server_id`: str = "" |
| `ocr_overlay` | Gerar imagem com overlay de OCR | `file_id`: int, `mode`: str = "translated", `target_lang`: str = "", `format`: str = "png" |
| `ocr_export_batch` | Exportar resultados de OCR em lote | `file_ids`: list, `format`: str = "", `output_dir`: str = "", `overlay_mode`: str = "translated", `target_lang`: str = "" |
| `ocr_pdf` | Executar OCR em documento PDF | `file_id`: int, `task`: str = "ocr_document", `language`: str = "auto", `server_id`: str = "", `page_range`: str = "" |
| `ocr_engines` | Listar engines OCR disponíveis e pontuações de capacidade | -- |
| `ocr_profiles` | Listar todos os perfis de capacidade de modelos | -- |
| `ocr_profiles_fetch` | Buscar e mesclar perfis de modelos da comunidade a partir de URL | `url`: str |
| `ocr_profile_update` | Atualizar pontuações de capacidade de um modelo manualmente | `model_prefix`: str, `scores`: dict |
| `ocr_benchmark` | Medir precisão com benchmark de OCR | `task`: str = "ocr", `server_id`: str = "", `benchmark_dir`: str = "" |
| `ocr_benchmark_cases` | Listar casos de teste de benchmark disponíveis | `benchmark_dir`: str = "" |
| `ocr_npu_status` | Verificar disponibilidade de NPU e sugestões de otimização | `task`: str = "ocr" |

## SD WebUI Bridge (14)

| Tool | Description | Parameters |
|------|-------------|------------|
| `sd_test_connection` | Testar conexão | — |
| `sd_generate` | Gerar imagem txt2img | `prompt`: str, `negative_prompt`: str = '', `steps`: int = 28, `sampler`: str = 'Euler a', `cfg_scale`: float = 7.0, `width`: int = 512, `height`: int = 768, `seed`: int = -1, `expand_wildcards`: bool = False |
| `sd_get_progress` | Progresso de geração | — |
| `sd_cancel` | Cancelar geração | — |
| `sd_list_models` | Listar modelos de checkpoint | — |
| `sd_list_samplers` | Listar samplers | — |
| `sd_list_loras` | Listar LoRAs | `q`: str = '' |
| `sd_list_embeddings` | Listar Embeddings | `q`: str = '' |
| `sd_list_scripts` | Listar scripts | — |
| `sd_get_script_info` | Detalhes do script | — |
| `sd_list_extensions` | Listar Extensions | — |
| `sd_list_upscalers` | Listar upscalers | — |
| `sd_get_config` | Obter configuração | — |
| `sd_save_config` | Salvar configuração | `api_url`: str = '', `save_folder`: str = '', `auto_save`, `auto_import`, `default_sampler`: str = '' |

## ComfyUI Bridge (13)

| Tool | Description | Parameters |
|------|-------------|------------|
| `comfyui_test_connection` | Testar conexão | — |
| `comfyui_generate` | Gerar imagem txt2img | `prompt`: str, `negative_prompt`: str = '', `steps`: int = 20, `sampler_name`: str = 'euler', `scheduler`: str = 'normal', `cfg`: float = 7.0, `width`: int = 512, `height`: int = 768, `seed`: int = -1, `ckpt_name`: str = '', `expand_wildcards`: bool = False, `image_format`: str = 'png' |
| `comfyui_generate_json` | Gerar com workflow JSON | `workflow`: str |
| `comfyui_get_progress` | Progresso de geração | — |
| `comfyui_cancel` | Cancelar geração | — |
| `comfyui_list_models` | Listar modelos de checkpoint | — |
| `comfyui_list_samplers` | Listar samplers | — |
| `comfyui_list_schedulers` | Listar schedulers | — |
| `comfyui_list_loras` | Listar LoRAs | `q`: str = '' |
| `comfyui_list_embeddings` | Listar Embeddings | `q`: str = '' |
| `comfyui_list_custom_nodes` | Listar nós personalizados | `q`: str = '' |
| `comfyui_get_config` | Obter configuração | — |
| `comfyui_save_config` | Salvar configuração | `api_url`: str = '', `save_folder`: str = '', `auto_save`, `auto_import`, `default_sampler`: str = '', `default_scheduler`: str = '' |

## NovelAI Bridge (8)

| Tool | Description | Parameters |
|------|-------------|------------|
| `nai_test_connection` | Testar conexão | — |
| `nai_get_anlas` | Obter saldo de Anlas | — |
| `nai_generate` | Gerar imagem | `prompt`: str, `negative_prompt`: str = '', `width`: int = 832, `height`: int = 1216, `steps`: int = 28, `sampler`: str = '', `noise_schedule`: str = '', `seed`: int = -1, `model`: str = '', `cfg_scale`: float = 5.0 |
| `nai_list_models` | Listar modelos | — |
| `nai_list_samplers` | Listar samplers | — |
| `nai_list_noise_schedules` | Listar noise schedules | — |
| `nai_get_config` | Obter configuração | — |
| `nai_save_config` | Salvar configuração | `api_key`: str = '', `save_folder`: str = '', `auto_save`: bool = True, `auto_import`: bool = True, `default_model`: str = '' |

## Hailo GenAI (10)

| Tool | Description | Parameters |
|------|-------------|------------|
| `hailo_genai_status` | Status da Extension | — |
| `hailo_genai_model_status` | Status de carregamento do modelo | — |
| `hailo_genai_model_download` | Baixar modelo | `model_name`: str = '' |
| `hailo_genai_model_unload` | Descarregar modelo | — |
| `hailo_llm_generate` | Gerar texto com LLM | `prompt`: str, `max_tokens`: int = 256, `temperature`: float = 0.7, `system_prompt`: str = '' |
| `hailo_llm_clear_context` | Limpar contexto do LLM | — |
| `hailo_vlm_generate` | Gerar texto a partir de imagem com VLM | `file_id`: int, `prompt`: str = 'Describe this image.', `max_tokens`: int = 256 |
| `hailo_benchmark` | Executar benchmark de desempenho do Hailo LLM | `prompt`: str, `runs`: int = 3, `max_tokens`: int = 256, `temperature`: float = 0.7, `model`: str = "qwen2.5-1.5b-chat" |
| `hailo_benchmark_compare` | Comparar desempenho do LLM Hailo vs Ollama | `prompt`: str, `runs`: int = 3, `max_tokens`: int = 256, `hailo_model`: str, `ollama_model`: str |
| `hailo_genai_openai_info` | Obter informações de endpoint da API compatível com OpenAI do Hailo GenAI | -- |

## Hailo Chat (7)

| Tool | Description | Parameters |
|------|-------------|------------|
| `hailo_chat_new` | Criar nova conversa no Hailo Chat | `model`: str = "qwen2.5-1.5b-chat" |
| `hailo_chat_list` | Listar conversas do Hailo Chat | `limit`: int = 50, `offset`: int = 0 |
| `hailo_chat_get` | Obter conversa com todas as mensagens | `conversation_id`: int |
| `hailo_chat_active` | Obter ID da conversa ativa atual | -- |
| `hailo_chat_search` | Pesquisa na Web via DuckDuckGo (para injeção de contexto) | `query`: str, `max_results`: int = 5 |
| `hailo_chat_rename` | Renomear conversa | `conversation_id`: int, `title`: str |
| `hailo_chat_delete` | Excluir conversa | `conversation_id`: int |

## Hailo Remote Tagger (7)

| Tool | Description | Parameters |
|------|-------------|------------|
| `hailo_tagger_tag_file` | Taggear um único arquivo com o tagger remoto Hailo | `file_id`: int |
| `hailo_tagger_batch` | Taggear múltiplos arquivos em lote (máx. 500) | `file_ids`: list, `expected_count`: int = 0 |
| `hailo_tagger_status` | Verificar status de conexão do tagger remoto Hailo | — |
| `hailo_tagger_get_config` | Obter configuração do tagger remoto Hailo | — |
| `hailo_tagger_save_config` | Salvar configuração do tagger remoto Hailo | `config`: dict |
| `hailo_tagger_get_tags` | Obter tags Hailo de um arquivo | `file_id`: int |
| `hailo_tagger_delete_tags` | Excluir tags Hailo de um arquivo | `file_id`: int |

## Tagger Server Registry (13)

| Tool | Description | Parameters |
|------|-------------|------------|
| `tagger_servers_list` | Listar servidores tagger registrados e modo distribuído | -- |
| `tagger_servers_add` | Adicionar servidor tagger | `name`: str, `type`: str, `config`: dict, `priority`: int = 50, `enabled`: bool = True |
| `tagger_servers_update` | Atualizar configuração do servidor tagger | `server_id`: str, `updates`: dict |
| `tagger_servers_remove` | Remover servidor tagger | `server_id`: str |
| `tagger_servers_test` | Testar conexão com servidor tagger | `server_id`: str |
| `tagger_servers_health` | Verificar saúde de todos os servidores habilitados | -- |
| `tagger_servers_set_mode` | Definir modo distribuído (single/parallel/idle_first) | `mode`: str |
| `tagger_servers_batch` | Tagging em lote distribuído (work-stealing com fila compartilhada) | `file_ids`: list = None, `limit`: int = 500, `force`: bool = False, `threshold`: float = None |
| `tagger_servers_batch_cancel` | Cancelar job de lote do cluster tagger em execução | -- |
| `tagger_servers_tags` | Obter tags tagger de um arquivo | `file_id`: int |
| `tagger_servers_delete_tags` | Excluir tags tagger de um arquivo | `file_id`: int |
| `tagger_servers_stats` | Estatísticas do tagger (contagem de arquivos sem tags) | -- |
| `tagger_servers_migrate_legacy` | Migrar configuração legada hailo_tagger para formato de registro | -- |

## Prompt Library (21)

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_prompts` | Pesquisar prompts | `query`: str = '', `folder_id`: int = 0, `tag_id`: int = 0, `sort`: str = 'updated_at', `order`: str = 'desc', `limit`: int = 50, `offset`: int = 0 |
| `get_prompt` | Obter detalhes do prompt | `prompt_id`: int |
| `create_prompt` | Criar prompt | `title`: str, `positive`: str = '', `negative`: str = '', `memo`: str = '', ... |
| `create_prompt_from_file` | Criar prompt a partir de metadados de imagem | `file_id`: int |
| `update_prompt` | Atualizar prompt (atualização parcial) | `prompt_id`: int, ... |
| `delete_prompt` | Excluir prompt | `prompt_id`: int |
| `list_prompt_folders` | Listar pastas | — |
| `create_prompt_folder` | Criar pasta | `name`: str |
| `update_prompt_folder` | Renomear pasta | `folder_id`: int, `name`: str |
| `delete_prompt_folder` | Excluir pasta | `folder_id`: int |
| `move_prompt_to_folder` | Mover prompt para pasta | `prompt_id`: int, `folder_id`: int |
| `remove_prompt_from_folder` | Remover da pasta (mover para raiz) | `prompt_id`: int |
| `list_prompt_tags` | Listar tags | — |
| `create_prompt_tag` | Criar tag | `name`: str |
| `delete_prompt_tag` | Excluir tag | `tag_id`: int |
| `set_prompt_tags` | Definir tags do prompt | `prompt_id`: int, `tag_ids`: list |
| `bulk_delete_prompts` | Excluir em lote | `prompt_ids`: list |
| `bulk_move_prompts` | Mover em lote | `prompt_ids`: list, `folder_id`: int |
| `bulk_tag_prompts` | Taggear em lote | `prompt_ids`: list, `tag_ids`: list |
| `export_prompts` | Exportar todos os prompts em JSON | — |
| `import_prompts` | Importar prompts de JSON | `data`: dict |

## Prompt Simulator (6)

| Tool | Description | Parameters |
|------|-------------|------------|
| `prompt_dp_analyze` | Analisar sintaxe Dynamic Prompts | `text`: str |
| `prompt_emphasis` | Converter sintaxe de ênfase | `text`: str, `format`: str = 'a1111' |
| `prompt_convert` | Converter formato A1111 ↔ NAI | `text`: str, `from_format`: str = 'a1111', `to_format`: str = 'nai' |
| `prompt_list_wildcards` | Listar wildcards | — |
| `prompt_set_wildcard_dirs` | Definir diretórios de wildcards | `dirs`: list |
| `prompt_danbooru_autocomplete` | Autocompletar tags Danbooru | `q`: str |

## Prompt Syntax (1)

| Tool | Description | Parameters |
|------|-------------|------------|
| `analyze_prompt_syntax` | Analisar sintaxe de prompt (informações de tokens) | `text`: str, `engine`: str = 'a1111' |

## SD/NAI Conversion (3)

| Tool | Description | Parameters |
|------|-------------|------------|
| `convert_sd_to_nai` | Converter prompt SD → NAI | `text`: str |
| `convert_nai_to_sd` | Converter prompt NAI → SD | `text`: str |
| `convert_prompt_batch` | Converter prompts em lote | `items`: list, `direction`: str = 'sd-to-nai' |

## Chat Logs (16)

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_chat_logs` | Pesquisa full-text FTS5 | `query`: str = '', `source`: str = '', `model`: str = '', `limit`: int = 50, ... |
| `search_chat_logs_grouped` | Pesquisa agrupada por conversa | `query`: str, `source`: str = '', `limit`: int = 20 |
| `get_conversation` | Detalhes da conversa (todas as mensagens) | `conversation_id`: int |
| `get_chat_full` | Alias de get_conversation | `conversation_id`: int |
| `get_chat_summary` | Resumo gerado por IA | `conversation_id`: int |
| `get_chat_decisions` | Decisões extraídas por IA | `conversation_id`: int |
| `get_related_conversations` | Conversas relacionadas | `conversation_id`: int, `limit`: int = 10 |
| `find_chat_by_entity` | Pesquisar conversas por entidade | `entity_type`: str, `entity_value`: str, `limit`: int = 50 |
| `search_chat_by_topic` | Pesquisa por tópico | `topic`: str, `limit`: int = 50 |
| `search_decisions` | Pesquisa cruzada de decisões | `query`: str, `limit`: int = 50 |
| `import_chat_log` | Importar de arquivo local | `source`: str, `json_path`: str |
| `get_chatlog_import_status` | Progresso de importação | — |
| `get_chatlog_stats` | Estatísticas de logs de chat | — |
| `delete_conversation` | Excluir conversa | `conversation_id`: int |
| `reprocess_chat_logs` | Reprocessar com IA | `target`: str = 'unprocessed' |
| `text_search` | Pesquisa cruzada MD/chat/prompt | `query`: str, `target`: str = 'md,chat,prompt', `limit`: int = 20 |

## Markdown Viewer (8)

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_md_files` | Pesquisar arquivos Markdown | `query`: str = '', `path_filter`: str = '', `limit`: int = 50, `offset`: int = 0 |
| `get_md_content` | Obter conteúdo do arquivo | `file_id`: int |
| `get_md_scan_roots` | Listar raízes de varredura | — |
| `set_md_scan_roots` | Definir raízes de varredura | `roots`: list |
| `remove_md_scan_root` | Remover raiz de varredura | `index`: int |
| `trigger_md_scan` | Iniciar varredura | — |
| `get_md_scan_status` | Progresso da varredura | — |
| `get_md_stats` | Estatísticas | — |

## Freeze & Pull-back (6)

| Tool | Description | Parameters |
|------|-------------|------------|
| `generate_freeze_pullback` | Gerar vídeo Ken Burns | `file_id`: int, `hold_seconds`: float = 2.0, `pull_seconds`: float = 5.0, `fps`: int = 30, ... |
| `get_fpb_status` | Status do job de renderização | — |
| `fpb_check` | Verificar pré-requisitos (ffmpeg, etc.) | — |
| `fpb_cancel` | Cancelar geração | — |
| `fpb_list_outputs` | Listar arquivos de saída | — |
| `fpb_delete_output` | Excluir arquivo de saída | `filename`: str |

## Speech-to-Text (8)

| Tool | Description | Parameters |
|------|-------------|------------|
| `s2t_status` | Status do backend | — |
| `s2t_transcribe_video` | Transcrever vídeo/áudio | `file_id`: int, `language`: str = '' |
| `s2t_batch_transcribe` | Transcrição em lote | `file_ids`: list, `language`: str = '', `expected_count`: int = 0 |
| `s2t_get_transcript` | Obter transcrição salva | `file_id`: int |
| `s2t_stream_start` | Iniciar transcrição de stream | `source_url`: str, `language`: str = 'ja', `mode`: str = 'chunk' |
| `s2t_stream_stop` | Parar transcrição de stream | — |
| `s2t_stream_status` | Obter status do stream | — |
| `s2t_stream_transcript` | Obter resultado da transcrição do stream | — |

## Statistics (6)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_stats_timeline` | Estatísticas de linha do tempo | `period`: str = 'daily' |
| `get_stats_hourly` | Estatísticas por horário | — |
| `get_stats_models` | Estatísticas de uso de modelos | — |
| `get_stats_resolutions` | Estatísticas de distribuição de resoluções | — |
| `get_stats_story` | Narrativa da história da biblioteca | — |
| `get_monthly_report` | Relatório mensal | `month`: str = '' |

## Profiles (11)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_profiles` | Listar perfis | — |
| `get_profile` | Obter perfil | `name`: str |
| `create_profile` | Criar perfil | `name`: str, `description`: str = '' |
| `update_profile` | Atualizar perfil | `name`: str, `settings`: dict |
| `delete_profile` | Excluir perfil | `name`: str |
| `duplicate_profile` | Duplicar perfil | `name`: str, `new_name`: str |
| `rename_profile` | Renomear perfil | `name`: str, `new_name`: str |
| `toggle_profile_favorite` | Alternar favorito | `name`: str |
| `export_profile` | Exportar perfil | `name`: str |
| `import_profile` | Importar perfil a partir de dados exportados | `qr_data`: str, `mode`: str = "full" |
| `import_profile_preview` | Prévia de importação de perfil | `qr_data`: str |

## File Operations (4)

| Tool | Description | Parameters |
|------|-------------|------------|
| `convert_image` | Converter formato de imagem | `file_id`: int, `format`: str = 'webp' |
| `extract_from_zip` | Extrair arquivos de ZIP | `file_id`: int, `members`: list |
| `inspect_metadata` | Inspecionar metadados brutos | `file_id`: int |
| `get_share_link` | Gerar link de compartilhamento | `file_id`: int |

## SVG Rasterization (2)

| Tool | Description | Parameters |
|------|-------------|------------|
| `svg_info` | Obter disponibilidade e informações do backend de rasterização SVG | — |
| `svg_rasterize` | Rasterizar SVG para PNG/WebP. O base64 retornado pode ser usado diretamente como entrada img2img | `file_id`: int = 0, `svg_path`: str = '', `svg_data`: str = '', `width`: int = 1024, `height`: int = 1024, `format`: str = 'png', `background`: str = '' |

## Download (1)

| Tool | Description | Parameters |
|------|-------------|------------|
| `batch_download_zip` | Baixar múltiplas imagens em ZIP | `file_ids`: list, `expected_count`: int = 0 |

## Video Analysis (3)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_video_analysis_config` | Obter configuração de análise de vídeo | — |
| `save_video_analysis_config` | Salvar configuração de análise de vídeo | `config`: dict |
| `get_video_analysis_status` | Status de análise de vídeo | — |

## Backup (5)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_backups` | Listar backups | — |
| `create_backup` | Criar backup | — |
| `restore_backup` | Restaurar backup | `filename`: str |
| `delete_backup` | Excluir backup | `filename`: str |
| `get_backup_status` | Status do backup | — |

## Archive Cleanup (7)

| Tool | Description | Parameters |
|------|-------------|------------|
| `archive_cleanup_scan` | Varrer pares de arquivos/arquivos | `path`: str = '' |
| `archive_cleanup_execute` | Executar limpeza | `actions`: list, `expected_count`: int = 0 |
| `archive_cleanup_llm_verify` | Verificar ação com LLM (único) | `file_path`: str, `action`: str |
| `archive_cleanup_llm_verify_batch` | Verificar ações com LLM (lote) | `items`: list |
| `archive_cleanup_get_llm_config` | Obter configuração do LLM | — |
| `archive_cleanup_save_llm_config` | Salvar configuração do LLM | `config`: dict |
| `archive_cleanup_list_models` | Listar modelos LLM disponíveis | — |

## Auto Scan Watcher (3)

| Tool | Description | Parameters |
|------|-------------|------------|
| `auto_scan_info` | Status de monitoramento | — |
| `auto_scan_start` | Iniciar monitoramento de arquivos | — |
| `auto_scan_stop` | Parar monitoramento de arquivos | — |

## Scheduler (6)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_scheduler_status` | Obter status do agendador de tarefas e jobs registrados | -- |
| `list_scheduled_jobs` | Listar todos os jobs agendados com gatilhos e próxima execução | -- |
| `trigger_scheduled_job` | Acionar execução imediata de um job agendado | `job_id`: str |
| `pause_scheduled_job` | Pausar um job agendado | `job_id`: str |
| `resume_scheduled_job` | Retomar um job agendado pausado | `job_id`: str |
| `get_scheduler_history` | Obter histórico de execuções recentes do agendador | -- |

## Webhooks (9)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_webhooks` | Listar Webhooks | — |
| `create_webhook` | Criar Webhook | `url`: str, `events`: list, `name`: str = '' |
| `update_webhook` | Atualizar Webhook | `webhook_id`: str, `url`: str = '', `events`: list = None, `name`: str = '', `enabled`: bool = True |
| `delete_webhook` | Excluir Webhook | `webhook_id`: str |
| `test_webhook` | Enviar evento de teste | `webhook_id`: str |
| `get_webhook_deliveries` | Histórico de entregas | `webhook_id`: str = '', `limit`: int = 50 |
| `create_inbound_webhook` | Criar webhook inbound para gatilho externo. Retorna URL com token. | `label`: str, `allowed_events`: list |
| `list_inbound_webhooks` | Listar webhooks inbound registrados. | — |
| `delete_inbound_webhook` | Excluir webhook inbound. | `webhook_id`: str |

## Extensions (25)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_extensions` | Listar Extensions | — |
| `get_extension_detail` | Detalhes da Extension | `name`: str |
| `toggle_extension` | Habilitar/desabilitar | `name`: str, `enabled`: bool |
| `install_extension` | Instalar a partir de repositório Git | `url`: str |
| `update_extension` | Atualizar Extension | `name`: str |
| `update_all_extensions` | Atualizar todas as Extensions em lote | — |
| `uninstall_extension` | Desinstalar Extension | `name`: str |
| `search_marketplace` | Pesquisar marketplace | `query`: str = '' |
| `refresh_marketplace` | Atualizar catálogo do marketplace | — |
| `get_extension_config` | Obter configuração | `name`: str |
| `set_extension_config` | Atualizar configuração | `name`: str, `values`: dict |
| `get_extension_permissions` | Obter informações de permissões | `name`: str |
| `approve_extension_permissions` | Aprovar/recusar permissões | `name`: str, `granted`: list = None, `denied`: list = None, `action`: str = 'approve' |
| `scan_extension_code` | Análise estática de código | `name`: str |
| `rescan_extension` | Revarrer código | `name`: str |
| `get_extension_tokens` | Status dos Capability Tokens | `name`: str |
| `get_extension_integrity` | Integridade de arquivo e status de monitoramento | `name`: str |
| `get_extension_hooks` | Listar hooks registrados | — |
| `get_extension_isolation_status` | Status de isolamento de processo | — |
| `get_extension_os_isolation_status` | Status de isolamento em nível de OS | — |
| `create_extension` | Criar nova Extension personalizada com scaffold | `name`: str, `description`: str = "" |
| `validate_extension` | Validar manifesto e código da Extension | `extension_name`: str |
| `list_extension_files` | Listar arquivos de Extension personalizada | `extension_name`: str |
| `read_extension_file` | Ler arquivo de Extension personalizada | `extension_name`: str, `file_type`: str, `filename`: str |
| `write_extension_file` | Gravar arquivo em Extension personalizada | `extension_name`: str, `file_type`: str, `filename`: str, `content`: str |

## UI Management (4)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_uis` | Listar UIs | — |
| `switch_ui` | Alternar UI ativa | `name`: str |
| `install_ui` | Instalar UI | `url`: str |
| `uninstall_ui` | Desinstalar UI | `name`: str |

## Settings (18)

| Tool | Description | Parameters |
|------|-------------|------------|
| `settings_get_schema` | Obter schema de configurações | — |
| `settings_get_all` | Obter todas as configurações | — |
| `settings_get` | Obter configuração individual | `key`: str |
| `settings_set` | Atualizar configuração | `key`: str, `value`: str, `op_uri`: str = '' |
| `get_legacy_config` | Obter config.json legado | — |
| `save_legacy_config` | Salvar config.json legado | `config`: dict |
| `secrets_status` | Status da chave de criptografia | — |
| `secrets_export` | Exportar chaves de criptografia | `password`: str |
| `secrets_import` | Importar chaves de criptografia | `export_json`: str, `password`: str |
| `get_op_status` | Status do CLI do 1Password | — |
| `delete_op_mapping` | Excluir mapeamento do 1Password | `key`: str |
| `migrate_secrets_to_keychain` | Migrar para o keychain do OS | — |
| `get_bw_status` | Obter status de integração com o Bitwarden CLI | -- |
| `list_bw_folders` | Listar pastas do Bitwarden | -- |
| `delete_bw_mapping` | Excluir mapeamento de campo do Bitwarden | `key`: str |
| `list_op_vaults` | Listar Vaults do 1Password | -- |
| `push_secrets_to_1password` | Enviar todos os segredos para o 1Password e vincular automaticamente mapeamentos op_secrets | `vault`: str, `item_title`: str = "YU AI Manager" |
| `push_secrets_to_bitwarden` | Enviar todos os segredos para o Bitwarden e vincular automaticamente mapeamentos | `item_name`: str = "YU AI Manager", `folder_id`: str = "" |

## SNS Sharing (15)

| Tool | Description | Parameters |
|------|-------------|------------|
| `share_to_bluesky` | Publicar no Bluesky | `file_id`: int, `text`: str = '', `attach_image`: bool = True |
| `test_bluesky_connection` | Testar conexão com Bluesky | — |
| `get_x_share_url` | Obter URL de compartilhamento no X (Twitter) | `file_id`: int |
| `get_sns_preview` | Prévia de compartilhamento em redes sociais | `file_id`: int |
| `get_sns_config` | Obter configuração de redes sociais | — |
| `save_sns_config` | Salvar configuração de redes sociais | `config`: dict |
| `bsky_get_pending_notifications` | Obter notificações Bluesky não lidas da fila | -- |
| `bsky_get_notification_queue` | Obter itens da fila de notificações com filtros | `status`: str = "", `notification_type`: str = "" |
| `bsky_poll_notifications` | Executar polling imediato de notificações Bluesky | -- |
| `bsky_triage_notification` | Definir resultado de triagem de notificação | `queue_id`: int, `result`: str |
| `bsky_send_auto_response` | Enviar resposta automática a menções/respostas/citações | `queue_id`: int, `text`: str |
| `bsky_get_monitor_config` | Obter configuração do monitor Bluesky | -- |
| `bsky_save_monitor_config` | Salvar configuração do monitor Bluesky | `poll_interval_minutes`: int = 0, `auto_dismiss_follow`: bool = True, `auto_dismiss_like`: bool = True, `auto_dismiss_repost`: bool = True, `auto_respond_enabled`: bool = False |
| `bsky_get_triage_prompts` | Obter prompts e templates de triagem do Bluesky | -- |
| `bsky_save_triage_prompts` | Salvar prompts de triagem do Bluesky | `triage_mention`: str = "", `triage_reply`: str = "", `triage_quote`: str = "", `response_mention`: str = "", `response_reply`: str = "" |

## LAN Share (2)

| Tool | Description | Parameters |
|------|-------------|------------|
| `create_lan_share` | Criar token de compartilhamento LAN | `collection_id`: int, `expires_hours`: int = 24 |
| `revoke_lan_share` | Revogar token de compartilhamento | `token`: str |

## MCP Client (8)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_mcp_connections` | Listar conexões MCP | — |
| `create_mcp_connection` | Criar conexão MCP | `name`: str, `command`: str, `args`: list = None, `env`: dict = None |
| `update_mcp_connection` | Atualizar conexão MCP | `connection_id`: str, `name`: str = '', `command`: str = '', `args`: list = None, `env`: dict = None |
| `delete_mcp_connection` | Excluir conexão MCP | `connection_id`: str |
| `connect_mcp_server` | Conectar ao servidor MCP | `connection_id`: str |
| `disconnect_mcp_server` | Desconectar do servidor MCP | `connection_id`: str |
| `get_mcp_connection_tools` | Listar ferramentas do destino de conexão | `connection_id`: str |
| `call_mcp_tool` | Chamar ferramenta do destino de conexão | `connection_id`: str, `tool_name`: str, `arguments`: dict = None |

## Cross Search (9)

| Tool | Description | Parameters |
|------|-------------|------------|
| `cross_search_get_scan_roots` | Obter diretórios raiz de varredura do Cross Search | -- |
| `cross_search_set_scan_roots` | Definir diretórios raiz de varredura do Cross Search | `roots`: list |
| `cross_search_delete_scan_root` | Excluir raiz de varredura do Cross Search por índice | `index`: int |
| `cross_search_scan` | Iniciar varredura de arquivos de texto do Cross Search | -- |
| `cross_search_scan_stop` | Parar varredura do Cross Search em execução | -- |
| `cross_search_scan_status` | Obter progresso da varredura do Cross Search | -- |
| `cross_search_get_txt` | Obter conteúdo de texto de arquivo indexado do Cross Search | `file_id`: int |
| `cross_search_open_file` | Abrir arquivo no gerenciador de arquivos do sistema | `path`: str |
| `cross_search_stats` | Obter estatísticas do Cross Search | -- |

## Tag Dictionary (6)

| Tool | Description | Parameters |
|------|-------------|------------|
| `search_tag_dictionary` | Pesquisar dicionário de tags | `query`: str, `limit`: int = 20, `fuzzy`: bool = False |
| `get_tag_dict_stats` | Estatísticas do dicionário de tags | — |
| `split_tags` | Dividir tags concatenadas | `text`: str |
| `import_tag_dictionary` | Importar dicionário de tags | `data`: dict |
| `clear_tag_dictionary` | Limpar dicionário de tags | — |
| `get_tag_dict_info` | Obter informações detalhadas de uma única tag | `tag`: str |

## Trophies (1)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_trophies` | Listar troféus | — |

## Source Code Browsing (3)

Ferramentas para referência somente leitura do código-fonte do projeto.
Protegido por segurança em 3 camadas (normalização de caminho + lista branca de extensões + lista negra de arquivos sensíveis).
Detalhes: [`docs/api/source.md`](source.md)

| Tool | Description | Parameters |
|------|-------------|------------|
| `source_tree` | Exibir árvore de diretórios | `path`: str = '', `depth`: int = 3 |
| `source_read` | Ler conteúdo do arquivo (com números de linha) | `path`: str, `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | Pesquisar texto no código-fonte | `query`: str, `glob`: str = '', `limit`: int = 30 |

## Help (3)

| Tool | Description | Parameters |
|------|-------------|------------|
| `help_toc` | Índice da ajuda | — |
| `help_get_section` | Obter conteúdo de seção | `section`: str |
| `help_search` | Pesquisar na ajuda | `query`: str, `limit`: int = 5 |

## System Info (3)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_server_info` | Informações do servidor | — |
| `get_inference_info` | Informações do engine de inferência | — |
| `get_market_quotes` | Informações de mercado | — |

## System Update (5)

| Tool | Description | Parameters |
|------|-------------|------------|
| `check_for_update` | Verificar se há nova versão disponível no GitHub | — |
| `get_update_status` | Obter método de instalação atual e versão | — |
| `apply_system_update` | Aplicar atualização disponível (somente git/portable) | `confirm`: str |
| `check_unified_updates` | Verificar status de atualização do sistema + todas as Extensions de uma vez | `force`: bool (optional) |
| `apply_unified_updates` | Atualizar sistema + Extensions em lote (com backup automático de configuração) | `update_system`: bool, `update_extensions`: bool, `extension_names`: list (optional) |

## Suggestions (4)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_suggestions` | Completar tags/prompts | `q`: str, `limit`: int = 10 |
| `suggest_tags` | Completar tags | `q`: str, `limit`: int = 10 |
| `suggest_lora` | Completar nome de LoRA | `q`: str = '' |
| `suggest_embedding` | Completar nome de Embedding | `q`: str = '' |

## Logs & Debug (9)

| Tool | Description | Parameters |
|------|-------------|------------|
| `get_recent_logs` | Obter logs recentes | `limit`: int = 100 |
| `get_debug_log` | Exibir log de depuração | `lines`: int = 200 |
| `clear_debug_log` | Limpar log de depuração | — |
| `get_cache_info` | Estatísticas de cache | — |
| `clear_cache` | Limpar cache | — |
| `rebuild_groups` | Reconstruir grupos de diretórios | — |
| `list_dirs` | Listar diretórios | `path`: str = '' |
| `debug_file_meta` | Metadados de depuração de arquivo | `file_id`: int |
| `debug_model_check` | Verificar disponibilidade de modelos | — |

## Agent Safety Gateway (25)

| Tool | Description | Parameters |
|------|-------------|------------|
| `agent_status` | Status geral dos recursos de segurança | — |
| `agent_kill` | Acionar Kill Switch (bloquear todas as ferramentas imediatamente) | `reason`: str = 'Manual kill via MCP' |
| `agent_resume` | Liberar Kill Switch | — |
| `agent_circuit_breaker_status` | Status do Circuit Breaker | — |
| `agent_circuit_breaker_reset` | Resetar Circuit Breaker | — |
| `agent_budget_status` | Status do Budget Tracker | — |
| `agent_budget_reset` | Resetar Budget Tracker | — |
| `agent_approval_status` | Listar solicitações de aprovação pendentes | — |
| `agent_approval_respond` | Responder a solicitação de aprovação | `request_id`: str, `action`: str |
| `agent_approval_history` | Histórico de aprovações | `limit`: int = 50 |
| `agent_scope_status` | Status do Scope Fence | — |
| `agent_scope_get` | Obter Scope de sessão | `session_id`: str |
| `agent_scope_set` | Definir Scope de sessão | `preset`: str = 'organizer', `duration_hours`: float = 0 |
| `agent_scope_delete` | Excluir Scope de sessão | `session_id`: str |
| `agent_tool_level` | Verificar nível de segurança de ferramentas | `tool_name`: str = '' |
| `agent_auto_approve_list` | Listar regras de aprovação automática | — |
| `agent_auto_approve_add` | Adicionar regra de aprovação automática | `tool_name`: str |
| `agent_auto_approve_remove` | Remover regra de aprovação automática | `index`: int |
| `agent_undo` | Desfazer ação | `journal_id`: int |
| `agent_undoable` | Listar ações que podem ser desfeitas | `session_id`: str = '', `limit`: int = 50 |
| `agent_journal` | Pesquisar journal de ações | `tool_name`: str = '', `status`: str = '', `session_id`: str = '', `limit`: int = 50, `offset`: int = 0 |
| `agent_journal_stats` | Estatísticas do journal | — |
| `agent_anomaly_status` | Status de detecção de anomalias | — |
| `agent_anomaly_alerts` | Histórico de alertas de anomalias | `limit`: int = 50 |
| `agent_anomaly_reset` | Resetar detecção de anomalias | — |

---

## GitHub Integration (12)

Monitoramento, triagem e relatórios de issues de contas do GitHub.

| Tool | Description | Parameters |
|------|-------------|------------|
| `github_list_accounts` | Listar contas GitHub registradas (tokens mascarados) | — |
| `github_fetch_issues` | Buscar issues de repositórios da conta | `account_label`: str, `state`: str = 'open', `since`: str = '' |
| `github_triage_issues` | Buscar e classificar issues (valid_bug / skip / needs_info). Retorna relatório com prioridades | `account_label`: str, `state`: str = 'open', `since`: str = '' |
| `github_get_issue_detail` | Obter detalhes do issue com saída estruturada para Claude Code. Com comentários | `account_label`: str, `repo`: str, `issue_number`: int |
| `github_rate_limit` | Verificar saldo de rate limit da API GitHub | `account_label`: str |
| `github_get_pending_issues` | Obter Issues não processadas da fila local | -- |
| `github_get_issue_queue` | Obter itens da fila de Issues com filtro de status | `status`: str = "" |
| `github_poll_issues` | Executar polling imediato de Issues do GitHub | -- |
| `github_triage_queue_item` | Definir resultado de triagem para Issue na fila | `queue_id`: int, `result`: str |
| `github_dismiss_queue_item` | Descartar Issue da fila (opcionalmente com fechamento automático) | `queue_id`: int, `auto_close`: bool = False, `account_label`: str = "" |
| `github_get_triage_prompts` | Obter prompts de triagem para Issues/PRs/Discussions | `repo`: str = "" |
| `github_save_triage_prompts` | Salvar prompts de triagem | `issue`: str = "", `pr`: str = "", `discussion`: str = "", `repo`: str = "" |

## Debug Tools (9)

Ferramentas de validação do sistema e depuração. Habilitadas com `YU_DEBUG_MODE=1`.

| Tool | Description | Parameters |
|------|-------------|------------|
| `debug_health_check` | Verificação de saúde do sistema: Flask, tabelas do banco de dados, versão do schema | -- |
| `debug_validate_counts` | Validação cruzada de estatísticas da API e contagens do banco de dados | -- |
| `debug_validate_search` | Validar API de pesquisa com padrões de teste | `patterns`: str = "all" |
| `debug_validate_collection` | Validar contagens em cache de coleções vs banco de dados | -- |
| `debug_validate_annotations` | Validar integridade dos dados de anotações | -- |
| `debug_sample_files` | Amostrar arquivos aleatórios e reportar completude dos campos | `n`: int = 50, `fields`: str = "meta_source,width,height" |
| `debug_roundtrip_test` | Teste de ciclo completo: escrever-ler-atualizar-excluir | -- |
| `debug_readonly_query` | Executar consulta SQL somente leitura | `sql`: str, `limit`: int = 100 |
| `debug_full_report` | Executar todas as validações de depuração em lote | -- |

---

## LoRA Dataset Manager (15)

| Tool | Description | Parameters |
|------|-------------|------------|
| `list_lora_projects` | Listar projetos | — |
| `get_lora_project` | Obter detalhes do projeto | `project_id`: int |
| `create_lora_project` | Criar projeto | `name`: str, `concept`: str, `base_model`: str = 'sdxl', `repeat`: int = 10, `model_scope`: str = 'active' |
| `update_lora_project` | Atualizar projeto | `project_id`: int, `file_ids`: list = None, `tag_exclude`: list = None, `model_scope`: str = 'active' / 'all' / '<model_id>' |
| `delete_lora_project` | Excluir projeto | `project_id`: int |
| `get_lora_project_tags` | Obter contagem de tags | `project_id`: int, `limit`: int = 200 |
| `preview_lora_caption` | Prévia de legenda | `project_id`: int, `file_id`: int = None |
| `export_lora_dataset` | Exportar dataset | `project_id`: int, `output_dir`: str = '' |
| `get_lora_export_status` | Verificar progresso de exportação | `project_id`: int |
| `list_lora_checkpoints` | Listar checkpoints | — |
| `preview_lora_train_command` | Prévia do comando de treinamento (dry run) | `project_id`: int, `checkpoint`: str |
| `start_lora_training` | Iniciar treinamento de LoRA | `project_id`: int, `checkpoint`: str |
| `get_lora_train_status` | Obter status e logs de treinamento | `project_id`: int, `tail`: int = 50 |
| `list_lora_tag_presets` | Listar presets de exclusão de tags | — |
| `create_lora_tag_preset` | Criar preset de exclusão de tags | `name`: str, `tags`: list |

## LLM Endpoints (5)

| Tool | Description | Parameters |
|------|-------------|------------|
| `llm-endpoints-list` | Listar endpoints LLM configurados | — |
| `llm-endpoints-set` | Adicionar/atualizar endpoint LLM | `category`: str, `base_url`: str, `model`: str, `api_key`: str = '', `timeout`: int = 60 |
| `llm-endpoints-remove` | Remover endpoint LLM | `category`: str |
| `llm-endpoints-test` | Testar conexão com endpoint LLM | `category`: str |
| `llm-chat` | Delegar chat para LLM configurado | `category`: str, `message`: str, `system_prompt`: str = '', `max_tokens`: int = 1024, `temperature`: float = 0.7 |

## Server Mode (2)

| Tool | Description | Parameters |
|------|-------------|------------|
| `server-mode-get` | Obter o modo de servidor atual | — |
| `server-subsystems-status` | Listar status dos subsistemas | — |

## Funcionalidades não suportadas pelo MCP

As seguintes funcionalidades não foram implementadas como ferramentas devido às limitações do MCP:

- **Retorno binário**: Miniaturas (`/api/thumbnail/`), imagens originais (`/api/original/`), download ZIP, arquivos de vídeo
- **Diálogos do OS**: Diálogo de seleção de pasta (`/api/tools/select-folder`), iniciar gerenciador de arquivos (`/api/open-folder/`)
- **Streams SSE**: Streaming de logs (`/api/logs/stream`)
