# Evaluación del Ecosistema Hailo-10H

**Fecha de creación**: 2026-03-19  
**Objetivo**: Hailo-10H (AI HAT 2 para Raspberry Pi 5)  
**HailoRT**: v5.2.0  
**DFC**: v5.2.0  
**Propósito**: Registrar la experiencia de desarrollo con Hailo-10H en este proyecto y organizar las limitaciones realistas y las perspectivas futuras

---

## Evaluación general

**El hardware es excelente. El ecosistema de software es decisivamente insuficiente.**

Hailo-10H es una NPU con 40 TOPS de rendimiento de inferencia y tiene suficiente potencial como hardware. Sin embargo, dado que la cadena de herramientas de software es cerrada e inmadura, los desarrolladores **prácticamente no pueden** traer sus propios modelos y ejecutarlos libremente.

En este proyecto se ha desarrollado la utilización multifacética de Hailo-10H para búsqueda semántica CLIP, detección de objetos YOLO, chat LLM/VLM, reconocimiento de voz Whisper y un servidor de etiquetado distribuido. Sin embargo, todo lo que funciona de manera estable **usa archivos HEF precompilados descargados desde el Model Zoo oficial de Hailo**, y **no ha habido ni un solo caso** de conversión exitosa de ONNX a HEF de forma independiente.

---

## Estado de implementación en este proyecto

### Funciones que funcionan (todas con HEF oficial descargado)

| Función | API utilizada | Fuente del HEF |
|------|---------|-----------|
| Codificador de imagen CLIP | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| Detección de objetos YOLO | `VDevice.create_infer_model()` | Hailo Model Zoo (S3) |
| Chat LLM | `hailo_platform.genai.LLM` | Hailo GenAI Model Zoo |
| Inferencia VLM imagen+texto | `hailo_platform.genai.VLM` | Hailo GenAI Model Zoo |
| Reconocimiento de voz Whisper | `hailo_platform.genai.Speech2Text` | Hailo GenAI Model Zoo |

### Funciones que no funcionaron (fallo de conversión HEF)

| Función | Intento | Resultado |
|------|-----------|------|
| WD-Tagger (SwinV2) | Conversión ONNX → HEF | Fallo: DFC no puede procesar LayerNormalization |
| WD-Tagger (ViT) | Conversión ONNX → HEF | Igual que arriba |
| WD-Tagger (ConvNeXt) | Conversión ONNX → HEF | Fallo: DFC no puede procesar operación Transpose |

### Notas destacadas de implementación

En este proyecto se implementaron todas las funciones **llamando directamente** a la API Python de la wheel `hailo_platform`. No se utilizaron hailo-ollama ni hailo-apps.

Los siguientes son elementos que se construyeron de forma independiente antes de que Hailo los proporcionara oficialmente:

- **Gestor de dispositivos VDevice con control exclusivo** — Conmutación automática entre CLIP/YOLO/LLM/VLM/S2T con un solo VDevice. hailo-apps no tiene un mecanismo de compartición de dispositivos
- **Fallback multi-backend** — Conmutación transparente automática Hailo → CoreML → ONNX Runtime
- **Pipeline de descuantización uint8** — Restauración de float32 desde scale/zero_point de `quant_info`
- **Arquitectura de inferencia distribuida LAN** — Etiquetado paralelo con robo de trabajo entre múltiples máquinas

Estos desarrollos se realizaron **con prácticamente ninguna documentación de API**. La especificación de E/S de la InferModel API, los requisitos de tamaño de buffer y el método de obtención de parámetros de cuantización se descifraron a partir de mensajes de error y análisis del código fuente.

---

## Problemas del Hailo Dataflow Compiler (DFC)

### Qué es DFC

Un compilador para convertir modelos ONNX / TensorFlow al formato HEF (Hailo Executable Format) para uso con Hailo-10H. Funciona en Linux x86_64 y convierte modelos con el siguiente pipeline:

```
model.onnx → HAR (float32) → optimización → cuantización (INT8) → compilación → model.hef
```

### La realidad

**DFC solo puede convertir correctamente arquitecturas prevalidadas por Hailo para su propio Model Zoo.**

Intentos de conversión en este proyecto (2026-03-06, DFC v5.2.0):

| Modelo | Tamaño | Error | Etapa alcanzada |
|--------|-------|--------|---------|
| wd-swinv2-tagger-v3 | 446 MB | `IndexError` en `_convert_axes_to_nhwc` | Antes de la optimización |
| wd-vit-tagger-v3 | 362 MB | Igual | Antes de la optimización |
| wd-convnext-tagger-v3 | 377 MB | `UnsupportedShuffleLayerError` | Antes de la optimización |

Los 3 modelos fallaron **a nivel del parser** antes de alcanzar la etapa de optimización. Se prepararon 500 imágenes de calibración pero nunca se llegaron a usar.

### Causa raíz

