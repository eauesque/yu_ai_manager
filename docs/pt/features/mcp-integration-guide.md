# Guia de Integração MCP — Operando YU AI Manager a partir de um LLM

YU AI Manager possui um servidor **MCP (Model Context Protocol)** built-in que permite operações de LLM na biblioteca de imagens usando linguagem natural.

Não há UI de chat built-in nesta aplicação.
Para interagir com ela usando linguagem natural, conecte a partir do cliente MCP compatível de sua preferência.

---

## O que é MCP?

MCP (Model Context Protocol) é um protocolo padrão que habilita aplicações de LLM a acessar ferramentas e fontes de dados externas.
YU AI Manager atua como servidor MCP, e clientes de LLM (como Claude Desktop) conectam a ele, traduzindo instruções em linguagem natural em operações de API.

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

## Clientes MCP Suportados

Os seguintes são clientes representativos compatíveis com MCP. Os passos de configuração são similares para todos.

| Cliente | Provedor | Recursos |
|---|---|---|
| **Claude Desktop** | Anthropic | Acesso direto a Claude. Suporte nativo de MCP |
| **Claude Code** | Anthropic | Cliente baseado em terminal para desenvolvedores |
| **Cline** | Extensão VS Code | Integração de editor. Suporte a multi-LLM |
| **Open WebUI** | Open Source | Auto-hospedado. Pode ser combinado com LLMs locais como Ollama |

Nota: O número de clientes compatíveis com MCP está crescendo rapidamente.
Qualquer cliente que suporte transporte stdio deve ser capaz de conectar.

## Configuração

### 1. Inicie YU AI Manager

O servidor MCP opera através da API do Web server, então YU AI Manager deve estar em execução primeiro.

```bash
python web_ui.py --db ./tags.db --port 5000
```

### 2. Emita uma Chave de API (Recomendado)

Emitir uma chave de API permite ao servidor MCP contornar autenticação de PIN ao usar compartilhamento em LAN ou autenticação de PIN.

As chaves de API podem ser emitidas em Settings -> API Keys.

Uma chave de API não é necessária ao executar sem PIN (`config_test.json`).

### 3. Adicione Configurações de Conexão ao Seu Cliente MCP

#### Claude Desktop

Edite `claude_desktop_config.json`:

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

Adicione configurações a `.mcp.json` na raiz do projeto, ou use comando `claude mcp add`:

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

Entre a mesma informação através de MCP Settings do Cline.

#### Variáveis de Ambiente

| Variável | Requerida | Padrão | Descrição |
|---|---|---|---|
| `YU_BASE_URL` | - | `http://localhost:5000` | URL do web server |
| `YU_API_KEY` | - | Nenhuma | Chave de API (requerida em ambientes PIN) |
| `YU_DEBUG_MODE` | - | `0` | Defina para `1` para adicionar ferramentas de debug |

## Exemplos de Uso

Uma vez conectado, você pode operar a biblioteca de imagens dando instruções em linguagem natural ao LLM.

### Pesquisar e Navegar

```
"Mostre-me as 20 imagens mais recentes de meninas com olhos azuis"
"Filtrar para apenas imagens geradas com NovelAI"
"Mostrar-me estatísticas para imagens digitalizadas na semana passada"
```

### Organizar e Classificar

```
"Dê a essas 10 imagens uma classificação de 5 estrelas"
"Adicione imagens marcadas com 'landscape' para a 'Scenery Collection'"
"Liste todas as imagens com classificação de 3 ou abaixo"
```

### Análise e Anotação

```
"Pontue a qualidade de imagens adicionadas recentemente e salve em anotações"
"Mostrar-me todas as anotações para a ID de imagem 12345"
"Procurar por anotações com agent de origem:claude"
```

### Operações de Scan

```
"Digitalize para novas imagens"
"Verificar o progresso da digitalização"
"Mostrar-me erros de digitalização"
```

## Ferramentas Disponíveis

O servidor MCP expõe as seguintes ferramentas ao LLM:

### Pesquisar e Navegar (4 ferramentas)

| Nome da Ferramenta | Descrição |
|---|---|
| `search_images` | Pesquisar imagens por tags, data, formato, classificação, etc. |
| `get_image_detail` | Recuperar todos os metadados para uma imagem |
| `get_library_stats` | Estatísticas da biblioteca (contagem de arquivo, contagem de tag, distribuição de origem, etc.) |
| `find_similar` | Pesquisar imagens similares usando hash perceptual |

### Coleções (4 ferramentas)

| Nome da Ferramenta | Descrição |
|---|---|
| `list_collections` | Listar coleções |
| `create_collection` | Criar uma coleção |
| `delete_collection` | Deletar uma coleção |
| `add_to_collection` / `remove_from_collection` | Adicionar/remover imagens |

### Tags e Classificações (2 ferramentas)

| Nome da Ferramenta | Descrição |
|---|---|
| `rate_images` | Definir classificações de estrela para múltiplas imagens por vez |
| `set_tags` | Adicionar/remover tags para múltiplas imagens por vez |

### Anotações (4 ferramentas)

| Nome da Ferramenta | Descrição |
|---|---|
| `set_annotations` | Salvar resultados de análise IA como anotações |
| `get_annotations` | Recuperar anotações para uma imagem |
| `search_annotations` | Pesquisar anotações através de origem, chave e confiança |
| `delete_annotations` | Deletar anotações |

### Scan (3 ferramentas)

| Nome da Ferramenta | Descrição |
|---|---|
| `trigger_scan` | Iniciar um scan |
| `get_scan_status` | Verificar progresso de scan |
| `get_scan_errors` | Listar erros de scan |

### Outro

As ferramentas para biblioteca de prompt, backup e gerenciamento de cliente MCP também são incluídas.

## FAQ

### P: Não há recurso de chat na aplicação?

R: Não há. YU AI Manager se especializa em gerenciamento de metadados de imagem, e a interface conversacional de IA é delegada a clientes compatíveis com MCP. Você pode executar todas as operações via linguagem natural executando Claude Desktop ou cliente similar ao lado.

### P: Qual LLM devo usar?

R: Qualquer LLM funciona, contanto que o cliente MCP o suporte.
Para tratamento confiável de argumentos de ferramenta, modelos em larga escala como Claude ou GPT-4 tendem a executar mais consistentemente.

### P: Posso usar um LLM local?

R: Sim, LLMs locais funcionam com combinações como Open WebUI + Ollama, contanto que suportem MCP. No entanto, a precisão de chamada de ferramenta depende das capacidades do modelo.

### P: YU AI Manager também tem um recurso de cliente MCP?

R: A extensão `MCP Client` (na página Tools) conecta YU AI Manager a **outros servidores MCP**. Este guia descreve a direção oposta: LLM externo -> YU AI Manager.
