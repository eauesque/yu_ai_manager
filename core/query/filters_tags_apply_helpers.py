import logging
from typing import Any

from core.prompt import normalize_tag_for_search

from .filters_tags_path import (
    path_search_condition,
    path_search_has_match,
    path_search_match_estimate,
    path_search_params,
)
from .filters_tags_resolve import (
    choose_tag_exists_sql,
    estimate_tag_match_count,
    resolve_tag_ids,
    tag_candidate_set_sql,
    tag_not_exists_by_id,
)

logger = logging.getLogger(__name__)


def _apply_regex_tag_filter(where_parts: list[str], params: list[Any], tag_query: str, case_sensitive: bool) -> None:
    stripped = tag_query.strip()
    try:
        where_parts.append(
            "EXISTS(SELECT 1 FROM templates tp WHERE tp.file_id=f.id AND "
            "(tp.raw_prompt REGEXP ? OR tp.raw_negative REGEXP ?))"
        )
        regex = stripped if case_sensitive else f"(?i){stripped}"
        params.extend([regex, regex])
    except Exception:
        where_parts.append(
            "EXISTS(SELECT 1 FROM templates tp WHERE tp.file_id=f.id AND "
            "(tp.raw_prompt LIKE ? OR tp.raw_negative LIKE ?))"
        )
        params.extend([f"%{stripped}%", f"%{stripped}%"])


def _apply_excluded_tag(where_parts: list[str], params: list[Any], tag_val: str, case_sensitive: bool, con) -> None:
    if case_sensitive:
        tag_ids = resolve_tag_ids(con, tag_val, case_sensitive=True)
        if tag_ids is not None:
            if tag_ids:
                where_parts.append(tag_not_exists_by_id(tag_ids))
                params.extend(tag_ids)
            return
        where_parts.append(
            "NOT EXISTS(SELECT 1 FROM file_tags ft JOIN tags t ON t.id=ft.tag_id "
            "WHERE ft.file_id=f.id AND t.tag=?)"
        )
        params.append(tag_val)
        return

    variants = normalize_tag_for_search(tag_val)
    all_ids, resolved = _collect_variant_ids(con, variants)
    if resolved:
        if all_ids:
            where_parts.append(tag_not_exists_by_id(all_ids))
            params.extend(all_ids)
        return
    variant_conditions = " AND ".join(
        "NOT EXISTS(SELECT 1 FROM file_tags ft JOIN tags t ON t.id=ft.tag_id "
        "WHERE ft.file_id=f.id AND LOWER(t.tag)=LOWER(?))"
        for _ in variants
    )
    where_parts.append("(" + variant_conditions + ")")
    params.extend(variants)


def _apply_included_tag(where_parts, params, tag, case_sensitive, also_search_path, con, *, positive_count=1, positive_index=0):
    if case_sensitive:
        tag_ids = resolve_tag_ids(con, tag, case_sensitive=True)
        if tag_ids is not None:
            if not tag_ids:
                path_hit = path_search_has_match(con, tag) if also_search_path else None
                where_parts.append(path_search_condition(tag) if also_search_path and path_hit is not False else "0=1")
                if also_search_path and path_hit is not False:
                    params.extend(path_search_params(tag))
                return
            _append_tag_or_path(
                where_parts, params, choose_tag_exists_sql(con, tag_ids), tag_ids, tag, also_search_path, con,
                prefer_candidate_set=_should_use_candidate_set(tag, tag_ids, also_search_path, con, positive_count, positive_index),
            )
            return
        tag_exists = (
            "EXISTS(SELECT 1 FROM file_tags ft JOIN tags t ON t.id=ft.tag_id "
            "WHERE ft.file_id=f.id AND t.tag=?)"
        )
        _append_tag_or_path(where_parts, params, tag_exists, [tag], tag, also_search_path, con, prefer_candidate_set=False)
        return

    variants = normalize_tag_for_search(tag)
    all_ids, resolved = _collect_variant_ids(con, variants)
    if resolved and all_ids:
        _append_tag_or_path(
            where_parts, params, choose_tag_exists_sql(con, all_ids), all_ids, tag, also_search_path, con,
            prefer_candidate_set=_should_use_candidate_set(tag, all_ids, also_search_path, con, positive_count, positive_index),
        )
        return
    if resolved and not all_ids:
        path_hit = path_search_has_match(con, tag) if also_search_path else None
        where_parts.append(path_search_condition(tag) if also_search_path and path_hit is not False else "0=1")
        if also_search_path and path_hit is not False:
            params.extend(path_search_params(tag))
        return
    _append_legacy_variant_conditions(where_parts, params, variants, tag, also_search_path, con)


