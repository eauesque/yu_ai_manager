# Hailo Auto-Reboot Phase 0.5 — Manual de operaciones para este entorno

**Creado**: 2026-05-17 (v4.215.1)
**Entorno objetivo**: — Pi 5 que ejecuta este repositorio
**Propósito**: Un manual autónomo para iniciar, verificar y concluir la observación de la Fase 0.5, incluso si la sesión de chat original se pierde.
**Especificación de diseño**: `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md` (rev3 APPROVED)
**Guía general del operador**: `docs/es/hailo/HAILO_AUTO_REBOOT_PHASE05.md` (este documento es la variante específica del entorno)

---

## 0. Requisitos previos y trabajo ya completado

- La implementación de observación de la Fase 0.5 fue integrada y enviada a main en v4.215.1 (commit `80af4fb73` + merge `69be148c6`)
- `config.json` (raíz del repositorio) ya contiene el bloque `hailo.auto_reboot`, **añadido el 2026-05-17**
  - Configuración recomendada: `mode = "lazy"` + `dry_run = true`
  - Copia de seguridad: `config.json.bak.<marca_de_tiempo>`
- **No se desencadenará ningún reinicio real** (`dry_run = true` + el diseño de la Fase 0.5 solo registra eventos `would_fire`)

Verificar config.json:

```bash
cd /home/pi/GitHub/yu_ai_manager
jq .hailo.auto_reboot config.json
# → Debe aparecer {"mode":"lazy","dry_run":true,...}
```

---

## 1. Procedimiento de primer inicio y activación

### 1.1 Reinicio del servidor

Es necesario reiniciar para aplicar el cambio de configuración. **Reinicie utilizando el mismo método de inicio actualmente en uso.**

Comando de inicio típico (ajustar al entorno real):

```bash
cd /home/pi/GitHub/yu_ai_manager
uv run python web_ui.py --config config.json --db data/tags.db
```

Si se ejecuta como servicio systemd, reiniciar la unidad correspondiente con `sudo systemctl restart <unit>`.

### 1.2 Verificación en los primeros 30 segundos tras el inicio (3 puntos)

#### A. ¿Está registrado el evento `boot_baseline`?

```bash
tail -n 20 /home/pi/GitHub/yu_ai_manager/logs/hailo_auto_reboot.log
```

Esperado: una línea con `{"event":"boot_baseline","state":"idle","mode":"lazy","dry_run":true,"cma_free_mb":<int|null>,"hailo_runtime_version":"5.3.0",...}`.

**Resolución de problemas si no aparece**:

- `logs/hailo_auto_reboot.log` no existe → el bucle judge no está en ejecución (posiblemente no iniciado en modo `["full"]`, o la variable de entorno `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` está establecida)
- El archivo existe pero está vacío → fallo en la resolución de rutas en `core/hailo_device_core/auto_reboot_logger.py`; verificar los permisos del directorio `logs/`
- `cma_free_mb: null` → fallo en la lectura de `/proc/meminfo` (comportamiento esperado en hardware que no es Pi, inofensivo)

#### B. ¿Está activo el opt-in a través de la respuesta `/api/system/cma`?

Si está conectado mediante PIN en el navegador, no se necesita API key. Usar curl o ejecutar en la consola DevTools del navegador (con sesión PIN activa):

```js
fetch("/ext/hailo-genai/api/system/cma").then(r => r.json()).then(j => console.log(j.cma.auto_reboot))
```

Esperado:

```json
{
  "enabled": true,
  "mode": "lazy",
  "dry_run": true,
  "state": "idle",
  "consecutive_rejects": 0
}
```

Si `enabled: false` o `mode: "off"` → verificar que `hailo.auto_reboot.mode` en config.json sea `"lazy"` y que el servidor haya reiniciado completamente.

#### C. ¿No hay errores de inicio en `error.log`?

```bash
tail -n 50 /home/pi/GitHub/yu_ai_manager/logs/error.log | grep -iE "hailo_auto_reboot|auto_reboot"
```

