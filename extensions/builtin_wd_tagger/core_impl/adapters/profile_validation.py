"""Validation helpers for tagger profile JSON."""

from __future__ import annotations

import math
import re

SUPPORTED_PROFILE_VERSIONS: frozenset[str] = frozenset({"1", "2"})

RE_MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9._-]{1,95}$")
RE_FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
ALLOWED_FILE_EXTS: frozenset[str] = frozenset({".onnx", ".csv", ".json", ".safetensors", ".txt"})
USER_ADAPTER_FAMILY_ALLOWLIST: frozenset[str] = frozenset({"wd", "camie", "oppai", "generic_onnx"})
USER_BACKEND_ALLOWLIST: frozenset[str] = frozenset({"onnx"})

_RE_HF_SUBDIR_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")
_HF_SUBDIR_MAX_DEPTH = 4
_DISPLAY_NAME_MAX_LEN = 128
_DTYPE_ENUM = frozenset({"float32", "float16"})
_LAYOUT_ENUM = frozenset({"NCHW", "NHWC"})
_CHANNEL_ORDER_ENUM = frozenset({"RGB", "BGR"})
_RESIZE_ENUM = frozenset({"letterbox", "longest_side_pad", "stretch"})
_ACTIVATION_ENUM = frozenset({"none", "sigmoid"})
_INPUT_SIZE_MIN = 32
_INPUT_SIZE_MAX = 2048


def validate_preprocess_spec(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise ValueError(f"preprocess_spec must be dict: {type(spec).__name__}")
    size = spec.get("input_size")
    if not isinstance(size, int) or isinstance(size, bool):
        raise ValueError(f"preprocess_spec.input_size must be int: {size!r}")
    if not _INPUT_SIZE_MIN <= size <= _INPUT_SIZE_MAX:
        raise ValueError(f"preprocess_spec.input_size out of range [{_INPUT_SIZE_MIN},{_INPUT_SIZE_MAX}]: {size}")
    for field, enum in (
        ("dtype", _DTYPE_ENUM),
        ("layout", _LAYOUT_ENUM),
        ("channel_order", _CHANNEL_ORDER_ENUM),
        ("resize_strategy", _RESIZE_ENUM),
    ):
        v = spec.get(field)
        if v is not None and v not in enum:
            raise ValueError(f"preprocess_spec.{field}={v!r} not in {sorted(enum)}")
    _validate_preprocess_number(spec.get("scale"), "scale", positive=True, max_value=1.0)
    for field in ("mean", "std", "pad_color"):
        _validate_preprocess_array(spec.get(field), field)
    return spec


def _validate_preprocess_number(value: object, field: str, *, positive: bool, max_value: float | None = None) -> None:
    if value is None:
        return
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"preprocess_spec.{field} must be numeric: {value!r}")
    numeric = float(value)
    if not math.isfinite(numeric) or (positive and numeric <= 0.0) or (max_value is not None and numeric > max_value):
        raise ValueError(f"preprocess_spec.{field} out of range (0,1]: {value}")


def _validate_preprocess_array(value: object, field: str) -> None:
    if value is None:
        return
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"preprocess_spec.{field} must be length-3 list: {value!r}")
    for item in value:
        if not isinstance(item, (int, float)) or isinstance(item, bool):
            raise ValueError(f"preprocess_spec.{field} element not numeric: {item!r}")
        if not math.isfinite(float(item)):
            raise ValueError(f"preprocess_spec.{field} element not finite: {item!r}")
    if field == "std" and any(float(item) <= 0.0 for item in value):
        raise ValueError(f"preprocess_spec.std must be all positive: {value!r}")


def validate_output_spec(spec: object) -> dict:
    """Validate profile.output_spec — which model output head to read, and
    whether its values still need an activation applied.

    Omitted (or empty) means: read the first ONNX output verbatim, which is
    what every v1 WD profile relies on. Models whose exported graph emits
    logits, or emits several heads, must say so here; guessing produces
    plausible-but-wrong tags rather than an error.
    """
    if spec is None:
        return {}
    if not isinstance(spec, dict):
        raise ValueError(f"output_spec must be dict or null: {type(spec).__name__}")
    key = spec.get("output_key")
    if key is not None and (not isinstance(key, str) or not key):
        raise ValueError(f"output_spec.output_key must be a non-empty string or null: {key!r}")
    activation = spec.get("activation", "none")
    if activation not in _ACTIVATION_ENUM:
        raise ValueError(
            f"output_spec.activation={activation!r} not in {sorted(_ACTIVATION_ENUM)}"
        )
    return {"output_key": key, "activation": str(activation)}


