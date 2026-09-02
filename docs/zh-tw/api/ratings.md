# Ratings API

用於管理檔案評分（1–5 星評分）的 API：設定、取得與統計。

## POST /api/ratings/set

為檔案設定評分。指定 `rating=0` 可清除評分。

**速率限制**: WRITE

### 請求

```json
{
  "file_id": 42,
  "rating": 5
}
```

| 參數 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `file_id` | int | 是 | 檔案 ID（正整數） |
| `rating` | int | 是 | 評分值（0–5）。0 表示清除評分 |

### 回應

```json
{
  "file_id": 42,
  "rating": 5
}
```

## POST /api/ratings/batch-set

一次為多個檔案設定評分。

**速率限制**: WRITE

### 請求

```json
{
  "items": [
    { "file_id": 1, "rating": 5 },
    { "file_id": 2, "rating": 3 }
  ]
}
```

| 參數 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `items` | array | 是 | 評分設定清單（最多 500 筆） |
| `items[].file_id` | int | 是 | 檔案 ID（正整數） |
| `items[].rating` | int | 是 | 評分值（0–5） |

### 回應

```json
{
  "total": 2,
  "succeeded": 2,
  "failed": 0,
  "errors": []
}
```

## GET /api/ratings/get

取得檔案的評分。未評分的檔案會回傳 `rating: 0`。

### 參數

| 參數 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `file_id` | int | 是 | 檔案 ID（查詢參數） |

### 回應

```json
{
  "file_id": 42,
  "rating": 5
}
```

> **注意**：未評分的檔案會回傳 `rating: 0`。

## POST /api/ratings/batch

一次取得多個檔案的評分。

### 請求

```json
{
  "file_ids": [1, 2, 3]
}
```

| 參數 | 類型 | 必填 | 說明 |
|------|------|------|------|
| `file_ids` | array | 是 | 檔案 ID 清單 |

### 回應

```json
{
  "ratings": {
    "1": 5,
    "3": 4
  }
}
```

> **注意**：僅已評分的檔案會出現在映射中。未評分的檔案不會包含在回應中。

## GET /api/ratings/stats

取得所有檔案的評分統計資訊。

### 參數

無。

### 回應

```json
{
  "total_rated": 1234,
  "distribution": {
    "1": 50,
    "2": 100,
    "3": 300,
    "4": 500,
    "5": 284
  }
}
```

| 欄位 | 類型 | 說明 |
|------|------|------|
| `total_rated` | int | 已評分檔案的總數 |
| `distribution` | object | 各評分值（1–5）的檔案數量 |
