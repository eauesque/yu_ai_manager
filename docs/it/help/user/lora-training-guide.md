# Guida all'Addestramento LoRA

Guida completa alla creazione di LoRA con YU AI Manager + MCP + kohya_ss tramite linguaggio naturale

---

## Introduzione

Questa guida pratica spiega come creare LoRA solo con istruzioni in linguaggio naturale, integrando il server MCP di YU AI Manager con kohya_ss.

Il grosso del lavoro tradizionale per la creazione di LoRA era la "preparazione manuale del dataset". Selezione delle immagini, revisione ed esclusione dei tag, formattazione dei file caption, organizzazione della struttura cartelle — tutto a carico degli esseri umani.

Con l'integrazione MCP di YU AI Manager questo flusso cambia. Con solo l'istruzione "crea una LoRA di ○○. Escludi i tag △△", funziona in modo coerente dalla raccolta materiale al tagging, generazione dataset e avvio di kohya_ss.

---

## Flusso Complessivo

Il processo di creazione LoRA è composto da 5 fasi.

| Fase | Contenuto | Responsabile |
|------|-----------|--------------|
| 1. Preparazione materiale | Raccolta e posizionamento immagini di addestramento | Umano / Agente AI |
| 2. Tagging | Tagging automatico con WD-Tagger | MCP (automatico) |
| 3. Generazione Dataset | Creazione progetto, configurazione tag esclusione, export | MCP (automatico) |
| 4. Esecuzione addestramento | Avvio addestramento tramite kohya_ss | MCP (automatico) |
| 5. Verifica | Verifica risultati con SD usando la LoRA | Umano |

L'intervento umano si limita alla decisione "cosa addestrare" e alla verifica finale del risultato.

---

## Prerequisiti

### Software Necessario

- YU AI Manager — con funzionalità server MCP
- Claude Desktop o Claude Code — client MCP
- kohya_ss — con sd-scripts
- Stable Diffusion WebUI (A1111 / ComfyUI / Forge) — per verifica risultati

### Requisiti GPU

| GPU VRAM | Modelli supportati | Impostazioni necessarie |
|---------|-------------------|------------------------|
| 8GB | Solo SD 1.5 praticabile | `--gradient_checkpointing` obbligatorio |
| 12GB | SDXL funziona (con limitazioni) | `--gradient_checkpointing` + `--cache_latents_to_disk` |
| 16GB | SDXL comodo | Funziona con impostazioni predefinite |
| 24GB+ | SDXL e FLUX supportati | Quasi nessuna limitazione |

### Struttura Directory kohya_ss

```
O:\webui\kohya_ss\              ← Directory top-level da impostare in kohya_path
O:\webui\kohya_ss\venv\         ← Ambiente virtuale Python (rilevato automaticamente)
O:\webui\kohya_ss\sd-scripts\   ← Directory con gli script di addestramento
```

> ⚠️ **Nota**: YU AI Manager rileva automaticamente la sottocartella `sd-scripts` e il venv dalla directory top-level specificata in `kohya_path`. Non specificare direttamente il percorso di sd-scripts.

---

## Configurazione YU AI Manager

### Impostazioni Extension

Inserire quanto segue nella scheda delle impostazioni di LoRA Dataset Manager.

| Impostazione | Descrizione | Esempio |
|-------------|-------------|---------|
| `kohya_path` | Directory top-level kohya_ss | `O:\webui\kohya_ss` |
| `output_base_dir` | Directory base output dataset | `C:\lora_datasets` |
| `checkpoint_dir` | Directory del modello base | `O:\webui\models\Stable-diffusion` |
| `default_base_model` | Tipo modello predefinito | `sdxl` |

### Configurazione WD-Tagger

Per uso con dataset LoRA non è consigliata la combinazione con VLM (llava ecc.). Il VLM genera grandi quantità di tag a testo libero, peggiorando la qualità dei caption.

```
engine_type: "onnx"  ← Usare ONNX standalone
```

> ⚠️ **Nota**: Impostando `engine_type` a `"both"` vengono generati tag compositi derivati da VLM (come `wooden_bear_and_fish_sculpture`). Questi non funzionano come caption per kohya_ss e ostacolano l'addestramento.

