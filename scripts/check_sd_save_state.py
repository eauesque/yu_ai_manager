"""Diagnose why SD WebUI Bridge double-save still occurs.

Usage::

    uv run python scripts/check_sd_save_state.py [api_url]

If ``api_url`` is omitted, the SD bridge config is read from the running
yu_ai_manager database. Run while the SD WebUI / Forge process is up.

What it prints:

1. detected api_type (sdapi_v1 vs gradio4)
2. whether ``/sdapi/v1/options`` is reachable
3. current upstream values of ``samples_save`` / ``grid_save``
4. the bridge's ``bridge_managed_save`` config flag
5. a verdict on whether double-save should be possible
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Allow running via `uv run python scripts/check_sd_save_state.py` regardless
# of cwd (uv does not add the project root to sys.path automatically).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.bridge_core import (
    BridgeConnectionError,
    BridgeHTTPClient,
    BridgeHTTPError,
)


def _get_options(http: BridgeHTTPClient) -> dict[str, Any] | str:
    try:
        data = http.get("/sdapi/v1/options", timeout=10)
    except BridgeHTTPError as exc:
        return f"HTTP {exc.status}"
    except BridgeConnectionError as exc:
        return f"connection error: {exc}"
    return data if isinstance(data, dict) else "non-dict response"


def main(argv: list[str]) -> int:
    if len(argv) >= 2:
        api_url = argv[1]
        bridge_managed = None
    else:
        try:
            from core.extensions_core.extensions_admin import (
                get_extension_config_value,
            )
        except Exception as exc:
            print(f"error: cannot read bridge config: {exc}", file=sys.stderr)
            print("hint: pass api_url explicitly: "
                  "uv run python scripts/check_sd_save_state.py http://...",
                  file=sys.stderr)
            return 2
        ext = "builtin-sd-webui-bridge"
        api_url = get_extension_config_value(
            ext, "api_url", "http://127.0.0.1:7860")
        bridge_managed = bool(get_extension_config_value(
            ext, "bridge_managed_save", False))

    print(f"api_url: {api_url}")
    if bridge_managed is not None:
        print(f"bridge_managed_save (bridge config): {bridge_managed}")

    http = BridgeHTTPClient(api_url, timeout=10.0)

    print()
    print("=== /sdapi/v1/options (GET) ===")
    opts = _get_options(http)
    if isinstance(opts, str):
        print(f"  unreachable: {opts}")
        print("  api_type -> gradio4 (or sdapi disabled)")
        print()
        print("verdict: cannot flip global save options via API.")
        print("  this is the most common cause of bridge_managed_save")
        print("  double-save persisting on Forge variants. Pick one:")
        print()
        print("  (a) RECOMMENDED -- restart Forge with --api enabled:")
        print("      add `--api` to webui-user.bat / launch.py COMMANDLINE_ARGS")
        print("      then restart Forge. The bridge will flip save options on")
        print("      next generate (no yu_ai_manager restart needed).")
        print()
        print("  (b) Edit Forge's config.json once and restart Forge:")
        print("        \"samples_save\": false,")
        print("        \"grid_save\": false")
        print("      config.json is in the Forge install root.")
        print()
        print("  (c) Live with it: SD outputs/ are duplicates of bridge")
        print("      save_folder (without sweep XMP). Periodically clean")
        print("      outputs/ -- bridge save_folder is the canonical copy.")
        return 1

    print(f"  samples_save : {opts.get('samples_save', '<missing>')}")
    print(f"  grid_save    : {opts.get('grid_save', '<missing>')}")
    save_keys = sorted(
        k for k in opts if "save" in k.lower() and isinstance(opts[k], bool))
    print(f"  all save-related bool keys: {len(save_keys)}")
    for k in save_keys:
        print(f"    {k} = {opts[k]}")

    print()
    print("=== verdict ===")
    samples_save = bool(opts.get("samples_save", True))
    grid_save = bool(opts.get("grid_save", True))
    if not samples_save and not grid_save:
        print("  upstream samples_save and grid_save are BOTH off.")
        print("  -> double-save from the basic save path should NOT happen.")
        print("  if double-save still occurs:")
        print("    - check enabled extensions (ADetailer / ControlNet etc.)")
        print("      that may save extra copies regardless of samples_save")
        print("    - confirm save_folder differs from SD outputs/")
        print("    - confirm the extra files are images (not metadata sidecars)")
    else:
        print("  upstream still has save enabled:")
        if samples_save:
            print("    samples_save=True -> SD will save samples to outdir")
        if grid_save:
            print("    grid_save=True -> SD will save grids to outdir")
        print("  -> bridge will flip these globally on the NEXT generate")
        print("     (after pulling v4.188.6+, suppression runs once per")
        print("     api_url, before the first txt2img / img2img call).")
        print("     Generate one image, then re-run this script to confirm.")

    print()
    print("raw options dump (truncated to 50 keys):")
    short = dict(list(opts.items())[:50])
    print(json.dumps(short, indent=2, default=str)[:4000])

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
