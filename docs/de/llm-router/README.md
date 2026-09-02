# LLM Router

> Zielversion: v4.55.0 oder später

## Was ist LLM Router

LLM Router ist ein **OpenAI-kompatibler LLM-Proxy**, der in yu_ai_manager integriert ist.  
Er bündelt mehrere lokale LLM-Backends wie Ollama, LM Studio und llama.cpp  
und stellt sie als **einzelnen Endpunkt** für Clients wie Claude Code, Continue und Open WebUI bereit.

```
Client (Claude Code / Continue, etc.)
          │  (OpenAI-kompatibler API)
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
    │   mdns-win01  ─── mDNS-automatisch erkannte Backends (alias: "mdns-<prefix>") │
    └─────────────────────────────────────────┘
```

### Funktionen

| Merkmal | Merkmal |
|---|---|
| **Mehrere Backends bündeln** | Registrieren Sie beliebig viele Ollama-Instanzen im LAN |
| **Abstraktion durch Aliase** | Verbergen Sie tatsächliche Modellnamen mit `"model": "fast"` |
| **mDNS-Automatische Erkennung** | yu_ai_manager-Knoten im gleichen LAN automatisch registrieren, ohne Konfiguration |
| **Claude Code Integration** | Implementieren Sie Anthropic-kompatible `/v1/messages`. Kein zusätzlicher Proxy erforderlich |
| **Dynamisches Aktivieren/Deaktivieren** | Backends sofort von der WebUI wechseln. Kein Neustart erforderlich |
| **Kategoriebasiertes Routing** | Optimale Modelle automatisch auswählen über virtuelle Backends `large` / `fast` / `vision` |

---

## Architektur

```
Client (Claude Code / Continue, etc.)
    │
    │ POST /v1/chat/completions
    │ POST /v1/messages          ← Anthropic compatible
    │ GET  /v1/models
    ▼
BackendCatalog  ─── Alias-Auflösung ──► Backend + Modellname
    │
    ├─ Manuell registrierte Backends (in config.json geschrieben)
    └─ mDNS-automatisch erkannte Backends (alias: "mdns-<prefix>")
```

**Anfrageflusss:**

1. Client sendet Anfrage mit `"model": "claude-opus-4-7"`
2. Router löst `"claude-opus-4-7"` → `"large"` in der Tabelle `aliases` auf
3. Wählen Sie einen gültigen Backend aus der Kategorie `large`
4. {trans["flow_step_4"]}
5. {trans["flow_step_5"]}

---

## Dokumentationsindex

| Merkmal | Merkmal |
|---|---|
| [Setup](setup.md) | Wie man config.json schreibt, Integration mit Claude Code/Continue, mDNS-Konfiguration |
| [WebUI](webui.md) | Bedienung des `/llm-router`-Dashboards |
| [Hailo-Automatische Erkennung](hailo-auto-discovery.md) | Automatische Registrierung von Knoten mit Hailo NPU |
| [Behandlung unerreichbarer Peers](mdns-peer-unreachable.md) | Behebung wenn mDNS erkannte Peers `unreachable` werden |

---

## Gateway Unterschied zum Gateway

| | LLM Router | Gateway |
|---|---|---|
| **Bereich** | Nur LLM (Ollama, etc.) | SD WebUI, ComfyUI, Ollama zusammen |
| **Authentifizierungsgrenze** | Lokal kann umgangen werden. api_key erforderlich außerhalb LAN | Bearer-Authentifizierung basierend auf Bereich für alle Backends |
| **Endpunkte** | `/v1/*` (OpenAI/Anthropic-kompatibel) | `/v1/*`, `/sd/*`, `/comfy/*` |
| **Primärer Verwendungszweck** | Backend für KI-Codier-Tools | Exposieren Sie Generierungstools sicher für externe Clients |

Beide Funktionen arbeiten unabhängig voneinander. Wenn Sie nur LLM verwenden, ist LLM Router allein ausreichend.

---

## Beziehung zu LAN Cowork

Wenn [LAN Cowork](../lan-cowork/README.md) aktiviert ist,  
werden Peers im gleichen LAN automatisch über mDNS erkannt und automatisch  
im LLM Router mit Aliasen wie `mdns-<node_id[:8]>` registriert.  
Eine Multi-Node-LLM-Umgebung wird ohne Konfiguration eingerichtet.
