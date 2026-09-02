# Hailo-10H Semantic Search — Registro de Desarrollo

**Proyecto**: YU AI Manager — Búsqueda semántica de imágenes CLIP con Hailo-10H
**Objetivo**: Realizar búsqueda de imágenes en lenguaje natural basada en CLIP en Raspberry Pi 5 + AI HAT 2 (Hailo-10H)
**Fecha de inicio**: 2026-03-01
**Estado**: Fases 1-8 completadas, Fases 9-12 (integración de subtítulos VLM, S2T de video, LLM multiturn, API compatible con OpenAI) completadas

---

## Por qué este proyecto es importante

Hailo-10H (AI HAT 2) es un acelerador de IA en el borde relativamente nuevo lanzado a finales de 2025,
que se instala en la ranura M.2 de la Raspberry Pi 5. Tiene un rendimiento de inferencia de 40 TOPS, pero
**casi no hay casos de uso publicados en aplicaciones prácticas**.

Este proyecto probablemente sea el primer software práctico que utiliza Hailo-10H para
búsqueda semántica (búsqueda de imágenes en lenguaje natural) en una biblioteca de imágenes
de escala de 200,000 imágenes.

---

## Fase 1: Verificación de viabilidad (2026-03-01)

### Información del entorno

| Elemento | Valor |
|------|-----|
| Hardware | Raspberry Pi 5 (8GB) + AI HAT 2 (Hailo-10H) |
| SO | Raspberry Pi OS Trixie (Linux 6.12.62+rpt-rpi-2712) |
| Python | 3.13.5 |
| Driver HailoRT | 5.2.0 (hailort-pcie-driver) |
| Biblioteca HailoRT | 5.2.0 (hailort deb) |
| Python HailoRT | 5.2.0 (**compilado desde código fuente**) |

### Paso 1-1: Reconocimiento del dispositivo — OK

```bash
$ hailortcli fw-control identify
Firmware Version: 5.2.0 (release,app)
Device Architecture: HAILO10H
```

El dispositivo fue reconocido sin problemas. La conexión PCIe y la carga del driver funcionaron correctamente.

### Paso 1-2: Descarga de HEF — OK

Se pudo descargar directamente desde el bucket S3 del Hailo Model Zoo v5.2.0 (sin autenticación necesaria).

```
~/hailo_models/clip_vit_b_16_image_encoder.hef  (76 MB)
~/hailo_models/clip_vit_b_16_text_encoder.hef   (77 MB)
```

Patrón de URL:
```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

### Paso 1-3: Bindings Python — Requiere compilación desde código fuente

#### Problema: Incompatibilidad de versiones de paquetes

En el repositorio de Raspberry Pi OS existen las siguientes 2 series de paquetes:

| Serie de paquetes | Versión | Notas |
|---------------|-----------|------|
| `hailort` + `hailort-pcie-driver` | 5.2.0 | deb oficial de Hailo. Sin bindings Python |
| `h10-hailort` + `python3-h10-hailort` | 5.1.1 | Proporcionado por el equipo de Raspberry Pi. Con Python |

**Problema**: Las 2 series tienen configuración `Conflicts` y no pueden coexistir. Si instalas `h10-hailort` (5.1.1), el driver también pasa a 5.1.1, pero hailo-ollama requiere 5.2.0.

#### Solución: Compilar wheel Python de hailort 5.2.0 desde el código fuente

**No hay wheel en PyPI**. Tampoco existe wheel para aarch64 en la página de descargas de Hailo Developer Zone (solo x86_64).

Solución compilando desde el repositorio de GitHub:

```bash
git clone --depth 1 --branch v5.2.0 https://github.com/hailo-ai/hailort.git ~/hailort

# Dependencias de compilación
sudo apt install -y swig build-essential
pip install pybind11 setuptools wheel

# Compilación (aprox. 2 minutos)
cd ~/hailort/hailort/libhailort/bindings/python/platform
HAILORT_INCLUDE_DIR=/usr/include/hailo \
LIBHAILORT_PATH=/usr/lib/libhailort.so.5.2.0 \
PYBIND11_PYTHON_VERSION=3.13 \
python3 setup.py bdist_wheel --plat-name linux_aarch64

# Instalación
pip install dist/hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

**Notas importantes**:
- `--plat-name linux_aarch64` es obligatorio. Sin él se produce `ValueError: not enough values to unpack` al analizar el nombre del directorio de `LIBHAILORT_PATH` (bug en la línea 163 de setup.py)
- El deb `hailort` (biblioteca C) debe instalarse previamente
- `h10-hailort` y `hailort` tienen `Conflicts` configurado y no pueden coexistir, así que eliminar `h10-hailort` antes de instalar `hailort` 5.2.0

### Paso 1-4: Prueba de inferencia — Éxito (con cambios de API)

#### Descubrimiento crítico: Hailo-10H no soporta la antigua API VStreams

El código `InferVStreams` + `ConfigureParams.create_from_hef()` que se había escrito en la especificación **no funciona en Hailo-10H**. `VDevice.configure()` devuelve `HAILO_NOT_IMPLEMENTED (error 7)`.

Este es un **hecho importante no documentado claramente en la documentación oficial** que constituye una diferencia fundamental de API entre Hailo-8/8L y Hailo-10H.

#### API correcta: InferModel

En Hailo-10H se usa `VDevice.create_infer_model()`:

