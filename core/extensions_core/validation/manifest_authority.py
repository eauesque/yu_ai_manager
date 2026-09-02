"""Manifest Authority (legislative): Reviews permission declarations in extension manifests.

Corresponds to the "legislative" branch of the separation-of-powers model,
validating the legitimacy, dangerous combinations, and integrity of
permissions declared in manifests.

Builtin (TrustLevel.TRUSTED) is auto-approved and skipped.
"""

import logging
from dataclasses import dataclass, field

from core.extensions_core.extensions_defs import (
    VALID_PERMISSIONS,
    ExtensionManifest,
    TrustLevel,
)

logger = logging.getLogger(__name__)

# (severity, message)
Issue = tuple[str, str]


@dataclass
class ManifestVerdict:
    """Manifest review result."""
    approved: bool = True
    issues: list[Issue] = field(default_factory=list)


# Dangerous permission combinations
DANGEROUS_COMBINATIONS: list[tuple[set[str], str]] = [
    (
        {"network:internet", "fs:write:any"},
        "ネットワーク通信 + 任意ファイル書き込みはデータ送信・改ざんリスク",
    ),
    (
        {"subprocess", "network:internet"},
        "外部プロセス実行 + ネットワーク通信はリモートコード実行リスク",
    ),
    (
        {"subprocess", "fs:write:any"},
        "外部プロセス実行 + 任意ファイル書き込みはシステム改ざんリスク",
    ),
    (
        {"db:write", "network:internet"},
        "DB 書き込み + ネットワーク通信はデータ漏洩・改ざんリスク",
    ),
]


class ManifestAuthority:
    """Manifest review authority."""

    def review(self, manifest: ExtensionManifest) -> ManifestVerdict:
        """Review permission declarations in a manifest.

        L0 (builtin) is auto-approved.
        L1/L2 checks:
          1. Presence of the permissions field
          2. Whether declared permissions are in VALID_PERMISSIONS
          3. Detection of dangerous combinations
          4. Consistency between hooks and permissions
        """
        verdict = ManifestVerdict()

        # L0: builtin bypasses all checks
        if manifest.trust_level == TrustLevel.TRUSTED:
            return verdict

        # 1. Check that permissions field is present
        if manifest.permissions is None:
            verdict.approved = False
            verdict.issues.append((
                "block",
                "permissions フィールドが未定義です。"
                "非 builtin Extension は権限宣言が必須です",
            ))
            return verdict

        # Collect all declared permission names
        all_perms: set[str] = set()
        for decl in manifest.permissions.required:
            all_perms.add(decl.name)
        for decl in manifest.permissions.optional:
            all_perms.add(decl.name)

        # 2. Validate permission names
        for perm_name in sorted(all_perms):
            if perm_name not in VALID_PERMISSIONS:
                verdict.approved = False
                verdict.issues.append((
                    "block",
                    f"未知の権限 '{perm_name}' が宣言されています。"
                    f"有効な権限: {', '.join(sorted(VALID_PERMISSIONS))}",
                ))

        # 3. Detect dangerous combinations
        for combo, reason in DANGEROUS_COMBINATIONS:
            if combo.issubset(all_perms):
                verdict.issues.append((
                    "warn",
                    f"危険な権限の組み合わせ: "
                    f"{', '.join(sorted(combo))} — {reason}",
                ))

        # 4. Consistency between hooks and permissions
        if manifest.hooks and "event_bus" not in all_perms:
            verdict.issues.append((
                "warn",
                "hooks を使用していますが event_bus 権限が宣言されていません",
            ))

        if manifest.has_blueprint:
            has_bp_perm = (
                "blueprint:api" in all_perms or "blueprint:page" in all_perms
            )
            if not has_bp_perm:
                verdict.issues.append((
                    "warn",
                    "Blueprint を持っていますが blueprint:api/blueprint:page "
                    "権限が宣言されていません",
                ))

        return verdict
