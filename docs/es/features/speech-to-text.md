# Extensión de Voz a Texto

**Estado**: Implementado (v3.28.0)
**Objetivo**: `extensions/builtin_speech_to_text/`
**Propósito**: Transcribir archivos de video y audio con detección automática de backend

---

## Descripción General

Esta Extensión extrae audio de archivos de video y audio y los transcribe usando modelos Whisper.
Selecciona automáticamente el backend óptimo basado en hardware disponible y se ejecuta en GPU o CPU incluso sin un NPU Hailo.

---

## Prioridad de Backend

| Prioridad | Backend | Librería | Hardware Objetivo |
|--------|-------------|-----------|-----------------|
| P100 | `hailo` | `hailo_platform.genai` | NPU Hailo-10H |
| P70 | `torch-whisper-rocm` | `torch` (ROCm) + `transformers` | GPU AMD (ROCm/HIP) |
| P50 | `faster-whisper-cuda` | `faster-whisper` (CTranslate2) | GPU NVIDIA (CUDA) |
| P40 | `torch-whisper-cuda` | `torch` (CUDA) + `transformers` | GPU NVIDIA (CUDA) |
| P20 | `torch-whisper-cpu` | `torch` + `transformers` | CPU |
| P50 | `faster-whisper-cpu` | `faster-whisper` (CTranslate2) | CPU |
| P10 | `whisper-cpp` | `pywhispercpp` | CPU (más ligero) |

En modo `auto`, se selecciona el backend con la prioridad más alta entre los que devuelven `is_available() == True`.

---

## Configuración Específica del Entorno

### Requisitos Comunes

- Python 3.11+
- ffmpeg (requerido para extraer audio de video)

### NPU Hailo-10H (Raspberry Pi AI HAT 2)

No se requieren paquetes adicionales (`hailo_platform` ya debe estar instalado).
El modelo (`whisper-base` etc.) debe haber sido descargado vía la Extensión GenAI.

```bash
# Descargar el modelo desde la UI de Extensión GenAI si aún no está presente
```

### GPU NVIDIA (CUDA)

```bash
# Recomendado: faster-whisper (ligero, no requiere PyTorch)
pip install faster-whisper

# GPU se utiliza automáticamente cuando se detecta CUDA (float16)
# Se retrocede a CPU automáticamente cuando CUDA está ausente (int8)
```

### GPU AMD (ROCm)

```bash
# 1. Instalar PyTorch edición ROCm
#    Oficial: https://pytorch.org/get-started/locally/
#    Ejemplo (ROCm 6.x):
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm6.2

# 2. Instalar transformers de HuggingFace
pip install transformers

# 3. Establecer backend en configuración (auto-detectado en modo "auto")
#    En la configuración de Extensión: backend: "rocm" o "auto"
```

**Mecanismo de detección de ROCm**: PyTorch expone ROCm como CUDA vía HIP.
El sistema identifica ROCm cuando `torch.version.hip` no es `None`.

**Requisitos de memoria** (ROCm):

| Modelo | Estimación de VRAM |
|--------|----------|
| tiny | ~150 MB |
| base | ~300 MB |
| small | ~500 MB |
| medium | ~1.5 GB |

### Solo CPU

```bash
# Opción 1: faster-whisper (recomendado, rápido con cuantización int8)
pip install faster-whisper

# Opción 2: whisper.cpp (más ligero, sin requerimiento de PyTorch)
pip install pywhispercpp

# Opción 3: torch + transformers (propósito general pero pesado)
pip install torch transformers
```

**Estimaciones de rendimiento de CPU** (modelo base, 1 minuto de audio):

| Backend | RPi 5 | x86 (4 núcleos) |
|---|---|---|
| faster-whisper (int8) | ~30 seg | ~5 seg |
| whisper.cpp | ~40 seg | ~8 seg |
| torch (float32) | ~90 seg | ~15 seg |

---

## Configuración

Configurar vía la página de configuración de Extensión (`/ext/speech-to-text/`) o config.json:

| Elemento | Opciones | Predeterminado | Descripción |
|------|--------|-----------|------|
| `backend` | auto / hailo / cuda / rocm / cpu | auto | Backend de inferencia |
| `model_size` | tiny / base / small / medium | base | Tamaño de modelo Whisper |
| `default_language` | Código BCP-47 (ja, en, etc.) | ja | Idioma predeterminado |

---

## Endpoints de API

Todos los endpoints están bajo el prefijo `/ext/speech-to-text`.

### POST `/api/s2t/transcribe`

Transcribir audio WAV cargado.

