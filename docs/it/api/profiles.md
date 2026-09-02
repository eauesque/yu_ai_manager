# API Profili

API per la gestione dei profili di configurazione. I profili sono snapshot denominati delle impostazioni dell'applicazione, archiviati come `profiles/<name>.json`.

Tutti gli endpoint richiedono autenticazione PIN. Restituisce 403 se l'autenticazione PIN è disabilitata, o 401 se la sessione non è autenticata.

## Regole del Nome del Profilo

- 1 a 64 caratteri
- Caratteri consentiti: `a-zA-Z0-9_-`

---

## GET /api/profiles

Elenca i metadati per tutti i profili. Ordinati per preferiti prima, quindi alfabeticamente per etichetta.

### Parametri

Nessuno

### Risposta

```json
{
  "profiles": [
    {
      "name": "default",
      "label": "Default",
      "description": "Standard configuration",
      "favorite": true,
      "last_used_at": "2026-03-20T12:00:00Z",
      "created_at": "2026-01-01T00:00:00Z",
      "db": null,
      "is_active": true
    }
  ]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `name` | string | Nome del profilo (utilizzato come nome del file) |
| `label` | string | Etichetta di visualizzazione |
| `description` | string | Testo della descrizione |
| `favorite` | boolean | Flag preferito |
| `last_used_at` | string/null | Timestamp dell'ultimo utilizzo (ISO 8601) |
| `created_at` | string/null | Timestamp di creazione (ISO 8601) |
| `db` | string/null | Percorso del database associato |
| `is_active` | boolean | Se questo è il profilo attivo attualmente |

## GET /api/profiles/\<name\>

Ottieni i dati completi di un profilo specifico.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome del profilo (parametro di percorso) |

### Risposta

```json
{
  "profile": {
    "name": "default",
    "label": "Default",
    "description": "Standard configuration",
    "favorite": false,
    "created_at": "2026-01-01T00:00:00Z",
    "last_used_at": "2026-03-20T12:00:00Z",
    "is_active": true
  }
}
```

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `invalid_profile_name` | 400 | Nome del profilo non valido |
| `profile_not_found` | 404 | Profilo non esiste |

## POST /api/profiles

Crea un nuovo profilo.

### Limite di Velocità

WRITE

### Richiesta

```json
{
  "name": "my_profile",
  "label": "My Profile",
  "description": "Custom settings",
  "base_config": {}
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `name` | string | Yes | Nome del profilo (`a-zA-Z0-9_-`, 1-64 caratteri) |
| `label` | string | No | Etichetta di visualizzazione. Predefinito al `name` se omesso |
| `description` | string | No | Testo della descrizione |
| `base_config` | object | No | Valori di configurazione iniziali. Le chiavi diverse dalle chiavi di metadati (`name`, `label`, `description`, `favorite`, `last_used_at`, `created_at`, `db`) vengono copiate nel profilo |

### Risposta (201)

```json
{
  "profile": {
    "name": "my_profile",
    "label": "My Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `invalid_profile_name` | 400 | Nome del profilo non valido |
| `invalid_label` | 400 | L'etichetta è vuota |
| `profile_exists` | 409 | Un profilo con lo stesso nome esiste già |

## PUT /api/profiles/\<name\>

Aggiorna i metadati del profilo. Solo `label`, `description` e `favorite` possono essere modificati.

### Limite di Velocità

WRITE

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome del profilo (parametro di percorso) |

### Richiesta

```json
{
  "label": "Updated Label",
  "description": "Updated description",
  "favorite": true
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `label` | string | No | Etichetta di visualizzazione |
| `description` | string | No | Testo della descrizione |
| `favorite` | boolean | No | Flag preferito |

Deve essere fornito almeno un campo.

### Risposta

```json
{
  "profile": {
    "name": "my_profile",
    "label": "Updated Label",
    "description": "Updated description",
    "favorite": true,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `empty_update` | 400 | Nessun campo specificato per l'aggiornamento |
| `update_failed` | 400 | Profilo non trovato, ecc. |

## DELETE /api/profiles/\<name\>

Cancella un profilo. Il profilo attivo attualmente non può essere cancellato.

### Limite di Velocità

WRITE

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome del profilo (parametro di percorso) |

### Risposta

```json
{
  "deleted": "my_profile"
}
```

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `delete_active` | 400 | Non è possibile eliminare il profilo attivo |
| `delete_failed` | 400 | Profilo non trovato, ecc. |

## POST /api/profiles/\<name\>/duplicate

Duplica un profilo con un nuovo nome.

### Limite di Velocità

WRITE

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome del profilo di origine (parametro di percorso) |

### Richiesta

```json
{
  "new_name": "copied_profile",
  "new_label": "Copied Profile"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `new_name` | string | Yes | Nuovo nome del profilo |
| `new_label` | string | No | Nuova etichetta di visualizzazione. Predefinito al `new_name` se omesso |

### Risposta (201)

```json
{
  "profile": {
    "name": "copied_profile",
    "label": "Copied Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `duplicate_failed` | 400 | Origine non trovata, nuovo nome non valido, o nome esiste già |

## POST /api/profiles/\<name\>/rename

Rinomina un profilo. Se il profilo attivo viene rinominato, `active_profile` in `config.json` viene automaticamente aggiornato.

### Limite di Velocità

WRITE

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome del profilo corrente (parametro di percorso) |

### Richiesta

```json
{
  "new_name": "renamed_profile"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `new_name` | string | Yes | Nuovo nome del profilo |

### Risposta

```json
{
  "profile": {
    "name": "renamed_profile",
    "label": "My Profile",
    "description": "Custom settings",
    "favorite": false,
    "created_at": "2026-03-22T00:00:00Z",
    "last_used_at": null
  }
}
```

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `invalid_profile_name` | 400 | Nuovo nome del profilo non valido |
| `rename_failed` | 400 | Profilo di origine non trovato o nuovo nome esiste già |

## POST /api/profiles/\<name\>/favorite

Attiva/disattiva lo stato preferito di un profilo. Inverte il valore corrente di `favorite`.

### Limite di Velocità

WRITE

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome del profilo (parametro di percorso) |

### Richiesta

Nessun corpo richiesto.

### Risposta

```json
{
  "profile": {
    "name": "my_profile",
    "label": "My Profile",
    "favorite": true
  }
}
```

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `profile_not_found` | 404 | Profilo non esiste |
| `favorite_failed` | 400 | Aggiornamento fallito |

---

## Esportazione / Importazione QR

Esporta e importa profili come stringhe JSON per codici QR. I campi sensibili (contenenti `pin`, `token`, `secret`, o `key`) vengono automaticamente rimossi durante l'esportazione.

## GET /api/profiles/\<name\>/export

Esporta un profilo come stringa JSON pronto per QR. I campi sensibili sono esclusi.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome del profilo (parametro di percorso) |

### Risposta

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\",\"description\":\"...\"}}"
}
```

`qr_data` è una stringa JSON destinata all'incorporamento in un codice QR. Il campo `schema` identifica la versione del formato.

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `profile_not_found` | 404 | Profilo non esiste |

## POST /api/profiles/import-preview

Anteprima di un'importazione dai dati QR. Utilizzato per verificare le differenze con i profili esistenti. Non viene eseguita alcuna importazione effettiva.

### Limite di Velocità

WRITE

### Richiesta

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `qr_data` | string/object | Yes | Stringa JSON o oggetto analizzato dal codice QR |

### Risposta (nuovo profilo)

```json
{
  "mode": "new",
  "name": "my_profile",
  "label": "My Profile",
  "preview": {
    "name": "my_profile",
    "label": "My Profile",
    "description": "..."
  }
}
```

### Risposta (profilo esistente)

```json
{
  "mode": "existing",
  "name": "my_profile",
  "label": "My Profile",
  "diff": {
    "description": {
      "old": "Old description",
      "new": "New description"
    }
  }
}
```

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `invalid_qr` | 400 | Dati QR non validi o chiave `profile` mancante |
| `invalid_profile_name` | 400 | Nome del profilo non valido |

## POST /api/profiles/import

Importa un profilo dai dati QR. Supporta tre modalità: crea nuovo, unione diff e sovrascrittura completa.

### Limite di Velocità

WRITE

### Richiesta

```json
{
  "qr_data": "{\"schema\":\"yu://profile/1\",\"profile\":{\"name\":\"my_profile\",\"label\":\"My Profile\"}}",
  "mode": "full"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `qr_data` | string/object | Yes | Stringa JSON o oggetto analizzato dal codice QR |
| `mode` | string | No | Modalità di importazione: `full` (sovrascrittura completa, predefinito), `diff` (unisci solo le chiavi modificate), `new` (crea solo nuovo) |

### Risposta

```json
{
  "imported": "my_profile",
  "mode": "full"
}
```

Restituisce lo stato 201 quando si crea un nuovo profilo.

### Errori

| Codice | Stato | Descrizione |
|------|--------|-------------|
| `invalid_qr` | 400 | Dati QR non validi |
| `invalid_profile_name` | 400 | Nome del profilo non valido |
| `profile_exists` | 409 | Profilo già esiste quando `mode=new` |
| `import_failed` | 400 | Importazione fallita |
