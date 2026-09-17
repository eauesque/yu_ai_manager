"""漢数字 → 整数 変換（第 2.2.3 節）。対象範囲 一〜三十一。解釈不能は ValueError。"""
from __future__ import annotations

_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9}


def kansuji_to_int(text: str) -> int:
    """`一`〜`三十一` を整数化。複合漢数字（二十三 等）を解釈。範囲外・不正は ValueError。"""
    s = text.strip()
    if not s:
        raise ValueError("empty kansuji")
    if s == "十":
        return 10
    if "十" in s:
        tens, _, ones = s.partition("十")
        if tens and tens not in _DIGITS:
            raise ValueError(f"unparseable kansuji tens: {text!r}")
        if ones and ones not in _DIGITS:
            raise ValueError(f"unparseable kansuji ones: {text!r}")
        value = (_DIGITS[tens] if tens else 1) * 10 + (_DIGITS[ones] if ones else 0)
        if not 10 <= value <= 31:
            raise ValueError(f"kansuji out of supported range: {text!r}")
        return value
    if len(s) == 1 and s in _DIGITS:
        return _DIGITS[s]
    raise ValueError(f"unparseable kansuji: {text!r}")
