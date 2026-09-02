"""Tag-source loader for schema v2 profiles (4 種 dispatch).

Spec § 5.2.

`load_tag_source(profile, model_dir)` は profile.tag_source.type に応じて:
- csv: profiles 既存 parse_tags_csv_with_spec
- json_list: list[str] vocabulary、categories_mode=all_general 想定
- json_dict: 2 つの sub-form をサポート
    - parallel-arrays: tags_key + category_key (index 整列、長さ一致)
    - mapping (Camie v2 real HF): idx_to_tag_key + tag_to_category_key
  どちらも container_key で nested object に navigate 可能
- composite: tags_file + categories_file (別ファイル、index 整列)

返却は [(tag_str, category_str), ...] の index-order list。
categories_mode == "all_general" のときは全エントリの category を
"general" で上書きする (spec § 5.4)。

Cross-check (metadata 先読み):
- json_dict / composite の長さ整合
- category_map の値が supports_categories に含まれること
失敗時は MetadataLoadError を raise。spec § 5.6 metadata 先読み block。

ファイル読み込みは 32MB の bounded read。
"""
from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from .base import TaggerProfile
from .csv_parser import parse_tags_csv_with_spec

_METADATA_MAX_BYTES = 32 * 1024 * 1024  # 32MB (spec § 5.6)
_MAX_TAGS = 100_000  # spec § 5.6
_MAX_TAG_LEN = 256  # spec § 5.6


def _validate_pairs_caps(
    pairs: list[tuple[str, str]],
    *,
    ctx: str,
) -> None:
    if len(pairs) > _MAX_TAGS:
        raise MetadataLoadError(
            f"{ctx} produced {len(pairs)} tags exceeding cap {_MAX_TAGS}"
        )
    for tag, _ in pairs:
        if len(tag) > _MAX_TAG_LEN:
            raise MetadataLoadError(
                f"{ctx} contains tag of length {len(tag)} exceeding {_MAX_TAG_LEN}"
            )


class MetadataLoadError(Exception):
    """metadata file の読み込み / cross-check 失敗."""


