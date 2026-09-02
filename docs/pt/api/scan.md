# API de Scan

APIs para scan de arquivo e gerenciamento de raiz de scan.

## Controle de Scan

### POST /api/scan/start

Iniciar um scan.

### Requisição

```json
{
  "root_indices": [0, 1],
  "force": false
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `root_indices` | int[] | Índices de raízes para scan (omita para todas as raízes) |
| `force` | bool | Fazer scan novamente de arquivos existentes |

### Resposta

```json
{
  "ok": true,
  "message": "Scan started"
}
```

### GET /api/scan/status

Recuperar progresso do scan.

### Resposta

```json
{
  "scanning": true,
  "progress": 45,
  "total": 1500,
  "current_file": "/images/output/00042.png",
  "errors": 0,
  "started_at": 1709500000
}
```

### POST /api/scan/cancel

Cancelar um scan em execução.

### GET /api/scan/interrupted

Recuperar informações sobre um scan interrompido.

### POST /api/scan/resume

Retomar um scan interrompido.

### POST /api/scan/dismiss

Descartar o estado de scan interrompido.

## CLI do Scan Worker

Desde v3.27.0, scans são executados em um processo separado (worker).
O worker pode ser controlado diretamente do CLI além da API WebUI.

```bash
# Iniciar um scan
python -m core.scan.scan_worker start --db ./tags.db --root /path/to/images [--scan-zips] [--force] [--resume]

# Parar um scan (SIGTERM -> graceful shutdown)
python -m core.scan.scan_worker stop

# Verificar status
python -m core.scan.scan_worker status
```

### Arquivos IPC

| Arquivo | Conteúdo |
|------|---------|
| `/tmp/yu-scan/worker.pid` | PID do Worker |
| `/tmp/yu-scan/progress.json` | Progresso (JSON: running, phase, current, total, percent, message, detail, error) |

A WebUI sonda este arquivo de progresso e retransmite os dados através de `GET /api/scan/status` e eventos SSE (`scan.progress`, `scan.complete`).

## Erros de Scan

### GET /api/scan-errors

Lista de erros que ocorreram durante o scanning.

| Parâmetro | Tipo | Descrição |
|-----------|------|-------------|
| `type` | string | Filtro de tipo de erro |
| `resolved` | bool | Apenas erros resolvidos |
| `limit` | int | Número de resultados |

### POST /api/scan-errors/<id>/resolve

Marcar um erro como resolvido.

### POST /api/scan-errors/clear

Deletar todos os erros resolvidos de uma vez.

## Gerenciamento de Raiz de Scan

### GET /api/scan-roots

Listar raízes de scan registradas.

### Resposta

```json
{
  "roots": [
    {
      "path": "O:\\webui\\outputs",
      "enabled": true,
      "file_count": 15000
    }
  ]
}
```

### POST /api/scan-roots

Adicionar uma raiz de scan.

```json
{
  "path": "O:\\webui\\outputs"
}
```

### PUT /api/scan-roots/<index>

Atualizar uma raiz de scan (mudar caminho, alternar habilitado/desabilitado).

### DELETE /api/scan-roots/<index>

Deletar uma raiz de scan.

## Backfill de Hash

### POST /api/hash-backfill/start

Iniciar computação de hash de background para arquivos existentes.

### GET /api/hash-backfill/status

Recuperar progresso.

### POST /api/hash-backfill/cancel

Cancelar a computação.

## Trabalhos de Background

### GET /api/jobs/status

Status de todos os trabalhos de background. Usado para exibição de banner de UI.

```json
{
  "jobs": [
    {
      "type": "scan",
      "status": "running",
      "progress": 45,
      "total": 1500
    }
  ]
}
```
