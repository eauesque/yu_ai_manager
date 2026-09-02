"""VLM (Vision Language Model) engine for WD-Tagger.

Uses OpenAI-compatible API (Ollama / hailo-ollama) to generate
Danbooru-style tags from images via a vision-capable LLM.

Supports two API styles:
  1. OpenAI compatible: /v1/chat/completions (image_url in content)
  2. Ollama native: /api/chat (images field) -- automatic fallback
"""

from __future__ import annotations

import base64
import json
import logging
import re
import urllib.error
import urllib.request
from pathlib import Path

from .types import TagPrediction, WdTaggerEngine, WdTagResult

logger = logging.getLogger(__name__)

_USER_AGENT = "YU-AI-Manager/2.0 (WD-Tagger VLM)"

# --- Prompts (from DANBOORU_TAG_GEN_SPEC.md) ---

SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
Analyze the image and output ONLY Danbooru-style tags as a JSON array.
Rules:
- Use underscores instead of spaces (e.g., long_hair, blue_eyes)
- Output ONLY the JSON array, no other text
- Include tags for: character count, gender, hair, eyes, clothing, pose, background, art style
- Do NOT include copyright or character name tags unless clearly identifiable
- Maximum 40 tags
Example output: ["1girl", "solo", "long_hair", "blue_eyes", "smile"]"""

USER_PROMPT = "Tag this image with Danbooru tags."

COMPLEMENT_SYSTEM_PROMPT = """You are a Danbooru image tagging assistant.
The image already has these tags from automated classification: {existing_tags}
Analyze the image and suggest ADDITIONAL Danbooru-style tags not in the list above.
Output ONLY a JSON array of new tags. Use underscores instead of spaces.
Focus on: composition, mood, background details, specific clothing items, art style.
Maximum 20 additional tags.
Example: ["looking_at_viewer", "outdoors", "cloudy_sky", "pleated_skirt"]"""

# MIME mapping
_MIME_MAP = {
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _parse_tag_list(content: str) -> list[str]:
    """Parse VLM response into a list of tag strings.

    Three-stage fallback:
    1. Direct JSON parse (array)
    2. Parse as object, extract "tags" key
    3. Regex extraction of [...] array
    """
    # Stage 1: direct array
    try:
        parsed = json.loads(content)
        if isinstance(parsed, list):
            return [str(t) for t in parsed]
        # Stage 2: {"tags": [...]}
        if isinstance(parsed, dict) and "tags" in parsed:
            tags = parsed["tags"]
            if isinstance(tags, list):
                return [str(t) for t in tags]
    except (json.JSONDecodeError, ValueError):
        pass

    # Stage 3: regex fallback -- extract JSON array from mixed text
    m = re.search(r'\[.*?\]', content, re.DOTALL)
    if m:
        try:
            parsed = json.loads(m.group())
            if isinstance(parsed, list):
                return [str(t) for t in parsed]
        except (json.JSONDecodeError, ValueError):
            pass

    # Stage 4: plain text fallback -- comma-separated, newline-separated,
    # or markdown list ("- tag") when VLM ignores JSON format instructions
    stripped = content.strip().strip("`").strip()
    # Remove markdown code fence if present
    stripped = re.sub(r'^```\w*\s*', '', stripped)
    stripped = re.sub(r'\s*```$', '', stripped)
    # Try comma-separated
    if "," in stripped:
        tags = [t.strip().strip('"\'').strip() for t in stripped.split(",")]
        tags = [t for t in tags if t and len(t) < 80 and not t.startswith("#")]
        if tags:
            return tags
    # Try newline / markdown list
    lines = stripped.splitlines()
    if len(lines) >= 3:
        tags = []
        for line in lines:
            line = line.strip().lstrip("-*•").strip().strip('"\'').strip()
            if line and len(line) < 80 and not line.startswith("#"):
                tags.append(line)
        if tags:
            return tags

    logger.warning("VLM: could not parse tag list from response: %s",
                   content[:200])
    return []


class VlmWdTaggerEngine(WdTaggerEngine):
    """OpenAI-compatible VLM engine for Danbooru tag generation.

    Tries OpenAI /v1/chat/completions first. If it returns 500
    (Ollama vision compat issue), falls back to Ollama native /api/chat.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "",
        timeout: int = 60,
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._use_ollama_native: bool | None = None  # auto-detect

    # --- OpenAI compatible API ---

    def _build_openai_payload(
        self,
        image_b64: str,
        mime: str,
        system_prompt: str,
        user_prompt: str,
    ) -> bytes:
        return json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {
                            "url": f"data:{mime};base64,{image_b64}",
                        }},
                        {"type": "text", "text": user_prompt},
                    ],
                },
            ],
            "max_tokens": 512,
            "temperature": 0.3,
        }).encode()

    def _call_openai(self, payload: bytes) -> str:
        req = urllib.request.Request(
            f"{self._base_url}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
        )
        resp = urllib.request.urlopen(req, timeout=self._timeout)
        data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"]

    # --- Ollama native API ---

    def _build_ollama_payload(
        self,
        image_b64: str,
        system_prompt: str,
        user_prompt: str,
    ) -> bytes:
        return json.dumps({
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt, "images": [image_b64]},
            ],
            "stream": False,
            "options": {"num_predict": 512, "temperature": 0.3},
        }).encode()

    def _call_ollama(self, payload: bytes) -> str:
        req = urllib.request.Request(
            f"{self._base_url}/api/chat",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": _USER_AGENT,
            },
        )
        resp = urllib.request.urlopen(req, timeout=self._timeout)
        data = json.loads(resp.read())
        return data.get("message", {}).get("content", "")

    # --- Unified call with auto-fallback ---

    def _call_api(self, image_b64: str, mime: str, system_prompt: str, user_prompt: str) -> str:
        """Call VLM API with automatic OpenAI -> Ollama fallback."""
        if self._use_ollama_native:
            payload = self._build_ollama_payload(image_b64, system_prompt, user_prompt)
            return self._call_ollama(payload)

        if self._use_ollama_native is None:
            # Auto-detect: try OpenAI first, fallback to Ollama on 500/timeout
            try:
                payload = self._build_openai_payload(image_b64, mime, system_prompt, user_prompt)
                result = self._call_openai(payload)
                self._use_ollama_native = False
                return result
            except urllib.error.HTTPError as e:
                if e.code == 500:
                    logger.info("OpenAI vision API returned 500, falling back to Ollama native API")
                    self._use_ollama_native = True
                    payload = self._build_ollama_payload(image_b64, system_prompt, user_prompt)
                    return self._call_ollama(payload)
                raise
            except (TimeoutError, OSError):
                logger.info("OpenAI vision API timed out, falling back to Ollama native API")
                self._use_ollama_native = True
                payload = self._build_ollama_payload(image_b64, system_prompt, user_prompt)
                return self._call_ollama(payload)

        # Explicitly OpenAI mode
        payload = self._build_openai_payload(image_b64, mime, system_prompt, user_prompt)
        return self._call_openai(payload)

    def _encode_image(self, image_path: str) -> tuple[str, str]:
        """Read and base64-encode an image file. Returns (b64, mime)."""
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode()
        suffix = Path(image_path).suffix.lower()
        mime = _MIME_MAP.get(suffix, "image/jpeg")
        return image_b64, mime

    def tag_image(self, image_path: str) -> WdTagResult:
        image_b64, mime = self._encode_image(image_path)
        content = self._call_api(image_b64, mime, SYSTEM_PROMPT, USER_PROMPT)

        raw_tags = _parse_tag_list(content)
        tags: list[TagPrediction] = []
        for t in raw_tags:
            name = str(t).strip().lower().replace(" ", "_")
            if name:
                tags.append(TagPrediction(tag=name, confidence=0.5, category="general"))

        return WdTagResult(tags=tags, model=self._model)

    def request_complement(
        self,
        image_path: str,
        existing_tags: list[str],
    ) -> list[TagPrediction]:
        """Request complementary tags for Mode B (composite engine)."""
        image_b64, mime = self._encode_image(image_path)
        tags_str = ", ".join(existing_tags)
        sys_prompt = COMPLEMENT_SYSTEM_PROMPT.format(existing_tags=tags_str)
        content = self._call_api(image_b64, mime, sys_prompt, USER_PROMPT)

        raw_tags = _parse_tag_list(content)
        existing_set = set(existing_tags)
        result: list[TagPrediction] = []
        for t in raw_tags:
            name = str(t).strip().lower().replace(" ", "_")
            if name and name not in existing_set:
                result.append(TagPrediction(tag=name, confidence=0.4, category="general"))
        return result

    def get_name(self) -> str:
        return f"VLM ({self._model})" if self._model else "VLM"

    def is_available(self) -> bool:
        from core.analysis.openai_compat_utils import check_openai_compat_connection
        result = check_openai_compat_connection(self._base_url, allow_local=True)
        return result.get("connected", False)
