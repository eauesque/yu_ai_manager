"""Boss-mode skin modules for PIN/Lock pages.

Mirrors src/ts/boss-lock/skins/ — each skin renders a full body HTML
(style + content) for one camouflage personality. The orchestrator
in pages_boss_render.py picks a skin per request and wraps the result
with <html><head>...</head><body>...</body></html>.
"""

from __future__ import annotations

import os
import random
from typing import Any

from . import bloomberg, ft, nikkei, wsj

SKINS = {
    'ft': ft,
    'wsj': wsj,
    'bloomberg': bloomberg,
    'nikkei': nikkei,
}
SKIN_IDS = list(SKINS.keys())


def pick_skin(forced: str | None = None) -> str:
    """Choose a skin id.

    Priority: explicit `forced` arg → `?skin=<id>` query param (caller passes) →
    YU_BOSS_SKIN env var (for tests) → random.
    """
    if forced and forced in SKINS:
        return forced
    env = os.environ.get('YU_BOSS_SKIN', '').strip().lower()
    if env in SKINS:
        return env
    return random.choice(SKIN_IDS)


def _quote_rows(quotes: list[dict[str, Any]]) -> str:
    """Build shared `.q-row[data-delta]` markup. Each skin styles via CSS."""
    out: list[str] = []
    for q in quotes:
        label = str(q.get('label', ''))[:8]
        value = str(q.get('value', ''))
        if value.startswith('-'):
            sign, glyph = 'down', '▼'
        elif value.startswith('+'):
            sign, glyph = 'up', '▲'
        else:
            sign, glyph = 'flat', '·'
        out.append(
            f'<div class="q-row" data-delta="{sign}">'
            f'<span class="q-label">{label}</span>'
            f'<span class="q-val"><span class="q-glyph">{glyph}</span>{value}</span>'
            f'</div>'
        )
    return ''.join(out)


def render(skin_id: str, ctx: dict[str, Any]) -> str:
    """Dispatch to the chosen skin module."""
    if skin_id not in SKINS:
        skin_id = 'ft'
    # Inject shared quote-row HTML so skins don't have to re-format
    if 'quotes_html' not in ctx and 'quotes' in ctx:
        ctx['quotes_html'] = _quote_rows(ctx['quotes'])
    return SKINS[skin_id].render(ctx)
