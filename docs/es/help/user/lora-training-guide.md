# Guía de entrenamiento LoRA

Guía práctica completa para crear LoRA con solo instrucciones en lenguaje natural usando el servidor MCP de YU AI Manager + kohya_ss

---

## Introducción

Esta es una guía práctica que explica el flujo para crear LoRA con solo instrucciones en lenguaje natural, combinando el servidor MCP de YU AI Manager con kohya_ss.

La mayor parte del tiempo de trabajo en la creación tradicional de LoRA estaba en la "preparación manual del dataset". Selección de imágenes, revisión y exclusión de etiquetas, formateo de archivos de caption, organización de la estructura de carpetas — todo esto era trabajo del humano.

Con la integración MCP de YU AI Manager, este flujo cambia. Con solo una instrucción como "Por favor crea una LoRA de ○○. Excluye las etiquetas △△", el flujo completo desde la recopilación de materiales hasta el etiquetado, la generación del dataset y el inicio de kohya_ss funciona de manera integrada.

---

## Flujo completo

El proceso de creación de LoRA consta de las siguientes 5 etapas.

| Fase | Contenido del trabajo | Responsable |
|---------|---------|------|
| 1. Preparación de materiales | Recopilación y colocación de imágenes de entrenamiento | Humano / Agente IA |
| 2. Etiquetado | Etiquetado automático con WD-Tagger | MCP (automático) |
| 3. Generación de dataset | Creación de proyecto, configuración de etiquetas excluidas, exportación | MCP (automático) |
| 4. Ejecución del entrenamiento | Llamada a kohya_ss para el entrenamiento | MCP (automático) |
| 5. Verificación | Verificación de resultados usando LoRA en SD | Humano |

El humano solo participa en las decisiones de "qué entrenar" y la verificación final de los resultados.

---

## Prerrequisitos

### Software necesario

- YU AI Manager — Incluye funcionalidad de servidor MCP
- Claude Desktop o Claude Code — Cliente MCP
- kohya_ss — Incluyendo sd-scripts
- Stable Diffusion WebUI (A1111 / ComfyUI / Forge) — Para verificación de resultados

### Requisitos de GPU

| GPU VRAM | Modelos compatibles | Configuración necesaria |
|---------|----------|-----------|
| 8GB | Solo SD 1.5 práctico | `--gradient_checkpointing` obligatorio |
| 12GB | SDXL funciona (con limitaciones) | `--gradient_checkpointing` + `--cache_latents_to_disk` |
| 16GB | SDXL cómodo | Funciona con configuración predeterminada |
| 24GB+ | Compatible con SDXL y FLUX | Casi sin limitaciones |

> **Nota**: El entrenamiento de LoRA SDXL con RTX 3060 12GB es posible, pero con gradient_checkpointing obligatorio tarda aproximadamente 10 horas para 24,000 pasos. Con RTX 5060 Ti 16GB se estima una reducción a 3〜5 horas.

### Estructura de directorios de kohya_ss

El directorio principal y el directorio de scripts de kohya_ss suelen estar separados.

```
O:\webui\kohya_ss\              ← Directorio principal a configurar en kohya_path
O:\webui\kohya_ss\venv\         ← Entorno virtual Python (detectado automáticamente)
O:\webui\kohya_ss\sd-scripts\   ← Directorio donde se almacenan los scripts de entrenamiento
```

> ⚠️ **Nota**: YU AI Manager detecta automáticamente la subcarpeta sd-scripts y venv especificando el directorio principal de `kohya_path`. No especificar la ruta de sd-scripts directamente.

---

## Configuración de YU AI Manager

### Configuración de extensiones

Ingresar lo siguiente en la pestaña de configuración del LoRA Dataset Manager.

| Elemento de configuración | Descripción | Ejemplo |
|---------|------|---|
| `kohya_path` | Directorio principal de kohya_ss | `O:\webui\kohya_ss` |
| `output_base_dir` | Directorio base de salida del dataset | `C:\lora_datasets` |
| `checkpoint_dir` | Directorio del modelo base | `O:\webui\models\Stable-diffusion` |
| `default_base_model` | Tipo de modelo predeterminado | `sdxl` |

### Configuración de WD-Tagger

