# Etiquetado Automático de Danbooru — Especificación de Implementación

**Estado**: Implementado (Fase 1-5: v2.77.0)
**Objetivo**: YU AI Manager
**Propósito**: Asignar automáticamente etiquetas de Danbooru a imágenes de IA usando un enfoque de dos niveles: WD-Tagger ONNX (CPU) + VLM (API compatible con OpenAI)
**Implementación**: `extensions/builtin_wd_tagger/core_impl/` (12 archivos), `routes/wd_tagger.py` (11 API)

---

## Estado de Implementación

| Fase | Estado | Ubicación |
|---|---|---|
| Fase 1: WD-Tagger ONNX | **Completo** | `extensions/builtin_wd_tagger/core_impl/engine_onnx.py` |
| Fase 2: VLM Engine (Compatible con OpenAI) | **Completo** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` + `engine_composite.py` |
| Fase 3: Postprocesamiento de Etiquetas | **Completo** (v2.77.0) | `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` |
| Fase 4: API por Lotes | **Completo** | `extensions/builtin_wd_tagger/core_impl/batch_ops.py` + `routes/wd_tagger.py` |
| Fase 5: UI | **Completo** | Página de Herramientas + insignias de etiqueta WD de modal detallado + visor XMP |

### Descripción General de Implementación de Fase 2/3 (v2.77.0-v2.77.1)

- **VLM Engine** (`engine_vlm.py`): Alternancia automática entre API compatible con OpenAI y API nativa de Ollama
- **Composite Engine** (`engine_composite.py`): Canalización de dos niveles ONNX + VLM (Modo B)
- **Postprocesamiento de Etiquetas** (`tag_postprocess.py`): Normalización (minúsculas, guion bajo, eliminación de caracteres inválidos, deduplicación) + filtro NSFW (~30 etiquetas)
- **Engine Factory**: Enrutamiento por `engine_type` ("onnx" / "vlm" / "both")
- **UI**: Selección de tipo de motor, configuración de URL/modelo/timeout de VLM, prueba de conexión, filtro NSFW
- **API**: `GET /api/wd-tagger/vlm/test`, `GET /api/wd-tagger/vlm/models`
- **MCP**: herramientas `wd_tagger_vlm_test`, `wd_tagger_vlm_models`
- **Probado**: Etiquetado de imagen real confirmado con Ollama qwen2.5vl:7b, 23 pruebas unitarias pasando

---

## Arte Previo

### DeepDanbooru (KichangKim)
- **Enfoque**: Modelo de clasificación de imágenes (TensorFlow) para predicción directa de etiquetas
- **Fortalezas**: Rápido, especializado en etiquetas, convertible a ONNX
- **Debilidades**: Conjunto de etiquetas fijo, no puede adaptarse a nuevas etiquetas
- **Referencia**: Ya integrado en A1111

### WD-Tagger (SmilingWolf) — Adoptado en Fase 1
- **Enfoque**: Sucesor de DeepDanbooru. Cuatro arquitecturas: SwinV2/ViT/ConvNeXt/EVA02
- **Fortalezas**: Mayor precisión que DeepDanbooru, incluye clasificación de categorías (general/character/copyright/rating)
- **ONNX**: Modelos ONNX oficiales + `selected_tags.csv` distribuidos en HuggingFace
- **Entrada**: 224x224 RGB (relación de aspecto preservada + relleno blanco)

### DanTagGen / DTG (KohakuBlueleaf)
- **Enfoque**: LLM basado en LLaMA (400M) para generación y finalización de etiquetas
- **Fortalezas**: Finalización de etiquetas consciente del contexto
- **Debilidades**: Lento debido a inferencia LLM
- **HuggingFace**: `KBlueLeaf/DanTagGen-beta`

### Lógica del Diseño
El sistema soporta **tanto** WD-Tagger ONNX (rápido, confiable) como Qwen2-VL vía hailo-ollama (flexible, consciente del contexto), para que los usuarios puedan elegir la herramienta adecuada para el trabajo.

---

## Arquitectura

```
[Entrada de Imagen]
    |
