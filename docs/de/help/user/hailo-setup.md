# Hailo-10H Einrichtung

Anleitung zur Einrichtung auf der Host-Seite für die Nutzung von Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H NPU) mit YU AI Manager. Da der Hardware- und OS-bezogene Teil nicht über PyPI abgeschlossen werden kann, sind einige manuelle Vorbereitungen erforderlich.

> **Zielgruppe**: Nur wenn Sie auf einem Raspberry Pi 5 (8 GB empfohlen) mit Hailo-10H Hardware die Hailo-Erweiterungen (GenAI Chat / Semantic Search / YOLO Detect / Tagger / Whisper) aktivieren möchten. In Umgebungen ohne Hailo-Hardware sind die Schritte auf dieser Seite nicht erforderlich.

---

## 1. Voraussetzungen

- Raspberry Pi 5 (8 GB wird dringend empfohlen. Aufgrund von CMA-Einschränkungen ist das gleichzeitige Laden mehrerer Modelle mit 4 GB schwierig)
- Hailo AI Hat+ (Hailo-10H)
- Raspberry Pi OS Bookworm 64-bit (aarch64)
- Python 3.13.x (In `pyproject.toml` unter `requires-python` auf `<3.14` festgelegt. `uv` wählt automatisch 3.13)

---

## 2. Installation des PCIe-Treibers

Hailo-10H verwendet das dedizierte Kernelmodul `hailo1x_pci` (ab HailoRT 5.3.0 von `hailo_pci` umbenannt).

```bash
sudo apt update
sudo apt install hailo-all
sudo reboot
```

Nach dem Neustart überprüfen:

```bash
lsmod | grep hailo1x
ls /dev/h1x-0
dmesg | grep -i hailo | tail -20
```

Erwartete Ergebnisse:

- `hailo1x_pci` ist geladen
- Geräteknoten `/dev/h1x-0` existiert (nicht das alte `/dev/hailo0`)
- `dmesg` enthält die Zeilen `Firmware loaded in NNNN ms` und `Device created at /dev/h1x-0`

> **Es ist kein Problem, wenn `/dev/hailo0` nicht vorhanden ist.** Ab HailoRT 5.3.0 ist `/dev/h1x-0` der Standard, und diese Anwendung erkennt beide (`core/llm_router/hailo_detect.py`).

---

## 3. Installation von HailoRT (Systemseite)

`hailortcli`-Binärdatei und gemeinsam genutzte Bibliothek `libhailort.so`. Diese sind im `hailo-all`-Paket enthalten, aber wenn Sie die neueste Version benötigen, holen Sie sich die `.deb`-Datei aus der Hailo Developer Zone und installieren Sie sie über die bestehende Installation.

Überprüfung:

```bash
hailortcli fw-control identify
```

Erwartete Ausgabe (Kernpunkte):

```
Device Architecture: HAILO10H
Firmware Version: 5.3.0 (release,app)
```

---

## 4. Vorbereitung des Python Wheels (`hailort-*.whl`)

Dies ist der Teil, der nicht über PyPI verfügbar ist. **Das Hailo Python Wheel für aarch64 ist auch nicht in der Hailo Developer Zone verfügbar, daher müssen Sie es selbst bauen.**

### 4.1 Aus dem Quellcode bauen

```bash
cd ~
git clone --branch v5.3.0 https://github.com/hailo-ai/hailort.git
cd hailort
./build.sh -aarch64
# Nach Abschluss wird hailort-5.3.0-cp313-cp313-linux_aarch64.whl im Build-Verzeichnis erzeugt
```

(Einzelheiten zum Build-Prozess und Abhängigkeiten finden Sie in der offiziellen Hailo README.)

### 4.2 Wheel im Home-Verzeichnis ablegen

Kopieren Sie das gebaute Wheel an **einen der folgenden Orte**, und es wird beim Start der Anwendung automatisch erkannt:

