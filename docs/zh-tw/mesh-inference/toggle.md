# 分散推論矩陣

**版本**：v4.67.0 以後

## 概述

在 `/mesh-inference` 頁面中，可針對參與 mesh inference 的各個 peer，以推論類型為單位切換啟用/停用。對象為 tagger、clip、yolo、whisper 共 4 種。

藉此可在不修改 config 的情況下進行角色分配，例如：將 Pi5 的 Hailo NPU 專用於 tagger、由 GPU 主機處理 clip 等。

## 使用方式

1. 從導覽列點擊「🕸️ 分散推論」
2. 點擊矩陣表中的各儲存格切換啟用/停用
   - ☑ = 啟用（在該 peer 上使用該推論類型）
   - ☐ = 停用（略過該 peer）
   - — = 該 peer 未提供對應類型（無法操作）
3. 「僅本機模式」按鈕可一次停用所有遠端 peer
4. 狀態會自動永久保存至 `data/mesh_inference_state.json`

## 行為

- 離線的 peer 也會保留設定（重新連線時自動套用）
- 「僅本機模式」僅在本機至少有一個啟用的類型時才可按下
- 若所有 peer 的 tagger 都已停用，啟動 tagger 批次時會以 `no_enabled_peers` 錯誤立即失敗
- 透過 mDNS 重新偵測導致 peer 暫時離開並恢復時，停用狀態仍會保留

## 與既有 YOLO 分散推論選項的關係

YOLO 偵測頁面的「分散推論」核取方塊為了向後相容而保留，與矩陣的組合行為如下：

| yoloDistributed | 矩陣 yolo 欄 | 實際行為 |
|---|---|---|
| ✅ ON | 所有 peer 啟用 | 如同以往在所有 peer 上分散 |
| ✅ ON | 部分停用 | 略過已停用的 peer |
| ❌ OFF | 忽略 | 僅限本機（繞過 router） |

## 相關

- API 參考：[api/mesh-inference.md](../api/mesh-inference.md)
- LLM Router（不同層級）：[../llm-router/](../llm-router/)
