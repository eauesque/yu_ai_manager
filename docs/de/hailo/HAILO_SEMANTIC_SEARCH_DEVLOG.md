# Hailo-10H Semantische Suche — Entwicklungsprotokoll

**Projekt**: YU AI Manager — Hailo-10H CLIP semantische Bildsuche
**Ziel**: CLIP-basierte natürlichsprachliche Bildsuche auf Raspberry Pi 5 + AI HAT 2 (Hailo-10H) realisieren
**Startdatum**: 2026-03-01
**Status**: Phase 1-8 abgeschlossen, Phase 9-12 (VLM-Caption-Integration, Video-S2T, LLM-Multiturn, OpenAI-kompatibler API) abgeschlossen

---

## Warum dieses Projekt wichtig ist

Hailo-10H (AI HAT 2) ist ein relativ neuer Edge-KI-Beschleuniger, der Ende 2025 veröffentlicht wurde und in den M.2-Steckplatz des Raspberry Pi 5 eingesetzt wird. Mit 40 TOPS Inferenzleistung gibt es bisher kaum praktische Anwendungsbeispiele.

Dieses Projekt wird wahrscheinlich die erste praktische Software sein, die mit Hailo-10H semantische Suche (natürlichsprachliche Bildsuche) über eine Bildbibliothek mit 200.000 Einträgen realisiert.

---

## Phase 1: Machbarkeitsnachweis (2026-03-01)

### Umgebungsinformationen

| Element | Wert |
|------|-----|
| Hardware | Raspberry Pi 5 (8GB) + AI HAT 2 (Hailo-10H) |
| OS | Raspberry Pi OS Trixie (Linux 6.12.62+rpt-rpi-2712) |
| Python | 3.13.5 |
| HailoRT-Treiber | 5.2.0 (hailort-pcie-driver) |
| HailoRT-Bibliothek | 5.2.0 (hailort deb) |
| HailoRT Python | 5.2.0 (**Quell-Build**) |

### Schritt 1-1: Geräteerkennung — OK

```bash
$ hailortcli fw-control identify
Firmware Version: 5.2.0 (release,app)
Device Architecture: HAILO10H
```

Gerät problemlos erkannt. PCIe-Verbindung und Treiberladen in Ordnung.

### Schritt 1-2: HEF-Download — OK

Direkt aus dem Hailo Model Zoo v5.2.0 S3-Bucket herunterladbar (keine Authentifizierung erforderlich).

```
~/hailo_models/clip_vit_b_16_image_encoder.hef  (76 MB)
~/hailo_models/clip_vit_b_16_text_encoder.hef   (77 MB)
```

URL-Muster:
```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

### Schritt 1-3: Python-Bindings — Quell-Build erforderlich

#### Problem: Paketversions-Mismatch

Im Raspberry Pi OS-Repository gibt es zwei Paketsysteme:

| Paketsystem | Version | Hinweise |
|---------------|-----------|------|
| `hailort` + `hailort-pcie-driver` | 5.2.0 | Offizielles Hailo-Deb. Keine Python-Bindings |
| `h10-hailort` + `python3-h10-hailort` | 5.1.1 | Vom Raspberry Pi Team bereitgestellt. Python vorhanden |

**Problem**: Die zwei Systeme haben `Conflicts` und können nicht koexistieren. `h10-hailort` (5.1.1) ändert auch den Treiber auf 5.1.1, aber hailo-ollama benötigt 5.2.0.

#### Lösung: Python-Wheel für hailort 5.2.0 aus Quellen bauen

**Kein Wheel auf PyPI.** Auch auf der Hailo Developer Zone Download-Seite gibt es **kein aarch64-Wheel** (nur x86_64).

Lösung durch Quell-Build aus dem GitHub-Repository:

```bash
git clone --depth 1 --branch v5.2.0 https://github.com/hailo-ai/hailort.git ~/hailort

# Build-Abhängigkeiten
sudo apt install -y swig build-essential
pip install pybind11 setuptools wheel

