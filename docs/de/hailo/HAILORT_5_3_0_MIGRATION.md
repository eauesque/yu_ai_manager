# HailoRT 5.2.0 → 5.3.0 Migrationshinweise

Erkenntnisse aus dem Upgrade von HailoRT 5.2.0 auf 5.3.0 auf dem Raspberry Pi 5 + AI HAT 2 (Hailo-10H). Basiert auf End-to-End-Implementierungstests und direkter Git-Diff-Analyse der offiziellen Tags `v5.2.0` / `v5.3.0`.

**Zielgruppe**: Entwickler, die Python (`pyhailort`) für Inferenz auf der Hailo-10H NPU verwenden.

---

## TL;DR

- **Praktisch keine Breaking Changes für typische Python-Inferenzanwendungen**.
  Die Schlagzahl (688 geänderte Dateien, +12.035 / -8.987 Zeilen) ist groß, aber
  die Oberflächen von `VDevice`, `InferModel` und GenAI (`LLM` / `VLM` / `Speech2Text`) sind vollständig rückwärtskompatibel.
- Der Großteil der Änderungen ist die **Entfernung von Hailo-8-Kamera-/ISP-/Firmware-Verwaltungs-APIs**
  und internes Refactoring. Für reine NPU-Inferenz nicht relevant.
- **`.hef`-Dateien aus der v5.2.0-Zeit werden unverändert unter dem 5.3.0-Runtime geladen.**
  Verifiziert mit fünf Modellen (YOLOv8n, CLIP ViT-B/16, Qwen2.5-1.5B, Qwen2-VL-2B, Whisper-Base).
- Der Linux-Treiber wurde von `hailo_pci` zu `hailo1x_pci` umbenannt, der Device-Node von
  `/dev/hailort0` zu **`/dev/h1x-0`**. `pyhailort` löst den neuen Node intern auf,
  daher müssen Python-Code, der `VDevice()` verwendet, nicht geändert werden. **Nur Docker-Geräte-Passthrough muss aktualisiert werden.**
- `Speech2Text.SegmentInfo` stellt `text` / `start_sec` / `end_sec` bereit
  (gleich wie v5.2.0). `start` oder `start_time` sind nicht öffentlich zugänglich.

---

## 1. Änderungsumfang

Direkter Diff zwischen den Tags `v5.2.0` und `v5.3.0` im offiziellen HailoRT-GitHub-Repository:

| Umfang | Dateien | Hinzugefügt | Entfernt |
|---|---:|---:|---:|
| Gesamt | 688 | +12.035 | -8.987 |
| Öffentliche C++-Header (`include/hailo/`) | 27 | +205 | **-383** |
| Python-Bindings (`bindings/python/`) | 35 | +306 | **-413** |
| Nur `pyhailort.py` | 1 | +98 | **-158** |

**Entfernt übertrifft hinzugefügt.** Dies ist ein "Vereinfachungs"-Release.
Das meiste Entfernte hat nichts mit dem NPU-Inferenzpfad zu tun.

---

## 2. Entfernte APIs — Nur Hailo-8-Kamera / ISP / Firmware

`hailort/libhailort/include/hailo/device.hpp` verlor 169 Zeilen,
`platform.h` verlor 75 Zeilen. Alles Entfernte ist Low-Level-Gerätesteuerung:

- `firmware_update()` / `second_stage_update()` (Firmware-Neuprogrammierung)
- `store_sensor_config()` / `store_isp_config()`
- `sensor_dump_config()` / `sensor_reset()`
- `sensor_load_and_start_config()`
- `sensor_set_i2c_bus_index()` / `sensor_set_generic_i2c_slave()`
- `sensor_get_sections_info()`
- `examine_user_config()` / `read_user_config()` /
  `write_user_config()` / `erase_user_config()`

Dies sind alles APIs für **Hailo-8 AI Vision-Kameramodule** (SoC-Boards, bei denen der Hailo-Chip
ISP und Bildsensor direkt steuert).
Sie werden im typischen `VDevice` → `InferModel` → `generate`-Fluss mit einer blanken Hailo-10H NPU nicht aufgerufen.

**Auswirkung**: Null für reine NPU-Inferenzanwendungen.

---

## 3. Python-Signaturänderungen

