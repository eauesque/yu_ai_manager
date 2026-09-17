# Entwicklungsdokumentations-Index

Liste interner Designdokumente, technischer Unterlagen und Entwicklungsprotokolle.
Alle Dateien befinden sich in `docs/development/development_docs/`.

Kann auch direkt mit dem MCP-Tool `source_read` gelesen werden.

---

## Design und Architektur

| Dokument | Inhalt |
|-------------|------|
| DESIGN_PHILOSOPHY | Designphilosophie — Projektweite Richtlinien und Entscheidungskriterien |
| MODULE_ORGANIZATION_GUIDELINES | Modulorganisationsrichtlinien |
| CODE_SIZE_GUIDELINES | Code-Größenrichtlinien (Dateiaufteilungskriterien) |
| ENTRYPOINT_MAP | Einstiegspunkte-Übersicht |
| DOCUMENT_LIFECYCLE | Dokumenten-Lebenszyklus-Richtlinien |
| UI_STATE_SPEC | UI-Zustandsspezifikation (Explorer/Library-Hybrid) |
| NOTIFICATION_PROGRESS_DESIGN | Benachrichtigungs-/Fortschrittsanzeige-Design |

## API und Batch-Verarbeitung

| Dokument | Inhalt |
|-------------|------|
| API_RESPONSE_GUIDELINES | API-Antwortformat-Richtlinien |
| BATCH_API_STANDARD | Batch-API-Standardspezifikation |
| ERROR_HANDLING | Fehlerbehandlungsrichtlinien |

## Extension-System

| Dokument | Inhalt |
|-------------|------|
| EXTENSION_TRIAS_POLITICA_SPEC | Sicherheitsmodell-Spezifikation (Gewaltenteilung) |
| EXTENSION_SANDBOX_SPEC | Sandbox- und Berechtigungsspezifikation |
| EXTENSION_HOOKS_SPEC | Extension-Hooks-Spezifikation |
| EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2 | Freeze & Pull-back Generator-Spezifikation |
| CORE_TO_EXTENSION_MIGRATION_SPEC | Core → Extension-Migrationsspezifikation |

## KI und Agent-Integration

| Dokument | Inhalt |
|-------------|------|
| AGENT_INTEGRATION_DESIGN | KI-Agent-Integrationsdesign-Leitfaden |
| AGENT_SAFETY_GATEWAY_SPEC | KI-Agent Safety Gateway-Spezifikation |
| AI_ANALYSIS_LANGUAGE | KI-Analyse Antwortsprachspezifikation |
| MCP_DEBUG_TOOLS | MCP-Debug-Tools-Spezifikation |
| OLLAMA_VLM_INTEGRATION_PITFALLS | Ollama/VLM-Integrationsprobleme und Lösungen |
| OPENAI_COMPAT_API_DEVLOG | OpenAI-kompatibler API-Entwicklungslog |
| VLM_ROUTING_OCR_SPEC | VLM Model Routing und OCR-Designspezifikation |
| VISION_API_IMAGE_FORMATS | Vision-API-Bildformat-Kompatibilitätstabelle |
| ai-driven-development-principles | KI-gesteuertes Entwicklungs-Designprinzip |

## Datenbank und Performance

| Dokument | Inhalt |
|-------------|------|
| SQLITE_READONLY_SEPARATION | SQLite Lese-/Schreib-Trennungsmuster |
| LARGE_SCALE_QUERY_OPTIMIZATION | Groß-DB (280K Dateien) Abfrageoptimierung |

## Frontend und UI

| Dokument | Inhalt |
|-------------|------|
| UI_AUDIT_GUIDE | UI-Umfassender Audit-Leitfaden |
| UI_BUTTON_PRIORITY_GUIDELINES | Schaltflächen-Prioritätsrichtlinien (Spielcontroller-Methode) |
| REUSABLE_UI_WIDGETS | Wiederverwendbare UI-Widgets-Integrationsleitfaden |
| VIRTUAL_SCROLL_PITFALLS | Virtuelles Scrollen — Hinweise und bekannte Bugs |
| IMAGE_DISPLAY_OPTIMIZATION | Bildanzeige-Optimierungs-Technisches Dokument |
| MODAL_LOADING_OPTIMIZATION | Detailmodal-Ladebeschleunigung Technisches Dokument |
| MODAL_MEDIA_LIFECYCLE | Modal-Medien-Lebenszyklus-Verwaltung |
| CONTAINER_VIEW_PERFORMANCE | Container-View-Performance-Optimierung |
| BROWSER_CONNECTION_SATURATION | Browser-Verbindungssättigung bei Suchergebnis-Verlust |

## Videoverarbeitung

| Dokument | Inhalt |
|-------------|------|
| VIDEO_STREAMING_ARCHITECTURE | Video-Streaming-Architektur |
| VIDEO_PERFORMANCE_OPTIMIZATION_HISTORY | Video-Performance-Optimierungsverlauf |
| VIDEO_METADATA_V2_PLAN | Video-Metadaten v2-Plan (Entwurf) |

## Datei- und Archivverarbeitung

| Dokument | Inhalt |
|-------------|------|
| NESTED_ZIP_HANDLING | Verschachtelte ZIP-Verarbeitung Design und Probleme |
| ZIP_SCAN_PERFORMANCE | ZIP/7z-Scan-Performance-Optimierung |
| ENCODING_FALLBACK | Archivdateinamen-Encoding-Fallback |
| SD_NAI_PROMPT_SYNTAX_SPEC | SD/NAI Prompt-Syntaxspezifikation |

## Cross-Platform und Infrastruktur

| Dokument | Inhalt |
|-------------|------|
| CROSS_PLATFORM_ISSUES | Cross-Platform-Unterschiede-Leitfaden |
| DRAG_TO_SHARE_CROSS_PLATFORM | Drag & Drop Cross-Platform-Unterstützung |
| ASYNC_EVENT_LOOP_BLOCKING_FIX | asyncio-Ereignisschleife-Blockierungskorrektur |
| MODULE_SAFETY | Modulsicheres Lade-Design |
| DOCKER_SETUP | Docker-Umgebungsaufbau-Leitfaden |
| TAURI_DESKTOP_APP | Tauri-Desktop-App-Entwicklungsleitfaden |

## Migration

| Dokument | Inhalt |
|-------------|------|
| QUART_MIGRATION_DEVLOG | Flask → Quart (ASGI) Migrations-Technisches Dokument |
| CHATLOG_ENHANCED_SPEC | Chat-Log-Erweiterungs-Spezifikation |

## Tests und Qualitätssicherung

| Dokument | Inhalt |
|-------------|------|
| FUZZ_BURN_IN_TEST | Fuzz-/Burn-in-Test-Leitfaden |
| QA_HANDOFF | Qualitätsprüfungs-Übergabedokument |
| yu-ai-manager-qa-agent-prompt | QA-Agent-System-Prompt |
| ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE | Unfall-Hotspots und gemeinsamer Layer-Geschwindigkeitsleitfaden |
| BUG_VIDEO_AI_ANALYZED_FILTER | Bug-Aufzeichnung: Video + KI-Analyse-Filter |

## Release und Übersetzung

| Dokument | Inhalt |
|-------------|------|
| RELEASE_PROCEDURE | Release-Verfahren |
| TRANSLATION_STYLE_GUIDE | Japanisch-Englisch-Übersetzungs-Stilguide |
