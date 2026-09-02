# Hailo 自動重開機 Phase 0.5 操作指南

**建立日期**：2026-05-17 (v4.215.0)
**適用對象**：Raspberry Pi 5 + Hailo-10H + HailoRT 5.3.0 的 CMA leak 觀測運作
**狀態**：觀測階段。不執行實際重開機，僅記錄 `would_fire` 事件。

---

## 1. Phase 0.5 的目的

Phase 0.5 是針對 HailoRT 5.3.0 + `hailo1x_pci` 的 CMA leak，所設計的自動重開機系統的觀測階段。

在此階段，判定器會計算以下狀態：

| 狀態 | 條件 |
|---|---|
| `idle` | 正常狀態 |
| `prewarn` | `CmaFree < 80 MB` 持續 180 秒 |
| `draining` | `CmaFree < 30 MB` 持續 60 秒，或 `acquire_genai` 的事前 reject 連續發生 3 次 |
| `would_fire` | 從 `draining` 經過 120 秒 |

重要：在 Phase 0.5 中，即使到達 `would_fire`，也不會重開機 Pi。僅以 JSON Lines 格式記錄至 `logs/hailo_auto_reboot.log`。

---

## 2. 預設值為 `mode = "off"` 的原因

`hailo.auto_reboot.mode` 的預設值為 `"off"`。由於自動重開機可能會中斷操作者的作業，因此只在操作者明確 opt-in 的環境中才開始觀測。

Phase 0.5 的建議設定如下：

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "prewarn_threshold_mb": 80,
      "prewarn_duration_seconds": 180,
      "drain_threshold_mb": 30,
      "drain_duration_seconds": 60,
      "drain_consecutive_rejects": 3,
      "fire_grace_seconds": 120,
      "poll_interval_seconds": 30
    }
  }
}
```

`dry_run = true` 是 Phase 0.5 的前提。實際的重開機路徑在 Phase 4 以後處理。

### 2.1 Opt-in 步驟

啟動時的 config 優先使用透過 `--config` 或 `TAGDB_CONFIG` 指定的檔案。若未指定，則依序讀取 repository 根目錄的 `config.json`，再讀取 `tagdb_config.json`。

範例：

```bash
cd <repo>
cp config.json config.json.bak.$(date +%Y%m%d-%H%M%S)
```

在 `<repo>/config.json` 或運作時透過 `--config` / `TAGDB_CONFIG` 指定的 JSON 中，新增以下設定：

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "lazy",
      "dry_run": true,
      "poll_interval_seconds": 30
    }
  }
}
```

重新啟動伺服器以套用設定。請根據您的啟動方式，保留實際使用的引數。

```bash
uv run python web_ui.py --config config.json --db data/tags.db
```

若使用 systemd 運作，請重新啟動該 unit：

```bash
sudo systemctl restart yu-ai-manager.service
```

### 2.2 停用步驟

在相同的 config 中將 `hailo.auto_reboot.mode` 改回 `"off"`，並重新啟動伺服器。

```json
{
  "hailo": {
    "auto_reboot": {
      "mode": "off",
      "dry_run": true
    }
  }
}
```

設定 `mode = "off"` 時，JSON Lines 的觀測事件仍會保留，但不會在 `error.log` 中輸出 WARN 摘要。

---

## 3. 日誌的閱讀方式

觀測日誌會輸出至以下檔案：

```text
logs/hailo_auto_reboot.log
```

格式為 JSON Lines。主要事件如下：

| 事件 | 意義 |
|---|---|
| `boot_baseline` | 啟動時的觀測起始點 |
| `prewarn_entered` | PREWARN 條件成立 |
| `drain_entered` | DRAIN 條件成立 |
| `would_fire` | 在 Phase 1+ 中會成為重開機觸發候選的時間點 |
| `drain_cleared` | CMA 恢復，DRAIN 解除 |

範例：

```json
{"event":"would_fire","cma_free_mb":18,"mode":"lazy","dry_run":true,"state":"would_fire","hailo_runtime_version":"5.3.0"}
```

確認指令範例：

```bash
tail -F logs/hailo_auto_reboot.log | jq -r '[.ts, .event, .cma_free_mb, .state] | @tsv'
```

```bash
grep would_fire logs/hailo_auto_reboot.log
grep drain_entered logs/hailo_auto_reboot.log
```

若 `would_fire` 頻繁發生，表示以目前的閾值，在實際運作中很可能需要重開機 Pi。反之，若只出現 `prewarn_entered` 而未進入 `drain_entered`，則可在 Phase 1 前重新調整閾值或寬限時間。

---

## 4. API 確認步驟

使用 admin API key 確認 `/api/system/cma`。

```bash
curl -H "X-API-Key: <admin-key>" \
  http://<host>:<port>/ext/hailo-genai/api/system/cma
```

查看回應中的 `cma.auto_reboot.enabled`、`cma.auto_reboot.mode`、`cma.auto_reboot.state`、`cma.auto_reboot.consecutive_rejects`。

```json
{
  "cma": {
    "auto_reboot": {
      "enabled": true,
      "mode": "lazy",
      "state": "idle",
      "consecutive_rejects": 0
    }
  }
}
```

---

## 5. 觀測期間

目標為 1〜2 週。請確保觀測期間至少包含以下模式：

- LLM 的一般聊天使用
- 長時間聊天使用
- 導致 Hailo GenAI model 載入失敗或事前 reject 的操作
- Pi 重開機後的首次載入

觀測完成的目標，是能夠統計 1〜2 週份的 `prewarn_entered` / `drain_entered` / `would_fire` 發生頻率。觀測結束後，查看 `would_fire` 的次數、`drain_entered` 的原因（`cma` / `rejects`）以及 `CmaFree` 的下降速度，在部署 Phase 1 前重新確定閾值。

統計範例：

```bash
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

---

## 6. 相關資料

- `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md`
- `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- `logs/hailo_cma.log` (`core/hailo_device_core/device_helpers.py::log_hailo_cma_event`)
- `logs/hailo_auto_reboot.log` (`core/hailo_device_core/auto_reboot_logger.py`)
