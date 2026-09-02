# Yu AI Manager — Especificação Geral

> **Público-alvo**: Agentes de IA como Claude Desktop  
> **Versão**: v4.91.15  
> **Atualizado em**: 2026-04-19

---

## Sumário

1. [Visão Geral do Projeto](#1-visão-geral-do-projeto)
2. [Pilha Tecnológica](#2-pilha-tecnológica)
3. [Visão Geral da Arquitetura](#3-visão-geral-da-arquitetura)
4. [Autenticação e Segurança](#4-autenticação-e-segurança)
5. [Endpoints da API REST](#5-endpoints-da-api-rest)
6. [Servidor MCP](#6-servidor-mcp)
7. [Eventos SSE](#7-eventos-sse)
8. [Esquema de Banco de Dados](#8-esquema-de-banco-de-dados)
9. [Extensões](#9-extensões)
10. [Configuração (config.json)](#10-configuração-configjson)
11. [Estrutura de Arquivos](#11-estrutura-de-arquivos)
12. [Convenções de Desenvolvimento](#12-convenções-de-desenvolvimento)

---

## 1. Visão Geral do Projeto

**Yu AI Manager** é um sistema de gerenciamento local de biblioteca para imagens, vídeos, áudio e texto gerados por IA.  
A filosofia de design é "edge-first" e independente de nuvem, priorizando a conclusão local/LAN.

### Funcionalidades Principais

| Funcionalidade | Descrição |
|-------|------|
| Gerenciamento de Biblioteca | Varredura, marcação e busca de imagens/vídeos/áudio/texto |
| Extração de Metadados | Extração automática de parâmetros de geração de A1111 / ComfyUI / NovelAI |
| Análise de IA | Análise de imagens por Claude / OpenAI / Ollama / Hailo VLM |
| Busca Semântica | Busca de significado através de CLIP (ONNX/CoreML) + Hailo |
| Integração Bridge | Solicitações de geração para Stable Diffusion / ComfyUI / NovelAI |
| LLM Router | Roteamento integrado para backends compatíveis com Ollama / OpenAI |
| Segurança do Agente | Mecanismos de segurança como Kill Switch / Circuit Breaker / Approval Gate |
| Colaboração em LAN | Descoberta automática via mDNS + compartilhamento entre pares |
| Servidor MCP | 180+ ferramentas operáveis diretamente do Claude Desktop |

---

## 2. Pilha Tecnológica

| Camada | Tecnologia |
|---------|------|
| Backend | Python 3.11+ / Quart (async) / Hypercorn |
| Banco de Dados | SQLite3 (busca de texto completo FTS5 + BLOB comprimido com zstd) |
| Frontend | TypeScript + build Vite |
| Desktop | Tauri (Rust) |
| MCP | FastMCP (Anthropic MCP Server) |
| LLM | Claude API / OpenAI API / Ollama / Hailo VLM |
| Inferência | ONNX Runtime / CoreML / Hailo Runtime |
| Gerenciador de Pacotes | Python: `uv pip` / Node.js: `pnpm` |

### Convenção de Portas

- `5000–5099`: Faixa de portas reservadas da aplicação (não alterar)
- `5100+`: Uso em testes/debug (`scripts/find_port.py` obtém porta vaga automaticamente)

---

## 3. Visão Geral da Arquitetura

```
┌──────────────────────────────────────────────────┐
│  Camada do Cliente                               │
│  ├─ Interface Web (TypeScript / Tauri)           │
│  ├─ Claude Desktop (MCP)                         │
│  └─ Ferramentas Externas (Chave API / Par LAN)   │
├──────────────────────────────────────────────────┤
│  Camada de Autenticação (auth_chain.py)          │
│  ├─ PIN / QuickLock (bloqueio do chefe)          │
│  ├─ Chave de API (Bearer / escopos)              │
│  └─ Confiança de Par LAN (verificação mDNS)      │
├──────────────────────────────────────────────────┤
│  Camada de API                                   │
│  ├─ API REST (235+ endpoints / Blueprint Quart)  │
│  ├─ Fluxo SSE (/api/events/stream)               │
│  └─ Servidor MCP (180+ ferramentas)              │
├──────────────────────────────────────────────────┤
│  Camada de Serviço                               │
│  ├─ TagDB (SQLite / esquema v53)                 │
│  ├─ Barramento de Eventos (transmissor SSE)      │
│  ├─ LLM Router (integração de múltiplos backends)│
│  ├─ Mecanismo de Análise (Claude/OpenAI/Ollama)  │
│  ├─ Extensões (47 built-in)                      │
│  └─ Serviços de Arquivo (varredura/entrega)      │
├──────────────────────────────────────────────────┤
│  Camada de Segurança do Agente                   │
│  ├─ Kill Switch          ├─ Rastreador de Orçamento │
│  ├─ Interruptor de Circuito ├─ Portão de Aprovação  │
│  ├─ Cerca de Escopo      ├─ Mecanismo de Desfazer   │
│  ├─ Detector de Anomalias └─ Bureau de Auditoria    │
└──────────────────────────────────────────────────┘
```

### Direção de Dependência de Módulos

```
routes/ → core/services_core/ → core/tagdb_core/ → SQLite
routes/ → core/web/ (autenticação)
mcp_server/ → routes/ via ou chamadas diretas de núcleo
extensions/ → core/extensions_core/ (gerenciamento de ciclo de vida)
```

---

## 4. Autenticação e Segurança

### Cadeia de Autenticação (core/web/auth_chain.py)

Avaliado em seguinte ordem a cada solicitação:

1. **Bypass de Arquivo Estático** — `/static/`, `/favicon.ico`, `/help/*`
2. **Bypass MCP** — `/mcp` (autenticação do MCP em si)
3. **Bypass de LLM Router** — `/v1/` (apenas em tempo de loopback)
4. **Bypass de Compartilhamento LAN** — `/s/<token>` (token de compartilhamento)
5. **Confiança de Par LAN** — pares verificados por mDNS não requerem PIN
6. **Autenticação de Chave de API** — `Authorization: Bearer <key>` (verificação de escopo)
7. **Verificação de QuickLock** — quando bloqueado, apenas `/api/lock/unlock` é permitido
8. **Verificação de PIN** — autenticação de sessão do navegador

### Escopos de Chave de API

| Escopo | Permissão |
|---------|------|
| `read` | Leitura geral |
| `write` | Gravação de arquivo/configuração |
| `tag.write` | Adicionar/remover tags |
| `collection.write` | Gerenciamento de coleções |
| `annotate` | Anotação |
| `scan` | Operações de varredura |
| `admin` | Administrador (todas as operações) |

### QuickLock / Modo Boss

- PIN hash via PBKDF2-SHA256 (600k iterations)
- Limite de taxa: bloqueio de 60 segundos após 5 falhas
- `/api/lock/status` verifica estado do bloqueio (sem autenticação)
- `/api/lock/unlock` desbloqueia (PIN obrigatório)

### Gerenciamento de Segredos

- Integração com 1Password (`op://vault/item/field` referência)
- Integração com Bitwarden
- Valores de configuração criptografados com Fernet (`enc:...` prefixo)

---

*Este documento está armazenado em `docs/ja/SPEC.md`. Se o conteúdo ficar desatualizado, consulte o código e git log.*