[Selección de Motor]  (engine_factory.py)
    |-- WD-Tagger ONNX (rápido, conjunto de etiquetas fijo ~10,000 etiquetas)  [Fase 1: implementado]
    |       | Puntuaciones de confianza + lista de etiquetas categorizadas
    |-- Qwen2-VL vía hailo-ollama (lento, flexible, consciente del contexto)   [Fase 2]
    |       | Array JSON -> análisis de etiquetas
    |-- Dos niveles: ONNX -> complemento Qwen2-VL                    [Opción Fase 2]
    |       | Alimentar etiquetas ONNX en el prompt, dejar que LLM genere etiquetas adicionales
    |
[Postprocesamiento: normalización de etiquetas, filtrado NSFW]  [Fase 3]
    |
[BD: guardar en tabla file_wd_tags]  (store.py)
[XMP: incrustar en archivo (opcional)]  (xmp_write.py)
```

---

## Fase 1: Motor WD-Tagger ONNX — Implementado

**Modelo**: SmilingWolf/wd-swinv2-tagger-v3 (recomendado), ViT v3, ConvNeXt v3, EVA02-Large v3

**Archivos de implementación** (`extensions/builtin_wd_tagger/core_impl/`):
| Archivo | Líneas | Rol |
|---|---|---|
| `types.py` | ~60 | TagPrediction, WdTagResult, WdTaggerEngine ABC |
| `tag_csv.py` | ~70 | Análisis de selected_tags.csv, mapeo de categorías |
| `model_download.py` | ~120 | Descarga HTTP de HuggingFace |
| `engine_onnx.py` | ~150 | Inferencia ONNX (224x224, BGR, filtrado de umbral) |
| `engine_factory.py` | ~50 | Caché de motor + creación |
| `store.py` | ~130 | CRUD de BD (tabla file_wd_tags) |
| `xmp_xml.py` | ~60 | Construcción de paquete XMP |
| `xmp_read.py` | ~90 | Lectura de XMP |
| `xmp_write.py` | ~160 | Escritura de XMP en PNG/JPEG/WebP |
| `config_ops.py` | ~70 | Lectura/escritura de config.json |
| `single_ops.py` | ~80 | Canalización de etiquetado de imagen única |
| `batch_ops.py` | ~120 | Procesamiento por lotes (integración JobManager) |

**BD**: tabla `file_wd_tags` (esquema v14)
```sql
CREATE TABLE file_wd_tags (
    id         INTEGER PRIMARY KEY,
    file_id    INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    tag_name   TEXT NOT NULL,
    confidence REAL NOT NULL,
    category   TEXT NOT NULL DEFAULT 'general',
    model      TEXT NOT NULL,
    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
    UNIQUE(file_id, tag_name, model)
);
```

**API**: `routes/wd_tagger.py` — 11 endpoints

---

## Fase 2: VLM Engine (API Compatible con OpenAI) — Implementado (v2.77.0)

**Propósito**: Complementar WD-Tagger ONNX con descripciones detalladas y etiquetas contextuales que ONNX no puede capturar
**Implementación**: `extensions/builtin_wd_tagger/core_impl/engine_vlm.py` (motor VLM genérico compatible con OpenAI)
**Nota**: La especificación original planificaba un `engine_hailo.py` específico de Hailo, pero la implementación real utiliza un motor genérico `engine_vlm.py` que maneja Ollama, hailo-ollama y otros servidores compatibles con OpenAI uniformemente. Soporta alternancia automática entre la API compatible con OpenAI (`/v1/chat/completions`) y la API nativa de Ollama (`/api/chat`).

### Configuración de Hardware

| Elemento | Especificación |
|---|---|
| **Dispositivo** | Raspberry Pi 5 + acelerador de IA Hailo-10H |
| **Memoria** | 8GB RAM |
| **Modelo VLM** | **Qwen2-VL-2B-Instruct** (único VLM en el Hailo Model Zoo) |
| **Marco de Inferencia** | hailo-ollama (API compatible con OpenAI) |
| **Endpoint** | `http://<pi-ip>:8000/v1/chat/completions` |

### Características del Modelo

- **Qwen2-VL-2B-Instruct**: Un modelo Vision-Language de la familia Qwen (parámetros 2B)
- Pertenece a la familia Qwen, no a la familia llava. La precisión de comprensión de imágenes es generalmente más alta que los modelos basados en llava
- Con parámetros 2B, encaja cómodamente dentro de los 8GB RAM de Hailo-10H
- Se ha confirmado que Qwen2 solo de texto (1.5B) funciona con hailo-ollama
- **Nota**: A partir de 2026-02, este es el único VLM disponible para Hailo-10H

### Diseño de Prompt

