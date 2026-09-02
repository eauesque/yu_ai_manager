# Hailo LLM 自動發現

**適用版本**：v4.66.0 以後

## 概述

yu_ai_manager 可自動發現在 Pi5 的 Hailo NPU 上運作的 LLM 端點，無需編輯 `config.json`。只要將 Pi5 接入區域網路，其他 yu_ai_manager 節點即可呼叫 Hailo LLM。

## 偵測對象的 2 個系統

| 端點 | 說明 | 預設 URL 格式 |
|---|---|---|
| **yu extension Hailo LLM** | yu_ai_manager 內建的 `builtin-hailo-genai` extension 提供的 OpenAI 相容 LLM | `http://<host>:<yu-port>/ext/hailo-genai/v1/` |
| **hailo-ollama** | 外部二進位檔 `/usr/bin/hailo-ollama` 提供的 OpenAI 相容 LLM（預設 `:8000`） | `http://<host>:8000/v1/` |

兩者同時運作時皆會自動註冊。在 HailoRT 5.3.0+ 設定 `HAILO_OLLAMA_VDEVICE_GROUP_ID=YU_SHARED` 後，HailoRT scheduler 會以 round-robin 共享實體裝置，因此同時使用也不會衝突。

## 本機自動註冊（Phase A）

yu_ai_manager 啟動時會獨立偵測以下兩項：

1. **yu extension**：`hailo_platform.genai.LLM` 可匯入，且 `/dev/hailo0` 或 `/dev/h1x-0` 其中之一存在 → 以 `hailo-local` backend 自動註冊到 catalog
   （v4.66.1 對應了 Raspberry Pi 5 + AI HAT + HailoRT 5.3.0 實機以 `/dev/h1x-0` 公開的情況）
2. **hailo-ollama**：對 `localhost:8000/v1/models` 發送 HTTP probe（2 秒逾時）→ 收到 200 回應則以 `hailo-ollama-local` backend 自動註冊

若 `config.json` 的 `llm_router.backends` 中已有同名 alias，則該設定優先（不會覆蓋）。

## mDNS 自動廣告（Phase B）

根據 Phase A 的偵測結果，yu_ai_manager 透過 mDNS TXT record 向其他節點廣告 Hailo 功能：

- `capabilities=llm,hailo` — 表示 yu extension 可用
- `hailo_ollama_url=http://192.168.1.10:8000/v1/` — 僅在 hailo-ollama 運作時（URL 會被改寫為區域網路可達的 IP）

其他 yu_ai_manager 節點透過 mDNS 接收後，會先對 `/api/mdns/identity` 端點進行 identity 驗證，然後以下列 alias 自動註冊額外的 backend：

- `mdns-<node_id[:8]>-hailo` — yu extension Hailo LLM（`capabilities` 中包含 `hailo` 時，從 peer 的 `web_port` + addresses 推導 URL）
- `mdns-<node_id[:8]>-hailo-ollama` — 外部 hailo-ollama（`hailo_ollama_url` 有廣告時，直接使用 TXT 中的 URL）

## 設定

預設為啟用。可在 `config.json` 中停用：

```json
{
  "llm_router": {
    "hailo_ollama": {
      "enabled": false,
      "port": 8000
    }
  }
}
```

- **`enabled`**：設為 `false` 可完全停用 hailo-ollama 的自動偵測。yu extension 端的偵測由另外控制（依 extension 是否載入自動判定）
- **`port`**：hailo-ollama 的連接埠號（預設 8000）。超出 1〜65535 範圍時會回退為預設值並輸出 warning 日誌

## 安全性注意事項

**hailo-ollama 不具備認證功能**。透過 mDNS 廣告後，**區域網路上的任何節點都能自由消耗 hailo-ollama 的推論資源**。

| 端點 | 認證 | 實際區域網路公開範圍 |
|---|---|---|
| yu extension（`/ext/hailo-genai/v1/`） | yu 的 web auth chain（PIN/session/api-key） | 僅能通過 yu 認證的用戶端 |
| hailo-ollama（`hailo_ollama_url`） | **無** | **區域網路上的所有節點** |

在家庭區域網路或信任的 VLAN 以外的環境（公共 Wi-Fi 等），請以 `hailo_ollama.enabled: false` 停用自動廣告。

## LLM Router WebUI 的顯示方式

自動註冊的 backend 會顯示在 v4.65.0 的 `/llm-router` 儀表板中：

