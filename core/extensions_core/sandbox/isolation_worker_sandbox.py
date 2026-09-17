"""Sandbox enforcement and module loading for the isolation worker.

Contains seccomp-bpf, network namespace, extension module loading,
serialization/deserialization, and RPC request handling.
"""

from __future__ import annotations

import builtins
import contextlib
import importlib.abc
import importlib.util
import logging
import sys
import types
from pathlib import Path
from typing import Any

logger = logging.getLogger("isolation_worker")
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_PUBLIC_SDK_MODULE = "yu_extension_sdk"
_PROJECT_IMPORT_ROOTS = frozenset(
    {path.name for path in _PROJECT_ROOT.iterdir() if path.is_dir()}
    | {path.stem for path in _PROJECT_ROOT.glob("*.py")}
    | {path.stem for path in Path(__file__).parent.glob("*.py")}
    | {"services"}
)


def _is_project_import(name: str) -> bool:
    return name.partition(".")[0] in _PROJECT_IMPORT_ROOTS


class _ProjectImportFence(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if _is_project_import(fullname):
            raise ImportError(f"Project-internal import denied: {fullname}")
        return None


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    fullname = name
    if level:
        package = (globals or {}).get("__package__", "")
        fullname = importlib.util.resolve_name("." * level + name, package)
    if _is_project_import(fullname):
        raise ImportError(f"Project-internal import denied: {fullname}")
    return builtins.__import__(name, globals, locals, fromlist, level)


def _install_project_import_fence() -> None:
    for name in tuple(sys.modules):
        if _is_project_import(name):
            sys.modules.pop(name, None)
    if not any(isinstance(finder, _ProjectImportFence) for finder in sys.meta_path):
        sys.meta_path.insert(0, _ProjectImportFence())


def install_public_sdk(rpc_client: Any) -> None:
    """Install the only project-facing module available to worker code."""
    try:
        from .ipc_protocol import ReadOnlyDBClient
    except ImportError:
        from ipc_protocol import ReadOnlyDBClient

    sdk = types.ModuleType(_PUBLIC_SDK_MODULE)
    sdk.db = ReadOnlyDBClient(rpc_client)
    sdk.__all__ = ("db",)
    sys.modules[_PUBLIC_SDK_MODULE] = sdk


def apply_seccomp() -> bool:
    """Apply seccomp-bpf syscall filtering (optional)."""
    try:
        import seccomp
    except ImportError:
        logger.info("seccomp library not installed, skipping")
        return False

    try:
        f = seccomp.SyscallFilter(seccomp.KILL)
        # Allow basic operations
        allowed = [
            "read", "write", "close", "fstat", "lseek",
            "mmap", "mprotect", "munmap", "brk",
            "rt_sigaction", "rt_sigprocmask", "rt_sigreturn",
            "ioctl", "access", "pipe", "select", "poll",
            "sched_yield", "mremap", "madvise",
            "dup", "dup2", "dup3",
            "nanosleep", "clock_nanosleep",
            "getpid", "getuid", "getgid", "geteuid", "getegid",
            "gettid", "getppid",
            "exit", "exit_group",
            "futex", "set_robust_list", "get_robust_list",
            "clock_gettime", "clock_getres",
            "openat", "newfstatat", "readlinkat",
            "getrandom", "pread64", "pwrite64",
            "fcntl", "flock",
            "lstat", "stat",
            "sendto", "recvfrom", "sendmsg", "recvmsg",  # For Unix sockets
        ]
        for name in allowed:
            with contextlib.suppress(Exception):
                f.add_rule(seccomp.ALLOW, name)
        f.load()
        logger.info("seccomp-bpf filter applied")
        return True
    except Exception as exc:
        logger.warning(f"seccomp application failed: {exc}")
        return False


def apply_network_namespace() -> bool:
    """Apply network namespace to block external communication (optional)."""
    try:
        import ctypes
        import ctypes.util

        CLONE_NEWNET = 0x40000000
        libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
        ret = libc.unshare(CLONE_NEWNET)
        if ret != 0:
            errno = ctypes.get_errno()
            logger.warning(f"unshare(CLONE_NEWNET) failed: errno={errno}")
            return False
        logger.info("Network namespace applied")
        return True
    except Exception as exc:
        logger.warning(f"Network namespace application failed: {exc}")
        return False


def load_extension_module(
    ext_name: str, ext_dir: str, entry: str
) -> Any:
    """Load an extension module from file path."""
    module_name = f"ext_{ext_name.replace('-', '_')}"
    from core.extensions_core.entry_path import resolve_extension_entry
    entry_path = resolve_extension_entry(Path(ext_dir), entry)

    spec = importlib.util.spec_from_file_location(
        module_name,
        str(entry_path),
        submodule_search_locations=[ext_dir],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create module spec for {entry_path}")

    _install_project_import_fence()
    module = importlib.util.module_from_spec(spec)
    module.__package__ = module_name
    module.__path__ = [ext_dir]
    safe_builtins = vars(builtins).copy()
    safe_builtins["__import__"] = _guarded_import
    module.__builtins__ = safe_builtins
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def serialize(obj: Any) -> Any:
    """Convert a Python object to a JSON-serializable form."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, bytes):
        import base64
        return {"__type__": "bytes", "data": base64.b64encode(obj).decode("ascii")}
    if isinstance(obj, Path):
        return {"__type__": "path", "data": str(obj)}
    if isinstance(obj, (list, tuple)):
        return [serialize(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): serialize(v) for k, v in obj.items()}
    return str(obj)


def deserialize(obj: Any) -> Any:
    """Restore a deserialized JSON value to its original Python type."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        t = obj.get("__type__")
        if t == "bytes":
            import base64
            return base64.b64decode(obj["data"])
        if t == "path":
            return Path(obj["data"])
        return {k: deserialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deserialize(x) for x in obj]
    return obj


def call_hook(module: Any, params: dict) -> Any:
    """Call an extension hook function."""
    hook_name = params.get("hook_name", "")
    args = deserialize(params.get("args", []))
    kwargs = deserialize(params.get("kwargs", {}))

    callback = getattr(module, hook_name, None)
    if callback is None or not callable(callback):
        raise AttributeError(f"Hook not found: {hook_name}")

    result = callback(*args, **kwargs)
    return serialize(result)


def handle_rpc_request(
    module: Any, request: dict, ext_name: str
) -> dict:
    """Process a JSON-RPC request and return the response."""
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params", {})

    try:
        if method == "hook.call":
            result = call_hook(module, params)
            return {"jsonrpc": "2.0", "result": result, "id": req_id}

        if method == "shutdown":
            return {"jsonrpc": "2.0", "result": "ok", "id": req_id}

        if method == "ping":
            return {"jsonrpc": "2.0", "result": "pong", "id": req_id}

        return {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": f"Unknown method: {method}"},
            "id": req_id,
        }
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32000, "message": str(exc)},
            "id": req_id,
        }
