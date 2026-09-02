# LAN Cowork

> 目標版本: v4.55.0 及更高版本（PIN 認證從 v4.92.0 開始可用）

## 什麼是 LAN Cowork

LAN Cowork 是一項擴展功能，可在網路上協調多個 yu_ai_manager 節點。  
每台機器獨立運行，同時允許將繁重的處理分散或作為 Fleet 進行集中管理。

```
┌──────────────┐    mDNS 發現      ┌──────────────┐
│  Windows PC  │◄──────────────────►│   Mac Mini   │
│  (配備 GPU)  │   PIN 配對        │  (控制)      │
│              │◄──────────────────►│              │
│  分散式推理  │                   │  Fleet 管理  │
│  (tagger等) │                   │              │
└──────────────┘                   └──────────────┘
        ▲                                  ▲
        └──────────────────────────────────┘
                      ▼
              ┌──────────────┐
              │ Raspberry Pi │
              │ (Hailo NPU)  │
              └──────────────┘
```

---

## 功能概覽

| 功能 | 說明 |
|---|---|
| **mDNS 自動發現** | 無需設定自動發現同一 LAN 上的節點 |
| **PIN 配對** | 管理員批准的 PIN 認證以發放節點間令牌 |
| **分散式推理** | 在多個節點上平行處理 tagger、CLIP、YOLO 和 Whisper |
| **生成分散** | 將 SD WebUI / ComfyUI 任務委派到 LAN 節點 |
| **Fleet 管理** | 集中管理所有節點的日誌和版本更新 |
| **節點事件中繼** | 將其他節點的事件串流傳輸到您自己的 SSE |
| **LLM 路由** | 自動在 LLM Router 中註冊發現的節點 |

---

## 設定步驟

### 1. 啟用

新增到 `config.json`:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true,
      "peer_name": "my-desktop"
    }
  }
}
```

> **注意**：本頁先前將啟用鍵說明為最上層的 `{"lan_cowork": {...}}`，但沒有任何實作會讀取該位置的鍵。上方的 `extensions` 區段才是正確位置。

> **預設值取決於後端：**Python 後端（混合模式）會將缺少的鍵視為**已啟用**，而 Rust 獨立伺服器除非明確啟用，否則為**已停用**。啟用後網路上實際會發生什麼，請參閱[網路行為](network-behavior.md)。

重新啟動後:
- 開始在 UDP 19850 上偵聽其他節點
- 開始透過 mDNS 公告 _yu-ai._tcp.local.

### 2. 配對節點

要從節點 A 連線到節點 B:

1. **節點 A WebUI** → `設定` → `LAN Cowork` → 新增節點 B URL
2. 節點 A 傳送 `POST /api/lan/pair/request`
3. **節點 B WebUI** → `/lan-cowork/peers` → 在「待批准」索引標籤中批准
4. 6 位數 PIN 傳送到節點 A（透過 SSE）
5. 節點 A 輸入 PIN → 取得 Bearer 令牌（有效期 30 天）

> **注意**: 配對是單向的。請同時執行 A→B 和 B→A。

詳見 [節點間 PIN 認證和令牌配對](peer-auth.md)。

### 3. 驗證操作

```bash
# 發現的節點清單（從節點 A）
curl http://localhost:5000/api/mdns/peers

# LAN Cowork 識別的節點
curl http://localhost:5000/api/lan/peers
```

---

## 功能特定設定

### 分散式推理

配對完成後，分散式推理自動可用。

- `設定` → `LAN Cowork` → 為每個節點啟用推理類型（tagger/CLIP/YOLO/Whisper）
- 或透過 `/mesh-inference` 頁面上的矩陣進行個別設定

詳情: [分散式推理設定](../mesh-inference/setup.md)

### Fleet 管理

設定「首席」節點以管理其他節點:

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "fleet": {
        "chief": true,
        "allow_remote_update": true,
        "allow_update_from": [
          "<paired peer_id>"
        ]
      }
    }
  }
}
```

詳情: [Fleet 管理](../features/fleet-admin.md)

### 生成分散（SD / ComfyUI 任務委派）

自動將生成任務分散到配備 GPU 的節點。可透過設定檔後端註冊或 mDNS 自動發現取得。  
如果節點 B 執行 SD WebUI / ComfyUI，設定後立即可用。

---

## 網路需求

| 連接埠 / 協定 | 用途 | 必須 |
|---|---|---|
| UDP 5353 | mDNS（節點發現） | 僅同一 L2 LAN |
| UDP 19850 | LAN Cowork 發現 | 僅同一 L2 LAN |
| TCP 5000 (預設) | API、配對、推理 | 節點之間 |

- mDNS 無法跨越路由器或 VPN（使用固定 IP 或 `.local` 主機名稱）
- 確保防火牆中 UDP 5353 和 TCP 5000 在 LAN 上開放

---

## 文件索引

| 文件 | 內容 |
|---|---|
| [節點間 PIN 認證](peer-auth.md) | 配對流程、令牌管理、安全設定 |
| [分散式推理設定](../mesh-inference/setup.md) | 在多個節點上平行化推理的步驟 |
| [分散式推理矩陣](../mesh-inference/toggle.md) | 透過 WebUI 按節點和類型啟用/停用 |
| [分散式推理架構](../mesh-inference/overview.md) | 內部設計、工作竊取、持久化 |
| [Fleet 管理](../features/fleet-admin.md) | 遠端日誌和版本更新的集中管理 |
| [mDNS 節點 API](../api/mdns-peers.md) | `/api/mdns/*` 端點詳情 |

---

## 安全性

- mDNS 沒有認證。**僅在家庭 LAN 或可信任網路上使用**
- 在公開 Wi-Fi 或共用 LAN 上，使用 `"mdns": {"enabled": false}` 停用
- 節點間通訊受 PIN 配對產生的 Bearer 令牌保護（儲存為 scrypt 雜湊）
- `ip_check_mode: strict` 僅允許發放令牌的 IP（預設）
