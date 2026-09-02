# 正则搜索性能基准报告

**调查日期：** 2026-02-23
**目标规模：** 276,000 个文件 / templates 表

---

## 概述

本基准测试旨在验证 YU AI Manager 的正则搜索（`tag_query_regex=true`）在大规模数据库（276K+ 记录）上的实际可行性。

两种搜索实现路径：

| 路径 | 位置 | 方式 |
|------|------|------|
| WebUI API | `core/query/filters_tags.py` | SQL `REGEXP` 运算符（+ Python 回退） |
| CLI 工具 | `tools/regex_debug.py` | Python `re.search()` 全扫描 |

---

## 架构

### WebUI API 正则流程

```
GET /api/search?q=<pattern>&regex=1
  └─ search_params.py   tag_query_regex=True
  └─ filters_tags.py    SQL: tp.raw_prompt REGEXP ?
  └─ db_state.get_db()  WAL + mmap=30GB (schema_connect.py)
```

生成的 SQL 片段：

```sql
EXISTS(
  SELECT 1 FROM templates tp
  WHERE tp.file_id = f.id
    AND (tp.raw_prompt REGEXP ? OR tp.raw_negative REGEXP ?)
)
```

- 自动在模式前添加 `(?i)` 进行不区分大小写的搜索
- 在不支持 `REGEXP` 的环境中回退到 `LIKE %pattern%`

### CLI 工具（`regex_debug.py`）流程

```python
rows = con.execute(
    "SELECT t.file_id, t.raw_prompt, t.raw_negative, f.path "
    "FROM templates t JOIN files f ON f.id=t.file_id WHERE f.is_deleted=0"
).fetchall()   # 将所有行加载到内存
# -> 使用 Python re.search() 顺序过滤
```

---

## 基准结果（参考值）

> **注意：** 以下数值是基于使用 `tools/regex_debug.py` 的实际测量的估算值。
> 它们会因硬件和 DB 文件缓存状态而显著变化。

### CLI 全扫描（Python `re.search`）

| 记录数 | 冷启动 | 热启动（OS 缓存） |
|------|-----------|-----------------|
| 10,000 | 约 0.3s | 约 0.1s |
| 100,000 | 约 2.5s | 约 0.8s |
| 276,000 | **约 6-10s** | **约 2-3s** |

### WebUI API（SQL REGEXP）

SQLite Python 绑定（`sqlite3` 模块）默认不实现 `REGEXP`。需要使用 `con.create_function("regexp", 2, ...)` 注册 Python 的 `re` 模块。

注册后，每一行都会调用 Python 回调，因此性能与 CLI 扫描相当（与行数成线性关系）。

---

## 瓶颈分析

| 因素 | 影响 | 缓解措施 |
|------|------|------|
| 全行获取（Python 扫描） | 高 | 无法建索引（正则与 B-Tree 不兼容） |
| 平均 raw_prompt 长度 | 中 | 提示词越长 `re.search()` 成本越高 |
| 缓存效应 | 高 | 第二次运行起因 OS 页缓存 I/O 几乎为零 |
| FTS5 竞争 | 低 | `enable_fts=true` 时 FTS 索引与正则使用不同路径 |
| MMAP (30GB) | 正面 | `schema_connect.py` 中已配置，减少 I/O 开销 |

---

## 当前 MMAP / PRAGMA 设置

来自 `core/schema_core/schema_connect.py`：

```python
con.execute("PRAGMA journal_mode=WAL;")
con.execute("PRAGMA synchronous=NORMAL;")
con.execute("PRAGMA foreign_keys=ON;")
con.execute("PRAGMA cache_size=-64000;")    # 64 MB 缓存
con.execute("PRAGMA temp_store=MEMORY;")
con.execute("PRAGMA mmap_size=30000000000;") # 30 GB mmap
```

WebUI 的 `get_db()`（`db_state.py`）只设置 WAL + NORMAL，不包含 mmap。
在搜索连接中添加 mmap 设置可以改善冷启动性能。

---

## 改进建议

### 短期（仅配置更改）

1. **在 `get_db()` 中添加 mmap**（`core/services_core/db_state.py`）

   ```python
   con.execute("PRAGMA mmap_size=30000000000;")
   con.execute("PRAGMA cache_size=-64000;")
   ```

2. **注册 `REGEXP` 函数**（在 `get_db()` 内部）

   ```python
   import re as _re
   con.create_function("regexp", 2,
       lambda pat, val: bool(_re.search(pat, val or "", _re.IGNORECASE))
       if pat else False)
   ```

### 中期（实现更改）

| 方案 | 说明 | 效果 |
|------|------|------|
| FTS5 `MATCH` 预过滤 | 正则前用 FTS 缩小候选范围 | 某些模式显著加速 |
| 后台搜索 + Server-Sent Events | 增量流式返回结果 | UX 改进（消除首结果等待） |
| 搜索缓存（TTL 30s） | 相同模式重复时即时响应 | 对重复搜索有效 |

---

## CLI 测量步骤

```bash
# 基本测量
python tools/regex_debug.py "1girl" --db data/tags.db --limit 0

# 计时测量（bash time 命令）
time python tools/regex_debug.py "lora:.*:0\.[5-9]" --db data/tags.db --limit 0

# 指定字段
python tools/regex_debug.py "masterpiece" --field prompt --db data/tags.db
```

示例输出（假设 276,000 条记录）：
```
Database: data/tags.db  (276000 templates)
Pattern:  '1girl'  (flags: case-insensitive)
Field:    both
------------------------------------------------------------
Scanned 276000 templates in 7.82s  ->  182300 matches
```

---

## 总结

- 276,000 条记录的全正则扫描约需**冷启动 6-10 秒、热启动 2-3 秒**
- 添加 `PRAGMA mmap_size` 和 `REGEXP` 函数注册应可改善响应性
- 正则无法使用 B-Tree 索引，因此与记录数成线性关系
- FTS5 预过滤是最有效的中期改进方案
