"""AI analysis API route registration facade."""

from quart import Blueprint

from .analysis_config_routes import register_analysis_config_routes
from .analysis_job_routes import register_analysis_job_routes
from .analysis_server_routes import register_analysis_server_routes

bp = Blueprint("analysis", __name__)

register_analysis_config_routes(bp)
register_analysis_job_routes(bp)
register_analysis_server_routes(bp)