Sin salida significa OK. Si hay errores, consultar «8. Problemas conocidos» al final de este documento.

---

## 2. Operaciones diarias durante el período de observación

### 2.1 Uso normal

**Acción principal**:

- **Usar el chat LLM como de costumbre** a través de `/ext/hailo-genai/chat` o `/tools` (p. ej., Qwen3-1.7B)
- Usar VLM / S2T según sea necesario
- Las sesiones largas (30+ minutos continuas) y los cambios de modelo múltiples también vale la pena probarlos intencionalmente para ampliar los datos de observación

No se requiere ninguna prueba especial. **Cuanto más se usa normalmente, más datos recoge la Fase 0.5** — ese es el objetivo del diseño.

### 2.2 Revisión semanal (una vez por semana, ~5 minutos)

```bash
cd /home/pi/GitHub/yu_ai_manager

# Recuento de cada tipo de evento
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c

# Marcas de tiempo y CmaFree para eventos would_fire
grep would_fire logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb] | @tsv'

# Motivo de drain_entered (cma vs. rejects)
grep drain_entered logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb, .consecutive_rejects, .reason] | @tsv' 2>/dev/null || \
  grep drain_entered logs/hailo_auto_reboot.log | head -10
```

**Puntos de comprobación**:

- `would_fire` aparece 1 o más veces → la introducción de la Fase 1 es valiosa (verificar si los tiempos registrados coinciden con los reinicios manuales realizados)
- `prewarn_entered` se dispara con frecuencia pero nunca avanza a `drain_entered` → `prewarn_threshold_mb` (80 MB) puede ser demasiado bajo; recalibrar
- El motivo de `drain_entered` siempre es `rejects` → el DRAIN está impulsado por rechazos; se necesitan medidas distintas del ajuste de umbral

---

## 3. Fin de la observación y criterios de decisión para la Fase 1

### 3.1 Período de observación requerido

**Mínimo 7 días / Recomendado 14 días**. El período debe cubrir al menos los siguientes patrones:

- Chat LLM normal
- Chat LLM largo (30+ minutos en una sola sesión)
- Cambio de modelos VLM / S2T
- Al menos un rechazo previo de `acquire_genai` (CmaFree insuficiente)
- Primera carga tras el reinicio del Pi

### 3.2 Criterios numéricos para la introducción de la Fase 1

Resumen:

```bash
cd /home/pi/GitHub/yu_ai_manager
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

Tabla de decisión:

| Resultado de la observación | Decisión Fase 1 |
|---|---|
| `would_fire` ≥ 1 | **GO** (la automatización del reinicio tiene valor) |
| `would_fire` = 0, `drain_entered` ≥ 1 | Reajustar umbrales y considerar la Fase 1 (se alcanza DRAIN pero no `would_fire` — `fire_grace_seconds` podría reducirse) |
| Solo `prewarn_entered`, `drain_entered` = 0 | El umbral actual nunca alcanza el estado «crítico» → la Fase 1 puede no ser necesaria según el patrón de uso |
| Todos los eventos 0 (solo `boot_baseline`) | El uso no agota la CMA → Fase 1 no necesaria |

### 3.3 Tareas posteriores a la observación

1. Guardar los resultados del resumen en `docs/es/hailo/HAILO_AUTO_REBOOT_PHASE05_OBSERVATION_RESULTS.md` (nuevo archivo)
2. Si se procede a la Fase 1: avanzar a la Fase 1 en la especificación rev3 §5.2 (banner DRAIN en la interfaz + i18n); reconfirmar los umbrales de §3.1 basándose en los datos de observación
3. Si la Fase 1 no es necesaria: establecer `mode = "off"` en config.json y archivar el registro de observación

---

## 4. Procedimiento de desactivación (emergencia / detención de la observación)

```bash
cd /home/pi/GitHub/yu_ai_manager
jq '.hailo.auto_reboot.mode = "off"' config.json > config.json.tmp && mv config.json.tmp config.json
# Reiniciar el servidor
```

Incluso con `mode = "off"`, los eventos JSONL continúan registrándose (se suprime la salida WARN en `error.log`). Para desactivar completamente, usar la variable de entorno:

```bash
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 5. Referencia de archivos de registro (relacionados)

