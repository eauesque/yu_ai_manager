# Documentation Hub

Utilizza questo file come "punto di ingresso della documentazione (hub ufficiale)".

**Ultimo aggiornamento**: 2026-05-13

## Important

- Project README: [`../../README.ja.md`](../../README.ja.md)
- Changelog: [`../../CHANGELOG.ja.md`](../../CHANGELOG.ja.md)
- Master TODO (single source of truth): [`../../TODO.md`](../../TODO.md)

## Development Guidelines

Le linee guida di sviluppo sono organizzate come singoli file in `development/development_docs/`.

- **[TODO Rules](TODO_RULES.md)** — Regole di scrittura TODO (P0/P1/P2/P3 + categoria obbligatoria)

### Documenti principali (`development/development_docs/`)

| Documento | Contenuto |
|---|---|
| [CODE_SIZE_GUIDELINES](development/development_docs/CODE_SIZE_GUIDELINES.md) | Considera la divisione a 300 righe, obbligatoria a 500 righe |
| [MODULE_ORGANIZATION_GUIDELINES](development/development_docs/MODULE_ORGANIZATION_GUIDELINES.md) | Directory feature-unit, 100-250 righe ideali |
| [MODULE_SAFETY](development/development_docs/MODULE_SAFETY.md) | Modello di difesa a tre livelli (validazione statica/parsing/runtime) |
| [ERROR_HANDLING](development/development_docs/ERROR_HANDLING.md) | `api_error()` unificato, `{ok, error, code, detail, hint}` |
| [API_RESPONSE_GUIDELINES](development/development_docs/API_RESPONSE_GUIDELINES.md) | `api_success()` / `api_error()` / `api_result()` |
| [ENTRYPOINT_MAP](development/development_docs/ENTRYPOINT_MAP.md) | Elenco completo dei punti di ingresso di tutti i moduli |
| [ACCIDENT_POINTS](development/development_docs/ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE.md) | Strategie di prevenzione per 6 punti critici |
| [UI_BUTTON_PRIORITY_GUIDELINES](development/development_docs/UI_BUTTON_PRIORITY_GUIDELINES.md) | Progettazione pulsanti Tier A/B/C |
| [UI_STATE_SPEC](development/development_docs/UI_STATE_SPEC.md) | Modello ibrido Explorer/Library |
| [DOCUMENT_LIFECYCLE](development/development_docs/DOCUMENT_LIFECYCLE.md) | Regole di posizionamento della documentazione |
| [FUZZ_BURN_IN_TEST](development/development_docs/FUZZ_BURN_IN_TEST.md) | Test API + UI fuzzing/burn-in |

### Altra documentazione di sviluppo

| Documento | Contenuto |
|---|---|
| [ai-driven-development-principles](development/development_docs/ai-driven-development-principles.md) | Principi di progettazione dello sviluppo guidato dall'IA |
| [BATCH_API_STANDARD](development/development_docs/BATCH_API_STANDARD.md) | Standard delle operazioni batch |
| [EXTENSION_HOOKS_SPEC](development/development_docs/EXTENSION_HOOKS_SPEC.md) | Ciclo di vita dei hook di estensione |
| [REUSABLE_UI_WIDGETS](development/development_docs/REUSABLE_UI_WIDGETS.md) | Elenco widget UI riutilizzabili |
| [SD_NAI_PROMPT_SYNTAX_SPEC](development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md) | Specifica sintassi prompt SD/NAI |
| [ENCODING_FALLBACK](development/development_docs/ENCODING_FALLBACK.md) | Codifica nome file di archivio |
| [VISION_API_IMAGE_FORMATS](development/development_docs/VISION_API_IMAGE_FORMATS.md) | Tabella di compatibilità formati immagine Vision API |
| [QA_HANDOFF](development/development_docs/QA_HANDOFF.md) | Risultati round QA e problemi rimanenti |

### Log di sviluppo e specifiche

