"""原本 sha256（第 2.4.2 節）。生バイト列・NFC/LF 正規化前・BOM 含む。"""
from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_raw(path: str | Path) -> str:
    """ワーキングツリー上のファイルを生バイトで読み、SHA-256 を十六進小文字 64 字で返す。"""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
