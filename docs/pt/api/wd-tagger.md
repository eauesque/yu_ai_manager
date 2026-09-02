# API WD Tagger

APIs para WD Tagger (Waifu Diffusion Tagger) auto-tagging Danbooru. Fornece gerenciamento de configuração, tagging único/lote, CRUD de tag, gerenciamento de modelo, leitura XMP e teste de conexão VLM.

## GET /api/wd-tagger/config

Obtém a configuração WD Tagger atual.

### Parâmetros

Nenhum

### Resposta

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

## POST /api/wd-tagger/config

Salva/atualiza configuração WD Tagger.

### Taxa de Limite

WRITE

### Solicitação

```json
{
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "threshold": 0.35
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| *(qualquer chave)* | qualquer | Não | Campo de configuração. Chaves desconhecidas ou valores inválidos retornam `400` |

### Resposta

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `invalid_json` | 400 | Corpo da solicitação não é um objeto JSON |
| `invalid_value` | 400 | Valor de configuração inválido |

## POST /api/wd-tagger/tag/<file_id>

Executa inferência WD Tagger em um único arquivo para prever e atribuir tags Danbooru.

### Taxa de Limite

HEAVY

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `file_id` | int | ID do arquivo (parâmetro de caminho) |

### Solicitação

```json
{
  "force": false
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `force` | boolean | Não | Se `true`, sobrescreve tags existentes e re-executa inferência. Padrão `false` |

### Resposta

```json
{
  "file_id": 42,
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general"},
    {"tag": "solo", "score": 0.95, "category": "general"}
  ]
}
```

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `tag_error` | 400 | Tagging falhou (arquivo não encontrado, erro de carregamento de imagem, etc.) |

## GET /api/wd-tagger/tags/<file_id>

Obtém tags WD Tagger armazenadas para um arquivo específico.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_id` | int | Sim | ID do arquivo (parâmetro de caminho) |
| `model` | string | Não | Filtrar por nome do modelo (parâmetro de query) |
| `all` | boolean | No | When `1`, `true`, or `yes`, return tags from all models and ignore the active model and `model` filter |

### Resposta

```json
{
  "file_id": 42,
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"},
    {"tag": "solo", "score": 0.95, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"}
  ]
}
```

## DELETE /api/wd-tagger/tags/<file_id>

Deleta tags WD Tagger para um arquivo específico.

### Taxa de Limite

WRITE

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_id` | int | Sim | ID do arquivo (parâmetro de caminho) |
| `model` | string | Não | Filtrar por nome do modelo (parâmetro de query). Se omitido, deleta tags de todos os modelos |

### Resposta

```json
{
  "file_id": 42,
  "deleted": 15
}
```

## DELETE /api/wd-tagger/tags/batch

Deleta tags WD Tagger para múltiplos arquivos de uma vez.

### Taxa de Limite

WRITE

### Solicitação

```json
{
  "file_ids": [1, 2, 3],
  "model": "wd-swinv2-tagger-v3"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_ids` | list | Sim | Array de IDs de arquivo (máx 500) |
| `model` | string | Não | Filtrar por nome do modelo. Se omitido, deleta tags de todos os modelos |

### Resposta

```json
{
  "deleted_files": 3,
  "deleted_tags": 45
}
```

## Active model (v4.192.0+)

Quando o mesmo arquivo é retagueado com vários modelos WD Tagger,
`file_wd_tags` mantém as tags de cada modelo como histórico. Ao definir um
active model, a visualização de detalhes, a busca `ai_analyzed` e a verificação
interna "já tagueado" do WD Tagger usam apenas as tags desse modelo. Se nenhum
active model estiver definido, o comportamento anterior é preservado e as tags
de todos os modelos são usadas em conjunto.

### Configuração na UI

O retag modal mostra o `Active model` atual no topo. Use o dropdown `Change` para
selecionar um modelo disponível. Escolha `(none / reset)` para limpar o active
model.

Após um retag, o modelo usado se torna active model por padrão. Desative a opção
"Definir como modelo ativo após retag" no retag modal para manter o active model
atual.

Rows de modelos antigos não são excluídas automaticamente. Elas permanecem no
banco como histórico. Para removê-las explicitamente, ative "Excluir também tags
de outros modelos" no retag modal e confirme o diálogo após o retag.


### GET /api/wd-tagger/profiles

Returns registered WD Tagger profiles and the current active model. Requires admin scope.

```json
{
  "profiles": [
    {
      "id": "camie_tagger_v2",
      "display_name": "Camie Tagger v2",
      "model_id": "Camais03/camie-tagger-v2",
      "adapter_family": "camie",
      "backend": "onnx",
      "builtin": true,
      "has_tags": false
    }
  ],
  "active_model_id": "Camais03/camie-tagger-v2"
}
```

### GET /api/wd-tagger/active-model

Retorna o active model atual e a lista de modelos presentes no banco de dados.
Requer admin scope.

```json
{
  "active_model_id": "SmilingWolf/wd-eva02-large-tagger-v3",
  "available_models": [
    {"model_id": "SmilingWolf/wd-eva02-large-tagger-v3", "file_count": 120},
    {"model_id": "SmilingWolf/wd-swinv2-tagger-v3", "file_count": 340}
  ]
}
```

### PUT /api/wd-tagger/active-model

Altera o active model. Requer admin scope. Envie `null` ou uma string vazia em
`model_id` para redefinir.

```json
{
  "model_id": "SmilingWolf/wd-eva02-large-tagger-v3"
}
```

| Código | Status | Descrição |
|--------|--------|-----------|
| `invalid_model_id` | 400 | model_id é longo demais ou contém caracteres de controle |
| `unknown_model` | 400 | Não há tags do modelo indicado no banco de dados |

## POST /api/wd-tagger/batch

Executa tagging em lote em múltiplos arquivos. Se `file_ids` é especificado, apenas esses arquivos são processados. Se omitido, seleciona automaticamente arquivos não marcados até `limit`.

### Taxa de Limite

HEAVY

### Solicitação

```json
{
  "file_ids": [1, 2, 3],
  "limit": 100,
  "force": false,
  "scan_root": ""
}
```

| Parâmetro | Tipo | Obrigatório | Limite | Descrição |
|-----------|------|----------|--------|-----------|
| `file_ids` | int[] | Não | Máx 500 | Array de IDs de arquivo alvo. Se omitido, arquivos não marcados são selecionados automaticamente |
| `limit` | int | Não | — | Máx arquivos a processar quando `file_ids` é omitido. Padrão `100` |
| `force` | boolean | Não | — | Se `true`, sobrescreve tags existentes. Padrão `false` |
| `scan_root` | string | Não | — | Filtrar por caminho raiz de varredura. String vazia para todos os arquivos |

### Resposta

```json
{
  "job_id": "wd_tagger",
  "total": 100,
  "status": "started"
}
```

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `batch_too_large` | 400 | `file_ids` excede 500 itens |
| `batch_error` | 409 | Um trabalho em lote já está em execução |

## POST /api/wd-tagger/batch/cancel

Cancela um trabalho de tagging em lote em execução.

### Taxa de Limite

WRITE

### Solicitação

Nenhum corpo obrigatório.

### Resposta

```json
{
  "status": "cancelling",
  "message": "Batch tagging cancel requested"
}
```

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `job_not_running` | 404 | Nenhum trabalho de tagging em lote em execução |

## GET /api/wd-tagger/stats

Obtém estatísticas de tagging WD Tagger.

### Parâmetros

Nenhum

### Resposta

```json
{
  "total_tagged": 1234,
  "total_tags": 56789,
  "models": {
    "SmilingWolf/wd-swinv2-tagger-v3": 1200
  },
  "untagged_unknown": 42
}
```

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `total_tagged` | int | Número de arquivos marcados |
| `total_tags` | int | Número total de tags armazenadas |
| `models` | object | Número de arquivos marcados por modelo |
| `untagged_unknown` | int | Número de arquivos sem metadados (`unknown`) e sem tags WD |

## GET /api/wd-tagger/untagged

Lista arquivos sem metadados (`unknown`) que ainda não foram marcados. Suporta paginação.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `limit` | int | Não | Número de resultados. 1-500, padrão `100` |
| `offset` | int | Não | Número de resultados a pular. Padrão `0` |

### Resposta

```json
{
  "files": [
    {"id": 10, "filepath": "/images/photo.png", "filename": "photo.png"}
  ],
  "total": 42
}
```

## GET /api/wd-tagger/xmp/<file_id>

Lê metadados XMP de um arquivo específico.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `file_id` | int | ID do arquivo (parâmetro de caminho) |

### Resposta

```json
{
  "file_id": 42,
  "xmp": {
    "subject": ["1girl", "solo", "blue_eyes"],
    "description": "...",
    "creator": "..."
  }
}
```

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `file_not_found` | 404 | Arquivo não existe ou está soft-deletado |

## GET /api/wd-tagger/vlm/test

Testa conectividade com um servidor VLM (Vision Language Model). Verifica acessibilidade de um endpoint de API compatível com OpenAI.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `url` | string | Sim | URL do servidor VLM (parâmetro de query) |

### Resposta

```json
{
  "ok": true,
  "message": "Connection successful",
  "server_info": "..."
}
```

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `missing_url` | 400 | Parâmetro `url` não fornecido |
| `invalid_url` | 400 | Formato de URL é inválido |

## GET /api/wd-tagger/vlm/models

Lista modelos disponíveis em um servidor VLM. Consulta o endpoint OpenAI-compatível `/v1/models`.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `url` | string | Sim | URL do servidor VLM (parâmetro de query) |

### Resposta

```json
{
  "models": [
    {"id": "llava-v1.6", "object": "model"}
  ]
}
```

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `missing_url` | 400 | Parâmetro `url` não fornecido |
| `invalid_url` | 400 | Formato de URL é inválido |
| `vlm_connection_error` | 502 | Falha ao conectar com servidor VLM |

## POST /api/wd-tagger/model/download

Baixa um modelo WD Tagger. Busca arquivos do modelo no Hugging Face e salva localmente.

### Taxa de Limite

HEAVY

### Solicitação

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `repo` | string | Não | Nome do repositório Hugging Face. Se omitido, usa o valor `model` da configuração |

### Resposta

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "path": "/path/to/model/directory",
  "ready": true
}
```

### Erros

| Código | Status | Descrição |
|--------|--------|-----------|
| `unknown_model` | 400 | Repositório de modelo desconhecido. `hint` contém lista de modelos conhecidos |
| `download_failed` | 500 | Download falhou |

## GET /api/wd-tagger/model/status

Verifica o status de download de um modelo WD Tagger.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `repo` | string | Não | Nome do repositório Hugging Face (parâmetro de query). Se omitido, usa o valor `model` da configuração |

### Resposta

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "downloaded": true,
  "path": "/path/to/model/directory",
  "known_models": {
    "SmilingWolf/wd-swinv2-tagger-v3": "SwinV2 (recommended)",
    "SmilingWolf/wd-convnext-tagger-v3": "ConvNeXt",
    "SmilingWolf/wd-vit-tagger-v3": "ViT"
  }
}
```

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `repo` | string | Nome do repositório sendo verificado |
| `downloaded` | boolean | Se o modelo está baixado localmente |
| `path` | string/null | Caminho do modelo local se baixado |
| `known_models` | object | Todos os modelos suportados (nome do repositório -> nome de exibição) |

