# Estensione Speech-to-Text

**Status**: Implementato (v3.28.0)
**Target**: `extensions/builtin_speech_to_text/`
**Scopo**: Trascrivere file video e audio con rilevamento backend automatico

---

## Panoramica

Questa Estensione estrae l'audio da file video e audio e li trascrive utilizzando modelli Whisper.
Seleziona automaticamente il backend ottimale in base all'hardware disponibile e viene eseguito su GPU o CPU anche senza un Hailo NPU.

---

## Priorità Backend

| Priorità | Backend | Libreria | Hardware Target |
|--------|-------------|-----------|-----------------|
| P100 | `hailo` | `hailo_platform.genai` | Hailo-10H NPU |
| P70 | `torch-whisper-rocm` | `torch` (ROCm) + `transformers` | AMD GPU (ROCm/HIP) |
| P50 | `faster-whisper-cuda` | `faster-whisper` (CTranslate2) | NVIDIA GPU (CUDA) |
| P40 | `torch-whisper-cuda` | `torch` (CUDA) + `transformers` | NVIDIA GPU (CUDA) |
| P20 | `torch-whisper-cpu` | `torch` + `transformers` | CPU |
| P50 | `faster-whisper-cpu` | `faster-whisper` (CTranslate2) | CPU |
| P10 | `whisper-cpp` | `pywhispercpp` | CPU (più leggero) |

In modalità `auto`, viene selezionato il backend con la priorità più alta tra quelli che restituiscono `is_available() == True`.

---

## Configurazione Specifica dell'Ambiente

### Requisiti Comuni