# Build (ca. 2 Minuten)
cd ~/hailort/hailort/libhailort/bindings/python/platform
HAILORT_INCLUDE_DIR=/usr/include/hailo \
LIBHAILORT_PATH=/usr/lib/libhailort.so.5.2.0 \
PYBIND11_PYTHON_VERSION=3.13 \
python3 setup.py bdist_wheel --plat-name linux_aarch64

# Installation
pip install dist/hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

**Wichtige Hinweise**:
- `--plat-name linux_aarch64` ist obligatorisch. Ohne es tritt ein `ValueError` in setup.py Zeile 163 auf
- `hailort` deb (C-Bibliothek) muss zuerst installiert werden
- `h10-hailort` und `hailort` können wegen `Conflicts` nicht koexistieren

### Schritt 1-4: Inferenztest — Erfolgreich (mit API-Änderungen)

#### Wichtige Entdeckung: Hailo-10H unterstützt die alte VStreams-API nicht

Der Code mit `InferVStreams` + `ConfigureParams.create_from_hef()` **funktioniert auf Hailo-10H nicht**. `VDevice.configure()` gibt `HAILO_NOT_IMPLEMENTED (error 7)` zurück.

Dies ist ein **fundamentaler API-Unterschied zwischen Hailo-8/8L und Hailo-10H**, der in der offiziellen Dokumentation nicht klar angegeben ist.

#### Korrekte API: InferModel

Für Hailo-10H `VDevice.create_infer_model()` verwenden:

```python
from hailo_platform import VDevice
import numpy as np

hef_path = "~/.hailo_models/clip_vit_b_16_image_encoder.hef"

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(hef_path)

    # inputs/outputs sind Eigenschaften (keine aufrufbaren Methoden)
    inp_info = infer_model.inputs[0]   # NICHT inputs()
    out_info = infer_model.outputs[0]

    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # Eingabe: uint8-Bild
    dummy = np.random.randint(0, 255, inp_info.shape, dtype=np.uint8)
    bindings.input().set_buffer(dummy)

    # Ausgabe: uint8-Puffer explizit allozieren
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    configured.run([bindings], timeout=10000)

    vec = output_buf.flatten()  # (512,) uint8
```

#### Blockpunkte und Lösungen

| Problem | Fehler | Lösung |
|------|--------|------|
| `infer_model.inputs()` TypeError | `'list' object is not callable` | Eigenschaft, also `inputs[0]` (ohne Klammern) |
| Ausgabepuffer nicht gesetzt | `not configured as view` | Mit `bindings.output().set_buffer(buf)` explizit allozieren |
| Ausgabepuffer als float32 alloziert | `buffer size 2048 != expected 512` | **uint8** verwenden (512 Bytes). float32 wären 2048 Bytes |
| Fehler beim Beenden von VDevice | `Lost communication with server` | Problem mit Bereinigungsreihenfolge von VDevice. **Hat keinen Einfluss auf Inferenzergebnisse** |

### Inferenzleistung

| Element | Wert |
|------|-----|
| Modell | CLIP ViT-B/16 Bild-Encoder |
| Eingabe | (224, 224, 3) uint8 |
| Ausgabe | (1, 1, 512) uint8 (quantisiert) |
| Inferenzzeit | **~20 ms** |
| Theoretischer Durchsatz | **~50 Bilder/Sek** |

Indexaufbau für 200.000 Bilder: Nur Inferenz ca. 67 Minuten. Inkl. Vorverarbeitung innerhalb einiger Stunden.

### Phase-1-Beurteilung

| Kriterium | Ergebnis |
|------|------|
| 512-dimensionaler Vektorausgang | **OK** (uint8-quantisiert, Dequantisierung erforderlich) |
| Inferenzgeschwindigkeit | **Ausgezeichnet** (20ms/Bild) |
| API-Kompatibilität | InferModel-API verwendet (VStreams-API nicht möglich) |
| Urteil | **Weiter zu Phase 2** |

---

## Phase 2: DB-Schema-Erweiterung (2026-03-01)

Als Migration 25 wurde die Tabelle `file_vectors` hinzugefügt.

