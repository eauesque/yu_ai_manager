"""Control/status routes for stream transcription."""

from quart import jsonify, request


def register_stream_control_routes(bp, require_admin_scope, logger) -> None:
    @bp.route("/api/s2t/stream/start", methods=["POST"])
    async def api_stream_start():
        """Start real-time stream transcription."""
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.stream_state import start_stream, validate_stream_source_url

        data = await request.get_json(silent=True) or {}
        source_url = data.get("source_url", "").strip()
        if not source_url:
            return jsonify(
                {
                    "status": "error",
                    "message": "source_url is required",
                }
            ), 400

        url_error = validate_stream_source_url(source_url)
        if url_error:
            return jsonify(
                {
                    "status": "error",
                    "message": url_error,
                }
            ), 400

        language = data.get("language", "ja")
        model_size = data.get("model_size", "")
        mode = data.get("mode", "chunk")
        if mode not in ("chunk", "live"):
            return jsonify(
                {
                    "status": "error",
                    "message": "mode must be 'chunk' or 'live'",
                }
            ), 400
        result = start_stream(
            source_url,
            language,
            model_size=model_size,
            mode=mode,
        )
        logger.info(
            "stream/start result: video_mode=%s, status=%s, source=%s",
            result.get("video_mode", "?"),
            result.get("status", "?"),
            source_url[:60],
        )
        return jsonify({"status": "ok", **result})

    @bp.route("/api/s2t/stream/stop", methods=["POST"])
    async def api_stream_stop():
        """Stop the running stream transcription."""
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.stream_state import stop_stream

        result = stop_stream()
        return jsonify({"status": "ok", **result})

    @bp.route("/api/s2t/stream/status")
    async def api_stream_status():
        """Return current stream transcription status."""
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.stream_state import get_status

        return jsonify({"status": "ok", **get_status()})

    @bp.route("/api/s2t/stream/transcript")
    async def api_stream_transcript():
        """Return accumulated transcript segments."""
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.stream_state import get_transcript, get_transcript_dropped_count

        segments = get_transcript()
        dropped = get_transcript_dropped_count()
        full_text = " ".join(segment.get("text", "") for segment in segments)
        return jsonify(
            {
                "status": "ok",
                "segments": segments,
                "text": full_text,
                "count": len(segments),
                "offset": dropped,
                "total_count": dropped + len(segments),
            }
        )
