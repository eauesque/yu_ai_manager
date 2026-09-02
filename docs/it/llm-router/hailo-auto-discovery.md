# Hailo LLM Auto-discovery

**Versione supportata**: v4.66.0 e successivi

## Panoramica

yu_ai_manager può scoprire e utilizzare automaticamente gli endpoint LLM in esecuzione su Hailo NPU del Pi5 senza modificare `config.json`. Basta collegare un Pi5 alla LAN e altri nodi yu_ai_manager possono chiamare Hailo LLM.

## Due Tipi di Endpoint

| Endpoint | Descrizione | Pattern URL Predefinito |
|---|---|---|
| **yu extension Hailo LLM** | LLM compatibile con OpenAI fornito dall'estensione integrata `builtin-hailo-genai` in yu_ai_manager | `http://<host>:<yu-port>/ext/hailo-genai/v1/` |
| **hailo-ollama** | LLM compatibile con OpenAI fornito dal binario esterno `/usr/bin/hailo-ollama` (porta predefinita `:8000`) | `http://<host>:8000/v1/` |

Entrambi possono essere eseguiti contemporaneamente e vengono registrati automaticamente. Con HailoRT 5.3.0+ e `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED` impostato, lo scheduler HailoRT condivide il dispositivo fisico tramite round-robin, quindi non c'è conflitto quando si utilizzano entrambi contemporaneamente.

## Registrazione Automatica Locale (Phase A)

All'avvio, yu_ai_manager rileva in modo indipendente i seguenti due endpoint:

1. **yu extension**: Se `hailo_platform.genai.LLM` è importabile e esiste `/dev/hailo0` o `/dev/h1x-0`, viene registrato automaticamente come backend `hailo-local` nel catalogo
   (v4.66.1 ha aggiunto il supporto per Raspberry Pi 5 + AI HAT + HailoRT 5.3.0 che espone il dispositivo come `/dev/h1x-0`)
2. **hailo-ollama**: Una sonda HTTP viene inviata a `localhost:8000/v1/models` (timeout di 2 secondi). Se viene ricevuta una risposta 200, viene registrata automaticamente come backend `hailo-ollama-local`

Se un backend con lo stesso alias esiste già in `llm_router.backends` in `config.json`, quella configurazione ha priorità (non verrà sovrascritta).

## Pubblicità mDNS (Phase B)

In base ai risultati del rilevamento della Phase A, yu_ai_manager pubblicizza le funzionalità Hailo ad altri nodi tramite record TXT mDNS:

- `capabilities=llm,hailo` -- Indica che l'estensione yu è disponibile
- `hailo_ollama_url=http://192.168.1.10:8000/v1/` -- Incluso solo se hailo-ollama è in esecuzione (riscritto in un IP raggiungibile dalla LAN)

Quando altri nodi yu_ai_manager lo ricevono tramite mDNS, eseguono la verifica dell'identità tramite l'endpoint `/api/mdns/identity`, quindi registrano automaticamente backend aggiuntivi con i seguenti alias:

- `mdns-<node_id[:8]>-hailo` -- yu extension Hailo LLM (quando `capabilities` include `hailo`, l'URL è derivato da `web_port` del peer + indirizzi)
- `mdns-<node_id[:8]>-hailo-ollama` -- hailo-ollama esterno (quando `hailo_ollama_url` è pubblicizzato, l'URL dal record TXT è utilizzato così com'è)

## Configurazione

Abilitato per impostazione predefinita. Puoi disabilitarlo in `config.json` come segue:

```json
{
  "llm_router": {
    "hailo_ollama": {
      "enabled": false,
      "port": 8000
    }
  }
}
```

- **`enabled`**: Impostare su `false` per disabilitare completamente il rilevamento automatico di hailo-ollama. Il rilevamento dell'estensione yu è controllato separatamente (determinato automaticamente dalla disponibilità dell'estensione)
- **`port`**: Numero di porta per hailo-ollama (predefinito 8000). I valori al di fuori dell'intervallo 1--65535 tornano al predefinito con un avviso di registro

## Note sulla Sicurezza

**hailo-ollama non ha autenticazione**. Quando pubblicizzato tramite mDNS, **qualsiasi nodo sulla LAN può consumare liberamente le risorse di inferenza di hailo-ollama**.

| Endpoint | Autenticazione | Esposizione Effettiva della LAN |
|---|---|---|
| yu extension (`/ext/hailo-genai/v1/`) | Catena di autenticazione web di yu (PIN/sessione/chiave API) | Solo client autenticati con yu |
| hailo-ollama (`hailo_ollama_url`) | **Nessuna** | **Tutti i nodi sulla LAN** |

Per ambienti diversi da LAN domestiche o VLAN affidabili (ad es. Wi-Fi pubblico), disabilita l'auto-pubblicità con `hailo_ollama.enabled: false`.

## Aspetto nel WebUI del LLM Router

I backend registrati automaticamente vengono visualizzati nel dashboard `/llm-router` (v4.65.0):

