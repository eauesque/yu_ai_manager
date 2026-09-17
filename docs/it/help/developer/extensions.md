# Estensioni

YU AI Manager supporta l'aggiunta di funzionalità tramite il sistema Extension. Attualmente sono installate 43 Extension built-in, classificate in 6 categorie.

## Elenco Extension Built-in

### Estrazione Metadati (metadata)

| Extension | Descrizione |
|-----------|-------------|
| builtin-a1111 | Estrazione metadati PNG/WebP/WebM di Automatic1111 / SD WebUI |
| builtin-novelai-v3 | Estrazione metadati NovelAI versioni precedenti a V3 |
| builtin-novelai-v4 | Estrazione metadati NovelAI V4 (supporto Character Prompts, Vibe Transfer) |
| builtin-comfyui | Parsing JSON workflow ComfyUI |
| builtin-annotations | Salvataggio, ricerca e operazioni batch annotazioni file |
| builtin-ratings | Sistema di valutazione a stelle (1~5 stelle) |
| builtin-tag-dictionary | Ricerca, importazione e suddivisione dizionario tag Danbooru |

### Bridge (bridge)

| Extension | Descrizione |
|-----------|-------------|
| builtin-sd-webui-bridge | Integrazione SD WebUI / Forge (generazione immagini, gestione modelli) |
| builtin-nai-bridge | Integrazione API NovelAI (generazione immagini) |
| builtin-comfyui-bridge | Integrazione ComfyUI (esecuzione workflow) |

### Prompt (prompt)

| Extension | Descrizione |
|-----------|-------------|
| builtin-prompt-library | Libreria e organizzazione prompt |
| builtin-prompt-syntax | Highlight sintassi prompt e rilevamento errori (supporto NAI/SD/DP) |
| builtin-prompt-simulator | Simulatore Dynamic Prompts, calcolo pesi, conversione |
| builtin-sd-nai-convert | Conversione bidirezionale prompt SD ↔ NovelAI |

### AI (ai)

| Extension | Descrizione |
|-----------|-------------|
| builtin-analysis | Analisi immagini AI (Claude, OpenAI, Ollama, Hailo VLM) |
| builtin-wd-tagger | Tagging automatico WD-Tagger (ONNX + motore VLM) |
| builtin-ocr | VLM OCR — estrazione testo, analisi strutturata, traduzione |
| builtin-clip-search | Motore di ricerca semantica immagini CLIP |
| builtin-clip-onnx | Backend encoder CLIP ONNX Runtime |
| builtin-clip-coreml | Encoder CLIP Core ML (Apple Neural Engine) |
| builtin-hailo-semantic-search | Ricerca semantica Hailo-10H |
| builtin-hailo-yolo-detect | Rilevamento oggetti YOLO Hailo-10H |
| builtin-hailo-genai | GenAI Hailo-10H (LLM/VLM/S2T) |
| builtin-speech-to-text | Trascrizione vocale (Hailo NPU / CUDA / ROCm / CPU) |
| builtin-audio-analysis | Analisi audio (Whisper locale / API OpenAI) |
| builtin-video-analysis | Analisi AI video (multi-keyframe + Gemini) |
| builtin-inference | Rilevamento provider ONNX Runtime, accelerazione GPU |

### Libreria (library)

