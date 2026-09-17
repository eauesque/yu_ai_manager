# SNS Share & Bluesky Monitor

## 概述

SNS Share 讓您可以直接從 YU AI Manager 將 AI 生成的圖像分享到 Bluesky 和 X (Twitter)。發帖文字透過可自訂的範本自動產生，圖像中繼資料變數會自動展開。Bluesky Monitor 新增了通知監控功能，支援 AI 驅動的分類和自動回覆。

## 設定

### 取得 Bluesky App Password

1. 登入 [bsky.app](https://bsky.app)，前往 **設定 > App Passwords**
2. 點擊 **新增 App Password**
3. 輸入名稱（例如「YU AI Manager」），點擊 **建立 App Password**
4. 複製顯示的密碼

> **注意**：App Password 只會顯示一次，請務必在關閉對話方塊前複製。請勿使用 Bluesky 主密碼。

### 在 YU AI Manager 中設定

1. 從導覽選單開啟 **Settings**
2. 切換到 **SNS** 分頁
3. 填寫以下資訊：
   - **Bluesky 控制代碼**：您的控制代碼（例如 `yourname.bsky.social`）
   - **App Password**：上述步驟取得的 App Password
   - **發帖範本**：發帖文字範本（參見[範本變數](#範本變數)）
4. 點擊 **儲存**

### 測試連線

儲存憑證後，點擊 **測試連線** 驗證 YU AI Manager 能否通過 Bluesky 驗證。測試成功後會顯示您的控制代碼和顯示名稱。

## 功能

### 分享到 Bluesky

從圖像詳情檢視直接將圖像分享到 Bluesky。

1. 開啟圖像詳情彈出視窗
2. 點擊 **SNS** 按鈕
3. 檢查並編輯產生的發帖文字
4. 點擊 **發佈到 Bluesky**

- 發帖文字從已設定的範本產生，中繼資料變數自動展開
- 圖像會自動壓縮和調整大小以符合 Bluesky 的 1 MB 上傳限制
- 貼文限制為 **300 grapheme**（超出部分會自動截斷）
- 可以選擇是否附加圖像

### 分享到 X (Twitter)

透過 Web Intent（在瀏覽器中開啟 X 的撰寫頁面）將圖像資訊分享到 X。

1. 開啟圖像詳情彈出視窗
2. 點擊 **SNS** 按鈕
3. 點擊 **分享到 X**

這會在新的瀏覽器分頁中開啟 X 的撰寫頁面，並自動填入範本產生的文字。發佈前可以編輯文字。X 不支援自動附加圖像，需要手動新增。

### Bluesky Monitor

Bluesky Monitor 輪詢您的 Bluesky 通知，並在本地排隊進行分類和回覆。

#### 通知類型

- **提及**：有人在貼文中提到了您
- **回覆**：有人回覆了您的貼文
- **引用**：有人引用了您的貼文
- **追蹤**：有人追蹤了您
- **按讚**：有人對您的貼文按讚
- **轉發**：有人轉發了您的貼文

#### 輪詢

通知以可設定的間隔自動取得（預設：30 分鐘，最小：5 分鐘）。也可以從 Settings 或透過 MCP 工具立即觸發輪詢。

#### 佇列系統

每條通知以 **pending**（待處理）狀態進入佇列，之後可以轉換為：

- **notified** -- 已報告給 MCP 客戶端（Claude Desktop）
- **dismissed** -- 標記為無需關注

#### 分類

AI 驅動的分類判斷每條通知是否需要回覆：

- **valid** -- 需要關注（真實的問題、錯誤回報、協作請求等）
- **invalid** -- 可以忽略（一般性稱讚、垃圾訊息、機器人內容等）

每種通知類型（提及、回覆、引用）都有可自訂的分類提示詞。提供預設提示詞，可隨時還原。

#### 自動回覆

對於被分類為 valid 的提及、回覆和引用，可以傳送基於範本的自動回覆：

- 在 Monitor 設定中啟用自動回覆
- 為每種通知類型自訂回覆範本
- 回覆限制為 300 grapheme

#### 自動忽略

追蹤、按讚和轉發可以自動忽略以減少佇列雜訊。每種類型可在 Settings 中獨立切換。

#### MCP 連線時通知

當 MCP 客戶端（Claude Desktop）連線時，待處理的通知會被批次報告，以便在開發過程中查看。

### Settings

SNS 設定在 Settings 頁面的 **SNS** 分頁中設定：

- **Bluesky 憑證**：控制代碼和 App Password（密碼加密儲存，顯示為遮罩）
- **發帖範本**：包含變數預留位置的範本文字
- **Monitor 設定**：
  - 輪詢間隔（分鐘）
  - 追蹤、按讚、轉發的自動忽略
  - 自動回覆啟用/停用
  - 提及、回覆、引用的分類提示詞
  - 提及、回覆、引用的自動回覆範本

## MCP 整合

SNS Share & Bluesky Monitor 提供 15 個 MCP 工具：

**分享（6 個工具）**：
- `share_to_bluesky` -- 將圖像發佈到 Bluesky
- `get_x_share_url` -- 取得 X Web Intent URL
- `get_sns_preview` -- 預覽範本展開
- `test_bluesky_connection` -- 測試 API 連線
- `get_sns_config` / `save_sns_config` -- 讀取/寫入 SNS 設定

**通知佇列（5 個工具）**：
- `bsky_get_pending_notifications` -- 取得待處理通知
- `bsky_get_notification_queue` -- 取得帶篩選器的佇列項目
- `bsky_triage_notification` -- 設定分類結果（valid/invalid）
- `bsky_send_auto_response` -- 傳送通知回覆
- `bsky_poll_notifications` -- 立即觸發輪詢

**Monitor 設定（4 個工具）**：
- `bsky_get_monitor_config` / `bsky_save_monitor_config` -- 讀取/寫入 Monitor 設定
- `bsky_get_triage_prompts` / `bsky_save_triage_prompts` -- 讀取/寫入分類提示詞和回覆範本

## 範本變數

發帖範本中可使用的變數：

| 變數 | 說明 |
|---|---|
| `{positive_short}` | 正向提示詞（前 100 個字元） |
| `{positive}` | 正向提示詞全文 |
| `{negative_short}` | 負向提示詞（前 50 個字元） |
| `{model}` | 模型名稱 |
| `{seed}` | 種子值 |
| `{steps}` | 取樣步數 |
| `{cfg}` | CFG 縮放比例 |
| `{sampler}` | 取樣器名稱 |
| `{size}` | 圖像尺寸 |
| `{tags}` | 前 5 個標籤 |
| `{filename}` | 檔案名稱 |

預設範本：`{positive_short}`

## 使用技巧

- **App Password 安全性**：請務必使用 App Password，切勿使用 Bluesky 主密碼。App Password 可隨時在 bsky.app 設定中撤銷
- **速率限制**：Bluesky API 有速率限制，請避免連續快速發帖。圖像上傳也計入速率限制
- **Grapheme 計算**：Bluesky 的 300 字限制使用 grapheme 叢集而非字元數。CJK 字元按 1 個 grapheme 計算
- **圖像壓縮**：超過 1 MB 的圖像會自動調整大小。如果圖像準備失敗，將僅以文字形式發佈
- **Monitor 輪詢間隔**：根據通知頻率設定輪詢間隔。通知量大的帳戶可使用較短間隔
- **自動忽略**：啟用追蹤、按讚和轉發的自動忽略可以集中精力處理需要回覆的通知
- **分類提示詞**：根據您的溝通風格和收到的互動類型自訂分類提示詞
