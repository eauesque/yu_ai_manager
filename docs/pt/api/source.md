# API de Navegação de Código-Fonte

Uma API somente leitura para navegar no código-fonte do projeto.
É projetada para que ferramentas MCP e agentes de IA externos possam visualizar e pesquisar o codebase com segurança.

## Modelo de Segurança

Três camadas de defesa garantem segurança:

### 1. Normalização de Caminho (Prevenção de Traversal)

- Todos os caminhos são normalizados com `os.path.realpath()` e verificados contra a raiz do projeto através de correspondência de prefixo.
- Ataques de traversal como `../../etc/passwd` ou `../../../Windows/System32` são bloqueados.
- Injeção de byte nulo (`\x00`) também é detectada e rejeitada.

### 2. Lista Branca de Extensão

Extensões de arquivo permitidas para leitura:

| Categoria | Extensões |
|----------|-----------|
| Python | `.py` |
| TypeScript / JavaScript | `.ts`, `.js`, `.mjs`, `.tsx`, `.jsx` |
| Web | `.html`, `.css`, `.scss` |
| Configuração | `.json`, `.yaml`, `.yml`, `.toml`, `.cfg`, `.ini` |
| Documentação | `.md`, `.txt`, `.rst` |
| Scripts | `.sh`, `.bat`, `.cmd`, `.ps1` |
| Outro | `.sql`, `.gitignore`, `.gitattributes`, `.editorconfig` |

Os seguintes arquivos sem extensão são especialmente permitidos: `Dockerfile`, `Makefile`, `Procfile`, `VERSION`, `LICENSE`, `CHANGELOG`, `TODO`

### 3. Lista de Bloqueio de Arquivo Sensível

Arquivos que correspondem aos seguintes padrões são rejeitados:

| Padrão | Razão |
|---------|--------|
| `config.json`, `config_*.json` | Dados de autenticação como PIN e API Key |
| `*.env`, `.env.*` | Variáveis de ambiente (segredos) |
| `secret.salt`, `*.key`, `*.pem`, `*.cert` | Chaves de criptografia e certificados |
| `credentials*`, `*token*`, `*secret*` | Dados de autenticação |
| `*.db`, `*.sqlite*` | Arquivos de banco de dados |
| `pnpm-lock.yaml`, `package-lock.json`, etc. | Arquivos de lock (grandes) |
| Imagem, vídeo, fonte e arquivos de modelo | Arquivos binários |

### Diretórios Bloqueados

`.git`, `__pycache__`, `node_modules`, `venv`, `dist`, `data`, `backups`, `screenshots`, `reports`, `src-tauri`

### Limites de Leitura

| Item | Limite |
|------|-------|
| Tamanho de arquivo | 1 MB |
| Linhas por leitura | 2,000 |
| Profundidade de traversal | 6 |
| Resultados de busca | 50 |

---

## Endpoints

### GET /api/source/tree

Recuperar uma árvore de diretório.

#### Parâmetros

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|---------|-------------|
| `path` | string | `""` (root) | Caminho relativo |
| `depth` | int | `3` | Profundidade de traversal (1-6) |

#### Resposta

```json
{
  "ok": true,
  "root": ".",
  "depth": 3,
  "entries": [
    {
      "name": "core",
      "type": "dir",
      "path": "core",
      "children": [
        {
          "name": "source_core",
          "type": "dir",
          "path": "core/source_core",
          "children": [
            {
              "name": "source_browser.py",
              "type": "file",
              "path": "core/source_core/source_browser.py",
              "size": 8234
            }
          ]
        }
      ]
    },
    {
      "name": "web_ui.py",
      "type": "file",
      "path": "web_ui.py",
      "size": 3456
    }
  ]
}
```

- Diretórios aparecem primeiro, seguidos por arquivos (classificados por nome).
- `size` é em bytes (apenas arquivos).
- `children` é omitido quando o traversal atinge a `depth` especificada.

---

### GET /api/source/read

Ler conteúdo de arquivo com números de linha.

#### Parâmetros

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|---------|-------------|
| `path` | string | — (obrigatório) | Caminho de arquivo relativo |
| `offset` | int | `0` | Linha inicial (baseada em 0) |
| `limit` | int | `2000` | Número máximo de linhas |

#### Resposta

```json
{
  "ok": true,
  "path": "core/source_core/source_browser.py",
  "total_lines": 250,
  "offset": 0,
  "limit": 2000,
  "content": "    1\t\"\"\"Source code browser...\n    2\t\n    3\timport os\n..."
}
```

- `content` usa formato `{line_number}\t{line_content}`.
- Use `offset` + `limit` para paginar através de arquivos longos.

#### Exemplos de Erro

```json
{
  "ok": false,
  "error": "This file is not eligible for reading"
}
```

```json
{
  "ok": false,
  "error": "Access outside the project root is prohibited"
}
```

---

### GET /api/source/search

Buscar no código-fonte por texto.

#### Parâmetros

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|------|---------|-------------|
| `q` | string | — (obrigatório) | Texto de busca (mínimo 2 caracteres) |
| `glob` | string | `""` (todos os arquivos) | Filtro de nome de arquivo (ex: `*.py`) |
| `limit` | int | `30` | Número máximo de resultados (1-50) |

#### Resposta

```json
{
  "ok": true,
  "query": "def source_tree",
  "glob": "*.py",
  "total": 2,
  "results": [
    {
      "file": "core/source_core/source_browser.py",
      "line": 120,
      "text": "def source_tree("
    },
    {
      "file": "routes/source_api.py",
      "line": 15,
      "text": "    result = source_tree(rel_path, depth_int)"
    }
  ]
}
```

- A busca é insensível a maiúsculas/minúsculas.
- `text` é truncado para um máximo de 200 caracteres.

---

## Ferramentas MCP

| Ferramenta | Descrição | Parâmetros Chave |
|------|-------------|----------------|
| `source_tree` | Exibir árvore de diretório | `path`: str = '', `depth`: int = 3 |
| `source_read` | Ler conteúdo de arquivo | `path`: str (obrigatório), `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | Buscar código-fonte por texto | `query`: str (obrigatório), `glob`: str = '', `limit`: int = 30 |

### Exemplos de Uso com MCP

```
# Ver a estrutura do projeto
source_tree(path="", depth=2)

# Ler um arquivo específico
source_read(path="core/source_core/source_browser.py")

# Buscar no codebase
source_search(query="def register_blueprints", glob="*.py")
```

### Escopo & Limitação de Taxa

- **Scope Fence**: Disponível no escopo `read_only` (permitido em todas as presets)
- **Budget Tracker**: Categoria `read` (sem limitação de taxa)
- **HITL Gate**: Nível 0 (sem aprovação obrigatória)

---

## Arquivos de Implementação

| Arquivo | Papel |
|------|------|
| `core/source_core/source_browser.py` | Camada de segurança + lógica de negócio |
| `routes/source_api.py` | Endpoints Flask API (Blueprint) |
| `mcp_server/source_tools.py` | Registro de ferramenta MCP |
