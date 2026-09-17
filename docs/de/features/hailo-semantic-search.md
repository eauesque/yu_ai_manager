# Hailo Semantic Search Extension — Implementierungsspezifikation

**Status**: Implementiert — Die Hailo-spezifische Version wurde von CLIP ONNX überholt (v2.95.0)
**Ziel**: YU AI Manager Extension
**Zweck**: Semantische Bildsuche mit CLIP/SigLIP auf Hailo-10H (AI HAT 2)
**Implementierung**: `extensions/builtin_clip_search/core_impl/` (gemeinsame Schicht) + `extensions/builtin_clip_onnx/core_impl/` (ONNX-Implementierung)
**Hinweis**: Diese Spezifikation beschreibt das anfängliche Hailo-nur-Design. Die aktuelle Implementierung verwendet eine einheitliche ONNX-Multi-Backend-Architektur

---

## Übersicht

Diese Erweiterung fügt die Möglichkeit hinzu, Bilder mit natürlichsprachlichem Text zu suchen. Beispiele: "blauer Himmel und Ozean", "Mädchen lächelt", "nächtliche Großstadt" — alle geben visuell ähnliche Bilder zurück.

Sie muss **parallel** mit der bestehenden FTS5-Tag-Suche und pHash-Ähnlichkeitssuche funktionieren. Die Erweiterung deaktiviert sich einfach in Umgebungen, in denen kein Hailo-Gerät vorhanden ist.

---

## Architektur

```
[Während des Image-Scans]
Image-Datei -> CLIP Image Encoder (Hailo HEF) -> 512-dim Vektor -> DB-Speicherung

[Während der Suche]
Texteingabe -> CLIP Text Encoder (CPU / Hailo HEF) -> 512-dim Vektor
           -> Kosinus-Ähnlichkeitssuche -> file_id Liste -> Mit bestehenden Suchergebnissen zusammenführen
```

**Sowohl CLIP als auch SigLIP werden unterstützt**, umschaltbar über Konfiguration. SigLIP bietet höhere Genauigkeit, aber CLIP hat einen stärkeren Track Record und mehr Community-Ressourcen. Der empfohlen Ansatz ist, mit CLIP zu beginnen und SigLIP später hinzuzufügen.

---

## Phasen-Aufschlüsselung

### Phase 1: Machbarkeitsprüfung (Zuerst machen)

Nach dem Wechsel zur Pi5-Umgebung lassen Sie Claude Code die folgenden Schritte **der Reihe nach von oben nach unten** ausführen. Stoppen Sie bei jedem Schritt, der fehlschlägt, und beheben Sie das Problem, bevor Sie fortfahren.

#### Schritt 1-1: HailoRT Runtime überprüfen

```bash
# Geräterkennung überprüfen
hailortcli fw-control identify

# Python-Bindungen überprüfen
python3 -c "import hailo_platform; print('HailoRT version:', hailo_platform.__version__)"
```

- **Gerät nicht sichtbar**: Überprüfen Sie den Treiberstatus mit `dmesg | grep hailo`. Überprüfen Sie die AI HAT 2 PCIe-Verbindung
- **Importfehler**: Installieren Sie über `pip install hailort` oder aus dem Hailo APT-Repository (`python3-hailort`)

#### Schritt 1-2: CLIP HEF-Dateien herunterladen

```bash
mkdir -p ~/hailo_models && cd ~/hailo_models

# Image Encoder
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef

# Text Encoder
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_text_encoder.hef
```