| Suchpfad (Priorität) | Zweck |
|---|---|
| Umgebungsvariable `$HAILORT_WHEEL` | Beliebiger vollständiger Pfad (höchste Priorität) |
| `$HOME/share/` | **Empfohlener Speicherort** |
| `$HOME/hailort/` | Wenn der Build-Baum am Quellort belassen wird |
| `$HOME/Downloads/` | Temporärer Speicherort nach dem Download |
| `$HOME/` (direkt) | Letzte Reserve |

Empfohlene Vorgehensweise:

```bash
mkdir -p ~/share
cp ~/hailort/hailort-5.3.0-cp313-cp313-linux_aarch64.whl ~/share/
```

### 4.3 Automatischer Installationsmechanismus

Beim Ausführen von `./start.sh` wird `scripts/install_hailo.py` ausgeführt:

1. Überprüft, ob `import hailo_platform` im venv erfolgreich ist
2. Nur bei Fehler: Suche nach einem **zur aktuellen Python-Version (cp313) + Architektur (aarch64) passenden** Wheel in den oben genannten Suchpfaden
3. Installiert das neueste gefundene Wheel mit `uv pip install`
4. Wenn kein Wheel vorhanden oder bereits installiert: keine Aktion (stille Nichtoperation)

Ein manuelles `uv pip install` ist daher nicht erforderlich. Es genügt, das Wheel im Home-Verzeichnis abzulegen und `./start.sh` neu zu starten.

---

## 4.4 Platzierung von HEF-Modelldateien

Legen Sie die von den Erweiterungen benötigten HEF-Dateien (für NPU kompilierte Modelle) in `~/hailo_models/` ab.

| Datei | Zweck | Größe (ca.) |
|---|---|---:|
| `yolov8n.hef` | YOLO Objekterkennung | 7 MB |
| `clip_vit_b_16_image_encoder.hef` | **Semantic Search (CLIP Bild)** | 76 MB |
| `clip_vit_b_16_text_encoder.hef` | Semantic Search (CLIP Text, optional) | 77 MB |
| `Whisper-{Tiny,Base,Small}.hef` | Spracherkennung | 75–405 MB |
| `Qwen3-1.7B-Instruct.hef` | LLM Chat | 2,9 GB |
| `Qwen3-VL-2B-Instruct.hef` | VLM (Bild+Text) | 3,2 GB |

Direkter Download ohne Authentifizierung aus dem S3-Bucket von Hailo Model Zoo (URL-Format):

```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

Beispiel (CLIP Bild-Encoder):

```bash
mkdir -p ~/hailo_models
curl -L -o ~/hailo_models/clip_vit_b_16_image_encoder.hef \
  https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef
