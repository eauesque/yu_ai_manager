"""Markdown ブロックトークナイザ（GFM subset・第 2.2.8 節）。

入力は NFC+LF 正規化済みテキスト。各 token は 1 起点の行範囲を持ち、
全入力行がちょうど一つの token に属す（行帰属 R1 の基盤・第 2.2.10 節）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_FENCE_RE = re.compile(r"^```(.*)$")
_HR_RE = re.compile(r"^---\s*$")
# 表区切線: 全セルがダッシュ（コロン整列可）。例 |---|:--:|
_TABLE_SEP_RE = re.compile(r"^\s*\|?(\s*:?-{1,}:?\s*\|)+\s*:?-{0,}:?\s*\|?\s*$")


@dataclass
class Token:
    kind: str               # h1/h2/h3/h4plus/table/code/quote/prose/hr/blank
    lines: list[str]        # 内容行（code はフェンス除く内側、それ以外は全行）
    start: int              # 1 起点・包含
    end: int                # 1 起点・包含
    lang: str | None = field(default=None)


def _heading_kind(line: str) -> str | None:
    m = re.match(r"^(#{1,6})\s", line)
    if not m:
        return None
    level = len(m.group(1))
    if level == 1:
        return "h1"
    if level == 2:
        return "h2"
    if level == 3:
        return "h3"
    return "h4plus"


def _is_table_row(line: str) -> bool:
    return "|" in line and line.strip() != ""


def tokenize(text: str) -> list[Token]:
    lines = text.split("\n")
    # 末尾改行で生じる空文字要素は行として数えない
    if lines and lines[-1] == "":
        lines = lines[:-1]
    tokens: list[Token] = []
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i]
        lineno = i + 1
        # blank
        if ln.strip() == "":
            tokens.append(Token("blank", [ln], lineno, lineno))
            i += 1
            continue
        # code fence
        m = _FENCE_RE.match(ln)
        if m:
            lang = m.group(1).strip() or None
            body: list[str] = []
            j = i + 1
            while j < n and not _FENCE_RE.match(lines[j]):
                body.append(lines[j])
                j += 1
            end = j + 1 if j < n else j  # 閉フェンス行番号（1 起点）。無ければ末尾。
            tokens.append(Token("code", body, lineno, min(end, n), lang))
            i = j + 1 if j < n else n
            continue
        # heading
        hk = _heading_kind(ln)
        if hk:
            tokens.append(Token(hk, [ln], lineno, lineno))
            i += 1
            continue
        # hr
        if _HR_RE.match(ln):
            tokens.append(Token("hr", [ln], lineno, lineno))
            i += 1
            continue
        # quote
        if ln.lstrip().startswith(">"):
            body = [ln]
            j = i + 1
            while j < n and lines[j].lstrip().startswith(">"):
                body.append(lines[j])
                j += 1
            tokens.append(Token("quote", body, lineno, j))
            i = j
            continue
        # table: 現行が pipe 行 かつ 次行が区切線
        if _is_table_row(ln) and i + 1 < n and _TABLE_SEP_RE.match(lines[i + 1]):
            body = [ln, lines[i + 1]]
            j = i + 2
            while j < n and _is_table_row(lines[j]) and lines[j].strip() != "":
                body.append(lines[j])
                j += 1
            tokens.append(Token("table", body, lineno, j))
            i = j
            continue
        # prose: 空行/特殊行まで連続
        body = [ln]
        j = i + 1
        while j < n:
            nxt = lines[j]
            if nxt.strip() == "" or _heading_kind(nxt) or _HR_RE.match(nxt) \
               or _FENCE_RE.match(nxt) or nxt.lstrip().startswith(">"):
                break
            # 次行が表開始ならそこで切る
            if _is_table_row(nxt) and j + 1 < n and _TABLE_SEP_RE.match(lines[j + 1]):
                break
            body.append(nxt)
            j += 1
        tokens.append(Token("prose", body, lineno, j))
        i = j
    return tokens
