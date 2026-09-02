# Restricciones de CMA bajo `numa=fake=8` en la Pi 5

Conocimientos prácticos sobre la asignación de CMA en una Raspberry Pi 5 (8 GB) al ejecutar cargas de trabajo Hailo-10H.
Describe el límite de `cma=`, por qué los valores superiores a 512M fallan de forma silenciosa, y cómo recuperar la CMA consumida por el controlador de pantalla.

**Audiencia**: desarrolladores que ejecutan modelos Hailo GenAI (LLM, Speech2Text) en una Raspberry Pi 5
(con AI HAT / AI HAT+).

---

## ⚠️ 2026-05 firmware Aviso de regresión

**A partir de la versión `raspi-firmware 1:1.20260513-1` + `pieeprom-2026-05-11` del 2026-05-13**, escribir `cma=` en `/boot/firmware/cmdline.txt`, sea cual sea el tamaño, silencia por completo el mailbox del firmware VC (`vcgencmd ioctl_set_msg failed:-1`, `raspberrypi-clk -22`, HEVC `-517`, ausencia del sysfs de cpufreq).

**Método recomendado y confirmado a partir del 2026-05-16**: en lugar de `cma=` en cmdline, escribir `dtoverlay=cma,cma-512` en `/boot/firmware/config.txt`. Como se reserva a través del nodo de memoria reservada `linux,cma` del DT, no entra en conflicto con el nuevo firmware. Ver §6 y [`docs/development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md`](../../development/investigations/pi5_firmware_cma_mailbox_regression_2026-05-16.md) para más detalles.

La siguiente descripción anterior (que recomendaba `cma=512M` en cmdline) corresponde a los resultados de verificación del 2026-04-15. El hallazgo sobre el límite (512M) impuesto por los límites de los nodos NUMA sigue siendo válido, pero **el lugar de configuración ha pasado del cmdline al argumento de overlay en config.txt**.

---

## TL;DR

- **El lugar de configuración es `dtoverlay=cma,cma-512` en `config.txt`** (confirmado el 2026-05-16; `cma=` en cmdline rompe el mailbox con el nuevo firmware)
- `cma-1024` y `cma-768` **fallan de forma silenciosa** en la Pi 5 (8 GB) — `CmaTotal` queda en 0, sin pánico del kernel ni advertencias (límite impuesto por los límites de los nodos NUMA; se presume que la misma restricción persiste también a través del overlay)
- **`cma-512` es el límite verificado y el valor recomendado** (reverificado el 2026-05-16 en una Pi 5 8 GB vía overlay; se confirmó la reserva de `CmaTotal: 524288 kB`)
- Causa raíz: el kernel predeterminado de la Pi 5 aplica `numa=fake=8`, limitando las asignaciones contiguas a un único nodo NUMA (1 GB)
- **`dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` consumen ~157 MB de CMA durante el arranque** — incluso si la inicialización del controlador DRM falla (verificado el 2026-04-15)
- **`camera_auto_detect=1`** carga `pisp_be` y `videobuf2_dma_contig`, consumiendo CMA adicional. Se recomienda desactivarlo en sistemas sin cabeza (headless)
- **Línea base optimizada para headless** (ambos overlays desactivados): ~98 MB de CMA usados durante el arranque, ~414 MB libres para modelos Hailo
- **YOLO InferModel usa 0 MB de CMA** (confirmado el 2026-04-15) — solo los modelos GenAI (LLM, Speech2Text) asignan desde CMA
- Carga simultánea de LLM (qwen2.5-1.5b) + Whisper-base: ~328 MB en total — cabe dentro de la línea base optimizada para headless
- La CMA no se recupera al reiniciar el servidor — solo se libera con un reinicio completo del sistema (reciclado de energía de PCIe) (bug del controlador `hailo1x_pci`, ya reportado a Hailo)
- Tratar VDevice como un **singleton de por vida del proceso**. Prohibido desalojarlo o recargarlo

---

## 1. Síntoma

