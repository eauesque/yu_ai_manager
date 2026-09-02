"""Parser for NovelAI's .naiv4vibe file format.

Format (reverse-engineered from official exports, see
tmp/research/naiv4vibe_format.md):

  Plain UTF-8 JSON with this top-level structure:

  {
    "identifier": "novelai-vibe-transfer",   // validation string
    "version": 1,
    "type": "image",
    "image": "<base64 JPEG or PNG>",         // original source image
    "id": "<hex>",
    "encodings": {
      "<model_short>": {
        "<hash_key>": {
          "encoding": "<base64 vibe blob>",  // what NAI /ai/generate-image expects
          "params": {
            "information_extracted": <float>
          }
        }
      }
    },
    "importInfo": {
      "model": "nai-diffusion-4-5-full",
      "information_extracted": <float>,
      "strength": <float>
    },
    "name": "<stem>",
    "thumbnail": "<base64>",
    "createdAt": <unix_ms>
  }

  `encodings` may contain multiple `<hash_key>` entries under the same
  `<model_short>` key when the same image was encoded at different
  `information_extracted` values (each info value needs its own encoding).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_IDENTIFIER = "novelai-vibe-transfer"

# Map model short names found in .naiv4vibe files to canonical model IDs.
# Extend as NAI releases new models.
_SHORT_TO_MODEL: dict[str, str] = {
    "v4-5full":    "nai-diffusion-4-5-full",
    "v4-5curated": "nai-diffusion-4-5-curated",
    "v4full":      "nai-diffusion-4-full",
    "v4curated":   "nai-diffusion-4-curated-preview",
}


_BUNDLE_IDENTIFIER = "novelai-vibe-transfer-bundle"


class NaiVibeFormatError(Exception):
    """Raised when input bytes are not a valid .naiv4vibe/.naiv4vibeBundle file."""


@dataclass
class VibeEntry:
    """One encoded vibe for a specific information_extracted value."""
    information_extracted: float
    blob: bytes  # raw binary; base64-encode before placing in reference_image_multiple


@dataclass
class ParsedVibe:
    """Result of parsing a single .naiv4vibe file."""
    model: str                    # canonical model name, e.g. "nai-diffusion-4-5-full"
    source_image_bytes: bytes     # original image (JPEG or PNG)
    thumbnail_bytes: bytes | None
    entries: list[VibeEntry]      # sorted by information_extracted ascending
    import_strength: float        # importInfo.strength — default strength to use
    import_info: float            # importInfo.information_extracted — last used info


def parse_naiv4vibe(data: bytes) -> ParsedVibe:
    """Parse .naiv4vibe file bytes into a :class:`ParsedVibe`.

    Raises :class:`NaiVibeFormatError` on any validation failure so callers
    can return HTTP 400 without crashing.
    """
    if not data:
        raise NaiVibeFormatError("empty input")

    # Decode JSON
    try:
        obj = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NaiVibeFormatError(f"not valid JSON: {exc}") from exc

    if not isinstance(obj, dict):
        raise NaiVibeFormatError("expected JSON object at top level")

    # Validate identifier
    ident = obj.get("identifier")
    if ident != _IDENTIFIER:
        raise NaiVibeFormatError(
            f"identifier mismatch: expected {_IDENTIFIER!r}, got {ident!r}"
        )

    # Source image
    raw_image_b64 = obj.get("image")
    if not raw_image_b64 or not isinstance(raw_image_b64, str):
        raise NaiVibeFormatError("missing 'image' field")
    try:
        source_image_bytes = base64.b64decode(raw_image_b64)
    except Exception as exc:
        raise NaiVibeFormatError(f"'image' is not valid base64: {exc}") from exc

    # Thumbnail (optional)
    thumbnail_bytes: bytes | None = None
    raw_thumb = obj.get("thumbnail")
    if raw_thumb and isinstance(raw_thumb, str):
        import contextlib
        with contextlib.suppress(Exception):
            thumbnail_bytes = base64.b64decode(raw_thumb)

    # importInfo — used to derive the canonical model name and default params
    import_info_obj = obj.get("importInfo") or {}
    full_model = import_info_obj.get("model", "")
    try:
        import_info = float(import_info_obj.get("information_extracted", 1.0))
    except (TypeError, ValueError):
        import_info = 1.0
    try:
        import_strength = float(import_info_obj.get("strength", 0.6))
    except (TypeError, ValueError):
        import_strength = 0.6

    # Encodings — each hash_key entry is one (info_extracted, blob) pair
    encodings = obj.get("encodings")
    if not isinstance(encodings, dict) or not encodings:
        raise NaiVibeFormatError("missing or empty 'encodings' field")

    entries: list[VibeEntry] = []
    resolved_model = full_model  # fall back to importInfo.model

    _MAX_MODELS_PER_VIBE = 10
    _MAX_ENTRIES_PER_MODEL = 50
    model_count = 0
    for short_name, enc_map in encodings.items():
        if not isinstance(enc_map, dict):
            continue
        model_count += 1
        if model_count > _MAX_MODELS_PER_VIBE:
            logger.warning("nai_vibe_file: too many model keys in encodings, truncating at %d", _MAX_MODELS_PER_VIBE)
            break
        # Resolve short name to canonical model if possible
        if short_name in _SHORT_TO_MODEL:
            resolved_model = _SHORT_TO_MODEL[short_name]
        elif full_model:
            resolved_model = full_model

        entry_count = 0
        for hash_key, enc_entry in enc_map.items():
            if entry_count >= _MAX_ENTRIES_PER_MODEL:
                logger.warning(
                    "nai_vibe_file: too many entries under model %s, truncating at %d",
                    short_name, _MAX_ENTRIES_PER_MODEL,
                )
                break
            entry_count += 1
            if not isinstance(enc_entry, dict):
                continue
            enc_b64 = enc_entry.get("encoding")
            params = enc_entry.get("params") or {}
            if not enc_b64 or not isinstance(enc_b64, str):
                logger.warning("nai_vibe_file: skipping entry with no encoding (%s)", hash_key)
                continue
            try:
                blob = base64.b64decode(enc_b64)
            except Exception as exc:
                logger.warning("nai_vibe_file: bad base64 in entry %s: %s", hash_key, exc)
                continue
            try:
                # Round to 2 decimal places to match the cache key precision
                # (:.2f) and the UI slider step (0.05). Avoids a mismatch
                # where a file's 0.547 gets keyed as "0.55" but the blob was
                # encoded at 0.547.
                info = round(float(params.get("information_extracted", import_info)), 2)
            except (TypeError, ValueError):
                info = round(import_info, 2)
            entries.append(VibeEntry(information_extracted=info, blob=blob))

    if not entries:
        raise NaiVibeFormatError("no valid encoding entries found")

    # Sort by information_extracted for deterministic ordering
    entries.sort(key=lambda e: e.information_extracted)

    return ParsedVibe(
        model=resolved_model or "nai-diffusion-4-5-full",
        source_image_bytes=source_image_bytes,
        thumbnail_bytes=thumbnail_bytes,
        entries=entries,
        import_strength=import_strength,
        import_info=import_info,
    )


# ---------------------------------------------------------------------------
# Bundle support
# ---------------------------------------------------------------------------

@dataclass
class ParsedVibeBundle:
    """Result of parsing a .naiv4vibeBundle (or a wrapped single vibe)."""
    vibes: list[ParsedVibe]


def parse_naiv4vibebundle(data: bytes) -> ParsedVibeBundle:
    """Parse a .naiv4vibeBundle file.

    The bundle format is a JSON wrapper:
    {
      "identifier": "novelai-vibe-transfer-bundle",
      "version": 1,
      "vibes": [ <.naiv4vibe object>, ... ]
    }

    Each element of ``vibes`` has the same structure as a single
    ``.naiv4vibe`` file and is parsed using :func:`parse_naiv4vibe`.
    """
    if not data:
        raise NaiVibeFormatError("empty input")

    try:
        obj = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NaiVibeFormatError(f"not valid JSON: {exc}") from exc

    if not isinstance(obj, dict):
        raise NaiVibeFormatError("expected JSON object at top level")

    ident = obj.get("identifier")
    if ident != _BUNDLE_IDENTIFIER:
        raise NaiVibeFormatError(
            f"identifier mismatch: expected {_BUNDLE_IDENTIFIER!r}, got {ident!r}"
        )

    raw_vibes = obj.get("vibes")
    if not isinstance(raw_vibes, list) or not raw_vibes:
        raise NaiVibeFormatError("missing or empty 'vibes' array")

    # Cap to prevent a malicious/malformed bundle from allocating unbounded
    # memory during base64 decode of per-vibe encodings.
    _MAX_VIBES_PER_BUNDLE = 20
    if len(raw_vibes) > _MAX_VIBES_PER_BUNDLE:
        raise NaiVibeFormatError(
            f"bundle contains {len(raw_vibes)} vibes; maximum is {_MAX_VIBES_PER_BUNDLE}"
        )

    parsed_vibes: list[ParsedVibe] = []
    for i, vibe_obj in enumerate(raw_vibes):
        if not isinstance(vibe_obj, dict):
            logger.warning("nai_vibe_file: bundle entry %d is not a dict, skipping", i)
            continue
        try:
            # Re-serialise the sub-object and delegate to the single-vibe parser
            parsed_vibes.append(parse_naiv4vibe(json.dumps(vibe_obj).encode()))
        except NaiVibeFormatError as exc:
            logger.warning("nai_vibe_file: bundle entry %d invalid: %s", i, exc)

    if not parsed_vibes:
        raise NaiVibeFormatError("bundle contained no valid vibe entries")

    return ParsedVibeBundle(vibes=parsed_vibes)


# ---------------------------------------------------------------------------
# Export (download) support
# ---------------------------------------------------------------------------

_MODEL_TO_SHORT: dict[str, str] = {v: k for k, v in _SHORT_TO_MODEL.items()}


def _naiv4vibe_obj(
    image_bytes: bytes,
    model: str,
    encoded_blob: bytes,
    information_extracted: float,
    strength: float,
    name: str,
) -> dict:
    short_model = _MODEL_TO_SHORT.get(model, model)
    hash_key = hashlib.sha256(encoded_blob).hexdigest()[:16]
    return {
        "identifier": _IDENTIFIER,
        "version": 1,
        "type": "image",
        "image": base64.b64encode(image_bytes).decode("ascii"),
        "id": uuid.uuid4().hex,
        "encodings": {
            short_model: {
                hash_key: {
                    "encoding": base64.b64encode(encoded_blob).decode("ascii"),
                    "params": {"information_extracted": information_extracted},
                },
            },
        },
        "importInfo": {
            "model": model,
            "information_extracted": information_extracted,
            "strength": strength,
        },
        "name": name,
        "createdAt": int(time.time() * 1000),
    }


def build_naiv4vibe(
    image_bytes: bytes,
    model: str,
    encoded_blob: bytes,
    information_extracted: float,
    strength: float,
    name: str = "vibe",
) -> bytes:
    """Serialise an already-encoded vibe back into .naiv4vibe file bytes.

    Mirrors the format documented at the top of this module so the
    result can be re-uploaded here (or into the official NAI web UI)
    later without paying for /ai/encode-vibe again.
    """
    obj = _naiv4vibe_obj(
        image_bytes, model, encoded_blob, information_extracted, strength, name)
    return json.dumps(obj).encode("utf-8")


def build_naiv4vibebundle(
    items: list[tuple[bytes, str, bytes, float, float]],
) -> bytes:
    """Serialise 2+ already-encoded vibes into .naiv4vibeBundle file bytes.

    Each item is (image_bytes, model, encoded_blob, information_extracted,
    strength) — the same fields :func:`build_naiv4vibe` takes for one vibe.
    """
    vibes = [
        _naiv4vibe_obj(image_bytes, model, blob, info, strength, f"vibe-{i + 1}")
        for i, (image_bytes, model, blob, info, strength) in enumerate(items)
    ]
    obj = {
        "identifier": _BUNDLE_IDENTIFIER,
        "version": 1,
        "vibes": vibes,
    }
    return json.dumps(obj).encode("utf-8")


def parse_vibe_any(data: bytes) -> ParsedVibeBundle:
    """Auto-detect file type and parse.

    Accepts both ``.naiv4vibe`` (single) and ``.naiv4vibeBundle`` (multi).
    A single ``.naiv4vibe`` is returned as a one-element
    :class:`ParsedVibeBundle` so callers always get the same type.
    """
    if not data:
        raise NaiVibeFormatError("empty input")

    try:
        obj = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise NaiVibeFormatError(f"not valid JSON: {exc}") from exc

    if not isinstance(obj, dict):
        raise NaiVibeFormatError("expected JSON object at top level")

    ident = obj.get("identifier")
    if ident == _BUNDLE_IDENTIFIER:
        return parse_naiv4vibebundle(data)
    if ident == _IDENTIFIER:
        return ParsedVibeBundle(vibes=[parse_naiv4vibe(data)])
    raise NaiVibeFormatError(
        f"unrecognised identifier: {ident!r}. "
        f"Expected {_IDENTIFIER!r} or {_BUNDLE_IDENTIFIER!r}."
    )
