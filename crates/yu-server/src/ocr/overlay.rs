use std::{
    fs,
    path::{Path, PathBuf},
};

use ab_glyph::{point, Font, FontArc, GlyphId, PxScale, ScaleFont};
use image::{
    codecs::{jpeg::JpegEncoder, png::PngEncoder},
    ColorType, DynamicImage, ImageEncoder, Rgba, RgbaImage,
};
use sha2::{Digest, Sha256};

use super::{
    overlay_layout::{
        self, BOX_PADDING, DEFAULT_BG_OPACITY, JPEG_QUALITY, LABEL_COLORS, OUTLINE_COLOR,
        OUTLINE_OFFSETS, PANEL_BACKGROUND, PANEL_BADGE_ALPHA, PANEL_BADGE_OFFSET_X,
        PANEL_BADGE_OFFSET_Y, PANEL_BADGE_WIDTH_PADDING, PANEL_FONT_MAX, PANEL_FONT_MIN,
        PANEL_FONT_WIDTH_DIVISOR, PANEL_LABEL_TEXT_GAP, PANEL_LINE_GAP, PANEL_PADDING,
        PANEL_RADIUS, PANEL_SMALL_FONT_MIN, PANEL_TEXT_COLOR, PANEL_TEXT_OFFSET_X,
        PANEL_WRAP_WIDTH_OFFSET, TEXT_COLOR,
    },
    parsers::OcrRegion,
};

pub const FONT_NAME: &str = "NotoSansCJK-Regular.ttc";
pub const LICENSE_NAME: &str = "OFL-1.1.txt";
pub const FONT_URL: &str =
    "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTC/NotoSansCJK-Regular.ttc";
pub const LICENSE_URL: &str = "https://raw.githubusercontent.com/notofonts/noto-fonts/main/LICENSE";
const FONT_SHA256: &str = "b76b0433203017ca80401b2ee0dd69350349871c4b19d504c34dbdd80541690a";
const LICENSE_SHA256: &str = "0dab92d0544f7b233403f14b84a663bdbfa746982eda629e7f4f9ffe1b036feb";
const MAX_REGIONS: usize = 1_000;
const MAX_LINES: usize = 200;
const MAX_PANEL_HEIGHT: u32 = 8_192;
const MAX_PIXELS: u64 = 64_000_000;
const MAX_DOWNLOAD_BYTES: usize = 32 * 1024 * 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Mode {
    Translated,
    Original,
    Both,
}
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Format {
    Png,
    Jpeg,
}

#[derive(Debug)]
pub enum Error {
    FontMissing,
    FontInvalid,
    TooLarge,
    Image(String),
    Encode(String),
}

pub fn parse_mode(value: Option<&str>) -> Option<Mode> {
    match value.unwrap_or("translated") {
        "translated" => Some(Mode::Translated),
        "original" => Some(Mode::Original),
        "both" => Some(Mode::Both),
        _ => None,
    }
}
pub fn parse_format(value: Option<&str>) -> Option<Format> {
    match value.unwrap_or("png").to_ascii_uppercase().as_str() {
        "PNG" => Some(Format::Png),
        "JPEG" => Some(Format::Jpeg),
        _ => None,
    }
}
pub fn font_dir(cache_dir: &Path) -> PathBuf {
    cache_dir.join("ocr").join("fonts")
}

pub fn load_font(cache_dir: &Path) -> Result<FontArc, Error> {
    let base = font_dir(cache_dir);
    let font = fs::read(base.join(FONT_NAME)).map_err(|_| Error::FontMissing)?;
    let license = fs::read(base.join(LICENSE_NAME)).map_err(|_| Error::FontMissing)?;
    if digest(&font) != FONT_SHA256 || digest(&license) != LICENSE_SHA256 {
        return Err(Error::FontInvalid);
    }
    FontArc::try_from_vec(font).map_err(|_| Error::FontInvalid)
}

