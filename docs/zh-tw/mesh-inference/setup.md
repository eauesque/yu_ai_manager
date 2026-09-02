# 分散推理設定指南

> 目標版本：v4.67.0 及更高版本

## 什麼是分散推理?

多個 yu_ai_manager 節點協作來**並行分散**推理處理（例如標籤、CLIP、YOLO 和語音辨識）的功能。您可以在多台機器間共享大檔案掃描，或將標籤任務委託給搭載 Hailo NPU 的 Pi5。

```
┌──────────────┐   影像批次    ┌──────────────┐
│    本機      │ ──────────────► │  Pi5 (Hailo) │  標籤器 × 200 張
│   (掃描)     │ ──────────────► │  GPU 機器    │  標籤器 × 300 張
│              │ ──────────────► │    本機      │  標籤器 × 100 張
└──────────────┘   工作          └──────────────┘
                  竊取
```

---

## 前置條件

每個節點需要滿足以下條件：

1. yu_ai_manager 正在執行
2. **LAN Cowork 擴充功能已啟用** (`"extensions": {"builtin-lan-cowork": {"enabled": true}}`)
3. 節點已**互相配對** ([對等節點認證指南](../lan-cowork/peer-auth.md))
4. 要使用的推理引擎已在每個節點上設定 (ONNX / Hailo / Whisper 等)

---

## 設定步驟

### 步驟 1：在每個節點上啟用 LAN Cowork

在所有節點的 `config.json` 中：

```json
{
  "extensions": {
    "builtin-lan-cowork": {
      "enabled": true
    }
  }
}
```

重新啟動後，節點將透過 mDNS 自動相互發現。

### 步驟 2：完成配對

在所有節點對之間執行配對（雙向）。
詳情：[對等節點 PIN 認證和令牌配對](../lan-cowork/peer-auth.md)

### 步驟 3：驗證分散推理矩陣

在任意節點上開啟 `/mesh-inference`。

已配對的節點顯示為列，推理類型顯示為欄：

| 節點 | 標籤器 | clip | yolo | whisper |
|---|---|---|---|---|
| 本機 | ☑ 啟用 | ☑ 啟用 | ☑ 啟用 | ☑ 啟用 |
| pi5-hailo | ☑ 啟用 | ☑ 啟用 | — 不可用 | — 不可用 |
| gpu-win | ☑ 啟用 | ☑ 啟用 | ☑ 啟用 | ☑ 啟用 |

- **☑ 啟用**：使用此節點進行推理
- **☐ 停用**：跳過（可手動切換）
- **—**：此節點沒有目標推理引擎（無法操作）

### 步驟 4：驗證操作

執行標籤批次，確認日誌顯示使用了多個節點：

```
[mesh-inference] dispatching tagger: 600 items to 3 peers
[mesh-inference] pi5-hailo: processed 200, errors 0
[mesh-inference] gpu-win:   processed 300, errors 0
[mesh-inference] local:     processed 100, errors 0
```

---

## 推理類型要求

| 類型 | 所需引擎 | 說明 |
|---|---|---|
| `tagger` | ONNX（WD14 等）或 Hailo NPU | 影像的 Danbooru 風格標籤 |
| `clip` | ONNX CLIP 或 Hailo | 影像語義嵌入向量（用於語義搜尋） |
| `yolo` | ONNX YOLO | 影像中的物體偵測 |
| `whisper` | faster-whisper 或遠端 | 音頻/視頻的語音轉文字 |

沒有設定引擎的節點將對該類型顯示「—」，且不會為該類型路由。

---

## 角色設計示例

### 示例 1：將 Pi5 + Hailo NPU 專用於標籤

僅為標籤分配 Pi5，減少其他節點的負載。

矩陣設定：
- Pi5：標籤器 ☑，其他 ☐
- 本機：clip ☑、yolo ☑、whisper ☑、標籤器 ☐（委託給 Pi5）

### 示例 2：快速批量掃描

同時在 GPU 機器和本機上啟用標籤器，透過工作竊取自動共享檔案。無需手動分割。

### 示例 3：僅本機模式（臨時）

在 `/mesh-inference` 中點擊「僅本機模式」按鈕，一次性停用所有遠端節點。在網路斷開時很有用。

---

## 故障排除

### 節點未出現在矩陣中

1. 使用 `/api/lan/peers` 檢查節點是否被辨識
2. 確認配對已完成 ([peer-auth.md](../lan-cowork/peer-auth.md))
3. 檢查遠端節點上 LAN Cowork 是否已啟用

### 到特定節點的路由不工作

- 檢查矩陣中該節點的目標類型是否顯示 ☑
- 檢查 `/api/lan/peers` 回應中該節點是否顯示 `status: "online"`
- 檢查是否收到遠端節點的心跳（在日誌中搜尋 `heartbeat`）

### 所有處理都在本機進行

如果所有遠端節點離線或停用，將自動進行本機回退。
這是正常操作（不是錯誤）。

### `no_enabled_peers` 錯誤

該類型在所有節點上都被停用。
在矩陣中至少為該類型啟用 1 個節點。

---

## 相關文件

- [分散推理架構](overview.md) — 工作竊取和 DisableAwareStrategy 的內部設計
- [分散推理矩陣](toggle.md) — WebUI 操作詳情
- [LAN Cowork 概覽](../lan-cowork/README.md) — LAN Cowork 整體設定
- [對等節點 PIN 認證](../lan-cowork/peer-auth.md) — 配對過程
