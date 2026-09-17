# Video Analysis API

APIs for managing video analysis configuration and checking status. Controls the settings for extracting keyframes from video files.

## GET /api/video-analysis/config

Get the current video analysis configuration. Returns saved settings merged with default values.

### Parameters

None

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

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | boolean | `true` | Whether video analysis is enabled |
| `keyframe_count` | int | `4` | Number of keyframes to extract (1-16) |
| `strategy` | string | `"uniform"` | Keyframe extraction strategy. `uniform` (evenly spaced), `scene` (scene change detection), `single` (single frame only) |
| `scene_threshold` | float | `0.4` | Scene change detection threshold (0.0-1.0). Used when `strategy` is `scene` |
| `store_per_keyframe` | boolean | `false` | Whether to store each keyframe individually |

## POST /api/video-analysis/config

Save video analysis configuration. Only specified fields are updated; omitted fields retain their existing values.

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

All fields are optional. Only specified fields are updated.

| Parameter | Type | Required | Constraints | Description |
|-----------|------|----------|-------------|-------------|
| `enabled` | boolean | No | - | Whether video analysis is enabled |
| `keyframe_count` | int | No | 1-16 | Number of keyframes to extract |
| `strategy` | string | No | `uniform`, `scene`, or `single` | Keyframe extraction strategy |
| `scene_threshold` | float | No | 0.0-1.0 | Scene change detection threshold |
| `store_per_keyframe` | boolean | No | - | Whether to store each keyframe individually |

### Response

Returns the merged configuration after saving (same format as GET).

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

| Status | Code | Condition |
|--------|------|-----------|
| 400 | `invalid_json` | Request body is not a JSON object |
| 400 | `invalid_value` | Validation error (wrong type, out-of-range value, invalid strategy, etc.) |

## GET /api/video-analysis/status

Get video analysis status information. Returns ffmpeg availability, video file count, and number of files with extracted keyframes.

### Parameters

None

### Response

```json
{
  "ffmpeg": true,
  "video_files": 150,
  "files_with_keyframes": 42
}
```

| Field | Type | Description |
|-------|------|-------------|
| `ffmpeg` | boolean | Whether ffmpeg is available on the system |
| `video_files` | int | Total number of video files in the database (excluding soft-deleted). Supported extensions: `.mp4`, `.webm`, `.avi`, `.mov`, `.mkv`, `.m4v`, `.ogv` |
| `files_with_keyframes` | int | Number of files that have extracted keyframes |
