// yufile:// custom URI scheme handler for YU AI Manager.
// Serves media files (video/audio only) via a custom protocol,
// bypassing CSP restrictions while blocking non-media file access.

#[path = "yufile_handler.rs"]
mod handler;
#[path = "yufile_mime.rs"]
mod mime;
#[path = "yufile_range.rs"]
mod range;

pub use handler::handle_yufile_request;
pub use mime::{is_allowed_media_ext, mime_from_ext};
pub use range::parse_range;

#[cfg(test)]
#[path = "yufile_tests.rs"]
mod tests;