| API | v5.2.0 | v5.3.0 | Kompatibilität |
|---|---|---|---|
| `Speech2Text.generate_all_segments(timeout_ms=)` | Standard `10000` | Standard `600000` | ✅ Nur Standard, bestehende Aufrufe unverändert |
| `Speech2Text.generate_all_text(timeout_ms=)` | Gleich | Gleich | ✅ Gleich |
| `LLM.read_all(timeout_ms=10000)` | Mit Standard | Standard **entfernt** (obligatorisch) | ⚠️ `read_all()` ohne Argument → `TypeError` |
| `DeviceArchitecture.__init__` | 9 Positionsargumente | +`chip_serial_number` (10) | ⚠️ Direkte Konstruktion bricht |

**`read_all()`-Fix ist eine einzeilige Änderung**:

```python
# Vorher (v5.2.0-Stil, 10-Sekunden-Standard)
text = generator.read_all()

# Nachher (v5.3.0 erfordert explizites Timeout)
text = generator.read_all(timeout_ms=600000)  # 10 Minuten
```

`DeviceArchitecture` wird im Benutzercode selten direkt konstruiert, daher hat diese Signaturänderung kaum Auswirkungen.

---

## 4. C++-Header-Namensänderungen (transparent über Python)

Für Anwendungen, die HailoRT direkt aus C++ verwenden, sind diese Breaking:

- **`Speech2Text::DEFAULT_OPERATION_TIMEOUT`** (10 s) →
  **`DEFAULT_GENERATE_ALL_TIMEOUT`** (10 min), Umbenennung und Verlängerung
- **`LLM::DEFAULT_READ_ALL_TIMEOUT`** hinzugefügt, ebenfalls 10 min
- 4 `generate_from_embeddings()`-Überladungen zu `vlm.hpp` hinzugefügt

Diese Umbenennungen propagieren nicht über Python-Bindings.

---

## 5. NMS-Bounding-Box-Koordinatenfix (Verhaltensänderung)

Logikfix in der NMS-Nachverarbeitung in `pyhailort.py`:

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

Verbesserungen:

- Bildbegrenzungs-Clipping `max(0, …)` / `min(image_width, …)` hinzugefügt
- `ceil` → `floor` (verhindert Überschuss)
- `bbox_width` wird aus geclipptem `x_max - x_min` neu berechnet

**Verhaltensunterschied**: Selbst mit demselben Modell und demselben Bild kann sich die NMS-Ausgabe nahe der Grenzen um ±1 Pixel verschieben.

---

## 6. Neue APIs (additiv)

- **`VDevice::create_session(uint16_t port)`** — Netzwerkbasierte Inferenz-Session-API (neue Funktion)
- **`VLM::generate_from_embeddings()`** — 4 Überladungen. Akzeptiert vorberechnete Bild-/Video-Embeddings als `MemoryView`-Eingabe.
  Ermöglicht einmaliges Berechnen von Bild-Embeddings und Wiederverwendung in mehreren VLM-Aufrufen.
- **`InferModel::set_nms_classes_filter_mask(vector<bool>)`** — Klassen-Level-Filterung für NMS-Ausgabe (On-Chip)
- **`Device::query_performance_stats(sampling_period_ms)`** — Konfigurierbarer Abtastzeitraum
- **`Device::get_current_limit()`** — Stromgrenze abfragen
- **`DeviceArchitecture.chip_serial_number`** — Chip-Seriennummer lesen

Alle additiv, daher bricht bestehender Code nicht.

---

## 7. Umgebungsänderungen

### 7.1 Neuer Linux-PCI-Treiber

| Element | Alt | Neu |
|---|---|---|
| Kernel-Modul | `hailo_pci` | `hailo1x_pci` |
| Device-Node | `/dev/hailort0` (oder `/dev/hailo0`) | `/dev/h1x-0` |

```bash
lsmod | grep hailo        # → hailo1x_pci
ls /dev/h1x-*             # → /dev/h1x-0
```

**`pyhailort` löst den neuen Device-Node intern auf**, daher funktioniert Python-Code mit `VDevice()` ohne Änderungen weiter.
Nur Code, der `/dev/hailo*` oder `/dev/hailort0` direkt öffnet, muss aktualisiert werden.

#### Docker / Podman-Passthrough

Geräte-Passthrough-Deklaration aktualisieren:

```yaml
# docker-compose.yml
services:
  my-app:
    devices:
      - /dev/h1x-0:/dev/h1x-0   # war: /dev/hailort0:/dev/hailort0
```

Auch systemd-Unit `DeviceAllow=`-Zeilen und udev-Regeln aktualisieren.

### 7.2 Gelockerte numpy-Einschränkung

- v5.2.0 `setup.py`: `numpy<2` (fest)
- v5.3.0 `setup.py`: `numpy` (keine Obergrenze)

