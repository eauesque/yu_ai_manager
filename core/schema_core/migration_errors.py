"""Typed migration failures for startup-facing diagnostics."""


class MigrationError(Exception):
    """Base class for migration failures that should stop startup."""


class InsufficientDiskForMigration(MigrationError):
    """Raised when a migration cannot safely fit its projected disk usage."""


class MigrationDataIntegrityError(MigrationError):
    """Raised when existing data would break a required migration invariant."""
