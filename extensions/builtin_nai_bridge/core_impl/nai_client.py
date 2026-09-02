"""NovelAI Image Generation API client built on :class:`BridgeHTTPClient`."""

from __future__ import annotations

import base64
import io
import logging
import zipfile
from typing import Any

from core.bridge_core import BridgeConnectionError, BridgeHTTPClient, BridgeHTTPError

from .nai_params import build_request_body

logger = logging.getLogger(__name__)

# Seconds to wait for /ai/generate-image. NAI charges Anlas when the request
# reaches its backend, so giving up early loses the image *and* the Anlas —
# a generous ceiling is cheaper than a premature cut. V5 spends noticeably
# longer in the tokenizer than V4.5, so 120s was no longer enough.
GENERATE_TIMEOUT_SEC = 300

# /ai/encode-vibe (Vibe Transfer / Precise Reference). V4-era only — V5 does
# not support it at launch — so this keeps the old ceiling.
ENCODE_VIBE_TIMEOUT_SEC = 60


class NAIClient:
    """High-level wrapper around the NovelAI Image Generation API.

    Parameters
    ----------
    api_token:
        NAI API bearer token (``pst-...``).
    timeout:
        Default timeout in seconds.  ``generate`` uses a longer timeout.
    """

    _IMAGE_BASE = "https://image.novelai.net"

    def __init__(self, api_token: str, timeout: float = 30.0) -> None:
        self.api_token = api_token
        auth = {"Authorization": f"Bearer {api_token}"}
        self._image_http = BridgeHTTPClient(
            self._IMAGE_BASE, timeout=timeout, default_headers=auth,
        )

    # -- connection / subscription ----------------------------------

    def test_connection(self) -> dict[str, Any]:
        """Test token validity by fetching subscription info.

        Persistent API tokens (``pst-...``) are scoped to
        ``image.novelai.net`` -- ``api.novelai.net`` rejects them with a
        400 even when the token itself is valid, so this must hit the
        image host like every other call in this client.

        Returns ``{"ok": True, "anlas": ..., "tier": ...}`` on success
        or ``{"ok": False, "error": ..., "status": ...}`` on failure.
        """
        try:
            sub = self._image_http.get("/user/subscription", timeout=15)
            anlas = self._extract_anlas(sub)
            tier = sub.get("tier", 0)
            usage = self._extract_usage(sub)
            return {"ok": True, "anlas": anlas, "tier": tier, "usage": usage}
        except BridgeConnectionError as exc:
            return {"ok": False, "error": str(exc), "status": 502}
        except BridgeHTTPError as exc:
            if exc.status == 401:
                return {"ok": False, "error": "Invalid API token (401)",
                         "status": 401}
            body_snip = (exc.body or "").strip()[:400]
            error = f"HTTP {exc.status}" + (f" -- {body_snip}" if body_snip else "")
            return {"ok": False, "error": error, "status": exc.status}

    def get_anlas(self) -> dict[str, Any]:
        """Fetch current Anlas balance.

        Returns ``{"ok": True, "anlas": ...}`` or error dict.
        """
        try:
            sub = self._image_http.get("/user/subscription", timeout=15)
            anlas = self._extract_anlas(sub)
            usage = self._extract_usage(sub)
            return {"ok": True, "anlas": anlas, "usage": usage}
        except BridgeConnectionError as exc:
            return {"ok": False, "error": str(exc), "status": 502}
        except BridgeHTTPError as exc:
            body_snip = (exc.body or "").strip()[:400]
            error = f"HTTP {exc.status}" + (f" -- {body_snip}" if body_snip else "")
            return {"ok": False, "error": error, "status": exc.status}

    # -- vibe encoding (V4+) ----------------------------------------

    def encode_vibe(
        self,
        image_b64: str,
        information_extracted: float,
        model: str,
    ) -> str:
        """Encode a raw image into a V4 vibe bundle.

        NAI V4 ``/ai/generate-image`` rejects raw base64 images in
        ``reference_image_multiple``; each image must first be passed
        through ``/ai/encode-vibe``, whose binary response is the vibe
        bundle that the generator accepts. Costs 2 Anlas per call.

        Parameters
        ----------
        image_b64:
            Base64-encoded raw reference image (PNG/JPEG/WebP).
        information_extracted:
            Locked-at-encode-time strength of the extracted semantic
            data (0–1). Must be re-encoded to change.
        model:
            Target generation model name (e.g. ``nai-diffusion-4-5-full``).

        Returns
        -------
        str
            Base64 of the binary vibe bundle, ready to use as an entry
            in ``reference_image_multiple``.
        """
        # Cache lookup: skip the 2 Anlas HTTP call when we've already
        # encoded this exact (image, model, info_extracted) triple.
        from . import nai_vibe_cache
        try:
            from core.extensions_core.extensions_admin import (
                get_extension_config_value,
            )
            max_mb = float(get_extension_config_value(
                "builtin-nai-bridge", "cache_max_size_mb", 500.0))
        except Exception:
            max_mb = 500.0

        try:
            raw_bytes = base64.b64decode(image_b64)
        except Exception as exc:
            raise BridgeHTTPError(400, f"invalid base64 image: {exc}") from exc
        cache_enabled = max_mb > 0

        if cache_enabled:
            with nai_vibe_cache.key_lock(
                raw_bytes, model, information_extracted,
            ):
                cached = nai_vibe_cache.get_cached(
                    raw_bytes, model, information_extracted,
                )
                if cached is not None:
                    return base64.b64encode(cached).decode("ascii")
                blob = self._call_encode_vibe(
                    image_b64, information_extracted, model)
                try:
                    nai_vibe_cache.put(
                        raw_bytes, model, information_extracted, blob)
                except OSError as exc:
                    logger.warning("nai_vibe_cache.put failed: %s", exc)
            nai_vibe_cache.prune_async(max_mb)
            return base64.b64encode(blob).decode("ascii")

        blob = self._call_encode_vibe(image_b64, information_extracted, model)
        return base64.b64encode(blob).decode("ascii")

    def _call_encode_vibe(
        self, image_b64: str, information_extracted: float, model: str,
    ) -> bytes:
        """Raw HTTP call to /ai/encode-vibe. Returns binary vibe blob."""
        body = {
            "image": image_b64,
            "information_extracted": float(information_extracted),
            "model": model,
        }
        return self._image_http.post_json_bytes(
            "/ai/encode-vibe",
            body,
            timeout=max(self._image_http.timeout, ENCODE_VIBE_TIMEOUT_SEC),
        )

    # -- generation -------------------------------------------------

    def generate(
        self,
        prompt: str,
        negative_prompt: str = "",
        **params: Any,
    ) -> dict[str, Any]:
        """Generate images via NAI API.

        Returns ``{"ok": True, "images": [bytes, ...], "seed": int}``
        or ``{"ok": False, "error": ...}``.

        Keyword arguments are forwarded to :func:`build_request_body`.
        """
        # V4 models require reference images to be pre-encoded via
        # /ai/encode-vibe. Each encode locks the information_extracted
        # value, so we encode per (image, info) pair.
        model = params.get("model", "")
        refs = params.get("reference_image_multiple") or []
        if refs and "diffusion-4" in model:
            infos = params.get("reference_information_extracted_multiple") \
                or [1.0] * len(refs)
            encoded: list[str] = []
            for img_b64, info in zip(refs, infos, strict=False):
                try:
                    encoded.append(self.encode_vibe(img_b64, info, model))
                except BridgeConnectionError as exc:
                    return {"ok": False, "error": f"encode-vibe: {exc}"}
                except BridgeHTTPError as exc:
                    logger.warning(
                        "NAI encode-vibe HTTP %s body=%r",
                        exc.status, exc.body[:400],
                    )
                    if exc.status == 401:
                        return {"ok": False,
                                "error": "Invalid API token (401)"}
                    if exc.status == 402:
                        return {"ok": False,
                                "error": "Insufficient Anlas (402)"}
                    body_snip = (exc.body or "").strip()[:400]
                    return {
                        "ok": False,
                        "error": (
                            f"NAI encode-vibe failed: HTTP {exc.status} "
                            f"— {body_snip}"
                        ),
                    }
            params["reference_image_multiple"] = encoded

        body = build_request_body(prompt, negative_prompt, **params)
        seed = body["parameters"]["seed"]
        requested_fmt = body["parameters"].get("image_format", "png")

        # Sanitized outgoing-body dump for vibe / precise-reference debug.
        # Truncates base64 image fields so the log stays small.
        if logger.isEnabledFor(logging.DEBUG):
            import copy as _copy
            dbg = _copy.deepcopy(body)
            p = dbg.get("parameters", {})
            for k in ("image", "mask"):
                v = p.get(k)
                if isinstance(v, str) and len(v) > 60:
                    p[k] = v[:60] + f"...(trunc, len={len(v)})"
            v = p.get("reference_image_multiple")
            if isinstance(v, list):
                p["reference_image_multiple"] = [
                    (s[:60] + f"...(trunc, len={len(s)})")
                    if isinstance(s, str) and len(s) > 60 else s
                    for s in v
                ]
            logger.debug("NAI outgoing body (sanitized): %r", dbg)

        try:
            zip_bytes = self._image_http.post_json_bytes(
                "/ai/generate-image",
                body,
                timeout=max(self._image_http.timeout, GENERATE_TIMEOUT_SEC),
            )
        except BridgeConnectionError as exc:
            return {"ok": False, "error": str(exc)}
        except BridgeHTTPError as exc:
            # Log full body so we can diagnose schema mismatches (e.g. V4
            # vibe-transfer rejecting V3-style reference_* params).
            logger.warning(
                "NAI generate HTTP %s body=%r", exc.status, exc.body[:1000],
            )
            if exc.status == 401:
                return {"ok": False, "error": "Invalid API token (401)"}
            if exc.status == 402:
                return {"ok": False, "error": "Insufficient Anlas (402)"}
            body_snip = (exc.body or "").strip()[:400]
            return {
                "ok": False,
                "error": f"NAI API error: HTTP {exc.status} — {body_snip}",
            }

        try:
            images = self._extract_images_from_zip(
                zip_bytes, preferred_format=requested_fmt)
        except Exception as exc:
            logger.warning("Failed to extract images from ZIP: %s", exc)
            return {"ok": False, "error": f"Failed to extract images: {exc}"}

        if not images:
            return {"ok": False, "error": "No images in response"}

        return {"ok": True, "images": images, "seed": seed}

    # -- helpers ----------------------------------------------------

    @staticmethod
    def _extract_images_from_zip(
        zip_bytes: bytes,
        preferred_format: str = "png",
    ) -> list[bytes]:
        """Extract image data from a ZIP archive.

        When the ZIP contains both PNG and WebP files (NAI API may
        return both), only the files matching *preferred_format* are
        returned.  Falls back to all image files when none match.
        """
        all_images: list[tuple[str, bytes]] = []
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                low = name.lower()
                if low.endswith((".png", ".webp", ".jpg", ".jpeg")):
                    all_images.append((low, zf.read(name)))

        if not all_images:
            return []

        # Filter by the requested format
        ext = f".{preferred_format}"
        preferred = [data for fname, data in all_images
                     if fname.endswith(ext)]
        if preferred:
            return preferred

        # Fallback: return all images if none match the preferred format
        return [data for _, data in all_images]

    @staticmethod
    def _extract_anlas(sub: dict[str, Any]) -> int:
        """Extract Anlas count from subscription response."""
        # trainingStepsLeft.fixedTrainingStepsLeft is used for Anlas
        training = sub.get("trainingStepsLeft", {})
        if isinstance(training, dict):
            return training.get("fixedTrainingStepsLeft", 0)
        return 0

    @staticmethod
    def _extract_usage(sub: dict[str, Any]) -> dict[str, Any] | None:
        """Extract the V5 Opus Usage Limit block from subscription response.

        Shape: ``{"percent": int, "isNegative": bool, "timeUntilNextPercent": int}``.
        Returns None if absent (non-Opus tiers, or NAI has not rolled it out),
        or if present but missing/malformed "percent" -- a block that cannot
        be evaluated for exhaustion must not be treated as "not exhausted".
        """
        usage = sub.get("usage")
        if not isinstance(usage, dict) or isinstance(usage.get("percent"), bool):
            return None
        if not isinstance(usage.get("percent"), (int, float)):
            return None
        return usage

    @staticmethod
    def usage_exhausted(usage: dict[str, Any] | None) -> bool:
        """Whether the V5 Opus Usage Limit is exhausted (would fall back to Anlas)."""
        if not usage:
            return False
        return usage.get("percent", 100) <= 0 or bool(usage.get("isNegative"))