def validate_hf_subdir(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"hf_subdir must be non-empty string or null: {value!r}")
    segments = value.split("/")
    if len(segments) > _HF_SUBDIR_MAX_DEPTH:
        raise ValueError(f"hf_subdir exceeds {_HF_SUBDIR_MAX_DEPTH} levels: {value!r}")
    for seg in segments:
        if seg in ("", ".", "..") or not _RE_HF_SUBDIR_SEGMENT.match(seg):
            raise ValueError(f"hf_subdir contains invalid segment {seg!r} in {value!r}")
    return value


def validate_display_name(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"display_name must be str: {value!r}")
    if len(value) > _DISPLAY_NAME_MAX_LEN:
        raise ValueError(f"display_name exceeds {_DISPLAY_NAME_MAX_LEN} chars: len={len(value)}")
    for ch in value:
        if ord(ch) < 0x20 or ord(ch) == 0x7F:
            raise ValueError(f"display_name contains control char U+{ord(ch):04X}")
    return value


def v1_tag_csv_spec_to_tag_source(data: dict) -> dict:
    spec = data.get("tag_csv_spec")
    if not isinstance(spec, dict):
        raise KeyError("v1 profile missing tag_csv_spec")
    return {
        "type": "csv",
        "file": "selected_tags.csv",
        "delimiter": spec.get("delimiter", ","),
        "name_col": spec.get("name_col", "name"),
        "category_col": spec.get("category_col", "category"),
        "category_map": dict(spec.get("category_map", {})),
    }


def validate_cross_check(
    *,
    tag_source: dict,
    threshold_source: dict,
    categories_mode: str,
    supports_categories: tuple[str, ...],
    files: tuple[object, ...],
) -> None:
    by_name = {f.name: f for f in files}
    refs = _tag_source_refs(tag_source) + _threshold_source_refs(threshold_source)
    for field, fname in refs:
        f = by_name.get(fname)
        if f is None:
            raise ValueError(f"{field}={fname!r} not in profile.files[]")
        if not f.required:
            raise ValueError(f"{field}={fname!r} must have required=true (cross-check)")
    _validate_category_consistency(tag_source, categories_mode, supports_categories)


def _tag_source_refs(tag_source: dict) -> list[tuple[str, str]]:
    ts_type = tag_source.get("type")
    if ts_type in ("csv", "json_list", "json_dict"):
        fname = tag_source.get("file")
        if not isinstance(fname, str):
            raise ValueError(f"tag_source.file must be str for type={ts_type!r}")
        return [("tag_source.file", fname)]
    if ts_type == "composite":
        refs = []
        for key in ("tags_file", "categories_file"):
            fname = tag_source.get(key)
            if not isinstance(fname, str):
                raise ValueError(f"tag_source.{key} must be str for composite")
            refs.append((f"tag_source.{key}", fname))
        return refs
    raise ValueError(f"tag_source.type={ts_type!r} not in csv/json_list/json_dict/composite")


def _threshold_source_refs(threshold_source: dict) -> list[tuple[str, str]]:
    ths_type = threshold_source.get("type")
    if ths_type == "global_per_category":
        return []
    if ths_type == "per_tag_json":
        fname = threshold_source.get("file")
        if not isinstance(fname, str):
            raise ValueError("threshold_source.file must be str for per_tag_json")
        return [("threshold_source.file", fname)]
    raise ValueError(f"threshold_source.type={ths_type!r} not in global_per_category/per_tag_json")


def _validate_category_consistency(tag_source: dict, categories_mode: str, supports_categories: tuple[str, ...]) -> None:
    if categories_mode == "all_general":
        if list(supports_categories) != ["general"]:
            raise ValueError(
                "categories_mode=all_general requires supports_categories==['general'], "
                f"got {list(supports_categories)}"
            )
        return
    if categories_mode != "from_tag_source":
        raise ValueError(f"categories_mode={categories_mode!r} not in from_tag_source/all_general")
    if tag_source.get("type") == "json_dict" and "idx_to_tag_key" in tag_source:
        return
    category_map = tag_source.get("category_map") or {}
    if not isinstance(category_map, dict):
        raise ValueError(f"tag_source.category_map must be a dict: {category_map!r}")
    for _v in category_map.values():
        if not isinstance(_v, str):
            raise ValueError(f"tag_source.category_map values must be strings: {_v!r}")
    unknown = set(category_map.values()) - set(supports_categories)
    if unknown:
        raise ValueError(f"tag_source.category_map values {sorted(unknown)} not in supports_categories")
