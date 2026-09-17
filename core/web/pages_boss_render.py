"""Boss-mode newspaper page orchestrator.

Builds shared context (auth bar, edition, quote rows) and delegates to one of
the skin modules in core/web/boss_skins/. The resulting body HTML is wrapped
with <html><head><script>...</script></head><body>...</body></html> here.
"""

from __future__ import annotations

import os

from quart import g, request, session

from core.web.boss_skins import pick_skin
from core.web.boss_skins import render as render_skin
from core.web.pages_boss_data import get_quotes_html, pick_boss_edition


def generate_csrf_token() -> str:
    """Generate (or reuse) a CSRF token in the session."""
    try:
        existing = session.get("_csrf_token")
        if existing:
            return existing
        token = os.urandom(16).hex()
        session["_csrf_token"] = token
    except RuntimeError:
        token = os.urandom(16).hex()  # outside request context
    return token


def _build_quotes_data() -> tuple[list[dict[str, str]], str]:
    """Return (quotes_list, source_label). Quotes are skin-rendered later."""
    try:
        from core.services_core.market_quotes import get_market_quotes_payload
        data = get_market_quotes_payload()
        quotes = data.get('quotes', [])
        source = data.get('source', 'fallback')
    except Exception:
        quotes = []
        source = 'fallback'

    if not quotes:
        # Build a tiny placeholder list so each skin renders something.
        quotes = [
            {'label': 'DOW', 'value': '+0.12%'},
            {'label': 'NAS', 'value': '-0.08%'},
            {'label': 'SPX', 'value': '+0.05%'},
            {'label': 'FTSE', 'value': '-0.21%'},
            {'label': 'USDX', 'value': '+0.04%'},
        ]
    src_label = 'LIVE' if source == 'yahoo' else 'FALLBACK'
    return quotes, src_label


def _read_skin_override() -> str | None:
    """Honour ?skin=<id> for QA. Falls back to env var inside pick_skin()."""
    try:
        s = (request.args.get('skin') or '').strip().lower()
        if s:
            return s
    except RuntimeError:
        pass
    return None


def render_boss_page(mode: str = 'pin', error: str = '', next_url: str = '') -> str:
    """Build unified boss-mode HTML across the four skins."""
    from markupsafe import escape

    ed = pick_boss_edition()
    brand = escape(ed['brand'])
    headline = escape(ed['headline'])
    subhead = escape(ed['subhead'])
    byline = escape(ed['byline'])
    desk_label = escape(ed['desk_label'])
    stories_raw = [str(s) for s in ed['stories']]
    stories_html = ''.join(f'<li>{escape(s)}</li>' for s in stories_raw)
    sections_html = ''.join(f'<span>{escape(s)}</span>' for s in ed['sections'])
    breaking_html = (
        f'<div class="breaking">{escape(ed["breaking_text"])}</div>'
        if ed['show_breaking'] else ''
    )

    quotes, src_label = _build_quotes_data()

    # -- Auth bar (consistent across skins; each skin styles `.auth-bar`) --
    if mode == 'pin':
        csrf_token = generate_csrf_token()
        next_val = escape(next_url) if next_url else ''
        auth_bar = (
            f'<form class="auth-bar" method="POST" action="/_pin_check" autocomplete="off">'
            f'<input type="hidden" name="_csrf_token" value="{csrf_token}">'
            f'<input type="hidden" name="next" value="{next_val}">'
            f'<span class="auth-label">Subscriber Login</span>'
            f'<input type="password" id="pinInput" name="pin" maxlength="64" autofocus placeholder="PIN">'
            f'<button type="button" class="eye" data-toggle-vis="pinInput">&#x1f441;</button>'
            f'<button type="submit">Sign in</button>'
            f'</form>'
        )
        error_html = (
            f'<div id="error">{escape(error)}</div>' if error
            else '<div id="error"></div>'
        )
    else:
        auth_bar = (
            '<div class="auth-bar">'
            '<span class="auth-label">Subscriber Login</span>'
            '<input type="password" id="lockPin" maxlength="64" autofocus placeholder="PIN" autocomplete="off">'
            '<button type="button" class="eye" data-toggle-vis="lockPin">&#x1f441;</button>'
            '<button type="button" id="unlockBtn">Sign in</button>'
            '</div>'
        )
        error_html = '<div id="error"></div>'

    skin_id = pick_skin(_read_skin_override())
    body_html = render_skin(skin_id, {
        'mode': mode,
        'brand': brand,
        'headline': headline,
        'subhead': subhead,
        'byline': byline,
        'desk_label': desk_label,
        'stories_raw': [escape(s) for s in stories_raw],
        'stories_html': stories_html,
        'sections_html': sections_html,
        'breaking_html': breaking_html,
        'quotes': quotes,
        'src_label': src_label,
        'auth_bar': auth_bar,
        'error_html': error_html,
    })

    # -- Lock-mode JS --
    lock_js = ''
    if mode == 'lock':
        lock_js = """
    async function unlockApp(){
      var pin=document.getElementById('lockPin').value;
      var res=await fetch('/api/lock/unlock',{
        method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'},
        body:JSON.stringify({pin:pin})
      });
      if(res.ok){window.location.reload()}else{
        var d=await res.json();
        document.getElementById('error').textContent=d.error||'Failed';
        document.getElementById('lockPin').value='';
        document.getElementById('lockPin').focus();
      }
    }
    document.addEventListener('click',function(ev){
      if(ev.target.closest('#unlockBtn'))unlockApp();
    });
    document.addEventListener('keydown',function(ev){
      if(ev.key==='Enter'&&ev.target&&ev.target.id==='lockPin')unlockApp();
    });"""

    nonce = ''
    try:
        nonce = getattr(g, 'csp_nonce', '') or ''
    except RuntimeError:
        nonce = ''

    title_brand = ed['brand']
    return f'''<!DOCTYPE html><html lang="ja"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title_brand)} - Subscriber Access</title>
</head><body data-skin="{skin_id}">
{body_html}
<script nonce="{nonce}">
function toggleVis(id,btn){{
  var inp=document.getElementById(id);if(!inp)return;
  var h=inp.type==='password';inp.type=h?'text':'password';
  if(btn)btn.textContent=h?'\U0001f648':'\U0001f441';
}}
document.addEventListener('click',function(ev){{
  var b=ev.target.closest('[data-toggle-vis]');
  if(b)toggleVis(b.getAttribute('data-toggle-vis'),b);
}});{lock_js}
</script>
</body></html>'''


# Re-export for backward compat (legacy callers may have imported this).
__all__ = ['generate_csrf_token', 'render_boss_page', 'get_quotes_html']
