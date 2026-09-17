# Hailo Auto-Reboot Phase 0.5 — 本环境操作手册

**创建日期**: 2026-05-17 (v4.215.1)
**目标环境**: 本仓库运行的 Pi 5
**本文目的**: 即使原始聊天会话记录丢失，仅凭本手册也能完整开始、确认及结束 Phase 0.5 观测。
**设计规格**: `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md` (rev3 APPROVED)
**通用操作指南**: `docs/zh-cn/hailo/HAILO_AUTO_REBOOT_PHASE05.md`（本文为其环境专用版本）

---

## 0. 前提条件与已完成的工作

- v4.215.1 中 Phase 0.5 观测实现已合并并推送至 main（commit `80af4fb73` + merge `69be148c6`）
- `config.json`（仓库根目录）已于 **2026-05-17** 添加 `hailo.auto_reboot` 块
  - 推荐设置：`mode = "lazy"` + `dry_run = true`
  - 备份：`config.json.bak.<时间戳>`
- **不会触发实际重启**（`dry_run = true` + Phase 0.5 设计仅记录 `would_fire` 事件）

确认 config.json：

```bash
cd /home/pi/GitHub/yu_ai_manager
jq .hailo.auto_reboot config.json
# → 应显示 {"mode":"lazy","dry_run":true,...}
```

---

## 1. 首次启动与启用流程

### 1.1 服务器重新启动

必须重启以应用 config 变更。**请使用当前的启动方式重新启动**。

典型启动命令（依实际环境调整）：

```bash
cd /home/pi/GitHub/yu_ai_manager
uv run python web_ui.py --config config.json --db data/tags.db
```

若已配置为 systemd 服务，请使用 `sudo systemctl restart <unit>` 重启对应 unit。

### 1.2 启动后 30 秒内的确认（3 项）

#### A. `boot_baseline` 事件是否已记录？

```bash
tail -n 20 /home/pi/GitHub/yu_ai_manager/logs/hailo_auto_reboot.log
```

预期结果：出现一行 `{"event":"boot_baseline","state":"idle","mode":"lazy","dry_run":true,"cma_free_mb":<int|null>,"hailo_runtime_version":"5.3.0",...}`。

**未出现时的排障步骤**：

- `logs/hailo_auto_reboot.log` 不存在 → judge loop 未启动（可能未以 `["full"]` 模式启动，或已设置 `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` 环境变量）
- 文件存在但为空 → `core/hailo_device_core/auto_reboot_logger.py` 路径解析失败；请检查 `logs/` 目录的权限
- `cma_free_mb: null` → `/proc/meminfo` 读取失败（在非 Pi 硬件上运行时的预期行为，无害）

#### B. `/api/system/cma` 响应中 opt-in 是否已生效？

若已在浏览器以 PIN 登录，则不需要 API key。可使用 curl 或在浏览器 DevTools 控制台（PIN 登录中）执行：

```js
fetch("/ext/hailo-genai/api/system/cma").then(r => r.json()).then(j => console.log(j.cma.auto_reboot))
```

预期结果：

```json
{
  "enabled": true,
  "mode": "lazy",
  "dry_run": true,
  "state": "idle",
  "consecutive_rejects": 0
}
```

若 `enabled: false` 或 `mode: "off"` → 请确认 config.json 中的 `hailo.auto_reboot.mode` 是否为 `"lazy"`，以及服务器是否已完成重启。

#### C. `error.log` 中是否有启动错误？

```bash
tail -n 50 /home/pi/GitHub/yu_ai_manager/logs/error.log | grep -iE "hailo_auto_reboot|auto_reboot"
```

无输出即为正常。若有错误，请参阅本文末尾「8. 已知问题」。

---

## 2. 观测期间的日常操作

### 2.1 正常使用

**主要操作**：

- 通过 `/ext/hailo-genai/chat` 或 `/tools` **如往常使用 LLM 聊天**（例如 Qwen3-1.7B）
- 按需使用 VLM / S2T
- 长时间聊天（连续 30 分钟以上）及多模型切换也值得刻意尝试，以拓宽观测数据的范围

无需特殊验证。**越正常使用，数据越丰富** — 这正是 Phase 0.5 的设计意图。

### 2.2 每周审查（每周 1 次，约 5 分钟）

```bash
cd /home/pi/GitHub/yu_ai_manager

# 各事件类型的发生次数
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c

# would_fire 的发生时间与 CmaFree
grep would_fire logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb] | @tsv'

# drain_entered 的原因（cma 还是 rejects）
grep drain_entered logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb, .consecutive_rejects, .reason] | @tsv' 2>/dev/null || \
  grep drain_entered logs/hailo_auto_reboot.log | head -10
```

**检查点**：

- `would_fire` 出现 1 次以上 → Phase 1 部署具有价值（确认记录的时间是否与手动重启的时间吻合）
- `prewarn_entered` 频繁触发但未进入 `drain_entered` → `prewarn_threshold_mb`（80 MB）可能过低，需重新确认
- `drain_entered` 的原因均为 `rejects` → DRAIN 由 reject 驱动，需要不同于阈值调整的对策

---

## 3. 观测结束与 Phase 1 部署判断基准

### 3.1 所需观测期间

**最少 7 天 / 建议 14 天**。观测期间至少须涵盖以下模式：

- LLM 一般聊天
- LLM 长时间连续聊天（单次会话 30 分钟以上）
- VLM / S2T 模型切换
- 至少 1 次 `acquire_genai` 事前拒绝（CmaFree 不足）
- Pi 重启后的首次加载

