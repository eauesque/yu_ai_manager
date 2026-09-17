# API de Rasterização SVG

API para converter imagens vetoriais SVG em bitmaps PNG/WebP.
Projetado para integração com pipeline img2img — os dados de imagem base64 retornados podem ser passados diretamente para NovelAI Bridge ou SD WebUI Bridge.

## GET /api/svg/info

Verificar disponibilidade de rasterização SVG.

- **Limite de taxa**: Nenhum (GET)

### Resposta

```json
{
  "available": true,
  "backend": "resvg"
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `available` | bool | Se a rasterização está disponível |
| `backend` | string \| null | Backend ativo (`"resvg"` ou `null`) |

---

## POST /api/svg/rasterize

Rasterizar um SVG para um bitmap PNG/WebP.

- **Limite de taxa**: HEAVY

### Corpo da Requisição

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `file_id` | int | *1 | ID de arquivo SVG do banco de dados |
| `svg_path` | string | *1 | Caminho absoluto para um arquivo SVG |
| `svg_data` | string | *1 | String XML SVG inline |
| `width` | int | Não | Largura de saída (padrão: 1024) |
| `height` | int | Não | Altura de saída (padrão: 1024) |
| `format` | string | Não | `"png"` ou `"webp"` (padrão: `"png"`) |
| `background` | string | Não | Cor de background (ex: `"#ffffff"`). Transparente se omitido |

> *1: Forneça exatamente um de `file_id`, `svg_path`, ou `svg_data`.

### Exemplo de Requisição

```json
{
  "file_id": 123,
  "width": 832,
  "height": 1216,
  "format": "png",
  "background": "#ffffff"
}
```

### Resposta

```json
{
  "ok": true,
  "base64": "iVBORw0KGgo...",
  "width": 832,
  "height": 1216,
  "format": "png",
  "size_bytes": 45678
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `ok` | bool | Flag de sucesso |
| `base64` | string | Dados PNG/WebP codificados em base64 |
| `width` | int | Largura de saída real |
| `height` | int | Altura de saída real |
| `format` | string | Formato de saída |
| `size_bytes` | int | Tamanho binário em bytes |

### Resposta de Erro

```json
{
  "ok": false,
  "error": "resvg is not installed (pip install resvg)"
}
```

---

## Integração MCP

Use Claude Desktop para construir um pipeline SVG → img2img:

```
# Passo 1: Rasterizar o SVG
svg_rasterize(file_id=123, width=832, height=1216, background="#ffffff")

# Passo 2: Passar o base64 retornado para img2img
nai_generate(prompt="icon, detailed illustration, ...", image=<base64>, strength=0.7)
```

### Ferramentas MCP

| Ferramenta | Descrição |
|------|-------------|
| `svg_info` | Verificar disponibilidade de rasterização |
| `svg_rasterize` | Rasterizar SVG para PNG/WebP |

---

## Dependências

| Pacote | Licença | Propósito |
|---------|---------|---------|
| `resvg` | MIT | Renderizador SVG baseado em Rust (multi-plataforma) |

Se `resvg` não estiver instalado, miniaturas mostram um placeholder e a API retorna HTTP 501.

```bash
pip install resvg
```
