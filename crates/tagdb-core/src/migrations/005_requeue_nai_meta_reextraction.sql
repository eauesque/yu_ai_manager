-- E2 (Rust migration 4) repaired only files.meta_source; it could not repair
-- incorrect meta tokens already materialized in file_tags, so those rows must
-- be re-extracted.
--
-- Only NovelAI images imported by Rust before E1 have incorrect tags. After E2
-- canonicalized meta_source, SQL cannot distinguish that set from correctly
-- imported Python rows, so this deliberately over-includes every canonical NAI
-- source. Re-extraction is idempotent, so correct rows remain unchanged; the
-- only cost is a slightly longer next scan.
--
-- Re-extraction replaces only file_tags rows whose source is 'meta', preserving
-- manually assigned tags. This downgrades the affected rows' parser_version to
-- the sentinel 0; it does not change CURRENT_PARSER_VERSION.
UPDATE files
SET parser_version = 0
WHERE parser_version <> 0
  AND meta_source IN (
    'novelai_v4_png',
    'novelai_v4_webp',
    'novelai_v4',
    'novelai_png',
    'novelai_webp',
    'nai_webp'
  );
