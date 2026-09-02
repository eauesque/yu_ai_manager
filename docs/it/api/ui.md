# API di gestione interfaccia utente

API per elencare, passare, installare e disinstallare i temi dell'interfaccia utente.

## GET /api/ui/list

Elenca tutte le interfacce utente installate. Restituisce informazioni sul manifest, stato attivo e se i file template/static esistono per ogni interfaccia utente.

### Parametri

Nessuno

### Risposta

```json
{
  "data": {
    "uis": [
      {
        "name": "default",
        "active": true,
        "manifest": {
          "name": "Default UI",
          "version": "1.0.0",
          "description": "Built-in reference UI"
        },
        "has_templates": true,
        "has_static": true
      },
      {
        "name": "custom-dark",
        "active": false,
        "manifest": {
          "name": "Custom Dark",
          "version": "0.2.0",
          "description": "Dark theme variant"
        },
        "has_templates": true,
        "has_static": true
      }
    ]
  }
}
```

| Campo | Tipo | Descrizione |
|-------|------|-------------|
| `name` | string | Nome directory dell'interfaccia utente |
| `active` | boolean | Se questa è l'interfaccia utente attualmente attiva |
| `manifest` | object | Contenuto di `manifest.json` |
| `has_templates` | boolean | Se esiste una directory `templates/` |
| `has_static` | boolean | Se esiste una directory `static/` |

## POST /api/ui/switch

Cambia l'interfaccia utente attiva. La modifica viene salvata in `config.json` e richiede un riavvio del server per avere effetto.

### Limite di velocità

WRITE

### Richiesta

```json
{
  "name": "custom-dark"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `name` | string | Sì | Nome interfaccia utente di destinazione. Sono consentiti solo caratteri alfanumerici, trattini e sottolineature |

### Risposta

```json
{
  "name": "custom-dark",
  "restart_required": true
}
```

### Errori

| Stato | Condizione |
|--------|-----------|
| 400 | Il nome dell'interfaccia utente è vuoto o contiene caratteri non validi |
| 404 | L'interfaccia utente specificata non esiste |
| 400 | `manifest.json` manca o non è valido |
| 500 | Impossibile salvare `config.json` |

## POST /api/ui/install

Installa un'interfaccia utente da un URL. **Consentito solo da localhost.**

### Limite di velocità

WRITE

### Autenticazione

Richiede l'autenticazione PIN o API Key, più la richiesta deve provenire da localhost. Le richieste remote vengono rifiutate con 403.

### Richiesta

```json
{
  "url": "https://github.com/user/my-ui/archive/refs/heads/main.zip"
}
```

| Parametro | Tipo | Obbligatorio | Descrizione |
|-----------|------|-------------|-------------|
| `url` | string | Sì | URL del pacchetto interfaccia utente (archivio zip, ecc.) |

### Risposta

```json
{
  "name": "my-ui",
  "installed": true
}
```

### Errori

| Stato | Condizione |
|--------|-----------|
| 400 | L'URL è vuoto |
| 403 | La richiesta non proviene da localhost |

## DELETE /api/ui/<name>/uninstall

Disinstalla un'interfaccia utente. **Consentito solo da localhost.** L'interfaccia utente predefinita (`default`) non può essere rimossa.

Se l'interfaccia utente disinstallata è attualmente attiva, l'impostazione dell'interfaccia utente in `config.json` viene ripristinata e viene ripristinata l'interfaccia utente predefinita.

### Limite di velocità

WRITE

### Autenticazione

Richiede l'autenticazione PIN o API Key, più la richiesta deve provenire da localhost. Le richieste remote vengono rifiutate con 403.

### Parametri

| Parametro | Tipo | Descrizione |
|-----------|------|-------------|
| `name` | string | Nome interfaccia utente (parametro di percorso). Solo caratteri alfanumerici, trattini e sottolineature |

### Risposta

```json
{
  "name": "custom-dark",
  "uninstalled": true
}
```

### Errori

| Stato | Condizione |
|--------|-----------|
| 400 | Nome interfaccia utente non valido, o tentativo di disinstallare `default` |
| 403 | La richiesta non proviene da localhost |
| 404 | L'interfaccia utente specificata non esiste |
