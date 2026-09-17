# Specifica di Implementazione per l'Auto-Tagging di Danbooru

**Status**: Implementato (Fase 1-5: v2.77.0)
**Target**: YU AI Manager
**Scopo**: Assegnare automaticamente tag Danbooru alle immagini AI utilizzando un approccio a due livelli: WD-Tagger ONNX (CPU) + VLM (API compatibile con OpenAI)
**Implementazione**: `extensions/builtin_wd_tagger/core_impl/` (12 file), `routes/wd_tagger.py` (11 API)

---

## Stato dell'Implementazione

| Fase | Status | Posizione |
|---|---|---|
| Fase 1: WD-Tagger ONNX | **Completo** | `extensions/builtin_wd_tagger/core_impl/engine_onnx.py` |
| Fase 2: VLM Engine (API compatibile con OpenAI) | **Completo** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` + `engine_composite.py` |
| Fase 3: Post-elaborazione dei Tag | **Completo** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` |
| Fase 4: API Batch | **Completo** | `extensions/builtin_wd_tagger/core_impl/batch_ops.py` + `routes/wd_tagger.py` |
| Fase 5: UI | **Completo** | Pagina Strumenti + badge WD tag modale dettagli + visualizzatore XMP |

### Panoramica dell'Implementazione Fase 2/3 (v2.77.0-v2.77.1)

- **VLM Engine** (`engine_vlm.py`): Fallback automatico tra API compatibile con OpenAI e API nativa Ollama
- **Composite Engine** (`engine_composite.py`): Pipeline a due livelli ONNX + VLM (Modalità B)
- **Post-elaborazione Tag** (`tag_postprocess.py`): Normalizzazione (minuscole, trattino basso, rimozione caratteri non validi, deduplicazione) + filtro NSFW (~30 tag)
- **Engine Factory**: Routing per `engine_type` ("onnx" / "vlm" / "both")
- **UI**: Selezione tipo engine, impostazioni URL/modello/timeout VLM, test di connessione, filtro NSFW
- **API**: `GET /api/wd-tagger/vlm/test`, `GET /api/wd-tagger/vlm/models`
- **MCP**: Strumenti `wd_tagger_vlm_test`, `wd_tagger_vlm_models`
- **Test**: Tagging immagine reale confermato con Ollama qwen2.5vl:7b, 23 test unitari superati

---

## Arte Precedente

### DeepDanbooru (KichangKim)
- **Approccio**: Modello di classificazione immagini (TensorFlow) per previsione tag diretta
- **Punti di forza**: Veloce, specializzato in tag, convertibile a ONNX
- **Punti deboli**: Set di tag fisso, non può adattarsi ai nuovi tag
- **Riferimento**: Già integrato in A1111

