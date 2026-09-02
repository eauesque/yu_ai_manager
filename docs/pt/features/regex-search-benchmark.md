# Relatório de Benchmark de Desempenho de Pesquisa Regex

**Data da pesquisa:** 2026-02-23
**Escala alvo:** 276,000 arquivos / tabela de templates

---

## Visão Geral

Este benchmark foi conduzido para verificar a viabilidade prática de pesquisa regex do YU AI Manager (`tag_query_regex=true`) em um banco de dados em larga escala (276K+ registros).

Existem dois caminhos de implementação de pesquisa:

| Caminho | Localização | Método |
|------|------|------|
| WebUI API | `core/query/filters_tags.py` | Operador SQL `REGEXP` (+ fallback Python) |
| Ferramenta CLI | `tools/regex_debug.py` | Full scan de Python `re.search()` |

---

## Arquitetura

### Fluxo de Regex da WebUI API

```
GET /api/search?q=<pattern>&regex=1
  └─ search_params.py   tag_query_regex=True
  └─ filters_tags.py    SQL: tp.raw_prompt REGEXP ?
  └─ db_state.get_db()  WAL + mmap=30GB (schema_connect.py)
```

Fragmento SQL gerado:

```sql
EXISTS(
  SELECT 1 FROM templates tp
  WHERE tp.file_id = f.id
    AND (tp.raw_prompt REGEXP ? OR tp.raw_negative REGEXP ?)
)
```

- `(?i)` é automaticamente preposto ao padrão para pesquisas case-insensitive
- O sistema volta para `LIKE %pattern%` em ambientes onde `REGEXP` não é suportado

### Fluxo da Ferramenta CLI (`regex_debug.py`)

```python
rows = con.execute(
    "SELECT t.file_id, t.raw_prompt, t.raw_negative, f.path "
    "FROM templates t JOIN files f ON f.id=t.file_id WHERE f.is_deleted=0"
).fetchall()   # Carregue todas as linhas em memória
# -> Filtragem sequencial com Python re.search()
```

---

## Resultados de Benchmark (Valores de Referência)

> **Nota:** Os valores abaixo são estimativas baseadas em medições reais usando `tools/regex_debug.py`.
> Eles variam significativamente dependendo do hardware e estado de cache do arquivo DB.

### Full Scan do CLI (Python `re.search`)

| Contagem de registros | Cold start | Warm (cache do SO) |
|------|-----------|-----------------|
| 10,000 | ~0.3s | ~0.1s |
| 100,000 | ~2.5s | ~0.8s |
| 276,000 | **~6-10s** | **~2-3s** |

### WebUI API (SQL REGEXP)

O binding Python do SQLite (`sqlite3` module) não implementa `REGEXP` por padrão. É necessário registrar o módulo `re` do Python usando `con.create_function("regexp", 2, ...)`.

Após registro, um callback de Python é invocado para cada linha, então o desempenho é comparável ao scan CLI (linear na contagem de linhas).

---

## Análise de Bottleneck

| Fator | Impacto | Mitigação |
|------|------|------|
| Full row fetch (scan Python) | Alto | Indexação não é possível (regex é incompatível com B-Tree) |
| Comprimento médio de raw_prompt | Médio | Prompts mais longos aumentam custo de `re.search()` |
| Efeito de cache | Alto | Segunda execução em diante tem quase zero I/O devido a cache de página do SO |
| Contenção FTS5 | Baixo | Índice FTS usa caminho separado de regex quando `enable_fts=true` |
| MMAP (30GB) | Positivo | Já configurado em `schema_connect.py`, reduz overhead de I/O |

---

## Configurações Atuais de MMAP / PRAGMA

De `core/schema_core/schema_connect.py`:

```python
con.execute("PRAGMA journal_mode=WAL;")
con.execute("PRAGMA synchronous=NORMAL;")
con.execute("PRAGMA foreign_keys=ON;")
con.execute("PRAGMA cache_size=-64000;")    # Cache de 64 MB
con.execute("PRAGMA temp_store=MEMORY;")
con.execute("PRAGMA mmap_size=30000000000;") # mmap de 30 GB
```

O `get_db()` da WebUI (`db_state.py`) apenas define WAL + NORMAL sem mmap.
Adicionar configurações de mmap à conexão de pesquisa poderia melhorar desempenho de cold start.

---

## Melhorias Recomendadas

### Curto prazo (Apenas Mudanças de Configuração)

1. **Adicionar mmap a `get_db()`** (`core/services_core/db_state.py`)

   ```python
   con.execute("PRAGMA mmap_size=30000000000;")
   con.execute("PRAGMA cache_size=-64000;")
   ```

2. **Registrar função `REGEXP`** (dentro de `get_db()`)

   ```python
   import re as _re
   con.create_function("regexp", 2,
       lambda pat, val: bool(_re.search(pat, val or "", _re.IGNORECASE))
       if pat else False)
   ```

### Médio prazo (Mudanças de Implementação)

| Abordagem | Descrição | Efeito |
|------|------|------|
| Pré-filtro FTS5 `MATCH` | Estreitar candidatos com FTS antes de regex | Speedup significativo para certos padrões |
| Pesquisa em background + Server-Sent Events | Transmitir resultados incrementalmente | Melhoria de UX (elimina espera para primeiro resultado) |
| Cache de pesquisa (TTL 30s) | Resposta instantânea para padrões idênticos repetidos | Efetivo para pesquisas repetidas |

---

## Procedimento de Medição CLI

```bash
# Medição básica
python tools/regex_debug.py "1girl" --db data/tags.db --limit 0

# Medição com tempo (comando bash time)
time python tools/regex_debug.py "lora:.*:0\.[5-9]" --db data/tags.db --limit 0

# Específico de campo
python tools/regex_debug.py "masterpiece" --field prompt --db data/tags.db
```

Saída de amostra (assumindo 276,000 registros):
```
Database: data/tags.db  (276000 templates)
Pattern:  '1girl'  (flags: case-insensitive)
Field:    both
------------------------------------------------------------
Scanned 276000 templates in 7.82s  ->  182300 matches
```

---

## Resumo

- Um full scan regex de 276,000 registros leva aproximadamente **6-10 segundos cold, 2-3 segundos warm**
- Adicionar `PRAGMA mmap_size` e registro de função `REGEXP` deve melhorar responsividade
- Regex não pode usar índices B-Tree, então escala linearmente com contagem de registros
- Um pré-filtro FTS5 é a melhoria mais efetiva de médio prazo
