# OS 層級隔離指南

此功能利用作業系統內建的安全機制，限制擴充功能（Extension）對系統的影響。

## 1. 什麼是 OS 隔離？

在智慧型手機上安裝應用程式時，您會看到「此應用程式要求存取您的相機」等提示。OS 隔離的原理完全相同。

根據 Extension 宣告的權限（檔案讀寫、網路通訊、執行外部指令等），**作業系統核心會實體阻擋未授權的操作**。無論 Python 程式碼中使用了什麼技巧，核心層級的限制都無法繞過。

> **注意**：此功能主要用於安全地使用第三方 Extension。`builtin-*` Extension 被視為受信任（L0），不受任何限制。

---

## 2. 支援的平台

| 作業系統 | 隔離方式 | 成熟度 |
|---------|---------|--------|
| **Linux** | AppArmor（強制存取控制） | 建議使用，正式環境可用 |
| **macOS** | sandbox-exec（Seatbelt） | 實驗性（Apple 已標記為棄用） |
| **Windows** | Restricted Token + Job Object | 基本資源限制 |

Linux 的 AppArmor 完成度最高，是建議的運行環境。

---

## 3. Linux 設定（AppArmor）

### 3.1 什麼是 AppArmor？

AppArmor 是內建於 Linux 核心的安全模組。它為每個程序定義設定檔，指定哪些檔案可以讀寫、是否允許網路通訊，並由核心強制執行。

Ubuntu / Debian 通常預設啟用 AppArmor，但 Raspberry Pi OS 等部分發行版需要手動啟用。

### 3.2 自動化設定

使用隨附的設定腳本進行一鍵設定。

```bash
sudo bash scripts/setup-apparmor.sh
```

此腳本執行以下操作：

1. **檢查/安裝 AppArmor 套件** — 若未安裝 `apparmor` 和 `apparmor-utils` 則自動安裝
2. **新增核心參數** — 在 `/boot/firmware/cmdline.txt` 中加入 `lsm=apparmor`（含備份）
3. **設置 sudoers 規則** — 僅允許免密碼執行 `apparmor_parser` 指令（最小權限）
4. **啟用 AppArmor 服務** — 透過 systemd 設定開機自動啟動

> **非 Raspberry Pi OS 環境**：使用 GRUB 的系統請手動在 `/etc/default/grub` 的 `GRUB_CMDLINE_LINUX` 中加入 `lsm=apparmor`，然後執行 `sudo update-grub`。

### 3.3 重新開機

新增核心參數後需要重新開機。

```bash
sudo reboot
```

### 3.4 驗證

重新開機後，確認 AppArmor 是否已啟用。

```bash
# 檢查核心模組是否已啟用
cat /sys/module/apparmor/parameters/enabled
# → 顯示 "Y" 表示已啟用

# 列出已載入的設定檔
sudo aa-status
```

### 3.5 在 config.json 中啟用

確認 AppArmor 正常運作後，在 `config.json` 中加入以下設定。

```json
{
  "os_isolation": {
    "enabled": true,
    "linux": {
      "apparmor": true
    }
  }
}
```

完成設定後，第三方 Extension 啟動時會自動產生並載入 AppArmor 設定檔。

---

## 4. 設定項目參考

透過 `config.json` 的 `os_isolation` 區段進行控制。

```json
{
  "os_isolation": {
    "enabled": true,
    "linux": {
      "apparmor": true
    },
    "macos": {
      "sandbox_exec": false
    },
    "windows": {
      "restricted_token": true,
      "job_object": true,
      "job_limits": {
        "memory_mb": 512,
        "cpu_percent": 50,
        "max_processes": 10
      }
    }
  }
}
```

| 鍵 | 型別 | 預設值 | 說明 |
|----|------|--------|------|
| `enabled` | bool | `false` | 全域啟用/停用 OS 隔離 |
| `linux.apparmor` | bool | `true` | 使用 AppArmor 設定檔 |
| `macos.sandbox_exec` | bool | `false` | 使用 macOS sandbox-exec（實驗性） |
| `windows.restricted_token` | bool | `true` | 以受限權杖啟動程序 |
| `windows.job_object` | bool | `true` | 透過 Job Object 限制資源 |
| `windows.job_limits.memory_mb` | int | `512` | 每個 Extension 的最大記憶體 (MB) |
| `windows.job_limits.cpu_percent` | int | `50` | 每個 Extension 的 CPU 使用率上限 (%) |
| `windows.job_limits.max_processes` | int | `10` | 每個 Extension 可產生的最大程序數 |

