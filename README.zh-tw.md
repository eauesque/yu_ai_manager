# YU AI Manager

AI 生成影像的詮釋資料管理 WebUI。

## 概述

AI 生成影像中嵌入的詮釋資料（提示詞、模型、種子值等）的抽取、搜尋及管理 WebUI 工具。

**您可以做到以下功能:**

- 掃描整個資料夾或 ZIP 壓縮檔並自動登記影像
- 按提示詞、標籤、模型名稱、種子值等進行跨域搜尋與篩選
- 將喜愛的影像直接傳送到 SD / ComfyUI / NovelAI 進行重新生成
- 使用 WD-Tagger 進行自動標籤，使用 Ollama/OpenAI 進行內容分析
- 從區域網路上的其他設備（智慧型手機等）透過 QR 碼進行存取

**支援的來源**: Stable Diffusion (A1111/Forge)、NovelAI V3/V4、ComfyUI

## 執行環境

- Windows / Linux / macOS

> **不需要手動安裝。** `start.sh` / `start.bat` 會在專案下自動啟動所有必要工具（無需系統寫入權限或管理員權限）。

## 設定及啟動

```bash
git clone https://github.com/eauesque/yu_ai_manager.git
cd yu_ai_manager

# Windows
start.bat

# macOS / Linux
./start.sh
```

初次啟動時的自動設定:

| 工具 | 取得方式 |
| --- | --- |
| `uv` | 自動下載至 `./bin/uv` |
| Python 3.11+ | `uv` 自動安裝 |
| Node.js 22 LTS | 選擇性 — 確認下載至 `./bin/node/`（約 30 MB） |
| pnpm | 一旦裝有 Node.js 就透過 `corepack` 啟動 |
| ffmpeg | 選擇性 — Windows/macOS 確認下載至 `./bin/ffmpeg/`（約 80 MB），Linux 引導至 distro 的 `apt`/`dnf`/`pacman` 指令 |

設定 `YU_AUTO_INSTALL=1` 可在非互動環境（CI 等）中略過提示進行完全自動安裝。ffmpeg 是影片分析、S2T、OCR 等擴充功能專用，本體啟動不需要。

第二次以後僅在相依性或 TypeScript 原始碼更新時重新安裝及重新構建。

在 `launch-args.txt` 中記載 `--db`、`--port`、`--lan`、`--pin` 等可進行持久性設定。

## 主要功能

### 掃描·登記
- PNG / WebP / JPEG 詮釋資料自動提取
- 無需展開就透過掃描 ZIP / 7z 壓縮檔
- 透過拖放新增檔案

### 搜尋·瀏覽
- 提示詞、標籤、模型名稱、種子值的全文搜尋
- 規則運算式搜尋、複合條件篩選
- pHash 相似影像搜尋、CLIP 語意搜尋

### 整理·管理
- 最愛、星級評分（1〜5）、備註（註解）
- 集合（群組分類）
- 統計儀表板、月度報告、獎盃系統

### 生成工具連動（Bridge）
- 直接將提示詞傳送至 SD WebUI / Forge / ComfyUI / NovelAI
- 也支援透過剪貼簿傳送

### AI 協助
- 透過 WD-Tagger 進行自動標籤
- 使用 Ollama / OpenAI 進行影像內容分析
- 語音文字轉換（S2T）

### 網路·分享
- 區域網路共享模式（透過 QR 碼從智慧型手機存取）
- MCP 伺服器（從 AI 代理操作）
- Fleet 管理（多個實例的統一管理）

### 自訂
- 自訂 UI、擴充功能系統
- 主題支援（淺色 / 深色）
- Tauri 桌面應用程式（無需瀏覽器即可啟動）

## 多言語支援

English / 日本語 / 繁體中文 / 简体中文 / 한국어

## 文件

- [快速開始](docs/zh-tw/help/user/quickstart.md)
- [使用案例集](docs/zh-tw/help/user/use-cases.md)
- [API 參考](docs/zh-tw/api/README.md)
- [效能調整](docs/zh-tw/help/user/performance-tuning.md)
- [部署](docs/zh-tw/help/user/deployment.md)
- [擴充功能開發](docs/zh-tw/plugin-development/getting-started.md)
- [自訂 UI](docs/zh-tw/custom-ui/README.md)
- [MCP 工具](docs/zh-tw/api/MCP_TOOLS_REFERENCE.md)
- [完整文件清單](docs/zh-tw/README.md)

## 開發·自訂

參考 [DEVELOPMENT.zh-tw.md](DEVELOPMENT.zh-tw.md) ([English](DEVELOPMENT.en.md))

## 遇到問題時向 AI 提問

### 無法啟動的情況

向 Claude Code Desktop 等 AI 代理，將此專案的資料夾開啟為工作目錄，如下所述:

> `start.bat`（或 `start.sh`）啟動後停止。請進行調查。

> **補充**: 在 Claude Code Desktop 中，需要在開始對話前指定專案資料夾。

### 啟動後的問題、設定、使用方法

**步驟 1 — 取得上下文**

開啟說明頁面（`/help`），按下**「複製 AI 上下文」**按鈕。
使用已登入的瀏覽器工作階段 `GET /api/ai-context` 並取得 JSON 至剪貼簿（在 http:// 區域網路環境中也可運作）。

> **補充（若您有 API 金鑰）**: 若您有管理員範圍的 API 金鑰，可直接在 `Authorization: Bearer <key>` 標題中呼叫 `GET /api/ai-context`。

**步驟 2 — 將上下文傳送給 AI**

將複製的 JSON 貼到 AI 聊天中，然後按照問題描述進行操作:

> 〔貼上的 JSON〕
> 基於此，請解決〔問題描述〕。

`/api/ai-context` 包含目前版本、有效功能、設定提示、API 清單及 CSRF 規則，包含 AI 精確協助所需的所有資訊。

## 常見問題

[docs/zh-tw/FAQ.md](docs/zh-tw/FAQ.md) ([English](docs/en/FAQ.md))

## 錯誤報告

[GitHub Issues](https://github.com/eauesque/yu_ai_manager/issues)

## 授權

MIT License — [LICENSE](LICENSE) / [中文版](docs/zh-tw/LICENSE.md) ([English](docs/en/LICENSE.md))
