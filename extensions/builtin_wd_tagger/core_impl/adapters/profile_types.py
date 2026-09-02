"""Tagger profile dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .profile_validation import (
    ALLOWED_FILE_EXTS,
    RE_FILE_NAME,
    RE_MODEL_ID,
    SUPPORTED_PROFILE_VERSIONS,
    USER_ADAPTER_FAMILY_ALLOWLIST,
    USER_BACKEND_ALLOWLIST,
    v1_tag_csv_spec_to_tag_source,
    validate_cross_check,
    validate_display_name,
    validate_hf_subdir,
    validate_output_spec,
    validate_preprocess_spec,
)


class UnsupportedProfileVersion(Exception):
    """Raised when a profile JSON has an unknown profile_version."""


@dataclass(frozen=True)
class ProfileFile:
    """One file referenced by a TaggerProfile."""

    name: str
    required: bool = True
    size_hint_mb: float = 0.0


@dataclass(frozen=True)
class TaggerProfile:
    """Configuration profile for one tagger model."""

    profile_version: str
    source_profile_version: str
    id: str
    display_name: str
    model_id: str
    adapter_family: str
    backend: str
    builtin: bool
    files: tuple[ProfileFile, ...]
    preprocess_spec: dict[str, Any]
    tag_source: dict[str, Any]
    threshold_source: dict[str, Any]
    categories_mode: str
    supports_categories: tuple[str, ...]
    default_thresholds: dict[str, float]
    hf_subdir: str | None = None
    output_spec: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict, *, origin: str = "builtin") -> TaggerProfile:
        version = _validate_version(data, origin)
        _require_core_fields(data)
        tag_source, threshold_source, categories_mode, hf_subdir = _normalize_v2_fields(data, version)
        profile_id = _validate_profile_id(data["id"])
        model_id = _validate_model_id(data["model_id"])
        files = _parse_files(data["files"])
        _validate_thresholds(data["default_thresholds"])
        hf_subdir = validate_hf_subdir(hf_subdir)
        display_name = validate_display_name(data["display_name"])
        validate_preprocess_spec(data["preprocess_spec"])
        supports_categories = _validate_supports_categories(data["supports_categories"])
        validate_cross_check(
            tag_source=tag_source,
            threshold_source=threshold_source,
            categories_mode=str(categories_mode),
            supports_categories=supports_categories,
            files=tuple(files),
        )
        adapter_family = str(data["adapter_family"])
        backend = str(data["backend"])
        _validate_user_origin(origin, adapter_family, backend)
        return cls(
            profile_version="2",
            source_profile_version=version,
            id=profile_id,
            display_name=display_name,
            model_id=model_id,
            adapter_family=adapter_family,
            backend=backend,
            builtin=bool(data["builtin"]),
            files=tuple(files),
            preprocess_spec=dict(data["preprocess_spec"]),
            tag_source=dict(tag_source),
            threshold_source=dict(threshold_source),
            categories_mode=str(categories_mode),
            supports_categories=supports_categories,
            default_thresholds=dict(data["default_thresholds"]),
            hf_subdir=hf_subdir,
            output_spec=validate_output_spec(data.get("output_spec")),
        )


def _validate_version(data: dict, origin: str) -> str:
    version = data.get("profile_version")
    if not isinstance(version, str) or version not in SUPPORTED_PROFILE_VERSIONS:
        raise UnsupportedProfileVersion(
            f"profile_version={version!r} not in {sorted(SUPPORTED_PROFILE_VERSIONS)}"
        )
    if origin == "user" and version != "2":
        raise ValueError(f"user drop-in profile must be profile_version=\"2\", got {version!r}")
    return version


def _require_core_fields(data: dict) -> None:
    for key in (
        "id", "display_name", "model_id", "adapter_family", "backend",
        "builtin", "files", "preprocess_spec", "default_thresholds",
        "supports_categories",
    ):
        if key not in data:
            raise KeyError(f"profile field missing: {key}")


def _normalize_v2_fields(data: dict, version: str) -> tuple[dict, dict, str, str | None]:
    if version == "1":
        return v1_tag_csv_spec_to_tag_source(data), {"type": "global_per_category"}, "from_tag_source", None
    for key in ("tag_source", "threshold_source"):
        if key not in data:
            raise KeyError(f"v2 profile missing: {key}")
    ts = data["tag_source"]
    th = data["threshold_source"]
    if not isinstance(ts, dict):
        raise ValueError(f"tag_source must be a dict: {ts!r}")
    if not isinstance(th, dict):
        raise ValueError(f"threshold_source must be a dict: {th!r}")
    return (
        ts,
        th,
        data.get("categories_mode", "from_tag_source"),
        data.get("hf_subdir"),
    )


def _validate_profile_id(profile_id: object) -> str:
    if not isinstance(profile_id, str) or not RE_FILE_NAME.match(profile_id) or ".." in profile_id:
        raise ValueError(f"invalid profile id: {profile_id!r} (must match {RE_FILE_NAME.pattern}, no path separators)")
    return profile_id


def _validate_model_id(model_id: object) -> str:
    if not isinstance(model_id, str) or not RE_MODEL_ID.match(model_id) or ".." in model_id:
        raise ValueError(f"invalid model_id: {model_id!r}")
    return model_id


def _parse_files(files_raw: object) -> list[ProfileFile]:
    if not isinstance(files_raw, list) or not files_raw:
        raise ValueError("files must be a non-empty list")
    files: list[ProfileFile] = []
    for file_data in files_raw:
        if not isinstance(file_data, dict):
            raise ValueError(f"files[] element must be a dict: {file_data!r}")
        name = file_data.get("name")
        _validate_file_name(name)
        raw_size = file_data.get("size_hint_mb", 0.0)
        if isinstance(raw_size, bool) or not isinstance(raw_size, (int, float)):
            raise ValueError(f"files[].size_hint_mb must be numeric: {raw_size!r}")
        files.append(ProfileFile(
            name=name,
            required=bool(file_data.get("required", True)),
            size_hint_mb=float(raw_size),
        ))
    return files


def _validate_file_name(name: object) -> None:
    if (
        not isinstance(name, str)
        or not RE_FILE_NAME.match(name)
        or ".." in name
        or "/" in name
        or "\\" in name
        or any(ord(c) < 0x20 or ord(c) == 0x7F for c in name)
    ):
        raise ValueError(f"invalid file name (must be basename only): {name!r}")
    ext_pos = name.rfind(".")
    ext = name[ext_pos:].lower() if ext_pos >= 0 else ""
    if ext not in ALLOWED_FILE_EXTS:
        raise ValueError(f"file extension {ext!r} not in allowed list {sorted(ALLOWED_FILE_EXTS)}")


def _validate_supports_categories(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"supports_categories must be a list: {value!r}")
    for item in value:
        if not isinstance(item, str):
            raise ValueError(f"supports_categories elements must be strings: {item!r}")
    return tuple(value)


def _validate_thresholds(thresholds_raw: object) -> None:
    if not isinstance(thresholds_raw, dict):
        raise ValueError("default_thresholds must be a dict")
    for cat_name, threshold in thresholds_raw.items():
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
            raise ValueError(f"default_thresholds[{cat_name!r}] must be numeric, got {type(threshold).__name__}")
        if not 0.0 <= float(threshold) <= 1.0:
            raise ValueError(f"default_thresholds[{cat_name!r}]={threshold} out of range [0.0, 1.0]")


def _validate_user_origin(origin: str, adapter_family: str, backend: str) -> None:
    if origin != "user":
        return
    if adapter_family not in USER_ADAPTER_FAMILY_ALLOWLIST:
        raise ValueError(
            f"adapter_family {adapter_family!r} not in user allowlist {sorted(USER_ADAPTER_FAMILY_ALLOWLIST)}"
        )
    if backend not in USER_BACKEND_ALLOWLIST:
        raise ValueError(f"backend {backend!r} not in user allowlist {sorted(USER_BACKEND_ALLOWLIST)}")
