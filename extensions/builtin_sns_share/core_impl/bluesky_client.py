"""Bluesky posting + connection testing."""

import logging
from typing import Any

from .bluesky_session import clear_session, get_client, is_available
from .image_prepare import prepare_image_for_bluesky
from .post_builder import _truncate_graphemes, build_post_text

logger = logging.getLogger(__name__)


def test_connection() -> dict[str, Any]:
    """Bluesky connection test.

    Returns:
        {"ok": True/False, "handle": str, "error": str|None}
    """
    if not is_available():
        return {
            "ok": False,
            "handle": "",
            "error": "atproto パッケージがインストールされていません。",
        }

    # Clear session cache and test reconnection
    clear_session()
    client, err = get_client()
    if err:
        return {"ok": False, "handle": "", "error": err}

    try:
        profile = client.get_profile(client.me.did)
        return {
            "ok": True,
            "handle": profile.handle,
            "display_name": profile.display_name or "",
            "error": None,
        }
    except Exception as exc:
        return {"ok": False, "handle": "", "error": str(exc)}


def post_to_bluesky(
    file_id: int,
    text: str | None = None,
    attach_image: bool = True,
) -> dict[str, Any]:
    """Post to Bluesky.

    Args:
        file_id: 投稿する画像の file_id
        text: 投稿テキスト (None ならテンプレートから生成)
        attach_image: 画像を添付するか

    Returns:
        {"ok": True/False, "uri": str, "error": str|None}
    """
    if not is_available():
        return {
            "ok": False,
            "uri": "",
            "error": "atproto パッケージがインストールされていません。",
        }

    client, err = get_client()
    if err:
        return {"ok": False, "uri": "", "error": err}

    # Prepare text
    if text is None:
        result = build_post_text(file_id)
        if result.get("error"):
            return {"ok": False, "uri": "", "error": result["error"]}
        text = result["text"]

    # Bluesky 300 grapheme limit
    text = _truncate_graphemes(text, 300)

    try:
        if attach_image:
            image_data, image_result = _prepare_image(file_id)
            if image_data:
                resp = client.send_image(
                    text=text,
                    image=image_data,
                    image_alt=text[:100],
                )
            else:
                # Image preparation failed -- post text only
                logger.warning("Image prepare failed: %s, posting text only", image_result)
                resp = client.send_post(text=text)
        else:
            resp = client.send_post(text=text)

        uri = getattr(resp, "uri", "")
        return {"ok": True, "uri": uri, "error": None}

    except Exception as exc:
        error_msg = str(exc)
        # Clear session on auth error
        if "auth" in error_msg.lower() or "token" in error_msg.lower():
            clear_session()
        logger.error("Bluesky post failed: %s", exc)
        return {"ok": False, "uri": "", "error": error_msg}


def _prepare_image(file_id: int) -> tuple:
    """Get image path from file_id and resize."""
    from core.services_core.db_state import get_readonly_db

    con = get_readonly_db()
    row = con.execute(
        "SELECT path FROM files WHERE id=? AND is_deleted=0", (file_id,)
    ).fetchone()
    if not row or not row[0]:
        return None, "File not found"

    import os
    path = row[0]
    if not os.path.isfile(path):
        return None, f"File does not exist: {path}"

    return prepare_image_for_bluesky(path)
