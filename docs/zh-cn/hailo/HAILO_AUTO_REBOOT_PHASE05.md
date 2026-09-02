# Hailo 自动重启 Phase 0.5 操作指南

**创建日期**：2026-05-17 (v4.215.0)
**适用对象**：Raspberry Pi 5 + Hailo-10H + HailoRT 5.3.0 的 CMA leak 观测运营
**状态**：观测阶段。不执行实际重启，仅记录 `would_fire` 事件。

---

## 1. Phase 0.5 的目的

Phase 0.5 是针对 HailoRT 5.3.0 + `hailo1x_pci` 的 CMA leak 所设计的自动重启系统的观测阶段。

在此阶段，判定器会计算以下状态：

| 状态 | 条件 |
|---|---|
| `idle` | 正常状态 |
| `prewarn` | `CmaFree < 80 MB` 持续 180 秒 |
| `draining` | `CmaFree < 30 MB` 持续 60 秒，或 `acquire_genai` 的预先 reject 连续发生 3 次 |
| `would_fire` | 从 `draining` 经过 120 秒 |

重要：在 Phase 0.5 中，即使到达 `would_fire`，也不会重启 Pi。仅以 JSON Lines 格式记录至 `logs/hailo_auto_reboot.log`。

---

## 2. 默认值为 `mode = "off"` 的原因

`hailo.auto_reboot.mode` 的默认值为 `"off"`。由于自动重启可能会中断操作者的工作，因此只在操作者明确 opt-in 的环境中才开始观测。

Phase 0.5 的推荐配置如下：

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

`dry_run = true` 是 Phase 0.5 的前提。实际的重启路径在 Phase 4 及以后处理。

### 2.1 Opt-in 步骤

启动时的 config 优先使用通过 `--config` 或 `TAGDB_CONFIG` 指定的文件。若未指定，则依次读取 repository 根目录的 `config.json`，再读取 `tagdb_config.json`。

示例：

```bash
cd <repo>
cp config.json config.json.bak.$(date +%Y%m%d-%H%M%S)
```

在 `<repo>/config.json` 或运营时通过 `--config` / `TAGDB_CONFIG` 指定的 JSON 中，添加以下配置：

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

重新启动服务器以应用配置。请根据您的启动方式，保留实际使用的参数。

```bash
uv run python web_ui.py --config config.json --db data/tags.db
```

若使用 systemd 运营，请重新启动该 unit：

```bash
sudo systemctl restart yu-ai-manager.service
```

### 2.2 禁用步骤

在相同的 config 中将 `hailo.auto_reboot.mode` 改回 `"off"`，并重新启动服务器。

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

设置 `mode = "off"` 时，JSON Lines 的观测事件仍会保留，但不会在 `error.log` 中输出 WARN 摘要。

---

## 3. 日志的读取方式

观测日志会输出至以下文件：

```text
logs/hailo_auto_reboot.log
```

格式为 JSON Lines。主要事件如下：

| 事件 | 含义 |
|---|---|
| `boot_baseline` | 启动时的观测起始点 |
| `prewarn_entered` | PREWARN 条件成立 |
| `drain_entered` | DRAIN 条件成立 |
| `would_fire` | 在 Phase 1+ 中会成为重启触发候选的时间点 |
| `drain_cleared` | CMA 恢复，DRAIN 解除 |

示例：

```json
{"event":"would_fire","cma_free_mb":18,"mode":"lazy","dry_run":true,"state":"would_fire","hailo_runtime_version":"5.3.0"}
```

确认命令示例：

```bash
tail -F logs/hailo_auto_reboot.log | jq -r '[.ts, .event, .cma_free_mb, .state] | @tsv'
```

```bash
grep would_fire logs/hailo_auto_reboot.log
grep drain_entered logs/hailo_auto_reboot.log
```

若 `would_fire` 频繁发生，表示以当前阈值，在实际运营中很可能需要重启 Pi。反之，若只出现 `prewarn_entered` 而未进入 `drain_entered`，则可在 Phase 1 前重新调整阈值或宽限时间。

---

## 4. API 确认步骤

使用 admin API key 确认 `/api/system/cma`。

```bash
curl -H "X-API-Key: <admin-key>" \
  http://<host>:<port>/ext/hailo-genai/api/system/cma
```

查看响应中的 `cma.auto_reboot.enabled`、`cma.auto_reboot.mode`、`cma.auto_reboot.state`、`cma.auto_reboot.consecutive_rejects`。

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

## 5. 观测期间

目标为 1〜2 周。请确保观测期间至少包含以下模式：

- LLM 的一般聊天使用
- 长时间聊天使用
- 导致 Hailo GenAI model 加载失败或预先 reject 的操作
- Pi 重启后的首次加载

观测完成的目标，是能够统计 1〜2 周份的 `prewarn_entered` / `drain_entered` / `would_fire` 发生频率。观测结束后，查看 `would_fire` 的次数、`drain_entered` 的原因（`cma` / `rejects`）以及 `CmaFree` 的下降速度，在部署 Phase 1 前重新确认阈值。

统计示例：

```bash
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

---

## 6. 相关资料

- `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md`
- `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- `logs/hailo_cma.log` (`core/hailo_device_core/device_helpers.py::log_hailo_cma_event`)
- `logs/hailo_auto_reboot.log` (`core/hailo_device_core/auto_reboot_logger.py`)
