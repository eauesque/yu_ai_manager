# API OCR

API para extração de texto (OCR) de imagens, vídeos e PDFs, juntamente com tradução, geração de imagem de sobreposição, exportação, benchmarking e gerenciamento de engine.

## POST /api/ocr/<file_id>

Executa OCR em um único arquivo e salva o resultado no banco de dados.

### Taxa de Limite

WRITE

### Solicitação

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_id` | int | Sim | ID do arquivo (parâmetro de caminho) |
| `task` | string | Não | Tipo de tarefa OCR. Um de `ocr` / `ocr_document` / `ocr_manga`. Padrão: `ocr` |
| `language` | string | Não | Dica de idioma. Padrão: `auto` |
| `server_id` | string | Não | ID do servidor de análise a usar. Auto-selecionado se omitido |

### Resposta (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr",
  "full_text": "Extracted text...",
  "language": "ja",
  "regions_count": 3,
  "row_id": 1
}
```

### Erros

- `400` — Valor de tarefa inválido
- `404` — Arquivo não encontrado
- `500` — Falha ao resolver engine OCR / Erro de execução OCR

---

## GET /api/ocr/result/<file_id>

Recupera um resultado OCR salvo.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_id` | int | Sim | ID do arquivo (parâmetro de caminho) |
| `task` | string | Não | Filtrar por tipo de tarefa |
| `engine` | string | Não | Filtrar por nome do engine |
| `all` | string | Não | Se definido para qualquer valor, retorna todos os resultados |

### Resposta (resultado encontrado)

```json
{
  "file_id": 42,
  "task": "ocr",
  "engine": "gemini-2.0-flash",
  "full_text": "Extracted text...",
  "language": "ja",
  "regions": [...]
}
```

### Resposta (com `?all=1`)

```json
{
  "file_id": 42,
  "results": [
    { "task": "ocr", "engine": "gemini-2.0-flash", "full_text": "..." },
    { "task": "ocr_manga", "engine": "manga-ocr", "full_text": "..." }
  ]
}
```

### Resposta (sem resultado)

```json
{
  "status": "not_found"
}
```

---

## DELETE /api/ocr/result/<file_id>

Deleta resultados OCR salvos.

### Taxa de Limite

WRITE

### Solicitação

```json
{
  "task": "",
  "engine": ""
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_id` | int | Sim | ID do arquivo (parâmetro de caminho) |
| `task` | string | Não | Filtrar por tipo de tarefa. String vazia alvo todos os tipos |
| `engine` | string | Não | Filtrar por nome do engine. String vazia alvo todos os engines |

### Resposta

```json
{
  "deleted": 2
}
```

---

## POST /api/ocr/batch

Executa OCR em múltiplos arquivos em lote.

### Taxa de Limite

WRITE

### Solicitação

```json
{
  "file_ids": [1, 2, 3],
  "task": "ocr",
  "language": "auto",
  "server_id": ""
}
```

| Parâmetro | Tipo | Obrigatório | Limite | Descrição |
|-----------|------|----------|--------|-----------|
| `file_ids` | int[] | Sim | Máx 500 | Array de IDs de arquivo alvo |
| `task` | string | Não | — | Tipo de tarefa OCR. `ocr` / `ocr_document` / `ocr_manga`. Padrão: `ocr` |
| `language` | string | Não | — | Dica de idioma. Padrão: `auto` |
| `server_id` | string | Não | — | ID do servidor de análise a usar |

### Resposta (200)

```json
{
  "processed": 2,
  "errors": 1,
  "results": [
    { "file_id": 1, "full_text_length": 128, "regions_count": 3 },
    { "file_id": 2, "full_text_length": 256, "regions_count": 5 }
  ],
  "error_details": [
    { "file_id": 3, "error": "File not found" }
  ]
}
```

### Erros

- `400` — `file_ids` vazio / excede 500 / valor de tarefa inválido
- `500` — Falha ao resolver engine OCR

---

## POST /api/ocr/video/<file_id>

Extrai quadros-chave de um arquivo de vídeo e executa OCR em cada quadro.

### Taxa de Limite

WRITE

### Solicitação

```json
{
  "task": "ocr",
  "language": "auto",
  "server_id": "",
  "keyframe_count": 4,
  "strategy": "uniform"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_id` | int | Sim | ID do arquivo (parâmetro de caminho) |
| `task` | string | Não | Tipo de tarefa OCR. Padrão: `ocr` |
| `language` | string | Não | Dica de idioma. Padrão: `auto` |
| `server_id` | string | Não | ID do servidor de análise a usar |
| `keyframe_count` | int | Não | Número de quadros-chave a extrair. Intervalo: 1-16. Padrão: `4` |
| `strategy` | string | Não | Estratégia de extração de quadro-chave. Padrão: `uniform` |

### Resposta (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr",
  "full_text": "Text extracted from frames...",
  "frame_count": 4,
  "row_id": 5
}
```

### Erros

- `400` — Arquivo não é um vídeo
- `404` — Arquivo não encontrado
- `500` — Falha ao resolver engine OCR / Erro de execução OCR de vídeo

---

## POST /api/ocr/pdf/<file_id>

Converte páginas de PDF em imagens e executa OCR. Útil para PDFs digitalizados sem camada de texto.

### Taxa de Limite

WRITE

### Solicitação

```json
{
  "task": "ocr_document",
  "language": "auto",
  "server_id": "",
  "page_range": "",
  "dpi": 200
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_id` | int | Sim | ID do arquivo (parâmetro de caminho) |
| `task` | string | Não | Tipo de tarefa OCR. Padrão: `ocr_document` |
| `language` | string | Não | Dica de idioma. Padrão: `auto` |
| `server_id` | string | Não | ID do servidor de análise a usar |
| `page_range` | string | Não | Intervalo de páginas (ex., `"1-5"`, `"1,3,5"`). String vazia significa todas as páginas |
| `dpi` | int | Não | Resolução de renderização. Intervalo: 72-400. Padrão: `200` |

### Resposta (200)

```json
{
  "file_id": 42,
  "engine": "gemini-2.0-flash",
  "task": "ocr_document",
  "full_text": "Text extracted from PDF...",
  "page_count": 10,
  "row_id": 6
}
```

### Erros

- `400` — Arquivo não é um PDF
- `404` — Arquivo não encontrado
- `500` — Falha ao resolver engine OCR / Erro de execução OCR de PDF

---

## POST /api/ocr/bbox/<file_id>

Detecta caixas delimitadoras de texto para resultados OCR existentes. Usado como segundo passe para adicionar informações de posição a regiões de texto previamente extraídas.

### Taxa de Limite

WRITE

### Solicitação

```json
{
  "task": "",
  "server_id": ""
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_id` | int | Sim | ID do arquivo (parâmetro de caminho) |
| `task` | string | Não | Tipo de tarefa OCR alvo |
| `server_id` | string | Não | ID do servidor de análise a usar |

### Resposta (200)

```json
{
  "file_id": 42,
  "total_regions": 5,
  "detected_bboxes": 4,
  "regions": [
    {
      "id": 0,
      "text": "Text region",
      "bbox": { "x": 10, "y": 20, "width": 200, "height": 30 }
    }
  ]
}
```

### Erros

- `400` — Nenhuma região de texto encontrada / Engine VLM obrigatório
- `404` — Resultado OCR não encontrado (execute OCR primeiro) / Arquivo não encontrado
- `500` — Falha ao resolver engine OCR / Erro de detecção bbox

---

## GET /api/ocr/engines

Lista engines OCR disponíveis (servidores de análise) com pontuações por tarefa.

### Parâmetros

Nenhum

### Resposta

```json
{
  "engines": [
    {
      "server_id": "server-1",
      "server_name": "Gemini Flash",
      "model": "gemini-2.0-flash",
      "type": "google",
      "scores": {
        "ocr": 85,
        "ocr_document": 90,
        "ocr_manga": 60
      }
    }
  ],
  "manga_ocr_available": false
}
```

---

## GET /api/ocr/npu

Obtém status do dispositivo NPU (Neural Processing Unit) e configurações de otimização recomendadas.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `task` | string | Não | Tipo de tarefa para recomendações de otimização. Padrão: `ocr` |

### Resposta

```json
{
  "npu": {
    "available": true,
    "device": "Hailo-10H",
    "driver_version": "4.20.0"
  },
  "optimization": {
    "recommended_batch_size": 4,
    "use_npu": true
  }
}
```

---

## POST /api/ocr/translate/<file_id>

Traduz um resultado OCR existente para o idioma especificado. A tradução é salva no banco de dados.

### Taxa de Limite

WRITE

### Solicitação

```json
{
  "target_lang": "en",
  "server_id": "",
  "task": ""
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_id` | int | Sim | ID do arquivo (parâmetro de caminho) |
| `target_lang` | string | Sim | Código de idioma alvo (ex., `en`, `ja`, `zh`, `ko`) |
| `server_id` | string | Não | ID do servidor de análise a usar |
| `task` | string | Não | Tipo de tarefa OCR alvo |

### Resposta (200)

```json
{
  "file_id": 42,
  "target_lang": "en",
  "translated_text": "Translated full text...",
  "engine": "gemini-2.0-flash",
  "region_translations": [
    { "region_id": 0, "original": "Original text", "translated": "Translated text" }
  ]
}
```

### Erros

- `400` — `target_lang` não especificado
- `404` — Resultado OCR não encontrado
- `500` — Erro de execução de tradução

---

## GET /api/ocr/translations/<file_id>

Obtém a lista de resultados de tradução para um arquivo.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_id` | int | Sim | ID do arquivo (parâmetro de caminho) |
| `target_lang` | string | Não | Filtrar por código de idioma |

### Resposta

```json
{
  "file_id": 42,
  "translations": [
    {
      "target_lang": "en",
      "translated_text": "Translated text...",
      "engine": "gemini-2.0-flash",
      "region_translations": [...]
    }
  ]
}
```

---

## GET /api/ocr/overlay/<file_id>

Gera uma imagem de sobreposição com resultados OCR (ou traduções) renderizados sobre a imagem original.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_id` | int | Sim | ID do arquivo (parâmetro de caminho) |
| `mode` | string | Não | Modo de exibição. `translated` / `original` / `both`. Padrão: `translated` |
| `target_lang` | string | Não | Filtrar por idioma de tradução |
| `format` | string | Não | Formato de imagem de saída. `png` / `jpeg`. Padrão: `png` |
| `task` | string | Não | Tipo de tarefa OCR alvo |

### Resposta

- Content-Type: `image/png` ou `image/jpeg`
- Nome do arquivo: `ocr_overlay_{file_id}.{ext}`

### Erros

- `400` — Valor de modo / formato inválido
- `404` — Resultado OCR não encontrado / Arquivo não encontrado
- `500` — Erro de geração de imagem de sobreposição

---

## GET /api/ocr/export/<file_id>

Exporta um resultado OCR no formato especificado como download de arquivo.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_id` | int | Sim | ID do arquivo (parâmetro de caminho) |
| `format` | string | Não | Formato de exportação. `txt` / `md` / `json` / `pdf`. Padrão: `md` |
| `task` | string | Não | Tipo de tarefa OCR alvo |
| `include_translation` | string | Não | Se definido para qualquer valor, inclui traduções |
| `target_lang` | string | Não | Código de idioma da tradução a incluir |

### Resposta

- Content-Type: Tipo MIME apropriado para formato
- Content-Disposition: `attachment; filename=...`

### Erros

- `400` — Valor de formato inválido
- `404` — Resultado OCR não encontrado

---

## POST /api/ocr/export/batch

Exporta em lote resultados OCR para múltiplos arquivos. Suporta download ZIP ou salvamento direto no servidor.

### Taxa de Limite

WRITE

### Solicitação

```json
{
  "file_ids": [1, 2, 3],
  "format": "md",
  "output_dir": "",
  "overlay_mode": "translated",
  "target_lang": "",
  "include_translation": false
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `file_ids` | int[] | Sim | Array de IDs de arquivo alvo |
| `format` | string | Não | Formato de exportação. `txt` / `md` / `json` / `pdf` / `overlay`. Padrões da configuração de extensão |
| `output_dir` | string | Não | Caminho absoluto para salvamento no servidor. Se omitido, retorna download ZIP |
| `overlay_mode` | string | Não | Modo de sobreposição (quando `format=overlay`). `translated` / `original` / `both`. Padrão: `translated` |
| `target_lang` | string | Não | Código de idioma de tradução |
| `include_translation` | bool | Não | Se deve incluir traduções. Padrão: `false` |

### Resposta (Download ZIP)

- Content-Type: `application/zip`
- Nome do arquivo: `ocr_export_batch.zip` (formatos de texto) ou `ocr_overlay_batch.zip` (formato de sobreposição)

### Resposta (Salvamento no servidor)

```json
{
  "saved": 3,
  "errors": 0,
  "output_dir": "/path/to/output",
  "results": [
    { "file_id": 1, "path": "/path/to/output/ocr_1.md" }
  ],
  "error_details": []
}
```

### Erros

- `400` — `file_ids` vazio / valor de formato inválido / `output_dir` não é caminho absoluto
- `403` — `output_dir` é diretório proibido
- `404` — Nenhum resultado OCR encontrado

---

## POST /api/ocr/benchmark

Executa um benchmark OCR para medir precisão e desempenho. Requer casos de benchmark (pares de imagem + texto de verdade absoluta).

### Taxa de Limite

WRITE

### Solicitação

```json
{
  "task": "ocr",
  "server_id": "",
  "benchmark_dir": ""
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `task` | string | Não | Tipo de tarefa para benchmark. Padrão: `ocr` |
| `server_id` | string | Não | ID do servidor de análise a usar |
| `benchmark_dir` | string | Não | Caminho do diretório para casos de benchmark. Padrão: `extensions/builtin_ocr/benchmarks/` |

### Resposta (200)

```json
{
  "total_cases": 10,
  "avg_accuracy": 0.92,
  "avg_time_ms": 1500,
  "results": [
    {
      "image": "test1.png",
      "accuracy": 0.95,
      "time_ms": 1200
    }
  ]
}
```

### Erros

- `404` — Nenhum caso de benchmark encontrado
- `500` — Falha ao resolver engine OCR / Erro de execução de benchmark

---

## GET /api/ocr/benchmark/cases

Lista casos de benchmark disponíveis.

### Parâmetros

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `dir` | string | Não | Caminho do diretório para casos de benchmark |

### Resposta

```json
{
  "cases": [
    {
      "image": "test1.png",
      "task": "ocr",
      "language": "ja",
      "expected_length": 256,
      "tags": ["manga", "vertical"]
    }
  ],
  "total": 10
}
```

---

## GET /api/ocr/profiles

Lista perfis de modelo OCR com configurações de pontuação por tarefa.

### Parâmetros

Nenhum

### Resposta

```json
{
  "profiles": [
    {
      "model_prefix": "gemini-2.0-flash",
      "scores": {
        "ocr": 85,
        "ocr_document": 90,
        "ocr_manga": 60
      }
    }
  ]
}
```

---

## POST /api/ocr/profiles/fetch

Busca e mescla perfis de modelo publicados pela comunidade de uma URL.

### Taxa de Limite

WRITE

### Solicitação

```json
{
  "url": "https://example.com/ocr-profiles.json"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `url` | string | Sim | URL do JSON de perfil |

### Resposta (200)

```json
{
  "added": 3,
  "updated": 1,
  "total": 15
}
```

### Erros

- `400` — `url` não especificado
- `500` — Busca ou mesclagem falhou

---

## PUT /api/ocr/profiles/<model_prefix>

Atualiza manualmente pontuações para um perfil de modelo.

### Taxa de Limite

WRITE

### Solicitação

```json
{
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-----------|
| `model_prefix` | string | Sim | Prefixo de nome de modelo (parâmetro de caminho) |
| `scores` | object | Sim | Objeto com tipos de tarefa como chaves e pontuações (inteiros) como valores |

### Resposta

```json
{
  "model": "gemini-2.0-flash",
  "scores": {
    "ocr": 90,
    "ocr_document": 85,
    "ocr_manga": 70
  }
}
```

### Erros

- `400` — `scores` não especificado
