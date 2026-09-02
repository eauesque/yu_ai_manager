# Documentation Hub

Bitte verwenden Sie diese Datei als "Dokumentations-Einstiegspunkt (kanonischer Hub)".

**Zuletzt aktualisiert**: 2026-05-13

## Important

- Project README: [`../../README.ja.md`](../../README.ja.md)
- Changelog: [`../../CHANGELOG.ja.md`](../../CHANGELOG.ja.md)
- Master TODO (single source of truth): [`../../TODO.md`](../../TODO.md)

## Entwicklungsrichtlinien

Die Entwicklungsrichtlinien befinden sich als einzelne Dateien in `development/development_docs/`.

- **[TODO Rules](TODO_RULES.md)** — TODO-Schreib-Regeln (P0/P1/P2/P3 + Kategorie erforderlich)

### Wichtigste Dokumente (`development/development_docs/`)

| Dokument | Inhalt |
|---|---|
| [CODE_SIZE_GUIDELINES](development/development_docs/CODE_SIZE_GUIDELINES.md) | Ab 300 Zeilen überdenken, ab 500 Zeilen Aufspaltung erforderlich |
| [MODULE_ORGANIZATION_GUIDELINES](development/development_docs/MODULE_ORGANIZATION_GUIDELINES.md) | Feature-Unit-Verzeichnis, 100-250 Zeilen sind ideal |
| [MODULE_SAFETY](development/development_docs/MODULE_SAFETY.md) | Dreischicht-Verteidigungsmodell (statisch/Parse/Runtime-Validierung) |
| [ERROR_HANDLING](development/development_docs/ERROR_HANDLING.md) | Einheitliche `api_error()`, `{ok, error, code, detail, hint}` |
| [API_RESPONSE_GUIDELINES](development/development_docs/API_RESPONSE_GUIDELINES.md) | `api_success()` / `api_error()` / `api_result()` |
| [ENTRYPOINT_MAP](development/development_docs/ENTRYPOINT_MAP.md) | Vollständige Einstiegspunkt-Liste aller Module |
| [ACCIDENT_POINTS](development/development_docs/ACCIDENT_POINTS_AND_COMMON_LAYER_SPEED_GUIDE.md) | Maßnahmen zur Vermeidung von 6 Unfallpunkten |
| [UI_BUTTON_PRIORITY_GUIDELINES](development/development_docs/UI_BUTTON_PRIORITY_GUIDELINES.md) | Tier A/B/C Buttondesign |
| [UI_STATE_SPEC](development/development_docs/UI_STATE_SPEC.md) | Explorer/Library-Hybridmuster |
| [DOCUMENT_LIFECYCLE](development/development_docs/DOCUMENT_LIFECYCLE.md) | Dokumentplatzierungsregeln |
| [FUZZ_BURN_IN_TEST](development/development_docs/FUZZ_BURN_IN_TEST.md) | API + UI Fuzz/Burn-in-Test |

### Weitere Entwicklungsdokumente

| Dokument | Inhalt |
|---|---|
| [ai-driven-development-principles](development/development_docs/ai-driven-development-principles.md) | Designprinzipien der KI-gesteuerten Entwicklung |
| [BATCH_API_STANDARD](development/development_docs/BATCH_API_STANDARD.md) | Batch-Operations-Konvention |
| [EXTENSION_HOOKS_SPEC](development/development_docs/EXTENSION_HOOKS_SPEC.md) | Erweiterungs-Hook-Lebenszyklen |
| [REUSABLE_UI_WIDGETS](development/development_docs/REUSABLE_UI_WIDGETS.md) | Liste wiederverwendbarer UI-Widgets |
| [SD_NAI_PROMPT_SYNTAX_SPEC](development/development_docs/SD_NAI_PROMPT_SYNTAX_SPEC.md) | SD/NAI-Prompt-Syntax-Spezifikation |
| [ENCODING_FALLBACK](development/development_docs/ENCODING_FALLBACK.md) | Archivdateinamen-Kodierung |
| [VISION_API_IMAGE_FORMATS](development/development_docs/VISION_API_IMAGE_FORMATS.md) | Vision API Bildformat-Kompatibilitätstabelle |
| [QA_HANDOFF](development/development_docs/QA_HANDOFF.md) | QA-Runden-Ergebnisse · Verbleibende Aufgaben |

### Entwicklungsprotokolle · Spezifikationen