```sql
CREATE TABLE file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip_vit_b_16',
    vector      BLOB NOT NULL,        -- float32 numpy array tobytes() (512*4=2048 Bytes)
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX idx_file_vectors_model ON file_vectors(model);
```

**Designentscheidungen**:
- `vector` speichert dequantisierten float32 BLOB. Bei uint8-Speicherung Genauigkeitsverlust
- `file_id` ist PRIMARY KEY (1 Datei, 1 Vektor)
- `ON DELETE CASCADE` für automatisches Löschen bei Dateilöschung

---

## Phase 3: Hailo-Inferenz-Kern (2026-03-01)

Das Paket `core/hailo_clip_core/` (jetzt `extensions/builtin_hailo_semantic_search/core_impl/`) wurde erstellt:

| Datei | Verantwortlichkeit |
|---------|------|
| `hailo_inference.py` | HailoClipEncoder Singleton. InferModel-API-Wrapper |
| `image_preprocess.py` | cv2-basiertes 224x224-Resize + BGR→RGB-Konvertierung |
| `dequantize.py` | uint8→float32-Dequantisierung + L2-Normalisierung + quant_params-Extraktion |
| `text_encoder.py` | CPU CLIP-Text-Encoder (`openai/clip-vit-base-patch16`) |

---

## Phase 4: Indexer + Extension (2026-03-01)

API-Endpunkte:
- `GET /ext/hailo-semantic/api/status` — Geräte- und Indexstatus
- `POST /ext/hailo-semantic/api/index/start` — Index-Aufbau starten
- `GET /ext/hailo-semantic/api/index/status` — Fortschritt
- `POST /ext/hailo-semantic/api/index/stop` — Unterbrechen
- `GET /ext/hailo-semantic/api/search` — Semantische Suche
- `POST /ext/hailo-semantic/api/index/clear` — Index leeren

---

## Phase 5: Semantische Suchmaschine (2026-03-01)

`core/hailo_clip_core/search.py` (jetzt `extensions/builtin_clip_search/core_impl/search.py`) — Cosinus-Ähnlichkeitssuche mit Speichercache

**Algorithmus**:
1. Alle Vektoren aus DB laden → Speichercache
2. Vektoren vorab L2-normalisieren
3. Abfragetext → CLIP-Text-Encoder → 512-dimensionaler Vektor
4. Matrizenmultiplikation (Skalarprodukt) für Batch-Cosinus-Ähnlichkeitsberechnung
5. Elemente über Schwellenwert sortieren → Ergebnis zurückgeben

**Speicherabschätzung**: 200.000 × 512 × 4 Bytes = ~400 MB (im Pi5 8GB RAM akzeptabel)

---

## Phase 6: UI-Integration (2026-03-01)

### Suchseite

- Semantischer Such-Toggle (Gehirn-Symbol im `regex-pill`-Stil) neben der Suchleiste hinzugefügt
- Wird nur angezeigt, wenn Hailo verfügbar und Index aufgebaut
- Bei aktiviertem Toggle: Formularübermittlung abfangen → Semantische Such-API → Ergebnisse im vorhandenen Raster anzeigen

### Tools-Seite

- Semantischer Such-Abschnitt im Tab "Search & Analysis" hinzugefügt
- Anzeige von Gerätestatus/Indexstatus
- Batch-Size-Schieberegler + Auto-Index-Checkbox
- Build Index / Stop / Clear-Schaltflächen + Fortschrittsbalken (2-Sekunden-Polling)

---

## Technische Hinweise

### Hauptunterschiede zwischen Hailo-10H und Hailo-8/8L (aus Entwicklerperspektive)

| Element | Hailo-8/8L | Hailo-10H |
|------|-----------|-----------|
| VStreams-API | Unterstützt | **Nicht unterstützt** (NOT_IMPLEMENTED) |
| InferModel-API | Unterstützt | Unterstützt |
| ConfigureParams | create_from_hef(hef, interface) | Nicht erforderlich (create_infer_model ersetzt es) |
| Ausgabeformat | float32 oder uint8 wählbar | uint8 fest (Dequantisierung erforderlich) |
| Python-Paket | PyPI-Wheel vorhanden | **Nicht vorhanden** (Quell-Build erforderlich) |
| APT-Paket | `hailort` integriert | `h10-hailort` separates System (nur 5.1.1) |

