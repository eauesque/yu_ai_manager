# Sweeps API

Bridge sweep（NAI / SD WebUI / ComfyUI 參數軸掃描）的執行歷史端點。

自 v4.183.0 起，執行資訊持久化到 `sweeps` / `sweep_axes` 資料表（migration 68）。`/sweep/<id>` 頁面的歷史清單透過本 API 渲染。

## GET /api/sweeps/history

回傳最近的 sweep 清單，支援「與目前 sweep 同條件」篩選。

### 查詢參數

| 參數 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `limit` | int (1..500) | 50 | 回傳條目數 |
| `ref` | string | — | 參照 sweep id；使用 `match` 時必填 |
| `match` | CSV | — | 與參照比對的欄位（逗號分隔） |
| `tol_steps` | string | `exact` | steps 容差：`exact` / `5` / `10` / `20`（%）|
| `tol_cfg` | string | `exact` | CFG 容差（同上）|
| `completed_only` | `0`/`1` | `0` | `1` 時僅回傳 `status='completed'` |
| `saved_only` | `0`/`1` | `0` | `1` 時僅回傳具備 `first_file_id` 的記錄 |
| `axis_count` | string | `all` | `all` / `1` / `2` / `3` |
| `date_range` | string | `all` | `all` / `today` / `week` / `month` |

#### 可用的 `match` 鍵

- `bridge` / `checkpoint` / `vae` / `sampler` — 字串完全比對
- `positive` / `negative` — `prompt_template` / `negative_template` 完全比對
- `axisX` / `axisY` / `axisZ` — 在 axis_index 0/1/2 的 `sweep_axes.param` 必須相符
- `resolution` — `width` 和 `height` 同時相符
- `steps` / `cfg` — 數值比對（容差由 `tol_*` 控制）
- `baseSeed` — `base_seed` 比對

參照 sweep 缺少該欄位值的鍵會被忽略。

### 回應

```json
{
  "ok": true,
  "data": {
    "entries": [{
      "id": "uuid-xxxx", "bridge": "nai",
      "created_at": 1714992000,
      "checkpoint": "nai-anime-v3", "sampler": "k_euler",
      "width": 832, "height": 1216, "steps": 28, "cfg": 5.5,
      "axis_count": 1, "first_file_id": 12345,
      "axes_params": ["cfg_rescale"]
    }],
    "total": 142
  }
}
```

## 資料寫入路徑

- **儲存時**: `core/bridge_core/bridge_save_batch.py` 於 auto-import 後呼叫 `upsert_sweep_from_meta()`
- **既有檔案**: `uv run python scripts/backfill_sweeps.py` 掃描 `has_sweep=1` 檔案從 XMP 重建記錄。idempotent
