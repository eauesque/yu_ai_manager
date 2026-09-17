# Sweeps API

Endpoints for Bridge sweep (NAI / SD WebUI / ComfyUI parameter axes) run history.

Run info has been persisted to `sweeps` / `sweep_axes` tables (migration 68) since v4.183.0. The `/sweep/<id>` page's history list is rendered through this API.

## GET /api/sweeps/history

Returns recent sweeps. Used by `/sweep/<id>` to show "same conditions as the current sweep" filters.

### Query parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `limit` | int (1..500) | 50 | Max entries returned |
| `ref` | string | — | Reference sweep id; required when `match` is set |
| `match` | CSV | — | Comma-separated list of fields to match against the reference |
| `tol_steps` | string | `exact` | Tolerance for steps: `exact` / `5` / `10` / `20` (percent) |
| `tol_cfg` | string | `exact` | Tolerance for CFG (same values) |
| `completed_only` | `0`/`1` | `0` | `1` keeps only `status='completed'` |
| `saved_only` | `0`/`1` | `0` | `1` keeps only rows with non-null `first_file_id` |
| `axis_count` | string | `all` | `all` / `1` / `2` / `3` |
| `date_range` | string | `all` | `all` / `today` / `week` / `month` |

#### Allowed `match` keys

- `bridge` / `checkpoint` / `vae` / `sampler` — string equality
- `positive` / `negative` — `prompt_template` / `negative_template` equality
- `axisX` / `axisY` / `axisZ` — `sweep_axes.param` at axis_index 0/1/2 must match
- `resolution` — `width` AND `height` match
- `steps` / `cfg` — numeric match (`tol_*` controls tolerance)
- `baseSeed` — `base_seed` match

Keys whose reference sweep has no value are silently ignored (in the UI the corresponding checkbox is disabled).

### Response

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

`total` is the unfiltered row count of `sweeps`, used for the "{shown} / {total} match" badge.

## GET /api/sweep/info/<file_id>

Reads the XMP packet of `file_id` and returns the structured sweep meta. See `core/bridge_core/sweep_xmp.py`.

## GET /api/sweep/files/<sweep_id>

Scans the parent folder of the hint `file_id` and returns every file whose XMP carries the same sweep id.

## How rows get populated

- **At save time**: `core/bridge_core/bridge_save_batch.py` calls `upsert_sweep_from_meta()` after auto-import. The run header + axes are written on first sight; subsequent batches only update `last_file_id` / `file_count` / `updated_at`.
- **Backfill for old files**: `uv run python scripts/backfill_sweeps.py [--db PATH] [--limit N]`. Walks `has_sweep=1` files and reconstructs rows from XMP attrs. Idempotent.

## Known limitations

- The async save path (`return_file_ids=False`) may leave `first_file_id` NULL. The UI then renders the row as a non-clickable item.
- `prompt_template` / `negative_template` are stored once per run. S/R-style per-axis substitutions are not reconstructed; per-image axis values stay in the XMP packet and are read by `/api/sweep/info/<file_id>`.
