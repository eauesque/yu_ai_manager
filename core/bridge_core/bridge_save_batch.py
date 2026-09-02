"""Shared batch-save handler for bridge extensions.

Used by Sweep "deferred save" mode where the client accumulates generated
images in localStorage during the run and posts the whole batch at the end
(or on cancel/recovery). The handler decodes each base64 image and saves it
using the same naming + auto-import logic as the per-generation auto-save
path.

Usage from a bridge route::

    from core.bridge_core.bridge_save_batch import handle_save_batch
    return await handle_save_batch(
        request,
        ext_name="builtin-nai-bridge",
        save_fn=save_images,  # bridge_core.bridge_save.save_images or wrapper
    )

The request body shape is::

    {
        "images": [
            {
                "base64": "...",
                "seed": 1234,
                "image_format": "png",
                "sweep_meta": { ... }   # optional, embedded into XMP if present
            },
            ...
        ]
    }

Returns ``api_success({"saved": [...paths...], "failed": [...errors...]})``
or ``api_error(...)`` on validation failure / missing save_folder.
"""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable
from typing import Any

from core.bridge_core.bridge_import import (
    import_saved_files_async,
    import_saved_files_sync,
)
from core.bridge_core.sweep_db import upsert_sweep_from_meta
from core.bridge_core.sweep_xmp import write_sweep_xmp_to_paths
from core.extensions_core.extensions_admin import get_extension_config_value
from core.infra_core.api_errors import api_error, api_success
from core.infra_core.api_request import require_json_dict
from core.infra_core.blocking_tasks import run_blocking_sync

MAX_BATCH_IMAGES = 500
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_BATCH_BYTES = 96 * 1024 * 1024
_IN_CHUNK_SIZE = 500


