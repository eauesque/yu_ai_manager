# Note di Migrazione da HailoRT 5.2.0 a 5.3.0

Conoscenze acquisite dall'aggiornamento da HailoRT 5.2.0 a 5.3.0 su Raspberry Pi 5 + AI HAT 2 (Hailo-10H). Basate su test di implementazione end-to-end e analisi diretta del git diff dei tag ufficiali `v5.2.0` / `v5.3.0`.

**Destinatari**: Sviluppatori che eseguono inferenza su Hailo-10H NPU utilizzando Python (`pyhailort`).

---

## TL;DR

- **Sostanzialmente zero breaking change per applicazioni Python di inferenza tipiche**. I numeri headline (688 file modificati, +12,035 / −8,987 righe) sembrano molti, ma le superfici di `VDevice`, `InferModel` e GenAI (`LLM` / `VLM` / `Speech2Text`) sono completamente retrocompatibili.
- La maggior parte delle modifiche riguarda **eliminazione delle API camera/ISP/firmware management di Hailo-8** e refactoring interno. Nessun impatto sull'inferenza NPU pura.
- **I file `.hef` dell'epoca v5.2.0 vengono caricati ed eseguiti senza modifiche sul runtime 5.3.0.** Verificato su 5 modelli (YOLOv8n, CLIP ViT-B/16, Qwen2.5-1.5B, Qwen2-VL-2B, Whisper-Base).
- Il driver Linux è cambiato da `hailo_pci` a `hailo1x_pci`, e il nodo dispositivo da `/dev/hailort0` a **`/dev/h1x-0`**. Poiché `pyhailort` risolve internamente il nuovo nodo, il codice Python che usa `VDevice()` funziona senza modifiche. **Solo il passthrough del dispositivo Docker richiede aggiornamento.**
- `Speech2Text.SegmentInfo` espone gli attributi `text` / `start_sec` / `end_sec` (identico a v5.2.0). `start` e `start_time` non sono esposti; il codice difensivo che usa questi nomi restituisce silenziosamente 0.0.

---

## 1. Portata delle Modifiche

Diff diretto tra i tag `v5.2.0` e `v5.3.0` del repository HailoRT ufficiale su GitHub:

| Portata | File | Aggiunte | Eliminazioni |
|---------|------|----------|--------------|
| Totale | 688 | +12,035 | −8,987 |
| Header C++ pubblici (`include/hailo/`) | 27 | +205 | **−383** |
| Binding Python (`bindings/python/`) | 35 | +306 | **−413** |
| Solo `pyhailort.py` | 1 | +98 | **−158** |

**Le eliminazioni superano le aggiunte.** Questo è un rilascio di "semplificazione". La maggior parte di ciò che è stato eliminato non riguarda il percorso di inferenza NPU.

---

## 2. API Eliminate — Solo Camera/ISP/Firmware Hailo-8

`hailort/libhailort/include/hailo/device.hpp` perde 169 righe, `platform.h` perde 75 righe. Tutto ciò che è stato eliminato riguarda il controllo dispositivo a basso livello:

- `firmware_update()` / `second_stage_update()` (riscrittura firmware)
- `store_sensor_config()` / `store_isp_config()`
- `sensor_dump_config()` / `sensor_reset()`
- `sensor_load_and_start_config()`
- `sensor_set_i2c_bus_index()` / `sensor_set_generic_i2c_slave()`
- `sensor_get_sections_info()`
- `examine_user_config()` / `read_user_config()` / `write_user_config()` / `erase_user_config()`

Queste sono tutte API per **Hailo-8 AI Vision Camera Module** (schede SoC in cui il chip Hailo controlla direttamente ISP e sensore immagine). Non vengono chiamate nel tipico flusso `VDevice` → `InferModel` → `generate` su Hailo-10H NPU bare.

**Impatto**: Zero per le applicazioni di inferenza NPU pura. Solo le applicazioni che controllano effettivamente i moduli camera Hailo-8 devono verificare l'utilizzo.

