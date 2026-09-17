"""Signed update package verification and application."""

from __future__ import annotations

from .apply import ApplyResult, apply_update_package
from .rollback import RollbackResult, rollback_latest_update
from .verify import UpdatePackageError, VerificationResult, verify_update_package

__all__ = [
    "ApplyResult",
    "RollbackResult",
    "UpdatePackageError",
    "VerificationResult",
    "apply_update_package",
    "rollback_latest_update",
    "verify_update_package",
]
