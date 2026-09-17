# Danbooru Auto-Tagging — Implementierungsspezifikation

**Status**: Implementiert (Phase 1-5: v2.77.0)
**Ziel**: YU AI Manager
**Zweck**: Automatisches Zuweisen von Danbooru-Tags zu KI-Bildern mit einem zweistufigen Ansatz: WD-Tagger ONNX (CPU) + VLM (OpenAI-kompatible API)
**Implementierung**: `extensions/builtin_wd_tagger/core_impl/` (12 Dateien), `routes/wd_tagger.py` (11 APIs)

---

## Implementierungsstatus

| Phase | Status | Ort |
|---|---|---|
| Phase 1: WD-Tagger ONNX | **Abgeschlossen** | `extensions/builtin_wd_tagger/core_impl/engine_onnx.py` |
| Phase 2: VLM Engine (OpenAI-kompatibel) | **Abgeschlossen** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` + `engine_composite.py` |
| Phase 3: Tag-Nachbearbeitung | **Abgeschlossen** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` |
| Phase 4: Batch-API | **Abgeschlossen** | `extensions/builtin_wd_tagger/core_impl/batch_ops.py` + `routes/wd_tagger.py` |
| Phase 5: UI | **Abgeschlossen** | Tools-Seite + Detail-Modal WD-Tag-Abzeichen + XMP-Viewer |

### Phase 2/3 Implementierungsübersicht (v2.77.0-v2.77.1)

- **VLM Engine** (`engine_vlm.py`): Automatisches Fallback zwischen OpenAI-kompatibler API und Ollama nativer API
- **Composite Engine** (`engine_composite.py`): Zweistufige ONNX + VLM Pipeline (Modus B)
- **Tag-Nachbearbeitung** (`tag_postprocess.py`): Normalisierung (Kleinbuchstaben, Unterstrich, Entfernung ungültiger Zeichen, Deduplizierung) + NSFW-Filter (~30 Tags)
- **Engine Factory**: Routing nach `engine_type` ("onnx" / "vlm" / "both")
- **UI**: Engine-Typ-Auswahl, VLM-URL/Modell/Timeout-Einstellungen, Verbindungstest, NSFW-Filter
- **API**: `GET /api/wd-tagger/vlm/test`, `GET /api/wd-tagger/vlm/models`
- **MCP**: `wd_tagger_vlm_test`, `wd_tagger_vlm_models` Tools
- **Getestet**: Echtes Bild-Tagging bestätigt mit Ollama qwen2.5vl:7b, 23 Unit-Tests erfolgreich

---

## Vorausgehende Arbeiten

### DeepDanbooru (KichangKim)
- **Ansatz**: Bildklassifizierungsmodell (TensorFlow) für direkte Tag-Vorhersage
- **Stärken**: Schnell, Tag-spezialisiert, ONNX-konvertierbar
- **Schwächen**: Festes Tag-Set, kann nicht an neue Tags angepasst werden
- **Referenz**: Bereits in A1111 integriert

### WD-Tagger (SmilingWolf) — in Phase 1 übernommen
- **Ansatz**: Nachfolger von DeepDanbooru. Vier Architekturen: SwinV2/ViT/ConvNeXt/EVA02
- **Stärken**: Höhere Genauigkeit als DeepDanbooru, Kategorienklassifizierung enthalten (general/character/copyright/rating)
- **ONNX**: Offizielle ONNX-Modelle + `selected_tags.csv` auf HuggingFace verteilt
- **Eingabe**: 448x448 RGB (Seitenverhältnis beibehalten + weiße Polsterung)

### DanTagGen / DTG (KohakuBlueleaf)
- **Ansatz**: LLaMA-basiertes LLM (400M) für Tag-Generierung und -Vervollständigung
- **Stärken**: Kontextabhängige Tag-Vervollständigung
- **Schwächen**: Langsam aufgrund von LLM-Inferenz
- **HuggingFace**: `KBlueLeaf/DanTagGen-beta`

### Design-Grundlagen
Das System unterstützt sowohl WD-Tagger ONNX (schnell, zuverlässig) als auch Qwen2-VL über hailo-ollama (flexibel, kontextabhängig), damit Benutzer das richtige Werkzeug für die Aufgabe auswählen können.

---

## Architektur

