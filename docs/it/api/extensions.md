# API Estensioni

API per la gestione delle estensioni, l'installazione, la sicurezza e la creazione.

---

## GET /api/extensions

Elenca tutte le estensioni installate.

### Parametri

Nessuno

### Risposta

```json
{
  "extensions": [
    {
      "name": "builtin-sd-webui-bridge",
      "version": "1.0.0",
      "description": "SD WebUI Bridge",
      "enabled": true,
      "trust_level": "trusted",
      "category": "integration",
      "directory": "extensions/builtin_sd_webui_bridge"
    }
  ],
  "total": 5,
  "category_order": ["core", "integration", "tools", "ui", "other"]
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `extensions` | array | Array di informazioni sulle estensioni |
| `total` | int | Numero totale di estensioni |
| `category_order` | string[] | Ordine di visualizzazione delle categorie |

## GET /api/extensions/\<name\>

Ottieni informazioni dettagliate su una specifica estensione.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome dell'estensione (parametro di percorso) |

### Risposta

```json
{
  "name": "builtin-sd-webui-bridge",
  "version": "1.0.0",
  "description": "SD WebUI Bridge",
  "enabled": true,
  "trust_level": "trusted",
  "category": "integration",
  "directory": "extensions/builtin_sd_webui_bridge"
}
```

### Errori

- `404` — Estensione non trovata

## POST /api/extensions/\<name\>/toggle

Attiva/disattiva lo stato di un'estensione.

### Limite di Velocità

WRITE

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome dell'estensione (parametro di percorso) |

### Richiesta

```json
{
  "enabled": true
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `enabled` | boolean | No | `true` per abilitare, `false` per disabilitare. Omettere per attiva/disattiva (invertire lo stato corrente) |

### Risposta

```json
{
  "name": "builtin-sd-webui-bridge",
  "enabled": true,
  "message": "Extension 'builtin-sd-webui-bridge' enabled"
}
```

### Errori

- `404` — Estensione non trovata

## GET /api/extensions/\<name\>/config

Ottieni lo schema di configurazione e i valori correnti per un'estensione.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome dell'estensione (parametro di percorso) |

### Risposta

```json
{
  "name": "builtin-sd-webui-bridge",
  "config_schema": {
    "fields": [
      {
        "key": "api_url",
        "label": "API URL",
        "type": "text",
        "default": "http://127.0.0.1:7860",
        "value": "http://127.0.0.1:7860"
      }
    ]
  }
}
```

### Errori

- `404` — Estensione non trovata

## POST /api/extensions/\<name\>/config

Salva i valori di configurazione dell'estensione. Include la convalida.

### Limite di Velocità

WRITE

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome dell'estensione (parametro di percorso) |

### Richiesta

```json
{
  "values": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `values` | object | Yes | Mappa delle chiavi di campo ai valori |

### Risposta

```json
{
  "ok": true,
  "saved": {
    "api_url": "http://127.0.0.1:7860",
    "timeout": 30
  }
}
```

### Errori

- `404` — Estensione non trovata
- `400` — Errore di convalida

---

## Installazione / Aggiornamento / Disinstallazione Estensione

I seguenti endpoint sono limitati all'accesso da **localhost**. Le richieste remote restituiscono `403`.

## POST /api/extensions/install

Installa un'estensione da un repository Git.

### Limite di Velocità

WRITE

### Restrizione di Accesso

Solo localhost

### Richiesta

```json
{
  "url": "https://github.com/user/my-extension.git"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `url` | string | Yes | URL del repository Git. `git` e `repo` sono accettati come alias |

### Risposta

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension installed successfully"
}
```

### Errori

- `400` — URL non fornito o formato URL non valido
- `403` — Accesso da non-localhost

## POST /api/extensions/\<name\>/update

Aggiorna un'estensione specifica all'ultima versione (git pull).

### Limite di Velocità

WRITE

### Restrizione di Accesso

Solo localhost

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome dell'estensione (parametro di percorso) |

### Risposta

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension updated successfully"
}
```

### Errori

- `403` — Accesso da non-localhost
- `404` — Estensione non trovata

## POST /api/extensions/update-all

Aggiornamento batch di tutte le estensioni installate da Git.

### Limite di Velocità

WRITE

### Restrizione di Accesso

Solo localhost

### Risposta

```json
{
  "results": [
    {"name": "my-extension", "ok": true, "message": "Updated"},
    {"name": "other-ext", "ok": false, "error": "Git pull failed"}
  ]
}
```

### Errori

- `403` — Accesso da non-localhost

## DELETE /api/extensions/\<name\>/uninstall

Disinstalla un'estensione (elimina la directory).

### Limite di Velocità

DESTRUCTIVE

### Restrizione di Accesso

Solo localhost

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome dell'estensione (parametro di percorso) |

### Risposta

```json
{
  "ok": true,
  "name": "my-extension",
  "message": "Extension uninstalled"
}
```

### Errori

- `403` — Accesso da non-localhost
- `404` — Estensione non trovata

---

## Sicurezza e Autorizzazioni

## GET /api/extensions/\<name\>/permissions

Ottieni le informazioni sui permessi e lo stato di approvazione per un'estensione.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome dell'estensione (parametro di percorso) |

### Risposta

```json
{
  "name": "my-extension",
  "trust_level": "L2",
  "approved": true,
  "permissions": {
    "required": [
      {"name": "network", "reason": "API calls to external service"}
    ],
    "optional": [
      {"name": "filesystem_read", "reason": "Read user images"}
    ]
  },
  "granted": {
    "granted": ["network", "filesystem_read"],
    "denied": [],
    "granted_at": "2025-01-15T10:30:00",
    "auto_approved": false
  }
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `trust_level` | string | Livello di trust (`trusted`, `L1`, `L2`) |
| `approved` | boolean | Se l'utente ha approvato questa estensione |
| `permissions.required` | array | Elenco dei permessi richiesti |
| `permissions.optional` | array | Elenco dei permessi opzionali |
| `granted` | object/null | Dettagli dei permessi concessi. `null` se non ancora approvato |

### Errori

- `404` — Estensione non trovata

## POST /api/extensions/\<name\>/permissions

Approva o revoca i permessi dell'estensione.

### Limite di Velocità

WRITE

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome dell'estensione (parametro di percorso) |

### Richiesta (Approvazione)

```json
{
  "action": "approve",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### Richiesta (Revoca)

```json
{
  "action": "revoke"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `action` | string | No | `"approve"` (predefinito) o `"revoke"` |
| `granted` | string[] | No | Elenco dei nomi dei permessi da concedere (per approvazione) |
| `denied` | string[] | No | Elenco dei nomi dei permessi da rifiutare (per approvazione) |

### Risposta (Approvazione)

```json
{
  "name": "my-extension",
  "action": "approved",
  "granted": ["network", "filesystem_read"],
  "denied": ["filesystem_write"]
}
```

### Risposta (Revoca)

```json
{
  "name": "my-extension",
  "action": "revoked"
}
```

### Errori

- `400` — `granted` non è un elenco
- `404` — Estensione non trovata

## GET /api/extensions/\<name\>/scan-results

Ottieni i risultati dell'analisi statica del codice dell'estensione. Restituisce sia i risultati di ManifestAuthority che di CodeVerifier.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome dell'estensione (parametro di percorso) |

### Risposta

```json
{
  "name": "my-extension",
  "trust_level": "L2",
  "manifest_review": {
    "approved": true,
    "issues": []
  },
  "code_scan": {
    "approved": true,
    "findings": [
      {
        "file": "my_ext.py",
        "line": 15,
        "severity": "warning",
        "message": "Uses subprocess module"
      }
    ]
  }
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `manifest_review.approved` | boolean | Se il manifesto ha superato la revisione |
| `manifest_review.issues` | array | Elenco dei problemi (`severity`, `message`) |
| `code_scan` | object/null | Risultati della scansione del codice. `null` se nessuna directory |
| `code_scan.findings` | array | Elenco dei risultati |

### Errori

- `404` — Estensione non trovata

## POST /api/extensions/\<name\>/rescan

Ripeti la scansione del codice dell'estensione. Restituisce lo stesso formato di risultato di `scan-results`.

### Limite di Velocità

WRITE

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome dell'estensione (parametro di percorso) |

### Risposta

Stesso formato di `GET /api/extensions/<name>/scan-results`.

## GET /api/extensions/\<name\>/tokens

Ottieni lo stato di emissione dei token di capacità per un'estensione.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome dell'estensione (parametro di percorso) |

### Risposta

```json
{
  "name": "my-extension",
  "token_count": 2,
  "tokens": [
    {
      "capability": "network",
      "issued_at": "2025-01-15T10:30:00",
      "expires_at": "2025-01-16T10:30:00"
    }
  ]
}
```

### Errori

- `404` — Estensione non trovata

## GET /api/extensions/\<name\>/integrity

Ottieni lo stato di integrità dei file per un'estensione. Include anche il tracker della revoca e le informazioni di protezione dell'importazione.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome dell'estensione (parametro di percorso) |

### Risposta

```json
{
  "name": "my-extension",
  "integrity": {
    "verified": true,
    "last_check": "2025-01-15T10:30:00",
    "files_changed": 0
  },
  "revocation": {
    "denial_count": 0,
    "last_access": null
  },
  "import_guard": {
    "import_denial_count": 0
  }
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `integrity` | object | Risultati del controllo di integrità dei file |
| `revocation` | object | Informazioni del tracker di revoca dei token |
| `import_guard` | object | Conteggio dei rifiuti della protezione dell'importazione |

### Errori

- `404` — Estensione non trovata

---

## Hook e Marketplace

## GET /api/extensions/hooks

Elenca gli hook registrati e le definizioni dei hook.

### Parametri

Nessuno

### Risposta

```json
{
  "hooks": {
    "after_scan": [
      {"extension": "builtin-tagger", "priority": 100}
    ]
  },
  "definitions": {
    "after_scan": {"mode": "sequential"},
    "before_import": {"mode": "sequential"}
  }
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `hooks` | object | Mappa dei nomi degli hook agli elenchi delle estensioni registrate |
| `definitions` | object | Definizioni degli hook disponibili. `mode` è la modalità di esecuzione |

## GET /api/extensions/marketplace

Cerca le estensioni del marketplace.

### Parametri

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `q` | string | No | Query di ricerca (parametro di query). Una stringa vuota restituisce tutti |

### Risposta

```json
{
  "extensions": [
    {
      "name": "awesome-extension",
      "description": "An awesome extension",
      "author": "developer",
      "version": "1.0.0",
      "installed": false
    }
  ],
  "total": 10
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `extensions` | array | Informazioni sull'estensione del marketplace |
| `extensions[].installed` | boolean | Se l'estensione è installata localmente |
| `total` | int | Numero totale dei risultati della ricerca |

## POST /api/extensions/marketplace/refresh

Forza l'aggiornamento della cache del marketplace.

### Limite di Velocità

WRITE

### Risposta

```json
{
  "refreshed": true,
  "total": 25
}
```

---

## Isolamento

## GET /api/extensions/isolation

Ottieni lo stato di isolamento del processo.

### Parametri

Nessuno

### Risposta

```json
{
  "available": true,
  "processes": {
    "my-extension": {
      "pid": 12345,
      "status": "running"
    }
  }
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `available` | boolean | Se l'isolamento dei processi è disponibile |
| `processes` | object | Mappa dei nomi delle estensioni allo stato del processo |

## GET /api/extensions/os-isolation

Ottieni lo stato di isolamento a livello di sistema operativo (Fase D). Include anche le informazioni di isolamento del processo.

### Parametri

Nessuno

### Risposta

```json
{
  "os_isolation": {
    "platform": "linux",
    "available_backends": ["apparmor"]
  },
  "config": {
    "enabled": true,
    "apparmor": true,
    "macos_sandbox_exec": false,
    "macos_user_isolation": false,
    "windows_restricted_token": false,
    "windows_job_object": false
  },
  "processes": {}
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `os_isolation` | object | Informazioni di isolamento a livello di sistema operativo |
| `config.enabled` | boolean | Se l'isolamento del sistema operativo è abilitato |
| `config.apparmor` | boolean | Stato di utilizzo di AppArmor (Linux) |
| `config.macos_sandbox_exec` | boolean | Stato di utilizzo di sandbox-exec su macOS |
| `config.macos_user_isolation` | boolean | Stato di isolamento degli utenti su macOS |
| `config.windows_restricted_token` | boolean | Stato di utilizzo del token ristretto su Windows |
| `config.windows_job_object` | boolean | Stato di utilizzo di Windows Job Object |
| `processes` | object | Stato di isolamento del processo |

---

## Creazione Estensione

API per la creazione e la modifica di estensioni personalizzate. Basato sul modello di concessione, solo la directory `extensions/custom-{name}/` è scrivibile.

Tutti gli endpoint sono limitati all'accesso da **localhost**.

### Vincoli di Sicurezza

- Nome dell'estensione: solo alfanumerico minuscolo e trattini (`[a-z0-9-]`), max 50 caratteri, prefisso `builtin-` vietato
- Tipi di file: whitelist only (`entrypoint`, `template`, `static_css`, `static_js`, `config`, `readme`)
- File binari: completamente vietati
- Limiti di dimensione del file: da 10KB a 50KB a seconda del tipo

## POST /api/extensions/author/create

Crea una nuova estensione personalizzata con file di scaffold.

### Limite di Velocità

WRITE

### Restrizione di Accesso

Solo localhost

### Richiesta

```json
{
  "name": "my-tool",
  "description": "A useful tool extension"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `name` | string | Yes | Nome dell'estensione (`[a-z0-9-]`, max 50 caratteri) |
| `description` | string | No | Descrizione dell'estensione |

### Risposta

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "path": "extensions/custom-my-tool",
  "files": [
    "extension.json",
    "my_tool_ext.py"
  ]
}
```

### Errori

- `400` — Nome non valido o estensione già esistente
- `403` — Accesso da non-localhost

## POST /api/extensions/author/\<name\>/write

Scrivi un file in un'estensione personalizzata.

### Limite di Velocità

WRITE

### Restrizione di Accesso

Solo localhost

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome dell'estensione (parametro di percorso, senza prefisso `custom-`) |

### Richiesta

```json
{
  "file_type": "entrypoint",
  "filename": "my_tool_ext",
  "content": "\"\"\"My tool extension.\"\"\"\n\nfrom quart import Blueprint\n..."
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_type` | string | Yes | Tipo di file. Uno di: `entrypoint`, `template`, `static_css`, `static_js`, `config`, `readme` |
| `filename` | string | Yes | Nome del file senza estensione. Solo caratteri alfanumerici, trattini e sottolineature |
| `content` | string | Yes | Contenuto del file (solo testo) |

### Vincoli del Tipo di File

| file_type | Estensione | Dimensione Max | Note |
|-----------|-----------|----------|-------|
| `entrypoint` | `.py` | 50KB | Punto di ingresso dell'estensione |
| `template` | `.html` | 50KB | Inserito in `templates/{name}/` |
| `static_css` | `.css` | 50KB | Inserito in `static/` |
| `static_js` | `.js` | 50KB | Inserito in `static/` |
| `config` | `.json` | 10KB | Il nome del file deve essere `extension` |
| `readme` | `.md` | 20KB | Il nome del file deve essere `README` |

### Risposta

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "size": 256
}
```

### Errori

- `400` — Errore di convalida (nome non valido, tipo di file, dimensione superata, binario rilevato)
- `403` — Accesso da non-localhost

## GET /api/extensions/author/\<name\>/read

Leggi un file da un'estensione personalizzata.

### Restrizione di Accesso

Solo localhost

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome dell'estensione (parametro di percorso) |

### Parametri di Query

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|----------|-------------|
| `file_type` | string | Yes | Tipo di file |
| `filename` | string | Yes | Nome del file senza estensione |

### Risposta

```json
{
  "ok": true,
  "file": "my_tool_ext.py",
  "content": "\"\"\"My tool extension.\"\"\"\n...",
  "size": 256
}
```

### Errori

- `400` — Errore di convalida
- `403` — Accesso da non-localhost

## GET /api/extensions/author/\<name\>/files

Elenca tutti i file in un'estensione personalizzata.

### Restrizione di Accesso

Solo localhost

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome dell'estensione (parametro di percorso) |

### Risposta

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "files": [
    {"path": "extension.json", "size": 320},
    {"path": "my_tool_ext.py", "size": 256},
    {"path": "templates/my_tool/index.html", "size": 1024}
  ],
  "total_size": 1600
}
```

### Errori

- `400` — Nome dell'estensione non valido
- `403` — Accesso da non-localhost

## POST /api/extensions/author/\<name\>/validate

Convalida l'extension.json e il codice di un'estensione personalizzata. Esegue CodeVerifier senza registrare l'estensione.

### Limite di Velocità

WRITE

### Restrizione di Accesso

Solo localhost

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome dell'estensione (parametro di percorso) |

### Risposta (Successo)

```json
{
  "ok": true,
  "name": "custom-my-tool",
  "issues": [],
  "code_findings": [],
  "manifest": {
    "name": "custom-my-tool",
    "version": "0.1.0",
    "entrypoint": "my_tool_ext.py"
  }
}
```

### Risposta (Problemi Trovati)

```json
{
  "ok": false,
  "name": "custom-my-tool",
  "issues": [
    "Missing required field: version",
    "CodeVerifier rejected: dangerous patterns detected"
  ],
  "code_findings": [
    {
      "severity": "critical",
      "message": "Uses eval()",
      "file": "my_tool_ext.py",
      "line": 42
    }
  ],
  "manifest": {}
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `ok` | boolean | Se tutti i controlli hanno superato |
| `issues` | string[] | Problemi di verifica del manifesto e del codice |
| `code_findings` | array | Risultati di CodeVerifier |
| `manifest` | object | Contenuti dell'extension.json analizzati |

### Errori

- `400` — Nome dell'estensione non valido o estensione non esiste