- Python 3.11+
- ffmpeg (richiesto per estrarre l'audio dai video)

### Hailo-10H NPU (Raspberry Pi AI HAT 2)

Nessun pacchetto aggiuntivo è richiesto (`hailo_platform` deve essere già installato).
Il modello (`whisper-base` ecc.) deve essere stato scaricato tramite l'Estensione GenAI.

```bash
# Scarica il modello dall'UI dell'Estensione GenAI se non già presente
```

### NVIDIA GPU (CUDA)

```bash
# Consigliato: faster-whisper (leggero, non richiede PyTorch)
pip install faster-whisper

# La GPU viene utilizzata automaticamente quando CUDA viene rilevato (float16)
# Ricade automaticamente su CPU quando CUDA è assente (int8)
```

### AMD GPU (ROCm)

```bash
# 1. Installa PyTorch edizione ROCm
#    Ufficiale: https://pytorch.org/get-started/locally/
#    Esempio (ROCm 6.x):
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.2

# 2. Installa HuggingFace transformers
pip install transformers

# 3. Imposta backend in configurazione (auto-rilevato in modalità "auto")
#    Nelle impostazioni dell'Estensione: backend: "rocm" o "auto"
```

**Meccanismo di rilevamento ROCm**: PyTorch espone ROCm come CUDA tramite HIP.
Il sistema identifica ROCm quando `torch.version.hip` non è `None`.

**Requisiti di memoria** (ROCm):

| Modello | Stima VRAM |
|--------|----------|
| tiny | ~150 MB |
| base | ~300 MB |
| small | ~500 MB |
| medium | ~1.5 GB |

### Solo CPU

```bash
# Opzione 1: faster-whisper (consigliato, veloce con quantizzazione int8)
pip install faster-whisper

# Opzione 2: whisper.cpp (più leggero, non richiede PyTorch)
pip install pywhispercpp

# Opzione 3: torch + transformers (scopo generale ma pesante)
pip install torch transformers
```

**Stime prestazioni CPU** (modello base, 1 minuto di audio):

| Backend | RPi 5 | x86 (4 core) |
|---|---|---|
| faster-whisper (int8) | ~30 sec | ~5 sec |
| whisper.cpp | ~40 sec | ~8 sec |
| torch (float32) | ~90 sec | ~15 sec |

---

## Configurazione

Configura tramite la pagina impostazioni dell'Estensione (`/ext/speech-to-text/`) o config.json:

| Elemento | Scelte | Predefinito | Descrizione |
|------|--------|-----------|------|
| `backend` | auto / hailo / cuda / rocm / cpu | auto | Backend di inferenza |
| `model_size` | tiny / base / small / medium | base | Dimensione modello Whisper |
| `default_language` | Codice BCP-47 (ja, en, ecc.) | ja | Lingua predefinita |

---

## Endpoint API

Tutti gli endpoint sono sotto il prefisso `/ext/speech-to-text`.

### POST `/api/s2t/transcribe`

Trascrive l'audio WAV caricato.

- **Content-Type**: `multipart/form-data`
- **Parametri**: `audio` (file), `language` (opzionale)
- **Risposta**: `{ status, text, segments, language, sample_rate, backend }`

### POST `/api/s2t/transcribe-video`

Trascrive un file video/audio registrato nel DB. I risultati vengono salvati come annotazioni.

- **Body**: `{ file_id: int, language?: string }`
- **Risposta**: `{ status, text, segments, language, backend }`
- **Annotazione**: `source="s2t"`, chiavi: `transcript`, `transcript_segments`, `transcript_backend`

### POST `/api/s2t/batch-transcribe`

Trascrizione batch di più file (viene eseguita in background).

Scegli **uno** dei tre metodi di input (mutuamente esclusivi):

#### Metodo 1: Lista ID File (Legacy)

```json
{
  "file_ids": [123, 456, 789],
  "language": "ja"
}
```

#### Metodo 2: Directory

Rileva automaticamente i file video/audio nella directory specificata ed elabora solo quelli registrati nel DB.

```json
{
  "directory": "/path/to/videos/",
  "recursive": true,
  "language": "en"
}
```

- `recursive` (predefinito: `true`): Ricerca ricorsivamente le sottodirectory
- Estensioni target: `.webm`, `.mp4`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv`, `.mp3`, `.wav`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.flac`

#### Metodo 3: Lista Testo/CSV

Specifica un file di testo o CSV che elenca i percorsi dei file.

```json
{
  "list_file": "/path/to/targets.txt",
  "language": "ja"
}
```

**Formato file di testo** (`.txt` ecc.):
```
# Linee di commento (le linee che iniziano con # vengono ignorate)
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```

**Formato CSV** (`.csv`):
```csv
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```
La prima colonna viene utilizzata come percorso del file. Le linee che iniziano con `#` vengono saltate.

#### Opzioni Comuni

| Parametro | Tipo | Predefinito | Descrizione |
|-----------|---|-----------|------|
| `language` | string | Valore config (tipicamente `ja`) | Codice lingua (vedi sotto) |
| `recursive` | bool | `true` | Metodo directory solo: ricerca sottodirectory ricorsiva |

#### Limiti e Vincoli

- Massimo file target: **500**
- Solo i file registrati nel DB (tabella `files`) vengono elaborati
- I file eliminati (`is_deleted=1`) vengono esclusi

#### Esempio Risposta

```json
{
  "status": "started",
  "total": 15,
  "mode": "directory",
  "directory": "/mnt/videos/",
  "recursive": true,
  "files_found": 23,
  "matched_in_db": 15
}
```

- **Eventi SSE**: `s2t.batch_start`, `s2t.batch_progress`, `s2t.batch_complete`

### GET `/api/s2t/transcript/<file_id>`

Recupera i risultati di trascrizione salvati. Sia `source="s2t"` che `source="hailo:s2t"` vengono controllati per compatibilità all'indietro.

### GET `/api/s2t/status`

Restituisce lo stato del backend e un elenco di backend disponibili.

---

## Strumenti MCP

| Nome Strumento | Descrizione |
|---------|------|
| `s2t_status` | Ottieni lo stato del backend |
| `s2t_transcribe_video` | Trascrivi un singolo file video |
| `s2t_batch_transcribe` | Avvia trascrizione batch (file_ids / directory / list_file) |
| `s2t_get_transcript` | Recupera la trascrizione salvata |

### Parametri `s2t_batch_transcribe`

| Parametro | Tipo | Richiesto | Descrizione |
|-----------|---|------|------|
| `file_ids` | list[int] | *1 | Lista ID file (max 500) |
| `directory` | string | *1 | Percorso directory (auto-rileva video/audio) |
| `list_file` | string | *1 | Percorso file testo/CSV |
| `recursive` | bool | | Solo metodo directory. Ricerca sottodirectory ricorsiva (predefinito true) |
| `language` | string | | Codice lingua. Vuoto = predefinito config |
| `expected_count` | int | | Per il rilevamento del troncamento file_ids |

*1: Specifica esattamente uno tra `file_ids`, `directory`, o `list_file` (mutuamente esclusivi)

---

## Struttura File

```
extensions/builtin_speech_to_text/
  extension.json                      # Manifest
  speech_to_text_ext.py               # Punto di ingresso (Blueprint)
  s2t_routes.py                       # Route API file singolo
  s2t_batch_routes.py                 # Route API batch
  core_impl/
    base.py                           # Classe base astratta S2TBackend
    backend_hailo.py                  # Hailo-10H NPU
    backend_faster_whisper.py         # faster-whisper (CUDA/CPU)
    backend_torch_whisper.py          # PyTorch transformers (ROCm/CUDA/CPU)
    backend_whisper_cpp.py            # whisper.cpp (CPU)
    backend_registry.py               # Auto-rilevamento + gestione singleton
  templates/speech_to_text/
    s2t.html                          # Pagina UI
mcp_server/
  s2t_tools.py                        # Definizioni strumenti MCP
```

---

## Codici Lingua Supportati

Codici lingua principali (BCP-47) supportati da Whisper:

| Codice | Lingua | Codice | Lingua |
|--------|------|--------|------|
| `ja` | Giapponese | `en` | Inglese |
| `zh` | Cinese | `ko` | Coreano |
| `de` | Tedesco | `fr` | Francese |
| `es` | Spagnolo | `it` | Italiano |
| `pt` | Portoghese | `ru` | Russo |
| `ar` | Arabo | `hi` | Hindi |
| `th` | Tailandese | `vi` | Vietnamita |
| `nl` | Olandese | `tr` | Turco |
| `pl` | Polacco | `uk` | Ucraino |
| `id` | Indonesiano | `sv` | Svedese |

Anche altri linguaggi supportati da Whisper possono essere specificati. Una stringa vuota attiva il rilevamento automatico.
La lingua predefinita può essere cambiata tramite l'impostazione dell'Estensione `default_language` (valore iniziale: `ja`).

---

## Limitazioni Note

- **Ritardo primo caricamento**: transformers / faster-whisper scaricano i modelli da HuggingFace Hub (base: ~150MB). La prima esecuzione potrebbe richiedere diversi minuti
- **Modelli HEF Hailo**: Devono essere scaricati tramite l'Estensione GenAI. L'Estensione S2T stessa non ha funzionalità di download
- **Memoria**: Il modello medium potrebbe causare errori out-of-memory su RPi 5 (8GB). Il modello base è consigliato
- **Concorrenza**: I backend vengono gestiti come singleton. Le richieste che arrivano durante l'elaborazione batch condividono la stessa istanza
- **Formato input**: WAV (PCM s16le, mono, 16kHz) si assume. I file video vengono convertiti automaticamente tramite ffmpeg
- **Input batch**: I metodi directory / list_file elaborano solo file registrati nel DB. I file non scansionati devono prima essere registrati tramite `start_scan`

---

## Trascrizione Streaming in Tempo Reale

Trascrivi l'audio da radio Internet, stream RTSP e file video in tempo reale e visualizza sottotitoli nella WebUI.

### Due Modalità

- **Modalità chunk** (predefinita): Divide l'audio in chunk utilizzando il rilevamento del silenzio basato su RMS. Compatibile con tutti i backend (Hailo/CUDA/CPU). I risultati vengono visualizzati dopo che ogni enunciato termina.
- **Modalità live**: Esegue la trascrizione incrementale utilizzando Silero VAD di faster-whisper. Visualizza i risultati provvisori mentre il discorso è ancora in corso. Richiede un backend ONNX/faster-whisper.

### Fonti di Input Supportate

- Stream HTTP/HTTPS (radio Internet, ecc.)
- Fotocamere RTSP
- Stream RTMP

### Endpoint API

| Endpoint | Metodo | Funzione |
|---|---|---|
| `/api/s2t/stream/start` | POST | Avvia streaming (`source_url`, `language`, `mode`) |
| `/api/s2t/stream/stop` | POST | Ferma streaming |
| `/api/s2t/stream/status` | GET | Ottieni stato |
| `/api/s2t/stream/transcript` | GET | Ottieni trascrizione completa |
| `/api/s2t/stream/export/txt` | GET | Esporta come testo |
| `/api/s2t/stream/export/srt` | GET | Esporta come sottotitoli SRT |

### Eventi SSE

| Evento | Descrizione |
|---|---|
| `s2t.stream_chunk` | Testo finalizzato |
| `s2t.stream_interim` | Testo provvisorio (solo modalità Live) |
| `s2t.stream_complete` | Streaming completo |

### Strumenti MCP

| Strumento | Descrizione |
|---|---|
| `s2t_stream_start(source_url, language)` | Avvia streaming |
| `s2t_stream_stop()` | Ferma streaming |
| `s2t_stream_status()` | Ottieni stato |
| `s2t_stream_transcript()` | Ottieni trascrizione completa |

### Configurazione Streaming

Elementi configurabili in `extension.json`:

| Elemento | Descrizione | Predefinito |
|---|---|---|
| `stream_chunk_min_sec` | Lunghezza minima chunk in modalità Chunk (secondi) | — |
| `stream_chunk_max_sec` | Lunghezza massima chunk in modalità Chunk (secondi) | — |
| `stream_silence_threshold` | Soglia RMS per il rilevamento del silenzio | — |
| `stream_silence_ms` | Durata del silenzio per il rilevamento (millisecondi) | — |
| `live_interval_sec` | Intervallo di trascrizione in modalità Live (secondi) | — |
