# Video Analysis API

用于管理视频分析配置和检查状态的 API。控制从视频文件提取关键帧的设置。

## GET /api/video-analysis/config

获取当前的视频分析配置。返回已保存的设置与默认值合并后的结果。

### Parameters

无

### Response

```json
{
  "config": {
    "enabled": true,
    "keyframe_count": 4,
    "strategy": "uniform",
    "scene_threshold": 0.4,
    "store_per_keyframe": false
  }
}
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | boolean | `true` | 是否启用视频分析 |
| `keyframe_count` | int | `4` | 要提取的关键帧数量 (1-16) |
| `strategy` | string | `"uniform"` | 关键帧提取策略。`uniform`（等间距）、`scene`（场景变化检测）、`single`（仅单帧） |
| `scene_threshold` | float | `0.4` | 场景变化检测阈值 (0.0-1.0)。当 `strategy` 为 `scene` 时使用 |
| `store_per_keyframe` | boolean | `false` | 是否单独存储每个关键帧 |

## POST /api/video-analysis/config

保存视频分析配置。仅更新指定的字段；未指定的字段保留现有值。

### Rate Limit

WRITE

### Request

```json
{
  "enabled": true,
  "keyframe_count": 8,
  "strategy": "scene",
  "scene_threshold": 0.3,
  "store_per_keyframe": false
}
```

所有字段均为可选。仅更新指定的字段。

| 参数 | 类型 | 必须 | 限制条件 | 说明 |
|------|------|------|----------|------|
| `enabled` | boolean | 否 | - | 是否启用视频分析 |
| `keyframe_count` | int | 否 | 1-16 | 要提取的关键帧数量 |
| `strategy` | string | 否 | `uniform`、`scene` 或 `single` | 关键帧提取策略 |
| `scene_threshold` | float | 否 | 0.0-1.0 | 场景变化检测阈值 |
| `store_per_keyframe` | boolean | 否 | - | 是否单独存储每个关键帧 |

### Response

保存后返回合并后的配置（格式与 GET 相同）。

```json
{
  "config": {
    "enabled": true,
    "keyframe_count": 8,
    "strategy": "scene",
    "scene_threshold": 0.3,
    "store_per_keyframe": false
  }
}
```

### Errors

| 状态码 | Code | 条件 |
|--------|------|------|
| 400 | `invalid_json` | 请求体不是 JSON 对象 |
| 400 | `invalid_value` | 验证错误（类型错误、值超出范围、无效的策略等） |

## GET /api/video-analysis/status

获取视频分析状态信息。返回 ffmpeg 的可用性、视频文件数量以及已提取关键帧的文件数量。

### Parameters

无

### Response

```json
{
  "ffmpeg": true,
  "video_files": 150,
  "files_with_keyframes": 42
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `ffmpeg` | boolean | 系统上是否可用 ffmpeg |
| `video_files` | int | 数据库中的视频文件总数（不含已软删除的文件）。支持的扩展名：`.mp4`、`.webm`、`.avi`、`.mov`、`.mkv`、`.m4v`、`.ogv` |
| `files_with_keyframes` | int | 已提取关键帧的文件数量 |