| Dokument | Inhalt |
|---|---|
| [HAILO_SEMANTIC_SEARCH_DEVLOG](development/development_docs/HAILO_SEMANTIC_SEARCH_DEVLOG.md) | Hailo-10H CLIP Entwicklungsprotokoll |
| [CLIP_ONNX_DEVLOG](development/development_docs/CLIP_ONNX_DEVLOG.md) | CLIP ONNX Multi-Backend-Entwicklungsprotokoll |
| [HAILO_DEVICE_CONTROL](development/development_docs/HAILO_DEVICE_CONTROL.md) | Hailo-Gerätekontrolle |
| [CHATLOG_ENHANCED_SPEC](development/development_docs/CHATLOG_ENHANCED_SPEC.md) | Chat-Log-Erweiterte-Spezifikation |
| [TAURI_DESKTOP_APP](development/development_docs/TAURI_DESKTOP_APP.md) | Tauri-Desktop-Integration |
| [EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR](development/development_docs/EXTENSION_SPEC_FREEZE_PULLBACK_GENERATOR_v0_2.md) | Freeze & Pull-back-Erweiterungs-Spezifikation |
| [VIDEO_METADATA_V2_PLAN](development/development_docs/VIDEO_METADATA_V2_PLAN.md) | Videomedadaten-v2-Plan (Entwurf) |

## Import Paths

Alle Importe verwenden direkte Module-Pfade. Der Aliasmechanismus wurde entfernt.

**Wichtigste Pfade-Beispiele:**
- `core.services_core.db_api` — DB-Zugriff (alt `core.db`)
- `core.configuration.api` — Konfigurationsverwaltung (alt `core.config`)
- `core.extensions_core.runtime` — Erweiterungs-Runtime (alt `core.extensions`)
- Neue Funktionen werden direkt zum `core/<feature>_core/` Verzeichnis hinzugefügt

## Fehlerbehebung & Betrieb

- Debug-Playbook: [`troubleshooting/debug-playbook.md`](troubleshooting/debug-playbook.md)
- Häufige Fehler (veraltet): [`troubleshooting/common-errors.md`](troubleshooting/common-errors.md)
- CJK / 2-Byte-Zeichenkodierungs-Fallstricke: [`troubleshooting/cjk-2byte-encoding-pitfalls.md`](troubleshooting/cjk-2byte-encoding-pitfalls.md)
- Escaped-Bracket-Parsefehler: [`troubleshooting/escaped-brackets-parse-error.md`](troubleshooting/escaped-brackets-parse-error.md)

## Features

| Dokument | Status | Inhalt |
|---|---|---|
| [MCP-Integrations-Anleitung](features/mcp-integration-guide.md) | Aktuell | yu_ai_manager vom LLM aus steuern |
| [NovelAI V4](features/novelai-v4.md) | Aktuell | NovelAI-V4-Prompt-Format · zeichenspezifische negative Unterstützung |
| [Hailo-Semantic-Suche](features/hailo-semantic-search.md) | Implementiert → ONNX-Migration | Hailo-10H CLIP Implementierungsanweisungen |
| [Danbooru-Tag-Auto-Generierung](features/danbooru-tag-gen-spec.md) | Implementiert (v2.77.0) | WD-Tagger + VLM zweistufig |
| [Text/Chat-Log-Verwaltung](features/text-chatlog-management-spec.md) | Aktuell | Chatlog-Import · FTS-Suche |
| [QR-Protokoll v1](features/qr-protocol-v1.md) | Aktuell | QR-Code für LAN-Freigabe |
| [Regex-Such-Benchmark](features/regex-search-benchmark.md) | Aktuell | Regex-Leistung |
| [Browser-Kompatibilität](features/browser-compatibility.md) | Aktuell | Unterstützte Browser-Liste |

## API Reference

- [API-Übersicht (Authentifizierung · CSRF · Ratenlimit)](api/README.md)
- [Suchapi](api/search.md)
- [Dateien-API](api/files.md)
- [Scan-API](api/scan.md)
- [SSE-Ereignisse](api/events.md)
- [Design-CSS-Variablen](api/theming.md)

## Benutzerdefinierte Benutzeroberfläche / Plugin-Entwicklung

- [Custom-UI-Anleitung](custom-ui/README.md) — Benutzerdefinierte UI-Entwicklung (Schnelleinstieg, Design, Vorlagen, Erweitert)
- [Plugin-Entwicklungs-Anleitung](plugin-development/getting-started.md) — Erweiterungs-Entwicklungs-Einführung
- [Manifest-Referenz](plugin-development/manifest-reference.md) — extension.json-Spezifikation

## Installation

- FFmpeg: [`installation/ffmpeg.md`](installation/ffmpeg.md)
- Docker: [`development/development_docs/DOCKER_SETUP.md`](development/development_docs/DOCKER_SETUP.md)

## Historische Dokumentation

Dies sind Implementierungs-Notizen/Hotfix-Aufzeichnungen aus der Vergangenheit (in `archive/docs_history/` platziert).

- `DEBUG_INSTRUCTIONS_v2.5.4.md` — Debug-Anweisungen aus v2.5.4-Zeitalter
- `DARK_MODE_TAGS_IMPROVEMENT.md` — Dunkelmodusmarkierungen-Verbesserungsvorschlag (bereits implementiert)
- `EXTENSION_DRAFT.md` — Extension-System-Anfangsentwurf (Nachfolger in plugin-development/)
