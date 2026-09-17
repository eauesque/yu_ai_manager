# 自訂 UI 開發指南

本指南介紹了可以完全替換 YU AI Manager 前端的自訂 UI 系統。

## 目錄

- [概述](#概述)
- [架構](#架構)
- [快速開始](quickstart.md) -- 建立一個最小的自訂 UI
- [設計指南](design-guide.md) -- CSS 設計、主題、響應式佈局、元件
- [範本指南](templates.md) -- Jinja2 模式、i18n、頁面結構
- [進階功能](advanced.md) -- SSE 即時更新、批次操作、安全性
- [API 參考](api-reference.md) -- 完整 API 文件連結

## 概述

YU AI Manager 將後端 API 與前端完全分離。將前端替換為自訂實作非常簡單。只需將自訂 UI 放置在 `ui/<name>/` 目錄中即可啟用。

### 功能

- **完整 UI 替換**：將搜尋、統計、設定等所有頁面替換為您自己的設計
- **主題自訂**：僅覆寫 CSS 變數即可變更配色方案
- **部分替換**：僅自訂所需的頁面，其餘回退到預設 UI
- **AI 生成 UI**：將 API 文件交給 Claude 或 ChatGPT，讓它自動生成 UI

### 架構

```
yu_ai_manager/
├── ui/
│   ├── default/              # 參考 UI（內建）
│   │   ├── manifest.json     # UI 中繼資料（必要）
│   │   ├── templates/        # Jinja2 HTML 範本
│   │   │   ├── index.html    # 主搜尋頁面
│   │   │   ├── stats.html    # 統計儀表板
│   │   │   ├── tools.html    # 工具頁面
│   │   │   ├── settings.html # 設定頁面
│   │   │   ├── story.html    # Your Story 頁面
│   │   │   ├── inspect.html  # 中繼資料檢視器
│   │   │   └── _nav.html     # 共用導覽列（include）
│   │   └── static/           # CSS、JS、圖片
│   │       ├── css/          # 樣式表
│   │       ├── dist/         # TypeScript 建置輸出
│   │       └── favicon.svg   # 網站圖示
│   ├── custom/               # 自訂 UI（gitignored，自動偵測）
│   │   ├── manifest.json
│   │   ├── templates/
│   │   └── static/
│   └── my-theme/             # 其他 UI（任意名稱）
│       ├── manifest.json
│       └── ...
├── routes/                   # 伺服器端 API 路由
│   ├── pages.py              # 頁面路由定義
│   └── ...                   # 各種 API 端點
└── docs/api/                 # API 文件
```

### UI 解析順序

伺服器在啟動時按以下優先順序決定使用哪個 UI：

| 優先順序 | 條件 | 行為 |
|----------|------|------|
| 1 | `config.json` 包含 `"ui": "my-theme"` | 使用指定的 `ui/my-theme/` |
| 2 | `ui/custom/` 有有效的 `manifest.json` | 自動偵測並使用 `ui/custom/` |
| 3 | 以上均不符合 | 回退到 `ui/default/` |

### manifest.json

每個自訂 UI 都需要一個 `manifest.json`：

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "My custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

| 欄位 | 必要 | 說明 |
|------|------|------|
| `name` | 是 | UI 識別碼（建議與目錄名稱一致） |
| `version` | 是 | 語意化版本 |
| `description` | 否 | UI 說明 |
| `author` | 否 | 作者名稱 |
| `api_version` | 否 | 支援的 API 版本（`"1"`） |
| `type` | 否 | `"full"`（預設）或 `"theme"` |

### 靜態檔案服務

自訂 UI 中的 `static/` 目錄對應到 Flask `/static/` URL：

```
ui/custom/static/style.css  →  /static/style.css
ui/custom/static/js/app.js  →  /static/js/app.js
ui/custom/static/img/logo.png  →  /static/img/logo.png
```

在 HTML 中參照：
```html
<link rel="stylesheet" href="/static/style.css">
<script src="/static/js/app.js"></script>
<img src="/static/img/logo.png">
```

### UI 管理 API

您可以透過設定頁面的「UI」標籤頁或 API 來管理 UI：

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/ui/list` | 列出已安裝的 UI |
| POST | `/api/ui/switch` | 切換使用中的 UI（需要重新啟動） |
| POST | `/api/ui/install` | 從 URL 安裝 UI（僅限 localhost） |
| DELETE | `/api/ui/<name>/uninstall` | 解除安裝 UI（僅限 localhost） |

### MCP 工具

也可以透過 MCP（Model Context Protocol）管理 UI：

- `list_uis()` -- 列出已安裝的 UI
- `switch_ui(name)` -- 切換使用中的 UI
- `install_ui(url)` -- 從 URL 安裝 UI
- `uninstall_ui(name)` -- 解除安裝 UI
