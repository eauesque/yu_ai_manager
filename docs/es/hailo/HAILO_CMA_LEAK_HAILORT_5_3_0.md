# Fuga de CMA en HailoRT 5.3.0 — Diagnóstico confirmado y restricciones operativas

> **Nota de corrección**: Este documento es un registro del diagnóstico de fuga de CMA basado en una medición antigua, y la conclusión antigua —según la cual la CMA no se recupera tras `release()`, se filtra de forma continua a razón de aproximadamente 14 MB/min durante la inferencia, y solo el reinicio del propio Pi es un medio de recuperación seguro— ha sido retractada. El veredicto final de la reprueba de HailoRT/driver 5.4.0 fue corregido en §8 de [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md). No consultar la conclusión antigua de este documento como el veredicto práctico vigente.

**Creado**: 2026-05-17 (descubierto y registrado en v4.214.11)
**Ámbito afectado**: Raspberry Pi 5 + Hailo-10H + `hailort==5.3.0` (ruta `hailo_platform.genai`)
**Síntoma**: Una vez cargado un LLM, la CMA apenas se recupera incluso después de llamar a `VDevice.release()` / `LLM.release()`. Además, la CMA continúa filtrándose de forma continua durante la inferencia. No hay forma de recuperarse excepto reiniciando el Pi.
**Estado**: Confirmado como restricción estructural en el lado del controlador. Se están investigando soluciones alternativas.

---

## 1. Base del diagnóstico confirmado

Usando el registrador de eventos CMA introducido en `v4.214.10` (`logs/hailo_cma.log`, `core/hailo_device_core/device_helpers.py::log_hailo_cma_event`), se midió la siguiente secuencia el 2026-05-17.

### 1-1. Registro de observación (raw)

`logs/hailo_cma.log`:

```text
2026-05-17T14:05:13+0900 event=vdevice_create_pre  cma_free_mb=392 pid=3237
2026-05-17T14:05:14+0900 event=vdevice_create_post cma_free_mb=393 pid=3237
2026-05-17T14:05:14+0900 event=acquire_pre  cma_free_mb=393 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:06:25+0900 event=acquire_post cma_free_mb=108 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
        ↓ 6 minutos de uso en chat (aproximadamente 5–10 mensajes de inferencia)
2026-05-17T14:12:36+0900 event=release_pre  cma_free_mb=24  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:12:36+0900 event=release_post cma_free_mb=25  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
```

### 1-2. Interpretación

| Fase | Diferencia CmaFree | Significado |
|---|---|---|
| `vdevice_create_pre` → `vdevice_create_post` | **+1 MB (≈ 0)** | La creación de VDevice en sí misma apenas consume CMA |
| `acquire_pre` → `acquire_post` (carga de Qwen3-1.7B-Instruct) | **−285 MB** | 1 LLM consume 285 MB |
| `acquire_post` → `release_pre` (6 minutos de inferencia) | **−84 MB / 6 min ≒ −14 MB/min** | **Fuga continua también durante la inferencia** |
| `release_pre` → `release_post` (descarga de LLM) | **+1 MB** | **`release()` efectivamente no devuelve CMA** |

### 1-3. Comparación con la hipótesis anterior

Este es un resultado de medición que contradice parcialmente la hipótesis inicial del §7 de `SQLCIPHER_MMAP_CORRUPTION.md` creado el 2026-05-16 y la hipótesis de que "la estrategia de retención de VDevice (nuestro `_maybe_reset_vdevice` vacío) amplifica la fuga". Dado que la creación de VDevice = 0 MB / release = 0 MB, **cambiar la estrategia de retención (= cambiar `_maybe_reset_vdevice` para que se reinicie cada vez) no tendría efecto**.

---

## 2. Restricciones estructurales

Según los resultados medidos, HailoRT 5.3.0 (build de comunidad, API `hailo_platform.genai`) tiene tres problemas concurrentes:

1. **`VDevice.release()` / `release()` del modelo GenAI no recupera la CMA del host** (confirmado por medición)
   - Dentro de un único proceso, el controlador PCIe (`hailo1x_pci`) continúa manteniendo las regiones DMA, y no ocurre ninguna operación equivalente a `munmap`
2. **Fuga continua de CMA durante la inferencia (~14 MB/min)** (confirmado por medición)
   - Observación de hoy: 84 MB perdidos en 6 minutos durante el uso de Qwen3-1.7B-Instruct
   - Una ruta separada independiente de carga/descarga. El agotamiento ocurre incluso sin descargar
