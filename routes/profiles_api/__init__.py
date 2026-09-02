"""Profiles API package -- backward-compat re-export.

Route registration callables now live in ``core/profiles_api/``. This
package is preserved as a thin re-export so external imports keep
working.
"""

from core.profiles_api import (
    register_profiles_crud_routes,
    register_profiles_qr_routes,
)

__all__ = [
    "register_profiles_crud_routes",
    "register_profiles_qr_routes",
]
