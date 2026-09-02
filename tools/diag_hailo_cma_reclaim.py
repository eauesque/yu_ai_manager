"""Phase 0 PoC — does killing a subprocess that loaded Hailo reclaim CMA?

This is the existential gate for the Hailo subprocess isolation spec
(`docs/superpowers/specs/2026-05-17-hailo-subprocess-isolation-design.md`).
If kill does **not** reclaim CMA, the entire spec is invalidated and the
project pivots to "auto-reboot" alternatives instead.

## What this PoC does

1. Parent: record baseline `CmaFree` from `/proc/meminfo`
2. Parent: spawn child via ``multiprocessing.get_context("spawn").Process``
3. Child:
   - Import `hailo_platform`
   - Construct a `VDevice` (CMA: ~0 MB observed)
   - Load an LLM HEF via the GenAI API (CMA: ~285 MB observed)
   - Signal "loaded" to parent via Queue, then sleep until told to exit
4. Parent: record `CmaFree` after "loaded" signal (should show ~280 MB drop)
5. Parent: send "exit" signal, child exits gracefully
6. Parent: ``terminate()`` the child anyway as belt-and-suspenders, then ``wait()``
7. Parent: record `CmaFree` after wait returns (the key measurement)
8. Parent: optionally also `kill()` (SIGKILL) after a graceful test to see if
   the recovery differs by signal

## How to run

Pi must have:
  - No minimum `CmaFree` is required. Low values are valid test inputs.
  - **No other Hailo process running** (stop the yu_ai_manager server first)
  - The Qwen3-1.7B-Instruct HEF downloaded (passed as ``--hef`` or auto-detected)

```bash
# 1. Stop the running server (so we don't compete for the VDevice)
#    Check: pgrep -fa "python.*web_ui.py"
#    Stop: kill <pid>  (or supervisor restart)
# 2. After stop, wait ~10s for the kernel to settle
# 3. Record CmaFree as telemetry (do not reboot solely because it is low):
grep CmaFree /proc/meminfo
# 4. Run:
uv run python tools/diag_hailo_cma_reclaim.py
#    optional: pass --hef and --signal kill|terminate
```

## Interpreting the output

The PoC prints a result table with deltas. A single large first-run `CmaFree`
drop is **INCONCLUSIVE** because loading a multi-GB HEF warms the page cache and
can repurpose movable CMA pages without making memory unavailable. Re-run from
the resulting low-CMA state and pass the first JSON with ``--previous-output``.
Only a material drop repeated in both runs is classified as **FAIL**; a repeat
whose net drop is within the noise tolerance is **PASS**.

The script writes a JSON summary to ``logs/hailo_cma_reclaim_poc.json`` and a
human-readable table to stdout.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

DEFAULT_HEF_GLOBS = [
    # Honour $HAILO_HEF_DIR override first (same convention as
    # core_impl/model_download._DEFAULT_HEF_DIR).
    os.environ.get("HAILO_HEF_DIR", "") + "/Qwen3-1.7B-Instruct.hef",
    "/home/pi/hailo_models/Qwen3-1.7B-Instruct.hef",
    str(Path.home() / "hailo_models" / "Qwen3-1.7B-Instruct.hef"),
    "cache/hailo_models/llm/Qwen3-1.7B-Instruct.hef",
]

NET_LOSS_TOLERANCE_MB = 16
CUMULATIVE_LOSS_FAILURE_MB = 50


def _classify_cma_result(
    net_loss_mb: int,
    previous_net_loss_mb: int | None = None,
) -> tuple[str, str]:
    """Classify net `CmaFree` change without treating first-run cache warmup as a leak."""
    if net_loss_mb <= NET_LOSS_TOLERANCE_MB:
        return (
            "PASS",
            f"net CmaFree drop {net_loss_mb} MB is within the "
            f"{NET_LOSS_TOLERANCE_MB} MB tolerance",
        )
    if previous_net_loss_mb is None:
        return (
            "INCONCLUSIVE",
            f"first observed net CmaFree drop is {net_loss_mb} MB; repeat from "
            "the current low-CMA state and pass --previous-output",
        )
    if (
        previous_net_loss_mb >= CUMULATIVE_LOSS_FAILURE_MB
        and net_loss_mb >= CUMULATIVE_LOSS_FAILURE_MB
    ):
        return (
            "FAIL",
            f"material net CmaFree drop repeated ({previous_net_loss_mb} MB, "
            f"then {net_loss_mb} MB)",
        )
    return (
        "INCONCLUSIVE",
        f"net CmaFree drop {net_loss_mb} MB exceeds tolerance but did not "
        "repeat at the cumulative-failure threshold",
    )


def _read_cma_free_mb() -> int | None:
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                m = re.match(r"CmaFree:\s+(\d+)", line)
                if m:
                    return int(m.group(1)) // 1024
    except (OSError, ValueError):
        return None
    return None


def _autodetect_hef() -> str | None:
    for path in DEFAULT_HEF_GLOBS:
        if Path(path).is_file():
            return path
    matches = list(Path("cache").rglob("*.hef")) if Path("cache").exists() else []
    for path in matches:
        if "qwen" in path.name.lower():
            return str(path)
    return matches[0].as_posix() if matches else None


def _child_main(hef: str, in_q, out_q, stderr_log_path: str) -> None:
    """Child process: import + construct VDevice + load LLM. Block until exit signal.

    Sends measurement points back to parent via ``out_q``:
      - ('starting', pid)
      - ('imported', wall_ms)
      - ('vdevice_created', wall_ms)
      - ('llm_loaded', wall_ms)
      - ('about_to_exit', None)

    Receives one signal from ``in_q``: 'exit' (after which child returns cleanly).

    stderr is redirected to ``stderr_log_path`` so HailoRT C-extension output
    (which can be voluminous and obscure the parent's interactive log) is
    captured for post-mortem when needed.
    """
    import contextlib as _contextlib
    import sys as _sys
    import time as _time
    # Redirect stderr to a per-run file. We keep stdout pointing at the parent
    # so any explicit prints still show up; HailoRT noise comes through stderr.
    with _contextlib.suppress(OSError):
        _sys.stderr = open(stderr_log_path, "w", buffering=1, encoding="utf-8")  # noqa: SIM115 — lifetime = child process

    t0 = _time.monotonic()

    def elapsed_ms() -> int:
        return int((_time.monotonic() - t0) * 1000)

    try:
        out_q.put(("starting", os.getpid()))
        import hailo_platform  # noqa: F401 — heavy import is the point
        from hailo_platform.genai import LLM
        out_q.put(("imported", elapsed_ms()))

        params = hailo_platform.VDevice.create_params()
        vd = hailo_platform.VDevice(params)
        out_q.put(("vdevice_created", elapsed_ms()))

        llm = LLM(vd, hef)
        out_q.put(("llm_loaded", elapsed_ms()))

        # Block until parent says to exit. We do NOT call release() because we
        # specifically want to test whether kill / process exit reclaims CMA.
        msg = in_q.get()
        if msg != "exit":
            out_q.put(("unexpected_msg", msg))
        out_q.put(("about_to_exit", elapsed_ms()))
        # Drop refs so Python GC has a chance — though we expect it to make no
        # difference (the leak is in the kernel DMA, not Python heap).
        del llm
        del vd
    except Exception as exc:  # pragma: no cover — child diagnostic only
        out_q.put(("error", f"{type(exc).__name__}: {exc}"))


def _wait_for_event(
    out_q,
    name: str,
    timeout: float,
    proc=None,
) -> tuple[str, Any]:
    """Wait for a named event from the child, also detecting child death.

    Polls ``out_q.get(timeout=1)`` and ``proc.is_alive()`` once per second.
    If the child process dies before emitting ``name``, raises RuntimeError
    with the exitcode (rather than waiting the full timeout).
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            ev = out_q.get(timeout=1.0)
        except Exception:
            # Queue empty; check if child is still alive.
            if proc is not None and not proc.is_alive():
                raise RuntimeError(
                    f"child died before emitting {name!r} (exitcode={proc.exitcode})"
                ) from None
            continue
        if ev[0] == name:
            return ev
        if ev[0] == "error":
            raise RuntimeError(f"child error: {ev[1]}")
        # Forward intermediate events to stdout for visibility.
        print(f"  child event: {ev[0]} ({ev[1]})", flush=True)
    raise TimeoutError(
        f"timed out after {timeout:.0f}s waiting for child event {name!r}"
    )


def _measure(label: str) -> tuple[str, int | None]:
    mb = _read_cma_free_mb()
    print(f"  [{label:24s}] cma_free_mb={mb}", flush=True)
    return (label, mb)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0 PoC: subprocess kill → CMA reclaim?")
    parser.add_argument("--hef", help="Path to LLM HEF file (default: autodetect)")
    parser.add_argument(
        "--signal", choices=["graceful", "terminate", "kill"], default="terminate",
        help="How to end the child: graceful (send exit msg, wait), terminate (SIGTERM via Process.terminate), or kill (SIGKILL via Process.kill)",
    )
    parser.add_argument(
        "--post-wait-seconds", type=float, default=30.0,
        help="Seconds to wait after the child exits before final CMA measurement. The kernel may need >5s to release DMA pages on Pi5; 30s is conservative",
    )
    parser.add_argument(
        "--vdevice-timeout-seconds", type=float, default=180.0,
        help="Timeout for VDevice() construction. Cold-start in a spawn-mode subprocess can take 30-60s on Pi5 (firmware load, PCIe init, CMA pool setup). v4.214.10 in-process measurement showed ~1s but cold-spawn is slower.",
    )
    parser.add_argument(
        "--llm-timeout-seconds", type=float, default=240.0,
        help="Timeout for LLM(vd, hef) construction. v4.214.10 measured 71s on Qwen3-1.7B-Instruct in-process; allow 4x margin for cold-spawn.",
    )
    parser.add_argument(
        "--output", default="logs/hailo_cma_reclaim_poc.json",
        help="Path to JSON output file",
    )
    parser.add_argument(
        "--stderr-log", default="logs/hailo_cma_reclaim_poc_child_stderr.log",
        help="Path where the child's stderr is captured (HailoRT C-extension output)",
    )
    parser.add_argument(
        "--previous-output",
        help="JSON from the immediately preceding run, used to detect repeated net loss",
    )
    args = parser.parse_args()

    previous_net_loss: int | None = None
    if args.previous_output:
        try:
            previous_summary = json.loads(Path(args.previous_output).read_text(encoding="utf-8"))
            previous_net_loss = int(previous_summary["net_loss_mb"])
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"ERROR: invalid --previous-output: {exc}", file=sys.stderr)
            return 2

    hef = args.hef or _autodetect_hef()
    if not hef or not Path(hef).is_file():
        print(f"ERROR: HEF file not found. Tried autodetect, none of {DEFAULT_HEF_GLOBS} exists.", file=sys.stderr)
        print("Specify with --hef /path/to/your.hef", file=sys.stderr)
        return 2

    # Ensure log dirs exist before the child starts.
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.stderr_log).parent.mkdir(parents=True, exist_ok=True)

    print(f"PoC starting. HEF={hef!r} signal={args.signal} post_wait={args.post_wait_seconds}s")
    print(f"  vdevice_timeout={args.vdevice_timeout_seconds}s llm_timeout={args.llm_timeout_seconds}s")
    print(f"  child stderr → {args.stderr_log}")
    print()

    timeline: list[tuple[str, int | None]] = []
    timeline.append(_measure("baseline_before_spawn"))

    ctx = multiprocessing.get_context("spawn")
    in_q = ctx.Queue()
    out_q = ctx.Queue()
    proc = ctx.Process(
        target=_child_main,
        args=(hef, in_q, out_q, args.stderr_log),
        name="hailo-cma-poc",
    )

    proc.start()
    timeline.append(_measure("after_spawn_call"))

    started_ev = _wait_for_event(out_q, "starting", timeout=30.0, proc=proc)
    timeline.append(("child_pid", started_ev[1]))
    timeline.append(_measure("after_child_starting"))

    _wait_for_event(out_q, "imported", timeout=60.0, proc=proc)
    timeline.append(_measure("after_child_imported"))

    _wait_for_event(out_q, "vdevice_created", timeout=args.vdevice_timeout_seconds, proc=proc)
    timeline.append(_measure("after_vdevice_created"))

    _wait_for_event(out_q, "llm_loaded", timeout=args.llm_timeout_seconds, proc=proc)
    timeline.append(_measure("after_llm_loaded"))

    print(f"\nSending end signal ({args.signal}) to child...\n")
    if args.signal == "graceful":
        in_q.put("exit")
        try:
            _wait_for_event(out_q, "about_to_exit", timeout=10.0, proc=proc)
            timeline.append(_measure("after_child_about_to_exit_signal"))
        except Exception as e:
            print(f"  (graceful exit signal not echoed: {e})", flush=True)
        proc.join(timeout=30.0)
    elif args.signal == "terminate":
        proc.terminate()
        proc.join(timeout=30.0)
    elif args.signal == "kill":
        proc.kill()
        proc.join(timeout=30.0)

    timeline.append(("child_exitcode", proc.exitcode))
    timeline.append(_measure("after_proc_join"))

    # Belt-and-suspenders: if anything is still alive after join, force-kill.
    if proc.is_alive():
        print("  WARN: child still alive after join, sending SIGKILL", flush=True)
        proc.kill()
        proc.join(timeout=10.0)
        timeline.append(("kill_fallback_exitcode", proc.exitcode))
        timeline.append(_measure("after_kill_fallback"))

    print(f"\nSleeping {args.post_wait_seconds}s for kernel to settle...")
    # Sample CmaFree every 5s during the post-wait so we can detect gradual reclaim.
    settled_samples: list[tuple[float, int | None]] = []
    sample_interval = 5.0
    t_start_wait = time.monotonic()
    while time.monotonic() - t_start_wait < args.post_wait_seconds:
        time.sleep(min(sample_interval, max(0.0, args.post_wait_seconds - (time.monotonic() - t_start_wait))))
        mb = _read_cma_free_mb()
        elapsed = time.monotonic() - t_start_wait
        settled_samples.append((elapsed, mb))
        print(f"  [post_wait t+{elapsed:5.1f}s         ] cma_free_mb={mb}", flush=True)
    timeline.append(_measure("after_post_wait"))

    # Compute headline deltas
    baseline = next((v for k, v in timeline if k == "baseline_before_spawn"), None)
    loaded = next((v for k, v in timeline if k == "after_llm_loaded"), None)
    post_wait = next((v for k, v in timeline if k == "after_post_wait"), None)

    if baseline is None or loaded is None or post_wait is None:
        print("ERROR: missing measurements", file=sys.stderr)
        return 3

    consumed = baseline - loaded
    recovered = post_wait - loaded
    net_loss = baseline - post_wait

    print()
    print("================================================================")
    print(f"  baseline_before_spawn    : {baseline:>5} MB")
    print(f"  after_llm_loaded         : {loaded:>5} MB   (consumed: {consumed:>+4} MB)")
    print(f"  after_post_wait          : {post_wait:>5} MB   (recovered: {recovered:>+4} MB)")
    print(f"  net CmaFree drop         : {net_loss:>+4} MB")
    print("================================================================")

    verdict, verdict_msg = _classify_cma_result(net_loss, previous_net_loss)

    print()
    print(f"VERDICT: {verdict} — {verdict_msg}")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "verdict": verdict,
        "verdict_msg": verdict_msg,
        "hef": hef,
        "signal": args.signal,
        "post_wait_seconds": args.post_wait_seconds,
        "vdevice_timeout_seconds": args.vdevice_timeout_seconds,
        "llm_timeout_seconds": args.llm_timeout_seconds,
        "baseline_before_spawn_mb": baseline,
        "after_llm_loaded_mb": loaded,
        "after_post_wait_mb": post_wait,
        "settled_samples": [{"t_seconds": round(t, 1), "cma_free_mb": mb} for t, mb in settled_samples],
        "consumed_mb": consumed,
        "recovered_mb": recovered,
        "net_loss_mb": net_loss,
        "previous_output": args.previous_output,
        "previous_net_loss_mb": previous_net_loss,
        "timeline": [(k, v) for k, v in timeline],
    }
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nJSON summary written to {out_path}")
    return {"PASS": 0, "INCONCLUSIVE": 1, "FAIL": 4}[verdict]


if __name__ == "__main__":
    sys.exit(main())
