# Tag Database - 调试检查清单

**按优先级排列的调试列表**
**状态**：旧版（记录于 v2.5.x 时期；所有项目均已解决）
**最后更新**：2026-02-13

---

## P0（紧急）：立即修复（影响可用性）

### 1. UI 布局对齐修复

**问题：**
```
搜索字段并排放置时会溢出，
导致按钮位置偏移。
```

**验证方法：**
1. 启动 WebUI
2. 将浏览器调整为 1366x768
3. 检查搜索字段对齐

**修复位置：** `templates/index.html`
```html
<!-- 修改前 -->
<div class="search-row">
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
  <div class="form-group">...</div>
</div>

<!-- 修改后 -->
<div class="search-row">
  <!-- 添加 flex-wrap: wrap -->
  <div class="form-group" style="flex: 1 1 200px;">...</div>
  ...
</div>
```

**验证：**
- [ ] 在 1920x1080 下正确显示
- [ ] 在 1366x768 下正确显示
- [ ] 在 768x1024（平板）下正确显示

---

### 2. 标签自动补全去重

**问题：**
```
自动补全建议中包含重复项。

示例：
  sample_creator_a,sample_creator_b,sample_creator_c
  sample_creator_a, sample_creator_b, sample_creator_c
  ^ 仅空格不同
```

**验证方法：**
1. 在标签输入框中输入 "sample_creator"
2. 检查自动补全建议
3. 查看是否有重复

**修复位置：** `static/js/main/main.js`
```javascript
// initTagAutocomplete() 内部
async function fetchSuggestions(q) {
  const response = await fetch(`/api/suggest?q=${encodeURIComponent(q)}`);
  const data = await response.json();

  // 规范化并去重
  const normalized = new Map();

  for (const item of data) {
    const clean = item.tag
      .replace(/,(?!\s)/g, ', ')  // 逗号后添加空格
      .replace(/\s+/g, ' ')        // 合并多个空格
      .trim();

    if (!normalized.has(clean)) {
      normalized.set(clean, item.count);
    } else {
      // 合并计数
      normalized.set(clean, normalized.get(clean) + item.count);
    }
  }

  return Array.from(normalized.entries()).map(([tag, count]) => ({
    tag,
    count
  }));
}
```

**验证：**
- [ ] 无剩余重复项
- [ ] 计数正确合并
- [ ] 无性能问题

---

## P1（高）：改进（影响功能）

### 3. 搜索中的括号规范化

**问题：**
```
验证 \(tag\) 和 (tag) 是否被同等对待。
```

**验证方法：**
1. 准备带有 `\(emphasis\)` 标签的图像
2. 在搜索框中搜索 `(emphasis)`
3. 检查图像是否出现在结果中

**检查点：**
- [ ] 搜索 `(tag)` 也能匹配 `\(tag\)`
- [ ] 搜索 `\(tag\)` 也能匹配 `(tag)`
- [ ] 正则表达式模式不应用此规范化

**相关代码：** `web_ui.py` - `normalize_tag_for_search()`

---

### 4. ZIP 内部文件读取测试

**问题：**
```
验证 ZIP 存档内的图像能正确显示，
且元数据能正确提取。
```

**测试用例：**

#### 测试 1：基本操作
```bash
# 1. 创建测试 ZIP
zip test.zip image1.png image2.png

# 2. 扫描
python tagdb_tool.py scan --db test.db --root . --scan-zips

# 3. 验证
python tagdb_tool.py search --db test.db --q "*"
```

**检查项：**
- [ ] ZIP 内文件注册为 `test.zip!image1.png`
- [ ] 元数据已提取
- [ ] 缩略图已显示

#### 测试 2：提取功能
```
1. 在 WebUI 中打开 ZIP 内文件
2. 点击"提取并编辑"按钮
3. 验证文件管理器是否打开
4. 验证提取的文件是否存在
```

**检查项：**
- [ ] 提取按钮可见
- [ ] 点击后打开文件管理器
- [ ] 文件被提取到 extracted/ 目录
- [ ] 提取的文件已注册到数据库

#### 测试 3：大型 ZIP
```bash
# 1) 创建 1.1 GB ZIP（Zip64）
mkdir -p /tmp/tagdb_largezip_test/input
python - <<'PY'
from pathlib import Path
import base64
Path('/tmp/tagdb_largezip_test/input/sample.png').write_bytes(
    base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+X2foAAAAASUVORK5CYII=')
)
PY
truncate -s 1100M /tmp/tagdb_largezip_test/input/payload.bin
python - <<'PY'
import zipfile
from pathlib import Path
root = Path('/tmp/tagdb_largezip_test')
with zipfile.ZipFile(root / 'large_1_1gb.zip', 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as z:
    z.write(root / 'input' / 'sample.png', arcname='images/sample.png')
    z.write(root / 'input' / 'payload.bin', arcname='payload/payload.bin')
print((root / 'large_1_1gb.zip').stat().st_size)
PY

# 2) 扫描 ZIP
/usr/bin/time -f 'elapsed=%E maxrss_kb=%M' \
  python tagdb_tool.py scan --db /tmp/tagdb_largezip_test/largezip.db \
  --root /tmp/tagdb_largezip_test --recursive --scan-zips
```

