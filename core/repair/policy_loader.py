"""Load AI repair policy files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_policy(path: Path | None = None) -> dict[str, Any]:
    policy_path = path or (_PROJECT_ROOT / "AI_REPAIR_POLICY.json")
    with policy_path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("AI repair policy must be a JSON object")
    return data
