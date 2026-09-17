# Sprache-zu-Text Extension

**Status**: Implementiert (v3.28.0)
**Ziel**: `extensions/builtin_speech_to_text/`
**Zweck**: Transkription von Video- und Audiodateien mit automatischer Backend-Erkennung

---

## Übersicht

Diese Erweiterung extrahiert Audio aus Video- und Audiodateien und transkribiert es mit Whisper-Modellen. Sie wählt automatisch das optimale Backend basierend auf verfügbarer Hardware aus und läuft auf GPU oder CPU auch ohne Hailo NPU.

---

## Backend-Priorität

| Priorität | Backend | Bibliothek | Ziel-Hardware |
|--------|-------------|-----------|-----------------|
| P100 | `hailo` | `hailo_platform.genai` | Hailo-10H NPU |
| P70 | `torch-whisper-rocm` | `torch` (ROCm) + `transformers` | AMD GPU (ROCm/HIP) |
| P50 | `faster-whisper-cuda` | `faster-whisper` (CTranslate2) | NVIDIA GPU (CUDA) |
| P40 | `torch-whisper-cuda` | `torch` (CUDA) + `transformers` | NVIDIA GPU (CUDA) |
| P20 | `torch-whisper-cpu` | `torch` + `transformers` | CPU |
| P50 | `faster-whisper-cpu` | `faster-whisper` (CTranslate2) | CPU |
| P10 | `whisper-cpp` | `pywhispercpp` | CPU (leichteste) |

Im `auto` Modus wird das Backend mit der höchsten Priorität unter denen mit `is_available() == True` ausgewählt.

---

## Umgebungs-spezifische Einrichtung

### Gemeinsame Anforderungen

- Python 3.11+
- ffmpeg (erforderlich zum Extrahieren von Audio aus Video)

### Hailo-10H NPU (Raspberry Pi AI HAT 2)

Keine zusätzlichen Pakete erforderlich (`hailo_platform` muss bereits installiert sein). Das Modell (`whisper-base` usw.) muss über die GenAI Extension heruntergeladen worden sein.

```bash
# Laden Sie das Modell herunter, wenn noch nicht vorhanden über die GenAI Extension UI
```

### NVIDIA GPU (CUDA)

```bash
# Empfohlen: faster-whisper (leichtgewichtig, kein PyTorch erforderlich)
pip install faster-whisper

# GPU wird automatisch verwendet, wenn CUDA erkannt wird (float16)
# Fallback zu CPU automatisch, wenn CUDA abwesend ist (int8)
```

### AMD GPU (ROCm)

```bash
# 1. Installieren Sie PyTorch ROCm Edition
#    Offiziell: https://pytorch.org/get-started/locally/
#    Beispiel (ROCm 6.x):
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.2

# 2. Installieren Sie HuggingFace transformers
pip install transformers

# 3. Setzen Sie Backend in config (auto-erkannt in "auto" Modus)
#    In Extension-Einstellungen: backend: "rocm" oder "auto"
```

**ROCm-Erkennungs-Mechanismus**: PyTorch stellt ROCm als CUDA über HIP aus. Das System identifiziert ROCm, wenn `torch.version.hip` nicht `None` ist.

**Speicher-Anforderungen** (ROCm):

| Modell | VRAM-Schätzung |
|--------|----------|
| tiny | ~150 MB |
| base | ~300 MB |
| small | ~500 MB |
| medium | ~1.5 GB |

### Nur CPU

```bash
# Option 1: faster-whisper (empfohlen, schnell mit int8 Quantisierung)
pip install faster-whisper

# Option 2: whisper.cpp (leichteste, kein PyTorch erforderlich)
pip install pywhispercpp

# Option 3: torch + transformers (Mehrzweck aber schwer)
pip install torch transformers
```

**CPU-Leistungs-Schätzungen** (Base-Modell, 1 Minute Audio):

| Backend | RPi 5 | x86 (4 Kern) |
|---|---|---|
| faster-whisper (int8) | ~30 Sek | ~5 Sek |
| whisper.cpp | ~40 Sek | ~8 Sek |
| torch (float32) | ~90 Sek | ~15 Sek |

---

## Konfiguration

Konfigurieren Sie über die Extension-Einstellungs-Seite (`/ext/speech-to-text/`) oder config.json:

| Element | Auswahlmöglichkeiten | Standard | Beschreibung |
|------|--------|-----------|------|
| `backend` | auto / hailo / cuda / rocm / cpu | auto | Inferenz-Backend |
| `model_size` | tiny / base / small / medium | base | Whisper-Modellgröße |
| `default_language` | BCP-47 Code (ja, en, usw.) | ja | Standard-Sprache |

---

## API-Endpunkte

Alle Endpunkte befinden sich unter dem `/ext/speech-to-text` Präfix.

### POST `/api/s2t/transcribe`

Transkribiert hochgeladenes WAV-Audio.

- **Content-Type**: `multipart/form-data`
- **Parameter**: `audio` (Datei), `language` (optional)
- **Antwort**: `{ status, text, segments, language, sample_rate, backend }`

