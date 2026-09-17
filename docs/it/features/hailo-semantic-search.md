# Specifica di Implementazione per l'Estensione Ricerca Semantica Hailo

**Status**: Implementato — La versione specifica di Hailo è stata superata da CLIP ONNX (v2.95.0)
**Target**: Estensione YU AI Manager
**Scopo**: Ricerca immagini semantica utilizzando CLIP/SigLIP su Hailo-10H (AI HAT 2)
**Implementazione**: `extensions/builtin_clip_search/core_impl/` (layer condiviso) + `extensions/builtin_clip_onnx/core_impl/` (implementazione ONNX)
**Nota**: Questa specifica descrive il design iniziale solo per Hailo. L'implementazione attuale utilizza un'architettura ONNX multi-backend unificata

---

## Panoramica

Questa Estensione aggiunge la capacità di cercare immagini utilizzando testo in linguaggio naturale.
Esempi: "cielo blu e oceano", "ragazza che sorride", "paesaggio urbano notturno" — tutti restituiscono immagini visivamente simili.

Deve funzionare **in parallelo** con la ricerca tag FTS5 esistente e la ricerca somiglianza pHash.
L'Estensione semplicemente si disabilita negli ambienti in cui nessun dispositivo Hailo è presente.

---

## Architettura

```
[Durante la scansione immagine]
File immagine -> CLIP Image Encoder (Hailo HEF) -> vettore 512-dim -> archiviazione DB

[Durante la ricerca]
Input testo -> CLIP Text Encoder (CPU / Hailo HEF) -> vettore 512-dim
           -> ricerca somiglianza coseno -> lista file_id -> Unione con risultati ricerca esistenti
```

**Sia CLIP che SigLIP sono supportati**, commutabili tramite configurazione.
SigLIP offre maggiore precisione, ma CLIP ha un track record più forte e più risorse comunità.
L'approccio consigliato è iniziare con CLIP e aggiungere SigLIP in seguito.

---

## Suddivisione Fase

### Fase 1: Verifica di Fattibilità (Fare Questo per Primo)

Dopo il passaggio all'ambiente Pi5, esegui i seguenti passaggi **in ordine dall'alto verso il basso**.
Fermati a qualsiasi passo che fallisce e affronta il problema prima di continuare.

#### Passo 1-1: Verifica Runtime HailoRT

```bash
# Controlla il riconoscimento del dispositivo
hailortcli fw-control identify

# Controlla i binding Python
python3 -c "import hailo_platform; print('HailoRT version:', hailo_platform.__version__)"
```

- **Dispositivo non visibile**: Controlla lo stato del driver con `dmesg | grep hailo`. Verifica la connessione PCIe di AI HAT 2
- **Import non riesce**: Installa via `pip install hailort` o dal repository APT di Hailo (`python3-hailort`)

#### Passo 1-2: Scarica File HEF CLIP

```bash
mkdir -p ~/hailo_models && cd ~/hailo_models

# Codificatore immagine
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef

# Codificatore testo
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_text_encoder.hef
```