- **Content-Type**: `multipart/form-data`
- **Parámetros**: `audio` (archivo), `language` (opcional)
- **Respuesta**: `{ status, text, segments, language, sample_rate, backend }`

### POST `/api/s2t/transcribe-video`

Transcribir un archivo de video/audio registrado en BD. Los resultados se guardan como anotaciones.

- **Cuerpo**: `{ file_id: int, language?: string }`
- **Respuesta**: `{ status, text, segments, language, backend }`
- **Anotación**: `source="s2t"`, claves: `transcript`, `transcript_segments`, `transcript_backend`

### POST `/api/s2t/batch-transcribe`

Transcripción por lotes de múltiples archivos (se ejecuta en fondo).

Elige **uno** de tres métodos de entrada (mutuamente excluyentes):

#### Método 1: Lista de IDs de Archivo (Heredado)

```json
{
  "file_ids": [123, 456, 789],
  "language": "ja"
}
```

#### Método 2: Directorio

Detecta automáticamente archivos de video/audio en el directorio especificado y procesa solo los registrados en BD.

```json
{
  "directory": "/path/to/videos/",
  "recursive": true,
  "language": "en"
}
```

- `recursive` (predeterminado: `true`): Buscar recursivamente subdirectorios
- Extensiones de destino: `.webm`, `.mp4`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv`, `.mp3`, `.wav`, `.ogg`, `.opus`, `.m4a`, `.aac`, `.flac`

#### Método 3: Lista de Texto/CSV

Especificar un archivo de texto o CSV listando rutas de archivo.

```json
{
  "list_file": "/path/to/targets.txt",
  "language": "ja"
}
```

**Formato de archivo de texto** (`.txt` etc.):
```
# Líneas de comentario (las líneas que comienzan con # se ignoran)
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
Se utiliza la primera columna como ruta de archivo. Las líneas que comienzan con `#` se omiten.

#### Opciones Comunes

| Parámetro | Tipo | Predeterminado | Descripción |
|-----------|---|-----------|------|
| `language` | string | Valor de configuración (típicamente `ja`) | Código de idioma (véase a continuación) |
| `recursive` | bool | `true` | Método de directorio solo: búsqueda recursiva de subdirectorios |

#### Límites y Restricciones

- Máximo de archivos de destino: **500**
- Solo se procesan archivos registrados en BD (tabla `files`)
- Se excluyen archivos eliminados (`is_deleted=1`)

#### Ejemplo de Respuesta

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

Recupera resultados de transcripción guardados. Tanto `source="s2t"` como `source="hailo:s2t"` se comprueban para compatibilidad con versiones anteriores.

### GET `/api/s2t/status`

Devuelve estado de backend y lista de backends disponibles.

---

## Herramientas MCP

| Nombre de Herramienta | Descripción |
|---------|------|
| `s2t_status` | Obtener estado de backend |
| `s2t_transcribe_video` | Transcribir un único archivo de video |
| `s2t_batch_transcribe` | Iniciar transcripción por lotes (file_ids / directory / list_file) |
| `s2t_get_transcript` | Recuperar transcripción guardada |

### Parámetros de `s2t_batch_transcribe`

| Parámetro | Tipo | Requerido | Descripción |
|-----------|---|------|------|
| `file_ids` | list[int] | *1 | Lista de IDs de archivo (máx 500) |
| `directory` | string | *1 | Ruta de directorio (detecta automáticamente video/audio) |
| `list_file` | string | *1 | Ruta de archivo de texto/CSV |
| `recursive` | bool | | Método de directorio solo. Búsqueda recursiva de subdirectorios (predeterminado true) |
| `language` | string | | Código de idioma. Vacío = predeterminado de configuración |
| `expected_count` | int | | Para detectar truncamiento de file_ids |

*1: Especificar exactamente uno de `file_ids`, `directory`, o `list_file` (mutuamente excluyentes)

---

## Estructura de Archivos

```
extensions/builtin_speech_to_text/
  extension.json                      # Manifiesto
  speech_to_text_ext.py               # Punto de entrada (Blueprint)
  s2t_routes.py                       # Rutas de API de archivo único
  s2t_batch_routes.py                 # Rutas de API de lotes
  core_impl/
    base.py                           # Clase base abstracta S2TBackend
    backend_hailo.py                  # NPU Hailo-10H
    backend_faster_whisper.py         # faster-whisper (CUDA/CPU)
    backend_torch_whisper.py          # Transformers de PyTorch (ROCm/CUDA/CPU)
    backend_whisper_cpp.py            # whisper.cpp (CPU)
    backend_registry.py               # Detección automática + gestión singleton
  templates/speech_to_text/
    s2t.html                          # Página de UI
mcp_server/
  s2t_tools.py                        # Definiciones de herramientas MCP
```

