-- Migration 84: Rust migration runner initialization marker.
-- No schema changes. This version in schema_version signals
-- that the Rust runner manages migrations from 84 onward.
SELECT 1;
