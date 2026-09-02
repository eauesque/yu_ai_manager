"""文書形式憲章 MD → YAML 抽出ツール。

生成: uv run python scripts/build_charter_yaml.py
検証: uv run python scripts/build_charter_yaml.py --check

抽出ルール（決定論的・意味的判断ナシ）:
  classification  : 早見表ノ行ヲ位置ベースノ key map ニテ写ス
  yaml_targets    : 第四条ノ番号付リストヲ写ス
  md_targets      : 第六条ノ番号付リストヲ写ス
  judgment_layers : 第八条ノ番号付リストヲ写ス（位置ベース key map）
  constraints     : 条番号 {7,9,10,11,12} ノ見出シヨリ title ト ref ヲ写ス

散文段落ハ一切パースセズ。
"""

from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import os
import re
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SOURCE = _REPO_ROOT / ".claude" / "doc-format-charter.md"
_ARTIFACT = _REPO_ROOT / ".claude" / "doc-format-charter.yaml"
GRAMMAR_VERSION = "1.0.0"

# 早見表の行 → classification key（位置ベース、第0行=ヘッダ除きデータ第1行）
_CLASSIFICATION_KEYS = [
    "fixed_procedure",
    "procedure_with_enumerable_exceptions",
    "procedure_with_judgment_exceptions",
    "judgment_criteria",
    "index_or_reference_table",
    "rationale_or_origin",
    "orientation",
    "skill",
    "philosophy",
]

# 第八条リスト項目 → judgment_layers key（位置ベース）
_JUDGMENT_LAYER_KEYS = ["criteria", "rationale", "link"]

# 制約条の固定集合
_CONSTRAINT_ARTICLES = [7, 9, 10, 11, 12]

# 漢数字マップ（条番号用）
_KANJI = {
    1: "一", 2: "二", 3: "三", 4: "四", 5: "五",
    6: "六", 7: "七", 8: "八", 9: "九", 10: "十",
    11: "十一", 12: "十二",
}


def _sha256_raw(path: Path) -> str:
    """ファイルヲ生バイトデ読ミ SHA-256 ヲ十六進小文字 64 字デ返ス。"""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_anchors(md_path: str | Path) -> frozenset[str]:
    """MD ファイルから有効なアンカー文字列集合を返す。

    認識する形式:
    - ATX 見出し: ## foo → "foo"
    - bold inline マーカー: 行頭 **第N条 → "第N条"（charter 慣例）
    """
    text = Path(md_path).read_text(encoding="utf-8")
    anchors: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        m = re.match(r"^#{1,6}\s+(.+)$", stripped)
        if m:
            anchors.add(m.group(1).strip())
            continue
        m = re.match(r"^\*\*(.+?)[\s（（]", stripped)
        if m:
            anchors.add(m.group(1).strip())
            continue
        m = re.match(r"^\*\*(.+)", stripped)
        if m:
            token = m.group(1).split("（")[0].split("　")[0].split(" ")[0].strip()
            if token:
                anchors.add(token)
    return frozenset(anchors)


def _parse_directives(text: str) -> dict:
    """MD テキストから ::: フェンス directive を抽出する。"""
    result: dict = {"out_of_scope": [], "requires_rationale_when": []}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = re.match(r"^:::(out_of_scope|requires_rationale_when)\s*$", lines[i].strip())
        if m:
            directive_type = m.group(1)
            body_lines: list[str] = []
            i += 1
            while i < len(lines) and lines[i].strip() != ":::":
                body_lines.append(lines[i])
                i += 1
            body = "\n".join(body_lines)
            try:
                parsed = yaml.safe_load(body) or {}
                if isinstance(parsed, dict):
                    result[directive_type].append(parsed)
            except yaml.YAMLError as e:
                raise ValueError(
                    f":::{ directive_type} directive の YAML が不正です: {e}"
                ) from e
        i += 1
    return result


def _classification_to_match(classification: dict) -> dict:
    """classification 辞書を match.branches + _default 形式に変換する。"""
    branches = [
        {"when": {"doc_type": key}, "do": value}
        for key, value in classification.items()
    ]
    return {
        "branches": branches,
        "_default": {
            "reason": "no_matching_branch",
            "rationale_ref": ".claude/doc-format-charter.md#第六条",
        },
    }


