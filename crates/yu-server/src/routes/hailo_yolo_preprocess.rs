//! Letterbox preprocessing ported from Python `preprocess_image_yolo()`.
//! It preserves the aspect ratio while resizing to a square target and fills
//! remaining space with the fixed gray value 114.

use image::imageops::FilterType;
use image::{DynamicImage, GenericImageView, Rgb, RgbImage};

pub(crate) struct ScaleInfo {
    pub orig_w: u32,
    pub orig_h: u32,
    pub scale: f64,
    pub pad_x: f64,
    pub pad_y: f64,
}

const LETTERBOX_FILL: u8 = 114;

pub(crate) fn letterbox_resize(image: &DynamicImage, target_size: u32) -> (Vec<u8>, ScaleInfo) {
    let (orig_w, orig_h) = image.dimensions();
    let scale = (target_size as f64 / orig_w as f64).min(target_size as f64 / orig_h as f64);
    let new_w = crate::num::sat_u32((f64::from(orig_w) * scale).round());
    let new_h = crate::num::sat_u32((f64::from(orig_h) * scale).round());

    let resized = image.resize_exact(new_w.max(1), new_h.max(1), FilterType::Triangle);
    let pad_x = ((target_size - new_w) as f64) / 2.0;
    let pad_y = ((target_size - new_h) as f64) / 2.0;

    let mut canvas = RgbImage::from_pixel(target_size, target_size, Rgb([LETTERBOX_FILL; 3]));
    image::imageops::overlay(
        &mut canvas,
        &resized.to_rgb8(),
        crate::num::sat_i64(pad_x.round()),
        crate::num::sat_i64(pad_y.round()),
    );

    (
        canvas.into_raw(),
        ScaleInfo {
            orig_w,
            orig_h,
            scale,
            pad_x,
            pad_y,
        },
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn letterbox_resize_square_image_no_padding() {
        let img = image::DynamicImage::new_rgb8(640, 640);
        let (buf, info) = letterbox_resize(&img, 640);
        assert_eq!(buf.len(), 640 * 640 * 3);
        assert_eq!(info.orig_w, 640);
        assert_eq!(info.orig_h, 640);
        assert!((info.scale - 1.0).abs() < 1e-6);
        assert_eq!(info.pad_x, 0.0);
        assert_eq!(info.pad_y, 0.0);
    }

    #[test]
    fn letterbox_resize_wide_image_pads_vertically() {
        // 1280x640 -> scale=640/1280=0.5, resized=640x320, pad_y=(640-320)/2=160
        let img = image::DynamicImage::new_rgb8(1280, 640);
        let (buf, info) = letterbox_resize(&img, 640);
        assert_eq!(buf.len(), 640 * 640 * 3);
        assert!((info.scale - 0.5).abs() < 1e-6);
        assert!((info.pad_x - 0.0).abs() < 1e-6);
        assert!((info.pad_y - 160.0).abs() < 1e-6);

        // Padding region (top rows, y < pad_y) must be filled with LETTERBOX_FILL.
        let pad_idx: usize = 0;
        assert_eq!(&buf[pad_idx..pad_idx + 3], &[LETTERBOX_FILL; 3]);

        // Image region (y == pad_y, just past the padding boundary) is the
        // source image (black, RGB 0,0,0), which differs from the fill value.
        let image_idx = (160usize * 640) * 3;
        assert_eq!(&buf[image_idx..image_idx + 3], &[0u8, 0, 0]);
    }

    #[test]
    fn letterbox_resize_tall_image_pads_horizontally() {
        // 640x1280 -> scale=640/1280=0.5, resized=320x640, pad_x=(640-320)/2=160
        let img = image::DynamicImage::new_rgb8(640, 1280);
        let (buf, info) = letterbox_resize(&img, 640);
        assert!((info.scale - 0.5).abs() < 1e-6);
        assert!((info.pad_x - 160.0).abs() < 1e-6);
        assert!((info.pad_y - 0.0).abs() < 1e-6);
    }
}
