# Manual de Depuração

Este é um manual abrangente com as informações necessárias para depurar o YU AI Manager.
Serve como guia para que desenvolvedores e agentes de IA possam investigar e corrigir bugs com eficiência.

---

## Índice

1. [Inicialização do servidor](#inicialização-do-servidor)
2. [Log de depuração](#log-de-depuração)
3. [Execução de testes](#execução-de-testes)
4. [Depuração do DB](#depuração-do-db)
5. [Bypass de autenticação e testes](#bypass-de-autenticação-e-testes)
6. [Depuração MCP](#depuração-mcp)
7. [Depuração do front-end](#depuração-do-front-end)
8. [Lista de variáveis de ambiente](#lista-de-variáveis-de-ambiente)
9. [Erros comuns e soluções](#erros-comuns-e-soluções)
10. [Depuração de desempenho](#depuração-de-desempenho)

---

## Inicialização do servidor

### Para verificação (recomendado)

Inicia sem PIN e com bind local. É a forma básica para testes e depuração.

```bash
source venv/Scripts/activate  # Windows Git Bash
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

Se `config_test.json` não existir, crie-o com o seguinte conteúdo:

```json
{
  "scan_roots": [],
  "server": {
    "host": "127.0.0.1",
    "port": 5100,
    "lan": false
  },
  "extract_a1111": true,
  "extract_comfyui": true,
  "lowercase_tags": true,
  "compute_hash": false,
  "enable_fts": true,
  "extensions": {}
}
```

### Equivalente a produção (publicação em LAN)

```bash
python web_ui.py --db ./tags.db --host 0.0.0.0 --port 5000 --pin 1234
```

> **Atenção**: ao fazer bind em `0.0.0.0`, o PIN é obrigatório. A partir da v4.8.1, a flag `--debug` é ignorada ao publicar na LAN (para prevenir vazamento de stack trace).

### Regras de seleção de portas

5100 → 5200 → 5300 → em seguida em incrementos de 100. Verifique antes de iniciar:

```bash
# Windows
netstat -ano | grep :5100

# Linux/macOS
ss -tlnp | grep :5100
```

### Lista de opções da CLI

| Opção | Tipo | Padrão | Descrição |
|-----------|-----|----------|------|
| `--db` | path | `data/tags.db` | Caminho do arquivo SQLite DB |
| `--config` | path | `config.json` | Caminho do arquivo de configuração |
| `--host` | str | `127.0.0.1` | Endereço de bind |
| `--port` | int | 5000 | Porta de bind |
| `--lan` | flag | - | Faz bind em `0.0.0.0` (publicação em LAN) |
| `--pin` | str | - | Ativa a autenticação por PIN |
| `--debug` | flag | - | Ativa o modo de depuração do Quart |
| `--debug-log` | `on`/`off` | - | Ativa/desativa log de depuração estruturado |
| `--debug-log-file` | path | `logs/debug.log` | Destino de saída do arquivo de log |
| `--debug-log-max-mb` | int | 10 | Tamanho de rotação do arquivo de log (MB) |
| `--debug-log-backups` | int | 5 | Número de gerações de backup de log |
| `--debug-log-stdout` | `on`/`off` | `on` | Também emite log para stderr |
| `--allow-restart` | flag | - | Ativa `/api/server/restart` |
| `--trusted-proxy-auth` | flag | - | Ativa autenticação Trusted Proxy |
| `--profile` | str | - | Nome do perfil de inicialização |

### launch-args.txt

Ao colocar `launch-args.txt` na raiz do projeto, os argumentos nele descritos são carregados automaticamente na inicialização. Os argumentos da CLI têm prioridade.

---

## Log de depuração

### Ativação

```bash
# Ativar pela CLI
python web_ui.py --db ./tags.db --debug-log on

# Ativar por variável de ambiente
export TAGDB_DEBUG=1
python web_ui.py --db ./tags.db
```

### Formato do log

Log de depuração estruturado (função `dlog()` em `core/infra_core/debug_log.py`):

```
[DEBUG] 2026-03-15 12:34:56 | scan:prepare | counting_start | root=/path/to/dir, recursive=True
```

Formato: `[DEBUG] timestamp | source | nome do evento | key=value, ...`

### Monitoramento em tempo real

```bash
# Tail do arquivo
tail -f logs/debug.log

# Obter via API
curl http://127.0.0.1:5100/api/debug/logs

# Streaming SSE
curl -N "http://127.0.0.1:5100/api/debug/logs?stream=1"
```

### Ring buffer de log

Os logs em execução também são armazenados em um ring buffer em memória (máximo 1000 entradas). Como eles somem ao reiniciar o servidor, use o log em arquivo quando for preciso persistir.

---

## Execução de testes

### Teste unitário

```bash
source venv/Scripts/activate

# Executar todos os testes
python -m pytest tests/test_basic.py -v

# Somente um teste específico
python -m pytest tests/test_basic.py::TestImports -v

# Parar imediatamente em falha
python -m pytest tests/test_basic.py -x
```

### Teste de integração da API

```bash
python -m pytest tests/api/ -v
```

### Teste de navegador Playwright

```bash
# 1. Iniciar o servidor de verificação
python web_ui.py --db ./tags.db --config config_test.json --port 5100 &

# 2. Executar o teste
TARGET_URL=http://localhost:5100 python -m pytest tests/test_webui_browser.py -v

# Teste de busca cruzada
TARGET_URL=http://localhost:5100 python -m pytest tests/test_cross_search_browser.py -v
```

### Saída de teste

- Screenshots: `screenshots/`
- Relatórios: `reports/`

### Política de testes

1. Execute os testes primeiro para entender as falhas atuais
2. Verifique os screenshots dos testes que falharam
3. Mantenha as correções no mínimo de alterações
4. Após corrigir, teste novamente para confirmar

---

## Depuração do DB

### Verificar a versão do schema

```bash
python -c "
import sqlite3
con = sqlite3.connect('data/tags.db')
v = con.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]
print(f'Schema version: {v}')
"
```

### Verificação de integridade do DB

```bash
python db_health.py --db ./tags.db
```

Verifica a existência de tabelas, a versão do schema, restrições de chave estrangeira e índices.

### Execução de depuração de queries SQL

Disponível apenas quando iniciado com `YU_DEBUG_MODE=1`.

```bash
# Via API
curl -X POST http://127.0.0.1:5100/api/debug/query \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"sql":"SELECT COUNT(*) as cnt FROM files WHERE is_deleted=0"}'
```

> **Atenção**: a partir da v4.8.1, apenas instruções SELECT são permitidas. ATTACH, PRAGMA, INSERT etc. são rejeitados.

### Queries de investigação usadas com frequência

```sql
-- Número de arquivos (por source)
SELECT meta_source, COUNT(*) as cnt FROM files WHERE is_deleted=0 GROUP BY meta_source;

-- Ranking de uso de modelos
SELECT model_name, COUNT(*) as cnt FROM templates GROUP BY model_name ORDER BY cnt DESC LIMIT 20;

-- Tags órfãs
SELECT t.id, t.name FROM tags t LEFT JOIN file_tags ft ON t.id=ft.tag_id WHERE ft.tag_id IS NULL;

-- Detecção de paths duplicados
SELECT path, COUNT(*) as cnt FROM files GROUP BY path HAVING cnt > 1;

-- Visão geral de anotações
SELECT source, key, COUNT(*), AVG(confidence) FROM file_annotations GROUP BY source, key;
```

### Uso diferenciado das conexões de DB

| Função | Uso | Quando usar |
|------|------|---------|
| `get_readonly_db()` | Somente leitura | API GET, busca, referência de miniaturas, estatísticas |
| `get_db()` | Gravação permitida (com Row factory) | API POST/PUT/DELETE |
| `get_raw_db()` | Gravação permitida (sem Row factory) | Processamento em lote, scan, migração |

> **Importante**: se uma API somente leitura usar `get_db()`, ocorre disputa de write lock durante o scan e o viewer fica bloqueado por alguns segundos. Sempre use `get_readonly_db()`.

---

## Bypass de autenticação e testes

### Pular autenticação por PIN

Ao iniciar com `config_test.json` (sem PIN configurado), toda a autenticação é ignorada.

### Teste de API Key

```bash
# Requisição à API com token Bearer (dispensa cabeçalho CSRF)
curl -H "Authorization: Bearer sk_xxxxxxxxxxxxxx" \
  http://127.0.0.1:5000/api/stats/all
```

### Escopos de API Key

A partir da v4.8.1, chaves sem escopo configurado permitem **apenas leitura**. Operações de escrita exigem uma chave com escopo explícito.

| Escopo | Operações permitidas |
|---------|--------------|
| `read` | Busca, detalhes de arquivo, miniaturas, estatísticas |
| `rate` | Definir/obter/em lote ratings |
| `tag.write` | Adicionar/remover tags |
| `collection.write` | CRUD de coleções, favoritos |
| `annotate` | Leitura/gravação de anotações |
| `scan` | Iniciar/abortar/retomar scan |
| `admin` | Gerenciamento de API Key, alteração de configurações, backup/restauração |

### Ordem da cadeia de autenticação

```
static → /s/ (LAN Share) → /_pin → API Key Bearer
→ QuickLock → Trusted Proxy → session → cookie → Exibição da tela de PIN
```

Detalhes: `core/web/auth_chain.py`

### Autenticar por PIN com curl

```bash
# 1. Obter o token CSRF
CSRF=$(curl -s -c cookies.txt http://127.0.0.1:5000/_pin | grep _csrf_token | sed 's/.*value="\([^"]*\)".*/\1/')

# 2. Enviar o PIN
curl -b cookies.txt -c cookies.txt -X POST http://127.0.0.1:5000/_pin_check \
  -d "pin=1234&_csrf_token=$CSRF"

# 3. Requisição autenticada
curl -b cookies.txt http://127.0.0.1:5000/api/stats/all
```

---

## Depuração MCP

### Iniciar o servidor MCP

```bash
source venv/Scripts/activate
python -m mcp_server
```

### Ativar ferramentas de depuração

```bash
export YU_DEBUG_MODE=1
export YU_BASE_URL=http://127.0.0.1:5100
export YU_API_KEY=sk_...
python -m mcp_server
```

### Configuração do Claude Desktop

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "yu-ai-manager": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "<raiz do projeto>",
      "env": {
        "YU_API_KEY": "sk_...",
        "YU_BASE_URL": "http://127.0.0.1:5000",
        "YU_DEBUG_MODE": "1"
      }
    }
  }
}
```

### Lista de ferramentas de depuração MCP

Com `YU_DEBUG_MODE=1`, 9 ferramentas de depuração são registradas adicionalmente:

| Ferramenta | Uso |
|--------|------|
| `debug_health_check` | Verifica a integridade de servidor/DB/tabelas |
| `debug_validate_counts` | Reconcilia estatísticas da API com contagens reais do DB |
| `debug_validate_search` | Verifica regressão da API de busca |
| `debug_validate_collection` | Consistência interna da contagem de coleções |
| `debug_validate_annotations` | Consistência da tabela de anotações |
| `debug_sample_files` | Análise de campos com amostragem aleatória |
| `debug_roundtrip_test` | Teste round-trip de annotation/rating/tag |
| `debug_readonly_query` | Execução de query SELECT arbitrária |
| `debug_full_report` | Relatório integrado de todas as ferramentas de observação (1-5) |

### Verificação do import MCP

```bash
python -c "from mcp_server.server import mcp; print('OK')"
```

---

## Scan de segurança de Extensions

O YU AI Manager possui um recurso embutido de scan de código de Extensions. Como o scan é **executado automaticamente no momento do carregamento da Extension**, ao adicionar ou modificar uma nova Extension, reinicie o servidor para que ela seja carregada uma vez.

### Mecanismo do scan automático

Na hora de carregar uma Extension, as verificações a seguir são executadas na seguinte ordem:

```
1. ManifestAuthority.review()   — revisão do manifest (formato e adequação de permissões)
2. CodeVerifier.verify()        — análise estática AST (scan de código de todos os arquivos .py)
3. Confirmação de aprovação pelo usuário — aprovar/rejeitar permissões
4. Emissão de Capability Token — token de permissão de execução
```

### O que o CodeVerifier detecta

| Categoria | Alvos detectados | severity |
|---------|---------|----------|
| Módulos perigosos | `subprocess`, `ctypes`, `importlib` | block |
| Acesso direto ao DB | `import sqlite3` (deve-se usar SandboxedDB) | block |
| Rede | `requests`, `urllib`, `httpx`, `aiohttp`, `socket` | warn |
| Execução dinâmica de código | `eval()`, `exec()`, `__import__()`, `compile()` | block |

Quando o severity é `block`, o carregamento da Extension é rejeitado.

### Como executar o scan

**Fluxo normal (recomendado):**

Após adicionar ou modificar a Extension, reinicie o servidor. No carregamento, o scan é executado automaticamente e os resultados são gravados no log.

```bash
# Recarregar a Extension pelo restart do servidor (o scan roda automaticamente)
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

**Se quiser executar somente o scan manualmente:**

```python
from pathlib import Path
from core.extensions_core.validation.code_verifier import CodeVerifier

result = CodeVerifier().verify(Path("extensions/my-extension"))

# Check result
for finding in result.findings:
    print(f"[{finding.severity}] {finding.file}:{finding.line} - {finding.message}")

print(f"Approved: {result.approved}")
```

### Trust Level

As Extensions são classificadas em 3 níveis de confiança:

| Nível | Condição | Restrições |
|--------|------|------|
| L0 Trusted | Prefixo `builtin-` | Sem restrições |
| L1 Verified | Assinatura verificada | Apenas permissões declaradas |
| L2 Untrusted | Instalação manual | Permissões declaradas + aprovação do usuário obrigatória |

### Proteção em runtime

Mesmo após o carregamento, a proteção em runtime continua:

- **Import Guard**: bloqueia via `sys.meta_path` o import de módulos não autorizados
- **Integrity Monitor**: a cada 5 minutos compara hashes SHA-256 e detecta adulteração de arquivos
- **Invalidação automática de Token**: ao detectar uma violação, invalida o Capability Token e interrompe a execução

### Documentação relacionada

| Documento | Local |
|-------------|------|
| Modelo de segurança de separação de poderes | `docs/development/development_docs/EXTENSION_TRIAS_POLITICA_SPEC.md` |
| Especificação do Sandbox | `docs/development/development_docs/EXTENSION_SANDBOX_SPEC.md` |
| Especificação de Hooks | `docs/development/development_docs/EXTENSION_HOOKS_SPEC.md` |

---

## Depuração do front-end

### Build do TypeScript

```bash
pnpm run build        # bundle com esbuild
pnpm run typecheck    # tsc --noEmit (apenas verificação de tipos)
```

Destino de saída: `ui/default/static/dist/` (alvo de gitignore)

### Configuração dos entry points

- Comum a todas as páginas: `src/ts/nav/index.ts` → `static/dist/nav.js`
- Por página: `src/ts/apps/*-app.ts` → `static/dist/*-app.js`

### Interceptador CSRF

`src/ts/nav/csrf-fetch.ts` envolve o `fetch` global com um Proxy e injeta automaticamente o cabeçalho `X-Requested-With` em todas as chamadas POST/PUT/DELETE.

```javascript
// Verificação no console do navegador
fetch('/api/stats/all').then(r => r.json()).then(console.log);
```

### Engine compartilhada de SSE

`window.EventSource` é sobrescrito por um Proxy; chamar `new EventSource()` diretamente resulta em erro.

```javascript
// Uso correto
window.sseSubscribe('scan.progress', (d) => console.log(d.data));

// Errado (erro em runtime)
// new EventSource('/api/events/...')
```

### Depuração de i18n

```javascript
// Troca de idioma
window.setLang('en');

// Verificar chave de tradução
console.log(window.tr('search.count.normal', { count: 5 }));
```

Arquivos i18n: `ui/default/static/i18n/{lang}.json`

---

## Lista de variáveis de ambiente

### Depuração/Log

| Variável | Valor | Padrão | Descrição |
|------|-----|----------|------|
| `TAGDB_DEBUG` | `1`/`0` | `0` | Ativar/desativar log de depuração estruturado |
| `TAGDB_DEBUG_LOG` | path | `logs/debug.log` | Caminho do arquivo de log |
| `TAGDB_DEBUG_LOG_MAX_MB` | int | `10` | Tamanho de rotação do log (MB) |
| `TAGDB_DEBUG_LOG_BACKUPS` | int | `5` | Número de gerações de backup |
| `TAGDB_DEBUG_STDOUT` | `1`/`0` | `1` | Saída do log em stderr |

### Servidor

| Variável | Valor | Descrição |
|------|-----|------|
| `TAGDB_DB` | path | Caminho do arquivo DB |
| `TAGDB_CONFIG` | path | Caminho de config.json |
| `TAGDB_PROFILE` | str | Nome do perfil de inicialização |
| `TAGDB_ALLOW_RESTART` | `1`/`0` | Ativa a API de restart |

### MCP

| Variável | Valor | Descrição |
|------|-----|------|
| `YU_DEBUG_MODE` | `1` | Registra adicionalmente 9 ferramentas de depuração |
| `YU_BASE_URL` | URL | BASE URL para o cliente MCP |
| `YU_API_KEY` | `sk_...` | API Key para o cliente MCP |

---

## Erros comuns e soluções

### Inicialização do servidor

| Erro | Causa | Solução |
|--------|------|------|
| `Address already in use` | Porta ocupada | Especifique outra porta com `--port 5200` |
| `database is locked` | Conflito de lock no DB | Verifique se o DB não está em um path de rede |
| `--pin is required` | PIN não configurado com bind em LAN | Configure com `--pin <dígitos>` |
| `ModuleNotFoundError` | venv não ativado ou pacote ausente | `source venv/Scripts/activate && uv pip install -r requirements.txt` |

### Autenticação

| Erro | Causa | Solução |
|--------|------|------|
| Tela de PIN exibida repetidamente | Erro nas configurações de cookie | Verifique os cookies do navegador (DevTools → Application) |
| `CSRF header missing` (403) | Cabeçalho `X-Requested-With` ausente | Adicione `-H "X-Requested-With: XMLHttpRequest"` ao fetch |
| API Key rejeitada | Escopo insuficiente | Após v4.8.1, chaves sem escopo permitem apenas leitura. Conceda o escopo necessário |

### DB

| Erro | Causa | Solução |
|--------|------|------|
| `no such table: schema_version` | Primeiro start | É gerado automaticamente; ignore |
| Falha de migração | Bug no script | Verifique a integridade com `db_health.py` → correção manual |
| `SQLITE_BUSY` (timeout) | Transação longa | Verifique se uma API de leitura está usando `get_db()` |

### Específicos do Windows

| Erro | Causa | Solução |
|--------|------|------|
| `UnicodeEncodeError` (no print) | em dash etc. não podem ser escritos em cp932 | Use apenas caracteres ASCII-safe |
| `pkill` não funciona | Restrição do Git Bash | `tasklist \| grep python` → `taskkill //F //PID <pid>` |
| Falha de `os.replace()` | Handle do arquivo aberto | Encerre o processo e tente novamente |

### TypeScript

| Erro | Causa | Solução |
|--------|------|------|
| Alterações não refletidas | Não compilado | `pnpm run build` |
| Erro de tipo | Inconsistência de definição de tipo | Verifique com `pnpm run typecheck` |
| Erro de `EventSource` | Chamou `new` diretamente | Use `window.sseSubscribe()` |

---

## Depuração de desempenho

### Bloqueio do viewer durante o scan

**Sintoma**: durante o scan, a exibição de imagens trava por 5-10 segundos

**Causa**: uma API de leitura estava usando `get_db()` (conexão com permissão de escrita)

**Solução**: APIs somente leitura devem sempre usar `get_readonly_db()`

### Detecção de latência pelo log de depuração

```bash
# Buscar entradas que levaram mais de 120 segundos
grep "per-entry.*120" logs/debug.log

# Detecção de bloqueios durante o scan
grep "SQLITE_BUSY" logs/debug.log
```

### Verificação de rate limit

Modelo de token bucket em 3 camadas:

| Camada | Alvos | Limite |
|--------|------|------|
| **HEAVY** | Busca por similaridade, cálculo de hash, análise por IA, scan | ~20 req/min (burst 5) |
| **DESTRUCTIVE** | purge, hard-delete, cache clear, config write | ~12 req/min (burst 3) |
| **WRITE** | Outros POST/PUT/DELETE | ~120 req/min (burst 30) |
| GET | Leitura | Sem limite |

Se receber 429, verifique o cabeçalho `Retry-After`.

---

## Documentação relacionada

| Documento | Local |
|-------------|------|
| Separação de leitura/escrita no DB | `docs/development/development_docs/SQLITE_READONLY_SEPARATION.md` |
| Unificação do formato de erros | `docs/development/development_docs/ERROR_HANDLING.md` |
| Multiplataforma | `docs/development/development_docs/CROSS_PLATFORM_ISSUES.md` |
| Especificação das ferramentas de depuração MCP | `docs/development/development_docs/MCP_DEBUG_TOOLS.md` |
| Log de migração do Quart | `docs/development/development_docs/QUART_MIGRATION_DEVLOG.md` |
| Handoff de QA | `docs/development/development_docs/QA_HANDOFF.md` |
| Verificação de segurança | skill `/security-check` |