```
[Image Input]
    |
[Engine Selection]  (engine_factory.py)
    |-- WD-Tagger ONNX (schnell, festes Tag-Set ~10.000 Tags)  [Phase 1: implementiert]
    |       | Konfidenzscores + kategorisierte Tag-Liste
    |-- Qwen2-VL über hailo-ollama (langsam, flexibel, kontextabhängig)   [Phase 2]
    |       | JSON-Array -> Tag-Parsing
    |-- Zweistufig: ONNX -> Qwen2-VL-Ergänzung                    [Phase 2 Option]
    |       | ONNX-Tags in Eingabeaufforderung eingeben, LLM zusätzliche Tags generieren lassen
    |
[Post-Processing: Tag-Normalisierung, NSFW-Filterung]  [Phase 3]
    |
[DB: in Datei_wd_tags Tabelle speichern]  (store.py)
[XMP: in Datei einbetten (optional)]  (xmp_write.py)
```

---

## Phase 1: WD-Tagger ONNX Engine — Implementiert

**Modell**: SmilingWolf/wd-swinv2-tagger-v3 (empfohlen), ViT v3, ConvNeXt v3, EVA02-Large v3

**Implementierungsdateien** (`extensions/builtin_wd_tagger/core_impl/`):
| Datei | Zeilen | Rolle |
|---|---|---|
| `types.py` | ~60 | TagPrediction, WdTagResult, WdTaggerEngine ABC |
| `tag_csv.py` | ~70 | selected_tags.csv Parsing, Kategorieabbildung |
| `model_download.py` | ~120 | HuggingFace HTTP-Download |
| `engine_onnx.py` | ~150 | ONNX-Inferenz (448x448, BGR, Schwellwert-Filterung) |
| `engine_factory.py` | ~50 | Engine-Cache + Erstellung |
| `store.py` | ~130 | DB CRUD (file_wd_tags Tabelle) |
| `xmp_xml.py` | ~60 | XMP-Paket-Konstruktion |
| `xmp_read.py` | ~90 | XMP-Lesevorgänge |
| `xmp_write.py` | ~160 | XMP-Schreiben zu PNG/JPEG/WebP |
| `config_ops.py` | ~70 | config.json Lesen/Schreiben |
| `single_ops.py` | ~80 | Single-Image-Tagging-Pipeline |
| `batch_ops.py` | ~120 | Batch-Verarbeitung (JobManager-Integration) |

**DB**: `file_wd_tags` Tabelle (Schema v14)
```sql
CREATE TABLE file_wd_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    category   TEXT NOT NULL DEFAULT 'general',
    model      TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name, model)
);
```

**API**: `routes/wd_tagger.py` — 11 Endpunkte

---

## Phase 2: VLM Engine (OpenAI-kompatible API) — Implementiert (v2.77.0)

**Zweck**: Ergänzung von WD-Tagger ONNX mit detaillierten Beschreibungen und kontextuellen Tags, die ONNX nicht erfassen kann
**Implementierung**: `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` (generische OpenAI-kompatible VLM-Engine)
**Hinweis**: Die ursprüngliche Spezifikation plante eine Hailo-spezifische `engine_hailo.py`, aber die tatsächliche Implementierung verwendet eine generische Engine `engine_vlm.py`, die Ollama, hailo-ollama und andere OpenAI-kompatible Server einheitlich handhabt. Sie unterstützt automatisches Fallback zwischen der OpenAI-kompatiblen API (`/v1/chat/completions`) und der Ollama nativen API (`/api/chat`).

### Hardware-Konfiguration

| Element | Spezifikation |
|---|---|
| **Gerät** | Raspberry Pi 5 + Hailo-10H AI-Beschleuniger |
| **Speicher** | 8GB RAM |
| **VLM-Modell** | **Qwen2-VL-2B-Instruct** (einziges VLM in Hailo Model Zoo) |
| **Inferenz-Framework** | hailo-ollama (OpenAI-kompatible API) |
| **Endpunkt** | `http://<pi-ip>:8000/v1/chat/completions` |

### Modellmerkmale

- **Qwen2-VL-2B-Instruct**: Ein Vision-Language Modell aus der Qwen-Familie (2B Parameter)
- Es gehört zur Qwen-Familie, nicht zur llava-Familie. Die Genauigkeit des Bildverständnisses ist im Allgemeinen höher als bei llava-basierten Modellen
- Mit 2B Parametern passt es komfortabel in die Hailo-10H 8GB RAM
- Das Text-only Qwen2 (1.5B) wurde mit hailo-ollama bestätigt
- **Hinweis**: Ab 2026-02 ist dies das einzige VLM, das für Hailo-10H verfügbar ist

### Eingabeaufforderungs-Design