Anwendungen, die zuvor auf numpy 1.x fixiert waren, können jetzt zusammen mit dem HailoRT-Bump auf numpy 2.x upgraden.

### 7.3 HEF-Binärkompatibilität

**`.hef`-Dateien, die unter dem v5.2.0-Bucket heruntergeladen wurden, werden unter dem 5.3.0-Runtime ohne Änderungen geladen und ausgeführt.**
Verifiziert mit fünf Modellen (Raspberry Pi 5 + AI HAT 2):

| Modell | Datei | Ergebnis |
|---|---|---|
| YOLOv8n | `yolov8n.hef` | ✅ `create_infer_model()` + `.run()` |
| CLIP ViT-B/16 Bild-Encoder | `clip_vit_b_16_image_encoder.hef` | ✅ 512-dimensionale Ausgabe |
| Qwen2.5-1.5B Instruct | `Qwen2.5-1.5B-Instruct.hef` | ✅ `LLM.generate_all()` gibt gültigen Text zurück |
| Qwen2-VL-2B Instruct | `Qwen2-VL-2B-Instruct.hef` | ✅ `VLM.generate_all(frames=[…])` gibt gültigen Text zurück |
| Whisper-Base | `Whisper-Base.hef` | ✅ `Speech2Text.generate_all_segments()` gibt `SegmentInfo` zurück |

### 7.4 HEF-Download-URL-Bucket

Der Hailo Developer Zone (`dev-public.hailo.ai`) hostet v5.2.0- und v5.3.0-Buckets parallel:

```
https://dev-public.hailo.ai/v5.2.0/blob/<model>.hef
https://dev-public.hailo.ai/v5.3.0/blob/<model>.hef
```

v5.3.0-Bucket-Status vom 2026-04-06:

| Modell | v5.3.0-Bucket |
|---|---|
| Qwen2.5-1.5B-Instruct | ✅ 200 |
| DeepSeek-R1-Distill-Qwen-1.5B | ✅ 200 |
| Qwen2.5-Coder-1.5B-Instruct | ✅ 200 |
| Qwen2-VL-2B-Instruct | ✅ 200 |
| Whisper-Base / Whisper-Small | ✅ 200 |
| **Llama-3.2-1B-Instruct** | ❌ **404** |

→ Anwendungen, die Llama-3.2-1B benötigen, müssen es vorerst weiterhin aus dem v5.2.0-Bucket beziehen. v5.2.0-HEFs laufen korrekt auf dem 5.3.0-Runtime.

---

## 8. `Speech2Text.SegmentInfo`-Attributnamen

In v5.2.0 und v5.3.0 gibt `Speech2Text.generate_all_segments()` `SegmentInfo`-Objekte mit diesen öffentlichen Attributen zurück:

```python
seg.text        # str
seg.start_sec   # float (Sekunden)
seg.end_sec     # float (Sekunden)
```

**`seg.start` und `seg.start_time` existieren nicht.** Alter Dokumentation und Beispielcode referenzieren manchmal diese Namen, was `AttributeError` auslöst oder bei defensivem Code mit `getattr()` still 0.0 zurückgibt.

---

## 9. Smoke-Test-Skript

Minimales Skript zur Bestätigung, dass die Umgebung nach dem Upgrade auf 5.3.0 funktioniert:

```python
"""HailoRT 5.3.0 Smoke Test — VDevice / InferModel / LLM / Speech2Text."""
import numpy as np
from hailo_platform import VDevice

# 1. VDevice erstellen
params = VDevice.create_params()
params.group_id = "SMOKE_TEST"
vd = VDevice(params)
print("1. VDevice OK")

# 2. InferModel-Pfad (YOLOv8n oder beliebige vorhandene HEF)
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

# 3. GenAI LLM-Pfad
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

# 4. Speech2Text-Pfad
from hailo_platform.genai import Speech2Text, Speech2TextTask
params = VDevice.create_params(); params.group_id = "SMOKE_TEST"
vd = VDevice(params)
s2t = Speech2Text(vd, "/path/to/Whisper-Base.hef")
audio = (np.random.default_rng(0).standard_normal(32000) * 0.01).astype("<f4")
segments = s2t.generate_all_segments(
    audio_data=audio, task=Speech2TextTask.TRANSCRIBE,
    language="en", timeout_ms=30000,
)
print(f"4. Speech2Text OK: {len(segments)} Segmente")
if segments:
    seg = segments[0]
    print(f"   attrs: text={seg.text!r} start_sec={seg.start_sec} end_sec={seg.end_sec}")
s2t.release(); vd.release()

print("\nAlle Smoke Tests bestanden.")
```

