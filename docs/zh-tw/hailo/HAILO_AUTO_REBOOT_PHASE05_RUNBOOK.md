# Hailo Auto-Reboot Phase 0.5 — 本環境操作手冊

**建立日期**: 2026-05-17 (v4.215.1)
**目標環境**: 本儲存庫運行的 Pi 5
**本文目的**: 即使原始聊天會話紀錄遺失，僅憑本手冊也能完整開始、確認及結束 Phase 0.5 觀測。
**設計規格**: `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md` (rev3 APPROVED)
**通用操作指南**: `docs/zh-tw/hailo/HAILO_AUTO_REBOOT_PHASE05.md`（本文為其環境專用版本）

---

## 0. 前提條件與已完成的作業

- v4.215.1 中 Phase 0.5 觀測實作已合併並推送至 main（commit `80af4fb73` + merge `69be148c6`）
- `config.json`（儲存庫根目錄）已於 **2026-05-17** 新增 `hailo.auto_reboot` 區塊
  - 建議設定：`mode = "lazy"` + `dry_run = true`
  - 備份：`config.json.bak.<時間戳記>`
- **不會觸發實際重新開機**（`dry_run = true` + Phase 0.5 設計僅記錄 `would_fire` 事件）

確認 config.json：

```bash
cd /home/pi/GitHub/yu_ai_manager
jq .hailo.auto_reboot config.json
# → 應顯示 {"mode":"lazy","dry_run":true,...}
```

---

## 1. 首次啟動與啟用程序

### 1.1 伺服器重新啟動

必須重新啟動以套用 config 變更。**請使用目前的啟動方式重新啟動**。

典型啟動指令（依實際環境調整）：

```bash
cd /home/pi/GitHub/yu_ai_manager
uv run python web_ui.py --config config.json --db data/tags.db
```

若已設定為 systemd 服務，請以 `sudo systemctl restart <unit>` 重新啟動對應的 unit。

### 1.2 啟動後 30 秒內的確認（3 項）

#### A. `boot_baseline` 事件是否已記錄？

```bash
tail -n 20 /home/pi/GitHub/yu_ai_manager/logs/hailo_auto_reboot.log
```

預期結果：出現一行 `{"event":"boot_baseline","state":"idle","mode":"lazy","dry_run":true,"cma_free_mb":<int|null>,"hailo_runtime_version":"5.3.0",...}`。

**未出現時的疑難排解**：

- `logs/hailo_auto_reboot.log` 不存在 → judge loop 未啟動（可能未以 `["full"]` 模式啟動，或已設定 `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` 環境變數）
- 檔案存在但為空 → `core/hailo_device_core/auto_reboot_logger.py` 路徑解析失敗；請確認 `logs/` 目錄的權限
- `cma_free_mb: null` → `/proc/meminfo` 讀取失敗（在非 Pi 硬體上執行時的預期行為，無害）

#### B. `/api/system/cma` 回應中 opt-in 是否已生效？

若已在瀏覽器以 PIN 登入，則不需要 API key。可使用 curl 或在瀏覽器 DevTools 主控台（PIN 登入中）執行：

```js
fetch("/ext/hailo-genai/api/system/cma").then(r => r.json()).then(j => console.log(j.cma.auto_reboot))
```

預期結果：

```json
{
  "enabled": true,
  "mode": "lazy",
  "dry_run": true,
  "state": "idle",
  "consecutive_rejects": 0
}
```

若 `enabled: false` 或 `mode: "off"` → 請確認 config.json 中的 `hailo.auto_reboot.mode` 是否為 `"lazy"`，以及伺服器是否已完成重新啟動。

#### C. `error.log` 中是否有啟動錯誤？

```bash
tail -n 50 /home/pi/GitHub/yu_ai_manager/logs/error.log | grep -iE "hailo_auto_reboot|auto_reboot"
```

無輸出即為正常。若有錯誤，請參閱本文末尾「8. 已知陷阱」。

---

## 2. 觀測期間的日常操作

### 2.1 正常使用

**主要操作**：

- 透過 `/ext/hailo-genai/chat` 或 `/tools` **如往常使用 LLM 聊天**（例如 Qwen3-1.7B）
- 視需要使用 VLM / S2T
- 長時間聊天（連續 30 分鐘以上）及多模型切換也值得刻意嘗試，以擴大觀測資料的範圍

無需特殊驗證。**愈正常使用，資料愈豐富** — 這正是 Phase 0.5 的設計意圖。

### 2.2 每週審閱（每週 1 次，約 5 分鐘）

```bash
cd /home/pi/GitHub/yu_ai_manager

# 各事件類型的發生次數
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c

# would_fire 的發生時間與 CmaFree
grep would_fire logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb] | @tsv'

# drain_entered 的原因（cma 還是 rejects）
grep drain_entered logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb, .consecutive_rejects, .reason] | @tsv' 2>/dev/null || \
  grep drain_entered logs/hailo_auto_reboot.log | head -10
```

**確認點**：

- `would_fire` 出現 1 次以上 → Phase 1 部署具有意義（確認記錄的時間是否與手動重新開機的時間吻合）
- `prewarn_entered` 頻繁觸發但未進入 `drain_entered` → `prewarn_threshold_mb`（80 MB）可能過低，需重新確認
- `drain_entered` 的原因均為 `rejects` → DRAIN 由 reject 驅動，需要不同於閾值調整的對策

---

## 3. 觀測結束與 Phase 1 部署判斷基準

### 3.1 所需觀測期間

**最少 7 天 / 建議 14 天**。觀測期間至少須涵蓋以下模式：

- LLM 一般聊天
- LLM 長時間連續聊天（單次會話 30 分鐘以上）
- VLM / S2T 模型切換
- 至少 1 次 `acquire_genai` 事前拒絕（CmaFree 不足）
- Pi 重新開機後的首次載入

