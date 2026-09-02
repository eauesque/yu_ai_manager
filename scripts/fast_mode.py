#!/usr/bin/env python3
"""Decide whether this launch may use the Rust server, and prepare it.

This module is the *only* place that decides. The launchers (start.sh and
start.ps1) ask and obey; they do not judge. Two judges would mean one of them
eventually rots.

Every way of failing lands in the same answer: keep running Python. A corrupt
binary, a foreign architecture, a hang, a schema mismatch and a stale bundle
are not distinguished, because a per-kind branch is a branch that can rot in
only one kind.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# Running this file directly (python scripts/fast_mode.py -- the actual
# start.sh/start.ps1 invocation) puts this file's own directory on
# sys.path[0], not the repo root, so "scripts.X" absolute imports below
# (and the existing deferred ones in dist_is_fresh()/launch_argv()) would
# otherwise fail with ModuleNotFoundError. Only needed for direct execution;
# harmless and idempotent under pytest, where the repo root is already on
# sys.path.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.internal.fast_mode_env import (
    python_env_overrides,
    read_yu_host,
    skip_fast_mode_requested,
    skip_launch_args_file_requested,
)

_COMPAT_TIMEOUT_SECONDS = 10

# The public repository, not the private development one. Anonymous users
# cannot read releases from a private repo, so pointing this at the
# development repo made every download 404 and fast mode never fired
# (measured with `gh api repos/<owner>/yu_ai_manager --jq .private` -> true).
# The release workflow must publish here too -- see release-yu-server.yml.
_REPO_SLUG = "eauesque/yu_ai_manager"
_RELEASE_URL = f"https://github.com/{_REPO_SLUG}/releases/download"
_PUBKEY = "scripts/yu-server-pubkey.pub"

_TRIPLES = {
    ("Windows", "AMD64"): "x86_64-pc-windows-msvc",
    ("Windows", "x86_64"): "x86_64-pc-windows-msvc",
    ("Darwin", "arm64"): "aarch64-apple-darwin",
    ("Darwin", "x86_64"): "x86_64-apple-darwin",
    ("Linux", "x86_64"): "x86_64-unknown-linux-gnu",
    ("Linux", "aarch64"): "aarch64-unknown-linux-gnu",
}


@dataclass(frozen=True)
class Decision:
    use_fast_mode: bool
    reason: str
    # Would acquiring a binary change this answer? False when the refusal is
    # about the checkout rather than the binary -- an unlisted extension or a
    # stale web bundle rejects a perfectly good binary, and re-downloading it
    # cannot help. Without this, main() spawned an acquisition on every
    # refusal and acquire() re-fetched ~83MB on every launch, forever.
    needs_binary: bool = True


def expected_schema_version(repo: Path) -> int | None:
    """The Python schema version this checkout expects, read from the Rust constant."""
    source = repo / "crates" / "tagdb-core" / "src" / "lib.rs"
    try:
        text = source.read_text(encoding="utf-8")
    except OSError:
        return None
    marker = "pub const EXPECTED_PYTHON_SCHEMA_VERSION: i64 = "
    for line in text.splitlines():
        if line.strip().startswith(marker):
            return int(line.strip()[len(marker):].rstrip(";").strip())
    return None


def expected_ui_contract(repo: Path) -> str | None:
    path = repo / "ui" / "default" / "static" / "dist" / "dist_info.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("v")
    except (OSError, ValueError):
        return None


def dist_is_fresh(repo: Path) -> tuple[bool, str]:
    """Reuse the existing check rather than reimplementing staleness."""
    try:
        from scripts.check_dist_freshness import check
    except ImportError as exc:
        return False, f"dist check unavailable: {exc}"
    return check()


# clap's exit code for "I could not parse these arguments". Distinct from any
# other non-zero exit --compat-info can produce, all of which mean the binary
# itself is unusable rather than the arguments being wrong.
_CLAP_USAGE_EXIT = 2


def _read_compat_info(binary: Path) -> tuple[dict | None, str]:
    """Ask the binary whether it is usable -- and whether it accepts this launch.

    The child inherits this process's cwd, which is the repo root, so it reads
    the same launch-args.txt yu-server will read at the real launch and runs
    the same clap parser over it. That makes this probe the authority on which
    flags are supported: no second list of flag names to drift out of sync
    with Cli (main.rs). yu-server answers --compat-info immediately after
    Cli::parse_from(), before it opens the database or reads the config, so a
    rejected launch costs nothing here.

    A parse failure is reported with clap's own message. Without it the caller
    prints "--compat-info exited 2" and the operator is told only that fast
    mode was declined, never that a line in their launch-args.txt is the
    reason -- the Python launch that follows honors that line, so the symptom
    is a silent, unexplained demotion to the slower path.
    """
    if not binary.is_file():
        return None, f"binary not present: {binary}"
    try:
        result = subprocess.run(
            [str(binary), "--compat-info"],
            capture_output=True,
            text=True,
            timeout=_COMPAT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return None, "binary did not answer --compat-info in time"
    except OSError as exc:
        # Not executable, wrong architecture, missing loader -- all one answer.
        return None, f"binary will not run: {exc}"
    if result.returncode == _CLAP_USAGE_EXIT:
        # First line only: clap follows the error with a usage block.
        detail = next(
            (line.strip() for line in (result.stderr or "").splitlines() if line.strip()),
            "",
        )
        return None, (
            f"yu-server does not accept these launch arguments ({detail or 'no detail'}). "
            "Check launch-args.txt -- the Python launcher supports flags yu-server does not."
        )
    if result.returncode != 0:
        return None, f"--compat-info exited {result.returncode}"
    try:
        return json.loads(result.stdout.strip()), ""
    except ValueError:
        return None, "--compat-info did not print JSON"


def unlisted_extensions(repo: Path) -> list[str]:
    from scripts.internal.gen_bundled_extensions import load_bundled_names, scan

    listed = load_bundled_names(repo)
    if not listed:
        # No manifest means no basis for trust. Refuse rather than assume.
        return ["<manifest missing>"]
    return sorted(scan(repo) - listed)


def checkout_blockers(repo: Path) -> list[str]:
    """Reasons this checkout cannot use fast mode, whatever binary is present.

    Kept separate from decide() so the running server can ask the same
    question live. A recorded verdict is a snapshot of the last launch: when
    the bundle is rebuilt afterwards -- by the launcher, by web_ui.py's inline
    build, or by hand -- the snapshot names a staleness that no longer exists.
    """
    blockers = []
    unlisted = unlisted_extensions(repo)
    if unlisted:
        blockers.append(f"extensions outside the bundled roster: {', '.join(unlisted)}")
    fresh, why = dist_is_fresh(repo)
    if not fresh:
        blockers.append(f"web bundle is stale ({why})")
    return blockers


def decide(repo: Path, binary: Path) -> Decision:
    blockers = checkout_blockers(repo)
    if blockers:
        # Acquiring a binary cannot fix any of these, so needs_binary is False
        # and no download or build is even attempted.
        return Decision(False, blockers[0], needs_binary=False)

    info, error = _read_compat_info(binary)
    if info is None:
        return Decision(False, error)

    wanted_schema = expected_schema_version(repo)
    if wanted_schema is None or info.get("python_schema_version") != wanted_schema:
        return Decision(
            False,
            f"schema version mismatch: binary {info.get('python_schema_version')} "
            f"vs checkout {wanted_schema}",
        )

    wanted_ui = expected_ui_contract(repo)
    if wanted_ui is not None and info.get("ui_contract") != wanted_ui:
        return Decision(False, "ui contract mismatch")

    return Decision(True, f"build {info.get('build_commit', 'unknown')}")


def refresh_after_dist_rebuild(repo: Path, config_path: str | None = None) -> Decision:
    """Re-decide once the bundle has been rebuilt, and act on the new answer.

    web_ui.py rebuilds the bundle inline when node is available and then boots
    normally -- it never exits 75, so the launcher's dist-retry branch (which
    re-resolves) does not run. Without this, that launch keeps the verdict
    made against the stale bundle: nothing is acquired, and the settings
    screen reports a staleness that was fixed seconds earlier.

    This cannot switch the running process to Rust -- Python is already
    serving. What it does is record the truth and start acquiring, so the
    next launch has something to use.
    """
    decision = decide(repo, binary_path(repo))
    record_decision(repo, decision)
    if not decision.use_fast_mode and decision.needs_binary:
        _spawn_acquisition(repo, config_path)
    return decision


def target_triple() -> str | None:
    """The release artifact for this machine, or None when we publish none."""
    return _TRIPLES.get((platform.system(), platform.machine()))


def _download(url: str, target: Path) -> tuple[bool, str]:
    """Fetch `url` into `target`.

    `target.unlink(missing_ok=True)` clears any pre-existing object -- a
    leftover from a crashed prior run, or a symlink/hard link an attacker
    planted to redirect the write -- before opening. `O_EXCL` is the actual
    guard: measured by racing a hard link into the gap between the unlink and
    the open (with the unlink itself disabled to force the gap), the open
    fails rather than writing through the link. `O_NOFOLLOW` (absent on
    Windows, hence the getattr default) is redundant insurance on top of
    that -- it cannot see a hard link at all, and every symlink case it would
    catch is already refused by `O_EXCL`; measured by removing only
    `O_NOFOLLOW`, every test still passes. `os.fchmod(fd, 0o600)` is likewise
    redundant insurance, not the source of the guarantee: `O_CREAT | O_EXCL`
    always creates the file fresh, so its mode is already `0o600` masked by
    umask (never looser); measured with `umask 000` and `fchmod` removed, the
    mode is still 0o600.
    """
    try:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "yu-ai-manager-fast-mode"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read()
        target.unlink(missing_ok=True)
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | nofollow, 0o600)
        with os.fdopen(fd, "wb") as handle:
            os.fchmod(fd, 0o600)
            handle.write(data)
    except Exception as exc:  # noqa: BLE001 -- any failure is the same answer
        return False, f"download failed: {exc}"
    return True, ""


def verify_signature(binary: Path, signature: Path, pubkey: Path) -> tuple[bool, str]:
    """Verify with minisign. Absence of minisign is a refusal, not a bypass."""
    minisign = shutil.which("minisign")
    if minisign is None:
        return False, "minisign が無いため検証できない。高速モードを見送る"
    try:
        result = subprocess.run(
            [minisign, "-V", "-p", str(pubkey), "-x", str(signature), "-m", str(binary)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"minisign を実行できない: {exc}"
    if result.returncode != 0:
        return False, (
            "yu-server の署名検証に失敗した（供給網改竄の疑い）。\n"
            f"  {result.stderr.strip()}"
        )
    return True, "signature verified"


def _register_firewall_exception(dest: Path) -> bool:
    """Pre-authorise the binary that will now listen, on macOS.

    A stamp naming the old uv-managed Python (F32) would leave `--lan`
    silently blocked once yu-server replaces it as the listener.

    Called only from the interactive `--lan` launch path in `main()`, not
    from `fetch()`/`build()`: those run inside the detached `--acquire`
    child (no tty ever reaches it, so `sudo -n` there could never succeed
    and there is no retry path). At this call site a blocking `sudo` prompt
    is expected and acceptable -- it mirrors `runtime_runner.py`'s
    synchronous, foreground `ensure_lan_firewall_exception()` call for the
    Python launch path. `KeyboardInterrupt` is intentionally not caught
    here and propagates to the caller.

    Returns True when the exception is in place (or unnecessary off
    macOS); False when the caller should abort the fast-mode launch and
    let it fall back to the Python path.
    """
    if platform.system() != "Darwin":
        return True
    try:
        from core.system.macos_firewall import ensure_lan_firewall_exception

        return ensure_lan_firewall_exception(str(dest))
    except Exception as exc:  # noqa: BLE001 -- report, let caller decide
        print(f"[fast-mode] firewall registration failed: {exc}", file=sys.stderr)
        return False


def _latest_release_tag() -> str | None:
    """The tag GitHub's /releases/latest redirects to, or None.

    `VERSION` moves on every commit; tags are pushed only at a release. At
    the time this was written the checkout said 4.669.0 while the newest tag
    was v4.627.1 -- 42 versions apart -- so building the URL from VERSION
    alone gave a 404 on every launch. Downgrading to whatever was actually
    released is safe because nothing here decides to *run* the binary:
    decide() still checks the schema version and UI contract afterwards, and
    verify_signature() still gates the write.

    `_REPO_SLUG` names the public mirror `eauesque/yu_ai_manager`, so this
    call needs no token. It still returns None until that repository has a
    release carrying a yu-server binary, and the publishing step in
    `.github/workflows/release-yu-server.yml` needs `PUBLIC_RELEASE_TOKEN`
    (a PAT with `contents: write` there) to put one out. Until then fast mode
    simply does not fire, which is fail-safe: Python runs.
    """
    url = f"https://github.com/{_REPO_SLUG}/releases/latest"
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "yu-ai-manager-fast-mode"}
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            final = response.geturl()
    except Exception:  # noqa: BLE001 -- absence of an answer is just "no candidate"
        return None
    tag = final.rstrip("/").rsplit("/", 1)[-1]
    return tag if tag.startswith("v") else None


def fetch(repo: Path, version: str, dest: Path) -> tuple[bool, str]:
    """Download, verify, then make runnable -- in that order.

    `dest` is never touched until verification has passed: the download lands
    in a same-directory temp file (0600, no exec bit) so an in-flight or
    rejected payload can never occupy the path `decide()` will later execute,
    and a pre-existing trusted binary at `dest` is never overwritten with
    unverified content even transiently.

    Two tags are tried: this checkout's own version first, then whatever
    GitHub reports as the latest release. See `_latest_release_tag()` for why
    the second candidate exists and why falling back to it is safe.
    """
    triple = target_triple()
    if triple is None:
        return False, f"no published binary for {platform.system()}/{platform.machine()}"

    suffix = ".exe" if platform.system() == "Windows" else ""
    name = f"yu-server-{triple}{suffix}"

    candidates = [f"v{version}"]
    latest = _latest_release_tag()
    if latest is not None and latest not in candidates:
        candidates.append(latest)

    tmp = dest.with_name(dest.name + ".partial")
    signature = dest.with_name(dest.name + ".minisig")

    used_tag = None
    try:
        last = "no release tag to try"
        for tag in candidates:
            base = f"{_RELEASE_URL}/{tag}/{name}"
            ok, last = _download(base, tmp)
            if not ok:
                # No such release for this tag. This is the only failure that
                # advances to the next candidate: it means "nothing published
                # here", not "something is wrong with what was published".
                continue

            ok, last = _download(base + ".minisig", signature)
            if not ok:
                # The binary exists but its signature does not. Trying the
                # next tag here would be looking for a release that happens to
                # pass -- the same "keep going until something works" the
                # verification branch below refuses.
                return False, last

            ok, last = verify_signature(tmp, signature, repo / _PUBKEY)
            if not ok:
                return False, last

            # Only a verified payload may ever reach `dest`.
            os.replace(tmp, dest)
            used_tag = tag
            break
        else:
            return False, last
    finally:
        # The guarantee this function makes is that `dest` never holds
        # unverified bytes -- not that no trace of the attempt ever survives.
        # Cleanup of the staging files is best-effort: swallow any failure
        # here (e.g. the directory became unwritable mid-verification) so it
        # cannot override the `(bool, str)` this function already decided to
        # return, or escape as an exception the caller does not expect. A
        # leftover `.partial`/`.minisig` in that case is a disk-hygiene
        # concern, not a trust concern -- `decide()` only ever executes `dest`.
        for leftover in (tmp, signature):
            with suppress(OSError):
                leftover.unlink(missing_ok=True)

    if platform.system() == "Darwin":
        # Gatekeeper marks downloads; bootstrap_ffmpeg.sh does the same.
        subprocess.run(
            ["xattr", "-d", "com.apple.quarantine", str(dest)],
            capture_output=True,
            check=False,
        )
    dest.chmod(0o755)

    # yu-infer is a sidecar yu-server spawns at runtime, not something it
    # execs itself -- a missing/failed fetch here degrades Hailo-backed
    # features (see infer_manager::spawn_with_restart's retry+warn behavior)
    # but must not fail the yu-server fetch that already succeeded above.
    # Reuse `used_tag`: the same release, same triple, same signing key that
    # just verified for yu-server -- no need to re-walk the tag candidates.
    infer_name = f"yu-infer-{triple}{suffix}"
    infer_dest = dest.parent / _infer_binary_name()
    ok, msg = _fetch_asset(repo, used_tag, infer_name, infer_dest)
    if not ok:
        print(
            f"[fast-mode] yu-infer サイドカーの取得に失敗（Hailo系機能が劣化）: {msg}",
            file=sys.stderr,
        )

    return True, f"fetched and verified {name}"


def _fetch_asset(repo: Path, tag: str, asset_name: str, dest: Path) -> tuple[bool, str]:
    """Download, verify, then place one release asset at `dest`.

    The single-tag half of fetch()'s download+verify+replace logic, pulled
    out so the yu-infer sidecar can reuse it against a tag fetch() already
    confirmed has a matching yu-server build, instead of re-walking the
    version-then-latest candidate list.
    """
    base = f"{_RELEASE_URL}/{tag}/{asset_name}"
    tmp = dest.with_name(dest.name + ".partial")
    signature = dest.with_name(dest.name + ".minisig")
    try:
        ok, msg = _download(base, tmp)
        if not ok:
            return False, msg
        ok, msg = _download(base + ".minisig", signature)
        if not ok:
            return False, msg
        ok, msg = verify_signature(tmp, signature, repo / _PUBKEY)
        if not ok:
            return False, msg
        os.replace(tmp, dest)
    finally:
        for leftover in (tmp, signature):
            with suppress(OSError):
                leftover.unlink(missing_ok=True)

    if platform.system() == "Darwin":
        subprocess.run(
            ["xattr", "-d", "com.apple.quarantine", str(dest)],
            capture_output=True,
            check=False,
        )
    dest.chmod(0o755)
    return True, f"fetched and verified {asset_name}"


def available_memory_gb() -> float | None:
    """Free memory in GiB, or None when we cannot tell."""
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / (1024 * 1024)
    except OSError:
        pass
    try:
        import psutil  # noqa: PLC0415 -- optional

        return psutil.virtual_memory().available / (1024**3)
    except Exception:  # noqa: BLE001
        return None


def available_swap_gb() -> float | None:
    """Free swap in GiB, or None when we cannot tell.

    Acceptance criterion 12 asks the consent point to show measured memory
    *and swap*, and the setting's own text names swap exhaustion as the way
    this goes wrong on a small machine. Nothing in the repo measured it --
    the warning was prose with no number behind it.
    """
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("SwapFree:"):
                    return int(line.split()[1]) / (1024 * 1024)
    except OSError:
        pass
    try:
        import psutil  # noqa: PLC0415 -- optional

        return psutil.swap_memory().free / (1024**3)
    except Exception:  # noqa: BLE001
        return None


ACQUIRE_SOURCES = ("download", "build", "auto")


def effective_config_path(passthrough: list[str]) -> str | None:
    """The config file this launch's server will actually use.

    The acquisition child has no argv of its own, so without this the setting
    would be read from a different file than the one the settings screen
    writes whenever --config is in play.
    """
    from core.web.startup_args import build_webui_parser, resolve_config_path

    try:
        merged, _unknown = build_webui_parser().parse_known_args(
            _read_launch_args_file(Path.cwd()) + passthrough
        )
    except SystemExit:
        return None
    return resolve_config_path(merged.config)


def acquire_source(repo: Path, config_path: str | None = None) -> str:
    """How this machine is allowed to obtain the Rust server.

    "download" (the default) never compiles; "build" never downloads; "auto"
    downloads and falls back to compiling. A failure to read means "download":
    the expensive path must never be reached by accident.

    Read with `load_config_json` -- the function the settings API writes
    through (`save_config_json`) -- and never with `load_config`, which
    returns DEFAULT_CONFIG plus env overrides and *reads no file at all* when
    given None. Reading the setting with the latter is why picking "auto" had
    no effect: every launch saw the default.

    `fast_mode_build: true` is the setting this replaced. It meant "download,
    and build if that fails", which is exactly "auto" -- so an existing opt-in
    keeps working without the user touching anything.
    """
    try:
        from core.configuration.json_rw import load_config_json

        config = load_config_json(config_path)
        if not isinstance(config, dict):
            return "download"
        value = config.get("fast_mode_source")
        if isinstance(value, str) and value in ACQUIRE_SOURCES:
            return value
        if value is None and bool(config.get("fast_mode_build", False)):
            return "auto"
    except Exception:  # noqa: BLE001 -- a settings failure means "do not build"
        return "download"
    return "download"


def build_opt_in(repo: Path, config_path: str | None = None) -> bool:
    """Whether compiling on this machine is permitted at all."""
    return acquire_source(repo, config_path) in {"build", "auto"}


_STALE_SOURCE_PATTERNS = (".rs", ".sql", ".json")
_STALE_SOURCE_FILENAMES = ("Cargo.toml", "Cargo.lock")
_STALE_PRUNE_DIRS = ("target", ".git")


def _is_stale_source_candidate(name: str) -> bool:
    if name in _STALE_SOURCE_FILENAMES:
        return True
    return any(name.endswith(suffix) for suffix in _STALE_SOURCE_PATTERNS)


def _stale_local_sources(repo: Path, binary: Path) -> tuple[int, list[Path], int | None]:
    """Which files under crates/ are newer than the binary, and by how much.

    Root is crates/ (not the repo root) to match cargo's own
    --manifest-path. target/ and .git are pruned *before* os.walk descends
    into them -- a release build's target/ is tens of thousands of files,
    and rglob()-then-filter (check_genesis_acceptance.py's approach) pays
    that cost on every launch. No early exit: an early cutoff at N files
    would let the "max mtime of the scanned set" retry-gate permanently
    miss edits to files beyond that cutoff (rev2-M1, reverted in rev3).
    """
    try:
        binary_mtime_ns = binary.stat().st_mtime_ns
    except OSError:
        return 0, [], None

    crates = repo / "crates"
    count = 0
    display_paths: list[Path] = []
    max_mtime_ns: int | None = None

    for dirpath, dirnames, filenames in os.walk(crates):
        dirnames[:] = [d for d in dirnames if d not in _STALE_PRUNE_DIRS]
        for name in filenames:
            if not _is_stale_source_candidate(name):
                continue
            path = Path(dirpath) / name
            try:
                mtime_ns = path.stat().st_mtime_ns
            except OSError:
                continue
            if mtime_ns <= binary_mtime_ns:
                continue
            count += 1
            if len(display_paths) < 5:
                display_paths.append(path)
            if max_mtime_ns is None or mtime_ns > max_mtime_ns:
                max_mtime_ns = mtime_ns

    return count, display_paths, max_mtime_ns

_BUILD_STATE_NAME = ".fast-mode-build-state.json"
_BUILD_LOG_NAME = "fast-mode-build.log"
_MAX_BUILD_FAILURES = 3

# Above this, the machine is busy and cargo should get out of the way.
_BUSY_CPU_PERCENT = 60.0
_IDLE_SAMPLE_SECONDS = 5.0


def _build_state_path(repo: Path) -> Path:
    return repo / "bin" / _BUILD_STATE_NAME


def build_log_path(repo: Path) -> Path:
    return repo / "bin" / _BUILD_LOG_NAME


def read_build_state(repo: Path) -> dict:
    try:
        data = json.loads(_build_state_path(repo).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def consecutive_build_failures(repo: Path) -> int:
    try:
        return int(read_build_state(repo)["failures"])
    except (KeyError, TypeError, ValueError):
        return 0


def _write_build_state(repo: Path, **fields: object) -> None:
    """Merge fields into the state file, keeping what other writers put there.

    A whole-file overwrite would drop `failures` every time the phase is
    recorded, and the failure counter is what stops a hopeless machine.
    """
    state = read_build_state(repo)
    state.update(fields)
    path = _build_state_path(repo)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
    except OSError:
        # Losing the counter costs a retry, never correctness.
        pass


_STALE_STATE_NAME = ".fast-mode-stale-state.json"
_STALE_LOG_NAME = "fast-mode-stale-build.log"
_STALE_UTIME_FAIL_CAP = 3  # matches _MAX_BUILD_FAILURES — see spec S2


def _stale_state_path(repo: Path) -> Path:
    return repo / "bin" / _STALE_STATE_NAME


def _stale_log_path(repo: Path) -> Path:
    return repo / "bin" / _STALE_LOG_NAME


def read_stale_state(repo: Path) -> dict:
    try:
        data = json.loads(_stale_state_path(repo).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_stale_state_locked(repo: Path, **fields: object) -> None:
    """Overwrite the stale state file with `fields`, atomically.

    Caller must already hold the lock (_try_acquire_lock()). Unlike
    _write_build_state()'s merge-only read-modify-write, a field set to
    None here is *removed* from the written file -- this is how "erase
    stale_pending_artifact" is expressed without a separate delete
    primitive. Fields not mentioned in `fields` are preserved from the
    current file (partial-update semantics), matching the "merge, but with
    working deletion" behavior the spec calls for.
    """
    state = read_stale_state(repo)
    for key, value in fields.items():
        if value is None:
            state.pop(key, None)
        else:
            state[key] = value
    path = _stale_state_path(repo)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        # A lock-free reader would rather see "no record" than a partial
        # write; losing this update costs a retry, never correctness.
        pass


def _delete_stale_state(repo: Path) -> None:
    """Whole-file delete, used on successful promotion (see Task 5)."""
    with suppress(OSError):
        _stale_state_path(repo).unlink(missing_ok=True)


def _should_retry_stale_build(repo: Path, max_mtime_ns: int) -> bool:
    """True unless a previous attempt already targeted this max_mtime_ns or newer."""
    recorded = read_stale_state(repo).get("stale_attempted_max_mtime")
    if not isinstance(recorded, int):
        return True
    return max_mtime_ns > recorded


def _spawn_stale_rebuild(
    repo: Path, config_path: str | None, max_mtime_ns: int, count: int
) -> None:
    """Lock, then detached `--acquire-stale` child. Silent on contention,
    matching _spawn_acquisition()'s existing silent-on-contention behavior.

    max_mtime_ns is passed as an argv int, never recomputed by the child --
    a time-of-check/time-of-use gap here would let the recorded value drift
    from what actually triggered this build.
    """
    lock = _try_acquire_lock(repo)
    if lock is None:
        return
    try:
        log = _stale_log_path(repo)
        try:
            handle = open(log, "a", encoding="utf-8")  # noqa: SIM115 -- owned by the child
        except OSError:
            handle = None
        argv = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--acquire-stale",
            "--stale-max-mtime",
            str(int(max_mtime_ns)),
        ]
        if config_path:
            argv += ["--config", config_path]
        subprocess.Popen(
            argv,
            cwd=str(repo),
            stdout=handle or subprocess.DEVNULL,
            stderr=subprocess.STDOUT if handle else subprocess.DEVNULL,
            start_new_session=True,
        )
        if handle is not None:
            handle.close()
        print(
            f"[fast-mode] {count} 個のソースがバイナリより新しい。背景で"
            "再ビルドします(反映は次回起動から。今回はこのまま既存バイナリで"
            "起動を続けます)",
            file=sys.stderr,
        )
    except OSError:
        lock.unlink(missing_ok=True)


def _tail_text(path: Path, limit: int) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-limit:]
    except OSError:
        return ""


def _record_build_result(repo: Path, ok: bool, message: str) -> None:
    """Count consecutive failures so a hopeless machine stops burning CPU.

    Success resets to zero rather than decrementing: one good build means the
    reason for the previous failures is gone.
    """
    _write_build_state(
        repo,
        failures=0 if ok else consecutive_build_failures(repo) + 1,
        last=message[:500],
        phase="ok" if ok else "failed",
        finished_at=time.time(),
    )


def _run_cargo(repo: Path, jobs: str) -> tuple[bool, str]:
    """Compile yu-server, yielding the machine whenever the user needs it.

    cargo is suspended while CPU load is high and resumed when it drops, so a
    build started in the background does not compete with what the user is
    actually doing. psutil is what makes this portable -- Popen.suspend() maps
    to SIGSTOP on POSIX and to the debug-suspend API on Windows, where SIGSTOP
    does not exist. Without psutil there is no way to *measure* load here, so
    rather than pretend, the build simply runs at low priority.
    """
    from scripts.internal.rust_toolchain import build_env, ensure_cargo

    cargo, how = ensure_cargo(repo)
    if cargo is None:
        return False, how
    print(f"[fast-mode] cargo: {how}", file=sys.stderr)

    argv = [
        str(cargo),
        "build",
        "--release",
        "--jobs",
        jobs,
        "-p",
        "yu-server",
        "-p",
        "yu-infer-shim",
        "--manifest-path",
        str(repo / "crates" / "Cargo.toml"),
    ]
    # cargo's output goes straight to a file, never to a pipe. _gate_on_idle()
    # below waits for the process without reading its output, so a pipe would
    # fill (64KiB on Linux, less on Windows), block cargo on its next write and
    # hang the build forever -- a release build of yu-server emits far more
    # than that in "Compiling ..." lines alone. The file doubles as the
    # progress the user can watch while it runs.
    log_path = build_log_path(repo)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(log_path, "w", encoding="utf-8")  # noqa: SIM115 -- closed below
    except OSError as exc:
        return False, f"ビルドログを開けない: {exc}"
    try:
        proc = subprocess.Popen(
            argv,
            env=build_env(repo),
            stdout=handle,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        return False, f"cargo を実行できない: {exc}"
    finally:
        # The child holds its own duplicate of the descriptor.
        handle.close()

    _lower_priority(proc.pid)
    _gate_on_idle(proc)

    proc.wait()
    if proc.returncode != 0:
        return False, _tail_text(log_path, 2000)
    return True, ""


def _lower_priority(pid: int) -> None:
    """Best-effort: never let this be the reason a build does not happen."""
    with suppress(Exception):
        import psutil  # noqa: PLC0415 -- optional

        handle = psutil.Process(pid)
        if platform.system() == "Windows":
            handle.nice(psutil.IDLE_PRIORITY_CLASS)
        else:
            handle.nice(19)
        with suppress(Exception):
            handle.ionice(psutil.IOPRIO_CLASS_IDLE)
        return
    with suppress(Exception):
        os.nice(19)


def _gate_on_idle(proc: subprocess.Popen) -> None:
    """Suspend cargo while the machine is busy; resume when it is not.

    Returns as soon as the process exits. When psutil is missing this returns
    immediately -- the caller has already lowered the priority, which is the
    honest fallback: it does not claim to be measuring idleness.
    """
    try:
        import psutil  # noqa: PLC0415 -- optional
    except Exception:  # noqa: BLE001
        return

    try:
        handle = psutil.Process(proc.pid)
    except Exception:  # noqa: BLE001
        return

    suspended = False
    while proc.poll() is None:
        try:
            # Whole-machine load, sampled over a window; cargo's own use is
            # included, which is why the process is suspended before the next
            # reading is taken.
            load = psutil.cpu_percent(interval=_IDLE_SAMPLE_SECONDS)
            if load >= _BUSY_CPU_PERCENT and not suspended:
                handle.suspend()
                suspended = True
            elif load < _BUSY_CPU_PERCENT and suspended:
                handle.resume()
                suspended = False
        except Exception:  # noqa: BLE001 -- the process died, or we lost access
            break

    # Never leave a suspended process behind: a stopped cargo holding the
    # target/ lock would block every later build with no way to notice.
    if suspended:
        with suppress(Exception):
            handle.resume()


def build(repo: Path, dest: Path, config_path: str | None = None, mode: Literal["acquire", "stale"] = "acquire") -> tuple[bool, str]:
    if not build_opt_in(repo, config_path):
        return False, (
            "取得方法の設定がビルドを許していない"
            f"（現在: {acquire_source(repo, config_path)}）"
        )

    failures = consecutive_build_failures(repo)
    if failures >= _MAX_BUILD_FAILURES:
        return False, (
            f"ビルドが {failures} 回続けて失敗したため、この端末では試みない。"
            f"理由は {_build_state_path(repo)} と bin/fast-mode-acquire.log に在る。"
            "設定を入れ直すか当該ファイルを消せば再開する"
        )

    memory = available_memory_gb()
    swap = available_swap_gb()
    # The consent point (acceptance 12): the setting's text carries the
    # warning, but a warning without a number is not something a user can
    # weigh. Print what was actually measured on this machine, at the moment
    # the expensive thing starts. Goes to stderr, which the acquisition child
    # now keeps in bin/fast-mode-acquire.log.
    print(
        "[fast-mode] Rust をこの端末でビルドします（設定で有効化済み）。"
        f"空きメモリ {memory:.1f}GB / 空きスワップ {swap:.1f}GB"
        if memory is not None and swap is not None
        else "[fast-mode] Rust をこの端末でビルドします（設定で有効化済み）。"
        f"空きメモリ {memory if memory is not None else '不明'} / "
        f"空きスワップ {swap if swap is not None else '不明'}",
        file=sys.stderr,
    )
    print(
        "[fast-mode] コンパイル中も全機能を利用できます。メモリが少ない環境では"
        "スワップを使い尽くしシステムごと落ちることがあります。",
        file=sys.stderr,
    )
    # cargo takes 1-2GB per job here. One job is the floor, never zero.
    jobs = "1" if memory is not None and memory < 4.0 else "2"

    # mode="stale" writes nothing to the shared build-state file --
    # that file is mode="acquire"'s alone. Its own state (stale_phase
    # etc.) is recorded separately by the --acquire-stale handler in
    # bin/.fast-mode-stale-state.json.
    if mode == "acquire":
        _write_build_state(repo, phase="building", started_at=time.time(), last="")

    ok, message = _run_cargo(repo, jobs)
    if not ok:
        if mode == "acquire":
            _record_build_result(repo, False, message)
        return False, f"cargo build に失敗した: {message}"

    built = repo / "crates" / "target" / "release" / dest.name
    if not built.exists():
        if mode == "acquire":
            _record_build_result(repo, False, f"artifact missing: {built}")
        return False, f"ビルドは成功したが成果物が無い: {built}"

    if mode == "stale":
        # Promotion (rename-based, exec-safe) happens on the *next* launch's
        # main(), not here -- see _promote_stale_build(). The artifact stays
        # in crates/target/release/ for that logic to find.
        return True, f"built locally ({jobs} job(s), {memory or '?'}GB free)"

    if mode == "acquire":
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(built, dest)
            dest.chmod(0o755)
        except OSError as exc:
            _record_build_result(repo, False, f"copy failed: {exc}")
            return False, f"ビルド成果物のコピーに失敗した: {exc}"
        _record_build_result(repo, True, "ok")

        # yu-infer is a sidecar yu-server spawns at runtime, not something it
        # execs itself -- a missing/failed copy here degrades Hailo-backed
        # features (see infer_manager::spawn_with_restart's retry+warn
        # behavior) but must not fail the yu-server acquisition itself.
        built_infer = repo / "crates" / "target" / "release" / _infer_binary_name()
        infer_dest = dest.parent / _infer_binary_name()
        try:
            shutil.copy2(built_infer, infer_dest)
            infer_dest.chmod(0o755)
        except OSError as exc:
            print(
                f"[fast-mode] yu-infer サイドカーのコピーに失敗（Hailo系機能が劣化）: {exc}",
                file=sys.stderr,
            )
    return True, f"built locally ({jobs} job(s), {memory or '?'}GB free)"


def _specified_flags(tokens: list[str]) -> frozenset[str]:
    """The `--flag` names a token list sets, in either `--x v` or `--x=v` form."""
    flags = set()
    for token in tokens:
        if token.startswith("--"):
            flags.add(token.split("=", 1)[0])
    return frozenset(flags)


def launch_argv(repo: Path, binary: Path, passthrough: list[str]) -> list[str]:
    """Arguments for starting yu-server, matching what Tauri passes.

    `launch-args.txt` is deliberately absent here: yu-server reads it itself,
    with the same precedence Python uses (main.rs:691,733). It is still read
    *for inspection* below, so a --db/--config/--profile written there counts
    as already specified and the env translation leaves it alone.
    """
    # web_ui.py's TAGDB_DB/TAGDB_CONFIG/TAGDB_PROFILE have no effect on
    # yu-server, which reads YU_*. Untranslated, a fast-mode launch quietly
    # serves a different database than the Python launch it replaced.
    already = _specified_flags(passthrough + _read_launch_args_file(repo))
    overrides = python_env_overrides(already)

    return [str(binary), "--standalone", *overrides, *passthrough]


_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_LAUNCH_ARGS_FILENAME = "launch-args.txt"
_ENV_DB_KEY_PREFIX = "__YU_FAST_ENV_DB_KEY__="


def _read_launch_args_file(repo: Path) -> list[str]:
    """Replicate yu-server's own launch-args.txt parsing.

    Mirrors main.rs's load_launch_args_file: blank lines and '#' comments
    skipped, remaining lines whitespace-split into argv tokens, and
    YU_SKIP_LAUNCH_ARGS_FILE=1 skips the file entirely (used by test
    harnesses, same as on the Rust side). Copied rather than shared because
    that parser lives in the Rust binary this script is deciding whether to
    launch -- test_fast_mode_cli.py asserts the filename/comment-marker
    literals below still match main.rs's, so this drifting out of sync with
    the source it was copied from fails a test instead of silently missing
    a --lan/--host in the file.
    """
    if skip_launch_args_file_requested():
        return []
    path = repo / _LAUNCH_ARGS_FILENAME
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    tokens: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tokens.extend(line.split())
    return tokens


def _read_raw_server_cfg(cfg_path: str | None) -> dict:
    """The config file's "server" table exactly as written, no defaults.

    core.configuration.api.load_config() merges DEFAULT_CONFIG into the
    parsed file, so its server.host is "127.0.0.1" even for a file that
    never mentions a host (and even when there is no file at all). Rust's
    own load_config does no such backfill, so a predicate that must decide
    "did the config file itself pin the host?" has to read the file raw.
    Any unreadable/unparseable/non-object file yields {}: yu-server treats
    a config it cannot parse as absent too.
    """
    if not cfg_path:
        return {}
    try:
        raw = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    server = raw.get("server") if isinstance(raw, dict) else None
    return server if isinstance(server, dict) else {}


def _will_bind_non_loopback(repo: Path, passthrough: list[str]) -> bool:
    """Will this launch's listener bind to something other than loopback?

    Every item in both lists below was measured against this function, not
    inferred from reading it. Do not add or move an item without running it.

    Covers the paths that can push yu-server off 127.0.0.1 that this
    predicate actually accounts for, so the macOS firewall exception (D14)
    is registered whenever it will be needed for one of them:
      - --lan / --host on the passthrough argv
      - --lan / --host inside launch-args.txt (lower priority than real
        argv and than a host the config file itself pins, matching main.rs's
        merge -- see the precedence comment below)
      - config.json / tagdb_config.json's "server".{lan,host}
      - YU_HOST (yu-server's clap `env = "YU_HOST"` binding), consulted
        only when nothing above already pinned the host explicitly
      - TAGDB_HOST / TAGDB_LAN, with or without a config file present:
        load_config() runs apply_env_overrides() over DEFAULT_CONFIG even
        when no file is found, so these land in server_cfg either way and
        resolve_server_bind_host() sees them

    Does NOT cover (Rust-only sources this path never reads, and not
    addressed here per Round 3's ruling -- Python never bound these hosts
    either, so this is not a regression, just an unaddressed pre-existing
    gap; a user relying on one of these needs the macOS firewall exception
    registered by hand):
      - config.toml's "server".{lan,host} (Rust prefers config.toml over
        config.json; resolve_config_path here never looks for config.toml)
      - YU_HOST / TAGDB_HOST / TAGDB_LAN set via a .env file rather than
        the process environment (main.rs's load_dotenv_files loads .env
        before evaluating them; nothing on this path reads .env)

    Delegates the host decision to core.web.startup_args.resolve_server_bind_host
    -- the same host-only logic core/web/runtime_runner.py's PIN-aware
    resolve_server_bind_and_pin wraps -- instead of re-implementing it, so
    the two can never diverge on how --host/--lan/config.json combine.
    Deliberately not resolve_server_bind_and_pin: that function also
    decrypts config.json's PIN via secret_store.decrypt(), which requires
    core.paths.init_app_paths() to have already run. This predicate runs
    from main() before any such initialization, so calling the PIN-aware
    function here would crash on a real config.json enc: PIN (see
    test_predicate_does_not_crash_on_an_encrypted_pin_before_init_app_paths).
    """
    from core.configuration.api import load_config
    from core.web.startup_args import (
        build_webui_parser,
        resolve_config_path,
        resolve_server_bind_host,
    )

    file_args = _read_launch_args_file(repo)
    parser = build_webui_parser()
    # file_args first, passthrough second: matches main.rs's Cli::parse_from
    # merge order, so a flag present on both sides resolves to the real-argv
    # value (last occurrence wins for a plain store option in both argparse
    # and clap).
    try:
        merged, _unknown = parser.parse_known_args(file_args + passthrough)
    except SystemExit:
        # A malformed passthrough arg (--port abc, --lan=1) makes argparse
        # print to stderr and exit(2) instead of raising -- and Rust's own
        # clap parser will refuse the same input identically, so this
        # launch cannot proceed unverified either way. Fail safe rather
        # than let the SystemExit escape uncaught: assume a firewall
        # exception may be needed, since we cannot determine the real host
        # from unparseable input, and a spurious sudo prompt is a smaller
        # cost than a silently-missing firewall rule.
        return True

    cfg_path = resolve_config_path(merged.config)
    server_cfg = load_config(cfg_path).get("server", {})
    file_server_cfg = _read_raw_server_cfg(cfg_path)

    # main.rs's effective_host keys off argv_flag(&merged_args, "--host"),
    # which scans the launch-args.txt-merged token list -- the same list
    # `merged` holds here -- so a --host written anywhere in that list
    # outranks the config file, exactly as Python's
    # parse_args(file_args + sys.argv[1:]) does. Two tiers, not three: the
    # earlier third tier existed because Rust scanned only real argv and so
    # let config.json override a file-only --host. That divergence is fixed
    # (main.rs argv_flag now takes the merged list); mirroring it here would
    # re-introduce it on this side.
    #
    # Below both: clap's env="YU_HOST" binding, which only fires when the
    # merged token list never set --host at all. It is gated on
    # file_server_cfg -- the host as literally written in the config file --
    # and not on load_config()'s result: load_config() backfills
    # DEFAULT_CONFIG's server.host = "127.0.0.1" when the file has no
    # top-level "server" key (and when there is no config file at all), while
    # leaving it absent when "server" exists but has no "host". Keying off
    # load_config()'s host would therefore claim "the config file pinned the
    # host" for a file like {"scan_roots": []} and discard YU_HOST. Rust's
    # load_config returns the raw parsed file with no such defaults, so the
    # raw read is what matches it.
    host_arg = merged.host
    if host_arg is None and not file_server_cfg.get("host"):
        env_host = read_yu_host()
        if env_host:
            host_arg = env_host

    candidate = argparse.Namespace(host=host_arg, lan=merged.lan)
    effective_host = resolve_server_bind_host(candidate, server_cfg)
    return effective_host not in _LOOPBACK_HOSTS


def binary_path(repo: Path) -> Path:
    name = "yu-server.exe" if platform.system() == "Windows" else "yu-server"
    return repo / "bin" / name


def _infer_binary_name() -> str:
    """Sibling sidecar binary yu-server spawns via current_exe().parent() --
    see crates/yu-server/src/main.rs (yu_infer_binary) and
    crates/yu-infer/Cargo.toml ([[bin]] name = "yu-infer")."""
    return "yu-infer.exe" if platform.system() == "Windows" else "yu-infer"


def _read_version(repo: Path) -> str:
    return (repo / "VERSION").read_text(encoding="utf-8").strip()


_LOCK_NAME = ".fast-mode-acquire.lock"

# A download or a local build finishing in under an hour is the expected
# case; anything still holding the lock past this is not an acquisition in
# flight, it is one that died without cleaning up (SIGKILL, a power loss, an
# interpreter that failed to start) and would otherwise block every future
# launch's acquisition forever.
_STALE_LOCK_SECONDS = 3600


def acquire_lock_path(repo: Path) -> Path:
    """The lock's presence is what tells a live acquisition from a dead one."""
    return repo / "bin" / _LOCK_NAME


def _try_acquire_lock(repo: Path) -> Path | None:
    """Create-only lock acquisition: O_CREAT|O_EXCL, never reclaims.

    Shared by every writer of the (existing and new) lock file: the
    existing acquisition path's own create step (via _spawn_acquisition()
    below), the stale-rebuild spawn, and the next-launch promotion logic.
    Reclaiming an abandoned lock stays exclusive to the existing
    --acquire/acquire() path -- _gate_on_idle() can suspend cargo for an
    unbounded time under high host load, so a plain launch that never
    touches the lock must not be the one that decides a long hold is dead.
    """
    lock = acquire_lock_path(repo)
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        os.close(fd)
        return lock
    except (FileExistsError, OSError):
        return None


_DECISION_NAME = ".fast-mode-decision.json"


def decision_path(repo: Path) -> Path:
    return repo / "bin" / _DECISION_NAME


def record_decision(repo: Path, decision: Decision) -> None:
    """Leave the verdict where the running server can read it.

    main() already prints the reason, but a launcher's stderr is not something
    anyone reads -- and when the refusal is about the checkout rather than the
    binary (needs_binary False) *nothing else is written at all*: no download,
    no build, no log. That combination is what makes fast mode look broken --
    the user turns the setting on and no file ever appears. The verdict has to
    outlive the launch to be answerable later.
    """
    try:
        path = decision_path(repo)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "use_fast_mode": decision.use_fast_mode,
                    "reason": decision.reason,
                    "needs_binary": decision.needs_binary,
                    "at": time.time(),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except OSError:
        # Losing the note costs an explanation, never correctness.
        pass


def _spawn_acquisition(repo: Path, config_path: str | None = None) -> None:
    """Start acquiring in the background and return immediately.

    The first launch must not wait for a download or a build (acceptance 2).
    A lock file keeps repeated launches from stacking up acquisitions.
    Creation is exclusive (O_CREAT|O_EXCL) rather than exists()-then-touch(),
    closing the TOCTOU window between the two. A lock older than
    _STALE_LOCK_SECONDS is treated as abandoned and removed before the
    exclusive create is attempted: the acquiring process clears it in its
    own `finally` (see acquire()), but a process that dies before reaching
    that `finally` (SIGKILL, a power loss, an interpreter that failed to
    start) leaves it behind forever -- without this staleness check, that
    would cost every subsequent launch its acquisition, not just the one
    that happened to find it. With this in place a stale lock costs at most
    one _STALE_LOCK_SECONDS window of skipped attempts, never a permanent
    one.
    """
    lock = acquire_lock_path(repo)
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
        try:
            if time.time() - lock.stat().st_mtime > _STALE_LOCK_SECONDS:
                lock.unlink(missing_ok=True)
        except FileNotFoundError:
            pass
        if _try_acquire_lock(repo) is None:
            return
        # The child's diagnostics are the only account of what happened:
        # the tamper accusation (acceptance criterion 3), a 404 for a version
        # that was never released, a build failure. DEVNULL here discarded
        # all three, so every acquisition failure looked identical to
        # success-with-nothing-to-do. Keep them in a file the user and the
        # next launch can read.
        log = repo / "bin" / "fast-mode-acquire.log"
        try:
            handle = open(log, "a", encoding="utf-8")  # noqa: SIM115 -- owned by the child
        except OSError:
            handle = None
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--acquire"]
            # The child has no argv of its own, so the config path has to be
            # handed to it: without this it would read the setting from a
            # different file than the settings screen writes.
            + (["--config", config_path] if config_path else []),
            cwd=str(repo),
            stdout=handle or subprocess.DEVNULL,
            stderr=subprocess.STDOUT if handle else subprocess.DEVNULL,
            start_new_session=True,
        )
        if handle is not None:
            handle.close()
    except OSError:
        lock.unlink(missing_ok=True)