```

> **Wenn HEF-Dateien fehlen, wird die Erweiterung als `Nicht verfügbar` angezeigt.** Wenn der Semantic-Search-Status beispielsweise `hailo-10h (CLIP HEF nicht platziert)` anzeigt, bedeutet das, dass `clip_vit_b_16_image_encoder.hef` nicht in `~/hailo_models/` vorhanden ist. Um die Ursache leicht von Hardware- oder Python-Runtime-Problemen unterscheiden zu können, enthält die Antwort die Ursachen in drei Stufen: `runtime_ok` / `hardware_ok` / `hef_ok` (Mauszeiger über den Statustext für Details).

Mit der Umgebungsvariable `HAILO_HEF_DIR` können Sie auch ein anderes Verzeichnis angeben.

---

## 5. Kernel-Parameter (CMA)

Hailo GenAI-Modelle (LLM/VLM/Whisper) benötigen CMA (Contiguous Memory Allocator) für DMA.

Fügen Sie am Ende von `/boot/firmware/cmdline.txt` hinzu:

```
cma=256M
```

> **Auf Pi 5 (8 GB) scheitert `cma=1G` oder `cma=512M` still.** Da der Standard-Kernel `numa=fake=8` anwendet, muss CMA innerhalb einer einzelnen NUMA-Knotengrenze (1 GB) liegen, und bei mehr als `256M` wird `CmaTotal=0` (kein Panic). Details: [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md)

Nach dem Neustart überprüfen:

```bash
grep CmaTotal /proc/meminfo
# CmaTotal:         262144 kB  ← 256 MB bedeutet Erfolg
```

Bei `0 kB` den Wert prüfen und bei Bedarf reduzieren.

---

## 6. Koexistenz mit hailo-ollama (optional)

Wenn Sie `hailo-ollama` (die Hailo-NPU-Version von Ollama) auf demselben Gerät betreiben:

- **HailoRT 5.3.0 und höher**: Starten Sie mit `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED hailo-ollama`, um das physische Gerät mit der yu_ai_manager-Seite (group_id `YU_SHARED`) zu teilen; der HailoRT-Scheduler führt Time-Slicing per ROUND_ROBIN durch
- **Vor 5.2.0**: group_id wird nicht akzeptiert, daher muss `hailo-ollama` vor dem Start von yu_ai_manager mit `systemctl stop hailo-ollama` gestoppt werden

---

## 7. Funktionsprüfung

Nach dem Start von `./start.sh` ist alles erfolgreich, wenn in der WebUI unter **Einstellungen → Erweiterungen** folgende Einträge aktiviert sind:

- `builtin_hailo_genai` (Hailo Chat / LLM / VLM / Speech2Text)
- `builtin_hailo_semantic_search` (CLIP Semantic Search)
- `builtin_hailo_yolo_detect` (YOLO Objekterkennung)

Oder direkt über die CLI:

```bash
uv run python -c "
from hailo_platform import VDevice
v = VDevice()
print('VDevice OK')
v.release()
"
```

---

## 8. Fehlerbehebung

### Alle Hailo-Erweiterungen zeigen „nicht geladen"

→ Das Python Wheel ist möglicherweise nicht installiert. Bitte prüfen:

```bash
uv run python -c "import hailo_platform; print(hailo_platform.__file__)"
```

Bei `ModuleNotFoundError`: Wheel im Home-Verzeichnis ablegen und `./start.sh` neu starten (§4.2).

### `hailortcli fw-control identify` schlägt mit `HAILO_OPEN_FILE_FAILURE` fehl

→ Problem mit Treiber oder Geräteknoten. Überprüfen Sie, ob `hailo1x_pci` in `lsmod | grep hailo1x` geladen ist und ob `ls /dev/h1x-0` existiert. Wenn beides fehlt, §2 wiederholen und neu starten.

### `HAILO_OUT_OF_HOST_MEMORY` beim Laden von LLM/VLM / Pi hängt

→ CMA-Mangel. Überprüfen Sie mit `grep CmaTotal /proc/meminfo`, ob 256 MB vorhanden sind (§5). Da `VDevice.release()` kein CMA zurückgibt, kann nach mehrfachem Modellwechsel ein Neustart des Prozesses erforderlich sein.

### `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`

→ Ein anderer Prozess belegt VDevice. Ermitteln Sie den Verursacher mit `lsof /dev/h1x-0` (typischerweise `hailo-ollama` oder ein vorheriger Prozess, der mit Ctrl+C nicht korrekt beendet wurde), führen Sie `kill` aus und starten Sie neu.

### Python wurde auf 3.14 aktualisiert und ist mit dem Wheel inkompatibel

→ Dieses Repository ist in `pyproject.toml` auf `requires-python = ">=3.13,<3.14"` festgelegt. Beim ersten `uv sync` nach dem Clone wird 3.13.x ausgewählt. Falls manuell `.python-version = 3.14` gesetzt wurde, bitte rückgängig machen.

---

## 9. Verwandte Dokumentation

- [`docs/ja/hailo/README.md`](../../hailo/README.md) — Hailo-10H Entwicklungsdokumentation Inhaltsverzeichnis
- [`docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md`](../../hailo/HAILORT_5_3_0_MIGRATION.md) — HailoRT 5.2.0 → 5.3.0 Migrationshinweise
- [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md) — Details zu Pi 5 CMA-Einschränkungen
- [`scripts/install_hailo.py`](../../../../scripts/install_hailo.py) — Skript zur automatischen Wheel-Erkennung
