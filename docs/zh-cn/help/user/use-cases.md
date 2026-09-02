# 使用案例集

汇整 YU AI Manager 的代表性用法，以「遇到这种情况就这样用」的形式呈现。

---

## 1. 想整理大量的 AI 图片

用 NovelAI 或 Stable Diffusion 生成的图片已累积数千张在文件夹中，回顾起来很费力时。

### 步骤

1. 在 **Settings > Scan** 选项卡注册扫描文件夹（可注册多个）
2. 添加文件夹后，扫描会自动开始。也可扫描 ZIP/7z 内的图片
3. 扫描完成后，在主页面以标签搜索（例：`1girl, blue_eyes`）或排序筛选图片
4. 选取喜欢的图片，右键 > **加入合集** 进行分组
5. 随时可从合集侧边栏以分组为单位浏览

### 提示

- 扫描中仍可进行搜索和浏览（使用只读 DB 连接，不会产生冲突）
- 启用 Auto Scan Watcher 扩展功能后，可自动检测文件夹中新增的文件
- 即使是 100 万件规模，也能通过 Keyset Pagination 高速翻页

---

## 2. 想找出以特定提示词生成的图片

「那时候的构图提示词是什么来着」想不起来时。

### 步骤

1. 将搜索栏的搜索对象切换为 **in_prompt**
2. 输入记得的关键字（例：`cherry blossom`）进行搜索
3. 使用正则表达式可更灵活地筛选（例：`masterpiece.*cherry`）

### 提示

- 若 FTS（全文搜索）已启用，即使大量提示词也能高速搜索
- 搭配日期范围或文件格式筛选器使用效果更佳
- 将排序设为 `random` 可重新发现被遗忘的图片

---

## 3. 想找出类似构图的图片

「这张图片类似氛围的图片应该还有其他的」想要搜索时。

### 方法 A：pHash 相似搜索（构图、色调）

1. 打开图片的详情弹窗
2. 点击 **搜索相似图片** 按钮
3. 以 pHash（感知哈希）搜索构图相近的图片，结果会显示在侧边面板

### 方法 B：CLIP 语义搜索（语义、概念）

1. 点击搜索栏右侧的 **语义搜索** 按钮
2. 以自然语言输入描述（例：「站在海边的少女」「夕阳下的街景」）
3. CLIP 理解图片的语义后，按相似度排序显示

### 提示

- 语义搜索需要事先设置 CLIP 模型（ONNX 或 Hailo-10H）
- 大规模图库（10 万件以上）安装 `faiss-cpu` 可大幅提升搜索速度
- pHash 擅长构图比对，CLIP 擅长语义相似性，两者各有所长。都试试看会有更多发现

---

## 4. 想管理收藏图片

想从大量图片中快速回顾杰作时。

### 步骤

1. 在图片卡片或详情弹窗点击 **爱心按钮** 加入收藏
2. 在详情弹窗设置 **星级评分**（1～5 级）评估品质
3. 在 **备注** 中留下自由笔记（例：「重绘候选」「已发布至 SNS」）
4. 以搜索筛选器筛选「仅收藏」「4 星以上」等条件

### 提示

- 以评分排序（`rating_desc`）可集中浏览高评分图片
- 也可从上下文菜单（右键）操作收藏和评分

---

## 5. 想将图片的提示词发送至其他工具

想重新利用过去制作图片的提示词，在其他工具中再生成或制作变体时。

### 步骤

1. 打开图片的详情弹窗，确认提示词信息
2. 点击 **发送至 SD WebUI** / **发送至 ComfyUI** / **发送至 NAI** 按钮
3. Bridge 页面会打开，提示词会自动输入
4. 根据需要编辑提示词，在生成工具端执行

### 提示

- SD <-> NAI 之间的 `()` 和 `{}` 权重语法会自动转换
- Bridge 工具栏的 **QP** 按钮可一键插入品质预设
- 也可从 Prompt Converter 或 Prompt Simulator 发送至各 Bridge

