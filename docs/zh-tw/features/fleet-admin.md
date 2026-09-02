# Fleet 管理

LAN Cowork 的 Fleet Admin 功能可讓您從中央位置管理網路上的多個 yu-ai-manager 節點。

## 概覽

- **機器資訊收集**：從所有節點彙總 CPU / RAM / GPU / 磁碟 / 版本 / 運行時間
- **遠端日誌查看**：從中央 UI 透過 SSE 即時串流任意節點的日誌
- **版本更新分發**：指示節點執行 `git pull --ff-only` + graceful restart

## 前提條件

- LAN Cowork 擴充功能已啟用（`extensions["builtin-lan-cowork"].enabled = true`）
- 節點之間已完成配對
- 已以 git 儲存庫形式 clone（使用更新功能時需要）
- Python 虛擬環境中已安裝 `psutil>=5.9`

## 設定

### 主節點設定

在 `config.json` 中新增：

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<已配對的 peer_id>"
        ],
        "allow_log_stream_from": [
          "<已配對的 peer_id>"
        ],
        "allowed_branches": [
          "main"
        ],
        "timings": {
          "chief_observation_sec": 25,
          "peers_poll_interval_sec": 30,
          "heartbeat_timeout_sec": 60,
          "update_job_timeout_sec": 600,
          "postcheck_timeout_sec": 180
        }
      }
    }
  }
}
```

### 一般節點設定

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": false,
        "allow_remote_update": true,
        "allow_update_from": [
          "<主節點的 peer_id>"
        ],
        "allow_log_stream_from": [
          "<主節點的 peer_id>"
        ],
        "allowed_branches": [
          "main"
        ]
      }
    }
  }
}
```

## 存取 Fleet UI

在主節點的瀏覽器中前往 `/ext/lan_cowork/fleet/ui`。

一般節點上此 URL 會回傳 404。

## 分頁功能

### 概覽

- 顯示各節點卡片（含 CPU / RAM / GPU / 磁碟使用率長條圖）
- 在線 / 離線 / 無法取得資訊 狀態顯示
- 主節點顯示 `[CHIEF]` 徽章
- 每 30 秒自動重新整理 + 手動重新整理按鈕
- 偵測到多個主節點時顯示警告橫幅

### 日誌

- 透過 SSE 即時串流任意節點的日誌（tail -f 風格）
- 層級篩選（DEBUG / INFO / WARNING / ERROR）
- 搜尋框（用戶端篩選）
- 自動捲動 ON/OFF
- 暫停 / 繼續

### 更新

- 版本 / git commit / 分支比較表
- 個別節點的「Pull & Restart」按鈕
- 多節點批次更新（dispatch）
- 進度顯示（precheck → fetching → pulling → restarting → online）
- 主節點本身從批次更新中排除（僅限個別按鈕）

## 安全性

授權採用兩層架構：

1. **配對（身份確認）**：Bearer token 用於識別呼叫者身份
2. **Allowlist（權限）**：每項操作都需要明確授權 peer_id

已配對並不代表擁有所有權限。

### Allowlist 設定範例

```json
"allow_update_from": [
  "abc123def456",
  {"peer_id": "def456abc789"}
]
```

- 字串和 `{peer_id: ...}` 格式均可使用
- 自身 peer_id 會自動加入（無需設定）

## 主節點自動降格

若同一網路上有多個 `chief = true` 的節點啟動，後啟動的節點會在 `chief_observation_sec` 秒觀察後自動降格。

降格後需透過修改設定並重新啟動才能恢復主節點身份（不會自動升格）。

## git 更新限制

- 僅使用 `git pull --ff-only`（不使用 merge/rebase）
- 無法 fast-forward 時立即回傳 `failed`（工作目錄不會被修改）
- 工作目錄有未提交變更時拒絕更新

## 疑難排解

| 症狀 | 原因 | 解決方法 |
|---|---|---|
| `/fleet/ui` 回傳 404 | 未設定 `chief = true` | 確認 config.json 後重新啟動 |
| `/fleet/info` 回傳 500 | 未安裝 psutil | `uv pip install psutil>=5.9` |
| `git_not_available` 錯誤 | 找不到 git 或 PATH 不正確 | 確認 git 安裝狀態 |
| 更新後 `postcheck_online` 逾時 | 重新啟動超過 3 分鐘 | 延長 `postcheck_timeout_sec` |
| 多主節點警告橫幅持續顯示 | 舊主節點程序仍在運行 | 重新啟動舊主節點 |

## API 參考

### 所有節點

| 端點 | 說明 |
|---|---|
| `GET /ext/lan_cowork/fleet/info` | 機器資訊（需要 Bearer 認證） |
| `GET /ext/lan_cowork/fleet/logs/stream` | 自身日誌 SSE（需要 allowlist 授權） |
| `POST /ext/lan_cowork/fleet/update` | git pull + 重新啟動（需要 allowlist 授權） |
| `GET /ext/lan_cowork/fleet/update/status` | 更新任務狀態查詢 |

### 僅主節點

| 端點 | 說明 |
|---|---|
| `GET /ext/lan_cowork/fleet/peers` | 所有節點資訊彙總 |
| `GET /ext/lan_cowork/fleet/logs/stream?peer_id=X` | 指定節點日誌 SSE 轉發 |
| `POST /ext/lan_cowork/fleet/update/dispatch` | 多節點批次更新 |
| `GET /ext/lan_cowork/fleet/update/dispatch/status` | dispatch 進度查詢 |
| `GET /ext/lan_cowork/fleet/ui` | Fleet 管理 UI |