---

## 3. Modifiche alle Signature Python

| API | v5.2.0 | v5.3.0 | Compatibilità |
|-----|--------|--------|---------------|
| `Speech2Text.generate_all_segments(timeout_ms=)` | Default `10000` | Default `600000` | Compatibile — solo default, chiamate esistenti invariate |
| `Speech2Text.generate_all_text(timeout_ms=)` | Stesso | Stesso | Compatibile |
| `LLM.read_all(timeout_ms=10000)` | Con default | Default **rimosso** (obbligatorio) | **Attenzione** `read_all()` senza argomenti → `TypeError` |
| `DeviceArchitecture.__init__` | 9 argomenti posizionali | +`chip_serial_number` (10) | **Attenzione** — costruzione diretta si rompe |

**La correzione di `read_all()` è una modifica di una riga**:

```python
# Prima (stile v5.2.0, default 10 secondi)
text = generator.read_all()

# Dopo (v5.3.0 richiede timeout esplicito)
text = generator.read_all(timeout_ms=600000)  # 10 minuti
```

`DeviceArchitecture` viene raramente costruito direttamente nel codice utente, quindi la sua modifica della signature ha poco impatto.

---

## 4. Cambiamenti nei Nomi degli Header C++ (Trasparenti Tramite Python)

Breaking per applicazioni che usano HailoRT direttamente da C++:

- **`Speech2Text::DEFAULT_OPERATION_TIMEOUT`** (10 secondi) → **`DEFAULT_GENERATE_ALL_TIMEOUT`** (10 minuti), rinominato e esteso
- **`LLM::DEFAULT_READ_ALL_TIMEOUT`** aggiunto, anch'esso 10 minuti
- 4 overload `generate_from_embeddings()` aggiunti a `vlm.hpp`

Questi cambiamenti non si propagano attraverso i binding Python.

---

## 5. Correzione delle Coordinate Bounding Box NMS (Cambiamento di Comportamento)

Correzione della logica di post-processing NMS in `pyhailort.py`:

```python
# v5.2.0
y_min = numpy.ceil(bbox[0] * image_height)
x_min = numpy.ceil(bbox[1] * image_width)
bbox_width = numpy.ceil((bbox[3] - bbox[1]) * image_width)

# v5.3.0
y_min = int(max(numpy.floor(bbox[0] * image_height), 0))
x_min = int(max(numpy.floor(bbox[1] * image_width), 0))
x_max = int(min(numpy.ceil(bbox[3] * image_width), image_width))
bbox_width = x_max - x_min
```

Miglioramenti:

- Clipping ai bordi dell'immagine `max(0, …)` / `min(image_width, …)` aggiunto
- Da `ceil` a `floor` (prevenzione overshoot)
- `bbox_width` ricalcolato da `x_max - x_min` clippato

**Differenza di comportamento**: Con lo stesso modello e la stessa immagine, l'output NMS può spostarsi di ±1 pixel vicino ai bordi dell'immagine.

---

## 6. Nuove API (Additive)

- **`VDevice::create_session(uint16_t port)`** — API sessione di inferenza basata su rete (nuova funzionalità)
- **`VLM::generate_from_embeddings()`** — 4 overload. Accetta embedding pre-calcolati di immagini/video come input `MemoryView`. Permette il riutilizzo degli embedding in più chiamate VLM.
- **`InferModel::set_nms_classes_filter_mask(vector<bool>)`** — Filtraggio a livello di classe per l'output NMS (on-chip)
- **`Device::query_performance_stats(sampling_period_ms)`** — Periodo di campionamento configurabile
- **`Device::get_current_limit()`** — Interrogazione del limite di corrente
- **`DeviceArchitecture.chip_serial_number`** — Lettura del numero seriale del chip

Tutte additive, quindi il codice esistente non si rompe.

---

