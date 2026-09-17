# Playbook de mantenimiento de tests

Resumen de los puntos que hay que mirar primero cuando pytest se detiene por una base de tests antigua o por dependencias del entorno.

## Objetivo

- Separar `failed` de `skipped`
- Distinguir entre skip legítimo por dependencias del entorno y stale tests que hay que reparar
- Fijar el camino más corto cuando el broad run (`pytest tests -q --maxfail=1`) se detiene

## Comandos básicos

Verificación global normal:

```powershell
venv\Scripts\python.exe -m pytest tests -q --maxfail=1
```

Verificar también los motivos de skip:

```powershell
venv\Scripts\python.exe -m pytest tests -q -rs
```

Tratar el shared test server en modo estricto:

```powershell
$env:PYTEST_STRICT_AUTOSTART_SERVER="1"
venv\Scripts\python.exe -m pytest tests\api -q
```

Auditoría de licencias:

```powershell
venv\Scripts\python.exe scripts\license_audit.py
```

## Cómo leer los skips actuales

A fecha 2026-04-21 el broad run tiene los motivos de skip concentrados en los 5 grupos siguientes.

### 1. Shared Test Server no arrancado

El skip más frecuente. El shared server de `tests/conftest.py` arranca en best-effort y, si no puede arrancar, deja en skip en lugar de fail los grupos que dependen de browser / server.

Motivo típico:

- `Shared test server unavailable on port <PORT>`

Objetivos habituales:

- `tests/api/`
- Tests de browser UX review
- Tests dependientes de browser/server de LAN Cowork / Fleet
- Tests live browser que usan `TARGET_URL` / `BASE` / `TARGET`
- Tests de auditoría que usan fixtures propios de Playwright/WebKit en vez del fixture `page`

En un run normal esto es un **skip legítimo**. Pero hay que investigar si:

- Los unit tests que no dependen de shared server aparecen saltados por el mismo motivo
- Grupos que antes pasaban con shared server empiezan de pronto a skipearse masivamente
- Ni siquiera con `PYTEST_STRICT_AUTOSTART_SERVER=1` se ve la causa

### 2. Tests específicos del SO

Tests de sandbox / AppArmor / process isolation solo de Linux. En Windows el skip es correcto.

Ejemplos representativos:

- `tests/basic/test_os_isolation.py`
- `tests/test_process_isolation_integration.py`

Motivos típicos:

- `Linux only`
- `AppArmor es exclusivo de Linux`

Es un **skip legítimo**.

### 3. Dependencias opcionales o componentes externos faltantes

Tests que no se ejecutan en entornos donde falta cierto paquete o nodo externo.

Ejemplos representativos:

- E2E real de mDNS: `optional zeroconf package is not installed`
- Arranque de browser: `Playwright unavailable`, `launch failed`
- No hay nodo externo ONNX / YAML / ComfyUI / inferencia

Es un **skip legítimo**. No es objeto de reparación, solo falta el entorno.

### 4. Faltan datos de test

Tests de browser que necesitan imágenes, resultados de búsqueda, conversaciones, datos con múltiples entradas, etc., que no existen con una BD ligera.

Motivos típicos:

- `No search results available in database`
- `Se salta porque no hay imágenes en la BD`
- `Se necesitan al menos 2 archivos`
- `No prompts to test copy`

Generalmente es un **skip legítimo**. Pero si los datos necesarios deberían prepararlos las fixtures, conviene sospechar de un test stale.

### 5. Rate limit o protección de API externa

Algunas integraciones saltan para respetar servicios externos y rate limits.

Ejemplos representativos:

- `Se salta por haber alcanzado el rate limit`

Es un **skip legítimo**.

### 6. Fuzz / burn-in prolongados

Los burn-in bajo `tests/fuzz/` no son verificación de regresión normal, sino comprobación extra de durabilidad / resistencia a crashes.

Por defecto se excluyen mediante la expresión de marker de `pytest.ini`.

Para ejecutarlos:

```powershell
venv\Scripts\python.exe -m pytest tests\fuzz -q -m fuzz
```

Si hace falta:

```powershell
$env:FUZZ_DURATION="60"
venv\Scripts\python.exe -m pytest tests\fuzz\test_api_fuzz.py -q -m fuzz
```

**No deben mezclarse en el broad run normal**.

## Patrones que hay que considerar anómalos

No dé por buenos los siguientes casos como "es skip, no pasa nada"; trátelos como mantenimiento de tests.

### A. Un test ligero que antes pasaba cae en setup skip

Ejemplo:

- Un smoke de API que debería resolverse con fixtures app/client acaba arrastrado como si requiriera shared server
- Unit tests de migration / schema / helper de BD fallan porque asumen inicialización global de estado en runtime

En este caso sospeche de una desviación entre el test harness y el implementado.

### B. Broad run pasa, pero en ejecución individual falla

Ejemplos típicos:

- Dependencia en estado process-global
- Se apoya en efectos secundarios de tests previos del broad run

La ejecución individual debe volver a un estado reproducible.

### C. Motivo de skip ambiguo

Malos ejemplos:

- `failed`
- `not ready`
- `something wrong`

El motivo de skip debe decir en una línea corta qué faltaba para saltarlo.

## Orden de prioridad de reparación

1. Corregir los hard failures que detienen el broad run
2. Corregir los stale tests que solo fallan en ejecución individual
3. Inclinar los skips de shared server / browser hacia skip seguro en lugar de fail
4. Mantener los skips opcionales para dependencias opcionales o de hardware real

## Lo que se ha fijado en esta ronda de mantenimiento

- Las dependencias browser / server: unificar "shared server unavailable" como skip en lugar de fail
- La auditoría de licencias mira solo las dependencias declaradas en `requirements*.txt`, no todo el venv
- La BD de test cumple el prerrequisito de FTS de path del esquema de búsqueda actual
- Las migrations 54 / 55 se corrigen para no ser frágiles frente a evoluciones de esquema base y estado no inicializado en runtime

## Criterios de decisión cuando dude

- Si solo falta el entorno, el skip está bien
- Si el valor esperado está desfasado respecto a la implementación actual, corrija el test
- Si depende de efectos secundarios del broad run, corrija la implementación o el test
- Si un unit test exige estado process-global, sospeche del diseño