```python
SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
Analyze the image and output ONLY Danbooru-style tags as a JSON array.
Rules:
- Use underscores instead of spaces (e.g., long_hair, blue_eyes)
- Output ONLY the JSON array, no other text
- Include tags for: character count, gender, hair, eyes, clothing, pose, background, art style
- Do NOT include copyright or character name tags unless clearly identifiable
- Maximum 40 tags
Example output: ["1girl", "solo", "long_hair", "blue_eyes", "smile"]"""

USER_PROMPT = "Tag this image with Danbooru tags."
```

### Implementierungs-Design (`extensions/builtin_wd_tagger/core_impl/engine_hailo.py` — ~100 Zeilen)

```python
import base64
import json
import logging
import urllib.request
from pathlib import Path

from .types import TagPrediction, WdTagResult, WdTaggerEngine

logger = logging.getLogger(__name__)

_USER_AGENT = "YU-AI-Manager/2.0 (WD-Tagger Qwen2-VL)"

class HailoQwen2VLEngine(WdTaggerEngine):
    """Qwen2-VL-2B-Instruct über hailo-ollama (OpenAI-kompatible API)."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str = "qwen2-vl:2b",
        timeout: int = 60,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def tag_image(self, image_path: str) -> WdTagResult:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        # MIME-Typ-Inferenz
        suffix = Path(image_path).suffix.lower()
        mime = {"png": "image/png", "webp": "image/webp"}.get(
            suffix.lstrip("."), "image/jpeg"
        )

        payload = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {
                            "url": f"data:{mime};base64,{image_b64}"
                        }},
                        {"type": "text", "text": USER_PROMPT},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 512,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            f"{self._base_url}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
        )

        resp = urllib.request.urlopen(req, timeout=self._timeout)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        raw_tags = json.loads(content)

        # Antwortformat: Liste oder {"tags": [...]}
        if isinstance(raw_tags, dict) and "tags" in raw_tags:
            raw_tags = raw_tags["tags"]
        if not isinstance(raw_tags, list):
            raw_tags = []

        tags = []
        for t in raw_tags:
            name = str(t).strip().lower().replace(" ", "_")
            if name:
                tags.append(TagPrediction(
                    tag=name,
                    confidence=0.5,  # LLMs geben keine Konfidenzscores zurück
                    category="general",
                ))

        return WdTagResult(tags=tags, model=self._model)

    def get_name(self) -> str:
        return f"Qwen2-VL ({self._model})"

    def is_available(self) -> bool:
        """Prüfen Sie die Konnektivität zum hailo-ollama-Server."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/v1/models",
                headers={"User-Agent": _USER_AGENT},
            )
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status == 200
        except Exception:
            return False
```

### Betriebsmodi

**Modus A: Qwen2-VL Standalone**
```
Bild -> Qwen2-VL -> JSON-Tag-Array -> Normalisierung -> DB speichern
```
- Das LLM analysiert das Bild direkt und generiert Tags
- Keine Konfidenzscores (einheitlich auf 0,5 gesetzt)
- Flexible Tagging ohne festes Tag-Set
- Geschwindigkeit: ~3-10 Sekunden pro Bild (geschätzt auf Hailo-10H)

**Modus B: WD-Tagger ONNX -> Qwen2-VL-Ergänzung (Zweistufig)**
```
Bild -> WD-Tagger ONNX -> High-Confidence-Tags (>=0,7)
                              |
                              v
    Qwen2-VL: "Diese Tags beschreiben das Bild. Schlagen Sie zusätzliche Tags vor."
                              |
                              v
    ONNX-Tags + LLM-Ergänzungs-Tags -> Zusammenführen -> Normalisierung -> DB speichern
```
- Kombiniert zuverlässige ONNX-Tags mit dem kontextuellen Verständnis des LLM
- Das Einschließen von ONNX-Tags in die Eingabeaufforderung sollte die LLM-Genauigkeit verbessern
- Geschwindigkeit: ONNX (~0,5s) + LLM (~3-10s) = ~4-11 Sekunden pro Bild

**Modus B Eingabeaufforderung**:
```python
补完_SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
The image already has these tags from automated classification: {existing_tags}
Analyze the image and suggest ADDITIONAL Danbooru-style tags not in the list above.
Output ONLY a JSON array of new tags. Use underscores instead of spaces.
Focus on: composition, mood, background details, specific clothing items, art style.
Maximum 20 additional tags.
Example: ["looking_at_viewer", "outdoors", "cloudy_sky", "pleated_skirt"]"""
```