---

## 6. 想浏览 ZIP/7z 压缩包内的图片

下载的图片集被打包成 ZIP，想在不解压的情况下确认内容时。

### 步骤

1. 在 Settings > Scan 中注册包含 ZIP/7z 文件的文件夹
2. 在扫描选项中启用 **ZIP/7z 内扫描**
3. 扫描完成后，压缩包内的图片可在主页面像普通图片一样搜索和浏览
4. 详情弹窗中会显示压缩包名称和压缩包内路径

### 提示

- 压缩包内的视频会展开至临时缓存（LRU 2GB），因此重复播放也很流畅
- 也支持嵌套 ZIP（ZIP-in-ZIP）
- 也可使用批量下载功能将压缩包内的图片重新打包成新的 ZIP

---

## 7. 想与团队或家人分享图片

想让同一 Wi-Fi 内的其他设备（手机、平板等）浏览图片时。

### 步骤

1. 在 **Settings > Server** 选项卡将「LAN Access」设为 ON
2. 设置 **PIN 码**（LAN 公开时为必需项）
3. 重新启动服务器
4. 从 LAN 内的其他设备访问 `http://<服务器 IP>:5000`
5. 输入 PIN 登录

### 提示

- 发放 **LAN Share 令牌**（`/s/` 路径）可分享无需 PIN 的访客访问链接
- 服务器界面会显示二维码，用手机相机扫描即可访问
- 也支持通过反向代理的 Trusted Proxy 认证

---

## 8. 想自动打标签

手动打标签很麻烦，想让 AI 分析图片自动赋予标签时。

### 方法 A：WD-Tagger（高速、标签专用）

1. 在 **Settings** 下载 WD-Tagger ONNX 模型
2. 从 Tools 页面或详情弹窗点击 **执行 WD-Tagger**
3. Danbooru 风格的标签会自动赋予

### 方法 B：AI Analysis（自然语言、高精度）

1. 在 **Settings > AI Analysis** 添加 Ollama 或 OpenAI 兼容服务器
2. 从图片详情弹窗的 **AI Analysis 选项卡** 执行分析
3. 会生成自然语言的图片描述

### 提示

- WD-Tagger 也支持与 VLM 引擎（OpenAI API 兼容）的复合模式
- NSFW 过滤和标签规范化等后处理会自动应用
- 也支持将标签写入 XMP 元数据，方便与其他工具联动

---

## 9. 想查看统计和报表

想掌握自己图片库的趋势和增长时。

### 步骤

1. 从导航栏打开 **Stats** 页面，确认整体统计
2. 在 **Monthly Report** 页面浏览月度详细报表
   - 月度文件数、与上月对比、TOP 20 标签、新标签、来源分布、每日计数
3. 在 **Trophies** 区块确认成就奖杯

### 提示

- 奖杯分为 6 个类别（milestone / streak / diversity / source / hidden）、4 个等级（bronze～platinum）逐步解锁
- 正确设置时区（Settings > Appearance）可使每日统计更精确

---

## 10. 想通过 MCP 与 AI 代理联动

想从 Claude Desktop 或其他支持 MCP 的 AI 工具操作图片库时。

### 步骤

1. 在 MCP 客户端（Claude Desktop 等）的设置中注册 YU AI Manager 的 MCP 服务器
   ```json
   {
     "command": "python",
     "args": ["-m", "mcp_server"],
     "env": { "YU_DB": "./tags.db" }
   }
   ```
2. 以自然语言指示 AI「搜索图片」「加入收藏」等
3. 可使用 `search_images`、`add_favorite`、`trigger_scan` 等 60 种以上的工具

### 提示

- 从 MCP 客户端扩展功能也可连接外部 MCP 服务器（stdio / SSE / Streamable HTTP）
- 设置 API Key 认证后，也可从外部工具直接调用 REST API（无需 CSRF 头）
- 使用 Hailo GenAI 扩展功能，也可通过 OpenAI SDK 兼容端点进行联动

