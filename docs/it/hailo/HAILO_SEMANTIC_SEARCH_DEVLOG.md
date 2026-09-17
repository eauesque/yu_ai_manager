# Hailo-10H Semantic Search — Log di sviluppo

**Progetto**: YU AI Manager — Ricerca semantica di immagini basata su CLIP con Hailo-10H
**Obiettivo**: realizzare la ricerca di immagini in linguaggio naturale basata su CLIP con Raspberry Pi 5 + AI HAT 2 (Hailo-10H)
**Data di inizio**: 2026-03-01
**Stato**: Phase 1-8 completate, Phase 9-12 (integrazione caption VLM, S2T video, LLM multi-turn, API OpenAI compatibili) completate

---

## Perché questo progetto è importante

Hailo-10H (AI HAT 2) è un acceleratore AI edge relativamente nuovo, rilasciato a fine 2025,
che si installa nello slot M.2 di Raspberry Pi 5. Ha una capacità di inferenza da 40 TOPS, ma
**esempi d'uso in applicazioni concrete sono ancora molto pochi, pubblicamente**.

Questo progetto realizza con Hailo-10H una ricerca semantica (ricerca immagini in linguaggio naturale)
su una libreria di immagini dell'ordine di 200.000 elementi, e sarà probabilmente il primo software
d'uso pratico in questo ambito.

---

## Phase 1: verifica di fattibilità (2026-03-01)

### Informazioni sull'ambiente

| Voce | Valore |
|------|-----|
| Hardware | Raspberry Pi 5 (8GB) + AI HAT 2 (Hailo-10H) |
| OS | Raspberry Pi OS Trixie (Linux 6.12.62+rpt-rpi-2712) |
| Python | 3.13.5 |
| Driver HailoRT | 5.2.0 (hailort-pcie-driver) |
| Libreria HailoRT | 5.2.0 (hailort deb) |
| HailoRT Python | 5.2.0 (**build dai sorgenti**) |

### Step 1-1: riconoscimento del dispositivo — OK

```bash
$ hailortcli fw-control identify
Firmware Version: 5.2.0 (release,app)
Device Architecture: HAILO10H
```

Il dispositivo è stato riconosciuto senza problemi. Connessione PCIe e caricamento del driver entrambi regolari.

### Step 1-2: download HEF — OK

Scaricabile direttamente dal bucket S3 di Hailo Model Zoo v5.2.0 (nessuna autenticazione richiesta).

```
~/hailo_models/clip_vit_b_16_image_encoder.hef  (76 MB)
~/hailo_models/clip_vit_b_16_text_encoder.hef   (77 MB)
```

Pattern di URL:
```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

### Step 1-3: binding Python — richiede build dai sorgenti

#### Problema: incompatibilità tra versioni dei pacchetti

Nei repository di Raspberry Pi OS esistono due linee di pacchetti:

| Linea di pacchetti | Versione | Note |
|---------------|-----------|------|
| `hailort` + `hailort-pcie-driver` | 5.2.0 | deb ufficiale Hailo. Nessun binding Python |
| `h10-hailort` + `python3-h10-hailort` | 5.1.1 | fornita dal team di Raspberry Pi. Con Python |

**Problema**: le due linee sono impostate in `Conflicts` e non possono coesistere. Installando `h10-hailort` (5.1.1) il driver diventa anch'esso 5.1.1, ma hailo-ollama richiede la 5.2.0.

#### Soluzione: build dai sorgenti del wheel Python di hailort 5.2.0

**Su PyPI non c'è il wheel**. Nemmeno nella pagina di download di Hailo Developer Zone
**esiste un wheel per aarch64** (solo per x86_64).

Si risolve con build dai sorgenti dal repository GitHub:

```bash
git clone --depth 1 --branch v5.2.0 https://github.com/hailo-ai/hailort.git ~/hailort

# Dipendenze di build
sudo apt install -y swig build-essential
pip install pybind11 setuptools wheel

# Build (circa 2 minuti)
cd ~/hailort/hailort/libhailort/bindings/python/platform
HAILORT_INCLUDE_DIR=/usr/include/hailo \
LIBHAILORT_PATH=/usr/lib/libhailort.so.5.2.0 \
PYBIND11_PYTHON_VERSION=3.13 \
python3 setup.py bdist_wheel --plat-name linux_aarch64

# Installazione
pip install dist/hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

**Note**:
- `--plat-name linux_aarch64` è obbligatorio. Omettendolo, il parsing del nome della directory di `LIBHAILORT_PATH`
  genera `ValueError: not enough values to unpack` (bug alla riga 163 di setup.py)
- Il deb `hailort` (libreria C) va installato prima
- `h10-hailort` e `hailort` non possono coesistere per impostazione `Conflicts`, quindi
  rimuovere prima `h10-hailort` e poi installare `hailort` 5.2.0

### Step 1-4: test di inferenza — riuscito (con cambiamenti di API)

#### Scoperta importante: Hailo-10H non supporta la vecchia API VStreams

Il codice `InferVStreams` + `ConfigureParams.create_from_hef()` descritto nella specifica
**non funziona su Hailo-10H**. `VDevice.configure()` restituisce `HAILO_NOT_IMPLEMENTED (error 7)`.