```python
from hailo_platform import VDevice
import numpy as np

hef_path = "~/.hailo_models/clip_vit_b_16_image_encoder.hef"

with VDevice() as vdevice:
    infer_model = vdevice.create_infer_model(hef_path)

    # inputs/outputs son propiedades (no callable)
    inp_info = infer_model.inputs[0]   # NO inputs()
    out_info = infer_model.outputs[0]

    configured = infer_model.configure()
    bindings = configured.create_bindings()

    # Entrada: imagen uint8
    dummy = np.random.randint(0, 255, inp_info.shape, dtype=np.uint8)
    bindings.input().set_buffer(dummy)

    # Salida: reservar explícitamente buffer uint8
    output_buf = np.empty(out_info.shape, dtype=np.uint8)
    bindings.output().set_buffer(output_buf)

    configured.run([bindings], timeout=10000)

    vec = output_buf.flatten()  # (512,) uint8
```

#### Puntos problemáticos y soluciones

| Problema | Error | Solución |
|------|--------|------|
| `infer_model.inputs()` da TypeError | `'list' object is not callable` | Es una propiedad, usar `inputs[0]` (sin paréntesis) |
| Buffer de salida no configurado | `not configured as view` | Reservar explícitamente con `bindings.output().set_buffer(buf)` |
| Buffer de salida reservado como float32 | `buffer size 2048 != expected 512` | Reservar como **uint8** (512 bytes). float32 da 2048 bytes |
| Error al cerrar VDevice | `Lost communication with server` | Problema en el orden de limpieza de VDevice. **No afecta los resultados de inferencia** |

### Rendimiento de inferencia

| Elemento | Valor |
|------|-----|
| Modelo | CLIP ViT-B/16 Image Encoder |
| Entrada | (224, 224, 3) uint8 |
| Salida | (1, 1, 512) uint8 (cuantizado) |
| Tiempo de inferencia | **~20 ms** |
| Throughput teórico | **~50 imágenes/s** |

Construcción del índice para 200,000 imágenes: solo la inferencia tomaría unos 67 minutos. Con el preprocesamiento, se completaría en pocas horas.

### Evaluación de la Fase 1

| Criterio | Resultado |
|------|------|
| Salida de vector de 512 dimensiones | **OK** (cuantización uint8, requiere descuantización) |
| Velocidad de inferencia | **Excelente** (20ms/imagen) |
| Compatibilidad de API | Usar InferModel API (la API VStreams de la especificación no es posible) |
| Evaluación | **Proceder a la Fase 2** |

### Elementos de transferencia a la siguiente fase

1. **Descuantización**: La salida uint8 debe convertirse a float32.
   El HEF debería contener parámetros de cuantización (scale/zero_point).
   Posible usar `hailo_platform.pyhailort._pyhailort.dequantize_output_buffer`.
2. **Codificador de texto**: El HEF existe pero no se ha probado. Verificar si funciona con la misma InferModel API.
   Puede ser más seguro implementarlo en CPU (sentence-transformers) según el plan de la especificación.
3. **Coexistencia con hailo-ollama**: VDevice usa el dispositivo exclusivamente.
   Hay que detener hailo-ollama durante la construcción del índice.
4. **Limpieza de VDevice**: El mensaje de error al terminar es inofensivo,
   pero prestar atención a las fugas de recursos en procesos de servidor de larga duración.

---

## Fase 2: Extensión del esquema de base de datos (2026-03-01)

### Contenido de la implementación

Se añadió la tabla `file_vectors` como migración 25.

```sql
CREATE TABLE file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip_vit_b_16',
    vector      BLOB NOT NULL,        -- numpy array float32 tobytes() (512*4=2048 bytes)
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
CREATE INDEX idx_file_vectors_model ON file_vectors(model);
```

**Decisiones de diseño**:
- `vector` almacena BLOB float32 descuantizado. Almacenar como uint8 degradaría la precisión
- `file_id` es PRIMARY KEY (1 vector por archivo). Se necesita cambio a UNIQUE(file_id, model) para soporte futuro de múltiples modelos
- `ON DELETE CASCADE` para eliminación automática al borrar archivos

**Prueba**: Aplicar migración en DB en memoria → confirmar existencia de tabla/índice → OK

### Archivos

- `core/schema_core/schema_migrate_steps_25.py` (nuevo)
- `core/schema_core/schema_migrate.py` (agregar import + `if current_version < 25`)
- `core/schema_core/schema_constants.py` (`CURRENT_SCHEMA_VERSION = 25`)
- `core/hailo_clip_core/vector_store.py` (nuevo - CRUD de vectores en base de datos)  *(actualmente movido a `extensions/builtin_hailo_semantic_search/core_impl/`)*

---

## Fase 3: Core de inferencia Hailo (2026-03-01)

### Contenido de la implementación

Se creó el paquete `core/hailo_clip_core/` *(actualmente `extensions/builtin_hailo_semantic_search/core_impl/`)*:

| Archivo | Responsabilidad |
|---------|------|
| `hailo_inference.py` | Singleton HailoClipEncoder. Wrapper de InferModel API |
| `image_preprocess.py` | Redimensionamiento 224x224 con cv2 + conversión BGR→RGB |
| `dequantize.py` | Descuantización uint8→float32 + normalización L2 + extracción quant_params |
| `text_encoder.py` | Codificador de texto CLIP en CPU (`openai/clip-vit-base-patch16`) |