- **403 / Accesso negato**: La registrazione su Hailo Developer Zone (https://hailo.ai/developer-zone/) è richiesta.
  Dopo la registrazione, prova a scaricare tramite CLI Model Zoo (`hailo_model_zoo`)
- **Controllo dimensione**: Ogni file dovrebbe essere decine di ~100 MB. Un file insolitamente piccolo indica un fallimento del download

#### Passo 1-3: Installa Dipendenze Python

```bash
# Richiesto per la pre-elaborazione immagine (utilizzato in Fase 1)
pip install opencv-python-headless numpy

# Verifica
python3 -c "import cv2; import numpy; print('cv2:', cv2.__version__, 'numpy:', numpy.__version__)"
```

#### Passo 1-4: Test Inferenza Minimo

```python
from hailo_platform import HEF, VDevice, HailoStreamInterface, InferVStreams, ConfigureParams
import numpy as np

hef_path = "/home/<user>/hailo_models/clip_vit_b_16_image_encoder.hef"
hef = HEF(hef_path)

# Controlla le info del layer di input/output HEF (i nomi dei layer variano per modello)
print("Input layers:", [l.name for l in hef.get_input_vstream_infos()])
print("Output layers:", [l.name for l in hef.get_output_vstream_infos()])

with VDevice() as target:
    configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
    network_groups = target.configure(hef, configure_params)
    network_group = network_groups[0]

    input_info = hef.get_input_vstream_infos()[0]
    input_name = input_info.name
    input_shape = input_info.shape  # Previsto: (224, 224, 3) ecc.
    print(f"Input: name={input_name}, shape={input_shape}")

    # Test inferenza con immagine fittizia
    dummy = np.random.randint(0, 255, (1, *input_shape), dtype=np.uint8)
    with InferVStreams(network_group, {}) as pipeline:
        result = pipeline.infer({input_name: dummy})
        for name, data in result.items():
            print(f"Output: name={name}, shape={data.shape}, dtype={data.dtype}")
            # Successo se viene output un vettore 512-dim
```

- **Errore VDevice (`not enough free devices`)**: hailo-ollama potrebbe essere in esecuzione. Fermalo con `systemctl stop hailo-ollama` e ritenta
- **Inferenza riesce ma l'output non è 512-dim**: Verifica la versione HEF e la variante modello

#### Passo 1-5: Criteri di Decisione

| Risultato | Azione Successiva |
|------|----------------|
| Output vettore 512-dim | Procedi a Fase 2 e oltre |
| HEF carica con successo ma dimensioni output differenti | Prova una variante modello differente (clip_resnet_50 ecc.) |
| Impossibile scaricare HEF | Registrati su Developer Zone -> scarica via CLI Model Zoo |
| Impossibile importare hailo_platform | Reinstalla HailoRT. Ricadere a CLIP CPU se irrisolto |
| Dispositivo non riconosciuto | Problema di connessione hardware / driver. Pausa lo sviluppo dell'Estensione |

Procedi con l'implementazione completa se Fase 1 riesce. Considera CLIP CPU come alternativa se non riesce.

---

### Fase 2: Estensione Schema DB

Aggiungi alla migrazione DB esistente:

```sql
-- migrazione 14: vettori ricerca semantica
CREATE TABLE IF NOT EXISTS file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip',   -- 'clip' | 'siglip'
    vector      BLOB NOT NULL,                  -- array numpy float32 -> bytes
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_file_vectors_model ON file_vectors(model);
```

Archiviazione: `numpy.ndarray.tobytes()` -> BLOB
Caricamento: `numpy.frombuffer(blob, dtype=numpy.float32)`

**Nota**: SQLite non ha indice ANN (Approximate Nearest Neighbor), quindi tutti i 200.000 record richiedono il calcolo completo della somiglianza coseno. Il calcolo batch con numpy dovrebbe mantenere questo entro limiti accettabili su Pi5 (misurazione richiesta). Considera l'estensione `sqlite-vec` se il conteggio dei record cresce significativamente.

---

### Fase 3: Core Inferenza Hailo

**Struttura file**:
```
extensions/hailo_semantic_search/
├── __init__.py
├── extension.py          # Punto di ingresso Estensione
├── core/
│   ├── hailo_clip.py     # Wrapper inferenza Hailo CLIP
│   ├── cpu_clip.py       # Fallback CPU per ambienti non-Hailo (opzionale)
│   └── vector_store.py   # DB vettore CRUD
├── routes/
│   └── semantic_search.py  # Endpoint API
└── templates/
    └── _semantic_search_ui.html
```

**Responsabilità di `hailo_clip.py`**:
- Caricamento HEF e inizializzazione VDevice (singleton, una volta all'avvio)
- Immagine -> pre-elaborazione (resize 224x224, normalizzazione) -> inferenza HEF -> vettore 512-dim
- Testo -> tokenizzazione -> inferenza HEF -> vettore 512-dim
  * Usa il codificatore testo HEF se disponibile per Hailo-10H; altrimenti usa CPU (libreria transformers)

**Pre-elaborazione**:
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

### Fase 4: API Costruzione Indice

**Endpoint**:
```
POST /api/extensions/hailo-semantic/index
```
- Elabora le immagini non indicizzate sequenzialmente in un thread di background
- Invia il progresso tramite SSE come eventi `semantic_index.progress`
- Opzionalmente si aggancia all'evento `scan.complete` esistente per l'esecuzione automatica

**Dimensione batch**: 32 immagini per batch (equilibrio tra memoria e velocità)

```
GET /api/extensions/hailo-semantic/index/status
-> { "total": 200000, "indexed": 12500, "running": true }
```

---

### Fase 5: API Ricerca Semantica

```
GET /api/extensions/hailo-semantic/search?q=blue sky&limit=50&threshold=0.25
```

**Flusso di elaborazione**:
1. Converti testo `q` in un vettore
2. Carica tutti i vettori da `file_vectors` (numpy)
3. Calcola somiglianza coseno in batch
4. Ordina i risultati sopra `threshold` per somiglianza decrescente
5. Restituisci la lista `file_id` nel formato `/api/search` esistente

**Calcolo somiglianza coseno**:
```python
def cosine_similarity_batch(query_vec: np.ndarray, stored_vecs: np.ndarray) -> np.ndarray:
    # query_vec: (512,), stored_vecs: (N, 512)
    query_norm = query_vec / np.linalg.norm(query_vec)
    stored_norm = stored_vecs / np.linalg.norm(stored_vecs, axis=1, keepdims=True)
    return stored_norm @ query_norm  # (N,)
```

**Target di prestazione**: Meno di 1 secondo per 200.000 record (raggiungibile con calcolo batch numpy, anche su Pi5)

---

### Fase 6: Integrazione UI

Aggiungi una scheda "Ricerca Semantica" all'UI ricerca esistente.
Può essere un'UI autonoma indipendente dal generatore di condizioni esistente (l'integrazione è per il futuro).

```html
<!-- Aggiungi pulsante toggle accanto alla barra di ricerca -->
<button id="semantic-search-toggle" class="btn-secondary">
  🔍 Ricerca Semantica (Hailo)
</button>
```

- Nascondi o disabilita il pulsante quando nessun dispositivo Hailo è rilevato
- Riutilizza la griglia esistente per i risultati della ricerca
- Mostra un prompt per costruire l'indice quando nessun indice esiste

---

## Configurazione (aggiunta config.json)

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

## Fatti Verificati (a partire da 2026-02-27)

Le seguenti informazioni sono state confermate tramite ricerca precedente. Usale come riferimento durante l'esecuzione della Fase 1.

### Disponibilità HEF CLIP

Hailo Model Zoo v5.2.0 contiene **sia codificatore immagine che codificatore testo** HEF per Hailo-10H su varianti CLIP/SigLIP:

| Modello | HEF Codificatore Immagine | HEF Codificatore Testo |
|--------|-------------------|-------------------|
| clip_vit_b_16 | Disponibile | Disponibile |
| clip_vit_b_32 | Disponibile | Disponibile |
| clip_vit_l_14 | Disponibile | Disponibile |
| clip_resnet_50 | Disponibile | Disponibile |
| siglip_b_16 | Disponibile | Disponibile |
| siglip_l_16_256 | Disponibile | Disponibile |
| siglip2_b_32_256 | Disponibile | Disponibile |
| Varianti TinyCLIP | Disponibile | Disponibile |

Modello URL S3: `https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef`

### Stato Codificatore Testo

- L'app ufficiale `hailo-CLIP` esegue **il codificatore testo su CPU (PyTorch)**
- HEF Codificatore Testo per Hailo-10H esistono in Model Zoo, ma **nessuna applicazione pubblicata li usa**
- Approccio consigliato: **Implementa il codificatore testo su CPU (`sentence-transformers`)**. Viene eseguito solo una volta per query di ricerca, quindi la velocità non è un problema
- Il codificatore immagine è dove l'accelerazione Hailo fornisce valore reale (indicizzazione batch di 200K immagini)

### Coesistenza con hailo-ollama

- La condivisione dispositivo tramite `SHARED_VDEVICE_GROUP_ID` è ufficialmente supportata
- Tuttavia, **il binary hailo-ollama non partecipa a questo condivisione** (occupa esclusivamente il dispositivo)
- Esempio comunità: Un gestore dispositivo personalizzato è stato costruito per eseguire 6 servizi simultaneamente
- **Approccio pratico**: Ferma hailo-ollama durante la costruzione dell'indice e condividi il dispositivo nel tempo
  - `systemctl stop hailo-ollama` -> Costruisci indice -> `systemctl start hailo-ollama`

### Stime Ricerca Vettore per 200.000 Record

- 200K x 512 float32 = approssimativamente 400MB — si adatta entro Pi5 (8GB) RAM
- Somiglianza coseno batch numpy dovrebbe completarsi entro 1 secondo su Cortex-A76 Pi5

### Accelerazione FAISS per Ricerca Vettore su Larga Scala (v3.26.0)

Il supporto FAISS (Facebook AI Similarity Search) è stato aggiunto in v3.26.0. Il sistema rileva automaticamente `faiss-cpu` quando installato e utilizza la ricerca approssimata del vicino più prossimo invece della forza bruta NumPy.

| Scala | NumPy (O(N)) | FAISS IndexFlatIP | FAISS IndexIVFFlat |
|------|-------------|-------------------|-------------------|
| 10K | ~10ms | ~2ms | - |
| 100K | ~100ms | ~20ms | ~5ms |
| 500K | ~500ms | ~100ms | ~10ms |
| 1.5M | ~1.5s | ~300ms | ~20ms |

- **< 50K**: IndexFlatIP (ricerca prodotto interno esatto) viene auto-selezionato
- **>= 50K**: IndexIVFFlat (clustering IVF) è auto-selezionato, nprobe = nlist/10
- Ricade a NumPy quando FAISS non è installato (nessun impatto)

**Installazione**:
```bash
source venv/bin/activate
uv pip install faiss-cpu  # L'installazione pip diretta funziona su x86_64
# Su aarch64 (RPi): conda install -c conda-forge faiss-cpu o costruisci dal sorgente
```

Il log di avvio mostra `FAISS x.x.x detected — using accelerated vector search` quando attivo.

### Note sull'App hailo-CLIP

- `hailo-ai/hailo-CLIP` è rivolto a **Hailo-8/8L**. Hailo-10H non è supportato
- È progettato per classificazione zero-shot in tempo reale, non pipeline di ricerca immagini
- Serve come materiale di riferimento ma non può essere usato direttamente. Una pipeline personalizzata deve essere costruita utilizzando l'API HailoRT

---

## Alternativa (Quando Hailo Non È Disponibile)

`sentence-transformers` con `clip-ViT-B-32` fornisce supporto CLIP solo CPU.
È più lento ma consente la stessa Estensione di funzionare in ambienti senza Hailo.

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('clip-ViT-B-32')
image_embedding = model.encode(Image.open(path))
text_embedding  = model.encode("blue sky")
```

L'impostazione `"device": "cpu"` nella configurazione dell'Estensione abilita la modalità CPU. Questo approccio dual-architecture massimizza la portabilità.

---

## Priorità Implementazione

```
Fase 1 (Verifica)   -> Richiesta, fare questo per primo
Fase 2 (DB)             -> Dopo successo Fase 1
Fase 3 (Core Inferenza) -> Dopo Fase 2
Fase 4 (Indicizzazione) -> Dopo Fase 3
Fase 5 (API Ricerca)    -> Dopo Fase 4
Fase 6 (UI)             -> Dopo Fase 5, ultimo
```

Passa all'intero approccio CLIP CPU se Fase 1 non riesce.

---

## Repository di Riferimento

- `hailo-ai/hailo-apps`: Campioni classificazione zero-shot CLIP
- `hailo-ai/hailort`: Riferimento API pyHailoRT
- `hailo-ai/Hailo-Application-Code-Examples`: Campioni inferenza Python
- `hailo-ai/hailo_model_zoo`: Fonte download HEF CLIP/SigLIP

---

*Creato: 2026-02-27*
*Addendum ricerca: 2026-02-27 — Dettagli procedura Fase 1, conferma disponibilità HEF, analisi coesistenza hailo-ollama*