## 7. Modifiche all'Ambiente

### 7.1 Nuovo Driver PCI Linux

| Elemento | Vecchio | Nuovo |
|----------|---------|-------|
| Modulo kernel | `hailo_pci` | `hailo1x_pci` |
| Nodo dispositivo | `/dev/hailort0` (o `/dev/hailo0`) | `/dev/h1x-0` |

```bash
lsmod | grep hailo        # → hailo1x_pci
ls /dev/h1x-*             # → /dev/h1x-0
```

**`pyhailort` risolve internamente il nuovo nodo del dispositivo**, quindi il codice Python che usa `VDevice()` continua a funzionare senza modifiche. Solo il codice che apre direttamente `/dev/hailo*` o `/dev/hailort0` richiede aggiornamento.

#### Passthrough Docker/Podman

Aggiorna la dichiarazione di passthrough del dispositivo:

```yaml
# docker-compose.yml
services:
  my-app:
    devices:
      - /dev/h1x-0:/dev/h1x-0   # era: /dev/hailort0:/dev/hailort0
```

Aggiorna anche le righe `DeviceAllow=` dei unit systemd e le regole udev.

### 7.2 Vincolo numpy Allentato

- v5.2.0 `setup.py`: `numpy<2` (fisso)
- v5.3.0 `setup.py`: `numpy` (senza limite superiore)

Le applicazioni precedentemente fissate su numpy 1.x possono ora aggiornare a numpy 2.x insieme all'aggiornamento di HailoRT.

### 7.3 Compatibilità Binaria HEF

**I file `.hef` scaricati dal bucket v5.2.0 vengono caricati ed eseguiti senza modifiche sul runtime 5.3.0.** Verificato su 5 modelli (Raspberry Pi 5 + AI HAT 2):

| Modello | File | Risultato |
|---------|------|-----------|
| YOLOv8n | `yolov8n.hef` | `create_infer_model()` + `.run()` |
| CLIP ViT-B/16 image encoder | `clip_vit_b_16_image_encoder.hef` | Output 512 dimensioni |
| Qwen2.5-1.5B Instruct | `Qwen2.5-1.5B-Instruct.hef` | `LLM.generate_all()` restituisce testo valido |
| Qwen2-VL-2B Instruct | `Qwen2-VL-2B-Instruct.hef` | `VLM.generate_all(frames=[…])` restituisce testo valido |
| Whisper-Base | `Whisper-Base.hef` | `Speech2Text.generate_all_segments()` restituisce `SegmentInfo` |

### 7.4 Bucket URL di Download HEF

Hailo Developer Zone (`dev-public.hailo.ai`) ospita parallelamente i bucket v5.2.0 e v5.3.0:

```
https://dev-public.hailo.ai/v5.2.0/blob/<model>.hef
https://dev-public.hailo.ai/v5.3.0/blob/<model>.hef
```

Stato del bucket v5.3.0 al 2026-04-06:

| Modello | Bucket v5.3.0 |
|---------|--------------|
| Qwen2.5-1.5B-Instruct | 200 |
| DeepSeek-R1-Distill-Qwen-1.5B | 200 |
| Qwen2.5-Coder-1.5B-Instruct | 200 |
| Qwen2-VL-2B-Instruct | 200 |
| Whisper-Base / Whisper-Small | 200 |
| **Llama-3.2-1B-Instruct** | **404** |

→ Le applicazioni che necessitano di Llama-3.2-1B devono ancora recuperarlo dal bucket v5.2.0. Gli HEF v5.2.0 si caricano correttamente sul runtime 5.3.0.

---

## 8. Nomi degli Attributi di `Speech2Text.SegmentInfo`

Sia in v5.2.0 che in v5.3.0, `Speech2Text.generate_all_segments()` restituisce oggetti `SegmentInfo` con questi attributi pubblici:

```python
seg.text        # str
seg.start_sec   # float (secondi)
seg.end_sec     # float (secondi)
```

