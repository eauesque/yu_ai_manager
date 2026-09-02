"""Linux GPU probes for fleet machine info."""

from __future__ import annotations

import json
import subprocess


def gpu_nvidia_smi() -> list[dict] | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    except Exception:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None

    gpus = []
    for line in result.stdout.strip().splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 4:
            continue
        try:
            gpus.append(
                {
                    "name": parts[0],
                    "vram_total_gb": round(float(parts[1]) / 1024.0, 1),
                    "vram_used_gb": round(float(parts[2]) / 1024.0, 1),
                    "utilization_pct": float(parts[3]),
                }
            )
        except ValueError:
            continue
    return gpus if gpus else None


def rocminfo_names() -> list[str]:
    try:
        result = subprocess.run(["rocminfo"], capture_output=True, text=True, timeout=8)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout:
        return []

    names: list[str] = []
    for block in result.stdout.split("*******"):
        if "Device Type:             GPU" not in block and "Device Type: GPU" not in block:
            continue
        for line in block.splitlines():
            if "Marketing Name:" in line:
                name = line.split(":", 1)[1].strip()
                if name:
                    names.append(name)
                break
    return names


def gpu_rocm_smi() -> list[dict] | None:
    try:
        result = subprocess.run(
            ["rocm-smi", "--showproductname", "--showmeminfo", "vram", "--showuse", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    except Exception:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        data = json.loads(result.stdout)
    except Exception:
        return None

    cards = sorted(
        [(key, value) for key, value in data.items() if isinstance(value, dict) and key.lower().startswith("card")],
        key=lambda item: item[0],
    )
    if not cards:
        return None

    names = rocminfo_names()

    def _to_int(val) -> int:
        try:
            return int(str(val).strip())
        except Exception:
            return 0

    gpus = []
    for idx, (_, card) in enumerate(cards):
        name = names[idx] if idx < len(names) else (
            card.get("Card series")
            or card.get("Card model")
            or card.get("Marketing Name")
            or card.get("Card SKU")
            or ""
        )
        vram_total_b = _to_int(card.get("VRAM Total Memory (B)"))
        vram_used_b = _to_int(card.get("VRAM Total Used Memory (B)"))
        util_raw = str(card.get("GPU use (%)", "")).strip()
        try:
            util_pct = float(util_raw) if util_raw else None
        except ValueError:
            util_pct = None
        gpus.append(
            {
                "name": name,
                "vram_total_gb": round(vram_total_b / 1e9, 1) if vram_total_b else None,
                "vram_used_gb": round(vram_used_b / 1e9, 1) if vram_total_b else None,
                "utilization_pct": util_pct,
            }
        )
    return gpus if gpus else None
