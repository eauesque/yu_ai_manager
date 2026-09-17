# Setup del LLM Router

## Aggiunta a config.json

```json
{
  "llm_router": {
    "enabled": true,
    "auth": {
      "mode": "loopback",
      "api_key": "",
      "allow_loopback_bypass": true
    },
    "backends": [
      {
        "alias": "ollama-local",
        "base_url": "http://localhost:11434/v1",
        "type": "ollama",
        "auto_discover": true
      }
    ],
    "aliases": {
      "local-fast": "ollama-local/qwen2.5:7b",
      "local-coder": "ollama-local/qwen2.5-coder:32b"
    }
  }
}
```

## Integrazione con Claude Code

```bash
ANTHROPIC_BASE_URL=http://localhost:5000/v1 claude
```

Quando si effettuano richieste, specificare un alias o un nome fisico nel campo `model`:
- `local-fast` (alias)
- `ollama-local/qwen2.5:7b` (nome fisico)

## Integrazione con Continue (VSCode)

`config.json`:
```json
{
  "models": [
    {
      "title": "Local Coder",
      "provider": "openai",
      "apiBase": "http://localhost:5000/v1",
      "model": "local-coder",
      "apiKey": "dummy"
    }
  ]
}
```

## Auto-discovery dei Nodi -- Supporto Hostname `.local` (Home LAN)

Quando si eseguono più macchine su una home LAN (ad es. Mac mini + Pi5 + macchina GPU Windows), è possibile utilizzare nomi host `.local` anziché indirizzi IP in `base_url`. In questo modo, **la configurazione continua a funzionare anche se DHCP riassegna gli indirizzi IP**. Non è necessaria alcuna implementazione aggiuntiva sul lato yu_ai_manager -- `httpx` risolve i nomi automaticamente tramite il resolver del sistema operativo (Bonjour / Avahi / mDNSResponder).

```json
{
  "llm_router": {
    "enabled": true,
    "backends": [
      { "alias": "ollama-mac", "base_url": "http://mac-mini.local:11434/v1", "type": "ollama" },
      { "alias": "ollama-pi5", "base_url": "http://pi5.local:11434/v1",      "type": "ollama" },
      { "alias": "ollama-win", "base_url": "http://gpu-rig.local:11434/v1",  "type": "ollama" }
    ],
    "aliases": {
      "local-fast":  "ollama-mac/qwen2.5:7b",
      "local-coder": "ollama-pi5/qwen2.5-coder:32b",
      "local-big":   "ollama-win/llama3.3:70b"
    }
  }
}
```

Esempio: [`config.example.local-hostname.json`](../../../config.example.local-hostname.json)

### Requisiti

| SO | Obbligatorio |
|---|---|
| macOS | Bonjour (integrato, nessuna installazione aggiuntiva necessaria) |
| Linux | `avahi-daemon` (`sudo apt install avahi-daemon` / `sudo systemctl enable --now avahi-daemon`) |
| Windows 10/11 | mDNSResponder (Win10 1803 e successivi possono risolvere `.local` nativamente. Se non funziona, installa Bonjour Print Services) |

### Verifica

```bash
# Test che la risoluzione funziona
python -c "import socket; print(socket.gethostbyname('mac-mini.local'))"
# → Se restituisce 192.168.x.x, funziona
```

### Cross-subnet / Corporate LAN / VPN

mDNS opera tramite multicast L2, quindi **non può raggiungere tra router, VPN o VLAN isolate nelle reti aziendali**. In questi ambienti, specificare direttamente gli indirizzi IP come prima:

```json
"backends": [
  { "alias": "remote-gpu", "base_url": "http://10.20.30.40:11434/v1", "type": "ollama" },
  { "alias": "tailscale-mac", "base_url": "http://100.x.x.x:11434/v1", "type": "ollama" }
]
```

Se hai bisogno di un reflector mDNS in un ambiente segmentato da VLAN, consulta il tuo amministratore LAN. yu_ai_manager non fornisce un reflector o proxy mDNS.

### Limitazioni Conosciute

