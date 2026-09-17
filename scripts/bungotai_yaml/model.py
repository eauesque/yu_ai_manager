"""bungotai YAML データモデル（第 2.1 節）。dataclass で構造を保持する。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Block:
    type: str                       # table / prose / code / note
    block_id: str
    # table
    role: str | None = None
    columns: list[str] | None = None
    rows: list[list[str]] | None = None
    # prose / note
    text: str | None = None
    # note
    label: str | None = None
    # code
    lang: str | None = None
    content: str | None = None


@dataclass
class Section:
    id: str
    heading: str
    blocks: list[Block] = field(default_factory=list)


@dataclass
class Chapter:
    id: int
    number_label: str
    title_ja: str
    title_en: str
    title_note: str | None = None
    source_line: int | None = None
    lead_blocks: list[Block] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)


@dataclass
class Appendix:
    id: str                         # "A".."D"
    number_label: str
    title_ja: str
    title_en: str
    title_note: str | None = None
    source_line: int | None = None
    lead_blocks: list[Block] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)


@dataclass
class TocBlock:
    block_id: str
    role: str
    columns: list[str]
    rows: list[list[str]]


@dataclass
class Document:
    title: str
    subtitle: str
    preamble: str
    toc: TocBlock | None = None


@dataclass
class Warning:
    code: str
    message: str
    source_line: int
    severity: str = "warn"


@dataclass
class ParseResult:
    document: Document
    chapters: list[Chapter] = field(default_factory=list)
    appendices: list[Appendix] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    attribution: dict[int, str] = field(default_factory=dict)