### 3.2 Phase 1 部署的數值基準

彙整：

```bash
cd /home/pi/GitHub/yu_ai_manager
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

判斷表：

| 觀測結果 | Phase 1 判斷 |
|---|---|
| `would_fire` ≥ 1 件 | **GO**（自動重新開機具有價值） |
| `would_fire` = 0、`drain_entered` ≥ 1 件 | 重新調整閾值後考慮部署 Phase 1（已到達 DRAIN 但未觸發 would_fire = `fire_grace_seconds` 有縮短空間） |
| 僅 `prewarn_entered`、`drain_entered` = 0 | 目前閾值從未達到「嚴重」狀態 → 依使用模式判斷是否需要 Phase 1 |
| 所有事件均為 0（僅 `boot_baseline`） | 此使用方式不會耗盡 CMA → 不需要 Phase 1 |

### 3.3 觀測完成後的作業

1. 將彙整結果儲存至 `docs/zh-tw/hailo/HAILO_AUTO_REBOOT_PHASE05_OBSERVATION_RESULTS.md`（新建）
2. 若部署 Phase 1：進入規格 rev3 §5.2 的 Phase 1（UI DRAIN 橫幅 + i18n）；依觀測資料重新確認 §3.1 閾值
3. 若不需要 Phase 1：在 config.json 中將 `mode` 改為 `"off"`，並封存觀測日誌

---

## 4. 停用程序（緊急情況 / 停止觀測時）

```bash
cd /home/pi/GitHub/yu_ai_manager
jq '.hailo.auto_reboot.mode = "off"' config.json > config.json.tmp && mv config.json.tmp config.json
# 重新啟動伺服器
```

即使設為 `mode = "off"`，JSONL 事件仍會繼續記錄（僅抑制輸出至 `error.log` 的 WARN）。若要完全停止，請使用環境變數：

```bash
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 5. 日誌檔案清單（相關）

| 檔案 | 用途 |
|---|---|
| `logs/hailo_auto_reboot.log` | **本功能的主要日誌**。JSONL 格式；10 MB × 30 個備份進行輪替 |
| `logs/hailo_cma.log` | 現有的 CMA 事件記錄器（自 v4.214.10 起）。記錄 `acquire_genai` 等 VDevice/模型生命週期事件 |
| `logs/error.log` | 應用程式全域錯誤日誌。`mode != "off"` 時也會輸出 `drain_entered` / `would_fire` 的 WARN 摘要 |

---

## 6. 相關程式碼位置（供日後調查使用）

| 功能 | 檔案 |
|---|---|
| 狀態機 + RejectTracker | `core/hailo_device_core/auto_reboot.py` |
| JSONL writer | `core/hailo_device_core/auto_reboot_logger.py` |
| 背景迴圈進入點 | `core/web/startup_background_hailo_judge.py` |
| 背景任務註冊 | `core/web/startup_background.py`（`hailo_auto_reboot_judge`） |
| Config 預設值 | `core/configuration/defaults.py`（`hailo.auto_reboot`） |
| acquire_genai hook | `core/hailo_device_core/device_manager_genai.py` |
| `/api/system/cma` 擴充 | `extensions/builtin_hailo_genai/hailo_genai_ext.py` |
| 單元測試 | `tests/test_hailo_auto_reboot_judge.py`、`tests/test_hailo_auto_reboot_logger.py` |

---

## 7. 審閱歷程（參考用）

本實作已通過 AGENTS 規定的完整審閱流程（請參閱 v4.215.1 commit 訊息）。各報告檔案已寫入 `.claude/agent-outputs/` 目錄，但該目錄已列入 `.gitignore`，不受 git 管理。如有需要可重新產生。

---

## 8. 已知陷阱

| 症狀 | 原因與對策 |
|---|---|
| `logs/hailo_auto_reboot.log` 無任何輸出 | 伺服器未重新啟動 / `mode = "off"` 仍有效 / 未以 `["full"]` 模式啟動 / 已設定 `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` 環境變數 |
| `cma_free_mb: null` 持續出現 | 在非 Pi 硬體（例如 WSL2）上執行，或 `/proc/meminfo` 讀取失敗；請在實際 Pi 硬體上重新確認 |
| `hailo_runtime_version: null` | 此環境未安裝 `hailo_platform` 套件；在實際 Pi 5 上，若已安裝 HailoRT 5.3.0 runtime 即可取得 |
| `would_fire` 從未出現 | 使用負載過低，或閾值過寬；請嘗試長時間連續聊天 / 模型切換後重新觀測 |
| 已設定 `eager` 模式但未作用 | Phase 0.5 中，`eager` 刻意退回至 `off`（並輸出警告日誌）；預計於 Phase 1+ 實作 |

---

## 9. 緊急回滾

若萬一 Phase 0.5 實作本身出現問題（由於不會觸發實際重新開機，可能性極低）：

```bash
cd /home/pi/GitHub/yu_ai_manager
# 從 v4.215.1 回滾至 v4.214.13（僅規格，實作前）
git revert -m 1 69be148c6
git push
```

或**僅透過設定完全停用**（建議）：

```bash
# 新增至啟動環境並重新啟動伺服器
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 10. 本文的維護

- 觀測完成時，**將 §3.3 彙整結果追加至本文末尾**（日後聊天會話進行 Phase 1 判斷時需要）
- 部署 Phase 1 後，請將本文重新命名為 `HAILO_AUTO_REBOOT_PHASE05_RUNBOOK_ARCHIVED.md`，並新建 Phase 1 手冊
- 本文置於 `/home/pi/GitHub/yu_ai_manager/docs/zh-tw/hailo/HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md`（git 管理下）