def _chunks(items: list, size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def _mark_sweep_paths(con, paths: list[str]) -> None:
    for chunk in _chunks(list(dict.fromkeys(paths))):
        placeholders = ",".join("?" for _ in chunk)
        con.execute(
            f"UPDATE files SET has_sweep=1 WHERE path IN ({placeholders})",
            chunk,
        )


def _mark_sweep_ids(con, ids: list[int]) -> None:
    for chunk in _chunks(list(dict.fromkeys(ids))):
        placeholders = ",".join("?" for _ in chunk)
        con.execute(
            f"UPDATE files SET has_sweep=1 WHERE id IN ({placeholders})",
            chunk,
        )


async def handle_save_batch(
    request_obj,
    *,
    ext_name: str,
    save_fn: Callable[..., list[str]],
    return_file_ids: bool = True,
) -> tuple:
    """Decode and save a batch of base64 images using *save_fn*.

    *save_fn* signature must match ``bridge_save.save_images``:
    ``(images: list[bytes], seed: int, folder: str, image_format: str, naming: str) -> list[str]``.

    Sweep contract: when ``return_file_ids`` is True (default) and ``auto_import``
    is enabled, this function blocks until indexing completes and includes
    ``saved_items: [{path, file_id}, ...]`` in the response. The client uses the
    file_id to deep-link into ``/sweep/<sweep_id>``. When ``return_file_ids`` is
    False, indexing is fire-and-forget (legacy behavior).
    """
    data, err = await require_json_dict(request_obj)
    if err:
        return api_error(err[0]["error"], err[1])

    images_in = data.get("images")
    if not isinstance(images_in, list) or not images_in:
        return api_error("images list is required", 400)
    if len(images_in) > MAX_BATCH_IMAGES:
        return api_error(
            f"images list exceeds the limit of {MAX_BATCH_IMAGES}",
            413,
            code="batch_too_large",
        )

    save_folder = get_extension_config_value(ext_name, "save_folder", "")
    if not save_folder:
        return api_error(
            "save_folder is not configured", 400,
            hint="Set the save folder in this bridge's settings",
        )

    naming = get_extension_config_value(ext_name, "save_naming", "daily_folder")
    auto_import = get_extension_config_value(ext_name, "auto_import", True)

    saved_all: list[str] = []
    sweep_paths: list[str] = []
    sweep_path_meta: dict[str, Any] = {}
    failed: list[dict[str, Any]] = []
    decoded_total = 0
    for idx, item in enumerate(images_in):
        if not isinstance(item, dict):
            failed.append({"index": idx, "error": "not an object"})
            continue
        b64 = item.get("base64") or ""
        try:
            img_bytes = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            failed.append({"index": idx, "error": f"decode: {exc}"})
            continue
        decoded_total += len(img_bytes)
        if len(img_bytes) > MAX_IMAGE_BYTES:
            return api_error(
                f"image at index {idx} exceeds the {MAX_IMAGE_BYTES} byte limit",
                413,
                code="image_too_large",
            )
        if decoded_total > MAX_BATCH_BYTES:
            return api_error(
                f"decoded image batch exceeds the {MAX_BATCH_BYTES} byte limit",
                413,
                code="batch_bytes_too_large",
            )
        try:
            seed = int(item.get("seed", -1))
        except (TypeError, ValueError):
            seed = -1
        fmt = item.get("image_format") or "png"
        if fmt not in ("png", "webp", "jpg"):
            fmt = "png"
        try:
            paths = await run_blocking_sync(
                save_fn, [img_bytes], seed, save_folder,
                image_format=fmt, naming=naming,
            )
        except Exception as exc:  # noqa: BLE001
            failed.append({"index": idx, "error": f"save: {exc}"})
            continue
        saved_all.extend(paths)

        sweep_meta = item.get("sweep_meta")
        if paths and sweep_meta:
            await run_blocking_sync(write_sweep_xmp_to_paths, paths, sweep_meta)
            sweep_paths.extend(paths)
            for p in paths:
                sweep_path_meta[p] = sweep_meta

    saved_items: list[dict[str, Any]] | None = None
    sweep_file_ids: list[int] = []
    if saved_all and auto_import:
        if return_file_ids:
            mapping = import_saved_files_sync(saved_all)
            saved_items = [
                {"path": p, "file_id": mapping.get(p)} for p in saved_all
            ]
            for p in sweep_paths:
                fid = mapping.get(p)
                if fid is not None:
                    sweep_file_ids.append(int(fid))
                # Mirror the sweep run into the sweeps / sweep_axes tables.
                meta = sweep_path_meta.get(p)
                if meta is not None:
                    upsert_sweep_from_meta(meta, int(fid) if fid is not None else None)
        else:
            import_saved_files_async(saved_all)
            # Mirror sweep header into DB even on the async path. file_id
            # is unknown here so it stays NULL; the row still lets the
            # /sweep history list show the run header.
            for _p, _meta in sweep_path_meta.items():
                upsert_sweep_from_meta(_meta, None)
            if sweep_paths:
                # Resolve sweep paths -> ids in the writer thread (paths were
                # just imported, so the mapping lookup runs after that write).
                from core.services_core.db_write import submit_db_write_no_wait

                def _flag_sweep(paths: list[str]) -> None:
                    from core.services_core.db_state import get_raw_db
                    try:
                        con = get_raw_db()
                    except Exception:
                        return
                    _mark_sweep_paths(con, paths)
                    con.commit()

                submit_db_write_no_wait(_flag_sweep, list(sweep_paths))

    if sweep_file_ids:
        from core.services_core.db_write import submit_db_write_no_wait

        def _flag_ids(ids: list[int]) -> None:
            from core.services_core.db_state import get_raw_db
            try:
                con = get_raw_db()
            except Exception:
                return
            _mark_sweep_ids(con, ids)
            con.commit()

        submit_db_write_no_wait(_flag_ids, list(sweep_file_ids))

    payload: dict[str, Any] = {"saved": saved_all, "failed": failed}
    if saved_items is not None:
        payload["saved_items"] = saved_items
    return api_success(payload)


__all__ = ["handle_save_batch"]
