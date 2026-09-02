# HailoRT / driver 5.4.0 — corrección y registro de verificación del veredicto de CMA no liberada

Creado: 2026-08-16 / Última actualización: 2026-08-17 / Versión correspondiente: yu_ai_manager 4.623.1

Registro de verificación de hipótesis y prueba A/B entre la versión oficial vanilla y la versión corregida con `FOLL_LONGTERM` de `hailo-ai/hailort-drivers` v5.4.0 (publicada el 2026-08-16, GPL-2.0, código fuente público), sobre el fenómeno que se había diagnosticado como CMA no liberada (véase `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md`), que corrige un veredicto erróneo del lado de la medición.

---

## 1. Conclusión

**Reintento final del 2026-08-17 (4.º intento): el `VERDICT: FAIL` obtenido hasta el 3.er intento fue un veredicto erróneo causado por usar únicamente la cantidad de recuperación absoluta de `CmaFree` tras la primera carga del HEF como criterio de fuga. Se comparó en A/B la versión oficial vanilla 5.4.0 y la versión corregida con `FOLL_LONGTERM`, y tuvieron éxito todas las pruebas: carga sucesiva partiendo de un `CmaFree` bajo, liberación y recarga dentro del mismo proceso, 20 generaciones, y la repetición completa de todas las pruebas partiendo de un estado de `CmaFree` aún más bajo. No hubo incremento o decremento monótono en el RSS ni en `CmaFree` durante la generación, y los fallos de asignación de CMA fueron 0. La caída inicial de `CmaFree` corresponde al aumento de la caché de páginas por el HEF de varios GB, y `MemAvailable` se mantuvo en aproximadamente 7 GB. Bajo las condiciones probadas en esta ocasión —Pi 5 + Hailo-10H + HailoRT/driver 5.4.0, un solo modelo, un solo dispositivo, repeticiones de corta duración— no se reprodujo una fuga de CMA con efecto práctico, y la corrección de `FOLL_LONGTERM` tampoco mostró una mejora medible. El funcionamiento continuo prolongado, el uso simultáneo de múltiples modelos, Hailo-8 y el funcionamiento bajo IOMMU no fueron probados, y quedan fuera del alcance de esta conclusión.**

### 1.1 Evolución del veredicto

| Intento | Fecha | Veredicto en ese momento | Fundamento de la actualización/corrección |
|---|---|---|---|
| 1.º | 2026-08-16 | No se pudo determinar | Al subir únicamente el driver a 5.4.0, la API fue rechazada por la verificación de coincidencia exacta con la biblioteca 5.3.0 (§3) |
| 2.º | 2026-08-17 | Solo se completaron pruebas limitadas | Se alinearon driver / biblioteca / firmware a 5.4.0, y la repetición de `run2` alcanzó una meseta, pero aún no se había ejecutado el repro directo vía pyhailort (§4) |
| 3.º | 2026-08-17 | `FAIL` provisional (posteriormente identificado como veredicto erróneo) | Resultado del diagnóstico anterior que solo evaluaba la cantidad de recuperación absoluta de `CmaFree` tras la primera carga del HEF. Una medición aislada no podía distinguir entre pérdida de memoria y uso de la caché de páginas (§5, §7) |
| 4.º | 2026-08-17 | No se reprodujo una fuga con efecto práctico | Se corrigió el 3.er intento midiendo A/B vanilla / `FOLL_LONGTERM`, repetición con CMA bajo, recarga dentro del mismo proceso, 20 generaciones, RSS, `MemAvailable` y fallos de asignación (§8) |

---

## 2. Diferencia de código fuente v5.3.0 → v5.4.0 (`hailo-ai/hailort-drivers`)

Se comparó (diff) todos los archivos entre ambas etiquetas mediante la API de GitHub. Al tratarse de un único commit squash, no se puede leer nada del mensaje de commit, por lo que se verificó mediante diff de archivos reales. No hubo cambios en la **lógica misma** de reserva/liberación de CMA (el par `dma_alloc_coherent`/`dma_free_coherent`); lo siguiente son principalmente refactorizaciones y correcciones defensivas:

| Archivo | Contenido del cambio |
|---|---|
| `linux/utils/compact.h` → `compat.h` | Cambio de nombre de archivo de la capa de compatibilidad del kernel |
| `linux/vdma/memory.c` | Se añadió verificación NULL a `hailo_desc_list_release()`, y se limpia el puntero a NULL tras la liberación (corrección defensiva contra **doble liberación**) |
| `linux/vdma/vdma.h` | Se eliminó el campo redundante `kernel_address` de `hailo_descriptors_list_buffer` (integrado en `desc_list.descs`) |
| `common/vdma_common.c` | Se reescribió la determinación de finalización de transferencia DMA, del cálculo directo de `hw_num_proc` a la comparación de `num_proc`/`num_avail` (posible corrección de un bug en el seguimiento de finalización de transferencia) |
| `linux/vdma/monitor.c` | `del_timer_sync` → `timer_delete_sync` (siguiendo el nuevo nombre de API del kernel) |
| `common/pcie_common.c` | Se eliminó el campo md5 del protocolo de control de FW, y se reforzó la verificación de corrupción del log SCU de solo los primeros 4 bytes a las primeras 5 palabras completas |

El texto de los mensajes de error también cambió (una explicación larga se abrevió a `out of CMA memory.`), pero el flujo de control de reserva/liberación es el mismo. **Solo a partir de este diff no se puede identificar ningún cambio que corresponda a la hipótesis vigente en su momento (CMA no liberada al recargar el modelo)**.

---

## 3. Trabajo de sustitución en hardware real y puntos de bloqueo (2026-08-16, 1.er intento)

Se intentó la sustitución a v5.4.0 mediante compilación manual, en un Raspberry Pi 5 + Hailo-10H con `hailo1x_pci 5.3.0` (gestionado por dkms) en funcionamiento.

### 3.1 `make install` no depende de `all`

El destino `install` de `linux/pcie/Makefile` es solo `modules_install`, y se completa sin advertencia incluso si no existe el producto de compilación (`.ko`) (para ser exactos, sí aparece una advertencia de ausencia de `System.map`, pero no queda claro que la causa sea que no se compiló).

```makefile
install:
	$(Q)$(MAKE) -C $(KERNEL_DIR) M=$(PWD) INSTALL_MOD_DIR=kernel/drivers/misc modules_install
	$(Q)$(DEPMOD) -a

all: $(TARGET_DIR) print-versions
	$(Q)$(MAKE)  -C $(KERNEL_DIR) M=$(PWD) $(GDB_FLAG) $(USER_FLAGS) modules
	$(Q)cp $(DRIVER_NAME_NO_EXT)* $(TARGET_DIR)
```