**Decisiones de diseño**:
- El preprocesamiento de imagen se pasa a Hailo como uint8 (la normalización se realiza dentro del HEF)
- El codificador de texto usa `CLIPModel` de `transformers` (no `sentence-transformers`).
  Razón: `openai/clip-vit-base-patch16` es el mismo modelo que el CLIP ViT-B/16 del HEF de Hailo, con espacios de vectores coincidentes
- Los parámetros de descuantización se obtienen de `infer_model.outputs[0].quant_infos[0]`,
  con fallback a scale=1.0, zero_point=0.0 si falla

**Paquetes dependientes**: `opencv-python-headless`, `numpy` (obligatorios), `transformers`, `torch` (para búsqueda de texto)

---

## Fase 4: Indexador + Extension (2026-03-01)

### Contenido de la implementación

| Archivo | Responsabilidad |
|---------|------|
| `core/hailo_clip_core/indexer.py` *(actualmente `extensions/builtin_clip_search/core_impl/`)* | Construcción del índice en lote en hilo de fondo |
| `core/hailo_clip_core/event_handler.py` *(actualmente `extensions/builtin_clip_search/core_impl/`)* | Indexado automático con evento scan.complete |
| `extensions/builtin_hailo_semantic_search/extension.json` | Manifiesto de Extension |
| `extensions/builtin_hailo_semantic_search/hailo_semantic_search.py` | Blueprint con 5 APIs |

**Endpoints de API**:
- `GET /ext/hailo-semantic/api/status` — Estado del dispositivo e índice
- `POST /ext/hailo-semantic/api/index/start` — Iniciar construcción del índice
- `GET /ext/hailo-semantic/api/index/status` — Progreso
- `POST /ext/hailo-semantic/api/index/stop` — Interrumpir
- `GET /ext/hailo-semantic/api/search` — Búsqueda semántica
- `POST /ext/hailo-semantic/api/index/clear` — Limpiar índice

**Eventos**: Se añadieron `semantic_index.start/progress/complete` al event_bus

---

## Fase 5: Motor de búsqueda semántica (2026-03-01)

### Contenido de la implementación

`core/hailo_clip_core/search.py` *(actualmente `extensions/builtin_clip_search/core_impl/search.py`)* — Búsqueda de similitud coseno con caché en memoria

**Algoritmo**:
1. Carga masiva de todos los vectores desde la DB → caché en memoria
2. Pre-normalización L2 de vectores
3. Texto de consulta → codificador de texto CLIP → vector de 512 dimensiones
4. Cálculo por lotes de similitud coseno con producto punto matricial
5. Ordenar los que superan el umbral → devolver resultados

**Estimación de memoria**: 200K x 512 x 4 bytes = ~400 MB (rango aceptable para Pi5 8GB RAM)

**Formato de respuesta**:
```json
{
    "status": "ok",
    "total": 25,
    "results": [{"file_id": 123, "score": 0.82, "path": "..."}],
    "query": "blue sky",
    "indexed_count": 200000,
    "threshold": 0.2,
    "timing": {"encode_ms": 150.3, "search_ms": 12.5}
}
```

---

## Fase 6: Integración en la interfaz de usuario (2026-03-01)

### Página de búsqueda

- Se añadió un toggle de búsqueda semántica junto a la barra de búsqueda (icono de cerebro, estilo `regex-pill`)
- Solo se muestra si Hailo está disponible y el índice está construido
- Con el toggle activado: interceptar el envío del formulario de búsqueda → API de búsqueda semántica → mostrar resultados en la cuadrícula existente
- Reemplazar el placeholder con ejemplos de texto en inglés

### Página de herramientas

- Se añadió una sección de búsqueda semántica en la pestaña Search & Analysis
- Visualización del estado del dispositivo y el índice
- Deslizador de tamaño de lote + checkbox de indexado automático
- Botones Build Index / Stop / Clear + barra de progreso (polling de 2 segundos)

---

## Notas técnicas

### Principales diferencias entre Hailo-10H y Hailo-8/8L (perspectiva del desarrollador)

| Elemento | Hailo-8/8L | Hailo-10H |
|------|-----------|-----------|
| API VStreams | Compatible | **No compatible** (NOT_IMPLEMENTED) |
| API InferModel | Compatible | Compatible |
| ConfigureParams | create_from_hef(hef, interface) | No necesario (create_infer_model lo reemplaza) |
| Formato de salida | float32 o uint8 seleccionable | uint8 fijo (requiere descuantización) |
| Paquete Python | Wheel disponible en PyPI | **No disponible** (requiere compilación desde código fuente) |
| Paquete APT | `hailort` integrado | Serie separada `h10-hailort` (solo 5.1.1) |

### Almacenamiento de wheels compiladas

```
~/hailort/hailort/libhailort/bindings/python/platform/dist/
  hailort-5.2.0-cp313-cp313-linux_aarch64.whl
```

Se puede copiar esta wheel a otros entornos Pi5 e instalarla directamente
(sin embargo, requiere libhailort.so.5.2.0 y hailort-pcie-driver 5.2.0).

---

## Registro de corrección de bugs después de implementar las Fases 2-6 (2026-03-01)

### 1. Problema de compatibilidad de `get_text_features` del codificador de texto

