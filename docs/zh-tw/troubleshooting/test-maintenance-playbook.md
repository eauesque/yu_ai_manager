# 測試維護劇本

當古舊的測試基礎設施或環境依賴導致 pytest 卡住時，一開始應該檢查的要點彙總。

## 目的

- 區分 `failed` 和 `skipped` 
- 區分正常的環境依賴 skip 和應該修復的過時測試
- 當 broad run (`pytest tests -q --maxfail=1`) 卡住時，建立固定的最短導線

## 基本命令

正常的全體檢查：

```powershell
venv\Scripts\python.exe -m pytest tests -q --maxfail=1
```

也檢查 skip 的原因：

```powershell
venv\Scripts\python.exe -m pytest tests -q -rs
```

嚴格處理 shared test server：

```powershell
$env:PYTEST_STRICT_AUTOSTART_SERVER="1"
venv\Scripts\python.exe -m pytest tests\api -q
```

授權許可稽核：

```powershell
venv\Scripts\python.exe scripts\license_audit.py
```

## 解讀目前的 skip

2026-04-21 時點的 broad run 中，skip 的主要原因偏向以下 5 個系統。

### 1. Shared Test Server 未啟動

最常見的 skip。`tests/conftest.py` 中的 shared server 以盡力而為的方式啟動，若啟動失敗，瀏覽器 / 伺服器相依的群組會被降級為 skip 而非 fail。

代表性的原因：

- `Shared test server unavailable on port <PORT>`

主要對象：

- `tests/api/`
- 瀏覽器 UX 審查類
- LAN Cowork / Fleet 瀏覽器/伺服器相依的測試
- 使用 `TARGET_URL` / `BASE` / `TARGET` 的 live browser test
- 使用自訂 Playwright/WebKit fixture 而非 `page` fixture 的稽核類測試

在正常執行中，這是**正常的 skip**。但若出現以下情況應調查：

- 與 shared server 無關的 unit test 也因同樣原因被 skip
- 以前通過的 shared server 類測試突然大量 skip 化
- 即使設定 `PYTEST_STRICT_AUTOSTART_SERVER=1` 也看不到原因

### 2. OS 專屬測試

Linux 專屬的 sandbox / AppArmor / process isolation 類。在 Windows 上 skip 是正確的。

代表例：

- `tests/basic/test_os_isolation.py`
- `tests/test_process_isolation_integration.py`

代表性的原因：

- `Linux only`
- `AppArmor is Linux-specific`

這是**正常的 skip**。

### 3. 任意依賴、外部元件缺失

特定套件或外部節點缺失的環境中，這些測試不執行。

代表例：

- mDNS 實機 E2E：`optional zeroconf package is not installed`
- 瀏覽器啟動：`Playwright unavailable`、`launch failed`
- ONNX / YAML / ComfyUI / 外部推論節點未連接

這是**正常的 skip**。不是修復對象，只是前置環境不完整。

### 4. 測試資料不足

需要影像、搜尋結果、對話日誌、多件資料等的瀏覽器測試，在輕量級資料庫中無法進行，因此被 skip。

代表性的原因：

- `No search results available in database`
- `DB 中無影像，因此跳過`
- `需要 2 件以上的檔案`
- `No prompts to test copy`

這**大致上是正常的 skip**。但若本該由 fixture 準備必要資料的測試才是過時化的嫌疑。

### 5. 頻率限制、外部 API 保護

某些整合測試會尊重外部服務或頻率限制而 skip。

代表性的原因：

- `因為達到頻率限制而跳過`

這是**正常的 skip**。

### 6. 長時間 fuzz / burn-in

`tests/fuzz/` 下的 burn-in 用於耐久性和崩潰復原性檢查，而非常規迴歸測試。

預設由 `pytest.ini` 中的 marker 式排除。

執行時：

```powershell
venv\Scripts\python.exe -m pytest tests\fuzz -q -m fuzz
```

必要時：

```powershell
$env:FUZZ_DURATION="60"
venv\Scripts\python.exe -m pytest tests\fuzz\test_api_fuzz.py -q -m fuzz
```

這**不應該混入常規的 broad run**。

## 應視為異常的模式

以下不應「skip 就沒問題」而草草結束，應納入測試維護對象。

### A. 以前通過的輕量級測試掉進 setup skip

例：

- 本應僅靠 app/client fixture 完整運作的 API smoke，被捲入 shared server 前提
- migration / schema / DB helper 的 unit test 因 runtime global state 初始化前提而掉落

此時應懷疑 test harness 與實裝的前提不一致。

### B. broad run 通過，單獨執行時才失敗

典型例：

- 依賴 process-global state
- broad run 中碰巧由先行測試初始化的副作用

應將單獨執行恢復到可再現的狀態。

### C. Skip 原因不明確

不好的例：

- `failed`
- `not ready`
- `something wrong`

Skip 原因應簡明扼要地寫出「缺少什麼導致跳過」。

## 修復的優先順序

1. 修復導致 broad run 停止的 hard failure
2. 修復只在單獨執行時崩潰的過時測試
3. 將瀏覽器 / 伺服器相依的 skip 改為安全的 skip，而非 fail
4. 維持任意依賴和實機相依的 optional skip

## 此次整備固定的項目

- 瀏覽器 / 伺服器依賴統一為 shared server unavailable 時 skip 而非 fail
- 授權許可稽核改為僅查看 `requirements*.txt` 宣告的依賴，而非整個 venv
- test DB 滿足當前搜尋架構的 path FTS 前提
- migration 54 / 55 已修正為對架構進化和執行時 state 未初始化不脆弱

## 迷茫時的判斷基準

- 缺少前置環境→skip 即可
- 現行實裝無法追蹤的舊期望值→修復測試
- 依賴 broad run 副作用→修復實裝或測試
- unit test 要求 process-global state→質疑設計
