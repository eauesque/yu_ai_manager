"""Download tagger models from HuggingFace.

Phase 2 Task 6: spec § 7 hardening.

- hf_subdir is reflected in both URL path and local cache directory
- DownloadResult dataclass replaces the bare Path return
- per-profile in-process threading.Lock prevents concurrent downloads
  of the same profile from clobbering each other
- tmp filename uses unique suffix .{pid}.{seq}.tmp and atomic move via os.replace
- URL construction uses posixpath.join + urllib.parse.quote(..., safe='/')
- required=false files: 404 → info skip; 403/410 → warn report;
  5xx / network / timeout → raise

Legacy entrypoints (download_model / is_model_downloaded / get_model_status)
remain unchanged for backward compat.
"""
from __future__ import annotations

import itertools
import logging
import os
import posixpath
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.error import HTTPError
from urllib.parse import quote

from .model_download_legacy import (
    LEGACY_DEFAULT_FILES as _LEGACY_DEFAULT_FILES,
)
from .model_download_legacy import (
    USER_AGENT as _USER_AGENT,
)
from .model_download_legacy import (
    get_model_dir,
)
from .model_download_legacy import (
    safe_name as _safe_name,
)
from .model_download_legacy import (
    wd_tagger_cache as _wd_tagger_cache,
)

if TYPE_CHECKING:
    from .adapters.base import TaggerProfile

logger = logging.getLogger(__name__)

_HF_HOST_ALLOW = ("huggingface.co", "hf.co")
_MAX_REDIRECTS = 5
_MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024 * 1024


class SSRFBlocked(Exception):
    """Redirect or initial URL host is not in the HuggingFace allowlist."""


def _is_hf_host(host: str | None) -> bool:
    """Match the URL's *resolved hostname* against the HF allowlist.

    Callers MUST pass `urlsplit(url).hostname` here, NOT raw netloc — netloc
    can contain `userinfo@host` and a naive split would treat the userinfo as
    the host (SSRF bypass: `https://huggingface.co@169.254.169.254/...`).
    `urlsplit.hostname` is lowercased and userinfo-stripped by urllib.
    """
    if not host:
        return False
    return host in _HF_HOST_ALLOW or any(host.endswith("." + allowed) for allowed in _HF_HOST_ALLOW)


