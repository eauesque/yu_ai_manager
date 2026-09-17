# YOLO Stream API

APIs para processamento de stream em tempo real YOLO. Fornece gerenciamento de fonte de stream, entrega MJPEG, regras de detecção e funcionalidade de gravação/snapshot.

Todos os endpoints POST/PUT/DELETE requerem o header `X-Requested-With` (exceto ao usar API Key de Bearer).

---

## Gerenciamento de Fonte

### GET /ext/hailo-yolo/api/stream/sources

Listar todas as fontes de stream registradas.

#### Resposta

```json
{
  "status": "ok",
  "sources": [
    {
      "id": "cam1",
      "name": "Front Camera",
      "url": "rtsp://192.168.1.100:554/stream",
      "type": "rtsp",
      "state": "running",
      "resolution": { "width": 1920, "height": 1080 },
      "fps": 25.0,
      "frame_count": 15420,
      "error": null,
      "viewers": 1
    }
  ]
}
```

### POST /ext/hailo-yolo/api/stream/sources

Adicionar uma nova fonte de stream.

#### Solicitação

```json
{
  "id": "cam2",
  "url": "rtsp://192.168.1.101:554/stream",
  "name": "Back Camera"
}
```

| Parâmetro | Tipo | Obrigatório | Descrição |
|-----------|------|----------|-------------|
| `id` | string | Sim | Identificador de fonte único |
| `url` | string | Sim | URL RTSP ou índice de dispositivo |
| `name` | string | Não | Nome de exibição |

#### Resposta (201)

```json
{ "status": "ok", "source": { "id": "cam2", "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/sources/\<id\>

Remover a fonte especificada.

#### Resposta

```json
{ "status": "ok" }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/start

Iniciar captura para a fonte especificada.

#### Resposta

```json
{ "status": "ok", "source": { "id": "cam1", "state": "running", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/stop

Parar captura para a fonte especificada.

#### Resposta

```json
{ "status": "ok", "source": { "id": "cam1", "state": "stopped", "..." : "..." } }
```

### POST /ext/hailo-yolo/api/stream/sources/\<id\>/test

Testar conexão com uma fonte. Se uma URL for fornecida no corpo da solicitação, essa URL é testada; caso contrário, a URL de fonte existente é usada.

#### Solicitação

```json
{ "url": "rtsp://192.168.1.100:554/stream" }
```

#### Resposta

```json
{ "ok": true, "resolution": { "width": 1920, "height": 1080 } }
```

### GET /ext/hailo-yolo/api/stream/devices

Detectar câmeras USB conectadas.

#### Resposta

```json
{
  "status": "ok",
  "devices": [
    { "index": 0, "name": "USB Camera", "resolution": null }
  ]
}
```

> **Nota:** A resposta nativa em Rust enumera câmeras USB apenas no Linux e nunca as abre; `resolution` é sempre `null`. Windows e macOS retornam `devices: []` e não aceitam registro por índice numérico de câmera.
>
> O fan-out de eventos também é reduzido: não há entrega wildcard implícita a extensões webhook configuradas, relay LAN quando um nome de evento personalizado corresponde a `RELAY_TYPES`, nem receptor MCP dedicado. `mcp_event` é entregue pelo hub SSE compartilhado.

---

## Video Stream

### GET /ext/hailo-yolo/api/stream/\<id\>/mjpeg

Retorna um stream MJPEG com sobreposição de detecção YOLO. Máximo 4 visualizadores simultâneos por fonte.

- **Content-Type**: `multipart/x-mixed-replace; boundary=frame`

---

## Gerenciamento de Regra

### GET /ext/hailo-yolo/api/stream/rules

Listar todas as regras.

#### Resposta

```json
{
  "status": "ok",
  "rules": [
    {
      "id": "rule1",
      "name": "Person detection",
      "enabled": true,
      "conditions": {
        "classes": ["person"],
        "min_confidence": 0.7,
        "sources": ["cam1"],
        "schedule": { "start": "22:00", "end": "06:00", "days": ["mon","tue","wed","thu","fri","sat","sun"] }
      },
      "cooldown_sec": 60,
      "actions": [
        { "type": "snapshot", "save_dir": "./detections/snapshots" },
        { "type": "record", "save_dir": "./detections/videos", "duration_sec": 30, "extend_mode": "fixed" },
        { "type": "webhook", "url": "https://example.com/hook", "secret": "hmac-key" },
        { "type": "sse", "channel": "yolo_stream" },
        { "type": "mcp_event", "event": "yolo_stream.detection" }
      ]
    }
  ]
}
```

### POST /ext/hailo-yolo/api/stream/rules

Adicionar uma nova regra. Passar o JSON completo da regra no corpo da solicitação.

#### Resposta (201)

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### PUT /ext/hailo-yolo/api/stream/rules/\<id\>

Atualizar uma regra existente.

#### Resposta

```json
{ "status": "ok", "rule": { "..." : "..." } }
```

### DELETE /ext/hailo-yolo/api/stream/rules/\<id\>

Excluir uma regra.

#### Resposta

```json
{ "status": "ok" }
```

---

## Gravações e Snapshots

### GET /ext/hailo-yolo/api/stream/recordings

Listar arquivos de gravação.

#### Resposta

```json
{
  "status": "ok",
  "recordings": [
    { "filename": "cam1_20260328_220500.mp4", "path": "./detections/videos/cam1_20260328_220500.mp4", "size_bytes": 5242880, "created_at": "2026-03-28T22:05:00" }
  ]
}
```

### GET /ext/hailo-yolo/api/stream/snapshot/\<filename\>

Servir um arquivo de imagem de snapshot.

---

## Status

### GET /ext/hailo-yolo/api/stream/status

Obter status geral do pipeline e fonte.

#### Resposta

```json
{
  "status": "ok",
  "pipeline": { "running": true, "queue_size": 2, "fps": 24.8 },
  "sources": [ { "id": "cam1", "state": "running" } ],
  "rules_count": 3,
  "recorder": { "active_recordings": 1 }
}
```

---

## Estrutura JSON de Regra

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `id` | string | Identificador de regra único |
| `name` | string | Nome da regra |
| `enabled` | boolean | Se a regra está ativa |
| `conditions.classes` | string[] | Classes de detecção alvo (ex. `["person"]`) |
| `conditions.min_confidence` | number | Limite de confiança mínima (0.0-1.0) |
| `conditions.sources` | string[] | IDs de fonte alvo. Todas as fontes se omitido |
| `conditions.schedule` | object | Agendamento (`start`, `end`, `days`) |
| `cooldown_sec` | number | Cooldown em segundos |
| `actions` | object[] | Array de ações |

### Tipos de Ação

| type | Descrição |
|------|-------------|
| `snapshot` | Salvar um snapshot na detecção |
| `record` | Iniciar gravação na detecção |
| `webhook` | Enviar notificação para URL webhook (com assinatura HMAC) |
| `sse` | Enviar evento para canal SSE |
| `mcp_event` | Disparar um evento MCP |
