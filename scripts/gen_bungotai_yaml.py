"""bungotai-grammar Markdown → YAML 生成 CLI + 同期検証。

生成: uv run python scripts/gen_bungotai_yaml.py
検証: uv run python scripts/gen_bungotai_yaml.py --check
仕様: docs/development/specs/BUNGOTAI_GRAMMAR_YAML_SPEC.md v0.4.2
"""
from __future__ import annotations

import argparse
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

from bungotai_yaml import GENERATOR_VERSION  # noqa: E402
from bungotai_yaml.emit import dump_artifact, to_artifact_dict  # noqa: E402
from bungotai_yaml.hashing import sha256_raw  # noqa: E402
from bungotai_yaml.index import build_index  # noqa: E402
from bungotai_yaml.parse import ParseError, parse_document  # noqa: E402

DEFAULT_SOURCE = _REPO_ROOT / ".claude" / "bungotai-grammar.md"
DEFAULT_OUT = _REPO_ROOT / ".claude" / "bungotai-grammar.yaml"


def _rel_to_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


def _load_text(source: Path) -> str:
    raw = source.read_bytes()
    if raw[:3] == b"\xef\xbb\xbf":
        raw = raw[3:]
    text = unicodedata.normalize("NFC", raw.decode("utf-8"))
    return text.replace("\r\n", "\n").replace("\r", "\n")


def generate(source: Path, out: Path) -> None:
    text = _load_text(source)
    result = parse_document(text)
    index = build_index(result)
    meta = {
        "source_path": _rel_to_root(source),
        "source_sha256": sha256_raw(source),
        "generator_version": GENERATOR_VERSION,
        "generated_at": datetime.now(UTC).astimezone().isoformat(),
    }
    artifact = to_artifact_dict(result, index, meta)
    # NFR4 (v0.4.4): 生成物 YAML は LF 固定で書出す。Win 実行時の CRLF 化を防ぐ。
    # Path.write_text の newline 引数は Python 3.10+ で利用可。
    out.write_text(dump_artifact(artifact), encoding="utf-8", newline="\n")


def verify_sync(source: str | Path, artifact: str | Path) -> tuple[bool, str]:
    """生成物の source_sha256 と現原本 sha256 を照合（第 2.4.3 節）。"""
    import yaml
    artifact_path = Path(artifact)
    if not artifact_path.exists():
        return False, f"[bungotai-yaml] 生成物が存在しない: {artifact_path}"
    obj = yaml.safe_load(artifact_path.read_text(encoding="utf-8"))
    recorded = obj.get("meta", {}).get("source_sha256")
    current = sha256_raw(source)
    if recorded == current:
        return True, "[bungotai-yaml] 同期 OK"
    return False, (
        f"[bungotai-yaml] DRIFT 検出: {_rel_to_root(Path(source))} ガ変更サレタルモ\n"
        f"  生成物 ({_rel_to_root(artifact_path)}) ガ未更新ナリ。\n"
        f"  再生成セヨ: uv run python scripts/gen_bungotai_yaml.py"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="bungotai-grammar YAML generator")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--check", action="store_true",
                        help="生成せず drift のみ検証（非零終了で drift 報告）")
    args = parser.parse_args(argv)

    source = Path(args.source)
    out = Path(args.out)

    if args.check:
        ok, msg = verify_sync(source, out)
        print(msg, file=sys.stderr if not ok else sys.stdout)
        return 0 if ok else 1

    try:
        generate(source, out)
    except ParseError as e:
        print(f"[bungotai-yaml] PARSE FAILED {e}", file=sys.stderr)
        return 2
    print(f"[bungotai-yaml] generated {_rel_to_root(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