def _collect_variant_ids(con, variants):
    all_ids = []
    for variant in variants:
        ids = resolve_tag_ids(con, variant, case_sensitive=False)
        if ids is None:
            return [], False
        all_ids.extend(ids)
    return all_ids, True


def _estimate_included_tag_score(tag, case_sensitive, also_search_path, con) -> int:
    estimates = []
    if also_search_path:
        path_estimate = path_search_match_estimate(con, tag)
        if path_estimate is not None:
            estimates.append(path_estimate)
    if not estimates:
        if case_sensitive:
            tag_ids = resolve_tag_ids(con, tag, case_sensitive=True)
            if tag_ids:
                tag_estimate = estimate_tag_match_count(con, tag_ids)
                if tag_estimate is not None:
                    estimates.append(tag_estimate)
        else:
            variants = normalize_tag_for_search(tag)
            all_ids, resolved = _collect_variant_ids(con, variants)
            if resolved and all_ids:
                tag_estimate = estimate_tag_match_count(con, all_ids)
                if tag_estimate is not None:
                    estimates.append(tag_estimate)
    return min(estimates) if estimates else 10**9


def _append_tag_or_path(where_parts, params, tag_exists_sql, tag_params, tag, also_search_path, con, *, prefer_candidate_set):
    from core.query.fts_like_helpers import path_fts_match_phrase
    path_hit = path_search_has_match(con, tag) if also_search_path else None
    # The path subquery uses trigram MATCH (idxNum=M0). Skip it for terms
    # too short to be indexed; otherwise we'd inject a LIKE-with-ESCAPE
    # subquery that forces a full virtual-table SCAN.
    path_eligible = (
        also_search_path
        and path_hit is not False
        and path_fts_match_phrase(tag) is not None
    )
    if path_eligible:
        path_sql = path_search_condition(tag)
        if prefer_candidate_set:
            where_parts.append(
                f"f.id IN ({tag_candidate_set_sql(tag_params)} UNION "
                f"SELECT rowid AS id FROM files_path_fts WHERE path MATCH ?)"
            )
            params.extend(tag_params)
            params.extend(path_search_params(tag))
        else:
            where_parts.append("(" + tag_exists_sql + " OR " + path_sql + ")")
            params.extend(tag_params)
            params.extend(path_search_params(tag))
    else:
        where_parts.append(tag_exists_sql)
        params.extend(tag_params)


def _append_legacy_variant_conditions(where_parts, params, variants, tag, also_search_path, con):
    conditions = [
        "EXISTS(SELECT 1 FROM file_tags ft JOIN tags t ON t.id=ft.tag_id "
        "WHERE ft.file_id=f.id AND LOWER(t.tag)=LOWER(?))"
        for _ in variants
    ]
    params.extend(variants)
    path_hit = path_search_has_match(con, tag) if also_search_path else None
    if also_search_path and path_hit is not False:
        conditions.append(path_search_condition(tag))
        params.extend(path_search_params(tag))
    where_parts.append("(" + " OR ".join(conditions) + ")")


def _resolve_wd_model_for_filter(con, wd_model: str | None):
    """Resolve the wd_model selector to a model scope for WD tag matching.

    Returns:
        ("all", None) - match tags from any WD model (no model_id constraint)
        ("id", int)   - match tags scoped to this WD model's db id
        (None, None)  - WD tag matching not applicable (no active model / unresolvable)
    """
    from core.services_core.wd_dict_resolver import resolve_model_id_readonly

    if wd_model and wd_model.lower() == "all":
        return ("all", None)
    if wd_model:
        model_db_id = resolve_model_id_readonly(con, wd_model)
        return ("id", model_db_id)

    from core.services_core.wd_active_model import (
        try_get_active_wd_model_id_for_legacy_schema,
    )

    active_model = try_get_active_wd_model_id_for_legacy_schema()
    if not active_model:
        return (None, None)
    return ("id", resolve_model_id_readonly(con, active_model))


def apply_wd_model_filter(where_parts, params, wd_model: str | None, con=None) -> None:
    """Restrict to files that have at least one WD-tagger tag from ``wd_model``.

    Standalone AND condition, independent of tag_query — lets the WD Model
    filter narrow results even when the user hasn't also typed a tag search
    (previously it only scoped WD-tag matching *within* a tag_query, so
    selecting a model alone had no effect). No-op when wd_model is empty
    (no explicit selection: preserves prior behavior).
    """
    if not wd_model or con is None:
        return
    if wd_model.lower() == "all":
        where_parts.append("EXISTS(SELECT 1 FROM file_wd_tags fwt WHERE fwt.file_id=f.id)")
        return
    try:
        from core.services_core.wd_dict_resolver import resolve_model_id_readonly

        model_db_id = resolve_model_id_readonly(con, wd_model)
    except Exception:
        logger.warning("WD model filter resolution failed", exc_info=True)
        model_db_id = None
    if model_db_id is None:
        where_parts.append("0=1")
        return
    where_parts.append("EXISTS(SELECT 1 FROM file_wd_tags fwt WHERE fwt.file_id=f.id AND fwt.model_id=?)")
    params.append(model_db_id)


