"""Mixing conversion helpers for SD/NAI prompt conversion."""

import re

from core.helpers_core.emphasis_constants import W_SNUM


def convert_and_to_mixing(text: str) -> str:
    parts = re.split(r"\s+AND\s+", text)
    converted = []
    for part in parts:
        part = part.strip()
        m = re.match(rf"^(.+?)\s*:({W_SNUM})\s*$", part)
        if m:
            converted.append(f"{m.group(1).strip()}:{m.group(2)}")
        else:
            converted.append(part)
    return "|".join(converted)


def convert_mixing_to_and(text: str) -> str:
    randomizers = []

    def _save_rand(m):
        randomizers.append(m.group(0))
        return f"\x00RAND{len(randomizers)-1}\x00"

    protected = re.sub(r"\|\|([^|]+(?:\|[^|]+)*)\|\|", _save_rand, text)

    dp_choices = []

    def _save_dp(m):
        dp_choices.append(m.group(0))
        return f"\x00DP{len(dp_choices)-1}\x00"

    protected = re.sub(r"\{[^{}]*\|[^{}]*\}", _save_dp, protected)

    if "|" in protected:
        parts = protected.split("|")
        converted = []
        for part in parts:
            part = part.strip()
            m = re.match(rf"^(.+?):({W_SNUM})\s*$", part)
            if m:
                converted.append(f"{m.group(1).strip()} :{m.group(2)}")
            else:
                converted.append(part)
        protected = " AND ".join(converted)

    for i, r in enumerate(randomizers):
        protected = protected.replace(f"\x00RAND{i}\x00", r)
    for i, d in enumerate(dp_choices):
        protected = protected.replace(f"\x00DP{i}\x00", d)

    return protected
