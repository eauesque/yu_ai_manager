# API WD Tagger

API per WD Tagger (Waifu Diffusion Tagger) Tagging automatico Danbooru. Fornisce gestione della configurazione, tagging singolo/batch, CRUD tag, gestione dei modelli, lettura XMP e test della connessione VLM.

## GET /api/wd-tagger/config

Ottieni la configurazione attuale di WD Tagger.

### Parametri

Nessuno

### Risposta

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

## POST /api/wd-tagger/config

Salva/aggiorna la configurazione di WD Tagger.

### Limite di Velocità

WRITE

### Richiesta

```json
{
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "threshold": 0.35
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| *(qualsiasi chiave)* | any | No | Campo di configurazione. Le chiavi sconosciute o i valori non validi restituiscono `400` |

### Risposta

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `invalid_json` | 400 | Il corpo della richiesta non è un oggetto JSON |
| `invalid_value` | 400 | Valore di configurazione non valido |

## POST /api/wd-tagger/tag/<file_id>

Esegui l'inferenza WD Tagger su un file singolo per prevedere e assegnare tag Danbooru.

### Limite di Velocità

HEAVY

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `file_id` | int | ID file (parametro di percorso) |

### Richiesta

```json
{
  "force": false
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `force` | boolean | No | Se `true`, sovrascrivi i tag esistenti e ri-esegui l'inferenza. Predefinito `false` |

### Risposta

```json
{
  "file_id": 42,
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general"},
    {"tag": "solo", "score": 0.95, "category": "general"}
  ]
}
```

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `tag_error` | 400 | Tagging fallito (file non trovato, errore di caricamento immagine, ecc.) |

## GET /api/wd-tagger/tags/<file_id>

Ottieni i tag WD Tagger archiviati per un file specifico.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID file (parametro di percorso) |
| `model` | string | No | Filtra per nome del modello (parametro di query) |
| `all` | boolean | No | When `1`, `true`, or `yes`, return tags from all models and ignore the active model and `model` filter |

### Risposta

```json
{
  "file_id": 42,
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"},
    {"tag": "solo", "score": 0.95, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"}
  ]
}
```

## DELETE /api/wd-tagger/tags/<file_id>

Cancella i tag WD Tagger per un file specifico.

### Limite di Velocità

WRITE

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_id` | int | Yes | ID file (parametro di percorso) |
| `model` | string | No | Filtra per nome del modello (parametro di query). Se omesso, cancella i tag da tutti i modelli |

### Risposta

```json
{
  "file_id": 42,
  "deleted": 15
}
```

## DELETE /api/wd-tagger/tags/batch

Cancella i tag WD Tagger per più file contemporaneamente.

### Limite di Velocità

WRITE

### Richiesta

```json
{
  "file_ids": [1, 2, 3],
  "model": "wd-swinv2-tagger-v3"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_ids` | list | Yes | Array di ID file (max 500) |
| `model` | string | No | Filtra per nome del modello. Se omesso, cancella i tag da tutti i modelli |

### Risposta

```json
{
  "deleted_files": 3,
  "deleted_tags": 45
}
```

## Active model (v4.192.0+)

Quando lo stesso file viene rietichettato con più modelli WD Tagger,
`file_wd_tags` conserva i tag di ogni modello come cronologia. Impostando un
active model, la vista di dettaglio, la ricerca `ai_analyzed` e il controllo
interno "già taggato" di WD Tagger usano solo i tag di quel modello. Se non è
impostato alcun active model, resta il comportamento precedente e i tag di tutti
i modelli vengono considerati insieme.

### Configurazione nella UI

Il retag modal mostra in alto l'`Active model` corrente. Usa il dropdown
`Change` per scegliere un modello disponibile. Scegli `(none / reset)` per
azzerare l'active model.

Dopo un retag, il modello usato diventa active model per impostazione
predefinita. Disattiva la casella "Imposta come modello attivo dopo il retag" nel
retag modal per mantenere l'active model corrente.

Le row dei vecchi modelli non vengono eliminate automaticamente. Rimangono nel
database come cronologia. Per rimuoverle esplicitamente, abilita "Elimina anche
i tag degli altri modelli" nel retag modal e conferma il dialogo dopo il retag.


### GET /api/wd-tagger/profiles

Returns registered WD Tagger profiles and the current active model. Requires admin scope.

```json
{
  "profiles": [
    {
      "id": "camie_tagger_v2",
      "display_name": "Camie Tagger v2",
      "model_id": "Camais03/camie-tagger-v2",
      "adapter_family": "camie",
      "backend": "onnx",
      "builtin": true,
      "has_tags": false
    }
  ],
  "active_model_id": "Camais03/camie-tagger-v2"
}
```

### GET /api/wd-tagger/active-model

Restituisce l'active model corrente e l'elenco dei modelli presenti nel database.
Richiede admin scope.

```json
{
  "active_model_id": "SmilingWolf/wd-eva02-large-tagger-v3",
  "available_models": [
    {"model_id": "SmilingWolf/wd-eva02-large-tagger-v3", "file_count": 120},
    {"model_id": "SmilingWolf/wd-swinv2-tagger-v3", "file_count": 340}
  ]
}
```

### PUT /api/wd-tagger/active-model

Cambia l'active model. Richiede admin scope. Invia `null` o una stringa vuota in
`model_id` per reimpostarlo.

```json
{
  "model_id": "SmilingWolf/wd-eva02-large-tagger-v3"
}
```

| Codice | Stato | Descrizione |
|--------|-------|-------------|
| `invalid_model_id` | 400 | model_id è troppo lungo o contiene caratteri di controllo |
| `unknown_model` | 400 | Nel database non esistono tag per il modello indicato |

## POST /api/wd-tagger/batch

Esegui il tagging batch su più file. Se `file_ids` è specificato, vengono elaborati solo quei file. Se omesso, auto-seleziona i file non taggati fino a `limit`.

### Limite di Velocità

HEAVY

### Richiesta

```json
{
  "file_ids": [1, 2, 3],
  "limit": 100,
  "force": false,
  "scan_root": ""
}
```

| Parametro | Tipo | Obbligatorio | Limite | Descrizione |
|-----------|------|----------|-------|-------------|
| `file_ids` | int[] | No | Max 500 | Array degli ID file target. Se omesso, i file non taggati vengono selezionati automaticamente |
| `limit` | int | No | - | Max file da elaborare quando `file_ids` è omesso. Predefinito `100` |
| `force` | boolean | No | - | Se `true`, sovrascrivi i tag esistenti. Predefinito `false` |
| `scan_root` | string | No | - | Filtra per percorso della radice di scansione. Stringa vuota per tutti i file |

### Risposta

```json
{
  "job_id": "wd_tagger",
  "total": 100,
  "status": "started"
}
```

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `batch_too_large` | 400 | `file_ids` supera 500 elementi |
| `batch_error` | 409 | Un lavoro batch è già in esecuzione |

## POST /api/wd-tagger/batch/cancel

Cancella un lavoro di tagging batch in esecuzione.

### Limite di Velocità

WRITE

### Richiesta

Nessun corpo richiesto.

### Risposta

```json
{
  "status": "cancelling",
  "message": "Batch tagging cancel requested"
}
```

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `job_not_running` | 404 | Nessun lavoro di tagging batch in esecuzione |

## GET /api/wd-tagger/stats

Ottieni le statistiche di tagging WD Tagger.

### Parametri

Nessuno

### Risposta

```json
{
  "total_tagged": 1234,
  "total_tags": 56789,
  "models": {
    "SmilingWolf/wd-swinv2-tagger-v3": 1200
  },
  "untagged_unknown": 42
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `total_tagged` | int | Numero di file taggati |
| `total_tags` | int | Numero totale di tag archiviati |
| `models` | object | Numero di file taggati per modello |
| `untagged_unknown` | int | Numero di file senza metadati (`unknown`) e senza tag WD |

## GET /api/wd-tagger/untagged

Elenca i file senza metadati (`unknown`) che non sono stati ancora taggati. Supporta la paginazione.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `limit` | int | No | Numero di risultati. 1-500, predefinito `100` |
| `offset` | int | No | Numero di risultati da saltare. Predefinito `0` |

### Risposta

```json
{
  "files": [
    {"id": 10, "filepath": "/images/photo.png", "filename": "photo.png"}
  ],
  "total": 42
}
```

## GET /api/wd-tagger/xmp/<file_id>

Leggi i metadati XMP da un file specifico.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `file_id` | int | ID file (parametro di percorso) |

### Risposta

```json
{
  "file_id": 42,
  "xmp": {
    "subject": ["1girl", "solo", "blue_eyes"],
    "description": "...",
    "creator": "..."
  }
}
```

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `file_not_found` | 404 | File non esiste o è soft-deleted |

## GET /api/wd-tagger/vlm/test

Testa la connettività a un server VLM (Vision Language Model). Verifica la raggiungibilità di un endpoint API compatibile con OpenAI.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `url` | string | Yes | URL del server VLM (parametro di query) |

### Risposta

```json
{
  "ok": true,
  "message": "Connection successful",
  "server_info": "..."
}
```

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `missing_url` | 400 | Parametro `url` non fornito |
| `invalid_url` | 400 | Formato URL non valido |

## GET /api/wd-tagger/vlm/models

Elenca i modelli disponibili su un server VLM. Interroga l'endpoint `/v1/models` compatibile con OpenAI.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `url` | string | Yes | URL del server VLM (parametro di query) |

### Risposta

```json
{
  "models": [
    {"id": "llava-v1.6", "object": "model"}
  ]
}
```

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `missing_url` | 400 | Parametro `url` non fornito |
| `invalid_url` | 400 | Formato URL non valido |
| `vlm_connection_error` | 502 | Errore di connessione al server VLM |

## POST /api/wd-tagger/model/download

Scarica un modello WD Tagger. Recupera i file del modello da Hugging Face e li salva localmente.

### Limite di Velocità

HEAVY

### Richiesta

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `repo` | string | No | Nome del repository Hugging Face. Se omesso, utilizza il valore `model` dalla configurazione |

### Risposta

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "path": "/path/to/model/directory",
  "ready": true
}
```

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `unknown_model` | 400 | Repository del modello sconosciuto. `hint` contiene l'elenco dei modelli noti |
| `download_failed` | 500 | Errore di download |

## GET /api/wd-tagger/model/status

Verifica lo stato del download di un modello WD Tagger.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `repo` | string | No | Nome del repository Hugging Face (parametro di query). Se omesso, utilizza il valore `model` dalla configurazione |

### Risposta

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "downloaded": true,
  "path": "/path/to/model/directory",
  "known_models": {
    "SmilingWolf/wd-swinv2-tagger-v3": "SwinV2 (recommended)",
    "SmilingWolf/wd-convnext-tagger-v3": "ConvNeXt",
    "SmilingWolf/wd-vit-tagger-v3": "ViT"
  }
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `repo` | string | Nome del repository controllato |
| `downloaded` | boolean | Se il modello è scaricato localmente |
| `path` | string/null | Percorso del modello locale se scaricato |
| `known_models` | object | Tutti i modelli supportati (nome repository -> nome di visualizzazione) |

## User profile CRUD (v4.197.0+)

API per fare CRUD dei tagger profile creati dall’utente dalla UI della pagina Tools. Tutti gli endpoint richiedono admin scope. Il formato di errore comune è `{ok: false, error, code, ...extra}`. Il body della richiesta ha un **hard cap di 1MB** (`code: profile_too_large`, 413). `id` deve rispettare la regex `^[a-z0-9][a-z0-9_-]{0,63}$`.

### POST /api/wd-tagger/profiles

Crea un nuovo profile utente.

**Richiesta**: profile JSON (schema v2, `profile_version: "2"`). Il campo `builtin` viene forzatamente sovrascritto a `false` lato server.

**Risposta (200)**:
```json
{
  "ok": true,
  "profile": { "...": "...サニタイズ済 profile JSON..." },
  "origin": "user",
  "overrides_builtin": false
}
```

| Campo | Descrizione |
|---|---|
| `profile` | Profile salvato (garantito `builtin: false`) |
| `origin` | Sempre `"user"` |
| `overrides_builtin` | `true` se esiste un profile builtin con lo stesso id (percorso avanzato) |

**Errori**:

| status | code | condizione |
|---|---|---|
| 400 | `validation_failed` | Il JSON viola lo schema v2 (`extra.errors=[{path, message}, ...]`) |
| 400 | `invalid_id` | L’`id` nel body non rispetta la regex |
| 409 | `id_conflict` | Stesso id di un profile utente già esistente |
| 413 | `profile_too_large` | body > 1MB |

### GET /api/wd-tagger/profiles/{id}

Ottenere il profile schema v2 completo per l’id specificato (chiamato dalla UI durante modifica / duplicazione / Export).

**path**: `id` (verifica regex richiesta)

**Risposta (200)**:
{Stesso formato di POST: profile / origin / overrides_builtin}

**Errori**:
- 400 `invalid_id` (l’id del path non rispetta la regex)
- 404 `not_found`

### PUT /api/wd-tagger/profiles/{id}

Aggiorna un profile utente esistente.

**path**: `id` (verifica regex richiesta)

**Richiesta**: profile JSON. `body.id` deve corrispondere all’id del path (per rinominare, guida la UI a `Duplicate → Delete`).

**Risposta (200)**: Stesso formato di POST.

**Errori**:

| status | code | condizione |
|---|---|---|
| 400 | `id_immutable` | l’id del path e l’id del body non corrispondono |
| 400 | `invalid_id` | l’id del path non rispetta la regex |
| 400 | `validation_failed` | violazione dello schema |
| 403 | `builtin_read_only` | l’id del path è un profile builtin (nessun file utente corrispondente) |
| 404 | `not_found` | id non registrato |
| 413 | `profile_too_large` | body > 1MB |

### DELETE /api/wd-tagger/profiles/{id}

Elimina un profile utente.

**path**: `id`

**Risposta (200)**:
```json
{"ok": true, "deleted": true}
```

**Errori**:

| status | code | condizione |
|---|---|---|
| 400 | `invalid_id` | id del path non valido |
| 403 | `builtin_read_only` | solo builtin, senza override utente |
| 404 | `not_found` | id non registrato |
| 409 | `in_use` | Questo profile è il modello attivo (include `extra.active_model_id`). Nella UI, cambia il profile attivo via `PUT /api/wd-tagger/active-model` e poi riprova |

### POST /api/wd-tagger/profiles/{id}/test

dry-run download. Esegue HEAD per ogni `files[]` su HuggingFace e, per quelli con `required: true`, effettua un download atomico per file (la cache riusa il percorso esistente).

**path**: `id`

**body**: non richiesto

**Comportamento**:
- per-file timeout: 30s
- timeout complessivo: 60s
- redirect: allowlist solo per i sottodomini `huggingface.co` / `hf.co`, max 5 hops; userinfo (`user:pass@`) è SSRFBlocked

**Risposta (200, successo)**:
```json
{
  "ok": true,
  "files": [
    {"name": "model.onnx", "status": "downloaded", "size": 1234567},
    {"name": "tags.csv",   "status": "cached",     "size": 89012},
    {"name": "optional.json", "status": "skipped_optional", "size": null}
  ]
}
```

Valori di `status`:
- `downloaded`: scaricato in questa esecuzione
- `cached`: esiste già localmente (solo HEAD)
- `skipped_optional`: `required: false` e 404 / HEAD fallito

**Errori (status / code)**:

| status | code | condizione |
|---|---|---|
| 400 | `invalid_id` / `required_missing` | id del path non valido / file required è 404 su HF |
| 404 | `not_found` | profile non registrato |
| 408 | `timeout` | superato il totale 60s |
| 502 | `ssrf_blocked` | redirect fuori allowlist HF / contiene userinfo / scheme non è http(s) |
| 502 | `hf_unavailable` | HF ha restituito 5xx |

In caso di errore, il body è nella forma `{"ok": false, "code": ..., "error": ..., "files": [...risultati parziali...], "detail": "..."}`.

### Formato profile JSON (schema v2)

```typescript
interface ProfileV2 {
  profile_version: "2";
  id: string;
  display_name: string;
  adapter_family: "wd" | "camie" | "oppai" | "generic_onnx";
  backend: "onnx";
  model_id: string;                        // Percorso repo HF "<owner>/<name>"
  hf_subdir: string | null;
  files: { name: string; required: boolean; size_hint_mb?: number }[];
  default_thresholds: Record<string, number>;
  tag_source: TagSourceSpec;               // type=csv/json_list/json_dict/composite
  threshold_source: ThresholdSourceSpec;   // type=global_per_category/per_tag_json
  preprocess_spec: PreprocessSpec;
  supports_categories: string[];
  categories_mode: "from_tag_source" | "all_general";
  builtin?: boolean;                       // sempre false per origine utente (forzato dal server)
}
```

Per maggiori dettagli, vedi `extensions/builtin_wd_tagger/core_impl/adapters/base.py` (`TaggerProfile`), oppure l’implementazione di riferimento builtin (`extensions/builtin_wd_tagger/core_impl/profiles/*.json`).
