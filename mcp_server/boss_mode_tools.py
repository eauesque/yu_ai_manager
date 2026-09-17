"""MCP tools for boss-mode quick lock / PIN auth status.

Thin wrappers over /api/lock/* and /api/auth/* endpoints. These are the
operator-facing controls for the same quick-lock feature exposed in the WebUI
nav ("boss mode" 🕴️). PIN verification reuses the server-side rate limiter and
scrypt hash — no PIN is stored here.

Safety guards:
- boss_mode_lock requires confirm=True. Locking hides the whole UI behind the
  PIN page, so an accidental tool call from an operator chat would be
  disruptive; the explicit confirm stops stray invocations.
- boss_mode_unlock refuses an empty PIN locally so the server's rate-limit
  counter is not burned on obviously-invalid attempts.
"""
from __future__ import annotations

from .llm_tools_common import as_error, as_json


def register_boss_mode_tools(mcp, client):
    @mcp.tool()
    def boss_mode_status() -> str:
        """Return auth + quick-lock state.

        Combines /api/auth/status and /api/lock/status. Fields:
          pin_auth, quick_lock_enabled, quick_lock_locked,
          trusted_proxy_auth, session_authenticated, lock_info.

        lock_info is the raw /api/lock/status payload (includes locked flag,
        lock reason, timestamps where available).
        """
        auth = client.get("/api/auth/status")
        lock = client.get("/api/lock/status")
        out = dict(auth) if isinstance(auth, dict) else {"auth": auth}
        out["lock_info"] = lock
        return as_json(out)

    @mcp.tool()
    def boss_mode_lock(confirm: bool = False) -> str:
        """Activate quick-lock (boss mode). Hides the UI behind the PIN page.

        Args:
            confirm: Must be True. Guards against accidental locks from a
                stray tool call.

        Requires PIN_AUTH enabled server-side; returns an error otherwise.
        """
        if not confirm:
            return as_error(
                "refusing to activate quick-lock without confirm=True; "
                "pass confirm=True to proceed"
            )
        return as_json(client.post("/api/lock/activate", body={}))

    @mcp.tool()
    def boss_mode_unlock(pin: str) -> str:
        """Unlock quick-lock by submitting the PIN.

        Args:
            pin: The PIN configured at server startup (--pin / YU_TAURI_PIN).

        The server enforces rate limiting and minimum length; this tool only
        refuses an empty string to avoid burning the counter needlessly.
        """
        if not pin:
            return as_error("pin is required")
        return as_json(client.post("/api/lock/unlock", body={"pin": pin}))

    @mcp.tool()
    def boss_mode_logout() -> str:
        """Clear the current session (cookie + pin_ok flag).

        Does NOT activate quick-lock — it only drops the authenticated
        session. Use boss_mode_lock to additionally hide the UI.
        """
        return as_json(client.post("/api/auth/logout", body={}))
