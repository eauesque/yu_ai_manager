# Protocolo QR YU v1 — Especificação de Payload Unificada

**Versão:** 1.0
**Data:** 2026-02-23
**Aplicação alvo:** YU AI Manager (TagDB)

---

## Visão Geral

YU AI Manager suporta compartilhamento de prompt e diagnóstico de erros via códigos QR.
Este documento fornece uma especificação unificada para o formato de payload do QR.

### Bibliotecas Usadas

| Propósito | Biblioteca | Versão |
|------|-----------|-----------|
| Geração QR | QRCode.js | 1.0.0 |
| Leitura QR | jsQR | 1.4.0 |

### Limites de Capacidade QR

- Caracteres máximos: **2,953** (nível de correção de erro M)
- Acima de 2,500 caracteres: o JSON de meta é minificado e retentado
- Acima de 2,953 caracteres: erro (`qr.info.too_long`)

---

## Tipo de Payload 1 — Compartilhamento de Prompt

### Origem

- `GET /api/share/<file_id>` -> Python `build_share_data_payload()`
- `routes/share_ops/payload_build.py`

### Schema JSON

```json
{
  "v":   "1.0",
  "t":   "prompt",
  "p":   "<positive prompt>",
  "n":   "<negative prompt>",
  "src": "TagDB",
  "m":   "<model name>",
  "s":   "<seed>",
  "st":  "<steps>",
  "cfg": "<CFG scale>",
  "sa":  "<sampler>",
  "sz":  "<WxH>"
}
```

### Definições de Campo

| Chave | Tipo | Requerido | Descrição | Limite |
|------|-----|------|------|------|
| `v` | string | ✅ | Versão do protocolo. Atualmente `"1.0"` | — |
| `t` | string | ✅ | Tipo de payload. Atualmente sempre `"prompt"` | — |
| `p` | string | ✅ | Prompt positivo | 2,000 chars |
| `n` | string | ✅ | Prompt negativo | 1,000 chars |
| `src` | string | ✅ | Identificador do emissor. Atualmente sempre `"TagDB"` | — |
| `m` | string | — | Nome do modelo | — |
| `s` | string | — | Valor da seed | — |
| `st` | string | — | Contagem de passos | — |
| `cfg` | string | — | Escala CFG | — |
| `sa` | string | — | Nome do sampler | — |
| `sz` | string | — | Tamanho da imagem em formato `"WxH"` | — |

---

## Modos QR — 4 Tipos

### Modo `positive`

```
qrText = shareData.p
```

- Conteúdo: Apenas texto de prompt positivo
- Caso de uso: Compartilhamento direto de texto de prompts

### Modo `negative`

```
qrText = shareData.n
```

- Conteúdo: Apenas texto de prompt negativo

### Modo `meta`

```
qrText = JSON.stringify(shareData, null, 0)
```

- Conteúdo: O payload JSON de Compartilhamento de Prompt completo, compactado
- Recua para `JSON.stringify` bem formatado quando o resultado excede 2,500 caracteres

### Modo `url`

```
encoded = btoa(unescape(encodeURIComponent(JSON.stringify(shareData))))
qrText  = "{origin}/share?data={encoded}"
```

- Conteúdo: Uma URL para a página de compartilhamento do YU AI Manager
- Desabilitado em localhost (`localhost` / `127.0.0.1`)

---

## Tipo de Payload 2 — Diagnóstico de Erro

### Origem

- Gerado em erros HTTP -> `_render_error_page()`
- `core/web/app_factory_handlers.py`

### Schema JSON

```json
{
  "s": "<HTTP status code>",
  "p": "<request path>",
  "v": "<APP_VERSION>"
}
```

### Definições de Campo

| Chave | Tipo | Descrição | Limite |
|------|-----|------|------|
| `s` | string | Código de status HTTP (`"404"`, `"500"`, etc.) | — |
| `p` | string | Caminho da requisição | 80 chars |
| `v` | string | Versão da aplicação (do arquivo `APP_VERSION`) | — |

---

## Procedimento de Decodificação de Compartilhamento de URL

Decodificação na página de compartilhamento (`/share?data=...`):

```javascript
const encoded = new URL(location).searchParams.get('data');
const json    = decodeURIComponent(escape(atob(encoded)));
const data    = JSON.parse(json);
```

---

## Parâmetros de Geração QR

```javascript
new QRCode(container, {
  text:         qrText,
  width:        200,   // 180 em páginas de erro
  height:       200,   // 180 em páginas de erro
  colorDark:    '#000000',
  colorLight:   '#ffffff',
  correctLevel: QRCode.CorrectLevel.M,  // Correção de erro de 15%
});
```

---

## Extensões Futuras (v1.x)

| Recurso | Status | Notas |
|------|------|------|
| Exportação QR de coleção (múltiplas imagens) | Não implementado | Planejado como tipo de payload 3 |
| Tipo `t: "collection"` | Não definido | Lista de file ID + nome de coleção |
| Compressão (gzip + Base64) | Não implementado | Alternativa para prompts excedendo 2,953 caracteres |

---

## Arquivos de Implementação

| Arquivo | Papel |
|----------|------|
| `routes/share.py` | Share API Blueprint |
| `routes/share_ops/payload_build.py` | Geração de payload |
| `routes/share_ops/prompt_extract.py` | Extração de dados de prompt |
| `core/web/app_factory_handlers.py` | Geração de dados QR de erro |
| `static/js/runtime/tools/runtime-tools-qr-core.js` | Construção e renderização QR |
| `static/js/runtime/tools/runtime-tools-qr.js` | Handlers de UI QR |
| `static/js/share/share-qr.js` | Decodificação de imagem QR |
| `static/js/share/share-page.js` | Exibição de página de compartilhamento |
| `static/vendor/qrcode.min.js` | Biblioteca QRCode.js |
| `static/vendor/jsQR.min.js` | Biblioteca jsQR |
