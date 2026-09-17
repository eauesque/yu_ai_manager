"""Classic (non-boss) PIN and QuickLock page renderers."""

from quart import g, make_response

from core.web.pages_boss_render import generate_csrf_token
from core.web.pages_classic_assets import CLASSIC_CSS, LOCK_SVG


def _nonce() -> str:
    try:
        return getattr(g, "csp_nonce", "") or ""
    except RuntimeError:
        return ""


def _build_classic_auth(mode: str, error: str = "", next_url: str = "") -> str:
    from markupsafe import escape

    nonce = _nonce()
    if mode == "pin":
        title_jp = "PIN を入力"
        sub_jp = "アクセスにはPINが必要です"
        title_en = "Unlock to continue"
        page_title = "YU AI Manager - PIN"
    else:
        title_jp = "ロック中"
        sub_jp = "PIN を入力して解除してください"
        title_en = "Locked"
        page_title = "YU AI Manager - ロック中"

    if mode == "pin":
        csrf_token = generate_csrf_token()
        next_val = escape(next_url) if next_url else ""
        form_open = (
            '<form method="POST" action="/_pin_check" id="authForm" autocomplete="off" novalidate>'
            f'<input type="hidden" name="_csrf_token" value="{csrf_token}">'
            f'<input type="hidden" name="next" value="{next_val}">'
        )
        form_close = "</form>"
        input_attrs = 'name="pin"'
        btn_attrs = 'type="submit"'
    else:
        form_open = '<div id="authForm">'
        form_close = "</div>"
        input_attrs = ""
        btn_attrs = 'type="button" id="unlockBtn"'

    initial_error = (
        f'<div id="error" class="error on">{escape(error)}</div>'
        if error
        else '<div id="error" class="error"></div>'
    )
    pin_input_id = "pinInput" if mode == "pin" else "lockPin"

    return f'''<!DOCTYPE html><html lang="ja"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>{page_title}</title>
<style>{CLASSIC_CSS}</style>
</head><body>
<main class="card" id="card" data-mode="{mode}">
  <div class="brand">
    <div class="brand-mark">{LOCK_SVG}</div>
    <div class="brand-name">YU AI Manager</div>
  </div>
  <h1 class="title">{title_jp}</h1>
  <p class="sub">{sub_jp} <span style="color:var(--c-text-faint)">·</span> <span style="letter-spacing:.06em;color:var(--c-text-faint)">{title_en}</span></p>
  {form_open}
    <div class="pin">
      <input class="pin-input" id="{pin_input_id}" {input_attrs} type="password" maxlength="64" inputmode="numeric" autocomplete="off" autofocus aria-label="PIN">
      <div class="pin-segs" aria-hidden="true">
        <div class="pin-seg"></div><div class="pin-seg"></div><div class="pin-seg"></div>
        <div class="pin-seg"></div><div class="pin-seg"></div><div class="pin-seg"></div>
      </div>
    </div>
    <div class="pin-meta">
      <span class="hint">Enter で解除</span>
      <span class="caps" id="capsHint">Caps Lock</span>
    </div>
    <button class="btn btn-primary" id="submitBtn" {btn_attrs}>
      <span>解除</span>
      <span class="kbd">↵</span>
    </button>
    {initial_error}
  {form_close}
  <div class="foot">Local Vault · {("PIN Gate" if mode == "pin" else "Locked")}</div>
</main>
<script nonce="{nonce}">
(function(){{
  var card  = document.getElementById('card');
  var input = document.getElementById('{pin_input_id}');
  var segs  = card.querySelectorAll('.pin-seg');
  var caps  = document.getElementById('capsHint');
  var error = document.getElementById('error');
  var btn   = document.getElementById('submitBtn');
  var mode  = card.getAttribute('data-mode');

  function paint(){{
    var len = input.value.length;
    var n = segs.length;
    var capped = Math.min(len, n);
    for (var i = 0; i < n; i++) {{
      segs[i].classList.toggle('filled', i < capped);
      segs[i].classList.toggle('active',
        document.activeElement === input && i === Math.min(len, n - 1));
    }}
  }}
  function clearError(){{
    if (error) {{ error.textContent = ''; error.classList.remove('on'); }}
  }}
  function shake(msg){{
    if (msg && error) {{ error.textContent = msg; error.classList.add('on'); }}
    card.classList.remove('shake');
    void card.offsetWidth;
    card.classList.add('shake');
  }}
  input.addEventListener('input', function(){{ paint(); clearError(); }});
  input.addEventListener('focus', paint);
  input.addEventListener('blur',  paint);
  input.addEventListener('keydown', function(ev){{
    caps.classList.toggle('on', ev.getModifierState && ev.getModifierState('CapsLock'));
  }});
  input.addEventListener('keyup', function(ev){{
    caps.classList.toggle('on', ev.getModifierState && ev.getModifierState('CapsLock'));
  }});
  paint();
  if (error && error.classList.contains('on') && error.textContent) {{
    setTimeout(function(){{ shake(); }}, 80);
  }}

  if (mode === 'lock') {{
    async function unlockApp(){{
      var pin = input.value;
      btn.setAttribute('disabled','');
      try {{
        var res = await fetch('/api/lock/unlock', {{
          method:'POST',
          headers:{{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'}},
          body: JSON.stringify({{pin: pin}})
        }});
        if (res.ok) {{
          card.style.transition = 'opacity 240ms ease, transform 240ms ease';
          card.style.opacity = '0';
          card.style.transform = 'translateY(-4px) scale(.99)';
          setTimeout(function(){{ window.location.reload(); }}, 220);
          return;
        }}
        var data = {{}};
        try {{ data = await res.json(); }} catch(e){{}}
        shake(data.error || '失敗');
        input.value = ''; paint(); input.focus();
      }} catch (e) {{
        shake('通信エラー');
      }} finally {{
        btn.removeAttribute('disabled');
      }}
    }}
    btn.addEventListener('click', unlockApp);
    document.addEventListener('keydown', function(ev){{
      if (ev.key === 'Enter' && document.activeElement === input) {{
        ev.preventDefault(); unlockApp();
      }}
    }});
  }} else {{
    document.getElementById('authForm').addEventListener('submit', function(){{
      btn.setAttribute('disabled','');
    }});
  }}
}})();
</script>
</body></html>'''


async def render_pin_page_classic(error: str = "", next_url: str = ""):
    return await make_response(_build_classic_auth("pin", error, next_url), 200)


async def render_lock_page_classic():
    return await make_response(_build_classic_auth("lock"), 200)
