use std::path::Path;

use image::DynamicImage;
use pdfium_render::prelude::*;

use crate::routes::files::bind_pdfium;

pub fn page_count(src: &Path, library_dir: &Path, system_fallback: bool) -> Result<usize, String> {
    let pdfium = bind_pdfium(library_dir, system_fallback)
        .ok_or_else(|| "failed to bind pdfium".to_string())?;
    let document = pdfium
        .load_pdf_from_file(src, None)
        .map_err(|error| format!("failed to open PDF: {error}"))?;
    // `pages().len()` is an i32; a negative count would mean pdfium failed
    // to report, and 0 pages is the honest answer for that.
    Ok(usize::try_from(document.pages().len()).unwrap_or(0))
}

pub fn render_page(
    src: &Path,
    page_index: usize,
    dpi: u32,
    library_dir: &Path,
    system_fallback: bool,
) -> Result<DynamicImage, String> {
    let pdfium = bind_pdfium(library_dir, system_fallback)
        .ok_or_else(|| "failed to bind pdfium".to_string())?;
    let document = pdfium
        .load_pdf_from_file(src, None)
        .map_err(|error| format!("failed to open PDF: {error}"))?;
    let page = document
        .pages()
        .get(
            page_index
                .try_into()
                .map_err(|_| "page index is too large")?,
        )
        .map_err(|error| format!("failed to get page {page_index}: {error}"))?;
    let width = crate::num::sat_i32(f64::from(
        (page.width().value * dpi as f32 / 72.0).round().max(1.0),
    ));
    let bitmap = page
        .render_with_config(&PdfRenderConfig::new().set_target_width(width))
        .map_err(|error| format!("failed to render page {page_index}: {error}"))?;
    bitmap
        .as_image()
        .map_err(|error| format!("failed to convert rendered page: {error}"))
}

#[cfg(test)]
mod tests {
    use std::{
        path::{Path, PathBuf},
        sync::Mutex,
    };

    use super::{page_count, render_page};

    static PDFIUM_TEST_LOCK: Mutex<()> = Mutex::new(());

    fn fixture() -> PathBuf {
        Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/pdf/four_pages.pdf")
    }

    fn library_dir() -> PathBuf {
        crate::testing::pdfium::vendored_library_dir()
    }

    /// `None` means the vendored pdfium is absent and the caller must return
    /// without asserting. See `crate::testing::pdfium` for why that is a skip
    /// and not a pass.
    fn library_dir_or_skip(name: &str) -> Option<PathBuf> {
        crate::testing::pdfium::library_dir_or_skip(name)
    }

    #[test]
    fn renders_the_requested_page_not_a_fixed_one() {
        let _lock = PDFIUM_TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let Some(library_dir) = library_dir_or_skip("renders_the_requested_page_not_a_fixed_one")
        else {
            return;
        };
        let p0 = render_page(&fixture(), 0, 200, &library_dir, false).expect("page 0");
        let p1 = render_page(&fixture(), 1, 200, &library_dir, false).expect("page 1");
        assert_ne!(p0.as_bytes(), p1.as_bytes());
    }

    #[test]
    fn dpi_changes_the_raster_size() {
        let _lock = PDFIUM_TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let Some(library_dir) = library_dir_or_skip("dpi_changes_the_raster_size") else {
            return;
        };
        let low = render_page(&fixture(), 0, 72, &library_dir, false).expect("72 DPI page");
        let high = render_page(&fixture(), 0, 400, &library_dir, false).expect("400 DPI page");
        assert!(high.width() > low.width());
    }

    #[test]
    fn out_of_range_page_has_a_reason() {
        let _lock = PDFIUM_TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        assert!(!render_page(&fixture(), 99, 200, &library_dir(), false)
            .unwrap_err()
            .is_empty());
    }

    #[test]
    fn page_count_matches_fixture() {
        let _lock = PDFIUM_TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let Some(library_dir) = library_dir_or_skip("page_count_matches_fixture") else {
            return;
        };
        assert_eq!(
            page_count(&fixture(), &library_dir, false).expect("page count"),
            4
        );
    }
}