- **403 / Zugriff verweigert**: Registrierung auf Hailo Developer Zone (https://hailo.ai/developer-zone/) ist erforderlich. Nach der Registrierung versuchen Sie, über Model Zoo CLI (`hailo_model_zoo`) herunterzuladen
- **Größenprüfung**: Jede Datei sollte Dutzende bis ~100 MB sein. Eine ungewöhnlich kleine Datei deutet auf Downloadfehler hin

#### Schritt 1-3: Python-Abhängigkeiten installieren

```bash
# Erforderlich für Bildvorverarbeitung (in Phase 1 verwendet)
pip install opencv-python-headless numpy

# Überprüfung
python3 -c "import cv2; import numpy; print('cv2:', cv2.__version__, 'numpy:', numpy.__version__)"
```

#### Schritt 1-4: Minimaler Inferenz-Test

```python
from hailo_platform import HEF, VDevice, HailoStreamInterface, InferVStreams, ConfigureParams
import numpy as np

hef_path = "/home/<user>/hailo_models/clip_vit_b_16_image_encoder.hef"
hef = HEF(hef_path)

# HEF-Eingabe-/Ausgabe-Layer-Info überprüfen (Layer-Namen variieren je nach Modell)
print("Input layers:", [l.name for l in hef.get_input_vstream_infos()])
print("Output layers:", [l.name for l in hef.get_output_vstream_infos()])

with VDevice() as target:
    configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
    network_groups = target.configure(hef, configure_params)
    network_group = network_groups[0]

    input_info = hef.get_input_vstream_infos()[0]
    input_name = input_info.name
    input_shape = input_info.shape  # Erwartet: (224, 224, 3) usw.
    print(f"Input: name={input_name}, shape={input_shape}")

    # Inferenz-Test mit Dummy-Bild
    dummy = np.random.randint(0, 255, (1, *input_shape), dtype=np.uint8)
    with InferVStreams(network_group, {}) as pipeline:
        result = pipeline.infer({input_name: dummy})
        for name, data in result.items():
            print(f"Output: name={name}, shape={data.shape}, dtype={data.dtype}")
            # Erfolg, wenn ein 512-dim-Vektor ausgegeben wird
```

- **VDevice-Fehler (`not enough free devices`)**: hailo-ollama könnte laufen. Stoppen Sie es mit `systemctl stop hailo-ollama` und versuchen Sie erneut
- **Inferenz erfolgreich, aber Ausgabe ist nicht 512-dim**: Überprüfen Sie die HEF-Version und Modellvariante

#### Schritt 1-5: Entscheidungskriterien

| Ergebnis | Nächste Aktion |
|------|----------------|
| 512-dim Vektor-Ausgabe | Phase 2 und später fortfahren |
| HEF lädt erfolgreich, aber Ausgabedimensionen sind unterschiedlich | Versuchen Sie eine andere Modellvariante (clip_resnet_50 usw.) |
| Kann HEF nicht herunterladen | Registrieren Sie sich auf Developer Zone -> Download über Model Zoo CLI |
| Kann hailo_platform nicht importieren | Installieren Sie HailoRT neu. Fallback zu CPU CLIP, falls ungelöst |
| Gerät nicht erkannt | Hardware-Verbindungs-/Treiberproblem. Pausieren Sie diese Erweiterungs-Entwicklung |

Fahren Sie mit der vollständigen Implementierung fort, wenn Phase 1 erfolgreich ist. Betrachten Sie CPU CLIP als Alternative, falls dies nicht der Fall ist.

---

### Phase 2: DB-Schema-Erweiterung

Zur bestehenden DB-Migration hinzufügen:

```sql
-- Migration 14: Semantische Such-Vektoren
CREATE TABLE IF NOT EXISTS file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip',   -- 'clip' | 'siglip'
    vector      BLOB NOT NULL,                  -- float32 numpy array -> bytes
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_file_vectors_model ON file_vectors(model);
```

Speicherung: `numpy.ndarray.tobytes()` -> BLOB
Laden: `numpy.frombuffer(blob, dtype=numpy.float32)`

**Hinweis**: SQLite hat keinen ANN (Approximate Nearest Neighbor) Index, daher benötigen alle 200.000 Datensätze vollständige Kosinus-Ähnlichkeitsberechnung. Batch-Berechnung mit numpy sollte dies im Pi5 annehmbar halten (Messung erforderlich). Erwägen Sie die `sqlite-vec`-Erweiterung, wenn die Datensatzanzahl erheblich wächst.

---

### Phase 3: Hailo Inferenz Core

**Dateistruktur**:
```
extensions/hailo_semantic_search/
├── __init__.py
├── extension.py          # Extension-Einstiegspunkt
├── core/
│   ├── hailo_clip.py     # Hailo CLIP Inferenz-Wrapper
│   ├── cpu_clip.py       # CPU-Fallback für Nicht-Hailo-Umgebungen (optional)
│   └── vector_store.py   # DB Vektor CRUD
├── routes/
│   └── semantic_search.py  # API-Endpunkte
└── templates/
    └── _semantic_search_ui.html
```

**Zuständigkeiten von `hailo_clip.py`**:
- HEF-Laden und VDevice-Initialisierung (Singleton, einmal beim Start)
- Bild -> Vorverarbeitung (224x224 Größenänderung, Normalisierung) -> HEF-Inferenz -> 512-dim Vektor
- Text -> Tokenisierung -> HEF-Inferenz -> 512-dim Vektor
  * Verwenden Sie den Text Encoder HEF, falls für Hailo-10H verfügbar; ansonsten CPU verwenden (transformers Bibliothek)

**Vorverarbeitung**:
```python
import cv2
import numpy as np

def preprocess_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (224, 224))
    img = img.astype(np.float32) / 255.0
    mean = np.array([0.48145466, 0.4578275, 0.40821073])
    std  = np.array([0.26862954, 0.26130258, 0.27577711])
    img = (img - mean) / std
    return img[np.newaxis, ...]  # (1, 224, 224, 3)
```

---

### Phase 4: Index-Building API

**Endpunkt**:
```
POST /api/extensions/hailo-semantic/index
```
- Verarbeitet unindexierte Bilder sequenziell in einem Hintergrund-Thread
- Sendet Fortschritt über SSE als `semantic_index.progress` Ereignisse
- Optional in vorhandenes `scan.complete` Ereignis für automatische Ausführung einbinden

**Batch-Größe**: 32 Bilder pro Batch (Balance zwischen Speicher und Geschwindigkeit)

```
GET /api/extensions/hailo-semantic/index/status
-> { "total": 200000, "indexed": 12500, "running": true }
```

---

### Phase 5: Semantic Search API

```
GET /api/extensions/hailo-semantic/search?q=blue sky&limit=50&threshold=0.25
```

**Verarbeitungsablauf**:
1. Text `q` in Vektor konvertieren
2. Alle Vektoren von `file_vectors` laden (numpy)
3. Kosinus-Ähnlichkeit in Batch berechnen
4. Ergebnisse über `threshold` nach aufsteigender Ähnlichkeit sortieren
5. `file_id` Liste im bestehenden `/api/search`-Format zurückgeben

**Kosinus-Ähnlichkeits-Berechnung**:
```python
def cosine_similarity_batch(query_vec: np.ndarray, stored_vecs: np.ndarray) -> np.ndarray:
    # query_vec: (512,), stored_vecs: (N, 512)
    query_norm = query_vec / np.linalg.norm(query_vec)
    stored_norm = stored_vecs / np.linalg.norm(stored_vecs, axis=1, keepdims=True)
    return stored_norm @ query_norm  # (N,)
```

**Leistungs-Ziel**: Unter 1 Sekunde für 200.000 Datensätze (erreichbar mit numpy Batch-Berechnung, auch auf Pi5)

---

### Phase 6: UI-Integration

Fügen Sie einen "Semantic Search"-Tab zur bestehenden Such-UI hinzu. Es kann eine eigenständige UI unabhängig vom vorhandenen Condition-Builder sein (Integration ist für die Zukunft).

```html
<!-- Umschalter-Schaltfläche neben Suchleiste hinzufügen -->
<button id="semantic-search-toggle" class="btn-secondary">
  🔍 Semantic Search (Hailo)
</button>
```

- Verbergen oder grau machen Sie die Schaltfläche, wenn kein Hailo-Gerät erkannt wird
- Verwenden Sie das bestehende Gitter für Suchergebnisse erneut
- Zeigen Sie eine Eingabeaufforderung zum Erstellen des Index an, wenn kein Index existiert

---

## Konfiguration (config.json Ergänzung)

```json
{
  "hailo_semantic_search": {
    "enabled": true,
    "model": "clip",           // "clip" | "siglip"
    "device": "auto",          // "auto" | "hailo" | "cpu"
    "batch_size": 32,
    "similarity_threshold": 0.25,
    "auto_index_on_scan": false,
    "hef_dir": "~/.local/share/hailo-ollama/models"
  }
}
```

---

## Verifizierte Fakten (ab 2026-02-27)

Die folgenden Informationen wurden durch vorherige Forschung bestätigt. Verwenden Sie sie als Referenz während der Phase 1-Ausführung.

### CLIP HEF-Verfügbarkeit

Hailo Model Zoo v5.2.0 enthält **sowohl Image als auch Text Encoder** HEFs für Hailo-10H über CLIP/SigLIP-Varianten:

| Modell | Image Encoder HEF | Text Encoder HEF |
|--------|-------------------|-------------------|
| clip_vit_b_16 | Verfügbar | Verfügbar |
| clip_vit_b_32 | Verfügbar | Verfügbar |
| clip_vit_l_14 | Verfügbar | Verfügbar |
| clip_resnet_50 | Verfügbar | Verfügbar |
| siglip_b_16 | Verfügbar | Verfügbar |
| siglip_l_16_256 | Verfügbar | Verfügbar |
| siglip2_b_32_256 | Verfügbar | Verfügbar |
| TinyCLIP Varianten | Verfügbar | Verfügbar |

S3-URL-Muster: `https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef`

### Text Encoder Status

- Die offizielle `hailo-CLIP` App führt **den Text Encoder auf CPU (PyTorch)** aus
- Text Encoder HEFs für Hailo-10H existieren in Model Zoo, aber **keine veröffentlichte Anwendung verwendet sie**
- Empfohlener Ansatz: **Text Encoder auf CPU implementieren (`sentence-transformers`)**. Es wird nur einmal pro Suchanfrage ausgeführt, daher ist Geschwindigkeit kein Problem
- Der Image Encoder ist, wo Hailo-Beschleunigung den wirklichen Wert bietet (Batch-Indizierung von 200K Bildern)

### Koexistenz mit hailo-ollama

- Geräte-Sharing via `SHARED_VDEVICE_GROUP_ID` wird offiziell unterstützt
- Jedoch **das hailo-ollama-Binär beteiligt sich nicht an diesem Sharing** (es besitzt das Gerät exklusiv)
- Community-Beispiel: Ein benutzerdefinierter Geräte-Manager wurde gebaut, um 6 Dienste gleichzeitig auszuführen
- **Praktischer Ansatz**: hailo-ollama während Index-Erstellung stoppen und das Gerät zeitlich teilen
  - `systemctl stop hailo-ollama` -> Index erstellen -> `systemctl start hailo-ollama`

### Vektor-Such-Schätzungen für 200.000 Datensätze

- 200K x 512 float32 = ungefähr 400MB — passt in Pi5 (8GB) RAM
- numpy Batch-Kosinus-Ähnlichkeit sollte innerhalb von 1 Sekunde auf dem Pi5 Cortex-A76 abgeschlossen sein

### FAISS-Beschleunigung für großmaßstäbliche Vektor-Suche (v3.26.0)

FAISS (Facebook AI Similarity Search) Unterstützung wurde in v3.26.0 hinzugefügt. Das System erkennt automatisch `faiss-cpu` wenn installiert und verwendet ungefähre Nearest-Neighbor-Suche anstelle von NumPy Brute Force.

| Maßstab | NumPy (O(N)) | FAISS IndexFlatIP | FAISS IndexIVFFlat |
|------|-------------|-------------------|-------------------|
| 10K | ~10ms | ~2ms | - |
| 100K | ~100ms | ~20ms | ~5ms |
| 500K | ~500ms | ~100ms | ~10ms |
| 1.5M | ~1.5s | ~300ms | ~20ms |

- **< 50K**: IndexFlatIP (genaue innere Produkt-Suche) wird automatisch ausgewählt
- **>= 50K**: IndexIVFFlat (IVF Clustering) wird automatisch ausgewählt, nprobe = nlist/10
- Fallback zu NumPy, wenn FAISS nicht installiert ist (kein Einfluss)

**Installation**:
```bash
source venv/bin/activate
uv pip install faiss-cpu  # Direktes pip install funktioniert auf x86_64
# Auf aarch64 (RPi): conda install -c conda-forge faiss-cpu oder von Quelle erstellen
```

Das Startup-Protokoll zeigt `FAISS x.x.x detected — using accelerated vector search` wenn aktiv.

### Notizen zur hailo-CLIP App

- `hailo-ai/hailo-CLIP` zielt auf **Hailo-8/8L**. Hailo-10H wird nicht unterstützt
- Es ist für Zero-Shot-Echtzeit-Klassifizierung konzipiert, nicht für Image-Such-Pipelines
- Es dient als Referenzmaterial, kann aber nicht direkt verwendet werden. Eine benutzerdefinierte Pipeline muss mit der HailoRT API erstellt werden

---

## Alternative (Wenn Hailo nicht verfügbar ist)

`sentence-transformers` mit `clip-ViT-B-32` bietet CPU-only CLIP-Unterstützung. Es ist langsamer, aber ermöglicht, dass die gleiche Erweiterung in Umgebungen ohne Hailo ausgeführt wird.

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('clip-ViT-B-32')
image_embedding = model.encode(Image.open(path))
text_embedding  = model.encode("blue sky")
```

Einstellung `"device": "cpu"` in der Erweiterungskonfiguration aktiviert CPU-Modus. Dieser Dual-Architektur-Ansatz maximiert Portabilität.

---

## Implementierungs-Priorität

```
Phase 1 (Verifizierung)   -> Erforderlich, zuerst machen
Phase 2 (DB)             -> Nach Phase 1 Erfolg
Phase 3 (Inferenz Core)  -> Nach Phase 2
Phase 4 (Indizierung)    -> Nach Phase 3
Phase 5 (Such-API)       -> Nach Phase 4
Phase 6 (UI)             -> Nach Phase 5, zuletzt
```

Wechseln Sie zur CPU CLIP-Architektur, wenn Phase 1 fehlschlägt.

---

## Referenz-Repositories

- `hailo-ai/hailo-apps`: CLIP Zero-Shot-Klassifizierungs-Beispiele
- `hailo-ai/hailort`: pyHailoRT API-Referenz
- `hailo-ai/Hailo-Application-Code-Examples`: Python Inferenz-Beispiele
- `hailo-ai/hailo_model_zoo`: CLIP/SigLIP HEF Download-Quelle

---

*Erstellt: 2026-02-27*
*Forschungs-Ergänzung: 2026-02-27 — Phase 1 Prozedur-Details, HEF-Verfügbarkeits-Bestätigung, hailo-ollama Koexistenz-Analyse*
