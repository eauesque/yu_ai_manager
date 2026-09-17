"""Semantic version comparison utility."""

from __future__ import annotations

import re


def parse_version(version_str: str) -> tuple[int, ...]:
    """Convert a version string to a tuple. "1.2.3" -> (1, 2, 3)"""
    match = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", version_str.strip())
    if not match:
        return (0, 0, 0)
    parts = [int(x) if x else 0 for x in match.groups()]
    return tuple(parts)


def version_satisfies(current: str, requirement: str) -> bool:
    """Check whether the current version satisfies the requirement.

    Supported operators:
        ">=1.0.0", ">1.0.0", "==1.0.0", "<=1.0.0", "<1.0.0",
        "1.0.0" (no operator = exact match)
    """
    requirement = requirement.strip()

    if requirement.startswith(">="):
        return parse_version(current) >= parse_version(requirement[2:])
    elif requirement.startswith(">"):
        return parse_version(current) > parse_version(requirement[1:])
    elif requirement.startswith("<="):
        return parse_version(current) <= parse_version(requirement[2:])
    elif requirement.startswith("<"):
        return parse_version(current) < parse_version(requirement[1:])
    elif requirement.startswith("=="):
        return parse_version(current) == parse_version(requirement[2:])
    else:
        # No operator = exact match
        return parse_version(current) == parse_version(requirement)


def compare_versions(a: str, b: str) -> int:
    """Compare two version strings.

    Returns:
        -1: a < b
         0: a == b
         1: a > b
    """
    va = parse_version(a)
    vb = parse_version(b)
    if va < vb:
        return -1
    if va > vb:
        return 1
    return 0