Para uso en dataset de LoRA, no se recomienda combinar con VLM (llava, etc.). El VLM genera grandes cantidades de etiquetas de texto libre que degradan la calidad del caption.

```
engine_type: "onnx"  ← Usar solo ONNX
```

> ⚠️ **Nota**: Si `engine_type` se configura como `"both"`, se generan etiquetas compuestas de origen VLM (como `wooden_bear_and_fish_sculpture`). Estas no funcionan como caption de kohya_ss y obstaculizan el entrenamiento.

---

## Procedimiento de creación de LoRA con MCP

### Paso 1: Preparación de imágenes de materiales

Colocar las imágenes de entrenamiento en la raíz de escaneo de YU AI Manager y escanear.

- Agregar la carpeta de entrenamiento en la configuración de Scan Root de YU AI Manager
- Después de completar el escaneo, las imágenes objetivo se registran en la BD
- Mínimo 20〜30 imágenes, recomendado 50〜200 imágenes

> **Nota**: La calidad de las imágenes es el mayor determinante del resultado del entrenamiento. Seleccionar imágenes con resolución de 512px o más donde el objeto esté claramente visible.

### Paso 2: Etiquetado con WD-Tagger

Ejecutar el etiquetado en lote desde MCP.

```python
# Obtener la lista de IDs de archivos objetivo y etiquetado en lote
wd_tagger_batch(file_ids=[...], expected_count=N)
wait_for_batch(job_id="wd_tagger")
```

Si ya hay etiquetas existentes, eliminarlas primero y volver a ejecutar.

```python
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
```

### Paso 3: Crear proyecto

```python
create_lora_project(
    name="carved_bear",
    concept="carved_bear",   # Usado para el nombre de la carpeta de kohya_ss
    base_model="sdxl",
    repeat=20
)
```

### Paso 4: Configurar archivos y etiquetas

Establecer los IDs de archivos en el proyecto y verificar el agregado de etiquetas.

```python
update_lora_project(project_id=N, file_ids=[...])
get_lora_project_tags(project_id=N)
```

Ver el agregado de etiquetas y decidir qué etiquetas excluir.

#### Filosofía de diseño de etiquetas excluidas

Aquí está el núcleo de "qué hacer aprender a la LoRA".

**Etiquetas a mantener**: Características únicas del concepto que se quiere aprender (forma, estilo, elementos únicos)

**Etiquetas a excluir**: Etiquetas genéricas que el modelo ya conoce (`no_humans`, `realistic`, `animal`, `solo`, series background, etc.)

Ejemplo para LoRA de oso tallado en madera:

- Mantener: `bear`, `fish`, `statue`, `sculpture`, `standing`, `full_body`, `open_mouth`
- Excluir: `no_humans`, `animal_focus`, `animal`, `realistic`, `simple_background`, `solo`, `indoors`, `shadow`...

> ⚠️ **Nota**: Si falla el recorte del concepto, el aprendizaje se dispersa. Si se quieren mantener `bear` o `wood`, el ONNX de WD-Tagger puede no asignarlos de forma fiable. En este caso, verificar la salida real con la vista previa del caption.

```python
update_lora_project(
    project_id=N,
    tag_exclude=["no_humans", "animal_focus", "animal", "realistic", ...]
)
```

### Paso 5: Verificar vista previa del caption

```python
preview_lora_caption(project_id=N, file_id=<cualquier_file_id>)
```

Ejemplo de salida:

```
"fish, full_body, open_mouth, standing"
```

Verificar que sea una secuencia de etiquetas simple sin ruido de VLM. Si hay muchos captions vacíos, revisar las etiquetas excluidas.

### Model Scope

Each project has a `model_scope` setting that controls which WD-Tagger model is used for captions, preview, and export.

- `active` (default for new projects): Use tags from the active WD model only. If no active model is set, it falls back to all models.
- `all` (default for existing projects): Mix tags from all models.
- `<model_id>` (for example, `wd-eva02-large-tagger-v3`): Use tags from the explicitly selected model only.

For files tagged by multiple models, `active` is usually sufficient. When you need an explicit model for comparison or validation, use the same model_id shown in the WD-Tagger profile dropdown on the Tools page.

### Paso 6: Exportar dataset

```python
export_lora_dataset(project_id=N)
```