```python
SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
Analyze the image and output ONLY Danbooru-style tags as a JSON array.
Rules:
- Use underscores instead of spaces (e.g., long_hair, blue_eyes)
- Output ONLY the JSON array, no other text
- Include tags for: character count, gender, hair, eyes, clothing, pose, background, art style
- Do NOT include copyright or character name tags unless clearly identifiable
- Maximum 40 tags
Example output: ["1girl", "solo", "long_hair", "blue_eyes", "smile"]"""

USER_PROMPT = "Tag this image with Danbooru tags."
```

### Diseño de Implementación (`extensions/builtin_wd_tagger/core_impl/engine_hailo.py` — ~100 líneas)

```python
import base64
import json
import logging
import urllib.request
from pathlib import Path

from .types import TagPrediction, WdTagResult, WdTaggerEngine

logger = logging.getLogger(__name__)

_USER_AGENT = "YU-AI-Manager/2.0 (WD-Tagger Qwen2-VL)"

class HailoQwen2VLEngine(WdTaggerEngine):
    """Qwen2-VL-2B-Instruct vía hailo-ollama (API compatible con OpenAI)."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        model: str = "qwen2-vl:2b",
        timeout: int = 60,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def tag_image(self, image_path: str) -> WdTagResult:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()

        # Inferencia de tipo MIME
        suffix = Path(image_path).suffix.lower()
        mime = {"png": "image/png", "webp": "image/webp"}.get(
            suffix.lstrip("."), "image/jpeg"
        )

        payload = json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {
                            "url": f"data:{mime};base64,{image_b64}"
                        }},
                        {"type": "text", "text": USER_PROMPT},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 512,
            "temperature": 0.3,
        }).encode()

        req = urllib.request.Request(
            f"{self._base_url}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
        )

        resp = urllib.request.urlopen(req, timeout=self._timeout)
        data = json.loads(resp.read())
        content = data["choices"][0]["message"]["content"]
        raw_tags = json.loads(content)

        # Formato de respuesta: lista o {"tags": [...]}
        if isinstance(raw_tags, dict) and "tags" in raw_tags:
            raw_tags = raw_tags["tags"]
        if not isinstance(raw_tags, list):
            raw_tags = []

        tags = []
        for t in raw_tags:
            name = str(t).strip().lower().replace(" ", "_")
            if name:
                tags.append(TagPrediction(
                    tag=name,
                    confidence=0.5,  # Los LLM no devuelven puntuaciones de confianza
                    category="general",
                ))

        return WdTagResult(tags=tags, model=self._model)

    def get_name(self) -> str:
        return f"Qwen2-VL ({self._model})"

    def is_available(self) -> bool:
        """Verificar conectividad al servidor hailo-ollama."""
        try:
            req = urllib.request.Request(
                f"{self._base_url}/v1/models",
                headers={"User-Agent": _USER_AGENT},
            )
            resp = urllib.request.urlopen(req, timeout=5)
            return resp.status == 200
        except Exception:
            return False
```

### Modos de Operación

**Modo A: Qwen2-VL Independiente**
```
Imagen -> Qwen2-VL -> array JSON de etiquetas -> Normalización -> guardado en BD
```
- El LLM analiza directamente la imagen y genera etiquetas
- Sin puntuaciones de confianza (uniformemente establecidas en 0.5)
- Etiquetado flexible sin conjunto de etiquetas fijo
- Velocidad: ~3-10 segundos por imagen (estimado en Hailo-10H)

**Modo B: Complemento WD-Tagger ONNX -> Qwen2-VL (Dos niveles)**
```
Imagen -> WD-Tagger ONNX -> Etiquetas de alta confianza (>=0.7)
                              |
                              v
    Qwen2-VL: "Estas etiquetas describen la imagen. Sugiere etiquetas adicionales."
                              |
                              v
    Etiquetas ONNX + etiquetas complementarias LLM -> Fusión -> Normalización -> guardado en BD
```
- Combina etiquetas ONNX confiables con la comprensión contextual del LLM
- Incluir etiquetas ONNX en el prompt debe mejorar la precisión del LLM
- Velocidad: ONNX (~0.5s) + LLM (~3-10s) = ~4-11 segundos por imagen

