# Indice della Documentazione di Sviluppo

Elenco dei documenti di design interni, documentazione tecnica e log di sviluppo. Tutti i file si trovano in `docs/development/development_docs/`.

È anche possibile leggerli direttamente con il tool MCP `source_read`.

---

## Design e Architettura

| Documento | Contenuto |
|-----------|-----------|
| DESIGN_PHILOSOPHY | Filosofia di design — principi guida e criteri decisionali del progetto |
| MODULE_ORGANIZATION_GUIDELINES | Linee guida per l'organizzazione dei moduli |
| CODE_SIZE_GUIDELINES | Linee guida dimensione codice (criteri suddivisione file) |
| ENTRYPOINT_MAP | Mappa degli entry point |
| DOCUMENT_LIFECYCLE | Policy ciclo di vita della documentazione |
| UI_STATE_SPEC | Specifiche stato UI (Explorer/Library ibrido) |
| NOTIFICATION_PROGRESS_DESIGN | Politica di design notifiche e indicatori di avanzamento |

## API e Elaborazione Batch

| Documento | Contenuto |
|-----------|-----------|
| API_RESPONSE_GUIDELINES | Linee guida formato risposta API |
| BATCH_API_STANDARD | Specifiche standard API batch |
| ERROR_HANDLING | Policy gestione errori |

## Sistema Extension

| Documento | Contenuto |
|-----------|-----------|
| EXTENSION_TRIAS_POLITICA_SPEC | Specifiche modello di sicurezza a tripartizione dei poteri |
| EXTENSION_SANDBOX_SPEC | Specifiche Sandbox & Permission |
| EXTENSION_HOOKS_SPEC | Specifiche Extension Hooks |
| EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2 | Specifiche Freeze & Pull-back Generator |
| CORE_TO_EXTENSION_MIGRATION_SPEC | Specifiche migrazione Core → Extension |

## AI e Integrazione Agenti

| Documento | Contenuto |
|-----------|-----------|
| AGENT_INTEGRATION_DESIGN | Guida al design integrazione AI Agent |
| AGENT_SAFETY_GATEWAY_SPEC | Specifiche AI Agent Safety Gateway |
| AI_ANALYSIS_LANGUAGE | Lingua di risposta analisi AI |
| MCP_DEBUG_TOOLS | Specifiche strumenti di debug MCP |
| OLLAMA_VLM_INTEGRATION_PITFALLS | Insidie e contromisure integrazione Ollama/VLM |
| OPENAI_COMPAT_API_DEVLOG | Log di sviluppo API compatibile OpenAI |
| VLM_ROUTING_OCR_SPEC | Specifiche design VLM Model Routing & OCR |
| VISION_API_IMAGE_FORMATS | Tabella compatibilità formati immagine Vision API |
| ai-driven-development-principles | Principi di design dello sviluppo guidato da AI |

## Database e Prestazioni

| Documento | Contenuto |
|-----------|-----------|
| SQLITE_READONLY_SEPARATION | Pattern separazione lettura/scrittura SQLite |
| LARGE_SCALE_QUERY_OPTIMIZATION | Ottimizzazione query DB large-scale (280K file) |

## Frontend e UI

| Documento | Contenuto |
|-----------|-----------|
| UI_AUDIT_GUIDE | Guida audit completo UI |
| UI_BUTTON_PRIORITY_GUIDELINES | Linee guida priorità pulsanti (metodo controller GC) |
| REUSABLE_UI_WIDGETS | Guida integrazione widget UI riutilizzabili |
| VIRTUAL_SCROLL_PITFALLS | Avvertenze e bug noti dello scroll virtuale |
| IMAGE_DISPLAY_OPTIMIZATION | Documentazione tecnica ottimizzazione visualizzazione immagini |
| MODAL_LOADING_OPTIMIZATION | Documentazione tecnica accelerazione caricamento modale dettagli |
| MODAL_MEDIA_LIFECYCLE | Gestione lifecycle media modale |
| CONTAINER_VIEW_PERFORMANCE | Ottimizzazione prestazioni vista container |
| BROWSER_CONNECTION_SATURATION | Scomparsa risultati ricerca per saturazione connessioni browser |

