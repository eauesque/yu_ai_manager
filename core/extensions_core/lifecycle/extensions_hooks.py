"""Extension hooks registry."""

from collections.abc import Callable
from typing import Any

from core.extensions_core.extensions_defs import HOOK_DEFINITIONS, HookEntry

from .extensions_hooks_invoke import invoke_chain, invoke_collect, invoke_exclusive
from .extensions_hooks_view import format_registered_hooks


class HookRegistry:
    """Register and invoke extension hooks."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookEntry]] = {
            name: [] for name in HOOK_DEFINITIONS
        }

    def register(self, hook_name: str, extension_name: str,
                 callback: Callable, priority: int = 100) -> None:
        if hook_name not in HOOK_DEFINITIONS:
            raise ValueError(
                f"Unknown hook: {hook_name!r}. Available: {list(HOOK_DEFINITIONS.keys())}"
            )
        entry = HookEntry(
            extension_name=extension_name,
            priority=priority,
            callback=callback,
            enabled=True,
        )
        self._hooks[hook_name].append(entry)
        self._hooks[hook_name].sort(key=lambda e: e.priority)

    def unregister(self, hook_name: str, extension_name: str) -> None:
        if hook_name in self._hooks:
            self._hooks[hook_name] = [
                e for e in self._hooks[hook_name]
                if e.extension_name != extension_name
            ]

    def unregister_all(self, extension_name: str) -> None:
        for hook_name in self._hooks:
            self.unregister(hook_name, extension_name)

    def set_enabled(self, extension_name: str, enabled: bool) -> None:
        for entries in self._hooks.values():
            for entry in entries:
                if entry.extension_name == extension_name:
                    entry.enabled = enabled

    def invoke(self, hook_name: str, *args, **kwargs) -> Any:
        if hook_name not in HOOK_DEFINITIONS:
            return None

        mode = HOOK_DEFINITIONS[hook_name]
        entries = [e for e in self._hooks[hook_name] if e.enabled]

        if not entries:
            return [] if mode == "collect" else None

        if mode == "exclusive":
            return self._invoke_exclusive(entries, *args, **kwargs)
        if mode == "chain":
            return self._invoke_chain(entries, *args, **kwargs)
        if mode == "collect":
            return self._invoke_collect(entries, *args, **kwargs)
        return None

    def _invoke_exclusive(self, entries: list[HookEntry], *args, **kwargs) -> Any:
        return invoke_exclusive(entries, *args, **kwargs)

    def _invoke_chain(self, entries: list[HookEntry], *args, **kwargs) -> Any:
        return invoke_chain(entries, *args, **kwargs)

    def _invoke_collect(self, entries: list[HookEntry], *args, **kwargs) -> list[Any]:
        return invoke_collect(entries, *args, **kwargs)

    def get_registered(self, hook_name: str | None = None) -> dict[str, list[dict]]:
        return format_registered_hooks(self._hooks, hook_name)