**Problema**: `CLIPModel.get_text_features(**inputs)` comenzó a devolver un objeto `BaseModelOutputWithPooling` en nuevas versiones de transformers, no un `torch.Tensor`.
Esto causaba `AttributeError` al llamar a `.squeeze()`, resultando en error `Search failed` en la búsqueda semántica.

**Síntoma**: `curl /ext/hailo-semantic/api/search?q=girl` → `{"message":"Search failed","status":"error"}`

**Causa**: El valor de retorno de `_model.get_text_features()` depende de la versión de transformers.
Las nuevas versiones devuelven el objeto de salida completo del modelo, siendo necesario extraer `.pooler_output` uno mismo.

**Corrección**: Cambio en `text_encoder.py` para procesar en 2 pasos con `text_model()` → `text_projection()`:

```python
# Antes (roto)
text_features = _model.get_text_features(**inputs)
vec = text_features.squeeze().numpy()

# Después (corregido)
text_out = _model.text_model(**inputs)
text_features = _model.text_projection(text_out.pooler_output)
vec = text_features.squeeze().numpy()
```

**Rendimiento**:
- Primera consulta (con carga del modelo): ~6 segundos
- Consultas siguientes: ~100-170ms (solo inferencia CPU)
- Búsqueda de vectores: <1ms (51 elementos, caché en memoria)

### 2. Bucle de reintentos infinito durante la construcción del índice

**Problema**: Los archivos con error de decodificación (archivos no imagen, archivos corruptos, etc.) no se rastreaban en `failed_ids`,
y `get_unindexed_file_ids()` devolvía los mismos archivos fallidos cada vez, haciendo que el contador de errores superara los 3 millones.

**Corrección**: Se añadió `failed_ids: set` a `indexer.py`. Se registran los file_id fallidos y se excluyen en el siguiente lote.

### 3. Fallo al leer imágenes de archivos

**Problema**: `cv2.imread('test.7z!image.png')` no entiende las rutas de miembros de archivo.

**Corrección**: En `image_preprocess.py`, se usa `is_archive_member()` para detectar rutas de archivo
y se cambia al patrón `read_bytes_from_zip` / `read_bytes_from_7z` + `cv2.imdecode()`.

### 4. Actualizaciones de progreso en tiempo real SSE

**Problema**: El polling de 2 segundos hacía que el progreso fuera irregular y la experiencia mala.

**Corrección**: Cambio a conexión SSE `EventSource`. Actualización en tiempo real con evento `semantic_index.progress`.
Desconexión de SSE cuando la pestaña no es visible (`visibilitychange`), con reconexión al regresar.

---

## Fase 7: Detección de objetos YOLO (2026-03-02)

### Resumen

Siguiendo a la búsqueda semántica CLIP, se implementó la detección de objetos YOLO en el mismo Hailo-10H.
Detección de objetos COCO de 80 clases en imágenes y videos, guardando los resultados en la tabla `file_annotations`.

### Diseño de arquitectura

#### Problema de compartición de VDevice

Hailo-10H solo puede usar un VDevice desde un proceso, y InferModel también es exclusivo.
No se pueden ejecutar CLIP y YOLO simultáneamente.

**Solución**: Se creó `core/hailo_device_core/device_manager.py`.
- `acquire_device(owner, hef_path)` — Liberación automática y cambio si otro propietario lo retiene
- Si el mismo propietario + el mismo HEF, reutilizar (evitar reinicialización)
- Thread-safe con `threading.Lock`
- Refactorizar `hailo_inference.py` de CLIP para delegar a device_manager

#### Manejo de tensores de salida YOLO

CLIP tiene un solo tensor de salida, pero YOLO tiene múltiples tensores de salida (correspondientes a cada cabeza de stride).
`device_manager` recopila los parámetros de cuantización de todas las salidas y los devuelve.

#### Pipeline de postprocesamiento

El postprocesamiento de YOLO sigue estos pasos:
1. Descuantización uint8 → float32 (usando scale/zero_point por tensor de salida)
2. Decodificación de coordenadas grid cell → pixel (sigmoid + offset de celda + stride)
3. Filtrado de confianza
4. NMS por clase (pure numpy)
5. Conversión de coordenadas letterbox → coordenadas normalizadas (0-1) de la imagen original

#### Soporte de video

Extracción de fotogramas con ffmpeg → detección independiente de cada fotograma → agregación por clase.
Se mantiene la confianza máxima y el número de fotogramas en que aparece cada clase.

### Nueva estructura de módulos

| Módulo | Rol |
|---|---|
| `core/hailo_device_core/device_manager.py` | Gestión del ciclo de vida de VDevice compartido |
| `core/hailo_yolo_core/hailo_yolo_inference.py` | Singleton YOLODetector |
| `core/hailo_yolo_core/yolo_postprocess.py` | NMS, decodificación de cajas, descuantización |
| `core/hailo_yolo_core/yolo_labels.py` | Etiquetas de las 80 clases COCO |
| `core/hailo_yolo_core/yolo_preprocess.py` | Redimensionamiento letterbox 640x640 |
| `core/hailo_yolo_core/yolo_video.py` | Extracción y agregación de fotogramas de video |
| `core/hailo_yolo_core/yolo_indexer.py` | Detección en lote en segundo plano |
| `core/hailo_yolo_core/model_download.py` | Descarga de HEF |
| `core/hailo_yolo_core/event_handler.py` | Handler de scan.complete |
| `extensions/builtin_hailo_yolo_detect/` | Extension + Blueprint API + interfaz de usuario |