| Archivo | Propósito |
|---|---|
| `logs/hailo_auto_reboot.log` | **Registro principal de esta función**. Formato JSONL; rotación a 10 MB × 30 copias de seguridad |
| `logs/hailo_cma.log` | Registrador de eventos CMA existente (desde v4.214.10). Registra eventos de ciclo de vida de VDevice/modelo como `acquire_genai` |
| `logs/error.log` | Registro de errores de toda la aplicación. Cuando `mode != "off"`, también genera resúmenes WARN para `drain_entered` / `would_fire` |

---

## 6. Ubicaciones del código relacionado (para futuras investigaciones)

| Función | Archivo |
|---|---|
| Máquina de estados + RejectTracker | `core/hailo_device_core/auto_reboot.py` |
| JSONL writer | `core/hailo_device_core/auto_reboot_logger.py` |
| Punto de entrada del bucle de fondo | `core/web/startup_background_hailo_judge.py` |
| Registro de tarea en segundo plano | `core/web/startup_background.py` (`hailo_auto_reboot_judge`) |
| Valores predeterminados de configuración | `core/configuration/defaults.py` (`hailo.auto_reboot`) |
| Hook de acquire_genai | `core/hailo_device_core/device_manager_genai.py` |
| Extensión de `/api/system/cma` | `extensions/builtin_hailo_genai/hailo_genai_ext.py` |
| Pruebas unitarias | `tests/test_hailo_auto_reboot_judge.py`, `tests/test_hailo_auto_reboot_logger.py` |

---

## 7. Historial de revisión (referencia)

Esta implementación superó el flujo de revisión completo de AGENTS (ver el mensaje del commit v4.215.1). Los archivos de informe individuales se escribieron en `.claude/agent-outputs/`, que está en `.gitignore` y no está gestionado por git. Se pueden regenerar si es necesario.

---

## 8. Problemas conocidos

| Síntoma | Causa y solución |
|---|---|
| Nada aparece en `logs/hailo_auto_reboot.log` | Servidor no reiniciado / `mode = "off"` aún establecido / no iniciado en modo `["full"]` / variable de entorno `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` establecida |
| `cma_free_mb: null` persiste | Ejecutándose en hardware que no es Pi (p. ej., WSL2) o fallo en la lectura de `/proc/meminfo`; verificar en hardware Pi real |
| `hailo_runtime_version: null` | Paquete `hailo_platform` no instalado en este entorno; en un Pi 5 real, se obtiene si HailoRT 5.3.0 está instalado |
| `would_fire` nunca aparece | La carga de uso es demasiado ligera o los umbrales son demasiado amplios; intentar chats largos continuos / cambios de modelo y volver a observar |
| El modo `eager` está configurado pero no funciona | En la Fase 0.5, `eager` vuelve intencionalmente a `off` (con un registro de advertencia); previsto para implementación en la Fase 1+ |

---

## 9. Reversión de emergencia

En el improbable caso de que la implementación de la Fase 0.5 tenga un problema (baja probabilidad ya que no se desencadenan reinicios reales):

```bash
cd /home/pi/GitHub/yu_ai_manager
# Revertir de v4.215.1 a v4.214.13 (solo especificación, antes de la implementación)
git revert -m 1 69be148c6
git push
```

O **desactivar completamente solo mediante configuración** (recomendado):

```bash
# Añadir al entorno de inicio y reiniciar el servidor
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 10. Mantenimiento de este documento

- Al completar la observación, **añadir el resumen de §3.3 al final de este documento** (necesario para la decisión de la Fase 1 en futuras sesiones de chat)
- Tras la introducción de la Fase 1, renombrar este documento a `HAILO_AUTO_REBOOT_PHASE05_RUNBOOK_ARCHIVED.md` y crear un nuevo manual para la Fase 1
- Este documento reside en `/home/pi/GitHub/yu_ai_manager/docs/es/hailo/HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md` (gestionado por git)