3. **No se ha confirmado ningún método para recuperar CMA de forma fiable excepto reiniciar el Pi** (medición + informes de la comunidad)
   - Incluso reiniciar el proceso del servidor (equivalente a `systemctl restart yu-ai-manager`) es incompleto ya que `hailo1x_pci` mantiene DMA hasta el ciclo de energía PCIe. La recuperación completa requiere `sudo reboot` del Pi (medido en este repositorio)
   - Existen múltiples informes independientes en la comunidad de Hailo: <https://community.hailo.ai/t/hailo-10h-on-rpi5-undocumented-api-findings-dfc-conversion-failures-with-transformer-based-models-swinv2-vit-convnext/18979> y <https://community.hailo.ai/t/hailo-10h-throughput-degrades-irreversibly-within-minutes-of-continuous-use-125-41-fps-only-host-reboot-recovers/19218> (indica explícitamente que `VDevice.release()` / salida de proceso / recarga del controlador no recupera, solo el reinicio del host)
   - Esto ya está documentado para los usuarios en el mensaje de error de rechazo previo de `acquire_genai` (`core/hailo_device_core/device_manager_genai.py::acquire_genai`, "a full system reboot is required")

### 2-1. «¿Matar un proceso hijo devuelve CMA?»: **Refutado por medición** (2026-05-17 Phase 0 PoC)

La versión anterior (rev1) concluyó teóricamente que «el kernel de Linux recupera las páginas DMA durante el teardown de `mm_struct`, por lo que matar un proceso hijo recupera completamente la CMA», pero **la medición con Phase 0 PoC (`tools/diag_hailo_cma_reclaim.py`) confirmó independientemente dos veces que matar un proceso hijo apenas recupera CMA**.

**Resultados de medición (2.ª ejecución, versión estricta)**:

| Punto de medición | CmaFree | Δ |
|---|---:|---:|
| Línea base (antes del inicio del PoC) | 503 MB | — |
| Después de crear VDevice | 372 MB | **-131 MB** (la construcción de VDevice consume CMA en proceso hijo de arranque en frío) |
| Después de cargar LLM | 372 MB | 0 MB (LLM contenido en el pool DMA de VDevice, sin nuevo consumo) |
| Después de SIGTERM + join | 378 MB | +6 MB |
| **Después de 30 segundos de espera** | **380 MB** | **Solo +8 MB recuperados en total** |

Frente a una recuperación esperada de ≥250 MB, el valor medido fue solo de +8 MB (+1 MB en la primera medición incidental). Esto está al nivel del jitter del sistema — **no se produjo ninguna recuperación significativa de CMA**.

**Diagnóstico confirmado**:

- El controlador `hailo1x_pci` gestiona el pool DMA en el **estado global interno del controlador** y no en el `mm_struct` del proceso de usuario (estimado)
- No se recupera mediante `process exit`, `kill` o `module unload` (coherente con los informes de la comunidad)
- **El único método de recuperación confirmado es `sudo reboot` del Pi (= ciclo de energía PCIe)** ← este es el hecho medido indicado en §2 fila 3

Informe detallado: `docs/superpowers/specs/codex-reviews/2026-05-17-hailo-subprocess-isolation-phase0-poc-result.md`

Como resultado de estos hallazgos, `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md` se marca como **REJECTED**, y se abandona el enfoque de mitigación mediante aislamiento de subprocess. Se adopta el enfoque de reinicio automático del §4 (D) como alternativa.

---

## 3. Implicaciones operativas

### 3-1. «1 modelo por reinicio del Pi» es efectivamente el límite

- Con Pi 5 (límite de CMA 512 MB, no se puede aumentar según la especificación del Pi) + LLM Qwen3 (285 MB):
    - CmaFree inmediatamente después del reinicio ≒ 480 MB
    - Después de cargar 1 LLM → CmaFree ≒ 190 MB
    - Después de decenas de minutos de inferencia → CmaFree ≒ 50 MB o menos
    - **Cargar un segundo modelo es permanentemente imposible** (requiere 250+ MB pero el restante es insuficiente, y release no lo devuelve)

### 3-2. El uso simultáneo de LLM + VLM / LLM + S2T no es posible

- Los casos de uso que alternan entre VLM (basado en llava, ~300 MB), S2T (whisper-small, ~175 MB) y LLM son imposibles debido a las restricciones anteriores a menos que se siga el procedimiento de **cargar → reiniciar → cargar**.
- **La UX multimodelo como «adjuntar una imagen durante la conversación para cambiar a otro modelo» o «transcribir audio de conversación» no es estructuralmente posible con HailoRT 5.3.0**.

### 3-3. Las sesiones de inferencia continua larga son difíciles

- La fuga de 14 MB/min significa que incluso comenzando con 200 MB de CmaFree, se reduce a la mitad en 14 minutos y se agota casi por completo en 30 minutos.
- Las sesiones de chat que superen los 30 minutos no pueden estabilizarse sin un reinicio del Pi en medio.