| Documento | Contenuto |
|---|---|
| [HAILO_SEMANTIC_SEARCH_DEVLOG](development/development_docs/HAILO_SEMANTIC_SEARCH_DEVLOG.md) | Log di sviluppo Hailo-10H CLIP |
| [CLIP_ONNX_DEVLOG](development/development_docs/CLIP_ONNX_DEVLOG.md) | Log di sviluppo CLIP ONNX multi-backend |
| [HAILO_DEVICE_CONTROL](development/development_docs/HAILO_DEVICE_CONTROL.md) | Controllo dispositivo Hailo |
| [CHATLOG_ENHANCED_SPEC](development/development_docs/CHATLOG_ENHANCED_SPEC.md) | Specifica estesa chatlog |
| [TAURI_DESKTOP_APP](development/development_docs/TAURI_DESKTOP_APP.md) | Integrazione desktop Tauri |
| [EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR](development/development_docs/EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2.md) | Specifica estensione Freeze & Pull-back |
| [VIDEO_METADATA_V2_PLAN](development/development_docs/VIDEO_METADATA_V2_PLAN.md) | Piano metadati video v2 (Draft) |

## Import Paths

Tutti gli import utilizzano percorsi modulo reali direttamente. I meccanismi di alias sono stati rimossi.

**Esempi di percorsi principali:**
- `core.services_core.db_api` — Accesso DB (precedentemente `core.db`)
- `core.configuration.api` — Gestione configurazione (precedentemente `core.config`)
- `core.extensions_core.runtime` — Runtime estensione (precedentemente `core.extensions`)
- Le nuove funzionalità vengono aggiunte direttamente alla directory `core/<feature>_core/`

## Troubleshooting & Operations

- Debug playbook: [`troubleshooting/debug-playbook.md`](troubleshooting/debug-playbook.md)
- Errori comuni (legacy): [`troubleshooting/common-errors.md`](troubleshooting/common-errors.md)
- Trappole codifica CJK / 2-byte: [`troubleshooting/cjk-2byte-encoding-pitfalls.md`](troubleshooting/cjk-2byte-encoding-pitfalls.md)
- Errore parse parentesi escape: [`troubleshooting/escaped-brackets-parse-error.md`](troubleshooting/escaped-brackets-parse-error.md)

## Features

| Documento | Stato | Contenuto |
|---|---|---|
| [Guida integrazione MCP](features/mcp-integration-guide.md) | Corrente | Controlla yu_ai_manager da LLM |
| [NovelAI V4](features/novelai-v4.md) | Corrente | Formato prompt NovelAI V4 - supporto negativo per personaggio |
| [Ricerca semantica Hailo](features/hailo-semantic-search.md) | Implementato → Migrazione ONNX | Istruzioni implementazione Hailo-10H CLIP |
| [Generazione tag Danbooru](features/danbooru-tag-gen-spec.md) | Implementato (v2.77.0) | Approccio due livelli WD-Tagger + VLM |
| [Gestione testo e chatlog](features/text-chatlog-management-spec.md) | Corrente | Importazione Chatlog, ricerca FTS |
| [Protocollo QR v1](features/qr-protocol-v1.md) | Corrente | Codice QR per condivisione LAN |
| [Benchmark ricerca regex](features/regex-search-benchmark.md) | Corrente | Prestazioni Regex |
| [Compatibilità browser](features/browser-compatibility.md) | Corrente | Elenco browser supportati |

## API Reference

- [Panoramica API (autenticazione, CSRF, limite di velocità)](api/README.md)
- [API ricerca](api/search.md)
- [API file](api/files.md)
- [API scansione](api/scan.md)
- [Eventi SSE](api/events.md)
- [Variabili CSS tema](api/theming.md)

## Custom UI / Plugin Development

- [Guida Custom UI](custom-ui/README.md) — Sviluppo UI personalizzato (quickstart, design, templates, advanced)
- [Guida sviluppo Plugin](plugin-development/getting-started.md) — Introduzione sviluppo estensione
- [Riferimento Manifest](plugin-development/manifest-reference.md) — Specifica extension.json

## Installation

- FFmpeg: [`installation/ffmpeg.md`](installation/ffmpeg.md)
- Docker: [`development/development_docs/DOCKER_SETUP.md`](development/development_docs/DOCKER_SETUP.md)

## Historical Docs

I seguenti sono memo di implementazione passati / registri hotfix (posizionati in `archive/docs_history/`).

- `DEBUG_INSTRUCTIONS_v2.5.4.md` — Istruzioni debug era v2.5.4
- `DARK_MODE_TAGS_IMPROVEMENT.md` — Proposta miglioramento tag dark mode (implementato)
- `EXTENSION_DRAFT.md` — Bozza iniziale sistema estensione (successore in plugin-development/)
