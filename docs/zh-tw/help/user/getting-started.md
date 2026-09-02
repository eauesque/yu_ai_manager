# 入門指南

YU AI Manager 是一款用於管理 AI 生成圖片元資料的 WebUI 應用程式。

## 安裝

### 系統需求

- Python 3.11 以上
- Node.js 18 以上（用於前端建置）

### 設定步驟

```bash
# 複製儲存庫
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager

# 安裝 uv（僅首次）
pip install uv

# 建立 Python 虛擬環境並安裝相依套件
python3 -m venv venv
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
uv pip install -r requirements.txt

# 建置前端
pnpm install
pnpm run build

# 選用：加速語意搜尋（適用於大型圖庫）
uv pip install faiss-cpu
```

## 啟動方式

```bash
source venv/bin/activate  # Windows Git Bash: source venv/Scripts/activate
python web_ui.py --db ./tags.db --port 5000
```

請在瀏覽器中開啟 `http://localhost:5000`。

## 初次設定

1. **註冊掃描資料夾**：前往 Settings > Scan 分頁，新增儲存 AI 圖片的資料夾
2. **執行掃描**：新增資料夾後，掃描將自動開始
3. **瀏覽圖片**：在主頁面上搜尋和瀏覽圖片

## LAN 公開

若要從其他裝置存取：

1. 前往 Settings > Server 分頁，將「LAN Access」設為 ON
2. 設定 PIN 認證（LAN 公開時為必要項目）
3. 重新啟動伺服器

LAN 內的其他裝置可透過 `http://<伺服器 IP>:5000` 存取。