---

## 11. 将 Hailo-10H 作为 OpenAI 兼容服务器使用

在配备 Hailo-10H NPU 的环境中，可将其作为本地 AI 服务器使用，完全兼容 OpenAI SDK。Open WebUI、Continue.dev 及自定义脚本等外部工具可直接使用 Hailo 的 LLM / VLM / 语音识别 / CLIP 嵌入向量功能。

### 支持的端点

| 端点 | 功能 | 对应的 OpenAI API |
|---|---|---|
| `GET /ext/hailo-genai/v1/models` | 列出已下载的模型 | List Models |
| `POST /ext/hailo-genai/v1/chat/completions` | 文本生成与图片理解 (VLM) | Chat Completions |
| `POST /ext/hailo-genai/v1/audio/transcriptions` | 语音转文字 | Audio Transcriptions |
| `POST /ext/hailo-genai/v1/embeddings` | 文本转向量 (CLIP) | Embeddings |

### 步骤

1. 确认 **Extensions > GenAI** 页面中 Hailo GenAI 扩展功能已启用
2. 下载所需模型（LLM: `qwen2.5-1.5b-chat` 等，VLM: `llava-v1.6-vicuna-7b` 等）
3. 在外部工具的连接设置中将 **Base URL** 设为：
   ```
   http://localhost:5000/ext/hailo-genai/v1
   ```
   （端口号请根据 YU AI Manager 的启动配置调整）
4. 本地访问无需 API Key。若工具要求必须填入，可输入任意值（例如 `dummy`）

### 外部工具连接示例

#### Open WebUI

在 Settings > Connections > OpenAI API 添加：
- **URL**: `http://localhost:5000/ext/hailo-genai/v1`
- **API Key**: `dummy`

#### Continue.dev（VS Code AI 助手）

在 `~/.continue/config.json` 中添加：
```json
{
  "models": [{
    "title": "Hailo Qwen2.5",
    "provider": "openai",
    "model": "qwen2.5-1.5b-chat",
    "apiBase": "http://localhost:5000/ext/hailo-genai/v1",
    "apiKey": "dummy"
  }]
}
```

#### Python（OpenAI SDK）

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:5000/ext/hailo-genai/v1",
    api_key="dummy",
)

# 文本生成
res = client.chat.completions.create(
    model="qwen2.5-1.5b-chat",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(res.choices[0].message.content)

# 语音转文字
res = client.audio.transcriptions.create(
    model="whisper-1",
    file=open("audio.wav", "rb"),
)

# 文本嵌入向量 (CLIP)
res = client.embeddings.create(
    model="clip",
    input="a girl standing by the sea",
)
print(len(res.data[0].embedding))  # 512
```

### 支持的参数

- **Chat Completions**: `model`, `messages`, `stream`, `temperature` (0-2), `max_tokens` (64-2048)
- **Audio Transcriptions**: `model`, `file`, `language`, `response_format` (json / text / verbose_json)
- **Embeddings**: `model`, `input`（字符串或字符串数组）
- **模型别名**: `whisper-1` → whisper-base, `clip` / `text-embedding-clip` → clip-vit-b-16

### 注意事项

- **设备排他性**: Hailo-10H 同时只能加载 1 个 GenAI 模型（LLM 或 VLM 或 S2T），可从 GenAI 页面切换模式
- **图片 URL 限制**: 基于安全考虑，`http://` 图片 URL 会被拦截。请使用 `data:image/...;base64,...` 格式或 YU AI Manager 的 `file_id:` 格式
- **CLIP 嵌入向量**: 仅支持文本→向量转换。图片→向量请通过 `/api/semantic/` 端点使用
- **音频格式**: WAV 以外的格式（MP3、M4A、OGG 等）需要安装 ffmpeg
- **`usage` 字段**: Token 计数始终返回 0（Hailo NPU 的限制）