Questa è una **differenza fondamentale di API tra Hailo-8/8L e Hailo-10H**, non chiaramente
documentata nemmeno nei documenti ufficiali.

#### API corretta: InferModel

Su Hailo-10H si usa `VDevice.create_infer_model()`:

```python
from hailo_platform import VDevice
import numpy as np

hef_path = "~/.hailo_models/clip_vit_b_16_image_encoder.hef"

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(hef_path)

    # inputs/outputs sono property (non callable)
    inp_info = infer_model.inputs[0]   # NOT inputs()
    out_info = infer_model.outputs[0]

    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # Input: immagine uint8
    dummy = np.random.randint(0, 255, inp_info.shape, dtype=np.uint8)
    bindings.input().set_buffer(dummy)

    # Output: allocare esplicitamente un buffer uint8
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    configured.run([bindings], timeout=10000)

    vec = output_buf.flatten()  # (512,) uint8
```

#### Punti di blocco e soluzioni

| Problema | Errore | Soluzione |
|------|--------|------|
| `infer_model.inputs()` TypeError | `'list' object is not callable` | Essendo property, usare `inputs[0]` (senza parentesi) |
| Buffer di output non impostato | `not configured as view` | Allocarlo esplicitamente con `bindings.output().set_buffer(buf)` |
| Buffer di output allocato float32 | `buffer size 2048 != expected 512` | Allocare come **uint8** (512 bytes). float32 sarebbe 2048 bytes |
| Errore alla chiusura di VDevice | `Lost communication with server` | Problema di ordine di cleanup di VDevice. **Nessun impatto sui risultati dell'inferenza** |

### Performance di inferenza

| Voce | Valore |
|------|-----|
| Modello | CLIP ViT-B/16 Image Encoder |
| Input | (224, 224, 3) uint8 |
| Output | (1, 1, 512) uint8 (quantizzato) |
| Tempo di inferenza | **~20 ms** |
| Throughput teorico | **~50 images/sec** |

Costruzione di un indice di 200.000 immagini: circa 67 minuti considerando solo l'inferenza. Con il preprocessing, previsto il completamento entro poche ore.

### Verdetto Phase 1

| Criterio | Risultato |
|------|------|
| Output vettoriale a 512 dimensioni | **OK** (quantizzato uint8, richiede dequantizzazione) |
| Velocità di inferenza | **Eccellente** (20ms/image) |
| Compatibilità API | Uso di InferModel API (la VStreams API della specifica non è utilizzabile) |
| Verdetto | **Procedere alla Phase 2** |

### Elementi da riportare alla fase successiva

1. **Dequantizzazione**: l'output uint8 va convertito in float32.
   L'HEF dovrebbe contenere i parametri di quantizzazione (scale/zero_point).
   Si può potenzialmente usare `hailo_platform.pyhailort._pyhailort.dequantize_output_buffer`.
2. **Text encoder**: l'HEF esiste ma non è stato testato. Verificare se funziona con la stessa InferModel API.
   In linea con la specifica potrebbe essere più sicuro implementarlo su CPU (sentence-transformers).
3. **Coesistenza con hailo-ollama**: VDevice usa il dispositivo in modo esclusivo.
   Durante la costruzione dell'indice è necessario fermare hailo-ollama.
4. **Cleanup di VDevice**: il messaggio di errore alla chiusura è innocuo, ma
   in processi server di lunga durata attenzione ai leak di risorse.

---

## Phase 2: estensione dello schema DB (2026-03-01)

### Implementazione

Aggiunta della tabella `file_vectors` come Migration 25.

```sql
CREATE TABLE file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip_vit_b_16',
    vector      BLOB NOT NULL,        -- float32 numpy array tobytes() (512*4=2048 bytes)
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX idx_file_vectors_model ON file_vectors(model);
```

**Decisioni di design**:
- `vector` salva il BLOB float32 dopo dequantizzazione. Salvarlo in uint8 degraderebbe la precisione
- `file_id` è PRIMARY KEY (1 file = 1 vettore). In futuro, per supportare più modelli, servirà passare a UNIQUE(file_id, model)
- `ON DELETE CASCADE` per la cancellazione automatica alla rimozione di files

**Test**: applicazione della migration su DB in-memory → verifica esistenza tabella/indice → OK

### File

- `core/schema_core/schema_migrate_steps_25.py` (nuovo)
- `core/schema_core/schema_migrate.py` (aggiunto import + `if current_version < 25`)
- `core/schema_core/schema_constants.py` (`CURRENT_SCHEMA_VERSION = 25`)
- `core/hailo_clip_core/vector_store.py` (nuovo - CRUD vettori DB)  *(attualmente spostato in `extensions/builtin_hailo_semantic_search/core_impl/`)*

---

## Phase 3: core di inferenza Hailo (2026-03-01)

### Implementazione

Creazione del nuovo package `core/hailo_clip_core/` *(attualmente `extensions/builtin_hailo_semantic_search/core_impl/`)*:

| File | Responsabilità |
|---------|------|
| `hailo_inference.py` | Singleton HailoClipEncoder. Wrapper dell'InferModel API |
| `image_preprocess.py` | Resize 224x224 + conversione BGR→RGB con cv2 |
| `dequantize.py` | Dequantizzazione uint8→float32 + normalizzazione L2 + estrazione quant_params |
| `text_encoder.py` | Text encoder CLIP su CPU (`openai/clip-vit-base-patch16`) |

