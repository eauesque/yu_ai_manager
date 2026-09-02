# YU QR Protocol v1 — 統一酬載規格

**版本：** 1.0
**日期：** 2026-02-23
**目標應用：** YU AI Manager (TagDB)

---

## 概述

YU AI Manager 支援透過 QR Code 進行提示詞共享和錯誤診斷。
本文件提供 QR Code 酬載格式的統一規格。

### 使用的函式庫

| 用途 | 函式庫 | 版本 |
|------|-----------|-----------|
| QR Code 產生 | QRCode.js | 1.0.0 |
| QR Code 讀取 | jsQR | 1.4.0 |

### QR Code 容量限制

- 最大字元數：**2,953**（糾錯等級 M）
- 超過 2,500 字元：壓縮 meta JSON 後重試
- 超過 2,953 字元：錯誤（`qr.info.too_long`）

---

## 酬載類型 1 — 提示詞共享

### 來源

- `GET /api/share/<file_id>` -> Python `build_share_data_payload()`
- `routes/share_ops/payload_build.py`

### JSON Schema

```json
{
  "v":   "1.0",
  "t":   "prompt",
  "p":   "<positive prompt>",
  "n":   "<negative prompt>",
  "src": "TagDB",
  "m":   "<model name>",
  "s":   "<seed>",
  "st":  "<steps>",
  "cfg": "<CFG scale>",
  "sa":  "<sampler>",
  "sz":  "<WxH>"
}
```

### 欄位定義

| 鍵 | 類型 | 必填 | 說明 | 限制 |
|------|-----|------|------|------|
| `v` | string | ✅ | 協定版本。目前為 `"1.0"` | — |
| `t` | string | ✅ | 酬載類型。目前固定為 `"prompt"` | — |
| `p` | string | ✅ | 正面提示詞 | 2,000 字元 |
| `n` | string | ✅ | 負面提示詞 | 1,000 字元 |
| `src` | string | ✅ | 發行者識別碼。目前固定為 `"TagDB"` | — |
| `m` | string | — | 模型名稱 | — |
| `s` | string | — | 種子值 | — |
| `st` | string | — | 步數 | — |
| `cfg` | string | — | CFG 比例 | — |
| `sa` | string | — | 採樣器名稱 | — |
| `sz` | string | — | 圖片尺寸，`"WxH"` 格式 | — |

---

## QR Code 模式 — 4 種類型

### `positive` 模式

```
qrText = shareData.p
```

- 內容：僅正面提示詞文字
- 用途：直接文字共享提示詞

### `negative` 模式

```
qrText = shareData.n
```

- 內容：僅負面提示詞文字

### `meta` 模式

```
qrText = JSON.stringify(shareData, null, 0)
```

- 內容：完整的 Prompt Share JSON 酬載（壓縮後）
- 結果超過 2,500 字元時，回退為美化列印的 `JSON.stringify`

### `url` 模式

```
encoded = btoa(unescape(encodeURIComponent(JSON.stringify(shareData))))
qrText  = "{origin}/share?data={encoded}"
```

- 內容：YU AI Manager 共享頁面的 URL
- 在 localhost（`localhost` / `127.0.0.1`）上停用

---

## 酬載類型 2 — 錯誤診斷

### 來源

- 在 HTTP 錯誤時產生 -> `_render_error_page()`
- `core/web/app_factory_handlers.py`

### JSON Schema

```json
{
  "s": "<HTTP status code>",
  "p": "<request path>",
  "v": "<APP_VERSION>"
}
```

### 欄位定義

| 鍵 | 類型 | 說明 | 限制 |
|------|-----|------|------|
| `s` | string | HTTP 狀態碼（`"404"`、`"500"` 等） | — |
| `p` | string | 請求路徑 | 80 字元 |
| `v` | string | 應用程式版本（來自 `APP_VERSION` 檔案） | — |

---

## URL 共享解碼流程

在共享頁面（`/share?data=...`）上的解碼：

```javascript
const encoded = new URL(location).searchParams.get('data');
const json    = decodeURIComponent(escape(atob(encoded)));
const data    = JSON.parse(json);
```

---

## QR Code 產生參數

```javascript
new QRCode(container, {
  text:         qrText,
  width:        200,   // 180 on error pages
  height:       200,   // 180 on error pages
  colorDark:    '#000000',
  colorLight:   '#ffffff',
  correctLevel: QRCode.CorrectLevel.M,  // 15% error correction
});
```

---

## 未來擴充（v1.x）

| 功能 | 狀態 | 備註 |
|------|------|------|
| 收藏集 QR 匯出（多張圖片） | 未實作 | 計畫作為酬載類型 3 |
| `t: "collection"` 類型 | 未定義 | 檔案 ID 清單 + 收藏集名稱 |
| 壓縮（gzip + Base64） | 未實作 | 超過 2,953 字元的提示詞替代方案 |

---

## 實作檔案

| 檔案 | 職責 |
|----------|------|
| `routes/share.py` | 共享 API Blueprint |
| `routes/share_ops/payload_build.py` | 酬載產生 |
| `routes/share_ops/prompt_extract.py` | 提示詞資料擷取 |
| `core/web/app_factory_handlers.py` | 錯誤 QR Code 資料產生 |
| `static/js/runtime/tools/runtime-tools-qr-core.js` | QR Code 建立與渲染 |
| `static/js/runtime/tools/runtime-tools-qr.js` | QR Code UI 處理器 |
| `static/js/share/share-qr.js` | QR Code 圖片解碼 |
| `static/js/share/share-page.js` | 共享頁面顯示 |
| `static/vendor/qrcode.min.js` | QRCode.js 函式庫 |
| `static/vendor/jsQR.min.js` | jsQR 函式庫 |