def acquire(repo: Path, config_path: str | None = None) -> int:
    """Obtain the Rust server the way the setting says to.

    Runs detached. Nothing here decides whether fast mode is used -- that
    stays in decide(), and the next launch asks it again.

    fetch()/build() are called under a broad except: Task 4 established that
    fetch() lets verify_signature/os.replace failures escape as exceptions
    rather than folding them into its (bool, str) return. This is background
    work triggered from main() -- a traceback here must never reach the
    caller of --resolve or the foreground launch; the worst case is simply
    that no binary was acquired this time, which the next launch's decide()
    will notice and retry from.
    """
    lock = acquire_lock_path(repo)
    try:
        dest = binary_path(repo)
        source = acquire_source(repo, config_path)
        print(f"[fast-mode] 取得方法の設定: {source}", file=sys.stderr)

        # "build" skips the download outright rather than treating a local
        # build as a fallback: someone who picked it wants their own binary,
        # not the published one, and a successful download would return
        # before the build ever ran.
        if source != "build":
            try:
                if target_triple() is not None:
                    ok, message = fetch(repo, _read_version(repo), dest)
                    if ok:
                        print(message, file=sys.stderr)
                        return 0
                    print(f"[fast-mode] {message}", file=sys.stderr)
                else:
                    print(
                        "[fast-mode] この環境向けの配布バイナリはありません",
                        file=sys.stderr,
                    )
            except Exception as exc:  # noqa: BLE001 -- background acquisition must not raise
                print(f"[fast-mode] fetch failed unexpectedly: {exc}", file=sys.stderr)

        if source == "download":
            # Say why nothing else happens. Silence here is what made the
            # feature look broken: the user turned something on and no file
            # ever appeared.
            print(
                "[fast-mode] 設定「配布バイナリのみ」により、この端末ではビルドしません",
                file=sys.stderr,
            )
            return 1

        try:
            ok, message = build(repo, dest, config_path)
        except Exception as exc:  # noqa: BLE001 -- background acquisition must not raise
            print(f"[fast-mode] build failed unexpectedly: {exc}", file=sys.stderr)
            return 1
        print(f"[fast-mode] {message}", file=sys.stderr)
        return 0 if ok else 1
    finally:
        lock.unlink(missing_ok=True)


