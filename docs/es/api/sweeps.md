# API de Sweeps

Puntos finales para el historial de ejecución de sweep Bridge (ejes de parámetros NAI / SD WebUI / ComfyUI).

La información de ejecución se ha persistido en las tablas `sweeps` / `sweep_axes` (migración 68) desde v4.183.0. La lista de historial de la página `/sweep/<id>` se renderiza a través de esta API.

## GET /api/sweeps/history

Devuelve sweeps recientes. Utilizado por `/sweep/<id>` para mostrar filtros de "mismas condiciones que el sweep actual".

### Parámetros de consulta

| Parámetro | Tipo | Predeterminado | Descripción |
|---|---|---|---|
| `limit` | int (1..500) | 50 | Máximo de entradas devueltas |
| `ref` | string | — | ID de sweep de referencia; requerido cuando se establece `match` |
| `match` | CSV | — | Lista separada por comas de campos para comparar con la referencia |
| `tol_steps` | string | `exact` | Tolerancia para pasos: `exact` / `5` / `10` / `20` (porcentaje) |
| `tol_cfg` | string | `exact` | Tolerancia para CFG (mismos valores) |
| `completed_only` | `0`/`1` | `0` | `1` mantiene solo `status='completed'` |
| `saved_only` | `0`/`1` | `0` | `1` mantiene solo filas con `first_file_id` no nulo |
| `axis_count` | string | `all` | `all` / `1` / `2` / `3` |
| `date_range` | string | `all` | `all` / `today` / `week` / `month` |

#### Claves `match` permitidas

- `bridge` / `checkpoint` / `vae` / `sampler` — igualdad de cadena
- `positive` / `negative` — igualdad de `prompt_template` / `negative_template`
- `axisX` / `axisY` / `axisZ` — `sweep_axes.param` en axis_index 0/1/2 debe coincidir
- `resolution` — coincidencia de `width` Y `height`
- `steps` / `cfg` — coincidencia numérica (`tol_*` controla la tolerancia)
- `baseSeed` — coincidencia de `base_seed`

Las claves cuyo sweep de referencia no tiene valor se ignoran silenciosamente (en la interfaz de usuario, la casilla de verificación correspondiente está deshabilitada).

### Respuesta

```json
{
  "ok": true,
  "data": {
    "entries": [
      {
        "id": "uuid-xxxx",
        "bridge": "nai",
        "base_seed": 1234567,
        "created_at": 1714992000,
        "prompt_template": "best quality, ...",
        "negative_template": "worst quality, ...",
        "checkpoint": "nai-anime-v3",
        "vae": null,
        "sampler": "k_euler",
        "width": 832,
        "height": 1216,
        "steps": 28,
        "cfg": 5.5,
        "axis_count": 1,
        "first_file_id": 12345,
        "last_file_id": 12399,
        "file_count": 6,
        "status": "completed",
        "updated_at": 1714992100,
        "axes_params": ["cfg_rescale"]
      }
    ],
    "total": 142
  }
}
```

`total` es el número de filas sin filtrar de `sweeps`, utilizado para el distintivo "{shown} / {total} match".

## GET /api/sweep/info/<file_id>

Lee el paquete XMP de `file_id` y devuelve los metadatos de sweep estructurados. Véase `core/bridge_core/sweep_xmp.py`.

## GET /api/sweep/files/<sweep_id>

Escanea la carpeta principal de la pista `file_id` y devuelve todos los archivos cuyo XMP tenga el mismo ID de sweep.

## Cómo se rellenan las filas

- **En el momento de guardar**: `core/bridge_core/bridge_save_batch.py` llama a `upsert_sweep_from_meta()` después de la importación automática. El encabezado de ejecución y los ejes se escriben a primera vista; los lotes posteriores solo actualizan `last_file_id` / `file_count` / `updated_at`.
- **Relleno retroactivo para archivos antiguos**: `uv run python scripts/backfill_sweeps.py [--db PATH] [--limit N]`. Recorre archivos `has_sweep=1` y reconstruye filas a partir de atributos XMP. Idempotente.

## Limitaciones conocidas

- La ruta de guardado asincrónico (`return_file_ids=False`) puede dejar `first_file_id` NULL. La interfaz de usuario luego renderiza la fila como un elemento no clickeable.
- `prompt_template` / `negative_template` se almacenan una vez por ejecución. Las sustituciones por eje estilo S/R no se reconstruyen; los valores de eje por imagen permanecen en el paquete XMP y son leídos por `/api/sweep/info/<file_id>`.
