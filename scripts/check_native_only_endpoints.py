"""Validate native-only API documentation against Rust routes and Python routes."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "docs" / "development" / "native-only-endpoints.yaml"
# The committed generated doc doubles as the baseline of "what was documented
# before this change". No separate inventory file is kept in sync by hand.
BASELINE_DOC = "docs/ja/api/all-endpoints.md"
_DOC_PATH_RE = re.compile(r"\|\s*`(/[^`]*)`\s*\|")


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _normalize(path: str) -> str:
    """Collapse route parameters so Flask and axum spellings compare equal.

    `/api/files/<int:file_id>` and `/api/files/{file_id}` both become
    `/api/files/{}`; `<path:subpath>` and `*subpath` likewise.
    """
    path = re.sub(r"<[^>]+>", "{}", path)
    path = re.sub(r"\{[^}]*\}", "{}", path)
    path = re.sub(r"(?<=/)[:*][^/]+", "{}", path)
    return path.rstrip("/") or "/"


def _baseline_paths() -> set[str] | None:
    """Endpoint paths documented at HEAD, or None when HEAD has no doc yet."""
    try:
        proc = subprocess.run(
            ["git", "show", f"HEAD:{BASELINE_DOC}"],
            cwd=REPO,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except OSError:
        return None
    if proc.returncode != 0 or not proc.stdout or not proc.stdout.strip():
        return None
    return set(_DOC_PATH_RE.findall(proc.stdout))


def _check_silent_removals(docs, rust) -> list[str]:
    """Catch endpoints that leave the docs while the Rust router still serves them.

    `gen_api_docs` reads Python route definitions plus the native-only manifest.
    Deleting a Python route for an endpoint that lives on in Rust therefore drops
    it from the docs with nothing failing — the manifest cannot notice, because it
    only scans the `rust_module` values it already lists.
    """
    baseline = _baseline_paths()
    if baseline is None:
        return []
    documented = {_normalize(ep.path) for ep in docs.collect_endpoints()}
    served = {_normalize(route.path) for route in rust.collect_rust_routes()}
    gone = sorted(
        path
        for path in baseline
        if _normalize(path) not in documented and _normalize(path) in served
    )
    return [
        f"  Dropped from docs but still served by Rust: {path}"
        f" (add it to {MANIFEST.relative_to(REPO)})"
        for path in gone
    ]


def _self_check() -> str | None:
    """Prove the removal detector still fires on the failure it was built for.

    A checker that silently returns "no findings" because its own inputs broke
    is indistinguishable from a clean tree, so re-derive the known failure here:
    a path that the baseline documents and Rust still serves, but that the
    current docs no longer list, must be reported.
    """
    baseline = {"/api/agent/kill", "/api/files/<int:file_id>"}
    documented = {"/api/files/{file_id}"}
    served = {"/api/agent/kill", "/api/files/{file_id}"}
    gone = {
        path
        for path in baseline
        if _normalize(path) not in {_normalize(p) for p in documented}
        and _normalize(path) in {_normalize(p) for p in served}
    }
    if gone != {"/api/agent/kill"}:
        return f"self-check failed: removal detector reported {sorted(gone)}, expected ['/api/agent/kill']"
    # Spelling collapse, asserted directly: the 480 Rust paths that look
    # "undocumented" are mostly Flask-vs-axum notation, so a normalizer that
    # stops collapsing them would make every parameterized route look dropped.
    for flask, axum in (
        ("/api/files/<int:file_id>", "/api/files/{file_id}"),
        ("/static/<path:subpath>", "/static/{subpath}"),
        ("/api/jobs/<job_id>/cancel", "/api/jobs/{job_id}/cancel"),
    ):
        if _normalize(flask) != _normalize(axum):
            return (
                "self-check failed: path normalizer no longer collapses "
                f"{flask!r} and {axum!r} to the same shape"
            )
    return None


def check() -> tuple[bool, str]:
    broken = _self_check()
    if broken:
        return False, broken
    entries = (yaml.safe_load(MANIFEST.read_text(encoding="utf-8")) or {}).get("endpoints", [])
    required = {item["rust_module"] for item in entries}
    declared = {(item["path"], method) for item in entries for method in item["methods"]}
    rust = _load_module("native_only_rust_routes", REPO / "scripts" / "check_rust_mcp_parity.py")
    actual = {(route.path, route.method) for route in rust.collect_rust_routes() if route.file in required}
    docs = _load_module("native_only_api_docs", REPO / "scripts" / "gen_api_docs.py")
    python_paths = {endpoint.path for endpoint in docs.collect_python_endpoints()}
    plaintext = sorted({item["path"] for item in entries} & python_paths)
    missing = sorted(actual - declared)
    extra = sorted(declared - actual)
    removed = _check_silent_removals(docs, rust)
    if plaintext or missing or extra or removed:
        lines = ["native-only endpoint drift:"]
        lines += [f"  Python definition present: {path}" for path in plaintext]
        lines += [f"  Manifest missing: {method} {path}" for path, method in missing]
        lines += [f"  Rust route missing: {method} {path}" for path, method in extra]
        lines += removed
        return False, "\n".join(lines)
    baseline = _baseline_paths()
    suffix = "" if baseline else " (no HEAD baseline; removal check skipped)"
    return True, f"native-only endpoints: {len(declared)} Rust route methods covered{suffix}"


if __name__ == "__main__":
    ok, message = check()
    print(message)
    raise SystemExit(not ok)