Si configura `cma=1G` (o `cma=768M`) en `/boot/firmware/cmdline.txt` y reinicia, ocurre lo siguiente:

```
$ grep CmaTotal /proc/meminfo
CmaTotal:              0 kB
```

El sistema arranca con normalidad. No hay pánico del kernel ni mensajes de error. La configuración de CMA en `cmdline.txt` se **ignora silenciosamente**, y todo lo que depende de CMA (el NPU Hailo-10H, las cámaras V4L2, etc.) falla al inicializarse.

**Después de modificar `cmdline.txt`, verifique siempre la asignación de CMA:**

```bash
grep CmaTotal /proc/meminfo
```

---

## 2. Causa raíz: los límites de los nodos de `numa=fake=8`

El kernel predeterminado de Raspberry Pi OS para la Pi 5 aplica `numa=fake=8`, dividiendo los 8 GB de memoria física en **8 nodos NUMA virtuales de 1 GB cada uno**:

```
numa=fake=8 physical memory layout (8 GB total):

┌──────┬──────┬──────┬──────┬──────┬──────┬──────┬──────┐
│ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │ 1GB  │
│node0 │node1 │node2 │node3 │node4 │node5 │node6 │node7 │
└──────┴──────┴──────┴──────┴──────┴──────┴──────┴──────┘
```

La CMA de Linux (`cma_init_reserved_mem`) debe asignarse en el arranque como **memoria física contigua que no cruce los límites de los nodos NUMA**.
Esto impone un límite estricto de 1 GB por nodo. Como el propio kernel ocupa memoria del mismo nodo, no es posible reservar exactamente 1 GB:

> **La siguiente tabla es un registro de mediciones del método cmdline, tal como estaba a fecha del 2026-04-15.**
> El hallazgo sobre el límite (512M) impuesto por los límites de los nodos NUMA sigue siendo válido, pero **`cma=` en cmdline ya no debe usarse** (véase la nota de regresión de firmware al inicio).
> El método de configuración actual es `dtoverlay=cma,cma-512` en `config.txt` (§6).

| Configuración de `cmdline.txt` (registro a fecha del 2026-04-15) | Resultado |
|---|---|
| `cma=1G` | Intenta consumir el nodo entero. No deja margen para el kernel → **falla silenciosamente**, CmaTotal=0 |
| `cma=768M` | Excede el rango contiguo fiable → **falla silenciosamente**, CmaTotal=0 (verificado el 2026-04-15) |
| `cma=512M` | La mitad de un nodo → **estable y confirmado** ✓ (verificado el 2026-04-15) ← recomendado en aquel momento. **Ahora debe usarse `dtoverlay=cma,cma-512`** |
| `cma=384M` | No verificado (512M ya está confirmado; 384M no es necesario) |
| `cma=256M` | Estable, pero ajustado si se usan LLM + Whisper simultáneamente |
| `cma=128M` | Estable, pero insuficiente para Hailo GenAI (el LLM por sí solo necesita ~234 MB) |

### Por qué el fallo es silencioso

`cma_init_reserved_mem` no entra en pánico cuando la asignación falla. El kernel arranca con `CmaTotal=0` y se comporta como si nunca se hubiera solicitado CMA.
El valor escrito en `cmdline.txt` se ignora, en la práctica.

---

## 3. Requisitos de CMA de Hailo-10H

Medido en Raspberry Pi 5, AI HAT+, HailoRT 5.3.0:

| Modelo / combinación | Uso de CMA | Notas |
|---|---|---|
| LLM — qwen2.5-1.5b-chat (solo) | **~234 MB** | Medido el 2026-04-15 |
| YOLO InferModel (yolov8n, configure + bindings) | **0 MB** | Confirmado el 2026-04-15 |
| Whisper-tiny (solo) | ~70 MB | Estimado |
| Whisper-base (solo) | ~100 MB | Estimado |
| Whisper-small (solo) | ~150 MB | Estimado |
| **LLM + Whisper-tiny (simultáneo)** | **~246 MB** | Medido con CMA de 256 MB |
| **LLM + Whisper-base (simultáneo)** | **~334 MB** | Estimado. Se espera que quepa dentro de la línea base headless |