- `hailo-local` / `hailo-ollama-local` — 本機偵測（source：`static` 標籤）
- `mdns-<id>-hailo` / `mdns-<id>-hailo-ollama` — 透過 mDNS 發現（source：`mdns` 標籤）

所有項目都可透過 Disable 切換按鈕暫時停用。停用狀態會永久保存至 `data/llm_router_state.json`，重啟後仍維持（v4.65.0 實作）。

## 誤偵測的安全機制

Phase A 偵測具備 2 項安全裝置：

1. **自我 probe 迴避**：若 `hailo_ollama.port` 與 yu 自身的 web port 相同，則完全略過 probe（防止 yu 將自己誤判為 hailo-ollama）
2. **既有 backend 優先**：若 `config.json` 中已註冊相同 `localhost:<port>/v1` 的 backend，則略過 probe 以尊重使用者的設定

## TODO 待辦項目

- (P3) 其他語言翻譯（`en`、`zh-tw`、`zh-cn`、`ko`）— 與 v4.65.0 LLM Router WebUI 的翻譯待辦一併處理
- (P3) Pi5 實機整合測試 — 2 節點架構的 Playwright 16 項目相當
- (P3) IPv6 支援 — 目前 `_pick_lan_ip` 僅回傳 IPv4
- (P3) 多 Hailo 裝置支援 — 目前以固定 alias `hailo-local` 為前提。多 USB dongle 情境需考慮 index suffix 設計
- (P3) `BackendCatalog.remove_backend()` — 目前 `_mark_unreachable` 僅更新 status，不從 catalog 移除

## 相關文件

- [LLM Router 設定](./setup.md)
- 設計規格：`docs/superpowers/specs/2026-04-08-hailo-auto-discovery-design.md`
- 實作計畫：`docs/superpowers/plans/2026-04-08-hailo-auto-discovery.md`

## v4.66.2 — Trusted peer auth（實機認證漏洞修正）

v4.66.0 的 Hailo 自動發現中，由於 yu 的 `/ext/hailo-genai/*` extension 位於 web auth chain 之下，LLM Router driver（不持有 Bearer 或 session）嘗試 probe/dispatch 時會收到認證 middleware 的 honeypot HTML，導致 JSON parse 失敗並卡在 `unreachable` 狀態。

### 運作機制

- 新增 `TrustedPeerRegistry`，初始化時 seed `127.0.0.1` / `::1`
- `LlmRouterMdnsBridge` 在 peer 驗證（對 `/api/mdns/identity` 發送 HTTP GET 並確認 node_id 一致）成功後，將該 peer 的所有 advertised addresses 加入 registry
- `auth_chain.check_trusted_peer` 收到 `/ext/<name>/v1/*` 路徑的請求時，若 remote_addr 在 registry 中則繞過 PIN auth
- 既有的 API key / session / cookie 認證路徑維持不變

### 與 Quick lock 的關係

- **loopback**（yu 自身的 self-probe）：quick_lock 期間也始終通過
- **peer IP**：quick_lock 期間會拒絕請求（`check_quick_lock` 回傳 503）。「使用者刻意鎖定」的狀態也會被 peer 尊重

藉此，以下場景可正常運作：

- pi2 的 `hailo-local` self-probe（`http://localhost:5000/ext/hailo-genai/v1/models`）
- Windows 存取 pi2 的 `mdns-<id>-hailo` cross-node dispatch（`http://192.168.50.4:5000/ext/hailo-genai/v1/chat/completions`）

### 設定

無需變更設定檔。即使 mDNS 已停用，loopback seed 仍可運作，因此 self-probe 修正可無條件生效。

### 除錯

設定環境變數 `TAGDB_DEBUG_TRUSTED_PEERS=1` 後啟動 yu，`/api/mdns/peers` 回應中會新增 `trusted_ips` 欄位。正式環境請勿設定此變數（trust 清單可能成為「攻擊目標清單」，因此不應在未認證端點中暴露）。

### 安全邊界

「信任區域網路前提」運作規則（與 v4.64.0 mDNS Phase B 相同前提）。不在保護範圍內的情境包括：區域網路中可進行實體存取的惡意節點 — 此時請使用 `/llm-router` WebUI 的 disable 切換或 quick_lock 因應。

詳情請參閱 `docs/superpowers/specs/2026-04-09-trusted-peer-auth-design.md`。
