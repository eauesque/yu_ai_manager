# Configuración de Hailo-10H

Guía de configuración en el lado del host para utilizar Raspberry Pi 5 + Hailo AI Hat+ (Hailo-10H NPU) con YU AI Manager. Dado que la parte relacionada con el hardware y el SO no puede completarse a través de PyPI, se requiere cierta preparación manual.

> **Destinatarios**: Solo si desea habilitar las extensiones Hailo (GenAI Chat / Semantic Search / YOLO Detect / Tagger / Whisper) en un Raspberry Pi 5 (se recomiendan 8 GB) con hardware Hailo-10H. En entornos sin hardware Hailo, no es necesario realizar ninguna de las operaciones de esta página.

---

## 1. Requisitos previos

- Raspberry Pi 5 (se recomiendan encarecidamente 8 GB; con 4 GB es difícil cargar varios modelos simultáneamente debido a las restricciones de CMA)
- Hailo AI Hat+ (Hailo-10H)
- Raspberry Pi OS Bookworm 64-bit (aarch64)
- Python 3.13.x (fijado en `<3.14` mediante `requires-python` en `pyproject.toml`; `uv` selecciona automáticamente 3.13)

---

## 2. Instalación del controlador PCIe

Hailo-10H usa el módulo de kernel dedicado `hailo1x_pci` (renombrado desde el antiguo `hailo_pci` en HailoRT 5.3.0).

```bash
sudo apt update
sudo apt install hailo-all
sudo reboot
```

Verificación tras el reinicio:

```bash
lsmod | grep hailo1x
ls /dev/h1x-0
dmesg | grep -i hailo | tail -20
```

Resultados esperados:

- `hailo1x_pci` está cargado
- Existe el nodo de dispositivo `/dev/h1x-0` (no el antiguo `/dev/hailo0`)
- En `dmesg` aparecen las líneas `Firmware loaded in NNNN ms` y `Device created at /dev/h1x-0`

> **No hay problema si `/dev/hailo0` no aparece.** A partir de HailoRT 5.3.0, `/dev/h1x-0` es el predeterminado, y esta aplicación reconoce ambos (`core/llm_router/hailo_detect.py`).

---

## 3. Instalación de HailoRT (lado del sistema)

Binario `hailortcli` y biblioteca compartida `libhailort.so`. Están incluidos en el paquete `hailo-all`, pero si necesita la última versión, obtenga el `.deb` de la Hailo Developer Zone e instálelo sobre la versión existente.

Verificación:

```bash
hailortcli fw-control identify
```

Salida esperada (puntos clave):

```
Device Architecture: HAILO10H
Firmware Version: 5.3.0 (release,app)
```

---

## 4. Preparación del wheel de Python (`hailort-*.whl`)

Esta es la parte que no está disponible en PyPI. **El wheel de Python de Hailo para aarch64 tampoco está en la Hailo Developer Zone, por lo que debe compilarse manualmente.**

### 4.1 Compilar desde el código fuente

```bash
cd ~
git clone --branch v5.3.0 https://github.com/hailo-ai/hailort.git
cd hailort
./build.sh -aarch64
# Al completarse, se genera hailort-5.3.0-cp313-cp313-linux_aarch64.whl en el árbol de compilación
```

(Consulte el README oficial de Hailo para obtener detalles del proceso de compilación y las dependencias.)

### 4.2 Colocar el wheel en el directorio de inicio

Copie el wheel compilado en **cualquiera de los siguientes lugares** y la aplicación lo detectará automáticamente al iniciarse:

| Ruta de búsqueda (prioridad) | Propósito |
|---|---|
| Variable de entorno `$HAILORT_WHEEL` | Ruta completa arbitraria (máxima prioridad) |
| `$HOME/share/` | **Ubicación recomendada** |
| `$HOME/hailort/` | Cuando el árbol de compilación se mantiene en el lugar del código fuente |
| `$HOME/Downloads/` | Ubicación temporal después de descargar |
| `$HOME/` (directamente) | Última reserva |

Procedimiento recomendado:

```bash
mkdir -p ~/share
cp ~/hailort/hailort-5.3.0-cp313-cp313-linux_aarch64.whl ~/share/
```

### 4.3 Mecanismo de instalación automática

Al ejecutar `./start.sh`, se ejecuta `scripts/install_hailo.py`:

1. Verifica si `import hailo_platform` tiene éxito en el venv
2. Solo en caso de error: busca un wheel **compatible con la versión de Python actual (cp313) + arquitectura (aarch64)** en las rutas de búsqueda anteriores
3. Instala el wheel más reciente encontrado con `uv pip install`
4. Si no hay wheel o ya está instalado: no realiza ninguna acción (sin operación silenciosa)

Por lo tanto, no es necesario ejecutar `uv pip install` manualmente. Basta con colocar el wheel en el directorio de inicio y reiniciar `./start.sh`.

---

## 4.4 Colocación de los archivos de modelo HEF

Coloque los archivos HEF (modelos compilados para NPU) que usan las extensiones en `~/hailo_models/`.

| Archivo | Propósito | Tamaño aproximado |
|---|---|---:|
| `yolov8n.hef` | Detección de objetos YOLO | 7 MB |
| `clip_vit_b_16_image_encoder.hef` | **Semantic Search (imagen CLIP)** | 76 MB |
| `clip_vit_b_16_text_encoder.hef` | Semantic Search (texto CLIP, opcional) | 77 MB |
| `Whisper-{Tiny,Base,Small}.hef` | Reconocimiento de voz | 75–405 MB |
| `Qwen3-1.7B-Instruct.hef` | LLM Chat | 2,9 GB |
| `Qwen3-VL-2B-Instruct.hef` | VLM (imagen+texto) | 3,2 GB |