**Ejecutar siempre en el orden `make all` seguido de `make install` con privilegios elevados.**

### 3.2 Las cabeceras del kernel de Raspberry Pi no incluyen `System.map`

Al ejecutar `modules_install` aparece la siguiente advertencia y `depmod` se omite silenciosamente:

```
Warning: modules_install: missing 'System.map' file. Skipping depmod.
```

Esto se debe a que no existe `/usr/src/linux-headers-<kernelver>/System.map`. Como sí existe `/boot/System.map-<kernelver>`, se resuelve copiándolo:

```bash
sudo cp /boot/System.map-$(uname -r) /usr/src/linux-headers-$(uname -r)/System.map
sudo depmod -a
```

Si no se hace esto, `modprobe` no puede resolver el `.ko` recién instalado y se produce `FATAL: Module hailo1x_pci not found` (aunque el archivo `.ko` sí existe en `/lib/modules/<kernelver>/kernel/drivers/misc/`).

### 3.3 Las reglas udev no se reflejan de inmediato sin reload/trigger

`/lib/udev/rules.d/51-hailo-pcie-udev.rules`:

```
SUBSYSTEM=="hailo1x", MODE="0666"
```

Justo después de sustituir el módulo, `/dev/h1x-0` queda como `crw-------` (exclusivo de root). Se resuelve con lo siguiente:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hailo1x
```

### 3.4 La discrepancia de versión entre driver y biblioteca es fatal

Al ejecutar `hailortcli` con solo el driver del kernel subido a 5.4.0:

```
dmesg: Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0
dmesg: hailo_soc_get_driver_info has failed with err -22

