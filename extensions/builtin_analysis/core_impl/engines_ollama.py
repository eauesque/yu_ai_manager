"""Ollama Vision API engine for local LLM image analysis."""

import base64
import contextlib
import io
import json
import logging
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .engines_claude_parse import parse_image_analysis, parse_trends_analysis
from .engines_claude_payload import build_image_prompt, build_trends_prompt, get_system_prompt
from .types import AnalysisEngine, AnalysisResult

_TIMEOUT = 300
_MAX_DIM = 1536
_MAX_RETRIES = 2
_RETRY_DELAY = 3  # seconds

log = logging.getLogger(__name__)


_OLLAMA_NATIVE_FORMATS = {".png", ".jpg", ".jpeg"}


def _encode_image_for_ollama(image_path: Path) -> str:
    """Encode image as base64 for Ollama.

    Ollama's model runner reliably supports PNG and JPEG only.
    Large images are downscaled to _MAX_DIM to avoid payload bloat and
    Ollama timeouts — most vision models resize internally to ~768px anyway.
    """
    from PIL import Image

    ext = image_path.suffix.lower()

    with Image.open(image_path) as img:
        w, h = img.size
        needs_resize = max(w, h) > _MAX_DIM
        needs_convert = ext not in _OLLAMA_NATIVE_FORMATS

        if not needs_resize and not needs_convert:
            # Fast path: native format + small enough — send raw bytes
            with open(image_path, "rb") as f:
                return base64.standard_b64encode(f.read()).decode("utf-8")

        if needs_resize:
            img.thumbnail((_MAX_DIM, _MAX_DIM), Image.LANCZOS)

        buf = io.BytesIO()
        if ext in {".jpg", ".jpeg"} and not needs_convert:
            img.save(buf, format="JPEG", quality=85)
        else:
            img.save(buf, format="PNG")

    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


class OllamaVisionEngine(AnalysisEngine):
    """Ollama Vision API (llava, bakllava, moondream etc.)"""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llava:latest", language: str = "ja"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.language = language

    def get_name(self) -> str:
        return f"Ollama Vision ({self.model})"

    def _call_api(
        self, messages: list,
        format_json: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        last_err: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return self._call_api_once(
                    messages, format_json=format_json, json_schema=json_schema,
                )
            except RuntimeError as e:
                msg = str(e)
                # Raise immediately for non-retryable errors
                if any(k in msg for k in ("not running", "not found", "Cannot connect")):
                    raise
                last_err = e
                if attempt < _MAX_RETRIES:
                    log.warning(
                        "Ollama attempt %d/%d failed (%s), retrying in %ds...",
                        attempt + 1, _MAX_RETRIES + 1, msg[:80], _RETRY_DELAY,
                    )
                    time.sleep(_RETRY_DELAY)
        raise last_err  # type: ignore[misc]

    def _call_api_once(
        self, messages: list,
        format_json: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        # Priority: JSON Schema (structured output) > format_json ("json")
        if json_schema:
            payload["format"] = json_schema
        elif format_json:
            payload["format"] = "json"

        fmt_label = "schema" if json_schema else ("json" if format_json else "none")
        data = json.dumps(payload).encode("utf-8")
        log.warning(
            "Ollama request: model=%s, payload_size=%.1fKB, format=%s",
            self.model, len(data) / 1024, fmt_label,
        )
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urllib.request.urlopen(req, timeout=_TIMEOUT)
        except urllib.error.HTTPError as e:
            body = ""
            with contextlib.suppress(Exception):
                body = e.read().decode("utf-8", errors="replace")[:300]
            if e.code == 404:
                raise RuntimeError(
                    f"Model not found: {self.model}. Run: ollama pull {self.model}"
                ) from e
            if "loading model" in body.lower() or e.code == 503:
                raise RuntimeError(
                    f"Ollama is loading model '{self.model}'. "
                    f"Please wait and retry, or run: ollama run {self.model}"
                ) from e
            log.warning("Ollama HTTP %d: %s", e.code, body)
            raise RuntimeError(f"Ollama API error (HTTP {e.code}): {body}") from e
        except urllib.error.URLError as e:
            reason = str(e.reason) if e.reason else ""
            if "refused" in reason.lower() or "connect" in reason.lower():
                raise RuntimeError(
                    f"Ollama is not running at {self.base_url}. "
                    f"Start Ollama first: ollama serve"
                ) from e
            raise RuntimeError(
                f"Cannot connect to Ollama at {self.base_url}: {e.reason}"
            ) from e
        except TimeoutError as e:
            raise RuntimeError(
                f"Ollama response timeout ({_TIMEOUT}s). The model may be too slow or not loaded."
            ) from e

        # Streaming: read chunk by chunk, concatenate content
        chunks: list = []
        try:
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg = obj.get("message", {})
                c = msg.get("content", "")
                if c:
                    chunks.append(c)
                if obj.get("done"):
                    break
        except TimeoutError as e:
            if chunks:
                log.warning("Ollama stream timed out after partial response (%d chunks)", len(chunks))
            else:
                raise RuntimeError(
                    f"Ollama response timeout ({_TIMEOUT}s). The model may be too slow or not loaded."
                ) from e
        finally:
            resp.close()

        full = "".join(chunks)
        if not full:
            raise RuntimeError("Ollama returned empty response")
        return full

    def analyze_image(
        self,
        image_path: Path,
        existing_tags: list[str] | None = None,
        existing_prompt: str | None = None,
        mode: str = "full",
        format_json: bool = False,
        json_schema: dict[str, Any] | None = None,
    ) -> AnalysisResult:
        image_data = _encode_image_for_ollama(image_path)
        prompt = build_image_prompt(existing_tags, existing_prompt, language=self.language, mode=mode)

        # Change system prompt to OCR-specific in OCR mode
        if mode == "ocr":
            system = "You are an OCR assistant. Read text from images accurately and return JSON."
        else:
            system = get_system_prompt(self.language)

        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": prompt,
                "images": [image_data],
            },
        ]
        raw = self._call_api(
            messages, format_json=format_json, json_schema=json_schema,
        )

        # In OCR mode, return raw response as-is (OCR parser handles it)
        if mode == "ocr":
            result = AnalysisResult()
            result.raw_response = raw
            return result

        return parse_image_analysis(raw)

    def analyze_prompt_trends(self, prompts: list[dict]) -> dict[str, Any]:
        sample = prompts[:50]
        prompt_texts = [p.get("positive", "")[:200] for p in sample if p.get("positive", "")]
        if not prompt_texts:
            return {"error": "No prompts to analyze"}

        analysis_prompt = build_trends_prompt(prompt_texts, language=self.language)
        raw = self._call_api([{"role": "user", "content": analysis_prompt}])
        return parse_trends_analysis(raw)