def _handle_acquire_stale(repo: Path, argv: list[str]) -> int:
    """--acquire-stale handler: build(mode="stale"), then record state.

    Runs detached (spawned by _spawn_stale_rebuild()). Never touches the
    shared build-state file or its failure counter -- a broken crates/
    edit is normal mid-development and must not burn through
    _MAX_BUILD_FAILURES meant for "binary missing" acquisitions.
    """
    lock = acquire_lock_path(repo)
    try:
        try:
            index = argv.index("--stale-max-mtime") + 1
            max_mtime_ns = int(argv[index])
        except (ValueError, IndexError):
            print("[fast-mode] --stale-max-mtime が不正", file=sys.stderr)
            return 2

        cfg = None
        if "--config" in argv:
            cfg_index = argv.index("--config") + 1
            if cfg_index < len(argv):
                cfg = argv[cfg_index]

        if consecutive_build_failures(repo) >= _MAX_BUILD_FAILURES:
            _write_stale_state_locked(
                repo,
                stale_phase="failed",
                stale_last=(
                    "shared build failure breaker is open — see "
                    f"{_build_state_path(repo).relative_to(repo)}"
                )[:200],
                stale_finished_at=time.time(),
                stale_attempted_max_mtime=max_mtime_ns,
            )
            return 1

        _write_stale_state_locked(
            repo,
            stale_phase="building",
            stale_started_at=time.time(),
            stale_attempted_max_mtime=max_mtime_ns,
        )

        dest = binary_path(repo)
        ok, message = build(repo, dest, cfg, mode="stale")

        log = _stale_log_path(repo)
        try:
            with open(log, "a", encoding="utf-8") as handle:
                handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
        except OSError:
            pass

        if not ok:
            _write_stale_state_locked(
                repo,
                stale_phase="failed",
                stale_last=(
                    f"{message} — see {_stale_log_path(repo).relative_to(repo)}"
                )[:200],
                stale_finished_at=time.time(),
            )
            return 1

        built = repo / "crates" / "target" / "release" / dest.name
        try:
            artifact_mtime_ns = built.stat().st_mtime_ns
        except OSError:
            _write_stale_state_locked(
                repo,
                stale_phase="failed",
                stale_last="build succeeded but artifact vanished before stat"[:200],
                stale_finished_at=time.time(),
            )
            return 1

        # yu-infer builds in the same cargo invocation (see _run_cargo) but
        # promoting it is best-effort: a missing/unstatable sidecar artifact
        # must not fail the yu-server promotion this function exists for.
        built_infer = repo / "crates" / "target" / "release" / _infer_binary_name()
        infer_pending = None
        with suppress(OSError):
            infer_pending = {
                "path": str(built_infer),
                "artifact_mtime_ns": built_infer.stat().st_mtime_ns,
            }

        _write_stale_state_locked(
            repo,
            stale_phase="ok",
            stale_last="ok",
            stale_finished_at=time.time(),
            stale_utime_fail_count=None,
            stale_pending_artifact={
                "path": str(built),
                "artifact_mtime_ns": artifact_mtime_ns,
                "source_max_mtime_ns": max_mtime_ns,
            },
            stale_pending_infer_artifact=infer_pending,
        )
        return 0
    finally:
        lock.unlink(missing_ok=True)


