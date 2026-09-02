# Erweiterungen (Extensions)

YU AI Manager kann mit dem Extension-System um Funktionen erweitert werden.
Derzeit sind 43 integrierte Extensions in 6 Kategorien enthalten.

## Integrierte Extensions-Liste

### Metadaten-Extraktion (metadata)

| Extension | Beschreibung |
|-----------|------|
| builtin-a1111 | Automatic1111 / SD WebUI PNG/WebP/WebM-Metadaten-Extraktion |
| builtin-novelai-v3 | NovelAI V3 und frühere Metadaten-Extraktion |
| builtin-novelai-v4 | NovelAI V4-Metadaten-Extraktion (Character Prompts, Vibe Transfer) |
| builtin-comfyui | ComfyUI-Workflow-JSON-Analyse |
| builtin-annotations | Datei-Annotation Speichern/Suchen/Massenoperationen |
| builtin-ratings | Sternbewertungs-System (1–5 Sterne) |
| builtin-tag-dictionary | Danbooru-Tag-Wörterbuch Suchen/Import/Aufteilen |

### Bridge-Verbindung (bridge)

| Extension | Beschreibung |
|-----------|------|
| builtin-sd-webui-bridge | SD WebUI / Forge-Integration (Bildgenerierung, Modellverwaltung) |
| builtin-nai-bridge | NovelAI-API-Integration (Bildgenerierung) |
| builtin-comfyui-bridge | ComfyUI-Integration (Workflow-Ausführung) |

### Prompts (prompt)

| Extension | Beschreibung |
|-----------|------|
| builtin-prompt-library | Prompt-Bibliothek und -Organisation |
| builtin-prompt-syntax | Prompt-Syntaxhervorhebung und Fehlererkennung (NAI/SD/DP) |
| builtin-prompt-simulator | Dynamic Prompts Simulator, Gewichtsberechnung, Konvertierung |
| builtin-sd-nai-convert | SD ↔ NovelAI-Prompt-Wechselkonvertierung |

### KI (ai)

| Extension | Beschreibung |
|-----------|------|
| builtin-analysis | KI-Bildanalyse (Claude, OpenAI, Ollama, Hailo VLM) |
| builtin-wd-tagger | WD-Tagger automatisches Tagging (ONNX + VLM Engine) |
| builtin-ocr | VLM OCR — Textextraktion, strukturierte Analyse, Übersetzung |
| builtin-clip-search | CLIP semantische Bildsuch-Engine |
| builtin-clip-onnx | CLIP ONNX Runtime Encoder-Backend |
| builtin-clip-coreml | CLIP Core ML Encoder (Apple Neural Engine) |
| builtin-hailo-semantic-search | Hailo-10H semantische Suche |
| builtin-hailo-yolo-detect | Hailo-10H YOLO-Objekterkennung |
| builtin-hailo-genai | Hailo-10H GenAI (LLM/VLM/S2T) |
| builtin-speech-to-text | Sprachtranskription (Hailo NPU / CUDA / ROCm / CPU) |
| builtin-audio-analysis | Audioanalyse (Whisper lokal / OpenAI API) |
| builtin-video-analysis | Video-KI-Analyse (Multi-Keyframe + Gemini) |
| builtin-inference | ONNX Runtime Provider-Erkennung, GPU-Beschleunigung |

### Bibliothek (library)

| Extension | Beschreibung |
|-----------|------|
| builtin-favorites-manager | Favoriten- und Sammlungsverwaltung |
| builtin-freeze-pullback | Freeze & Pull-back Videogenerierung (Ken Burns-Effekt) |
| builtin-download | Ausgewählte Bilder als ZIP-Batch-Download |
| builtin-chatlog | Chat-Log-Importer und -Viewer (Claude / ChatGPT) |
| builtin-md-viewer | Markdown-Dateiviewer (FTS5-Volltextsuche) |
| builtin-cross-search | Cross-Suche (MD, Chat-Logs, Prompts, Text) |
| builtin-lan-share | LAN-Sammlungsfreigabe (zeitlich begrenzte Token-Authentifizierung) |
| builtin-stats | Statistik-Insights (Timeline, Meilensteine) |
| builtin-trophy | Trophäen- und Leistungssystem |
| builtin-export | Export-Hooks (Record-Transformation bei CSV-Ausgabe) |

### System (system)

| Extension | Beschreibung |
|-----------|------|
| builtin-auto-scan-watcher | Automatische Dateierkennung und inkrementelle Aktualisierung |
| builtin-mcp-client | Externe MCP-Server-Verbindungsverwaltung |
| builtin-backup | DB-Backup, Restore, Scheduler |
| builtin-sns-share | SNS-Teilen (Bluesky, X/Twitter) |
| builtin-webhook | Webhook-Dispatcher (ereignisgesteuerte HTTP-Lieferung) |
| builtin-debug-check | Debug-Diagnose-CLI |
| builtin-github-integration | GitHub-Issue-Überwachung, Triage, PR/Discussion/Release-Tracking |

