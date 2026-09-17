"""Discovery API routes for SD WebUI Bridge.

Exposes LoRA, Embedding, Script, and Extension lists from the
connected SD WebUI instance.
"""

from __future__ import annotations

import asyncio
import logging

from quart import Blueprint, request

from core.infra_core.api_errors import api_error, api_success

logger = logging.getLogger(__name__)


# Discovery routes call into urllib-backed sync HTTP clients. Without a thread
# offload these block the event loop, which queues every other request behind
# the slow first-time LoRA scan and makes the WebUI panel appear stuck.
async def _run_sync(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


async def _client_or_error(make_client):
    try:
        client = await _run_sync(make_client)
        return client, None
    except Exception:
        logger.exception("Failed to create SD WebUI discovery client")
        return None, api_error("SD WebUI connection failed", 502)


def register_sd_discovery_routes(
    bp: Blueprint,
    make_client,
) -> None:
    """Register discovery endpoints on the given blueprint.

    Parameters
    ----------
    bp:
        The SD WebUI Bridge Blueprint.
    make_client:
        Callable that returns a configured bridge client
        (SDWebUIClient or Gradio4ForgeClient).
    """

    @bp.route("/api/loras")
    async def api_loras():
        q = (request.args.get("q") or "").strip().lower()
        client, err = await _client_or_error(make_client)
        if err:
            return err
        loras = await _run_sync(client.list_loras)
        if q:
            loras = [l for l in loras if q in l.get("name", "").lower() or q in l.get("alias", "").lower()]
        return api_success({"loras": loras})

    @bp.route("/api/embeddings")
    async def api_embeddings():
        q = (request.args.get("q") or "").strip().lower()
        client, err = await _client_or_error(make_client)
        if err:
            return err
        result = await _run_sync(client.list_embeddings)
        if q:
            result = {
                "loaded": [n for n in result["loaded"] if q in n.lower()],
                "skipped": [n for n in result["skipped"] if q in n.lower()],
            }
        return api_success(result)

    @bp.route("/api/scripts")
    async def api_scripts():
        client, err = await _client_or_error(make_client)
        if err:
            return err
        scripts = await _run_sync(client.list_scripts)
        return api_success(scripts)

    @bp.route("/api/script-info")
    async def api_script_info():
        client, err = await _client_or_error(make_client)
        if err:
            return err
        info = await _run_sync(client.list_script_info)
        return api_success({"scripts": info})

    @bp.route("/api/extensions")
    async def api_extensions():
        client, err = await _client_or_error(make_client)
        if err:
            return err
        extensions = await _run_sync(client.list_extensions)
        return api_success({"extensions": extensions})
