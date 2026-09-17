"""OpenAI Vision API engine for GPT-4o / GPT-4 Turbo image analysis."""

import http.client
import json
import ssl
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .engines_claude_parse import parse_image_analysis, parse_trends_analysis
from .engines_claude_payload import build_image_prompt, build_trends_prompt, encode_image, get_system_prompt
from .types import AnalysisEngine, AnalysisResult

_TIMEOUT = 90
_OPENAI_NATIVE_FORMATS = {".png", ".jpg", ".jpeg"}


def _encode_image_for_openai(image_path: Path) -> tuple[str, str]:
    """Encode image for OpenAI-compatible vision APIs."""
    if image_path.suffix.lower() in _OPENAI_NATIVE_FORMATS:
        return encode_image(image_path)

    import base64
    import io

    from PIL import Image

    with Image.open(image_path) as img:
        buf = io.BytesIO()
        img.save(buf, format="PNG")
    return "image/png", base64.standard_b64encode(buf.getvalue()).decode("utf-8")


class OpenAIVisionEngine(AnalysisEngine):
    """OpenAI Chat Completions API with vision (gpt-4o, gpt-4o-mini etc.)"""

    _DEFAULT_BASE = "https://api.openai.com"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", base_url: str = "", language: str = "ja"):
        self.api_key = api_key
        self.model = model
        self.language = language
        self._custom_base = base_url.rstrip("/") if base_url else ""
        self.base_url = (
            f"{self._custom_base}/v1/chat/completions"
            if self._custom_base
            else f"{self._DEFAULT_BASE}/v1/chat/completions"
        )
        self._conn: http.client.HTTPConnection | http.client.HTTPSConnection | None = None

    def get_name(self) -> str:
        if self._custom_base and self._custom_base != self._DEFAULT_BASE:
            return f"OpenAI Compatible ({self.model})"
        return f"OpenAI Vision ({self.model})"

    def _get_conn(self) -> http.client.HTTPConnection | http.client.HTTPSConnection:
        """Reuse connection. Recreate on disconnect."""
        if self._conn is not None:
            try:
                self._conn.request("HEAD", "/")
                self._conn.getresponse()
            except Exception:
                self._conn = None
        if self._conn is None:
            parsed = urlparse(self.base_url)
            if parsed.scheme == "http":
                self._conn = http.client.HTTPConnection(
                    parsed.hostname,
                    parsed.port or 80,
                    timeout=_TIMEOUT,
                )
            else:
                ctx = ssl.create_default_context()
                self._conn = http.client.HTTPSConnection(
                    parsed.hostname,
                    parsed.port or 443,
                    timeout=_TIMEOUT,
                    context=ctx,
                )
        return self._conn

    def _call_api(self, messages: list, max_tokens: int = 2000, *, use_schema: bool = True) -> str:
        token_key = "max_completion_tokens" if self.model.startswith(("gpt-5", "o1", "o3", "o4")) else "max_tokens"
        payload_dict: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            token_key: max_tokens,
        }
        if use_schema:
            payload_dict["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "image_analysis",
                    "schema": {"type": "object", "additionalProperties": True},
                },
            }
        payload = json.dumps(payload_dict).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        parsed = urlparse(self.base_url)
        try:
            conn = self._get_conn()
            conn.request("POST", parsed.path, body=payload, headers=headers)
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
        except Exception:
            self._conn = None
            conn = self._get_conn()
            conn.request("POST", parsed.path, body=payload, headers=headers)
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")

        if resp.status != 200:
            if resp.status == 401:
                raise RuntimeError("OpenAI API key is invalid or expired")
            if resp.status == 429:
                raise RuntimeError("OpenAI rate limit exceeded. Please wait and retry.")
            if resp.status == 404:
                raise RuntimeError(f"Model not found: {self.model}")
            # Local OpenAI-compatible backends (Ollama/llama.cpp) can crash their
            # grammar-constrained decoder on certain tokenizers (e.g. Gemma's
            # <unusedNN> reserved tokens) when response_format=json_schema is set.
            # Retry once in free-form mode; parse_image_analysis tolerates non-JSON.
            if use_schema and "grammar" in body.lower():
                return self._call_api(messages, max_tokens, use_schema=False)
            detail = ""
            try:
                err = json.loads(body).get("error", {})
                detail = err.get("message", "") if isinstance(err, dict) else str(err)
            except Exception:
                detail = body[:500]
            suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"OpenAI API error (HTTP {resp.status}){suffix}")

        result = json.loads(body)
        choices = result.get("choices", [])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "")

    def analyze_image(
        self,
        image_path: Path,
        existing_tags: list[str] | None = None,
        existing_prompt: str | None = None,
        mode: str = "full",
        format_json: bool = False,
        json_schema: dict | None = None,
    ) -> AnalysisResult:
        media_type, image_data = _encode_image_for_openai(image_path)
        prompt = build_image_prompt(existing_tags, existing_prompt, language=self.language, mode=mode)
        data_url = f"data:{media_type};base64,{image_data}"

        if mode == "ocr":
            system = "You are an OCR assistant. Read text from images accurately and return JSON."
        else:
            system = get_system_prompt(self.language)

        messages = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}},
                    {"type": "text", "text": prompt},
                ],
            },
        ]
        raw = self._call_api(messages)

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
        raw = self._call_api(
            [{"role": "user", "content": analysis_prompt}],
            max_tokens=3000,
        )
        return parse_trends_analysis(raw)