---

## 4. Posibles contramedidas

Listadas con prioridad y esfuerzo:

| Opción | Efecto | Esfuerzo | Efectos secundarios / Riesgos |
|---|---|---|---|
| ~~(A) Aislar operaciones de Hailo en un subprocess y matar periódicamente para devolver CMA al kernel~~ | ❌ **REJECTED** (refutado por Phase 0 PoC, reproducido dos veces). La recuperación tras kill fue solo de +8 MB en total — la hipótesis falla | — | No adoptado |
| **(B) Actualizar `_CMA_ESTIMATES_MB` a valores medidos + margen** | Mejora la precisión del rechazo previo (reduce los intentos de carga falsos positivos) | ✅ Aplicable inmediatamente, 1 línea | Los casos que apenas funcionaban con la suposición de 250 MB serán rechazados, pero ya estaban fallando |
| **(C) Banner de UI cuando `CmaFree < 80 MB` / WARN en error.log cuando `< 30 MB`** | Los usuarios pueden entender la situación y se les indica que reinicien el Pi | Medio | Riesgo de fatiga de advertencias / notificaciones excesivas |
| **(D) Detectar `CmaFree < 30 MB` y enviar SIGTERM al supervisor** | Recuperación automática (aunque se necesita reinicio completo del Pi, a través de `systemctl reboot`) | Medio | Requiere permisos de supervisor / interrupción de sesión durante otro trabajo |
| **(E) Esperar corrección de HailoRT + documentar restricciones claramente** | Costo 0 | 0 | Depende del ciclo de lanzamiento de Hailo (meses+) |
| **(F) Enviar solicitud de corrección al rastreador de problemas / foro de Hailo** | Posiblemente acelera el tiempo de corrección | Pequeño | La velocidad de respuesta depende del contrato de soporte y el estado de la comunidad |

Política a corto plazo (implementada en v4.214.11): **Aplicar (B) + este documento (punto de partida para E y F)**.
Política a medio plazo (spec separado): Considerar en el orden de **(C) advertencia de UI → (A) aislamiento de subprocess**.
Largo plazo: Monitorear las versiones de HailoRT y actualizar este documento para eliminar las restricciones cuando se corrijan.

---

## 5. Documentos / Código relacionados

- `core/hailo_device_core/device_manager_genai.py::acquire_genai` — La verificación previa de CmaFree + el mensaje de error para el usuario expone explícitamente esta restricción
- `core/hailo_device_core/device_helpers.py::_CMA_ESTIMATES_MB` — Estimaciones de requisitos de CMA por modelo (qwen incrementado de 250 → 300 en v4.214.11)
- `core/hailo_device_core/device_helpers.py::log_hailo_cma_event` — Instrumentación de medición introducida en v4.214.10. Los datos de medición en este documento provienen de aquí
- `core/hailo_device_core/device_manager_state.py::_maybe_reset_vdevice` — Diseño que mantiene VDevice durante la vida útil del proceso (función vacía). Esta medición confirma que cambiarlo para que se reinicie no contribuiría a la recuperación de CMA
- `docs/ja/hailo/HAILO_AUTO_REBOOT_PHASE05.md` — Guía del operador para la fase de observación 0.5. Procedimiento para recopilar solo registros `would_fire` con `mode=lazy` + `dry_run=true`
- `docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md` — Límite total de CMA del Pi5 y consumo base de cada controlador (camera / KMS / Hailo / HEVC)
- `docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md` — Antecedentes de la migración a HailoRT 5.3.0 y diferencias conocidas

---

## 6. Pasos de reproducción (para informes de problemas de Hailo)

Pasos mínimos de reproducción para informes de errores externos:

```bash
# 1. Confirmar la línea base inmediatamente después del reinicio del Pi
grep CmaFree /proc/meminfo
# CmaFree: ~480000 kB

# 2. Iniciar servidor + cargar el 1.er LLM (p.ej., enviar 1 mensaje a través de GenAI en /tools)
# 1 solicitud a /api/llm/generate o /api/chat/send

# 3. Verificar CmaFree
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB (-280 MB)

# 4. Descargar modelo
curl -X POST http://127.0.0.1:5000/ext/hailo-genai/api/model/unload -d '{"model":"llm"}'

# 5. Verificar CmaFree
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB (no devuelto ← bug)

# 6. Intentar recargar el mismo / otro modelo → rechazado por CMA insuficiente
```

Comportamiento esperado: En el paso 5, CmaFree debería volver a un valor cercano a la línea base del paso 1 (>400 MB).
Comportamiento real: Solo se devuelve aproximadamente +1 MB, la recarga es imposible.
