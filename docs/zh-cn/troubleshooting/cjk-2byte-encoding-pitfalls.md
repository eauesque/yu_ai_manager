# CJK / 双字节编码陷阱与解决方案

本文档整理了双字节字符环境（主要是日语 CP932/Shift-JIS）中特有的 bug，以及本项目中采用的解决方案。旨在为遇到类似问题的开发者和 AI 代理提供参考。

---

## 1. Windows 控制台 cp932 崩溃

### 症状

Windows `cmd.exe` / PowerShell / Git Bash 的默认输出编码为 **cp932 (Shift-JIS)**。当 `print()` 输出 cp932 中不存在的 Unicode 字符时，会立即引发 `UnicodeEncodeError` 导致崩溃。

```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2014' in position 12
```

### 引发问题的字符

| 字符 | 名称 | 使用场景 |
|------|------|---------|
| `—` (U+2014) | em dash | 日志输出分隔符 |
| `–` (U+2013) | en dash | 进度显示 |
| `✓ ✗ ✅ ❌ ⚠️` | 对勾/表情符号 | 成功/失败指示 |
| `🧹 📦 📁 🔍 🔧` | 表情符号 | 操作标签 |
| `█ ░` | 块状字符 | 进度条 |

### 解决方案

- **在 `print()` 中只使用 ASCII 安全字符**：`[OK]`、`[NG]`、`[!]`、`--`、`#`、`-` 等。
- `logging` 处理器同样适用。编码为 cp932 的处理器会遇到相同的问题。
- 可以通过设置 `PYTHONIOENCODING=utf-8` 来解决，但依赖用户环境不够可靠。防御性地使用 ASCII 更为安全。

### 影响范围

本项目需要对 **19 个文件**进行批量修复（v2.28.0）。AI 代码生成器（Claude/GPT）高频使用表情符号和 em dash。**这是审查 AI 生成代码时最需要检查的项目之一。**

---

## 2. ZIP 文件名乱码（CP437）

### 症状

在旧版 Windows 系统（95/98/XP 时代）创建的 ZIP 文件以 **Shift-JIS (CP932)** 存储文件名，但 ZIP 规范不包含编码元数据。Python 的 `zipfile` 模块在 UTF-8 标志（第 11 位）未设置时将文件名解码为 **CP437**。这会导致日语文件名变成 `âwâCâèâb` 这样的乱码。

### 解决方案：10 级回退链

`core/infra_core/encoding.py` 定义了优先级排列的 CJK 编码列表：

```
UTF-8（zipfile 首先尝试）→ CP932 → EUC-JP → ISO-2022-JP
→ EUC-KR → CP949 → GB2312 → GBK → Big5 → CP950
```

- **不使用** `chardet` / `cchardet`：短文件名（10--30 字节）会产生过多误判。
- 固定优先级方式提供更好的可重现性和更简单的调试。

### Python 3.11+ 的 `metadata_encoding` 参数

```python
# Python 3.11+ 允许通过 metadata_encoding 直接指定
zf = zipfile.ZipFile(path, metadata_encoding='cp932')
```

此方法无法处理以 CP932 以外编码存储的 ZIP 文件。失败时，代码会在不使用 `metadata_encoding` 的情况下重新打开存档，并通过 `repair_cp437_name()` 尝试恢复。

### 7z 存档

7-Zip 有自己的文件名处理方式。通过 7z CLI 可能出现 CP437 乱码；`repair_cp437_name()` 应用相同的恢复逻辑。

---

## 3. 双字节文件名导致 ZIP/7z 扫描挂起

### 症状

当 `zipfile.ZipFile()` 读取 Shift-JIS 编码文件名的旧 ZIP 中央目录时，可能进入阻塞 I/O 状态而挂起。文件数量多的存档尤其容易出现此问题。

### 解决方案

1. **超时保护**：引入了 `run_with_timeout()` 守护线程辅助函数。
   - 文件列表：30 秒
   - 扫描 I/O：60 秒
2. **scan_errors 表**（迁移 v24）：超时和编码错误被持久化到数据库中。
   - 错误类型分类：`encoding` / `timeout` / `scan` / `archive_scan` / `archive_timeout` / `filesystem`

---

## 4. SQLite FTS5 tokenchars 引号问题

### 症状

根据 `tokenchars` 选项使用的引号组合，可能在 SQLite FTS5 `tokenize` 指令中触发解析错误。

```sql
-- NG：外层单引号 + 内层双引号 → 解析错误
tokenize='unicode61 tokenchars "_:."'

-- OK：外层双引号 + 内层单引号
tokenize="unicode61 tokenchars '_:.'"
```

### 原因

FTS5 分词器解析器无法正确解析嵌套在单引号内的双引号。可能还存在版本特定的行为差异（在 SQLite 3.45.1 上确认）。

### 解决方案

使用 Python 三引号字符串以兼容两种 SQL 引号类型：

