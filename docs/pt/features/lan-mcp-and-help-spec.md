# Especificação de Endpoint de Acesso MCP em LAN & Help

**Versão de implementação**: 3.1.0
**Documentação relacionada**: `docs/en/features/mcp-integration-guide.md`
**Arquivos relacionados**: `routes/mcp_endpoint.py`, `routes/help.py`, `mcp_server/help_tools.py`

---

## Visão Geral

1. **Acesso MCP em LAN** — Permita clientes MCP em LAN conectarem ao endpoint de MCP por endereço IP quando modo de compartilhamento em LAN está habilitado
2. **Endpoint `/help`** — Forneça um manual web built-in para a aplicação (também publicado como recurso MCP)

---

## 1. Acesso MCP em LAN

### 1-1. Arquitetura

Sobre a LAN, clientes MCP conectam diretamente ao endpoint `/mcp` do YU AI Manager usando transporte HTTP/SSE.

### 1-2. Endpoint MCP SSE

| Item | Detalhes |
|------|------|
| Endpoint | `/mcp` (SSE + postagem de mensagem) |
| Transporte | HTTP + Server-Sent Events (SSE) |
| Autenticação | Não requerida de localhost. Chave API requerida de IPs em LAN |

### 1-3. Autenticação por Chave de API

O mecanismo existente de gerenciamento de chave de API (`/api/keys`) é reutilizado.

### 1-4. UI de Configurações

Um snippet de configuração de conexão MCP em LAN (versão HTTP) é adicionado à aba Settings > API Keys.

---

## 2. Endpoint `/help`

### 2-1. Princípios de Design

- Totalmente offline
- Duplo propósito como recurso MCP
- Nenhuma autenticação requerida

### 2-2. Endpoints

| Endpoint | Conteúdo |
|----------------|------|
| `GET /help` | Página superior de manual |
| `GET /help/<section>` | Página específica de seção |
| `GET /api/help/toc` | Índice de conteúdo JSON |
| `GET /api/help/content/<section>` | Corpo de seção JSON |

### 2-3. Ferramentas MCP

- `help_search`: Pesquisa de palavra-chave
- `help_get_section`: Recuperação de seção