### WD-Tagger (SmilingWolf) — Adottato in Fase 1
- **Approccio**: Successore di DeepDanbooru. Quattro architetture: SwinV2/ViT/ConvNeXt/EVA02
- **Punti di forza**: Precisione maggiore di DeepDanbooru, classificazione categoria inclusa (general/character/copyright/rating)
- **ONNX**: Modelli ONNX ufficiali + `selected_tags.csv` distribuiti su HuggingFace
- **Input**: RGB 448x448 (rapporto d'aspetto preservato + padding bianco)

### DanTagGen / DTG (KohakuBlueleaf)
- **Approccio**: LLaMA-based LLM (400M) per generazione e completamento tag
- **Punti di forza**: Completamento tag consapevole del contesto
- **Punti deboli**: Lento a causa dell'inferenza LLM
- **HuggingFace**: `KBlueLeaf/DanTagGen-beta`

### Razionale del Design
Il sistema supporta **sia** WD-Tagger ONNX (veloce, affidabile) che Qwen2-VL via hailo-ollama (flessibile, consapevole del contesto), quindi gli utenti possono scegliere lo strumento giusto per il lavoro.

---

## Architettura

```
[Input Immagine]
    |
[Selezione Engine]  (engine_factory.py)
    |-- WD-Tagger ONNX (veloce, set di tag fisso ~10.000 tag)  [Fase 1: implementato]
    |       | Punteggi di confidenza + lista di tag categorizzata
    |-- Qwen2-VL via hailo-ollama (lento, flessibile, consapevole del contesto)   [Fase 2]
    |       | Array JSON -> parsing dei tag
    |-- Due livelli: ONNX -> complemento Qwen2-VL                    [Opzione Fase 2]
    |       | Alimenta i tag ONNX nel prompt, lascia che LLM generi tag aggiuntivi
    |
[Post-elaborazione: normalizzazione tag, filtro NSFW]  [Fase 3]
    |
[DB: salva nella tabella file_wd_tags]  (store.py)
[XMP: incorpora nel file (opzionale)]  (xmp_write.py)
```

---

## Fase 1: WD-Tagger ONNX Engine — Implementato

**Modello**: SmilingWolf/wd-swinv2-tagger-v3 (consigliato), ViT v3, ConvNeXt v3, EVA02-Large v3

**File di implementazione** (`extensions/builtin_wd_tagger/core_impl/`):
| File | Righe | Ruolo |
|---|---|---|
| `types.py` | ~60 | TagPrediction, WdTagResult, WdTaggerEngine ABC |
| `tag_csv.py` | ~70 | Parsing selected_tags.csv, mapping categoria |
| `model_download.py` | ~120 | Download HTTP HuggingFace |
| `engine_onnx.py` | ~150 | Inferenza ONNX (448x448, BGR, filtro soglia) |
| `engine_factory.py` | ~50 | Cache engine + creazione |
| `store.py` | ~130 | CRUD DB (tabella file_wd_tags) |
| `xmp_xml.py` | ~60 | Costruzione pacchetto XMP |
| `xmp_read.py` | ~90 | Lettura XMP |
| `xmp_write.py` | ~160 | Scrittura XMP in PNG/JPEG/WebP |
| `config_ops.py` | ~70 | Lettura/scrittura config.json |
| `single_ops.py` | ~80 | Pipeline tagging immagine singola |
| `batch_ops.py` | ~120 | Elaborazione batch (integrazione JobManager) |

**DB**: Tabella `file_wd_tags` (schema v14)
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

**API**: `routes/wd_tagger.py` — 11 endpoint

---

## Fase 2: VLM Engine (API compatibile con OpenAI) — Implementato (v2.77.0)

**Scopo**: Integrare WD-Tagger ONNX con descrizioni dettagliate e tag contestuali che ONNX non può catturare
**Implementazione**: `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` (engine VLM generico compatibile con OpenAI)
**Nota**: La specifica originale prevedeva un `engine_hailo.py` specifico per Hailo, ma l'implementazione effettiva utilizza un engine generico `engine_vlm.py` che gestisce Ollama, hailo-ollama e altri server compatibili con OpenAI uniformemente. Supporta il fallback automatico tra l'API compatibile con OpenAI (`/v1/chat/completions`) e l'API nativa Ollama (`/api/chat`).

### Configurazione Hardware

| Elemento | Specifica |
|---|---|
| **Dispositivo** | Raspberry Pi 5 + Hailo-10H AI accelerator |
| **Memoria** | 8GB RAM |
| **Modello VLM** | **Qwen2-VL-2B-Instruct** (unico VLM in Hailo Model Zoo) |
| **Framework di Inferenza** | hailo-ollama (API compatibile con OpenAI) |
| **Endpoint** | `http://<pi-ip>:8000/v1/chat/completions` |

### Caratteristiche del Modello

- **Qwen2-VL-2B-Instruct**: Un modello Vision-Language della famiglia Qwen (2B parametri)
- Appartiene alla famiglia Qwen, non alla famiglia llava. L'accuratezza della comprensione delle immagini è generalmente superiore ai modelli basati su llava
- Con 2B parametri, si adatta comodamente nella Hailo-10H 8GB RAM
- Il Qwen2 solo testo (1.5B) è stato confermato funzionare con hailo-ollama
- **Nota**: A partire da 2026-02, questo è l'unico VLM disponibile per Hailo-10H

### Design del Prompt

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

### Design di Implementazione (`extensions/builtin_wd_tagger/core_impl/engine_vlm.py` — ~100 righe)

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
    """Qwen2-VL-2B-Instruct via hailo-ollama (API compatibile con OpenAI)."""

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

        # Inferenza del tipo MIME
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

        # Formato risposta: lista o {"tags": [...]}
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
                    confidence=0.5,  # I LLM non restituiscono punteggi di confidenza
                    category="general",
                ))

        return WdTagResult(tags=tags, model=self._model)

    def get_name(self) -> str:
        return f"Qwen2-VL ({self._model})"

    def is_available(self) -> bool:
        """Controlla la connettività al server hailo-ollama."""
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

### Modalità Operative

**Modalità A: Qwen2-VL Standalone**
```
Immagine -> Qwen2-VL -> Array JSON tag -> Normalizzazione -> Salvataggio DB
```
- L'LLM analizza direttamente l'immagine e genera i tag
- Nessun punteggio di confidenza (uniformemente impostato a 0.5)
- Tagging flessibile senza un set di tag fisso
- Velocità: ~3-10 secondi per immagine (stima su Hailo-10H)