## Elaborazione Video

| Documento | Contenuto |
|-----------|-----------|
| VIDEO_STREAMING_ARCHITECTURE | Architettura streaming video |
| VIDEO_PERFORMANCE_OPTIMIZATION_HISTORY | Registro completo ottimizzazione prestazioni video |
| VIDEO_METADATA_V2_PLAN | Piano Video Metadata v2 (bozza) |

## Elaborazione File e Archivi

| Documento | Contenuto |
|-----------|-----------|
| NESTED_ZIP_HANDLING | Design e insidie gestione ZIP annidati |
| ZIP_SCAN_PERFORMANCE | Ottimizzazione prestazioni scansione ZIP/7z |
| ENCODING_FALLBACK | Fallback encoding nome file archivio |
| SD_NAI_PROMPT_SYNTAX_SPEC | Specifiche sintassi prompt SD/NAI |

## Cross-Platform e Infrastruttura

| Documento | Contenuto |
|-----------|-----------|
| CROSS_PLATFORM_ISSUES | Guida differenze cross-platform |
| DRAG_TO_SHARE_CROSS_PLATFORM | Supporto cross-platform drag & drop |
| ASYNC_EVENT_LOOP_BLOCKING_FIX | Correzione blocco asyncio event loop |
| MODULE_SAFETY | Design caricamento sicuro moduli |
| DOCKER_SETUP | Guida configurazione ambiente Docker |
| TAURI_DESKTOP_APP | Guida sviluppo app desktop Tauri |

## Migrazione

| Documento | Contenuto |
|-----------|-----------|
| QUART_MIGRATION_DEVLOG | Documentazione tecnica migrazione Flask → Quart (ASGI) |
| CHATLOG_ENHANCED_SPEC | Specifiche estensione chat log |

## Test e Controllo Qualità

| Documento | Contenuto |
|-----------|-----------|
| FUZZ_BURN_IN_TEST | Guida test Fuzz / Burn-in |
| QA_HANDOFF | Documento di handoff QA |
| yu-ai-manager-qa-agent-prompt | Prompt di sistema agente QA |
| ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE | Guida punti ad alto rischio incidenti e velocità layer comuni |
| BUG_VIDEO_AI_ANALYZED_FILTER | Record bug: filtro video + analisi AI |

## Release e Traduzione

| Documento | Contenuto |
|-----------|-----------|
| RELEASE_PROCEDURE | Procedura di rilascio |
| TRANSLATION_STYLE_GUIDE | Guida stile traduzione giapponese-inglese |

## Architettura

Backend: Python 3.11+ (FastAPI)
Frontend: TypeScript + Vanilla JS
Database: SQLite 3
Communication: REST API + SSE

## Setup sviluppo

```bash
git clone repo
cd yu_ai_manager
python -m venv venv
source venv/bin/activate  # o .\venv\Scripts\activate Windows
uv pip install -r requirements-dev.txt
pnpm install
pnpm run dev
```

## Test running

```bash
# Unit tests
pytest tests/

# E2E tests
pytest tests/e2e/ --playwright

# Coverage
pytest --cov=core/ tests/
```

## Code style

- Python: Black formatter, flake8
- JavaScript/TypeScript: Prettier, ESLint
- Pre-commit hooks: husky + lint-staged

```bash
# Formatta
black .
prettier --write .

# Lint
flake8 core/
eslint ui/
```

## Commit convention

```
feat: descrizione feature
fix: descrizione bug fix
docs: aggiornamenti doc
style: formattazione
refactor: refactoring senza cambio behavior
test: aggiungi test
```

## Database migration

New schema → `core/migrations/migrate_vXX.py`:

```python
def up(db):
    # Schema changes
    pass

def down(db):
    # Rollback
    pass
```

Run: `python -m core.migrations.migrate`

## Deployment

Build release:
```bash
pnpm run build:release
git tag v4.100.0
git push --tags
```
