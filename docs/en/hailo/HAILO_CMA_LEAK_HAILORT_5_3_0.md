# HailoRT 5.3.0 CMA Leak — Confirmed Diagnosis and Operational Constraints

> **Correction note**: This document is a record of the CMA leak diagnosis based on earlier measurements, and the earlier conclusion that CMA is not reclaimed even after `release()`, that it continues to leak at approximately 14 MB/min during inference, and that only rebooting the Pi itself is a reliable recovery method, has been retracted. The final determination from the retest on HailoRT/driver 5.4.0 has been corrected in [HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md](HAILO_5_4_0_DRIVER_VANILLA_TRIAL.md) §8. Do not reference this document's old conclusions as the current operational determination.

**Created**: 2026-05-17 (discovered and recorded in v4.214.11)
**Affected scope**: Raspberry Pi 5 + Hailo-10H + `hailort==5.3.0` (via `hailo_platform.genai`)
**Symptom**: Once an LLM is loaded, CMA is barely reclaimed even after calling `VDevice.release()` / `LLM.release()`. Additionally, CMA continues to leak continuously during inference. Recovery is impossible without rebooting the Pi itself.
**Status**: Confirmed as a structural constraint on the driver side. Workarounds under investigation.

---

## 1. Basis for Confirmed Diagnosis

Using the CMA event logger introduced in `v4.214.10` (`logs/hailo_cma.log`, `core/hailo_device_core/device_helpers.py::log_hailo_cma_event`), the following sequence was measured on 2026-05-17.

### 1-1. Observed Log (raw)

`logs/hailo_cma.log`:

```text
2026-05-17T14:05:13+0900 event=vdevice_create_pre  cma_free_mb=392 pid=3237
2026-05-17T14:05:14+0900 event=vdevice_create_post cma_free_mb=393 pid=3237
2026-05-17T14:05:14+0900 event=acquire_pre  cma_free_mb=393 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:06:25+0900 event=acquire_post cma_free_mb=108 pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
        ↓ 6 minutes of chat usage (approximately 5–10 messages of inference)
2026-05-17T14:12:36+0900 event=release_pre  cma_free_mb=24  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
2026-05-17T14:12:36+0900 event=release_post cma_free_mb=25  pid=3237 owner=llm hef=Qwen3-1.7B-Instruct.hef
```

### 1-2. Interpretation

| Phase | CmaFree Delta | Meaning |
|---|---|---|
| `vdevice_create_pre` → `vdevice_create_post` | **+1 MB (≈ 0)** | VDevice creation itself consumes almost no CMA |
| `acquire_pre` → `acquire_post` (Qwen3-1.7B-Instruct load) | **−285 MB** | 1 LLM consumes 285 MB |
| `acquire_post` → `release_pre` (6 minutes of inference) | **−84 MB / 6 min ≒ −14 MB/min** | **Continuous leak even during inference** |
| `release_pre` → `release_post` (LLM unload) | **+1 MB** | **`release()` effectively returns no CMA** |

### 1-3. Comparison with Previous Hypothesis

This is a measurement result that partially contradicts the initial hypothesis in `SQLCIPHER_MMAP_CORRUPTION.md` §7 created on 2026-05-16 and the old document's hypothesis that "the VDevice retention strategy (our `_maybe_reset_vdevice` being empty) amplifies the leak." Since VDevice creation = 0 MB and release = 0 MB, **changing the retention strategy (= changing `_maybe_reset_vdevice` to reset every time) would have no effect**.

---

## 2. Structural Constraints

Based on measured results, HailoRT 5.3.0 (community build, `hailo_platform.genai` API) has three concurrent problems:

1. **`VDevice.release()` / GenAI model `release()` does not reclaim host CMA** (confirmed by measurement)
   - Within a single process, the PCIe driver (`hailo1x_pci`) continues to hold DMA regions, and no `munmap`-equivalent operation occurs
2. **Continuous CMA leak during inference (~14 MB/min)** (confirmed by measurement)
   - Today's observation: 84 MB lost in 6 minutes while using Qwen3-1.7B-Instruct
   - A separate path independent of load/unload. Exhaustion occurs even without unloading
