import http.client
import json
import ssl
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .engines_claude_parse import parse_image_analysis, parse_trends_analysis
from .engines_claude_payload import (
    build_image_messages,
    build_image_prompt,
    build_trends_prompt,
    encode_image,
    get_system_prompt,
)
from .types import AnalysisEngine, AnalysisResult


class ClaudeVisionEngine(AnalysisEngine):
    """Image analysis using Anthropic Claude Vision API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6", language: str = "ja"):
        self.api_key = api_key
        self.model = model
        self.language = language
        self.base_url = "https://api.anthropic.com/v1/messages"
        self._conn: http.client.HTTPSConnection | None = None

    def get_name(self) -> str:
        return f"Claude Vision ({self.model})"

    def _get_conn(self) -> http.client.HTTPSConnection:
        """Reuse HTTPS connection. Recreate on disconnect."""
        if self._conn is not None:
            try:
                self._conn.request("HEAD", "/")
                self._conn.getresponse()
            except Exception:
                self._conn = None
        if self._conn is None:
            parsed = urlparse(self.base_url)
            ctx = ssl.create_default_context()
            self._conn = http.client.HTTPSConnection(
                parsed.hostname, parsed.port or 443,
                timeout=60, context=ctx,
            )
        return self._conn

    def _call_api(self, messages: list, max_tokens: int = 2000, system: str = "") -> str:
        body = {"model": self.model, "max_tokens": max_tokens, "messages": messages}
        if system:
            body["system"] = system
        payload = json.dumps(body).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        parsed = urlparse(self.base_url)
        try:
            conn = self._get_conn()
            conn.request("POST", parsed.path, body=payload, headers=headers)
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")
        except Exception:
            # Reset and retry on connection error
            self._conn = None
            conn = self._get_conn()
            conn.request("POST", parsed.path, body=payload, headers=headers)
            resp = conn.getresponse()
            body = resp.read().decode("utf-8")

        if resp.status != 200:
            if resp.status == 401:
                raise RuntimeError("Anthropic API key is invalid or expired")
            if resp.status == 404:
                raise RuntimeError(
                    f"Model not found: {self.model}. "
                    "Valid IDs: claude-sonnet-4-6, claude-opus-4-6, claude-haiku-4-5"
                )
            if resp.status == 429:
                raise RuntimeError("Anthropic rate limit exceeded. Please wait and retry.")
            raise RuntimeError(f"Anthropic API error (HTTP {resp.status})")

        result = json.loads(body)
        text_parts = [block["text"] for block in result.get("content", []) if block.get("type") == "text"]
        return "\n".join(text_parts)

    def analyze_image(self, image_path: Path, existing_tags: list[str] | None = None,
                      existing_prompt: str | None = None, mode: str = "full",
                      format_json: bool = False,
                      json_schema: dict | None = None) -> AnalysisResult:
        media_type, image_data = encode_image(image_path)
        prompt = build_image_prompt(existing_tags, existing_prompt, language=self.language, mode=mode)
        messages = build_image_messages(media_type, image_data, prompt)

        if mode == "ocr":
            system = "You are an OCR assistant. Read text from images accurately and return JSON."
        else:
            system = get_system_prompt(self.language)

        raw = self._call_api(messages, system=system)

        if mode == "ocr":
            result = AnalysisResult()
            result.raw_response = raw
            return result

        return parse_image_analysis(raw)

    def analyze_prompt_trends(self, prompts: list[dict]) -> dict[str, Any]:
        sample = prompts[:50]
        prompt_texts = []
        for p in sample:
            text = p.get("positive", "")[:200]
            if text:
                prompt_texts.append(text)
        if not prompt_texts:
            return {"error": "分析するプロンプトがありません"}

        analysis_prompt = build_trends_prompt(prompt_texts, language=self.language)
        raw = self._call_api([{"role": "user", "content": analysis_prompt}], max_tokens=3000)
        return parse_trends_analysis(raw)
