"""TaggerRegistry — singleton holder for TaggerProfiles.

Loads builtin profiles from extensions/builtin_wd_tagger/core_impl/profiles/.
User profiles (Phase 3) will be added later. EngineCache integration also
happens in Phase 1b (invalidate hooks).

Spec § 3.1, § 4.1, § 5.4.
"""
from __future__ import annotations

import json
import logging
import threading
from json import JSONDecodeError
from pathlib import Path

from core.paths import get_profiles_dir

from .adapters.base import TaggerProfile

logger = logging.getLogger(__name__)

_BUILTIN_PROFILES_DIR = Path(__file__).resolve().parent / "profiles"
_PROFILE_JSON_MAX_BYTES = 1 * 1024 * 1024  # 1MB (spec § 5.6)
_USER_ALLOWED_FAMILIES = {"wd", "camie", "oppai", "generic_onnx"}
_USER_ALLOWED_BACKENDS = {"onnx"}


def _duplicate_key_hook(pairs):
    seen: set[str] = set()
    for k, _ in pairs:
        if k in seen:
            raise ValueError(f"duplicate key {k!r} in profile JSON")
        seen.add(k)
    return dict(pairs)


class TaggerRegistry:
    """Singleton holder for TaggerProfiles."""

    _instance: TaggerRegistry | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._profiles: dict[str, TaggerProfile] = {}
        self._origin_map: dict[str, str] = {}
        self._builtin_ids: frozenset[str] = frozenset()
        self._reload_lock = threading.RLock()
        self.reload()

    @classmethod
    def get(cls) -> TaggerRegistry:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_for_test(cls) -> None:
        """Drop the singleton so the next get() builds a fresh one."""
        with cls._lock:
            cls._instance = None

    def resolve(self, model_id: str) -> TaggerProfile:
        try:
            return self._profiles[model_id]
        except KeyError as exc:
            raise LookupError(
                f"unknown profile id: {model_id!r}. "
                f"Known: {sorted(self._profiles)}"
            ) from exc

    def list_profiles(self) -> list[TaggerProfile]:
        return list(self._profiles.values())

    def list_profiles_with_metadata(self) -> list[tuple[TaggerProfile, dict]]:
        """Return profiles paired with API-facing metadata.

        Return origin metadata while preserving the existing tuple shape.
        """
        origin_map = getattr(self, "_origin_map", {})
        builtin_ids = getattr(self, "_builtin_ids", frozenset())
        return [
            (
                p,
                {
                    "origin": origin_map.get(p.id, "builtin"),
                    "overrides_builtin": (
                        p.id in builtin_ids
                        and origin_map.get(p.id, "builtin") == "user"
                    ),
                },
            )
            for p in self._profiles.values()
        ]

    def profile_origin(self, profile_id: str) -> str | None:
        """Return 'builtin' | 'user' | None.

        Return the profile origin from the current registry overlay.
        """
        return getattr(self, "_origin_map", {}).get(profile_id)

    def get_builtin_ids(self) -> frozenset[str]:
        """Return raw builtin ids before user overlays are applied."""
        return getattr(self, "_builtin_ids", frozenset())

    def find_by_model_id(self, model_id: str) -> TaggerProfile | None:
        """Return the first profile whose model_id matches, or None."""
        for profile in self._profiles.values():
            if profile.model_id == model_id:
                return profile
        return None

    def find_all_by_model_id(self, model_id: str) -> list[TaggerProfile]:
        """Return every profile whose model_id matches (Phase 4: hf_subdir variants)."""
        return [p for p in self._profiles.values() if p.model_id == model_id]

    def resolve_any(self, key: str) -> TaggerProfile | None:
        """Resolve by profile.id first, then by profile.model_id (HF repo).

        Lets callers (routes, retag jobs, engine factory) accept either the
        canonical short id (e.g. ``wd_swinv2_v3``) or the HuggingFace repo
        path (e.g. ``SmilingWolf/wd-swinv2-tagger-v3``) without forcing one
        form on the client.
        """
        if key in self._profiles:
            return self._profiles[key]
        return self.find_by_model_id(key)

    def invalidate(self, model_id: str) -> None:
        """Re-read the JSON for one profile.

        EngineCache eviction hook will be added in Phase 1b.
        """
        with self._reload_lock:
            json_path = self._find_json_for_id(model_id)
            if json_path is None:
                logger.warning("invalidate: no JSON found for %s", model_id)
                return
            user_dir = _user_profiles_dir()
            if user_dir is not None and json_path.parent.resolve() == user_dir.resolve():
                self.reload()
                return
            try:
                profile = self._load_one(json_path, builtin=True)
                self._profiles[profile.id] = profile
                self._origin_map[profile.id] = "builtin"
                logger.info("Profile reloaded: %s", profile.id)
            except Exception as exc:
                logger.warning("invalidate failed for %s: %s", model_id, exc)

    def reload(self) -> None:
        """Rescan all profile directories and rebuild the registry."""
        with self._reload_lock:
            builtin_map: dict[str, TaggerProfile] = {}
            for json_path in sorted(_BUILTIN_PROFILES_DIR.glob("*.json")):
                try:
                    profile = self._load_one(json_path, builtin=True)
                    builtin_map[profile.id] = profile
                except Exception as exc:
                    logger.warning(
                        "Skipping invalid profile %s: %s",
                        json_path.name, exc,
                    )
            self._builtin_ids = frozenset(builtin_map)

            user_map: dict[str, TaggerProfile] = {}
            user_dir = _user_profiles_dir()
            if user_dir is not None:
                for json_path in sorted(user_dir.glob("*.json")):
                    try:
                        profile = self._load_one(json_path, builtin=False)
                        if profile.adapter_family not in _USER_ALLOWED_FAMILIES:
                            raise ValueError(
                                f"adapter_family {profile.adapter_family!r} not allowed"
                            )
                        if profile.backend not in _USER_ALLOWED_BACKENDS:
                            raise ValueError(f"backend {profile.backend!r} not allowed")
                        user_map[profile.id] = profile
                    except Exception as exc:
                        logger.warning(
                            "Skipping invalid user profile %s: %s",
                            json_path.name,
                            exc,
                        )

            merged = {**builtin_map, **user_map}
            self._profiles = merged
            self._origin_map = {
                profile_id: "user" if profile_id in user_map else "builtin"
                for profile_id in merged
            }
            logger.info(
                "Loaded %d builtin profiles and %d user profiles",
                len(builtin_map),
                len(user_map),
            )

    def _find_json_for_id(self, model_id: str) -> Path | None:
        # Guard against path traversal: ensure the resolved candidate path
        # stays inside _BUILTIN_PROFILES_DIR. Catches "../" / absolute path
        # / drive letter style inputs even before .exists() runs.
        # Spec § 5.7.3.
        builtin_root = _BUILTIN_PROFILES_DIR.resolve()
        candidate = (builtin_root / f"{model_id}.json").resolve()
        if not candidate.is_relative_to(builtin_root):
            logger.warning(
                "Path traversal attempt rejected for model_id=%r", model_id,
            )
            return None
        if candidate.exists():
            return candidate
        user_dir = _user_profiles_dir()
        if user_dir is not None:
            user_root = user_dir.resolve()
            candidate = (user_root / f"{model_id}.json").resolve()
            if not candidate.is_relative_to(user_root):
                logger.warning(
                    "Path traversal attempt rejected for model_id=%r", model_id,
                )
                return None
            if candidate.exists():
                return candidate
        return None

    def _load_one(self, json_path: Path, *, builtin: bool) -> TaggerProfile:
        with open(json_path, "rb") as fh:
            raw = fh.read(_PROFILE_JSON_MAX_BYTES + 1)
        if len(raw) > _PROFILE_JSON_MAX_BYTES:
            raise ValueError(
                f"profile JSON exceeds {_PROFILE_JSON_MAX_BYTES} bytes: "
                f"{json_path.name}"
            )
        text = raw.decode("utf-8-sig")  # tolerate UTF-8 BOM
        try:
            data = json.loads(text, object_pairs_hook=_duplicate_key_hook)
        except JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {json_path.name}: {exc}") from exc
        # Force builtin flag based on directory of origin
        data["builtin"] = builtin
        origin = "builtin" if builtin else "user"
        return TaggerProfile.from_dict(data, origin=origin)


def _user_profiles_dir() -> Path | None:
    path = get_profiles_dir() / "wd_tagger"
    if not path.exists():
        return None
    if not path.is_dir():
        logger.warning("User WD-Tagger profiles path is not a directory: %s", path)
        return None
    return path
