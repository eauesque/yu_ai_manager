# 5 分钟上手 YU AI Manager

## 什么是 YU AI Manager

YU AI Manager 是一款可统一管理 AI 生成图片（Stable Diffusion / NovelAI / ComfyUI 等）元数据的 WebUI 应用程序。自动提取图片中嵌入的提示词和模型信息，提升标签搜索、浏览及整理的效率。

---

## 运行环境

| 项目 | 要求 |
|------|------|
| Python | 3.11 以上 |
| Node.js | 18 以上（用于前端构建） |
| OS | Windows 10/11, macOS, Linux |
| 浏览器 | Chrome / Firefox / Edge（建议使用最新版） |

---

## 安装步骤

### 1. 克隆仓库

```bash
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager
```

### 2. 创建 Python 虚拟环境

**macOS / Linux：**

```bash
python3 -m venv venv
source venv/bin/activate
```

**Windows (PowerShell)：**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (Git Bash)：**

```bash
python -m venv venv
source venv/Scripts/activate
```

### 3. 安装 Python 依赖包

```bash
uv pip install -r requirements.txt
```

> 若尚未安装 `uv`，请先执行 `pip install uv`。

### 4. 构建前端

```bash
pnpm install
pnpm run build
```

> 若尚未安装 `pnpm`，请先执行 `npm install -g pnpm`。

安装完成。

---

## 首次启动

### 1. 启动服务器

```bash
# 若尚未激活 venv，请先激活
source venv/bin/activate        # macOS/Linux
# source venv/Scripts/activate  # Windows Git Bash

python web_ui.py
```

### 2. 以浏览器访问

启动后，在浏览器中打开以下网址：

```
http://localhost:5000
```

*（主界面截图）*

---

## 首先要做的事

### Step 1：注册图片文件夹进行扫描

注册存放 AI 生成图片的文件夹，读取元数据。

1. 从界面右上方的汉堡菜单打开 **Settings**
2. 选择 **Scan** 选项卡
3. 添加扫描对象文件夹的路径
4. 添加文件夹后，扫描会自动开始

*（扫描文件夹注册界面截图）*

扫描中界面上方会显示进度条。图片数量多时可能需要几分钟，但扫描中仍可进行搜索和浏览。

### Step 2：以缩略图网格浏览图片

扫描完成后，主页面会显示缩略图网格。

*（缩略图网格显示截图）*

- **滚动**：通过虚拟滚动流畅显示大量图片
- **排序**：使用界面上方的排序菜单切换日期顺序、评分顺序等
- **右键**：从上下文菜单可进行收藏或添加至合集

### Step 3：以标签搜索筛选图片

在搜索栏中以逗号分隔输入标签，仅显示符合条件的图片。

```
1girl, blue_eyes, school_uniform
```

*（标签搜索界面截图）*

- **自动补全**：输入时会显示候选标签
- **筛选器**：可按日期范围、文件格式、星评分等进行筛选
- **提示词内搜索**：也可搜索提示词的全文

### Step 4：在详情弹窗中确认图片信息

点击缩略图后，会打开详情弹窗。

*（详情弹窗截图）*

- **Info 选项卡**：确认提示词、反向提示词、模型名称、生成参数等
- **AI Analysis 选项卡**：显示 WD-Tagger 的自动标记结果（已设置时）
- **星评分**：可为图片评定 1～5 星
- **收藏**：点击爱心图标加入收藏
- **标签编辑**：可添加或删除用户标签
- **键盘操作**：使用左右方向键切换前后图片

---

## 常用操作总览

| 目的 | 操作 |
|-------------|------|
| 搜索图片 | 在搜索栏中输入标签 |
| 查看图片详情 | 点击缩略图 |
| 加入收藏 | 详情弹窗的爱心图标，或右键菜单 |
| 评定星级 | 详情弹窗的星星图标 |
| 将图片加入合集 | 右键菜单 > 加入合集 |
| 选取多张图片 | Ctrl+点击（或 Shift+点击）进行范围选取 |
| 扫描新文件夹 | Settings > Scan 选项卡 |

---

## 下一步

熟悉基本操作后，也请尝试以下功能。

### Settings（设置）

Settings 页面可进行外观自定义、时区设置、LAN 公开设置等。
详情请参阅 [Settings 指南](settings.md)。

### Bridge（图片生成工具联动）

与 SD WebUI / ComfyUI / NovelAI API 联动，可收发提示词。
详情请参阅 [Bridge 指南](bridges.md)。

### Extensions（扩展功能）

可使用 WD-Tagger（自动标记）、提示词库、聊天记录查看器等多种扩展功能。可在 Settings > Extensions 选项卡中管理。

### 语义搜索

设置 CLIP 模型后，可使用如「海边看夕阳的女孩」等自然语言搜索图片。
详情请参阅 [搜索指南](search.md)。

### MCP 服务器

可从 Claude Desktop 等 AI 代理操作 YU AI Manager。通过 stdio 传输进行连接。

---

## 故障排除

遇到问题时，请参阅 [故障排除指南](troubleshooting.md)。

常见问题：

- **找不到 `uv` 命令**：执行 `pip install uv` 进行安装
- **找不到 `pnpm` 命令**：执行 `npm install -g pnpm` 进行安装
- **端口 5000 被占用**：以 `python web_ui.py --port 5100` 指定其他端口
- **图片无法显示**：确认扫描文件夹路径是否正确、图片文件实体是否存在
