# YU AI Manager

AI 生成图像的元数据管理 WebUI。

## 概述

从 AI 生成图像中提取、搜索和管理嵌入的元数据（提示词、模型、种子等）的 WebUI 工具。

**您可以做什么:**

- 扫描整个文件夹或 ZIP 存档，自动注册图像
- 通过提示词、标签、模型名称、种子值等进行跨域搜索和筛选
- 将喜欢的图像立即发送到 SD / ComfyUI / NovelAI 进行重新生成
- 使用 WD-Tagger 自动标记，使用 Ollama/OpenAI 分析内容
- 从 LAN 上的其他设备（智能手机等）通过二维码访问

**支持的来源**: Stable Diffusion (A1111/Forge)、NovelAI V3/V4、ComfyUI

## 运行环境

- Windows / Linux / macOS

> **无需手动安装。** `start.sh` / `start.bat` 将在项目目录下 bootstrap 所有必需的工具（无需系统写入权限、无需管理员权限）。

## 设置和启动

```bash
git clone https://github.com/eauesque/yu_ai_manager.git
cd yu_ai_manager

# Windows
start.bat

# macOS / Linux
./start.sh
```

首次启动时自动设置:

| 工具 | 获取方式 |
| --- | --- |
| `uv` | 自动下载到 `./bin/uv` |
| Python 3.11+ | `uv` 自动安装 |
| Node.js 22 LTS | 可选 — 确认下载到 `./bin/node/`（约 30 MB） |
| pnpm | 装有 Node.js 后通过 `corepack` 启用 |
| ffmpeg | 可选 — Windows/macOS 确认下载到 `./bin/ffmpeg/`（约 80 MB），Linux 将指导使用发行版的 `apt`/`dnf`/`pacman` 命令 |

设置 `YU_AUTO_INSTALL=1` 可以在非交互环境（如 CI）中跳过提示，实现完全自动安装。ffmpeg 仅用于视频分析、S2T、OCR 等扩展功能，本体启动不需要。

第二次及以后仅当依赖关系或 TypeScript 源代码更新时才重新安装和重新构建。

可以在 `launch-args.txt` 中写入 `--db`、`--port`、`--lan`、`--pin` 等参数来进行永久设置。

## 主要功能

### 扫描和注册
- PNG / WebP / JPEG 元数据自动提取
- ZIP / 7z 存档透明扫描（无需解压）
- 拖放添加文件

### 搜索和浏览
- 提示词、标签、模型名称、种子值的全文搜索
- 正则表达式搜索、复合条件筛选
- pHash 相似图像搜索、CLIP 语义搜索

### 整理和管理
- 收藏夹、星级评分（1-5）、备注（注释）
- 集合（分组）
- 统计仪表板、月度报告、奖杯系统

### 生成工具集成（Bridge）
- 向 SD WebUI / Forge / ComfyUI / NovelAI 立即发送提示词
- 也支持通过剪贴板发送

### AI 辅助
- WD-Tagger 自动标记
- 使用 Ollama / OpenAI 进行图像内容分析
- 语音转文本 (S2T)

### 网络和共享
- LAN 共享模式（通过二维码从智能手机访问）
- MCP 服务器（从 AI 代理操作）
- Fleet 管理（多个实例的统一管理）

### 自定义
- 自定义 UI 和 Extension 系统
- 主题支持（浅色/深色）
- Tauri 桌面应用（无需浏览器启动）

## 多语言支持

English / 日本語 / 繁體中文 / 简体中文 / 한국어

## 文档

- [快速开始](docs/ja/help/user/quickstart.md)
- [用例集](docs/ja/help/user/use-cases.md)
- [API 参考](docs/ja/api/README.md)
- [性能调优](docs/ja/help/user/performance-tuning.md)
- [部署](docs/ja/help/user/deployment.md)
- [Extension 开发](docs/ja/plugin-development/getting-started.md)
- [自定义 UI](docs/ja/custom-ui/README.md)
- [MCP 工具](docs/ja/api/MCP_TOOLS_REFERENCE.md)
- [完整文档列表](docs/ja/README.md)

## 开发和自定义

参考 [DEVELOPMENT.ja.md](DEVELOPMENT.ja.md) ([English](DEVELOPMENT.en.md))

## 不确定时询问 AI

### 无法启动的情况

向 Claude Code Desktop 等 AI 代理打开此项目的文件夹作为工作目录后，请说明如下：

> `start.bat`（或 `start.sh`）启动后停滞。请调查。

> **注**: Claude Code Desktop 需要在开始会话前指定项目文件夹。

### 启动后的问题、设置、使用方法

**步骤 1 — 获取上下文**

打开帮助页面（`/help`），按下 **"复制 AI 上下文"** 按钮。
它使用登录的浏览器会话 fetch `GET /api/ai-context`，并将 JSON 复制到剪贴板（在 http:// LAN 环境中也能工作）。

> **注（如果您有 API 密钥）**: 如果您有 admin 范围的 API 密钥，可以直接使用 `Authorization: Bearer <key>` 标头调用 `GET /api/ai-context`。

**步骤 2 — 提交给 AI**

将复制的 JSON 粘贴到 AI 聊天中，然后写下您的问题：

> 〔粘贴的 JSON〕
> 根据以上内容，请解决 〔问题描述〕。

`/api/ai-context` 包含当前版本、启用的功能、设置提示、API 列表和 CSRF 规则，包含 AI 准确支持所需的所有信息。

## 常见问题

[docs/ja/FAQ.md](docs/ja/FAQ.md) ([English](docs/en/FAQ.md))

## 错误报告

[GitHub Issues](https://github.com/eauesque/yu_ai_manager/issues)

## 许可证

MIT License — [LICENSE](LICENSE) / [口语翻译](docs/ja/LICENSE.md) ([English](docs/en/LICENSE.md))