## User profile CRUD (v4.197.0+)

API para fazer CRUD de tagger profiles criados pelo usuário a partir da UI da página Tools. Todos os endpoints exigem admin scope. O formato de erro comum é `{ok: false, error, code, ...extra}`. O body da requisição tem um **hard cap de 1MB** (`code: profile_too_large`, 413). `id` deve corresponder ao regex `^[a-z0-9][a-z0-9_-]{0,63}$`.

### POST /api/wd-tagger/profiles

Criar um novo profile de usuário.

**Requisição**: profile JSON (schema v2, `profile_version: "2"`). O campo `builtin` é sobrescrito forçadamente para `false` no servidor.

**Resposta (200)**:
```json
{
  "ok": true,
  "profile": { "...": "...サニタイズ済 profile JSON..." },
  "origin": "user",
  "overrides_builtin": false
}
```

| Campo | Descrição |
|---|---|
| `profile` | Profile salvo (garantido `builtin: false`) |
| `origin` | Sempre `"user"` |
| `overrides_builtin` | `true` se existir um profile builtin com o mesmo id (caminho avançado) |

**Erros**:

| status | code | condição |
|---|---|---|
| 400 | `validation_failed` | O JSON viola o schema v2 (`extra.errors=[{path, message}, ...]`) |
| 400 | `invalid_id` | O `id` no body não corresponde ao regex |
| 409 | `id_conflict` | Mesmo id de um profile de usuário existente |
| 413 | `profile_too_large` | body > 1MB |

