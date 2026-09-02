# Hailo Auto-Reboot Phase 0.5 Operations Guide

**Created**: 2026-05-17 (v4.215.0)
**Target**: Raspberry Pi 5 + Hailo-10H + HailoRT 5.3.0 CMA leak observation operations
**Status**: Observation phase. No actual reboot is performed; `would_fire` events are recorded only.

---

## 1. Purpose of Phase 0.5

Phase 0.5 is the observation phase of the auto-reboot design against CMA leaks in HailoRT 5.3.0 + `hailo1x_pci`.

In this phase, the state machine calculates the following states:

| State | Condition |
|---|---|
| `idle` | Normal state |
| `prewarn` | `CmaFree < 80 MB` persists for 180 seconds |
| `draining` | `CmaFree < 30 MB` persists for 60 seconds, or `acquire_genai` pre-reject occurs 3 times consecutively |
| `would_fire` | 120 seconds elapsed since `draining` |

Important: In Phase 0.5, even if `would_fire` is reached, the Pi is NOT rebooted. The event is only recorded as JSON Lines in `logs/hailo_auto_reboot.log`.

---

## 2. Why the Default is `mode = "off"`

The default value of `hailo.auto_reboot.mode` is `"off"`. Because automatic reboot can interrupt the operator's work, observation is only started in environments where the operator has explicitly opted in.

The recommended configuration for Phase 0.5 is as follows:

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

`dry_run = true` is a prerequisite for Phase 0.5. The actual reboot path is handled in Phase 4 and later.

### 2.1 Opt-in Procedure

The startup config prioritizes the file specified via `--config` or `TAGDB_CONFIG`. If not specified, it reads `config.json` in the repository root, then `tagdb_config.json`.

Example:

```bash
cd <repo>
cp config.json config.json.bak.$(date +%Y%m%d-%H%M%S)
```

Add the following settings to `<repo>/config.json` or the JSON file specified via `--config` / `TAGDB_CONFIG` during operation:

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

Restart the server to apply the configuration. Keep the arguments you are actually using according to your startup method.

```bash
uv run python web_ui.py --config config.json --db data/tags.db
```

If operating with systemd, restart its unit:

```bash
sudo systemctl restart yu-ai-manager.service
```

### 2.2 Disabling

Return `hailo.auto_reboot.mode` to `"off"` in the same config and restart the server.

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

With `mode = "off"`, JSON Lines observation events remain, but no WARN summary is output to `error.log`.

---

## 3. How to Read the Logs

Observation logs are written to the following file:

```text
logs/hailo_auto_reboot.log
```

The format is JSON Lines. The main events are as follows:

| event | Meaning |
|---|---|
| `boot_baseline` | Observation start point at startup |
| `prewarn_entered` | PREWARN condition met |
| `drain_entered` | DRAIN condition met |
| `would_fire` | Point that would become a reboot trigger in Phase 1+ |
| `drain_cleared` | CMA recovered and DRAIN cleared |

Example:

```json
{"event":"would_fire","cma_free_mb":18,"mode":"lazy","dry_run":true,"state":"would_fire","hailo_runtime_version":"5.3.0"}
```

Example confirmation commands:

```bash
tail -F logs/hailo_auto_reboot.log | jq -r '[.ts, .event, .cma_free_mb, .state] | @tsv'
```

```bash
grep would_fire logs/hailo_auto_reboot.log
grep drain_entered logs/hailo_auto_reboot.log
```

If `would_fire` occurs frequently, it indicates a high likelihood that Pi reboot will be necessary during actual operation with the current thresholds. Conversely, if only `prewarn_entered` appears without progressing to `drain_entered`, the thresholds or grace times can be re-adjusted before Phase 1.

---

## 4. API Verification Procedure

Check `/api/system/cma` with the admin API key.

```bash
curl -H "X-API-Key: <admin-key>" \
  http://<host>:<port>/ext/hailo-genai/api/system/cma
```

Look at `cma.auto_reboot.enabled`, `cma.auto_reboot.mode`, `cma.auto_reboot.state`, and `cma.auto_reboot.consecutive_rejects` in the response.

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

## 5. Observation Period

The target is 1–2 weeks. Ensure the period covers at least the following patterns:

- Normal LLM chat usage
- Extended chat usage
- Operations that cause Hailo GenAI model load failures or pre-rejects
- First load after Pi reboot

The observation is considered complete when frequency data for `prewarn_entered` / `drain_entered` / `would_fire` over 1–2 weeks can be aggregated. After observation, review the number of `would_fire` occurrences, the reason for `drain_entered` (`cma` / `rejects`), and the rate of `CmaFree` decline to finalize thresholds before deploying Phase 1.

Aggregation example:

```bash
jq -r '.event' logs/hailo_auto_reboot.log | sort | uniq -c
```

---

## 6. Related Documents

- `docs/superpowers/specs/2026-05-17-hailo-auto-reboot-design.md`
- `docs/ja/hailo/HAILO_CMA_LEAK_HAILORT_5_3_0.md`
- `logs/hailo_cma.log` (`core/hailo_device_core/device_helpers.py::log_hailo_cma_event`)
- `logs/hailo_auto_reboot.log` (`core/hailo_device_core/auto_reboot_logger.py`)
