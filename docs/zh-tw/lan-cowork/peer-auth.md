# 節點 PIN 驗證與令牌配對

**實作版本**: 4.92.0
**相關檔案**: `extensions/builtin_lan_cowork/`, `core/lan_cowork_core/`

---

## 概覽

在 v4.92 之前，LAN 上的節點通訊僅透過 `X-Peer-Id` 標頭來識別對方。
由於此標頭可由同一網路上的任何人偽造，安全性不足。

從 v4.92 起，系統已遷移至 **PIN 核准式令牌配對** 方式。

- 初次連接時傳送「配對請求」
- 對方管理員在管理畫面核准後，發出 6 位數 PIN（有效期 5 分鐘）
- 輸入 PIN 後發行 Bearer 令牌（有效期 30 天）
- 後續通訊使用 `Authorization: Bearer <token>` 進行驗證

舊版 `X-Peer-Id` 標頭方式可透過設定保留相容性，但 DELETE 操作始終需要新驗證方式。

---

## 配對流程

```
[節點 A（發起方）]                     [節點 B（目標方）]
       |                                      |
       |--- POST /api/lan/pair/request ------->|
       |    (peer_id, display_name, public_key)|
       |                                      |
       |                           管理員在 /lan-cowork/peers 確認並核准
       |                                      |
       |<--- SSE: peer_pairing.pin_ready ------|
       |    (6 位數 PIN，有效期 5 分鐘)         |
       |                                      |
       |--- POST /api/lan/pair/verify -------->|
       |    (peer_id, pin)                     |
       |                                      |
       |<--- 200 OK: { token, expires_at } ----|
       |    (Bearer 令牌，有效期 30 天)          |
       |                                      |
       |--- 後續: Authorization: Bearer <token>
```

### 各步驟說明

| 步驟 | 端點 | 說明 |
|------|------|------|
| 1. 傳送請求 | `POST /api/lan/pair/request` | 傳送節點 ID、顯示名稱及公鑰 |
| 2. 等待核准 | — | 管理員在 `/lan-cowork/peers` 確認請求 |
| 3. 發出 PIN | — | 管理員點擊核准按鈕，生成 6 位數 PIN（有效 5 分鐘） |
| 4. PIN 驗證 | `POST /api/lan/pair/verify` | 提交 PIN 並接收 Bearer 令牌 |
| 5. 已驗證通訊 | — | 附加 `Authorization: Bearer <token>` 標頭 |

---

## 管理畫面 (`/lan-cowork/peers`)

### 待核准請求

當新節點傳送配對請求時，會顯示在管理畫面的「待核准」標籤中。

- **核准**: 生成 PIN 並透過 SSE 通知請求方節點
- **拒絕**: 刪除請求。請求方節點收到 403

### 已連接節點清單

顯示所有已配對的節點及各令牌的到期日。

| 欄位 | 內容 |
|------|------|
| 顯示名稱 | 節點名稱 |
| IP 位址 | 最後觀察到的來源 IP |
| 到期日 | Bearer 令牌到期日（30 天） |
| 最後連線 | 最後心跳的時間戳記 |
| 操作 | 撤銷令牌按鈕 |

### 令牌撤銷

點擊「撤銷」可立即使目標節點的 Bearer 令牌失效。
下次通訊時，節點收到 401 並自動嘗試重新配對。

---

## 設定項目

設定位於 `config.json` 的 `lan_cowork` 區段，或透過設定畫面的「LAN 協作」標籤修改。

### `ip_check_mode`

指定來源 IP 位址的驗證方式。

| 值 | 行為 |
|----|------|
| `strict` | 僅允許與發行令牌時完全相符的 IP（預設） |
| `cidr` | 允許 `allowed_cidr` 指定的 CIDR 範圍內的 IP |
| `rfc1918` | 允許所有私有 IP 位址（192.168.x.x / 10.x.x.x / 172.16-31.x.x） |

### `allow_legacy_auth`

是否保留與舊版 `X-Peer-Id` 標頭驗證的相容性。

- `true`: 僅使用 `X-Peer-Id` 標頭也允許部分操作（預設: `true`）
- `false`: 拒絕所有不含 Bearer 令牌的連線

> **注意**: 使用 `DELETE` 方法的操作（停止掃描、強制刪除等）無論 `allow_legacy_auth` 設定為何，始終需要 Bearer 令牌。

### `protect_heartbeat`

是否對心跳端點 (`/api/lan/heartbeat`) 也要求驗證。

- `true`: 心跳也需要 Bearer 令牌
- `false`: 心跳無需驗證即可通過（預設: `false`）

由於心跳頻繁傳送，設為 `false` 可防止令牌到期偵測的延遲。

### `protect_events`

是否對 SSE 事件串流 (`/api/events/`) 也要求驗證。

- `true`: SSE 連線也需要 Bearer 令牌
- `false`: SSE 無需驗證即可通過（預設: `false`）

---

## 安全性說明

### 令牌雜湊

發行的 Bearer 令牌**不會以明文儲存**在資料庫中。
使用 scrypt（N=16384, r=8, p=1）雜湊後才儲存。
即使資料庫洩露，也無法還原原始令牌。

### 日誌遮罩

- `Authorization: Bearer <token>` 標頭在日誌輸出時自動替換為 `Bearer [REDACTED]`
- PIN 代碼也不會留在日誌中

### 速率限制

為防止 DoS 攻擊和暴力破解，適用以下速率限制：

| 端點 | 限制 |
|------|------|
| `POST /api/lan/pair/request` | 10 次/分鐘/IP |
| `POST /api/lan/pair/verify` | 30 次/分鐘/IP |

PIN 在 5 分鐘後自動到期，每個請求只能驗證一次。

---

## 疑難排解

### 配對請求未收到

- 確認遠端節點的 URL 設定是否正確
- 確認連接埠是否被防火牆封鎖
- 查看遠端節點的日誌，確認 `pair/request` 的接收狀況

### PIN 已到期

PIN 有效期為 5 分鐘。如已到期，請在管理畫面再次點擊「核准」按鈕，即可發出新的 PIN。

### 令牌突然無法使用

可能原因：

1. 管理員在管理畫面撤銷了令牌
2. 30 天有效期已到期
3. 使用 `ip_check_mode: strict` 時 IP 位址已變更

請重新執行配對流程。

### 將 `allow_legacy_auth` 設為 `false` 後無法連線

若現有節點仍在使用舊版驗證方式，所有節點都將收到 401。
請先在每個節點完成重新配對，再將 `allow_legacy_auth` 設為 `false`。
