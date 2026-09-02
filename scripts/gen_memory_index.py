"""Generate and verify docs/development/memory-index/<node_id>.yaml.

Links Claude persistent memory (~/.claude/projects/<slug>/memory/*.md) to
repository knowledge docs (docs/development/development_docs/**/*.md) via
opt-in frontmatter (memory `doc:` / docs `memory_key:`).

Generate: uv run python scripts/gen_memory_index.py
Verify  : uv run python scripts/gen_memory_index.py --check

Spec: docs/superpowers/specs/2026-05-31-memory-docs-sync.md
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DOC_TOKEN_RE = re.compile(r"^\s*doc\s*:", re.MULTILINE)
_MEMORY_KEY_TOKEN_RE = re.compile(r"^\s*memory_key\s*:", re.MULTILINE)
_NODE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SLUG_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SLUG_RE = re.compile(r"[^A-Za-z0-9]")
_TITLE_SPLIT_RE = re.compile(r" — |。|\n")
_TITLE_MAX = 60
_SUMMARY_MAX = 120
_GENERATOR_VERSION = 1
DEV_DOCS_SUBDIR = "docs/development/development_docs"
MEMORY_INDEX_SUBDIR = "docs/development/memory-index"


def derive(description: str) -> tuple[str, str]:
    """Return title and summary deterministically from a memory description."""
    desc = description.strip()
    summary = desc if len(desc) <= _SUMMARY_MAX else desc[:_SUMMARY_MAX] + "…"
    segments = _TITLE_SPLIT_RE.split(desc)
    title_src = next((seg.strip() for seg in segments if seg.strip()), desc)
    title = title_src if len(title_src) <= _TITLE_MAX else title_src[:_TITLE_MAX] + "…"
    return title, summary


def slugify_repo_path(repo_root: Path) -> str:
    """Mirror Claude Code's ~/.claude/projects/<slug> naming."""
    return _SLUG_RE.sub("-", str(repo_root.resolve()))


def resolve_memory_dir(repo_root: Path) -> Path:
    """Resolve the local memory dir, honoring CLAUDE_MEMORY_DIR."""
    env = os.environ.get("CLAUDE_MEMORY_DIR")
    if env:
        return Path(env)
    return Path.home() / ".claude" / "projects" / slugify_repo_path(repo_root) / "memory"


def read_node_id(repo_root: Path) -> str | None:
    """Read data/node_id.txt without creating it."""
    path = repo_root / "data" / "node_id.txt"
    if path.exists():
        raw = path.read_text(encoding="utf-8").strip().lower()
        if _NODE_ID_RE.match(raw):
            return raw
    return None


def resolve_or_create_node_id(repo_root: Path) -> str:
    """Read the node id, creating it through core.node_identity if absent."""
    existing = read_node_id(repo_root)
    if existing:
        return existing

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    import core.node_identity as ni

    ni._NODE_ID_PATH = repo_root / "data" / "node_id.txt"
    return ni.get_node_id()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _front_matter_block(text: str) -> str | None:
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    return text[3:end]


