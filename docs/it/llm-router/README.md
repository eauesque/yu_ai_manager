# LLM Router

> Versione di destinazione: v4.55.0 o successiva

## Cos'è LLM Router

LLM Router è un **proxy LLM compatibile con OpenAI** integrato in yu_ai_manager.  
Riunisce più backend LLM locali come Ollama, LM Studio e llama.cpp,  
e li fornisce come un **singolo endpoint** a client come Claude Code, Continue e Open WebUI.

```
Client (Claude Code / Continue, ecc.)
          │  (API compatibile con OpenAI)
          ▼
    yu_ai_manager
    ┌─────────────────────────────────────────┐
    │           LLM Router                   │
    │                                         │
    │  alias: "claude-opus-4-7" ──► large    │
    │  alias: "local-coder" ──► ollama-mac/…│
    │                                         │
    │  [BackendCatalog]                       │
    │   ollama-mac  ─── 192.168.1.10:11434   │
    │   ollama-pi5  ─── 192.168.1.20:11434   │
    │   mdns-win01  ─── Backend rilevati automaticamente da mDNS (alias: "mdns-<prefix>") │
    └─────────────────────────────────────────┘
```

### Capacità

| Funzionalità | Funzionalità |
|---|---|
| **Raggruppamento di più backend** | Registra un numero qualsiasi di istanze Ollama sulla LAN |
| **Astrazione con alias** | Nascondi i nomi reali dei modelli con `"model": "fast"` |
| **Rilevamento automatico mDNS** | Registra automaticamente i nodi yu_ai_manager sulla stessa LAN senza configurazione |
| **Integrazione Claude Code** | Implementa `/v1/messages` compatibile con Anthropic. Nessun proxy aggiuntivo necessario |
| **Controllo dinamico abilita/disabilita** | Cambia i backend immediatamente dall'interfaccia Web. Nessun riavvio necessario |
| **Routing basato su categoria** | Seleziona automaticamente i modelli ottimali tramite backend virtuali `large` / `fast` / `vision` |

---

## Architettura

```
Client (Claude Code / Continue, ecc.)
    │
    │ POST /v1/chat/completions
    │ POST /v1/messages          ← Anthropic compatible
    │ GET  /v1/models
    ▼
BackendCatalog  ─── Risoluzione dell'alias ──► Backend + nome del modello
    │
    ├─ Backend registrati manualmente (scritti in config.json)
    └─ Backend rilevati automaticamente da mDNS (alias: "mdns-<prefix>")
```

**Flusso di richiesta:**

1. Il client richiede con `"model": "claude-opus-4-7"`
2. Il router risolve `"claude-opus-4-7"` → `"large"` nella tabella `aliases`
3. Seleziona un backend valido dalla categoria `large`
4. {trans["flow_step_4"]}
5. {trans["flow_step_5"]}

---

## Indice della documentazione

| Funzionalità | Funzionalità |
|---|---|
| [Configurazione](setup.md) | Come scrivere config.json, integrazione con Claude Code/Continue, configurazione mDNS |
| [Interfaccia Web](webui.md) | Come utilizzare la dashboard `/llm-router` |
| [Rilevamento automatico Hailo](hailo-auto-discovery.md) | Registrazione automatica dei peer con Hailo NPU |
| [Gestione dei peer irraggiungibili](mdns-peer-unreachable.md) | Risoluzione dei problemi quando i peer rilevati da mDNS diventano `unreachable` |

---

## Gateway Differenza rispetto a Gateway

| | LLM Router | Gateway |
|---|---|---|
| **Ambito** | Solo LLM (Ollama, ecc.) | SD WebUI, ComfyUI, Ollama insieme |
| **Limite di autenticazione** | Il locale può essere bypassato. api_key richiesto al di fuori della LAN | Autenticazione Bearer basata su scope per tutti i backend |
| **Endpoint** | `/v1/*` (compatibile con OpenAI/Anthropic) | `/v1/*`, `/sd/*`, `/comfy/*` |
| **Caso d'uso principale** | Backend per strumenti di codifica IA | Esponi in modo sicuro i strumenti di generazione ai client esterni |

Entrambe le funzionalità funzionano in modo indipendente. Se utilizzi solo LLM, LLM Router è sufficiente.

---

## Relazione con LAN Cowork

Quando [LAN Cowork](../lan-cowork/README.md) è abilitato,  
i peer sulla stessa LAN vengono rilevati automaticamente tramite mDNS e registrati automaticamente  
in LLM Router con alias come `mdns-<node_id[:8]>`.  
Un ambiente LLM multi-nodo viene configurato senza configurazione.
