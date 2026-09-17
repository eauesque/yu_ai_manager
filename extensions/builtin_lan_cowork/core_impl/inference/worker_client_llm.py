"""Remote LLM worker calls."""

from __future__ import annotations

import json
import logging

from ..models import PeerInfo
from ..transport import PeerTransport

logger = logging.getLogger(__name__)


def _get_mgr():
    try:
        from ...lan_cowork_ext import _get_manager

        return _get_manager()
    except Exception:
        return None


async def llm_chat_remote(
    peer: PeerInfo,
    messages: list,
    model: str | None = None,
    max_tokens: int = 256,
    temperature: float = 0.7,
    timeout: float = 60.0,
) -> dict | None:
    try:
        import aiohttp
    except ImportError:
        logger.warning("llm_chat_remote requires aiohttp")
        return None

    url = f"http://{peer.api_host}:{peer.api_port}/ext/lan_cowork/api/peer/infer/llm-chat"
    payload = {
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if model:
        payload["model"] = model

    mgr = _get_mgr()
    if mgr is None:
        logger.warning("llm_chat_remote %s failed: manager unavailable", peer.name)
        return None
    body = json.dumps(payload, separators=(",", ":")).encode()
    full_path = f"{PeerTransport._PREFIX}/api/peer/infer/llm-chat"
    from core.crypto_identity import path_requires_nonce

    from ..peer_auth_client import build_peer_headers

    headers = build_peer_headers(
        mgr.local_seed(),
        mgr.local_peer.peer_id,
        getattr(peer, "token", None) or "",
        "POST",
        full_path,
        "",
        body,
        require_nonce=path_requires_nonce(full_path),
    )
    headers["Accept"] = "application/json"
    headers["User-Agent"] = "yu-ai-manager"

    try:
        async with aiohttp.ClientSession() as session, session.post(
            url,
            data=body,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status != 200:
                logger.warning("llm_chat_remote %s -> %d", peer.name, resp.status)
                return None
            data = await resp.json()
            if not data.get("ok"):
                logger.warning("llm_chat_remote %s error: %s", peer.name, data.get("error"))
                return None
            return data
    except Exception as exc:
        logger.warning("llm_chat_remote %s failed: %s", peer.name, exc)
        return None