**`seg.start` e `seg.start_time` non esistono.** La vecchia documentazione e il codice di esempio a volte fa riferimento a questi nomi, ma causano `AttributeError`, o peggio, restituiscono silenziosamente 0.0 quando wrappati in codice difensivo come `getattr(seg, "start", 0.0)`.

Per verificare i nomi effettivi degli attributi sul runtime:

```python
from hailo_platform import VDevice
from hailo_platform.genai import Speech2Text, Speech2TextTask
import numpy as np

vd = VDevice()
s2t = Speech2Text(vd, "/path/to/Whisper-Base.hef")
audio = (np.random.default_rng(0).standard_normal(32000) * 0.01).astype("<f4")
segments = s2t.generate_all_segments(
    audio_data=audio, task=Speech2TextTask.TRANSCRIBE,
    language="en", timeout_ms=30000,
)
if segments:
    print([a for a in dir(segments[0]) if not a.startswith("_")])
    # => ['end_sec', 'start_sec', 'text']
```

---

## 9. Script di Smoke Test

Script minimale per verificare che l'ambiente funzioni effettivamente dopo l'aggiornamento a 5.3.0:

```python
"""HailoRT 5.3.0 smoke test — VDevice / InferModel / LLM / Speech2Text."""
import numpy as np
from hailo_platform import VDevice

# 1. Creazione VDevice
params = VDevice.create_params()
params.group_id = "SMOKE_TEST"
vd = VDevice(params)
print("1. VDevice OK")

# 2. Percorso InferModel (YOLOv8n o qualsiasi HEF esistente)
im = vd.create_infer_model("/path/to/yolov8n.hef")
conf = im.configure()
inp = im.inputs[0]
bindings = conf.create_bindings()
bindings.input().set_buffer(np.zeros(tuple(inp.shape), dtype=np.uint8))
for o in im.outputs:
    fmt = str(getattr(o.format, "type", "")).lower()
    dtype = np.float32 if "float" in fmt else np.uint8
    bindings.output(o.name).set_buffer(np.zeros(tuple(o.shape), dtype=dtype))
conf.run([bindings], timeout=10000)
print("2. InferModel (YOLO) OK")
del conf, im

vd.release()
del vd

# 3. Percorso GenAI LLM
from hailo_platform.genai import LLM
params = VDevice.create_params(); params.group_id = "SMOKE_TEST"
vd = VDevice(params)
llm = LLM(vd, "/path/to/Qwen2.5-1.5B-Instruct.hef")
text = llm.generate_all(
    prompt=[{"role": "user", "content": "Say hi in one word."}],
    temperature=0.1, max_generated_tokens=16,
)
print(f"3. LLM OK: {text!r}")
llm.release(); vd.release()

# 4. Percorso Speech2Text
from hailo_platform.genai import Speech2Text, Speech2TextTask
params = VDevice.create_params(); params.group_id = "SMOKE_TEST"
vd = VDevice(params)
s2t = Speech2Text(vd, "/path/to/Whisper-Base.hef")
audio = (np.random.default_rng(0).standard_normal(32000) * 0.01).astype("<f4")
segments = s2t.generate_all_segments(
    audio_data=audio, task=Speech2TextTask.TRANSCRIBE,
    language="en", timeout_ms=30000,
)
print(f"4. Speech2Text OK: {len(segments)} segments")
if segments:
    seg = segments[0]
    print(f"   attrs: text={seg.text!r} start_sec={seg.start_sec} end_sec={seg.end_sec}")
s2t.release(); vd.release()

print("\nAll smoke tests passed.")
```

---

## 10. Checklist di Aggiornamento

Punti da verificare nel codice prima o durante l'aggiornamento da 5.2.0 a 5.3.0:

- [ ] `VDevice()` / `create_infer_model()` / `InferModel.configure()` — **Nessuna modifica necessaria**
- [ ] Costruttori `LLM(vd, path)` / `VLM(vd, path)` / `Speech2Text(vd, path)` — **Nessuna modifica necessaria**
- [ ] Argomenti keyword di `LLM.generate()` / `.generate_all()` / `VLM.generate(frames=…)` / `.generate_all()` — **Nessuna modifica necessaria**
- [ ] `Speech2Text.generate_all_segments(audio_data=, task=, language=, timeout_ms=)` — **Nessuna modifica necessaria** (se `timeout_ms` è già passato esplicitamente)
- [ ] Verificare se si chiama `LLM.read_all()` senza argomento `timeout_ms` → se sì, aggiungere timeout esplicito
- [ ] Verificare se si costruisce `DeviceArchitecture` direttamente → se sì, aggiungere `chip_serial_number`
- [ ] grep per apertura diretta di `/dev/hailo*` o `/dev/hailort0` → se trovato, sostituire con `/dev/h1x-0`
- [ ] Aggiornare le sezioni `devices:` di Docker/Podman a `/dev/h1x-0`
- [ ] Aggiornare le righe `DeviceAllow=` dei unit systemd e le regole udev
- [ ] grep per accesso agli attributi `SegmentInfo` `.start` o `.start_time` → passare a `.start_sec` / `.end_sec`
- [ ] Se numpy era fissato a 1.x (per `numpy<2` di v5.2.0), ora è possibile rimuovere il pin
- [ ] I file `.hef` esistenti **non devono essere riscaricati**
- [ ] Se gli URL di download HEF erano hardcodati con il bucket `v5.2.0`, aggiornare a `v5.3.0` (mantenere v5.2.0 per Llama-3.2-1B)
- [ ] Se si dipende dal post-processing NMS integrato di pyhailort, notare che i bounding box vicino ai bordi potrebbero spostarsi di ±1 pixel

---

## 11. Comandi Usati per l'Analisi

Presuppone che il repository HailoRT ufficiale sia clonato:

```bash
cd ~/hailort

# Dimensione complessiva del diff
git diff --stat v5.2.0 v5.3.0 | tail

# Diff degli header C++ pubblici
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/'

# Diff dei binding Python
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/bindings/python/'

# Diff completo di pyhailort.py
git diff v5.2.0 v5.3.0 -- \
  'hailort/libhailort/bindings/python/platform/hailo_platform/pyhailort/pyhailort.py'

# Diff API pubblica di un header specifico (solo signature di funzioni)
git diff v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/genai/llm/llm.hpp' \
  | grep -E '^[+-]' | grep -E 'Expected|hailo_status|void|static'

# API eliminate da device.hpp
git diff v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/device.hpp' \
  | grep '^-' | grep 'virtual'
```

---

## 12. Conclusione

Il titolo "688 file modificati" è lontano dall'impatto reale. Su una tipica applicazione di inferenza NPU Hailo-10H:

- **Le API di inferenza NPU core (`VDevice` / `InferModel` / GenAI) sono completamente retrocompatibili**
- Tutte le API eliminate riguardano le superfici di gestione camera/sensore/ISP/firmware di Hailo-8
- **Tutti i file `.hef` esistenti si caricano senza ri-download**
- L'unica modifica obbligatoria a livello di ambiente è aggiornare il passthrough del dispositivo Docker a `/dev/h1x-0`

Principali miglioramenti della qualità della vita dopo l'aggiornamento:

- I timeout predefiniti sono aumentati notevolmente (da 10 secondi a 10 minuti), riducendo i falsi timeout nelle generazioni di testo lunghe
- `FormatType.FLOAT32` ora disponibile (in v5.2.0 era richiesta la quantizzazione/dequantizzazione manuale)
- Correzione del bug di clipping delle coordinate NMS
- Percorso di aggiornamento a numpy 2.x aperto
- `VLM.generate_from_embeddings()` permette di riutilizzare gli embedding pre-calcolati in più chiamate VLM