---

## Phase 2-6 Bug-Protokoll nach der Implementierung (2026-03-01)

### 1. `get_text_features`-Kompatibilitätsproblem des Text-Encoders

**Problem**: `CLIPModel.get_text_features(**inputs)` gibt in neueren transformers-Versionen ein `BaseModelOutputWithPooling`-Objekt zurück statt eines `torch.Tensor`.

**Fix**: Zweistufige Verarbeitung in `text_encoder.py`: `text_model()` → `text_projection()`.

### 2. Endloswiederholungsschleife beim Index-Aufbau

**Problem**: Dateien, die beim Dekodieren fehlschlugen, wurden nicht in `failed_ids` verfolgt, sodass `get_unindexed_file_ids()` jedes Mal dieselben fehlgeschlagenen Dateien zurückgab.

**Fix**: `failed_ids: set` zu `indexer.py` hinzugefügt.

### 3. Fehler beim Laden von Archivdateibildern

**Problem**: `cv2.imread('test.7z!image.png')` versteht keine Archiv-Member-Pfade.

**Fix**: `is_archive_member()` zur Erkennung von Archivpfaden verwenden und auf `cv2.imdecode()`-Muster umstellen.

### 4. SSE-Echtzeit-Fortschrittsupdate

**Problem**: 2-Sekunden-Polling ergab ruckartigen Fortschritt.

**Fix**: Auf `EventSource` SSE-Verbindung umgestellt.

---

## Phase 7: YOLO-Objekterkennung (2026-03-02)

### Überblick

YOLO-Objekterkennung auf demselben Hailo-10H implementiert. 80-Klassen-COCO-Objekterkennung für Bilder und Videos, Ergebnisse in Tabelle `file_annotations` gespeichert.

### Architekturdesign

#### VDevice-Sharing-Problem

Hailo-10H kann nur einen VDevice aus einem einzelnen Prozess verwenden, und InferModel ist exklusiv.
CLIP und YOLO können nicht gleichzeitig laufen.

**Lösung**: `core/hailo_device_core/device_manager.py` eingeführt.

### Neue Modulstruktur

| Modul | Rolle |
|---|---|
| `core/hailo_device_core/device_manager.py` | Gemeinsamer VDevice-Lebenszyklus-Manager |
| `core/hailo_yolo_core/hailo_yolo_inference.py` | YOLODetector Singleton |
| `core/hailo_yolo_core/yolo_postprocess.py` | NMS, Box-Dekodierung, Dequantisierung |
| `core/hailo_yolo_core/yolo_labels.py` | COCO 80-Klassen-Labels |
| `core/hailo_yolo_core/yolo_preprocess.py` | 640x640 Letterbox-Resize |
| `core/hailo_yolo_core/yolo_video.py` | Video-Frame-Extraktion + Aggregation |
| `core/hailo_yolo_core/yolo_indexer.py` | Hintergrund-Batch-Erkennung |
| `core/hailo_yolo_core/model_download.py` | HEF-Download |
| `core/hailo_yolo_core/event_handler.py` | scan.complete-Handler |
| `extensions/builtin_hailo_yolo_detect/` | Extension + Blueprint-API + UI |

---

## Phase 8: GenAI (LLM / VLM / Speech2Text)-Integration (2026-03-02)

### Ziel

`hailo_platform.genai`-Modul (LLM, VLM, Speech2Text) in device_manager integrieren, Textgenerierung, Bildverstehen und Sprachtranskription über WebUI verfügbar machen.

### device_manager-Erweiterung

- **Problem**: Bestehender device_manager unterstützt nur InferModel-API (CLIP/YOLO).
  GenAI-Klassen nehmen VDevice direkt statt InferModel
- **Lösung**: `_mode`-Variable (`"infer"` | `"genai"`) zur Modusdifferenzierung.
  `acquire_genai(owner, model_path, genai_factory)` hinzugefügt