_STALE_RETREAT_MAX_AGE_SECONDS = 300  # 5 minutes


def _cleanup_stale_artifacts(repo: Path) -> None:
    """Best-effort removal of aged temp/retreat files, every --resolve call.

    Independent of promotion success/failure and does not take the lock --
    these are leftover byproducts (Windows retreat renames, an unconsumed
    promotion temp file), not the state file itself.

    Patterns are anchored to this feature's own known filename prefixes
    (the binary's name, the stale-state file's name) rather than a bare
    "*.new-*"/"*.stale-*"/"*.tmp-*" glob -- bin/ is not exclusively ours
    (it also holds e.g. config.json.pre-toml-*.bak from the config
    migration), and an unanchored wildcard would delete unrelated files
    that happen to share a substring, once they age past the cutoff.
    """
    bin_dir = repo / "bin"
    if not bin_dir.is_dir():
        return
    dest_name = binary_path(repo).name
    infer_name = _infer_binary_name()
    now = time.time()
    for pattern in (
        f"{dest_name}.new-*",
        f"{dest_name}.stale-*",
        f"{infer_name}.new-*",
        f"{infer_name}.stale-*",
        f"{_STALE_STATE_NAME}.tmp-*",
    ):
        for path in bin_dir.glob(pattern):
            try:
                if now - path.stat().st_mtime > _STALE_RETREAT_MAX_AGE_SECONDS:
                    path.unlink(missing_ok=True)
            except OSError:
                pass


