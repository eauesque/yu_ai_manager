# Extensão de Fala para Texto

**Status**: Implementado (v3.28.0)
**Alvo**: `extensions/builtin_speech_to_text/`
**Propósito**: Transcrever arquivos de vídeo e áudio com detecção automática de backend

---

## Visão Geral

Esta Extensão extrai áudio de arquivos de vídeo e áudio e os transcreve usando modelos Whisper.
Ela seleciona automaticamente o backend ideal com base no hardware disponível e é executada em GPU ou CPU até mesmo sem um NPU Hailo.

---

## Prioridade de Backend

| Prioridade | Backend | Biblioteca | Hardware Alvo |
|--------|-------------|-----------|-----------------|
| P100 | `hailo` | `hailo_platform.genai` | Hailo-10H NPU |
| P70 | `torch-whisper-rocm` | `torch` (ROCm) + `transformers` | AMD GPU (ROCm/HIP) |
| P50 | `faster-whisper-cuda` | `faster-whisper` (CTranslate2) | NVIDIA GPU (CUDA) |
| P40 | `torch-whisper-cuda` | `torch` (CUDA) + `transformers` | NVIDIA GPU (CUDA) |
| P20 | `torch-whisper-cpu` | `torch` + `transformers` | CPU |
| P50 | `faster-whisper-cpu` | `faster-whisper` (CTranslate2) | CPU |
| P10 | `whisper-cpp` | `pywhispercpp` | CPU (mais leve) |

Em modo `auto`, o backend com prioridade mais alta entre aqueles retornando `is_available() == True` é selecionado.

---

## Configuração Específica de Ambiente

### Requisitos Comuns

- Python 3.11+
- ffmpeg (necessário para extrair áudio de vídeo)

### Hailo-10H NPU (Raspberry Pi AI HAT 2)

Nenhum pacote adicional é requerido (`hailo_platform` deve já estar instalado).
O modelo (`whisper-base` etc.) deve ter sido baixado via a Extensão GenAI.

```bash
# Baixar o modelo da UI de Extensão GenAI se não já presente
```

### GPU NVIDIA (CUDA)

```bash
# Recomendado: faster-whisper (leve, não requer PyTorch)
pip install faster-whisper

# GPU é usada automaticamente quando CUDA é detectado (float16)
# Volta para CPU automaticamente quando CUDA está ausente (int8)
```

### AMD GPU (ROCm)

```bash
# 1. Instale PyTorch edição ROCm
#    Oficial: https://pytorch.org/get-started/locally/
#    Exemplo (ROCm 6.x):
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.2

# 2. Instale transformers do HuggingFace
pip install transformers

# 3. Defina backend em config (auto-detectado em modo "auto")
#    Em configurações de Extensão: backend: "rocm" ou "auto"
```

**Mecanismo de detecção de ROCm**: PyTorch expõe ROCm como CUDA via HIP.
O sistema identifica ROCm quando `torch.version.hip` não é `None`.

**Requisitos de memória** (ROCm):

| Modelo | Estimativa de VRAM |
|--------|----------|
| tiny | ~150 MB |
| base | ~300 MB |
| small | ~500 MB |
| medium | ~1.5 GB |

### Apenas CPU

```bash
# Opção 1: faster-whisper (recomendado, rápido com quantização int8)
pip install faster-whisper

# Opção 2: whisper.cpp (mais leve, não requer PyTorch)
pip install pywhispercpp

# Opção 3: torch + transformers (uso geral mas pesado)
pip install torch transformers
```

**Estimativas de desempenho de CPU** (modelo base, 1 minuto de áudio):

| Backend | RPi 5 | x86 (4 core) |
|---|---|---|
| faster-whisper (int8) | ~30 sec | ~5 sec |
| whisper.cpp | ~40 sec | ~8 sec |
| torch (float32) | ~90 sec | ~15 sec |

---

## Configuração

Configure via página de configurações de Extensão (`/ext/speech-to-text/`) ou config.json:

| Item | Escolhas | Padrão | Descrição |
|------|--------|-----------|------|
| `backend` | auto / hailo / cuda / rocm / cpu | auto | Backend de inferência |
| `model_size` | tiny / base / small / medium | base | Tamanho de modelo Whisper |
| `default_language` | Código BCP-47 (ja, en, etc.) | ja | Idioma padrão |

---

## Endpoints de API

Todos os endpoints estão sob prefixo `/ext/speech-to-text`.

### POST `/api/s2t/transcribe`

Transcreve áudio WAV carregado.

- **Content-Type**: `multipart/form-data`
- **Parâmetros**: `audio` (file), `language` (opcional)
- **Resposta**: `{ status, text, segments, language, sample_rate, backend }`