### POST `/api/s2t/transcribe-video`

Transkribiert eine in der DB registrierte Video-/Audiodatei. Ergebnisse werden als Anmerkungen gespeichert.

- **Body**: `{ file_id: int, language?: string }`
- **Antwort**: `{ status, text, segments, language, backend }`
- **Anmerkung**: `source="s2t"`, Schlüssel: `transcript`, `transcript_segments`, `transcript_backend`

### POST `/api/s2t/batch-transcribe`

Batch-Transkription mehrerer Dateien (läuft im Hintergrund).

Wählen Sie **eine** von drei Eingabemethoden (gegenseitig ausschließlich):

#### Methode 1: Datei-ID-Liste (Legacy)

```json
{
  "file_ids": [123, 456, 789],
  "language": "ja"
}
```

#### Methode 2: Verzeichnis

Erkennt automatisch Video-/Audiodateien im angegebenen Verzeichnis und verarbeitet nur die in der DB registrierten.

```json
{
  "directory": "/path/to/videos/",
  "recursive": true,
  "language": "en"
}
```

- `recursive` (Standard: `true`): Rekursive Suche in Unterverzeichnissen
- Ziel-Erweiterungen: `.webm`, `.mp4`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv`, `.mp3`, `.wav`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.flac`

#### Methode 3: Text/CSV Liste

Geben Sie eine Textdatei oder CSV-Datei mit Dateipfaden an.

```json
{
  "list_file": "/path/to/targets.txt",
  "language": "ja"
}
```

**Textdatei-Format** (`.txt` usw.):
```
# Kommentarzeilen (Zeilen, die mit # beginnen, werden ignoriert)
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```

**CSV-Format** (`.csv`):
```csv
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```
Die erste Spalte wird als Dateipfad verwendet. Zeilen, die mit `#` beginnen, werden übersprungen.

#### Gemeinsame Optionen

| Parameter | Typ | Standard | Beschreibung |
|-----------|---|-----------|------|
| `language` | string | Config-Wert (typischerweise `ja`) | Sprach-Code (siehe unten) |
| `recursive` | bool | `true` | Verzeichnis-Methode nur: Rekursive Unterverzeichnis-Suche |

#### Limits und Einschränkungen

- Maximale Zieldateien: **500**
- Nur in der DB registrierte Dateien (`files` Tabelle) werden verarbeitet
- Gelöschte Dateien (`is_deleted=1`) sind ausgeschlossen

#### Antwort-Beispiel

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

- **SSE-Ereignisse**: `s2t.batch_start`, `s2t.batch_progress`, `s2t.batch_complete`

### GET `/api/s2t/transcript/<file_id>`

Ruft gespeicherte Transkriptions-Ergebnisse ab. Sowohl `source="s2t"` als auch `source="hailo:s2t"` werden für Rückwärts-Kompatibilität überprüft.

### GET `/api/s2t/status`

Gibt Backend-Status und eine Liste verfügbarer Backends zurück.

---

## MCP-Tools

| Tool-Name | Beschreibung |
|---------|------|
| `s2t_status` | Backend-Status abrufen |
| `s2t_transcribe_video` | Einzelne Videodatei transkribieren |
| `s2t_batch_transcribe` | Batch-Transkription starten (file_ids / Verzeichnis / list_file) |
| `s2t_get_transcript` | Gespeicherte Transkription abrufen |

### `s2t_batch_transcribe` Parameter

| Parameter | Typ | Erforderlich | Beschreibung |
|-----------|---|------|------|
| `file_ids` | list[int] | *1 | Datei-ID-Liste (max 500) |
| `directory` | string | *1 | Verzeichnispfad (Auto-erkennt Video/Audio) |
| `list_file` | string | *1 | Text/CSV-Dateipfad |
| `recursive` | bool | | Verzeichnis-Methode nur. Rekursive Unterverzeichnis-Suche (Standard true) |
| `language` | string | | Sprach-Code. Leer = Config-Standard |
| `expected_count` | int | | Zum Erkennen von file_ids Truncation |

*1: Geben Sie genau eine von `file_ids`, `directory` oder `list_file` an (gegenseitig ausschließlich)

---

## Dateistruktur

```
extensions/builtin_speech_to_text/
  extension.json                      # Manifest
  speech_to_text_ext.py               # Einstiegspunkt (Blueprint)
  s2t_routes.py                       # Single-Datei API-Routen
  s2t_batch_routes.py                 # Batch-API-Routen
  core_impl/
    base.py                           # S2TBackend abstrakte Basisklasse
    backend_hailo.py                  # Hailo-10H NPU
    backend_faster_whisper.py         # faster-whisper (CUDA/CPU)
    backend_torch_whisper.py          # PyTorch transformers (ROCm/CUDA/CPU)
    backend_whisper_cpp.py            # whisper.cpp (CPU)
    backend_registry.py               # Auto-Erkennung + Singleton-Verwaltung
  templates/speech_to_text/
    s2t.html                          # UI-Seite
mcp_server/
  s2t_tools.py                        # MCP-Tool-Definitionen
```

