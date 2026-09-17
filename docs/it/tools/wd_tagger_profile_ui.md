# Guida UI profili WD-Tagger

Questo documento spiega come usare l’**interfaccia di gestione profili** di WD-Tagger (aggiunta in v4.197.0+).

## 1. Panoramica

- Un **profilo** raggruppa impostazioni WD-Tagger: file del modello, definizione tag, soglie e preprocessamento.
- Apri: pagina Tools → sezione **WD-Tagger** → `Gestisci profili...`.
- Nel modale si passa tra **Lista (List)** e **Modulo (Form)**.

## 2. Vista lista (List)

### 2.1 Badge (Builtin / User)

- `builtin`: profili integrati (sola lettura)
- `user`: profili utente (creazione/modifica/eliminazione)
- `↻`: il profilo **sovrascrive** un profilo integrato con lo stesso `id`

### 2.2 Filtro (All / User / Builtin)

Pulsanti:

- `Tutti`
- `Utente`
- `Integrati`

### 2.3 Pulsanti (azioni)

Azioni per riga:

- `Duplica`: copia il profilo e apre il modulo (per personalizzare un profilo integrato)
- `Modifica`: modifica un profilo utente (integrati non modificabili)
- `Elimina`: elimina un profilo utente (integrati non eliminabili)
- `Esporta`: scarica il profilo come `.json`
- `Test (download a secco)`: verifica senza download reale che i file siano recuperabili da HuggingFace

In alto a destra:

- `+ Nuovo`: crea un profilo vuoto
- `Importa`: crea un profilo da JSON (upload / incolla)

## 3. Vista modulo (Form)

Il modulo è diviso in 5 sezioni a fisarmonica.

### 3.1 Metadata

- `id`: identificatore profilo (non modificabile in seguito)
- `Nome visualizzato`: nome nella lista
- `profile_version`: versione schema (di solito lasciare invariata)

### 3.2 Model & Files

- `model_id`: id modello HuggingFace (es.: `SmilingWolf/wd-swinv2-tagger-v3`)
- `adapter_family`, `backend`, `hf_subdir`: solo se necessario
- `File`:
  - `name`: nome file (es.: `model.onnx`)
  - `Obbligatorio`: trattato come richiesto nel test
  - `size_hint_mb`: opzionale
  - `+ Aggiungi file` / `Rimuovi`: aggiungi/rimuovi righe

### 3.3 Tag source

Origine delle definizioni dei tag.

- `csv`: file(file), separatore(delimiter), colonna nome(name_col), colonna categoria(category_col), mappa(category_map)
- `json_list`: file(file), schema(schema)
- `json_dict`: file(file), mappatura(mapping)
- `composite`: combinazione sorgenti(sources)

### 3.4 Threshold source

Origine delle soglie.

- `global_per_category`: soglie per categoria direttamente in UI
- `per_tag`: file + fallback
  - file(file)
  - modalità fallback(fallback.mode): `global` / `category_default`
  - valore fallback(fallback.value)

### 3.5 Preprocess & Categories

- Preprocesso(`preprocess_spec`): `input_size`, `dtype`, `layout`, `channel_order`, `resize_strategy` (`letterbox` / `longest_side_pad` / `stretch`), `scale`, `mean`, `std`
- Categorie:
  - `Categorie supportate`
  - `categories_mode`: `from_tag_source` / `all_general`

## 4. Import / Export

### 4.1 Importa

`Importa` mostra due tab:

- Carica JSON: carica un file `.json`
- Incolla JSON: incolla JSON nell’area di testo

Dopo l’import il modulo si apre. Controlla/modifica e poi `Salva`.

### 4.2 Esporta

In lista, `Esporta` scarica il profilo come JSON.

## 5. Test (download a secco)

- Verifica se i file elencati in `files` sono recuperabili da **HuggingFace**.
- In caso di successo può comparire `Download OK: {n} file ({total} MB)`.
- In caso di errore viene mostrata la causa (sezione successiva).

## 6. Errori comuni (breve)

- `id_conflict`: esiste già un profilo utente con lo stesso `id`
- `id_immutable`: `id` non modificabile (rinomina con Duplica → Elimina)
- `in_use`: impossibile eliminare perché il profilo è attivo
- `validation_failed`: validazione fallita (`{detail}` contiene dettagli)
- `profile_too_large`: JSON importato > 1MB
- `ssrf_blocked`: reindirizzamento fuori da HuggingFace bloccato (protezione SSRF)
- `hf_unavailable`: HuggingFace non disponibile / risposta non valida
- `timeout`: timeout (60s)
- `required_missing`: file obbligatorio mancante

## 7. Limitazioni (importante)

- I profili integrati (`builtin`) non sono modificabili/eliminabili. Usa `Duplica`.
- `id` è immutabile. Per rinominare: `Duplica` → `Elimina` il vecchio.
- Limite import: **1MB**.
- `Test` consente solo host HuggingFace (allowlist SSRF):
  - `huggingface.co`
  - `hf.co`
