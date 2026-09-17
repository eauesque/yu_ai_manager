# Seguimiento DFC: Reverificación de modelos WD-Tagger con DFC v5.3.0

**Fecha**: 2026-04-06
**Versión DFC**: 5.3.0
**Informe anterior**: [`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md) (2026-03-06)
**Entorno**: WSL2 (Ubuntu 24.04), x86_64

---

## Antecedentes

En marzo de 2026, se reportó que las 3 variantes de WD-Tagger (SwinV2, ViT, ConvNeXt)
fallaban todas en la etapa del parser de Hailo Dataflow Compiler v5.2.0, sin alcanzar
el paso de cuantización. El informe original está guardado en
[`ONNX_TO_HEF_CONVERSION_REPORT.md`](ONNX_TO_HEF_CONVERSION_REPORT.md).

Se lanzó DFC v5.3.0, por lo que aquí se registran los resultados de reverificar los mismos 3 modelos.

---

## Resumen de resultados

| Modelo | Tamaño | Error DFC 5.2.0 | Error DFC 5.3.0 | Cambio |
|---|---|---|---|---|
| `wd-swinv2-tagger-v3` | 446 MB | `IndexError` en `_convert_axes_to_nhwc` | Idéntico | **Ninguno** |
| `wd-vit-tagger-v3` | 362 MB | Igual | Idéntico (también después de reintento con onnxsim) | Solo se agregó flujo de reintento |
| `wd-convnext-tagger-v3` | 377 MB | `UnsupportedShuffleLayerError` | Igual + `UnsupportedModelError` adicional | **Aumentaron los errores** |

**Los 3 modelos siguen fallando en la etapa del parser**. Las 500 imágenes de calibración
preparadas siguen sin usarse, igual que con v5.2.0.

---

## Qué cambió en DFC v5.3.0

Aunque los fallos continúan, se observan las siguientes mejoras comparado con v5.2.0:

### 1. Se añadió el método `_create_layer_normalization_layer`

Este método no existía en v5.2.0. DFC v5.3.0 intenta manejar explícitamente el operador
`LayerNormalization` con una ruta de código dedicada. Esta es sin duda una evidencia de
que el esfuerzo de desarrollo está progresando.

Sin embargo, **la implementación interna está incompleta**, y la llamada a
`_convert_axes_to_nhwc` después de que se invoca el método produce el mismo
`IndexError: list index out of range` que en v5.2.0 con los mismos shapes de tensor.

### 2. Se añadió flujo de simplificación onnxsim + reintento

Para ViT y ConvNeXt, DFC v5.3.0 simplifica automáticamente el ONNX de entrada con `onnxsim`
y reintenta el análisis. El modelo simplificado se guarda como `model.sim.onnx` junto al
archivo de entrada. Es una red de seguridad útil para modelos con grafos ONNX redundantes.

Sin embargo, para los modelos actuales, dado que la causa raíz está en el lado de
`_convert_axes_to_nhwc`, el reintento **falla exactamente en el mismo punto**.

### 3. Función de recomendación de nodo final

Para ConvNeXt, DFC v5.3.0 recomienda nodos finales específicos cuando el parser se rinde
y pide al usuario que reintente fijándolos. Es una mejora de UX considerada.

Sin embargo, el reintento con los nodos finales recomendados también falla de la misma manera.
La causa raíz está en el manejo de LayerNormalization / Transpose, no en la selección del nodo final.

---

## Causa raíz (sin cambios desde marzo)

El parser ONNX de DFC sigue fallando cuando el tensor de entrada del operador `LayerNormalization`
no sigue el formato NCHW esperado para la conversión de ejes. La cadena de llamadas es:

```
_create_layer_normalization_layer
  → get_layer_normalization_info
    → _convert_axes_to_nhwc
      → IndexError: list index out of range
```

Para ConvNeXt, además el `UnsupportedShuffleLayerError` que ocurre en múltiples nodos Transpose
(`token_5` a `token_34`) indica la incompletitud del manejo de Transpose para el patrón
channels-last que usa esta arquitectura.

En resumen, **la nueva ruta de código existe pero todavía no puede manejar los casos que
antes fallaban**.

---

## Solicitudes (sin cambios desde marzo)

Las 2 solicitudes mencionadas en el artículo de marzo continúan sin cambios:

### 1. Corregir `_convert_axes_to_nhwc` para `LayerNormalization` multidimensional

Ahora se puede alcanzar hasta donde se llama al método (mejora). Sin embargo,
la lógica de mapeo de ejes en sí falla con tensores de entrada no NCHW.
Las arquitecturas Transformer modernas como SwinV2, ViT y ConvNeXt dependen de que
esto funcione correctamente.

### 2. ONNX Runtime Execution Provider para Hailo-10H

Esto haría que la conversión completa con DFC fuera opcional y resolvería estructuralmente
este tipo de problemas. Muchos usuarios de la comunidad darían la bienvenida a poder ejecutar
modelos ONNX sin modificar directamente en Hailo-10H, aunque el throughput sea menor
que con HEF completamente cuantizado.

---

## Sobre el componente "ONNX Runtime Hailo Pipeline"

Las notas de lanzamiento de DFC v5.3.0 mencionan un componente llamado "ONNX Runtime Hailo Pipeline".
Si este componente permite ejecutar la inferencia de WD-Tagger en Hailo-10H **sin conversión
completa con DFC** (es decir, como proveedor de ejecución de ORT que delega solo los subgrafos
compatibles a la NPU), sería muy útil recibir orientación oficial sobre el uso correcto.

Específicamente:

- ¿Está este componente destinado a ser una ruta de avance para modelos que DFC no puede
  analizar actualmente?
- ¿Se necesita un HEF parcial (compilar subgrafos analizables a HEF y ejecutar el resto
  en CPU vía ORT)?
- ¿Hay código de ejemplo o tutoriales sobre cómo usar esto con modelos ONNX basados en Transformer?

---

## Pasos de reproducción

Pasos para reproducir estos resultados:

```bash
# 1. Configurar DFC v5.3.0 en un venv limpio de Python
python3.11 -m venv venv
source venv/bin/activate
pip install hailo_dataflow_compiler-5.3.0-py3-none-linux_x86_64.whl

# 2. Descargar 3 variantes de modelos ONNX de WD-Tagger
for variant in swinv2 vit convnext; do
  huggingface-cli download \
    "SmilingWolf/wd-${variant}-tagger-v3" \
    model.onnx --local-dir "./wd-${variant}-tagger-v3"
done

# 3. Intentar el análisis con cada modelo
for variant in swinv2 vit convnext; do
  hailo parser onnx "./wd-${variant}-tagger-v3/model.onnx" \
    --hw-arch hailo10h \
    --tensor-shapes input_1:1,448,448,3 2>&1 | tee "${variant}_5.3.0.log"
done
```

Los logs de error completos de cada ejecución están disponibles bajo pedido.

---

## Entorno de prueba

| Elemento | Detalles |
|---|---|
| SO | Ubuntu 24.04 (WSL2) |
| CPU | AMD Ryzen 5 5600X |
| RAM | 151 GB |
| Python | 3.11 |
| DFC | 5.3.0 |
| Modelos | `SmilingWolf/wd-{swinv2,vit,convnext}-tagger-v3` (HuggingFace) |
| Datos de calibración | 500 imágenes de salida de ComfyUI / SD (sin usar porque no se alcanza la cuantización) |

---

## Resumen

Los esfuerzos de desarrollo visibles en DFC v5.3.0 (`_create_layer_normalization_layer`,
flujo de reintento onnxsim, recomendación de nodo final) son realmente alentadores.
Son exactamente el avance que la comunidad esperaba. La brecha restante está en la
implementación dentro de `_convert_axes_to_nhwc`, que ahora puede alcanzarse pero
todavía no funciona correctamente para los modelos actuales.

Se continuará reverificando con cada versión de DFC y se publicarán actualizaciones
cuando cambie la situación. Si alguien de Hailo lee esto y necesita los logs de error
completos, hashes SHA-256 del modelo ONNX o código mínimo de reproducción, se proporcionarán
con mucho gusto.
