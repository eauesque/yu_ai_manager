# LLM Router 設定

## 新增至 config.json

```json
{
  "llm_router": {
    "enabled": true,
    "auth": {
      "mode": "loopback",
      "api_key": "",
      "allow_loopback_bypass": true
    },
    "backends": [
      {
        "alias": "ollama-local",
        "base_url": "http://localhost:11434/v1",
        "type": "ollama",
        "auto_discover": true
      }
    ],
    "aliases": {
      "local-fast": "ollama-local/qwen2.5:7b",
      "local-coder": "ollama-local/qwen2.5-coder:32b"
    }
  }
}
```

## 與 Claude Code 整合

LLM Router 已實作 Anthropic 相容的 `/v1/messages` 端點，因此 Claude Code
（Anthropic 官方 CLI）可以**直接**對接本地 LLM，不需要額外的代理
（claude-code-router 等）。

### 1. yu_ai_manager 端的 alias 設定

Claude Code 內部會傳送 `claude-opus-4-*` / `claude-sonnet-4-*` /
`claude-haiku-4-*` 等模型名稱。在 `config.json` 的 `aliases` 中將其映射到
本地分類（`large` / `fast` / `vision`）或實體模型：

```json
{
  "llm_router": {
    "enabled": true,
    "aliases": {
      "claude-opus-4-7":           "large",
      "claude-sonnet-4-6":         "fast",
      "claude-haiku-4-5":          "fast",
      "claude-3-5-haiku-20241022": "fast"
    }
  }
}
```

| Claude Code 傳送的模型名稱 | 建議映射目標 | 用途 |
|---|---|---|
| `claude-opus-*` | `large`（例：qwen2.5:72b / llama3.3:70b） | 主推論 |
| `claude-sonnet-*` | `fast` 或 `large` | 平衡 |
| `claude-haiku-*` | `fast`（例：qwen2.5:7b） | 背景任務（摘要、標題生成等） |

`large` / `fast` / `vision` 是 `core/llm_core` 分類登錄的虛擬後端，會從已註冊
的模型中自動挑選（可在 `/llm-router` WebUI 確認）。

### 2. Claude Code 端的設定

在 `~/.claude/settings.json`（Windows：`%USERPROFILE%\.claude\settings.json`）
加入：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:5000/v1",
    "ANTHROPIC_AUTH_TOKEN": "dummy"
  }
}
```

- loopback 存取時 `ANTHROPIC_AUTH_TOKEN` 不會被驗證，但 Claude Code 要求變數
  存在，填任意字串即可
- 從 LAN 內其他主機連線時改為 `http://<host>.local:5000/v1`，並將
  `config.json` 的 `auth.mode` 設為 `api_key` 並提供實際 token

僅想單次嘗試時可用環境變數：

```bash
ANTHROPIC_BASE_URL=http://localhost:5000/v1 ANTHROPIC_AUTH_TOKEN=dummy claude
```

### 3. 將背景任務（haiku 等價）導向另一模型

Claude Code 的背景任務可由 `ANTHROPIC_SMALL_FAST_MODEL` 覆寫：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:5000/v1",
    "ANTHROPIC_AUTH_TOKEN": "dummy",
    "ANTHROPIC_SMALL_FAST_MODEL": "fast"
  }
}
```

主流量走 alias（opus → large），背景流量明確命中 `fast` 分類。

### 4. 動作確認

```bash
# /v1/messages 是否有回應
curl -s http://localhost:5000/v1/messages \
  -H "content-type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"claude-opus-4-7","max_tokens":64,"messages":[{"role":"user","content":"ping"}]}'

