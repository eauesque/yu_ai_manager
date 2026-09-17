# 拖放文件注册

将图片/视频文件拖放到主媒体库页面（`/`）即可保存到配置的 **Drop Inbox**
目录并自动注册到媒体库。使用常规扫描路径（`scan_one`），因此元数据提取、
缩略图生成、标签等处理都会照常执行。

## 行为

1. 在主页面打开状态下，从文件管理器或其他浏览器拖动文件
2. 窗口上会显示覆盖层并显示目标（Drop Inbox）路径
3. 放下后，每个文件会被复制到 Drop Inbox 并注册到媒体库
4. Toast 会显示成功与失败数量

## Drop Inbox 的决定逻辑

Drop Inbox 以以下优先顺序决定：

1. `config.json` 的 `drop_inbox_dir`（明确指定）
2. 未设置时：直接使用第一个已启用的扫描根目录

**限制**：`drop_inbox_dir` 必须位于 `scan_roots` 的某个条目之下。外部目录
会以 HTTP 400 拒绝。这是为了维持"扫描根目录 = 媒体库文件的单一事实来源"
的不变条件。

## 配置示例

```json
{
  "scan_roots": [
    { "path": "D:/Pictures/AI", "enabled": true, "recursive": true }
  ],
  "drop_inbox_dir": "D:/Pictures/AI/inbox"
}
```

若 `drop_inbox_dir` 不存在则会自动创建（父目录仍需在 `scan_roots` 之下）。

## 文件名冲突处理

若 inbox 中已有同名文件，会自动添加 `_1`、`_2` 等后缀保存。绝不覆盖现有文件。

## 允许的扩展名

| 类别 | 扩展名 |
|---|---|
| 图片 | `.png` `.jpg` `.jpeg` `.webp` `.gif` `.bmp` `.tiff` `.tif` `.svg` |
| 视频 | `.mp4` `.webm` `.mov` `.avi` `.mkv` `.m4v` |

压缩包（`.zip` / `.7z` / `.rar`）**不支持** 拖放。请将压缩包直接放入扫描
根目录，然后执行常规扫描。

## 限制

- 单个请求的总大小上限为 `MAX_CONTENT_LENGTH`（默认 **100 MB**）
- 含路径穿越（`..`）的文件名会被拒绝
- 目前不支持整个目录的拖放（仅支持单个文件）

## HTTP API

### `POST /api/dnd-upload`

以 multipart 接收多个文件，保存到 Drop Inbox 并注册到媒体库。

### `GET /api/dnd-inbox`

返回当前解析的 Drop Inbox 信息，供 UI 覆盖层显示。

### `POST /api/files/register-path`

以路径指定方式注册已在磁盘上的文件（无需上传）。路径必须在 `scan_roots`
之下。MCP 工具 `register_file` 也使用此 API。

## MCP 工具

| 工具 | 说明 |
|---|---|
| `register_file(path)` | 以绝对路径将文件注册到媒体库 |
| `drop_inbox_info()` | 获取当前解析的 Drop Inbox 目录 |