**检查项：**
- [x] 内存使用在正常范围内
- [x] 扫描在可接受时间内完成（5 分钟以内）
- [x] 无错误

**测量结果（2026-02-17）：**
- ZIP 大小：`1,153,433,914 bytes`（约 1.1 GB）
- 耗时：`elapsed=0:00.14`
- 峰值 RSS：`maxrss_kb=23864`
- 数据库记录：`zip_members=1`（`large_1_1gb.zip!images/sample.png`）

---

### 5. 检查点搜索测试

**问题：**
```
验证模型名称能正确提取和搜索。
```

**测试用例：**

#### 测试 1：模型名称提取
```python
# 各格式的提取验证

# NovelAI
metadata = {"model": "nai-diffusion-3"}
→ model_name: "nai-diffusion-3"

# SD
metadata = {"Model": "animagine-xl-3.1", "Model hash": "abc123"}
→ model_name: "animagine-xl-3.1", model_hash: "abc123"

# ComfyUI
metadata = {"checkpoint": "ponyDiffusionV6XL.safetensors"}
→ model_name: "ponyDiffusionV6XL"
```

**检查项：**
- [ ] NovelAI 格式提取正常
- [ ] SD 格式提取正常
- [ ] ComfyUI 格式提取正常

#### 测试 2：搜索功能
```
1. 在 WebUI 中点击检查点输入框
2. 验证自动补全是否出现
3. 搜索 "animagine"
4. 验证是否只显示该模型的图像
```

**检查项：**
- [ ] 自动补全正常工作
- [ ] 部分匹配正常工作
- [ ] 结果按使用频率排序

---

## P2（中等）：未来工作（性能改进）

### 6. 缩略图缓存实现

**问题：**
```
ZIP 内文件的缩略图每次请求都会重新生成。
速度很慢。
```

**建议实现：**
```python
# web_ui.py
import hashlib

CACHE_DIR = Path("cache/thumbnails")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

@app.route("/api/thumbnail/<int:file_id>")
def api_thumbnail(file_id):
    # 生成缓存路径
    cache_key = hashlib.md5(f"{file_id}".encode()).hexdigest()
    cache_path = CACHE_DIR / f"{cache_key}.jpg"

    # 如果缓存版本可用则返回
    if cache_path.exists():
        return send_file(cache_path, mimetype='image/jpeg')

    # 否则生成
    thumbnail = generate_thumbnail(...)

    # 保存到缓存
    thumbnail.save(cache_path, 'JPEG', quality=85)

    return send_file(cache_path, mimetype='image/jpeg')
```

**验证：**
- [ ] 第二次访问明显更快
- [ ] 磁盘使用量可接受
- [ ] 缓存清除正常工作

---

### 7. 大规模性能测量

**测试用例：**

#### 测试 1：100,000 个文件
```bash
# 测量扫描时间
time python tagdb_tool.py scan --db large.db --root /path/to/100k --recursive

# 测量搜索时间
time python tagdb_tool.py search --db large.db --q "1girl"
```

**目标：**
- [ ] 扫描：每小时至少 50,000 个文件
- [ ] 搜索：1 秒以内（在 100,000 个文件中）

#### 测试 2：WebUI 响应性
```
1. 使用 100,000 个文件的数据库启动 WebUI
2. 执行搜索
3. 滚动浏览结果
```

**检查项：**
- [ ] 搜索结果在 3 秒内显示
- [ ] 滚动流畅
- [ ] 浏览器不卡顿

---

## 测试执行检查清单

### 环境设置
- [ ] Python 3.8+ 已安装
- [ ] 依赖已安装
- [ ] 测试数据已准备（各格式的图像）

### 功能测试
- [ ] ZIP 读取
- [ ] 多目录扫描
- [ ] 标签规范化
- [ ] 检查点搜索
- [ ] 模型过滤

### UI/UX 测试
- [ ] 布局（多分辨率）
- [ ] 暗色模式
- [ ] 键盘快捷键
- [ ] 自动补全

### 性能测试
- [ ] 10,000 个文件
- [ ] 50,000 个文件
- [ ] 100,000 个文件
- [ ] 大型 ZIP（500 MB+）

### 浏览器兼容性
- [ ] Chrome/Edge
- [ ] Firefox
- [ ] Safari

### 操作系统兼容性
- [ ] Windows 10/11
- [ ] macOS
- [ ] Linux (Ubuntu)

---

## 调试工具

### 启用日志
```bash
# 在 tagdb_tool.py 顶部添加
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 性能测量
```python
import time

start = time.time()
# ... 处理 ...
print(f"Time: {time.time() - start:.2f}s")
```

### 内存使用检查
```python
import tracemalloc

tracemalloc.start()
# ... 处理 ...
current, peak = tracemalloc.get_traced_memory()
print(f"Memory: {peak / 1024 / 1024:.2f} MB")
tracemalloc.stop()
```

---

**创建日期：** 2026-02-13
**优先级顺序：** P0 → P1 → P2
**注意：** 此检查清单创建于 v2.5.x 时期。所有列出的项目均已解决。
