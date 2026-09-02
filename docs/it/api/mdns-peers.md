# API: /api/mdns (Scoperta peer)

> Versione di destinazione: v4.64.0 e successiva (Estensioni Hailo: v4.66.0 e successiva)

API per i nodi yu_ai_manager su una LAN per scoprire l'uno l'altro tramite mDNS (`_yu-ai._tcp.local.`). Ci sono due endpoint.

---

## GET /api/mdns/identity

### Panoramica

Un endpoint di auto-presentazione per un nodo. Altri nodi lo chiamano durante la verifica peer per confermare che le informazioni pubblicizzate tramite mDNS appartengono a una vera istanza di yu_ai_manager.

### Autenticazione

**Bypass dell'autenticazione (non richiesto).** L'autenticazione è intenzionalmente omessa poiché questo endpoint viene utilizzato per la verifica reciproca dei peer. La risposta contiene solo informazioni già pubblicamente disponibili tramite mDNS. Non sono incluse informazioni segrete o sensibili.

### Risposta

```json
{
  "product": "yu_ai_manager",
  "node_id": "a1b2c3d4-...",
  "version": "4.66.0",
  "capabilities": ["hailo"],
  "hailo_ollama_url": "http://192.168.1.10:11434"
}
```

| Campo | Tipo | Descrizione |
|---|---|---|
| `product` | string | Sempre `"yu_ai_manager"` |
| `node_id` | string | UUID univoco del nodo |
| `version` | string | Versione dell'applicazione (letta dal file VERSION) |
| `capabilities` | string[] | Elenco delle capacità disponibili. Attualmente solo `"hailo"` |
| `hailo_ollama_url` | string (opzionale) | URL di accesso LAN per Hailo-Ollama. Non incluso se l'IP LAN non può essere determinato |

**Condizione affinché `capabilities` includa `"hailo"`:** Il backend `"hailo-local"` è registrato nel catalogo LLM Router.

**Condizione affinché `hailo_ollama_url` sia incluso:** Il backend `"hailo-ollama-local"` è registrato nel catalogo e un IP LAN può essere determinato. Gli indirizzi loopback (`127.0.0.1`, ecc.) vengono riscritti nell'IP LAN.

---

## GET /api/mdns/peers

### Panoramica

Restituisce un elenco di peer LAN scoperti da questo nodo. Destinato al controllo dello stato del sottosistema mDNS e al debug.

### Autenticazione

**Bypass dell'autenticazione (non richiesto).** La risposta contiene solo informazioni già trasmesse sulla LAN tramite mDNS.

### Risposta (normale)

```json
{
  "running": true,
  "status": "browsing",
  "self_node_id": "a1b2c3d4-...",
  "peers": [
    {
      "node_id": "e5f6a7b8-...",
      "hostname": "raspberrypi.local",
      "version": "4.66.0",
      "llm_base_url": "http://192.168.1.20:11434",
      "llm_provider": "ollama",
      "capabilities": ["hailo"],
      "web_port": 5000,
      "addresses": ["192.168.1.20"],
      "hailo_ollama_url": "http://192.168.1.20:11434",
      "first_seen": 1712600000.0,
      "last_seen": 1712603600.0
    }
  ]
}
```

| Campo | Tipo | Descrizione |
|---|---|---|
| `running` | bool | Se il sottosistema mDNS è in esecuzione |
| `status` | string | Stringa dello stato del sottosistema |
| `self_node_id` | string | node_id di questo nodo |
| `peers` | object[] | Elenco dei peer scoperti (vedi tabella sottostante) |

**Elementi peer:**

| Campo | Tipo | Descrizione |
|---|---|---|
| `node_id` | string | UUID univoco del peer |
| `hostname` | string | Nome host mDNS |
| `version` | string | Versione dell'applicazione del peer |
| `llm_base_url` | string \| null | URL dell'endpoint LLM del peer |
| `llm_provider` | string \| null | Nome del provider LLM (es. `"ollama"`) |
| `capabilities` | string[] | Elenco delle capacità del peer |
| `web_port` | int \| null | Porta WebUI del peer |
| `addresses` | string[] | Indirizzi IP LAN del peer |
| `hailo_ollama_url` | string \| null | URL Hailo-Ollama del peer |
| `first_seen` | float \| null | Ora della prima scoperta (timestamp Unix) |
| `last_seen` | float \| null | Ora dell'ultima verifica (timestamp Unix) |

### Risposta (mDNS non inizializzato)

```json
{
  "running": false,
  "reason": "mdns subsystem not initialised (disabled or init failed)",
  "peers": []
}
```

Quando `running: false`, mDNS è disabilitato o l'inizializzazione non è riuscita. Controlla la configurazione e i log di avvio.

---

## Modalità debug

Avvia yu con la variabile di ambiente `TAGDB_DEBUG_TRUSTED_PEERS=1` per includere campi aggiuntivi nella risposta `/api/mdns/peers`.

```json
{
  "running": true,
  "peers": [...],
  "trusted_ips": ["192.168.1.20", "192.168.1.30"],
  "bridge": {
    "managed_aliases": ["ollama-192.168.1.20"],
    "config_aliases": ["my-nas"],
    "cooldown_seconds_remaining": {
      "e5f6a7b8": 12.3
    }
  }
}
```

| Campo | Descrizione |
|---|---|
| `trusted_ips` | Elenco di IP registrati nel registro IP affidabile |
| `bridge.managed_aliases` | Elenco di alias gestiti dal bridge mDNS |
| `bridge.config_aliases` | Elenco di alias definiti staticamente in config |
| `bridge.cooldown_seconds_remaining` | Secondi rimanenti di cooldown codificati dai primi 8 caratteri di node_id |

**Avvertenza:** `trusted_ips` potrebbe servire come elenco di destinazioni di attacco, quindi non è esposto per impostazione predefinita. Non impostare `TAGDB_DEBUG_TRUSTED_PEERS=1` negli ambienti di produzione.

---

## Flusso di scoperta mDNS

```
L'altro nodo inizia
    │
    ▼
Pubblicizza mDNS _yu-ai._tcp.local.
    │
    ▼
LlmRouterMdnsBridge riceve on_peer_added()
    │
    ▼
Verifica HTTP tramite GET /api/mdns/identity
    │
    ├─ Successo → Registra in PeerRegistry / BackendCatalog
    └─ Errore → Riprova dopo il cooldown
```

---

## File correlati

- `routes/mdns_identity.py` -- Implementazione dell'endpoint
- `core/mdns/` -- Servizio mDNS / utilità indirizzi
- `core/llm_router/state.py` -- BackendCatalog
- `core/web/trusted_peer_registry.py` -- Registro IP affidabile
- `docs/en/mesh-inference/overview.md` -- Architettura complessiva dell'inferenza mesh
