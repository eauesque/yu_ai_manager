-- Phase 1 added `use_coords` / `negative_use_coords` / `use_order` to the
-- NovelAI detail payload. Rows scanned before that carry no value for them, so
-- the viewer would read "the image did not say" for images that do say.
--
-- The read path treats a missing flag as null (unknown) rather than false, so
-- an un-migrated row still renders its markers and merely shows the
-- "unconfirmed" badge -- no false claim either way. This requeue upgrades those
-- rows to the real value on the next scan.
--
-- Re-extraction is idempotent and replaces only file_tags rows whose source is
-- 'meta', preserving manually assigned tags. It downgrades the affected rows'
-- parser_version to the sentinel 0; it does not change CURRENT_PARSER_VERSION.
--
-- Scoped to the NovelAI sources listed in `is_nai_source`
-- (crates/meta-extract/src/lib.rs) and its Python twin
-- (core/prompt/detail_parsing.py `_NAI_SOURCES`). The two internal parser
-- identifiers `nai_v4` / `nai_v3` are included because rows polluted before E1
-- still carry them.
UPDATE files
SET parser_version = 0
WHERE parser_version <> 0
  AND meta_source IN (
    'novelai_v4_png',
    'novelai_v4_webp',
    'novelai_v4',
    'novelai_png',
    'novelai_webp',
    'nai_webp',
    'nai_v4',
    'nai_v3'
  );