Estructura de carpetas de salida:

```
{output_base_dir}/{project_name}/{repeat}_{concept}/
    image001.jpeg
    image001.txt   ← caption
    image002.jpeg
    image002.txt
```

### Paso 7: Ejecutar entrenamiento

Primero verificar el comando con dry_run.

```python
preview_lora_train_command(
    project_id=N,
    checkpoint="ruta_completa\checkpoint.safetensors"
)
```

Si no hay problemas, iniciar el entrenamiento.

```python
start_lora_training(
    project_id=N,
    checkpoint="ruta_completa\checkpoint.safetensors",
    extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
)
```

Verificar el progreso:

```python
get_lora_train_status(project_id=N, tail=20)
```

---

## Parámetros de entrenamiento predeterminados

| Parámetro | Valor predeterminado | Descripción |
|-----------|------------|------|
| `network_dim` | 32 | Rango de LoRA. Mayor = más capacidad de expresión pero también mayor tamaño de archivo |
| `network_alpha` | 16 | Normalmente configurar a la mitad del dim |
| `learning_rate` | 1e-4 | Tasa de aprendizaje |
| `max_train_epochs` | 10 | Número de épocas |
| `save_every_n_epochs` | 2 | Intervalo de guardado intermedio |
| `mixed_precision` | fp16 | Precisión. bf16 puede ahorrar VRAM |
| `resolution` | 1024,1024 (SDXL) | Resolución de entrenamiento. SD1.5 es 512,512 |

> **Nota**: Estos se pueden cambiar en la pestaña Settings o con `set_extension_config`. Los argumentos adicionales se pueden agregar con `extra_args` de `start_lora_training`.

---

## Configuración recomendada por GPU

| GPU VRAM | extra_args recomendados |
|---------|---------------|
| 8GB | `--gradient_checkpointing --xformers --cache_latents_to_disk --optimizer_type=AdamW8bit` |
| 12GB | `--gradient_checkpointing --xformers --cache_latents_to_disk` |
| 16GB | (Funciona con configuración predeterminada) |
| 24GB+ | (Funciona con configuración predeterminada, también se puede aumentar batch_size) |

> ⚠️ **Nota**: Con GPU 12GB y gradient_checkpointing, SDXL tarda aproximadamente 10〜12 horas para 24,000 pasos. Con 16GB o más esta restricción desaparece y la velocidad mejora significativamente.

---

## Guía de número de repeats y épocas

**Total de pasos de entrenamiento = Número de imágenes × número de repeats × número de épocas**

| Complejidad del concepto | Pasos recomendados | Ejemplo (50 imágenes) |
|------------|-------------|--------------|
| Objeto simple / estilo | 1,000〜3,000 | repeat=10, epoch=5 |
| Personaje / objeto con forma | 3,000〜8,000 | repeat=20, epoch=5 |
| Estilo complejo / persona | 5,000〜15,000 | repeat=20, epoch=10 |

> **Nota**: Con 120 imágenes × 20 repeats × 10 épocas = 24,000 pasos se obtiene calidad suficiente. Sin embargo, es posible obtener resultados equivalentes con 5〜6 épocas, por lo que se recomienda intentar con épocas más cortas la próxima vez.

---

## Solución de problemas

### ModuleNotFoundError: No module named 'torch'

**Causa**: Se intenta ejecutar los scripts de kohya_ss en el venv de YU AI Manager.

**Solución**: Configurar `kohya_path` al directorio principal (el padre de sd-scripts). YU AI Manager detecta automáticamente `kohya_path/venv/Scripts/python.exe`.

---

### AssertionError: resolution is required

**Causa**: `--resolution` no está especificado.

**Solución**: En la última versión de YU AI Manager se agrega automáticamente (SDXL: 1024,1024, SD1.5: 512,512).

---

### AssertionError: network for Text Encoder cannot be trained with caching

**Causa**: `--cache_text_encoder_outputs` y `--network_train_unet_only` no están emparejados.

**Solución**: En la última versión de YU AI Manager se agrega automáticamente `--network_train_unet_only` para SDXL.

---

### torch.OutOfMemoryError: CUDA out of memory

**Causa**: VRAM insuficiente.

**Solución**: Agregar lo siguiente a `extra_args`:

```python
extra_args=["--gradient_checkpointing", "--xformers", "--cache_latents_to_disk"]
```

---

### Mezcla de etiquetas con ruido de VLM

**Causa**: `engine_type` está configurado como `"both"` y el VLM (llava, etc.) genera etiquetas de texto libre.

**Solución**: Cambiar a `engine_type="onnx"` en la configuración de WD-Tagger, eliminar todas las etiquetas y volver a etiquetar.

```python
wd_tagger_save_config({"engine_type": "onnx"})
wd_tagger_delete_tags_batch(file_ids=[...], expected_count=N)
wd_tagger_batch(file_ids=[...], expected_count=N)
```

---

### checkpoint must be inside checkpoint_dir (error 403)

**Causa**: La ruta del checkpoint apunta fuera de `checkpoint_dir`.

**Solución**: Verificar que `checkpoint_dir` en la configuración de extensiones apunta al directorio correcto.

---

### output_base_dir not configured (error 400)

**Causa**: `output_base_dir` en la configuración de extensiones no está configurado o no se ha guardado.

**Solución**: Volver a guardar en la pestaña de configuración de la interfaz de usuario, o configurar con `set_extension_config` desde MCP.

---

## Prompt para generación

### Estructura básica del prompt

```
{concept_token}, {etiquetas características}, <lora:{lora_name}:{strength}>
```

Ejemplo para LoRA de oso tallado en madera:

```
carved_bear, wooden sculpture, bear statue, wood texture, brown,
full_body, standing, open_mouth, fish, simple_background,
<lora:carved_bear:0.7>
```

Prompt negativo:

```
blurry, lowres, bad anatomy, worst quality, flat color, monochrome
```

### Ajuste de la intensidad de LoRA

| Intensidad | Características |
|-----|------|
| 0.5〜0.6 | La influencia del modelo base es fuerte. Color y estilo más cerca del modelo base |
| 0.7〜0.8 | Rango recomendado. Buen equilibrio entre las características de LoRA y el modelo base |
| 0.9〜1.0 | La influencia de LoRA es fuerte. La forma sale pero el color tiende a ser blanco/crema |

> **Nota**: Si el color se vuelve demasiado blanco, reducir la intensidad o añadir `brown wood, warm tone` al prompt para guiar el color.

---

## Expansiones futuras

### Automatización de la recopilación de materiales

Actualmente, las imágenes de materiales deben prepararse manualmente por el humano. Con agentes de navegador como Claude in Chrome, también se puede automatizar la recopilación de materiales con instrucciones como "Por favor recopila imágenes de ○○ desde la web y colócalas en una carpeta".

También es efectivo usar las imágenes generadas de YU AI Manager como materiales. Se establece un ciclo donde las imágenes generadas con SD/ComfyUI/NAI se reutilizan directamente como materiales de LoRA.

### Flujo de producción masiva de LoRA

Con MCP + Claude Desktop, se puede lograr la siguiente automatización completa.

1. Recopilar materiales desde la web (Claude in Chrome)
2. Escanear y etiquetar en YU AI Manager (MCP)
3. Crear proyecto, configurar etiquetas excluidas y exportar (MCP)
4. Iniciar entrenamiento kohya_ss (MCP)
5. Dar instrucciones antes de dormir → LoRA completa por la mañana

### Selección del modelo base

Los modelos base de la serie Illustrious como waiSHUFFLENOOB están optimizados para generación de estilo anime. Al entrenar materiales fotorrealistas (como osos tallados en madera), el tono de color tiende a ser blanco/crema.

Para buscar una textura cercana al realismo, seleccionar modelos base de la serie realisticPhoto. La LoRA debe usarse con el mismo modelo que el modelo base.

---

## Resumen

Con el flujo YU AI Manager + MCP + kohya_ss, se puede reducir significativamente el tiempo de trabajo en la creación de LoRA.

- Todo el entrenamiento de épocas desde las imágenes de materiales funciona con solo instrucciones MCP
- Todo el flujo funciona con instrucciones en lenguaje natural
- La forma del objeto objetivo de entrenamiento se expresa claramente en las imágenes generadas

El único desafío restante es la automatización de la recopilación de materiales, y combinándola con Claude in Chrome y otros, la automatización completa está a la vista.
