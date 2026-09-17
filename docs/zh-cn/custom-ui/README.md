# 自定义 UI 开发指南

本指南介绍了可以完全替换 YU AI Manager 前端的自定义 UI 系统。

## 目录

- [概述](#概述)
- [架构](#架构)
- [快速开始](quickstart.md) -- 创建一个最小的自定义 UI
- [设计指南](design-guide.md) -- CSS 设计、主题、响应式布局、组件
- [模板指南](templates.md) -- Jinja2 模式、i18n、页面结构
- [高级功能](advanced.md) -- SSE 实时更新、批量操作、安全
- [API 参考](api-reference.md) -- 完整 API 文档链接

## 概述

YU AI Manager 将后端 API 与前端完全分离。将前端替换为自定义实现非常简单。只需将自定义 UI 放置在 `ui/<name>/` 目录中即可激活。

### 功能

- **完整 UI 替换**：将搜索、统计、设置等所有页面替换为您自己的设计
- **主题定制**：仅覆盖 CSS 变量即可更改配色方案
- **部分替换**：仅自定义所需的页面，其余回退到默认 UI
- **AI 生成 UI**：将 API 文档交给 Claude 或 ChatGPT，让它自动生成 UI

### 架构

```
yu_ai_manager/
├── ui/
│   ├── default/              # 参考 UI（内置）
│   │   ├── manifest.json     # UI 元数据（必需）
│   │   ├── templates/        # Jinja2 HTML 模板
│   │   │   ├── index.html    # 主搜索页面
│   │   │   ├── stats.html    # 统计仪表板
│   │   │   ├── tools.html    # 工具页面
│   │   │   ├── settings.html # 设置页面
│   │   │   ├── story.html    # Your Story 页面
│   │   │   ├── inspect.html  # 元数据检查器
│   │   │   └── _nav.html     # 共享导航栏（include）
│   │   └── static/           # CSS、JS、图片
│   │       ├── css/          # 样式表
│   │       ├── dist/         # TypeScript 构建输出
│   │       └── favicon.svg   # 网站图标
│   ├── custom/               # 自定义 UI（gitignored，自动检测）
│   │   ├── manifest.json
│   │   ├── templates/
│   │   └── static/
│   └── my-theme/             # 其他 UI（任意名称）
│       ├── manifest.json
│       └── ...
├── routes/                   # 服务端 API 路由
│   ├── pages.py              # 页面路由定义
│   └── ...                   # 各种 API 端点
└── docs/api/                 # API 文档
```

### UI 解析顺序

服务器在启动时按以下优先级确定使用哪个 UI：

| 优先级 | 条件 | 行为 |
|--------|------|------|
| 1 | `config.json` 包含 `"ui": "my-theme"` | 使用指定的 `ui/my-theme/` |
| 2 | `ui/custom/` 有有效的 `manifest.json` | 自动检测并使用 `ui/custom/` |
| 3 | 以上均不满足 | 回退到 `ui/default/` |

### manifest.json

每个自定义 UI 都需要一个 `manifest.json`：

```json
{
  "name": "my-custom-ui",
  "version": "1.0.0",
  "description": "My custom UI for YU AI Manager",
  "author": "Your Name",
  "api_version": "1"
}
```

| 字段 | 必需 | 说明 |
|------|------|------|
| `name` | 是 | UI 标识符（建议与目录名一致） |
| `version` | 是 | 语义化版本 |
| `description` | 否 | UI 描述 |
| `author` | 否 | 作者名称 |
| `api_version` | 否 | 支持的 API 版本（`"1"`） |
| `type` | 否 | `"full"`（默认）或 `"theme"` |

### 静态文件服务

自定义 UI 中的 `static/` 目录映射到 Flask `/static/` URL：

```
ui/custom/static/style.css  →  /static/style.css
ui/custom/static/js/app.js  →  /static/js/app.js
ui/custom/static/img/logo.png  →  /static/img/logo.png
```

在 HTML 中引用：
```html
<link rel="stylesheet" href="/static/style.css">
<script src="/static/js/app.js"></script>
<img src="/static/img/logo.png">
```

### UI 管理 API

您可以通过设置页面的"UI"标签页或 API 来管理 UI：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/ui/list` | 列出已安装的 UI |
| POST | `/api/ui/switch` | 切换活动 UI（需要重启） |
| POST | `/api/ui/install` | 从 URL 安装 UI（仅限 localhost） |
| DELETE | `/api/ui/<name>/uninstall` | 卸载 UI（仅限 localhost） |

### MCP 工具

也可以通过 MCP（Model Context Protocol）管理 UI：

- `list_uis()` -- 列出已安装的 UI
- `switch_ui(name)` -- 切换活动 UI
- `install_ui(url)` -- 从 URL 安装 UI
- `uninstall_ui(name)` -- 卸载 UI