---

## 5. Extension 權限與 AppArmor 規則的對應

AppArmor 設定檔會根據 Extension 的 `extension.json` 中宣告的權限自動產生。

| Extension 權限 | AppArmor 控制 |
|---------------|--------------|
| `db:read` | 僅允許讀取 `data/` 目錄 |
| `db:write` | 允許讀寫 `data/` 目錄 |
| `fs:read:scan_roots` | 允許讀取已設定的掃描根目錄 |
| `fs:write:any` | 允許讀寫所有路徑 |
| `network:local` | 允許 TCP/Unix socket（拒絕 UDP） |
| `network:internet` | 允許所有 TCP/UDP/Unix socket |
| `subprocess` | 允許執行 `/usr/bin/`、`/bin/` 等 |
| 無網路權限 | 明確拒絕 TCP/UDP，僅允許 IPC 用 Unix socket |
| 無 subprocess 權限 | 明確拒絕執行 `/usr/bin/`、`/bin/` 等 |

Extension 自身的目錄（`extensions/<name>/`）始終可讀寫。

---

## 6. 透過 API 確認狀態

OS 隔離的狀態可透過 API 查詢。

```bash
curl -s http://localhost:5000/api/extensions/os-isolation-info | python -m json.tool
```

回應範例（Linux / AppArmor 已啟用）：

```json
{
  "platform": "linux",
  "available": true,
  "method": "apparmor",
  "details": {
    "apparmor_kernel": "enabled",
    "apparmor_tools": true,
    "apparmor_sudoers": true,
    "aa_exec_path": "/usr/sbin/aa-exec"
  }
}
```

當 `available` 為 `false` 時，回應中會包含 `setup` 欄位，提供設定步驟。

---

## 7. 疑難排解

### AppArmor 未啟用

```bash
cat /sys/module/apparmor/parameters/enabled
# → "N" 或檔案不存在
```

**原因**：核心參數尚未套用。

**解決方法**：
- Raspberry Pi OS：確認 `/boot/firmware/cmdline.txt` 中有 `lsm=apparmor`，然後重新開機
- GRUB 環境：確認 `/etc/default/grub` 中 `GRUB_CMDLINE_LINUX="... lsm=apparmor"`，然後執行 `sudo update-grub && sudo reboot`

### Extension 啟動時出現「sudoers not configured」

**原因**：`apparmor_parser` 的 NOPASSWD sudoers 規則未設定。

**解決方法**：
```bash
sudo bash scripts/setup-apparmor.sh
```

腳本會在 `/etc/sudoers.d/yu-ai-apparmor` 設置必要的規則。

### Extension 因權限不足無法運作

**原因**：Extension 的 `extension.json` 中未宣告必要的權限。

**解決方法**：在 Extension 的 `extension.json` 的 `permissions.required` 中新增必要的權限，或從「設定 > 擴充功能」手動授予權限。

### 手動檢查 AppArmor 設定檔

產生的設定檔儲存在 `/tmp/yu_ai_apparmor/`。

```bash
# 檢視設定檔內容
cat /tmp/yu_ai_apparmor/yu_ai_ext_<extension_name>

# 列出目前已載入的 YU AI Manager 設定檔
sudo aa-status | grep yu_ai_ext
```

---

## 8. 安全注意事項

OS 隔離是縱深防禦策略的一部分。YU AI Manager 透過多重層級確保安全：

1. **靜態分析**（Phase 1）— 安裝時以 AST 分析 Extension 程式碼，檢測危險的 import
2. **權限閘道**（Phase 2-3）— 透過 ServiceRegistry 的權限檢查代理控制存取
3. **OS 隔離**（Phase 4）— 核心層級強制限制檔案、網路和程序執行

OS 隔離本身無法消除所有風險，但與其他防禦層結合後，可為使用第三方 Extension 提供安全的環境。

對於不受信任的 Extension，建議在啟用 OS 隔離的 Linux 環境中使用。
