# Gestione Fleet (Fleet Admin)

La funzionalità Fleet Admin di LAN Cowork consente di gestire centralmente più nodi yu-ai-manager sulla rete.

## Panoramica

- **Raccolta informazioni macchina**: Aggregazione centrale di CPU / RAM / GPU / disco / versione / uptime per ogni nodo
- **Visualizzazione log remota**: Streaming live dei log di qualsiasi peer tramite SSE dall'UI del nodo centrale
- **Distribuzione aggiornamenti versione**: Istruzione da centro a peer specifici per `git pull --ff-only` + graceful restart

## Prerequisiti

- L'estensione LAN Cowork deve essere abilitata (`extensions["builtin-lan-cowork"].enabled = true`)
- Il pairing tra i peer deve essere completato
- Deve essere clonato come repository git (per la funzionalità di aggiornamento)
- `psutil>=5.9` deve essere installato nell'ambiente virtuale Python

## Configurazione

### Configurazione del Nodo Chief

Aggiungi quanto segue a `config.json`:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<peer_id con pairing completato>"
        ],
        "allow_log_stream_from": [
          "<peer_id con pairing completato>"
        ],
        "allowed_branches": [
          "main"
        ],
        "timings": {
          "chief_observation_sec": 25,
          "peers_poll_interval_sec": 30,
          "heartbeat_timeout_sec": 60,
          "update_job_timeout_sec": 600,
          "postcheck_timeout_sec": 180
        }
      }
    }
  }
}
```

### Configurazione del Nodo Standard

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": false,
        "allow_remote_update": true,
        "allow_update_from": [
          "<peer_id del chief>"
        ],
        "allow_log_stream_from": [
          "<peer_id del chief>"
        ],
        "allowed_branches": [
          "main"
        ]
      }
    }
  }
}
```

## Accesso all'UI di Gestione Fleet

Accedi a `/ext/lan_cowork/fleet/ui` dal browser del nodo chief.

Nei nodi standard questo URL restituisce 404.

## Funzionalità dei Tab

### Tab Panoramica

- Visualizzazione a card di tutti i nodi (con barre di utilizzo CPU / RAM / GPU / Disco)
- Indicatore di stato online / offline / errore recupero informazioni
- Badge `[CHIEF]` per il nodo chief
- Aggiornamento automatico ogni 30 secondi + pulsante aggiornamento manuale
- Banner di avviso in caso di rilevamento di più chief

### Tab Log

- Visualizzazione live dei log di qualsiasi peer tramite SSE (stile tail -f)
- Filtro per livello (DEBUG / INFO / WARNING / ERROR)
- Casella di ricerca (filtro lato client)
- Scorrimento automatico ON/OFF
- Pausa / Ripresa

### Tab Aggiornamenti

- Tabella di confronto versione / git commit / branch
- Pulsante "Pull & Restart" per singolo nodo
- Aggiornamento massivo di più nodi (dispatch)
- Visualizzazione avanzamento (precheck → fetching → pulling → restarting → online)
- Il chief stesso è escluso dall'aggiornamento massivo (solo pulsante individuale)

## Sicurezza

### Doppio Livello di Autorizzazione

1. **Pairing (verifica identità)**: Identifica "chi" tramite Bearer token
2. **Allowlist (permessi)**: Autorizzazione esplicita per ogni operazione

Pairing completato ≠ tutti i permessi.

### Esempio di Configurazione Allowlist

```json
"allow_update_from": [
  "abc123def456",
  {"peer_id": "def456abc789"}
]
```

- Sono supportati sia il formato stringa che `{peer_id: ...}`
- Il peer_id della macchina corrente viene aggiunto automaticamente (non è necessario configurarlo)

## Degradazione Automatica del Chief

Se più nodi con `chief = true` vengono avviati sulla stessa rete, il nodo avviato successivamente viene degradato automaticamente (dopo `chief_observation_sec` secondi di osservazione).

Per riprendere il ruolo di chief dopo la degradazione è necessario un riavvio dopo la modifica della configurazione (non avviene promozione automatica).

## Limitazioni degli Aggiornamenti git

- Viene utilizzato solo `git pull --ff-only` (merge/rebase non vengono usati)
- Se il fast-forward non è possibile, lo stato diventa immediatamente `failed` (il working tree non viene modificato)
- Se il working tree è dirty, l'aggiornamento viene rifiutato

## Risoluzione dei Problemi

| Sintomo | Causa | Soluzione |
|---------|-------|-----------|
| `/fleet/ui` restituisce 404 | `chief = true` non impostato | Controlla config.json e riavvia |
| `/fleet/info` restituisce 500 | psutil non installato | `uv pip install psutil>=5.9` |
| Errore `git_not_available` | git assente o PATH non corretto | Verifica l'installazione di git |
| Timeout `postcheck_online` dopo l'aggiornamento | Il riavvio ha impiegato più di 3 minuti | Aumenta `postcheck_timeout_sec` |
| Il banner di rilevamento più chief non scompare | Processo chief precedente ancora attivo | Riavvia il vecchio chief |

## Riferimento API

### Comune a Tutti i Nodi

| Endpoint | Descrizione |
|----------|-------------|
| `GET /ext/lan_cowork/fleet/info` | Informazioni macchina (autenticazione Bearer obbligatoria) |
| `GET /ext/lan_cowork/fleet/logs/stream` | SSE log del nodo corrente (autorizzazione allowlist) |
| `POST /ext/lan_cowork/fleet/update` | git pull + riavvio (autorizzazione allowlist) |
| `GET /ext/lan_cowork/fleet/update/status` | Stato del job di aggiornamento |

### Solo per il Nodo Chief

| Endpoint | Descrizione |
|----------|-------------|
| `GET /ext/lan_cowork/fleet/peers` | Aggregazione informazioni di tutti i peer |
| `GET /ext/lan_cowork/fleet/logs/stream?peer_id=X` | Relay SSE log del peer specificato |
| `POST /ext/lan_cowork/fleet/update/dispatch` | Aggiornamento massivo a più peer |
| `GET /ext/lan_cowork/fleet/update/dispatch/status` | Verifica avanzamento dispatch |
| `GET /ext/lan_cowork/fleet/ui` | UI di gestione Fleet |
