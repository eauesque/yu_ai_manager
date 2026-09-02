#!/usr/bin/env python3
"""License compliance audit script."""

import sys

from license_audit_checks import run_all_checks
from license_audit_i18n import msg
from license_audit_state import AuditState


def main() -> int:
    state = AuditState()
    print("=" * 60)
    print(msg("title"))
    print("=" * 60)
    run_all_checks(state)
    print("\n" + "=" * 60)
    print(msg("results").format(passed=state.passed, failed=state.failed))
    print("=" * 60)
    return 1 if state.failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
