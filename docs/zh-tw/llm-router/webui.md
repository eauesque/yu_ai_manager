# LLM Router WebUI

透過 `/llm-router` 開啟的管理儀表板。可確認已註冊後端的狀態，並進行停用/啟用操作。

---

## 畫面架構

```
┌─────────────────────────────────────┐
│  🤖 LLM Router          [Refresh All] │
├─────────┬─────────┬────────┬─────────┤
│Backends │ Enabled │ Models │ Aliases │  ← 摘要卡片
├─────────┴─────────┴────────┴─────────┤
│  Backends 表格                       │
├───────────────────────────────────────┤
│  Routing Aliases 表格                │
└───────────────────────────────────────┘
```

### 摘要卡片（4 張）

| 卡片 | 內容 |
|---|---|
| **Backends** | 已註冊到目錄的後端總數 |
| **Enabled** | 未被停用（disabled）的後端數量 |
| **Models** | 所有後端公開的模型合計數 |
| **Routing aliases** | 設定檔中定義的別名數量 |

卡片的值在頁面載入時透過 `/api/llm_router/status` 取得並自動繪製。

---

## 後端一覽表格

每一列對應一個實體後端（Ollama 實例等）。

### 各欄說明

| 欄位 | 說明 |
|---|---|
| **Alias** | 用於識別後端的唯一簡稱（例：`ollama-mac`、`mdns-pi5-hailo`）。作為路由設定及別名解析的鍵值 |
| **Base URL** | 後端的 OpenAI 相容端點基礎 URL（例：`http://192.168.1.10:11434`） |
| **Status** | 與後端的連線狀態。詳見下方說明 |
| **SLO** | 後端的資源負載狀態（`vision_idle` / `vision_active` / `unknown`）。用於 Hailo Vision 系列後端 |
| **Models** | 上次 probe 取得的模型數量。部分實作可點擊展開詳細列表 |
| **Last Seen** | 上次確認正常回應的日期時間（ISO 8601）。`null` 表示從未成功 |
| **Actions** | 個別操作按鈕（詳見下方） |

### Status 的含義

| 值 | 意義 |
|---|---|
| `ready` | 上次 probe 成功，已取得模型列表 |
| `unreachable` | 連線逾時或發生錯誤 |
| `unknown` | 尚未執行 probe（例如剛啟動時） |
| `probing` | 正在執行 probe（Refresh 期間 UI 會短暫顯示） |

> **提示**：`unreachable` 的後端會從路由對象中排除，但仍保留在目錄中。網路恢復後執行 Refresh All 或個別 Refresh 即可回到 `ready`。

### SLO 的含義

| 值 | 意義 |
|---|---|
| `vision_idle` | Vision 任務閒置中。LLM 負載較低 |
| `vision_active` | Vision 任務運行中。LLM Router 可能優先使用其他後端 |
| `unknown` | 無法取得 SLO 資訊（非 Hailo 後端，或取得失敗） |

---

## Refresh All 按鈕

點擊畫面右上的 **Refresh All** 後，會對所有後端強制執行 probe，更新模型列表與狀態。

- 執行期間按鈕會被停用，完成後重新繪製
- 內部動作：呼叫 `POST /api/llm_router/refresh`（無 body），執行所有後端的 `discover_all`
- 個別後端的 Refresh 可從 Actions 欄的 Refresh 按鈕（視實作而定）執行

---

## 個別後端的 disable / enable

### 操作步驟

1. 確認後端一覽表格的 **Actions** 欄
2. 在要停用的後端列點擊 **Disable** 按鈕
3. 按鈕變為 **Enable**，該列會變灰
4. 要重新啟用時點擊 **Enable**

### 行為與永久化

- 操作會立即反映到記憶體中的目錄
- 同時以原子寫入方式儲存至 `data/llm_router_state.json`

  ```json
  {
    "version": 1,
    "disabled_aliases": ["ollama-slow", "mdns-pi5"]
  }
  ```

- 重啟應用程式後停用狀態仍會保持
- 透過 mDNS 動態發現的後端在啟動前已被停用時，發現後也會自動套用（`_pending_disabled` 機制）
- 寫入失敗時記憶體狀態會被回滾，不會與磁碟產生不一致

### 已停用後端的行為

- 從 `/v1/chat/completions` 等 OpenAI 相容端點的路由對象中排除
- 嘗試直接路由至已停用的後端時會回傳 `503 Service Unavailable`
- 在 WebUI 表格中仍會顯示（用於確認狀態及重新啟用）

---

## Routing Aliases 表格

顯示設定檔中定義的邏輯模型名稱與實體模型 ID 的對應關係。

| 欄位 | 說明 |
|---|---|
| **Alias** | 用戶端在 `model` 參數中指定的邏輯名稱（例：`default-llm`、`fast-chat`） |
| **Physical Model** | 實際處理請求的實體模型 ID（格式：`後端alias/模型名`、例：`ollama-mac/qwen2.5:7b`） |

### 別名的作用

使用別名可在不修改用戶端程式碼的情況下切換後端或使用的模型。

- 用戶端以邏輯名稱發送請求，如 `"model": "default-llm"`
- LLM Router 解析 `default-llm → ollama-mac/qwen2.5:7b` 並代理轉發
- 將後端遷移至其他機器時，只需變更別名的指向即可

別名在設定檔中靜態定義，WebUI 以唯讀方式顯示。變更需編輯設定檔並重啟應用程式。

---

## 常見操作

### 後端顯示 unreachable 時

1. 確認後端服務（Ollama 等）是否正在運行
2. 執行 **Refresh All** 或個別 Refresh
3. 仍未解決時，確認 `last_error` 欄（或 API 回應）中的錯誤內容

### 想永久停用透過 mDNS 自動發現的後端

1. 在目標後端的 Actions 欄點擊 **Disable**
2. alias 會儲存到 `data/llm_router_state.json`，再次被發現後仍維持停用

### 想暫時停止對特定後端的負載

**Disable** 立即排除 → 作業完成後 **Enable** 恢復。無需重啟。