### POST `/api/s2t/transcribe-video`

Transcreve um arquivo de vídeo/áudio registrado em DB. Resultados são salvos como anotações.

- **Corpo**: `{ file_id: int, language?: string }`
- **Resposta**: `{ status, text, segments, language, backend }`
- **Anotação**: `source="s2t"`, chaves: `transcript`, `transcript_segments`, `transcript_backend`

### POST `/api/s2t/batch-transcribe`

Transcrição em lote de múltiplos arquivos (executa em background).

Escolha **um** de três métodos de entrada (mutuamente exclusivos):

#### Método 1: Lista de File ID (Legado)

```json
{
  "file_ids": [123, 456, 789],
  "language": "ja"
}
```

#### Método 2: Diretório

Detecta automaticamente arquivos de vídeo/áudio no diretório especificado e processa apenas aqueles registrados em DB.

```json
{
  "directory": "/path/to/videos/",
  "recursive": true,
  "language": "en"
}
```

- `recursive` (padrão: `true`): Pesquise recursivamente subdiretórios
- Extensões alvo: `.webm`, `.mp4`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv`, `.mp3`, `.wav`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.flac`

#### Método 3: Lista de Texto/CSV

Especifique um arquivo de texto ou CSV listando caminhos de arquivo.

```json
{
  "list_file": "/path/to/targets.txt",
  "language": "ja"
}
```

**Formato de arquivo de texto** (`.txt` etc.):
```
# Linhas de comentário (linhas começando com # são ignoradas)
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```

**Formato CSV** (`.csv`):
```csv
/mnt/videos/interview_01.mp4
/mnt/videos/interview_02.webm
/mnt/audio/podcast_03.mp3
```
A primeira coluna é usada como caminho de arquivo. Linhas começando com `#` são puladas.

#### Opções Comuns

| Parâmetro | Tipo | Padrão | Descrição |
|-----------|---|-----------|------|
| `language` | string | Valor de config (típicamente `ja`) | Código de idioma (veja abaixo) |
| `recursive` | bool | `true` | Método de diretório apenas: pesquisa recursiva de subdiretório |

#### Limites e Restrições

- Máximo de arquivos alvo: **500**
- Apenas arquivos registrados em DB (tabela `files`) são processados
- Arquivos deletados (`is_deleted=1`) são excluídos

#### Exemplo de Resposta

```json
{
  "status": "started",
  "total": 15,
  "mode": "directory",
  "directory": "/mnt/videos/",
  "recursive": true,
  "files_found": 23,
  "matched_in_db": 15
}
```

- **Eventos SSE**: `s2t.batch_start`, `s2t.batch_progress`, `s2t.batch_complete`

### GET `/api/s2t/transcript/<file_id>`

Recupera resultados de transcrição salvos. Ambos `source="s2t"` e `source="hailo:s2t"` são verificados para compatibilidade retroativa.

### GET `/api/s2t/status`

Retorna status de backend e uma lista de backends disponíveis.

---

## Ferramentas MCP

| Nome da Ferramenta | Descrição |
|---------|------|
| `s2t_status` | Obter status de backend |
| `s2t_transcribe_video` | Transcrever um único arquivo de vídeo |
| `s2t_batch_transcribe` | Iniciar transcrição em lote (file_ids / directory / list_file) |
| `s2t_get_transcript` | Recuperar transcrição salva |

### Parâmetros de `s2t_batch_transcribe`

| Parâmetro | Tipo | Requerido | Descrição |
|-----------|---|------|------|
| `file_ids` | list[int] | *1 | Lista de file ID (máx 500) |
| `directory` | string | *1 | Caminho de diretório (auto-detecta vídeo/áudio) |
| `list_file` | string | *1 | Caminho de arquivo texto/CSV |
| `recursive` | bool | | Método de diretório apenas. Pesquisa recursiva de subdiretório (padrão true) |
| `language` | string | | Código de idioma. Vazio = padrão de config |
| `expected_count` | int | | Para detectar truncamento de file_ids |

*1: Especifique exatamente um de `file_ids`, `directory`, ou `list_file` (mutuamente exclusivos)

---

## Estrutura de Arquivo

```
extensions/builtin_speech_to_text/
  extension.json                      # Manifesto
  speech_to_text_ext.py               # Ponto de entrada (Blueprint)
  s2t_routes.py                       # Routes de API de arquivo único
  s2t_batch_routes.py                 # Routes de API de lote
  core_impl/
    base.py                           # Classe base abstrata S2TBackend
    backend_hailo.py                  # Hailo-10H NPU
    backend_faster_whisper.py         # faster-whisper (CUDA/CPU)
    backend_torch_whisper.py          # PyTorch transformers (ROCm/CUDA/CPU)
    backend_whisper_cpp.py            # whisper.cpp (CPU)
    backend_registry.py               # Auto-detecção + gerenciamento singleton
  templates/speech_to_text/
    s2t.html                          # Página de UI
mcp_server/
  s2t_tools.py                        # Definições de ferramenta MCP
```

