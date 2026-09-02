"""Route registrations for scan-roots APIs."""

from routes.scan_roots_api.routes_config import register_scan_roots_config_routes
from routes.scan_roots_api.routes_scan import register_scan_roots_scan_routes


def register_scan_roots_routes(bp) -> None:
    register_scan_roots_config_routes(bp)
    register_scan_roots_scan_routes(bp)