3. **No confirmed method other than Pi reboot to reliably reclaim CMA** (measurement + community reports)
   - Even restarting the server process (equivalent to `systemctl restart yu-ai-manager`) is incomplete since `hailo1x_pci` holds DMA until PCIe power-cycle. Full recovery requires `sudo reboot` of the Pi (confirmed by measurement in this repository)
   - Multiple independent reports exist in the Hailo community: <https://community.hailo.ai/t/hailo-10h-on-rpi5-undocumented-api-findings-dfc-conversion-failures-with-transformer-based-models-swinv2-vit-convnext/18979> and <https://community.hailo.ai/t/hailo-10h-throughput-degrades-irreversibly-within-minutes-of-continuous-use-125-41-fps-only-host-reboot-recovers/19218> (explicitly states that `VDevice.release()` / process exit / driver reload does not recover, only host reboot does)
   - This is already documented for users in the pre-rejection error message of `acquire_genai` (`core/hailo_device_core/device_manager_genai.py::acquire_genai`) ("a full system reboot is required")

### 2-1. "Does Killing a Child Process Return CMA?": **Disproven by Measurement** (2026-05-17 Phase 0 PoC)

The previous version (rev1) theoretically concluded that "the Linux kernel reclaims DMA pages during `mm_struct` teardown, so killing a child process completely recovers CMA," but **measuring with Phase 0 PoC (`tools/diag_hailo_cma_reclaim.py`) independently confirmed twice that killing a child process barely recovers CMA**.

**Measurement Results (2nd run, strict version)**:

| Measurement Point | CmaFree | Δ |
|---|---:|---:|
| baseline (before PoC start) | 503 MB | — |
| After VDevice creation | 372 MB | **-131 MB** (VDevice construction consumes CMA in cold-spawn child process) |
| After LLM load | 372 MB | 0 MB (LLM is contained within VDevice DMA pool, no new consumption) |
| After SIGTERM + join | 378 MB | +6 MB |
| **After 30-second wait** | **380 MB** | **Only +8 MB total reclaimed** |

Against an expected reclamation of ≥250 MB, actual measurement was only +8 MB (+1 MB in the first incidental measurement). This is at the system jitter level — **no significant CMA reclamation occurred**.

**Confirmed Diagnosis**:

- The `hailo1x_pci` driver manages the DMA pool in **driver-internal global state** rather than the user process `mm_struct` (estimated)
- Not reclaimed by `process exit`, `kill`, or `module unload` (consistent with community reports)
- **The only confirmed recovery method is `sudo reboot` of the Pi (= PCIe power-cycle)** ← this is the measured fact stated in §2 row 3

Detailed report: `docs/superpowers/specs/codex-reviews/2026-05-17-hailo-subprocess-isolation-phase0-poc-result.md`

As a result of these findings, `docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md` is marked **REJECTED**, and the subprocess isolation mitigation approach is abandoned. The automatic reboot approach in §4 (D) is adopted as an alternative.

---

## 3. Operational Implications

### 3-1. "1 Model per Pi Reboot" is Effectively the Limit

- With Pi 5 (CMA limit 512 MB, cannot be increased per Pi spec) + Qwen3 LLM (285 MB):
    - CmaFree immediately after reboot ≒ 480 MB
    - After loading 1 LLM → CmaFree ≒ 190 MB
    - After tens of minutes of inference → CmaFree ≒ 50 MB or less
    - **Loading a second model is permanently impossible** (requires 250+ MB but insufficient remaining, and release does not return it)

### 3-2. Simultaneous Use of LLM + VLM / LLM + S2T is Not Possible

- Use cases that switch between VLM (llava-based, ~300 MB), S2T (whisper-small, ~175 MB), and LLM are impossible due to the above constraints unless the procedure of **load → reboot → load** is followed.
- **Multi-model UX such as "attach an image during conversation to switch to another model" or "transcribe conversation audio" is structurally impossible with HailoRT 5.3.0**.

### 3-3. Long Continuous Inference Sessions are Difficult

- The 14 MB/min leak means that even starting at 200 MB CmaFree, it halves in 14 minutes and is nearly exhausted in 30 minutes.
- Chat sessions exceeding 30 minutes cannot be stabilized without a Pi reboot in between.