- **La risoluzione mDNS su Windows può essere occasionalmente lenta** (~1 secondo): Si consiglia di impostare il backend `timeout` a 3 secondi o più
- **Il suffisso `.local` è richiesto**: Usare solo `mac-mini` ricorrerà a NetBIOS / DNS, quindi scrivi sempre `mac-mini.local`
- **Ollama non pubblicizza tramite mDNS**: Viene utilizzata solo la risoluzione del nome host; la porta (11434) deve essere specificata manualmente. Per Ollama collocato con yu, v4.71.0 aggiunge un advertiser `_ollama._tcp.local.` sul lato yu. Per nodi Ollama puramente bare (senza yu), vedi "Gestione di Nodi Ollama Puri Bare (senza yu)" di seguito per la politica

## Variabili d'Ambiente

| Variabile | Comportamento |
|---|---|
| `TAGDB_DISABLE_LLM_ROUTER` | Impostare su `1` per disabilitare l'intero Router |
| `TAGDB_DISABLE_LLM_ROUTER_REFRESH` | Impostare su `1` per disabilitare il ciclo di aggiornamento di 5 minuti |
| `TAGDB_LLM_ROUTER_AUTH_MODE` | Sovrascrivere con `none`/`loopback`/`api_key` |

## Documentazione Multilingue

