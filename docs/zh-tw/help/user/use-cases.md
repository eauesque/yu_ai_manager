# 使用案例集

彙整 YU AI Manager 的代表性用法，以「遇到這種情況就這樣用」的形式呈現。

---

## 1. 想整理大量的 AI 圖片

用 NovelAI 或 Stable Diffusion 生成的圖片已累積數千張在資料夾中，回顧起來很費力時。

### 步驟

1. 在 **Settings > Scan** 分頁註冊掃描資料夾（可註冊多個）
2. 新增資料夾後，掃描會自動開始。也可掃描 ZIP/7z 內的圖片
3. 掃描完成後，在主頁面以標籤搜尋（例：`1girl, blue_eyes`）或排序篩選圖片
4. 選取喜歡的圖片，右鍵 > **加入合集** 進行分組
5. 隨時可從合集側邊欄以群組為單位瀏覽

### 提示

- 掃描中仍可進行搜尋和瀏覽（使用唯讀 DB 連線，不會產生衝突）
- 啟用 Auto Scan Watcher 擴充功能後，可自動偵測資料夾中新增的檔案
- 即使是 100 萬件規模，也能透過 Keyset Pagination 高速翻頁

---

## 2. 想找出以特定提示詞生成的圖片

「那時候的構圖提示詞是什麼來著」想不起來時。

### 步驟

1. 將搜尋列的搜尋對象切換為 **in_prompt**
2. 輸入記得的關鍵字（例：`cherry blossom`）進行搜尋
3. 使用正規表示式可更靈活地篩選（例：`masterpiece.*cherry`）

### 提示

- 若 FTS（全文搜尋）已啟用，即使大量提示詞也能高速搜尋
- 搭配日期範圍或檔案格式篩選器使用效果更佳
- 將排序設為 `random` 可重新發現被遺忘的圖片

---

## 3. 想找出類似構圖的圖片

「這張圖片類似氛圍的圖片應該還有其他的」想要搜尋時。

### 方法 A：pHash 相似搜尋（構圖、色調）

1. 開啟圖片的詳細彈窗
2. 點擊 **搜尋相似圖片** 按鈕
3. 以 pHash（感知雜湊）搜尋構圖相近的圖片，結果會顯示在側邊面板

### 方法 B：CLIP 語意搜尋（語意、概念）

1. 點擊搜尋列右側的 **語意搜尋** 按鈕
2. 以自然語言輸入描述（例：「站在海邊的少女」「夕陽下的街景」）
3. CLIP 理解圖片的語意後，按相似度排序顯示

### 提示

- 語意搜尋需要事先設定 CLIP 模型（ONNX 或 Hailo-10H）
- 大規模圖庫（10 萬件以上）安裝 `faiss-cpu` 可大幅提升搜尋速度
- pHash 擅長構圖比對，CLIP 擅長語意相似性，兩者各有所長。都試試看會有更多發現

---

## 4. 想管理收藏圖片

想從大量圖片中快速回顧傑作時。

### 步驟

1. 在圖片卡片或詳細彈窗點擊 **愛心按鈕** 加入收藏
2. 在詳細彈窗設定 **星級評分**（1～5 級）評估品質
3. 在 **備註** 中留下自由筆記（例：「重繪候選」「已發布至 SNS」）
4. 以搜尋篩選器篩選「僅收藏」「4 星以上」等條件

### 提示

- 以評分排序（`rating_desc`）可集中瀏覽高評分圖片
- 也可從內容選單（右鍵）操作收藏和評分

---

## 5. 想將圖片的提示詞傳送至其他工具

想重新利用過去製作圖片的提示詞，在其他工具中再生成或製作變體時。

### 步驟

1. 開啟圖片的詳細彈窗，確認提示詞資訊
2. 點擊 **傳送至 SD WebUI** / **傳送至 ComfyUI** / **傳送至 NAI** 按鈕
3. Bridge 頁面會開啟，提示詞會自動輸入
4. 視需要編輯提示詞，在生成工具端執行