class _NoFollowRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Reject urllib auto-redirects so every hop can be host-checked."""

    def http_error_301(self, req, fp, code, msg, headers):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)

    http_error_302 = http_error_303 = http_error_307 = http_error_308 = http_error_301


def _hf_request(
    method: str,
    url: str,
    *,
    timeout: int,
    max_redirects: int = _MAX_REDIRECTS,
):
    opener = urllib.request.build_opener(_NoFollowRedirectHandler())
    current = url
    seen = 0
    while True:
        parsed = urllib.parse.urlsplit(current)
        if parsed.scheme not in ("http", "https"):
            raise SSRFBlocked(parsed.scheme)
        # Reject userinfo (user:pass@) — `https://huggingface.co@evil.com/`
        # would otherwise pass an allowlist check on the userinfo portion.
        if parsed.username or parsed.password:
            raise SSRFBlocked("userinfo in URL")
        if not _is_hf_host(parsed.hostname):
            raise SSRFBlocked(parsed.hostname or parsed.netloc)
        req = urllib.request.Request(
            current,
            method=method,
            headers={"User-Agent": _USER_AGENT},
        )
        try:
            return opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in (301, 302, 303, 307, 308):
                raise
            if seen >= max_redirects:
                raise SSRFBlocked(f"too many redirects (>{max_redirects})") from exc
            location = exc.headers.get("Location") if exc.headers else None
            if not location:
                raise
            current = urllib.parse.urljoin(current, location)
            seen += 1


def _content_length(headers) -> int | None:
    if hasattr(headers, "getheader"):
        value = headers.getheader("Content-Length")
        return int(value) if value and str(value).isdigit() else None
    value = headers.get("Content-Length") if headers else None
    return int(value) if value and str(value).isdigit() else None

# ============================================================
# Per-profile lock registry (spec § 7)
# ============================================================

_PROFILE_LOCKS: dict[str, threading.Lock] = {}
_PROFILE_LOCKS_GUARD = threading.Lock()


def _get_profile_lock(profile_id: str) -> threading.Lock:
    """Return a stable per-profile in-process lock.

    Two concurrent download_model_for_profile() calls for the same
    profile_id must serialize so they don't clobber each other's tmp
    files / partial writes. Different profiles can still download in
    parallel.
    """
    with _PROFILE_LOCKS_GUARD:
        lock = _PROFILE_LOCKS.get(profile_id)
        if lock is None:
            lock = threading.Lock()
            _PROFILE_LOCKS[profile_id] = lock
        return lock


# ============================================================
# Result dataclass (spec § 7)
# ============================================================

@dataclass
class DownloadResult:
    """Outcome of a profile-driven download.

    - downloaded: file names that exist locally after the call (either
      freshly downloaded or already cached)
    - skipped_optional: (name, reason) for optional files that 404'd
    - failed_optional: (name, reason) for optional files that warn'd
      (403 / 410) - present as a report channel but not raised
    """

    profile_id: str
    cache_dir: Path
    downloaded: list[str] = field(default_factory=list)
    skipped_optional: list[tuple[str, str]] = field(default_factory=list)
    failed_optional: list[tuple[str, str]] = field(default_factory=list)


_TEMPORARY_DOWNLOAD_SEQUENCE = itertools.count()


def _temporary_download_path(base: Path, name: str) -> Path:
    """Return a temporary path no concurrent download can also pick.

    The pid alone is not unique within one process, and the cache directory is
    derived from model_id + hf_subdir while the serializing lock is keyed on
    profile.id -- so two profiles pointing at the same HuggingFace repo take
    different locks, share this directory, and used to write the same
    ``{name}.{pid}.tmp``. ``os.replace`` is atomic but cannot help when what it
    moves is a half-written file, and the cached check below tests existence
    only, so one such collision poisons the cache permanently.

    ``itertools.count`` is a C-level iterator, so ``next()`` on it is a single
    bytecode and needs no lock of its own.
    """
    return base / f"{name}.{os.getpid()}.{next(_TEMPORARY_DOWNLOAD_SEQUENCE)}.tmp"


def get_model_dir_for_profile(profile: TaggerProfile) -> Path:
    """Return the cache directory for a profile, applying hf_subdir.

    Spec § 7: hf_subdir must be reflected in **both** the URL path and
    the local cache path so that variant repos (e.g. WD V1 vs V1.1
    under one HF repo) don't collide on disk.
    """
    base = _wd_tagger_cache() / _safe_name(profile.model_id)
    if profile.hf_subdir:
        base = base / profile.hf_subdir
    return base


# ============================================================
# Profile-driven helpers (Phase 2a, hardened in Phase 2 Task 6)
# ============================================================

def is_model_downloaded_for_profile(profile: TaggerProfile) -> bool:
    """Check if every required file in profile.files[] is present.

    Optional files (required=false) are ignored - their absence does
    not flip readiness to False.
    """
    model_dir = get_model_dir_for_profile(profile)
    return all(
        (model_dir / f.name).exists()
        for f in profile.files
        if f.required
    )


def get_model_status_for_profile(profile: TaggerProfile) -> dict:
    """Return download status for a profile, listing every file (required
    or optional) in profile.files[]."""
    model_dir = get_model_dir_for_profile(profile)
    files: dict[str, dict] = {}
    for f in profile.files:
        path = model_dir / f.name
        if path.exists():
            files[f.name] = {
                "exists": True,
                "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
                "required": f.required,
            }
        else:
            files[f.name] = {
                "exists": False,
                "size_mb": 0,
                "required": f.required,
            }
    return {
        "repo": profile.model_id,
        "ready": is_model_downloaded_for_profile(profile),
        "cache_dir": str(model_dir),
        "files": files,
    }


def _build_hf_url(model_id: str, hf_subdir: str | None, file_name: str) -> str:
    """Construct an HF resolve URL safely.

    Uses posixpath.join for relative path assembly and
    urllib.parse.quote(safe='/') to URL-escape path segments while
    keeping the '/' separator intact.
    """
    rel_path = (
        posixpath.join(hf_subdir, file_name) if hf_subdir else file_name
    )
    return (
        f"https://huggingface.co/{quote(model_id, safe='/')}"
        f"/resolve/main/{quote(rel_path, safe='/')}"
    )


def head_only(profile: TaggerProfile, file_spec, *, timeout: int = 30) -> dict:
    """HEAD a single HuggingFace profile file and return status/size."""
    url = _build_hf_url(profile.model_id, profile.hf_subdir, file_spec.name)
    try:
        resp = _hf_request("HEAD", url, timeout=timeout)
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "size": _content_length(exc.headers)}
    return {"status": resp.status, "size": _content_length(resp)}


def _download_one_file(
    profile: TaggerProfile,
    file_spec,
    *,
    timeout: int = 60,
    dest_dir: Path | None = None,
    max_bytes: int = _MAX_DOWNLOAD_BYTES,
    progress_callback=None,
) -> dict:
    """Download one profile file using atomic tmp -> replace."""
    base = dest_dir or get_model_dir_for_profile(profile)
    base.mkdir(parents=True, exist_ok=True)
    dest = base / file_spec.name
    if dest.exists():
        return {
            "name": file_spec.name,
            "status": "cached",
            "size": dest.stat().st_size,
        }

    url = _build_hf_url(profile.model_id, profile.hf_subdir, file_spec.name)
    tmp_dest = _temporary_download_path(base, file_spec.name)
    downloaded = 0
    try:
        with _hf_request("GET", url, timeout=timeout) as resp:
            total = _content_length(resp.headers) or 0
            if total > max_bytes:
                raise RuntimeError(f"{file_spec.name} exceeds max download size")
            with open(tmp_dest, "wb") as out:
                while True:
                    chunk = resp.read(1024 * 256)
                    if not chunk:
                        break
                    downloaded += len(chunk)
                    if downloaded > max_bytes:
                        raise RuntimeError(f"{file_spec.name} exceeds max download size")
                    out.write(chunk)
                    if progress_callback:
                        progress_callback(file_spec.name, downloaded, total)
                out.flush()
                os.fsync(out.fileno())
        os.replace(tmp_dest, dest)
        return {
            "name": file_spec.name,
            "status": "downloaded",
            "size": dest.stat().st_size,
        }
    except Exception:
        tmp_dest.unlink(missing_ok=True)
        raise


def download_model_for_profile(
    profile: TaggerProfile,
    progress_callback=None,
) -> DownloadResult:
    """Download every file in profile.files[] (required + optional) from HF.

    Spec § 7 contract:
      - hf_subdir applies to both URL and local cache path
      - per-profile in-process lock serializes concurrent calls
      - tmp file uses .{pid}.{seq}.tmp suffix and atomic os.replace
      - optional files: 404 → skip (info), 403/410 → warn (failed_optional),
        5xx / network / timeout → raise as RuntimeError
      - required files: any failure → raise as RuntimeError
    """
    base = get_model_dir_for_profile(profile)
    base.mkdir(parents=True, exist_ok=True)

    result = DownloadResult(profile_id=profile.id, cache_dir=base)

    with _get_profile_lock(profile.id):
        for pf in profile.files:
            dest = base / pf.name
            if dest.exists():
                logger.info("File already cached: %s", dest)
                result.downloaded.append(pf.name)
                continue

            url = _build_hf_url(profile.model_id, profile.hf_subdir, pf.name)
            logger.info("Downloading %s from %s", pf.name, url)

            try:
                _download_one_file(
                    profile,
                    pf,
                    timeout=120,
                    dest_dir=base,
                    progress_callback=progress_callback,
                )
                result.downloaded.append(pf.name)
                logger.info(
                    "Downloaded %s (%.1f MB)", pf.name,
                    dest.stat().st_size / (1024 * 1024),
                )
            except HTTPError as exc:
                if not pf.required:
                    if exc.code == 404:
                        logger.info(
                            "Optional file %s not available (404): %s",
                            pf.name, exc,
                        )
                        result.skipped_optional.append((pf.name, "404"))
                        continue
                    if exc.code in (403, 410):
                        logger.warning(
                            "Optional file %s denied (%d): %s",
                            pf.name, exc.code, exc,
                        )
                        result.failed_optional.append(
                            (pf.name, str(exc.code))
                        )
                        continue
                    # 5xx etc on optional file - fall through to raise
                raise RuntimeError(
                    f"Failed to download "
                    f"{'required ' if pf.required else ''}{pf.name} "
                    f"from {profile.model_id}: {exc}"
                ) from exc
            except Exception as exc:
                # Non-HTTPError (network, timeout, etc.) is always raised,
                # even for optional files (spec § 7).
                raise RuntimeError(
                    f"Failed to download "
                    f"{'required ' if pf.required else ''}{pf.name} "
                    f"from {profile.model_id}: {exc}"
                ) from exc

    return result


def is_model_downloaded(repo: str) -> bool:
    model_dir = get_model_dir(repo)
    return all((model_dir / file_name).exists() for file_name in _LEGACY_DEFAULT_FILES)


def get_model_status(repo: str) -> dict:
    model_dir = get_model_dir(repo)
    files: dict[str, dict] = {}
    for file_name in _LEGACY_DEFAULT_FILES:
        path = model_dir / file_name
        files[file_name] = (
            {"exists": True, "size_mb": round(path.stat().st_size / (1024 * 1024), 2)}
            if path.exists()
            else {"exists": False, "size_mb": 0}
        )
    return {
        "repo": repo,
        "ready": is_model_downloaded(repo),
        "cache_dir": str(model_dir),
        "files": files,
    }


def download_model(repo: str, progress_callback=None) -> Path:
    from .model_download_legacy import download_model as _download_model

    return _download_model(repo, progress_callback)


# Well-known model repos (legacy KNOWN_MODELS - preserved for any UI
# or admin code that iterates this dict; new code should use
# TaggerRegistry.list_profiles() instead).
KNOWN_MODELS = {
    "SmilingWolf/wd-swinv2-tagger-v3": "SwinV2 v3 (recommended)",
    "SmilingWolf/wd-vit-tagger-v3": "ViT v3",
    "SmilingWolf/wd-convnext-tagger-v3": "ConvNeXt v3",
    "SmilingWolf/wd-eva02-large-tagger-v3": "EVA02-Large v3",
    "Camais03/camie-tagger-v2": "Camie Tagger v2",
}
