"""Server auth/lock page renderers.

Re-export facade: actual implementations live in pages_boss_data,
pages_boss_render, and pages_classic modules.
"""

import logging

from quart import make_response

from core.web.pages_boss_data import _fetch_real_headlines  # noqa: F401 - re-export
from core.web.pages_boss_render import render_boss_page
from core.web.pages_classic import render_lock_page_classic, render_pin_page_classic

log = logging.getLogger(__name__)


# -- Public API ----------------------------------------------------------------

async def render_pin_page(error: str = "", boss_mode: bool = False, next_url: str = ""):
    """Return PIN input page."""
    if boss_mode:
        return await make_response(render_boss_page('pin', error, next_url), 200)
    return await render_pin_page_classic(error, next_url=next_url)


async def render_lock_page(boss_mode: bool = False):
    """Return QuickLock page."""
    if boss_mode:
        return await make_response(render_boss_page('lock'), 200)
    return await render_lock_page_classic()
