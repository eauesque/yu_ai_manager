# Hailo Auto-Reboot Phase 0.5 — Operations Runbook for This Environment

**Created**: 2026-05-17 (v4.215.1)
**Target environment**: — Pi 5 running this repository
**Purpose**: A self-contained runbook to start, verify, and conclude Phase 0.5 observation even if the originating chat session is lost.
**Design spec**: `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md` (rev3 APPROVED)
**General operator guide**: `docs/en/hailo/HAILO_AUTO_REBOOT_PHASE05.md` (this document is the environment-specific variant)

---

## 0. Prerequisites and Already-Completed Work

- Phase 0.5 observation implementation merged and pushed to main in v4.215.1 (commit `80af4fb73` + merge `69be148c6`)
- `config.json` (repository root) already has the `hailo.auto_reboot` block added **as of 2026-05-17**
  - Recommended settings: `mode = "lazy"` + `dry_run = true`
  - Backup: `config.json.bak.<timestamp>`
- **No actual reboot will be triggered** (`dry_run = true` + Phase 0.5 design only records `would_fire` events)

Verify config.json:

```bash
cd /home/pi/GitHub/yu_ai_manager
jq .hailo.auto_reboot config.json
# → {"mode":"lazy","dry_run":true,...} should appear
```

---

## 1. Initial Startup and Activation Procedure

### 1.1 Server Restart

A restart is required to apply the config change. **Restart using the same startup method currently in use.**

Typical startup command (adjust to your environment):

```bash
cd /home/pi/GitHub/yu_ai_manager
uv run python web_ui.py --config config.json --db data/tags.db
```

If running as a systemd service, restart the relevant unit with `sudo systemctl restart <unit>`.

### 1.2 Verification Within 30 Seconds of Startup (3 Checks)

#### A. Is the `boot_baseline` event recorded?

```bash
tail -n 20 /home/pi/GitHub/yu_ai_manager/logs/hailo_auto_reboot.log
```

Expected: one line containing `{"event":"boot_baseline","state":"idle","mode":"lazy","dry_run":true,"cma_free_mb":<int|null>,"hailo_runtime_version":"5.3.0",...}`.

**Troubleshooting if absent**:

- `logs/hailo_auto_reboot.log` does not exist → judge loop is not running (possibly not started in `["full"]` mode, or `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` env var is set)
- File exists but is empty → path resolution failure in `core/hailo_device_core/auto_reboot_logger.py`; check `logs/` directory permissions
- `cma_free_mb: null` → `/proc/meminfo` read failure (expected behavior when running on non-Pi hardware, harmless)

#### B. Is the opt-in active via `/api/system/cma` response?

If logged in via PIN in the browser, no API key is needed. Either use curl or run in the browser DevTools console while PIN-logged in:

```js
fetch("/ext/hailo-genai/api/system/cma").then(r => r.json()).then(j => console.log(j.cma.auto_reboot))
```

Expected:

```json
{
  "enabled": true,
  "mode": "lazy",
  "dry_run": true,
  "state": "idle",
  "consecutive_rejects": 0
}
```

If `enabled: false` or `mode: "off"` → verify that `hailo.auto_reboot.mode` in config.json is `"lazy"` and the server has fully restarted.

#### C. Are there no startup errors in `error.log`?

```bash
tail -n 50 /home/pi/GitHub/yu_ai_manager/logs/error.log | grep -iE "hailo_auto_reboot|auto_reboot"
```

No output means OK. If errors appear, refer to "8. Known Pitfalls" at the end of this document.

---

## 2. Day-to-Day Operations During the Observation Period

### 2.1 Normal Usage

**Main action**:

- **Use LLM chat as usual** via `/ext/hailo-genai/chat` or `/tools` (e.g., Qwen3-1.7B)
- Use VLM / S2T as needed
- Extended sessions (30+ minutes continuous) and multiple model switches are also worth trying intentionally to broaden the observation data

No special testing is required. **The more you use it normally, the more data Phase 0.5 collects** — that is the design intent.

### 2.2 Weekly Review (Once per week, ~5 minutes)

```bash
cd /home/pi/GitHub/yu_ai_manager

# Count of each event type
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c

# Timestamps and CmaFree for would_fire events
grep would_fire logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb] | @tsv'

# reason for drain_entered (cma vs. rejects)
grep drain_entered logs/hailo_auto_reboot.log | jq -r '[.ts, .cma_free_mb, .consecutive_rejects, .reason] | @tsv' 2>/dev/null || \
  grep drain_entered logs/hailo_auto_reboot.log | head -10
```

**Checkpoints**:

- `would_fire` has 1 or more occurrences → Phase 1 rollout is worthwhile (verify whether the recorded timestamps match when manual reboots were performed)
- `prewarn_entered` fires frequently but never progresses to `drain_entered` → `prewarn_threshold_mb` (80 MB) may be too low; re-calibrate
- `drain_entered` reason is always `rejects` → DRAIN is reject-driven; a different mitigation is needed beyond threshold re-calibration

---

## 3. End-of-Observation and Phase 1 Rollout Decision Criteria

### 3.1 Required Observation Period

**Minimum 7 days / Recommended 14 days**. The period should cover at least the following patterns:

- Normal LLM chat
- Extended LLM chat (30+ minutes in a single session)
- VLM / S2T model switching
- At least one `acquire_genai` pre-rejection (insufficient CmaFree)
- First load after a Pi reboot