### 提示

- SD <-> NAI 之間的 `()` 和 `{}` 權重語法會自動轉換
- Bridge 工具列的 **QP** 按鈕可一鍵插入品質預設
- 也可從 Prompt Converter 或 Prompt Simulator 傳送至各 Bridge

---

## 6. 想瀏覽 ZIP/7z 壓縮檔內的圖片

下載的圖片集被打包成 ZIP，想在不解壓縮的情況下確認內容時。

### 步驟

1. 在 Settings > Scan 中註冊包含 ZIP/7z 檔案的資料夾
2. 在掃描選項中啟用 **ZIP/7z 內掃描**
3. 掃描完成後，壓縮檔內的圖片可在主頁面像普通圖片一樣搜尋和瀏覽
4. 詳細彈窗中會顯示壓縮檔名稱和壓縮檔內路徑

### 提示

- 壓縮檔內的影片會展開至暫存快取（LRU 2GB），因此重複播放也很流暢
- 也支援巢狀 ZIP（ZIP-in-ZIP）
- 也可使用批次下載功能將壓縮檔內的圖片重新打包成新的 ZIP

---

## 7. 想與團隊或家人分享圖片

想讓同一 Wi-Fi 內的其他裝置（手機、平板等）瀏覽圖片時。

### 步驟

1. 在 **Settings > Server** 分頁將「LAN Access」設為 ON
2. 設定 **PIN 碼**（LAN 公開時為必要項目）
3. 重新啟動伺服器
4. 從 LAN 內的其他裝置存取 `http://<伺服器 IP>:5000`
5. 輸入 PIN 登入

### 提示

- 發行 **LAN Share 權杖**（`/s/` 路徑）可分享無需 PIN 的訪客存取連結
- 伺服器畫面會顯示 QR code，用手機相機掃描即可存取
- 也支援透過反向代理的 Trusted Proxy 認證

---

## 8. 想自動標記

手動標記很麻煩，想讓 AI 分析圖片自動賦予標籤時。

### 方法 A：WD-Tagger（高速、標籤專用）

1. 在 **Settings** 下載 WD-Tagger ONNX 模型
2. 從 Tools 頁面或詳細彈窗點擊 **執行 WD-Tagger**
3. Danbooru 風格的標籤會自動賦予

### 方法 B：AI Analysis（自然語言、高精度）

1. 在 **Settings > AI Analysis** 新增 Ollama 或 OpenAI 相容伺服器
2. 從圖片詳細彈窗的 **AI Analysis 分頁** 執行分析
3. 會生成自然語言的圖片描述

### 提示

- WD-Tagger 也支援與 VLM 引擎（OpenAI API 相容）的複合模式
- NSFW 過濾和標籤正規化等後處理會自動套用
- 也支援將標籤寫入 XMP 元資料，方便與其他工具連動

---

## 9. 想查看統計和報表

想掌握自己圖片庫的趨勢和成長時。

### 步驟

1. 從導覽列開啟 **Stats** 頁面，確認整體統計
2. 在 **Monthly Report** 頁面瀏覽月度詳細報表
   - 月度檔案數、與前月比較、TOP 20 標籤、新標籤、來源分布、每日計數
3. 在 **Trophies** 區塊確認成就獎盃

### 提示

- 獎盃分為 6 個類別（milestone / streak / diversity / source / hidden）、4 個等級（bronze～platinum）逐步解鎖
- 正確設定時區（Settings > Appearance）可使每日統計更精確

---

## 10. 想透過 MCP 與 AI 代理程式連動

想從 Claude Desktop 或其他支援 MCP 的 AI 工具操作圖片庫時。

### 步驟

1. 在 MCP 用戶端（Claude Desktop 等）的設定中註冊 YU AI Manager 的 MCP 伺服器
   ```json
   {
     "command": "python",
     "args": ["-m", "mcp_server"],
     "env": { "YU_DB": "./tags.db" }
   }
   ```
