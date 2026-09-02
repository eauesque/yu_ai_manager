"""Core extension system implementation package.

Subpackage structure:
    sandbox/    -- Sandbox, process isolation, OS isolation, import guard
    validation/ -- Code verification, manifest review, permission management
    token_mgmt/ -- Capability Token issuance/verification/revocation
    lifecycle/  -- Loader, manager, hooks, admin, marketplace

Backward compatibility: old paths (e.g. core.extensions_core.capability_token)
are auto-resolved to new paths by the import alias installer.
"""

from core.extensions_core.import_aliases import install_import_aliases

install_import_aliases()
