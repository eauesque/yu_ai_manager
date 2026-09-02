# 搜索

## 基本搜索

在搜索栏中以逗号分隔输入标签。

```
1girl, blue_eyes, school_uniform
```

## 搜索筛选器

| 筛选器 | 说明 |
|---------|------|
| 日期范围 | 以起始日～结束日进行筛选 |
| 文件格式 | PNG / WebP / JPG / GIF |
| 评分 | 以 1～5 星进行筛选 |
| 收藏 | 仅显示已加入收藏的项目 |
| 合集 | 仅显示特定合集内的项目 |

## 提示词内搜索

使用「in_prompt」字段可对图片的提示词文本进行全文搜索。
若 FTS (Full-Text Search) 已启用，可进行高速搜索。

## 排序方式

| 排序 | 说明 |
|--------|------|
| date | 注册日（最新优先） |
| date_old | 注册日（最旧优先） |
| folder | 文件夹顺序 |
| path | 路径顺序 |
| random | 随机 |
| rating_desc | 评分（由高到低） |
| rating_asc | 评分（由低到高） |

## 语义搜索

若已设置 Hailo-10H 或 ONNX CLIP 模型，可使用自然语言搜索图片。
请使用搜索栏右侧的语义搜索按钮。

### 使用 FAISS 加速（推荐）

语义搜索默认使用 NumPy 进行暴力搜索，
**安装 FAISS 后可大幅提升速度**。

| 图库规模 | NumPy（默认） | FAISS（推荐） |
|-------------|-------------------|-------------|
| 1 万件以下 | 数十 ms | 数 ms |
| 10 万件 | 1～3 秒 | 数十 ms |
| 100 万件以上 | 10 秒以上 | 100 ms 以下 |

FAISS 会根据搜索对象的规模自动选择最优索引：
- **5 万件以下**：IndexFlatIP（精确全量搜索，速度已足够快）
- **5 万件以上**：IndexIVFFlat（近似最近邻搜索，大规模也能高速处理）

#### 安装方式

```bash
# 先激活 venv 再安装
source venv/bin/activate

# x86_64 (Intel/AMD) — 可直接用 pip 安装
uv pip install faiss-cpu

# Raspberry Pi 5 (aarch64) — pip 无法安装时
# 方法 1：通过 conda
conda install -c conda-forge faiss-cpu

# 方法 2：从源代码构建
# https://github.com/facebookresearch/faiss/blob/main/INSTALL.md
```

安装后只需重新启动服务器即可自动检测。
若启动日志中显示以下信息，表示 FAISS 已启用：

```
FAISS x.x.x detected — using accelerated vector search
```

即使未安装 FAISS，仍可使用 NumPy 正常运行。