### Notas técnicas

- **Múltiples tensores de salida**: El HEF de YOLO tiene múltiples tensores de salida (correspondientes a cabezas de cada stride).
  Hay que recorrer `infer_model.outputs` y recopilar todos los shapes/quant_params
- **Buffers de salida**: Reservar un buffer uint8 individual para cada tensor de salida
  y vincular por nombre con `bindings.output(out.name).set_buffer(buf)`
- **Distribución de tensores**: La forma generalmente es `(1, H, W, C)`. C contiene bbox (4) + puntuaciones de clase (80)
- **Descarga de HEF**: Descarga directa desde Hailo Model Zoo v5.2.0. Se establece `_USER_AGENT` porque Cloudflare bloquea sin User-Agent
- **Guardado de resultados de detección**: Se guarda como array JSON en la tabla `file_annotations` con `source='hailo:<model>'`, `key='detections'`. Se aprovecha la API CRUD de anotaciones existente

---

## Fase 8: Integración de GenAI (LLM / VLM / Speech2Text) (2026-03-02)

### Objetivo

Integrar el módulo `hailo_platform.genai` (LLM, VLM, Speech2Text) de Hailo-10H
en device_manager y hacer disponibles la generación de texto, la comprensión de imágenes
y la transcripción de voz desde la WebUI.

### Extensión de device_manager

- **Problema**: El device_manager existente solo soporta la InferModel API (CLIP/YOLO).
  Las clases GenAI no son InferModel sino que reciben VDevice directamente en otro modo
- **Solución**: Distinción de modo con variable `_mode` (`"infer"` | `"genai"`).
  Se añade `acquire_genai(owner, model_path, genai_factory)` y se crea la instancia de LLM/VLM/S2T con patrón de fábrica
- **Diferencias en el proceso de liberación**:
  - InferModel: `del configured` → `del infer_model` → `del vdevice`
  - GenAI: `instance.release()` → `vdevice.release()` (método release explícito)

### Descubrimientos de la API GenAI

- **Formato de mensajes**: Estructura role/content compatible con OpenAI. El content es un array con formato `{"type": "text", "text": "..."}`
- **Entrada de imagen VLM**: Array numpy RGB uint8 de 336x336. Se pasa como lista con `frames=[image]`.
  Se coloca un placeholder `{"type": "image"}` en el prompt
- **Entrada S2T**: little-endian float32 (`<f4`), mono, 16kHz. Es obligatoria la normalización int16→float32
- **Segmentos S2T**: `generate_all_segments()` devuelve una lista de objetos `SegmentInfo`.
  Tienen atributos `.text`, `.start`, `.end`
- **Gestión de contexto**: LLM/VLM gestiona la ventana de contexto con `get_context_usage_size()`, `max_context_capacity()`,
  `clear_context()`
- **Streaming**: `generate()` devuelve un iterador que hace yield por token

### URLs de descarga de HEF de modelos

- Patrón: `https://dev-public.hailo.ai/v{hailort_version}/blob/{ModelName}.hef`
- HailoRT 5.2.0 → `v5.2.0`
- Los nombres de modelos son CamelCase (p.ej.: `Qwen2.5-1.5B-Instruct.hef`, `Whisper-Base.hef`)
- Verificado con el tipo de fuente `gen-ai-mz` del `download_resources.py` de `hailo-apps-infra`

### Nuevos archivos

| Archivo | Descripción |
|----------|------|
| `core/hailo_genai_core/__init__.py` | Init del paquete |
| `core/hailo_genai_core/genai_types.py` | Enum GenAIModelType + dataclass GenAIModelInfo |
| `core/hailo_genai_core/model_download.py` | Gestión de descarga de HEF para 7 modelos |
| `core/hailo_genai_core/llm_inference.py` | Wrapper HailoLLM (singleton, streaming) |
| `core/hailo_genai_core/vlm_inference.py` | Wrapper HailoVLM (singleton, preprocesamiento de imagen) |
| `core/hailo_genai_core/s2t_inference.py` | Wrapper HailoS2T (singleton, soporte de segmentos) |
| `extensions/builtin_hailo_genai/extension.json` | Manifiesto de Extension |
| `extensions/builtin_hailo_genai/hailo_genai_ext.py` | Blueprint con 8 APIs (streaming SSE) |
| `extensions/.../templates/hailo_genai/_genai_ui.html` | Interfaz de usuario de la página Tools (4 paneles) |

### Notas técnicas

- **`VDevice.create_params()`**: En modo GenAI, se crea la instancia con `VDevice.create_params()` para los parámetros y `VDevice(params)`. Diferente de `VDevice()` (sin argumentos) en modo InferModel
- **Streaming SSE**: Se envía `data: {"token": "..."}\n\n` por token con `Response(generator(), mimetype='text/event-stream')` de Flask. `data: {"done": true}\n\n` al completar
- **Envío FormData de VLM**: La API VLM usa `multipart/form-data` en lugar de JSON para enviar simultáneamente imagen y texto
- **Lectura de WAV para S2T**: El servidor lee directamente desde bytes WAV subidos con el módulo `wave` + `io.BytesIO`

---

## Fase 9: Integración de búsqueda semántica + subtítulos VLM (2026-03-03)

### Objetivo

Generar subtítulos en lote con VLM (Qwen2-VL) para las imágenes resultantes de la búsqueda CLIP
y guardarlos en `file_annotations`.

