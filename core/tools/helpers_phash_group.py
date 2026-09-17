"""pHash grouping helpers."""

from collections import defaultdict
from functools import lru_cache
from typing import Any

import numpy as np

_NP_BITCOUNT = getattr(np, "bitwise_count", None)
_PHASH_GROUP_CHUNK_SIZE = 256


@lru_cache(maxsize=8192)
def hamming_distance_hex(h1: str, h2: str) -> int:
    try:
        i1 = int(h1, 16)
        i2 = int(h2, 16)
        return bin(i1 ^ i2).count("1")
    except (ValueError, TypeError):
        return 999


def _is_valid_uint64_hex(value: Any) -> bool:
    if not isinstance(value, str) or not value or len(value) > 16:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _phash_values_and_valid_mask(items: list[tuple[Any, Any, Any]]) -> tuple[np.ndarray, np.ndarray]:
    values: list[int] = []
    valid: list[bool] = []
    for _, _, phash in items:
        if _is_valid_uint64_hex(phash):
            values.append(int(phash, 16))
            valid.append(True)
        else:
            values.append(0)
            valid.append(False)
    return np.array(values, dtype=np.uint64), np.array(valid, dtype=np.bool_)


def _popcount64(x: np.ndarray) -> np.ndarray:
    if _NP_BITCOUNT is not None:
        return _NP_BITCOUNT(x).astype(np.uint8, copy=False)

    # Constants and shifts must stay uint64; Python ints can promote to object.
    m1 = np.uint64(0x5555555555555555)
    m2 = np.uint64(0x3333333333333333)
    m4 = np.uint64(0x0F0F0F0F0F0F0F0F)
    h01 = np.uint64(0x0101010101010101)
    x = x - ((x >> np.uint64(1)) & m1)
    x = (x & m2) + ((x >> np.uint64(2)) & m2)
    x = (x + (x >> np.uint64(4))) & m4
    return ((x * h01) >> np.uint64(56)).astype(np.uint8, copy=False)


def find_phash_groups(rows, threshold: int):
    """Build groups by pHash Hamming distance.

    Only 1-16 digit hexadecimal pHash values are compared. Empty, non-hex,
    None, and over-16-digit values are excluded from comparison and remain
    singleton entries, matching the operational 64-bit pHash contract.
    """
    parent = {}

    def find(x):
        # Iterative path compression: recursion overflows at depth ~1000 when
        # threshold>=64 unions all valid rows into a single chain.
        parent.setdefault(x, x)
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(a, b):
        pa, pb = find(a), find(b)
        if pa != pb:
            parent[pa] = pb

    items = [(r[0], r[1], r[2]) for r in rows]
    if len(items) > 10000:
        items = items[:10000]

    phash_values, valid_mask = _phash_values_and_valid_mask(items)
    valid_indices = np.flatnonzero(valid_mask)

    if threshold >= 64:
        if valid_indices.size > 1:
            first = int(valid_indices[0])
            for idx in valid_indices[1:].tolist():
                union(first, int(idx))
    elif threshold >= 0:
        item_count = len(items)
        for i0 in range(0, item_count, _PHASH_GROUP_CHUNK_SIZE):
            i1 = min(i0 + _PHASH_GROUP_CHUNK_SIZE, item_count)
            block = np.bitwise_xor(phash_values[i0:i1, None], phash_values[None, :])
            dist = _popcount64(block)
            valid = valid_mask[i0:i1, None] & valid_mask[None, :]
            hit_mask = (dist <= threshold) & valid
            ii, jj = np.where(hit_mask)
            ii_global = ii + i0
            upper = jj > ii_global
            for a, b in zip(ii_global[upper].tolist(), jj[upper].tolist(), strict=False):
                union(int(a), int(b))

    group_map = defaultdict(list)
    for idx, (fid, path, phash) in enumerate(items):
        root = find(idx)
        group_map[root].append({"id": fid, "path": path, "phash": phash})

    groups: list[dict[str, Any]] = []
    for members in group_map.values():
        if len(members) > 1:
            groups.append(
                {
                    "hash": f"phash_group_{len(groups)}",
                    "count": len(members),
                    "files": [m["path"] for m in members],
                    "ids": [m["id"] for m in members],
                    "similarity": "perceptual",
                }
            )

    groups.sort(key=lambda g: -g["count"])
    return groups
