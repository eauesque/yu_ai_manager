"""Update runtime auth and response helpers."""

from __future__ import annotations

from core.infra_core.api_errors import api_error, api_success
from core.web.auth_core import is_local_request


def check_update_auth(app, pin_ok: bool):
    """Check authorization for update operations."""
    if not app.config.get("RESTART_ENV_ENABLED"):
        return api_error(
            "更新APIは無効です",
            403,
            code="update_disabled",
            hint="TAGDB_ALLOW_RESTART=1 / --allow-restart / config.server.allow_restart=true のいずれかで有効化してください",
        )

    has_pin = app.config.get("PIN_AUTH")
    if has_pin:
        if not pin_ok:
            return api_error(
                "更新にはPIN認証済みセッションが必要です",
                401,
                code="pin_auth_required",
            )
    else:
        if not is_local_request():
            return api_error(
                "PIN認証が無効のためリモートからの更新は許可されていません",
                403,
                code="pin_required",
            )
    return None


def get_version_string() -> str:
    """Read VERSION from project root if present."""
    import os

    from core.update_core.detect import PROJECT_ROOT

    version = "0.0.0"
    try:
        vpath = os.path.join(PROJECT_ROOT, "VERSION")
        with open(vpath, encoding="utf-8") as f:
            version = f.read().strip()
    except OSError:
        pass
    return version


def accepted_update_response(*, message: str, code: str, **extra):
    """Return the accepted response payload for async update requests."""
    payload = {
        "accepted": True,
        "message": message,
        "code": code,
    }
    payload.update(extra)
    return api_success(payload)