def _promote_artifact_file(built: Path, dest: Path) -> tuple[bool, str]:
    """Copy `built` over `dest`, atomically, with the same Windows
    exec-safe retreat-rename fallback `_promote_stale_build` uses for
    yu-server itself: a plain `os.replace` can fail on Windows while the
    target is still mapped by a running process (the sidecar, spawned from
    `dest`), so a failed replace retreats the old file aside first and
    restores it if the second attempt also fails, rather than leaving
    `dest` missing.
    """
    tmp = dest.with_name(dest.name + f".new-{os.getpid()}")
    try:
        shutil.copy2(built, tmp)
        if platform.system() != "Windows":
            tmp.chmod(0o755)
        try:
            os.replace(tmp, dest)
        except OSError:
            if platform.system() != "Windows":
                raise
            retreat = dest.with_name(dest.name + f".stale-{os.getpid()}-{int(time.time())}")
            os.replace(dest, retreat)
            try:
                os.replace(tmp, dest)
            except OSError:
                os.replace(retreat, dest)
                raise
    except OSError as exc:
        return False, str(exc)
    finally:
        tmp.unlink(missing_ok=True)
    return True, "ok"


def _promote_stale_build(repo: Path, config_path: str | None) -> None:
    """Runs at the start of every --resolve launch, before exec.

    Gate order (cheapest first, spec 設計3): (1) does the stale state file
    even exist -- absent for every distribution user and any dev who never
    triggered this feature, single stat, no config read, no lock. (2)
    non-blocking lock -- skip this launch, retry next if contended. (3)
    does stale_pending_artifact exist. (4) acquire_source()=="build". (5)
    does the recorded artifact match the real crates/target/release file.
    """
    if not _stale_state_path(repo).exists():
        return

    lock = _try_acquire_lock(repo)
    if lock is None:
        return
    try:
        state = read_stale_state(repo)
        pending = state.get("stale_pending_artifact")
        if not isinstance(pending, dict):
            return
        if acquire_source(repo, config_path) != "build":
            return

        built = Path(pending.get("path", ""))
        try:
            real_mtime_ns = built.stat().st_mtime_ns
        except OSError:
            real_mtime_ns = None

        if real_mtime_ns is None or real_mtime_ns != pending.get("artifact_mtime_ns"):
            # Mismatch (e.g. a manual `cargo build --release` clobbered the
            # artifact): drop only the pending record, keep phase/last as
            # the most recent result display.
            _write_stale_state_locked(
                repo,
                stale_pending_artifact=None,
                stale_attempted_max_mtime=None,
            )
            return

        dest = binary_path(repo)
        tmp = dest.with_name(dest.name + f".new-{os.getpid()}")
        try:
            # `copyfile`, not `copy2`: the mtime is set explicitly below to
            # `source_max_mtime_ns`, so copy2's `copystat` would only stamp a
            # value we immediately overwrite -- while making the whole
            # promotion fail on a filesystem that cannot set times.
            shutil.copyfile(built, tmp)
            if platform.system() != "Windows":
                tmp.chmod(0o755)
            try:
                os.replace(tmp, dest)
            except OSError:
                if platform.system() != "Windows":
                    raise
                retreat = dest.with_name(dest.name + f".stale-{os.getpid()}-{int(time.time())}")
                os.replace(dest, retreat)
                try:
                    os.replace(tmp, dest)
                except OSError:
                    # dest.replace() failed after we already moved the old
                    # binary out of the way -- restore it rather than leave
                    # dest missing entirely.
                    os.replace(retreat, dest)
                    raise
        except OSError:
            # Promotion itself failed (still holding the old binary in
            # place, e.g. another instance is still running and even the
            # Windows retreat rename was refused). Non-fatal: keep pending,
            # retry next launch.
            return
        finally:
            tmp.unlink(missing_ok=True)

        source_max_mtime_ns = pending["source_max_mtime_ns"]
        try:
            os.utime(dest, ns=(time.time_ns(), source_max_mtime_ns))
        except OSError:
            # dest is already replaced -- the content is correct, only the
            # mtime stamp failed. Repeating the full copy every launch
            # would be silently wasteful with no stopping condition, so
            # this is capped (spec S2): count failures, and once the cap
            # is hit, drop only stale_pending_artifact (keep
            # stale_attempted_max_mtime so _should_retry_stale_build()
            # does not restart a fresh cargo build -- that would reopen
            # the rev5-M1 no-op-rebuild loop).
            fail_count = int(state.get("stale_utime_fail_count", 0)) + 1
            if fail_count >= _STALE_UTIME_FAIL_CAP:
                _write_stale_state_locked(
                    repo,
                    stale_phase="failed",
                    stale_last=(
                        "mtime stamp failed — artifact already updated, see "
                        f"{_stale_log_path(repo).relative_to(repo)}"
                    )[:200],
                    stale_pending_artifact=None,
                    stale_utime_fail_count=fail_count,
                    stale_finished_at=time.time(),
                )
            else:
                _write_stale_state_locked(repo, stale_utime_fail_count=fail_count)
            return

        # Sidecar promotion is best-effort and untracked past this point: the
        # whole stale-state file is deleted below regardless of whether it
        # succeeds. A failure here just means yu-infer stays on its previous
        # build until the next stale-rebuild cycle notices newer sources --
        # degraded, not broken (see infer_manager::spawn_with_restart), and
        # it must never block or unwind the yu-server promotion that already
        # committed above.
        infer_pending = state.get("stale_pending_infer_artifact")
        if isinstance(infer_pending, dict):
            built_infer = Path(infer_pending.get("path", ""))
            try:
                real_infer_mtime_ns = built_infer.stat().st_mtime_ns
            except OSError:
                real_infer_mtime_ns = None
            if real_infer_mtime_ns is not None and real_infer_mtime_ns == infer_pending.get(
                "artifact_mtime_ns"
            ):
                infer_dest = dest.parent / _infer_binary_name()
                ok, msg = _promote_artifact_file(built_infer, infer_dest)
                if not ok:
                    print(f"[fast-mode] yu-infer サイドカーの昇格に失敗: {msg}", file=sys.stderr)

        _delete_stale_state(repo)
    except Exception as exc:  # noqa: BLE001 -- foreground --resolve promotion must not raise
        print(f"[fast-mode] stale promotion failed unexpectedly: {exc}", file=sys.stderr)
        return
    finally:
        lock.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    repo = Path.cwd()

    # Honour the opt-out here too, not only in the launchers: the inert check
    # (Task 10) runs this script directly, and a check that misses the real
    # entry point measures a path production never takes.
    if skip_fast_mode_requested():
        return 1

    if "--acquire" in argv:
        cfg = None
        if "--config" in argv:
            index = argv.index("--config") + 1
            if index < len(argv):
                cfg = argv[index]
        return acquire(repo, cfg)

    if "--acquire-stale" in argv:
        return _handle_acquire_stale(repo, argv)

    if "--resolve" not in argv:
        print("usage: fast_mode.py --resolve [-- passthrough args]", file=sys.stderr)
        return 2

    passthrough = argv[argv.index("--") + 1:] if "--" in argv else []
    _cleanup_stale_artifacts(repo)
    _promote_stale_build(repo, effective_config_path(passthrough))
    binary = binary_path(repo)
    decision = decide(repo, binary)
    record_decision(repo, decision)
    if not decision.use_fast_mode:
        print(f"[fast-mode] Python で起動します: {decision.reason}", file=sys.stderr)
        # Nothing to run this time -- start getting something for next time,
        # but only when a binary is what is missing. decide() answers that;
        # main() must not re-derive it by reading the reason string.
        if decision.needs_binary:
            _spawn_acquisition(repo, effective_config_path(passthrough))
        return 1

    # Registration happens here, not in fetch()/build(): fetch/build run
    # inside the detached `--acquire` child, which never has a tty, so this
    # is the earliest synchronous, foreground point in the fast-mode path
    # that can prompt for sudo (decide() above is also synchronous here,
    # but needs no user-facing sudo prompt, so it does not count). Gated
    # on the non-loopback-bind predicate, not on --lan
    # alone: Python has three more ways to reach 0.0.0.0 (config.json's
    # "lan"/"host", --host 0.0.0.0) and yu-server itself adds YU_HOST and
    # launch-args.txt on top of those -- see _will_bind_non_loopback()
    # (mirrors runtime_runner.py's synchronous check for the Python launch
    # path, acceptance criterion 16).
    if (
        platform.system() == "Darwin"
        and _will_bind_non_loopback(repo, passthrough)
        and not _register_firewall_exception(binary)
    ):
        print(
            "[fast-mode] macOS ファイアウォール許可に失敗した。"
            "Python 経路にフォールバックします。",
            file=sys.stderr,
        )
        return 1

    if (repo / "crates" / "target").is_dir():
        count, _display_paths, max_mtime_ns = _stale_local_sources(repo, binary)
        if count and max_mtime_ns is not None:
            cfg = effective_config_path(passthrough)
            if acquire_source(repo, cfg) == "build" and _should_retry_stale_build(
                repo, max_mtime_ns
            ):
                _spawn_stale_rebuild(repo, cfg, max_mtime_ns, count)

    argv_out = launch_argv(repo, binary, passthrough)
    from core.services_core.db_cipher import _APP_KEY

    output = [_ENV_DB_KEY_PREFIX + _APP_KEY, *argv_out]
    # One argument per line, not space-joined: binary_path() is
    # Path.cwd()/bin/yu-server, and a real install can sit under
    # "C:\Users\Taro Yamada" or "~/My Apps". A space-joined line fans out
    # under an unquoted `$VAR`/`Invoke-Expression` in the launchers into the
    # wrong number of arguments (or a glob expansion on the sh side), so the
    # launchers instead read one argument per line. That format cannot
    # represent a literal \n *or* \r inside a single argument -- sh's
    # `while IFS= read -r line` splits on \n only, but a bare \r would sail
    # through unharmed there and still be a hazard on PowerShell, which can
    # split the captured process output on \r as well as \n -- so refuse
    # fast mode rather than emit output a launcher would silently misparse.
    if any(c in arg for arg in output for c in "\r\n"):
        print(
            "[fast-mode] Python で起動します: an argument contains a newline or "
            "carriage return, which the one-argument-per-line launch format "
            "cannot represent",
            file=sys.stderr,
        )
        return 1
    print("\n".join(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