### 3.2 Phase 1 部署的数值基准

汇总：

```bash
cd /home/pi/GitHub/yu_ai_manager
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

判断表：

| 观测结果 | Phase 1 判断 |
|---|---|
| `would_fire` ≥ 1 件 | **GO**（自动重启具有价值） |
| `would_fire` = 0、`drain_entered` ≥ 1 件 | 重新调整阈值后考虑部署 Phase 1（已到达 DRAIN 但未触发 would_fire = `fire_grace_seconds` 有缩短空间） |
| 仅 `prewarn_entered`、`drain_entered` = 0 | 当前阈值从未达到「严重」状态 → 依使用模式判断是否需要 Phase 1 |
| 所有事件均为 0（仅 `boot_baseline`） | 此使用方式不会耗尽 CMA → 不需要 Phase 1 |

### 3.3 观测完成后的工作

1. 将汇总结果保存至 `docs/zh-cn/hailo/HAILO_AUTO_REBOOT_PHASE05_OBSERVATION_RESULTS.md`（新建）
2. 若部署 Phase 1：进入规格 rev3 §5.2 的 Phase 1（UI DRAIN 横幅 + i18n）；依观测数据重新确认 §3.1 阈值
3. 若不需要 Phase 1：在 config.json 中将 `mode` 改为 `"off"`，并归档观测日志

---

## 4. 停用流程（紧急情况 / 停止观测时）

```bash
cd /home/pi/GitHub/yu_ai_manager
jq '.hailo.auto_reboot.mode = "off"' config.json > config.json.tmp && mv config.json.tmp config.json
# 重启服务器
```

即使设为 `mode = "off"`，JSONL 事件仍会继续记录（仅抑制输出至 `error.log` 的 WARN）。若要完全停止，请使用环境变量：

```bash
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 5. 日志文件清单（相关）

| 文件 | 用途 |
|---|---|
| `logs/hailo_auto_reboot.log` | **本功能的主日志**。JSONL 格式；10 MB × 30 个备份进行轮转 |
| `logs/hailo_cma.log` | 现有的 CMA 事件记录器（自 v4.214.10 起）。记录 `acquire_genai` 等 VDevice/模型生命周期事件 |
| `logs/error.log` | 应用程序全局错误日志。`mode != "off"` 时也会输出 `drain_entered` / `would_fire` 的 WARN 摘要 |

---

## 6. 相关代码位置（供日后调查使用）

| 功能 | 文件 |
|---|---|
| 状态机 + RejectTracker | `core/hailo_device_core/auto_reboot.py` |
| JSONL writer | `core/hailo_device_core/auto_reboot_logger.py` |
| 后台循环入口 | `core/web/startup_background_hailo_judge.py` |
| 后台任务注册 | `core/web/startup_background.py`（`hailo_auto_reboot_judge`） |
| Config 默认值 | `core/configuration/defaults.py`（`hailo.auto_reboot`） |
| acquire_genai hook | `core/hailo_device_core/device_manager_genai.py` |
| `/api/system/cma` 扩展 | `extensions/builtin_hailo_genai/hailo_genai_ext.py` |
| 单元测试 | `tests/test_hailo_auto_reboot_judge.py`、`tests/test_hailo_auto_reboot_logger.py` |

---

## 7. 审查历程（参考用）

本实现已通过 AGENTS 规定的完整审查流程（请参阅 v4.215.1 commit 信息）。各报告文件已写入 `.claude/agent-outputs/` 目录，但该目录已列入 `.gitignore`，不受 git 管理。如有需要可重新生成。

---

## 8. 已知问题

| 症状 | 原因与对策 |
|---|---|
| `logs/hailo_auto_reboot.log` 无任何输出 | 服务器未重启 / `mode = "off"` 仍有效 / 未以 `["full"]` 模式启动 / 已设置 `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` 环境变量 |
| `cma_free_mb: null` 持续出现 | 在非 Pi 硬件（例如 WSL2）上运行，或 `/proc/meminfo` 读取失败；请在实际 Pi 硬件上重新确认 |
| `hailo_runtime_version: null` | 此环境未安装 `hailo_platform` 包；在实际 Pi 5 上，若已安装 HailoRT 5.3.0 runtime 即可获取 |
| `would_fire` 从未出现 | 使用负载过轻，或阈值过宽；请尝试长时间连续聊天 / 模型切换后重新观测 |
| 已设置 `eager` 模式但未生效 | Phase 0.5 中，`eager` 刻意回退至 `off`（并输出警告日志）；计划于 Phase 1+ 实现 |

---

## 9. 紧急回滚

若万一 Phase 0.5 实现本身出现问题（由于不会触发实际重启，可能性极低）：

```bash
cd /home/pi/GitHub/yu_ai_manager
# 从 v4.215.1 回滚至 v4.214.13（仅规格，实现前）
git revert -m 1 69be148c6
git push
```

或**仅通过设置完全停用**（推荐）：

```bash
# 添加至启动环境并重启服务器
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 10. 本文的维护

- 观测完成时，**将 §3.3 汇总结果追加至本文末尾**（日后聊天会话进行 Phase 1 判断时需要）
- 部署 Phase 1 后，请将本文重命名为 `HAILO_AUTO_REBOOT_PHASE05_RUNBOOK_ARCHIVED.md`，并新建 Phase 1 手册
- 本文置于 `/home/pi/GitHub/yu_ai_manager/docs/zh-cn/hailo/HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md`（git 管理下）
