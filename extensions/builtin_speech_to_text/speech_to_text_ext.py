"""Speech-to-Text Extension entry point.

Provides unified S2T with automatic backend selection:
Hailo NPU > CUDA GPU > CPU (faster-whisper / whisper.cpp).
"""

from quart import Blueprint, render_template


def get_blueprint():
    """Return the Quart Blueprint for Speech-to-Text."""
    bp = Blueprint(
        "ext_speech_to_text",
        __name__,
        template_folder="templates",
    )

    @bp.route("/")
    async def index():
        return await render_template("speech_to_text/s2t.html")

    from .s2t_batch_routes import register_batch_routes
    from .s2t_routes import register_s2t_routes
    from .s2t_stream_routes import register_stream_routes

    register_s2t_routes(bp)
    register_batch_routes(bp)
    register_stream_routes(bp)

    return bp