### GET /api/wd-tagger/profiles/{id}

Obter o profile schema v2 completo do id especificado (chamado pela UI ao editar / duplicar / Export).

**path**: `id` (verificação de regex obrigatória)

**Resposta (200)**:
{Mesmo formato do POST: profile / origin / overrides_builtin}

**Erros**:
- 400 `invalid_id` (o id do path não corresponde ao regex)
- 404 `not_found`

### PUT /api/wd-tagger/profiles/{id}

Atualizar um profile de usuário existente.

**path**: `id` (verificação de regex obrigatória)

**Requisição**: profile JSON. `body.id` deve corresponder ao id do path (para renomear, orientar a UI para `Duplicate → Delete`).

**Resposta (200)**: Mesmo formato do POST.

**Erros**:

| status | code | condição |
|---|---|---|
| 400 | `id_immutable` | o id do path e o id do body não correspondem |
| 400 | `invalid_id` | o id do path não corresponde ao regex |
| 400 | `validation_failed` | violação do schema |
| 403 | `builtin_read_only` | o id do path é um profile builtin (não há arquivo de usuário correspondente) |
| 404 | `not_found` | id não registrado |
| 413 | `profile_too_large` | body > 1MB |

### DELETE /api/wd-tagger/profiles/{id}

Excluir um profile de usuário.

