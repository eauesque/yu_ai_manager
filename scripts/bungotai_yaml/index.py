"""語形索引（第 2.3 節）。表の rows のみから生成。derived・手編集禁止。"""
from __future__ import annotations

import re
import unicodedata

from bungotai_yaml.model import (
    Block,
    ParseResult,
    Section,
    Warning,
)

_TILDE = "〜～"                 # U+301C / U+FF5E
_BRACKETS = "「」『』（）()"

# Markdown 強調記法（`**...**` / `*...*` / `` `...` ``）— 中身を残し記号のみ除去
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*", flags=re.DOTALL)
_MD_ITALIC = re.compile(r"\*(.+?)\*", flags=re.DOTALL)
_MD_CODE = re.compile(r"`([^`]+)`")

# 親語形抽出（第 2.3.3b 節）: 「…」 / 『…』 引用括弧内
_PARENT_QUOTE_RE = re.compile(r"[「『]([^」』]+)[」』]")


def _strip_markdown_emphasis(text: str) -> str:
    """`**...**` / `*...*` / `` `...` `` を中身を残して peel する（第 2.3.2 節）。

    nested 強調にも対応するため、変化が無くなるまで反復適用する。
    """
    prev = None
    cur = text
    while prev != cur:
        prev = cur
        cur = _MD_BOLD.sub(r"\1", cur)
        cur = _MD_ITALIC.sub(r"\1", cur)
        cur = _MD_CODE.sub(r"\1", cur)
    return cur


def normalize_concept_key(text: str) -> str:
    """by_concept キー正規化（第 2.3.2 節）: Markdown 強調除去 + NFC + 小文字化 + trim。"""
    s = unicodedata.normalize("NFC", text)
    s = _strip_markdown_emphasis(s)
    return s.strip().lower()


def normalize_form_key(text: str) -> str:
    """by_form キー正規化（第 2.3.1 節 v0.4.4）:
    NFC → Markdown 強調 peel → 波ダッシュ除去 → 括弧除去 → 前後空白除去。
    """
    s = unicodedata.normalize("NFC", text)
    s = _strip_markdown_emphasis(s)
    s = s.strip()
    s = s.strip(_TILDE)
    s = s.strip(_BRACKETS)
    s = s.strip().strip("　")
    s = s.strip(_TILDE)  # 括弧除去後に再度先頭波ダッシュ
    return s


def block_id_key(bid: str) -> tuple[int, int, int, int, int]:
    """block_id を数値 tuple に分解（第 2.3.5 節）。

    返値: (owner_kind, owner_num, locus_kind, sub_num, block_seq)
      owner_kind 0=chapter / 1=appendix / 2=doc.toc
      locus_kind 0=lead_blocks / 1=section / 2=doc.toc
    """
    if bid == "doc.toc":
        return (2, 0, 2, 0, 0)
    if bid.startswith("ch"):
        m = re.match(r"^ch(\d+)\.lead\.b(\d+)$", bid)
        return (0, int(m.group(1)), 0, 0, int(m.group(2)))
    if bid.startswith("ap"):
        m = re.match(r"^ap([A-D])\.lead\.b(\d+)$", bid)
        return (1, ord(m.group(1)) - ord("A"), 0, 0, int(m.group(2)))
    m = re.match(r"^([0-9A-D]+)\.(\d+)\.b(\d+)$", bid)
    owner, minor, seq = m.group(1), int(m.group(2)), int(m.group(3))
    if owner.isdigit():
        return (0, int(owner), 1, minor, seq)
    return (1, ord(owner) - ord("A"), 1, minor, seq)


def _extract_parent_form_from_heading(text: str) -> str | None:
    """heading / title から 「…」/『…』 内の語を抽出（第 2.3.3b 節 step 1）。"""
    if not text:
        return None
    m = _PARENT_QUOTE_RE.search(text)
    return m.group(1).strip() if m else None


