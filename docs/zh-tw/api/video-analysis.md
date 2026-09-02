# Video Analysis API

用於管理影片分析設定和檢查狀態的 API。控制從影片檔案擷取關鍵影格的設定。

## GET /api/video-analysis/config

取得目前的影片分析設定。回傳已儲存的設定與預設值合併後的結果。

### Parameters

無

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

| 欄位 | 型別 | 預設值 | 說明 |
|------|------|--------|------|
| `enabled` | boolean | `true` | 是否啟用影片分析 |
| `keyframe_count` | int | `4` | 要擷取的關鍵影格數量 (1-16) |
| `strategy` | string | `"uniform"` | 關鍵影格擷取策略。`uniform`（等間距）、`scene`（場景變換偵測）、`single`（僅單一影格） |
| `scene_threshold` | float | `0.4` | 場景變換偵測閾值 (0.0-1.0)。當 `strategy` 為 `scene` 時使用 |
| `store_per_keyframe` | boolean | `false` | 是否個別儲存每個關鍵影格 |

## POST /api/video-analysis/config

儲存影片分析設定。僅更新指定的欄位；未指定的欄位保留現有值。

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

所有欄位皆為選填。僅更新指定的欄位。

| 參數 | 型別 | 必須 | 限制條件 | 說明 |
|------|------|------|----------|------|
| `enabled` | boolean | 否 | - | 是否啟用影片分析 |
| `keyframe_count` | int | 否 | 1-16 | 要擷取的關鍵影格數量 |
| `strategy` | string | 否 | `uniform`、`scene` 或 `single` | 關鍵影格擷取策略 |
| `scene_threshold` | float | 否 | 0.0-1.0 | 場景變換偵測閾值 |
| `store_per_keyframe` | boolean | 否 | - | 是否個別儲存每個關鍵影格 |

### Response

儲存後回傳合併後的設定（格式與 GET 相同）。

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

| 狀態碼 | Code | 條件 |
|--------|------|------|
| 400 | `invalid_json` | 請求主體不是 JSON 物件 |
| 400 | `invalid_value` | 驗證錯誤（型別錯誤、值超出範圍、無效的策略等） |

## GET /api/video-analysis/status

取得影片分析狀態資訊。回傳 ffmpeg 的可用性、影片檔案數量以及已擷取關鍵影格的檔案數量。

### Parameters

無

### Response

```json
{
  "ffmpeg": true,
  "video_files": 150,
  "files_with_keyframes": 42
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `ffmpeg` | boolean | 系統上是否可使用 ffmpeg |
| `video_files` | int | 資料庫中的影片檔案總數（不含已軟刪除的檔案）。支援的副檔名：`.mp4`、`.webm`、`.avi`、`.mov`、`.mkv`、`.m4v`、`.ogv` |
| `files_with_keyframes` | int | 已擷取關鍵影格的檔案數量 |
