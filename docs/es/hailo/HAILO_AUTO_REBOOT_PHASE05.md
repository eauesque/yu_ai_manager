# Guía de operaciones de Hailo Auto-Reboot Phase 0.5

**Creado**: 2026-05-17 (v4.215.0)
**Objetivo**: Operaciones de observación de CMA leak en Raspberry Pi 5 + Hailo-10H + HailoRT 5.3.0
**Estado**: Fase de observación. No se realiza ningún reinicio real; solo se registran los eventos `would_fire`.

---

## 1. Propósito de la Phase 0.5

La Phase 0.5 es la fase de observación del diseño de reinicio automático contra los CMA leaks en HailoRT 5.3.0 + `hailo1x_pci`.

En esta fase, la máquina de estados calcula los siguientes estados:

| Estado | Condición |
|---|---|
| `idle` | Estado normal |
| `prewarn` | `CmaFree < 80 MB` persiste durante 180 segundos |
| `draining` | `CmaFree < 30 MB` persiste durante 60 segundos, o el pre-reject de `acquire_genai` ocurre 3 veces consecutivas |
| `would_fire` | Han transcurrido 120 segundos desde `draining` |

Importante: En la Phase 0.5, aunque se alcance `would_fire`, el Pi NO se reinicia. El evento solo se registra como JSON Lines en `logs/hailo_auto_reboot.log`.

---

## 2. Por qué el valor predeterminado es `mode = "off"`

El valor predeterminado de `hailo.auto_reboot.mode` es `"off"`. Dado que el reinicio automático puede interrumpir el trabajo del operador, la observación solo se inicia en entornos donde el operador ha optado explícitamente por participar (opt-in).

La configuración recomendada para la Phase 0.5 es la siguiente:

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "prewarn_threshold_mb": 80,
      "prewarn_duration_seconds": 180,
      "drain_threshold_mb": 30,
      "drain_duration_seconds": 60,
      "drain_consecutive_rejects": 3,
      "fire_grace_seconds": 120,
      "poll_interval_seconds": 30
    }
  }
}
```

`dry_run = true` es un requisito previo de la Phase 0.5. La ruta de reinicio real se maneja en la Phase 4 y posteriores.

### 2.1 Procedimiento de opt-in

La configuración de inicio prioriza el archivo especificado mediante `--config` o `TAGDB_CONFIG`. Si no se especifica, lee `config.json` en el directorio raíz del repositorio, luego `tagdb_config.json`.

Ejemplo:

```bash
cd <repo>
cp config.json config.json.bak.$(date +%Y%m%d-%H%M%S)
```

Añada la siguiente configuración a `<repo>/config.json` o al archivo JSON especificado mediante `--config` / `TAGDB_CONFIG` durante la operación:

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "poll_interval_seconds": 30
    }
  }
}
```

Reinicie el servidor para aplicar la configuración. Mantenga los argumentos que está utilizando según su método de inicio.

```bash
uv run python web_ui.py --config config.json --db data/tags.db
```

Si opera con systemd, reinicie la unidad correspondiente:

```bash
sudo systemctl restart yu-ai-manager.service
```

### 2.2 Procedimiento de desactivación

Cambie `hailo.auto_reboot.mode` a `"off"` en la misma configuración y reinicie el servidor.

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "off",
      "dry_run": true
    }
  }
}
```

Con `mode = "off"`, los eventos de observación de JSON Lines permanecen, pero no se genera ningún resumen WARN en `error.log`.

---

## 3. Cómo leer los registros

Los registros de observación se escriben en el siguiente archivo:

```text
logs/hailo_auto_reboot.log
```

El formato es JSON Lines. Los eventos principales son los siguientes:

| Evento | Significado |
|---|---|
| `boot_baseline` | Punto de inicio de observación en el arranque |
| `prewarn_entered` | Condición PREWARN cumplida |
| `drain_entered` | Condición DRAIN cumplida |
| `would_fire` | Punto que se convertiría en disparador de reinicio en la Phase 1+ |
| `drain_cleared` | CMA recuperado y DRAIN eliminado |

Ejemplo:

```json
{"event":"would_fire","cma_free_mb":18,"mode":"lazy","dry_run":true,"state":"would_fire","hailo_runtime_version":"5.3.0"}
```

Ejemplos de comandos de verificación:

```bash
tail -F logs/hailo_auto_reboot.log | jq -r '[.ts, .event, .cma_free_mb, .state] | @tsv'
```

```bash
grep would_fire logs/hailo_auto_reboot.log
grep drain_entered logs/hailo_auto_reboot.log
```

Si `would_fire` ocurre con frecuencia, indica que con los umbrales actuales es muy probable que sea necesario reiniciar el Pi durante la operación real. Por el contrario, si solo aparece `prewarn_entered` sin progresar a `drain_entered`, los umbrales o tiempos de tolerancia pueden reajustarse antes de la Phase 1.

---

## 4. Procedimiento de verificación de la API

Verifique `/api/system/cma` con la clave de API de administrador.

```bash
curl -H "X-API-Key: <admin-key>" \
  http://<host>:<port>/ext/hailo-genai/api/system/cma
```

Examine `cma.auto_reboot.enabled`, `cma.auto_reboot.mode`, `cma.auto_reboot.state` y `cma.auto_reboot.consecutive_rejects` en la respuesta.

```json
{
  "cma": {
    "auto_reboot": {
      "enabled": true,
      "mode": "lazy",
      "state": "idle",
      "consecutive_rejects": 0
    }
  }
}
```

---

## 5. Período de observación

El objetivo es de 1 a 2 semanas. Asegúrese de que el período cubra al menos los siguientes patrones:

- Uso normal de chat con LLM
- Uso de chat de larga duración
- Operaciones que causen fallos de carga del modelo Hailo GenAI o pre-rejects
- Primera carga después del reinicio del Pi

La observación se considera completa cuando se pueden agregar datos de frecuencia de `prewarn_entered` / `drain_entered` / `would_fire` durante 1 a 2 semanas. Después de la observación, revise el número de ocurrencias de `would_fire`, el motivo de `drain_entered` (`cma` / `rejects`) y la tasa de disminución de `CmaFree` para finalizar los umbrales antes de implementar la Phase 1.

Ejemplo de agregación:

```bash
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

---

## 6. Documentos relacionados

- `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md`
- `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- `logs/hailo_cma.log` (`core/hailo_device_core/device_helpers.py::log_hailo_cma_event`)
- `logs/hailo_auto_reboot.log` (`core/hailo_device_core/auto_reboot_logger.py`)
