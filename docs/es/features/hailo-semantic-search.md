# Extensión de Búsqueda Semántica Hailo — Especificación de Implementación

**Estado**: Implementado — La versión específica de Hailo ha sido reemplazada por CLIP ONNX (v2.95.0)
**Objetivo**: Extensión de YU AI Manager
**Propósito**: Búsqueda de imágenes semántica usando CLIP/SigLIP en Hailo-10H (AI HAT 2)
**Implementación**: `extensions/builtin_clip_search/core_impl/` (capa compartida) + `extensions/builtin_clip_onnx/core_impl/` (implementación ONNX)
**Nota**: Esta especificación describe el diseño inicial solo para Hailo. La implementación actual utiliza una arquitectura unificada de multi-backend ONNX

---

## Descripción General

Esta Extensión añade la capacidad de buscar imágenes usando texto en lenguaje natural.
Ejemplos: "cielo azul y océano", "chica sonriendo", "paisaje urbano nocturno" — todos devuelven imágenes visualmente similares.

Se requiere que funcione **en paralelo** con la búsqueda de etiquetas FTS5 existente y la búsqueda de similitud pHash.
La Extensión simplemente se desactiva en entornos donde no hay dispositivo Hailo presente.

---

## Arquitectura

```
[Durante escaneo de imagen]
Archivo de imagen -> Codificador de Imagen CLIP (Hailo HEF) -> vector 512-dim -> almacenamiento en BD

[Durante búsqueda]
Entrada de texto -> Codificador de Texto CLIP (CPU / Hailo HEF) -> vector 512-dim
           -> Búsqueda de similitud coseno -> lista file_id -> Fusionar con resultados de búsqueda existentes
```

**Tanto CLIP como SigLIP se admiten**, intercambiables vía configuración.
SigLIP ofrece mayor precisión, pero CLIP tiene un historial más fuerte y más recursos comunitarios.
El enfoque recomendado es comenzar con CLIP y añadir SigLIP después.

---

## Desglose de Fases

### Fase 1: Verificación de Factibilidad (Hacer Esto Primero)

Después de mudarse al entorno Pi5, haz que Claude Code ejecute los siguientes pasos **en orden de arriba a abajo**.
Detente en cualquier paso que falle y aborda el problema antes de continuar.

#### Paso 1-1: Verificar Tiempo de Ejecución HailoRT

```bash
# Verificar reconocimiento de dispositivo
hailortcli fw-control identify

# Verificar vinculaciones de Python
python3 -c "import hailo_platform; print('HailoRT version:', hailo_platform.__version__)"
```

- **Dispositivo no visible**: Verificar estado del controlador con `dmesg | grep hailo`. Verificar conexión PCIe de AI HAT 2
- **Importación falla**: Instalar vía `pip install hailort` o desde el repositorio APT de Hailo (`python3-hailort`)

#### Paso 1-2: Descargar Archivos HEF CLIP

```bash
mkdir -p ~/hailo_models && cd ~/hailo_models

# Codificador de imagen
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef

# Codificador de texto
wget https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_text_encoder.hef
```

