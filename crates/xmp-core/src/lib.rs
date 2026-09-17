//! Namespace-aware XMP packet parse/serialize/merge, ported from Python
//! `core/tools/xmp/` (packet.py/merge.py/io.py/registry.py). Shared by
//! Sweep (crates/yu-server/src/routes/sweep_common.rs) and WD-Tagger.
//! See docs/superpowers/specs/2026-07-06-wd-tagger-xmp-native-write-design.md.

pub mod io;
pub mod merge;
pub mod packet;
pub mod registry;

pub use merge::{merge_into_file, NamespaceMerge, XmpError};
pub use packet::{parse, serialize, XmpData};