def _wd_tag_exists_condition(tag: str, con, wd_model: str | None = None) -> tuple[str, list] | None:
    """Return (sql, params) for a WD-tagger tag EXISTS check, or None if not applicable.

    Scoped to ``wd_model`` when given ("all" matches any model), otherwise
    falls back to the active WD model. Returns None when there is no active
    WD model (and no override) or when con is unavailable.
    """
    if con is None:
        return None
    try:
        from core.services_core.wd_dict_resolver import resolve_tag_ids_readonly

        mode, model_db_id = _resolve_wd_model_for_filter(con, wd_model)
        if mode is None:
            return None
        if mode == "id" and model_db_id is None:
            return ("0=1", [])
        variants = normalize_tag_for_search(tag)
        tag_ids = resolve_tag_ids_readonly(con, variants)
        if not tag_ids:
            return ("0=1", [])
        placeholders = ",".join("?" for _ in tag_ids)
        if mode == "all":
            sql = (
                "EXISTS(SELECT 1 FROM file_wd_tags fwt"
                f" WHERE fwt.file_id=f.id AND fwt.tag_id IN ({placeholders}))"
            )
            return (sql, [*tag_ids])
        sql = (
            "EXISTS(SELECT 1 FROM file_wd_tags fwt"
            " WHERE fwt.file_id=f.id AND fwt.model_id=? "
            f"AND fwt.tag_id IN ({placeholders}))"
        )
        return (sql, [model_db_id, *tag_ids])
    except Exception:
        logger.warning("WD tag dictionary EXISTS resolution failed", exc_info=True)
        return None


def _wd_tag_candidate_sql(tag: str, con, wd_model: str | None = None) -> tuple[str, list] | None:
    """Return (SELECT file_id SQL, params) for UNION-based OR tag search, or None."""
    if con is None:
        return None
    try:
        from core.services_core.wd_dict_resolver import resolve_tag_ids_readonly

        mode, model_db_id = _resolve_wd_model_for_filter(con, wd_model)
        if mode is None:
            return None
        if mode == "id" and model_db_id is None:
            return ("SELECT file_id AS id FROM file_wd_tags WHERE 0=1", [])
        variants = normalize_tag_for_search(tag)
        tag_ids = resolve_tag_ids_readonly(con, variants)
        if not tag_ids:
            return ("SELECT file_id AS id FROM file_wd_tags WHERE 0=1", [])
        placeholders = ",".join("?" for _ in tag_ids)
        if mode == "all":
            sql = f"SELECT file_id AS id FROM file_wd_tags WHERE tag_id IN ({placeholders})"
            return (sql, [*tag_ids])
        sql = (
            "SELECT file_id AS id FROM file_wd_tags "
            f"WHERE model_id=? AND tag_id IN ({placeholders})"
        )
        return (sql, [model_db_id, *tag_ids])
    except Exception:
        logger.warning("WD tag dictionary candidate resolution failed", exc_info=True)
        return None


def _should_use_candidate_set(tag, tag_ids, also_search_path, con, positive_count, positive_index) -> bool:
    if not tag_ids:
        return False
    # Only the first positive tag may drive a materialised candidate set;
    # subsequent tags stay as plain semi-joins / EXISTS clauses.
    if positive_index != 0:
        return False
    # Path search is the strongest reason to materialise: the OR-of-IN
    # form (`f.id IN (tag) OR f.id IN (path_fts)`) frequently degenerates
    # into a 280K-row outer scan with two correlated probes, which is the
    # 3〜4s tag-search hot path observed in production. Forcing the union
    # into a single IN gives the planner a small driving set instead.
    if also_search_path and path_search_has_match(con, tag) is not False:
        estimate = estimate_tag_match_count(con, tag_ids)
        return estimate is None or estimate < 100000
    # Without path search there is no OR to flatten, so the simple
    # semi-join form is fine for single-tag queries.
    if positive_count <= 1:
        return False
    if len(tag_ids) > 32:
        return True
    estimate = estimate_tag_match_count(con, tag_ids)
    return estimate is not None and estimate < 2000
