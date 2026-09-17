# Sweeps API

Bridge sweep（NAI / SD WebUI / ComfyUI 参数轴扫描）的运行历史端点。

自 v4.183.0 起，运行信息持久化到 `sweeps` / `sweep_axes` 表（migration 68）。`/sweep/<id>` 页面的历史列表通过本 API 渲染。

## GET /api/sweeps/history

返回最近的 sweep 列表，支持"与当前 sweep 同条件"过滤。

### 查询参数

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `limit` | int (1..500) | 50 | 返回条目数 |
| `ref` | string | — | 参考 sweep id；使用 `match` 时必需 |
| `match` | CSV | — | 与参考比较的字段（逗号分隔） |
| `tol_steps` | string | `exact` | steps 容差：`exact` / `5` / `10` / `20`（%）|
| `tol_cfg` | string | `exact` | CFG 容差（同上）|
| `completed_only` | `0`/`1` | `0` | `1` 时仅返回 `status='completed'` |
| `saved_only` | `0`/`1` | `0` | `1` 时仅返回有 `first_file_id` 的记录 |
| `axis_count` | string | `all` | `all` / `1` / `2` / `3` |
| `date_range` | string | `all` | `all` / `today` / `week` / `month` |

#### 可用的 `match` 键

- `bridge` / `checkpoint` / `vae` / `sampler` — 字符串完全匹配
- `positive` / `negative` — `prompt_template` / `negative_template` 完全匹配
- `axisX` / `axisY` / `axisZ` — 在 axis_index 0/1/2 的 `sweep_axes.param` 必须匹配
- `resolution` — `width` 和 `height` 同时匹配
- `steps` / `cfg` — 数值匹配（容差通过 `tol_*` 控制）
- `baseSeed` — `base_seed` 匹配

参考 sweep 中没有值的字段会被忽略。

### 响应

```json
{
  "ok": true,
  "data": {
    "entries": [
      {
        "id": "uuid-xxxx",
        "bridge": "nai",
        "created_at": 1714992000,
        "checkpoint": "nai-anime-v3",
        "sampler": "k_euler",
        "width": 832, "height": 1216,
        "steps": 28, "cfg": 5.5,
        "axis_count": 1,
        "first_file_id": 12345,
        "axes_params": ["cfg_rescale"]
      }
    ],
    "total": 142
  }
}
```

## 数据写入路径

- **保存时**: `core/bridge_core/bridge_save_batch.py` 在 auto-import 后调用 `upsert_sweep_from_meta()`
- **历史文件**: `uv run python scripts/backfill_sweeps.py` 会扫描 `has_sweep=1` 文件并从 XMP 重建记录。idempotent