### Ergänzung zu engine_factory.py

```python
# Ergänzung zu get_engine() in engine_factory.py

engine_type = config.get("engine_type", "onnx")  # "onnx" | "hailo" | "both"

if engine_type == "hailo":
    from .engine_hailo import HailoQwen2VLEngine
    engine = HailoQwen2VLEngine(
        base_url=config.get("hailo_url", "http://localhost:8000"),
        model=config.get("hailo_model", "qwen2-vl:2b"),
        timeout=config.get("hailo_timeout", 60),
    )
elif engine_type == "both":
    # Zweistufig: ONNX -> Hailo-Ergänzung (Phase 2 Option)
    ...
```

### config.json Einträge

```json
{
  "wd_tagger": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "general_threshold": 0.35,
    "character_threshold": 0.85,
    "write_xmp": true,
    "auto_download": true,
    "engine_type": "onnx",
    "hailo_url": "http://localhost:8000",
    "hailo_model": "qwen2-vl:2b",
    "hailo_timeout": 60
  }
}
```

### Vor der Implementierung durchgeführte Verifikation (Pi Hardware-Tests)

1. **Bestätigen Sie, dass Qwen2-VL-2B-Instruct auf hailo-ollama startet**
   ```bash
   # Auf dem Pi
   hailo-ollama run qwen2-vl:2b
   ```

2. **Bestätigen Sie, dass Vision-Anfragen durch die OpenAI-kompatible API funktionieren**
   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen2-vl:2b",
       "messages": [{"role": "user", "content": [
         {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/..."}},
         {"type": "text", "text": "Was ist auf diesem Bild?"}
       ]}],
       "max_tokens": 256
     }'
   ```

3. **Bestätigen Sie, dass die Danbooru-Format-JSON-Ausgabe stabil ist**
   - Prüfen Sie, ob hailo-ollama `response_format: json_object` unterstützt
   - Ein Regex-basiertes JSON-Extraktions-Fallback aus der Textausgabe ist erforderlich, wenn nicht unterstützt

4. **Messen Sie die tatsächliche Inferenzgeschwindigkeit** — Sekunden pro Bild (erforderlich für Batch-Größe-Berechnung)

---

## Phase 3: Tag-Nachbearbeitung — Implementiert (v2.77.0)

**Implementierung**: `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py`
**Integration**: Automatisch angewendet nach Inferenz in `single_ops.py` / `batch_ops.py`

```python
class TagPostProcessor:
    INVALID_CHARS = set('[](){}"\'/\\')
    MAX_TAG_LEN = 100

    def normalize(self, tags: list[str]) -> list[str]:
        result = []
        for tag in tags:
            tag = tag.strip().lower()
            tag = tag.replace(" ", "_")
            # Ungültige Zeichen entfernen
            tag = "".join(c for c in tag if c not in self.INVALID_CHARS)
            if 1 <= len(tag) <= self.MAX_TAG_LEN:
                result.append(tag)
        # Deduplizieren und sortieren
        return sorted(set(result))

    def filter_nsfw(self, tags: list[str], allow_nsfw: bool) -> list[str]:
        # NSFW-Tag-Liste (in separater Datei verwaltet)
        if allow_nsfw:
            return tags
        return [t for t in tags if t not in NSFW_TAG_SET]
