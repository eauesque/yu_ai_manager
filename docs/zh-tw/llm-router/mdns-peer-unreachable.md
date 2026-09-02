# mDNS 後端持續顯示「無法連線」

LLM Router 的 mDNS 自動發現中新增的後端持續顯示「無法連線 (unreachable)」
而無法恢復時的原因、診斷、處理方式彙整。

---

## 結構概覽

```
MdnsService (zeroconf layer)
  └─ on_peer_added / on_peer_updated / on_peer_removed
       └─ LlmRouterMdnsBridge
            ├─ _verify()       ← 透過 HTTP 確認 /api/mdns/identity
            ├─ _apply_peer_to_catalog()  ← 向 BackendCatalog 註冊
            ├─ _enter_cooldown() / _in_cooldown()  ← 失敗後的重試限制
            └─ retry_pending_peers()  ← 60 秒週期掃描（v4.91.15〜）
```

**重要流程**:

1. zeroconf 偵測到節點 → 呼叫 `on_peer_added`
2. `_verify()` 呼叫 `/api/mdns/identity`，驗證 `node_id` 與 `product`
3. 成功 → 透過 `_apply_peer_to_catalog()` 將後端新增至 catalog
4. 失敗 → 進入 60 秒 cooldown，忽略相同 `node_id` 的事件
5. **v4.91.15〜**: 每 60 秒的掃描任務在 cooldown 過期後重試未到達的節點

---

## 顯示「無法連線」的主要模式

### 模式 A — 初次 verify 失敗 → cooldown 靜默

**症狀**: LLM Router 中顯示後端但 status=unreachable。  
**原因**:
- 對方節點剛啟動時 HTTP 伺服器尚未就緒
- 自己的連接埠已改變而節點仍參照舊的 TXT（v4.91.14 以前的
  `--port` override 錯誤：已在 35a3679a 修正）

**行為 (v4.91.14 以前)**: cooldown（60 秒）結束後等待下一個 `on_peer_updated`
事件，但若該事件未觸發則永遠無法恢復。

**行為 (v4.91.15〜)**: cooldown 過期後，下一個掃描 tick（最多 60 秒後）
自動重試 → 成功則反映至 catalog。

---

### 模式 B — zeroconf 不觸發 `ServiceStateChange.Updated`

**症狀**: 節點重啟後 LLM Router 仍維持舊狀態。  
**原因**: 依 zeroconf 的快取狀態，TXT 變更時 `Updated` 事件
有時不會觸發（zeroconf 函式庫的已知行為）。  
**處理**: v4.91.15 的掃描任務在 60 秒內捕獲。

---

### 模式 C — 對方節點的連接埠與廣播值不符

**症狀**: curl 可到達但 verify timeout 持續。  
**原因**: 使用 `--port` CLI 旗標但 config.json 的 `server.port` 仍為
舊值 → mDNS TXT 廣播了錯誤的連接埠。  
**修正**: v4.91.14 (35a3679a) 已修正為以實際連接埠覆寫 `config["server"]["port"]`。
若舊的啟動腳本直接覆寫 config.json，請同時確認設定檔。

---

### 模式 D — 未在 trusted_peer_registry 中註冊

**症狀**: LLM Router 顯示「ready」但對 `/ext/<name>/v1/*` 的代理回傳 403。  
**原因**: verify 成功已進入 catalog，但 `_apply_peer_to_catalog()` 呼叫前
程序重啟，或因 `service_kind != "yu"` 跳過了 registry 的註冊
（bare Ollama 節點不註冊的規格）。  
**確認**:
```bash
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool | grep -E 'node_id|trusted'
```

---

## 診斷步驟

### 1. 確認節點目前狀態

```bash
# 已知的節點清單
curl -s http://127.0.0.1:PORT/api/mdns/peers | python3 -m json.tool

# LLM Router 後端清單（mDNS 來源的 alias 以 "mdns-" 開頭）
curl -s http://127.0.0.1:PORT/api/llm_router/status | python3 -m json.tool
```

### 2. 確認對方節點能否到達自己的 identity 端點

在對方節點上：
```bash
curl -v http://<自己的LAN-IP>:<PORT>/api/mdns/identity
```

預期回應：
```json
{"product": "yu_ai_manager", "node_id": "...", "version": "..."}
```

失敗時：
- 防火牆/路由問題
- 連接埠實際值與廣播值不符（確認是否以 `--port` 啟動）

### 3. 確認自己廣播的連接埠

```bash
# 啟動日誌中會顯示 "web_port"
grep -i "web_port\|mdns.*port\|effective_port" logs/app.log | tail -20

# 或透過 settings API
curl -s http://127.0.0.1:PORT/api/server/info | python3 -m json.tool | grep port
```

### 4. 確認 cooldown 狀態

GUI: **LLM Router** > 後端卡片 > 詳細中顯示 `last_error` 與
`last_seen_at`。錯誤為 "identity verification failed" 時表示 verify 可到達
但內容不符（node_id / product 不一致）。
錯誤為 "timeout" 時表示 HTTP 本身無法到達。

### 5. 確認掃描日誌

```bash
grep "\[mdns\] sweep" logs/app.log
```

出現 `sweep re-verified peer <8字元>` 表示已透過掃描恢復。

---

## 強制恢復（手動）

不等掃描、立即恢復的方法：

### 方法 1: 重啟對方節點

重啟後 zeroconf 觸發 `ServiceStateChange.Removed` + `Added` →
`on_peer_removed` 清除 cooldown → `on_peer_added` 立即重新驗證。

### 方法 2: mDNS 服務重啟 API（從設定畫面）

**設定** > **LLM Router** > **mDNS 重啟** 按鈕（若存在）。

### 方法 3: 重啟應用程式

cooldown 僅存在於記憶體中。重啟後所有 cooldown 重置，
啟動後立即重新驗證所有節點。

---

## 防止再發的要點

| 檢查項目 | 確認方法 |
|---|---|
| 使用 `--port` 時 config.json 的 `server.port` 是否為相同值 | 參照 config.json |
| 防火牆是否允許 `PORT` 的 inbound | `sudo ufw status` / macOS 設定 |
| 多 NIC 環境中是否 bind 到正確的 LAN 介面 | `config.json` 的 `mdns.bind_address` |
| 是否使用 v4.91.15 以後的版本（內建掃描任務） | `curl .../api/server/info` |

---

## 相關檔案

| 檔案 | 作用 |
|---|---|
| `core/llm_router/mdns_integration.py` | `LlmRouterMdnsBridge`·cooldown·retry_pending_peers |
| `core/web/runtime_mdns.py` | 掃描任務啟動·停止 |
| `core/mdns/service.py` | zeroconf 包裝器·`list_peers()` |
| `core/web/trusted_peer_registry.py` | 跨節點 `/ext/*` 認證 |
