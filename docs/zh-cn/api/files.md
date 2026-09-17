# Files API

用于获取文件详情、缩略图和原始媒体的 API。

## GET /api/file/<id>

获取文件的详细元数据。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `id` | int | 文件 ID（路径参数） |

### 响应

```json
{
  "id": 42,
  "path": "/images/output/00042.png",
  "filename": "00042.png",
  "size": 1234567,
  "mtime": 1709500000,
  "width": 1024,
  "height": 1536,
  "meta_type": "a1111_png",
  "model_name": "animagine-xl-3.1",
  "positive": "1girl, landscape",
  "negative": "low quality",
  "steps": 28,
  "sampler": "Euler a",
  "cfg_scale": 7.0,
  "seed": 1234567890,
  "rating": 4,
  "is_favorite": true,
  "tags": ["landscape"],
  "collections": [1, 3],
  "hash_md5": "abc123...",
  "hash_phash": "def456...",
  "analysis": { "description": "A scenic landscape..." }
}
```

## GET /api/thumbnail/<id>

缩略图（WebP）。支持 ETag 缓存。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `id` | int | 文件 ID |
| `size` | int | 缩略图尺寸（默认 300） |

### 响应

- Content-Type: `image/webp`
- ETag / If-None-Match 支持（304 Not Modified）
- 缓存：24 小时

## GET /api/original/<id>

流式传输原始文件。也支持 ZIP 归档内的文件。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `id` | int | 文件 ID |

### 响应

- Content-Type：文件的 MIME 类型
- Content-Disposition: `inline`
- 支持 Range 请求（用于视频跳转）

## POST /api/convert

提示词格式转换（A1111 <-> NAI）。

### 请求

```json
{
  "prompt": "1girl, (masterpiece:1.2)",
  "direction": "a1111_to_nai"
}
```

### 响应

```json
{
  "converted": "1girl, {{masterpiece}}",
  "direction": "a1111_to_nai"
}
```

## GET /api/container-thumb-ids

容器（文件夹/ZIP）的缩略图 ID 列表，排除已缓存的条目。

### 参数

| 参数 | 类型 | 说明 |
|-----------|------|-------------|
| `keys` | string | 容器键（逗号分隔） |
