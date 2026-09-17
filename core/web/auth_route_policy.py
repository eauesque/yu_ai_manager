"""Route declaration helpers for auth-chain bypass metadata."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

_CONVERTER_RE = re.compile(r"<(?:(?P<converter>[a-zA-Z_][a-zA-Z0-9_]*):)?(?P<name>[a-zA-Z_][a-zA-Z0-9_]*)>")


@dataclass(frozen=True)
class DeclaredBypassRoute:
    rule: str
    require: str
    pattern: re.Pattern[str]


_DECLARED_BYPASS_ROUTES: dict[tuple[str, str], DeclaredBypassRoute] = {}


def _compile_rule_pattern(rule: str) -> re.Pattern[str]:
    parts: list[str] = ["^"]
    last = 0
    for match in _CONVERTER_RE.finditer(rule):
        start, end = match.span()
        parts.append(re.escape(rule[last:start]))
        converter = match.group("converter") or "default"
        parts.append(r".+" if converter == "path" else r"[^/]+")
        last = end
    parts.append(re.escape(rule[last:]))
    parts.append("$")
    return re.compile("".join(parts))


def clear_declared_bypass_routes() -> None:
    _DECLARED_BYPASS_ROUTES.clear()


def register_declared_bypass_route(rule: str, *, require: str) -> None:
    key = (rule, require)
    if key in _DECLARED_BYPASS_ROUTES:
        return
    _DECLARED_BYPASS_ROUTES[key] = DeclaredBypassRoute(
        rule=rule,
        require=require,
        pattern=_compile_rule_pattern(rule),
    )


def match_declared_bypass(path: str) -> DeclaredBypassRoute | None:
    for route in _DECLARED_BYPASS_ROUTES.values():
        if route.pattern.match(path):
            return route
    return None


def auth_route(
    bp,
    rule: str,
    *,
    absolute_prefix: str,
    methods=None,
    bypass_session: bool = False,
    require: str | None = None,
    **route_kwargs,
):
    """Register a route and capture auth policy beside its declaration."""
    if bypass_session and not require:
        raise ValueError("bypass_session=True routes must declare require=")

    absolute_rule = f"{absolute_prefix}{rule}"

    def decorator(func: Callable):
        func.__auth_policy__ = {
            "bypass_session": bypass_session,
            "require": require,
            "rule": absolute_rule,
        }
        if bypass_session:
            register_declared_bypass_route(absolute_rule, require=require or "")
        return bp.route(rule, methods=methods, **route_kwargs)(func)

    return decorator