## Extension-Verwaltung

Unter Settings > Extensions-Tab folgende Operationen möglich:

- **Aktivieren/Deaktivieren**: Toggle-Schalter für sofortigen Wechsel
- **Neu installieren**: Git-Repository-URL eingeben und installieren
- **Marketplace**: Öffentliche Extensions suchen und mit einem Klick installieren
- **Aktualisieren**: Git-basierte Extensions auf die neueste Version aktualisieren
- **Deinstallieren**: Drittanbieter-Extensions entfernen

### Verwaltung per API

```bash
# Extension-Liste
curl -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions

# Aktivieren/Deaktivieren
curl -X POST -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions/builtin_wd_tagger/toggle

# Aus Git installieren
curl -X POST -H "Authorization: Bearer sk_xxx" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://github.com/user/my-extension.git"}' \
     http://localhost:5000/api/extensions/install
```

## Extension-Sandbox

Drittanbieter-Extensions werden durch Sandbox geschützt.

### Vertrauensstufen

| Stufe | Ziel | Einschränkungen |
|--------|------|------|
| L0 (TRUSTED) | `builtin-*` | Keine Einschränkungen |
| L2 (UNTRUSTED) | Andere | DB/FS/Netzwerk eingeschränkt |

### Sandbox 4 Phasen

1. **Capability Token**: HMAC-SHA256-signierter Token für Berechtigungsverwaltung. 24-Stunden-Ablauf
2. **SandboxedDB / SandboxedFS**: Extensions mit nur `db:read` erlauben nur SELECT. Dateizugriff pfadbasiert kontrolliert
3. **SandboxedHTTPClient / ImportGuard**: SSRF-Verhinderung, Runtime-Import-Überwachung, SHA-256-Manipulationserkennung
4. **Prozess-Isolation (Linux)**: L2-Extensions in separaten Prozessen ausführen. Unix-Socket JSON-RPC 2.0 IPC

### OS-Level-Isolation (optional)

- **Linux**: AppArmor-Profil automatisch generiert
- **macOS**: sandbox-exec (experimentell)
- **Windows**: Restricted Token + Job Object

> **Tipp**: Details zur Extension-Entwicklung finden Sie im Abschnitt "Extension-Entwicklung".

## Verzeichnisstruktur

```
extensions/builtin_<name>/
  extension.json            # Manifest (Name, Version, Berechtigungen usw.)
  <name>_ext.py             # Einstiegspunkt (publiziert get_blueprint())
  templates/<name>/          # Jinja2-Templates
  core_impl/                 # Geschäftslogik (optional)
```

### Pflichtfelder in extension.json

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entrypoint": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library"
}
```

Kategorien: `metadata`, `bridge`, `prompt`, `ai`, `library`, `system`

## Extension Module API v2 (ES-Module-Unterstützung)

Ab v4.29.0 können Extensions mit `<script type="module">` und Import Maps im ES-Module-Muster geschrieben werden.

### Aktivierung

In `extension.json` `"script_type": "module"` hinzufügen.

### Verwendung

```html
<script nonce="{{ csp_nonce }}" type="module">
import { showToast, sseSubscribe, tr, apiFetch, escapeHtml } from 'yu-api';

// Toast-Benachrichtigung
showToast('Gespeichert');

// SSE-Ereignis abonnieren
sseSubscribe('scan.progress', (data) => {
  console.log('Fortschritt:', data);
});

// i18n-Übersetzung
const label = tr('my_ext.title', 'My Extension');

// API-Aufruf (CSRF-Header automatisch hinzugefügt)
const res = await apiFetch('/ext/my-extension/api/data');
const json = await res.json();
</script>
```

### Öffentliche API-Liste

| Funktion | Beschreibung |
|---|---|
| `showToast(message, isError?)` | Toast-Benachrichtigung anzeigen |
| `sseSubscribe(eventType, handler)` | SSE-Ereignis abonnieren |
| `sseUnsubscribe(eventType, handler)` | SSE-Ereignis-Abonnement beenden |
| `tr(path, a?, b?)` | i18n-Übersetzungsschlüssel auflösen |
| `apiFetch(path, opts?)` | CSRF-erweiterte fetch-Funktion |
| `apiUrl(path)` | API-URL aufbauen |
| `escapeHtml(text)` | HTML-Sonderzeichen escapen |

### Legacy-Kompatibilität

`"script_type": "classic"` (Standard)-Extensions können weiterhin globale Funktionen wie `window.showToast()` verwenden. Bestehende Extensions müssen nicht umgeschrieben werden.

## Entwicklungsdokumentation

Extension-Entwicklung und interne Designentscheidungen sind über den [MD Viewer](/ext/md-viewer/) zugänglich.