def _read_json_bounded(path: Path, *, ctx: str) -> Any:
    """Read JSON with size cap + duplicate-key reject + BOM tolerated."""
    with open(path, "rb") as fh:
        raw = fh.read(_METADATA_MAX_BYTES + 1)
    if len(raw) > _METADATA_MAX_BYTES:
        raise MetadataLoadError(
            f"{ctx} {path.name} exceeds {_METADATA_MAX_BYTES} bytes"
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MetadataLoadError(f"{ctx} {path.name} not UTF-8: {exc}") from exc
    try:
        return json.loads(text, object_pairs_hook=_duplicate_key_hook)
    except (JSONDecodeError, ValueError) as exc:
        raise MetadataLoadError(f"{ctx} {path.name} invalid JSON: {exc}") from exc


def _duplicate_key_hook(pairs):
    seen: set[str] = set()
    for k, _ in pairs:
        if k in seen:
            raise ValueError(f"duplicate key {k!r}")
        seen.add(k)
    return dict(pairs)


def _apply_categories_mode(
    pairs: list[tuple[str, str]],
    profile: TaggerProfile,
) -> list[tuple[str, str]]:
    if profile.categories_mode == "all_general":
        return [(t, "general") for t, _ in pairs]
    return pairs


def _map_category_int(raw: Any, category_map: dict, ctx: str) -> str:
    """Map a raw int/str category value to category name via category_map."""
    # category_map keys may arrive as int (from python dict) or str (from JSON).
    if raw in category_map:
        return str(category_map[raw])
    key_str = str(raw)
    if key_str in category_map:
        return str(category_map[key_str])
    raise MetadataLoadError(
        f"{ctx} category value {raw!r} not in category_map {sorted(category_map)}"
    )


def load_tag_source(
    profile: TaggerProfile,
    model_dir: Path,
) -> list[tuple[str, str]]:
    """Dispatch on profile.tag_source.type and return ordered (tag, cat) pairs."""
    ts = profile.tag_source
    ts_type = ts.get("type")

    if ts_type == "csv":
        csv_path = model_dir / ts["file"]
        # Bounded read sentinel - reject CSV >32MB before opening the parser.
        try:
            size = csv_path.stat().st_size
        except OSError as exc:
            raise MetadataLoadError(f"tag_source.file {ts['file']!r}: {exc}") from exc
        if size > _METADATA_MAX_BYTES:
            raise MetadataLoadError(
                f"tag_source.file {ts['file']!r} exceeds {_METADATA_MAX_BYTES} bytes ({size})"
            )
        names, cats = parse_tags_csv_with_spec(
            csv_path,
            {
                "delimiter": ts.get("delimiter", ","),
                "name_col": ts.get("name_col", "name"),
                "category_col": ts.get("category_col", "category"),
                "category_map": ts.get("category_map", {}),
            },
        )
        pairs = list(zip(names, cats, strict=True))
        _validate_pairs_caps(pairs, ctx="tag_source.type=csv")
        return _apply_categories_mode(pairs, profile)

    if ts_type == "json_list":
        data = _read_json_bounded(model_dir / ts["file"], ctx="tag_source.file")
        if not isinstance(data, list):
            raise MetadataLoadError(
                f"tag_source.file {ts['file']!r} must be list[str], got {type(data).__name__}"
            )
        pairs = [(str(t), "general") for t in data]
        _validate_pairs_caps(pairs, ctx="tag_source.type=json_list")
        return _apply_categories_mode(pairs, profile)

    if ts_type == "json_dict":
        data = _read_json_bounded(model_dir / ts["file"], ctx="tag_source.file")
        if not isinstance(data, dict):
            raise MetadataLoadError(
                f"tag_source.file {ts['file']!r} must be object, got {type(data).__name__}"
            )
        # Navigate optional dotted container_key (e.g. "dataset_info.tag_mapping")
        container: Any = data
        ck = ts.get("container_key")
        if isinstance(ck, str) and ck:
            for part in ck.split("."):
                if not isinstance(container, dict) or part not in container:
                    raise MetadataLoadError(
                        f"tag_source.container_key={ck!r}: missing segment {part!r}"
                    )
                container = container[part]
        if not isinstance(container, dict):
            raise MetadataLoadError(
                f"tag_source.file/container must resolve to dict, got {type(container).__name__}"
            )

        # Mapping sub-form (Camie v2 real HF layout): idx_to_tag + tag_to_category
        if "idx_to_tag_key" in ts and "tag_to_category_key" in ts:
            idx_to_tag = container.get(ts["idx_to_tag_key"])
            tag_to_cat = container.get(ts["tag_to_category_key"])
            if not isinstance(idx_to_tag, dict) or not isinstance(tag_to_cat, dict):
                raise MetadataLoadError(
                    "json_dict mapping sub-form requires both keys to be dicts"
                )
            # idx_to_tag keys are stringified ints; sort by int for canonical order.
            try:
                ordered = sorted(idx_to_tag.items(), key=lambda kv: int(kv[0]))
            except (ValueError, TypeError) as exc:
                raise MetadataLoadError(
                    f"idx_to_tag_key {ts['idx_to_tag_key']!r}: keys must be int-castable strings"
                ) from exc
            pairs: list[tuple[str, str]] = []
            for _, tag_name in ordered:
                tag_str = str(tag_name)
                cat = tag_to_cat.get(tag_str)
                if cat is None:
                    raise MetadataLoadError(
                        f"tag_to_category missing entry for tag {tag_str!r}"
                    )
                pairs.append((tag_str, str(cat)))
            # Cross-check: categories ⊆ supports_categories (deferred from spec § 5.6)
            unknown = {c for _, c in pairs} - set(profile.supports_categories)
            if unknown:
                raise MetadataLoadError(
                    f"tag_to_category values {sorted(unknown)} not in supports_categories "
                    f"{list(profile.supports_categories)}"
                )
            _validate_pairs_caps(pairs, ctx="tag_source.type=json_dict(mapping)")
            return _apply_categories_mode(pairs, profile)

        # Parallel-arrays sub-form (original spec § 5.2): tags_key + category_key
        if "tags_key" in ts and "category_key" in ts:
            tags = container.get(ts["tags_key"])
            cats_raw = container.get(ts["category_key"])
            if not isinstance(tags, list) or not isinstance(cats_raw, list):
                raise MetadataLoadError(
                    f"tag_source.file {ts['file']!r} tags_key/category_key must be lists"
                )
            if len(tags) != len(cats_raw):
                raise MetadataLoadError(
                    f"tag_source.file {ts['file']!r} length mismatch: "
                    f"tags={len(tags)} categories={len(cats_raw)}"
                )
            cmap = ts.get("category_map", {})
            pairs = [
                (str(t), _map_category_int(c, cmap, ctx=f"tag_source.file {ts['file']!r}"))
                for t, c in zip(tags, cats_raw, strict=True)
            ]
            _validate_pairs_caps(pairs, ctx="tag_source.type=json_dict(parallel)")
            return _apply_categories_mode(pairs, profile)

        raise MetadataLoadError(
            "json_dict requires either (idx_to_tag_key + tag_to_category_key) "
            "or (tags_key + category_key)"
        )

    if ts_type == "composite":
        tags_data = _read_json_bounded(model_dir / ts["tags_file"], ctx="tag_source.tags_file")
        cats_data = _read_json_bounded(model_dir / ts["categories_file"], ctx="tag_source.categories_file")
        if not isinstance(tags_data, list) or not isinstance(cats_data, list):
            raise MetadataLoadError("composite files must be list[]")
        if len(tags_data) != len(cats_data):
            raise MetadataLoadError(
                f"composite length mismatch: tags={len(tags_data)} cats={len(cats_data)}"
            )
        cmap = ts.get("category_map", {})
        pairs = [
            (str(t), _map_category_int(c, cmap, ctx="composite"))
            for t, c in zip(tags_data, cats_data, strict=True)
        ]
        _validate_pairs_caps(pairs, ctx="tag_source.type=composite")
        return _apply_categories_mode(pairs, profile)

    raise MetadataLoadError(f"tag_source.type={ts_type!r} not supported")