### Implementación

- **`core/hailo_clip_core/caption_runner.py`** *(actualmente `extensions/builtin_hailo_semantic_search/core_impl/caption_runner.py`)* (~150 líneas): Generación de subtítulos VLM en lote en hilo de fondo. Sigue el patrón `_state_lock` + `_stop_requested` + `_progress` de `indexer.py`. Eventos SSE `vlm_caption.start/progress/complete`
- **Extensión Blueprint**: Se añadieron 3 endpoints a `hailo_semantic_search.py`: `/api/caption/start`, `/api/caption/status`, `/api/caption/stop`
- **Interfaz de usuario**: Panel "VLM Caption Generation" añadido a la sección Semantic Search de la página Tools. Entrada de prompt, barra de progreso SSE, vinculación automática con file_ids de resultados de búsqueda

### Control exclusivo de VDevice

- Se obtiene VLM con `acquire_genai("vlm", ...)`. Si el indexador CLIP está en funcionamiento, device_manager libera automáticamente según el comportamiento existente
- Después de completar los subtítulos, VLM retiene el dispositivo, por lo que reanudar el índice CLIP requiere descargar el modelo

### Convención de guardado de anotaciones

- `source="hailo:vlm"`, `key="caption"`, `value=<texto del subtítulo>`

---

## Fase 10: Transcripción de audio de video — Pipeline S2T (2026-03-03)

### Objetivo

Extracción de audio de archivos de video con ffmpeg → transcripción con Whisper (S2T) → guardado en `file_annotations`.

### Implementación

- **`core/files_core/video_audio.py`** (~80 líneas): `extract_audio_wav()` para extracción de audio con ffmpeg (mono PCM s16le 16kHz). Cálculo dinámico del timeout según la duración del video (máximo 120 segundos). `check_ffmpeg()` reutilizado desde `media_video.py`
- **Extensión Blueprint**: Se añadieron 3 endpoints a `hailo_genai_ext.py`:
  - `POST /api/s2t/transcribe-video`: Transcripción de un solo video (file_id, language)
  - `POST /api/s2t/batch-transcribe`: Transcripción en lote de múltiples videos (file_ids, language), hilo de fondo + progreso SSE (`video_s2t.*`)
  - `GET /api/s2t/transcript/<file_id>`: Obtener transcripción guardada
- **Interfaz de usuario**: Se añadió una subsección "Video Transcription" dentro del panel S2T. Entrada de file_id, selección de idioma (ja/en), botón de obtención guardada

### Convención de guardado de anotaciones

- `source="hailo:s2t"`, `key="transcript"`, `value=<texto completo>`
- `source="hailo:s2t"`, `key="transcript_segments"`, `value=<JSON [{text, start, end}, ...]>`

### Notas

- Los WAV temporales se crean con `tempfile.NamedTemporaryFile` y siempre se eliminan en finally
- S2T y LLM/VLM son exclusivos entre sí (no pueden usarse simultáneamente)

---

## Fase 11: Mejoras de la interfaz de usuario de conversación multiturn LLM (2026-03-03)

### Objetivo

Ampliar los prompts únicos a soporte de historial de conversación. Continuación del contexto, reinicio y interfaz de usuario tipo burbuja.

### Implementación

- **Corrección de API**: `api_llm_generate()` puede recibir un array `messages`. Compatibilidad hacia atrás: si solo se proporciona `prompt`, se convierte al mensaje sistema + usuario convencional. `generate_stream()` ya soportaba multiturn (vía `_normalise_prompt()`)
- **Interfaz de chat tipo burbuja**: `hg-chat-container` + `hg-bubble` (usuario=alineado a la derecha púrpura, IA=alineado a la izquierda gris). Clases CSS: `hg-bubble-user`, `hg-bubble-ai`, `hg-bubble-label`
- **Gestión del historial de conversación**: Array `_chatHistory = []` en el lado JS que acumula `{role, content}`. Se pasa `messages: [systemMsg, ..._chatHistory]` al enviar a la API. `hgLlmClear()` reinicia el array + limpia el contexto de HailoRT
- **Streaming**: La burbuja AI se inserta primero en el DOM y los tokens SSE se agregan sucesivamente

### Bug corregido: Error de system role en conversación multiturn (2026-03-03)

Descubierto con consulta de depuración MCP + logs de hailort. El siguiente error aparecía en llamadas a `generate()` a partir del 2º turno:

```
[HailoRT] [error] CHECK failed - System role messages can only be provided on the first prompt
[HailoRT] [error] CHECK_SUCCESS failed with status=HAILO_INVALID_OPERATION(6)
```

**Causa**: La plantilla de la interfaz de usuario enviaba `[systemMsg].concat(_chatHistory)` con system role al frente cada vez. La API LLM de HailoRT no acepta system role cuando ya existe un contexto (2º turno en adelante).

**Corrección**:
1. Se añadió el método `_prepare_prompt()` a `llm_inference.py`: si `get_context_usage_size() > 0`, excluye automáticamente los mensajes de system role
2. Plantilla de la interfaz de usuario (`_genai_ui.html`): el system solo se adjunta cuando `_chatHistory.length <= 1` (solo el primer mensaje del usuario)