```python
# OK：Python ''' 包裹 SQL 的 " 和 '
con.execute('''
    CREATE VIRTUAL TABLE fts USING fts5(
        col1,
        tokenize="unicode61 tokenchars '_:.'"
    )
''')
```

### 发现经过

此问题在重建 FTS5 表的迁移 29 中被发现。AI 生成的代码使用了单引号外层语法。在 SQLite 3.45.1 上服务器启动时崩溃（v2.70.1 中修复）。

---

## 5. UTF-16 编码的 WebP EXIF

### 症状

部分图像生成工具（尤其是 NAI 系列工具）以 **UTF-16（带 BOM）** 存储 WebP EXIF 元数据。标准 UTF-8 解码会产生乱码。

### 解决方案

- 检测 BOM（字节顺序标记）以判断 UTF-16 BE/LE。
- 无 BOM 时使用启发式方法推测 BE/LE。
- 依次回退到 UTF-8 和 latin-1。

---

## 6. PNG tEXt 块编码

### 症状

PNG 规范将 tEXt 块定义为 **Latin-1 (ISO-8859-1)**，但大多数 AI 图像生成工具直接写入 UTF-8 编码的字符串。以 `latin-1` 解码会导致日语文本乱码。

### 解决方案

先尝试 UTF-8 解码，失败时回退到 latin-1：

```python
try:
    text = raw_bytes.decode('utf-8')
except UnicodeDecodeError:
    text = raw_bytes.decode('latin-1')
```

---

## 7. config.json 中的 Windows 路径反斜杠

### 症状

Windows 文件路径包含反斜杠（`\`）。在 JSON 文件中手动输入路径会产生无效的转义序列。

```json
{"scan_roots": ["C:\Users\test"]}  // \U 和 \t 会变成转义序列
```

### 解决方案

- `_repair_json_backslashes()` 在服务器启动时自动修复路径。
- 路径在保存前会进行内部规范化。

---

## 8. pathlib 与 WSL UNC 路径

### 症状

在 WSL（Windows Subsystem for Linux）下，`pathlib.Path.exists()` 对 UNC 路径（`\\server\share\...`）可能返回错误的结果。

### 解决方案

- UNC 路径的存在性检查使用 `os.path.exists()`。
- `pathlib` 虽然方便，但对网络路径不可靠。

---

## 9. CSV 导出的 UTF-8 BOM

### 症状

Excel 会将没有 BOM 的 UTF-8 CSV 文件显示为乱码。Excel 将无 BOM 的 UTF-8 解释为 ANSI（日语环境中为 CP932）。

### 解决方案

```python
buf.write("\ufeff")  # 用于 Excel 兼容性的 UTF-8 BOM
```

在 CSV 输出前添加 BOM（`\ufeff`）。这可确保 Excel 将文件识别为 UTF-8。

---

## 10. JSON 输出中的 `ensure_ascii=False`

### 症状

Python 的 `json.dumps()` 默认将非 ASCII 字符转义为 `\uXXXX`。包含日语标签名或文件路径的 MCP 工具响应会显示为 `\u30bf\u30b0`，使 AI 代理难以理解内容。

### 解决方案

```python
json.dumps(data, ensure_ascii=False, indent=2)
```

本项目在所有 MCP 工具模块（10 个文件）中一致使用此设置。

---

## 11. 文件夹选择对话框输出解码

### 症状

Windows 上的 PowerShell 文件夹选择对话框以 CP932 编码返回 `subprocess` 输出。默认的 UTF-8 解码会引发 `UnicodeDecodeError`。

### 解决方案

```python
result = subprocess.run(..., capture_output=True)
path = result.stdout.decode('cp932', errors='replace').strip()
```

`errors='replace'` 标志确保即使解码失败也能安全处理。

---

## AI 代理注意事项

上述许多问题都是 **AI 代码生成器容易忽略的模式**：

1. **不要在 `print()` 中使用表情符号或装饰字符** -- AI 生成器经常为了视觉效果而使用它们。
2. **不要假设文件名编码** -- 基于 UTF-8 假设编写的代码在 CP932 环境中会出错。
3. **在实际运行时测试 SQLite 引号** -- 符合文档的语法在实践中仍可能失败。
4. **始终向 `json.dumps()` 传递 `ensure_ascii=False`** -- 处理日语数据时必不可少。
5. **使用环境编码解码 subprocess 输出** -- Windows 通常使用 CP932。
6. **在 CSV 输出中包含 BOM** -- 这是 Excel 兼容性所必需的。

---

## 参考：本项目相关文件

| 文件 | 说明 |
|------|------|
| `core/infra_core/encoding.py` | CJK 回退链、CP437 乱码修复 |
| `core/schema_core/schema_migrate_steps_29.py` | 正确的 FTS5 tokenchars 引号 |
| `core/tools/fs_dialog.py` | 文件夹选择对话框 CP932 解码 |
| `core/configuration/json_rw.py` | config.json 反斜杠修复 |
| `routes/collections.py` | CSV 导出 BOM 插入 |
| `CLAUDE.md` | "Windows 环境注意事项 > 控制台输出"部分 |