El parser ONNX de DFC no puede procesar los siguientes operadores:

- `LayerNormalization` (conversión de eje en tensores multidimensionales)
- `Transpose` (patrones de conversión channels-last/first)

Estos son componentes básicos de arquitecturas basadas en Transformer (SwinV2, ViT, ConvNeXt, etc.) y son utilizados por la gran mayoría de los modelos modernos desde 2022.

### Alcance real de DFC

| Arquitectura | Soporte DFC | Evidencia |
|---------------|---------|------|
| ResNet, MobileNet y similares CNN | ✓ Compatible | Muchos en Model Zoo |
| YOLO v5/v8/v11 | ✓ Compatible | HEF disponible en Model Zoo |
| CLIP ViT (versión Hailo) | ✓ Compatible | HEF en Model Zoo (convertido por Hailo) |
| SwinTransformer V2 | ✗ No compatible | Fallo de conversión LayerNorm |
| Vision Transformer (genérico) | ✗ No compatible | Fallo de conversión LayerNorm |
| ConvNeXt | ✗ No compatible | Fallo de conversión Transpose |

> **Nota**: Que CLIP ViT esté en el Model Zoo probablemente se debe a que Hailo hizo un tratamiento especial internamente (transformaciones manuales del grafo o parsers personalizados). El mismo ViT falla cuando los usuarios generales intentan convertirlo con DFC.

---

## Problemas con el formato HEF

- **La especificación binaria no es pública** — Hailo no publica documentación del formato
- **No hay otras formas de generarlo** — Es imposible crear un HEF con herramientas de terceros
- **La ingeniería inversa tampoco es realista** — Requiere conocimiento del conjunto de instrucciones y la arquitectura de flujo de datos de la NPU

Es decir, los modelos que DFC no puede convertir **no pueden ejecutarse en Hailo-10H de ninguna manera**. No existen alternativas.

---

## Evaluación de la cadena de herramientas de desarrollo

### hailo_platform (Python SDK)

| Elemento | Evaluación |
|------|------|
| InferModel API | Funciona, pero documentación extremadamente escasa |
| API GenAI (LLM/VLM/S2T) | Relativamente fácil de usar. Pero muchos comportamientos no documentados |
| Distribución de wheel Python | No en PyPI. La wheel aarch64 requiere compilación desde el código fuente |
| Mensajes de error | Mínimos. Difícil identificar la causa de discrepancias en el tamaño del buffer |
| Gestión VDevice | Solo acceso exclusivo. No se pueden usar múltiples modelos simultáneamente |

### Comportamientos no documentados descubiertos durante el desarrollo

1. **InferModel API es la correcta** — La antigua API VStreams (`InferVStreams`, `ConfigureParams.create_from_hef`) devuelve `HAILO_NOT_IMPLEMENTED` en Hailo-10H
2. **La salida es uint8 cuantizado** — Reservar el buffer como float32 da `buffer size mismatch`. Hay que reservarlo como uint8 y descuantizar después
3. **`input()`/`output()` son propiedades** — No son métodos (inconsistente con otras APIs de Hailo)
4. **Obtención de `quant_info`** — Se puede obtener scale/zero_point con `infer_model.output().quant_info`, pero no hay documentación que lo explique
5. **Exclusión mutua con hailo-ollama** — Hay que detener hailo-ollama mientras se usa VDevice. La causa no es obvia a partir del mensaje de error

---

## Comparación con competidores

### Ryzen AI (XDNA) NPU

| Elemento | Hailo-10H | Ryzen AI (XDNA) |
|------|----------|-----------------|
| Rendimiento | 40 TOPS | 16〜50 TOPS (según generación) |
| Traer modelos propios | Conversión DFC obligatoria, generalmente falla | **ONNX Runtime compatible directamente** |
| Experiencia del desarrollador | Cadena de herramientas propietaria, documentación escasa | `pip install onnxruntime-directml` basta |
| Ecosistema | Cerrado, dependiente de Model Zoo | ONNX / DirectML / colaboración con Microsoft |
| Unidades distribuidas | Pi + AI HAT, dongle USB (previsto) | **Millones de portátiles con NPU integrada** |

La integración con Ryzen AI se completa con solo:

```python
import onnxruntime as ort
session = ort.InferenceSession("model.onnx", providers=["DmlExecutionProvider"])
```

Lo mismo es imposible con Hailo-10H. No existe un Execution Provider de ONNX Runtime.

### NVIDIA CUDA

| Elemento | Hailo-10H | NVIDIA CUDA |
|------|----------|-------------|
| Traer modelos propios | Vía DFC, generalmente falla fuera de Model Zoo | ONNX / PyTorch / TensorFlow → funciona directamente |
| Cadena de herramientas | Inmadura, semicerrada | Madura, abierta, documentación abundante |
| Comunidad de desarrolladores | Extremadamente pequeña | La más grande del mundo |
| Rango de precios | Barato (~$70) | Caro ($200〜$2000+) |