### GenAI-API-Entdeckungen

- **Nachrichtenformat**: OpenAI-kompatibler role/content-Aufbau. Content als Array mit `{"type": "text", "text": "..."}` Format
- **VLM-Bildeingabe**: 336x336 RGB uint8 numpy-Array. Als `frames=[image]` übergeben.
  `{"type": "image"}`-Platzhalter im Prompt platzieren
- **S2T-Eingabe**: Little-Endian float32 (`<f4`), Mono, 16kHz. int16→float32-Normalisierung erforderlich
- **S2T-Segmente**: `generate_all_segments()` gibt `SegmentInfo`-Objekte zurück
- **Kontext-Verwaltung**: `get_context_usage_size()`, `max_context_capacity()`, `clear_context()` für Kontextfenster
- **Streaming**: `generate()` gibt Iterator zurück, yield per Token

### Modell-HEF-Download-URL

- Muster: `https://dev-public.hailo.ai/v{hailort_version}/blob/{ModelName}.hef`
- Modellnamen in CamelCase (z.B. `Qwen2.5-1.5B-Instruct.hef`, `Whisper-Base.hef`)

---

## Phase 9: Semantische Suche + VLM-Caption-Integration (2026-03-03)

### Ziel

CLIP-Suchergebnisbilder mit VLM (Qwen2-VL) als Batch-Captions generieren und in `file_annotations` speichern.

### Annotations-Konvention

- `source="hailo:vlm"`, `key="caption"`, `value=<Caption-Text>`

---

## Phase 10: Video-Sprachtranskription — S2T-Pipeline (2026-03-03)

### Implementierung

- **`core/files_core/video_audio.py`** (~80 Zeilen): `extract_audio_wav()` für ffmpeg-Audioextraktion (Mono PCM s16le 16kHz)
- Blueprint-Erweiterung: 3 neue Endpunkte:
  - `POST /api/s2t/transcribe-video`: Einzelvideo-Transkription
  - `POST /api/s2t/batch-transcribe`: Batch-Transkription mehrerer Videos
  - `GET /api/s2t/transcript/<file_id>`: Gespeicherte Transkription abrufen

### Annotations-Konvention

- `source="hailo:s2t"`, `key="transcript"`, `value=<Volltext>`
- `source="hailo:s2t"`, `key="transcript_segments"`, `value=<JSON [{text, start, end}, ...]>`

---

## Phase 11: LLM-Multiturn-Chat-UI-Verbesserung (2026-03-03)

### Ziel

Einzelne Prompts auf Gesprächsverlaufs-Unterstützung erweitern. Kontext fortführen, zurücksetzen, Blasen-UI.

### Bug-Fix: Multiturn-System-Role-Fehler (2026-03-03)