### 3.2 Numeric Criteria for Phase 1 Rollout

Aggregate:

```bash
cd /home/pi/GitHub/yu_ai_manager
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

Decision table:

| Observation result | Phase 1 decision |
|---|---|
| `would_fire` ≥ 1 | **GO** (automated rebooting has value) |
| `would_fire` = 0, `drain_entered` ≥ 1 | Re-adjust thresholds and consider Phase 1 (DRAIN is reached but `would_fire` is not — `fire_grace_seconds` may be shortened) |
| `prewarn_entered` only, `drain_entered` = 0 | Current thresholds never reach "critical" state → Phase 1 may not be needed depending on usage patterns |
| All events 0 (only `boot_baseline`) | CMA does not become exhausted with this usage → Phase 1 not needed |

### 3.3 Post-Observation Tasks

1. Save aggregated results to `docs/en/hailo/HAILO_AUTO_REBOOT_PHASE05_OBSERVATION_RESULTS.md` (new file)
2. If proceeding to Phase 1: move on to Phase 1 (UI DRAIN banner + i18n) in spec rev3 §5.2; re-confirm thresholds in §3.1 based on observation data
3. If Phase 1 is not needed: set `mode = "off"` in config.json and archive the observation log

---

## 4. Disabling the Feature (Emergency / Stopping Observation)

```bash
cd /home/pi/GitHub/yu_ai_manager
jq '.hailo.auto_reboot.mode = "off"' config.json > config.json.tmp && mv config.json.tmp config.json
# Restart the server
```

Even with `mode = "off"`, JSONL events continue to be recorded (WARN output to `error.log` is suppressed). To disable completely, use the env var:

```bash
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 5. Log File Reference (Related Files)

| File | Purpose |
|---|---|
| `logs/hailo_auto_reboot.log` | **Primary log for this feature**. JSONL format; rotates at 10 MB × 30 backups |
| `logs/hailo_cma.log` | Existing CMA event logger (since v4.214.10). Records VDevice/model lifecycle events such as `acquire_genai` |
| `logs/error.log` | Application-wide error log. When `mode != "off"`, also outputs WARN summaries for `drain_entered` / `would_fire` |

---

## 6. Related Code Locations (For Future Investigation)

| Feature | File |
|---|---|
| State machine + RejectTracker | `core/hailo_device_core/auto_reboot.py` |
| JSONL writer | `core/hailo_device_core/auto_reboot_logger.py` |
| Background loop entry | `core/web/startup_background_hailo_judge.py` |
| Background task registration | `core/web/startup_background.py` (`hailo_auto_reboot_judge`) |
| Config defaults | `core/configuration/defaults.py` (`hailo.auto_reboot`) |
| acquire_genai hook | `core/hailo_device_core/device_manager_genai.py` |
| `/api/system/cma` extension | `extensions/builtin_hailo_genai/hailo_genai_ext.py` |
| Unit tests | `tests/test_hailo_auto_reboot_judge.py`, `tests/test_hailo_auto_reboot_logger.py` |

---

## 7. Review History (Reference)

This implementation passed the full AGENTS review workflow (see the v4.215.1 commit message). Individual report files were written under `.claude/agent-outputs/`, which are listed in `.gitignore` and not tracked by git. They can be regenerated if needed.

---

## 8. Known Pitfalls

| Symptom | Cause and remedy |
|---|---|
| Nothing appears in `logs/hailo_auto_reboot.log` | Server not restarted / `mode = "off"` still set / not started in `["full"]` mode / `TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE` env var is set |
| `cma_free_mb: null` persists | Running on non-Pi hardware (e.g., WSL2) or `/proc/meminfo` read failure; re-verify on actual Pi hardware |
| `hailo_runtime_version: null` | `hailo_platform` package not installed in this environment; on actual Pi 5, HailoRT 5.3.0 runtime will populate this |
| `would_fire` never appears | Usage load is too light or thresholds are too loose; try extended continuous chat / model switching and re-observe |
| `eager` mode is configured but not working | In Phase 0.5, `eager` intentionally falls back to `off` (with a warning log); scheduled for implementation in Phase 1+ |

---

## 9. Emergency Rollback

In the unlikely event that the Phase 0.5 implementation itself has a problem (low probability since no actual reboots are triggered):

```bash
cd /home/pi/GitHub/yu_ai_manager
# Roll back from v4.215.1 to v4.214.13 (spec only, pre-implementation)
git revert -m 1 69be148c6
git push
```

Or **disable completely via config only** (recommended):

```bash
# Add to the startup environment and restart the server
TAGDB_DISABLE_HAILO_AUTO_REBOOT_JUDGE=1 uv run python web_ui.py ...
```

---

## 10. Maintenance of This Document

- When observation is complete, **append the §3.3 aggregated results to the end of this document** (needed for Phase 1 decision in future chat sessions)
- After Phase 1 rollout, rename this document to `HAILO_AUTO_REBOOT_PHASE05_RUNBOOK_ARCHIVED.md` and create a new Phase 1 runbook
- This document lives at `/home/pi/GitHub/yu_ai_manager/docs/en/hailo/HAILO_AUTO_REBOOT_PHASE05_RUNBOOK.md` (git-tracked)