**path**: `id`

**Resposta (200)**:
```json
{"ok": true, "deleted": true}
```

**Erros**:

| status | code | condição |
|---|---|---|
| 400 | `invalid_id` | id do path inválido |
| 403 | `builtin_read_only` | apenas builtin, sem override do usuário |
| 404 | `not_found` | id não registrado |
| 409 | `in_use` | Este profile é o modelo ativo (inclui `extra.active_model_id`). Na UI, troque o profile ativo via `PUT /api/wd-tagger/active-model` e depois tente novamente |

### POST /api/wd-tagger/profiles/{id}/test

dry-run download. Faz HEAD de cada `files[]` no HuggingFace e, para itens com `required: true`, executa um download atômico por arquivo (o cache reutiliza o caminho existente).

**path**: `id`

**body**: não requerido

**Comportamento**:
- per-file timeout: 30s
- timeout total: 60s
- redirect: allowlist apenas para subdomínios `huggingface.co` / `hf.co`, no máximo 5 hops; userinfo (`user:pass@`) é SSRFBlocked

**Resposta (200, sucesso)**:
```json
{
  "ok": true,
  "files": [
    {"name": "model.onnx", "status": "downloaded", "size": 1234567},
    {"name": "tags.csv",   "status": "cached",     "size": 89012},
    {"name": "optional.json", "status": "skipped_optional", "size": null}
  ]
}
```

Valores de `status`:
- `downloaded`: baixado nesta execução
- `cached`: já existe localmente (apenas HEAD)
- `skipped_optional`: `required: false` e 404 / HEAD falhou

**Erros (status / code)**:

| status | code | condição |
|---|---|---|
| 400 | `invalid_id` / `required_missing` | id do path inválido / arquivo required é 404 no HF |
| 404 | `not_found` | profile não registrado |
| 408 | `timeout` | excedeu o total de 60s |
| 502 | `ssrf_blocked` | redirect fora da allowlist do HF / contém userinfo / scheme não é http(s) |
| 502 | `hf_unavailable` | HF retornou 5xx |

Em caso de erro, o body é da forma `{"ok": false, "code": ..., "error": ..., "files": [...resultados parciais...], "detail": "..."}`.

### Formato do profile JSON (schema v2)

```typescript
interface ProfileV2 {
  profile_version: "2";
  id: string;
  display_name: string;
  adapter_family: "wd" | "camie" | "oppai" | "generic_onnx";
  backend: "onnx";
  model_id: string;                        // Caminho do repo HF "<owner>/<name>"
  hf_subdir: string | null;
  files: { name: string; required: boolean; size_hint_mb?: number }[];
  default_thresholds: Record<string, number>;
  tag_source: TagSourceSpec;               // type=csv/json_list/json_dict/composite
  threshold_source: ThresholdSourceSpec;   // type=global_per_category/per_tag_json
  preprocess_spec: PreprocessSpec;
  supports_categories: string[];
  categories_mode: "from_tag_source" | "all_general";
  builtin?: boolean;                       // sempre false para origem do usuário (o servidor força)
}
```

Para mais detalhes, veja `extensions/builtin_wd_tagger/core_impl/adapters/base.py` (`TaggerProfile`), ou a implementação de referência builtin (`extensions/builtin_wd_tagger/core_impl/profiles/*.json`).