hailortcli: [HailoRT] [error] CHECK failed - Driver version (5.4.0) is different from library version (5.3.0)
hailortcli: [HailoRT] [error] Driver version mismatch, status HAILO_INVALID_DRIVER_VERSION(76)
```

La biblioteca HailoRT exige **coincidencia exacta** con el driver del kernel, y si solo se actualiza uno de los dos primero, todas las llamadas a la API son rechazadas de inmediato. No es posible verificar la versión vanilla solo con el driver; también es necesario subir simultáneamente el paquete de espacio de usuario `hailort` (el propio SDK).

- `apt-cache policy hailort` → candidato 5.3.0 (a la fecha, 5.4.0 aún no distribuido en apt oficial)
- `gh api repos/hailo-ai/hailort/releases` → la etiqueta `v5.4.0` existe, pero `assets` está vacío (sin .deb compilado, solo código fuente)

En otras palabras, **la verificación en el terreno de 5.4.0 no es posible salvo instalando HailoRT en sí mediante un .deb o compilándolo completo desde el código fuente**. La compilación completa implica una compilación considerable de CMake C++ + bindings de Python, con el riesgo de arrastrar paquetes de dependencia como `hailo-tappas` y `python3-hailort`, por lo que en el 1.er intento se pospuso y se decidió esperar la distribución del .deb oficial.

---

## 4. Registro del procedimiento de compilación propia (2026-08-17, 2.º intento)

Sin esperar la distribución de apt/.deb oficial, procedimiento y puntos de bloqueo al compilar por cuenta propia desde el código fuente de GitHub (driver: GPL-2.0, `hailort` en sí: MIT) e instalarlo en el sistema.

### 4.1 Entorno de compilación

- Se instaló `checkinstall` (`sudo apt-get install -y checkinstall`). Sin embargo, el paso de compresión `xz` del módulo del kernel entra en conflicto con `installwatch` (el mecanismo de seguimiento de archivos basado en LD_PRELOAD de checkinstall), y al ejecutar `make install` vía checkinstall, fallaba cada vez con `xz: ... no existe el fichero o el directorio`. **No usar checkinstall para empaquetar el módulo del kernel; usar dkms (para el driver en sí) o el `make install` simple (para la biblioteca de espacio de usuario)**
- Se liberó memoria antes de compilar: se detuvieron temporalmente los procesos duplicados de `headroom mcp serve` y `rust-analyzer` (liberando en total casi 1 GB). La memoria del Pi es de 7.9 Gi, y se logró mantener disponibles unos 3.8 Gi incluso durante la compilación

### 4.2 Compilación de `hailort` (biblioteca de espacio de usuario)

```bash
git clone --branch v5.4.0 --depth 1 https://github.com/hailo-ai/hailort.git
cd hailort/build   # crear el directorio antes
cmake .. -DCMAKE_BUILD_TYPE=Release   # obtiene automáticamente dependencias externas (protobuf/spdlog/eigen, etc.) vía FetchContent, unos 4 minutos
cmake --build . -j2   # limitado a -j2 (para evitar presión de memoria), unos 15 minutos
sudo make install     # se coloca en /usr/local/{include,lib,bin}. Puede coexistir con la versión de apt (5.3.0, bajo /usr)
```

Como todos los valores de `option()` por defecto tenían apagados los componentes pesados (GStreamer, pruebas, servidor, integración con Ollama, etc.), se compiló una configuración relativamente ligera con solo `libhailort.so`, `hailortcli` y `libhailopp`.

**Nota**: el producto de `make install` se coloca bajo `/usr/local` y no sobrescribe la versión de apt (bajo `/usr`, 5.3.0). Al verificar el funcionamiento hay que especificar la ruta explícitamente, como en `LD_LIBRARY_PATH=/usr/local/lib /usr/local/bin/hailortcli ...`.

### 4.3 Sustitución del driver (módulo del kernel) y actualización del firmware

El driver en sí se compiló e instaló vía dkms (con el mismo procedimiento que la restitución del Apéndice A, sustituyendo `-v 5.4.0`), y se recargó con `rmmod`/`modprobe`. En este punto `hailortcli` daba `HAILO_DRIVER_OPERATION_FAILED(36)` / en dmesg `Mismatch Driver version pcie driver 5:4:0 pci_ep driver 5:3:0`, y se descubrió que **también era necesario subir por separado a 5.4.0 el firmware del dispositivo (lado SoC, pci_ep)**.

```bash
# Obtener el firmware desde el S3 oficial (usando el script incluido en el repositorio del driver)
bash hailort-drivers/download_firmware_hailo10h.sh
# Hacer copia de seguridad del firmware existente antes de sustituirlo por la nueva versión
sudo cp -r /lib/firmware/hailo/hailo10h /lib/firmware/hailo/hailo10h.backup-5.3.0
sudo cp <destino de extracción>/hailo10h_fw_5.4.0/* /lib/firmware/hailo/hailo10h/
sudo chown -R root:root /lib/firmware/hailo/hailo10h/
```

En este punto se intentó recargar el módulo (`rmmod`/`modprobe`, incluyendo la especificación `support_soft_reset=1`), pero dmesg devolvía consistentemente `SOC Firmware batch was already loaded`. Al revisar el código fuente del driver, se comprobó que `load_soc_firmware()` (la ruta de carga del firmware SoC del Hailo-10H) no implementa el procesamiento de reinicio suave mediante `support_soft_reset` (solo está implementado en `load_nnc_firmware()` del Hailo-8), y se omite incondicionalmente mientras `hailo_pcie_is_firmware_loaded()` devuelva true. Es decir, **el estado del firmware en el SoC no se puede cambiar recargando el módulo; es imprescindible un ciclo de energía real del hardware**.

Tras el reinicio, dmesg registró la escritura del batch de firmware (en el orden `customer_certificate.bin`, `scu_fw.bin`, `u-boot-*.dtb.signed`, `u-boot-spl.bin`, `fitImage`, `image-fs`, 4064 ms) → `SOC Firmware Batch loaded successfully`, y `hailortcli fw-control identify` respondió normalmente con `Firmware Version: 5.4.0 (release,app)`.

### 4.4 Verificación simple del comportamiento de CMA y sus límites

Con `hailortcli run2` (resnet_v1_18.hef, un modelo pequeño incluido en el paquete `hailo_tutorials`), se observó la evolución de `CmaFree` (`/proc/meminfo`) en una única ejecución load/run/exit y en 8 ejecuciones sucesivas:

| Ejecución | CmaFree (kB) |
|---|---|
| baseline (justo tras reiniciar) | 170464 |
| iter 1 | 134864 |
| iter 2 | 134144 |
| iter 3~8 | 133744 (sin cambio, meseta) |

Se alcanzó una meseta en pocas repeticiones, y no se observó fuga adicional hasta la 8.ª ejecución. Sin embargo, esto es un simple load/run/exit vía CLI (iniciando un proceso distinto cada vez), y es una ruta distinta de ambas fugas conocidas reportadas por `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md`: (a) la no liberación al llamar a `VDevice.release()`/recargar el modelo **dentro del mismo proceso**, y (b) la fuga continua durante la ejecución de `generate_stream()` (inferencia LLM); este resultado no es evidencia de que el problema esté "resuelto".

El repro principal (`tools/diag_hailo_cma_reclaim.py` y el script descrito en el documento de seguimiento del foro) carga un LLM de GenAI vía los bindings de Python `hailo_platform` (pyhailort), por lo que no se pudo ejecutar tal cual en el entorno 5.4.0:

```
$ hailo_platform dentro del .venv está enlazado de forma fija a libhailort.so.5.3.0 (confirmado con ldd)
$ Se prevé que, al construir VDevice(), se produzca el mismo HAILO_INVALID_DRIVER_VERSION por discrepancia de versión driver(5.4.0)/library(5.3.0)
```

En este punto aún no se había iniciado el trabajo de recompilar pyhailort (los bindings de Python) desde el código fuente de 5.4.0 y sustituirlo en el `.venv`, pero se llevó a cabo en el 3.er intento (§5).

---

## 5. Recompilación de pyhailort y reejecución del repro (2026-08-17, 3.er intento)

Esta sección registra el veredicto provisional en el momento del 3.er intento. El método de determinación y la conclusión fueron corregidos en la prueba A/B del 4.º intento (§8).

### 5.1 Compilación de pyhailort (bindings de Python)

`hailort/libhailort/bindings/python/platform/` del repositorio del propio `hailort` es la fuente del paquete pip de pyhailort (`pyproject.toml`, basado en scikit-build-core + pybind11). Se compiló enlazando explícitamente con libhailort 5.4.0, ya colocado en `/usr/local` en §4.2:

```bash
cd hailort/libhailort/bindings/python/platform
CMAKE_ARGS="-DLIBHAILORT_PATH=/usr/local/lib/libhailort.so.5.4.0 -DHAILORT_INCLUDE_DIR=/usr/local/include" \
  <venv>/bin/python -m pip install .
```

Dentro del aislamiento de compilación (build isolation) se obtuvieron automáticamente `scikit-build-core`/`pybind11` desde PyPI, se compiló, y se sustituyó `hailort` en el `.venv` del wheel 5.3.0 → 5.4.0. Se confirmó con `ldd` que `_pyhailort*.so` está enlazado a `/usr/local/lib/libhailort.so.5.4.0`, y el construct/release de `VDevice()` también funcionó normalmente por sí solo.

### 5.2 Reejecución del repro existente (`tools/diag_hailo_cma_reclaim.py`)

Se remidió con el mismo script de repro, mismo criterio de veredicto y mismo HEF (`~/hailo_models/Qwen3-1.7B-Instruct.hef`) que en 2026-05, en el mismo entorno con `hailo_platform` sustituido a 5.4.0 en el `.venv`:

```bash
uv run python tools/diag_hailo_cma_reclaim.py --signal terminate
```

Resultado (`logs/hailo_cma_reclaim_poc.json`):

| Evento | CmaFree (MB) |
|---|---|
| baseline_before_spawn | 159 |
| after_vdevice_created / after_llm_loaded | 22 (consumidos 137 MB) |
| justo tras el kill del hijo (`terminate`) | 23 |
| post_wait +5s | 26 |
| post_wait +10s | 28 |
| post_wait +15s | 29 |
| post_wait +20s~+30s | **0** (una caída adicional de unos 28.5 MB desde 29 MB, y `CmaFree` se mantuvo pegado en torno a 512 kB durante varios minutos después también) |

Esta segunda caída de 29 MB → alrededor de 512 kB no se pudo confirmar como debida a competencia de otros procesos en ese mismo momento, pero esta medición por sí sola no permite identificar la causa; se deja registrado como una observación no resuelta.

Sin embargo, este entorno de alrededor de 512 kB es la misma banda que los 464→1,648 kB observados durante la prueba de `FOLL_LONGTERM` en §8.3, y desde ese estado se logró con éxito realizar 20 generaciones, liberación y recarga. El proceso que llevó al valor bajo permanece sin resolver, pero **se confirmó en hardware real que este rango de `CmaFree` por sí solo no implica de inmediato un estado peligroso ni la imposibilidad de carga**.

Texto original emitido por la antigua herramienta de diagnóstico (veredicto provisional del momento del 3.er intento; la conclusión final fue corregida en §8):

```
VERDICT: FAIL — only -22 MB recovered after kill+wait. spec hypothesis invalid → pivot to auto-reboot alternatives
```

Lo único que quedó establecido en este intento es que el `CmaFree` tras la primera carga del HEF no se recuperó conforme al antiguo criterio de veredicto. No se demostró la pérdida de memoria disponible tras la finalización del proceso ni que la fuga permaneciera sin corregir en v5.4.0. En el 3.er intento se interpretó provisionalmente como no liberada, pero esa interpretación y el método de determinación fueron corregidos en §8.

---

## 6. Fallo del kernel durante el 3.er intento y restauración del código de depuración de CMA (2026-08-17)

### 6.1 Evento y candidatos de causa

Para investigar la ruta de liberación de CMA, se había añadido a `linux/vdma/memory.c` del código fuente local de DKMS un include de `linux/mm.h` y código de medición que llama a `virt_to_page()` / `page_count()` justo antes de `dma_free_coherent()`. Al cargar el módulo que incluía este cambio, el sistema se colgaba al usar Hailo y quedaba incapaz de arrancar, por lo que actualmente se detiene la carga automática con `module_blacklist=hailo1x_pci,hailo_pci` en `/boot/firmware/cmdline.txt`.

Convertir directamente a página la dirección virtual de CPU devuelta por `dma_alloc_coherent()` mediante `virt_to_page()` no forma parte del contrato de la API DMA. El formato de mapeo de la dirección devuelta queda a discreción del asignador (allocator), por lo que el `page_count()` obtenido de esta forma no es un medio correcto de observar el conteo de referencias de CMA, y puede generar referencias a páginas inválidas. El código de medición se ejecuta en ambas rutas de liberación, tanto de la lista de descriptores como del buffer continuo.

La hora de la adición fue 10:15:36, y el inicio de la compilación DKMS correspondiente fue 10:15:39, por lo que se puede determinar que el módulo que se colgó incluía este código. No se pudo obtener el stack trace justo antes del fallo, por lo que no es una determinación estricta de la causa, pero es el único cambio de código de ejecución local que no existe en el vanilla v5.4.0, y se considera el candidato de causa más probable.

### 6.2 Estado restaurado

Se eliminaron las siguientes 7 líneas (el include de `linux/mm.h` y los logs de `virt_to_page()` / `page_count()` en dos puntos), se recompiló DKMS y se completó hasta `depmod`.

- Kernel: `6.18.39+rpt-rpi-2712`
- Módulo recompilado: `/lib/modules/6.18.39+rpt-rpi-2712/updates/dkms/hailo1x_pci.ko.xz`
- Este módulo ya está registrado en `modules.dep`
- La lista negra (blacklist) sigue vigente; el módulo recompilado aún no se ha cargado

La próxima vez, tras asegurar una ruta de recuperación como una consola serie, se quitará la lista negra y se confirmará la primera carga mediante un reinicio. En la investigación del propio problema de CMA no liberada, no se reintroducirá la medición que convierte la dirección devuelta por la API DMA en páginas internas; el objeto de observación serán el libro mayor de buffers, el tamaño de reserva y el número de llamadas a `dma_free_coherent()` que mantiene el driver.

**Añadido (2026-08-17, más tarde)**: tras preparar una copia de seguridad de `cmdline.txt` (`cmdline.txt.bak-blacklisted`), se quitó la lista negra, se reinició, y se confirmó que arrancaba normalmente (también se configuró la consola serie `console=serial0,115200`, con lo que la ruta de recuperación está asegurada). A partir de aquí, se continuó la investigación con la instrumentación segura de §7 (sin inspección de páginas en bruto, solo salida de log de contadores y tamaños existentes).

---

## 7. Formación y exclusión de hipótesis de causa — verificación y refutación de `FOLL_LONGTERM` (2026-08-17)

Esta sección registra la formación de hipótesis de causa a raíz del 3.er intento, y los candidatos de causa que se pudieron excluir mediante experimentación. El papel de esta sección es acotar candidatos; el veredicto final sobre la existencia o no de la fuga de CMA depende de la prueba A/B del 4.º intento (§8).

Tras el fallo de §6, se continuó la investigación con instrumentación segura que evita el acceso directo al interior de páginas como `virt_to_page()` (solo salida de log mediante `dev_err()`; sin inspección ni conversión de punteros en bruto).

### 7.1 Contenido de la instrumentación

Se añadieron logs que emiten los contadores atómicos existentes (`controller->desc_cma_in_use` / `controller->cma_in_use`) y el tamaño de reserva, en los siguientes puntos de `linux/vdma/memory.c` / `linux/vdma/ioctl.c` / `linux/vdma/vdma.c` (sin ningún acceso al interior de páginas):

- `hailo_desc_list_create`/`hailo_desc_list_release` (alloc/free de la lista de descriptores)
- `hailo_vdma_continuous_buffer_alloc`/`hailo_vdma_continuous_buffer_free` (alloc/free del buffer continuo)
- `hailo_desc_list_release_ioctl`/`hailo_vdma_continuous_buffer_free_ioctl` (ruta ioctl de liberación explícita)
- `hailo_vdma_buffer_map`/`hailo_vdma_buffer_destroy` (ruta de mapeo/desmapeo DMA de buffers de espacio de usuario; también se emiten `buffer_type`/`is_mmio`/`is_dmabuf`)
- `hailo_vdma_file_context_finalize` (limpieza masiva en el momento de fops_release, emitiendo los contadores en ENTER/EXIT)

### 7.2 Resultados observados

Se ejecutó `tools/diag_hailo_cma_reclaim.py --signal terminate` justo tras reiniciar (`CmaFree` ≈ 451 MB), y se recolectaron y agregaron todos los logs con `sudo dmesg | grep CMA_DBG`.

- **`CmaFree` de `/proc/meminfo`**: 451 MB → 195 MB (**consumidos 256 MB**) → tras kill+30 s de espera, 204 MB (**247 MB por debajo del baseline**)
- **`desc_cma_in_use` propio del driver (lista de descriptores, vía `dma_alloc_coherent`)**: como máximo unos 2~4 MB. En el momento del EXIT de `file_context_finalize` vuelve con seguridad a 0
- **`cma_in_use` (buffer continuo, vía `dma_alloc_coherent`)**: durante esta sesión, siempre 0 (el buffer continuo nunca se usó)
- **Mapeo DMA de buffers de espacio de usuario (`hailo_vdma_buffer_map`, `buffer_type=0`=`HAILO_DMA_USER_PTR_BUFFER`, `is_mmio=0`, `is_dmabuf=0`)**: llamado 621 veces, de las cuales **342 fueron de tamaño 8 MB (`0x800000`)** (un total de 2.7 GB en llamadas de mapeo. Parece que el mismo buffer de staging del lado del host se reutiliza en el procesamiento de la canalización). `hailo_vdma_buffer_destroy` se llamó 628 veces, correspondiendo casi 1 a 1 con `buffer_map`, y **como libro mayor de mapeo propio del driver no está roto** (`dma_unmap_sg` se llama correctamente)
- **SWIOTLB (`/sys/kernel/debug/swiotlb/`)**: `io_tlb_used_hiwater=0`. El buffer de rebote nunca se usó
- El dispositivo Hailo no está bajo IOMMU (no existe `/sys/bus/pci/devices/0001:01:00.0/iommu_group`)

En este punto, se interpretó como candidato de causa de la caída de CMA no la reserva propia del driver vía `dma_alloc_coherent()` (lista de descriptores, buffer continuo), sino la ruta que maneja `hailo_vdma_buffer_map()` — "mapear para DMA memoria ya reservada por el espacio de usuario" (`HAILO_DMA_USER_PTR_BUFFER`). En esta ruta el driver no reserva nueva CMA, sino que fija (pin) las páginas de usuario existentes para hacerlas accesibles por DMA.

### 7.3 Hipótesis de causa: no se especifica `FOLL_LONGTERM` en `get_user_pages()`

Al revisar `prepare_sg_table()` (llamada internamente por `hailo_vdma_buffer_map()`) en `linux/vdma/memory.c`:

```c
pinned_pages = compat_get_user_pages(user_address, npages, FOLL_WRITE | FOLL_FORCE, pages);
```

`compat_get_user_pages` (dado que este kernel 6.18.39 corresponde a `LINUX_VERSION_CODE >= KERNEL_VERSION(6, 5, 0)`) es simplemente un alias de `get_user_pages()`, y **no se especifica la bandera `FOLL_LONGTERM`**. El lado de liberación (`clear_sg_table()`) también llama al `put_page()` correspondiente, permaneciendo en el antiguo sistema `get_user_pages()`/`put_page()` en lugar de la nueva familia de API `pin_user_pages()`/`unpin_user_pages()`.

Según la práctica documentada del kernel de Linux (`Documentation/core-api/pin_user_pages.rst`), el código que mantiene referencias a páginas durante largo tiempo, como en las transferencias DMA, **debería usar `pin_user_pages()` con `FOLL_LONGTERM`**. Si no se especifica `FOLL_LONGTERM`, aunque una página de usuario que casualmente residía en la región CMA se fije mediante `get_user_pages()`, la propiedad de "poder moverse a otro uso cuando sea necesario" (migratable) inherente a la CMA queda deshabilitada durante un período prolongado. El asignador de CMA normalmente migra esa página fuera de la región CMA antes de la fijación de largo plazo, pero en la ruta que no usa `FOLL_LONGTERM` esta migración no ocurre, por lo que **mientras está fijada, esa porción se pierde efectivamente de la región CMA, y ni siquiera tras liberarla (`put_page()`) se reconoce de inmediato como espacio libre de CMA** (porque se necesita migración/compactación adicional por separado).

Esta hipótesis fue consistente con la medición aislada del 3.er intento (§7.2):
- Los contadores de CMA propios del driver son irrelevantes (`get_user_pages` no pasa por `dma_alloc_coherent`)
- El número de llamadas map/destroy está correctamente balanceado (el propio `put_page()` sí se llama correctamente; el problema es que el "retorno" a CMA tras la liberación es lento/incompleto)
- Al cargar un LLM grande como Qwen3-1.7B-Instruct se reservan y mapean vía DMA en la memoria del host un gran número de buffers de 8 MB, y si parte de ellos incluye páginas dentro de la región CMA, este problema se manifiesta
- También es consistente con la recuperación lenta y parcial de `CmaFree` tras el kill (unos +15~30 MB en 30 segundos, seguido de un aumento gradual durante varios minutos más) (el propio `put_page()` sí se llama con seguridad al finalizar el proceso, pero se necesita procesamiento adicional para la recuperación como espacio libre de CMA)

### 7.4 Implementación y verificación en hardware del candidato de corrección → refutación (2026-08-17, continuación)

Se sustituyó realmente `prepare_sg_table()` de `get_user_pages(FOLL_WRITE | FOLL_FORCE)` + `put_page()` a `pin_user_pages(FOLL_WRITE | FOLL_FORCE | FOLL_LONGTERM)` + `unpin_user_page()`, añadiendo el include de `<linux/mm.h>`, y se completó la compilación, el reregistro en dkms y la carga en hardware real (se confirmó que los símbolos `pin_user_pages`/`unpin_user_page` se resolvían correctamente con `modprobe --dump-modversions`).

Resultado de ejecutar el mismo repro partiendo de un estado de `CmaFree` alto (453 MB) justo tras reiniciar:

| | Antes de la corrección (n=varias ejecuciones) | Después de la corrección (n=1) |
|---|---|---|
| baseline | 436~451 MB | 453 MB |
| after_llm_loaded | 173~195 MB (consumidos 256~263 MB) | 180 MB (consumidos 273 MB) |
| after_post_wait | 188~204 MB (recuperados 9~15 MB) | 190 MB (**recuperados 10 MB**) |
| `VERDICT` según el criterio antiguo | `FAIL` | **`FAIL` (sin cambio)** |

> Esta tabla es asimétrica en número de ejecuciones y método de agregación, y no es una comparación A/B estricta. El veredicto A/B se basa en el resultado de §8, repetido bajo condiciones idénticas.

Al revisar `CMA_DBG buffer_map` en `dmesg`, se confirmó que también tras la corrección los mismos buffers de tamaño 0x800000 (8 MB) se mapeaban sin problemas vía `pin_user_pages` (no aparecía ningún fallo de pin ni advertencia del kernel), y la ruta de código en sí se ejecutaba como se pretendía. La compactación forzada mediante `echo 1 > /proc/sys/vm/compact_memory` tampoco tuvo efecto. `MemAvailable` se mantuvo saludable en 7.1 GB, y al igual que antes de la corrección, no se trataba de una escasez de memoria en todo el sistema sino solo de una contabilidad específica de `CmaFree` que no se recuperaba.

**Conclusión: la hipótesis de la ausencia de `FOLL_LONGTERM` fue refutada experimentalmente.** El reemplazo de `get_user_pages()`→`pin_user_pages()`+`FOLL_LONGTERM` es una mejora legítima acorde con la práctica documentada del kernel de Linux, pero no fue la causa directa del síntoma de CMA no liberada observado en esta sesión. La hipótesis en sí es teóricamente razonable (la interacción entre el mecanismo de migración de CMA y la fijación de largo plazo es un tipo de problema conocido y real), y sigue siendo válida como señalamiento de calidad de código, pero **no es, por sí sola, la causa raíz que explica el resultado medido en esta ocasión**.

### 7.5 Exclusión de candidatos de causa (el veredicto final está en §8)

Los siguientes son candidatos de causa que se pudieron **excluir** claramente mediante experimentación. Esta lista es válida como resultado de la verificación de hipótesis, pero no constituye el veredicto sobre la existencia de la fuga en sí.

- Reserva propia del driver vía `dma_alloc_coherent()` (lista de descriptores, buffer continuo) — solo unos pocos MB, vuelve correctamente a 0
- Inconsistencia en las llamadas map/destroy del mapeo SG — está balanceada
- Buffer de rebote SWIOTLB — nunca se usó (`io_tlb_used_hiwater=0`)
- Ausencia de `FOLL_LONGTERM` en `get_user_pages()` — se implementó la corrección y se verificó en hardware real, sin mejora

El hecho que permaneció hasta el 3.er intento fue que `CmaFree` caía tras la primera carga mientras `MemAvailable` seguía sano. En su momento esto se interpretó como no liberado, pero una única prueba no puede distinguir entre "pérdida de memoria disponible" y "reconversión de páginas movibles de CMA en caché de páginas". En el 4.º intento se reintentó manteniendo un `CmaFree` bajo, midiendo la viabilidad real de carga, la disminución neta en repeticiones, el RSS y los fallos de asignación de CMA, corrigiendo así el veredicto.

---

## 8. 4.º intento: reprueba A/B vanilla / `FOLL_LONGTERM` y confirmación del veredicto erróneo (2026-08-17)

### 8.1 Objetos de comparación

- Versión corregida con `FOLL_LONGTERM`: `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`, al cargar `srcversion=C84A00ABB326748A1832CE1`
- Vanilla oficial 5.4.0: etiqueta `v5.4.0`, commit `b6dd17c609504e648eb516ff4a867167edf56f3c`, `get_user_pages()` / `put_page()`, al cargar `srcversion=A260C39C9F2C06DD4FB072E`
- Kernel: `6.18.39+rpt-rpi-2712`
- HEF: `Qwen3-1.7B-Instruct.hef` (2,880,748,478 bytes)

### 8.2 Dos cargas sucesivas en procesos independientes

| Driver | Intento | baseline | loaded | tras exit | cambio respecto a baseline | Carga |
|---|---:|---:|---:|---:|---:|---|
| `FOLL_LONGTERM` | 1 | 338 MB | 34 MB | 25 MB | **-313 MB (disminución)** | Éxito |
| `FOLL_LONGTERM` | 2 | 5 MB | 6 MB | 7 MB | **+2 MB (aumento)** | Éxito |
| vanilla | 1 | 376 MB | 99 MB | 112 MB | **-264 MB (disminución)** | Éxito |
| vanilla | 2 | 125 MB | 118 MB | 124 MB | **-1 MB (disminución)** | Éxito |

En ambos drivers, `CmaFree` solo caía significativamente en la primera vez, y la segunda carga partiendo de ese valor bajo tenía éxito con una disminución neta prácticamente de 0. El diagnóstico anterior juzgaba únicamente "cuántos MB del consumo durante la carga se recuperaron", por lo que marcaba como `FAIL` incluso casos normales como la segunda vez, en la que `CmaFree` ya partía bajo desde el inicio.

### 8.3 Generación, liberación y recarga dentro del mismo proceso

| Métrica | `FOLL_LONGTERM` | vanilla 1.ª vez | vanilla repetición con CMA bajo |
|---|---:|---:|---:|
| Generación completada | 20/20 | 20/20 | 20/20 |
| 1.ª carga | Éxito | Éxito | Éxito |
| 2.ª carga tras liberación | Éxito | Éxito | Éxito |
| `CmaFree` generación 1→20 | 464→1,648 kB | 115,376→123,728 kB | 82,320→83,296 kB |
| `MemAvailable` generación 1→20 | 6,706,208→6,788,432 kB | 6,830,352→6,910,560 kB | 6,871,504→6,906,368 kB |
| RSS durante la generación | fijo en 63,888 kB | 63,904~63,920 kB | 63,936~63,952 kB |
| Fallos de asignación de CMA | 0 | 0 | 0 |

La repetición vanilla con CMA bajo comenzó con `CmaFree=87,424 kB`, quedó en 79,520 kB justo tras liberar todo, y luego volvió a 87,344 kB (diferencia neta de 80 kB). No hay un comportamiento de pérdida progresiva a medida que se repite carga, generación y liberación. Que `nr_foll_pin_*` sea 0 en vanilla se debe a que no usa la API `FOLL_PIN`, por lo que no puede usarse para comparar el éxito o fracaso de la liberación del pin.

### 8.4 Interpretación de la caída inicial

Desde justo tras reiniciar en vanilla hasta después de todas las repruebas, `Cached` aumentó de 1,845,872 kB a unos 4,988,224 kB, mientras que `MemAvailable` se mantuvo entre 7,071,280 kB y unos 6,962,816 kB. El aumento es consistente con la lectura del HEF de varios GB, y la caída inicial de `CmaFree` puede explicarse no como pérdida de memoria inaccesible, sino como el uso en caché de páginas de páginas libres que incluyen páginas movibles de CMA.

### 8.5 Conclusión operativa

1. No se debe rechazar la carga de un modelo únicamente por el valor absoluto de `CmaFree`. En hardware real, la carga de Qwen tuvo éxito incluso partiendo de menos de 1 MB.
2. Un `CmaFree` bajo se registra como telemetría, y se usa el error real de asignación de memoria de HailoRT como criterio de fallo.
3. No se deben confundir el valor observado de `CmaFree`, el fallo real de carga y el diagnóstico de fuga; se manejan en los siguientes 3 estados.

| Estado | Condición de determinación | Tratamiento a nivel de producto | Reinicio / investigación |
|---|---|---|---|
| `INCONCLUSIVE` | Solo caída inicial, menos de 3 repeticiones, o no cumple las condiciones de `FAIL` de abajo | Se registra la telemetría y se intenta la carga. No se rechaza únicamente por un `CmaFree` bajo | No se reinicia. Se agregan mediciones bajo las mismas condiciones |
| `OPERATIONAL_FAIL` | HailoRT devolvió realmente un error de asignación de memoria del host | Solo se falla esa solicitud de carga concreta, se detienen workloads de Hailo innecesarios y se reintenta | No se reinicia por un solo caso. Solo cuando el fallo real se repite y no se recupera tras liberar el workload, se sigue la política operativa. La Fase 0.5 actual solo registra `would_fire`, sin reinicio automático |
| `FAIL` | Se repite la misma condición 3 veces desde un estado de CMA bajo, y la disminución neta respecto al baseline tras liberar es **superior a 10 MB en una sola prueba en 2 de 3 repeticiones**, la suma de las 3 disminuciones netas positivas **supera 20 MB**, y se acompaña de un aumento monótono de RSS o una caída de más de 128 MB en `MemAvailable` | Se registra como un diagnóstico de fuga separado de la viabilidad de carga individual | Se reanuda la investigación del lado del kernel / HailoRT y se recopila evidencia directa. El diagnóstico por sí solo no reinicia automáticamente |

Este criterio de 3 repeticiones es para diagnósticos futuros, y no se aplica retroactivamente a §8.2 de esta sección, donde los intentos en procesos independientes fueron solo 2 por driver. La conclusión del 4.º intento combina el A/B de §8.2 con las 20 generaciones, liberación y recarga dentro del mismo proceso, y la repetición con CMA bajo de §8.3.
4. El reemplazo por `FOLL_LONGTERM` es válido como práctica general de la API DMA de Linux, pero no tuvo efecto en este caso; el hardware real se restauró al vanilla oficial 5.4.0.
5. El criterio de reinicio automático no se activa únicamente por un `CmaFree` bajo; requiere como condición indispensable la observación de un fallo de carga real.

---

## 9. Próximas acciones (al 2026-08-17)

1. Se completó el examen y la refutación en hardware real de la corrección `FOLL_LONGTERM`. El diff para reproducción y el método de restauración se guardan en el Apéndice B, y no se aplica al driver de producción.
2. **El lado del producto ya está corregido**: `core/hailo_device_core/device_manager_genai.py::acquire_genai` se modificó en v4.620.8 para que, aunque `CmaFree` sea inferior a la cantidad requerida estimada, se registre `acquire_low_cma_observed` y se continúe con la carga real. Solo se registra en el tracker de rechazo el error real de memoria del host devuelto por HailoRT desde la factory, y `tests/test_hailo_cma_false_positive.py` fija que se continúe la carga partiendo de valores bajos.
3. Se reauditó en los logs y en la implementación anterior la afirmación del borrador anterior del foro de que "un `LLM(...)` posterior fue rechazado por HailoRT por insuficiente CMA de host". En la sesión PID 3237 citada como fuente no hay registro de acquire tras el release, y todos los rechazos por CMA bajo rastreables en el log del mismo día fueron el evento propio `acquire_rejected_low_cma` previo a la llamada a HailoRT. En otra sesión, el fallo que sí llegó hasta la factory fue status 8 (`HAILO_INTERNAL_FAILURE`), no status 3 (error de memoria del host). Por lo tanto, no hay evidencia de OOM de HailoRT que respalde la afirmación anterior, y se retracta explícitamente en `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md`, dejando constancia de que se mezcló en el informe un rechazo originado por la propia guarda interna.
4. La publicación de corrección integrará en un único borrador vigente las cifras y el alcance de aplicación de §8, la corrección de la guarda de implementación, la refutación de `FOLL_LONGTERM` y las advertencias sobre la instrumentación, sin dejar el antiguo borrador en inglés en forma copiable.
5. Solo si se reproduce un fallo de carga real o una pérdida acumulativa de memoria disponible por cada repetición, se reanudará la investigación de fuga del lado del kernel / HailoRT. En ese caso se recopilará evidencia directa como `page_owner`, información de depuración de CMA, status de fallo de asignación, RSS y `MemAvailable`.

---

## Apéndice A. Procedimiento de restauración a v5.3.0

Tras hacer `remove --all` de dkms una vez, la restauración falla con `apt-get install --reinstall` si no queda el `.deb` en la caché de apt (en este caso también falló: `no es posible reinstalar, no se puede descargar`). Como dpkg sigue reconociendo el paquete `hailort-pcie-driver` como `ii` (instalado), si no ha desaparecido el destino de expansión del origen del paquete `/usr/src/hailort-pcie-driver/`, se puede reconstruir manualmente el árbol de dkms desde ahí:

```bash
sudo rmmod hailo1x_pci

sudo rm -rf /usr/src/hailo1x_pci-5.3.0
sudo cp -r /usr/src/hailort-pcie-driver /usr/src/hailo1x_pci-5.3.0
sudo sed 's/@PCIE_DRIVER_VERSION@/5.3.0/' \
  /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf.in \
  | sudo tee /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf > /dev/null

# dkms.conf debe colocarse directamente en la raíz del árbol (bajo linux/pcie/ da error)
sudo cp /usr/src/hailo1x_pci-5.3.0/linux/pcie/dkms.conf /usr/src/hailo1x_pci-5.3.0/dkms.conf

sudo dkms add -m hailo1x_pci -v 5.3.0
sudo dkms build -m hailo1x_pci -v 5.3.0 -k $(uname -r)
sudo dkms install -m hailo1x_pci -v 5.3.0 -k $(uname -r) --force
sudo depmod -a
sudo modprobe hailo1x_pci
sudo udevadm trigger --subsystem-match=hailo1x
```

Confirmación de la restauración:

```bash
cat /sys/module/hailo1x_pci/version   # → 5.3.0
hailortcli fw-control identify        # → si responde normalmente, restauración completa
```

---

## Apéndice B. Procedimiento de guardado, aplicación y restauración a vanilla del parche del driver para el experimento de refutación

### B.1 Elemento guardado y su posicionamiento

Se guardó tal cual, en el siguiente archivo, el diff de driver realmente usado en el A/B.

- `docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch`
- SHA-256: `7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f`
- Código fuente base: `hailo-ai/hailort-drivers` etiqueta `v5.4.0`, commit `b6dd17c609504e648eb516ff4a867167edf56f3c`
- Archivos objetivo: `linux/vdma/ioctl.c`, `linux/vdma/memory.c`, `linux/vdma/vdma.c`

Este parche no solo contiene el reemplazo a `pin_user_pages(FOLL_LONGTERM)` / `unpin_user_page()`, sino también la instrumentación `CMA_DBG` usada en §7.1. Es decir, es el **diff completo de verificación** para reproducir el módulo experimental usado en el A/B, y no es un parche recomendado para producción. En el experimento no se confirmó ningún efecto, y el hardware actual ya se restauró al vanilla oficial 5.4.0. No se realizó ningún cambio en la biblioteca de espacio de usuario de HailoRT.

Los valores identificadores confirmados en el mismo kernel, código fuente y entorno de compilación son los siguientes.

| Estado | `srcversion` |
|---|---|
| Parche experimental | `C84A00ABB326748A1832CE1` |
| Vanilla oficial 5.4.0 | `A260C39C9F2C06DD4FB072E` |

### B.2 Verificación antes de aplicar

Lo siguiente solo debe ejecutarse cuando `/usr/src/hailo1x_pci-5.4.0` en el Raspberry Pi apunte al commit oficial mencionado arriba y no haya cambios locales en los 3 archivos objetivo. Si no coincide el commit, el checksum del parche o el checksum de `memory.c` vanilla, hay que detenerse, y no se debe forzar la aplicación del parche.

```bash
set -euo pipefail

REPO=/home/pi/GitHub/yu_ai_manager
SRC=/usr/src/hailo1x_pci-5.4.0
PATCH="$REPO/docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch"
EXPECTED_HEAD=b6dd17c609504e648eb516ff4a867167edf56f3c
EXPECTED_PATCH_SHA=7b5c4027f37432dbbbe39e4bdec2f0f5e8dd87e133473b5a44c44b1e86c5503f
EXPECTED_MEMORY_SHA=85d564acaa70cdb41eb18bad35ad958d3b2af168ae03c17466976cbe64b1e58c

test "$(sudo git -c safe.directory="$SRC" -C "$SRC" rev-parse HEAD)" = "$EXPECTED_HEAD"
printf '%s  %s\n' "$EXPECTED_PATCH_SHA" "$PATCH" | sha256sum -c -
printf '%s  %s\n' "$EXPECTED_MEMORY_SHA" "$SRC/linux/vdma/memory.c" | sha256sum -c -
sudo git -c safe.directory="$SRC" -C "$SRC" diff --exit-code -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
sudo git -c safe.directory="$SRC" -C "$SRC" apply --check "$PATCH"
```

### B.3 Aplicación del parche experimental

Solo si todas las verificaciones tienen éxito, se aplica el parche y se instala el módulo DKMS para el próximo arranque. No sustituir manualmente el módulo en carga con `rmmod` / `modprobe`; tras la compilación, cambiar mediante un reinicio normal.

```bash
set -euo pipefail

SRC=/usr/src/hailo1x_pci-5.4.0
PATCH=/home/pi/GitHub/yu_ai_manager/docs/development/patches/hailo1x_pci-5.4.0-foll-longterm-cma-debug-experiment.patch
KERNEL_VERSION="$(uname -r)"

sudo git -c safe.directory="$SRC" -C "$SRC" apply "$PATCH"
sudo dkms build -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo dkms install -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo depmod -a "$KERNEL_VERSION"

modinfo -n hailo1x_pci
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

`modinfo` indica el módulo instalado para el próximo arranque; `/sys/module/.../srcversion` indica el módulo actualmente cargado. Es normal que en este punto los valores difieran. Una vez listo, reiniciar y confirmar tras la reconexión que ambos coinciden.

```bash
sudo reboot

# Tras la reconexión
modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

En el mismo entorno de verificación, el valor esperado tras aplicar el parche es `C84A00ABB326748A1832CE1`. Si difiere, no se debe continuar la prueba por suposición; verificar el diff de código fuente, el kernel y el log de compilación de DKMS.

### B.4 Restauración al vanilla oficial 5.4.0

La restauración no depende de la aplicación inversa del parche; se restauran explícitamente los 3 archivos objetivo desde el commit verificado. Esto evita un estado de aplicación parcial o en el que solo quede la instrumentación.

```bash
set -euo pipefail

SRC=/usr/src/hailo1x_pci-5.4.0
EXPECTED_HEAD=b6dd17c609504e648eb516ff4a867167edf56f3c
EXPECTED_MEMORY_SHA=85d564acaa70cdb41eb18bad35ad958d3b2af168ae03c17466976cbe64b1e58c
KERNEL_VERSION="$(uname -r)"

test "$(sudo git -c safe.directory="$SRC" -C "$SRC" rev-parse HEAD)" = "$EXPECTED_HEAD"
sudo git -c safe.directory="$SRC" -C "$SRC" restore --source="$EXPECTED_HEAD" -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
sudo git -c safe.directory="$SRC" -C "$SRC" diff --exit-code -- \
  linux/vdma/ioctl.c linux/vdma/memory.c linux/vdma/vdma.c
printf '%s  %s\n' "$EXPECTED_MEMORY_SHA" "$SRC/linux/vdma/memory.c" | sha256sum -c -

sudo dkms build -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo dkms install -m hailo1x_pci -v 5.4.0 -k "$KERNEL_VERSION" --force
sudo depmod -a "$KERNEL_VERSION"

modinfo -F srcversion hailo1x_pci
head -n 1 /sys/module/hailo1x_pci/srcversion
```

En el mismo entorno de verificación, el valor esperado del módulo vanilla instalado es `A260C39C9F2C06DD4FB072E`. Confirmar que el valor actualmente cargado difiere, reiniciar, y tras la reconexión confirmar que ambos pasan a ser `A260C39C9F2C06DD4FB072E`.

---

## Referencia: documentos relacionados

- `docs/development/development_docs/HAILO_FORUM_FOLLOWUP_CMA_INFERENCE_LEAK.md` — datos de medición reales, script de repro y borrador de publicación en el foro de la fuga de CMA basados en la medición antigua (la conclusión está corregida en §8 de este documento)
- [HAILORT_5_3_0_MIGRATION.md](HAILORT_5_3_0_MIGRATION.md) — registro de la migración de v5.2.0 → v5.3.0 (cambio del nombre del nodo de dispositivo a `/dev/h1x-0`, etc.)
- [HAILO_CMA_LEAK_HAILORT_5_3_0.md](HAILO_CMA_LEAK_HAILORT_5_3_0.md) — registro en español del problema de fuga de CMA basado en el diagnóstico antiguo (la conclusión está corregida en §8 de este documento)
- Repositorio GitHub `hailo-ai/hailort-drivers` (GPL-2.0, código fuente público): https://github.com/hailo-ai/hailort-drivers