pub async fn download_font(cache_dir: &Path) -> Result<(), Error> {
    let client = reqwest::Client::builder()
        .user_agent("YU-AI-Manager")
        .build()
        .map_err(|error| Error::Image(error.to_string()))?;
    let font = download(&client, FONT_URL).await?;
    let license = download(&client, LICENSE_URL).await?;
    if digest(&font) != FONT_SHA256 || digest(&license) != LICENSE_SHA256 {
        return Err(Error::FontInvalid);
    }
    let base = font_dir(cache_dir);
    fs::create_dir_all(&base).map_err(|error| Error::Image(error.to_string()))?;
    atomic_write(&base.join(FONT_NAME), &font)?;
    atomic_write(&base.join(LICENSE_NAME), &license)
}

async fn download(client: &reqwest::Client, url: &str) -> Result<Vec<u8>, Error> {
    let response = client
        .get(url)
        .send()
        .await
        .map_err(|error| Error::Image(error.to_string()))?
        .error_for_status()
        .map_err(|error| Error::Image(error.to_string()))?;
    if response
        .content_length()
        .is_some_and(|size| size > MAX_DOWNLOAD_BYTES as u64)
    {
        return Err(Error::Image("font download exceeds limit".to_owned()));
    }
    let body = response
        .bytes()
        .await
        .map_err(|error| Error::Image(error.to_string()))?;
    if body.len() > MAX_DOWNLOAD_BYTES {
        return Err(Error::Image("font download exceeds limit".to_owned()));
    }
    Ok(body.to_vec())
}
fn atomic_write(path: &Path, data: &[u8]) -> Result<(), Error> {
    let temp = path.with_extension("tmp");
    fs::write(&temp, data).map_err(|error| Error::Image(error.to_string()))?;
    fs::rename(temp, path).map_err(|error| Error::Image(error.to_string()))
}
fn digest(data: &[u8]) -> String {
    hex::encode(Sha256::digest(data))
}

pub fn render(
    image_path: &Path,
    mut regions: Vec<OcrRegion>,
    full_text: &str,
    translations: &std::collections::HashMap<usize, String>,
    mode: Mode,
    format: Format,
    font: &FontArc,
) -> Result<Vec<u8>, Error> {
    if regions.len() > MAX_REGIONS {
        return Err(Error::TooLarge);
    }
    regions = overlay_layout::maybe_reparse_jsonl_regions(regions);
    if regions.len() > MAX_REGIONS {
        return Err(Error::TooLarge);
    }
    let mut image = image::open(image_path)
        .map_err(|error| Error::Image(error.to_string()))?
        .to_rgba8();
    if u64::from(image.width()) * u64::from(image.height()) > MAX_PIXELS {
        return Err(Error::TooLarge);
    }
    let mut panel = Vec::new();
    let mut has_boxes = false;
    let mut unrenderable = 0_usize;
    for region in &regions {
        if let Some((x, y, width, height)) = bbox(region) {
            has_boxes = true;
            let text = resolve_text(region, translations, mode);
            if !text.trim().is_empty() {
                unrenderable += missing_glyphs(font, &text);
                draw_box(&mut image, x, y, width, height, &text, font)?;
            }
        } else {
            let text = resolve_text(region, translations, mode);
            unrenderable += missing_glyphs(font, &text);
            panel.push((region.label.as_str(), text));
        }
    }
    panel.retain(|(_, text)| !text.trim().is_empty());
    if panel.is_empty() && !has_boxes && !full_text.trim().is_empty() {
        unrenderable += missing_glyphs(font, full_text);
        panel.push(("text", full_text.to_owned()));
    }
    if !panel.is_empty() {
        image = append_panel(image, &panel, font)?;
    }
    if unrenderable > 0 {
        tracing::warn!(unrenderable, "OCR overlay font cannot render code points");
    }
    encode(&image, format)
}

