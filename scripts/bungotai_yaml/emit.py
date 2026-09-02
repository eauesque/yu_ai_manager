"""YAML 出力（logical order）+ canonical content（比較用）。第 2.5.3 節。"""
from __future__ import annotations

import copy

import yaml

from bungotai_yaml import SCHEMA_VERSION
from bungotai_yaml.model import (
    Appendix,
    Block,
    Chapter,
    ParseResult,
    Section,
    TocBlock,
)


def _block_dict(b: Block) -> dict:
    d: dict = {"type": b.type, "block_id": b.block_id}
    if b.type == "table":
        d["role"] = b.role
        d["columns"] = b.columns
        d["rows"] = b.rows
    elif b.type == "prose":
        d["text"] = b.text
    elif b.type == "code":
        d["lang"] = b.lang
        d["content"] = b.content
    elif b.type == "note":
        d["label"] = b.label
        d["text"] = b.text
    return d


def _section_dict(s: Section) -> dict:
    return {"id": s.id, "heading": s.heading,
            "blocks": [_block_dict(b) for b in s.blocks]}


def _chapter_dict(c: Chapter) -> dict:
    return {
        "id": c.id,
        "number_label": c.number_label,
        "title_ja": c.title_ja,
        "title_en": c.title_en,
        "title_note": c.title_note,
        "source_line": c.source_line,
        "lead_blocks": [_block_dict(b) for b in c.lead_blocks],
        "sections": [_section_dict(s) for s in c.sections],
    }


def _appendix_dict(a: Appendix) -> dict:
    return {
        "id": a.id,
        "number_label": a.number_label,
        "title_ja": a.title_ja,
        "title_en": a.title_en,
        "title_note": a.title_note,
        "source_line": a.source_line,
        "lead_blocks": [_block_dict(b) for b in a.lead_blocks],
        "sections": [_section_dict(s) for s in a.sections],
    }


def _toc_dict(t: TocBlock | None) -> dict | None:
    if t is None:
        return None
    return {"block_id": t.block_id, "role": t.role,
            "columns": t.columns, "rows": t.rows}


def to_artifact_dict(result: ParseResult, index: dict, meta: dict) -> dict:
    """logical order の生成物 dict を構築（第 2.5.3 節 出力順）。"""
    ordered_meta = {
        "source_path": meta["source_path"],
        "source_sha256": meta["source_sha256"],
        "generator_version": meta["generator_version"],
        "generated_at": meta["generated_at"],   # 末尾（揮発）
    }
    document = {
        "title": result.document.title,
        "subtitle": result.document.subtitle,
        "preamble": result.document.preamble,
        "toc": _toc_dict(result.document.toc),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "meta": ordered_meta,
        "document": document,
        "chapters": [_chapter_dict(c) for c in result.chapters],
        "appendices": [_appendix_dict(a) for a in result.appendices],
        "index": index,
        "warnings": [
            {"code": w.code, "message": w.message,
             "source_line": w.source_line, "severity": w.severity}
            for w in result.warnings
        ],
    }


def dump_artifact(artifact: dict) -> str:
    """生成物を logical order（挿入順保存）で YAML 文字列化。NFR4。"""
    return yaml.safe_dump(artifact, allow_unicode=True, sort_keys=False,
                          indent=2, width=10_000)


def canonical_content(artifact: dict) -> str:
    """canonical content（第 2.5.3 節）: generated_at 除去 + sort_keys=True。"""
    obj = copy.deepcopy(artifact)
    if isinstance(obj.get("meta"), dict):
        obj["meta"].pop("generated_at", None)
    return yaml.safe_dump(obj, allow_unicode=True, sort_keys=True,
                          indent=2, width=10_000)
