"""Scan roots and model checkpoint APIs."""

from quart import Blueprint

from routes.scan_roots_api import register_scan_roots_routes

bp = Blueprint("scan_roots", __name__)

register_scan_roots_routes(bp)