Descarga directa sin autenticación desde el bucket S3 de Hailo Model Zoo (formato URL):

```
https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/<model>.hef
```

Ejemplo (codificador de imagen CLIP):

```bash
mkdir -p ~/hailo_models
curl -L -o ~/hailo_models/clip_vit_b_16_image_encoder.hef \
  https://hailo-model-zoo.s3.eu-west-2.amazonaws.com/ModelZoo/Compiled/v5.2.0/hailo10h/clip_vit_b_16_image_encoder.hef
```

> **Si faltan archivos HEF, la extensión se mostrará como `No disponible`.** Por ejemplo, si el estado de Semantic Search muestra `hailo-10h (CLIP HEF no colocado)`, significa que `clip_vit_b_16_image_encoder.hef` no está en `~/hailo_models/`. Para facilitar la distinción de problemas de hardware o de tiempo de ejecución de Python, la respuesta incluye las causas en tres niveles: `runtime_ok` / `hardware_ok` / `hef_ok` (coloque el cursor sobre el texto de estado para ver los detalles).

También puede especificar otro directorio con la variable de entorno `HAILO_HEF_DIR`.

---

## 5. Parámetros del kernel (CMA)

Los modelos GenAI de Hailo (LLM/VLM/Whisper) requieren CMA (Contiguous Memory Allocator) para DMA.

Añada al final de `/boot/firmware/cmdline.txt`:

```
cma=256M
```

> **En Pi 5 (8 GB), `cma=1G` o `cma=512M` fallan silenciosamente.** Dado que el kernel predeterminado aplica `numa=fake=8`, CMA debe estar dentro del límite de un único nodo NUMA (1 GB), y si supera `256M`, `CmaTotal=0` (sin pánico). Detalles: [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md)

Verificación tras el reinicio:

```bash
grep CmaTotal /proc/meminfo
# CmaTotal:         262144 kB  ← 256 MB significa éxito
```

Si aparece `0 kB`, verifique el valor y redúzcalo si es necesario.

---

## 6. Coexistencia con hailo-ollama (opcional)

Si ejecuta `hailo-ollama` (la versión Hailo NPU de Ollama) en el mismo dispositivo:

- **HailoRT 5.3.0 y posterior**: Inicie con `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED hailo-ollama` para compartir el dispositivo físico con el lado de yu_ai_manager (group_id `YU_SHARED`); el planificador HailoRT realizará time-slicing con ROUND_ROBIN
- **Antes de 5.2.0**: No acepta group_id, por lo que debe detener `hailo-ollama` con `systemctl stop hailo-ollama` antes de iniciar yu_ai_manager

---

## 7. Verificación de funcionamiento

Después de iniciar `./start.sh`, la configuración es exitosa si los siguientes elementos están habilitados en la WebUI en **Configuración → Extensiones**:

- `builtin_hailo_genai` (Hailo Chat / LLM / VLM / Speech2Text)
- `builtin_hailo_semantic_search` (CLIP Semantic Search)
- `builtin_hailo_yolo_detect` (Detección de objetos YOLO)

O directamente desde la CLI:

```bash
uv run python -c "
from hailo_platform import VDevice
v = VDevice()
print('VDevice OK')
v.release()
"
```

---

## 8. Solución de problemas

### Todas las extensiones Hailo muestran «no cargado»

→ Es posible que el wheel de Python no esté instalado. Verifique:

```bash
uv run python -c "import hailo_platform; print(hailo_platform.__file__)"
```

Si aparece `ModuleNotFoundError`, coloque el wheel en el directorio de inicio y reinicie `./start.sh` (§4.2).

### `hailortcli fw-control identify` falla con `HAILO_OPEN_FILE_FAILURE`

→ Problema con el controlador o el nodo de dispositivo. Compruebe si `hailo1x_pci` está cargado en `lsmod | grep hailo1x` y si `ls /dev/h1x-0` existe. Si ambos faltan, repita §2 y reinicie.

### `HAILO_OUT_OF_HOST_MEMORY` al cargar LLM/VLM / Pi se congela

→ CMA insuficiente. Compruebe con `grep CmaTotal /proc/meminfo` si hay 256 MB (§5). Dado que `VDevice.release()` no devuelve CMA, puede ser necesario reiniciar el proceso después de cambiar entre varios modelos repetidamente.

### `HAILO_OUT_OF_PHYSICAL_DEVICES(74)`

→ Otro proceso está ocupando VDevice. Identifique al responsable con `lsof /dev/h1x-0` (típicamente `hailo-ollama` o un proceso anterior que no terminó correctamente con Ctrl+C), ejecute `kill` y reinicie.

### Python se actualizó a 3.14 y es incompatible con el wheel

→ Este repositorio está fijado en `pyproject.toml` con `requires-python = ">=3.13,<3.14"`. El primer `uv sync` después del clone selecciona 3.13.x. Si se estableció manualmente `.python-version = 3.14`, reviértalo.

---

## 9. Documentación relacionada

- [`docs/ja/hailo/README.md`](../../hailo/README.md) — Índice de documentación de desarrollo Hailo-10H
- [`docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md`](../../hailo/HAILORT_5_3_0_MIGRATION.md) — Notas de migración HailoRT 5.2.0 → 5.3.0
- [`docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md`](../../hailo/PI5_NUMA_CMA_CONSTRAINTS.md) — Detalles de restricciones CMA de Pi 5
- [`scripts/install_hailo.py`](../../../../scripts/install_hailo.py) — Script de detección automática de wheel