---

## Códigos de Idioma Suportados

Códigos de idioma maiores (BCP-47) suportados por Whisper:

| Código | Idioma | Código | Idioma |
|--------|------|--------|------|
| `ja` | Japonês | `en` | Inglês |
| `zh` | Chinês | `ko` | Coreano |
| `de` | Alemão | `fr` | Francês |
| `es` | Espanhol | `it` | Italiano |
| `pt` | Português | `ru` | Russo |
| `ar` | Árabe | `hi` | Hindi |
| `th` | Tailandês | `vi` | Vietnamita |
| `nl` | Holandês | `tr` | Turco |
| `pl` | Polonês | `uk` | Ucraniano |
| `id` | Indonésio | `sv` | Sueco |

Outros idiomas suportados por Whisper também podem ser especificados. Uma string vazia dispara detecção automática.
O idioma padrão pode ser alterado via configuração de Extensão `default_language` (valor inicial: `ja`).

---

## Limitações Conhecidas

- **Atraso de primeiro carregamento**: transformers / faster-whisper baixam modelos do HuggingFace Hub (base: ~150MB). A primeira execução pode levar vários minutos
- **Modelos HEF de Hailo**: Devem ser baixados via Extensão GenAI. A Extensão S2T em si não tem funcionalidade de download
- **Memória**: O modelo medium pode causar erros de falta de memória em RPi 5 (8GB). O modelo base é recomendado
- **Concorrência**: Backends são gerenciados como singletons. Requisições chegando durante processamento em lote compartilham a mesma instância
- **Formato de entrada**: WAV (PCM s16le, mono, 16kHz) é assumido. Arquivos de vídeo são automaticamente convertidos via ffmpeg
- **Entrada de lote**: Os métodos de diretório / list_file apenas processam arquivos registrados em DB. Arquivos não-digitalizados devem primeiro ser registrados via `start_scan`

---

## Transcrição de Streaming em Tempo Real

Transcreva áudio de rádio internet, streams RTSP e arquivos de vídeo em tempo real e exiba legendas na WebUI.

### Dois Modos

- **Modo Chunk** (padrão): Divide áudio em chunks usando detecção de silêncio baseada em RMS. Compatível com todos os backends (Hailo/CUDA/CPU). Resultados são exibidos após cada enunciado terminar.
- **Modo Live**: Executa transcrição incremental usando Silero VAD do faster-whisper. Exibe resultados interim enquanto discurso ainda está em andamento. Requer um backend ONNX/faster-whisper.

### Fontes de Entrada Suportadas

- Streams HTTP/HTTPS (rádio internet, etc.)
- Câmeras RTSP
- Streams RTMP

### Endpoints de API

| Endpoint | Método | Função |
|---|---|---|
| `/api/s2t/stream/start` | POST | Iniciar streaming (`source_url`, `language`, `mode`) |
| `/api/s2t/stream/stop` | POST | Parar streaming |
| `/api/s2t/stream/status` | GET | Obter status |
| `/api/s2t/stream/transcript` | GET | Obter transcrição completa |
| `/api/s2t/stream/export/txt` | GET | Exportar como texto |
| `/api/s2t/stream/export/srt` | GET | Exportar como legendas SRT |

### Eventos SSE

| Evento | Descrição |
|---|---|
| `s2t.stream_chunk` | Texto finalizado |
| `s2t.stream_interim` | Texto interim (Modo Live apenas) |
| `s2t.stream_complete` | Streaming completo |

### Ferramentas MCP

| Ferramenta | Descrição |
|---|---|
| `s2t_stream_start(source_url, language)` | Iniciar streaming |
| `s2t_stream_stop()` | Parar streaming |
| `s2t_stream_status()` | Obter status |
| `s2t_stream_transcript()` | Obter transcrição completa |

### Configuração de Streaming

Itens configuráveis em `extension.json`:

| Item | Descrição | Padrão |
|---|---|---|
| `stream_chunk_min_sec` | Comprimento mínimo de chunk em Chunk mode (segundos) | — |
| `stream_chunk_max_sec` | Comprimento máximo de chunk em Chunk mode (segundos) | — |
| `stream_silence_threshold` | Threshold RMS para detecção de silêncio | — |
| `stream_silence_ms` | Duração de silêncio para detecção (milissegundos) | — |
| `live_interval_sec` | Intervalo de transcrição em Modo Live (segundos) | — |