---

## Unterstützte Sprach-Codes

Wichtige von Whisper unterstützte Sprach-Codes (BCP-47):

| Code | Sprache | Code | Sprache |
|--------|------|--------|------|
| `ja` | Japanisch | `en` | Englisch |
| `zh` | Chinesisch | `ko` | Koreanisch |
| `de` | Deutsch | `fr` | Französisch |
| `es` | Spanisch | `it` | Italienisch |
| `pt` | Portugiesisch | `ru` | Russisch |
| `ar` | Arabisch | `hi` | Hindi |
| `th` | Thai | `vi` | Vietnamesisch |
| `nl` | Niederländisch | `tr` | Türkisch |
| `pl` | Polnisch | `uk` | Ukrainisch |
| `id` | Indonesisch | `sv` | Schwedisch |

Andere von Whisper unterstützte Sprachen können auch angegeben werden. Ein leerer String löst automatische Erkennung aus. Die Standard-Sprache kann über die Extension-Einstellung `default_language` geändert werden (Anfangswert: `ja`).

---

## Bekannte Einschränkungen

- **Erste Lade-Verzögerung**: transformers / faster-whisper lädt Modelle vom HuggingFace Hub herunter (base: ~150MB). Der erste Run kann mehrere Minuten dauern
- **Hailo HEF-Modelle**: Müssen über die GenAI Extension heruntergeladen werden. Die S2T Extension selbst hat keine Download-Funktionalität
- **Speicher**: Das Medium-Modell kann Out-of-Memory-Fehler auf RPi 5 (8GB) verursachen. Das Base-Modell wird empfohlen
- **Parallelität**: Backends werden als Singletons verwaltet. Anfragen, die während der Batch-Verarbeitung ankommen, teilen die gleiche Instanz
- **Eingabe-Format**: WAV (PCM s16le, mono, 16kHz) wird angenommen. Videodateien werden automatisch über ffmpeg konvertiert
- **Batch-Eingabe**: Die Verzeichnis- / list_file-Methoden verarbeiten nur DB-registrierte Dateien. Unbekannte Dateien müssen zuerst über `start_scan` registriert werden

---

## Echtzeit-Streaming-Transkription

Transkribieren Sie Audio von Internet-Radio, RTSP-Streams und Videodateien in Echtzeit und zeigen Sie Untertitel in der WebUI an.

### Zwei Modi

- **Chunk-Modus** (Standard): Teilt Audio in Blöcke unter Verwendung von RMS-basierter Stille-Erkennung auf. Kompatibel mit allen Backends (Hailo/CUDA/CPU). Ergebnisse werden angezeigt, nachdem jede Äußerung endet.
- **Live-Modus**: Führt inkrementelle Transkription mit Silero VAD von faster-whisper durch. Zeigt Zwischenergebnisse an, während Sprache noch andauert. Erfordert ein ONNX/faster-whisper Backend.

### Unterstützte Input-Quellen

- HTTP/HTTPS-Streams (Internet-Radio usw.)
- RTSP-Kameras
- RTMP-Streams

### API-Endpunkte

| Endpunkt | Methode | Funktion |
|---|---|---|
| `/api/s2t/stream/start` | POST | Streaming starten (`source_url`, `language`, `mode`) |
| `/api/s2t/stream/stop` | POST | Streaming stoppen |
| `/api/s2t/stream/status` | GET | Status abrufen |
| `/api/s2t/stream/transcript` | GET | Vollständige Transkription abrufen |
| `/api/s2t/stream/export/txt` | GET | Als Text exportieren |
| `/api/s2t/stream/export/srt` | GET | Als SRT-Untertitel exportieren |

### SSE-Ereignisse

| Ereignis | Beschreibung |
|---|---|
| `s2t.stream_chunk` | Finalisierter Text |
| `s2t.stream_interim` | Zwischentext (nur Live-Modus) |
| `s2t.stream_complete` | Streaming-Abschluss |

### MCP-Tools

| Tool | Beschreibung |
|---|---|
| `s2t_stream_start(source_url, language)` | Streaming starten |
| `s2t_stream_stop()` | Streaming stoppen |
| `s2t_stream_status()` | Status abrufen |
| `s2t_stream_transcript()` | Vollständige Transkription abrufen |

### Streaming-Konfiguration

Konfigurierbare Elemente in `extension.json`:

| Element | Beschreibung | Standard |
|---|---|---|
| `stream_chunk_min_sec` | Minimale Chunk-Länge im Chunk-Modus (Sekunden) | — |
| `stream_chunk_max_sec` | Maximale Chunk-Länge im Chunk-Modus (Sekunden) | — |
| `stream_silence_threshold` | RMS-Schwellwert für Stille-Erkennung | — |
| `stream_silence_ms` | Stille-Dauer für Erkennung (Millisekunden) | — |
| `live_interval_sec` | Transkriptions-Intervall im Live-Modus (Sekunden) | — |
