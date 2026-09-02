"""Pre-push hallucination & quality gate.

Runs the fast static checks that catch LLM-generated code issues before push:

  1. ruff check --select F821,F811,F405,E9    -- undefined names / syntax
  2. pnpm typecheck                            -- TypeScript API hallucinations
  3. pyright --outputjson (changed files)      -- Python API hallucinations
  4. pytest --collect-only                     -- Python import errors

Target files = those changed vs origin/main, falling back to HEAD~1 if origin
is unreachable. Pass --all to scan the full tree.

Exit codes:
  0  all clean
  1  one or more checks failed
  2  tool setup problem (missing binary etc.)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import tomllib
from collections.abc import Callable
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    from scripts.internal.pre_push_check_shared import run_command
except ImportError:
    from internal.pre_push_check_shared import run_command  # type: ignore[no-redef]


def check_githooks_installed() -> tuple[bool, str]:
    """Advisory: verify core.hooksPath points to .githooks so the tracked
    pre-push/pre-commit gate is actually enforced. Returns ok=True always
    (advisory — never blocks), but emits a warning when the gate is dormant.
    """
    import subprocess
    try:
        proc = subprocess.run(
            ["git", "config", "--get", "core.hooksPath"],
            capture_output=True, text=True, cwd=_REPO_ROOT,
        )
    except Exception as e:
        return True, f"(could not read core.hooksPath: {e})"
    value = proc.stdout.strip()
    if value == ".githooks":
        return True, "core.hooksPath=.githooks (tracked gate active)"
    shown = value if value else "(unset)"
    return True, (
        f"⚠ core.hooksPath is {shown}, not '.githooks' — the tracked pre-push/pre-commit "
        "gate is DORMANT on this clone. push-time checks are NOT auto-enforced.\n"
        "  Fix (once per clone): git config core.hooksPath .githooks\n"
        "  (This warning is advisory — does not block push.)"
    )


def check_ps1_bom() -> tuple[bool, str]:
    """Ensure .ps1 files with non-ASCII content have UTF-8 BOM (EF BB BF).

    PowerShell 5.1 (powershell.exe) reads .ps1 files as ANSI (CP932 on Japanese
    Windows) unless a UTF-8 BOM is present. ASCII-only .ps1 files need no BOM.
    """
    _UTF8_BOM = bytes([0xEF, 0xBB, 0xBF])
    missing: list[str] = []
    checked = 0
    for ps1 in _REPO_ROOT.rglob("*.ps1"):
        if ".venv" in ps1.parts or "tmp" in ps1.parts or ".claude" in ps1.parts:
            continue
        checked += 1
        raw = ps1.read_bytes()
        if raw[:3] == _UTF8_BOM:
            continue
        if any(b >= 0x80 for b in raw):
            missing.append(str(ps1.relative_to(_REPO_ROOT)))
    if missing:
        lines = "\n".join(f"  {p}" for p in missing)
        return False, (
            "Non-ASCII .ps1 files must have UTF-8 BOM (PowerShell 5.1 reads ANSI otherwise).\n"
            "Fix: $c=Get-Content file -Raw -Encoding UTF8; [IO.File]::WriteAllText(file,$c,(New-Object Text.UTF8Encoding $true))\n"
            f"{lines}"
        )
    return True, f"All .ps1 files pass encoding check ({checked} checked)"


def check_bat_bom() -> tuple[bool, str]:
    """Ensure .bat files with non-ASCII content use UTF-16LE encoding (BOM FF FE).

    cmd.exe reliably handles multi-byte characters (Japanese/Korean/Chinese) only
    in UTF-16LE files. ASCII-only .bat files need no BOM.
    """
    _UTF16LE_BOM = bytes([0xFF, 0xFE])
    missing: list[str] = []
    checked = 0
    for bat in _REPO_ROOT.rglob("*.bat"):
        if ".venv" in bat.parts:
            continue
        checked += 1
        raw = bat.read_bytes()
        if raw[:2] == _UTF16LE_BOM:
            continue
        # No UTF-16LE BOM — fail if non-ASCII bytes are present
        if any(b >= 0x80 for b in raw):
            missing.append(str(bat.relative_to(_REPO_ROOT)))
    if missing:
        lines = "\n".join(f"  {p}" for p in missing)
        return False, (
            "Non-ASCII .bat files must use UTF-16LE encoding.\n"
            "Fix: $content = Get-Content file -Raw; $content | Out-File file -Encoding Unicode\n"
            f"{lines}"
        )
    return True, f"All .bat files pass encoding check ({checked} checked)"


def check_uv_binary_pinned() -> tuple[bool, str]:
    """Verify project uv binaries match the pinned release manifest."""
    manifest_path = _REPO_ROOT / "scripts" / "uv-checksums.txt"
    if not manifest_path.exists():
        return True, "(scripts/uv-checksums.txt 無シ — スキップ)"

    binary_paths = [
        _REPO_ROOT / "bin" / "uv",
        _REPO_ROOT / "bin" / "uvx",
        _REPO_ROOT / "bin" / "uv.exe",
        _REPO_ROOT / "bin" / "uvx.exe",
    ]
    existing_binaries = [path for path in binary_paths if path.exists()]
    if not existing_binaries:
        return True, "(プロジェクト固有 uv 無シ＝system uv 想定 — スキップ)"

    pinned_version = "unknown"
    trusted_hashes: set[str] = set()
    for raw_line in manifest_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "version":
            pinned_version = parts[1]
            continue
        if len(parts) >= 5 and parts[2] == "binary":
            trusted_hashes.add(parts[3].lower())

    violations: list[str] = []
    for binary_path in existing_binaries:
        actual_hash = hashlib.sha256(binary_path.read_bytes()).hexdigest()
        if actual_hash.lower() in trusted_hashes:
            continue
        relative_path = binary_path.relative_to(_REPO_ROOT).as_posix()
        violations.append(
            f"{relative_path} sha256={actual_hash[:16]}..."
        )

    if violations:
        return False, (
            "bin/uv が pin マニフェストの信頼済みリリースバイナリと不一致。"
            "すり替えの疑い。正規再取得: `bash scripts/bootstrap_uv.sh`"
            "（アーカイブを checksum 検証して再インストール）。"
            "uv 版を意図的に更新する場合のみ `bash scripts/update_uv_checksums.sh` "
            "でマニフェスト再生成\n"
            + "\n".join(f"  {violation}" for violation in violations)
        )

    return True, f"bin/uv 等 {len(existing_binaries)} 件 = pinned uv {pinned_version} リリースバイナリと一致"


def _normalized_requirement_name(requirement: str) -> str:
    """Extract and normalize a package name from a PEP 508-ish requirement."""
    name = requirement.strip().split("#", 1)[0].split(";", 1)[0].strip()
    if not name:
        return ""
    name = re.split(r"\s+@", name, maxsplit=1)[0].strip()
    name = re.split(r"[<>=!~\[]", name, maxsplit=1)[0].strip()
    return re.sub(r"[-_.]+", "-", name).lower()


def check_requirements_pyproject_sync() -> tuple[bool, str]:
    """Ensure legacy requirements.txt covers pyproject main dependencies."""
    pyproject_path = _REPO_ROOT / "pyproject.toml"
    requirements_path = _REPO_ROOT / "requirements.txt"

    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"Failed to parse pyproject.toml: {e}"
    if not requirements_path.exists():
        return False, "requirements.txt missing"

    dependencies = pyproject.get("project", {}).get("dependencies", [])
    if not isinstance(dependencies, list):
        return False, "pyproject.toml [project].dependencies is malformed"

    pyproject_deps = sorted(
        {
            name
            for dep in dependencies
            if isinstance(dep, str)
            for name in [_normalized_requirement_name(dep)]
            if name
        }
    )
    requirements_deps = {
        name
        for line in requirements_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
        for name in [_normalized_requirement_name(line)]
        if name
    }

    missing = [dep for dep in pyproject_deps if dep not in requirements_deps]
    if missing:
        return False, (
            "requirements.txt is missing pyproject deps: "
            + ", ".join(missing)
            + "\n  -> add them to requirements.txt to keep CI (pip) in sync with pyproject (uv)"
        )
    return True, f"requirements.txt covers all {len(pyproject_deps)} pyproject [project].dependencies"


_DEV_DOCS_DIR = "docs/development/development_docs"
_DEV_DOCS_INDEX = f"{_DEV_DOCS_DIR}/dev-docs-index.yaml"


def _claude_criteria_yamls(require_ref: bool = True) -> list[Path]:
    """Return .claude/*.yaml files that have a 'criteria:' top-level key.

    If require_ref=True (default), also require 'rationale_ref:' key.
    If require_ref=False, return all yaml with 'criteria:' (for structural validation).
    """
    claude_dir = _REPO_ROOT / ".claude"
    result = []
    for yml_file in sorted(claude_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(yml_file.read_text(encoding="utf-8"))
        except Exception as exc:
            # A criteria file that stops parsing stops gating, silently. This
            # gate exists to catch exactly that class of quiet disappearance,
            # so it must not become an instance of it.
            print(f"  ⚠ {yml_file.name}: unparseable, not checked ({exc})")
            continue
        if not isinstance(data, dict) or "criteria" not in data:
            continue
        if require_ref and "rationale_ref" not in data:
            continue
        result.append(yml_file)
    return result


def _parse_frontmatter(md_path: Path) -> dict:
    """Parse YAML front-matter from a markdown file. Returns {} if absent or invalid."""
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None)
    if end is None:
        return {}
    try:
        return yaml.safe_load("\n".join(lines[1:end])) or {}
    except Exception:
        return {}


def check_rationale_ref_resolution() -> tuple[bool, str]:
    """Check all rationale_refs in criteria yamls resolve to existing files."""
    errors: list[str] = []
    yamls = _claude_criteria_yamls(require_ref=True)
    for yml_file in yamls:
        data = yaml.safe_load(yml_file.read_text(encoding="utf-8"))
        ref = data["rationale_ref"]
        if not isinstance(ref, str) or not (_REPO_ROOT / ref).exists():
            errors.append(f"  {yml_file.name}: rationale_ref not found: {ref!r}")
        for c in data.get("criteria", []):
            if "rationale_ref" in c:
                cref = c["rationale_ref"]
                if not isinstance(cref, str) or not (_REPO_ROOT / cref).exists():
                    errors.append(f"  {yml_file.name}[{c.get('id', '?')}]: rationale_ref not found: {cref!r}")
    if errors:
        return False, "rationale_ref resolution failed:\n" + "\n".join(errors)
    return True, f"All rationale_refs resolved ({len(yamls)} criteria yaml(s) checked)"


def check_pair_completeness() -> tuple[bool, str]:
    """Check each md with doc_type:paired has a criteria yaml referencing it."""
    docs_dir = _REPO_ROOT / "docs" / "development" / "development_docs"

    referenced: set[str] = set()
    for yml_file in _claude_criteria_yamls(require_ref=True):
        data = yaml.safe_load(yml_file.read_text(encoding="utf-8"))
        ref = data["rationale_ref"]
        if isinstance(ref, str):
            referenced.add(str((_REPO_ROOT / ref).resolve()))

    errors: list[str] = []
    count = 0
    for md_file in sorted(docs_dir.glob("*.md")):
        fm = _parse_frontmatter(md_file)
        if not fm:
            continue
        if fm.get("doc_type") != "paired":
            continue
        count += 1
        if str(md_file.resolve()) not in referenced:
            errors.append(f"  {md_file.name}: doc_type:paired but no criteria yaml references it")

    if errors:
        return False, "pair completeness check failed:\n" + "\n".join(errors)
    return True, f"All paired mds have criteria yaml ({count} paired md(s) checked)"


def check_no_duplicate_rationale_refs() -> tuple[bool, str]:
    """Check no two criteria yamls share the same rationale_ref (1:1 constraint)."""
    seen: dict[str, str] = {}  # normalized_ref -> yml_name
    errors: list[str] = []
    for yml_file in _claude_criteria_yamls(require_ref=True):
        data = yaml.safe_load(yml_file.read_text(encoding="utf-8"))
        ref = data["rationale_ref"]
        if not isinstance(ref, str):
            continue
        normalized = ref.replace("\\", "/")
        if normalized in seen:
            errors.append(
                f"  {yml_file.name} and {seen[normalized]}: both reference {normalized!r}"
            )
        else:
            seen[normalized] = yml_file.name
    if errors:
        return False, "duplicate rationale_ref detected (1:1 constraint):\n" + "\n".join(errors)
    return True, f"All rationale_refs are unique ({len(seen)} criteria yaml(s) checked)"


def check_index_v2_sync() -> tuple[bool, str]:
    """Check dev-docs-index.yaml v2 is in sync with filesystem and free of conflicts.

    doc_sha256 フィールドを持つエントリはファイルの現 SHA256 と照合する。
    SHA256 不一致はドキュメントが更新されたが索引が再生成されていないことを示す。
    """
    import hashlib as _hl

    def _doc_sha256(path: Path) -> str:
        # Must match scripts/gen_docs_index.py::_sha256 exactly (CRLF -> LF
        # normalized) or every doc looks "changed" on a Windows checkout
        # (core.autocrlf=true) even when nothing was edited.
        return _hl.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()

    index_path = _REPO_ROOT / _DEV_DOCS_INDEX
    if not index_path.exists():
        return True, "(dev-docs-index.yaml not found — skipped)"

    try:
        raw = "\n".join(
            l for l in index_path.read_text(encoding="utf-8").splitlines()
            if not l.startswith("#")
        )
        index = yaml.safe_load(raw)
    except Exception as e:
        return False, f"Failed to parse dev-docs-index.yaml: {e}"

    if not isinstance(index, dict):
        return False, "dev-docs-index.yaml is malformed"

    errors: list[str] = []
    version = index.get("version", 1)

    if version == 2:
        sets = index.get("sets", {})
        docs_dir = _REPO_ROOT / "docs" / "development" / "development_docs"

        # Case (a): sets md has doc_type:standalone_prior
        for _, info in sets.items():
            md_path = _REPO_ROOT / info.get("md", "")
            if md_path.exists() and _parse_frontmatter(md_path).get("doc_type") == "standalone_prior":
                errors.append(f"  CONFLICT(a): {info.get('md', '?')} is in sets but doc_type:standalone_prior")

        # Case (b): doc_type:paired md is not in sets
        sets_mds = {info.get("md", "").replace("\\", "/") for info in sets.values()}
        for md_file in sorted(docs_dir.glob("*.md")):
            rel = str(md_file.relative_to(_REPO_ROOT)).replace("\\", "/")
            if _parse_frontmatter(md_file).get("doc_type") == "paired" and rel not in sets_mds:
                errors.append(f"  CONFLICT(b): {rel} has doc_type:paired but not in sets")

        # doc_sha256 照合 — standalone と foundations の両方をチェック
        sha_mismatches: list[str] = []

        for entry in index.get("standalone", []):
            expected = entry.get("doc_sha256")
            if not expected:
                continue
            doc_path = docs_dir / entry["file"]
            if not doc_path.exists():
                # エントリが在るのにファイルが無い → 索引が陳腐化した参照を持つ
                sha_mismatches.append(f"  {entry['file']} (NOT FOUND — stale entry or path mismatch)")
                continue
            actual = _doc_sha256(doc_path)
            if actual != expected:
                sha_mismatches.append(f"  {entry['file']} (content changed)")

        for entry in index.get("foundations", []):
            expected = entry.get("doc_sha256")
            if not expected:
                continue
            doc_path = _REPO_ROOT / entry["file"]
            if not doc_path.exists():
                sha_mismatches.append(f"  {entry['file']} (NOT FOUND — stale entry or path mismatch)")
                continue
            actual = _doc_sha256(doc_path)
            if actual != expected:
                sha_mismatches.append(f"  {entry['file']} (content changed)")

        if sha_mismatches:
            errors.append(
                f"⚠ {len(sha_mismatches)} doc(s) changed — re-run gen_docs_index.py and verify summary/when_to_read:\n"
                + "\n".join(sha_mismatches)
            )

    # Git drift check（AMD: 追加・修正・削除を検出）
    for base in ("origin/main", "HEAD~1"):
        proc = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=AMD", base],
            capture_output=True, text=True, cwd=_REPO_ROOT,
        )
        if proc.returncode != 0:
            continue
        doc_changes = [
            f for f in proc.stdout.splitlines()
            if f.startswith(_DEV_DOCS_DIR) and f.endswith(".md")
        ]
        if doc_changes:
            proc2 = subprocess.run(
                ["git", "diff", "--name-only", base],
                capture_output=True, text=True, cwd=_REPO_ROOT,
            )
            all_changed = proc2.stdout.splitlines() if proc2.returncode == 0 else []
            if _DEV_DOCS_INDEX not in all_changed:
                errors.append(
                    f"⚠ {len(doc_changes)} doc(s) changed but dev-docs-index.yaml NOT updated"
                )
        break

    if errors:
        return False, "check_index_v2_sync failed:\n" + "\n".join(errors)
    return True, f"dev-docs-index.yaml in sync (version={version})"


def check_feature_index_sync() -> tuple[bool, str]:
    """FEATURES.md must match a fresh generation from extension.json."""
    proc = subprocess.run(
        [sys.executable, str(_REPO_ROOT / "scripts" / "gen_feature_index.py"), "--check"],
        capture_output=True, text=True, cwd=_REPO_ROOT,
    )
    if proc.returncode == 0:
        return True, "FEATURES.md in sync"
    return False, (proc.stderr.strip() or "FEATURES.md stale")


def check_structural_validators() -> tuple[bool, str]:
    """Run doc-format-check.yaml against all criteria yamls (both yml_types)."""
    checker = _REPO_ROOT / ".claude" / "doc-format-check.yaml"
    if not checker.exists():
        return True, "(doc-format-check.yaml not found — skipped)"

    subjects = _claude_criteria_yamls(require_ref=False)
    if not subjects:
        return True, "(no criteria yamls found — skipped)"

    errors: list[str] = []
    for subject in subjects:
        proc = subprocess.run(
            [sys.executable,
             str(_REPO_ROOT / "scripts" / "run_criteria.py"),
             str(checker.relative_to(_REPO_ROOT)),
             str(subject.relative_to(_REPO_ROOT))],
            capture_output=True, text=True, cwd=_REPO_ROOT,
        )
        if proc.returncode != 0:
            errors.append(f"  FAIL: {subject.name}")
            for line in (proc.stdout + proc.stderr).splitlines()[:8]:
                errors.append(f"    {line}")

    if errors:
        return False, "structural validators check failed:\n" + "\n".join(errors)
    return True, f"All criteria yamls pass doc-format-check ({len(subjects)} checked)"



_DEV_OVERVIEW_JSON = _REPO_ROOT / "docs" / "development" / "dev-overview.json"
_DEV_OVERVIEW_HTML = _REPO_ROOT / "docs" / "development" / "dev-overview.html"
_VERSION_FILE = _REPO_ROOT / "VERSION"
_SETTINGS_SCHEMA_JSON = _REPO_ROOT / "config" / "settings_schema.json"


def check_version_sync() -> tuple[bool, str]:
    """Fail when package.json / Cargo.toml / Cargo.lock lag behind VERSION.

    Static Checks runs `sync_version.py --check`, but CI is nightly-only, so
    without the same check here a version bump that skipped sync_version.py
    stays red until the next morning. Reuses sync_version's own getters so the
    two gates cannot disagree about how a version is read.
    """
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
    import sync_version

    canonical = sync_version.read_canonical()
    actual = {
        "package.json": sync_version.get_pkg_version(),
        "Cargo.toml": sync_version.get_cargo_toml_version(),
        # Empty when src-tauri/Cargo.lock is absent; sync_version skips it too.
        "Cargo.lock": sync_version.get_cargo_lock_version(),
    }
    bad = [f"{name} ({got}) ≠ VERSION ({canonical})" for name, got in actual.items() if got and got != canonical]
    if bad:
        return False, "\n".join(
            ["⚠ " + line for line in bad] + ["  Run: uv run python scripts/sync_version.py"]
        )
    return True, f"versions match {canonical}"


def check_dev_overview_sync() -> tuple[bool, str]:
    """Warn when dev-overview.json version lags behind VERSION file.

    Also verifies that dev-overview.html is in sync with the JSON
    (i.e. sync_dev_overview.py has been run after editing the JSON), and that
    structured path references still exist in the repository.
    """
    import json
    import re

    if not _DEV_OVERVIEW_JSON.exists():
        return True, "(dev-overview.json missing — skipped)"
    if not _VERSION_FILE.exists():
        return True, "(VERSION missing — skipped)"

    current_version = _VERSION_FILE.read_text(encoding="utf-8").strip()

    try:
        overview = json.loads(_DEV_OVERVIEW_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"dev-overview.json is malformed: {e}"

    json_version = overview.get("version", "(none)")
    last_synced = overview.get("last_synced", "(unknown)")

    lines: list[str] = []
    ok = True
    stale_paths: list[tuple[str, str]] = []

    def _normalize_path(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        path = value.strip().strip("/")
        if not path or "*" in path:
            return None
        return path

    def _path_exists(path: str) -> bool:
        return (_REPO_ROOT / path).exists()

    def _check_path(field: str, value: object) -> None:
        path = _normalize_path(value)
        if path is None:
            return
        if not _path_exists(path):
            stale_paths.append((field, path))

    def _first_scalar_path(value: object) -> str | None:
        if not isinstance(value, str):
            return None
        path = value
        for sep in (" (", " + ", "|"):
            path = path.split(sep, 1)[0]
        return _normalize_path(path)

    # Check 1: version matches VERSION file
    if json_version != current_version:
        ok = False
        lines.append(
            f"⚠ dev-overview.json version ({json_version}) ≠ VERSION ({current_version})"
        )
        lines.append(f"  last_synced: {last_synced}")
        lines.append("  Update docs/development/dev-overview.json then run:")
        lines.append("    uv run python scripts/sync_dev_overview.py")

    # Check 2: HTML is in sync with JSON (same JSON content embedded)
    if _DEV_OVERVIEW_HTML.exists():
        html = _DEV_OVERVIEW_HTML.read_text(encoding="utf-8")
        marker = re.compile(
            r'<script id="overview-data" type="application/json">\n(.*?)</script>',
            re.DOTALL,
        )
        m = marker.search(html)
        if m:
            html_json_text = m.group(1).rstrip()
            # sync_dev_overview.py escapes '<' as < when embedding into HTML
            file_json_text = _DEV_OVERVIEW_JSON.read_text(encoding="utf-8").rstrip().replace("<", "\\u003c")
            if html_json_text != file_json_text:
                ok = False
                lines.append("⚠ dev-overview.html is out of sync with dev-overview.json")
                lines.append("  Run: uv run python scripts/sync_dev_overview.py")

    # Check 3: structured references point at existing repository paths.
    top_level = overview.get("top_level_structure", {})
    if isinstance(top_level, dict):
        tests = top_level.get("tests", {})
        if isinstance(tests, dict):
            categories = tests.get("categories", [])
            if isinstance(categories, list):
                for category in categories:
                    path = _normalize_path(category)
                    if path is None:
                        continue
                    _check_path("top_level_structure.tests.categories", f"tests/{path}")

        docs = top_level.get("docs", {})
        if isinstance(docs, dict):
            key_files = docs.get("key_files", [])
            if isinstance(key_files, list):
                for item in key_files:
                    if not isinstance(item, str) or " — " not in item:
                        continue
                    _check_path("top_level_structure.docs.key_files", item.split(" — ", 1)[0])

        scalar_fields = (
            ("top_level_structure.backend.entry_point", ("backend", "entry_point")),
            ("top_level_structure.mcp_server.entry", ("mcp_server", "entry")),
            ("top_level_structure.cli.entry", ("cli", "entry")),
            ("top_level_structure.desktop.config", ("desktop", "config")),
            ("top_level_structure.frontend.src", ("frontend", "src")),
        )
        for field, keys in scalar_fields:
            section = top_level.get(keys[0], {})
            value = section.get(keys[1]) if isinstance(section, dict) else None
            path = _first_scalar_path(value)
            if path is not None and not _path_exists(path):
                stale_paths.append((field, path))

    backend_arch = overview.get("backend_architecture", {})
    route_pattern = (
        backend_arch.get("route_layer_pattern", {}) if isinstance(backend_arch, dict) else {}
    )
    domain_api_map = (
        route_pattern.get("domain_api_map", []) if isinstance(route_pattern, dict) else []
    )
    if isinstance(domain_api_map, list):
        for entry in domain_api_map:
            if not isinstance(entry, dict):
                continue
            _check_path("backend_architecture.route_layer_pattern.domain_api_map.core", entry.get("core"))
            routes = entry.get("routes")
            if isinstance(routes, str):
                for route in routes.split(","):
                    _check_path(
                        "backend_architecture.route_layer_pattern.domain_api_map.routes",
                        route,
                    )

    if stale_paths:
        ok = False
        lines.append("⚠ dev-overview.json references stale paths:")
        for field, path in stale_paths:
            lines.append(f"  {field}: {path}")
        lines.append("  Update docs/development/dev-overview.json to match the current repo layout.")

    if ok:
        return True, f"dev-overview.json in sync (version={json_version}, last_synced={last_synced})"
    return False, "\n".join(lines)


def check_settings_schema_sync() -> tuple[bool, str]:
    """Verify config/settings_schema.json is generated from SETTINGS_SCHEMA."""
    script = _REPO_ROOT / "scripts" / "gen_settings_schema.py"
    if not script.exists():
        return True, "(gen_settings_schema.py missing — skipped)"
    if not _SETTINGS_SCHEMA_JSON.exists():
        return False, "config/settings_schema.json missing — run: uv run python scripts/gen_settings_schema.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--check"],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    out = (proc.stdout + proc.stderr).strip() or "(no output)"
    return proc.returncode == 0, out


def check_fast_mode_inert() -> tuple[bool, str]:
    """Verify fast mode changes nothing for a user who never enables it.

    Acceptance criterion 17. Delegates to the checker rather than
    reimplementing it, so the gate and the standalone invocation can never
    measure different things.
    """
    script = _REPO_ROOT / "scripts" / "internal" / "check_fast_mode_inert.py"
    if not script.exists():
        return False, "scripts/internal/check_fast_mode_inert.py missing"
    proc = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        cwd=_REPO_ROOT,
    )
    out = (proc.stdout + proc.stderr).strip() or "(no output)"
    return proc.returncode == 0, out


def check_agents_md_sync() -> tuple[bool, str]:
    """Verify AGENTS.md is byte-identical to CLAUDE.md (Windows symlink workaround)."""
    script = _REPO_ROOT / "scripts" / "sync_agents_md.py"
    if not script.exists():
        return True, "(sync_agents_md.py missing — skipped)"
    proc = subprocess.run(
        [sys.executable, str(script), "--check"],
        capture_output=True,
        text=True,
    )
    out = (proc.stdout + proc.stderr).strip() or "(no output)"
    return proc.returncode == 0, out

try:
    from scripts.internal.pre_push_check_checkers import (
        _collect_async_route_violations,
        _collect_db_write_violations,
        _collect_i18n_key_violations,
        changed_py_files,
        check_async_route_sync_io,
        check_bundled_extensions_manifest,
        check_db_write_rule,
        check_feature_parity,
        check_genesis_acceptance,
        check_i18n_key_drift,
        check_lan_cowork_clippy,
        check_lan_cowork_pinned_rev_public,
        check_mcp_parity_errors,
        check_mcp_parity_warnings,
        check_pyright,
        check_pytest_collect,
        check_ruff,
        check_rust_compat,
        check_rust_fmt,
        check_rust_genesis_sql_sync,
        check_rust_schema_version_pin,
        check_rust_standalone_build,
        check_scan_roots_recovery_filter,
        check_schema_drift,
        check_ts,
    )
except ImportError:
    from internal.pre_push_check_checkers import (  # type: ignore[no-redef]
        _collect_async_route_violations,
        _collect_db_write_violations,
        _collect_i18n_key_violations,
        changed_py_files,
        check_async_route_sync_io,
        check_bundled_extensions_manifest,
        check_db_write_rule,
        check_feature_parity,
        check_genesis_acceptance,
        check_i18n_key_drift,
        check_lan_cowork_clippy,
        check_lan_cowork_pinned_rev_public,
        check_mcp_parity_errors,
        check_mcp_parity_warnings,
        check_pyright,
        check_pytest_collect,
        check_ruff,
        check_rust_compat,
        check_rust_fmt,
        check_rust_genesis_sql_sync,
        check_rust_schema_version_pin,
        check_rust_standalone_build,
        check_scan_roots_recovery_filter,
        check_schema_drift,
        check_ts,
    )

try:
    from scripts.internal.pre_push_check_scope_gate import check_scope_gate_violations
except ImportError:
    from internal.pre_push_check_scope_gate import check_scope_gate_violations  # type: ignore[no-redef]

try:
    from scripts.internal.lan_cowork_schema_contract import check_lan_cowork_schema_contract
except ImportError:
    from internal.lan_cowork_schema_contract import (  # type: ignore[no-redef]
        check_lan_cowork_schema_contract,
    )

__all__ = [
    "_collect_async_route_violations",
    "_collect_db_write_violations",
    "_collect_i18n_key_violations",
    "changed_py_files",
    "check_async_route_sync_io",
    "check_db_write_rule",
    "check_githooks_installed",
    "check_index_v2_sync",
    "check_rationale_ref_resolution",
    "check_pair_completeness",
    "check_no_duplicate_rationale_refs",
    "check_structural_validators",
    "check_version_sync",
    "check_dev_overview_sync",
    "check_settings_schema_sync",
    "check_feature_parity",
    "check_i18n_key_drift",
    "check_lan_cowork_clippy",
    "check_lan_cowork_pinned_rev_public",
    "check_rust_fmt",
    "check_bungo_all_normalized",
    "check_bungo_katakana_baseline",
    "check_bungotai_normalized",
    "check_bungotai_sync",
    "check_charter_reproducibility",
    "check_skills_structure",
    "check_skills_index_sync",
    "check_memory_index_sync",
    "check_mcp_parity_errors",
    "check_mcp_parity_warnings",
    "check_pyright",
    "check_pytest_collect",
    "check_requirements_pyproject_sync",
    "check_ruff",
    "check_genesis_acceptance",
    "check_rust_genesis_sql_sync",
    "check_rust_schema_version_pin",
    "check_scan_roots_recovery_filter",
    "check_schema_drift",
    "check_rust_compat",
    "check_scope_gate_violations",
    "check_ts",
    "check_uv_binary_pinned",
    "main",
]


def check_rust_tests() -> tuple[bool, str]:
    """Run the yu-server test suite.

    Skip 名: rust-tests

    This gate did not exist, and that is how a broken Rust test reached main:
    every other check here reads docs, formats, or structure. Nothing ran the
    tests.

    Two things had to be fixed before it could exist at all. The PDF tests bound
    to a gitignored `vendor/pdfium`, so they failed on every fresh checkout --
    a suite that is always red gates nothing; they now skip explicitly when the
    library is absent and *fail* when CI says it should be there. And
    `second_submit_returns_409_describing_the_incumbent` raced its own spawned
    job, failing roughly one run in two.
    """
    crate_dir = _REPO_ROOT / "crates"
    if not (crate_dir / "Cargo.toml").exists():
        return True, "cargo test: no crates workspace — スキップ"

    env = dict(os.environ)
    # Memory-constrained host: a wider job count has taken the OS down with it.
    env["CARGO_BUILD_JOBS"] = "2"
    result = subprocess.run(
        ["cargo", "test", "-p", "yu-server", "-j", "2", "--", "--test-threads=4"],
        cwd=crate_dir,
        capture_output=True,
        text=True,
        env=env,
    )
    failed = [
        line.split()[1]
        for line in result.stdout.splitlines()
        if line.startswith("test ") and line.rstrip().endswith("FAILED")
    ]
    if result.returncode == 0:
        totals = [l for l in result.stdout.splitlines() if l.startswith("test result")]
        return True, f"cargo test -p yu-server: {totals[0] if totals else 'ok'}"
    if failed:
        shown = "\n".join(f"    - {name}" for name in failed[:10])
        more = f"\n    (+{len(failed) - 10} more)" if len(failed) > 10 else ""
        # The names alone are not diagnosable. `real_app_state_is_inactive_...`
        # failed twice inside this gate and passed every standalone rerun, and
        # the assertion message -- the only thing that says *why* -- was being
        # discarded here. Carry the panic lines through.
        panics = [
            line.strip()
            for line in (result.stdout + "\n" + (result.stderr or "")).splitlines()
            # `... ok` lines can contain "assertion" when a test is named for
            # one, so match the panic report itself, not the progress line.
            if ("panicked at" in line)
            or line.lstrip().startswith(("assertion ", "left:", "right:"))
        ]
        detail = ""
        if panics:
            detail = "\n  失敗の詳細:\n" + "\n".join(f"    {p}" for p in panics[:12])
        return False, f"FAIL: cargo test -p yu-server ({len(failed)} failing)\n{shown}{more}{detail}"
    tail = "\n".join((result.stderr or result.stdout).strip().splitlines()[-8:])
    return False, f"FAIL: cargo test -p yu-server did not build or run\n{tail}"


def check_ai_coreutils_binary_fresh() -> tuple[bool, str]:
    """ai-coreutils ソース変更時にバイナリが再ビルドされているか検証。

    Skip 名: ai-coreutils-fresh
    修正手順:
      Windows:   pwsh -File scripts/setup-ai-tools.ps1 update
      Linux/Mac: bash scripts/setup-dev-tools.sh --update
    """
    crate_dir = _REPO_ROOT / "crates" / "ai_coreutils"
    if not crate_dir.exists():
        return True, "ai-coreutils: crate dir not found — skipped"

    # ソース変更を origin/main または HEAD~1 と比較
    changed: list[str] = []
    for base in ("origin/main", "HEAD~1"):
        rc = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", base],
            capture_output=True,
            text=True,
            cwd=_REPO_ROOT,
        )
        if rc.returncode == 0:
            changed = rc.stdout.splitlines()
            break

    crate_changed = any(f.startswith("crates/ai_coreutils/") for f in changed)
    if not crate_changed:
        return True, "ai-coreutils: no source changes — skipped"

    # インストール済みバイナリを探す（優先順: ~/.local/bin → ~/.cargo/bin）
    suffix = ".exe" if sys.platform == "win32" else ""
    ai_candidates = [
        Path.home() / ".local" / "bin" / f"ai-coreutils{suffix}",
        Path.home() / ".cargo" / "bin" / f"ai-coreutils{suffix}",
    ]
    yu_candidates = [
        Path.home() / ".local" / "bin" / f"yu{suffix}",
        Path.home() / ".cargo" / "bin" / f"yu{suffix}",
    ]
    installed_ai = [p for p in ai_candidates if p.exists()]
    installed_yu = [p for p in yu_candidates if p.exists()]
    installed = installed_ai + installed_yu

    # ソースの最新 mtime
    src_files = list(crate_dir.rglob("*.rs")) + list(crate_dir.rglob("Cargo.toml"))
    if not src_files:
        return True, "ai-coreutils: no src files found — skipped"
    newest_src_mtime = max(f.stat().st_mtime for f in src_files)

    if not installed_ai or not installed_yu:
        missing = []
        if not installed_ai:
            missing.append("ai-coreutils")
        if not installed_yu:
            missing.append("yu")
        return False, (
            f"FAIL: ai-coreutils source changed but binary not found ({', '.join(missing)}).\n"
            "  Windows:   pwsh -File scripts/setup-ai-tools.ps1 update\n"
            "  Linux/Mac: bash scripts/setup-dev-tools.sh --update"
        )

    newest_bin_mtime = max(p.stat().st_mtime for p in installed)
    if newest_src_mtime > newest_bin_mtime:
        stale = installed[0]
        return False, (
            f"FAIL: ai-coreutils source changed but binary is stale ({stale}).\n"
            "  Windows:   pwsh -File scripts/setup-ai-tools.ps1 update\n"
            "  Linux/Mac: bash scripts/setup-dev-tools.sh --update"
        )

    ver_result = subprocess.run(
        [str(installed_ai[0]), "--version"], capture_output=True, text=True
    )
    ver = (ver_result.stdout.strip() or "?").splitlines()[0]
    return True, f"ai-coreutils/yu: binaries are fresh ({ver})"


def check_bungotai_normalized() -> tuple[bool, str]:
    """bungotai-grammar.md が normalize_bungo.py の収束状態ニ在ルカ検証（read-only）。

    再正規化: uv run python .claude/scripts/normalize_bungo.py .claude/bungotai-grammar.md
    """
    source = _REPO_ROOT / ".claude" / "bungotai-grammar.md"
    if not source.exists():
        return True, "(source .claude/bungotai-grammar.md missing — skipped)"
    nb_dir = str(_REPO_ROOT / ".claude" / "scripts")
    if nb_dir not in sys.path:
        sys.path.insert(0, nb_dir)
    # .claude/scripts を実行時 sys.path 追加シテ遅延 import（stdlib ノミ・副作用ナシ）
    from normalize_bungo import normalize  # pyright: ignore[reportMissingImports]
    text = source.read_text(encoding="utf-8")
    normalized = normalize(text)  # 既定モード（--strict-headings は使わない）
    if normalized == text:
        return True, "正規化済み（収束状態）"
    diff = sum(
        1
        for a, b in zip(text.split("\n"), normalized.split("\n"), strict=False)
        if a != b
    )
    return False, (
        f"未正規化: {diff} 行ニ表記揺レ。\n"
        "  再正規化: uv run python .claude/scripts/normalize_bungo.py .claude/bungotai-grammar.md"
    )


def check_bungo_all_normalized() -> tuple[bool, str]:
    """全対象文語文書が normalize_bungo.py --all の収束状態ニ在ルカ検証。"""
    nb_dir = str(_REPO_ROOT / ".claude" / "scripts")
    if nb_dir not in sys.path:
        sys.path.insert(0, nb_dir)
    from normalize_bungo import _all_targets, normalize  # pyright: ignore[reportMissingImports]

    targets = _all_targets()
    changed: list[str] = []
    for path in targets:
        text = path.read_text(encoding="utf-8")
        if normalize(text) != text:
            changed.append(str(path.relative_to(_REPO_ROOT)))
    if changed:
        detail = "\n".join(f"  {p}" for p in changed)
        return False, (
            "未正規化ファイル:\n"
            f"{detail}\n"
            "  再正規化: uv run python .claude/scripts/normalize_bungo.py --all"
        )
    return True, f"全文語文書 正規化済み（{len(targets)} ファイル収束）"


def check_bungo_katakana_baseline() -> tuple[bool, str]:
    """カタカナ語 baseline ニ無キ新規 signature ガ無イカ検証。"""
    nb_dir = str(_REPO_ROOT / ".claude" / "scripts")
    if nb_dir not in sys.path:
        sys.path.insert(0, nb_dir)
    from normalize_bungo import (  # pyright: ignore[reportMissingImports]
        _all_targets,
        collect_katakana_signatures,
    )

    baseline_path = _REPO_ROOT / ".claude" / "bungo-katakana-baseline.json"
    if not baseline_path.exists():
        return True, "(baseline 未生成 — skipped)"
    data = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline = set(data.get("signatures", []))
    current = collect_katakana_signatures(_all_targets())
    new_signatures = sorted(current - baseline)
    if new_signatures:
        detail = "\n".join(f"  {sig}" for sig in new_signatures)
        return False, (
            "新規カタカナ語:\n"
            f"{detail}\n"
            "  baseline 更新: uv run python .claude/scripts/normalize_bungo.py --update-baseline --all"
        )
    return True, f"新規カタカナ語ナシ（baseline {len(baseline)} 件）"


_SEMGREP_TEST_SUMMARY = re.compile(r"(\d+)/(\d+):\s*.?\s*All tests passed")


def _count_semgrep_rules(rules_dir: Path) -> int:
    """Count `- id:` entries across the rule files, without a YAML parser."""
    total = 0
    for path in sorted(rules_dir.glob("*.yaml")) + sorted(rules_dir.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.match(r"^\s*-\s+id:\s*\S", line):
                total += 1
    return total


def _semgrep_local_rules_self_test(rules_dir: Path) -> tuple[bool, str]:
    """Verify the local semgrep rules still match their fixtures.

    `semgrep --test` EXITS 0 EVEN WHEN TESTS FAIL. Measured on 1.175.0: a rule
    whose pattern was deliberately broken printed "Found rule id mismatch ...
    Failing due to rule id mismatch" and returned 0, and `--test --json` prints
    the same prose with no JSON at all. Checking the return code -- the obvious
    way to write this -- reports PASS for a rule set that matches nothing, which
    is indistinguishable from a clean tree and would stay green forever.

    So the verdict is read from the summary line, and the pass count is required
    to equal the number of rules on disk. Requiring the count is what catches the
    other direction: a rule added without a fixture would otherwise pass as
    "1/1 tests passed" while the new rule is never exercised.
    """
    try:
        # Run from inside .semgrep/: semgrep pairs a rule file with the
        # same-named fixture file, and only resolves that pairing when the
        # scanning root is the rules directory itself.
        proc = subprocess.run(
            ["semgrep", "--test", "."],
            capture_output=True, text=True, cwd=rules_dir, timeout=120,
        )
    except subprocess.TimeoutExpired:
        return True, "semgrep rule self-test timed out (skipping)"
    except Exception as e:
        return True, f"semgrep rule self-test failed to run (skipping): {e}"

    output = (proc.stdout + proc.stderr).strip()
    match = _SEMGREP_TEST_SUMMARY.search(output)
    if not match:
        return False, (
            "semgrep local rule self-test FAILED (no passing summary in output):\n"
            f"{output[-2000:]}"
        )
    passed, total = int(match.group(1)), int(match.group(2))
    expected = _count_semgrep_rules(rules_dir)
    if passed != total or total == 0:
        return False, f"semgrep local rule self-test FAILED ({passed}/{total}):\n{output[-2000:]}"
    if total != expected:
        return False, (
            f"semgrep local rule self-test covered {total} rule(s) but {expected} are "
            f"defined in {rules_dir.name}/. Every rule needs a fixture in the matching "
            "`.py` file, or it ships unverified."
        )
    return True, f"semgrep local rules: {passed}/{total} verified"


def check_semgrep() -> tuple[bool, str]:
    """Run semgrep on changed Python files (p/python + p/secrets + local rules).

    Advisory when semgrep is not installed; FAIL on actual findings.
    Install: uv tool install semgrep

    `.semgrep/` holds rules for conventions the registry packs cannot know about
    -- the User-Agent requirement on outbound requests, and numeric parameters
    re-defaulted with `or` so that 0 is silently replaced. Its own fixtures are
    verified first: a rule file that stops matching is indistinguishable from a
    clean tree, so a broken rule would report PASS forever.
    """
    import shutil
    if not shutil.which("semgrep"):
        return True, "semgrep not found — skipped (install: uv tool install semgrep)"

    local_rules = _REPO_ROOT / ".semgrep"
    if local_rules.is_dir():
        ok, message = _semgrep_local_rules_self_test(local_rules)
        if not ok:
            return False, message

    files = changed_py_files()
    if not files:
        return True, "No changed Python files"
    targets = [str(_REPO_ROOT / f) for f in files if (_REPO_ROOT / f).exists()]
    if not targets:
        return True, "No changed Python files on disk"

    cmd = [
        "semgrep", "scan",
        "--config=p/python", "--config=p/secrets",
        *(["--config=.semgrep/"] if local_rules.is_dir() else []),
        "--error", "--quiet", "--no-autofix",
        *targets,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=_REPO_ROOT,
                                timeout=60)
    except subprocess.TimeoutExpired:
        return True, "semgrep timed out (skipping — check network/registry)"
    except Exception as e:
        return True, f"semgrep execution failed (skipping): {e}"

    output = (result.stdout + result.stderr).strip()
    if result.returncode == 0:
        return True, f"semgrep clean ({len(targets)} file(s))"
    if result.returncode == 1:
        return False, f"semgrep findings:\n{output}"
    # exit 2+: only skip if output confirms a network/registry transient failure.
    # Config errors, crashes, invalid patterns → FAIL to surface real problems.
    _NETWORK_PATTERNS = (
        "connection refused", "network unreachable", "failed to fetch",
        "could not connect", "ssl", "timeout", "registry", "unreachable",
        "name or service not known", "temporary failure",
    )
    if any(p in output.lower() for p in _NETWORK_PATTERNS):
        return True, f"semgrep network/registry error (exit {result.returncode}, skipping):\n{output[:400]}"
    return False, f"semgrep error (exit {result.returncode}):\n{output[:400]}"


def check_bungotai_sync() -> tuple[bool, str]:
    """bungotai-grammar.md と生成 YAML の sha256 同期検証（spec 第 2.4.3 節）。"""
    source = _REPO_ROOT / ".claude" / "bungotai-grammar.md"
    artifact = _REPO_ROOT / ".claude" / "bungotai-grammar.yaml"
    if not source.exists():
        return True, "(source .claude/bungotai-grammar.md missing — skipped)"
    if not artifact.exists():
        # source が在るのに artifact が無い → 削除か生成漏れ → FAIL
        return False, "artifact .claude/bungotai-grammar.yaml missing — run: uv run python scripts/gen_bungotai_yaml.py"
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from gen_bungotai_yaml import verify_sync  # 遅延 import（read-only）
    return verify_sync(source, artifact)


def check_skills_index_sync() -> tuple[bool, str]:
    """skills-index.yaml と .claude/commands/*.md 群の sha256 同期検証。

    再生成: uv run python scripts/gen_skills_index.py
    """
    source_dir = _REPO_ROOT / ".claude" / "commands"
    artifact = _REPO_ROOT / ".claude" / "skills-index.yaml"
    if not source_dir.exists() or not any(source_dir.glob("*.md")):
        return True, "(source_dir .claude/commands/ missing or empty — skipped)"
    if not artifact.exists():
        # commands/ に .md があるのに artifact が無い → FAIL
        return False, "artifact .claude/skills-index.yaml missing — run: uv run python scripts/gen_skills_index.py"
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from gen_skills_index import verify_sync as _verify  # 遅延 import（read-only）
    return _verify(source_dir, artifact)


def check_skills_structure() -> tuple[bool, str]:
    """Validate .claude/commands/*.md structural health."""
    source_dir = _REPO_ROOT / ".claude" / "commands"
    if not source_dir.exists() or not any(source_dir.glob("*.md")):
        return True, "(source_dir .claude/commands/ missing or empty — skipped)"
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from check_skills import validate  # 遅延 import（read-only）

    ok, problems = validate(source_dir)
    if ok:
        count = len(list(source_dir.glob("*.md")))
        return True, f"skills 構造 OK（{count} 件）"
    return False, "\n".join(problems) + "\n修正後再 push スベシ"


def check_skills_yaml_structure() -> tuple[bool, str]:
    """スキル YAML ファイルの必須フィールド検証と索引整合チェック。

    再生成: uv run python scripts/gen_skills_index.py
    """
    yaml_dir = _REPO_ROOT / ".claude" / "commands" / "yaml"
    if not yaml_dir.exists():
        return True, "(yaml_dir .claude/commands/yaml/ missing — skipped)"
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from check_skills_yaml import validate_index_consistency, validate_yaml_skills  # 遅延 import

    ok1, problems1 = validate_yaml_skills(yaml_dir)
    ok2, problems2 = validate_index_consistency()

    all_ok = ok1 and ok2
    all_problems = problems1 + problems2

    if all_ok:
        count = sum(1 for p in yaml_dir.glob("*.yaml") if p.name != "_schema.yaml")
        return True, f"skills YAML 構造 OK（{count} 件）・索引整合 OK"
    return False, "\n".join(all_problems) + "\n修正後再 push スベシ"


def check_scope_fence_presets_golden_sync() -> tuple[bool, str]:
    """Rust Scope Fence の drift-guard テストが参照する golden fixture が
    Python core/agent_safety/scope_fence.py::PRESETS と同期しているか検証する。

    再生成: uv run python scripts/gen_scope_fence_presets_golden.py
    """
    import json

    fixture = _REPO_ROOT / "crates" / "yu-server" / "tests" / "fixtures" / "scope_fence_presets_golden.json"
    if not fixture.exists():
        return True, "(fixture missing — skipped)"

    try:
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        from core.agent_safety.scope_fence import PRESETS
    except Exception as e:
        return True, f"(scope_fence import failed — skipped: {e})"

    expected = {preset: data["denied"] for preset, data in PRESETS.items()}
    try:
        actual = json.loads(fixture.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"golden fixture unreadable: {e}"

    if actual != expected:
        return False, (
            "scope_fence_presets_golden.json drifted from Python PRESETS.\n"
            "  再生成: uv run python scripts/gen_scope_fence_presets_golden.py"
        )
    return True, "[scope-fence-golden] 同期 OK"


def check_charter_reproducibility() -> tuple[bool, str]:
    """doc-format-charter の再現性を5ステップで検証する（V-3）。

    再生成: uv run python scripts/build_charter_yaml.py
    """
    import importlib
    import subprocess
    import tempfile

    source = _REPO_ROOT / ".claude" / "doc-format-charter.md"
    artifact = _REPO_ROOT / ".claude" / "doc-format-charter.yaml"
    script = _REPO_ROOT / "scripts" / "build_charter_yaml.py"

    if not source.exists():
        return True, "(source .claude/doc-format-charter.md missing — skipped)"
    if not artifact.exists():
        return False, "artifact .claude/doc-format-charter.yaml missing — run: uv run python scripts/build_charter_yaml.py"

    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    bcy = importlib.import_module("build_charter_yaml")

    try:
        obj = yaml.safe_load(artifact.read_text(encoding="utf-8")) or {}
    except Exception as e:
        return False, f"artifact parse error: {e}"
    meta = obj.get("meta") or {}

    # Step 2: grammar_version 文字列の一致確認
    recorded_gv = meta.get("grammar_version")
    if recorded_gv != bcy.GRAMMAR_VERSION:
        return False, (
            f"grammar_version 不一致: artifact={recorded_gv!r}, "
            f"script={bcy.GRAMMAR_VERSION!r}\n"
            f"  再生成: uv run python scripts/build_charter_yaml.py"
        )

    # Step 3: grammar_content_sha256（parser ソース hash）の一致確認
    current_grammar_hash = hashlib.sha256(script.read_bytes()).hexdigest()
    recorded_grammar_hash = meta.get("grammar_content_sha256")
    if recorded_grammar_hash != current_grammar_hash:
        return False, (
            f"grammar_content_sha256 不一致: parser ソースが変更されたのに yaml が未再生成\n"
            f"  recorded: {recorded_grammar_hash}\n"
            f"  current:  {current_grammar_hash}\n"
            f"  再生成: uv run python scripts/build_charter_yaml.py"
        )

    # Step 4: source_sha256（md hash）の一致確認
    ok, msg = bcy.verify_sync(source, artifact)
    if not ok:
        return False, msg

    # Step 5/6: 再実行して yml_content_sha256 を照合
    import contextlib
    import os as _os
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as tf:
        tmp_path = tf.name
    try:
        result = subprocess.run(
            [sys.executable, str(script), "--out", tmp_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            return False, f"build_charter_yaml.py 再実行失敗:\n{result.stderr}"
        with open(tmp_path, encoding="utf-8") as _f:
            regen = yaml.safe_load(_f) or {}
    finally:
        with contextlib.suppress(OSError):
            _os.unlink(tmp_path)

    regen_hash = (regen.get("meta") or {}).get("yml_content_sha256")
    recorded_hash = meta.get("yml_content_sha256")
    if regen_hash != recorded_hash:
        return False, (
            f"yml_content_sha256 不一致: yaml の内容が変わっているのに再生成されていない\n"
            f"  recorded: {recorded_hash}\n"
            f"  regen:    {regen_hash}\n"
            f"  再生成: uv run python scripts/build_charter_yaml.py"
        )

    return True, "[charter-yaml] 同期 OK"


def _check_charter_validators() -> tuple[bool, str]:
    """V-1a / V-1c / V-1b / V-4 を charter yaml に対して実行する。"""
    import importlib

    artifact = _REPO_ROOT / ".claude" / "doc-format-charter.yaml"
    if not artifact.exists():
        return True, "(artifact missing — skipped)"

    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    cv = importlib.import_module("charter_validators")

    # V-1c は V-1b の前提。V-1c が失敗したら V-1b をスキップしてショートサーキットする
    # （V-1c 失敗時に V-1b を呼ぶと文字列ガードで TypeError が発生する）。
    v1c_ok, v1c_msg = cv.check_guard_conformance(artifact)
    if not v1c_ok:
        return False, f"charter validators FAIL:\n  V-1c: {v1c_msg}"

    checks = [
        ("V-1a", cv.check_default_arms(artifact)),
        ("V-1b", cv.check_guard_inclusion(artifact)),
        ("V-4",  cv.check_rationale_refs(artifact, _REPO_ROOT)),
    ]
    failures = [(name, msg) for name, (ok, msg) in checks if not ok]
    warnings = [(name, msg) for name, (ok, msg) in checks if ok and msg and "WARNING" in msg]

    if warnings:
        for name, msg in warnings:
            print(f"  {name}: {msg}")
    if failures:
        detail = "\n".join(f"  {name}: {msg}" for name, msg in failures)
        return False, f"charter validators FAIL:\n{detail}"
    return True, "charter validators OK"


def _check_charter_stranded_procedures() -> tuple[bool, str]:
    """V-2: stranded-procedure lint（warning のみ）。"""
    import importlib

    source = _REPO_ROOT / ".claude" / "doc-format-charter.md"
    artifact = _REPO_ROOT / ".claude" / "doc-format-charter.yaml"
    if not source.exists() or not artifact.exists():
        return True, "(source/artifact missing — skipped)"

    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    cv = importlib.import_module("charter_validators")

    msg = cv.check_stranded_procedures(source, artifact)[1]
    if msg:
        print(f"  {msg}")
    return True, "V-2: " + ("warning emitted" if msg else "OK")


def check_memory_index_sync() -> tuple[bool, str]:
    """Verify local memory to docs/development links without writing files.

    Regenerate: uv run python scripts/gen_memory_index.py
    Spec: docs/superpowers/specs/2026-05-31-memory-docs-sync.md
    """
    scripts_dir = str(_REPO_ROOT / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from gen_memory_index import (  # type: ignore[import-not-found]
        read_node_id,
        resolve_memory_dir,
        verify_sync,
    )

    memory_dir = resolve_memory_dir(_REPO_ROOT)
    node_id = read_node_id(_REPO_ROOT)
    return verify_sync(memory_dir, _REPO_ROOT, node_id)


def check_new_route_openapi_coverage() -> tuple[bool, str]:
    """Warn when a diff adds @bp.route / @app.route without register_endpoint in the same file.

    File-level matching avoids url_prefix complexity (llm_router /v1, gateway_admin /api/gateway).
    Known gap: two routes added + one register_endpoint in the same file won't be detected.
    Skip with PRE_PUSH_SKIP=openapi-new-routes or --skip openapi-new-routes.
    Warning only — never blocks push.
    """
    import os as _os
    skip_env = _os.environ.get("PRE_PUSH_SKIP", "")
    if "openapi-new-routes" in {s.strip() for s in skip_env.split(",")}:
        return True, "openapi-new-routes skipped (PRE_PUSH_SKIP)"

    for base in ("origin/main...HEAD", "HEAD~1"):
        proc = subprocess.run(
            ["git", "diff", "--unified=0", base, "--", "*.py"],
            capture_output=True, text=True, cwd=_REPO_ROOT,
        )
        if proc.returncode == 0:
            diff_text = proc.stdout
            break
    else:
        return True, "(could not get diff — skipped)"

    # Parse diff into per-file added-line sets
    file_added: dict[str, list[str]] = {}
    current_file: str | None = None
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
            file_added.setdefault(current_file, [])
        elif line.startswith("+") and not line.startswith("+++") and current_file:
            file_added[current_file].append(line[1:])

    _ROUTE_RE = re.compile(r"@(?:bp|app)\.route\s*\(")
    _REG_RE = re.compile(r"\bregister_endpoint\s*\(")

    warnings: list[str] = []
    for filepath, added_lines in file_added.items():
        # Only check routes/ and core/ Python files; skip extensions/
        if not filepath.endswith(".py"):
            continue
        if filepath.startswith("extensions/"):
            continue
        has_new_route = any(_ROUTE_RE.search(ln) for ln in added_lines)
        has_register = any(_REG_RE.search(ln) for ln in added_lines)
        if has_new_route and not has_register:
            warnings.append(f"  {filepath}")

    if warnings:
        detail = "\n".join(warnings)
        return True, (
            f"⚠ OpenAPI 未登録の新規ルートの疑い ({len(warnings)} ファイル) — "
            "register_endpoint() を追加するか PRE_PUSH_SKIP=openapi-new-routes でスキップ:\n"
            + detail
        )
    return True, "openapi-new-routes: 未登録ルート無し"


def check_no_rust_proxy_calls() -> tuple[bool, str]:
    """Rust route handler が fwd_get/post/put/delete を呼んでいないことを確認する。"""
    import re

    call_re = re.compile(r"\bfwd_(get|post|put|delete)\(")
    def_re = re.compile(r"\bfn\s+fwd_")
    # テストコード内の変数代入（let response = fwd_...）は除外
    test_assign_re = re.compile(r"\blet\s+\w+\s*=\s*fwd_")
    routes_dir = _REPO_ROOT / "crates" / "yu-server" / "src" / "routes"
    violations: list[str] = []
    for rs_file in sorted(routes_dir.rglob("*.rs")):
        for i, line in enumerate(rs_file.read_text(encoding="utf-8").splitlines(), 1):
            if call_re.search(line) and not def_re.search(line) and not test_assign_re.search(line) and "no-rust-proxy-calls" not in line:
                violations.append(f"  {rs_file.relative_to(_REPO_ROOT)}:{i}: {line.strip()}")
    if violations:
        return False, "Python proxy calls found (replace with 501 stub):\n" + "\n".join(violations)
    return True, "No proxy calls in route handlers."


def check_python_forwarder_ratchet() -> tuple[bool, str]:
    """Freeze the set of handlers that still forward to Python; it may only shrink."""
    try:
        from scripts.internal.rust_python_forwarders import check as _check
    except ImportError:
        from internal.rust_python_forwarders import check as _check  # type: ignore[no-redef]
    return _check()


def check_portfolio_forwarder_count() -> tuple[bool, str]:
    """The count written in MIGRATION_PORTFOLIO_STATUS.md must be the measured one.

    Skip 名: portfolio-forwarder-count

    The doc's own rule is "update this book whenever the source of truth moves",
    and the doc broke it: it said 28 for 51 versions while the measured file went
    to 7. A number restated in prose next to a gate is not protected by that gate
    -- so this one is.

    The doc marks the line with `<!-- gate:forwarder-count -->`; the first
    ``N 件`` after the marker is compared with the non-comment line count of
    docs/development/rust-python-forwarders.txt.
    """
    doc = _REPO_ROOT / "docs" / "development" / "development_docs" / "MIGRATION_PORTFOLIO_STATUS.md"
    measured_file = _REPO_ROOT / "docs" / "development" / "rust-python-forwarders.txt"
    if not doc.exists() or not measured_file.exists():
        return True, "portfolio-forwarder-count: 対象ファイル無シ — スキップ"

    measured = sum(
        1
        for line in measured_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )

    text = doc.read_text(encoding="utf-8")
    marker = "<!-- gate:forwarder-count -->"
    if marker not in text:
        return False, (
            f"FAIL: {doc.name} に {marker} が無い。\n"
            "  この marker が数字の在処を示す。消すとこの門は数えるものを失う。"
        )
    after = text.split(marker, 1)[1]
    match = re.search(r"(\d+)\s*件", after)
    if match is None:
        return False, f"FAIL: {doc.name} の {marker} の直後に「N 件」が無い。"
    claimed = int(match.group(1))
    if claimed != measured:
        return False, (
            f"FAIL: {doc.name} は {claimed} 件と書くが、"
            f"rust-python-forwarders.txt の実測は {measured} 件。\n"
            "  どちらかが古い。実測を正としてドキュメントを直すこと。"
        )
    return True, f"portfolio-forwarder-count: {measured} 件で一致"


def check_config_read_format() -> tuple[bool, str]:
    try:
        from scripts.internal.config_read_format import check as check
    except ImportError:
        from internal.config_read_format import check as check  # type: ignore[no-redef]
    return check()


def check_crate_include_paths() -> tuple[bool, str]:
    try:
        from scripts.internal.crate_include_paths import check as check
    except ImportError:
        from internal.crate_include_paths import check as check  # type: ignore[no-redef]
    return check()


def check_crate_escapes_root() -> tuple[bool, str]:
    try:
        from scripts.internal.crate_escapes_root import check
    except ImportError:
        from internal.crate_escapes_root import check  # type: ignore[no-redef]
    return check()


def check_sse_kind_parity() -> tuple[bool, str]:
    try:
        from scripts.internal.sse_kind_parity import check_sse_kind_parity as check
    except ImportError:
        from internal.sse_kind_parity import check_sse_kind_parity as check  # type: ignore[no-redef]
    return check()


def check_ruff_ratchet() -> tuple[bool, str]:
    try:
        from scripts.internal.ruff_ratchet import check
    except ImportError:
        from internal.ruff_ratchet import check  # type: ignore[no-redef]
    return check()


def check_public_leaks() -> tuple[bool, str]:
    try:
        from scripts.internal.audit_public_leaks import check
    except ImportError:
        from internal.audit_public_leaks import check  # type: ignore[no-redef]
    return check()


def check_eslint_ratchet() -> tuple[bool, str]:
    try:
        from scripts.internal.eslint_ratchet import check
    except ImportError:
        from internal.eslint_ratchet import check  # type: ignore[no-redef]
    return check()


def check_parity_relaxations() -> tuple[bool, str]:
    try:
        from scripts.internal.parity_relaxation_ratchet import check
    except ImportError:
        from internal.parity_relaxation_ratchet import check  # type: ignore[no-redef]
    return check()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Scan full tree for pyright too")
    parser.add_argument("--skip", default="", help="Comma-separated: githooks-path,ruff,ts,pyright,async-route-io,db-write-rule,i18n,pytest,scan-roots-recovery-filter,schema-drift,genesis-sql-sync,schema-version-pin,genesis-acceptance,uv-pin,reqs-sync,doc-index-v2,feature-index,dev-overview,settings-schema,agents-md,bat-bom,ps1-bom,feature-parity,scope-gate,mcp-parity-errors,mcp-parity-warnings,bungotai-normalize,bungo-all-normalize,bungo-katakana,bungotai-sync,scope-fence-golden,charter-sync,charter-validators,charter-stranded,skills-structure,skills-index-sync,memory-index-sync,rationale-ref,pair-completeness,dup-rationale-ref,structural-validators,sse-kind-parity,openapi-new-routes,semgrep,ai-coreutils-fresh,rust-tests,rust-fmt,rust-compat,rust-standalone-build,lan-cowork-clippy,lan-cowork-schema-contract,lan-cowork-mirror-drift,parity-allowlist-sync,extension-contract-sync,no-rust-proxy-calls,python-forwarder-ratchet,parity-relaxations,ruff-ratchet,eslint-ratchet,public-leaks,native-only-endpoints,crate-include-paths,crate-escapes-root,config-read-format,portfolio-forwarder-count")
    args = parser.parse_args()
    skip = {item.strip() for item in args.skip.split(",") if item.strip()}

    files = ["core", "extensions", "routes", "mcp_server"] if args.all else changed_py_files()

    checks: list[tuple[str, Callable[[], tuple[bool, str]]]] = []
    if "githooks-path" not in skip:
        checks.append(("git hooks installed (core.hooksPath)", check_githooks_installed))
    if "ruff" not in skip:
        checks.append(("ruff F821/F811/F405/E9", check_ruff))
    if "ts" not in skip:
        checks.append(("tsc --noEmit", check_ts))
    if "pyright" not in skip:
        checks.append((f"pyright ({len(files)} path(s))", lambda: check_pyright(files)))
    if "async-route-io" not in skip:
        checks.append((f"async route sync-I/O ({len(files)} path(s))", lambda: check_async_route_sync_io(files)))
    if "db-write-rule" not in skip:
        checks.append((f"db write rule §3.2 ({len(files)} path(s))", lambda: check_db_write_rule(files)))
    if "i18n" not in skip:
        checks.append(("i18n key drift", check_i18n_key_drift))
    if "pytest" not in skip:
        checks.append(("pytest --collect-only", check_pytest_collect))
    if "scan-roots-recovery-filter" not in skip:
        checks.append((
            "scan_roots recovery broad-root filter (actually run, not just collected)",
            check_scan_roots_recovery_filter,
        ))
    if "schema-drift" not in skip:
        checks.append(("schema drift (BASE ↔ migration tail)", check_schema_drift))
    if "genesis-sql-sync" not in skip:
        checks.append(("Rust genesis SQL ↔ generator", check_rust_genesis_sql_sync))
    if "schema-version-pin" not in skip:
        checks.append(("schema version pin (Python ↔ Rust ↔ genesis file)", check_rust_schema_version_pin))
    if "genesis-acceptance" not in skip:
        checks.append(("standalone genesis acceptance (real boot)", check_genesis_acceptance))
    if "uv-pin" not in skip:
        checks.append(("uv binary pin (bin/uv ↔ scripts/uv-checksums.txt)", check_uv_binary_pinned))
    if "reqs-sync" not in skip:
        checks.append(("requirements.txt ↔ pyproject [project].dependencies", check_requirements_pyproject_sync))
    if "doc-index-v2" not in skip:
        checks.append(("dev-docs-index.yaml v2 sync", check_index_v2_sync))
    if "feature-index" not in skip:
        checks.append(("FEATURES.md sync", check_feature_index_sync))
    if "rationale-ref" not in skip:
        checks.append(("rationale_ref resolution", check_rationale_ref_resolution))
    if "pair-completeness" not in skip:
        checks.append(("pair completeness (doc_type:paired ↔ criteria yaml)", check_pair_completeness))
    if "dup-rationale-ref" not in skip:
        checks.append(("rationale_ref uniqueness (1:1)", check_no_duplicate_rationale_refs))
    if "structural-validators" not in skip:
        checks.append(("structural validators (doc-format-check)", check_structural_validators))
    if "sse-kind-parity" not in skip:
        checks.append(("SSE event kind parity", check_sse_kind_parity))
    if "version-sync" not in skip:
        checks.append(("VERSION ↔ package.json/Cargo sync", check_version_sync))
    if "dev-overview" not in skip:
        checks.append(("dev-overview.json sync", check_dev_overview_sync))
    if "settings-schema" not in skip:
        checks.append(("settings_schema.json sync", check_settings_schema_sync))
    if "fast-mode-inert" not in skip:
        checks.append(("fast mode inert when disabled", check_fast_mode_inert))
    if "agents-md" not in skip:
        checks.append(("AGENTS.md ↔ CLAUDE.md sync", check_agents_md_sync))
    if "ps1-bom" not in skip:
        checks.append(("ps1 UTF-8 BOM", check_ps1_bom))
    if "bat-bom" not in skip:
        checks.append(("bat UTF-8 BOM", check_bat_bom))
    if "feature-parity" not in skip:
        checks.append(("feature parity (API/MCP/WebUI)", check_feature_parity))
    if "scope-gate" not in skip:
        checks.append(("scope gate violations (extensions/**/*.py)", check_scope_gate_violations))
    if "bundled-extensions-manifest" not in skip:
        checks.append(("bundled extensions manifest", check_bundled_extensions_manifest))
    if "mcp-parity-errors" not in skip:
        checks.append(("MCP parity — broken route refs (ERROR)", check_mcp_parity_errors))
    if "mcp-parity-warnings" not in skip:
        checks.append(("MCP parity — uncovered routes (WARNING)", check_mcp_parity_warnings))
    if "bungotai-normalize" not in skip:
        checks.append(("bungotai-grammar.md normalize (片仮名文語収束)", check_bungotai_normalized))
    if "bungo-all-normalize" not in skip:
        checks.append(("全文語文書 normalize (--all 収束)", check_bungo_all_normalized))
    if "bungo-katakana" not in skip:
        checks.append(("カタカナ語 baseline (新規検出)", check_bungo_katakana_baseline))
    if "bungotai-sync" not in skip:
        checks.append(("bungotai-grammar.md ↔ .yaml sync (sha256)", check_bungotai_sync))
    if "scope-fence-golden" not in skip:
        checks.append(("scope-fence presets golden ↔ Python PRESETS sync", check_scope_fence_presets_golden_sync))
    if "charter-sync" not in skip:
        checks.append(("doc-format-charter.md ↔ .yaml sync (sha256)", check_charter_reproducibility))
    if "charter-validators" not in skip:
        checks.append(("charter structural validators (V-1/V-4)", _check_charter_validators))
    if "charter-stranded" not in skip:
        checks.append(("charter stranded-procedure lint (V-2)", _check_charter_stranded_procedures))
    if "skills-structure" not in skip:
        checks.append(("skills 構造 validator", check_skills_structure))
    if "skills-yaml-structure" not in skip:
        checks.append(("skills YAML 構造 validator + 索引整合", check_skills_yaml_structure))
    if "skills-index-sync" not in skip:
        checks.append(("skills-index.yaml ↔ skills/*.md sync (sha256)", check_skills_index_sync))
    if "memory-index-sync" not in skip:
        checks.append(("memory-docs sync (対応漏れ)", check_memory_index_sync))
    if "openapi-new-routes" not in skip:
        checks.append(("OpenAPI 新規ルート登録 (WARNING)", check_new_route_openapi_coverage))
    if "no-rust-proxy-calls" not in skip:
        checks.append(("Rust proxy calls (fwd_* in handlers)", check_no_rust_proxy_calls))
    if "python-forwarder-ratchet" not in skip:
        checks.append(
            ("Python forwarder ratchet (may only shrink)", check_python_forwarder_ratchet)
        )
    if "parity-relaxations" not in skip:
        checks.append(
            ("parity relaxation ratchet (may only shrink)", check_parity_relaxations)
        )
    if "ruff-ratchet" not in skip:
        checks.append(("ruff ratchet (S/ASYNC/DTZ, may only shrink)", check_ruff_ratchet))
    if "eslint-ratchet" not in skip:
        checks.append(("eslint ratchet (TS/JS, may only shrink)", check_eslint_ratchet))
    if "public-leaks" not in skip:
        checks.append(("private identifiers in the public release set", check_public_leaks))
    if "native-only-endpoints" not in skip:
        try:
            from scripts.check_native_only_endpoints import check as check_native_only_endpoints
        except ImportError:
            from check_native_only_endpoints import check as check_native_only_endpoints
        checks.append(("native-only endpoint manifest drift", check_native_only_endpoints))
    if "crate-include-paths" not in skip:
        checks.append(("yu-server crate include paths", check_crate_include_paths))
    if "crate-escapes-root" not in skip:
        checks.append(("crate paths stay inside CARGO_MANIFEST_DIR", check_crate_escapes_root))
    # Always on: what this catches is a number in prose, which no changed-path
    # predicate can see going stale.
    if "portfolio-forwarder-count" not in skip:
        checks.append(
            ("portfolio doc ↔ forwarder count", check_portfolio_forwarder_count)
        )
    if "config-read-format" not in skip:
        checks.append(("config read format", check_config_read_format))
    if "semgrep" not in skip:
        checks.append((f"semgrep p/python+p/secrets ({len(files)} file(s))", check_semgrep))
    if "ai-coreutils-fresh" not in skip:
        checks.append(("ai-coreutils binary fresh", check_ai_coreutils_binary_fresh))
    _changed_names = ""
    for _base in ("origin/main", "HEAD~1"):
        _rc, _names = run_command(["git", "diff", "--name-only", "--diff-filter=ACMR", _base])
        if _rc == 0:
            _changed_names = _names
            break
    _changed_files = _changed_names.splitlines()
    # Live parity covers native route behavior; shared auth and build code use
    # their focused unit tests instead of host-dependent full-route comparison.
    _rust_changed = any(
        f.startswith("crates/yu-server/src/routes/")
        or f == "crates/yu-server/src/main.rs"
        or f.startswith("routes/")
        # The parity TABLE itself. Editing an entry -- adding a route, widening
        # `accept_statuses`, promoting one out of `skip` -- changes what the
        # suite asserts, and until v4.689.5 that landed without the suite ever
        # running. A gate whose own configuration is outside its trigger is a
        # gate you can turn off by editing it.
        or f == "scripts/verify_rust_compat.py"
        for f in _changed_files
    )
    _inputs_changed = any(
        "compat_goldens/" in f
        or "parity_allowlist_sync" in f
        or f == "docs/development/rust-migration-inventory.yaml"
        for f in _changed_files
    )
    # Always on: no changed-path predicate. The miss this gate exists to catch
    # was caused by a predicate that never named crates/lan-cowork.
    # Always on. Formatting drift is invisible to a changed-path predicate --
    # the 13 files this caught were last touched across many commits, and the
    # only thing that reported them was the public mirror's CI, after publish.
    if "rust-fmt" not in skip:
        checks.append(("rust fmt (crates/)", check_rust_fmt))
    if "lan-cowork-clippy" not in skip:
        checks.append(("rust clippy (workspace, + ratchet)", check_lan_cowork_clippy))
    # Always on, same reasoning as the clippy gate: the drift this catches is
    # invisible to a changed-path predicate (core schema and the crate move apart).
    if "lan-cowork-schema-contract" not in skip:
        checks.append(
            ("lan-cowork ↔ core schema contract", check_lan_cowork_schema_contract)
        )
    # Always on: what this catches lives between two repos, so no changed-path
    # predicate in this one can see it. `crates/Cargo.toml` is not enough of a
    # trigger either — the pin can go stale without this repo changing at all.
    if "lan-cowork-pin" not in skip:
        checks.append(
            ("lan-cowork pinned rev is public", check_lan_cowork_pinned_rev_public)
        )
    if "rust-compat" not in skip and _rust_changed:
        checks.append(("rust↔python native route parity", check_rust_compat))
    # Any crates/ change, not just routes/: the suite covers logs/, ocr/, jobs/
    # and the rest, and a predicate narrower than the thing it guards is how the
    # lan-cowork gate got missed.
    _crates_changed = any(f.startswith("crates/") for f in _changed_files)
    if "rust-tests" not in skip and _crates_changed:
        checks.append(("cargo test -p yu-server", check_rust_tests))
    if "rust-standalone-build" not in skip and _rust_changed:
        checks.append(("Rust standalone build (--no-default-features)", check_rust_standalone_build))
    if "parity-allowlist-sync" not in skip and (_rust_changed or _inputs_changed):
        sys.path.insert(0, str(_REPO_ROOT / "scripts" / "internal"))
        from parity_allowlist_sync import check_sync as _check_allowlist_sync

        def _check_parity_allowlist_sync() -> tuple[bool, str]:
            return _check_allowlist_sync()

        checks.append(("parity allowlist ↔ inventory sync", _check_parity_allowlist_sync))

    # The OCR capability scores live in three places (router.py's
    # _DEFAULT_CAPABILITIES, routes/ocr.rs's builtin_ocr_profiles, ocr/router.rs's
    # BUILTIN_SCORES). Nothing in the build makes them agree, and a divergence
    # only shows up as "the wrong VLM was chosen" at runtime.
    _ocr_score_files = (
        "extensions/builtin_ocr/core_impl/router.py",
        "crates/yu-server/src/routes/ocr.rs",
        "crates/yu-server/src/ocr/router.rs",
    )
    if "ocr-score-tables" not in skip and any(
        f in _ocr_score_files for f in _changed_files
    ):

        def _check_ocr_score_tables() -> tuple[bool, str]:
            proc = subprocess.run(
                [sys.executable, str(_REPO_ROOT / "scripts" / "check_ocr_score_tables.py")],
                capture_output=True,
                text=True,
                cwd=_REPO_ROOT,
            )
            output = (proc.stdout + proc.stderr).strip()
            # Exit 2 means the checker could not read a table -- that is a
            # broken checker, not a clean run. Reporting it as a pass would
            # make the gate silently blind.
            if proc.returncode == 2:
                return False, f"checker could not read a score table:\n{output}"
            return proc.returncode == 0, output

        checks.append(("OCR capability score tables (py ↔ rust)", _check_ocr_score_tables))

    _ext_changed = any(
        f.startswith("extensions/") or f.startswith("crates/yu-server/src/routes/")
        or f.startswith("tests/parity/")
        for f in _changed_files
    )
    if "extension-contract-sync" not in skip and (_ext_changed or _inputs_changed):
        sys.path.insert(0, str(_REPO_ROOT / "scripts" / "internal"))
        from extension_contract_sync import check_sync as _check_ext_sync

        def _check_extension_contract_sync() -> tuple[bool, str]:
            return _check_ext_sync()

        checks.append(("extension contract ↔ rust_builtin_map sync", _check_extension_contract_sync))

    # Catches the class of bug where an extension route module builds a
    # `Router<SharedState>` via `fn routes()` but `main.rs` never merges it —
    # the module's own tests build their router directly and stay green while
    # production 404s every path. Triggered by changes to either side of that
    # invariant: the routes tree (a module could gain/lose its routes() fn) or
    # main.rs (a merge call could be added/removed/renamed).
    _route_merge_changed = any(
        f.startswith("crates/yu-server/src/routes/")
        or f == "crates/yu-server/src/main.rs"
        for f in _changed_files
    )
    if "route-merge-wiring" not in skip and (_route_merge_changed or _inputs_changed):
        sys.path.insert(0, str(_REPO_ROOT / "scripts" / "internal"))
        from route_merge_wiring_check import check_sync as _check_route_merge_wiring

        def _check_route_merge_wiring_wrapper() -> tuple[bool, str]:
            return _check_route_merge_wiring()

        checks.append(("extension route -> main.rs merge wiring", _check_route_merge_wiring_wrapper))

    any_fail = False
    # Per-stage timing. This gate went unresponsive for over 30 minutes on one
    # machine and the run left no record of WHICH stage was stuck, so the only
    # way forward was to re-run each check by hand. The header is flushed
    # before the check runs and the duration is printed after, so a run killed
    # mid-stage still names the stage it died in.
    timings: list[tuple[str, float]] = []
    for name, fn in checks:
        print(f"\n=== {name} ===", flush=True)
        started = time.monotonic()
        try:
            ok, msg = fn()
        finally:
            elapsed = time.monotonic() - started
            timings.append((name, elapsed))
        print(msg.strip() or "(no output)")
        # The verdict keeps its own bare line: callers (and the git hook) count
        # these anchored, so appending a duration here would break them.
        # Only the slow stages get an extra line; a duration on all ~68 would
        # bury the verdicts this output exists to show.
        if elapsed >= 5.0:
            print(f"  ({elapsed:.1f}s)")
        print("PASS" if ok else "FAIL")
        if not ok:
            any_fail = True

    slowest = sorted(timings, key=lambda pair: pair[1], reverse=True)[:5]
    total = sum(seconds for _, seconds in timings)
    print(f"\n=== timing ({total:.1f}s over {len(timings)} stage(s)) ===")
    for name, seconds in slowest:
        print(f"  {seconds:7.1f}s  {name}")

    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
