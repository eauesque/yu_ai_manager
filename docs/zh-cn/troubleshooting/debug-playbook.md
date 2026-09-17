# YU AI Manager 调试手册

## 快速开始

```bash
# 运行全部诊断
python debug_check.py

# 指定数据库
python debug_check.py --db /path/to/tags.db

# 简易检查（跳过语法/Extension）
python debug_check.py --quick
```

---

## 常见问题及处理方法

### 1. config.json 损坏（反斜杠问题）

**症状：** 服务器启动时出现 JSONDecodeError
**原因：** 手动输入 Windows 路径时 `\U`、`\w` 等成为无效转义
**处理：** 服务器启动时会自动修复。手动修复方法：
```bash
python -c "
from core.config import safe_load_json
data = safe_load_json('config.json')
print('OK' if data else 'FAILED')
"
```

### 2. scan-all 中特定文件夹被跳过

**症状：** "全文件夹扫描"中部分文件夹未被处理
**确认步骤：**
```bash
# 确认 scan_roots 内容
python -c "
import json
c = json.load(open('config.json'))
for i, r in enumerate(c.get('scan_roots', [])):
    print(f'  [{i}] repr={repr(r)} len={len(r)}')
"
```
**检查项：**
- 路径是否过短（是否仅为 `\\wsl.localhost\`）
- 末尾是否有 `\`
- `os.path.exists(path)` 是否返回 True

### 3. QR 分享显示"没有内容"

**症状：** QR 分享按钮 → Positive/Negative 为空
**可能原因：**
1. `templates` 表中没有记录（meta_source=unknown）
2. API 响应的键不匹配（v2.7.0 已修复）

**确认：**
```bash
# 检查文件 ID 的模板是否存在
python -c "
import sqlite3
con = sqlite3.connect('tags.db')
file_id = 276323  # 有问题的 ID
row = con.execute('SELECT * FROM templates WHERE file_id=?', (file_id,)).fetchone()
print('templates:', 'EXISTS' if row else 'MISSING')
meta = con.execute('SELECT meta_source FROM files WHERE id=?', (file_id,)).fetchone()
print('meta_source:', meta[0] if meta else 'NOT FOUND')
"
```

### 4. WSL/UNC 路径扫描失败

**症状：** `\\wsl.localhost\...` 路径探测失败
**确认：**
```bash
python -c "
import os
path = r'\\\\wsl.localhost\\Ubuntu\\home\\user\\...'
print(f'exists: {os.path.exists(path)}')
print(f'isdir: {os.path.isdir(path)}')
print(f'repr: {repr(path)}')
print(f'len: {len(path)}')
"
```
**注意：** `pathlib.Path.exists()` 在 WSL UNC 路径上有 bug。请使用 `os.path.exists()`。

### 5. Extension 未加载

**症状：** Extension 列表中不显示
**确认：**
```bash
python debug_check.py  # 查看 Extension 检查部分
```
**检查项：**
- `extension.json` 或 `extension.yml` 是否存在
- JSON/YAML 是否有效（使用 `safe_load_config` 检查）
- `name` 字段是否存在

### 6. PIN 认证被锁定

**症状：** 5 次失败 → 60 秒锁定
**处理：** 等待 60 秒，或重启服务器以重置。
**确认：** 浏览器开发者工具 → Network → 查看 `/_pin_check` 的响应错误消息

---

## 调试日志的阅读方法

### 服务器控制台输出

```
[WARN] config.json had invalid escapes -- auto-repaired and saved
  → config.json 的反斜杠自动修复已执行

[DEBUG] scan/start: raw=..., sanitized=...
  → 扫描开始时的路径（原始值 → 清理后）

[DEBUG] scan-all root 0: repr=..., len=...
  → 全文件夹扫描时各根路径的详细信息

[Scan] Auto-registered scan root: /path/to/dir
  → 扫描成功时的自动注册

[DEBUG share] file_id=123, file_row=yes, tmpl=no
  → QR 分享 API：文件存在但没有模板

[ERROR] file.json: JSON parse failed: ...
  → safe_load_json 的解析错误（应用不会崩溃）
```

---

## 文件结构与调试对象

```
web_ui.py          ← 入口点（服务器启动）
core/
  config.py        ← 配置管理、safe_load_*
  server.py        ← PIN 认证、QuickLock
  scanner.py       ← 扫描引擎
  extensions.py    ← Extension 加载
  db.py            ← 数据库连接管理
  schema.py        ← 表定义
routes/
  scan.py          ← 扫描 API
  search.py        ← 搜索 API
  share.py         ← QR 分享 API
  tools.py         ← 工具 API + Inspect API
  debug.py         ← 调试 API
  pages.py         ← 页面路由
static/js/
  main.js          ← 主 UI（搜索、模态框、QR、键盘）
  scan-banner.js   ← 扫描进度 + 滚动到顶部（全页面）
```
