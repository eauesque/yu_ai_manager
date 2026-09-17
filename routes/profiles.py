"""Profile Manager API blueprint assembly."""

from quart import Blueprint

from core.profiles_api import register_profiles_crud_routes, register_profiles_qr_routes

bp = Blueprint("profiles", __name__)

register_profiles_crud_routes(bp)
register_profiles_qr_routes(bp)
