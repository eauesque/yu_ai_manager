"""Webhook HTTP dispatcher with HMAC signing and retry."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import random
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from core.event_bus import event_bus
from core.event_bus.event_types import Event
from core.extensions_core.sandbox.sandbox_http import SandboxedHTTPClient

from .webhook_config import validate_webhook_url

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
TIMEOUT_SECONDS = 10
USER_AGENT = "YU-AI-Manager-Webhook/1.0"

# HTTP status codes that should NOT be retried (client errors except 429)
_NO_RETRY_4XX = set(range(400, 500)) - {429}


def _sign_payload(secret: str, payload: bytes) -> str:
    """Compute HMAC-SHA256 signature for a payload."""
    return hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()


def _validate_delivery_target(url: str) -> str | None:
    try:
        return validate_webhook_url(url)
    except Exception as exc:
        logger.warning("Webhook target validation failed: %s", exc)
        return "webhook target validation failed"


class WebhookDispatcher:
    """Subscribe to event bus and dispatch matching events as HTTP POSTs."""

    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="webhook")
        self._subscribed = False

    def start(self) -> None:
        """Subscribe to all events on the global bus."""
        if self._subscribed:
            return
        event_bus.subscribe(None, self._on_event)
        self._subscribed = True

    def stop(self) -> None:
        """Unsubscribe from event bus and shut down the thread pool."""
        if self._subscribed:
            event_bus.unsubscribe(None, self._on_event)
            self._subscribed = False
        self._pool.shutdown(wait=True, cancel_futures=False)

    def _on_event(self, event: Event) -> None:
        """Dispatch matching webhooks in the thread pool."""
        from .webhook_config import list_webhooks
        hooks = list(list_webhooks())  # snapshot to avoid iteration race
        for wh in hooks:
            if not wh.get("active", True):
                continue
            subscribed_events = wh.get("events", [])
            if subscribed_events and event.type not in subscribed_events:
                continue
            self._pool.submit(self._deliver, wh, event)

    def _deliver(self, webhook: dict[str, Any], event: Event) -> None:
        """POST event to webhook URL with HMAC signature + retry."""
        from .webhook_config import get_secret
        from .webhook_delivery_log import log_delivery

        payload = json.dumps(event.to_dict(), ensure_ascii=False).encode("utf-8")
        payload_str = payload.decode("utf-8")
        secret = get_secret()
        signature = _sign_payload(secret, payload)

        url = webhook["url"]
        wh_id = webhook["id"]
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": USER_AGENT,
            "X-Webhook-Signature": f"sha256={signature}",
            "X-Webhook-Id": wh_id,
            "X-Webhook-Event": event.type,
        }

        last_error: str | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                url_err = _validate_delivery_target(url)
                if url_err:
                    last_error = url_err
                    log_delivery(
                        wh_id, event.type, payload_str,
                        attempt=attempt, success=False, error=last_error,
                    )
                    break
                resp = SandboxedHTTPClient("webhook", scope="internet").post(
                    url, data=payload, headers=headers, timeout=TIMEOUT_SECONDS,
                )
                if resp.ok:
                    log_delivery(
                        wh_id, event.type, payload_str,
                        status_code=resp.status_code,
                        response_body=resp.text[:1024],
                        attempt=attempt, success=True,
                    )
                    return
                last_error = f"HTTP {resp.status_code}"
                log_delivery(
                    wh_id, event.type, payload_str,
                    status_code=resp.status_code,
                    response_body=resp.text[:1024],
                    attempt=attempt, success=False, error=last_error,
                )
                # Don't retry on permanent client errors (4xx except 429)
                if resp.status_code in _NO_RETRY_4XX:
                    break
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                log_delivery(
                    wh_id, event.type, payload_str,
                    attempt=attempt, success=False, error=last_error,
                )
            logger.warning(
                "Webhook %s attempt %d/%d failed: %s",
                wh_id, attempt, MAX_RETRIES, last_error,
            )
            # Exponential backoff with jitter before next attempt
            if attempt < MAX_RETRIES:
                backoff = (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                time.sleep(backoff)

        # All retries exhausted — log at ERROR level
        if last_error:
            logger.error(
                "Webhook %s permanently failed after %d attempts: %s",
                wh_id, MAX_RETRIES, last_error,
            )

    async def send_test(self, webhook: dict[str, Any]) -> dict[str, Any]:
        """Send a test event without blocking the event loop."""
        test_event = Event(
            type="webhook.test",
            data={"message": "This is a test event", "webhook_id": webhook["id"]},
            source="manual",
        )
        from .webhook_config import get_secret
        payload = json.dumps(test_event.to_dict(), ensure_ascii=False).encode("utf-8")
        secret = get_secret()
        signature = _sign_payload(secret, payload)

        url = webhook["url"]
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": USER_AGENT,
            "X-Webhook-Signature": f"sha256={signature}",
            "X-Webhook-Id": webhook["id"],
            "X-Webhook-Event": "webhook.test",
        }
        try:
            url_err = _validate_delivery_target(url)
            if url_err:
                return {"success": False, "error": "Invalid webhook target"}
            resp = await asyncio.to_thread(
                SandboxedHTTPClient("webhook", scope="internet").post,
                url, data=payload, headers=headers, timeout=TIMEOUT_SECONDS,
            )
            return {
                "success": resp.ok,
                "status_code": resp.status_code,
                "body": resp.text[:1024],
            }
        except Exception as e:
            logger.warning("Webhook test failed: %s: %s", type(e).__name__, e)
            return {"success": False, "error": "Connection failed"}