---

## Procedura di Creazione LoRA tramite MCP

### Step 1: Preparazione Immagini Materiale

Posizionare le immagini di addestramento nella scan root di YU AI Manager ed effettuare la scansione.

- Aggiungere la cartella di addestramento nelle impostazioni Scan Root di YU AI Manager
- Dopo il completamento della scansione, le immagini target vengono registrate nel DB
- Minimo 20~30, consigliati 50~200

### Step 2: Tagging con WD-Tagger

Eseguire il tagging batch da MCP.

```python
# Ottenere la lista ID file target ed eseguire il tagging batch
wd_tagger_batch(file_ids=[...], expected_count=N)
wait_for_batch(job_id="wd_tagger")
```

Se sono presenti tag esistenti, eliminarli prima di rieseguire.

```python
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
```

### Step 3: Creazione Progetto

```python
create_lora_project(
    name="carved_bear",
    concept="carved_bear",   # Usato come nome cartella in kohya_ss
    base_model="sdxl",
    repeat=20
)
```

### Step 4: Impostazione File e Tag

Impostare gli ID file nel progetto e verificare il conteggio tag.

```python
update_lora_project(project_id=N, file_ids=[...])
get_lora_project_tags(project_id=N)
```

Verificare il conteggio tag e decidere quali escludere.

#### Filosofia di Design dei Tag da Escludere

Questo è il nucleo di "cosa far imparare alla LoRA".

**Tag da mantenere**: Caratteristiche uniche del concetto da apprendere (forma, stile, elementi unici)

**Tag da escludere**: Tag generici già noti al modello (`no_humans`, `realistic`, `animal`, `solo`, tag sfondo ecc.)

```python
update_lora_project(
    project_id=N,
    tag_exclude=["no_humans", "animal_focus", "animal", "realistic", ...]
)
```

### Step 5: Verifica Anteprima Caption

```python
preview_lora_caption(project_id=N, file_id=ID_file_qualsiasi)
```

Verificare che non ci sia rumore VLM e che sia una sequenza semplice di tag.

### Model Scope

Each project has a `model_scope` setting that controls which WD-Tagger model is used for captions, preview, and export.

- `active` (default for new projects): Use tags from the active WD model only. If no active model is set, it falls back to all models.
- `all` (default for existing projects): Mix tags from all models.
- `<model_id>` (for example, `wd-eva02-large-tagger-v3`): Use tags from the explicitly selected model only.

For files tagged by multiple models, `active` is usually sufficient. When you need an explicit model for comparison or validation, use the same model_id shown in the WD-Tagger profile dropdown on the Tools page.

### Step 6: Export Dataset

```python
export_lora_dataset(project_id=N)
```

Struttura cartella output:

```
{output_base_dir}/{project_name}/{repeat}_{concept}/
    image001.jpeg
    image001.txt   ← caption
    image002.jpeg
    image002.txt
```

### Step 7: Esecuzione Addestramento

Prima verificare il comando con dry_run.

```python
preview_lora_train_command(
    project_id=N,
    checkpoint="percorso_completo\checkpoint.safetensors"
)
```

Se non ci sono problemi, avviare l'addestramento.

```python
start_lora_training(
    project_id=N,
    checkpoint="percorso_completo\checkpoint.safetensors",
    extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
)
```

Verifica avanzamento:

```python
get_lora_train_status(project_id=N, tail=20)
```

---

## Parametri di Addestramento Predefiniti

| Parametro | Valore predefinito | Descrizione |
|-----------|-------------------|-------------|
| `network_dim` | 32 | Rank LoRA. Maggiore = più espressivo ma file più grande |
| `network_alpha` | 16 | Di solito impostato alla metà del dim |
| `learning_rate` | 1e-4 | Learning rate |
| `max_train_epochs` | 10 | Numero di epoch |
| `save_every_n_epochs` | 2 | Intervallo salvataggio intermedio |
| `mixed_precision` | fp16 | Precisione. bf16 può risparmiare VRAM |
| `resolution` | 1024,1024 (SDXL) | Risoluzione addestramento. SD1.5: 512,512 |

