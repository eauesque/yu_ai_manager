# Guida di Integrazione MCP — Operare YU AI Manager da un LLM

YU AI Manager ha un **server MCP (Model Context Protocol)** incorporato che permette alle applicazioni LLM di operare la libreria di immagini usando il linguaggio naturale.

Non c'è nessuna UI chat incorporata in questa applicazione.
Per interagire con essa usando il linguaggio naturale, connetti da un tuo client compatibile con MCP preferito.

---

## Che Cos'è MCP?

MCP (Model Context Protocol) è un protocollo standard che abilita le applicazioni LLM ad accedere a strumenti e fonti di dati esterne.
YU AI Manager funge da server MCP, e i client LLM (come Claude Desktop) si connettono ad esso, traducendo le istruzioni in linguaggio naturale in operazioni API.

```
┌─────────────────┐      MCP (stdio)       ┌─────────────────────┐
│  LLM Client     │ <--------------------> │  YU AI Manager      │
│  (Claude Desktop│                        │  MCP Server         │
│   / Open WebUI   │                        │  (python -m         │
│   / Cline etc.)  │                        │   mcp_server)       │
└─────────────────┘                        └────────┬────────────┘
                                                    │ HTTP API
                                                    v
                                          ┌─────────────────────┐
                                          │  YU AI Manager      │
                                          │  Web Server          │
                                          │  (localhost:5000)    │
                                          └─────────────────────┘
```

## Client MCP Supportati

I seguenti sono client rappresentativi compatibili con MCP. I passaggi di configurazione sono simili per tutti loro.

| Client | Provider | Funzionalità |
|---|---|---|
| **Claude Desktop** | Anthropic | Accesso diretto a Claude. Supporto nativo MCP |
| **Claude Code** | Anthropic | Client basato su terminale per sviluppatori |
| **Cline** | Estensione VS Code | Integrazione editor. Supporto multi-LLM |
| **Open WebUI** | Open Source | Self-hosted. Può essere combinato con LLM locali come Ollama |

Nota: Il numero di client compatibili con MCP sta crescendo rapidamente.
Qualsiasi client che supporti il trasporto stdio dovrebbe essere in grado di connettersi.

## Configurazione

### 1. Avvia YU AI Manager

Il server MCP opera attraverso l'API del Web server, quindi YU AI Manager deve essere eseguito prima.

```bash
python web_ui.py --db ./tags.db --port 5000
```

### 2. Emetti una Chiave API (Consigliato)

L'emissione di una chiave API consente al server MCP di aggirare l'autenticazione PIN quando si utilizza la condivisione LAN o l'autenticazione PIN.

Le chiavi API possono essere emesse da Impostazioni -> Chiavi API.

Una chiave API non è necessaria quando si esegue senza PIN (`config_test.json`).

### 3. Aggiungi Impostazioni di Connessione al tuo Client MCP

#### Claude Desktop

Modifica `claude_desktop_config.json`:

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "C:/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

#### Claude Code

Aggiungi impostazioni a `.mcp.json` alla radice del progetto, o usa il comando `claude mcp add`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

#### Cline (VS Code)

Inserisci le stesse informazioni tramite le Impostazioni MCP di Cline.

#### Variabili d'Ambiente

| Variabile | Richiesta | Predefinito | Descrizione |
|---|---|---|---|
| `YU_BASE_URL` | - | `http://localhost:5000` | URL del web server |
| `YU_API_KEY` | - | Nessuno | Chiave API (richiesta negli ambienti PIN) |
| `YU_DEBUG_MODE` | - | `0` | Imposta a `1` per aggiungere strumenti di debug |

## Esempi di Utilizzo

Una volta connesso, puoi operare la libreria di immagini dando istruzioni in linguaggio naturale al LLM.

### Ricerca e Navigazione

```
"Mostrami le 20 immagini più recenti di ragazze con occhi blu"
"Filtra solo immagini generate con NovelAI"
"Mostrami statistiche per immagini scansionate la scorsa settimana"
```

### Organizza e Classifica

```
"Dai a queste 10 immagini una valutazione di 5 stelle"
"Aggiungi immagini contrassegnate 'landscape' alla 'Scenery Collection'"
"Elenca tutte le immagini con una valutazione di 3 o inferiore"
```

### Analisi e Annotazione

```
"Valuta la qualità delle immagini aggiunte di recente e salva alle annotazioni"
"Mostrami tutte le annotazioni per l'immagine ID 12345"
"Cerca annotazioni con fonte agent:claude"
```

### Operazioni di Scansione

```
"Scansiona per nuove immagini"
"Controlla il progresso della scansione"
"Mostrami eventuali errori di scansione"
```

## Strumenti Disponibili

Il server MCP espone i seguenti strumenti all'LLM:

### Ricerca e Navigazione (4 strumenti)

| Nome Strumento | Descrizione |
|---|---|
| `search_images` | Cerca immagini per tag, data, formato, valutazione, ecc. |
| `get_image_detail` | Recupera tutti i metadati per un'immagine |
| `get_library_stats` | Statistiche libreria (conteggio file, conteggio tag, distribuzione fonte, ecc.) |
| `find_similar` | Cerca immagini simili usando hash percettivo |

### Collezioni (4 strumenti)

| Nome Strumento | Descrizione |
|---|---|
| `list_collections` | Elenca collezioni |
| `create_collection` | Crea una collezione |
| `delete_collection` | Elimina una collezione |
| `add_to_collection` / `remove_from_collection` | Aggiungi/rimuovi immagini |

### Tag e Valutazioni (2 strumenti)

| Nome Strumento | Descrizione |
|---|---|
| `rate_images` | Imposta valutazioni stelle per più immagini contemporaneamente |
| `set_tags` | Aggiungi/rimuovi tag per più immagini contemporaneamente |

### Annotazioni (4 strumenti)

| Nome Strumento | Descrizione |
|---|---|
| `set_annotations` | Salva risultati analisi AI come annotazioni |
| `get_annotations` | Recupera annotazioni per un'immagine |
| `search_annotations` | Cerca annotazioni tra fonte, chiave e confidenza |
| `delete_annotations` | Elimina annotazioni |

### Scansione (3 strumenti)

| Nome Strumento | Descrizione |
|---|---|
| `trigger_scan` | Avvia una scansione |
| `get_scan_status` | Controlla il progresso della scansione |
| `get_scan_errors` | Elenca gli errori di scansione |

### Altro

Sono inclusi anche strumenti per la libreria prompt, il backup e la gestione dei client MCP.

## FAQ

### D: Non c'è nessuna funzione di chat nell'app?

R: Non c'è. YU AI Manager è specializzato nella gestione dei metadati delle immagini, e l'interfaccia AI conversazionale è delegata ai client compatibili con MCP. Puoi eseguire tutte le operazioni tramite linguaggio naturale eseguendo Claude Desktop o un client simile insieme ad esso.

### D: Quale LLM dovrei usare?

R: Funziona qualsiasi LLM, purché il client MCP lo supporti.
Per un'elaborazione affidabile degli argomenti dello strumento, i modelli su larga scala come Claude o GPT-4 tendono a funzionare in modo più coerente.

### D: Posso usare un LLM locale?

R: Sì, i LLM locali funzionano con combinazioni come Open WebUI + Ollama, a condizione che supportino MCP. Tuttavia, l'accuratezza del tool-calling dipende dalle capacità del modello.

### D: YU AI Manager ha anche una funzione client MCP?

R: L'estensione `MCP Client` (nella pagina Strumenti) connette YU AI Manager a **altri server MCP**. Questa guida descrive la direzione opposta: LLM esterno -> YU AI Manager.