def scan_memory(memory_dir: Path, repo_root: Path) -> tuple[list[dict], list[str], list[str]]:
    """Scan local memory files and validate opt-in doc links."""
    entries: list[dict] = []
    errors: list[str] = []
    skips: list[str] = []
    docs_root = (repo_root / DEV_DOCS_SUBDIR).resolve()
    seen_names: dict[str, str] = {}
    seen_docs: dict[str, str] = {}

    for md in sorted(memory_dir.glob("*.md")):
        if md.name == "MEMORY.md":
            continue

        text = md.read_text(encoding="utf-8", errors="replace")
        block = _front_matter_block(text)
        if block is None:
            continue

        has_doc_token = bool(_DOC_TOKEN_RE.search(block))
        try:
            fm = yaml.safe_load(block) or {}
            if not isinstance(fm, dict):
                raise yaml.YAMLError("front matter is not a mapping")
        except yaml.YAMLError as exc:
            if has_doc_token:
                errors.append(f"{md.name}: invalid YAML front matter with doc: {exc}")
            else:
                skips.append(f"{md.name}: invalid YAML front matter without doc: skipped")
            continue

        doc = fm.get("doc")
        if doc is None:
            continue
        if not isinstance(doc, str):
            errors.append(f"{md.name}: `doc:` must be a string, got {type(doc).__name__}")
            continue

        name = fm.get("name")
        if not isinstance(name, str) or not _SLUG_KEY_RE.match(name):
            errors.append(f"{md.name}: `name:` missing or not a valid slug")
            continue

        description = fm.get("description")
        if not isinstance(description, str) or not description.strip():
            errors.append(f"{md.name}: `description:` missing, non-string, or blank")
            continue

        doc_path = Path(doc)
        if doc_path.is_absolute() or ".." in doc_path.parts:
            errors.append(f"{md.name}: `doc:` must be relative without '..': {doc}")
            continue
        resolved = (repo_root / doc_path).resolve()
        if not resolved.is_relative_to(docs_root):
            errors.append(f"{md.name}: `doc:` escapes development_docs tree: {doc}")
            continue
        if not resolved.exists():
            errors.append(f"{md.name}: linked doc does not exist: {doc}")
            continue

        # Normalize doc to canonical repo-relative posix path (removes './' prefix etc.)
        # so that scan_docs_backward can compare by string equality (spec §4.3-1).
        doc_normalized = resolved.relative_to(repo_root.resolve()).as_posix()

        # 1:1 constraint: multiple memories pointing to the same doc (spec §4.3-3)
        if doc_normalized in seen_docs:
            errors.append(
                f"multiple memories point to same doc {doc_normalized!r}"
                f" ({seen_docs[doc_normalized]}, {md.name})"
            )
            continue

        doc_fm = _front_matter_block(resolved.read_text(encoding="utf-8", errors="replace"))
        doc_key = None
        if doc_fm is not None:
            try:
                parsed = yaml.safe_load(doc_fm) or {}
                if isinstance(parsed, dict):
                    doc_key = parsed.get("memory_key")
            except yaml.YAMLError:
                doc_key = None
        if doc_key != name:
            errors.append(f"{md.name}: doc {doc} memory_key={doc_key!r} != name={name!r}")
            continue

        if name in seen_names:
            errors.append(f"duplicate memory name {name!r} ({seen_names[name]}, {md.name})")
            continue
        seen_names[name] = md.name
        seen_docs[doc_normalized] = md.name

        title, summary = derive(description)
        entries.append({
            "key": name,
            "title": title,
            "summary": summary,
            "sha256": _sha256(md),
            "doc": doc_normalized,
        })

    entries.sort(key=lambda entry: entry["key"])
    return entries, errors, skips


def scan_docs_backward(
    repo_root: Path,
    local_names: set[str],
    name_to_doc: dict[str, str],
) -> list[str]:
    """Validate docs-side memory_key links for this node."""
    errors: list[str] = []
    docs_root = repo_root / DEV_DOCS_SUBDIR
    seen_keys: dict[str, str] = {}

    for md in sorted(docs_root.rglob("*.md")):
        block = _front_matter_block(md.read_text(encoding="utf-8", errors="replace"))
        if block is None:
            continue

        try:
            fm = yaml.safe_load(block) or {}
        except yaml.YAMLError as exc:
            if _MEMORY_KEY_TOKEN_RE.search(block):
                rel = md.relative_to(repo_root).as_posix()
                errors.append(f"{rel}: invalid YAML front matter with memory_key: {exc}")
            continue
        if not isinstance(fm, dict):
            continue

        key = fm.get("memory_key")
        if key is None:
            continue

        rel = md.relative_to(repo_root).as_posix()
        if not isinstance(key, str):
            errors.append(f"{rel}: `memory_key:` must be a string")
            continue
        if not _SLUG_KEY_RE.match(key):
            errors.append(f"{rel}: `memory_key:` {key!r} is not a valid slug")
            continue
        if key in seen_keys:
            errors.append(f"duplicate memory_key {key!r} ({seen_keys[key]}, {rel})")
            continue
        seen_keys[key] = rel

        if key in local_names:
            linked = name_to_doc.get(key)
            if linked != rel:
                errors.append(f"{rel}: local memory {key!r} doc={linked!r} does not point back")

    return errors


