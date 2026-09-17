"""token → model 変換（第 2.2 節）。fail-loud・block_id 採番・role 分類・note label 抽出。"""
from __future__ import annotations

import re

from bungotai_yaml.accountability import attribute_lines
from bungotai_yaml.kansuji import kansuji_to_int
from bungotai_yaml.model import (
    Appendix,
    Block,
    Chapter,
    Document,
    ParseResult,
    Section,
    TocBlock,
    Warning,
)
from bungotai_yaml.tokenize import Token, tokenize

_CHAPTER_RE = re.compile(r"^##\s+第(\S+?)章[　 ]+(.*)$")
_APPENDIX_RE = re.compile(r"^##\s+付録([A-Z])[　 ]+(.*)$")
_H2_RE = re.compile(r"^##\s+(.*)$")
_H3_RE = re.compile(r"^###\s+(.*)$")
_H1_RE = re.compile(r"^#\s+(.*)$")
# title 本体: "断定（Copula）— 補足" を 3 群に分解
_TITLE_RE = re.compile(r"^(.*?)（([^）]*)）(?:[　 ]*[—-][　 ]*(.*))?$")
_NOTE_LABEL_RE = re.compile(r"^>\s*\*\*([^*]+)\*\*[:：][ 　]*")
# 付録D 節見出し: "一節　…"
_APPENDIX_SECTION_RE = re.compile(r"^(\S+?)節[　 ]+(.*)$")


class ParseError(Exception):
    """fail-loud（第 2.2.4 節）。message と原本行番号を保持。"""

    def __init__(self, message: str, source_line: int) -> None:
        super().__init__(f"L{source_line}: {message}")
        self.source_line = source_line


def _split_title(rest: str, source_line: int) -> tuple[str, str, str | None]:
    m = _TITLE_RE.match(rest.strip())
    if not m:
        raise ParseError(f"章/付録題の解析不能: {rest!r}", source_line)
    ja = m.group(1).strip()
    en = m.group(2).strip()
    note = m.group(3).strip() if m.group(3) else None
    return ja, en, note


def _split_row(line: str) -> list[str]:
    """GFM 行をセル配列に分解。`\\|` エスケープと code span 内 `|` は区切と看做さず。"""
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    cells: list[str] = []
    buf: list[str] = []
    in_code = False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s) and s[i + 1] == "|":
            buf.append("|")
            i += 2
            continue
        if ch == "`":
            in_code = not in_code
            buf.append(ch)
            i += 1
            continue
        if ch == "|" and not in_code:
            cells.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def classify_role(columns: list[str], is_toc: bool) -> str:
    """表ヘッダ → role（第 2.2.7 節）。上から順に評価。"""
    if is_toc:
        return "toc"
    joined = " ".join(columns)
    if "欧州語" in joined or "modal" in joined.lower():
        return "mapping"
    if set(c.strip() for c in columns) == {"義", "意味", "判別指標", "用例"}:
        return "senses"
    if "現代語" in joined and "文語形" in joined:
        return "contrast"
    if "語形" in joined:
        return "paradigm"
    return "misc"


def _table_block(tok: Token, block_id: str) -> Block:
    columns = _split_row(tok.lines[0])
    rows = [_split_row(line) for line in tok.lines[2:]]
    ncol = len(columns)
    for idx, row in enumerate(rows):
        if len(row) != ncol:
            raise ParseError(
                f"表の列数不揃ヒ（ヘッダ {ncol} 列・データ {len(row)} 列）",
                tok.start + 2 + idx,
            )
    role = classify_role(columns, is_toc=False)
    return Block(type="table", block_id=block_id, role=role, columns=columns, rows=rows)


def _note_block(tok: Token, block_id: str) -> Block:
    first = tok.lines[0]
    label = None
    m = _NOTE_LABEL_RE.match(first)
    body_lines = list(tok.lines)
    if m:
        label = m.group(1).strip()
        body_lines[0] = first[m.end():]
    # 各行頭の "> " マーカーを除去
    stripped = []
    for ln in body_lines:
        t = ln.lstrip()
        if t.startswith(">"):
            t = t[1:]
            if t.startswith(" "):
                t = t[1:]
        stripped.append(t)
    return Block(type="note", block_id=block_id, label=label, text="\n".join(stripped))


def _prose_block(tok: Token, block_id: str) -> Block:
    return Block(type="prose", block_id=block_id, text="\n".join(tok.lines))


def _code_block(tok: Token, block_id: str) -> Block:
    return Block(type="code", block_id=block_id, lang=tok.lang, content="\n".join(tok.lines))