```

**Integration mit Phase 1**:
- WD-Tagger ONNX trennt bereits Rating-Tags mit Kategorie 9 (Bewertung)
- Der NSFW-Filter verwendet Rating-Tags (`explicit`, `questionable`) plus eine zusätzliche NSFW-Liste
- Implementierung: `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` (~80 Zeilen)

---

## Phase 4: Batch-Verarbeitung API — Implementiert

**API** (`routes/wd_tagger.py`):

| Methode | Pfad | Zweck |
|---|---|---|
| POST | `/api/wd-tagger/batch` | Batch starten (file_ids, limit, force) |
| POST | `/api/wd-tagger/tag/<file_id>` | Ein einzelnes Bild taggen |
| GET | `/api/wd-tagger/tags/<file_id>` | Tags abrufen |
| DELETE | `/api/wd-tagger/tags/<file_id>` | Tags löschen |
| GET | `/api/wd-tagger/stats` | Statistiken |
| GET | `/api/wd-tagger/untagged` | Ungetaggte Dateien auflisten |
| GET/POST | `/api/wd-tagger/config` | Einstellungen CRUD |
| POST | `/api/wd-tagger/model/download` | Modell-Download |
| GET | `/api/wd-tagger/model/status` | Modellstatus |
| GET | `/api/wd-tagger/xmp/<file_id>` | XMP-Lesevorgänge |

**Verarbeitungsablauf** (`batch_ops.py`):
1. Verarbeiten Sie Dateien in `file_ids` der Reihe nach (standardmäßig ungetaggte Dateien mit `meta_source=unknown`, wenn nicht angegeben)
2. Führen Sie Inferenz durch die Engine durch
3. UPSERT in die Tabelle `file_wd_tags` (Engine identifiziert nach der Modellspalte)
4. XMP in die Datei einbetten (optional)
5. Verfolgen Sie den Fortschritt und unterstützen Sie Abbruch über JobManager

---

## Phase 5: UI — Implementiert

**Tools-Seite** (`templates/tools/content/primary/_wd_tagger.html`):
- Modellauswahl (4 Modelle), Schwellwert-Schieberegler (general/character)
- XMP-Schreib-Umschalter, Modell-Download-Schaltfläche
- Batch-Ausführungsschaltfläche + Fortschrittsbalken
- Statistikdisplay (Tag-Anzahl, pro-Kategorie-Aufschlüsselung, ungetaggte Anzahl)

**Detail-Modal**:
- WD-Tag-Abzeichen (general=blau, character=grün, copyright=orange, rating=rot)
- XMP-Viewer-Schaltfläche (dc:subject + wdtag-Namespace + Roh-XML)
- Tag-Klick löst Suche aus

---

## Dateistruktur (Aktuell)

```
extensions/builtin_wd_tagger/core_impl/
├── __init__.py              # Modulinitialisierung
├── types.py                 # TagPrediction, WdTagResult, WdTaggerEngine ABC
├── tag_csv.py               # selected_tags.csv Parsing
├── model_download.py        # HuggingFace Modell-Download
├── engine_onnx.py           # WD-Tagger ONNX-Inferenz [Phase 1]
├── engine_vlm.py            # VLM-Engine (OpenAI-kompatibel) [Phase 2: vollständig]
├── engine_composite.py      # ONNX + VLM zweistufig [Phase 2: vollständig]
├── engine_factory.py        # Engine-Erstellung + Cache
├── store.py                 # DB CRUD (file_wd_tags)
├── xmp_xml.py               # XMP-Paket-Konstruktion
├── xmp_read.py              # XMP-Lesevorgänge
├── xmp_write.py             # XMP-Schreiben (PNG/JPEG/WebP)
├── config_ops.py            # config.json Lesen/Schreiben
├── single_ops.py            # Single-Image-Tagging-Pipeline
├── batch_ops.py             # Batch-Verarbeitung (JobManager)
├── batch_processors.py      # Batch-Verarbeitungslogik
└── tag_postprocess.py       # Tag-Normalisierung, NSFW-Filter [Phase 3: vollständig]

routes/wd_tagger.py          # API-Endpunkte (11 insgesamt)

src/ts/tools-page/wd-tagger/
├── core.ts                  # Einstellungen CRUD, Batch, Modell-Download
└── render.ts                # DOM-Rendering

src/ts/runtime-tools-ui/tools/
└── wd-tags.ts               # Detail-Modal WD-Tags + XMP-Viewer
```

---

## Implementierungs-Priorität (Aktualisiert)

```
Phase 1 (WD-Tagger ONNX)        -> Abgeschlossen
Phase 4 (Batch-API)              -> Abgeschlossen
Phase 5 (UI)                     -> Abgeschlossen
Phase 3 (Nachbearbeitung/NSFW)   -> Nächste (~80 zusätzliche Zeilen)
Phase 2 (Qwen2-VL hailo-ollama) -> Nach Pi Hardware-Tests (~100 zusätzliche Zeilen + Factory-Änderungen)
```

---

## Referenzen

- WD-Tagger (SmilingWolf): https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3
- DeepDanbooru: https://github.com/KichangKim/DeepDanbooru
- DanTagGen: https://huggingface.co/KBlueLeaf/DanTagGen-beta
- Hailo Model Zoo VLM: Qwen2-VL-2B-Instruct (hailo.ai Model Explorer)
- hailo-ollama API-Spezifikation: Siehe modifizierte Fork-Quelle

---

*Erstellt: 2026-02-27 / Aktualisiert: 2026-02-27 (Phase 1 Implementierung abgeschlossen, Phase 2 überarbeitet zu Qwen2-VL-Basis)*