**Modalità B: WD-Tagger ONNX -> Complemento Qwen2-VL (Due livelli)**
```
Immagine -> WD-Tagger ONNX -> Tag ad alta confidenza (>=0.7)
                              |
                              v
    Qwen2-VL: "Questi tag descrivono l'immagine. Suggerisci tag aggiuntivi."
                              |
                              v
    Tag ONNX + tag complemento LLM -> Unione -> Normalizzazione -> Salvataggio DB
```
- Combina tag affidabili ONNX con la comprensione contestuale del LLM
- Includere i tag ONNX nel prompt dovrebbe migliorare l'accuratezza LLM
- Velocità: ONNX (~0.5s) + LLM (~3-10s) = ~4-11 secondi per immagine

**Prompt Modalità B**:
```python
COMPLEMENTO_SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
The image already has these tags from automated classification: {existing_tags}
Analyze the image and suggest ADDITIONAL Danbooru-style tags not in the list above.
Output ONLY a JSON array of new tags. Use underscores instead of spaces.
Focus on: composition, mood, background details, specific clothing items, art style.
Maximum 20 additional tags.
Example: ["looking_at_viewer", "outdoors", "cloudy_sky", "pleated_skirt"]"""
```

### Aggiunta a engine_factory.py

```python
# Aggiunta a get_engine() in engine_factory.py

engine_type = config.get("engine_type", "onnx")  # "onnx" | "hailo" | "both"

if engine_type == "hailo":
    from .engine_vlm import HailoQwen2VLEngine
    engine = HailoQwen2VLEngine(
        base_url=config.get("hailo_url", "http://localhost:8000"),
        model=config.get("hailo_model", "qwen2-vl:2b"),
        timeout=config.get("hailo_timeout", 60),
    )
elif engine_type == "both":
    # Due livelli: ONNX -> complemento Hailo (opzione Fase 2)
    ...
```

### Voci config.json

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

### Verifica Pre-implementazione (Test Hardware Pi)

1. **Conferma che Qwen2-VL-2B-Instruct si avvia su hailo-ollama**
   ```bash
   # Sul Pi
   hailo-ollama run qwen2-vl:2b
   ```

2. **Conferma che le richieste di visione funzionano attraverso l'API compatibile con OpenAI**
   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen2-vl:2b",
       "messages": [{"role": "user", "content": [
         {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/..."}},
         {"type": "text", "text": "What is in this image?"}
       ]}],
       "max_tokens": 256
     }'
   ```

3. **Conferma che l'output JSON in formato Danbooru è stabile**
   - Verifica che hailo-ollama supporti `response_format: json_object`
   - È necessario un fallback di estrazione JSON basato su regex dall'output di testo se non supportato

4. **Misura la velocità effettiva di inferenza** — secondi per immagine (necessario per il calcolo della dimensione del batch)

---

## Fase 3: Post-elaborazione Tag — Implementato (v2.77.0)

**Implementazione**: `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py`
**Integrazione**: Applicato automaticamente dopo l'inferenza in `single_ops.py` / `batch_ops.py`

```python
class TagPostProcessor:
    INVALID_CHARS = set('[](){}"\'/\\')
    MAX_TAG_LEN = 100

    def normalize(self, tags: list[str]) -> list[str]:
        result = []
        for tag in tags:
            tag = tag.strip().lower()
            tag = tag.replace(" ", "_")
            # Rimuovi caratteri non validi
            tag = "".join(c for c in tag if c not in self.INVALID_CHARS)
            if 1 <= len(tag) <= self.MAX_TAG_LEN:
                result.append(tag)
        # Deduplicazione e ordinamento
        return sorted(set(result))

    def filter_nsfw(self, tags: list[str], allow_nsfw: bool) -> list[str]:
        # Lista tag NSFW (gestita in un file separato)
        if allow_nsfw:
            return tags
        return [t for t in tags if t not in NSFW_TAG_SET]
