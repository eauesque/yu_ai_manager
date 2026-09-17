# Impostazioni

## Impostazioni server

| Elemento | Descrizione |
|------|------|
| Host | Indirizzo bind (127.0.0.1 fisso quando LAN OFF) |
| Port | Numero porta server web |
| LAN Access | ON consente accesso da altri device su LAN |
| PIN Auth | Richiedi input PIN all'accesso |
| Boss Mode | Schermata login PIN stile giornale |

## Impostazioni scansione

Aggiungi/rimuovi/riordina/abilita-disabilita cartelle registrate.

## Impostazioni parser

| Elemento | Descrizione |
|------|------|
| Extract A1111 | Estrai metadati formato Stable Diffusion WebUI |
| Extract ComfyUI | Estrai metadati workflow ComfyUI |
| Normalize tags | Normalizza tag a minuscole |
| Compute hash | Calcola hash file (per rilevamento duplicati) |
| FTS | Abilita indexing full-text search |

## API Key

Gestisci API Key per strumenti esterni (server MCP, script, agent).
Usati in autenticazione Bearer.

## Aspetto

Personalizza tema, colore accento, immagine sfondo, effetti sonori.

## Secure secret store (crittografia)

PIN, password Bluesky, secret Webhook e altri valori sensibili sono protetti con crittografia Fernet da package `cryptography`.

- **Formato**: Stringa con prefisso `enc:`
- **Compatibilità**: Valori plaintext esistenti rimangono funzionali (solo nuovi salvataggi sono crittografati)
- **Installazione**: `uv pip install cryptography` (se non installato, crittografia disabilitata)

### Backend chiave

Chiave crittografia è ottenuta in questo ordine di priorità:

1. **Passphrase** — Se impostata variabile ambiente `YU_SECRET_PASSPHRASE`, deriva chiave con PBKDF2-HMAC-SHA256 (600.000 iterations). Salt auto-salvato in `data/secret.salt`
2. **OS Keychain** — Se package `keyring` installato, archivia chiave in Windows Credential Manager / macOS Keychain / Linux Secret Service
3. **File** — `data/secret.key` (compatibilità tradizionale, auto-generato primo run)

```bash
# Esempio impostazione passphrase
export YU_SECRET_PASSPHRASE="my-strong-passphrase"

# Utilizzo keychain
uv pip install keyring
```

### Export/import chiave

Per migrazione altro machine o backup, esporta/importa chiave crittografia in formato JSON protetto da password.

- `POST /api/settings/secrets/export` — Esporta protetto da password (8+ char)
- `POST /api/settings/secrets/import` — Ripristina chiave da export data e password
- `POST /api/settings/secrets/migrate-keychain` — Migra da file a keychain
- `GET /api/settings/secrets/status` — Visualizza stato backend

### Migrazione a keychain

Per migrare chiave da file a keychain, chiama `/api/settings/secrets/migrate-keychain`. Dopo migrazione, `data/secret.key` auto-cancellato.

## Integrazione 1Password CLI

In ambiente con `op` CLI installato, ottieni dinamicamente secret da 1Password Vault.

### Setup

1. Installa [1Password CLI](https://developer.1password.com/docs/cli/)
2. `op signin` per accedere
