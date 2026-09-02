# API de Análise de Vídeo

APIs para gerenciar configuração de análise de vídeo e verificar status. Controla as configurações para extrair keyframes de arquivos de vídeo.

## GET /api/video-analysis/config

Obter a configuração atual de análise de vídeo. Retorna configurações salvas mescladas com valores padrão.

### Parâmetros

Nenhum

### Resposta

```json
{
  "config": {
    "enabled": true,
    "keyframe_count": 4,
    "strategy": "uniform",
    "scene_threshold": 0.4,
    "store_per_keyframe": false
  }
}
```

| Campo | Tipo | Padrão | Descrição |
|-------|------|---------|-------------|
| `enabled` | boolean | `true` | Se a análise de vídeo está habilitada |
| `keyframe_count` | int | `4` | Número de keyframes para extrair (1-16) |
| `strategy` | string | `"uniform"` | Estratégia de extração de keyframe. `uniform` (espaçado uniformemente), `scene` (detecção de mudança de cena), `single` (apenas um frame) |
| `scene_threshold` | float | `0.4` | Limiar de detecção de mudança de cena (0.0-1.0). Usado quando `strategy` é `scene` |
| `store_per_keyframe` | boolean | `false` | Se cada keyframe é armazenado individualmente |

## POST /api/video-analysis/config

Salvar configuração de análise de vídeo. Apenas campos especificados são atualizados; campos omitidos retêm seus valores existentes.

### Limite de Taxa

WRITE

### Requisição

```json
{
  "enabled": true,
  "keyframe_count": 8,
  "strategy": "scene",
  "scene_threshold": 0.3,
  "store_per_keyframe": false
}
```

Todos os campos são opcionais. Apenas campos especificados são atualizados.

| Parâmetro | Tipo | Obrigatório | Restrições | Descrição |
|-----------|------|----------|-------------|-------------|
| `enabled` | boolean | Não | - | Se a análise de vídeo está habilitada |
| `keyframe_count` | int | Não | 1-16 | Número de keyframes para extrair |
| `strategy` | string | Não | `uniform`, `scene`, ou `single` | Estratégia de extração de keyframe |
| `scene_threshold` | float | Não | 0.0-1.0 | Limiar de detecção de mudança de cena |
| `store_per_keyframe` | boolean | Não | - | Se cada keyframe é armazenado individualmente |

### Resposta

Retorna a configuração mesclada após salvar (mesmo formato que GET).

```json
{
  "config": {
    "enabled": true,
    "keyframe_count": 8,
    "strategy": "scene",
    "scene_threshold": 0.3,
    "store_per_keyframe": false
  }
}
```

### Erros

| Status | Código | Condição |
|--------|------|-----------|
| 400 | `invalid_json` | Corpo de requisição não é um objeto JSON |
| 400 | `invalid_value` | Erro de validação (tipo errado, valor fora do intervalo, estratégia inválida, etc.) |

## GET /api/video-analysis/status

Obter informações de status de análise de vídeo. Retorna disponibilidade de ffmpeg, contagem de arquivo de vídeo e número de arquivos com keyframes extraídos.

### Parâmetros

Nenhum

### Resposta

```json
{
  "ffmpeg": true,
  "video_files": 150,
  "files_with_keyframes": 42
}
```

| Campo | Tipo | Descrição |
|-------|------|-------------|
| `ffmpeg` | boolean | Se ffmpeg está disponível no sistema |
| `video_files` | int | Número total de arquivos de vídeo no banco de dados (excluindo soft-deleted). Extensões suportadas: `.mp4`, `.webm`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv` |
| `files_with_keyframes` | int | Número de arquivos que têm keyframes extraídos |
