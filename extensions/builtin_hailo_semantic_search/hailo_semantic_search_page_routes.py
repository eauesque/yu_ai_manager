"""Page route for Hailo semantic search."""

from quart import render_template


def register_page_routes(bp):
    @bp.route("/")
    async def index():
        return await render_template("hailo_semantic_search/semantic.html")
