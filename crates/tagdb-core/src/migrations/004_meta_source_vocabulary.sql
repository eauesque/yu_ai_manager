-- Repair pre-E1 rows where Rust stored meta-extract's internal parser identifiers.
-- This migration only repairs files.meta_source. Incorrect tokens already materialized
-- in file_tags (for example, NAI metadata tokenized with non-NAI syntax) require
-- re-extraction and cannot be repaired here.
-- comfyui is an historically valid Python-written source, and txt is a valid source
-- shared by Rust sidecar extraction and Python; both are intentionally excluded.
UPDATE files SET meta_source = CASE
  WHEN meta_source = 'nai_v4' AND lower(path) LIKE '%.webp' THEN 'novelai_v4_webp'
  WHEN meta_source = 'nai_v4' AND lower(path) LIKE '%.png'  THEN 'novelai_v4_png'
  WHEN meta_source = 'nai_v4'                               THEN 'novelai_v4'
  WHEN meta_source = 'nai_v3' AND lower(path) LIKE '%.webp' THEN 'novelai_webp'
  WHEN meta_source = 'nai_v3'                               THEN 'novelai_png'
  WHEN meta_source = 'comfy'  AND lower(path) LIKE '%.webm' THEN 'comfy_webm'
  WHEN meta_source = 'comfy'  AND lower(path) LIKE '%.webp' THEN 'comfy_webp'
  WHEN meta_source = 'comfy'  AND lower(path) LIKE '%.flac' THEN 'comfy_flac'
  WHEN meta_source = 'comfy'                                THEN 'comfy_png'
  WHEN meta_source = 'a1111'  AND lower(path) LIKE '%.jpg'  THEN 'a1111_jpg'
  WHEN meta_source = 'a1111'  AND lower(path) LIKE '%.jpeg' THEN 'a1111_jpg'
  WHEN meta_source = 'a1111'  AND lower(path) LIKE '%.webp' THEN 'a1111_webp'
  WHEN meta_source = 'a1111'  AND lower(path) LIKE '%.png'  THEN 'a1111_png'
  -- Unknown A1111 extensions stay unchanged: SQLite has no concise last-dot extension
  -- extraction matching db_meta_source's dynamic a1111_<ext> mapping, and E3 accepts a1111.
  ELSE meta_source
END
WHERE meta_source IN ('nai_v4', 'nai_v3', 'comfy', 'a1111');