def build(memory_dir: Path, repo_root: Path, node_id: str) -> dict:
    """Build this node's memory index data."""
    entries, errors, _ = scan_memory(memory_dir, repo_root)
    if errors:
        raise ValueError("; ".join(errors))
    return {"version": _GENERATOR_VERSION, "node_id": node_id, "entries": entries}


def _freshness_warnings(live_entries: list[dict], index_path: Path) -> list[str]:
    if not index_path.exists():
        if live_entries:
            return [f"index file {index_path.name} not generated for current live memory"]
        return []

    try:
        obj = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        return [f"index file {index_path.name} parse error: {exc}"]

    indexed = {entry["key"]: entry for entry in (obj.get("entries") or [])}
    live = {entry["key"]: entry for entry in live_entries}
    warns: list[str] = []

    for key in sorted(set(live) - set(indexed)):
        warns.append(f"memory {key!r} not in index; run gen_memory_index.py")
    for key in sorted(set(indexed) - set(live)):
        warns.append(f"index {key!r} no longer in live memory")
    for key in sorted(set(live) & set(indexed)):
        for field in ("title", "summary", "sha256", "doc"):
            if live[key].get(field) != indexed[key].get(field):
                warns.append(f"memory {key!r} field {field!r} drifted from index")

    return warns


def verify_sync(memory_dir: Path, repo_root: Path, node_id: str | None) -> tuple[bool, str]:
    """Verify live node-local memory and docs links."""
    memory_dir = Path(memory_dir)
    repo_root = Path(repo_root)
    if not memory_dir.exists():
        return True, f"(memory dir {memory_dir} not found - skipped)"

    entries, errors, skips = scan_memory(memory_dir, repo_root)
    local_names = {entry["key"] for entry in entries}
    name_to_doc = {entry["key"]: entry["doc"] for entry in entries}
    errors.extend(scan_docs_backward(repo_root, local_names, name_to_doc))

    if errors:
        return False, "memory-docs link errors:\n  " + "\n  ".join(errors)

    warns = list(skips)
    if node_id is not None:
        index_path = repo_root / MEMORY_INDEX_SUBDIR / f"{node_id}.yaml"
        warns.extend(_freshness_warnings(entries, index_path))

    if warns:
        return True, "PASS with WARN:\n  " + "\n  ".join(warns)
    return True, f"memory-docs in sync ({len(entries)} linked entries)"


def main() -> int:
    parser = argparse.ArgumentParser(description="memory-docs index generator/verifier")
    parser.add_argument("--check", action="store_true", help="verify only; do not write")
    args = parser.parse_args()

    memory_dir = resolve_memory_dir(_REPO_ROOT)
    if args.check:
        node_id = read_node_id(_REPO_ROOT)
        ok, msg = verify_sync(memory_dir, _REPO_ROOT, node_id)
        print(msg)
        return 0 if ok else 1

    if not memory_dir.exists():
        print(f"(memory dir {memory_dir} not found - nothing to generate)")
        return 0

    node_id = resolve_or_create_node_id(_REPO_ROOT)
    data = build(memory_dir, _REPO_ROOT, node_id)
    out_dir = _REPO_ROOT / MEMORY_INDEX_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{node_id}.yaml"
    with out.open("w", encoding="utf-8", newline="\n") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    print(f"generated: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