# 從 Claude Code
claude
> /model          # 確認當前模型
> hello           # 有回應即代表已透過本地路由
```

### 5. 常見問題

| 症狀 | 原因 / 對策 |
|---|---|
| `model_not_found` 錯誤 | Claude Code 傳送的模型名既不在 alias 也不在分類中。請在 `/llm-router` WebUI 查看請求記錄並新增 alias |
| 回應極慢 | `large` 對應到 70B 級模型。請在 alias 直接指定較輕的模型 |
| `401 unauthorized` | `auth.mode` 為 `api_key` 但 Claude Code 端 `ANTHROPIC_AUTH_TOKEN` 不一致 |
| 串流中途中斷 | 後端（如 Ollama）逾時太短。請將 `config.json` 的 `backends[].timeout` 設為 120 以上 |

### 6. 直接指定實體名稱 / 自訂 alias

`aliases` 區段可加入任何名稱，不限於 Claude 模型名：

```json
"aliases": {
  "local-fast":  "ollama-local/qwen2.5:7b",
  "local-coder": "ollama-mac/qwen2.5-coder:32b"
}
```

在 Claude Code 端執行 `/model local-coder` 即會直接路由到該模型。

### 7. 混合運用 (opus = 真實 Anthropic、sonnet/haiku = 本地) 的現狀

「協調器使用 Anthropic 的 opus，僅子代理使用本地」這種分割運用，
**目前的 Claude Code + LLM Router 不建議採用**。原因：

- `ANTHROPIC_BASE_URL` 對整個 session 生效，因此「僅 opus 請求直通 Anthropic 本家」
  的設定無法在 Claude Code 端組合
- LLM Router 加入 upstream passthrough 後端在技術上可行，但**經濟性不成立**：
  - **Max/Pro 訂閱使用者**：設定 `ANTHROPIC_BASE_URL` 後即脫離訂閱認證路徑，
    passthrough 的 opus 請求改以 API 單價計費（反而更貴）
  - **API key 計費使用者**：passthrough 不會改變 opus 的 token 單價，
    且協調器消耗的 opus token 占主導，將子代理改為本地化的節省效果有限

**建議方針**：若以節省成本為目的，**請將協調器也全部導向本地**
（例：將 `claude-opus-*` 也 alias 到 `large` 分類），透過本地模型選型
（Qwen2.5-72B / Llama 3.3-70B / DeepSeek 等）確保品質。
若採用協調器與實作代理分離的設計，70B 級模型通常足夠勝任。

未來若 Claude Code 支援 `ANTHROPIC_OPUS_BASE_URL` 之類的模型別端點分割，
本節將更新。

## 與 Continue（VSCode）整合

`config.json`：
```json
{
  "models": [
    {
      "title": "Local Coder",
      "provider": "openai",
      "apiBase": "http://localhost:5000/v1",
      "model": "local-coder",
      "apiKey": "dummy"
    }
  ]
}
```

## 節點自動發現 — `.local` 主機名支援（家庭區域網路）

在家庭區域網路中運行多台機器（mac mini + Pi5 + Windows GPU 主機等）時，`base_url` 中使用 `.local` 主機名而非 IP 位址，即可在 **DHCP 變更 IP 後仍正常運作**。yu_ai_manager 端無需額外實作，`httpx` 會透過作業系統的 resolver（Bonjour / Avahi / mDNSResponder）自動完成名稱解析。

```json
{
  "llm_router": {
    "enabled": true,
    "backends": [
      { "alias": "ollama-mac", "base_url": "http://mac-mini.local:11434/v1", "type": "ollama" },
      { "alias": "ollama-pi5", "base_url": "http://pi5.local:11434/v1",      "type": "ollama" },
      { "alias": "ollama-win", "base_url": "http://gpu-rig.local:11434/v1",  "type": "ollama" }
    ],
    "aliases": {
      "local-fast":  "ollama-mac/qwen2.5:7b",
      "local-coder": "ollama-pi5/qwen2.5-coder:32b",
      "local-big":   "ollama-win/llama3.3:70b"
    }
  }
}
```

範例：[`config.example.local-hostname.json`](../../../config.example.local-hostname.json)

### 運作需求

| 作業系統 | 必要條件 |
|---|---|
| macOS | Bonjour（預設即可運作，無需額外安裝） |
| Linux | `avahi-daemon`（`sudo apt install avahi-daemon` / `sudo systemctl enable --now avahi-daemon`） |
| Windows 10/11 | mDNSResponder（Win10 1803 以後作業系統內建即可解析 `.local`。無法運作時請安裝 Bonjour Print Services） |

### 驗證運作

```bash
# 測試能否解析
python -c "import socket; print(socket.gethostbyname('mac-mini.local'))"
# → 回傳 192.168.x.x 即表示成功
```

### 跨子網路 / 企業區域網路 / VPN 跨越

mDNS 透過 L2 多播運作，因此**無法穿越路由器、VPN 或企業網路的隔離 VLAN**。在這類環境中請直接指定 IP 位址：

```json
"backends": [
  { "alias": "remote-gpu", "base_url": "http://10.20.30.40:11434/v1", "type": "ollama" },
  { "alias": "tailscale-mac", "base_url": "http://100.x.x.x:11434/v1", "type": "ollama" }
]
```

在 VLAN 分割環境等需要 mDNS reflector 的情況，請洽詢區域網路管理員。yu_ai_manager 端不提供 mDNS reflector / 代理。

### 已知限制

- **Windows 的 mDNS 解析偶爾較慢**（約 1 秒）：建議將後端 `timeout` 設為 3 秒以上
- **必須加上 `.local` 後綴**：單獨使用 `mac-mini` 會回退到 NetBIOS / DNS，務必寫成 `mac-mini.local`
- **Ollama 本身不進行 mDNS advertise**：僅支援主機名稱解析，連接埠（11434）需手動指定。若 Ollama 端支援 advertise，將可實現完全自動化（參見 TODO.md mDNS Phase B/C）

## 環境變數

| 變數名稱 | 行為 |
|---|---|
| `TAGDB_DISABLE_LLM_ROUTER` | 設為 `1` 可停用整個 Router |
| `TAGDB_DISABLE_LLM_ROUTER_REFRESH` | 設為 `1` 可停用 5 分鐘 refresh 循環 |
| `TAGDB_LLM_ROUTER_AUTH_MODE` | 覆蓋為 `none`/`loopback`/`api_key` |

## 其他語言文件

依照 CLAUDE.md 的 `docs/ 讀取規則`，以 `ja/` 為基礎同步 `en/zh-tw/zh-cn/ko` 版本（實作後的獨立任務；參見 TODO.md）。

## 節點自動發現（Phase B — v4.64.0 以後）

同一區域網路上的 yu_ai_manager 節點透過 mDNS（`_yu-ai._tcp.local.`）互相自動發現。即使不在 `config.json` 中手動新增後端，被發現的節點也會自動以 `mdns-<prefix>` alias 註冊到 `BackendCatalog`。

### 運作機制

1. 啟動時 `core/mdns/` 會 advertise `_yu-ai._tcp.local.`
2. 訂閱其他節點的 TXT record，確認必要的鍵（version/node_id/llm_base_url）齊全
3. 對主版本號一致的節點發送 HTTP GET 至 `http://<addr>:<web_port>/api/mdns/identity`，確認 product/node_id/version 相符
4. 通過驗證的節點以 `BackendInfo(alias="mdns-<node_id[:8]>")` 註冊到 LLM Router
5. 之後由現有的 probe loop 定期重新整理

