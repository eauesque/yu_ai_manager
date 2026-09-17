"""Extension permission persistence: managed in the extension_permissions section of config.json.

Saves user-approved/denied permissions to config.json so that
the same decisions are applied on the next startup.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


@dataclass
class GrantedPermissions:
    """Permission information approved by the user."""
    trust_level: str = ""
    granted: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)
    granted_at: str = ""
    auto_approved: bool = False


def load_extension_permissions(config: dict) -> dict[str, GrantedPermissions]:
    """Load permission information from the extension_permissions section of config."""
    result: dict[str, GrantedPermissions] = {}
    section = config.get("extension_permissions", {})
    if not isinstance(section, dict):
        return result

    for ext_name, data in section.items():
        if not isinstance(data, dict):
            continue
        result[ext_name] = GrantedPermissions(
            trust_level=data.get("trust_level", ""),
            granted=data.get("granted", []),
            denied=data.get("denied", []),
            granted_at=data.get("granted_at", ""),
            auto_approved=data.get("auto_approved", False),
        )
    return result


def get_granted_permission_set(config: dict, ext_name: str) -> set[str]:
    """Return the set of approved permission names for a specific extension."""
    perms = load_extension_permissions(config)
    gp = perms.get(ext_name)
    if gp is None:
        return set()
    return set(gp.granted)


def has_user_approval(config: dict, ext_name: str) -> bool:
    """Return whether the user has already approved permissions."""
    perms = load_extension_permissions(config)
    return ext_name in perms


def save_extension_permissions(
    config: dict,
    ext_name: str,
    granted: GrantedPermissions,
) -> None:
    """Write permission information to the config dict.

    Note: Only modifies the config dict; file saving is done by the caller.
    """
    if "extension_permissions" not in config:
        config["extension_permissions"] = {}

    config["extension_permissions"][ext_name] = {
        "trust_level": granted.trust_level,
        "granted": granted.granted,
        "denied": granted.denied,
        "granted_at": granted.granted_at,
        "auto_approved": granted.auto_approved,
    }


def approve_permissions(
    config: dict,
    ext_name: str,
    trust_level: str,
    granted_perms: list[str],
    denied_perms: list[str] | None = None,
    auto: bool = False,
) -> GrantedPermissions:
    """Approve permissions and save to config."""
    gp = GrantedPermissions(
        trust_level=trust_level,
        granted=granted_perms,
        denied=denied_perms or [],
        granted_at=datetime.now(UTC).isoformat(),
        auto_approved=auto,
    )
    save_extension_permissions(config, ext_name, gp)
    logger.info(
        f"Extension '{ext_name}' の権限を承認: "
        f"granted={granted_perms}, denied={denied_perms or []}"
    )
    return gp


def revoke_permissions(config: dict, ext_name: str) -> bool:
    """Revoke permission approval."""
    section = config.get("extension_permissions", {})
    if ext_name in section:
        del section[ext_name]
        logger.info(f"Extension '{ext_name}' の権限承認を取り消しました")
        return True
    return False