**Nota técnica**: Como restricción de HailoRT, `LLM.generate()` solo procesa el system role en la primera llamada. Este es un comportamiento diferente a la API de OpenAI, y hay que tenerlo en cuenta al implementar conversaciones multiturn

---

## Prueba real de WD-Tagger VLM × Hailo-10H (2026-03-03)

### Entorno de prueba
- Raspberry Pi 5 + Hailo AI HAT 2 (Hailo-10H)
- HailoRT FW 5.2.0, hailo_platform Python 5.2.0
- hailo-ollama v0.5.1 (versión compilada)
- Qwen2-VL-2B-Instruct.hef (3.0 GB)

### Descubrimiento importante: hailo-ollama no soporta VLM

Declarado explícitamente en la documentación oficial de hailo-ollama (USAGE.rst):
> "The Hailo-Ollama API is currently limited to language models (LLMs) and cannot be used for VLMs."

En la tabla MODELS, la columna Inference API de `Qwen2-VL-2B-Instruct` es solo "C++, Python", sin incluir "Hailo-Ollama".

Lista de modelos devuelta por `/hailo/v1/list`:
```
deepseek_r1:1.5b, llama3.2:1b, qwen2.5-coder:1.5b, qwen2.5:1.5b, qwen2:1.5b
```
`qwen2-vl` no está incluido.

### Resultados de prueba de hailo-ollama

**Nota sobre la configuración**: El binario compilado usa la macro `NLOHMANN_DEFINE_TYPE_NON_INTRUSIVE`, y la clave `limits` es obligatoria en el JSON de configuración. No está incluida en la plantilla de configuración oficial, por lo que hay que añadir:
```json
"limits": {"max_in_flight": 4, "max_queue": 10, "retry_after_sec": 1}
```

- **Generación de texto LLM (qwen2.5:1.5b)**: OpenAI + Ollama native ambos OK, 6.5 TPS
- **Solicitud vision de API OpenAI**: Error 500 (`Node is NOT a STRING`)
- **API Ollama native + images**: Se acepta pero LLM no puede procesar imágenes
- **Fallback VlmWdTaggerEngine**: Cambio automático OpenAI 500 → Ollama native OK
- **response_format: json_object**: Se acepta pero la salida JSON no se fuerza

### Resultados de prueba directa de VLM con Python SDK de Hailo

VLM requiere incluir `{"type": "image"}` en el formato de mensaje:
```python
messages = [
    {"role": "user", "content": [
        {"type": "image"},
        {"type": "text", "text": "Tag this image."}
    ]}
]
vlm.generate_all(messages, frames=[frame_336x336_rgb_uint8])
```

- **Carga del modelo**: 33 segundos (primer inicio en frío. La diferencia con los 6.2 segundos oficiales se debe al dominio del I/O de disco)
- **Velocidad de inferencia**: ~5.1 TPS (128 tokens / 20 segundos). La diferencia con los 6.73 TPS oficiales incluye TTFT
- **Precisión de reconocimiento de imagen**: Comprensión correcta del contenido de la imagen (describió con precisión "dos mujeres tomadas de la mano en un paisaje nevado")
- **Calidad de salida JSON**: Baja. El modelo 2B es inestable en la generación de JSON estructurado (faltan comas, se mezclan fences de código markdown)

### Bugs encontrados

1. **Formato de prompt en `engines_hailo_vlm.py`**: Se pasaban mensajes solo de texto a VLM → Corrección al formato de lista que incluye `{"type": "image"}`
2. **Argumento frames en `vlm_inference.py`**: `frames` es obligatorio para `generate_all()` de VLM pero estaba declarado como Optional → Corrección a obligatorio

### Notas técnicas

- **Restricción de exclusión VDevice**: No se puede adquirir `hailo_platform.VDevice()` mientras hailo-ollama está en ejecución. Hay que detener hailo-ollama al usar VLM directamente
- **`VLM.generate_all()` requiere frames**: La inferencia solo de texto da error `HAILO_INVALID_OPERATION`. LLM y VLM tienen diferentes precondiciones de API
- **Plantilla de prompt de Qwen2-VL**: Se inserta `<|vision_start|><|image_pad|><|vision_end|>` con plantilla Jinja2. Si se incluye `{"type": "image"}` en el formato de mensaje, el SDK lo procesa automáticamente

---

## Fase 12: API compatible con OpenAI + corrección de bugs de conmutación de dispositivos (2026-03-14)

### Objetivo

1. Proporcionar una API compatible con OpenAI que permita utilizar directamente Hailo GenAI desde herramientas externas como OpenAI SDK / LiteLLM / Continue.dev / Open WebUI
2. Corregir deficiencias de soporte async de Quart
3. Soporte de endpoint SSE para herramientas MCP

### Implementación: API compatible con OpenAI (`hailo_openai_routes.py`)

Se creó el nuevo archivo `extensions/builtin_hailo_genai/hailo_openai_routes.py`. Se implementaron los siguientes 4 endpoints:

| Endpoint | Función | Modelos compatibles |
|---|---|---|
| `GET /v1/models` | Lista de modelos disponibles | Todos los modelos + CLIP |
| `POST /v1/chat/completions` | Chat de texto/imagen (compatible con stream) | LLM + VLM |
| `POST /v1/audio/transcriptions` | Transcripción de voz | Whisper |
| `POST /v1/embeddings` | Texto→vector CLIP | CLIP ViT-B/16 |

#### Decisiones de diseño