| Extension | Descrizione |
|-----------|-------------|
| builtin-favorites-manager | Gestione preferiti e collezioni |
| builtin-freeze-pullback | Generazione video Freeze & Pull-back (effetto Ken Burns) |
| builtin-download | Download ZIP batch delle immagini selezionate |
| builtin-chatlog | Importatore e visualizzatore chat log (Claude / ChatGPT) |
| builtin-md-viewer | Visualizzatore file Markdown (ricerca full-text FTS5) |
| builtin-cross-search | Ricerca cross (MD, chat log, prompt, testo) |
| builtin-lan-share | Condivisione collezioni LAN (autenticazione token a tempo) |
| builtin-stats | Statistiche (timeline, milestone) |
| builtin-trophy | Sistema trofei e obiettivi |
| builtin-export | Hook export (conversione record all'output CSV) |

### Sistema (system)

| Extension | Descrizione |
|-----------|-------------|
| builtin-auto-scan-watcher | Rilevamento automatico modifiche file e aggiornamento differenziale |
| builtin-mcp-client | Gestione connessioni server MCP esterni |
| builtin-backup | Backup DB, ripristino, scheduler |
| builtin-sns-share | Condivisione SNS (Bluesky, X/Twitter) |
| builtin-webhook | Dispatcher Webhook (distribuzione HTTP event-driven) |
| builtin-debug-check | CLI diagnostica debug |
| builtin-github-integration | Monitoraggio issue GitHub, triage, tracciamento PR/Discussion/Release |

## Gestione delle Extension

Dalla scheda Settings > Extensions sono disponibili le seguenti operazioni:

- **Abilitazione/disabilitazione**: Cambio immediato con interruttore
- **Nuova installazione**: Installazione specificando URL repository Git
- **Marketplace**: Ricerca e installazione in un clic delle Extension pubbliche
- **Aggiornamento**: Aggiornamento Extension Git-based all'ultima versione
- **Disinstallazione**: Rimozione Extension di terze parti

### Gestione tramite API

```bash
# Lista Extension
curl -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions

# Abilitazione/disabilitazione
curl -X POST -H "Authorization: Bearer sk_xxx" \
     http://localhost:5000/api/extensions/builtin_wd_tagger/toggle

# Installazione da Git
curl -X POST -H "Authorization: Bearer sk_xxx" \
     -H "Content-Type: application/json" \
     -d '{"url": "https://github.com/user/my-extension.git"}' \
     http://localhost:5000/api/extensions/install
```

## Extension Sandbox

Le Extension di terze parti sono protette da sandbox.

### Livelli di Trust

| Livello | Target | Restrizioni |
|---------|--------|-------------|
| L0 (TRUSTED) | `builtin-*` | Nessuna |
| L2 (UNTRUSTED) | Altre | Restrizioni DB/FS/rete |

### 4 Fasi della Sandbox

1. **Capability Token**: Gestione permessi con token firmati HMAC-SHA256. Scadenza 24 ore
2. **SandboxedDB / SandboxedFS**: Extension con solo `db:read` permettono solo SELECT. L'accesso ai file è controllato per percorso
3. **SandboxedHTTPClient / ImportGuard**: Prevenzione SSRF, monitoraggio import runtime, rilevamento manomissioni SHA-256
4. **Isolamento processo (Linux)**: Esecuzione Extension L2 in processo separato. IPC JSON-RPC 2.0 su Unix socket

### Isolamento a Livello OS (Opzionale)

- **Linux**: Generazione automatica profilo AppArmor
- **macOS**: sandbox-exec (sperimentale)
- **Windows**: Restricted Token + Job Object

> **Suggerimento**: Per i dettagli sullo sviluppo Extension consultare la sezione "Sviluppo Extension".

## Struttura Directory

```
extensions/builtin_<name>/
  extension.json            # Manifesto (nome, versione, permessi ecc.)
  <name>_ext.py             # Entry point (espone get_blueprint())
  templates/<name>/          # Template Jinja2
  core_impl/                 # Business logic (opzionale)
```

### Campi Obbligatori di extension.json

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entrypoint": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library"
}
```

Le categorie sono 6: `metadata`, `bridge`, `prompt`, `ai`, `library`, `system`.

## Extension Module API v2 (Supporto ES Module)

Dalla v4.29.0, le Extension possono essere scritte con il pattern ES Module usando `<script type="module">` e Import Maps.

### Abilitazione

Aggiungere `"script_type": "module"` a `extension.json`:

```json
{
  "name": "my-extension",
  "version": "1.0.0",
  "entry": "my_extension_ext.py",
  "has_blueprint": true,
  "category": "library",
  "script_type": "module"
}
```

### Utilizzo

Cambiare il `<script>` nel template in `<script type="module">` e importare da `yu-api`:

```html
<script nonce="{{ csp_nonce }}" type="module">
import { showToast, sseSubscribe, tr, apiFetch, escapeHtml } from 'yu-api';

// Notifica toast
showToast('Salvato');

// Sottoscrizione evento SSE
sseSubscribe('scan.progress', (data) => {
  console.log('Avanzamento:', data);
});

// Traduzione i18n
const label = tr('my_ext.title', 'My Extension');

// Chiamata API (aggiunta automatica header CSRF)
const res = await apiFetch('/ext/my-extension/api/data');
const json = await res.json();
</script>
```

### Elenco API Pubbliche

| Funzione | Descrizione |
|----------|-------------|
| `showToast(message, isError?)` | Visualizza notifica toast |
| `sseSubscribe(eventType, handler)` | Sottoscrivi evento SSE |
| `sseUnsubscribe(eventType, handler)` | Annulla sottoscrizione evento SSE |
| `tr(path, a?, b?)` | Risolve chiave traduzione i18n |
| `apiFetch(path, opts?)` | Wrapper fetch con CSRF |
| `apiUrl(path)` | Costruisce URL API |
| `escapeHtml(text)` | Escape caratteri speciali HTML |

## Documentazione di Sviluppo

Le conoscenze di sviluppo sullo sviluppo Extension e le decisioni di design interne, avvertenze note, debug tip ecc. sono consultabili tramite [MD Viewer](/ext/md-viewer/).
