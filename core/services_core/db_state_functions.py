"""SQLite custom functions and normalization helpers."""

import re
import unicodedata

from core.services_core.db_cipher import sqlite3


def _sqlite_regexp(pattern: str, value: str) -> bool:
    if value is None:
        return False
    try:
        return re.search(pattern, value) is not None
    except re.error:
        return False


_SEARCH_NORMALIZE_TABLE = str.maketrans({
    "\u30fc": "-",
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u2212": "-",
    "\u301c": "~",
    "\u30fb": "\u00b7",
})


def _sqlite_nfkc_lower(value: str) -> str:
    if value is None:
        return value
    return unicodedata.normalize("NFKC", value).lower().translate(_SEARCH_NORMALIZE_TABLE)


def nfkc_lower(value: str) -> str:
    if value is None:
        return value
    return unicodedata.normalize("NFKC", value).lower().translate(_SEARCH_NORMALIZE_TABLE)


def register_custom_functions(con: sqlite3.Connection) -> None:
    con.create_function("REGEXP", 2, _sqlite_regexp)
    con.create_function("nfkc_lower", 1, _sqlite_nfkc_lower)
