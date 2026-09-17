# 入门指南

YU AI Manager 是一款用于管理 AI 生成图片元数据的 WebUI 应用程序。

## 安装

### 系统要求

- Python 3.11 以上
- Node.js 18 以上（用于前端构建）

### 设置步骤

```bash
# 克隆仓库
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager

# 安装 uv（仅首次）
pip install uv

# 创建 Python 虚拟环境并安装依赖包
python3 -m venv venv
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
uv pip install -r requirements.txt

# 构建前端
pnpm install
pnpm run build

# 可选：加速语义搜索（适用于大规模图库）
uv pip install faiss-cpu
```

## 启动方式

```bash
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
python web_ui.py --db ./tags.db --port 5000
```

请在浏览器中打开 `http://localhost:5000`。

## 初次设置

1. **注册扫描文件夹**：前往 Settings > Scan 选项卡，添加存放 AI 图片的文件夹
2. **执行扫描**：添加文件夹后，扫描将自动开始
3. **浏览图片**：在主页面上搜索和浏览图片

## LAN 公开

若要从其他设备访问：

1. 前往 Settings > Server 选项卡，将「LAN Access」设为 ON
2. 设置 PIN 认证（LAN 公开时为必需项）
3. 重新启动服务器

LAN 内的其他设备可通过 `http://<服务器 IP>:5000` 访问。