- **403 / Acceso denegado**: Se requiere registro en la Zona de Desarrolladores de Hailo (https://hailo.ai/developer-zone/).
  Después del registro, intenta descargar vía CLI de Model Zoo (`hailo_model_zoo`)
- **Verificación de tamaño**: Cada archivo debe ser decenas a ~100 MB. Un archivo inusualmente pequeño indica falla de descarga

#### Paso 1-3: Instalar Dependencias de Python

```bash
# Requerido para preprocesamiento de imágenes (utilizado en Fase 1)
pip install opencv-python-headless numpy

# Verificar
python3 -c "import cv2; import numpy; print('cv2:', cv2.__version__, 'numpy:', numpy.__version__)"
```

#### Paso 1-4: Prueba de Inferencia Mínima

```python
from hailo_platform import HEF, VDevice, HailoStreamInterface, InferVStreams, ConfigureParams
import numpy as np

hef_path = "/home/<user>/hailo_models/clip_vit_b_16_image_encoder.hef"
hef = HEF(hef_path)

# Verificar información de capa HEF/output (los nombres de capas varían según el modelo)
print("Capas de entrada:", [l.name for l in hef.get_input_vstream_infos()])
print("Capas de salida:", [l.name for l in hef.get_output_vstream_infos()])

with VDevice() as target:
    configure_params = ConfigureParams.create_from_hef(hef, interface=HailoStreamInterface.PCIe)
    network_groups = target.configure(hef, configure_params)
    network_group = network_groups[0]

    input_info = hef.get_input_vstream_infos()[0]
    input_name = input_info.name
    input_shape = input_info.shape  # Esperado: (224, 224, 3) etc.
    print(f"Entrada: name={input_name}, shape={input_shape}")

    # Prueba de inferencia con imagen ficticia
    dummy = np.random.randint(0, 255, (1, *input_shape), dtype=np.uint8)
    with InferVStreams(network_group, {}) as pipeline:
        result = pipeline.infer({input_name: dummy})
        for name, data in result.items():
            print(f"Salida: name={name}, shape={data.shape}, dtype={data.dtype}")
            # Éxito si se genera un vector 512-dim
```

- **Error VDevice (`not enough free devices`)**: hailo-ollama puede estar ejecutándose. Detenerlo con `systemctl stop hailo-ollama` e intentar nuevamente
- **La inferencia tiene éxito pero la salida no es 512-dim**: Verificar la versión HEF y la variante del modelo

#### Paso 1-5: Criterios de Decisión

| Resultado | Acción Siguiente |
|------|----------------|
| Salida de vector 512-dim | Proceder a Fase 2 y más allá |
| HEF se carga exitosamente pero dimensiones de salida difieren | Probar una variante de modelo diferente (clip_resnet_50 etc.) |
| No se puede descargar HEF | Registrar en Developer Zone -> descargar vía CLI de Model Zoo |
| No se puede importar hailo_platform | Reinstalar HailoRT. Retroceder a CLIP de CPU si no se resuelve |
| Dispositivo no reconocido | Problema de conexión de hardware / controlador. Pausar desarrollo de esta Extensión |

Proceder con la implementación completa si Fase 1 tiene éxito. Considerar CLIP de CPU como alternativa si no lo hace.

---

### Fase 2: Extensión de Esquema de BD

Añadir a la migración de BD existente:

```sql
-- migración 14: vectores de búsqueda semántica
CREATE TABLE IF NOT EXISTS file_vectors (
    file_id     INTEGER PRIMARY KEY REFERENCES files(id) ON DELETE CASCADE,
    model       TEXT NOT NULL DEFAULT 'clip',   -- 'clip' | 'siglip'
    vector      BLOB NOT NULL,                  -- matriz numpy float32 -> bytes
    created_at  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE INDEX IF NOT EXISTS idx_file_vectors_model ON file_vectors(model);
```

Almacenamiento: `numpy.ndarray.tobytes()` -> BLOB
Carga: `numpy.frombuffer(blob, dtype=numpy.float32)`

**Nota**: SQLite no tiene ANN (Approximate Nearest Neighbor), por lo que todos los 200,000 registros requieren cálculo de similitud coseno completo. El cálculo por lotes con numpy debe mantener esto dentro de los límites aceptables en Pi5 (medición requerida). Considerar la extensión `sqlite-vec` si el recuento de registros crece significativamente.

---

### Fase 3: Núcleo de Inferencia Hailo

**Estructura de archivos**:
```
extensions/hailo_semantic_search/
├── __init__.py
├── extension.py          # Punto de entrada de extensión
├── core/
│   ├── hailo_clip.py     # Envoltorio de inferencia CLIP Hailo
│   ├── cpu_clip.py       # Alternancia de CPU para entornos sin Hailo (opcional)
│   └── vector_store.py   # CRUD de BD de vectores
├── routes/
│   └── semantic_search.py  # Endpoints de API
└── templates/
    └── _semantic_search_ui.html
```

**Responsabilidades de `hailo_clip.py`**:
- Carga de HEF e inicialización de VDevice (singleton, una vez al inicio)
- Imagen -> preprocesamiento (redimensionamiento 224x224, normalización) -> inferencia HEF -> vector 512-dim
- Texto -> tokenización -> inferencia HEF -> vector 512-dim
  * Utilizar HEF de codificador de texto si está disponible para Hailo-10H; de lo contrario usar CPU (librería transformers)

**Preprocesamiento**:
```python
import cv2
import numpy as np

def preprocess_image(path: str) -> np.ndarray:
    img = cv2.imread(path)
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img = cv2.resize(img, (224, 224))
    img = img.astype(np.float32) / 255.0
    mean = np.array([0.48145466, 0.4578275, 0.40821073])
    std  = np.array([0.26862954, 0.26130258, 0.27577711])
    img = (img - mean) / std
    return img[np.newaxis, ...]  # (1, 224, 224, 3)
```

---

### Fase 4: API de Construcción de Índice

**Endpoint**:
```
POST /api/extensions/hailo-semantic/index
```
- Procesa imágenes sin indexar secuencialmente en un hilo de fondo
- Envía progreso vía SSE como eventos `semantic_index.progress`
- Opcionalmente se conecta al evento existente `scan.complete` para ejecución automática

**Tamaño de lote**: 32 imágenes por lote (equilibrando memoria y velocidad)

```
GET /api/extensions/hailo-semantic/index/status
-> { "total": 200000, "indexed": 12500, "running": true }
```

---

### Fase 5: API de Búsqueda Semántica

```
GET /api/extensions/hailo-semantic/search?q=blue sky&limit=50&threshold=0.25
```

**Flujo de procesamiento**:
1. Convertir texto `q` a un vector
2. Cargar todos los vectores de `file_vectors` (numpy)
3. Calcular similitud coseno en lote
4. Ordenar resultados por encima de `threshold` por similitud descendente
5. Devolver la lista `file_id` en formato existente `/api/search`

**Cálculo de similitud coseno**:
```python
def cosine_similarity_batch(query_vec: np.ndarray, stored_vecs: np.ndarray) -> np.ndarray:
    # query_vec: (512,), stored_vecs: (N, 512)
    query_norm = query_vec / np.linalg.norm(query_vec)
    stored_norm = stored_vecs / np.linalg.norm(stored_vecs, axis=1, keepdims=True)
    return stored_norm @ query_norm  # (N,)
```

**Objetivo de rendimiento**: Menos de 1 segundo para 200,000 registros (alcanzable con cálculo por lotes numpy, incluso en Pi5)

---

### Fase 6: Integración de UI

Añadir una pestaña "Búsqueda Semántica" a la UI de búsqueda existente.
Puede ser una UI independiente separada del constructor de condiciones existente (la integración es para el futuro).

```html
<!-- Añadir botón de alternancia junto a la barra de búsqueda -->
<button id="semantic-search-toggle" class="btn-secondary">
  🔍 Búsqueda Semántica (Hailo)
</button>
```

- Ocultar o desactivar el botón cuando no se detecta dispositivo Hailo
- Reutilizar la cuadrícula existente para resultados de búsqueda
- Mostrar un mensaje para construir el índice cuando no existe índice

---

## Configuración (adición config.json)

```json
{
  "hailo_semantic_search": {
    "enabled": true,
    "model": "clip",           // "clip" | "siglip"
    "device": "auto",          // "auto" | "hailo" | "cpu"
    "batch_size": 32,
    "similarity_threshold": 0.25,
    "auto_index_on_scan": false,
    "hef_dir": "~/.local/share/hailo-ollama/models"
  }
}
```

---

## Hechos Verificados (a partir de 2026-02-27)

La siguiente información ha sido confirmada a través de investigación previa. Utilizarla como referencia durante la ejecución de la Fase 1.

### Disponibilidad de HEF CLIP

Hailo Model Zoo v5.2.0 contiene **codificadores de imagen y texto** HEF para Hailo-10H en todas las variantes de CLIP/SigLIP:

| Modelo | HEF de Codificador de Imagen | HEF de Codificador de Texto |
|--------|-------------------|-------------------|
| clip_vit_b_16 | Disponible | Disponible |
| clip_vit_b_32 | Disponible | Disponible |
| clip_vit_l_14 | Disponible | Disponible |
| clip_resnet_50 | Disponible | Disponible |
| siglip_b_16 | Disponible | Disponible |
| siglip_l_16_256 | Disponible | Disponible |
| siglip2_b_32_256 | Disponible | Disponible |
| Variantes TinyCLIP | Disponible | Disponible |

Patrón de URL de S3: `https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef`

### Estado del Codificador de Texto

- La app oficial `hailo-CLIP` ejecuta **el codificador de texto en CPU (PyTorch)**
- Los HEF de Codificador de Texto para Hailo-10H existen en Model Zoo, pero **ninguna aplicación publicada los utiliza**
- Enfoque recomendado: **Implementar el codificador de texto en CPU (`sentence-transformers`)**. Se ejecuta solo una vez por consulta de búsqueda, por lo que la velocidad no es una preocupación
- El codificador de imagen es donde la aceleración de Hailo proporciona valor real (indexación por lotes de 200K imágenes)

### Coexistencia con hailo-ollama

- El compartir dispositivo vía `SHARED_VDEVICE_GROUP_ID` se soporta oficialmente
- Sin embargo, **el binario hailo-ollama no participa en este compartir** (ocupa el dispositivo exclusivamente)
- Ejemplo comunitario: Se construyó un gestor de dispositivos personalizado para ejecutar 6 servicios simultáneamente
- **Enfoque práctico**: Detener hailo-ollama durante construcción de índice y compartir el dispositivo en el tiempo
  - `systemctl stop hailo-ollama` -> Construir índice -> `systemctl start hailo-ollama`

### Estimaciones de Búsqueda de Vectores para 200,000 Registros

- 200K x 512 float32 = aproximadamente 400MB — encaja dentro de Pi5 (8GB) RAM
- La similitud coseno numpy por lotes debe completarse dentro de 1 segundo en el Cortex-A76 de Pi5

### Aceleración FAISS para Búsqueda de Vectores a Gran Escala (v3.26.0)

Se añadió soporte de FAISS (Facebook AI Similarity Search) en v3.26.0. El sistema detecta automáticamente `faiss-cpu` cuando se instala y utiliza búsqueda de vecino más cercano aproximada en lugar de fuerza bruta NumPy.

| Escala | NumPy (O(N)) | FAISS IndexFlatIP | FAISS IndexIVFFlat |
|------|-------------|-------------------|-------------------|
| 10K | ~10ms | ~2ms | - |
| 100K | ~100ms | ~20ms | ~5ms |
| 500K | ~500ms | ~100ms | ~10ms |
| 1.5M | ~1.5s | ~300ms | ~20ms |

- **< 50K**: IndexFlatIP (búsqueda de producto interno exacta) se selecciona automáticamente
- **>= 50K**: IndexIVFFlat (agrupación IVF) se selecciona automáticamente, nprobe = nlist/10
- Se retrocede a NumPy cuando FAISS no se instala (sin impacto)

**Instalación**:
```bash
source venv/bin/activate
uv pip install faiss-cpu  # La instalación directa pip funciona en x86_64
# En aarch64 (RPi): conda install -c conda-forge faiss-cpu o compilar desde fuente
```

El registro de inicio muestra `FAISS x.x.x detected — using accelerated vector search` cuando está activo.

### Notas en la App hailo-CLIP

- `hailo-ai/hailo-CLIP` se dirige a **Hailo-8/8L**. Hailo-10H no se soporta
- Está diseñada para clasificación de cero disparos en tiempo real, no canalizaciones de búsqueda de imágenes
- Sirve como material de referencia pero no se puede usar directamente. Se debe construir una canalización personalizada usando la API HailoRT

---

## Alternativa (Cuando Hailo No Está Disponible)

`sentence-transformers` con `clip-ViT-B-32` proporciona soporte CLIP solo en CPU.
Es más lento pero permite que la misma Extensión se ejecute en entornos sin Hailo.

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('clip-ViT-B-32')
image_embedding = model.encode(Image.open(path))
text_embedding  = model.encode("blue sky")
```

Establecer `"device": "cpu"` en la configuración de Extensión habilita modo CPU. Este enfoque de arquitectura dual maximiza la portabilidad.

---

## Prioridad de Implementación

```
Fase 1 (Verificación)   -> Requerida, hacer esto primero
Fase 2 (BD)             -> Después de éxito de Fase 1
Fase 3 (Núcleo de inferencia) -> Después de Fase 2
Fase 4 (Indexación)       -> Después de Fase 3
Fase 5 (API de búsqueda)     -> Después de Fase 4
Fase 6 (UI)             -> Después de Fase 5, última
```

Cambiar el enfoque completo a CLIP de CPU si Fase 1 falla.

---

## Repositorios de Referencia

- `hailo-ai/hailo-apps`: Ejemplos de clasificación CLIP de cero disparos
- `hailo-ai/hailort`: Referencia de API pyHailoRT
- `hailo-ai/Hailo-Application-Code-Examples`: Ejemplos de inferencia en Python
- `hailo-ai/hailo_model_zoo`: Fuente de descarga HEF CLIP/SigLIP

---

*Creado: 2026-02-27*
*Apéndice de investigación: 2026-02-27 — Detalles del procedimiento Fase 1, confirmación de disponibilidad de HEF, análisis de coexistencia hailo-ollama*