2. 以自然語言指示 AI「搜尋圖片」「加入收藏」等
3. 可使用 `search_images`、`add_favorite`、`trigger_scan` 等 60 種以上的工具

### 提示

- 從 MCP 用戶端擴充功能也可連接外部 MCP 伺服器（stdio / SSE / Streamable HTTP）
- 設定 API Key 認證後，也可從外部工具直接呼叫 REST API（無需 CSRF 標頭）
- 使用 Hailo GenAI 擴充功能，也可透過 OpenAI SDK 相容端點進行連動

---

## 11. 將 Hailo-10H 當作 OpenAI 相容伺服器使用

在配備 Hailo-10H NPU 的環境中，可將其作為本機 AI 伺服器使用，完全相容 OpenAI SDK。Open WebUI、Continue.dev 及自訂腳本等外部工具可直接使用 Hailo 的 LLM / VLM / 語音辨識 / CLIP 嵌入向量功能。

### 支援的端點

| 端點 | 功能 | 對應的 OpenAI API |
|---|---|---|
| `GET /ext/hailo-genai/v1/models` | 列出已下載的模型 | List Models |
| `POST /ext/hailo-genai/v1/chat/completions` | 文字生成與圖片理解 (VLM) | Chat Completions |
| `POST /ext/hailo-genai/v1/audio/transcriptions` | 語音轉文字 | Audio Transcriptions |
| `POST /ext/hailo-genai/v1/embeddings` | 文字轉向量 (CLIP) | Embeddings |

### 步驟

1. 確認 **Extensions > GenAI** 頁面中 Hailo GenAI 擴充功能已啟用
2. 下載所需模型（LLM: `qwen2.5-1.5b-chat` 等，VLM: `llava-v1.6-vicuna-7b` 等）
3. 在外部工具的連線設定中將 **Base URL** 設為：
   ```
   http://localhost:5000/ext/hailo-genai/v1
   ```
   （埠號請依 YU AI Manager 的啟動設定調整）
4. 本機存取無需 API Key。若工具要求必須填入，可輸入任意值（例如 `dummy`）

### 外部工具連線範例

#### Open WebUI

在 Settings > Connections > OpenAI API 新增：
- **URL**: `http://localhost:5000/ext/hailo-genai/v1`
- **API Key**: `dummy`

#### Continue.dev（VS Code AI 助手）

在 `~/.continue/config.json` 中新增：
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

# 文字生成
res = client.chat.completions.create(
    model="qwen2.5-1.5b-chat",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(res.choices[0].message.content)

# 語音轉文字
res = client.audio.transcriptions.create(
    model="whisper-1",
    file=open("audio.wav", "rb"),
)

# 文字嵌入向量 (CLIP)
res = client.embeddings.create(
    model="clip",
    input="a girl standing by the sea",
)
print(len(res.data[0].embedding))  # 512
```

### 支援的參數

- **Chat Completions**: `model`, `messages`, `stream`, `temperature` (0-2), `max_tokens` (64-2048)
- **Audio Transcriptions**: `model`, `file`, `language`, `response_format` (json / text / verbose_json)
- **Embeddings**: `model`, `input`（字串或字串陣列）
- **模型別名**: `whisper-1` → whisper-base, `clip` / `text-embedding-clip` → clip-vit-b-16

### 注意事項

- **裝置排他性**: Hailo-10H 同時只能載入 1 個 GenAI 模型（LLM 或 VLM 或 S2T），可從 GenAI 頁面切換模式
- **圖片 URL 限制**: 基於安全考量，`http://` 圖片 URL 會被封鎖。請使用 `data:image/...;base64,...` 格式或 YU AI Manager 的 `file_id:` 格式
- **CLIP 嵌入向量**: 僅支援文字→向量轉換。圖片→向量請透過 `/api/semantic/` 端點使用
- **音訊格式**: WAV 以外的格式（MP3、M4A、OGG 等）需要安裝 ffmpeg
- **`usage` 欄位**: Token 計數一律回傳 0（Hailo NPU 的限制）
