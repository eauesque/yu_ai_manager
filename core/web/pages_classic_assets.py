"""Shared assets for classic auth pages."""

CLASSIC_CSS = """
:root{
  --c-ink:#0a0b10;
  --c-ink-2:#0e1016;
  --c-card:#13151c;
  --c-card-hi:#181b24;
  --c-rule:#22252e;
  --c-rule-soft:#1c1f27;
  --c-text:#e6e8ec;
  --c-text-soft:#9aa0ad;
  --c-text-faint:#5b6170;
  --c-accent:#5eead4;
  --c-accent-deep:#2dd4bf;
  --c-danger:#f87171;
}
*{box-sizing:border-box}
html,body{height:100%}
body{
  margin:0;background:var(--c-ink);color:var(--c-text);
  font-family:'SF Pro Text',-apple-system,BlinkMacSystemFont,'Segoe UI Variable Text','Segoe UI','Hiragino Sans','Yu Gothic UI','Noto Sans CJK JP',sans-serif;
  font-feature-settings:"kern" 1,"ss01" 1,"cv11" 1;
  display:flex;justify-content:center;align-items:center;
  min-height:100vh;overflow:hidden;
  background-image:
    radial-gradient(ellipse 60% 50% at 50% 0%,rgba(94,234,212,0.05),transparent 60%),
    radial-gradient(ellipse 80% 60% at 50% 110%,rgba(45,212,191,0.04),transparent 70%);
}
body::before{
  content:'';position:fixed;inset:0;pointer-events:none;
  background-image:repeating-linear-gradient(0deg,rgba(255,255,255,0.008) 0 1px,transparent 1px 3px);
  mix-blend-mode:overlay;
}
.card{
  position:relative;
  width:min(380px,calc(100% - 32px));
  background:linear-gradient(180deg,var(--c-card-hi) 0%,var(--c-card) 100%);
  border:1px solid var(--c-rule);
  border-radius:14px;
  padding:36px 32px 28px;
  box-shadow:
    0 1px 0 rgba(255,255,255,0.05) inset,
    0 0 0 1px rgba(0,0,0,0.4),
    0 24px 60px -20px rgba(0,0,0,0.6),
    0 8px 24px -8px rgba(0,0,0,0.4);
  animation:c-rise 480ms cubic-bezier(.22,.61,.36,1) both;
}
.card.shake{animation:c-shake 380ms cubic-bezier(.36,.07,.19,.97) both}
@keyframes c-rise{
  from{opacity:0;transform:translateY(10px) scale(.985);filter:blur(4px)}
  to{opacity:1;transform:none;filter:none}
}
@keyframes c-shake{
  10%,90%{transform:translateX(-1px)}
  20%,80%{transform:translateX(2px)}
  30%,50%,70%{transform:translateX(-4px)}
  40%,60%{transform:translateX(4px)}
}
.card::before{
  content:'';position:absolute;inset:0;border-radius:inherit;pointer-events:none;
  background:radial-gradient(80% 50% at 50% -8%,rgba(94,234,212,0.10),transparent 60%);
}
.brand{
  display:flex;flex-direction:column;align-items:center;gap:10px;
  margin-bottom:22px;
}
.brand-mark{
  width:42px;height:42px;display:grid;place-items:center;
  background:linear-gradient(180deg,#1a1d27,#11131a);
  border:1px solid var(--c-rule);border-radius:11px;
  box-shadow:0 1px 0 rgba(255,255,255,0.06) inset,0 6px 16px -6px rgba(0,0,0,0.6);
}
.brand-mark svg{width:20px;height:20px;color:var(--c-accent)}
.brand-name{
  font-size:10px;letter-spacing:0.32em;text-transform:uppercase;
  color:var(--c-text-faint);font-weight:600;
}
.title{
  margin:0;text-align:center;
  font-size:18px;font-weight:600;letter-spacing:-0.005em;color:var(--c-text);
}
.sub{
  margin:6px 0 22px;text-align:center;
  font-size:12.5px;color:var(--c-text-soft);letter-spacing:0.01em;
}
.pin{
  position:relative;height:54px;margin:6px 0 4px;
  display:flex;justify-content:center;
}
.pin-input{
  position:absolute;inset:0;width:100%;height:100%;
  background:transparent;border:0;padding:0;margin:0;
  font-size:1px;color:transparent;caret-color:transparent;
  letter-spacing:0;outline:none;
  text-align:center;z-index:2;
}
.pin-segs{
  display:grid;grid-template-columns:repeat(6,1fr);gap:8px;width:100%;
  pointer-events:none;
}
.pin-seg{
  position:relative;height:54px;border-radius:9px;
  background:linear-gradient(180deg,#0e1016,#0b0d12);
  border:1px solid var(--c-rule);
  box-shadow:0 1px 0 rgba(255,255,255,0.025) inset;
  transition:border-color 160ms ease,box-shadow 220ms ease,background 220ms ease;
  display:grid;place-items:center;
}
.pin-seg::after{
  content:'';width:9px;height:9px;border-radius:999px;
  background:var(--c-text-soft);
  transform:scale(0);opacity:0;
  transition:transform 180ms cubic-bezier(.22,.61,.36,1),opacity 160ms ease;
}
.pin-seg.filled::after{transform:scale(1);opacity:1}
.pin-seg.active{
  border-color:var(--c-accent);
  box-shadow:0 0 0 3px rgba(94,234,212,0.12),0 1px 0 rgba(255,255,255,0.04) inset;
  background:linear-gradient(180deg,#101319,#0b0d12);
}
.pin-input:focus + .pin-segs .pin-seg.active{
  border-color:var(--c-accent);
}
.pin-meta{
  display:flex;justify-content:space-between;align-items:center;
  font-size:10.5px;letter-spacing:0.16em;text-transform:uppercase;
  color:var(--c-text-faint);min-height:16px;margin:8px 2px 14px;
}
.pin-meta .caps{color:#fbbf24;opacity:0;transition:opacity 160ms ease}
.pin-meta .caps.on{opacity:1}
.btn{
  display:flex;align-items:center;justify-content:center;gap:8px;
  width:100%;padding:11px 14px;
  background:linear-gradient(180deg,#1a1d27,#13161e);
  color:var(--c-text);
  border:1px solid var(--c-rule);border-radius:10px;
  font:inherit;font-size:13.5px;font-weight:600;letter-spacing:0.04em;
  cursor:pointer;
  box-shadow:0 1px 0 rgba(255,255,255,0.05) inset,0 8px 18px -10px rgba(0,0,0,0.5);
  transition:border-color 160ms ease,background 160ms ease,transform 80ms ease;
}
.btn:hover{border-color:#2f3340;background:linear-gradient(180deg,#1d2029,#161922)}
.btn:active{transform:translateY(0.5px)}
.btn-primary{
  background:linear-gradient(180deg,var(--c-accent) 0%,var(--c-accent-deep) 100%);
  color:#062a25;border-color:transparent;
  box-shadow:0 1px 0 rgba(255,255,255,0.4) inset,0 8px 22px -10px rgba(94,234,212,0.5);
}
.btn-primary:hover{
  background:linear-gradient(180deg,#7ef3dd 0%,#3eddc7 100%);
  border-color:transparent;
}
.btn .kbd{
  margin-left:6px;font-size:10.5px;letter-spacing:0.05em;
  padding:1px 6px;border-radius:5px;
  background:rgba(0,0,0,0.18);
  border:1px solid rgba(0,0,0,0.25);
  color:rgba(6,42,37,0.7);font-weight:700;
}
.btn-primary[disabled]{opacity:.45;cursor:not-allowed}
.error{
  margin:14px 0 0;text-align:center;min-height:18px;
  font-size:12px;color:var(--c-danger);letter-spacing:0.02em;
  opacity:0;transform:translateY(-2px);transition:opacity 160ms ease,transform 160ms ease;
}
.error.on{opacity:1;transform:none}
.foot{
  margin-top:22px;padding-top:16px;border-top:1px solid var(--c-rule-soft);
  text-align:center;font-size:10.5px;letter-spacing:0.16em;text-transform:uppercase;
  color:var(--c-text-faint);
}
@media(max-width:420px){
  .card{padding:28px 22px 22px}
  .pin-segs{gap:6px}
  .pin-seg{height:48px}
}
"""

LOCK_SVG = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" '
    'aria-hidden="true">'
    '<rect x="4" y="10.5" width="16" height="11" rx="2.4"/>'
    '<path d="M7.5 10.5V7a4.5 4.5 0 0 1 9 0v3.5"/>'
    '<circle cx="12" cy="15.6" r="1.4" fill="currentColor" stroke="none"/>'
    '<path d="M12 17v2"/>'
    '</svg>'
)