**YOLO usa 0 MB de CMA**: en HailoRT 5.3.0, YOLO InferModel, `configure()` y `create_bindings()` no asignan ninguna CMA en absoluto.
Los búferes DMA de entrada y salida se mapean desde arreglos numpy preasignados vía `set_buffer()`, no desde CMA.
Por lo tanto, YOLO no es un factor en el cálculo del presupuesto de CMA.

Con CMA de 512 MB y la optimización headless aplicada (ver §5), se espera que funcionen las siguientes configuraciones:

- Solo LLM (~234 MB, ~180 MB de margen)
- Solo Whisper-tiny / Whisper-base (cabe con holgura)
- LLM + Whisper-base simultáneos (~334 MB en total, ~80 MB de margen)

La combinación de Whisper-small y LLM (estimada en ~384 MB) se acerca al límite teórico — confírmelo con mediciones reales antes de confiar en ella.

Para más detalles, consulte los resultados de las pruebas de carga simultánea en [hailo_genai_concurrent_2026-04-15.md](../../development/investigations/hailo_genai_concurrent_2026-04-15.md).

---

## 4. La CMA no se recupera hasta un reinicio completo

La CMA asignada por HailoRT permanece en memoria hasta un reinicio completo del sistema.
Esto ocurre independientemente de `VDevice.release()`, la finalización del proceso del servidor o la recarga del módulo del kernel.

**Causa raíz** (confirmada el 2026-04-15): `hailo1x_pci` conserva las asignaciones coherentes de DMA incluso después de cerrar el fd del dispositivo o recargar el módulo.
Solo se liberan con un reinicio completo (reciclado de energía de PCIe). El bug ya fue reportado a Hailo.

| Fase | CmaFree (CMA 512 MB, optimizado headless) |
|---|---|
| Arranque | **~426 MB** |
| Tras cargar el LLM (~234 MB) | ~192 MB |
| Tras cargar Whisper-base (~100 MB) | ~92 MB |
| Tras `VDevice.release()` | ~92 MB (**no se devuelve**) |
| Tras finalizar el proceso del servidor | ~92 MB (**no se devuelve**) |
| Tras `rmmod hailo1x_pci && modprobe hailo1x_pci` | ~92 MB (**no se devuelve**) |
| Tras un reinicio completo del sistema | **~426 MB (restaurado)** |

**Implicación**: el consumo de CMA se acumula a través de los reinicios del servidor dentro de la misma sesión de arranque.
No espere que la CMA se recupere al reiniciar el servidor. Diseñe VDevice como un **singleton de por vida del proceso**.
Si la CMA se agota, solo un reinicio completo del sistema la restaurará.

---

## 5. Optimización headless: `/boot/firmware/config.txt`

El `config.txt` predeterminado de Pi OS incluye dos configuraciones que consumen una gran cantidad de CMA incluso en sistemas headless (sin pantalla).

### 5.1 `dtoverlay=vc4-kms-v3d` y `max_framebuffers=2`

**Efecto**: el firmware de la Pi 5 preasigna búferes de fotograma (framebuffer) CMA para la canalización de pantalla durante el arranque.
Con `max_framebuffers=2`, esto consume ~157 MB de CMA **antes de que se ejecute ningún proceso en espacio de usuario**.

La asignación persiste incluso si el controlador DRM de Linux falla más tarde al inicializarse (por ejemplo, `[drm] Couldn't stop firmware display driver: -22` o `Couldn't get core clock` en `dmesg`).

| Estado de `config.txt` | CmaFree en el arranque |
|---|---|
| `dtoverlay=vc4-kms-v3d` + `max_framebuffers=2` habilitados (predeterminado) | **~257 MB** |
| Ambos comentados | **~305 MB** (+~48 MB) |

**Corrección** (modo headless / servidor):