---

## 4. Possible Countermeasures

Listed with priority and effort:

| Option | Effect | Effort | Side Effects / Risks |
|---|---|---|---|
| ~~(A) Isolate Hailo operations in a subprocess and periodically kill to return CMA to kernel~~ | ❌ **REJECTED** (disproven by Phase 0 PoC, reproduced twice). Reclamation after kill was only +8 MB total — hypothesis fails | — | Not adopted |
| **(B) Update `_CMA_ESTIMATES_MB` to measured values + margin** | Improves accuracy of pre-rejection (reduces false-positive load attempts) | ✅ Immediately applicable, 1 line | Cases that were barely working with 250 MB assumption will be rejected, but those were already failing | 
| **(C) UI banner when `CmaFree < 80 MB` / WARN in error.log when `< 30 MB`** | Users can understand the situation and be prompted to reboot Pi | Medium | Risk of warning fatigue / excessive notifications |
| **(D) Detect `CmaFree < 30 MB` and send SIGTERM to supervisor** | Automatic recovery (though Pi full reboot is needed, so via `systemctl reboot`) | Medium | Requires supervisor permissions / sessions cut during other work |
| **(E) Wait for HailoRT fix + document constraints clearly** | Cost 0 | 0 | Depends on Hailo's release cycle (months+) |
| **(F) Submit fix request to Hailo's issue tracker / forum** | Possibly accelerates fix timing | Small | Response speed depends on support contract and community status |

Short-term policy (implemented in v4.214.11): **(B) apply + this document (starting point for E and F)**.
Medium-term policy (separate spec): Consider in order of **(C) UI warning → (A) subprocess isolation**.
Long-term: Monitor HailoRT releases and update this document to remove constraints when fixed.

---

## 5. Related Documents / Code

- `core/hailo_device_core/device_manager_genai.py::acquire_genai` — Pre-CmaFree check + user-facing error message explicitly states this constraint
- `core/hailo_device_core/device_helpers.py::_CMA_ESTIMATES_MB` — Per-model CMA requirement estimates (qwen bumped from 250 → 300 in v4.214.11)
- `core/hailo_device_core/device_helpers.py::log_hailo_cma_event` — Measurement instrumentation introduced in v4.214.10. Measurement data in this document comes from here
- `core/hailo_device_core/device_manager_state.py::_maybe_reset_vdevice` — Design that holds VDevice for process lifetime (empty function). This measurement confirms that changing it to reset would not contribute to CMA reclamation
- `docs/ja/hailo/HAILO_AUTO_REBOOT_PHASE05.md` — Operator guide for Phase 0.5 observation phase. Procedure for collecting only `would_fire` logs with `mode=lazy` + `dry_run=true`
- `docs/ja/hailo/PI5_NUMA_CMA_CONSTRAINTS.md` — CMA limit for Pi5 as a whole and baseline consumption by each driver (camera / KMS / Hailo / HEVC)
- `docs/ja/hailo/HAILORT_5_3_0_MIGRATION.md` — Background of migration to HailoRT 5.3.0 and known differences

---

## 6. Reproduction Steps (for Hailo Issue Reports)

Minimal reproduction steps for external bug reports:

```bash
# 1. Confirm baseline immediately after Pi reboot
grep CmaFree /proc/meminfo
# CmaFree: ~480000 kB

# 2. Start server + load 1st LLM (e.g., send 1 message via GenAI in /tools)
# 1 request to /api/llm/generate or /api/chat/send

# 3. Check CmaFree
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB (-280 MB)

# 4. Unload model
curl -X POST http://127.0.0.1:5000/ext/hailo-genai/api/model/unload -d '{"model":"llm"}'

# 5. Check CmaFree
grep CmaFree /proc/meminfo
# CmaFree: ~100 MB (not returned ← bug)

# 6. Attempt reload of same / different model → rejected due to insufficient CMA
```

Expected behavior: In step 5, CmaFree should return to a value close to the baseline in step 1 (>400 MB).
Actual behavior: Only about +1 MB returned, reload is impossible.
