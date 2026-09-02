# API de Arquivos

APIs para recuperar detalhes de arquivo, miniaturas e mídia original.

## GET /api/file/<id>

Recuperar metadados detalhados para um arquivo.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `id` | int | ID do arquivo (parâmetro de caminho) |

### Resposta

```json
{
  "id": 42,
  "path": "/images/output/00042.png",
  "filename": "00042.png",
  "size": 1234567,
  "mtime": 1709500000,
  "width": 1024,
  "height": 1536,
  "meta_type": "a1111_png",
  "model_name": "animagine-xl-3.1",
  "positive": "1girl, landscape",
  "negative": "low quality",
  "steps": 28,
  "sampler": "Euler a",
  "cfg_scale": 7.0,
  "seed": 1234567890,
  "rating": 4,
  "is_favorite": true,
  "tags": ["landscape"],
  "collections": [1, 3],
  "hash_md5": "abc123...",
  "hash_phash": "def456...",
  "analysis": { "description": "A scenic landscape..." }
}
```

## GET /api/thumbnail/<id>

Imagem em miniatura (WebP). Suporta cache ETag.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `id` | int | ID do arquivo |
| `size` | int | Tamanho da miniatura (padrão 300) |

### Resposta

- Content-Type: `image/webp`
- Suporte ETag / If-None-Match (304 Not Modified)
- Cache: 24 horas

## GET /api/original/<id>

Transmitir o arquivo original. Também suporta arquivos dentro de arquivos ZIP.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `id` | int | ID do arquivo |

### Resposta

- Content-Type: Tipo MIME do arquivo
- Content-Disposition: `inline`
- Suporte para requisições de intervalo (para busca de vídeo)

## POST /api/convert

Conversão de formato de prompt (A1111 <-> NAI).

### Requisição

```json
{
  "prompt": "1girl, (masterpiece:1.2)",
  "direction": "a1111_to_nai"
}
```

### Resposta

```json
{
  "converted": "1girl, {{masterpiece}}",
  "direction": "a1111_to_nai"
}
```

## GET /api/container-thumb-ids

Lista de IDs de miniatura para um contêiner (pasta/ZIP), excluindo entradas já em cache.

### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `keys` | string | Chaves de contêiner (separadas por vírgula) |
