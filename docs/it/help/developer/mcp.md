# Integrazione MCP

YU AI Manager incorpora un server MCP (Model Context Protocol), permettendo di operare direttamente da client AI come Claude Desktop, Claude Code e Cline. Offre oltre 137 strumenti e accede a tutte le funzionalità dalla gestione immagini all'analisi AI.

## Client MCP Supportati

| Client | Metodo connessione | Note |
|--------|--------------------|------|
| Claude Desktop | stdio / HTTP | Client consigliato |
| Claude Code | stdio | Ambiente CLI |
| Cline (VS Code) | stdio | Estensione VS Code |
| Open WebUI | HTTP/SSE | Web-based |

## Connessione Locale (stdio)

Per connettersi da Claude Desktop / Claude Code sulla stessa macchina:

1. Creare una API key dalla scheda Settings > API Keys
2. Aggiungere quanto segue al file di configurazione del client

### Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

### Claude Code

`.mcp.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/yu_ai_manager",
      "env": {
        "YU_BASE_URL": "http://localhost:5000",
        "YU_API_KEY": "sk_your_api_key_here"
      }
    }
  }
}
```

## Connessione LAN (HTTP/SSE)

Per connettersi da un'altra macchina in LAN:

1. Impostare LAN Access su ON nelle impostazioni di YU AI Manager
2. Creare una API key
3. Copiare la configurazione di connessione da Settings > API Keys > "MCP Connection Snippet"

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "type": "http",
      "url": "http://192.168.x.x:5000/mcp",
      "headers": {
        "Authorization": "Bearer sk_your_api_key_here"
      }
    }
  }
}
```

## Strumenti Disponibili (per Categoria)

### Ricerca e Gestione Immagini

| Strumento | Descrizione |
|-----------|-------------|
| `search_images` | Ricerca con filtri per tag, data, rating ecc. |
| `get_image_detail` | Recupero metadati dettagliati immagine |
| `get_library_stats` | Statistiche libreria (conteggio file, distribuzione tag ecc.) |
| `find_similar` | Rilevamento immagini simili tramite hash percettivo |
| `rate_images` | Impostazione batch valutazione a stelle |
| `set_tags` | Aggiunta/rimozione tag |
| `set_annotations` | Impostazione annotazioni |
| `get_annotations` | Recupero annotazioni |

### Collezioni

| Strumento | Descrizione |
|-----------|-------------|
| `list_collections` | Lista collezioni |
| `create_collection` | Creazione collezione |
| `add_to_collection` | Aggiunta immagini alla collezione |
| `remove_from_collection` | Rimozione immagini dalla collezione |
| `delete_collection` | Eliminazione collezione |

### Scansione

| Strumento | Descrizione |
|-----------|-------------|
| `trigger_scan` | Esecuzione scansione |
| `get_scan_status` | Verifica avanzamento scansione |
| `list_scan_roots` | Lista radici di scansione |
| `add_scan_root` | Aggiunta radice di scansione |
| `scan_directory` | Scansione directory specifica |

### Analisi AI

| Strumento | Descrizione |
|-----------|-------------|
| `analyze_image` | Analisi AI immagine (singola) |
| `analyze_batch` | Analisi AI immagine (batch) |
| `wd_tagger_tag_file` | Inferenza WD-Tagger (singola) |
| `wd_tagger_batch` | Inferenza WD-Tagger (batch) |
| `semantic_search` | Ricerca semantica CLIP |
| `s2t_transcribe_video` | Trascrizione vocale |

### Bridge

| Strumento | Descrizione |
|-----------|-------------|
| `sd_generate` | Generazione immagini con SD WebUI |
| `sd_list_models` | Lista modelli SD WebUI |
| `comfyui_generate` | Generazione immagini con ComfyUI |
| `comfyui_generate_json` | Esecuzione workflow JSON ComfyUI |

### Libreria Prompt

| Strumento | Descrizione |
|-----------|-------------|
| `create_prompt` | Creazione prompt |
| `search_prompts` | Ricerca prompt |
| `get_prompt` | Recupero prompt |
| `update_prompt` | Aggiornamento prompt |

### Impostazioni

| Strumento | Descrizione |
|-----------|-------------|
| `settings_get_schema` | Recupero schema impostazioni |
| `settings_get` | Recupero valore impostazione |
| `settings_set` | Aggiornamento valore impostazione |
| `secrets_status` | Verifica stato chiave di crittografia |

### Meccanismi di Sicurezza Agente

| Strumento | Descrizione |
|-----------|-------------|
| `agent_kill` / `agent_resume` | Controllo Kill Switch |
| `agent_status` | Stato meccanismi di sicurezza |
| `agent_journal` | Ricerca journal operazioni |
| `agent_undo` | Annullamento operazione |
| `agent_circuit_breaker_status` | Stato Circuit Breaker |
| `agent_budget_status` | Stato budget tracker |
| `agent_scope_set` | Impostazione scope |
| `agent_anomaly_status` | Stato rilevamento anomalie |

### Altro

| Strumento | Descrizione |
|-----------|-------------|
| `find_duplicates` | Rilevamento file duplicati |
| `search_chat_logs` | Ricerca chat log |
| `search_md_files` | Ricerca file Markdown |
| `help_search` | Ricerca documentazione help |
| `share_to_bluesky` | Post su Bluesky |
| `list_trophies` | Lista trofei |
| `get_monthly_report` | Report mensile |

## Variabili d'Ambiente

| Variabile | Descrizione | Default |
|-----------|-------------|---------|
| `YU_BASE_URL` | URL del server | `http://localhost:5000` |
| `YU_API_KEY` | API key | (obbligatorio) |
| `YU_DEBUG_MODE` | Abilitazione strumenti debug | `0` |

Con `YU_DEBUG_MODE=1` vengono aggiunti strumenti dedicati al debug come query dirette DB e health check.

## Risoluzione dei Problemi

### Impossibile connettersi

1. Verificare che YU AI Manager sia avviato
2. Verificare che la API key sia corretta (con prefisso `sk_`)
3. Verificare che `YU_BASE_URL` sia corretto
4. Per connessioni LAN, verificare che LAN Access sia ON

### Strumenti Non Trovati

- Se un'Extension è disabilitata, i suoi strumenti diventano non disponibili
- Verificare lo stato di abilitazione con `list_extensions`

### Timeout

- Le ricerche e le operazioni batch su librerie di grandi dimensioni possono richiedere tempo
- Limitare i risultati con il parametro `limit`

## Cos'è MCP

Model Context Protocol — standardizzato interfaccia tra LLM e tool server.
YU AI Manager fornisce 521+ strumenti via MCP.

## Setup

```bash
# Dipendenze
uv pip install mcp

# Test server
python -m mcp_server
```

## Implementare tool

```python
from mcp.server.tools import Tool

class MyServer(MCPServer):
    def setup(self):
        self.register_tool(
            Tool(
                name="my_tool",
                description="Descrizione tool",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "param": {"type": "string"}
                    }
                },
                handler=self.my_handler
            )
        )

    async def my_handler(self, param: str):
        return {"result": f"Processed {param}"}
```

## Testing

```python
# Test handler
async def test_my_tool():
    server = MyServer()
    result = await server.my_handler("test")
    assert result["result"] == "Processed test"
```

## Deployment

Registra in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "my-server": {
      "command": "python",
      "args": ["-m", "my_server"]
    }
  }
}
```

## Best practices

- Input validation rigorosa
- Output consistent format
- Caching risultati when appropriate
- Proper error handling
- Documentare tool
