# Source Code Browsing API

只读浏览项目源代码的 API。
设计目的是让 MCP 工具和外部 AI 代理可以安全地查看和搜索代码库。

## 安全模型

三层防御确保安全性：

### 1. 路径规范化（遍历防护）

- 所有路径使用 `os.path.realpath()` 规范化，并通过前缀匹配与项目根目录进行验证。
- 阻止 `../../etc/passwd` 或 `../../../Windows/System32` 等遍历攻击。
- 同时检测并拒绝空字节注入（`\x00`）。

### 2. 扩展名白名单

允许读取的文件扩展名：

| 分类 | 扩展名 |
|----------|-----------|
| Python | `.py` |
| TypeScript / JavaScript | `.ts`, `.js`, `.mjs`, `.tsx`, `.jsx` |
| Web | `.html`, `.css`, `.scss` |
| 配置 | `.json`, `.yaml`, `.yml`, `.toml`, `.cfg`, `.ini` |
| 文档 | `.md`, `.txt`, `.rst` |
| 脚本 | `.sh`, `.bat`, `.cmd`, `.ps1` |
| 其他 | `.sql`, `.gitignore`, `.gitattributes`, `.editorconfig` |

以下无扩展名文件被特别允许：`Dockerfile`、`Makefile`、`Procfile`、`VERSION`、`LICENSE`、`CHANGELOG`、`TODO`

### 3. 敏感文件黑名单

匹配以下模式的文件将被拒绝：

| 模式 | 原因 |
|---------|--------|
| `config.json`、`config_*.json` | PIN、API Key 等认证数据 |
| `*.env`、`.env.*` | 环境变量（密钥） |
| `secret.salt`、`*.key`、`*.pem`、`*.cert` | 加密密钥和证书 |
| `credentials*`、`*token*`、`*secret*` | 认证数据 |
| `*.db`、`*.sqlite*` | 数据库文件 |
| `pnpm-lock.yaml`、`package-lock.json` 等 | 锁定文件（大文件） |
| 图片、视频、字体、模型文件 | 二进制文件 |

### 被阻止的目录

`.git`、`__pycache__`、`node_modules`、`venv`、`dist`、`data`、`backups`、`screenshots`、`reports`、`src-tauri`

### 读取限制

| 项目 | 限制 |
|------|-------|
| 文件大小 | 1 MB |
| 每次读取行数 | 2,000 |
| 树遍历深度 | 6 |
| 搜索结果 | 50 |

---

## 端点

### GET /api/source/tree

获取目录树。

#### 参数

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|-------------|
| `path` | string | `""`（根目录） | 相对路径 |
| `depth` | int | `3` | 遍历深度（1-6） |

#### 响应

```json
{
  "ok": true,
  "root": ".",
  "depth": 3,
  "entries": [
    {
      "name": "core",
      "type": "dir",
      "path": "core",
      "children": [
        {
          "name": "source_core",
          "type": "dir",
          "path": "core/source_core",
          "children": [
            {
              "name": "source_browser.py",
              "type": "file",
              "path": "core/source_core/source_browser.py",
              "size": 8234
            }
          ]
        }
      ]
    },
    {
      "name": "web_ui.py",
      "type": "file",
      "path": "web_ui.py",
      "size": 3456
    }
  ]
}
```

- 目录在前，文件在后（按名称排序）。
- `size` 以字节为单位（仅文件）。
- 达到指定 `depth` 后 `children` 将被省略。

---

### GET /api/source/read

读取带行号的文件内容。

#### 参数

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|-------------|
| `path` | string | —（必填） | 相对文件路径 |
| `offset` | int | `0` | 起始行（从 0 开始） |
| `limit` | int | `2000` | 最大行数 |

#### 响应

```json
{
  "ok": true,
  "path": "core/source_core/source_browser.py",
  "total_lines": 250,
  "offset": 0,
  "limit": 2000,
  "content": "    1\t\"\"\"Source code browser...\n    2\t\n    3\timport os\n..."
}
```

- `content` 使用 `{行号}\t{行内容}` 格式。
- 使用 `offset` + `limit` 对长文件进行分页读取。

#### 错误示例

```json
{
  "ok": false,
  "error": "This file is not eligible for reading"
}
```

```json
{
  "ok": false,
  "error": "Access outside the project root is prohibited"
}
```

---

### GET /api/source/search

在源代码中搜索文本。

#### 参数

| 参数 | 类型 | 默认值 | 说明 |
|-----------|------|---------|-------------|
| `q` | string | —（必填） | 搜索文本（至少 2 个字符） |
| `glob` | string | `""`（所有文件） | 文件名过滤（如 `*.py`） |
| `limit` | int | `30` | 最大结果数（1-50） |

#### 响应

```json
{
  "ok": true,
  "query": "def source_tree",
  "glob": "*.py",
  "total": 2,
  "results": [
    {
      "file": "core/source_core/source_browser.py",
      "line": 120,
      "text": "def source_tree("
    },
    {
      "file": "routes/source_api.py",
      "line": 15,
      "text": "    result = source_tree(rel_path, depth_int)"
    }
  ]
}
```

- 搜索不区分大小写。
- `text` 最多截断为 200 个字符。

---

## MCP 工具

| 工具 | 说明 | 主要参数 |
|------|-------------|----------------|
| `source_tree` | 显示目录树 | `path`: str = '', `depth`: int = 3 |
| `source_read` | 读取文件内容 | `path`: str（必填）, `offset`: int = 0, `limit`: int = 2000 |
| `source_search` | 按文本搜索源代码 | `query`: str（必填）, `glob`: str = '', `limit`: int = 30 |

### MCP 使用示例

```
# 查看项目结构
source_tree(path="", depth=2)

# 读取特定文件
source_read(path="core/source_core/source_browser.py")

# 在代码库中搜索
source_search(query="def register_blueprints", glob="*.py")
```

### 范围与速率限制

- **Scope Fence**：在 `read_only` 范围内可用（所有预设中均允许）
- **Budget Tracker**：`read` 类别（无速率限制）
- **HITL Gate**：等级 0（无需审批）

---

## 实现文件

| 文件 | 职责 |
|------|------|
| `core/source_core/source_browser.py` | 安全层 + 业务逻辑 |
| `routes/source_api.py` | Flask API 端点（Blueprint） |
| `mcp_server/source_tools.py` | MCP 工具注册 |
