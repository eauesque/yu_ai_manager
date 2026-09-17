# Integração com MCP

O YU AI Manager possui um servidor MCP (Model Context Protocol) embutido,
que permite operá-lo diretamente a partir de clientes de IA como Claude Desktop, Claude Code e Cline.
Oferece mais de 137 ferramentas e possibilita acessar todas as funções, da gestão de imagens à análise por IA.

## Clientes MCP suportados

| Cliente | Modo de conexão | Observações |
|-------------|---------|------|
| Claude Desktop | stdio / HTTP | Cliente recomendado |
| Claude Code | stdio | Ambiente CLI |
| Cline (VS Code) | stdio | Extensão do VS Code |
| Open WebUI | HTTP/SSE | Baseado em web |

## Conexão local (stdio)

Para conectar a partir do Claude Desktop / Claude Code na mesma máquina:

1. Na aba Settings > API Keys, crie uma API Key
2. Adicione o seguinte no arquivo de configuração do cliente

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

## Conexão via LAN (HTTP/SSE)

Para conectar a partir de outra máquina na LAN:

1. Ative LAN Access no YU AI Manager
2. Crie uma API Key
3. Copie a configuração de conexão em "MCP Connection Snippet" na aba Settings > API Keys

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

## Ferramentas disponíveis (por categoria)

### Busca e gerenciamento de imagens

| Ferramenta | Descrição |
|--------|------|
| `search_images` | Busca com filtros por tags, data, rating etc. |
| `get_image_detail` | Obtém metadados detalhados da imagem |
| `get_library_stats` | Estatísticas da biblioteca (número de arquivos, distribuição de tags etc.) |
| `find_similar` | Detecção de imagens semelhantes por hash perceptual |
| `rate_images` | Definição em lote de rating por estrelas |
| `set_tags` | Adicionar/remover tags |
| `set_annotations` | Definir anotações |
| `get_annotations` | Obter anotações |

### Coleções

| Ferramenta | Descrição |
|--------|------|
| `list_collections` | Lista coleções |
| `create_collection` | Cria coleção |
| `add_to_collection` | Adiciona imagem a uma coleção |
| `remove_from_collection` | Remove imagem de uma coleção |
| `delete_collection` | Remove coleção |

### Scan

| Ferramenta | Descrição |
|--------|------|
| `trigger_scan` | Executa scan |
| `get_scan_status` | Verifica o progresso do scan |
| `list_scan_roots` | Lista scan roots |
| `add_scan_root` | Adiciona scan root |
| `scan_directory` | Scan de um diretório específico |

### Análise por IA

| Ferramenta | Descrição |
|--------|------|
| `analyze_image` | Análise de imagem por IA (única) |
| `analyze_batch` | Análise de imagens por IA (em lote) |
| `wd_tagger_tag_file` | Inferência WD-Tagger (única) |
| `wd_tagger_batch` | Inferência WD-Tagger (em lote) |
| `semantic_search` | Busca semântica CLIP |
| `s2t_transcribe_video` | Transcrição de fala para texto |

### Integração com Bridge

| Ferramenta | Descrição |
|--------|------|
| `sd_generate` | Gera imagem no SD WebUI |
| `sd_list_models` | Lista modelos do SD WebUI |
| `comfyui_generate` | Gera imagem no ComfyUI |
| `comfyui_generate_json` | Executa workflow JSON do ComfyUI |

### Biblioteca de prompts

| Ferramenta | Descrição |
|--------|------|
| `create_prompt` | Cria prompt |
| `search_prompts` | Busca prompts |
| `get_prompt` | Obtém prompt |
| `update_prompt` | Atualiza prompt |

### Configurações

| Ferramenta | Descrição |
|--------|------|
| `settings_get_schema` | Obtém o schema das configurações |
| `settings_get` | Obtém valor de configuração |
| `settings_set` | Atualiza valor de configuração |
| `secrets_status` | Verifica estado da chave de criptografia |

### Mecanismo de segurança do agente

| Ferramenta | Descrição |
|--------|------|
| `agent_kill` / `agent_resume` | Controle do Kill Switch |
| `agent_status` | Status do mecanismo de segurança |
| `agent_journal` | Busca no journal de operações |
| `agent_undo` | Desfazer operação |
| `agent_circuit_breaker_status` | Estado do Circuit Breaker |
| `agent_budget_status` | Estado do tracker de orçamento |
| `agent_scope_set` | Configuração de escopo |
| `agent_anomaly_status` | Status de detecção de anomalias |

### Outras

| Ferramenta | Descrição |
|--------|------|
| `find_duplicates` | Detecção de arquivos duplicados |
| `search_chat_logs` | Busca em logs de chat |
| `search_md_files` | Busca em arquivos Markdown |
| `help_search` | Busca na documentação de ajuda |
| `share_to_bluesky` | Postagem no Bluesky |
| `list_trophies` | Lista troféus |
| `get_monthly_report` | Relatório mensal |

## Variáveis de ambiente

| Variável | Descrição | Padrão |
|------|------|----------|
| `YU_BASE_URL` | URL do servidor | `http://localhost:5000` |
| `YU_API_KEY` | API Key | (obrigatório) |
| `YU_DEBUG_MODE` | Ativar ferramentas de depuração | `0` |

Definindo `YU_DEBUG_MODE=1`, são adicionadas ferramentas exclusivas de depuração, como query direta ao DB e health check.

## Troubleshooting

### Não consegue conectar

1. Verifique se o YU AI Manager está em execução
2. Confira se a API Key está correta (com prefixo `sk_`)
3. Verifique se `YU_BASE_URL` está correto
4. Para conexão pela LAN, verifique se o LAN Access está ativado

### Ferramenta não encontrada

- Quando a Extension está desativada, suas ferramentas também ficam indisponíveis
- Verifique o estado de ativação com `list_extensions`

### Timeout

- Buscas e operações em lote em bibliotecas grandes podem demorar
- Limite o número de resultados com o parâmetro `limit`