```ini
# /boot/firmware/config.txt
#dtoverlay=vc4-kms-v3d
#max_framebuffers=2
```

**Compensación**: `vc4-kms-v3d` es necesario para la visualización acelerada por hardware y 3D (V3D).
Si accede al sistema únicamente por SSH o mediante una interfaz web, es seguro desactivarlo.

### 5.2 `camera_auto_detect=1` y `display_auto_detect=1`

**Efecto**: estos overlays sondean las cámaras CSI y las pantallas DSI durante el arranque, y cargan `pisp_be` (el backend ISP de Pi) y `videobuf2_dma_contig`.
Los módulos cargados y el hardware detectado preasignan CMA adicional en cada caso.

| Estado de `config.txt` | CmaFree en el arranque |
|---|---|
| `camera_auto_detect=1` + `display_auto_detect=1` | ~305 MB (tras desactivar vc4) |
| Ambos puestos en 0 | **~426 MB** (+~121 MB) |

**Corrección**:

```ini
camera_auto_detect=0
display_auto_detect=0
```

**Nota**: `camera_auto_detect=0` solo afecta a las cámaras CSI. Las cámaras USB (UVC / `uvcvideo`) no se ven afectadas y siguen funcionando con normalidad.

### 5.3 `config.txt` mínimo recomendado para uso headless con AI HAT+

```ini
auto_initramfs=1
arm_64bit=1
arm_boost=1

[cm5]
dtoverlay=dwc2,dr_mode=host

[all]
dtparam=pciex1_gen=3
```

Estimación de CMA en el arranque con esta configuración: **~98 MB usados**, ~414 MB libres para modelos Hailo.

### 5.4 Resumen del presupuesto de CMA (CMA 512 MB, optimizado headless)

| Configuración | CmaFree | Disponible para Hailo |
|---|---|---|
| Predeterminada (vc4-kms-v3d + cámara habilitados) | ~257 MB | ~257 MB |
| vc4-kms-v3d + max_framebuffers desactivados | ~305 MB | ~305 MB |
| + camera/display_auto_detect=0 | **~426 MB** | **~426 MB** |
| Tras cargar el LLM (~234 MB) | ~192 MB | Para Whisper |
| Tras cargar LLM + Whisper-base (~100 MB) | ~92 MB | (margen) |

---

## 6. Configuración recomendada

### Configurar `dtoverlay=cma,cma-512` (confirmado el 2026-05-16)

```bash
# Verificar el estado actual de CMA
grep CmaTotal /proc/meminfo

# 1) Eliminar cualquier cma= existente de cmdline.txt (porque rompe el mailbox con el nuevo firmware)
sudo sed -i 's/ *cma=[^ ]*//g' /boot/firmware/cmdline.txt

# 2) Añadir dtoverlay=cma,cma-512 a la sección [all] de config.txt
sudo sed -i '/^\[all\]$/a dtoverlay=cma,cma-512' /boot/firmware/config.txt

# 3) Se recomienda un reinicio en frío (desconectar y volver a conectar la alimentación)
sudo sync && sudo poweroff

# Verificar después del reinicio (comprobar los 4 elementos)
vcgencmd version                                # Respuesta de Broadcom obligatoria (el silencio indica fallo)
grep CmaTotal /proc/meminfo                     # Se espera 524288 kB
journalctl -b -k | grep 'linux,cma'             # Debe aparecer "initialized node linux,cma"
journalctl -b -k | grep '0x00030087'            # No debe aparecer
```

Si en `dmesg` aparece `OF: reserved mem: initialized node linux,cma, compatible id shared-dma-pool`, es evidencia de que se reservó por la ruta del DT.
Por el contrario, si aparece `Reserved memory: bypass linux,cma node, using cmdline CMA params instead`, significa que aún queda `cma=` en cmdline, así que elimínelo.

### Si desea habilitar `vc4-kms-v3d`

Si necesita KMS DRM para pantalla, puede integrarlo como argumento del overlay:
```ini
dtoverlay=vc4-kms-v3d,cma-512
```
Sin embargo, como se indica en §5.1, vc4-kms-v3d consume ~157 MB de CMA, por lo que se recomienda desactivarlo para uso con Hailo GenAI.

