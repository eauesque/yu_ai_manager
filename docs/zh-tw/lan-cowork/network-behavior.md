# LAN Cowork 的網路行為（LAN 上會發生什麼）

> 適用範圍：v4.538.0 及以上的 Rust standalone（`yu-server`）。關於 Python 後端混合（hybrid）設置，
> 請參考末尾的「Python 版的差異」。

本頁總結了 **「啟用 LAN Cowork 時，您的機器在網路上會開始執行什麼操作」** 這個問題。
在變更設定前，請先瀏覽此頁。

---

## 要點

- **預設不做任何事情。** Rust standalone 在沒有明確啟用下述設定的情況下，
  不會在 LAN 上進行監聽或宣告。
- 啟用時，**會被同一 LAN 上的其他節點發現**。這是設計預期的行為。
- **PIN 的有無不會阻止發現宣告。** 詳情請參考「PIN 的關係（容易誤解的點）」。

---

## 啟用時會開始的操作

| 操作 | 內容 |
|---|---|
| **UDP 監聽** | 綁定至 `0.0.0.0:19850`（所有介面） |
| **定期宣告** | 每 10 秒向 `255.255.255.255:19850` broadcast 一條簽名的 HELLO。內容包含本節點的 ID、公鑰、API 連接埠、主機名等 |
| **其他節點註冊** | 驗證接收的 HELLO 簽名，並將對方節點記錄到自己的節點列表中（TOFU） |
| **入站 HTTP 接受** | 下表中 peer 的端點開始返回回應 |
| **本地傳遞** | 接受的節點事件傳遞至登入用戶的畫面訂閱的 SSE（`/api/events/stream`） |
| **過期清理** | 每 60 秒清理記憶體中過期的配對要求和明文 PIN |

### 入站接受的端點

| 端點 | 身份驗證 |
|---|---|
| `GET /ext/lan_cowork/api/peer/discover` | **無需登入工作階段**（查詢節點列表） |
| `GET /ext/lan_cowork/api/peer/status` | **無需登入工作階段**（自節點記述子） |
| `POST /ext/lan_cowork/api/peer/register` | **無需登入工作階段**（節點自我註冊。伺服器端驗證註冊目標） |
| `POST /ext/lan_cowork/api/peer/pair/request` / `pair/verify` | **無需登入工作階段**（配對開始。未配對的對方無法擁有工作階段） |
| `POST /ext/lan_cowork/api/peer/token/renew` | 簽名 + nonce（無需 Bearer） |
| `POST /ext/lan_cowork/api/peer/event` / `heartbeat` | 簽名 + Bearer Token |

「無需登入工作階段」不是指**沒有身份驗證**，而是指**不需要登入工作階段**。
未配對的對方無法擁有工作階段，因此只有這 5 條路由作為例外而開放。
其他路由仍如以往需要登入。

---

## 啟用與無效化的方式

在 `config.json` 的 **`extensions` 段落**中切換。

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true
    }
  }
}
```

- **如果沒有此鍵則為「無效」**（Rust standalone）。
- 需要**重新啟動**才能生效。
- 如果要暫時切換，也可以透過啟動選項指定。優先順序為
  **命令列 > `config.json` > 環境變數 > 預設值**。

| 方式 | 啟用 | 無效化 |
|---|---|---|
| 命令列 | `--native-daemon` | `--no-native-daemon` |
| 環境變數 | `YU_LAN_COWORK_NATIVE_DAEMON=1` | 同 `=0` |

> 環境變數只將 `1` / `true` / `yes` 解釋為「啟用」。`on` 或 `Y` **被視為無效**。

### 檢查是否已啟用

```bash
curl -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5000/ext/lan_cowork/api/peer/status
```

| 回應 | 意思 |
|---|---|
| `200` | 已啟用。節點功能正在運作 |
| `405` | **已無效**（功能本身未內建） |
| `503` | 已啟用但尚未就緒（節點特定金鑰未生成，或內部初始化失敗） |

> **畫面上的擴充功能清單顯示不可靠。** 擴充功能清單可能會顯示 LAN Cowork 為「已啟用」，
> 但這只是基於隨附資訊的顯示，**與上述 daemon 是否實際運作無關**。應根據上述端點的回應，
> 或啟動日誌中的 `native_daemon=...` 行來判斷。

---

## PIN 的關係（容易誤解的點）

**認為未設定 PIN 就無法從 LAN 觸及任何東西是不準確的。**

- **正確的是**：使用 `--lan`（所有介面監聽）需要 PIN，沒有 PIN 則啟動會中止。
  預設監聽是 `127.0.0.1`，所以**正常啟動時 HTTP 介面無法從 LAN 存取**。
- **注意 1**：若直接在 `--host` 指定 LAN IP，PIN 必須檢查會被略過。
  而且未設定 PIN 時登入大門本身會開啟，**請避免在沒有 PIN 的情況下將其暴露於 LAN**。
- **注意 2**：**UDP 宣告與是否設定 PIN 無關。** 若已啟用，即使未設定 PIN 的節點
  也會每 10 秒向 LAN broadcast 自己的存在。PIN 只限制 HTTP 介面的暴露。

也就是說，**PIN 可以限制 HTTP 介面的暴露，但無法阻止發現宣告。**

### 僅在 loopback 監聽時（v4.539.0 及以上）

若監聽位址僅為 loopback（預設值 `127.0.0.1`，桌面版也同樣如此），
**此節點不會在 LAN 上宣告自身**。即使宣告，其他節點也無法連線。
啟動後會記錄一次下列警告（這是 WARN 而非 INFO，因此預設可見）。

```
LAN Cowork discovery inactive: server listens on loopback only; bind a LAN address or use --lan
```

若要在 LAN 上使用，請綁定 LAN 位址或使用 `--lan`（`--lan` 需要 PIN）。

> v4.539.0 之前，僅在 loopback 監聽的節點會宣告 LAN IP。對等節點可以發現它，
> 但無法連線；因此變更了此行為。

---

## 啟用前須知

- **即使無效化，在啟用期間記錄的節點資訊不會自動還原。** 此外，
  **啟用並首次啟動時**，舊的節點記錄清理會執行
  （7 天以上未能到達的記錄，以及未配對超過 1 小時的記錄會被刪除）。
  建議在切換前備份 `tags.db`。
- 接收的節點事件會傳遞至登入用戶的畫面訂閱的 SSE。**內容來自對方節點的輸入**
  （送信源 ID 會被伺服器端已驗證的值取代）。
- 日誌中只記錄**數量、型別和送信源 ID**，事件內容不會被記錄。
- 如果要確認動作狀況，請啟用 INFO 級別的日誌
  （例：`RUST_LOG=yu_server=info`）。保持預設時，不會輸出顯示節點事件接收的行。

---

## Python 版的差異

| | Python 後端混合（hybrid） | Rust standalone |
|---|---|---|
| 預設 | **已啟用**（`config.json` 中無此項時為啟用） | **已無效**（需明確啟用） |
| 實作 | Python 擴充功能負責 | `yu-server` 負責 |

**Rust standalone 意圖上設為「預設無效」。** 這是為了避免單純更新就改變網路上的行為。
hybrid 構成的行為從未改變。

> 過去的文件曾建議設定啟用為 `{"lan_cowork": {"enabled": true}}`（最頂層），但
> **這個位置的鍵不會被任何實作讀取。** 上述的 `extensions` 段落才是正確的位置。
