# Hailo-10H Gerätesteuerung

## Überblick

Die Hailo-10H NPU kann **mehrere Modelle gleichzeitig ausführen**.
Der integrierte ROUND_ROBIN-Scheduler teilt den Hardware-Zugriff automatisch zeitlich zwischen Modellen auf.

In yu_ai_manager wird ein einziger gemeinsamer VDevice gehalten, wobei CLIP, YOLO, LLM, VLM und Speech2Text gleichzeitig geladen und inferiert werden können. Die gemeinsame Nutzung mit externen Prozessen (hailo-ollama) wird mit `group_id` unterstützt.

## Architektur

```
┌─────────────────────────────────────────────┐
│              Shared VDevice                  │
│         (group_id = YU_SHARED)               │
│                                              │
│  ┌─────────┐ ┌─────────┐ ┌───────────────┐  │
│  │  CLIP   │ │  YOLO   │ │  LLM (GenAI)  │  │
│  │InferMdl │ │InferMdl │ │  VLM / S2T    │  │
│  └─────────┘ └─────────┘ └───────────────┘  │
│                                              │
│     HailoRT ROUND_ROBIN Scheduler            │
└─────────────────────────────────────────────┘
```

- InferModel-API (CLIP, YOLO) und GenAI-API (LLM, VLM, S2T) können auf demselben VDevice koexistieren
- Alle Modelle müssen auf der **gleichen VDevice-Instanz** erstellt werden (separate Instanzen funktionieren nicht)

## Vergleich der zwei Modi

| | Python SDK (Hailo VLM) | hailo-ollama-vlm (OpenAI-kompatibel) |
|---|---|---|
| Geräteverwaltung | yu's device_manager | Externer C++-Server |
| Koexistenz mit CLIP-Suche | Möglich (gleichzeitiger Betrieb) | Möglich (group_id-Sharing, v5.3.0+) |
| Inferenzgeschwindigkeit | Gleich | Gleich |
| Overhead | ~15ms | ~200-400ms (base64+HTTP) |
| Mehrere Clients | Nicht möglich | Möglich |
| Flask-Thread | Blockiert während Inferenz | Nur HTTP-Warten |

## VDevice-Sharing (group_id)

### Intra-Prozess-Sharing

`device_manager.py` verwaltet automatisch. Alle Modelle teilen sich einen VDevice.

group_id kann per Umgebungsvariable geändert werden:
```bash
export HAILO_VDEVICE_GROUP_ID=MY_GROUP
```

Standard: `YU_SHARED`

### Koexistenz mit hailo-ollama (v5.3.0+)

hailo-ollama v5.3.0+ unterstützt die Umgebungsvariable `HAILO_OLLAMA_VDEVICE_GROUP_ID`.
Wenn dieselbe group_id wie bei yu_ai_manager gesetzt wird, können beide Prozesse das Gerät teilen:

```bash
# yu_ai_manager-Seite
export HAILO_VDEVICE_GROUP_ID=SHARED

# hailo-ollama-Seite
HAILO_OLLAMA_VDEVICE_GROUP_ID=SHARED hailo-ollama
```

**Hinweis**: group_id funktioniert in yu_ai_manager ab HailoRT 5.2.0.
hailo-ollama akzeptiert group_id erst ab v5.3.0.

## device_manager API

### Modell abrufen

```python
from core.hailo_device_core.device_manager import acquire_device, acquire_genai

# InferModel (CLIP, YOLO)
infer_model, configured, quant_params = acquire_device("clip", "/path/to.hef")

# GenAI (LLM, VLM, S2T)
llm = acquire_genai("llm", "/path/to.hef", lambda vd, p: LLM(vd, p))
```

- Gleicher Eigentümer + gleiche HEF → Bestehende Session wiederverwenden
- Gleicher Eigentümer + andere HEF → Altes Modell freigeben und neues erstellen
- Anderer Eigentümer → **Koexistenz** (altes Modell wird nicht freigegeben)

### Modell freigeben

```python
from core.hailo_device_core.device_manager import release_device, shutdown_all

release_device("clip")   # Nur CLIP freigeben, andere weiterführen
shutdown_all()            # Alle Modelle + VDevice freigeben (beim Prozessende)
```

### Status prüfen

```python
from core.hailo_device_core.device_manager import (
    get_active_owners, is_model_active,
    is_hailo_available, is_genai_available,
)

get_active_owners()       # ["clip", "yolo", "llm"]
is_model_active("clip")   # True
```

## Fehlerbehebung

### VDevice-Erstellungsfehler

**Symptom**: `HAILO_OUT_OF_PHYSICAL_DEVICES(74)` oder `Failed to create VDevice`

**Ursache**: Ein anderer Prozess belegt das Gerät mit einer anderen group_id

**Lösung**:
1. Prüfen, ob hailo-ollama läuft:
   ```bash
   ps aux | grep hailo-ollama
   ```
2. group_id angleichen oder stoppen:
   ```bash
   sudo systemctl stop hailo-ollama
   ```

### Gerät wird nicht freigegeben

**Lösung**:
1. yu-Prozess neu starten
2. Zombie-Prozesse prüfen:
   ```bash
   sudo lsof /dev/hailo* 2>/dev/null
   kill <PID>
   ```
3. Hailo-Treiber zurücksetzen:
   ```bash
   sudo systemctl restart hailort.service
   ```

## API-Nutzungsleitfaden

| Modellstruktur | Empfohlene API | Grund |
|---|---|---|
| Einfach (1 Eingabe, YOLO usw.) | `InferModel` | `create_infer_model()` + `configure()` funktioniert |
| Komplex (2+ Eingaben, Whisper usw.) | `GenAI SDK` | InferModel gibt `INVALID_ARGUMENT` zurück |
| CLIP-Encoder | `InferModel` | 1 Eingabe, 1 Ausgabe, kein Problem |
| LLM (qwen2.5 usw.) | `GenAI SDK` | Autoregressive Dekodierung erforderlich |

## Verlauf

- **v4.61.0**: Auf gemeinsamen VDevice-Ansatz umgestellt. Exklusive acquire/release aufgegeben, gleichzeitiger Betrieb von CLIP + YOLO + LLM unterstützt.
- **v4.60.1**: Alle Konsumenten über device_manager vereinheitlicht (exklusiver Ansatz).
- **Vor v4.60.0**: Jeder Konsument rief VDevice() unabhängig auf, was häufig zu Konfliktfehlern führte.