def parse_document(text: str) -> ParseResult:  # noqa: C901 — 状態機械ゆえ分岐多め
    tokens = tokenize(text)
    attribution = attribute_lines(tokens)
    doc = Document(title="", subtitle="", preamble="")
    chapters: list[Chapter] = []
    appendices: list[Appendix] = []
    warnings: list[Warning] = []

    preamble_parts: list[str] = []
    expect_toc_table = False
    cur_chapter: Chapter | None = None
    cur_appendix: Appendix | None = None
    cur_section: Section | None = None
    sec_counter = 0
    lead_counter = 0
    block_counter = 0

    for tok in tokens:
        if tok.kind == "blank" or tok.kind == "hr":
            continue
        if tok.kind == "h4plus":
            raise ParseError("H4 以下の見出しは未対応（仕様改訂を要す）", tok.start)
        if tok.kind == "h1":
            doc.title = _H1_RE.match(tok.lines[0]).group(1).strip()
            continue
        if tok.kind == "h2":
            line = tok.lines[0]
            cm = _CHAPTER_RE.match(line)
            am = _APPENDIX_RE.match(line)
            if cm:
                try:
                    cid = kansuji_to_int(cm.group(1))
                except ValueError as e:
                    raise ParseError(f"章番号の漢数字が解析不能: {e}", tok.start) from e
                expected = (chapters[-1].id + 1) if chapters else 1
                if cid != expected:
                    raise ParseError(f"章番号が連番でない（期待 {expected}・実 {cid}）", tok.start)
                ja, en, note = _split_title(cm.group(2), tok.start)
                cur_chapter = Chapter(id=cid, number_label=f"第{cm.group(1)}章",
                                      title_ja=ja, title_en=en, title_note=note,
                                      source_line=tok.start)
                chapters.append(cur_chapter)
                cur_appendix = None
                cur_section = None
                sec_counter = 0
                lead_counter = 0
                continue
            if am:
                ja, en, note = _split_title(am.group(2), tok.start)
                cur_appendix = Appendix(id=am.group(1), number_label=f"付録{am.group(1)}",
                                        title_ja=ja, title_en=en, title_note=note,
                                        source_line=tok.start)
                appendices.append(cur_appendix)
                cur_chapter = None
                cur_section = None
                sec_counter = 0
                lead_counter = 0
                continue
            # 通常 H2: 目次 か subtitle か
            h2text = _H2_RE.match(line).group(1).strip()
            if h2text.startswith("目次"):
                expect_toc_table = True
                continue
            if not doc.subtitle:
                doc.subtitle = h2text
                continue
            # それ以外の H2 は想定外 → prose 退避ではなく fail-loud（構造マーカー）
            raise ParseError(f"未知の H2 見出し: {h2text!r}", tok.start)
        if tok.kind == "h3":
            heading = _H3_RE.match(tok.lines[0]).group(1).strip()
            if cur_chapter is None and cur_appendix is None:
                raise ParseError("章/付録の外に H3 が出現", tok.start)
            if cur_appendix is not None:
                am = _APPENDIX_SECTION_RE.match(heading)
                if am:
                    try:
                        minor = kansuji_to_int(am.group(1))
                    except ValueError:
                        sec_counter += 1
                        minor = sec_counter
                    else:
                        sec_counter = minor
                else:
                    sec_counter += 1
                    minor = sec_counter
                sid = f"{cur_appendix.id}.{minor}"
                cur_section = Section(id=sid, heading=heading)
                cur_appendix.sections.append(cur_section)
            else:
                sec_counter += 1
                sid = f"{cur_chapter.id}.{sec_counter}"
                cur_section = Section(id=sid, heading=heading)
                cur_chapter.sections.append(cur_section)
            block_counter = 0
            continue

        # ここから content token（table/code/quote/prose）
        # 前付段階（章/付録未開始）の散文・表
        if cur_chapter is None and cur_appendix is None:
            if expect_toc_table and tok.kind == "table":
                columns = _split_row(tok.lines[0])
                rows = [_split_row(line) for line in tok.lines[2:]]
                doc.toc = TocBlock(block_id="doc.toc", role="toc",
                                   columns=columns, rows=rows)
                expect_toc_table = False
                continue
            if tok.kind == "prose":
                preamble_parts.append("\n".join(tok.lines))
                continue
            # 目次直後以外の前付表・code・quote は preamble に verbatim 退避
            preamble_parts.append("\n".join(tok.lines))
            continue

        # block_id 採番（owner は section / lead のいずれか）
        if cur_section is not None:
            block_counter += 1
            bid = f"{cur_section.id}.b{block_counter}"
            sink = cur_section.blocks
        else:
            lead_counter += 1
            prefix = f"ch{cur_chapter.id}" if cur_chapter is not None else f"ap{cur_appendix.id}"
            bid = f"{prefix}.lead.b{lead_counter}"
            sink = (cur_chapter or cur_appendix).lead_blocks

        if tok.kind == "table":
            sink.append(_table_block(tok, bid))
        elif tok.kind == "code":
            sink.append(_code_block(tok, bid))
        elif tok.kind == "quote":
            sink.append(_note_block(tok, bid))
        elif tok.kind == "prose":
            sink.append(_prose_block(tok, bid))
        else:
            sink.append(_prose_block(tok, bid))
            warnings.append(Warning(code="UNKNOWN_BLOCK",
                                    message=f"未知記法ヲ prose ニ退避: {tok.kind}",
                                    source_line=tok.start))

    doc.preamble = "\n\n".join(preamble_parts)
    return ParseResult(document=doc, chapters=chapters, appendices=appendices,
                       warnings=sorted(warnings, key=lambda w: w.source_line),
                       attribution=attribution)
