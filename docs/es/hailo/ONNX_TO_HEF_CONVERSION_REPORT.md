# Informe de conversión ONNX a HEF

**Fecha**: 2026-03-06
**Propósito**: Convertir modelos ONNX de WD-Tagger al formato HEF de Hailo para habilitar la inferencia en Raspberry Pi 5 + AI HAT 2 (Hailo-10H)
**Resultado**: Fallo (conversión imposible con todas las variantes del modelo)

---

## Entorno

| Elemento | Detalles |
|------|------|
| SO | Ubuntu 24.04 (WSL2) |
| Python | 3.11.13 (instalado con uv) |
| Hailo Dataflow Compiler | v5.2.0 |
| GPU | CUDA 12.8, Driver 591 |
| RAM | 151GB |

---

## Modelos probados

### 1. wd-swinv2-tagger-v3 (SwinTransformer V2)

- **Fuente**: `SmilingWolf/wd-swinv2-tagger-v3` (446MB)
- **Entrada**: `[batch, 448, 448, 3]` float32
- **Salida**: `[batch, 10861]` float32
- **Resultado**: Fallo
- **Error**: `IndexError: list index out of range` en `_convert_axes_to_nhwc`
- **Causa**: Conversión de eje de LayerNormalization no compatible con DFC v5.2.0

### 2. wd-vit-tagger-v3 (Vision Transformer)

- **Fuente**: `SmilingWolf/wd-vit-tagger-v3` (362MB)
- **Entrada**: `[batch, 448, 448, 3]` float32
- **Salida**: `[batch, 10861]` float32
- **Resultado**: Fallo
- **Error**: Igual (`IndexError` en `_convert_axes_to_nhwc`)
- **Causa**: ViT también usa LayerNormalization, falla en el mismo punto

### 3. wd-convnext-tagger-v3 (ConvNeXt)

- **Fuente**: `SmilingWolf/wd-convnext-tagger-v3` (377MB)
- **Entrada**: `[batch, 448, 448, 3]` float32
- **Salida**: `[batch, 10861]` float32
- **Resultado**: Fallo
- **Error**: `UnsupportedShuffleLayerError` (múltiples nodos Transpose) + `UnsupportedModelError` (incompatibilidad de shape en Mul)
- **Causa**: Las operaciones Transpose relacionadas con el diseño channels-last de ConvNeXt no son compatibles con DFC

---

## Causa raíz del fallo

El parser ONNX de DFC v5.2.0 no puede procesar correctamente las siguientes operaciones:

1. **LayerNormalization**: Se produce un error de índice en la conversión de ejes NHWC de LayerNorm para tensores de 3 o más dimensiones
2. **Transpose (Shuffle)**: El patrón Transpose utilizado para la conversión channels-last/first en ConvNeXt no es compatible

Todas las variantes de WD-Tagger (SwinV2, ViT, ConvNeXt) son arquitecturas modernas que hacen uso intensivo de LayerNormalization, lo que las hace imposibles de convertir con DFC v5.2.0.

---

## Datos de calibración

- Se seleccionaron aleatoriamente 500 imágenes de salida de ComfyUI / Stable Diffusion forge
- Se aplicó el mismo preprocesamiento que WD-Tagger (composición RGBA→RGB fondo blanco, redimensionamiento manteniendo relación de aspecto, relleno blanco, conversión BGR)
- Se guardaron como `calibration_data.npy`, pero no se llegó a usar porque no se alcanzó el paso de conversión

---

## Posibilidades futuras

- **Versiones futuras de DFC**: Si Hailo mejora el soporte de LayerNormalization / Transpose, vale la pena intentarlo de nuevo
- **Modificación del modelo**: Creación de un modelo modificado con LayerNorm reemplazado por BatchNorm (gran cantidad de trabajo, riesgo de degradación de precisión)
- **Mantener el estado actual**: Continuar con la inferencia en ONNX Runtime (CPU)