### 前置條件

- 作業系統的 mDNS responder 需處於運作狀態（macOS：Bonjour、Linux：Avahi、Windows：mDNSResponder）
- 節點須位於同一 L2 子網路（跨路由器、跨 VPN 時請使用 Phase A 的手動 config）
- 本機防火牆需允許 UDP 5353
- **Ollama 須對區域網路公開** — Ollama 預設綁定於 `127.0.0.1:11434`，區域網路上的其他節點無法連線。請設定環境變數 `OLLAMA_HOST=0.0.0.0:11434` 後再啟動 Ollama（macOS 使用 `launchctl setenv OLLAMA_HOST "0.0.0.0:11434"`、Linux 使用 systemd unit / `.bashrc`、Windows 使用系統環境變數）。未設定時，yu_ai_manager 會判定為僅限 localhost 並不 advertise `llm_base_url`（啟動日誌會出現警告）

### Ollama 自動偵測

若 `config.json` 的 `llm_router.backends` 中沒有 localhost 項目，yu_ai_manager 啟動時會依序嘗試以下方式偵測 Ollama：

1. `http://<LAN_IP>:11434/api/tags` — 可從區域網路存取的 Ollama
2. `http://localhost:11434/api/tags` — 偵測到但不進行區域網路 advertise（輸出上述警告）