La única ventaja de Hailo es el **precio y el consumo energético**.

---

## Relación con hailo-apps (2025-10)

### Resumen de hailo-apps

Colección de aplicaciones oficiales lanzada por Hailo en octubre de 2025. Incluye más de 20 aplicaciones de muestra:

- GenAI: voice_assistant, vlm_chat, agent_tools_example, whisper
- Pipeline: detección de objetos, estimación de pose, reconocimiento facial, clasificación CLIP, OCR
- Standalone: demos de aprendizaje de HailoRT en Python/C++

### Comparación con este proyecto

| Elemento | hailo-apps | Este proyecto |
|------|-----------|-------------|
| Soporte VLM | app vlm_chat | Implementación directa de `hailo_platform.genai.VLM` |
| CLIP | app clip | Integrado como sistema de búsqueda semántica |
| LLM | simple_llm_chat | Integrado como extensión GenAI |
| Whisper | simple_whisper_chat | Integrado como extensión Speech-to-Text |
| Gestión de dispositivos | Ninguna (asume app única) | **Gestor de dispositivos con control exclusivo (conmutación automática CLIP/YOLO/LLM/VLM/S2T)** |
| Fallback de backend | Ninguno | **Conmutación automática Hailo → CoreML → ONNX** |
| Inferencia distribuida | Ninguna | **Robo de trabajo distribuido LAN** |
| Nivel de integración | Apps demo individuales | Aplicación WebUI única e integrada |

Este proyecto había construido software de integración superior a hailo-apps antes de que se publicaran, a partir de las APIs de bajo nivel de la wheel `hailo_platform`. Sin embargo, incluso así no se pudo lograr la ejecución NPU de modelos personalizados (WD-Tagger) debido a las limitaciones de DFC.

---

## Perspectivas futuras

### Corto plazo (realista)

- **ONNX Runtime + distribución LAN es la única solución práctica** — Operación con backend ONNX del servidor de etiquetado distribuido
- Hailo-10H se usa solo para usos con HEF oficial disponible (YOLO, CLIP, LLM, Whisper)
- Se abandona la ejecución NPU de modelos personalizados

### Mediano plazo (esperanzador)

- ASUS y otros lanzarán dongles USB con Hailo-10H → aumento de usuarios
- Con el aumento de usuarios, puede haber presión sobre Hailo para mejorar las herramientas
- Posibilidad de que futuras versiones de DFC añadan soporte para arquitecturas Transformer

### Largo plazo (desafíos estructurales)

- A menos que Hailo proporcione un Execution Provider de ONNX Runtime, perderán ante Ryzen AI (XDNA) en el ecosistema de desarrolladores
- Incluso si el hardware prolifera con dongles USB, si no hay libertad de software, seguirá siendo "una llave que ejecuta YOLO rápido"
- El potencial de 40 TOPS seguirá aprovechándose solo con los pocos modelos del Model Zoo

---

## Resumen

Hailo-10H tiene un excelente rendimiento de hardware de 40 TOPS, pero el cierre e inmadurez del ecosistema de software lo hace **prácticamente imposible** para que los desarrolladores traigan y utilicen libremente sus propios modelos.

En este proyecto se construyó software de integración superior a la colección de aplicaciones oficiales de Hailo (hailo-apps) mediante la exploración a tientas de APIs no documentadas. Sin embargo, incluso así, la ejecución NPU de modelos personalizados (WD-Tagger) no fue posible debido a las limitaciones de DFC.

**"Las herramientas son demasiado escasas para que el desarrollo sea prácticamente posible"** — Esta es la conclusión honesta después de meses de desarrollo con Hailo-10H.

---

## Documentos relacionados

- [`HAILO_SEMANTIC_SEARCH_DEVLOG.md`](./HAILO_SEMANTIC_SEARCH_DEVLOG.md) — Registro de desarrollo de la búsqueda semántica CLIP (Fases 1〜12+)
- [`ONNX_TO_HEF_CONVERSION_GUIDE.md`](./ONNX_TO_HEF_CONVERSION_GUIDE.md) — Guía de conversión DFC (material de referencia)
- [`ONNX_TO_HEF_CONVERSION_REPORT.md`](./ONNX_TO_HEF_CONVERSION_REPORT.md) — Informe de fallo de conversión de WD-Tagger
- [`CLIP_ONNX_DEVLOG.md`](./CLIP_ONNX_DEVLOG.md) — Registro de desarrollo del fallback CLIP ONNX
- [`HAILO_DEVICE_CONTROL.md`](./HAILO_DEVICE_CONTROL.md) — Diseño de gestión de dispositivos VDevice
- [`../features/distributed-tagger-server.md`](../features/distributed-tagger-server.md) — Documentación del servidor de etiquetado distribuido