```

**Integrazione con Fase 1**:
- WD-Tagger ONNX separa già i tag rating utilizzando la categoria 9 (rating)
- Il filtro NSFW utilizza i tag rating (`explicit`, `questionable`) più una lista NSFW aggiuntiva
- Implementazione: `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` (~80 righe)

---

## Fase 4: API Elaborazione Batch — Implementato

**API** (`routes/wd_tagger.py`):

| Metodo | Percorso | Scopo |
|---|---|---|
| POST | `/api/wd-tagger/batch` | Avvia batch (file_ids, limit, force) |
| POST | `/api/wd-tagger/tag/<file_id>` | Etichetta una singola immagine |
| GET | `/api/wd-tagger/tags/<file_id>` | Recupera i tag |
| DELETE | `/api/wd-tagger/tags/<file_id>` | Elimina i tag |
| GET | `/api/wd-tagger/stats` | Statistiche |
| GET | `/api/wd-tagger/untagged` | Elenca i file non taggati |
| GET/POST | `/api/wd-tagger/config` | CRUD Impostazioni |
| POST | `/api/wd-tagger/model/download` | Download modello |
| GET | `/api/wd-tagger/model/status` | Stato modello |
| GET | `/api/wd-tagger/xmp/<file_id>` | Lettura XMP |

**Flusso di elaborazione** (`batch_ops.py`):
1. Elabora i file in `file_ids` sequenzialmente (di default i file non taggati con `meta_source=unknown` quando non specificato)
2. Esegui l'inferenza attraverso l'engine
3. UPSERT nella tabella `file_wd_tags` (engine identificato dalla colonna model)
4. Incorpora XMP nel file (opzionale)
5. Traccia il progresso e supporta l'annullamento via JobManager

---

## Fase 5: UI — Implementato

**Pagina Strumenti** (`templates/tools/content/primary/_wd_tagger.html`):
- Selezione modello (4 modelli), slider soglia (general/character)
- Toggle scrittura XMP, pulsante download modello
- Pulsante esecuzione batch + barra di progresso
- Visualizzazione statistiche (conteggio tag, ripartizione per categoria, conteggio non taggati)

**Modale dettagli**:
- Badge WD tag (general=blu, character=verde, copyright=arancione, rating=rosso)
- Pulsante visualizzatore XMP (dc:subject + namespace wdtag + XML grezzo)
- Click tag attiva ricerca

---

## Struttura File (Attuale)

```
extensions/builtin_wd_tagger/core_impl/
├── __init__.py              # Inizializzazione modulo
├── types.py                 # TagPrediction, WdTagResult, WdTaggerEngine ABC
├── tag_csv.py               # Parsing selected_tags.csv
├── model_download.py        # Download modello HuggingFace
├── engine_onnx.py           # Inferenza WD-Tagger ONNX [Fase 1]
├── engine_vlm.py            # VLM engine (API compatibile con OpenAI) [Fase 2: completo]
├── engine_composite.py      # Due livelli ONNX + VLM [Fase 2: completo]
├── engine_factory.py        # Creazione engine + cache
├── store.py                 # CRUD DB (file_wd_tags)
├── xmp_xml.py               # Costruzione pacchetto XMP
├── xmp_read.py              # Lettura XMP
├── xmp_write.py             # Scrittura XMP (PNG/JPEG/WebP)
├── config_ops.py            # Lettura/scrittura config.json
├── single_ops.py            # Pipeline tagging immagine singola
├── batch_ops.py             # Elaborazione batch (JobManager)
├── batch_processors.py      # Logica interna elaborazione batch
└── tag_postprocess.py       # Normalizzazione tag, filtro NSFW [Fase 3: completo]

routes/wd_tagger.py          # Endpoint API (11 totali)

src/ts/tools-page/wd-tagger/
├── core.ts                  # CRUD impostazioni, batch, download modello
└── render.ts                # Rendering DOM

src/ts/runtime-tools-ui/tools/
└── wd-tags.ts               # Tag WD modale dettagli + visualizzatore XMP
```

---

## Priorità Implementazione (Aggiornato)

```
Fase 1 (WD-Tagger ONNX)        -> Completo
Fase 4 (API Batch)              -> Completo
Fase 5 (UI)                     -> Completo
Fase 3 (Post-elaborazione/NSFW) -> Prossimo (~80 righe aggiuntive)
Fase 2 (Qwen2-VL hailo-ollama) -> Dopo test hardware Pi (~100 righe aggiuntive + cambiamenti factory)
```

---

## Riferimenti

- WD-Tagger (SmilingWolf): https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3
- DeepDanbooru: https://github.com/KichangKim/DeepDanbooru
- DanTagGen: https://huggingface.co/KBlueLeaf/DanTagGen-beta
- Hailo Model Zoo VLM: Qwen2-VL-2B-Instruct (hailo.ai Model Explorer)
- Specifica API hailo-ollama: Fare riferimento al codice sorgente del fork modificato

---

*Creato: 2026-02-27 / Aggiornato: 2026-02-27 (implementazione Fase 1 completa, Fase 2 rivista per base Qwen2-VL)*