**Prompt del Modo B**:
```python
补完_SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
The image already has these tags from automated classification: {existing_tags}
Analyze the image and suggest ADDITIONAL Danbooru-style tags not in the list above.
Output ONLY a JSON array of new tags. Use underscores instead of spaces.
Focus on: composition, mood, background details, specific clothing items, art style.
Maximum 20 additional tags.
Example: ["looking_at_viewer", "outdoors", "cloudy_sky", "pleated_skirt"]"""
```

### Adición a engine_factory.py

```python
# Adición a get_engine() en engine_factory.py

engine_type = config.get("engine_type", "onnx")  # "onnx" | "hailo" | "both"

if engine_type == "hailo":
    from .engine_hailo import HailoQwen2VLEngine
    engine = HailoQwen2VLEngine(
        base_url=config.get("hailo_url", "http://localhost:8000"),
        model=config.get("hailo_model", "qwen2-vl:2b"),
        timeout=config.get("hailo_timeout", 60),
    )
elif engine_type == "both":
    # Dos niveles: complemento ONNX -> Hailo (opción Fase 2)
    ...
```

### Entradas config.json

```json
{
  "wd_tagger": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "general_threshold": 0.35,
    "character_threshold": 0.85,
    "write_xmp": true,
    "auto_download": true,
    "engine_type": "onnx",
    "hailo_url": "http://localhost:8000",
    "hailo_model": "qwen2-vl:2b",
    "hailo_timeout": 60
  }
}
```

### Verificación Previa a Implementación (Prueba de Hardware de Pi)

1. **Confirmar que Qwen2-VL-2B-Instruct se lanza en hailo-ollama**
   ```bash
   # En la Pi
   hailo-ollama run qwen2-vl:2b
   ```

2. **Confirmar que las solicitudes de visión funcionan a través de la API compatible con OpenAI**
   ```bash
   curl -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{
       "model": "qwen2-vl:2b",
       "messages": [{"role": "user", "content": [
         {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/..."}},
         {"type": "text", "text": "What is in this image?"}
       ]}],
       "max_tokens": 256
     }'
   ```

3. **Confirmar que la salida JSON en formato Danbooru es estable**
   - Verificar que hailo-ollama soporta `response_format: json_object`
   - Se necesita una alternancia fallback de extracción de JSON basada en regex de salida de texto si no se admite

4. **Medir velocidad real de inferencia** — segundos por imagen (requerido para cálculo de tamaño de lote)

---

## Fase 3: Postprocesamiento de Etiquetas — Implementado (v2.77.0)

**Implementación**: `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py`
**Integración**: Aplicado automáticamente después de inferencia en `single_ops.py` / `batch_ops.py`

```python
class TagPostProcessor:
    INVALID_CHARS = set('[](){}"\'/\\')
    MAX_TAG_LEN = 100

    def normalize(self, tags: list[str]) -> list[str]:
        result = []
        for tag in tags:
            tag = tag.strip().lower()
            tag = tag.replace(" ", "_")
            # Eliminar caracteres inválidos
            tag = "".join(c for c in tag if c not in self.INVALID_CHARS)
            if 1 <= len(tag) <= self.MAX_TAG_LEN:
                result.append(tag)
        # Deduplicar y ordenar
        return sorted(set(result))

    def filter_nsfw(self, tags: list[str], allow_nsfw: bool) -> list[str]:
        # Lista de etiquetas NSFW (gestionada en archivo separado)
        if allow_nsfw:
            return tags
        return [t for t in tags if t not in NSFW_TAG_SET]
```

**Integración con Fase 1**:
- WD-Tagger ONNX ya separa etiquetas de calificación usando categoría 9 (rating)
- El filtro NSFW utiliza etiquetas de calificación (`explicit`, `questionable`) más una lista NSFW adicional
- Implementación: `extensions/builtin_wd_tagger/core_impl/tag_postprocess.py` (~80 líneas)

---

## Fase 4: API de Procesamiento por Lotes — Implementado

**API** (`routes/wd_tagger.py`):

| Método | Ruta | Propósito |
|---|---|---|
| POST | `/api/wd-tagger/batch` | Iniciar lote (file_ids, limit, force) |
| POST | `/api/wd-tagger/tag/<file_id>` | Etiquetar una imagen |
| GET | `/api/wd-tagger/tags/<file_id>` | Recuperar etiquetas |
| DELETE | `/api/wd-tagger/tags/<file_id>` | Eliminar etiquetas |
| GET | `/api/wd-tagger/stats` | Estadísticas |
| GET | `/api/wd-tagger/untagged` | Listar archivos sin etiquetas |
| GET/POST | `/api/wd-tagger/config` | CRUD de configuración |
| POST | `/api/wd-tagger/model/download` | Descarga de modelo |
| GET | `/api/wd-tagger/model/status` | Estado del modelo |
| GET | `/api/wd-tagger/xmp/<file_id>` | Lectura de XMP |

