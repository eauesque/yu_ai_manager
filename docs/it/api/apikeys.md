# API API Key

API per la creazione, l'elenco e l'eliminazione delle API key. Tutti gli endpoint richiedono l'autenticazione della sessione PIN.

Le API key sono generate nel formato `sk_` + 32 caratteri esadecimali (128-bit). Solo l'hash viene memorizzato lato server; la chiave grezza viene restituita solo una volta al momento della creazione.

## Scopi

Le API key possono essere assegnate a scopi per limitare quali endpoint possono accedere. Le chiavi senza scopi predefiniti sono di sola lettura.

| Scope | Descrizione |
|-------|-------------|
| `read` | Ricerca, dettagli file, miniature, statistiche |
| `rate` | Rating get/set/batch |
| `tag.write` | Aggiunta/rimozione tag |
| `collection.write` | Creazione/aggiornamento/eliminazione raccolta, batch-add, preferiti |
| `annotate` | Lettura/scrittura/eliminazione annotazione |
| `scan` | Avvio/annullamento/ripresa scansione |
| `admin` | Gestione API key, impostazioni, backup/ripristino |

## POST /api/apikeys

Crea una nuova API key.

### Limite di velocità

WRITE (scope: `admin`)

### Autenticazione

Sessione PIN o API key con scope `admin`

### Richiesta

```json
{
  "label": "My Integration",
  "scopes": ["read", "rate"]
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `label` | string | No | Etichetta identificativa per la chiave. Per impostazione predefinita `Key <timestamp>` se omessa |
| `scopes` | string[] | No | Array di scopi. Ometti o passa array vuoto per accesso di sola lettura |

### Risposta (201)

```json
{
  "id": "ak_1a2b3c4d5e6f7890",
  "key": "sk_abcdef1234567890abcdef1234567890",
  "key_prefix": "sk_abcdef12",
  "label": "My Integration",
  "created_at": 1709500000,
  "scopes": ["read", "rate"]
}
```

> **Nota**: Il campo `key` è incluso solo nella risposta di creazione. Questo valore non può essere recuperato di nuovo, quindi conservalo in una posizione sicura.

### Errori

| Stato | Descrizione |
|-------|-------------|
| 400 | Scope non valido specificato |

## GET /api/apikeys

Elenca tutte le API key. Gli hash non sono inclusi; viene restituito solo il prefisso.

### Autenticazione

Sessione PIN o API key con scope `admin`

### Parametri

Nessuno

### Risposta

```json
{
  "keys": [
    {
      "id": "ak_1a2b3c4d5e6f7890",
      "key_prefix": "sk_abcdef12",
      "label": "My Integration",
      "created_at": 1709500000,
      "last_used_at": 1709600000,
      "scopes": ["read", "rate"]
    }
  ]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `id` | string | ID chiave (prefisso `ak_`) |
| `key_prefix` | string | Primi 10 caratteri della chiave (per identificazione) |
| `label` | string | Etichetta definita dall'utente |
| `created_at` | int | Ora di creazione (timestamp Unix) |
| `last_used_at` | int/null | Ora dell'ultimo utilizzo. `null` se mai utilizzato |
| `scopes` | string[] | Scopi assegnati. Il campo viene omesso se non sono impostati scopi |

## DELETE /api/apikeys/<key_id>

Elimina (revoca) un'API key.

### Limite di velocità

WRITE (scope: `admin`)

### Autenticazione

Sessione PIN o API key con scope `admin`

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `key_id` | string | ID API key (parametro di percorso) |

### Risposta

```json
{
  "deleted": "ak_1a2b3c4d5e6f7890"
}
```

### Errori

| Stato | Descrizione |
|-------|-------------|
| 404 | Chiave con l'ID specificato non trovata |

## Utilizzo delle API Key

Usa l'API key creata tramite l'intestazione `Authorization`:

```
Authorization: Bearer sk_abcdef1234567890abcdef1234567890
```

Le richieste autenticate con API key non richiedono l'intestazione CSRF (`X-Requested-With`).