---

## 10. Upgrade-Checkliste

Punkte zum Überprüfen im Code vor oder während des 5.2.0 → 5.3.0-Upgrades:

- [ ] `VDevice()` / `create_infer_model()` / `InferModel.configure()` — **Keine Änderung erforderlich**
- [ ] `LLM(vd, path)` / `VLM(vd, path)` / `Speech2Text(vd, path)` Konstruktoren — **Keine Änderung erforderlich**
- [ ] `LLM.generate()` / `.generate_all()` / `VLM.generate(frames=…)` / `.generate_all()` Schlüsselwortargumente — **Keine Änderung erforderlich**
- [ ] `Speech2Text.generate_all_segments(audio_data=, task=, language=, timeout_ms=)` — **Keine Änderung erforderlich** (wenn `timeout_ms` explizit übergeben wird)
- [ ] Prüfen, ob `LLM.read_all()` ohne `timeout_ms`-Argument aufgerufen wird → Wenn ja, explizites Timeout hinzufügen
- [ ] Prüfen, ob `DeviceArchitecture` direkt konstruiert wird → Wenn ja, `chip_serial_number` hinzufügen
- [ ] Grep nach direktem Öffnen von `/dev/hailo*` oder `/dev/hailort0` → Wenn vorhanden, auf `/dev/h1x-0` ersetzen (oder über pyhailort routen)
- [ ] Docker/Podman `devices:`-Abschnitte auf `/dev/h1x-0` aktualisieren
- [ ] systemd-Unit `DeviceAllow=`-Zeilen und udev-Regeln aktualisieren
- [ ] Grep nach `SegmentInfo`-Attributzugriff mit `.start` oder `.start_time` → Auf `.start_sec` / `.end_sec` umstellen
- [ ] numpy kann jetzt ggf. auf 1.x-Fixierung verzichtet werden (wegen v5.2.0 `numpy<2`)
- [ ] Vorhandene `.hef`-Dateien müssen **nicht** neu heruntergeladen werden
- [ ] Falls HEF-Download-URLs mit `v5.2.0`-Bucket fest kodiert sind, auf `v5.3.0` ändern (Llama-3.2-1B behält v5.2.0)
- [ ] Bei Abhängigkeit von pyhailort's eingebauter NMS-Nachverarbeitung: Bounding Boxes nahe Bildrändern können sich um ±1 Pixel verschieben

---

## 11. Für die Untersuchung verwendete Befehle

Vorausgesetzt, das offizielle HailoRT-Repository ist geklont:

```bash
cd ~/hailort

# Gesamter Diff-Umfang
git diff --stat v5.2.0 v5.3.0 | tail

# Öffentliche C++-Header-Diff
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/include/hailo/'

# Python-Bindings-Diff
git diff --stat v5.2.0 v5.3.0 -- 'hailort/libhailort/bindings/python/'

# Vollständiger Diff von pyhailort.py
git diff v5.2.0 v5.3.0 -- \
  'hailort/libhailort/bindings/python/platform/hailo_platform/pyhailort/pyhailort.py'
```

C++-Header enthalten pro Zeile die meisten Informationen für die API-Analyse — Python-Bindings sind größtenteils pybind11-Boilerplate.

---

## 12. Fazit

Die Schlagzahl "688 geänderte Dateien" ist weit von der tatsächlichen Auswirkung entfernt.
Für eine typische Hailo-10H NPU-Inferenzanwendung:

- **Kern-NPU-Inferenz-API (`VDevice` / `InferModel` / GenAI) ist vollständig rückwärtskompatibel**
- Alle entfernten APIs gehören zur Hailo-8-Kamera/Sensor/ISP/Firmware-Verwaltungsoberfläche
- **Alle vorhandenen `.hef`-Dateien werden ohne Neudownload geladen**
- Die einzige zwingend erforderliche Umgebungsänderung ist die Aktualisierung des Docker-Geräte-Passthroughs auf `/dev/h1x-0`

Hauptverbesserungen der Lebensqualität nach dem Upgrade:
- Timeout-Standards stark verlängert (10 Sek. → 10 Min.)
- `FormatType.FLOAT32` verfügbar (v5.2.0 erforderte manuelle Quantisierung/Dequantisierung)
- NMS-Koordinaten-Clipping-Bug behoben
- numpy 2.x Upgrade-Pfad freigeschaltet
- `VLM.generate_from_embeddings()` ermöglicht Wiederverwendung vorberechneter Bild-Embeddings