### Verificar después de cada cambio de kernel, firmware o configuración

Los cambios en `/boot/firmware/cmdline.txt` o `config.txt`, o las actualizaciones de kernel/firmware, pueden alterar silenciosamente el estado de CMA y la respuesta del mailbox.
Convierta la verificación de los 4 elementos anteriores en una rutina después de cada reinicio.

---

## 7. Interacción con otros problemas de `numa=fake=8`

`numa=fake=8` provoca al menos dos problemas distintos relevantes para este proyecto:

| Problema | Síntoma | Causa raíz |
|---|---|---|
| Fallo silencioso de CMA | `CmaTotal=0` tras `cma=1G`, `cma=768M` | Los límites de los nodos NUMA restringen las asignaciones contiguas |
| Fallo de instalación de Node.js | El instalador de npm/node aborta con error de memoria | La memoria por nodo NUMA (1 GB) se detecta erróneamente como la RAM total. Reportado upstream como [anthropics/claude-code#33864](https://github.com/anthropics/claude-code/issues/33864) |
| Drenaje de CMA por `vc4-kms-v3d` | Consume ~157 MB durante el arranque. No se devuelve aunque falle la inicialización de DRM | `max_framebuffers=2` hace que el firmware reserve búferes de fotograma CMA antes de que arranque el controlador Linux |

Tanto el fallo silencioso como el drenaje de vc4 se deben a la misma restricción subyacente (la zona DMA de los primeros 4 GB, los límites de los nodos NUMA).
Si se produce un fallo inesperado relacionado con la memoria, revise primero `/proc/meminfo` y `config.txt`.

---

## 8. Lista de verificación de diagnóstico rápido

```bash
# 1. Respuesta del mailbox (verificar primero con el nuevo firmware)
vcgencmd version                     # El silencio sugiere que aún queda cma= en cmdline

# 2. Verificar la asignación de CMA
grep CmaTotal /proc/meminfo          # 0 kB = fallo silencioso

# 3. Verificar la ruta DT frente a la ruta cmdline
journalctl -b -k | grep 'linux,cma'
# Esperado: "initialized node linux,cma, compatible id shared-dma-pool" (ruta DT = normal)
# Error:    "bypass linux,cma node, using cmdline CMA params instead" (persiste cmdline)

# 4. Verificar la topología NUMA
numactl --hardware                   # Muestra el número de nodos y la memoria por nodo

# 5. Verificar la línea de comandos actual y la configuración del overlay
cat /boot/firmware/cmdline.txt       # Confirmar que no contiene cma=
grep '^dtoverlay=cma' /boot/firmware/config.txt   # Debe existir dtoverlay=cma,cma-512

# 6. Verificar la disponibilidad del dispositivo Hailo
ls /dev/h1x-*                        # HailoRT 5.3.0: /dev/h1x-0
hailortcli fw-control identify       # Confirmar que el NPU es accesible

# 7. Verificar config.txt en busca de consumidores de CMA
grep -E 'vc4-kms-v3d|camera_auto_detect|display_auto_detect|max_framebuffers' \
  /boot/firmware/config.txt

# 8. Verificar los módulos del kernel cargados (usuarios de CMA)
lsmod | grep -E 'vc4|v3d|pisp|videobuf2_dma'
```

---

**Entorno de verificación**: Raspberry Pi 5 8 GB, Raspberry Pi OS
(Linux 6.12.62+rpt-rpi-2712, aarch64), HailoRT 5.3.0, AI HAT+, CMA=512M
(**revalidado el 2026-05-16**: en Linux 6.18.29+rpt-rpi-2712 / raspi-firmware 1:1.20260513-1 / pieeprom-2026-05-11 / Hailo-10H AI HAT se confirmaron 524288 kB reservados vía `dtoverlay=cma,cma-512`, y respuesta del mailbox verificada)
