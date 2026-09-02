# 调试手册

YU AI Manager 的综合调试指南。
面向开发者和 AI 代理，帮助高效调查和修复 bug。

---

## 目录

1. [启动服务器](#启动服务器)
2. [调试日志](#调试日志)
3. [运行测试](#运行测试)
4. [DB 调试](#db-调试)
5. [认证绕过与测试](#认证绕过与测试)
6. [MCP 调试](#mcp-调试)
7. [前端调试](#前端调试)
8. [环境变量](#环境变量)
9. [常见错误与解决方案](#常见错误与解决方案)
10. [性能调试](#性能调试)

---

## 启动服务器

### 开发模式（推荐）

不使用 PIN 认证启动，用于本地调试：

```bash
source venv/Scripts/activate  # Windows Git Bash
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

如果 `config_test.json` 不存在，使用以下内容创建：

```json
{
  "scan_roots": [],
  "server": {
    "host": "127.0.0.1",
    "port": 5100,
    "lan": false
  },
  "extract_a1111": true,
  "extract_comfyui": true,
  "lowercase_tags": true,
  "compute_hash": false,
  "enable_fts": true,
  "extensions": {}
}
```

### 生产模式（LAN 暴露）

```bash
python web_ui.py --db ./tags.db --host 0.0.0.0 --port 5000 --pin 1234
```

> **注意**：绑定到 `0.0.0.0` 时需要 PIN。自 v4.8.1 起，LAN 暴露时 `--debug` 标志被忽略（防止堆栈跟踪泄漏）。

### 端口选择

5100 → 5200 → 5300 → 每次递增 100。启动前检查：

```bash
# Windows
netstat -ano | grep :5100

# Linux/macOS
ss -tlnp | grep :5100
```

### CLI 选项

| 选项 | 类型 | 默认值 | 说明 |
|--------|------|---------|-------------|
| `--db` | path | `data/tags.db` | SQLite DB 文件路径 |
| `--config` | path | `config.json` | 配置文件路径 |
| `--host` | str | `127.0.0.1` | 绑定地址 |
| `--port` | int | 5000 | 绑定端口 |
| `--lan` | flag | - | 绑定到 `0.0.0.0`（LAN 访问） |
| `--pin` | str | - | 启用 PIN 认证 |
| `--debug` | flag | - | 启用 Quart 调试模式 |
| `--debug-log` | `on`/`off` | - | 启用/禁用结构化调试日志 |
| `--debug-log-file` | path | `logs/debug.log` | 日志文件输出路径 |
| `--debug-log-max-mb` | int | 10 | 日志轮转大小（MB） |
| `--debug-log-backups` | int | 5 | 日志备份代数 |
| `--debug-log-stdout` | `on`/`off` | `on` | 同时输出到 stderr |
| `--allow-restart` | flag | - | 启用 `/api/server/restart` |
| `--trusted-proxy-auth` | flag | - | 启用 Trusted Proxy 认证 |
| `--profile` | str | - | 启动配置文件名称 |

### launch-args.txt

在项目根目录放置 `launch-args.txt` 可在启动时自动加载参数。CLI 参数优先。

---

## 调试日志

### 启用

```bash
# 通过 CLI
python web_ui.py --db ./tags.db --debug-log on

# 通过环境变量
export TAGDB_DEBUG=1
python web_ui.py --db ./tags.db
```

### 日志格式

通过 `dlog()` 函数（`core/infra_core/debug_log.py`）输出结构化调试日志：

```
[DEBUG] 2026-03-15 12:34:56 | scan:prepare | counting_start | root=/path/to/dir, recursive=True
```

格式：`[DEBUG] 时间戳 | 来源 | 事件名 | key=value, ...`

### 实时监控

```bash
# 跟踪日志文件
tail -f logs/debug.log

# 通过 API
curl http://127.0.0.1:5100/api/debug/logs

# SSE 流式传输
curl -N "http://127.0.0.1:5100/api/debug/logs?stream=1"
```

### 日志环形缓冲区

运行日志也存储在内存环形缓冲区中（最多 1000 条）。服务器重启时丢失；使用文件日志进行持久化。

---

## 运行测试

### 单元测试

```bash
source venv/Scripts/activate

# 运行所有测试
python -m pytest tests/test_basic.py -v

# 仅运行特定测试
python -m pytest tests/test_basic.py::TestImports -v

# 在第一个失败时停止
python -m pytest tests/test_basic.py -x
```

### API 集成测试

```bash
python -m pytest tests/api/ -v
```

### Playwright 浏览器测试

```bash
# 1. 启动测试服务器
python web_ui.py --db ./tags.db --config config_test.json --port 5100 &

# 2. 运行测试
TARGET_URL=http://localhost:5100 python -m pytest tests/test_webui_browser.py -v
```

### 测试输出

- 截图：`screenshots/`
- 报告：`reports/`

---

## DB 调试

### 检查 Schema 版本

```bash
python -c "
import sqlite3
con = sqlite3.connect('data/tags.db')
v = con.execute('SELECT MAX(version) FROM schema_version').fetchone()[0]
print(f'Schema version: {v}')
"
```

### 健康检查

```bash
python db_health.py --db ./tags.db
```

### 调试 SQL 执行

仅在 `YU_DEBUG_MODE=1` 时可用：

```bash
curl -X POST http://127.0.0.1:5100/api/debug/query \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: XMLHttpRequest" \
  -d '{"sql":"SELECT COUNT(*) as cnt FROM files WHERE is_deleted=0"}'
```

> **注意**：自 v4.8.1 起，仅允许 SELECT 语句。

### 常用调查查询

```sql
-- 按来源统计文件数
SELECT meta_source, COUNT(*) as cnt FROM files WHERE is_deleted=0 GROUP BY meta_source;

-- 模型使用排名
SELECT model_name, COUNT(*) as cnt FROM templates GROUP BY model_name ORDER BY cnt DESC LIMIT 20;

-- 孤立标签
SELECT t.id, t.name FROM tags t LEFT JOIN file_tags ft ON t.id=ft.tag_id WHERE ft.tag_id IS NULL;

-- 重复路径检测
SELECT path, COUNT(*) as cnt FROM files GROUP BY path HAVING cnt > 1;
```

### DB 连接规则

| 函数 | 用途 | 使用场景 |
|----------|---------|-------------|
| `get_readonly_db()` | 只读 | GET API、搜索、缩略图、统计 |
| `get_db()` | 读写（Row factory） | POST/PUT/DELETE API |
| `get_raw_db()` | 读写（无 Row factory） | 批处理、扫描、迁移 |

> **重要**：在只读 API 中使用 `get_db()` 会导致扫描期间的写锁竞争，阻塞查看器数秒。始终使用 `get_readonly_db()`。

---

## 认证绕过与测试

### 跳过 PIN 认证

使用 `config_test.json`（未配置 PIN）启动以跳过所有认证。

### API Key 测试

```bash
# Bearer token 请求（无需 CSRF 头）
curl -H "Authorization: Bearer sk_xxxxxxxxxxxxxx" \
  http://127.0.0.1:5000/api/stats/all
```

### API Key 权限范围

自 v4.8.1 起，未设置权限范围的密钥默认为**只读**。

| 权限范围 | 允许的操作 |
|-------|-------------------|
| `read` | 搜索、文件详情、缩略图、统计 |
| `rate` | 评分设置/获取/批量 |
| `tag.write` | 标签添加/移除 |
| `collection.write` | 合集 CRUD、收藏 |
| `annotate` | 注解读写 |
| `scan` | 扫描启动/取消/恢复 |
| `admin` | API 密钥管理、设置、备份/恢复 |

### 认证链顺序

```
static → /s/（LAN Share） → /_pin → API Key Bearer
→ QuickLock → Trusted Proxy → session → cookie → PIN 页面
```

---

## MCP 调试

### 启动 MCP 服务器

```bash
source venv/Scripts/activate
python -m mcp_server
```

### 启用调试工具

```bash
export YU_DEBUG_MODE=1
export YU_BASE_URL=http://127.0.0.1:5100
export YU_API_KEY=sk_...
python -m mcp_server
```

### 调试工具（9 个工具，YU_DEBUG_MODE=1）

| 工具 | 用途 |
|------|---------|
| `debug_health_check` | 服务器、DB 和表健康检查 |
| `debug_validate_counts` | API 统计与 DB 实际计数对比 |
| `debug_validate_search` | 搜索 API 回归检查 |
| `debug_validate_collection` | 合集计数一致性 |
| `debug_validate_annotations` | 注解表完整性 |
| `debug_sample_files` | 随机抽样字段分析 |
| `debug_roundtrip_test` | 注解/评分/标签往返测试 |
| `debug_readonly_query` | 执行任意 SELECT 查询 |
| `debug_full_report` | 工具 1-5 的综合报告 |

### 导入检查

```bash
python -c "from mcp_server.server import mcp; print('OK')"
```

---

## Extension 安全扫描

YU AI Manager 内置了 Extension 代码扫描功能。扫描**在 Extension 加载时自动运行**，因此在添加或修改 Extension 后，重启服务器即可触发扫描。

### 自动扫描工作原理

Extension 加载时按顺序执行以下检查：

```
1. ManifestAuthority.review()   — 清单审查（格式、权限有效性）
2. CodeVerifier.verify()        — AST 静态分析（所有 .py 文件的代码扫描）
3. 用户同意检查                  — 权限批准/拒绝
4. Capability Token 签发         — 执行权限令牌
```

### CodeVerifier 检测内容

| 类别 | 目标 | 严重程度 |
|----------|--------|----------|
| 危险模块 | `subprocess`、`ctypes`、`importlib` | block |
| 直接 DB 访问 | `import sqlite3`（应使用 SandboxedDB） | block |
| 网络 | `requests`、`urllib`、`httpx`、`aiohttp`、`socket` | warn |
| 动态代码执行 | `eval()`、`exec()`、`__import__()`、`compile()` | block |

检测到 `block` 严重程度的发现时，Extension 将被拒绝加载。

### 如何运行扫描

**正常流程（推荐）：**

添加或修改 Extension 后重启服务器。扫描在加载过程中自动运行，结果输出到日志。

```bash
# 重启服务器以重新加载 Extension（扫描自动运行）
python web_ui.py --db ./tags.db --config config_test.json --port 5100
```

**仅手动扫描：**

```python
from pathlib import Path
from core.extensions_core.validation.code_verifier import CodeVerifier

result = CodeVerifier().verify(Path("extensions/my-extension"))

# 检查结果
for finding in result.findings:
    print(f"[{finding.severity}] {finding.file}:{finding.line} - {finding.message}")

print(f"Approved: {result.approved}")
```

### 信任级别

Extension 分为 3 个信任级别：

| 级别 | 条件 | 限制 |
|-------|-----------|-------------|
| L0 Trusted | `builtin-` 前缀 | 无限制 |
| L1 Verified | 签名已验证 | 仅限声明的权限 |
| L2 Untrusted | 手动安装 | 声明的权限 + 需要用户同意 |

### 运行时保护

加载后在运行时继续提供保护：

- **Import Guard**：通过 `sys.meta_path` 阻止未授权的模块导入
- **完整性监控**：每 5 分钟比较 SHA-256 哈希值以检测文件篡改
- **令牌自动撤销**：检测到违规时撤销 Capability Token，停止执行

### 相关文档

| 文档 | 位置 |
|----------|----------|
| 三权分立安全模型 | `docs/development/development_docs/EXTENSION_TRIAS_POLITICA_SPEC.md` |
| 沙箱规格 | `docs/development/development_docs/EXTENSION_SANDBOX_SPEC.md` |
| Hook 规格 | `docs/development/development_docs/EXTENSION_HOOKS_SPEC.md` |

---

## 前端调试

### TypeScript 构建

```bash
pnpm run build        # esbuild 打包
pnpm run typecheck    # tsc --noEmit（仅类型检查）
```

输出：`ui/default/static/dist/`（已 gitignore）

### CSRF 拦截器

`src/ts/nav/csrf-fetch.ts` 使用 Proxy 包装全局 `fetch`，在所有 POST/PUT/DELETE 请求上自动注入 `X-Requested-With` 头。

### SSE 共享引擎

`window.EventSource` 被 Proxy 覆盖。直接 `new EventSource()` 会抛出错误。

```javascript
// 正确
window.sseSubscribe('scan.progress', (d) => console.log(d.data));

// 错误（运行时错误）
// new EventSource('/api/events/...')
```

### i18n 调试

```javascript
window.setLang('en');
console.log(window.tr('search.count.normal', { count: 5 }));
```

---

## 环境变量

### 调试 / 日志

| 变量 | 值 | 默认值 | 说明 |
|----------|--------|---------|-------------|
| `TAGDB_DEBUG` | `1`/`0` | `0` | 启用结构化调试日志 |
| `TAGDB_DEBUG_LOG` | path | `logs/debug.log` | 日志文件路径 |
| `TAGDB_DEBUG_LOG_MAX_MB` | int | `10` | 日志轮转大小（MB） |
| `TAGDB_DEBUG_LOG_BACKUPS` | int | `5` | 备份代数 |
| `TAGDB_DEBUG_STDOUT` | `1`/`0` | `1` | 输出到 stderr |

### 服务器

| 变量 | 值 | 说明 |
|----------|--------|-------------|
| `TAGDB_DB` | path | DB 文件路径 |
| `TAGDB_CONFIG` | path | config.json 路径 |
| `TAGDB_PROFILE` | str | 启动配置文件名称 |
| `TAGDB_ALLOW_RESTART` | `1`/`0` | 启用重启 API |

### MCP

| 变量 | 值 | 说明 |
|----------|--------|-------------|
| `YU_DEBUG_MODE` | `1` | 注册 9 个调试工具 |
| `YU_BASE_URL` | URL | MCP 客户端基础 URL |
| `YU_API_KEY` | `sk_...` | MCP 客户端 API 密钥 |

---

## 常见错误与解决方案

### 服务器启动

| 错误 | 原因 | 修复 |
|-------|-------|-----|
| `Address already in use` | 端口被占用 | 使用 `--port 5200` |
| `database is locked` | DB 锁竞争 | 确保 DB 在本地磁盘上 |
| `--pin is required` | 无 PIN 的 LAN 绑定 | 添加 `--pin <digit>` |
| `ModuleNotFoundError` | venv 未激活 | `source venv/Scripts/activate && uv pip install -r requirements.txt` |

### 认证

| 错误 | 原因 | 修复 |
|-------|-------|-----|
| PIN 页面循环 | Cookie 问题 | 在 DevTools 中检查 Cookie |
| `CSRF header missing` (403) | 缺少 `X-Requested-With` | 在 fetch 请求中添加该头 |
| API Key 被拒绝 | 权限范围不足 | 分配所需的权限范围（v4.8.1+） |

### Windows 特有问题

| 错误 | 原因 | 修复 |
|-------|-------|-----|
| `UnicodeEncodeError` on print | cp932 编码 | 使用 ASCII 安全字符 |
| `pkill` 不起作用 | Git Bash 限制 | 使用 `taskkill //F //PID <pid>` |

---

## 性能调试

### 扫描期间查看器阻塞

**症状**：扫描期间图片加载停止 5-10 秒

**原因**：只读 API 使用了 `get_db()`（可写连接）

**修复**：所有只读 API 使用 `get_readonly_db()`

### 速率限制

| 层级 | 目标 | 限制 |
|------|--------|-------|
| **HEAVY** | 相似搜索、哈希、AI 分析、扫描 | ~20 req/min（突发 5） |
| **DESTRUCTIVE** | purge、hard-delete、缓存清除 | ~12 req/min（突发 3） |
| **WRITE** | 其他 POST/PUT/DELETE | ~120 req/min（突发 30） |
| GET | 读取 | 无限制 |

收到 429 响应时检查 `Retry-After` 头。

---

## 相关文档

| 文档 | 位置 |
|----------|----------|
| DB 读写分离 | `docs/development/development_docs/SQLITE_READONLY_SEPARATION.md` |
| 错误格式标准 | `docs/development/development_docs/ERROR_HANDLING.md` |
| 跨平台问题 | `docs/development/development_docs/CROSS_PLATFORM_ISSUES.md` |
| MCP 调试工具规格 | `docs/development/development_docs/MCP_DEBUG_TOOLS.md` |
| Quart 迁移日志 | `docs/development/development_docs/QUART_MIGRATION_DEVLOG.md` |
| QA 交接 | `docs/development/development_docs/QA_HANDOFF.md` |
| 安全检查清单 | `/security-check` 技能 |