若以區域網路 IP 回傳 200，則自動作為 `llm_base_url` 加入 TXT record。此設計用於零設定讓 Ollama 共存節點加入 mDNS。非預設連接埠（11435 等）或 lmstudio / llamacpp 仍需在 `config.json` 中明確指定。

### 未與 `yu` 共存的 pure bare Ollama 節點之處理方針

未執行 `yu_ai_manager` 的 pure bare Ollama 節點（例如家人 mac 上只裝了 Ollama、
NAS 上的 Ollama 容器等）**不屬於自動發現的對象**。由於 `Ollama` 本身並無官方
advertise `_ollama._tcp.local.` 的功能，結構上沒有偵測方法。

如需從 LLM Router 使用此類節點，請以下列方式 **手動設定**：

```json
{
  "llm_router": {
    "backends": [
      { "alias": "ollama-nas",    "base_url": "http://nas.local:11434/v1",     "type": "ollama" },
      { "alias": "ollama-family", "base_url": "http://192.168.1.42:11434/v1", "type": "ollama" }
    ]
  }
}
```

- 若環境支援 `.local` 主機名稱（見上述「節點自動發現 — `.local` 主機名稱支援」），建議優先使用
- 否則請直接寫入固定 IP

#### 不採用自動發現的理由

在設計檢討（2026-04-11）時比較了以下 3 種方案，最後選擇 (c) 手動設定引導：

| 方案 | 內容 | 採否 |
|---|---|---|
| (a) 啟動時對整個區域網路 `:11434` 掃描 | 啟動時對子網路內主機進行全數 probe | **不採用** — 網路負載大，對企業 / 多主機區域網路造成困擾，可能被誤認為連接埠掃描，違背 edge-first 哲學 |
| (b) 常駐外部 Ollama 廣告 daemon | 在各 Ollama 主機上額外常駐 yu 提供的輕量 advertiser | **不採用** — 要求額外的常駐行程，等同於直接安裝 `yu_ai_manager` 本體，失去 pure bare 的意義 |
| (c) 引導使用固定 IP / `.local` / 手動 backend 設定 | 在 `config.json` 中手寫 | **採用** — 零額外實作、行為明確、不會將使用者捲入非預期的掃描 |

未來若 Ollama 本體官方 advertise `_ollama._tcp.local.`，或新增官方 service
discovery 機制，屆時再以 Phase D 重新評估自動發現層。

### 停用

在不需要的網路環境（Docker 隔離、企業區域網路、CI 等）可停用：

- 在 `config.json` 中加入 `"mdns": {"enabled": false}`
- 或設定環境變數 `YU_AI_MDNS_DISABLED=1`

### 已知行為

- **多網路介面環境（Wi-Fi + 有線）**：預設（`bind_address: null`）會在兩個介面上 advertise，`PeerInfo.addresses` 會包含多個 IP。若要限制為單一介面，請指定 `"bind_address": "192.168.x.y"`。
- **alias 衝突**：若 `config.json` 的 backend 已使用 `mdns-xxxxxxxx` 格式的 alias，手動設定優先，mDNS 發現的部分會被略過。
- **跨子網路**：mDNS 預設僅在 L2 廣播網域內運作。跨越時請使用 Phase A 的 `.local` 主機名稱指定。
- **安全性**：mDNS 本身不具備認證機制。預設假設在家庭區域網路等信任環境下使用。在公共 Wi-Fi 或多人區域網路中建議停用。`/api/mdns/identity` 的驗證可防止意外的錯誤節點識別或不相容舊版本的混入。