fn bbox(region: &OcrRegion) -> Option<(i64, i64, u32, u32)> {
    let (x, y, width, height) = (
        region.bbox.first()?,
        region.bbox.get(1)?,
        region.bbox.get(2)?,
        region.bbox.get(3)?,
    );
    if *width <= 0 || *height <= 0 {
        return None;
    }
    let width = u32::try_from(*width).ok()?;
    let height = u32::try_from(*height).ok()?;
    x.checked_add(i64::from(width))?;
    y.checked_add(i64::from(height))?;
    Some((*x, *y, width, height))
}
fn resolve_text(
    region: &OcrRegion,
    translations: &std::collections::HashMap<usize, String>,
    mode: Mode,
) -> String {
    match mode {
        Mode::Original => region.text.clone(),
        Mode::Translated => translations
            .get(&region.region_id)
            .filter(|text| !text.is_empty())
            .cloned()
            .unwrap_or_else(|| region.text.clone()),
        Mode::Both => translations
            .get(&region.region_id)
            .filter(|text| !text.is_empty())
            .map_or_else(
                || region.text.clone(),
                |text| format!("{}\n-> {text}", region.text),
            ),
    }
}
#[allow(
    clippy::cast_possible_truncation,
    clippy::cast_sign_loss,
    reason = "measured width is clamped to non-negative before conversion"
)]
fn draw_box(
    image: &mut RgbaImage,
    x: i64,
    y: i64,
    width: u32,
    height: u32,
    text: &str,
    font: &FontArc,
) -> Result<(), Error> {
    fill_rect(
        image,
        x,
        y,
        width,
        height,
        Rgba([255, 255, 255, DEFAULT_BG_OPACITY]),
    );
    let inner_w = width.saturating_sub(BOX_PADDING * 2);
    let inner_h = height.saturating_sub(BOX_PADDING * 2);
    if inner_w == 0 || inner_h == 0 {
        return Ok(());
    }
    let size = overlay_layout::auto_font_size(width, height, text) as f32;
    let lines = wrap(text, font, size, f64::from(inner_w));
    if lines.len() > MAX_LINES {
        return Err(Error::TooLarge);
    }
    let line_height = line_height(font, size);
    let total =
        line_height.saturating_mul(u32::try_from(lines.len()).map_err(|_| Error::TooLarge)?);
    let start_y = y + i64::from(BOX_PADDING + inner_h.saturating_sub(total) / 2);
    for (index, line) in lines.iter().enumerate() {
        let line_y = start_y + i64::from(line_height) * index as i64;
        if line_y + i64::from(line_height)
            > y.checked_add(i64::from(height)).ok_or(Error::TooLarge)?
        {
            break;
        }
        let line_w = measure(font, size, line).ceil().max(0.0) as u32;
        let line_x = x + i64::from(BOX_PADDING + inner_w.saturating_sub(line_w) / 2);
        for (dx, dy) in OUTLINE_OFFSETS {
            draw_text(
                image,
                font,
                size,
                line_x + i64::from(dx),
                line_y + i64::from(dy),
                line,
                OUTLINE_COLOR,
            );
        }
        draw_text(image, font, size, line_x, line_y, line, TEXT_COLOR);
    }
    Ok(())
}
#[allow(
    clippy::cast_possible_truncation,
    clippy::cast_sign_loss,
    reason = "font sizes and measured widths are clamped to non-negative bounded panel values"
)]
fn append_panel(
    image: RgbaImage,
    entries: &[(&str, String)],
    font: &FontArc,
) -> Result<RgbaImage, Error> {
    let width = image.width();
    let size = (width / PANEL_FONT_WIDTH_DIVISOR).clamp(PANEL_FONT_MIN, PANEL_FONT_MAX) as f32;
    let small = (size as u32).saturating_sub(4).max(PANEL_SMALL_FONT_MIN) as f32;
    let mut prepared = Vec::new();
    let mut panel_h = PANEL_PADDING;
    for (label, text) in entries {
        let wrapped = wrap(
            text,
            font,
            size,
            f64::from(width.saturating_sub(PANEL_PADDING * 2 + PANEL_WRAP_WIDTH_OFFSET)),
        );
        if wrapped.len() > MAX_LINES {
            return Err(Error::TooLarge);
        }
        let label_h = line_height(font, small);
        let text_h = line_height(font, size)
            .saturating_mul(u32::try_from(wrapped.len()).map_err(|_| Error::TooLarge)?);
        let entry_h = label_h
            .saturating_add(text_h)
            .saturating_add(PANEL_LINE_GAP);
        panel_h = panel_h.saturating_add(entry_h);
        prepared.push((*label, wrapped, label_h));
    }
    panel_h = panel_h.saturating_add(PANEL_PADDING);
    if panel_h > image.height().saturating_mul(2).min(MAX_PANEL_HEIGHT) {
        return Err(Error::TooLarge);
    }
    let total_h = image.height().checked_add(panel_h).ok_or(Error::TooLarge)?;
    if u64::from(width) * u64::from(total_h) > MAX_PIXELS {
        return Err(Error::TooLarge);
    }
    let mut output = RgbaImage::new(width, total_h);
    image::imageops::replace(&mut output, &image, 0, 0);
    fill_rect(
        &mut output,
        0,
        i64::from(image.height()),
        width,
        panel_h,
        Rgba(PANEL_BACKGROUND),
    );
    let mut y = PANEL_PADDING;
    for (label, wrapped, label_h) in prepared {
        let color = LABEL_COLORS
            .iter()
            .find(|(name, _)| *name == label)
            .map_or([107, 114, 128], |(_, color)| *color);
        let badge_w = measure(font, small, &label.to_uppercase()).ceil().max(0.0) as u32
            + PANEL_BADGE_WIDTH_PADDING;
        round_rect(
            &mut output,
            PANEL_PADDING,
            image.height() + y,
            badge_w,
            label_h,
            Rgba([color[0], color[1], color[2], PANEL_BADGE_ALPHA]),
        );
        draw_text(
            &mut output,
            font,
            small,
            i64::from(PANEL_PADDING + PANEL_BADGE_OFFSET_X),
            i64::from(image.height() + y + PANEL_BADGE_OFFSET_Y),
            &label.to_uppercase(),
            TEXT_COLOR,
        );
        y = y.saturating_add(label_h + PANEL_LABEL_TEXT_GAP);
        for line in wrapped {
            draw_text(
                &mut output,
                font,
                size,
                i64::from(PANEL_PADDING + PANEL_TEXT_OFFSET_X),
                i64::from(image.height() + y),
                &line,
                PANEL_TEXT_COLOR,
            );
            y = y.saturating_add(line_height(font, size));
        }
        y = y.saturating_add(PANEL_LINE_GAP);
    }
    Ok(output)
}
fn wrap(text: &str, font: &FontArc, size: f32, max_width: f64) -> Vec<String> {
    overlay_layout::wrap_text(text, max_width, &|line| {
        f64::from(measure(font, size, line))
    })
}
#[allow(
    clippy::cast_possible_truncation,
    clippy::cast_sign_loss,
    reason = "ceil().max(1.0) bounds the metric before conversion"
)]
fn line_height(font: &FontArc, size: f32) -> u32 {
    ((font.as_scaled(PxScale::from(size)).ascent() - font.as_scaled(PxScale::from(size)).descent())
        * 1.3)
        .ceil()
        .max(1.0) as u32
}
fn measure(font: &FontArc, size: f32, text: &str) -> f32 {
    let scaled = font.as_scaled(PxScale::from(size));
    let mut previous = None;
    text.chars().fold(0.0, |width, ch| {
        let id = font.glyph_id(ch);
        let kern = previous.map_or(0.0, |prior| scaled.kern(prior, id));
        previous = Some(id);
        width + kern + scaled.h_advance(id)
    })
}
#[allow(
    clippy::cast_possible_truncation,
    reason = "glyph pixel bounds are converted only to signed coordinates and clipped by blend"
)]
fn draw_text(
    image: &mut RgbaImage,
    font: &FontArc,
    size: f32,
    x: i64,
    y: i64,
    text: &str,
    color: [u8; 4],
) {
    let scale = PxScale::from(size);
    let mut cursor = 0.0;
    let mut previous: Option<GlyphId> = None;
    let baseline = font.as_scaled(scale).ascent();
    for ch in text.chars() {
        let id = font.glyph_id(ch);
        cursor += previous.map_or(0.0, |prior| font.as_scaled(scale).kern(prior, id));
        let glyph =
            id.with_scale_and_position(scale, point(x as f32 + cursor, y as f32 + baseline));
        if let Some(outline) = font.outline_glyph(glyph) {
            let bounds = outline.px_bounds();
            outline.draw(|gx, gy, coverage| {
                let px = bounds.min.x.floor() as i64 + i64::from(gx);
                let py = bounds.min.y.floor() as i64 + i64::from(gy);
                blend(image, px, py, color, coverage);
            });
        }
        cursor += font.as_scaled(scale).h_advance(id);
        previous = Some(id);
    }
}
#[allow(
    clippy::cast_possible_truncation,
    clippy::cast_sign_loss,
    reason = "alpha is clamped to 0..=1 and source channels are u8"
)]
fn blend(image: &mut RgbaImage, x: i64, y: i64, color: [u8; 4], coverage: f32) {
    let (Ok(x), Ok(y)) = (u32::try_from(x), u32::try_from(y)) else {
        return;
    };
    if x >= image.width() || y >= image.height() {
        return;
    }
    let pixel = image.get_pixel_mut(x, y);
    let alpha = (f32::from(color[3]) / 255.0 * coverage).clamp(0.0, 1.0);
    for (old, new) in pixel.0.iter_mut().zip(color) {
        *old = (f32::from(*old) * (1.0 - alpha) + f32::from(new) * alpha) as u8;
    }
}
fn fill_rect(image: &mut RgbaImage, x: i64, y: i64, width: u32, height: u32, color: Rgba<u8>) {
    let start_x = x.clamp(0, i64::from(image.width()));
    let start_y = y.clamp(0, i64::from(image.height()));
    let end_x = x
        .checked_add(i64::from(width))
        .unwrap_or(i64::MAX)
        .clamp(0, i64::from(image.width()));
    let end_y = y
        .checked_add(i64::from(height))
        .unwrap_or(i64::MAX)
        .clamp(0, i64::from(image.height()));
    for py in start_y..end_y {
        for px in start_x..end_x {
            blend(image, px, py, color.0, 1.0);
        }
    }
}