def _extract_parent_from_prose(blocks_before: list[Block]) -> str | None:
    """直前 prose 末尾段落から親語形抽出（第 2.3.3b 節 step 2）。"""
    for blk in reversed(blocks_before):
        if blk.type == "prose" and blk.text:
            # 末尾段落: 最後の改行以降を優先するが、引用括弧パターンを全文走査
            m = _PARENT_QUOTE_RE.search(blk.text)
            if m:
                return m.group(1).strip()
            return None  # 直前 prose で取れなければ skip（更に遡らない）
    return None


def _iter_tables(result: ParseResult):
    """全表を (table_block, owner_kind, owner, parent_blocks_before, appendix_id) で列挙。

    - owner_kind: "chapter_lead" / "chapter_section" / "appendix_lead" / "appendix_section"
    - owner: Chapter / Appendix / Section instance（heading/title 抽出用）
    - parent_blocks_before: 同一 owner 内で当該表より前のブロック列（prose 探索用）
    - appendix_id: 親 appendix.id（chapter 配下なら None）
    """
    for ch in result.chapters:
        for i, blk in enumerate(ch.lead_blocks):
            if blk.type == "table":
                yield blk, "chapter_lead", ch, ch.lead_blocks[:i], None
        for sec in ch.sections:
            for i, blk in enumerate(sec.blocks):
                if blk.type == "table":
                    yield blk, "chapter_section", sec, sec.blocks[:i], None
    for ap in result.appendices:
        for i, blk in enumerate(ap.lead_blocks):
            if blk.type == "table":
                yield blk, "appendix_lead", ap, ap.lead_blocks[:i], ap.id
        for sec in ap.sections:
            for i, blk in enumerate(sec.blocks):
                if blk.type == "table":
                    yield blk, "appendix_section", sec, sec.blocks[:i], ap.id


def _extract_parent_form(
    owner,
    parent_blocks_before: list[Block],
) -> str | None:
    """senses 表の親語形を抽出（第 2.3.3b 節 規約）。

    優先順位:
      1) owner（Chapter/Appendix の title_ja・Section の heading）の 「…」/『…』
      2) 同一 owner 内の直前 prose 末尾段落の 「…」/『…』
      3) None
    """
    heading_text = owner.heading if isinstance(owner, Section) else (getattr(owner, "title_ja", "") or "")
    parent = _extract_parent_form_from_heading(heading_text)
    if parent:
        return parent
    return _extract_parent_from_prose(parent_blocks_before)


def _split_forms(cell: str) -> list[str]:
    """文語形セルを ／ / で分割。code span 内・全角括弧内は分割せず。"""
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    in_code = False
    for ch in cell:
        if ch == "`":
            in_code = not in_code
            buf.append(ch)
            continue
        if ch == "（":
            depth += 1
            buf.append(ch)
            continue
        if ch == "）":
            depth = max(0, depth - 1)
            buf.append(ch)
            continue
        if ch in "／/" and depth == 0 and not in_code:
            parts.append("".join(buf).strip())
            buf = []
            continue
        buf.append(ch)
    parts.append("".join(buf).strip())
    return [p for p in parts if p]


