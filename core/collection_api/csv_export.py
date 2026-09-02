"""CSV export builder for a single collection.

Pure sync — call from ``run_in_heavy_io`` so the per-row UTF-8 encoding and
StringIO build do not occupy DB executor slots.
"""

from __future__ import annotations

import csv
import datetime
import io
import os
from importlib import import_module

from core.services_core.db_api import get_readonly_db

_fav_mod = import_module("extensions.builtin_favorites_manager.core_impl")
get_collection_name = _fav_mod.get_collection_name


def build_collection_csv(collection_id: int) -> tuple[str | None, bytes | None]:
    """Return (collection_name, csv_bytes) or (None, None) if collection missing."""
    _exp_hooks = import_module("extensions.builtin_export.core_impl.export_hooks")
    apply_export_hooks = _exp_hooks.apply_export_hooks

    cname = get_collection_name(collection_id)
    if cname is None:
        return None, None

    con = get_readonly_db()
    rows = con.execute(
        "SELECT f.id, f.path, f.meta_source, f.mtime, "
        "t.raw_prompt, t.raw_negative "
        "FROM favorites fav "
        "JOIN files f ON f.id = fav.file_id AND f.is_deleted = 0 "
        "LEFT JOIN templates t ON t.file_id = f.id "
        "WHERE fav.collection_id = ? "
        "ORDER BY fav.added_at DESC",
        (collection_id,),
    )

    buf = io.StringIO()
    buf.write("﻿")  # UTF-8 BOM for Excel compatibility
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        ["id", "filename", "folder", "path", "meta_source", "mtime", "positive", "negative"]
    )

    for r in rows:
        fid, path, meta_source, mtime, positive, negative = r
        fname = os.path.basename(path) if path else ""
        folder = os.path.dirname(path) if path else ""
        mtime_iso = ""
        if mtime:
            # Same output as the old `utcfromtimestamp` (measured across the
            # epoch, a fractional stamp and year 9999), but aware -- the naive
            # form is deprecated since 3.12 and already warns on this project's
            # 3.13 floor.
            mtime_iso = datetime.datetime.fromtimestamp(
                mtime, tz=datetime.UTC
            ).strftime("%Y-%m-%dT%H:%M:%SZ")
        record = {
            "id": fid,
            "filename": fname,
            "folder": folder,
            "path": path,
            "meta_source": meta_source or "",
            "mtime": mtime_iso,
            "positive": positive or "",
            "negative": negative or "",
        }
        record = apply_export_hooks(record)
        writer.writerow(
            [
                record["id"],
                record["filename"],
                record["folder"],
                record["path"],
                record["meta_source"],
                record["mtime"],
                record["positive"],
                record["negative"],
            ]
        )

    return cname, buf.getvalue().encode("utf-8")


def build_collection_recipe_csv(collection_id: int) -> tuple[str | None, bytes | None]:
    """CSV with gen params columns for recipe sharing."""
    from core.recipe_api.recipe_payload import build_recipe

    cname = get_collection_name(collection_id)
    if cname is None:
        return None, None

    con = get_readonly_db()
    rows = con.execute(
        "SELECT f.id, f.path FROM favorites fav "
        "JOIN files f ON f.id = fav.file_id AND f.is_deleted = 0 "
        "WHERE fav.collection_id = ? ORDER BY fav.added_at DESC",
        (collection_id,),
    ).fetchall()

    buf = io.StringIO()
    buf.write("﻿")  # UTF-8 BOM for Excel
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(
        [
            "id",
            "filename",
            "folder",
            "bridge_id",
            "model",
            "model_hash",
            "seed",
            "steps",
            "cfg",
            "sampler",
            "width",
            "height",
            "positive",
            "negative",
        ]
    )

    for fid, fpath in rows:
        recipe = build_recipe(fid, con)
        if recipe is None:
            writer.writerow(
                [
                    fid,
                    os.path.basename(fpath or ""),
                    os.path.dirname(fpath or ""),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            )
            continue
        writer.writerow(
            [
                fid,
                os.path.basename(fpath or ""),
                os.path.dirname(fpath or ""),
                recipe.get("bridge_id", ""),
                recipe.get("model", ""),
                recipe.get("model_hash", ""),
                recipe.get("seed", ""),
                recipe.get("steps", ""),
                recipe.get("cfg", ""),
                recipe.get("sampler", ""),
                recipe.get("width", ""),
                recipe.get("height", ""),
                recipe.get("positive", ""),
                recipe.get("negative", ""),
            ]
        )

    return cname, buf.getvalue().encode("utf-8")


def build_collection_recipe_json(collection_id: int) -> tuple[str | None, list | None]:
    """Raw array of recipe dicts for MCP/LLM consumption."""
    from core.recipe_api.recipe_payload import build_recipe

    cname = get_collection_name(collection_id)
    if cname is None:
        return None, None

    con = get_readonly_db()
    rows = con.execute(
        "SELECT f.id FROM favorites fav "
        "JOIN files f ON f.id = fav.file_id AND f.is_deleted = 0 "
        "WHERE fav.collection_id = ? ORDER BY fav.added_at DESC",
        (collection_id,),
    ).fetchall()

    return cname, [r for fid, in rows if (r := build_recipe(fid, con)) is not None]