---

## Impostazioni Consigliate per GPU

| GPU VRAM | extra_args consigliati |
|---------|----------------------|
| 8GB | `--gradient_checkpointing --xformers --cache_latents_to_disk --optimizer_type=AdamW8bit` |
| 12GB | `--gradient_checkpointing --xformers --cache_latents_to_disk` |
| 16GB | (funziona con predefiniti) |
| 24GB+ | (funziona con predefiniti, possibile aumentare batch_size) |

---

## Risoluzione dei Problemi

### ModuleNotFoundError: No module named 'torch'

**Causa**: Si sta cercando di eseguire gli script di kohya_ss con il venv di YU AI Manager.

**Soluzione**: Impostare `kohya_path` nella directory top-level (il genitore di sd-scripts). YU AI Manager rileva automaticamente `kohya_path/venv/Scripts/python.exe`.

---

### torch.OutOfMemoryError: CUDA out of memory

**Causa**: VRAM insufficiente.

**Soluzione**: Aggiungere quanto segue a `extra_args`.

```python
extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
```

---

### Contaminazione da tag rumore VLM

**Causa**: `engine_type` è impostato su `"both"` e il VLM (llava ecc.) sta generando tag a testo libero.

**Soluzione**: Cambiare `engine_type="onnx"` nelle impostazioni WD-Tagger, eliminare tutti i tag e ripetere il tagging.

```python
wd_tagger_save_config({"engine_type": "onnx"})
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
wd_tagger_batch(file_ids=[...], expected_count=N)
```

---

## Prompt per la Generazione

### Struttura Base del Prompt

```
{concept_token}, {tag_caratteristiche}, <lora:{nome_lora}:{forza}>
```

Esempio per LoRA orso intagliato nel legno:

```
carved_bear, wooden sculpture, bear statue, wood texture, brown,
full_body, standing, open_mouth, fish, simple_background,
<lora:carved_bear:0.7>
```

Prompt negativo:

```
blurry, lowres, bad anatomy, worst quality, flat color, monochrome
```

### Regolazione della Forza LoRA

| Forza | Caratteristiche |
|-------|-----------------|
| 0.5~0.6 | Influenza forte del modello base |
| 0.7~0.8 | Intervallo consigliato. Buon equilibrio |
| 0.9~1.0 | Forte influenza LoRA. La forma emerge ma i colori tendono al bianco/crema |

---

## Riepilogo

Con il flusso YU AI Manager + MCP + kohya_ss è possibile ridurre notevolmente il lavoro di creazione LoRA.

- Dalla preparazione delle immagini materiale al completamento dell'addestramento di tutte le epoch, il flusso funziona solo con istruzioni MCP
- L'intero flusso funziona con istruzioni in linguaggio naturale
- Le immagini generate esprimono chiaramente la forma dell'oggetto da apprendere

## Selezione immagini

1. Filtra per qualità (4-5 stars)
2. Seleziona stile coerente
3. Evita sfondi complessi
4. Target 20-100 immagini

## Preprocessing

- Resize: 512px (SD1.5), 768-1024px (SDXL)
- Crop square per 1:1
- Converti JPG → PNG per qualità

## Tagging

- Usa WD-Tagger per auto-tag
- Aggiungi trigger word personalizzato
- Normalizza tag capitalization
- 5-15 tag per immagine

## Dataset export

```bash
# Seleziona collection in UI
# Clicca "Export for LoRA"
# Seleziona folder destinazione
```

File generati:
- `images/` — Immagini PNG
- `captions.json` — Metadata e prompt

## Configurazione training

Parametri consigliati:
- Learning rate: 1e-4
- Epochs: 10-20
- Batch size: 4
- Save interval: ogni 5 epoch

## Testing output

- Genera con trigger word
- Compara con output base
- Iterate su training

## Troubleshooting

- Overfitting: Aumenta dataset size
- Blurry output: Riduci learning rate
- Memory error: Riduci batch size
