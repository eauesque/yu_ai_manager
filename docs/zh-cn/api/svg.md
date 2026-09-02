# SVG 光栅化 API

将 SVG 矢量图片转换为 PNG/WebP 位图的 API。
专为 img2img 管线集成设计——返回的 base64 图片数据可直接传入 NovelAI Bridge 或 SD WebUI Bridge。

## GET /api/svg/info

确认 SVG 光栅化功能是否可用。

- **速率限制**: 无 (GET)

### 响应

```json
{
  "available": true,
  "backend": "resvg"
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `available` | bool | 是否可进行光栅化 |
| `backend` | string \| null | 使用中的后端 (`"resvg"` 或 `null`) |

---

## POST /api/svg/rasterize

将 SVG 光栅化为 PNG/WebP 位图。

- **速率限制**: HEAVY

### 请求正文

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file_id` | int | ※1 | 数据库中的 SVG 文件 ID |
| `svg_path` | string | ※1 | SVG 文件的绝对路径 |
| `svg_data` | string | ※1 | 内联 SVG XML 字符串 |
| `width` | int | 否 | 输出宽度 (默认: 1024) |
| `height` | int | 否 | 输出高度 (默认: 1024) |
| `format` | string | 否 | `"png"` 或 `"webp"` (默认: `"png"`) |
| `background` | string | 否 | 背景色 (例: `"#ffffff"`)。未指定则为透明 |

> ※1: 请提供 `file_id`、`svg_path`、`svg_data` 其中之一。

### 请求示例

```json
{
  "file_id": 123,
  "width": 832,
  "height": 1216,
  "format": "png",
  "background": "#ffffff"
}
```

### 响应

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

| 字段 | 类型 | 说明 |
|------|------|------|
| `ok` | bool | 成功标志 |
| `base64` | string | Base64 编码的 PNG/WebP 数据 |
| `width` | int | 实际输出宽度 |
| `height` | int | 实际输出高度 |
| `format` | string | 输出格式 |
| `size_bytes` | int | 二进制大小 (bytes) |

### 错误响应

```json
{
  "ok": false,
  "error": "resvg is not installed (pip install resvg)"
}
```

---

## MCP 集成

通过 Claude Desktop 构建 SVG → img2img 管线：

```
# 步骤 1：光栅化 SVG
svg_rasterize(file_id=123, width=832, height=1216, background="#ffffff")

# 步骤 2：将返回的 base64 传入 img2img
nai_generate(prompt="icon, detailed illustration, ...", image=<base64>, strength=0.7)
```

### MCP 工具

| 工具 | 说明 |
|------|------|
| `svg_info` | 确认光栅化功能是否可用 |
| `svg_rasterize` | SVG → PNG/WebP 光栅化 |

---

## 依赖包

| 包 | 许可证 | 用途 |
|----|--------|------|
| `resvg` | MIT | 基于 Rust 的 SVG 渲染器 (跨平台) |

若 `resvg` 未安装，缩略图会显示占位图，API 会返回 HTTP 501。

```bash
pip install resvg
```
