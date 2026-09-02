# API Impostazioni

API per la gestione delle impostazioni dell'applicazione, la crittografia dei segreti e l'integrazione del gestore password esterno (1Password / Bitwarden).

I valori segreti sono sempre mascherati (`****`) nelle risposte GET. Il campo `source` indica da quale backend è stato risolto il valore.

## Autenticazione

Tutti gli endpoint richiedono l'autenticazione PIN o l'autenticazione API Key.

---

## GET /api/settings/schema

Recupera la definizione dello schema delle impostazioni completo. Restituisce nomi di chiave, tipi, impostazioni predefinite, categorie e altri metadati per tutte le impostazioni.

### Parametri

Nessuno

### Risposta

```json
{
  "schema": [
    {
      "key": "pin",
      "type": "str",
      "default": "",
      "category": "security",
      "secret": true,
      "label": "PIN Code"
    }
  ]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `key` | string | Chiave impostazione (separata da punti, es. `github.token`) |
| `type` | string | Tipo di valore (`str`, `int`, `float`, `bool`) |
| `default` | any | Valore predefinito |
| `category` | string | Nome categoria |
| `secret` | bool | Se questo è un valore segreto |
| `label` | string | Etichetta di visualizzazione |

---

## GET /api/settings/all

Recupera tutti i valori delle impostazioni. I valori segreti vengono restituiti in forma mascherata.

### Parametri

Nessuno

### Risposta

```json
{
  "settings": [
    {
      "key": "pin",
      "value": "****",
      "source": "encrypted",
      "secret": true,
      "category": "security"
    },
    {
      "key": "theme",
      "value": "dark",
      "source": "config",
      "secret": false,
      "category": "appearance"
    }
  ]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `key` | string | Chiave impostazione |
| `value` | any | Valore attuale (mascherato se segreto) |
| `source` | string | Fonte valore: `default` / `config` / `encrypted` / `1password` / `bitwarden` |
| `secret` | bool | Se questo è un valore segreto |
| `category` | string | Nome categoria |

---

## GET /api/settings/\<key\>

Recupera un singolo valore di impostazione. La chiave utilizza il formato del percorso separato da punti (es. `github.token`).

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `key` | string | Chiave impostazione (parametro di percorso) |

### Risposta

```json
{
  "key": "github.token",
  "value": "****",
  "source": "1password",
  "secret": true,
  "category": "integrations"
}
```

### Errori

| Stato | Codice | Descrizione |
|--------|--------|-------------|
| 404 | `not_found` | Chiave impostazione sconosciuta |

---

## PUT /api/settings/\<key\>

Aggiorna un valore di impostazione. I valori segreti vengono crittografati automaticamente. Facoltativamente specifica un URI 1Password per gestire il segreto esternamente.

### Limite di velocità

DESTRUCTIVE

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `key` | string | Chiave impostazione (parametro di percorso) |

### Richiesta

```json
{
  "value": "new-value",
  "op_uri": "op://vault/item/field"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `value` | any | Sì | Il valore da impostare. Automaticamente coercizzato al tipo definito dallo schema |
| `op_uri` | string | No | URI 1Password. Quando specificato, salva una mappatura `op_secrets` invece del valore |

### Risposta

```json
{
  "key": "github.token",
  "updated": true
}
```

### Errori

| Stato | Codice | Descrizione |
|--------|--------|-------------|
| 400 | `bad_request` | Corpo della richiesta mancante `value` |
| 404 | `not_found` | Chiave impostazione sconosciuta |

---

## GET /api/settings/secrets/status

Recupera lo stato del backend della chiave di crittografia. Mostra quale metodo di gestione delle chiavi è attualmente in uso.

### Parametri

Nessuno

### Risposta

```json
{
  "backend": "keychain",
  "available": true,
  "keychain_supported": true
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `backend` | string | Backend chiave attuale (`keychain` / `passphrase` / `file`) |
| `available` | bool | Se la crittografia è disponibile |
| `keychain_supported` | bool | Se il portachiavi del sistema operativo è supportato |

---

## POST /api/settings/secrets/export

Esporta la chiave di crittografia come JSON protetto da password. Utilizzato per il backup o la migrazione a un altro ambiente.

### Limite di velocità

DESTRUCTIVE

### Richiesta

```json
{
  "password": "my-export-password"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `password` | string | Sì | Password per proteggere i dati esportati |

### Risposta

```json
{
  "success": true,
  "export_data": "base64-encoded-encrypted-key-data"
}
```

### Errori

| Stato | Codice | Descrizione |
|--------|--------|-------------|
| 400 | `bad_request` | Corpo della richiesta mancante `password` |
| 400 | `export_failed` | Operazione di esportazione non riuscita |

---

## POST /api/settings/secrets/import

Importa una chiave di crittografia dai dati precedentemente esportati.

### Limite di velocità

DESTRUCTIVE

### Richiesta

```json
{
  "export_data": "base64-encoded-encrypted-key-data",
  "password": "my-export-password"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `export_data` | string | Sì | I dati ottenuti durante l'esportazione |
| `password` | string | Sì | La password impostata durante l'esportazione |

### Risposta

```json
{
  "success": true,
  "message": "Key imported successfully"
}
```

### Errori

| Stato | Codice | Descrizione |
|--------|--------|-------------|
| 400 | `bad_request` | `export_data` o `password` mancante |
| 400 | `import_failed` | Password errata o dati corrotti |

---

## POST /api/settings/secrets/migrate-keychain

Migra la chiave di crittografia dal backend file al portachiavi del sistema operativo. Supporta macOS Keychain, Windows Credential Manager e Linux Secret Service.

### Limite di velocità

DESTRUCTIVE

### Richiesta

Nessuno (nessun corpo richiesto)

### Risposta

```json
{
  "success": true,
  "message": "Key migrated to OS keychain"
}
```

### Errori

| Stato | Codice | Descrizione |
|--------|--------|-------------|
| 400 | `migration_failed` | Portachiavi non disponibile o migrazione non riuscita |

---

## GET /api/settings/op-status

Recupera lo stato di connessione di 1Password CLI (`op`).

### Parametri

Nessuno

### Risposta

```json
{
  "available": true,
  "signed_in": true,
  "version": "2.24.0"
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `available` | bool | Se il comando `op` esiste su PATH |
| `signed_in` | bool | Se connesso a 1Password |
| `version` | string | Versione della CLI `op` |

---

## GET /api/settings/secrets/op-vaults

Elenca i vault 1Password disponibili.

### Parametri

Nessuno

### Risposta

```json
{
  "vaults": [
    {
      "id": "abc123",
      "name": "Personal"
    }
  ]
}
```

### Errori

| Stato | Codice | Descrizione |
|--------|--------|-------------|
| 503 | `op_unavailable` | CLI 1Password non disponibile |

---

## POST /api/settings/secrets/push-to-op

Scrivi in batch tutte le impostazioni segrete in 1Password e salva le mappature `op_secrets` in config.json.

### Limite di velocità

DESTRUCTIVE

### Richiesta

```json
{
  "vault": "Personal",
  "item_title": "YU AI Manager",
  "remove_local": false
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `vault` | string | Sì | Nome del vault 1Password di destinazione |
| `item_title` | string | No | Titolo elemento 1Password. Predefinito: `YU AI Manager` |
| `remove_local` | bool | No | Se `true`, rimuove i valori crittografati localmente da config.json dopo il push. Predefinito: `false` |

### Risposta

```json
{
  "message": "2 secrets pushed to 1Password",
  "pushed_keys": ["github.token", "pin"],
  "uris": {
    "github.token": "op://Personal/YU AI Manager/github.token",
    "pin": "op://Personal/YU AI Manager/pin"
  },
  "remove_local": false
}
```

### Errori

| Stato | Codice | Descrizione |
|--------|--------|-------------|
| 400 | `bad_request` | `vault` mancante |
| 400 | `no_secrets` | Nessun segreto da inviare |
| 500 | `op_push_failed` | Impossibile scrivere su 1Password |
| 503 | `op_unavailable` | CLI 1Password non disponibile |

---

## DELETE /api/settings/op-mapping/\<key\>

Rimuovi una mappatura URI 1Password, ripristinando la crittografia locale.

### Limite di velocità

WRITE

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `key` | string | Chiave impostazione (parametro di percorso) |

### Risposta

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### Errori

| Stato | Codice | Descrizione |
|--------|--------|-------------|
| 404 | `not_found` | Chiave non trovata nella mappatura `op_secrets` |

---

## GET /api/settings/bw-status

Recupera lo stato di connessione di Bitwarden CLI (`bw`).

### Parametri

Nessuno

### Risposta

```json
{
  "available": true,
  "status": "unlocked"
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `available` | bool | Se il comando `bw` esiste su PATH |
| `status` | string | Stato della sessione Bitwarden |

---

## GET /api/settings/secrets/bw-folders

Elenca le cartelle Bitwarden disponibili.

### Parametri

Nessuno

### Risposta

```json
{
  "folders": [
    {
      "id": "folder-uuid",
      "name": "Development"
    }
  ]
}
```

### Errori

| Stato | Codice | Descrizione |
|--------|--------|-------------|
| 503 | `bw_unavailable` | CLI Bitwarden non disponibile |

---

## POST /api/settings/secrets/push-to-bw

Scrivi in batch tutte le impostazioni segrete in Bitwarden e salva le mappature `bw_secrets` in config.json.

### Limite di velocità

WRITE

### Richiesta

```json
{
  "folder_id": "folder-uuid",
  "item_name": "YU AI Manager"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `folder_id` | string/null | No | ID della cartella Bitwarden di destinazione. Ometti per nessuna cartella |
| `item_name` | string | No | Nome dell'elemento Bitwarden. Predefinito: `YU AI Manager` |

### Risposta

```json
{
  "message": "2 secrets pushed to Bitwarden",
  "pushed_keys": ["github.token", "pin"],
  "mappings": {
    "github.token": {"item_id": "item-uuid", "field": "github.token"},
    "pin": {"item_id": "item-uuid", "field": "pin"}
  }
}
```

### Errori

| Stato | Codice | Descrizione |
|--------|--------|-------------|
| 400 | `no_secrets` | Nessun segreto da inviare |
| 500 | `bw_push_failed` | Impossibile scrivere su Bitwarden |
| 503 | `bw_unavailable` | CLI Bitwarden non disponibile |

---

## DELETE /api/settings/bw-mapping/\<key\>

Rimuovi una mappatura Bitwarden, ripristinando la crittografia locale.

### Limite di velocità

WRITE

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `key` | string | Chiave impostazione (parametro di percorso) |

### Risposta

```json
{
  "key": "github.token",
  "unlinked": true
}
```

### Errori

| Stato | Codice | Descrizione |
|--------|--------|-------------|
| 404 | `not_found` | Chiave non trovata nella mappatura `bw_secrets` |