def build_index(result: ParseResult) -> dict:
    """語形索引を構築（第 2.3 節）。

    senses 表は親語形抽出経由で by_form に登録し、senses 行自体は by_form に
    寄与しない（第 2.3.3a 節 v0.4.4）。失敗時は result.warnings へ追加。
    """
    by_form: dict[str, dict] = {}
    by_concept: dict[str, dict] = {}
    # 親語形（正規化キー）→ senses_ref。複数 senses 表で重複したら後出 warn
    senses_loc: dict[str, dict] = {}

    for blk, owner_kind, owner, parent_blocks_before, appendix_id in _iter_tables(result):
        role = blk.role
        if role == "mapping":
            for r_idx, row in enumerate(blk.rows):
                if not row:
                    continue
                concept = normalize_concept_key(row[0])
                if not concept:
                    continue
                forms_cell = row[2] if len(row) >= 3 else ""
                by_concept.setdefault(concept, {
                    "forms": _split_forms(forms_cell),
                    "ref": {"block_id": blk.block_id, "row": r_idx},
                })
            continue

        if role in ("paradigm", "contrast"):
            # col0 を語形として by_form に登録（既存ロジック）
            for r_idx, row in enumerate(blk.rows):
                if not row:
                    continue
                raw_form = row[0]
                key = normalize_form_key(raw_form)
                if not key:
                    continue
                entry = by_form.setdefault(key, {"display": raw_form, "refs": []})
                entry["refs"].append({
                    "block_id": blk.block_id, "row": r_idx, "column": 0,
                })
            continue

        if role == "senses":
            # 第 2.3.3a/b 節 v0.4.4: col0 は義名、語形に非ず。
            # 行自身は by_form に寄与せず、親語形を抽出して senses_ref を付す。
            raw_parent = _extract_parent_form(owner, parent_blocks_before)
            if not raw_parent:
                result.warnings.append(Warning(
                    code="SENSES_PARENT_NOT_FOUND",
                    message=(
                        f"senses 表 {blk.block_id} の親語形抽出に失敗"
                        "（owner heading / 直前 prose に 「…」/『…』 引用括弧パターン無し）"
                    ),
                    source_line=0,
                    severity="warn",
                ))
                continue
            key = normalize_form_key(raw_parent)
            if not key:
                result.warnings.append(Warning(
                    code="SENSES_PARENT_NOT_FOUND",
                    message=(
                        f"senses 表 {blk.block_id} の親語形 {raw_parent!r} が正規化後に空"
                    ),
                    source_line=0,
                    severity="warn",
                ))
                continue
            # appendix 経由 senses ならば appendix id を、chapter 配下なら chapter id を採る
            if appendix_id is not None:
                loc = {"appendix": appendix_id, "block_id": blk.block_id}
            else:
                # chapter 配下の senses 表は規格外だが堅牢に対応（chapter id を記す）
                ch_id = owner.id if owner_kind == "chapter_lead" else None
                # chapter_section の場合 owner=Section なので親 chapter は別途取得不可。
                # 規格外につき block_id のみで誘導する。
                loc = {"block_id": blk.block_id}
                if isinstance(ch_id, int):
                    loc["chapter"] = ch_id
            if key in senses_loc:
                result.warnings.append(Warning(
                    code="SENSES_PARENT_DUPLICATE",
                    message=(
                        f"senses 表 {blk.block_id} の親語形 {raw_parent!r}"
                        f" が既出（先出を採り後出は無視）"
                    ),
                    source_line=0,
                    severity="warn",
                ))
                continue
            senses_loc[key] = loc
            # by_form エントリ確保（既存ならば display は既存優先・refs は保持）
            by_form.setdefault(key, {"display": raw_parent, "refs": []})
            continue

        # その他 role（toc / misc 等）は by_form / by_concept に寄与せず

    # senses_ref 付与（第 2.3.3 節）
    for key, loc in senses_loc.items():
        if key in by_form:
            by_form[key]["senses_ref"] = loc

    # ソート（第 2.3.5 節）
    for entry in by_form.values():
        entry["refs"].sort(key=lambda r: (block_id_key(r["block_id"]), r["row"], r["column"]))
        # 重複 ref 除去
        seen = set()
        uniq = []
        for r in entry["refs"]:
            t = (r["block_id"], r["row"], r["column"])
            if t not in seen:
                seen.add(t)
                uniq.append(r)
        entry["refs"] = uniq

    # warnings も source_line 昇順に再整列（追加分の安定化・第 2.5.3 節）
    result.warnings.sort(key=lambda w: (w.source_line, w.code, w.message))

    by_form_sorted = {k: by_form[k] for k in sorted(by_form)}
    by_concept_sorted = {k: by_concept[k] for k in sorted(by_concept)}
    return {"by_form": by_form_sorted, "by_concept": by_concept_sorted}