fn missing_glyphs(font: &FontArc, text: &str) -> usize {
    let missing = font.glyph_id('\0');
    text.chars()
        .filter(|ch| *ch != '\0' && font.glyph_id(*ch) == missing)
        .count()
}
fn round_rect(image: &mut RgbaImage, x: u32, y: u32, width: u32, height: u32, color: Rgba<u8>) {
    let radius = i64::from(PANEL_RADIUS);
    for py in 0..height {
        for px in 0..width {
            let dx = i64::from(px).min(i64::from(width.saturating_sub(1).saturating_sub(px)));
            let dy = i64::from(py).min(i64::from(height.saturating_sub(1).saturating_sub(py)));
            if dx >= radius
                || dy >= radius
                || (radius - dx).pow(2) + (radius - dy).pow(2) <= radius.pow(2)
            {
                blend(image, i64::from(x + px), i64::from(y + py), color.0, 1.0);
            }
        }
    }
}
fn encode(image: &RgbaImage, format: Format) -> Result<Vec<u8>, Error> {
    let mut bytes = Vec::new();
    match format {
        Format::Png => PngEncoder::new(&mut bytes)
            .write_image(
                image,
                image.width(),
                image.height(),
                ColorType::Rgba8.into(),
            )
            .map_err(|error| Error::Encode(error.to_string()))?,
        Format::Jpeg => JpegEncoder::new_with_quality(&mut bytes, JPEG_QUALITY)
            .write_image(
                &DynamicImage::ImageRgba8(image.clone()).to_rgb8(),
                image.width(),
                image.height(),
                ColorType::Rgb8.into(),
            )
            .map_err(|error| Error::Encode(error.to_string()))?,
    }
    Ok(bytes)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn region(bbox: Vec<i64>) -> OcrRegion {
        OcrRegion {
            region_id: 1,
            bbox,
            text: "text".to_owned(),
            confidence: 1.0,
            direction: "horizontal".to_owned(),
            label: "other".to_owned(),
        }
    }

    #[test]
    fn missing_font_is_an_explicit_condition() {
        let Ok(cache) = tempfile::tempdir() else {
            return;
        };
        assert!(matches!(load_font(cache.path()), Err(Error::FontMissing)));
    }

    #[test]
    fn modes_and_formats_validate_the_python_contract() {
        assert!(parse_mode(Some("invalid")).is_none());
        assert!(parse_format(Some("gif")).is_none());
        assert_eq!(parse_mode(Some("translated")), Some(Mode::Translated));
        assert_eq!(parse_format(Some("jPeG")), Some(Format::Jpeg));
    }

    #[test]
    fn negative_bbox_origin_is_preserved_without_unsigned_conversion() {
        assert_eq!(bbox(&region(vec![-4, -3, 8, 9])), Some((-4, -3, 8, 9)));
    }
}