- **Soporte Vision**: Acepta el formato Vision API de OpenAI (`image_url` con `data:` base64). Adicionalmente, puede referenciarse directamente con el formato `file_id:123` para imágenes de la biblioteca YU
- **URLs HTTP no soportadas**: Por razones de seguridad SSRF, `image_url` no acepta `http://` / `https://`
- **Alias de modelos**: Definición de alias compatibles con OpenAI como `whisper-1` → `whisper-base`, `clip` → `clip-vit-b-16`
- **Audio no WAV**: Conversión automática con ffmpeg (16kHz mono PCM16)
- **Campo Usage**: Fijo en `0` porque el SDK de Hailo no devuelve conteo de tokens. Margen para mejora futura

#### Herramientas MCP

- `hailo_genai_openai_info`: Herramienta auxiliar que devuelve la lista de endpoints y las instrucciones de uso (generado localmente sin llamar a la API)

### Corrección: Generadores SSE async de Quart

Había deficiencias en el soporte async de los generadores SSE en todos los archivos de ruta:

| Archivo | Problema | Corrección |
|---|---|---|
| `hailo_llm_routes.py` | `def generate_sse()` era función síncrona | Cambio a `async def`, `get_llm()` y `next(it)` ejecutados con `asyncio.to_thread` |
| `hailo_vlm_routes.py` | Igual + referencia DB síncrona | Igual + envolver con `run_db_sync` |
| `hailo_s2t_routes.py` | transcribe en ejecución síncrona + DB síncrona | `asyncio.to_thread` + envolver con `run_db_sync` |
| `hailo_chat_routes.py` | Igual (LLM/VLM ambos) | Async de todas las llamadas bloqueantes |

En Quart (ASGI), si el generador no es `async def`, el bucle de eventos se bloquea y no puede procesar otras solicitudes durante la entrega SSE. El procesamiento pesado como la inferencia de Hailo debe escaparse siempre a otro hilo con `asyncio.to_thread`.

### Bug encontrado: Inconsistencia de singleton al conmutar dispositivos

#### Síntoma

Error `'NoneType' object has no attribute 'get_context_usage_size'` al llamar a LLM después de usar VLM. También ocurre en la dirección opuesta (LLM→VLM→LLM).

#### Análisis de causa

Hailo-10H solo puede mantener un VDevice, por lo que `device_manager.py` gestiona el acceso exclusivo. Flujo al conmutar modelos:

1. `get_vlm()` de VLM → `acquire_genai("vlm", ...)` → `_release_internal()` interno libera el VDevice del LLM
2. Uso de VLM completado
3. `get_llm()` de LLM → `_instance` permanece + `model_name` también coincide → **Reutilizar instancia existente**
4. El VDevice detrás de `_instance._llm` ya ha sido liberado por `_release_internal()` de `device_manager` → `get_context_usage_size()` se llama sobre `None` y se bloquea

Raíz del problema: Incluso si el `_instance` del singleton permanece, el objeto SDK de Hailo (`self._llm`) al que apunta tiene sus recursos nativos liberados por `device_manager`. El recuento de referencias de Python mantiene `_instance._llm` vivo, pero el recurso nativo del SDK de Hailo ha sido liberado.

#### Corrección

Se añade verificación de `device_manager.get_current_owner()` a la comprobación de reutilización del singleton en `get_llm()` / `get_vlm()` / `get_s2t()`:

```python
def get_llm(model_name="qwen2.5-1.5b-chat"):
    global _instance
    with _lock:
        if _instance is not None and _instance.model_name == model_name:
            from core.hailo_device_core.device_manager import get_current_owner
            if get_current_owner() == "llm":
                return _instance  # Dispositivo retenido → reutilización OK
            # El dispositivo ha sido tomado por otro modelo → Recrear
            _instance = None
        ...
```

Se aplica la misma corrección a los 3 singletons de LLM / VLM / S2T.

#### Verificación

Se confirmó el funcionamiento correcto en 4 conmutaciones consecutivas LLM → VLM → LLM → VLM.

### Otras correcciones

- **MCP `post_sse` method**: Se añadió el método `post_sse()` a `mcp_server/client.py` que consume el stream SSE y devuelve el texto final como JSON. Lo usan las herramientas `hailo_llm_generate` y `hailo_vlm_generate`
- **Parámetro MCP `yolo_search`**: Se renombró `labels` a `class_name` (para coincidir con el nombre del parámetro del lado de la API)
- **Circuit Breaker**: Se añadieron `_READ_SUFFIXES` (`_status`, `_info`, `_list`, `_stats`). En estado half_open, se permiten herramientas de estado como `hailo_genai_status`
- **Semantic Search async**: Se envolvieron `get_encoder_info()` y `semantic_search()` con `run_db_sync` (prevención del bloqueo del bucle de eventos de Quart)

### Notas técnicas

- **La restricción de exclusión de VDevice es a nivel de SDK**: Incluso si se mantiene una referencia Python al objeto, no se puede usar si los recursos del lado nativo del SDK de Hailo han sido liberados. Al usar el patrón singleton, hay que verificar por separado la validez de los recursos nativos
- **Quart + generadores síncronos**: Pasar un generador síncrono a la respuesta SSE de Quart funciona, pero el procesamiento entre `yield` bloquea el bucle de eventos. El procesamiento pesado como la inferencia de Hailo siempre debe escaparse a otro hilo con `asyncio.to_thread`