**Decisioni di design**:
- Il preprocessing immagini passa uint8 a Hailo (la normalizzazione avviene dentro l'HEF)
- Il text encoder usa CLIPModel di `transformers` (non `sentence-transformers`).
  Motivo: `openai/clip-vit-base-patch16` è lo stesso modello del CLIP ViT-B/16 dell'HEF Hailo,
  quindi lo spazio vettoriale coincide
- I parametri di dequantizzazione vengono tentati da `infer_model.outputs[0].quant_infos[0]`;
  in caso di errore fallback a scale=1.0, zero_point=0.0

**Pacchetti dipendenti**: `opencv-python-headless`, `numpy` (obbligatori), `transformers`, `torch` (per la ricerca testuale)

---

## Phase 4: indexer + Extension (2026-03-01)

### Implementazione

| File | Responsabilità |
|---------|------|
| `core/hailo_clip_core/indexer.py` *(attualmente `extensions/builtin_clip_search/core_impl/`)* | Costruzione indice a batch in thread in background |
| `core/hailo_clip_core/event_handler.py` *(attualmente `extensions/builtin_clip_search/core_impl/`)* | Indicizzazione automatica su evento scan.complete |
| `extensions/builtin_hailo_semantic_search/extension.json` | Manifesto Extension |
| `extensions/builtin_hailo_semantic_search/hailo_semantic_search.py` | Blueprint con 5 API |

**Endpoint API**:
- `GET /ext/hailo-semantic/api/status` — stato del dispositivo e dell'indice
- `POST /ext/hailo-semantic/api/index/start` — avvio costruzione indice
- `GET /ext/hailo-semantic/api/index/status` — progresso
- `POST /ext/hailo-semantic/api/index/stop` — interruzione
- `GET /ext/hailo-semantic/api/search` — ricerca semantica
- `POST /ext/hailo-semantic/api/index/clear` — pulizia dell'indice

**Eventi**: aggiunti `semantic_index.start/progress/complete` all'event_bus

---

## Phase 5: motore di ricerca semantica (2026-03-01)

### Implementazione

`core/hailo_clip_core/search.py` *(attualmente `extensions/builtin_clip_search/core_impl/search.py`)* — ricerca per similarità coseno con cache in memoria

**Algoritmo**:
1. Caricamento in blocco di tutti i vettori dal DB → cache in memoria
2. Normalizzazione L2 preliminare dei vettori
3. Testo della query → text encoder CLIP → vettore a 512 dimensioni
4. Calcolo batch della similarità coseno tramite prodotto di matrice (dot product)
5. Ordinamento per soglia → restituzione risultati

**Stima memoria**: 200K x 512 x 4 bytes = ~400 MB (entro i limiti degli 8GB di RAM del Pi5)

**Formato della risposta**:
```json
{
    "status": "ok",
    "total": 25,
    "results": [{"file_id": 123, "score": 0.82, "path": "..."}],
    "query": "blue sky",
    "indexed_count": 200000,
    "threshold": 0.2,
    "timing": {"encode_ms": 150.3, "search_ms": 12.5}
}
```

---

## Phase 6: integrazione UI (2026-03-01)

### Pagina di ricerca

- Aggiunta di un toggle ricerca semantica (icona cervello, stile `regex-pill`) accanto alla barra di ricerca
- Visualizzato solo se Hailo è disponibile & l'indice è costruito
- Con toggle ON: intercetta l'invio del form di ricerca → API di ricerca semantica → visualizza i risultati nella griglia esistente
- Sostituzione del placeholder con esempi di testo in inglese

### Pagina Tools

- Aggiunta della sezione di ricerca semantica nel tab Search & Analysis
- Visualizzazione stato dispositivo/stato indice
- Slider per batch size + checkbox di auto-indicizzazione
- Pulsanti Build Index / Stop / Clear + barra di progresso (polling a 2 secondi)

---

## Note tecniche

### Principali differenze Hailo-10H vs Hailo-8/8L (prospettiva dello sviluppatore)

| Voce | Hailo-8/8L | Hailo-10H |
|------|-----------|-----------|
| VStreams API | Supportata | **Non supportata** (NOT_IMPLEMENTED) |
| InferModel API | Supportata | Supportata |
| ConfigureParams | create_from_hef(hef, interface) | Non necessaria (create_infer_model la sostituisce) |
| Formato di output | float32 o uint8 selezionabile | Fisso uint8 (serve dequantizzazione) |
| Pacchetto Python | Wheel PyPI disponibile | **Non disponibile** (serve build dai sorgenti) |
| Pacchetto APT | `hailort` integrato | `h10-hailort` linea separata (solo 5.1.1) |

### Conservazione del wheel compilato

```
~/hailort/hailort/libhailort/bindings/python/platform/dist/
  hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

Per distribuzioni su altri ambienti Pi5 è possibile copiare e installare questo wheel
(però servono libhailort.so.5.2.0 e hailort-pcie-driver 5.2.0).

---

## Log delle correzioni di bug dopo Phase 2-6 (2026-03-01)

### 1. Problema di compatibilità di `get_text_features` del text encoder

**Problema**: nelle nuove versioni di transformers, `CLIPModel.get_text_features(**inputs)` non restituisce più
un `torch.Tensor`, ma un oggetto `BaseModelOutputWithPooling`.
Quindi la chiamata a `.squeeze()` genera `AttributeError` e la ricerca semantica fallisce con `Search failed`.

**Sintomo**: `curl /ext/hailo-semantic/api/search?q=girl` → `{"message":"Search failed","status":"error"}`

**Causa**: il valore di ritorno di `_model.get_text_features()` dipende dalla versione di transformers.
Nelle nuove versioni viene restituito l'intero oggetto di output del modello, ed è necessario estrarre manualmente `.pooler_output` ecc.

**Correzione**: modificato `text_encoder.py` per elaborare esplicitamente in 2 passi `text_model()` → `text_projection()`:

```python
# Before (broken)
text_features = _model.get_text_features(**inputs)
vec = text_features.squeeze().numpy()

# After (fixed)
text_out = _model.text_model(**inputs)
text_features = _model.text_projection(text_out.pooler_output)
vec = text_features.squeeze().numpy()
```

**Performance**:
- Prima query (incl. caricamento modello): ~6 secondi
- Dalla seconda in poi: ~100-170ms (solo inferenza CPU)
- Ricerca vettoriale: <1ms (51 elementi, cache in memoria)

### 2. Loop di retry infinito durante la costruzione dell'indice

**Problema**: i file che fallivano la decodifica (non-immagine, corrotti, ecc.) non venivano tracciati come `failed_ids`,
quindi `get_unindexed_file_ids()` ogni volta restituiva gli stessi file falliti e il conteggio errori superava i 3 milioni.

**Correzione**: aggiunto `failed_ids: set` in `indexer.py`. Registra i file_id falliti ed esclude dal batch successivo.

### 3. Fallimento nel caricamento di immagini da file archivio

**Problema**: `cv2.imread('test.7z!image.png')` non comprende i path di membri di archivio.

**Correzione**: in `image_preprocess.py` uso di `is_archive_member()` per rilevare i path di archivio,
quindi passaggio al pattern `read_bytes_from_zip` / `read_bytes_from_7z` + `cv2.imdecode()`.

### 4. Aggiornamento di progresso in tempo reale via SSE

**Problema**: il polling a 2 secondi rendeva il progresso a scatti, peggiorando l'esperienza.

**Correzione**: passaggio a connessione SSE `EventSource`. Aggiornamento in tempo reale tramite evento `semantic_index.progress`.
Con `visibilitychange` si disconnette SSE quando la tab è nascosta e si riconnette al ritorno.

---

## Phase 7: rilevamento oggetti YOLO (2026-03-02)

### Panoramica

A seguire la ricerca semantica CLIP, è stato implementato il rilevamento oggetti YOLO sullo stesso Hailo-10H.
Effettua rilevamento oggetti COCO 80 classi su immagini/video e salva i risultati nella tabella `file_annotations`.

### Design architetturale

#### Problema di condivisione del VDevice

Hailo-10H può avere un solo VDevice per processo, e anche InferModel è esclusivo.
CLIP e YOLO non possono girare contemporaneamente.

**Soluzione**: creato `core/hailo_device_core/device_manager.py`.
- `acquire_device(owner, hef_path)` — se un altro owner sta trattenendo il dispositivo, rilascia automaticamente e passa
- Se stesso owner + stesso HEF, riutilizza (evitando la reinizializzazione)
- Thread-safe con `threading.Lock`
- Refactor di `hailo_inference.py` di CLIP per delegare al device_manager

#### Gestione dei tensori di output YOLO

CLIP ha un solo tensore di output, mentre YOLO ha più tensori di output (uno per testa di ciascun stride).
`device_manager` raccoglie e restituisce i parametri di quantizzazione di tutti gli output.

#### Pipeline di post-processing

Post-processing di YOLO:
1. Dequantizzazione uint8 → float32 (con scale/zero_point per ogni output)
2. Decodifica da grid cell a coordinate pixel (sigmoid + grid offset + stride)
3. Filtro di confidence
4. NMS per classe (pure numpy)
5. Conversione delle coordinate letterbox → coordinate normalizzate sull'immagine originale (0-1)

#### Supporto video

Estrazione frame con ffmpeg → rilevamento indipendente per ciascun frame → aggregazione per classe.
Si mantengono la confidence massima per classe e il numero di frame in cui compare.

### Struttura dei nuovi moduli

| Modulo | Ruolo |
|---|---|
| `core/hailo_device_core/device_manager.py` | Gestione del ciclo di vita del VDevice condiviso |
| `core/hailo_yolo_core/hailo_yolo_inference.py` | Singleton YOLODetector |
| `core/hailo_yolo_core/yolo_postprocess.py` | NMS, box decode, dequantize |
| `core/hailo_yolo_core/yolo_labels.py` | Etichette delle 80 classi COCO |
| `core/hailo_yolo_core/yolo_preprocess.py` | Letterbox resize 640x640 |
| `core/hailo_yolo_core/yolo_video.py` | Estrazione frame video + aggregazione |
| `core/hailo_yolo_core/yolo_indexer.py` | Rilevamento batch in background |
| `core/hailo_yolo_core/model_download.py` | Download HEF |
| `core/hailo_yolo_core/event_handler.py` | Handler scan.complete |
| `extensions/builtin_hailo_yolo_detect/` | Extension + Blueprint API + UI |

### Note tecniche

- **Tensori di output multipli**: l'HEF YOLO ha più tensori di output (testa per ciascun stride).
  Bisogna scorrere `infer_model.outputs` e raccogliere tutti gli shape/quant_params
- **Buffer di output**: allocare un buffer uint8 separato per ciascun tensore di output e
  collegare specificando il nome con `bindings.output(out.name).set_buffer(buf)`
- **Layout dei tensori**: tipicamente la forma è `(1, H, W, C)`. In C sono memorizzati bbox (4) + class scores (80)
- **Download HEF**: scaricato direttamente da Hailo Model Zoo v5.2.0. Senza impostare lo User-Agent
  viene bloccato da Cloudflare, quindi si imposta `_USER_AGENT`
- **Salvataggio dei risultati**: salvati come array JSON in `file_annotations` con
  `source='hailo:<model>'`, `key='detections'`. Viene riutilizzata l'API CRUD di annotations esistente

---

## Phase 8: integrazione GenAI (LLM / VLM / Speech2Text) (2026-03-02)

### Obiettivo

Integrare il modulo `hailo_platform.genai` (LLM, VLM, Speech2Text) di Hailo-10H nel
device_manager e rendere generazione testuale, comprensione immagini e trascrizione audio utilizzabili dalla WebUI.

### Estensioni di device_manager

- **Problema**: il device_manager esistente supportava solo l'InferModel API (CLIP/YOLO).
  Le classi GenAI non sono InferModel ma ricevono direttamente VDevice, in un altro modo
- **Soluzione**: distinzione del mode con la variabile `_mode` (`"infer"` | `"genai"`).
  Aggiunta `acquire_genai(owner, model_path, genai_factory)` che tramite pattern factory
  crea istanze di LLM/VLM/S2T
- **Differenze nel release**:
  - InferModel: `del configured` → `del infer_model` → `del vdevice`
  - GenAI: `instance.release()` → `vdevice.release()` (metodo release esplicito)

### Scoperte sulle API GenAI

- **Formato messaggi**: struttura role/content compatibile con OpenAI. content è un array nel formato `{"type": "text", "text": "..."}`
- **Input immagine VLM**: numpy array RGB uint8 336x336. Passato come lista con `frames=[image]`.
  Nel prompt si inserisce un placeholder `{"type": "image"}`
- **Input S2T**: float32 little-endian (`<f4`), mono, 16kHz. Normalizzazione int16→float32 obbligatoria
- **Segmenti S2T**: `generate_all_segments()` restituisce una lista di oggetti `SegmentInfo`.
  Hanno attributi `.text`, `.start`, `.end`
- **Gestione del contesto**: LLM/VLM gestiscono la finestra di contesto con `get_context_usage_size()`, `max_context_capacity()`,
  `clear_context()`
- **Streaming**: `generate()` restituisce un iteratore, yield per ciascun token

### URL di download dei HEF dei modelli

- Pattern: `https://dev-public.hailo.ai/v{hailort_version}/blob/{ModelName}.hef`
- HailoRT 5.2.0 → `v5.2.0`
- Nomi dei modelli in CamelCase (es. `Qwen2.5-1.5B-Instruct.hef`, `Whisper-Base.hef`)
- Confermato nel source type `gen-ai-mz` di `download_resources.py` di `hailo-apps-infra`

### Nuovi file

| File | Descrizione |
|----------|------|
| `core/hailo_genai_core/__init__.py` | Init del package |
| `core/hailo_genai_core/genai_types.py` | enum GenAIModelType + dataclass GenAIModelInfo |
| `core/hailo_genai_core/model_download.py` | Gestione del download HEF per 7 modelli |
| `core/hailo_genai_core/llm_inference.py` | Wrapper HailoLLM (singleton, streaming) |
| `core/hailo_genai_core/vlm_inference.py` | Wrapper HailoVLM (singleton, preprocessing immagini) |
| `core/hailo_genai_core/s2t_inference.py` | Wrapper HailoS2T (singleton, supporto segmenti) |
| `extensions/builtin_hailo_genai/extension.json` | Manifesto Extension |
| `extensions/builtin_hailo_genai/hailo_genai_ext.py` | Blueprint con 8 API (SSE streaming) |
| `extensions/.../templates/hailo_genai/_genai_ui.html` | UI della pagina Tools (4 pannelli) |

### Note tecniche

- **VDevice.create_params()**: in modalità GenAI si creano i parametri con `VDevice.create_params()` e
  si istanzia con `VDevice(params)`. Differisce dal `VDevice()` (senza argomenti) della modalità InferModel
- **SSE streaming**: con `Response(generator(), mimetype='text/event-stream')` di Flask
  si invia `data: {"token": "..."}\n\n` per ciascun token. Al completamento `data: {"done": true}\n\n`
- **Invio FormData per VLM**: per mandare contemporaneamente file immagine + prompt testo,
  l'API VLM non usa JSON ma `multipart/form-data`
- **Lettura WAV in S2T**: lato server, lettura diretta dal byte stream WAV caricato con
  modulo `wave` + `io.BytesIO`

---

## Phase 9: integrazione ricerca semantica + caption VLM (2026-03-03)

### Obiettivo

Generare caption in batch con VLM (Qwen2-VL) per le immagini risultanti dalla ricerca CLIP
e salvarle in `file_annotations`.

### Implementazione

- **`core/hailo_clip_core/caption_runner.py`** *(attualmente `extensions/builtin_hailo_semantic_search/core_impl/caption_runner.py`)* (~150 righe): esecuzione batch della generazione caption VLM in thread in background. Segue il pattern `_state_lock` + `_stop_requested` + `_progress` di `indexer.py`. Eventi SSE `vlm_caption.start/progress/complete`
- **Estensione Blueprint**: aggiunti 3 endpoint in `hailo_semantic_search.py`: `/api/caption/start`, `/api/caption/status`, `/api/caption/stop`
- **UI**: nella sezione Semantic Search della pagina Tools aggiunto il pannello "VLM Caption Generation". Input prompt, barra di progresso SSE, collegamento automatico ai file_ids dei risultati di ricerca

### Controllo esclusivo del VDevice

- Acquisizione di VLM con `acquire_genai("vlm", ...)`. Se l'indexer CLIP è attivo viene rilasciato automaticamente dal normale comportamento di device_manager
- Dopo il completamento della caption VLM mantiene il dispositivo, quindi per riavviare l'indicizzazione CLIP è necessario scaricare il modello

### Convenzioni di salvataggio delle annotation

- `source="hailo:vlm"`, `key="caption"`, `value=<testo caption>`

---

## Phase 10: trascrizione audio video — pipeline S2T (2026-03-03)

### Obiettivo

Estrazione audio dai file video con ffmpeg → trascrizione con Whisper (S2T) → salvataggio in `file_annotations`.

### Implementazione

- **`core/files_core/video_audio.py`** (~80 righe): `extract_audio_wav()` estrae audio via ffmpeg (mono PCM s16le 16kHz). Calcolo dinamico del timeout in base alla duration del video (max 120 secondi). `check_ffmpeg()` riutilizzato da `media_video.py`
- **Estensione Blueprint**: aggiunti 3 endpoint in `hailo_genai_ext.py`:
  - `POST /api/s2t/transcribe-video`: trascrizione di un singolo video (file_id, language)
  - `POST /api/s2t/batch-transcribe`: trascrizione batch di più video (file_ids, language), thread background + progresso SSE (`video_s2t.*`)
  - `GET /api/s2t/transcript/<file_id>`: recupero della trascrizione salvata
- **UI**: aggiunta sottosezione "Video Transcription" nel pannello S2T. Input file_id, selezione lingua (ja/en), pulsante di recupero salvati

### Convenzioni di salvataggio delle annotation

- `source="hailo:s2t"`, `key="transcript"`, `value=<testo completo>`
- `source="hailo:s2t"`, `key="transcript_segments"`, `value=<JSON [{text, start, end}, ...]>`

### Note

- WAV temporaneo creato con `tempfile.NamedTemporaryFile`, sempre eliminato nel finally
- S2T e LLM/VLM sono esclusivi sul dispositivo (non utilizzabili contemporaneamente)

---

## Phase 11: miglioramento UI conversazione multi-turn LLM (2026-03-03)

### Obiettivo

Estendere il prompt singolo al supporto della cronologia di conversazione. Continuazione/reset del contesto, UI a bolle.

### Implementazione

- **Modifiche API**: `api_llm_generate()` ora accetta un array `messages`. Backward compat: se è presente solo `prompt`, lo converte come in passato in messaggio system + user. `generate_stream()` supporta già multi-turn (via `_normalise_prompt()`)
- **UI chat a bolle**: `hg-chat-container` + `hg-bubble` (user=viola a destra, AI=grigio a sinistra). Classi CSS: `hg-bubble-user`, `hg-bubble-ai`, `hg-bubble-label`
- **Gestione della cronologia**: lato JS array `_chatHistory = []` accumula `{role, content}`. All'invio all'API passa `messages: [systemMsg, ..._chatHistory]`. `hgLlmClear()` resetta l'array + esegue clear context HailoRT
- **Streaming**: la bolla AI viene inserita prima nel DOM e i token SSE vengono via via accodati

### Bug fix: errore system role nelle conversazioni multi-turn (2026-03-03)

Scoperto tramite MCP debug query + log di hailort. Alle chiamate `generate()` dal secondo turno in poi si verificava il seguente errore:

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_INVALID_OPERATION(6)
```

**Causa**: il template UI inviava ogni volta il system role in testa con `[systemMsg].concat(_chatHistory)`. L'API LLM di HailoRT non accetta il system role in presenza di contesto (dal secondo turno).

**Correzione**:
1. Aggiunto metodo `_prepare_prompt()` in `llm_inference.py`: se `get_context_usage_size() > 0`, esclude automaticamente i messaggi system role
2. Nel template UI (`_genai_ui.html`): aggiunge il system solo quando `_chatHistory.length <= 1` (solo primo messaggio utente)

**Nota tecnica**: come vincolo di HailoRT, `LLM.generate()` elabora il system role solo alla prima chiamata. È un comportamento diverso dalle API OpenAI, di cui bisogna tenere conto implementando conversazioni multi-turn.

---

## Test sul campo WD-Tagger VLM × Hailo-10H (2026-03-03)

### Ambiente di test
- Raspberry Pi 5 + Hailo AI HAT 2 (Hailo-10H)
- HailoRT FW 5.2.0, hailo_platform Python 5.2.0
- hailo-ollama v0.5.1 (versione compilata)
- Qwen2-VL-2B-Instruct.hef (3.0 GB)

### Scoperta importante: hailo-ollama non supporta VLM

Documentazione ufficiale di hailo-ollama (USAGE.rst) chiara:
> "The Hailo-Ollama API is currently limited to language models (LLMs) and cannot be used for VLMs."

Anche nella tabella MODELS la colonna Inference API di `Qwen2-VL-2B-Instruct` riporta solo "C++, Python", senza "Hailo-Ollama".

Elenco modelli restituito da `/hailo/v1/list`:
```
deepseek_r1:1.5b, llama3.2:1b, qwen2.5-coder:1.5b, qwen2.5:1.5b, qwen2:1.5b
```
`qwen2-vl` non è incluso.

### Risultati test hailo-ollama

**Note sul config**: la versione compilata usa la macro `NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE` e richiede obbligatoriamente la chiave `limits` nel config JSON. Non è inclusa nel template ufficiale, quindi va aggiunta così:
```json
"limits": {"max_in_flight": 4, "max_queue": 10, "retry_after_sec": 1}
```

- **Generazione testuale LLM (qwen2.5:1.5b)**: OpenAI + Ollama native entrambi OK, 6.5 TPS
- **Richiesta vision API OpenAI**: errore 500 (`Node is NOT a STRING`)
- **API Ollama native + images**: accettata ma l'LLM non sa elaborare immagini
- **Fallback VlmWdTaggerEngine**: OpenAI 500 → switch automatico a Ollama native OK
- **response_format: json_object**: accettato ma non obbliga l'output JSON

### Risultati test diretti VLM con Hailo Python SDK

Il VLM richiede `{"type": "image"}` nel formato messaggi:
```python
messages = [
    {"role": "user", "content": [
        {"type": "image"},
        {"type": "text", "text": "Tag this image."}
    ]}
]
vlm.generate_all(messages, frames=[frame_336x336_rgb_uint8])
```

- **Caricamento modello**: 33 secondi (primo cold start. Differenza rispetto ai 6.2 secondi nominali dominata da I/O disco)
- **Velocità di inferenza**: ~5.1 TPS (128 token / 20 secondi). La differenza rispetto ai 6.73 TPS nominali è dovuta all'inclusione del TTFT
- **Precisione di riconoscimento**: comprensione corretta del contenuto (descrive con precisione "due donne che si tengono per mano in un paesaggio innevato")
- **Qualità dell'output JSON**: bassa. Con un modello 2B la generazione di JSON strutturato è instabile (virgole mancanti, code fence markdown misti)

### Bug trovati

1. **Formato prompt in `engines_hailo_vlm.py`**: passava al VLM messaggi solo testo → corretto in lista contenente `{"type": "image"}`
2. **Argomento frames in `vlm_inference.py`**: `generate_all()` di VLM richiede `frames`, ma era dichiarato Optional → reso obbligatorio

### Note tecniche

- **Vincolo esclusivo del VDevice**: con hailo-ollama attivo non si può ottenere `hailo_platform.VDevice()`. Per inferenza VLM diretta bisogna fermare hailo-ollama
- **VLM.generate_all() richiede frames**: l'inferenza solo testo genera errore `HAILO_INVALID_OPERATION`. LLM e VLM hanno prerequisiti API diversi
- **Prompt template di Qwen2-VL**: template Jinja2 che inserisce `<|vision_start|><|image_pad|><|vision_end|>`. Se si include `{"type": "image"}` nel formato messaggi, l'SDK lo gestisce automaticamente

---

## Phase 12: API compatibili OpenAI + correzione bug di switch dispositivo (2026-03-14)

### Obiettivi

1. Fornire un'API compatibile OpenAI che permetta a strumenti esterni come OpenAI SDK / LiteLLM / Continue.dev / Open WebUI di utilizzare direttamente Hailo GenAI
2. Correggere le insufficienze di supporto async di Quart
3. Supporto degli endpoint SSE nei tool MCP

### Implementazione: API compatibili OpenAI (`hailo_openai_routes.py`)

Creato il nuovo file `extensions/builtin_hailo_genai/hailo_openai_routes.py`. Implementati i 4 endpoint seguenti:

| Endpoint | Funzione | Modelli supportati |
|---|---|---|
| `GET /v1/models` | Elenco dei modelli disponibili | Tutti i modelli + CLIP |
| `POST /v1/chat/completions` | Chat testo/immagine (supporto stream) | LLM + VLM |
| `POST /v1/audio/transcriptions` | Trascrizione audio | Whisper |
| `POST /v1/embeddings` | Testo → vettore CLIP | CLIP ViT-B/16 |

#### Decisioni di design

- **Supporto Vision**: accetta direttamente il formato OpenAI Vision API (`image_url` with `data:` base64). Inoltre permette di fare riferimento diretto alle immagini della libreria YU con il formato `file_id:123`
- **HTTP URL non supportati**: per prevenire SSRF non vengono accettati `http://` / `https://` in `image_url`
- **Alias di modello**: definiti alias compatibili OpenAI come `whisper-1` → `whisper-base`, `clip` → `clip-vit-b-16`
- **Audio non WAV**: conversione automatica via ffmpeg (16kHz mono PCM16)
- **Campo Usage**: poiché l'SDK Hailo non restituisce il numero di token, fisso a `0`. Margine di miglioramento futuro

#### Tool MCP

- `hailo_genai_openai_info`: tool helper che restituisce l'elenco degli endpoint e le modalità d'uso (generato localmente senza chiamare l'API)

### Correzione: generatori SSE async di Quart

In tutti i file di route, i generatori SSE avevano insufficienze di supporto async:

| File | Problema | Correzione |
|---|---|---|
| `hailo_llm_routes.py` | `def generate_sse()` era funzione sync | Cambiato in `async def`, `get_llm()` e `next(it)` eseguiti con `asyncio.to_thread` |
| `hailo_vlm_routes.py` | Sopra + accesso DB sync | Sopra + wrap con `run_db_sync` |
| `hailo_s2t_routes.py` | transcribe eseguita sync + DB sync | Wrap con `asyncio.to_thread` + `run_db_sync` |
| `hailo_chat_routes.py` | Sopra (sia LLM che VLM) | Tutte le chiamate bloccanti rese async |

In Quart (ASGI) se il generatore non è `async def` blocca l'event loop e durante la trasmissione SSE le altre richieste non vengono processate.

### Bug scoperto: incoerenza dei singleton durante lo switch di dispositivo

#### Sintomo

Chiamando LLM dopo aver usato VLM, errore `'NoneType' object has no attribute 'get_context_usage_size'`. Anche nella direzione inversa (LLM→VLM→LLM) avviene sempre.

#### Analisi della causa

Hailo-10H può contenere un solo VDevice, quindi `device_manager.py` gestisce in esclusiva. Flusso allo switch di modello:

1. `get_vlm()` del VLM → `acquire_genai("vlm", ...)` → internamente `_release_internal()` rilascia il VDevice dell'LLM
2. Utilizzo di VLM completato
3. `get_llm()` dell'LLM → `_instance` rimane + `model_name` corrisponde → **riutilizzo dell'istanza esistente**
4. Il VDevice dietro `_instance._llm` è già stato rilasciato → `get_context_usage_size()` viene chiamato su `None` e crash

Radice del problema: anche se il `_instance` singleton rimane, il VDevice puntato dall'oggetto Hailo SDK interno (`self._llm`) è già `.release()` da `_release_internal()` di `device_manager`. A livello di reference counting di Python `_instance._llm` è ancora vivo, ma le risorse native lato Hailo SDK sono state liberate.

#### Correzione

Aggiunta la verifica `device_manager.get_current_owner()` al controllo di riutilizzo del singleton in `get_llm()` / `get_vlm()` / `get_s2t()`:

```python
def get_llm(model_name="qwen2.5-1.5b-chat"):
    global _instance
    with _lock:
        if _instance is not None and _instance.model_name == model_name:
            from core.hailo_device_core.device_manager import get_current_owner
            if get_current_owner() == "llm":
                return _instance  # Dispositivo trattenuto → riuso OK
            # Il dispositivo è stato preso da un altro modello → ricreare
            _instance = None
        ...
```

Stessa correzione applicata a tutti e 3 i singleton LLM / VLM / S2T.

#### Verifica

Confermato funzionamento normale con 4 switch consecutivi LLM → VLM → LLM → VLM.

### Altre correzioni

- **Metodo MCP `post_sse`**: aggiunto in `mcp_server/client.py` un metodo `post_sse()` che consuma lo stream SSE e restituisce il testo finale come JSON. Usato dai tool `hailo_llm_generate` e `hailo_vlm_generate`
- **Parametro MCP `yolo_search`**: rinominato da `labels` a `class_name` (allineato al nome del parametro lato API)
- **Circuit Breaker**: aggiunti `_READ_SUFFIXES` (`_status`, `_info`, `_list`, `_stats`). In stato half_open i tool di stato come `hailo_genai_status` sono ora consentiti
- **Semantic Search async**: `get_encoder_info()` e `semantic_search()` wrappati con `run_db_sync` (per prevenire il blocco dell'event loop Quart)

### Note tecniche

- **Il vincolo esclusivo del VDevice è a livello SDK**: anche mantenendo un riferimento all'oggetto lato Python, se le risorse native dell'Hailo SDK vengono rilasciate non si può più usare. Se si usa un pattern singleton, bisogna verificare separatamente la validità delle risorse native
- **Quart + generatori sync**: se si passa un generatore sync a una response SSE di Quart funziona, ma l'elaborazione tra i `yield` blocca l'event loop. Elaborazioni pesanti come l'inferenza Hailo vanno sempre spostate in un altro thread con `asyncio.to_thread`
- **Integrazione OpenAI Vision API e VLM**: OpenAI Vision API riceve le immagini nel campo `image_url`, ma Hailo VLM riceve `frames` (numpy array). Nel layer di conversione si esegue: decodifica base64 → decodifica OpenCV → resize RGB 336x336