- `hailo-local` / `hailo-ollama-local` -- Rilevati localmente (origine: badge `static`)
- `mdns-<id>-hailo` / `mdns-<id>-hailo-ollama` -- Scoperto tramite mDNS (origine: badge `mdns`)

Tutti possono essere disabilitati temporaneamente tramite il comando Disable. Lo stato disabilitato è persistente in `data/llm_router_state.json` e conservato dopo i riavvii (implementato in v4.65.0).

## Sicurezza da Falsi Positivi

Il rilevamento della Phase A ha due meccanismi di sicurezza:

1. **Evitamento della sonda automatica**: Se `hailo_ollama.port` è impostato sullo stesso valore della porta web di yu stessa, la sonda viene saltata completamente (previene che yu si identifichi erroneamente come hailo-ollama)
2. **Priorità del backend esistente**: Se un backend con lo stesso `localhost:<port>/v1` è già registrato in `config.json`, la sonda viene saltata per rispettare l'intento dell'utente

## Elementi TODO Rimanenti

- (P3) Traduzioni in più lingue (`en`, `zh-tw`, `zh-cn`, `ko`) -- pianificate di essere affrontate insieme al backlog di traduzione del WebUI del LLM Router v4.65.0
- (P3) Test di integrazione Pi5 -- Equivalente di 16 elementi Playwright in una configurazione a 2 nodi
- (P3) Supporto IPv6 -- Attualmente `_pick_lan_ip` restituisce solo IPv4
- (P3) Supporto per più dispositivi Hailo -- Presuppone un alias fisso `hailo-local`. Design con suffisso indice da considerare per casi come più dongle USB
- (P3) `BackendCatalog.remove_backend()` -- Attualmente `_mark_unreachable` aggiorna solo lo stato e non rimuove dal catalogo

## Documentazione Correlata

- [Setup del LLM Router](./setup.md)
- Design spec: `docs/superpowers/specs/2026-04-08-hailo-auto-discovery-design.md`
- Piano di implementazione: `docs/superpowers/plans/2026-04-08-hailo-auto-discovery.md`

## v4.66.2 -- Autenticazione Peer Affidabile (Correzione di un Buco di Autenticazione su Dispositivo Reale)

Nella Hailo auto-discovery di v4.66.0, l'estensione `/ext/hailo-genai/*` di yu era protetta dalla catena di autenticazione web. Quando il driver del LLM Router (che non ha né un token Bearer né una sessione) tentava di sondare/inviare, il middleware di autenticazione restituiva HTML honeypot, causando errori di analisi JSON e il backend rimane bloccato come `unreachable`.

### Come Funziona

- Un nuovo `TrustedPeerRegistry` semina `127.0.0.1` / `::1` al momento dell'inizializzazione
- Quando `LlmRouterMdnsBridge` verifica con successo un peer (HTTP GET a `/api/mdns/identity` + conferma di corrispondenza node_id), tutti gli indirizzi pubblicizzati di quel peer vengono aggiunti al registro
- `auth_chain.check_trusted_peer` ignora l'autenticazione PIN quando riceve una richiesta per percorsi `/ext/<name>/v1/*` se remote_addr è nel registro
- I percorsi di autenticazione della chiave API / sessione / cookie esistenti rimangono invariati

### Relazione con Quick Lock

- **loopback** (sonda automatica di yu): Sempre passa, anche durante quick_lock
- **peer IP**: Le richieste vengono rifiutate durante quick_lock (`check_quick_lock` restituisce 503). Ciò significa che i peer rispettano anche lo stato "utente ha bloccato intenzionalmente"

Questo abilita i seguenti scenari a funzionare come previsto:

- Sonda automatica `hailo-local` di pi2 (`http://localhost:5000/ext/hailo-genai/v1/models`)
- Invio cross-node da Windows a `mdns-<id>-hailo` di pi2 (`http://192.168.50.4:5000/ext/hailo-genai/v1/chat/completions`)

### Configurazione

Non sono necessarie modifiche al file di configurazione. Anche in ambienti in cui mDNS è disabilitato, il seed loopback continua a funzionare, quindi la correzione della sonda automatica è disponibile in modo incondizionato.

### Debug

Impostare la variabile di ambiente `TAGDB_DEBUG_TRUSTED_PEERS=1` prima di avviare yu per aggiungere un campo `trusted_ips` alla risposta `/api/mdns/peers`. Non impostare questo in produzione (l'elenco di fiducia è essenzialmente un "elenco target di attacco" e non dovrebbe essere esposto su endpoint non autenticati).

### Confine di Sicurezza

Operante secondo l'assunzione di "LAN affidabile" (stesso presupposto della Phase B di v4.64.0). La protezione contro nodi dannosi con accesso fisico alla LAN è fuori portata -- usa il comando Disable toggle nel WebUI `/llm-router` o quick_lock per tali casi.

Vedi `docs/superpowers/specs/2026-04-09-trusted-peer-auth-design.md` per i dettagli.