Seguendo le `docs/ reading rules` in CLAUDE.md, le versioni `en/zh-tw/zh-cn/ko` vengono sincronizzate in base alla fonte `ja/` (come attività separata dopo l'implementazione; vedi TODO.md).

## Auto-discovery dei Nodi (Phase B -- v4.64.0 e successivi)

I nodi yu_ai_manager sulla stessa LAN si scoprono automaticamente tramite mDNS (`_yu-ai._tcp.local.`). Anche senza scrivere manualmente i backend in `config.json`, i nodi scoperti vengono registrati automaticamente nel `BackendCatalog` con alias `mdns-<prefix>`.

### Come Funziona

1. All'avvio, `core/mdns/` pubblicizza `_yu-ai._tcp.local.`
2. Si iscrive ai record TXT di altri nodi e verifica che le chiavi richieste (version/node_id/llm_base_url) siano presenti
3. Per i nodi con una versione principale corrispondente, invia una GET HTTP a `http://<addr>:<web_port>/api/mdns/identity` per confermare che product/node_id/version corrispondono
4. I nodi verificati vengono registrati nel LLM Router come `BackendInfo(alias="mdns-<node_id[:8]>")`
5. Da lì, il ciclo di sonda esistente gestisce gli aggiornamenti periodici

### Prerequisiti

- Il responder mDNS del sistema operativo deve essere in esecuzione (macOS: Bonjour, Linux: Avahi, Windows: mDNSResponder)
- I nodi devono essere sulla stessa subnet L2 (per scenari cross-router / VPN, usa la configurazione manuale della Phase A)
- UDP 5353 deve essere consentito attraverso il firewall locale
- **Ollama deve essere esposto alla LAN** -- Ollama si associa a `127.0.0.1:11434` per impostazione predefinita, quindi non è raggiungibile da altri nodi sulla LAN. Impostare la variabile di ambiente `OLLAMA_HOST=0.0.0.0:11434` prima di avviare Ollama (macOS: `launchctl setenv OLLAMA_HOST "0.0.0.0:11434"`, Linux: unità systemd / `.bashrc`, Windows: variabili di ambiente di sistema). Se non impostato, yu_ai_manager determina che è solo localhost e non pubblicizzerà `llm_base_url` (apparirà un avviso nel log di avvio)

### Auto-discovery di Ollama

Se non esiste alcun entry localhost in `llm_router.backends` in `config.json`, yu_ai_manager cerca Ollama all'avvio nel seguente ordine:

1. `http://<LAN_IP>:11434/api/tags` -- Ollama raggiungibile dalla LAN
2. `http://localhost:11434/api/tags` -- Anche se rilevato, la pubblicità LAN non viene eseguita (l'avviso precedente viene visualizzato)

Se viene restituita una risposta 200 dall'IP della LAN, viene automaticamente incluso come `llm_base_url` nel record TXT. Ciò è destinato alla partecipazione a zero-configurazione dei nodi collocati con Ollama tramite mDNS. Porte non predefinite (11435, ecc.) o lmstudio / llamacpp richiedono ancora voci esplicite in `config.json`.

### Gestione di Nodi Ollama Puri Bare (senza yu) (politica)

I nodi Ollama puri bare dove `yu_ai_manager` **non** è in esecuzione (ad es. il Mac di un membro della famiglia che ha solo Ollama installato, o un contenitore Ollama su un NAS) **non sono coperti dall'auto-discovery**. Ollama stesso non ha alcuna caratteristica che pubblicizzi `_ollama._tcp.local.` ufficialmente, quindi non c'è alcun modo strutturale per rilevarli.

Per utilizzare tali nodi dal LLM Router, configurali **manualmente** tramite uno di:

```json
{
  "llm_router": {
    "backends": [
      { "alias": "ollama-nas",    "base_url": "http://nas.local:11434/v1",     "type": "ollama" },
      { "alias": "ollama-family", "base_url": "http://192.168.1.42:11434/v1", "type": "ollama" }
    ]
  }
}
```

- Se il tuo ambiente supporta i nomi host `.local` (vedi "Auto-discovery dei Nodi -- Supporto Hostname `.local`" sopra), preferisci quello
- Altrimenti, hard-code l'indirizzo IP fisso

#### Perché l'auto-discovery non viene tentato

Quando si progettava questo (2026-04-11), le seguenti tre opzioni sono state confrontate e l'opzione (c) configurazione manuale è stata scelta:

| Opzione | Descrizione | Decisione |
|---|---|---|
| (a) Scansione dell'intera LAN `:11434` all'avvio | Sonda di forza bruta di tutti gli host nella subnet | **Rifiutata** -- carico di rete pesante, dirompente su LAN aziendali / grandi, può essere scambiata per port scanning, contraddice la filosofia edge-first |
| (b) Daemon advertiser esterno di Ollama | Spedisci un advertiser leggero fornito da yu che viene eseguito insieme a ogni host Ollama | **Rifiutata** -- richiede un processo residente aggiuntivo, equivalente a installare `yu_ai_manager` stesso. Sconfigge il punto di "puro bare" |
| (c) Configurazione manuale del backend tramite IP fisso / `.local` | Voci scritte a mano in `config.json` | **Scelta** -- implementazione zero aggiuntiva, comportamento esplicito, evita di trascinare gli utenti in scansioni non intenzionali |

Se Ollama upstream in seguito pubblicizzerà `_ollama._tcp.local.` ufficialmente, o aggiunge un meccanismo ufficiale di service discovery, rivisiteremo questo come Phase D a quel tempo.

### Disabilitazione

Puoi disabilitare l'auto-discovery negli ambienti in cui non è necessario (isolamento Docker, LAN aziendale, CI, ecc.):

- Aggiungi `"mdns": {"enabled": false}` a `config.json`
- Oppure imposta la variabile di ambiente `YU_AI_MDNS_DISABLED=1`

### Comportamenti Conosciuti

- **Ambienti multi-homed (Wi-Fi + Ethernet)**: Con l'impostazione predefinita (`bind_address: null`), la pubblicità avviene su entrambi gli indirizzi e `PeerInfo.addresses` conterrà più IP. Per limitare a una singola interfaccia, specifica `"bind_address": "192.168.x.y"`.
- **Collisione di alias**: Se un backend in `config.json` utilizza un alias nel formato `mdns-xxxxxxxx`, la configurazione manuale ha priorità e la voce scoperta da mDNS viene saltata.
- **Cross-subnet**: mDNS funziona solo nel dominio di broadcast L2 per impostazione predefinita. Per il funzionamento cross-subnet, usa l'approccio con nome host `.local` della Phase A.
- **Sicurezza**: mDNS stesso non ha autenticazione. È progettato per ambienti affidabili come home LAN. La disabilitazione è consigliata su Wi-Fi pubblico o reti condivise di grandi dimensioni. La verifica `/api/mdns/identity` previene l'errata identificazione accidentale di nodi o la miscelazione di versioni più vecchie incompatibili.