MCP-Debug-Abfrage + hailort-Logs entdeckten folgenden Fehler beim zweiten+ Turn:

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_INVALID_OPERATION(6)
```

**Ursache**: UI-Template sendete bei jedem Turn `[systemMsg].concat(_chatHistory)`.
HailoRT LLM-API akzeptiert keine System-Role bei bestehendem Kontext (ab 2. Turn).

**Fix**:
1. `_prepare_prompt()`-Methode zu `llm_inference.py` hinzugefügt: Bei `get_context_usage_size() > 0` System-Role-Nachrichten automatisch entfernen
2. UI-Template: System nur bei erstem Benutzernachricht hinzufügen

---

## WD-Tagger VLM × Hailo-10H Praxistest (2026-03-03)

### Wichtige Entdeckung: hailo-ollama unterstützt VLM nicht

Aus der offiziellen hailo-ollama-Dokumentation (USAGE.rst):
> "The Hailo-Ollama API is currently limited to language models (LLMs) and cannot be used for VLMs."

### Hailo Python SDK VLM-Direkttest-Ergebnisse

VLM muss das Nachrichtenformat mit `{"type": "image"}` verwenden:
```python
messages = [
    {"role": "user", "content": [
        {"type": "image"},
        {"type": "text", "text": "Tag this image."}
    ]}
]
vlm.generate_all(messages, frames=[frame_336x336_rgb_uint8])
```

- **Modell-Ladezeit**: 33 Sek. (Erster Kaltstart)
- **Inferenzgeschwindigkeit**: ~5,1 TPS
- **JSON-Ausgabequalität**: Niedrig. 2B-Modell generiert unzuverlässig strukturiertes JSON

---

## Phase 12: OpenAI-kompatibler API + Device-Switching-Bug-Fix (2026-03-14)

### Ziel

1. OpenAI-kompatible API für direkte Nutzung von Hailo GenAI aus externen Tools (OpenAI SDK / LiteLLM / Continue.dev / Open WebUI)
2. Quart-Async-Mängel beheben
3. MCP-Tool SSE-Endpunkt-Unterstützung

### Implementierung: OpenAI-kompatibler API (`hailo_openai_routes.py`)

Neue Datei mit 4 Endpunkten:

| Endpunkt | Funktion | Unterstützte Modelle |
|---|---|---|
| `GET /v1/models` | Verfügbare Modellliste | Alle Modelle + CLIP |
| `POST /v1/chat/completions` | Text/Bild-Chat (Stream-Unterstützung) | LLM + VLM |
| `POST /v1/audio/transcriptions` | Sprachtranskription | Whisper |
| `POST /v1/embeddings` | Text→CLIP-Vektor | CLIP ViT-B/16 |

### Entdeckter Bug: Singleton-Inkonsistenz beim Device-Wechsel

#### Symptom

Nach Verwendung von VLM → LLM aufrufen ergibt `'NoneType' object has no attribute 'get_context_usage_size'`.

#### Ursachenanalyse

Hailo-10H kann nur einen VDevice halten. Bei Modellwechsel:

1. VLMs `get_vlm()` → `acquire_genai("vlm", ...)` → intern gibt `_release_internal()` LLMs VDevice frei
2. VLM-Verwendung abgeschlossen
3. LLMs `get_llm()` → `_instance` noch vorhanden + `model_name` stimmt überein → **bestehende Instanz wiederverwenden**
4. VDevice hinter `_instance._llm` wurde bereits von `device_manager` freigegeben → `get_context_usage_size()` auf `None` aufgerufen → Absturz

**Wurzelproblem**: Singleton `_instance` bleibt bestehen, aber der dahinter liegende Hailo-SDK-nativer VDevice wurde freigegeben.

#### Fix

`device_manager.get_current_owner()`-Prüfung zu Singleton-Wiederverwendungsprüfungen in `get_llm()` / `get_vlm()` / `get_s2t()` hinzugefügt:

```python
def get_llm(model_name="qwen2.5-1.5b-chat"):
    global _instance
    with _lock:
        if _instance is not None and _instance.model_name == model_name:
            from core.hailo_device_core.device_manager import get_current_owner
            if get_current_owner() == "llm":
                return _instance  # Device wird gehalten → Wiederverwendung OK
            # Device wurde von einem anderen Modell übernommen → Neu erstellen
            _instance = None
        ...
```

Dieselbe Korrektur auf alle 3 Singletons (LLM / VLM / S2T) angewendet.

### Technische Hinweise

- **Exklusivitätsbeschränkung von VDevice auf SDK-Ebene**: Selbst wenn Python Objekte referenziert, werden native Ressourcen freigegeben, sobald der device_manager `.release()` aufruft. Bei Singleton-Mustern ist die Gültigkeit nativer Ressourcen separat zu prüfen
- **Quart + synchrone Generatoren**: SSE-Antworten mit synchronen Generatoren können Ereignisschleifen blockieren. Hailo-Inferenz muss immer über `asyncio.to_thread` in separate Threads ausgelagert werden
- **OpenAI Vision API und VLM**: OpenAI Vision API empfängt Bilder im `image_url`-Feld, Hailo VLM empfängt `frames` (numpy-Array). Konvertierungsschicht: base64-Dekodierung → OpenCV-Dekodierung → 336x336 RGB-Resize
