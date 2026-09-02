# WD Tagger API

WD Tagger（Waifu Diffusion Tagger）Danbooru 自動標籤的 API。提供設定管理、單檔/批次標籤、標籤 CRUD、模型管理、XMP 讀取及 VLM 連線測試功能。

## GET /api/wd-tagger/config

取得目前的 WD Tagger 設定。

### 參數

無

### 回應

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

## POST /api/wd-tagger/config

儲存/更新 WD Tagger 設定。

### Rate Limit

WRITE

### 請求

```json
{
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "threshold": 0.35
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| *（任意鍵）* | any | 否 | 設定欄位。未知的鍵或無效的值會回傳 `400` |

### 回應

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `invalid_json` | 400 | 請求主體不是 JSON 物件 |
| `invalid_value` | 400 | 無效的設定值 |

## POST /api/wd-tagger/tag/<file_id>

對單一檔案執行 WD Tagger 推論，預測並指派 Danbooru 標籤。

### Rate Limit

HEAVY

### 參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `file_id` | int | 檔案 ID（路徑參數） |

### 請求

```json
{
  "force": false
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `force` | boolean | 否 | 若為 `true`，覆寫現有標籤並重新執行推論。預設 `false` |

### 回應

```json
{
  "file_id": 42,
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general"},
    {"tag": "solo", "score": 0.95, "category": "general"}
  ]
}
```

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `tag_error` | 400 | 標籤處理失敗（找不到檔案、圖片載入錯誤等） |

## GET /api/wd-tagger/tags/<file_id>

取得指定檔案已儲存的 WD Tagger 標籤。

### 參數

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file_id` | int | 是 | 檔案 ID（路徑參數） |
| `model` | string | 否 | 依模型名稱篩選（查詢參數） |
| `all` | boolean | No | When `1`, `true`, or `yes`, return tags from all models and ignore the active model and `model` filter |

### 回應

```json
{
  "file_id": 42,
  "tags": [
    {"tag": "1girl", "score": 0.98, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"},
    {"tag": "solo", "score": 0.95, "category": "general", "model": "SmilingWolf/wd-swinv2-tagger-v3"}
  ]
}
```

## DELETE /api/wd-tagger/tags/<file_id>

刪除指定檔案的 WD Tagger 標籤。

### Rate Limit

WRITE

### 參數

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file_id` | int | 是 | 檔案 ID（路徑參數） |
| `model` | string | 否 | 依模型名稱篩選（查詢參數）。省略時刪除所有模型的標籤 |

### 回應

```json
{
  "file_id": 42,
  "deleted": 15
}
```

## DELETE /api/wd-tagger/tags/batch

批次刪除多個檔案的 WD Tagger 標籤。

### Rate Limit

WRITE

### 請求

```json
{
  "file_ids": [1, 2, 3],
  "model": "wd-swinv2-tagger-v3"
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `file_ids` | list | 是 | 檔案 ID 陣列（最大 500） |
| `model` | string | 否 | 依模型名稱篩選。省略時刪除所有模型的標籤 |

### 回應

```json
{
  "deleted_files": 3,
  "deleted_tags": 45
}
```

## Active model (v4.192.0+)

同一檔案若用多個 WD Tagger 模型重新標籤，`file_wd_tags` 會保留各模型的標籤
作為歷史。設定 active model 後，詳細顯示、`ai_analyzed` 搜尋，以及 WD Tagger
內部的「已標籤檔案」判定只會使用該模型的標籤。未設定時會維持舊行為，將所有
模型的標籤一起處理。

### 在 UI 中設定

retag modal 上方會顯示目前的 `Active model`。使用 `Change` dropdown 可從可用
模型中選擇。選擇 `(none / reset)` 可清除 active model。

重新標籤完成後，預設會把這次使用的模型切換為 active model。若要維持目前的
active model，請關閉 retag modal 中的「重新標籤後設為作用中模型」勾選。

舊模型的 row 不會自動刪除，會保留在 DB 中作為歷史。只有在 retag modal 中啟用
「也刪除其他模型的標籤」並於重新標籤後確認對話框時，才會明確刪除舊模型標籤。


### GET /api/wd-tagger/profiles

Returns registered WD Tagger profiles and the current active model. Requires admin scope.

```json
{
  "profiles": [
    {
      "id": "camie_tagger_v2",
      "display_name": "Camie Tagger v2",
      "model_id": "Camais03/camie-tagger-v2",
      "adapter_family": "camie",
      "backend": "onnx",
      "builtin": true,
      "has_tags": false
    }
  ],
  "active_model_id": "Camais03/camie-tagger-v2"
}
```

### GET /api/wd-tagger/active-model

取得目前 active model 與 DB 中存在的模型清單。需要 admin scope。

```json
{
  "active_model_id": "SmilingWolf/wd-eva02-large-tagger-v3",
  "available_models": [
    {"model_id": "SmilingWolf/wd-eva02-large-tagger-v3", "file_count": 120},
    {"model_id": "SmilingWolf/wd-swinv2-tagger-v3", "file_count": 340}
  ]
}
```

### PUT /api/wd-tagger/active-model

變更 active model。需要 admin scope。`model_id` 傳入 `null` 或空字串可重設為
未設定。

```json
{
  "model_id": "SmilingWolf/wd-eva02-large-tagger-v3"
}
```

| 代碼 | 狀態 | 說明 |
|------|------|------|
| `invalid_model_id` | 400 | model_id 太長或包含控制字元 |
| `unknown_model` | 400 | DB 中不存在指定模型的標籤 |

## POST /api/wd-tagger/batch

對多個檔案執行批次標籤。若指定 `file_ids`，僅處理這些檔案。若省略，則自動選取未標籤的檔案，最多 `limit` 個。

### Rate Limit

HEAVY

### 請求

```json
{
  "file_ids": [1, 2, 3],
  "limit": 100,
  "force": false,
  "scan_root": ""
}
```

| 參數 | 類型 | 是否必填 | 限制 | 說明 |
|------|------|----------|------|------|
| `file_ids` | int[] | 否 | 最多 500 | 目標檔案 ID 陣列。省略時自動選取未標籤的檔案 |
| `limit` | int | 否 | - | `file_ids` 省略時的最大處理數。預設 `100` |
| `force` | boolean | 否 | - | 若為 `true`，覆寫現有標籤。預設 `false` |
| `scan_root` | string | 否 | - | 依掃描根路徑篩選。空字串表示所有檔案 |

### 回應

```json
{
  "job_id": "wd_tagger",
  "total": 100,
  "status": "started"
}
```

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `batch_too_large` | 400 | `file_ids` 超過 500 筆 |
| `batch_error` | 409 | 批次任務已在執行中 |

## POST /api/wd-tagger/batch/cancel

取消正在執行的批次標籤任務。

### Rate Limit

WRITE

### 請求

不需要請求主體。

### 回應

```json
{
  "status": "cancelling",
  "message": "Batch tagging cancel requested"
}
```

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `job_not_running` | 404 | 沒有正在執行的批次標籤任務 |

## GET /api/wd-tagger/stats

取得 WD Tagger 標籤統計資訊。

### 參數

無

### 回應

```json
{
  "total_tagged": 1234,
  "total_tags": 56789,
  "models": {
    "SmilingWolf/wd-swinv2-tagger-v3": 1200
  },
  "untagged_unknown": 42
}
```

| 欄位 | 類型 | 說明 |
|------|------|------|
| `total_tagged` | int | 已標籤的檔案數 |
| `total_tags` | int | 已儲存的標籤總數 |
| `models` | object | 各模型的已標籤檔案數 |
| `untagged_unknown` | int | 無中繼資料（`unknown`）且無 WD 標籤的檔案數 |

## GET /api/wd-tagger/untagged

列出無中繼資料（`unknown`）且尚未標籤的檔案。支援分頁。

### 參數

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `limit` | int | 否 | 結果數量。1-500，預設 `100` |
| `offset` | int | 否 | 要跳過的結果數。預設 `0` |

### 回應

```json
{
  "files": [
    {"id": 10, "filepath": "/images/photo.png", "filename": "photo.png"}
  ],
  "total": 42
}
```

## GET /api/wd-tagger/xmp/<file_id>

讀取指定檔案的 XMP 中繼資料。

### 參數

| 參數 | 類型 | 說明 |
|------|------|------|
| `file_id` | int | 檔案 ID（路徑參數） |

### 回應

```json
{
  "file_id": 42,
  "xmp": {
    "subject": ["1girl", "solo", "blue_eyes"],
    "description": "...",
    "creator": "..."
  }
}
```

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `file_not_found` | 404 | 檔案不存在或已被軟刪除 |

## GET /api/wd-tagger/vlm/test

測試與 VLM（Vision Language Model）伺服器的連線。檢查 OpenAI 相容 API 端點的可達性。

### 參數

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `url` | string | 是 | VLM 伺服器 URL（查詢參數） |

### 回應

```json
{
  "ok": true,
  "message": "Connection successful",
  "server_info": "..."
}
```

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `missing_url` | 400 | 未提供 `url` 參數 |
| `invalid_url` | 400 | URL 格式無效 |

## GET /api/wd-tagger/vlm/models

列出 VLM 伺服器上的可用模型。查詢 OpenAI 相容的 `/v1/models` 端點。

### 參數

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `url` | string | 是 | VLM 伺服器 URL（查詢參數） |

### 回應

```json
{
  "models": [
    {"id": "llava-v1.6", "object": "model"}
  ]
}
```

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `missing_url` | 400 | 未提供 `url` 參數 |
| `invalid_url` | 400 | URL 格式無效 |
| `vlm_connection_error` | 502 | 無法連線到 VLM 伺服器 |

## POST /api/wd-tagger/model/download

下載 WD Tagger 模型。從 Hugging Face 取得模型檔案並儲存到本機。

### Rate Limit

HEAVY

### 請求

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3"
}
```

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `repo` | string | 否 | Hugging Face 儲存庫名稱。省略時使用設定中的 `model` 值 |

### 回應

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "path": "/path/to/model/directory",
  "ready": true
}
```

### 錯誤

| 代碼 | 狀態碼 | 說明 |
|------|--------|------|
| `unknown_model` | 400 | 未知的模型儲存庫。`hint` 包含已知模型列表 |
| `download_failed` | 500 | 下載失敗 |

## GET /api/wd-tagger/model/status

檢查 WD Tagger 模型的下載狀態。

### 參數

| 參數 | 類型 | 是否必填 | 說明 |
|------|------|----------|------|
| `repo` | string | 否 | Hugging Face 儲存庫名稱（查詢參數）。省略時使用設定中的 `model` 值 |

### 回應

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "downloaded": true,
  "path": "/path/to/model/directory",
  "known_models": {
    "SmilingWolf/wd-swinv2-tagger-v3": "SwinV2 (recommended)",
    "SmilingWolf/wd-convnext-tagger-v3": "ConvNeXt",
    "SmilingWolf/wd-vit-tagger-v3": "ViT"
  }
}
```

| 欄位 | 類型 | 說明 |
|------|------|------|
| `repo` | string | 正在檢查的儲存庫名稱 |
| `downloaded` | boolean | 模型是否已下載到本機 |
| `path` | string/null | 已下載時的本機模型路徑 |
| `known_models` | object | 所有支援的模型（儲存庫名稱 -> 顯示名稱） |

## User profile CRUD (v4.197.0+)

用於在 Tools 頁面 UI 以 CRUD 管理使用者自訂 tagger profile 的 API。所有端點都需要 admin scope。共通錯誤格式為 `{ok: false, error, code, ...extra}`。請求 body 有 **1MB 硬上限**（`code: profile_too_large`、413）。`id` 必須符合 `^[a-z0-9][a-z0-9_-]{0,63}$` regex。

### POST /api/wd-tagger/profiles

建立新的使用者 profile。

**請求**: profile JSON（schema v2、`profile_version: "2"`）。`builtin` 欄位會在伺服器端被強制覆寫為 `false`。

**回應 (200)**:
```json
{
  "ok": true,
  "profile": { "...": "...サニタイズ済 profile JSON..." },
  "origin": "user",
  "overrides_builtin": false
}
```

| 欄位 | 說明 |
|---|---|
| `profile` | 已儲存的 profile（確定為 `builtin: false`） |
| `origin` | 永遠為 `"user"` |
| `overrides_builtin` | 若存在相同 id 的 builtin profile 則為 `true`（advanced 路徑） |

**錯誤**:

| status | code | 條件 |
|---|---|---|
| 400 | `validation_failed` | JSON 不符合 schema v2（`extra.errors=[{path, message}, ...]`） |
| 400 | `invalid_id` | body 的 `id` 不符合 regex |
| 409 | `id_conflict` | 與既有 user profile 的 id 衝突 |
| 413 | `profile_too_large` | body > 1MB |

### GET /api/wd-tagger/profiles/{id}

取得指定 id 的 full schema v2 profile（UI 於編輯 / 複製 / Export 時呼叫）。

**path**: `id`（regex check 必須）

**回應 (200)**:
{與 POST 同形: profile / origin / overrides_builtin}

**錯誤**:
- 400 `invalid_id`（path id regex 不符合）
- 404 `not_found`

### PUT /api/wd-tagger/profiles/{id}

更新既有的使用者 profile。

**path**: `id`（必須做 regex 檢查）

**請求**: profile JSON。`body.id` 必須與 path id 一致（rename 請在 UI 引導 `Duplicate → Delete`）。

**回應 (200)**: 與 POST 同形。

**錯誤**:

| status | code | 條件 |
|---|---|---|
| 400 | `id_immutable` | path id 與 body id 不一致 |
| 400 | `invalid_id` | path id 不符合 regex |
| 400 | `validation_failed` | schema 違反 |
| 403 | `builtin_read_only` | path id 為 builtin profile（user 端無對應檔案） |
| 404 | `not_found` | id 未註冊 |
| 413 | `profile_too_large` | body > 1MB |

### DELETE /api/wd-tagger/profiles/{id}

刪除使用者 profile。

**path**: `id`

**回應 (200)**:
```json
{"ok": true, "deleted": true}
```

**錯誤**:

| status | code | 條件 |
|---|---|---|
| 400 | `invalid_id` | path id 不正確 |
| 403 | `builtin_read_only` | 僅有 builtin，且沒有 user override |
| 404 | `not_found` | id 未註冊 |
| 409 | `in_use` | 該 profile 為 active model（會附帶 `extra.active_model_id`）。UI 端請先透過 `PUT /api/wd-tagger/active-model` 切換 active 後再重試 |

### POST /api/wd-tagger/profiles/{id}/test

dry-run download。會對每個 `files[]` 在 HuggingFace 上做 HEAD，並針對 `required: true` 的項目執行檔案級的 atomic download（快取會重用既有路徑）。

**path**: `id`

**body**: 不需要

**行為**:
- per-file timeout: 30s
- 全體 timeout: 60s
- redirect: 僅允許 `huggingface.co` / `hf.co` 子網域 allowlist，最多 5 hop，userinfo（`user:pass@`）為 SSRFBlocked

**回應 (200, 成功)**:
```json
{
  "ok": true,
  "files": [
    {"name": "model.onnx", "status": "downloaded", "size": 1234567},
    {"name": "tags.csv",   "status": "cached",     "size": 89012},
    {"name": "optional.json", "status": "skipped_optional", "size": null}
  ]
}
```

`status` 值:
- `downloaded`: 本次下載完成
- `cached`: 本機已存在（僅 HEAD）
- `skipped_optional`: `required: false` 且 404 / HEAD 失敗

**錯誤 (status / code)**:

| status | code | 條件 |
|---|---|---|
| 400 | `invalid_id` / `required_missing` | path id 不正確 / required 檔案在 HF 為 404 |
| 404 | `not_found` | profile 未註冊 |
| 408 | `timeout` | 全體超過 60s |
| 502 | `ssrf_blocked` | redirect 不在 HF allowlist / 含 userinfo / scheme 非 http(s) |
| 502 | `hf_unavailable` | HF 回傳 5xx |

錯誤時 body 會是 `{"ok": false, "code": ..., "error": ..., "files": [...部分結果...], "detail": "..."}` 形。

### profile JSON 格式 (schema v2)

```typescript
interface ProfileV2 {
  profile_version: "2";
  id: string;
  display_name: string;
  adapter_family: "wd" | "camie" | "oppai" | "generic_onnx";
  backend: "onnx";
  model_id: string;                        // HF repo path "<owner>/<name>"
  hf_subdir: string | null;
  files: { name: string; required: boolean; size_hint_mb?: number }[];
  default_thresholds: Record<string, number>;
  tag_source: TagSourceSpec;               // type=csv/json_list/json_dict/composite
  threshold_source: ThresholdSourceSpec;   // type=global_per_category/per_tag_json
  preprocess_spec: PreprocessSpec;
  supports_categories: string[];
  categories_mode: "from_tag_source" | "all_general";
  builtin?: boolean;                       // 使用者來源永遠為 false（伺服器強制）
}
```

詳細請參考 `extensions/builtin_wd_tagger/core_impl/adapters/base.py`（`TaggerProfile`），或 builtin 的參考實作（`extensions/builtin_wd_tagger/core_impl/profiles/*.json`）。