def _yml_content_hash(data: dict) -> str:
    """meta.generated_at / yml_content_sha256 / grammar_content_sha256 を除いた
    canonical dump の SHA-256 を返す。

    generated_at と self-referential フィールドを除外してから canonical hash を計算する。
    呼び出し元は yml_content_sha256 をセットする前にこの関数を呼ぶこと。
    """
    d = copy.deepcopy(data)
    meta = d.get("meta", {})
    for key in ("generated_at", "yml_content_sha256", "grammar_content_sha256"):
        meta.pop(key, None)
    d["meta"] = meta
    canonical = yaml.dump(
        d,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _source_mtime_iso(path: Path) -> str:
    """ソースファイルノ mtime ヲ ISO 8601 UTC デ返ス（冪等性保証）。"""
    mtime = os.path.getmtime(path)
    return datetime.datetime.fromtimestamp(mtime, tz=datetime.UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _parse_early_table(text: str) -> list[tuple[str, str]]:
    """早見表ノ データ行ヲ (content_cell, format_cell) リストトシテ返ス。

    セパレータ行（|---|）直後カラ開始シ、非テーブル行デ終了ス。
    ヘッダ行（セパレータ前）ハ含マズ。
    """
    lines = text.splitlines()
    rows: list[tuple[str, str]] = []
    past_separator = False
    in_table_section = False

    for line in lines:
        stripped = line.strip()
        # 早見セクション開始検出
        if re.search(r"^#{1,4}\s*早見", stripped):
            in_table_section = True
            continue
        if not in_table_section:
            continue
        if not stripped.startswith("|"):
            if rows:
                break  # テーブル終了
            continue
        # セパレータ行スキップ
        if re.match(r"^\|[-:\s|]+\|$", stripped):
            past_separator = True
            continue
        if not past_separator:
            continue  # ヘッダ行スキップ
        # データ行パース
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) >= 2 and cells[0]:
            rows.append((cells[0], cells[1]))

    return rows


def _parse_format_cell(cell: str) -> str | list[str]:
    """形式列ノ文字列ヲ yaml 値ニ変換スル。

    "yaml（...）＋ md（...）" → ["yaml", "md"]
    "yaml（...）" → "yaml"
    "yaml/json"   → "yaml"
    "md（...）"   → "md"
    """
    cell = cell.strip()
    if "＋" in cell:
        parts = [p.strip() for p in cell.split("＋")]
        return [_first_token(p) for p in parts]
    return _first_token(cell)


def _first_token(s: str) -> str:
    """括弧・スラッシュ前ノ最初ノトークンヲ小文字デ返ス。"""
    s = s.strip()
    s = re.split(r"[（(/]", s)[0].strip()
    return s.lower()


def _find_article_line(lines: list[str], n: int) -> int:
    """**第N条（...）** パターンノ行番号ヲ返ス。見付カラズバ -1。"""
    kanji = _KANJI[n]
    pattern = rf"\*\*第{kanji}条（"
    for i, line in enumerate(lines):
        if re.search(pattern, line):
            return i
    return -1


def _extract_article_title(lines: list[str], article_line: int) -> str:
    """第N条（タイトル）ノ括弧内テキストヲ返ス。"""
    line = lines[article_line]
    m = re.search(r"第[一二三四五六七八九十]+条（(.+?)）", line)
    return m.group(1) if m else ""


def _extract_numbered_list(lines: list[str], start: int) -> list[str]:
    """start 行以降ノ番号付リスト項目ヲ返ス。リスト終了デ停止。"""
    items: list[str] = []
    seen_item = False
    for line in lines[start + 1 :]:
        m = re.match(r"^\d+\.\s+(.+)$", line.strip())
        if m:
            seen_item = True
            items.append(m.group(1).strip())
        elif seen_item:
            if line.strip() == "":
                continue  # リスト内ノ空行ハ継続（稀ナルケース）
            break  # リスト終了
    return items


def _extract_judgment_layer_value(item: str) -> str:
    """リスト項目ヨリ形式値ヲ抽出スル。

    バッククォート → rationale_ref 等ノ識別子
    括弧内 → yaml/md 等ノ形式名
    """
    m = re.search(r"`([^`]+)`", item)
    if m:
        return m.group(1)
    m = re.search(r"（([^）]+)）", item)
    if m:
        return m.group(1).lower()
    return item.strip()


def build(source: Path) -> dict:
    """憲章 MD ヲパースシテ YAML 辞書ヲ返ス。"""
    text = source.read_text(encoding="utf-8")
    lines = text.splitlines()
    directives = _parse_directives(text)

    # ── classification（早見表） ─────────────────────────────────────────
    table_rows = _parse_early_table(text)
    if len(table_rows) != len(_CLASSIFICATION_KEYS):
        raise ValueError(
            f"早見表ノ行数 ({len(table_rows)}) ガ期待値 ({len(_CLASSIFICATION_KEYS)}) ト一致セズ。"
            " 憲章ノ早見表構造ヲ確認スベシ。"
        )
    classification = {
        key: _parse_format_cell(fmt)
        for key, (_, fmt) in zip(_CLASSIFICATION_KEYS, table_rows, strict=True)
    }

    # ── yaml_targets（第四条） ─────────────────────────────────────────────
    art4 = _find_article_line(lines, 4)
    if art4 < 0:
        raise ValueError("第四条ガ見付カラズ")
    yaml_targets = _extract_numbered_list(lines, art4)

    # ── md_targets（第六条） ───────────────────────────────────────────────
    art6 = _find_article_line(lines, 6)
    if art6 < 0:
        raise ValueError("第六条ガ見付カラズ")
    md_targets = _extract_numbered_list(lines, art6)

    # ── judgment_layers（第八条） ──────────────────────────────────────────
    art8 = _find_article_line(lines, 8)
    if art8 < 0:
        raise ValueError("第八条ガ見付カラズ")
    layer_items = _extract_numbered_list(lines, art8)
    if len(layer_items) != len(_JUDGMENT_LAYER_KEYS):
        raise ValueError(
            f"第八条ノリスト項目数 ({len(layer_items)}) ガ期待値 ({len(_JUDGMENT_LAYER_KEYS)}) ト一致セズ"
        )
    judgment_layers = {
        key: _extract_judgment_layer_value(item)
        for key, item in zip(_JUDGMENT_LAYER_KEYS, layer_items, strict=True)
    }

    # ── constraints（第七・九・十・十一・十二条） ─────────────────────────
    constraints: list[dict] = []
    for n in _CONSTRAINT_ARTICLES:
        art_line = _find_article_line(lines, n)
        if art_line < 0:
            raise ValueError(f"第{_KANJI[n]}条ガ見付カラズ")
        title = _extract_article_title(lines, art_line)
        ref = f".claude/doc-format-charter.md#第{_KANJI[n]}条"
        constraints.append({"id": n, "title": title, "ref": ref})

    _this_file = Path(__file__).resolve()
    data: dict = {
        "meta": {
            "source": str(source.relative_to(_REPO_ROOT)).replace("\\", "/"),
            "source_sha256": _sha256_raw(source),
            "generated_at": _source_mtime_iso(source),
            "grammar_version": GRAMMAR_VERSION,
            "grammar_content_sha256": _sha256_raw(_this_file),
        },
        "match": _classification_to_match(classification),
        "_schema_version": "match-v1",
        "yaml_targets": yaml_targets,
        "md_targets": md_targets,
        "judgment_layers": judgment_layers,
        "constraints": constraints,
    }
    if directives["out_of_scope"]:
        data["out_of_scope"] = directives["out_of_scope"]
    if directives["requires_rationale_when"]:
        data["requires_rationale_when"] = directives["requires_rationale_when"]
    data["meta"]["yml_content_sha256"] = _yml_content_hash(data)
    return data


def verify_sync(source: str | Path, artifact: str | Path) -> tuple[bool, str]:
    """生成物ノ source_sha256 ト現原本 sha256 ヲ照合ス。"""
    source = Path(source)
    artifact = Path(artifact)
    if not source.exists():
        return True, f"(source {source} missing — skipped)"
    if not artifact.exists():
        return True, f"(artifact {artifact} not yet generated — skipped)"
    try:
        obj = yaml.safe_load(artifact.read_text(encoding="utf-8")) or {}
    except Exception as e:
        return False, f"artifact parse error: {e}"
    recorded = (obj.get("meta") or {}).get("source_sha256")
    current = _sha256_raw(source)
    if recorded == current:
        return True, "[charter-yaml] 同期 OK"
    return False, (
        f"doc-format-charter.md ↔ .yaml 不一致\n"
        f"  recorded: {recorded}\n"
        f"  current:  {current}\n"
        f"  再生成: uv run python scripts/build_charter_yaml.py"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="文書形式憲章 MD → YAML 抽出")
    parser.add_argument("--check", action="store_true", help="同期検証のみ（生成しない）")
    parser.add_argument("--source", default=str(_SOURCE), help="ソース MD パス")
    parser.add_argument("--out", default=str(_ARTIFACT), help="出力 YAML パス")
    args = parser.parse_args()

    source = Path(args.source)
    out = Path(args.out)

    if args.check:
        ok, msg = verify_sync(source, out)
        print(msg)
        return 0 if ok else 1

    data = build(source)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="\n") as f:
        yaml.dump(
            data,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )
    print(f"生成完了: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
