import threading

_gate = None
_gate_lock = threading.Lock()


def get_or_create_gate(factory):
    global _gate
    if _gate is None:
        with _gate_lock:
            if _gate is None:
                _gate = factory()
    return _gate
