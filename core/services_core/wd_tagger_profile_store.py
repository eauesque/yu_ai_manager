"""User-authored WD-Tagger profile CRUD store.

All functions are synchronous. Async routes must call them through
asyncio.to_thread so filesystem and network I/O do not block the event loop.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path

from filelock import FileLock

from core.paths import get_profiles_dir
from extensions.builtin_wd_tagger.core_impl import registry as _reg
from extensions.builtin_wd_tagger.core_impl.adapters.base import TaggerProfile

_PROFILE_JSON_MAX_BYTES = 1024 * 1024
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class StoreError(Exception):
    """Base class for profile store errors."""


class InvalidIdError(StoreError):
    """Profile id is malformed or escapes the user profile root."""


class NotFoundError(StoreError):
    """User profile does not exist."""


class IdConflictError(StoreError):
    """User profile already exists."""

    def __init__(self, id_: str, overrides_builtin: bool = False):
        super().__init__(id_)
        self.id_ = id_
        self.overrides_builtin = overrides_builtin


class IdImmutableError(StoreError):
    """Path id and body id differ."""


class BuiltinReadOnlyError(StoreError):
    """Builtin-only profile cannot be edited or deleted."""


class InUseError(StoreError):
    """Profile is currently active."""

    def __init__(self, id_: str, active_model_id: str):
        super().__init__(id_)
        self.id_ = id_
        self.active_model_id = active_model_id


class ProfileTooLargeError(StoreError):
    """Profile JSON exceeds the 1MB cap."""


class ValidationFailedError(StoreError):
    """Submitted JSON failed TaggerProfile validation."""

    def __init__(self, errors: list[dict]):
        super().__init__("validation failed")
        self.errors = errors


def _wd_tagger_dir() -> Path:
    directory = get_profiles_dir() / "wd_tagger"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _lock_dir() -> Path:
    directory = _wd_tagger_dir() / ".locks"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _validate_id(id_: str) -> None:
    if not isinstance(id_, str) or not _ID_RE.match(id_):
        raise InvalidIdError(id_)


def _user_path(id_: str) -> Path:
    _validate_id(id_)
    root = _wd_tagger_dir().resolve()
    candidate = (root / f"{id_}.json").resolve()
    if not candidate.is_relative_to(root):
        raise InvalidIdError(id_)
    return candidate


def _lock_for(id_: str) -> FileLock:
    _validate_id(id_)
    return FileLock(str(_lock_dir() / f"{id_}.lock"))


def _read_user_json(path: Path) -> dict:
    with path.open("rb") as fh:
        raw = fh.read(_PROFILE_JSON_MAX_BYTES + 1)
    if len(raw) > _PROFILE_JSON_MAX_BYTES:
        raise ProfileTooLargeError(str(path))
    return json.loads(raw.decode("utf-8-sig"))


def _atomic_write_json(dest: Path, obj: dict) -> None:
    parent = dest.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f"{dest.stem}.", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8"))
            fh.write(b"\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, dest)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_path)
        raise


def _validate_body(body: dict) -> TaggerProfile:
    if not isinstance(body, dict):
        raise ValidationFailedError([{"path": "", "message": "body must be a JSON object"}])
    data = dict(body)
    data["builtin"] = False
    try:
        return TaggerProfile.from_dict(data, origin="user")
    except (KeyError, TypeError, ValueError) as exc:
        message = str(exc)
        path = message.split(":", 1)[0] if message.startswith(".") else ""
        raise ValidationFailedError([{"path": path, "message": message}]) from exc


def _profile_to_dict(profile: TaggerProfile) -> dict:
    return asdict(profile)


def _safe_serialize(profile: TaggerProfile, *, origin: str, overrides_builtin: bool) -> dict:
    return {
        "profile": _profile_to_dict(profile),
        "origin": origin,
        "overrides_builtin": overrides_builtin,
    }


def _body_for_write(profile: TaggerProfile) -> dict:
    data = _profile_to_dict(profile)
    data.pop("source_profile_version", None)
    data["builtin"] = False
    return data


def _current_builtin_ids() -> frozenset[str]:
    return _reg.TaggerRegistry.get().get_builtin_ids()


def _active_model_id_or_none() -> str | None:
    from core.services_core.wd_active_model import get_active_wd_model_id

    try:
        return get_active_wd_model_id()
    except Exception:
        return None


def create_profile(body: dict) -> dict:
    profile = _validate_body(body)
    id_ = profile.id
    dest = _user_path(id_)
    with _lock_for(id_):
        overrides = id_ in _current_builtin_ids()
        if dest.exists():
            raise IdConflictError(id_, overrides_builtin=overrides)
        _atomic_write_json(dest, _body_for_write(profile))
        _reg.TaggerRegistry.get().reload()
        return _safe_serialize(profile, origin="user", overrides_builtin=overrides)


def update_profile(id_: str, body: dict) -> dict:
    _validate_id(id_)
    body_id = body.get("id") if isinstance(body, dict) else None
    if body_id != id_:
        raise IdImmutableError(id_)
    profile = _validate_body(body)
    dest = _user_path(id_)
    with _lock_for(id_):
        registry = _reg.TaggerRegistry.get()
        meta_by_id = {p.id: m for p, m in registry.list_profiles_with_metadata()}
        if id_ not in meta_by_id:
            raise NotFoundError(id_)
        if meta_by_id[id_]["origin"] == "builtin" and not dest.exists():
            raise BuiltinReadOnlyError(id_)
        overrides = id_ in _current_builtin_ids()
        _atomic_write_json(dest, _body_for_write(profile))
        registry.reload()
        return _safe_serialize(profile, origin="user", overrides_builtin=overrides)


def serialize_profile_full(id_: str) -> dict:
    """Return the full v2 profile JSON plus origin metadata for API responses."""
    _validate_id(id_)
    registry = _reg.TaggerRegistry.get()
    meta_by_id = {p.id: m for p, m in registry.list_profiles_with_metadata()}
    if id_ not in meta_by_id:
        raise NotFoundError(id_)
    try:
        profile = registry.resolve(id_)
    except LookupError as exc:
        raise NotFoundError(id_) from exc
    meta = meta_by_id[id_]
    return _safe_serialize(
        profile,
        origin=str(meta.get("origin") or "builtin"),
        overrides_builtin=bool(meta.get("overrides_builtin", False)),
    )


def delete_profile(id_: str) -> None:
    _validate_id(id_)
    dest = _user_path(id_)
    with _lock_for(id_):
        registry = _reg.TaggerRegistry.get()
        meta_by_id = {p.id: m for p, m in registry.list_profiles_with_metadata()}
        if id_ not in meta_by_id:
            raise NotFoundError(id_)
        if meta_by_id[id_]["origin"] == "builtin" and not dest.exists():
            raise BuiltinReadOnlyError(id_)
        active = _active_model_id_or_none()
        if active is not None and active == id_:
            raise InUseError(id_, active)
        if dest.exists():
            dest.unlink()
        registry.reload()


def dry_run_download(id_: str, *, total_timeout: int = 60) -> dict:
    from extensions.builtin_wd_tagger.core_impl import model_download

    _validate_id(id_)
    try:
        profile = _reg.TaggerRegistry.get().resolve(id_)
    except LookupError as exc:
        raise NotFoundError(id_) from exc

    started = time.monotonic()
    files_out = []
    for file_spec in profile.files:
        remaining = total_timeout - (time.monotonic() - started)
        if remaining <= 0:
            return {"ok": False, "code": "timeout", "files": files_out}
        timeout = max(1, min(30, int(remaining)))
        try:
            head = model_download.head_only(profile, file_spec, timeout=timeout)
        except model_download.SSRFBlocked as exc:
            return {
                "ok": False,
                "code": "ssrf_blocked",
                "files": files_out,
                "detail": str(exc),
            }
        except Exception as exc:
            if file_spec.required:
                return {
                    "ok": False,
                    "code": "required_missing",
                    "files": files_out,
                    "detail": f"HEAD failed for {file_spec.name}: {exc}",
                }
            files_out.append({"name": file_spec.name, "status": "skipped_optional", "size": None})
            continue

        status = int(head["status"])
        if status == 404:
            if file_spec.required:
                return {
                    "ok": False,
                    "code": "required_missing",
                    "files": files_out,
                    "detail": f"hf returned 404 for {file_spec.name}",
                }
            files_out.append({"name": file_spec.name, "status": "skipped_optional", "size": None})
            continue
        if 500 <= status < 600:
            return {
                "ok": False,
                "code": "hf_unavailable",
                "files": files_out,
                "detail": f"hf {status} for {file_spec.name}",
            }
        if status >= 400:
            if file_spec.required:
                return {
                    "ok": False,
                    "code": "required_missing",
                    "files": files_out,
                    "detail": f"hf returned {status} for {file_spec.name}",
                }
            files_out.append({"name": file_spec.name, "status": "skipped_optional", "size": head["size"]})
            continue

        if file_spec.required:
            remaining = total_timeout - (time.monotonic() - started)
            if remaining <= 0:
                return {"ok": False, "code": "timeout", "files": files_out}
            try:
                downloaded = model_download._download_one_file(
                    profile,
                    file_spec,
                    timeout=max(1, min(30, int(remaining))),
                )
            except model_download.SSRFBlocked as exc:
                return {
                    "ok": False,
                    "code": "ssrf_blocked",
                    "files": files_out,
                    "detail": str(exc),
                }
            except Exception as exc:
                return {
                    "ok": False,
                    "code": "required_missing",
                    "files": files_out,
                    "detail": f"download failed for {file_spec.name}: {exc}",
                }
            files_out.append({
                "name": file_spec.name,
                "status": downloaded.get("status", "downloaded"),
                "size": downloaded.get("size", head["size"]),
            })
        else:
            files_out.append({"name": file_spec.name, "status": "cached", "size": head["size"]})

    return {"ok": True, "files": files_out}
