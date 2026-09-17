# 5 分鐘上手 YU AI Manager

## 什麼是 YU AI Manager

YU AI Manager 是一款可統一管理 AI 生成圖片（Stable Diffusion / NovelAI / ComfyUI 等）元資料的 WebUI 應用程式。自動擷取圖片中嵌入的提示詞和模型資訊，提升標籤搜尋、瀏覽及整理的效率。

---

## 執行環境

| 項目 | 需求 |
|------|------|
| Python | 3.11 以上 |
| Node.js | 18 以上（用於前端建置） |
| OS | Windows 10/11, macOS, Linux |
| 瀏覽器 | Chrome / Firefox / Edge（建議使用最新版） |

---

## 安裝步驟

### 1. 複製儲存庫

```bash
git clone https://github.com/your-repo/yu_ai_manager.git
cd yu_ai_manager
```

### 2. 建立 Python 虛擬環境

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

### 3. 安裝 Python 相依套件

```bash
uv pip install -r requirements.txt
```

> 若尚未安裝 `uv`，請先執行 `pip install uv`。

### 4. 建置前端

```bash
pnpm install
pnpm run build
```

> 若尚未安裝 `pnpm`，請先執行 `npm install -g pnpm`。

安裝完成。

---

## 首次啟動

### 1. 啟動伺服器

```bash
# 若尚未啟用 venv，請先啟用
source venv/bin/activate        # macOS/Linux
# source venv/Scripts/activate  # Windows Git Bash

python web_ui.py
```

### 2. 以瀏覽器存取

啟動後，在瀏覽器中開啟以下網址：

```
http://localhost:5000
```

*（主畫面截圖）*

---

## 首先要做的事

### Step 1：註冊圖片資料夾進行掃描

註冊儲存 AI 生成圖片的資料夾，讀取元資料。

1. 從畫面右上方的漢堡選單開啟 **Settings**
2. 選擇 **Scan** 分頁
3. 新增掃描對象資料夾的路徑
4. 新增資料夾後，掃描會自動開始

*（掃描資料夾註冊畫面截圖）*

掃描中畫面上方會顯示進度條。圖片數量多時可能需要數分鐘，但掃描中仍可進行搜尋和瀏覽。

### Step 2：以縮圖格狀檢視瀏覽圖片

掃描完成後，主頁面會顯示縮圖格狀檢視。

*（縮圖格狀檢視截圖）*

- **捲動**：透過虛擬捲動流暢顯示大量圖片
- **排序**：使用畫面上方的排序選單切換日期順序、評分順序等
- **右鍵**：從內容選單可進行收藏或新增至合集

### Step 3：以標籤搜尋篩選圖片

在搜尋列中以逗號分隔輸入標籤，僅顯示符合條件的圖片。

```
1girl, blue_eyes, school_uniform
```

*（標籤搜尋畫面截圖）*

- **自動完成**：輸入時會顯示候選標籤
- **篩選器**：可依日期範圍、檔案格式、星評分等進行篩選
- **提示詞內搜尋**：也可搜尋提示詞的全文

### Step 4：在詳細彈窗中確認圖片資訊

點擊縮圖後，會開啟詳細彈窗。

*（詳細彈窗截圖）*

- **Info 分頁**：確認提示詞、反向提示詞、模型名稱、生成參數等
- **AI Analysis 分頁**：顯示 WD-Tagger 的自動標記結果（已設定時）
- **星評分**：可為圖片評定 1～5 星
- **收藏**：點擊愛心圖示加入收藏
- **標籤編輯**：可新增或刪除使用者標籤
- **鍵盤操作**：使用左右方向鍵切換前後圖片

---

## 常用操作總覽

| 目的 | 操作 |
|-------------|------|
| 搜尋圖片 | 在搜尋列中輸入標籤 |
| 檢視圖片詳情 | 點擊縮圖 |
| 加入收藏 | 詳細彈窗的愛心圖示，或右鍵選單 |
| 評定星級 | 詳細彈窗的星星圖示 |
| 將圖片加入合集 | 右鍵選單 > 加入合集 |
| 選取多張圖片 | Ctrl+點擊（或 Shift+點擊）進行範圍選取 |
| 掃描新資料夾 | Settings > Scan 分頁 |

---

## 下一步

熟悉基本操作後，也請嘗試以下功能。

### Settings（設定）

Settings 頁面可進行外觀自訂、時區設定、LAN 公開設定等。
詳情請參閱 [Settings 指南](settings.md)。

### Bridge（圖片生成工具連動）

與 SD WebUI / ComfyUI / NovelAI API 連動，可收發提示詞。
詳情請參閱 [Bridge 指南](bridges.md)。

### Extensions（擴充功能）

可使用 WD-Tagger（自動標記）、提示詞庫、聊天記錄檢視器等多種擴充功能。可在 Settings > Extensions 分頁中管理。

### 語意搜尋

設定 CLIP 模型後，可使用如「海邊看夕陽的女孩」等自然語言搜尋圖片。
詳情請參閱 [搜尋指南](search.md)。

### MCP 伺服器

可從 Claude Desktop 等 AI 代理程式操作 YU AI Manager。透過 stdio 傳輸進行連線。

---

## 疑難排解

遇到問題時，請參閱 [疑難排解指南](troubleshooting.md)。

常見問題：

- **找不到 `uv` 指令**：執行 `pip install uv` 進行安裝
- **找不到 `pnpm` 指令**：執行 `npm install -g pnpm` 進行安裝
- **連接埠 5000 被佔用**：以 `python web_ui.py --port 5100` 指定其他連接埠
- **圖片無法顯示**：確認掃描資料夾路徑是否正確、圖片檔案實體是否存在
