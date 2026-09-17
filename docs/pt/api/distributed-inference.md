# API de Inferência Distribuída

REST API para o registro de servidor de inferência distribuída. Distribui cargas de trabalho de indexação semântica CLIP em múltiplos nós usando uma estratégia de fila compartilhada.

## Endpoints

### GET /api/inference-servers

Retorna a lista de servidores registrados e o modo de dispatch atual.

**Resposta:**

```json
{
  "status": "ok",
  "mode": "single",
  "servers": [
    {
      "id": 1,
      "name": "Hailo Worker 1",
      "endpoint_url": "http://192.168.1.10:9090",
      "inference_types": ["clip"],
      "priority": 50,
      "enabled": true,
      "timeout": 30
    }
  ]
}
```

- `mode`: `"single"` | `"parallel"` | `"idle_first"`
- `servers`: array de objetos de configuração de servidor

---

### POST /api/inference-servers

Registrar um novo servidor de inferência.

**Corpo da Requisição:**

| Campo | Tipo | Obrigatório | Padrão | Descrição |
|---|---|---|---|---|
| `name` | string | ✓ | — | Nome de exibição |
| `endpoint_url` | string | ✓ | — | URL base do Worker |
| `inference_types` | string[] | — | `["clip"]` | Tipos de inferência suportados |
| `priority` | int | — | `50` | Prioridade (valor menor = prioridade maior) |
| `bearer_token` | string | — | — | Token de autenticação |
| `timeout` | int | — | `30` | Timeout da requisição em segundos |

**Resposta:**

```json
{
  "status": "ok",
  "server": { ... }
}
```

---

### PUT /api/inference-servers/{server_id}

Atualizar a configuração de um servidor existente. Aceita um corpo parcial com os mesmos campos que POST.

---

### DELETE /api/inference-servers/{server_id}

Remover um servidor do registro.

**Resposta:**

```json
{ "status": "ok" }
```

---

### POST /api/inference-servers/{server_id}/test

Executar uma verificação de saúde no servidor especificado.

**Resposta:**

```json
{
  "status": "ok",
  "server_id": 1,
  "healthy": true,
  "latency_ms": 12.5
}
```

---

### GET /api/inference-servers/health

Executar verificações de saúde em todos os servidores habilitados simultaneamente.

**Resposta:**

```json
{
  "status": "ok",
  "results": [
    { "server_id": 1, "healthy": true, "latency_ms": 12.5 },
    { "server_id": 2, "healthy": false, "error": "Connection refused" }
  ]
}
```

---

### POST /api/inference-servers/mode

Definir o modo de dispatch.

**Corpo da Requisição:**

| Campo | Tipo | Obrigatório | Descrição |
|---|---|---|---|
| `mode` | string | ✓ | `"single"` \| `"parallel"` \| `"idle_first"` |

**Resposta:**

```json
{ "status": "ok", "mode": "parallel" }
```

---

## Modos de Dispatch

| Modo | Descrição |
|---|---|
| `single` | Use apenas o servidor com maior prioridade (valor de prioridade mais baixo) |
| `parallel` | Distribuir trabalho em todos os servidores habilitados usando uma fila compartilhada |
| `idle_first` | Verificação de saúde primeiro, depois distribuir entre servidores responsivos apenas |

## Indexação Semântica Distribuída

Adicione `distributed: true` ao corpo da requisição `POST /api/index/start` (extensão de busca semântica) para habilitar indexação distribuída usando servidores de worker registrados.

```json
{
  "batch_size": 32,
  "distributed": true
}
```

## Configuração de Worker Server

```bash
python deploy/hailo_tagger_server.py --port 9090
```

Endpoints suportados:

| Caminho | Descrição |
|---|---|
| `GET /health` | Verificação de saúde |
| `POST /tag` | Inferência WD-Tagger |
| `POST /clip-encode` | Codificação de vetor CLIP |

## Ferramentas MCP

| Ferramenta | Descrição |
|---|---|
| `inference-servers-list` | Listar servidores e obter modo atual |
| `inference-server-add` | Registrar um novo servidor |
| `inference-server-update` | Atualizar configuração de servidor |
| `inference-server-remove` | Remover um servidor |
| `inference-server-health` | Executar verificações de saúde |
| `inference-dispatch-mode-set` | Definir modo de dispatch |
