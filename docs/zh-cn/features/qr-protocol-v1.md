# YU QR Protocol v1 — 统一载荷规格

**版本：** 1.0
**日期：** 2026-02-23
**目标应用：** YU AI Manager (TagDB)

---

## 概述

YU AI Manager 支持通过二维码进行提示词共享和错误诊断。
本文档提供二维码载荷格式的统一规格。

### 使用的库

| 用途 | 库 | 版本 |
|------|-----------|-----------|
| 二维码生成 | QRCode.js | 1.0.0 |
| 二维码读取 | jsQR | 1.4.0 |

### 二维码容量限制

- 最大字符数：**2,953**（纠错级别 M）
- 超过 2,500 字符：压缩元 JSON 后重试
- 超过 2,953 字符：错误（`qr.info.too_long`）

---

## 载荷类型 1 — 提示词共享

### 来源

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

### 字段定义

| 键 | 类型 | 必需 | 说明 | 限制 |
|------|-----|------|------|------|
| `v` | string | ✅ | 协议版本。当前为 `"1.0"` | — |
| `t` | string | ✅ | 载荷类型。当前始终为 `"prompt"` | — |
| `p` | string | ✅ | 正面提示词 | 2,000 字符 |
| `n` | string | ✅ | 负面提示词 | 1,000 字符 |
| `src` | string | ✅ | 发行者标识。当前始终为 `"TagDB"` | — |
| `m` | string | — | 模型名称 | — |
| `s` | string | — | 种子值 | — |
| `st` | string | — | 步数 | — |
| `cfg` | string | — | CFG 缩放值 | — |
| `sa` | string | — | 采样器名称 | — |
| `sz` | string | — | 图片尺寸，格式为 `"WxH"` | — |

---

## 二维码模式 — 4 种类型

### `positive` 模式

```
qrText = shareData.p
```

- 内容：仅正面提示词文本
- 用例：直接文本形式的提示词共享

### `negative` 模式

```
qrText = shareData.n
```

- 内容：仅负面提示词文本

### `meta` 模式

```
qrText = JSON.stringify(shareData, null, 0)
```

- 内容：完整的 Prompt Share JSON 载荷（压缩格式）
- 当结果超过 2,500 字符时回退到格式化的 `JSON.stringify`

### `url` 模式

```
encoded = btoa(unescape(encodeURIComponent(JSON.stringify(shareData))))
qrText  = "{origin}/share?data={encoded}"
```

- 内容：YU AI Manager 共享页面的 URL
- 在 localhost（`localhost` / `127.0.0.1`）上禁用

---

## 载荷类型 2 — 错误诊断

### 来源

- 在 HTTP 错误时生成 -> `_render_error_page()`
- `core/web/app_factory_handlers.py`

### JSON Schema

```json
{
  "s": "<HTTP status code>",
  "p": "<request path>",
  "v": "<APP_VERSION>"
}
```

### 字段定义

| 键 | 类型 | 说明 | 限制 |
|------|-----|------|------|
| `s` | string | HTTP 状态码（`"404"`、`"500"` 等） | — |
| `p` | string | 请求路径 | 80 字符 |
| `v` | string | 应用版本（来自 `APP_VERSION` 文件） | — |

---

## URL 共享解码步骤

共享页面上的解码（`/share?data=...`）：

```javascript
const encoded = new URL(location).searchParams.get('data');
const json    = decodeURIComponent(escape(atob(encoded)));
const data    = JSON.parse(json);
```

---

## 二维码生成参数

```javascript
new QRCode(container, {
  text:         qrText,
  width:        200,   // 错误页面为 180
  height:       200,   // 错误页面为 180
  colorDark:    '#000000',
  colorLight:   '#ffffff',
  correctLevel: QRCode.CorrectLevel.M,  // 15% 纠错
});
```

---

## 未来扩展（v1.x）

| 功能 | 状态 | 备注 |
|------|------|------|
| 合集二维码导出（多张图片） | 未实现 | 计划作为载荷类型 3 |
| `t: "collection"` 类型 | 未定义 | 文件 ID 列表 + 合集名称 |
| 压缩（gzip + Base64） | 未实现 | 超过 2,953 字符的提示词的替代方案 |

---

## 实现文件

| 文件 | 职责 |
|----------|------|
| `routes/share.py` | 共享 API Blueprint |
| `routes/share_ops/payload_build.py` | 载荷生成 |
| `routes/share_ops/prompt_extract.py` | 提示词数据提取 |
| `core/web/app_factory_handlers.py` | 错误二维码数据生成 |
| `static/js/runtime/tools/runtime-tools-qr-core.js` | 二维码构建和渲染 |
| `static/js/runtime/tools/runtime-tools-qr.js` | 二维码 UI 处理器 |
| `static/js/share/share-qr.js` | 二维码图片解码 |
| `static/js/share/share-page.js` | 共享页面显示 |
| `static/vendor/qrcode.min.js` | QRCode.js 库 |
| `static/vendor/jsQR.min.js` | jsQR 库 |
