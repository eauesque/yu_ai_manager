# SVG 光柵化 API

將 SVG 向量圖片轉換為 PNG/WebP 點陣圖的 API。
專為 img2img 管線整合設計——回傳的 base64 圖片資料可直接傳入 NovelAI Bridge 或 SD WebUI Bridge。

## GET /api/svg/info

確認 SVG 光柵化功能是否可用。

- **速率限制**: 無 (GET)

### 回應

```json
{
  "available": true,
  "backend": "resvg"
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `available` | bool | 是否可進行光柵化 |
| `backend` | string \| null | 使用中的後端 (`"resvg"` 或 `null`) |

---

## POST /api/svg/rasterize

將 SVG 光柵化為 PNG/WebP 點陣圖。

- **速率限制**: HEAVY

### 請求本文

| 參數 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `file_id` | int | ※1 | 資料庫中的 SVG 檔案 ID |
| `svg_path` | string | ※1 | SVG 檔案的絕對路徑 |
| `svg_data` | string | ※1 | 內嵌 SVG XML 字串 |
| `width` | int | 否 | 輸出寬度 (預設: 1024) |
| `height` | int | 否 | 輸出高度 (預設: 1024) |
| `format` | string | 否 | `"png"` 或 `"webp"` (預設: `"png"`) |
| `background` | string | 否 | 背景色 (例: `"#ffffff"`)。未指定則為透明 |

> ※1: 請提供 `file_id`、`svg_path`、`svg_data` 其中之一。

### 請求範例

```json
{
  "file_id": 123,
  "width": 832,
  "height": 1216,
  "format": "png",
  "background": "#ffffff"
}
```

### 回應

```json
{
  "ok": true,
  "base64": "iVBORw0KGgo...",
  "width": 832,
  "height": 1216,
  "format": "png",
  "size_bytes": 45678
}
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `ok` | bool | 成功旗標 |
| `base64` | string | Base64 編碼的 PNG/WebP 資料 |
| `width` | int | 實際輸出寬度 |
| `height` | int | 實際輸出高度 |
| `format` | string | 輸出格式 |
| `size_bytes` | int | 二進位大小 (bytes) |

### 錯誤回應

```json
{
  "ok": false,
  "error": "resvg is not installed (pip install resvg)"
}
```

---

## MCP 整合

透過 Claude Desktop 建立 SVG → img2img 管線：

```
# 步驟 1：光柵化 SVG
svg_rasterize(file_id=123, width=832, height=1216, background="#ffffff")

# 步驟 2：將回傳的 base64 傳入 img2img
nai_generate(prompt="icon, detailed illustration, ...", image=<base64>, strength=0.7)
```

### MCP 工具

| 工具 | 說明 |
|------|------|
| `svg_info` | 確認光柵化功能是否可用 |
| `svg_rasterize` | SVG → PNG/WebP 光柵化 |

---

## 依賴套件

| 套件 | 授權 | 用途 |
|------|------|------|
| `resvg` | MIT | Rust 基礎 SVG 渲染器 (跨平台) |

若 `resvg` 未安裝，縮圖會顯示佔位圖，API 會回傳 HTTP 501。

```bash
pip install resvg
```
