"""View/serialization helpers for extension hook registry."""



def format_registered_hooks(hooks: dict[str, list], hook_name: str | None = None) -> dict[str, list[dict]]:
    if hook_name:
        entries = hooks.get(hook_name, [])
        return {
            hook_name: [
                {"extension": e.extension_name, "priority": e.priority, "enabled": e.enabled}
                for e in entries
            ]
        }

    result = {}
    for name, entries in hooks.items():
        result[name] = [
            {"extension": e.extension_name, "priority": e.priority, "enabled": e.enabled}
            for e in entries
        ]
    return result
