"""Small platform delegates for runtime runner."""


def ensure_ssl_certs() -> None:
    from core.platform import ensure_ssl_certs as _ensure_ssl_certs

    _ensure_ssl_certs()


def kill_stale_port(port: int) -> None:
    from core.platform import kill_stale_port as _kill_stale_port

    _kill_stale_port(port)
