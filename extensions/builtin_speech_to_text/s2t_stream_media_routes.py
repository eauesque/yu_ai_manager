"""Media streaming routes for stream transcription."""

import asyncio

from quart import Response, jsonify


def register_stream_media_routes(bp, logger) -> None:
    @bp.route("/api/s2t/stream/video")
    async def api_stream_video():
        """Stream video as MJPEG for browser preview."""
        from .core_impl.stream_state import get_video_relay

        relay = get_video_relay()
        if relay is None or not relay.is_running:
            return jsonify({"status": "error", "message": "No video stream"}), 404

        async def generate():
            while True:
                frame = await asyncio.get_event_loop().run_in_executor(
                    None,
                    relay.read_frame,
                )
                if frame is None:
                    break
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )

        resp = Response(
            generate(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )
        resp.timeout = None
        resp.headers["Cache-Control"] = "no-cache, no-store"
        return resp

    @bp.route("/api/s2t/stream/media")
    async def api_stream_media():
        """Stream as fMP4 (video+audio) for browser <video> playback."""
        from .core_impl.stream_state import (
            get_media_relay,
            get_status,
            restart_media_relay,
        )

        relay = get_media_relay()
        if relay is None:
            status = get_status()
            video_mode = status.get("video_mode", "unknown")
            source_url = status.get("source_url", "")
            running = status.get("running", False)
            logger.warning(
                "stream/media 404: video_mode=%s, running=%s, source=%s",
                video_mode,
                running,
                source_url[:60],
            )
            return jsonify(
                {
                    "status": "error",
                    "message": "No media stream (use mjpeg endpoints for RTSP)",
                    "video_mode": video_mode,
                    "running": running,
                }
            ), 404

        if not relay.is_running:
            logger.info("MediaRelay FFmpeg died, restarting...")
            relay = restart_media_relay()
            if relay is None or not relay.is_running:
                return jsonify(
                    {
                        "status": "error",
                        "message": "Media relay restart failed",
                    }
                ), 503

        async def generate():
            while True:
                data = await asyncio.get_event_loop().run_in_executor(
                    None,
                    relay.read,
                    8192,
                )
                if not data:
                    break
                yield data

        resp = Response(generate(), mimetype="video/mp4")
        resp.timeout = None
        resp.headers["Cache-Control"] = "no-cache, no-store"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @bp.route("/api/s2t/stream/audio")
    async def api_stream_audio():
        """Stream audio as MP3 for browser playback."""
        from .core_impl.stream_state import get_audio_relay

        relay = get_audio_relay()
        if relay is None or not relay.is_running:
            return jsonify({"status": "error", "message": "No active stream"}), 404

        async def generate():
            while True:
                data = await asyncio.get_event_loop().run_in_executor(
                    None,
                    relay.read,
                    4096,
                )
                if not data:
                    break
                yield data

        resp = Response(generate(), mimetype="audio/mpeg")
        resp.timeout = None
        resp.headers["Cache-Control"] = "no-cache, no-store"
        return resp