---

## Códigos de Idioma Soportados

Códigos de idioma principales (BCP-47) soportados por Whisper:

| Código | Idioma | Código | Idioma |
|--------|------|--------|------|
| `ja` | Japonés | `en` | Inglés |
| `zh` | Chino | `ko` | Coreano |
| `de` | Alemán | `fr` | Francés |
| `es` | Español | `it` | Italiano |
| `pt` | Portugués | `ru` | Ruso |
| `ar` | Árabe | `hi` | Hindi |
| `th` | Tailandés | `vi` | Vietnamita |
| `nl` | Holandés | `tr` | Turco |
| `pl` | Polaco | `uk` | Ucraniano |
| `id` | Indonesio | `sv` | Sueco |

También se pueden especificar otros idiomas soportados por Whisper. Una cadena vacía desencadena detección automática.
El idioma predeterminado se puede cambiar vía la configuración de Extensión `default_language` (valor inicial: `ja`).

---

## Limitaciones Conocidas

- **Retraso de primera carga**: transformers / faster-whisper descarga modelos de HuggingFace Hub (base: ~150MB). La primera ejecución puede tomar varios minutos
- **Modelos HEF de Hailo**: Deben descargarse vía la Extensión GenAI. La Extensión S2T misma no tiene funcionalidad de descarga
- **Memoria**: El modelo medio puede causar errores de falta de memoria en RPi 5 (8GB). Se recomienda el modelo base
- **Concurrencia**: Los backends se gestionan como singletons. Las solicitudes que llegan durante procesamiento por lotes comparten la misma instancia
- **Formato de entrada**: WAV (PCM s16le, mono, 16kHz) se asume. Los archivos de video se convierten automáticamente vía ffmpeg
- **Entrada de lotes**: Los métodos directory / list_file solo procesan archivos registrados en BD. Los archivos sin escanear primero deben registrarse vía `start_scan`

---

## Transcripción de Streaming en Tiempo Real

Transcribir audio desde radio por internet, flujos RTSP y archivos de video en tiempo real y mostrar subtítulos en la WebUI.

### Dos Modos

- **Modo de fragmento** (predeterminado): Divide el audio en fragmentos usando detección de silencio basada en RMS. Compatible con todos los backends (Hailo/CUDA/CPU). Los resultados se muestran después de que termina cada enunciado.
- **Modo en vivo**: Realiza transcripción incremental usando Silero VAD de faster-whisper. Muestra resultados provisionales mientras la voz todavía está en curso. Requiere un backend ONNX/faster-whisper.

### Fuentes de Entrada Soportadas

- Flujos HTTP/HTTPS (radio por internet, etc.)
- Cámaras RTSP
- Flujos RTMP

### Endpoints de API

| Endpoint | Método | Función |
|---|---|---|
| `/api/s2t/stream/start` | POST | Iniciar streaming (`source_url`, `language`, `mode`) |
| `/api/s2t/stream/stop` | POST | Detener streaming |
| `/api/s2t/stream/status` | GET | Obtener estado |
| `/api/s2t/stream/transcript` | GET | Obtener transcripción completa |
| `/api/s2t/stream/export/txt` | GET | Exportar como texto |
| `/api/s2t/stream/export/srt` | GET | Exportar como subtítulos SRT |

### Eventos SSE

| Evento | Descripción |
|---|---|
| `s2t.stream_chunk` | Texto finalizado |
| `s2t.stream_interim` | Texto provisional (solo modo en vivo) |
| `s2t.stream_complete` | Streaming completo |

### Herramientas MCP

| Herramienta | Descripción |
|---|---|
| `s2t_stream_start(source_url, language)` | Iniciar streaming |
| `s2t_stream_stop()` | Detener streaming |
| `s2t_stream_status()` | Obtener estado |
| `s2t_stream_transcript()` | Obtener transcripción completa |

### Configuración de Streaming

Elementos configurables en `extension.json`:

| Elemento | Descripción | Predeterminado |
|---|---|---|
| `stream_chunk_min_sec` | Longitud de fragmento mínimo en modo Fragmento (segundos) | — |
| `stream_chunk_max_sec` | Longitud de fragmento máximo en modo Fragmento (segundos) | — |
| `stream_silence_threshold` | Umbral RMS para detección de silencio | — |
| `stream_silence_ms` | Duración de silencio para detección (milisegundos) | — |
| `live_interval_sec` | Intervalo de transcripción en modo en vivo (segundos) | — |
