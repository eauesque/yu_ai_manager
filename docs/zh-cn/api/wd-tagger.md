# WD Tagger API

WD Tagger（Waifu Diffusion Tagger）Danbooru 自动标签的 API。提供配置管理、单文件/批量标签、标签 CRUD、模型管理、XMP 读取及 VLM 连接测试功能。

## GET /api/wd-tagger/config

获取当前的 WD Tagger 配置。

### 参数

无

### 响应

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

保存/更新 WD Tagger 配置。

### Rate Limit

WRITE

### 请求

```json
{
  "model": "SmilingWolf/wd-swinv2-tagger-v3",
  "threshold": 0.35
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| *（任意键）* | any | 否 | 配置字段。未知的键或无效的值会返回 `400` |

### 响应

```json
{
  "config": {
    "model": "SmilingWolf/wd-swinv2-tagger-v3",
    "threshold": 0.35,
    "...": "..."
  }
}
```

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `invalid_json` | 400 | 请求体不是 JSON 对象 |
| `invalid_value` | 400 | 无效的配置值 |

## POST /api/wd-tagger/tag/<file_id>

对单个文件执行 WD Tagger 推理，预测并分配 Danbooru 标签。

### Rate Limit

HEAVY

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `file_id` | int | 文件 ID（路径参数） |

### 请求

```json
{
  "force": false
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `force` | boolean | 否 | 若为 `true`，覆盖现有标签并重新执行推理。默认 `false` |

### 响应

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

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `tag_error` | 400 | 标签处理失败（找不到文件、图片加载错误等） |

## GET /api/wd-tagger/tags/<file_id>

获取指定文件已存储的 WD Tagger 标签。

### 参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file_id` | int | 是 | 文件 ID（路径参数） |
| `model` | string | 否 | 按模型名称筛选（查询参数） |
| `all` | boolean | No | When `1`, `true`, or `yes`, return tags from all models and ignore the active model and `model` filter |

### 响应

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

删除指定文件的 WD Tagger 标签。

### Rate Limit

WRITE

### 参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file_id` | int | 是 | 文件 ID（路径参数） |
| `model` | string | 否 | 按模型名称筛选（查询参数）。省略时删除所有模型的标签 |

### 响应

```json
{
  "file_id": 42,
  "deleted": 15
}
```

## DELETE /api/wd-tagger/tags/batch

批量删除多个文件的 WD Tagger 标签。

### Rate Limit

WRITE

### 请求

```json
{
  "file_ids": [1, 2, 3],
  "model": "wd-swinv2-tagger-v3"
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `file_ids` | list | 是 | 文件 ID 数组（最大 500） |
| `model` | string | 否 | 按模型名称筛选。省略时删除所有模型的标签 |

### 响应

```json
{
  "deleted_files": 3,
  "deleted_tags": 45
}
```

## Active model (v4.192.0+)

同一文件若用多个 WD Tagger 模型重新标签，`file_wd_tags` 会按模型保留标签作为
历史。设置 active model 后，详情显示、`ai_analyzed` 搜索，以及 WD Tagger 内部的
“已标签文件”判定只会使用该模型的标签。未设置时保持旧行为，将所有模型的标签
一起处理。

### 在 UI 中设置

retag modal 顶部会显示当前 `Active model`。使用 `Change` dropdown 可从可用模型
中选择。选择 `(none / reset)` 可清除 active model。

重新标签完成后，默认会把本次使用的模型切换为 active model。若要保持当前 active
model 不变，请关闭 retag modal 中的“重新标签后设为活动模型”勾选。

旧模型的 row 不会自动删除，会保留在 DB 中作为历史。只有在 retag modal 中启用
“同时删除其他模型的标签”并在重新标签后确认对话框时，才会明确删除旧模型标签。


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

获取当前 active model 以及 DB 中存在的模型列表。需要 admin scope。

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

更改 active model。需要 admin scope。`model_id` 传入 `null` 或空字符串可重置为
未设置。

```json
{
  "model_id": "SmilingWolf/wd-eva02-large-tagger-v3"
}
```

| 代码 | 状态 | 说明 |
|------|------|------|
| `invalid_model_id` | 400 | model_id 过长或包含控制字符 |
| `unknown_model` | 400 | DB 中不存在指定模型的标签 |

## POST /api/wd-tagger/batch

对多个文件执行批量标签。若指定 `file_ids`，仅处理这些文件。若省略，则自动选取未标签的文件，最多 `limit` 个。

### Rate Limit

HEAVY

### 请求

```json
{
  "file_ids": [1, 2, 3],
  "limit": 100,
  "force": false,
  "scan_root": ""
}
```

| 参数 | 类型 | 是否必填 | 限制 | 说明 |
|------|------|----------|------|------|
| `file_ids` | int[] | 否 | 最多 500 | 目标文件 ID 数组。省略时自动选取未标签的文件 |
| `limit` | int | 否 | - | `file_ids` 省略时的最大处理数。默认 `100` |
| `force` | boolean | 否 | - | 若为 `true`，覆盖现有标签。默认 `false` |
| `scan_root` | string | 否 | - | 按扫描根路径筛选。空字符串表示所有文件 |

### 响应

```json
{
  "job_id": "wd_tagger",
  "total": 100,
  "status": "started"
}
```

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `batch_too_large` | 400 | `file_ids` 超过 500 条 |
| `batch_error` | 409 | 批量任务已在运行中 |

## POST /api/wd-tagger/batch/cancel

取消正在运行的批量标签任务。

### Rate Limit

WRITE

### 请求

不需要请求体。

### 响应

```json
{
  "status": "cancelling",
  "message": "Batch tagging cancel requested"
}
```

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `job_not_running` | 404 | 没有正在运行的批量标签任务 |

## GET /api/wd-tagger/stats

获取 WD Tagger 标签统计信息。

### 参数

无

### 响应

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

| 字段 | 类型 | 说明 |
|------|------|------|
| `total_tagged` | int | 已标签的文件数 |
| `total_tags` | int | 已存储的标签总数 |
| `models` | object | 各模型的已标签文件数 |
| `untagged_unknown` | int | 无元数据（`unknown`）且无 WD 标签的文件数 |

## GET /api/wd-tagger/untagged

列出无元数据（`unknown`）且尚未标签的文件。支持分页。

### 参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `limit` | int | 否 | 结果数量。1-500，默认 `100` |
| `offset` | int | 否 | 要跳过的结果数。默认 `0` |

### 响应

```json
{
  "files": [
    {"id": 10, "filepath": "/images/photo.png", "filename": "photo.png"}
  ],
  "total": 42
}
```

## GET /api/wd-tagger/xmp/<file_id>

读取指定文件的 XMP 元数据。

### 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `file_id` | int | 文件 ID（路径参数） |

### 响应

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

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `file_not_found` | 404 | 文件不存在或已被软删除 |

## GET /api/wd-tagger/vlm/test

测试与 VLM（Vision Language Model）服务器的连接。检查 OpenAI 兼容 API 端点的可达性。

### 参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `url` | string | 是 | VLM 服务器 URL（查询参数） |

### 响应

```json
{
  "ok": true,
  "message": "Connection successful",
  "server_info": "..."
}
```

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `missing_url` | 400 | 未提供 `url` 参数 |
| `invalid_url` | 400 | URL 格式无效 |

## GET /api/wd-tagger/vlm/models

列出 VLM 服务器上的可用模型。查询 OpenAI 兼容的 `/v1/models` 端点。

### 参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `url` | string | 是 | VLM 服务器 URL（查询参数） |

### 响应

```json
{
  "models": [
    {"id": "llava-v1.6", "object": "model"}
  ]
}
```

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `missing_url` | 400 | 未提供 `url` 参数 |
| `invalid_url` | 400 | URL 格式无效 |
| `vlm_connection_error` | 502 | 无法连接到 VLM 服务器 |

## POST /api/wd-tagger/model/download

下载 WD Tagger 模型。从 Hugging Face 获取模型文件并保存到本地。

### Rate Limit

HEAVY

### 请求

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3"
}
```

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `repo` | string | 否 | Hugging Face 仓库名称。省略时使用配置中的 `model` 值 |

### 响应

```json
{
  "repo": "SmilingWolf/wd-swinv2-tagger-v3",
  "path": "/path/to/model/directory",
  "ready": true
}
```

### 错误

| 代码 | 状态码 | 说明 |
|------|--------|------|
| `unknown_model` | 400 | 未知的模型仓库。`hint` 包含已知模型列表 |
| `download_failed` | 500 | 下载失败 |

## GET /api/wd-tagger/model/status

检查 WD Tagger 模型的下载状态。

### 参数

| 参数 | 类型 | 是否必填 | 说明 |
|------|------|----------|------|
| `repo` | string | 否 | Hugging Face 仓库名称（查询参数）。省略时使用配置中的 `model` 值 |

### 响应

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

| 字段 | 类型 | 说明 |
|------|------|------|
| `repo` | string | 正在检查的仓库名称 |
| `downloaded` | boolean | 模型是否已下载到本地 |
| `path` | string/null | 已下载时的本地模型路径 |
| `known_models` | object | 所有支持的模型（仓库名称 -> 显示名称） |

## User profile CRUD (v4.197.0+)

用于在 Tools 页面 UI 以 CRUD 管理用户自定义 tagger profile 的 API。所有端点都需要 admin scope。通用错误格式为 `{ok: false, error, code, ...extra}`。请求 body 有 **1MB 硬上限**（`code: profile_too_large`、413）。`id` 必须符合 `^[a-z0-9][a-z0-9_-]{0,63}$` regex。

### POST /api/wd-tagger/profiles

创建新的用户 profile。

**请求**: profile JSON（schema v2、`profile_version: "2"`）。`builtin` 字段会在服务端被强制覆盖为 `false`。

**响应 (200)**:
```json
{
  "ok": true,
  "profile": { "...": "...サニタイズ済 profile JSON..." },
  "origin": "user",
  "overrides_builtin": false
}
```

| 字段 | 说明 |
|---|---|
| `profile` | 已保存的 profile（确保为 `builtin: false`） |
| `origin` | 始终为 `"user"` |
| `overrides_builtin` | 若存在相同 id 的 builtin profile 则为 `true`（advanced 路径） |

**错误**:

| status | code | 条件 |
|---|---|---|
| 400 | `validation_failed` | JSON 不符合 schema v2（`extra.errors=[{path, message}, ...]`） |
| 400 | `invalid_id` | body 的 `id` 不符合 regex |
| 409 | `id_conflict` | 与既有 user profile 的 id 冲突 |
| 413 | `profile_too_large` | body > 1MB |

### GET /api/wd-tagger/profiles/{id}

获取指定 id 的 full schema v2 profile（UI 在编辑 / 复制 / Export 时调用）。

**path**: `id`（必须做 regex 检查）

**响应 (200)**:
{与 POST 同形: profile / origin / overrides_builtin}

**错误**:
- 400 `invalid_id`（path id regex 不匹配）
- 404 `not_found`

### PUT /api/wd-tagger/profiles/{id}

更新已有的用户 profile。

**path**: `id`（必须做 regex 检查）

**请求**: profile JSON。`body.id` 必须与 path id 一致（rename 请在 UI 引导 `Duplicate → Delete`）。

**响应 (200)**: 与 POST 同形。

**错误**:

| status | code | 条件 |
|---|---|---|
| 400 | `id_immutable` | path id 与 body id 不一致 |
| 400 | `invalid_id` | path id 不符合 regex |
| 400 | `validation_failed` | schema 违规 |
| 403 | `builtin_read_only` | path id 为 builtin profile（user 侧无对应文件） |
| 404 | `not_found` | id 未注册 |
| 413 | `profile_too_large` | body > 1MB |

### DELETE /api/wd-tagger/profiles/{id}

删除用户 profile。

**path**: `id`

**响应 (200)**:
```json
{"ok": true, "deleted": true}
```

**错误**:

| status | code | 条件 |
|---|---|---|
| 400 | `invalid_id` | path id 非法 |
| 403 | `builtin_read_only` | 仅有 builtin，且没有 user override |
| 404 | `not_found` | id 未注册 |
| 409 | `in_use` | 该 profile 为 active model（会附带 `extra.active_model_id`）。UI 侧请先通过 `PUT /api/wd-tagger/active-model` 切换 active 后再重试 |

### POST /api/wd-tagger/profiles/{id}/test

dry-run download。会对每个 `files[]` 在 HuggingFace 上做 HEAD，并针对 `required: true` 的项执行按文件的 atomic download（缓存会复用已有路径）。

**path**: `id`

**body**: 不需要

**行为**:
- per-file timeout: 30s
- 总体 timeout: 60s
- redirect: 仅允许 `huggingface.co` / `hf.co` 子域 allowlist，最多 5 hop，userinfo（`user:pass@`）为 SSRFBlocked

**响应 (200, 成功)**:
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
- `downloaded`: 本次下载完成
- `cached`: 本地已存在（仅 HEAD）
- `skipped_optional`: `required: false` 且 404 / HEAD 失败

**错误 (status / code)**:

| status | code | 条件 |
|---|---|---|
| 400 | `invalid_id` / `required_missing` | path id 非法 / required 文件在 HF 为 404 |
| 404 | `not_found` | profile 未注册 |
| 408 | `timeout` | 总体超过 60s |
| 502 | `ssrf_blocked` | redirect 不在 HF allowlist / 含 userinfo / scheme 非 http(s) |
| 502 | `hf_unavailable` | HF 返回 5xx |

错误时 body 形如 `{"ok": false, "code": ..., "error": ..., "files": [...部分结果...], "detail": "..."}`。

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
  builtin?: boolean;                       // 用户来源始终为 false（服务端强制）
}
```

详情请参考 `extensions/builtin_wd_tagger/core_impl/adapters/base.py`（`TaggerProfile`），或 builtin 的参考实现（`extensions/builtin_wd_tagger/core_impl/profiles/*.json`）。
