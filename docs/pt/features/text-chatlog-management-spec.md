# Especificação de Gerenciamento de Texto e Chatlog do YU AI Manager

Criado: 2026-03-01
Versão alvo: TBD (timing de implementação sob consideração)

## Visão Geral

Três recursos são adicionados ao YU AI Manager:

- **MD Viewer** — Visualização local de arquivos Markdown
- **Chatlog Management** — Importar, visualizar e pesquisar logs de Claude/ChatGPT/Open WebUI
- **Full-Text Search** — Pesquisa entre conteúdos alimentada por FTS5

A filosofia de design é a mesma de recursos existentes: "totalmente local, sem dependência de nuvem."

---

## 1. MD Viewer

### Propósito

Visualizadores de arquivo do SO oferecem renderização pobre de Markdown. Este recurso traz visualização de Markdown inteiramente dentro do YU AI Manager, servindo como ferramenta diária de referência para notas de desenvolvimento, documentos de design e listas TODO.

### Alvos de Scan

- Extensões: `.md`, `.markdown`
- Raízes de scan existentes são reutilizadas
- Excluído: arquivos sob `.git/` e `node_modules/`

### Schema de DB

```sql
CREATE TABLE md_files (
    id          INTEGER PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE,
    mtime       INTEGER NOT NULL,
    size        INTEGER NOT NULL,
    title       TEXT,        -- Extraído do primeiro # heading
    content     TEXT,        -- Texto bruto Markdown
    is_deleted  INTEGER NOT NULL DEFAULT 0,
    indexed_at  INTEGER
);

CREATE VIRTUAL TABLE md_files_fts USING fts5(
    title,
    content,
    content='md_files',
    content_rowid='id'
);
```

### UI do Viewer

- Integrado ao modal existente ou painel lateral
- Renderização: marked.js (agrupado localmente, sem CDN)
- Code blocks: destaque de sintaxe (highlight.js)
- Um botão toggle de visualização de texto bruto é fornecido

### Suporte MCP

- `search_md_files(query, path_filter)` -> lista de arquivo
- `get_md_content(file_id)` -> texto bruto

---

## 2. Chatlog Management

### Propósito

Este recurso serve como motor de pesquisa para histórico de desenvolvimento, tornando possível encontrar discussões passadas usando palavras-chave vagas. Exemplos: "Onde foi aquela discussão de bug?" ou "Qual era a razão para aquela decisão de design?"

### Formatos Suportados

| Serviço | Formato de Exportação | Como Obter |
|---|---|---|
| Claude | conversations.json | Settings -> Export Data |
| ChatGPT | conversations.json | Settings -> Export Data |
| Open WebUI | Exportação JSON | Chat History -> Export |

### Schema de DB

```sql
-- Por conversa
CREATE TABLE chat_conversations (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,  -- 'claude' / 'chatgpt' / 'openwebui'
    external_id   TEXT,           -- ID de Conversa do serviço original
    title         TEXT,
    model         TEXT,           -- Nome de modelo usado
    created_at    INTEGER,
    updated_at    INTEGER,
    message_count INTEGER,
    imported_at   INTEGER NOT NULL
);

-- Por mensagem
CREATE TABLE chat_messages (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id),
    role            TEXT NOT NULL,  -- 'user' / 'assistant' / 'system'
    content         TEXT NOT NULL,
    created_at      INTEGER,
    seq             INTEGER         -- Ordem dentro da conversa
);

-- FTS5 full-text search
CREATE VIRTUAL TABLE chat_messages_fts USING fts5(
    content,
    content='chat_messages',
    content_rowid='id',
    tokenize='unicode61'
);
```

### Importador

O JSON de cada serviço é convertido para um formato intermediário comum e inserido em DB.

**Estrutura JSON do Claude (campos principais):**

```json
{
  "uuid": "...",
  "name": "Título de conversa",
  "created_at": "2026-01-01T00:00:00Z",
  "chat_messages": [
    {"role": "human", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

**Estrutura JSON do ChatGPT (campos principais):**

```json
{
  "id": "...",
  "title": "Título de conversa",
  "create_time": 1234567890,
  "mapping": {
    "node_id": {
      "message": {
        "author": {"role": "user"},
        "content": {"parts": ["..."]}
      }
    }
  }
}
```

**Estrutura JSON do Open WebUI:**

- Segue o formato API compatível com OpenAI
- Array de mensagens com role/content

### UI do Importador

- Uma seção de importação é adicionada à página de configurações
- Arquivos JSON podem ser soltos via drag-and-drop ou selecionados com um file picker
- Conversas previamente importadas são deduplicadas por `external_id` (idempotente)
- Um sumário de importação (contagem adicionada e contagem pulada) é exibido

### UI do Viewer

- Página de lista de conversa (título, data, modelo, origem)
- Página de detalhe de conversa (exibição com turno com color coding baseado em role)
- Filtros por nome de modelo, origem e intervalo de data
- Imagens anexadas armazenam apenas referências de caminho (sem cópias de arquivo)

### Suporte MCP

- `search_chat_logs(query, source, model, date_from, date_to)` -> lista de conversa
- `get_conversation(conversation_id)` -> lista de mensagem
- `import_chat_log(source, json_path)` -> executar importação

---

## 3. Full-Text Search

### Alvos

- Arquivos MD (`md_files_fts`)
- Chat logs (`chat_messages_fts`)
- Biblioteca de prompt existente (`prompt_library_fts`, já implementada)

### UI de Pesquisa

- Estenda a barra de pesquisa existente ou forneça uma página de pesquisa de texto dedicada
- Toggle de alvos de pesquisa (MD / chatlog / biblioteca de prompt)
- Resultados classificados por score BM25
- Exibição de snippet de hit (~50 caracteres de contexto ao redor)

### API de Pesquisa

```
GET /api/text-search?q=keyword&target=md,chat,prompt&limit=20
```

Resposta:

```json
{
  "results": [
    {
      "type": "chat",
      "conversation_id": 123,
      "title": "Título de conversa",
      "snippet": "...texto ao redor do hit...",
      "score": 0.95,
      "date": "2026-01-01"
    }
  ]
}
```

---

## Prioridade de Implementação

1. MD Viewer (custo de implementação baixo, valor imediato alto)
2. Importador de Chatlog (suporte Claude/ChatGPT primeiro)
3. Visualizador de Chatlog
4. Suporte Open WebUI
5. UI de pesquisa de conteúdo cruzado

---

## Extensões Futuras

- Importação periódica automática de chatlog (coloque arquivos de exportação em uma pasta observada para ingestão automática)
- Linke prompts de geração de imagem a discussões de chatlog que os produziram
- Sumarização automática de chatlog e tagging via Ollama

---

## Notas

- Padrões FTS5 podem ser reutilizados da implementação existente `prompt_library_fts`
- marked.js é agrupado localmente em vez de carregado de um CDN (seguindo a filosofia de design apenas local)
- Imagens anexadas em chatlogs (imagens geradas DALL-E, etc.) não são salvas localmente porque suas URLs expiram
