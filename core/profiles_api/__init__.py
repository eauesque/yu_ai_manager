"""Profiles service layer.

Pydantic request models + route registration callables. Routes layer
(``routes/profiles.py``) creates the Blueprint and calls the
``register_profiles_*_routes(bp)`` helpers.
"""

from core.profiles_api.request_models import (
    ProfileCreateRequest,
    ProfileDuplicateRequest,
    ProfileRenameRequest,
    ProfileUpdateRequest,
)
from core.profiles_api.routes_crud import register_profiles_crud_routes
from core.profiles_api.routes_qr import register_profiles_qr_routes

__all__ = [
    "ProfileCreateRequest",
    "ProfileDuplicateRequest",
    "ProfileRenameRequest",
    "ProfileUpdateRequest",
    "register_profiles_crud_routes",
    "register_profiles_qr_routes",
]
