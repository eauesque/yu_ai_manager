"""Transcript export routes for stream transcription."""

from quart import Response


def _format_srt_time(seconds: float) -> str:
    """Format seconds as SRT timestamp HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole_seconds = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def register_stream_export_routes(bp, require_admin_scope) -> None:
    @bp.route("/api/s2t/stream/export/txt")
    async def api_stream_export_txt():
        """Export transcript as plain text."""
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.stream_state import get_transcript

        segments = get_transcript()
        text = "\n".join(
            segment.get("text", "")
            for segment in segments
            if segment.get("text")
        )
        return Response(
            text,
            mimetype="text/plain",
            headers={
                "Content-Disposition": "attachment; filename=transcript.txt",
            },
        )

    @bp.route("/api/s2t/stream/export/srt")
    async def api_stream_export_srt():
        """Export transcript as SRT subtitle format."""
        auth_err = require_admin_scope()
        if auth_err:
            return auth_err
        from .core_impl.stream_state import get_transcript

        segments = get_transcript()
        lines = []
        for index, segment in enumerate(segments, 1):
            start = _format_srt_time(segment.get("start", 0))
            end = _format_srt_time(segment.get("end", 0))
            text = segment.get("text", "").strip()
            if text:
                lines.append(f"{index}\n{start} --> {end}\n{text}\n")
        srt = "\n".join(lines)
        return Response(
            srt,
            mimetype="text/plain",
            headers={
                "Content-Disposition": "attachment; filename=transcript.srt",
            },
        )
