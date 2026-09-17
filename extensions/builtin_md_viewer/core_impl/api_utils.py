from quart import request


def int_param(name: str, default: int, min_val: int = 0, max_val: int = 10000) -> int:
    try:
        val = int(request.args.get(name, default))
        return max(min_val, min(val, max_val))
    except (ValueError, TypeError):
        return default
