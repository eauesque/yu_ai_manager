# HailoRT 5.3.0 的 CMA 記憶體洩漏 — 確定診斷與操作限制

> **訂正注記**: 本文為基於舊測量的 CMA 洩漏診斷記錄，`release()` 後 CMA 不會回收、推論期間以約 14 MB/分鐘持續洩漏、僅 Pi 本體重新啟動為確實回收手段等舊結論已撤回。經 HailoRT / driver 5.4.0 重新試驗後的最終判定，已於 [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8 訂正。請勿將本文舊結論作為現行的實用判定參照。

**建立日期**: 2026-05-17（在 v4.214.11 中發現並記錄）
**影響範圍**: Raspberry Pi 5 + Hailo-10H + `hailort==5.3.0`（透過 `hailo_platform.genai` 路徑）
**症狀**: 一旦載入 LLM，即使呼叫 `VDevice.release()` / `LLM.release()`，CMA 也幾乎無法被回收。此外，推論過程中 CMA 也會持續洩漏。除了重新啟動 Pi 本體之外，沒有其他恢復手段。
**狀態**: 已確認為驅動程式端的結構性限制。正在研究迴避方法。

---

## 1. 確定診斷的依據

使用 `v4.214.10` 中引入的 CMA 事件記錄器（`logs/hailo_cma.log`、`core/hailo_device_core/device_helpers.py::log_hailo_cma_event`），於 2026-05-17 實測了以下序列。

### 1-1. 觀測日誌（原始資料）

`logs/hailo_cma.log`:

```text
2026-05-17T14:05:13+0900 event=vdevice_create_pre  cma_free_mb=392 pid=3237
2026-05-17T14:05:14+0900 event=vdevice_create_post cma_free_mb=393 pid=3237
2026-05-17T14:05:14+0900 event=acquire_pre  cma_free_mb=393 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:06:25+0900 event=acquire_post cma_free_mb=108 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
        ↓ 6 分鐘的聊天使用（大約 5〜10 則訊息的推論）
2026-05-17T14:12:36+0900 event=release_pre  cma_free_mb=24  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:12:36+0900 event=release_post cma_free_mb=25  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
```

### 1-2. 解讀

| 階段 | CmaFree 差值 | 意義 |
|---|---|---|
| `vdevice_create_pre` → `vdevice_create_post` | **+1 MB（≈ 0）** | VDevice 建立本身幾乎不消耗 CMA |
| `acquire_pre` → `acquire_post`（Qwen3-1.7B-Instruct 載入） | **−285 MB** | 1 個 LLM 消耗 285 MB |
| `acquire_post` → `release_pre`（6 分鐘推論） | **−84 MB / 6 min ≒ −14 MB/min** | **推論中也持續洩漏** |
| `release_pre` → `release_post`（LLM 卸載） | **+1 MB** | **`release()` 實際上不歸還 CMA** |

### 1-3. 與先前假設的比較

這是 2026-05-16 建立的 `SQLCIPHER_MMAP_CORRUPTION.md` §7 及舊文件初始假設「VDevice 保持策略（我們的 `_maybe_reset_vdevice` 為空）放大了洩漏」的部分反證觀測結果。由於 VDevice 建立 0 MB / release 0 MB，**即使改變保持策略（= 將 `_maybe_reset_vdevice` 改為每次重置），也不會有效果**。

---

## 2. 結構性限制

根據實測結果，HailoRT 5.3.0（社群版本，`hailo_platform.genai` API）存在以下三個同時發生的問題：

1. **`VDevice.release()` / GenAI 模型的 `release()` 不回收主機 CMA**（實測確認）
   - 在單一行程內，PCIe 驅動程式（`hailo1x_pci`）持續持有 DMA 區域，不會發生相當於 `munmap` 的操作
2. **推論中持續的 CMA 洩漏（約 14 MB/分鐘）**（實測確認）
   - 今日觀測：使用 Qwen3-1.7B-Instruct 的 6 分鐘內損失了 84 MB
   - 與載入/卸載無關的獨立路徑。即使不卸載也會耗盡
3. **除 Pi 本體重啟外，沒有確認過可靠回收 CMA 的方法**（實測 + 社群報告）
   - 即使重新啟動伺服器行程（相當於 `systemctl restart yu-ai-manager`），由於 `hailo1x_pci` 在 PCIe 電源循環之前持續持有 DMA，也無法完全恢復。完整恢復需要 Pi 本體的 `sudo reboot`（本儲存庫的實測）
   - Hailo 社群中也有多個獨立報告：<https://community.hailo.ai/t/hailo-10h-on-rpi5-undocumented-api-findings-dfc-conversion-failures-with-transformer-based-models-swinv2-vit-convnext/18979> 和 <https://community.hailo.ai/t/hailo-10h-throughput-degrades-irreversibly-within-minutes-of-continuous-use-125-41-fps-only-host-reboot-recovers/19218>（明確指出 `VDevice.release()` / 行程退出 / 驅動程式重新載入無法恢復，只有主機重啟才能恢復）
   - 這已在 `acquire_genai` 的事前拒絕錯誤訊息中告知使用者（`core/hailo_device_core/device_manager_genai.py::acquire_genai`，"a full system reboot is required"）

### 2-1. 「終止子行程是否可以歸還 CMA？」：**實測反證**（2026-05-17 Phase 0 PoC）

舊版本（rev1）從理論上斷定「Linux 核心在 `mm_struct` teardown 時回收 DMA 頁面，因此終止子行程可以完整回收 CMA」，但**使用 Phase 0 PoC（`tools/diag_hailo_cma_reclaim.py`）實測的結果，兩次獨立確認終止子行程幾乎不回收 CMA**。

**測量結果（第 2 次，嚴格版本）**：

| 測量點 | CmaFree | Δ |
|---|---:|---:|
| 基準線（PoC 開始前） | 503 MB | — |
| VDevice 建立後 | 372 MB | **-131 MB**（冷啟動子行程中 VDevice 構建時消耗） |
| LLM 載入後 | 372 MB | 0 MB（LLM 在 VDevice DMA pool 內完結，無新增消耗） |
| SIGTERM 傳送 + join 後 | 378 MB | +6 MB |
| **等待 30 秒後** | **380 MB** | **僅回收累計 +8 MB** |

預期回收 ≥250 MB，實測值僅 +8 MB（第 1 次偶發測量為 +1 MB）。這只是系統抖動等級，**沒有發生有意義的 CMA 回收**。

**確定診斷**：

- `hailo1x_pci` 驅動程式以**驅動程式內部全局狀態**而非使用者行程的 `mm_struct` 管理 DMA pool（推定）
- `process exit`、`kill`、`module unload` 都不會回收（與社群報告一致）
- **唯一確認的回收手段是 Pi 本體的 `sudo reboot`（= PCIe 電源循環）** ← §2 第 3 行記載的實測事實

詳細報告：`docs/superpowers/specs/codex-reviews/2026-05-17-hailo-subprocess-isolation-phase0-poc-result.md`

基於這個結果，`docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md` 被標記為 **REJECTED**，透過子行程隔離進行緩解的路線廢止。改採 §4 (D) 的自動重啟路線作為替代方案。

---

## 3. 操作上的含義

### 3-1. 「每次 Pi 重啟 1 個模型」實際上是上限

- Pi 5（CMA 上限 512 MB，Pi 規格無法增加）+ Qwen3 系 LLM（285 MB）的組合：
    - 重啟後立即 CmaFree ≒ 480 MB
    - 載入 1 個 LLM → CmaFree ≒ 190 MB
    - 數十分鐘推論後 → CmaFree ≒ 50 MB 以下
    - **第 2 個模型的載入永久不可能**（需要 250+ MB 但剩餘不足，即使 release 也不會歸還）

### 3-2. LLM + VLM / LLM + S2T 無法同時使用

- VLM（llava 系，約 300 MB）、S2T（whisper-small，約 175 MB）與 LLM 切換使用的場景，在上述限制下，除非採用**載入 → 重啟 → 載入**的流程，否則無法實現。
- **「對話中附加圖片切換到其他模型」「對對話音訊進行語音轉文字」等多模型 UX 在 HailoRT 5.3.0 中在設計上無法成立**。

### 3-3. 長時間持續推論困難

- 14 MB/分鐘的洩漏意味著即使 CmaFree 為 200 MB 時，14 分鐘後減半，30 分鐘後幾乎耗盡。
- 超過 30 分鐘的聊天會話在不插入 Pi 重啟的情況下無法保持穩定。

---

## 4. 可採取的對策

按優先順序和工時列舉：

| 方案 | 效果 | 工時 | 副作用・風險 |
|---|---|---|---|
| ~~(A) 將 Hailo 操作隔離到子行程，定期終止讓核心回收 CMA~~ | ❌ **REJECTED**（Phase 0 PoC 反證，兩次重現）。終止後的回收量僅累計 +8 MB，假設不成立 | — | 不採用 |
| **(B) 將 `_CMA_ESTIMATES_MB` 更新為實測值 + 餘量** | 提高事前拒絕的精確度（減少假陽性載入嘗試） | ✅ 立即可用，1 行 | 以 250 MB 假設勉強運作的現有使用者將被拒絕，但那原本就已在失敗 |
| **(C) `CmaFree < 80 MB` 時顯示 UI 橫幅 / `< 30 MB` 時在 error.log 記錄 WARN** | 使用者可以了解狀況，提示 Pi 重啟 | 中 | 警告疲勞 / 過度通知的風險 |
| **(D) 檢測到 `CmaFree < 30 MB` 時向 supervisor 傳送 SIGTERM** | 自動恢復（但由於需要 Pi 全體重啟，透過 `systemctl reboot`） | 中 | 需要 supervisor 權限 / 其他作業中的連線中斷 |
| **(E) 等待 HailoRT 修正 + 明確記錄限制** | 成本 0 | 0 | 取決於 Hailo 的發布週期（數個月〜） |
| **(F) 向 Hailo 的問題追蹤器 / 論壇提交修正請求** | 可能加速修正時機 | 小 | 回應速度取決於支援合約和社群狀況 |

短期方針（v4.214.11 中實施）：**適用 (B) + 本文件（E 和 F 的出發點）**。
中期方針（另行 spec）：按照 **(C) UI 警告 → (A) 子行程隔離**的順序考慮。
長期：監控 HailoRT 的發布，修正後更新本文件並解除限制。

---

## 5. 相關文件 / 程式碼

- `core/hailo_device_core/device_manager_genai.py::acquire_genai` — 事前 CmaFree 檢查 + 面向使用者的錯誤訊息已明示本限制
- `core/hailo_device_core/device_helpers.py::_CMA_ESTIMATES_MB` — 按模型別的 CMA 需求量估計（v4.214.11 中 qwen 從 250 → 300 提升）
- `core/hailo_device_core/device_helpers.py::log_hailo_cma_event` — v4.214.10 中引入的測量儀器。本文件的實測資料也來自這裡
- `core/hailo_device_core/device_manager_state.py::_maybe_reset_vdevice` — 在行程生命週期內持有 VDevice 的設計（空函數）。本實測結果確認，即使改為重置，也不會有助於 CMA 回收
- `docs/ja/hailo/HAILO_AUTO_REBOOT_PHASE05.md` — Phase 0.5 觀測階段的操作員指南。使用 `mode=lazy` + `dry_run=true` 僅收集 `would_fire` 日誌的流程
- `docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md` — Pi5 整體的 CMA 上限及各驅動程式（camera / KMS / Hailo / HEVC）的基準消耗量
- `docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md` — 遷移到 HailoRT 5.3.0 的經過與已知差異

---

## 6. 重現步驟（供 Hailo 問題報告使用）

向外部提交錯誤報告時的最小重現步驟：

```bash
# 1. 確認 Pi 重啟後立即的基準線
grep CmaFree /proc/meminfo
# CmaFree: 480000 kB 前後

# 2. 啟動伺服器 + 載入第 1 個 LLM（例如：透過 /tools 的 GenAI 傳送 1 則訊息）
# 向 /api/llm/generate 或 /api/chat/send 發送 1 個請求

# 3. 確認 CmaFree
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB (-280 MB)

# 4. 卸載模型
curl -X POST http://127.0.0.1:5000/ext/hailo-genai/api/model/unload -d '{"model":"llm"}'

# 5. 確認 CmaFree
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB（不歸還 ← bug）

# 6. 嘗試重新載入相同模型 / 其他模型 → 因 CMA 不足而拒絕
```

預期行為：步驟 5 中，CmaFree 應恢復到接近步驟 1 基準線的值（>400 MB）。
實際行為：只歸還約 +1 MB，無法重新載入。