**Flujo de procesamiento** (`batch_ops.py`):
1. Procesar archivos en `file_ids` secuencialmente (por defecto archivos sin etiquetas con `meta_source=unknown` cuando no se especifica)
2. Ejecutar inferencia a través del motor
3. UPSERT en la tabla `file_wd_tags` (motor identificado por la columna model)
4. Incrustar XMP en el archivo (opcional)
5. Rastrear progreso y soportar cancelación vía JobManager

---

## Fase 5: UI — Implementado

**Página de Herramientas** (`templates/tools/content/primary/_wd_tagger.html`):
- Selección de modelo (4 modelos), deslizadores de umbral (general/character)
- Alternancia de escritura de XMP, botón de descarga de modelo
- Botón de ejecución por lotes + barra de progreso
- Visualización de estadísticas (recuento de etiquetas, desglose por categoría, recuento sin etiquetar)

**Modal detallado**:
- Insignias de etiqueta WD (general=azul, character=verde, copyright=naranja, rating=rojo)
- Botón de visor de XMP (dc:subject + espacio de nombres wdtag + XML sin formato)
- Clic en etiqueta desencadena búsqueda

---

## Estructura de Archivos (Actual)

```
extensions/builtin_wd_tagger/core_impl/
├── __init__.py              # Inicialización de módulo
├── types.py                 # TagPrediction, WdTagResult, WdTaggerEngine ABC
├── tag_csv.py               # Análisis de selected_tags.csv
├── model_download.py        # Descarga de modelo de HuggingFace
├── engine_onnx.py           # Inferencia WD-Tagger ONNX [Fase 1]
├── engine_vlm.py            # Motor VLM (compatible con OpenAI) [Fase 2: completo]
├── engine_composite.py      # Dos niveles ONNX + VLM [Fase 2: completo]
├── engine_factory.py        # Creación de motor + caché
├── store.py                 # CRUD de BD (file_wd_tags)
├── xmp_xml.py               # Construcción de paquete XMP
├── xmp_read.py              # Lectura de XMP
├── xmp_write.py             # Escritura de XMP (PNG/JPEG/WebP)
├── config_ops.py            # Lectura/escritura de config.json
├── single_ops.py            # Canalización de etiquetado de imagen única
├── batch_ops.py             # Procesamiento por lotes (JobManager)
├── batch_processors.py      # Lógica interna de procesamiento por lotes
└── tag_postprocess.py       # Normalización de etiquetas, filtro NSFW [Fase 3: completo]

routes/wd_tagger.py          # Endpoints de API (11 total)

src/ts/tools-page/wd-tagger/
├── core.ts                  # CRUD de configuración, lote, descarga de modelo
└── render.ts                # Renderizado de DOM

src/ts/runtime-tools-ui/tools/
└── wd-tags.ts               # Etiquetas WD de modal detallado + visor de XMP
```

---

## Prioridad de Implementación (Actualizada)

```
Fase 1 (WD-Tagger ONNX)        -> Completo
Fase 4 (API por Lotes)          -> Completo
Fase 5 (UI)                     -> Completo
Fase 3 (Postprocesamiento/NSFW) -> Siguiente (~80 líneas adicionales)
Fase 2 (Qwen2-VL hailo-ollama)  -> Después de prueba de hardware de Pi (~100 líneas adicionales + cambios de factory)
```

---

## Referencias

- WD-Tagger (SmilingWolf): https://huggingface.co/SmilingWolf/wd-swinv2-tagger-v3
- DeepDanbooru: https://github.com/KichangKim/DeepDanbooru
- DanTagGen: https://huggingface.co/KBlueLeaf/DanTagGen-beta
- Hailo Model Zoo VLM: Qwen2-VL-2B-Instruct (hailo.ai Model Explorer)
- Especificación de API hailo-ollama: Consultar la fuente de bifurcación modificada

---

*Creado: 2026-02-27 / Actualizado: 2026-02-27 (implementación de Fase 1 completa, Fase 2 revisada para base Qwen2-VL)*
