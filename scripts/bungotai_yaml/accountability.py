"""行帰属（R1・第 2.2.10 節）。token から各原本行を retained/ignore に分類。

ignore-set は構造マーカーのみ消費する（表区切線・コードフェンス開閉・hr・code 外空行）。
見出し本文・引用本文・表データ・コード内側は retained。全行がちょうど一分類に属す。
"""
from __future__ import annotations

from bungotai_yaml.tokenize import Token


def attribute_lines(tokens: list[Token]) -> dict[int, str]:
    """各行番号（1 起点）→ 分類ラベル（"retained:*" / "ignore:*"）の写像を返す。"""
    attr: dict[int, str] = {}
    for t in tokens:
        if t.kind == "blank":
            attr[t.start] = "ignore:blank"
        elif t.kind == "hr":
            attr[t.start] = "ignore:hr"
        elif t.kind in ("h1", "h2", "h3"):
            attr[t.start] = "retained:heading"
        elif t.kind == "quote":
            for ln in range(t.start, t.end + 1):
                attr[ln] = "retained:note"
        elif t.kind == "prose":
            for ln in range(t.start, t.end + 1):
                attr[ln] = "retained:prose"
        elif t.kind == "table":
            for ln in range(t.start, t.end + 1):
                attr[ln] = "ignore:table-sep" if ln == t.start + 1 else "retained:table"
        elif t.kind == "code":
            for ln in range(t.start, t.end + 1):
                attr[ln] = "ignore:fence" if ln in (t.start, t.end) else "retained:code"
        else:  # h4plus 等はここに到達する前に parser が fail-loud
            for ln in range(t.start, t.end + 1):
                attr[ln] = f"unclassified:{t.kind}"
    return attr


def count_table_data_rows(tokens: list[Token]) -> int:
    """全 table token のデータ行総数（ヘッダ・区切線を除く）。R1b 用。"""
    total = 0
    for t in tokens:
        if t.kind == "table":
            total += max(0, (t.end - t.start + 1) - 2)
    return total
