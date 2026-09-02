"""LLM post-processing routes for stream transcription."""

import logging

from quart import jsonify, request

logger = logging.getLogger(__name__)


def register_stream_llm_routes(bp) -> None:
    @bp.route("/api/s2t/stream/llm-process", methods=["POST"])
    async def api_stream_llm_process():
        """Send transcript to LLM for refinement/translation."""
        from .core_impl.stream_state import get_transcript

        data = await request.get_json(silent=True) or {}
        mode = data.get("mode", "refine")
        target_lang = data.get("target_lang", "en")

        segments = get_transcript()
        text = "\n".join(
            segment.get("text", "")
            for segment in segments
            if segment.get("text")
        )
        if not text:
            return jsonify(
                {"status": "error", "message": "No transcript available"}
            ), 400

        if mode == "translate":
            prompt = (
                f"Translate the following transcript to {target_lang}. "
                f"Keep the meaning accurate. Output only the translation:\n\n{text}"
            )
        elif mode == "summarize":
            prompt = f"Summarize the following transcript concisely:\n\n{text}"
        else:
            prompt = (
                "Clean up and correct the following speech-to-text transcript. "
                "Fix obvious recognition errors, add proper punctuation, "
                f"and make it readable. Output only the corrected text:\n\n{text}"
            )

        try:
            from importlib import import_module

            genai_mod = import_module(
                "extensions.builtin_hailo_genai.core_impl.llm_inference"
            )
            result_text = genai_mod.generate(prompt, max_tokens=2048)
            return jsonify(
                {
                    "status": "ok",
                    "result": result_text,
                    "mode": mode,
                    "backend": "hailo-llm",
                }
            )
        except (ImportError, Exception):
            logger.warning("stream LLM step failed", exc_info=True)

        return jsonify(
            {
                "status": "ok",
                "result": None,
                "prompt": prompt,
                "mode": mode,
                "backend": "none",
                "message": "LLM not available. Use the prompt with an external LLM.",
            }
        )
