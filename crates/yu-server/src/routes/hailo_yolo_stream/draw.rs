use bytes::Bytes;
use font8x8::{UnicodeFonts, BASIC_FONTS};
use infer_core::yolo_postprocess::Detection;

const BOX_COLOR: [u8; 3] = [0, 255, 0];
const TEXT_COLOR: [u8; 3] = [0, 0, 0];
const BOX_THICKNESS: u32 = 2;
const GLYPH_SIZE: u32 = 8;
const LABEL_HEIGHT: u32 = GLYPH_SIZE + 2;

#[derive(Clone, Debug, Eq, PartialEq)]
pub(crate) struct DrawnFrame {
    pub(crate) width: u32,
    pub(crate) height: u32,
    pub(crate) bytes: Bytes,
}

pub(crate) fn drawn_frame(
    bytes: &[u8],
    width: u32,
    height: u32,
    detections: &[Detection],
) -> Result<DrawnFrame, String> {
    let mut bytes = bytes.to_vec();
    draw_detections(&mut bytes, width, height, detections)?;
    Ok(DrawnFrame {
        width,
        height,
        bytes: Bytes::from(bytes),
    })
}

pub(crate) fn draw_detections(
    frame: &mut [u8],
    width: u32,
    height: u32,
    detections: &[Detection],
) -> Result<(), String> {
    let expected = usize::try_from(width)
        .ok()
        .zip(usize::try_from(height).ok())
        .and_then(|(width, height)| width.checked_mul(height))
        .and_then(|pixels| pixels.checked_mul(3))
        .ok_or_else(|| "source frame dimensions overflow".to_string())?;
    if frame.len() != expected || width == 0 || height == 0 {
        return Err("source frame dimensions do not match its bytes".to_string());
    }

    for detection in detections {
        let [x1, y1, x2, y2] = detection.bbox;
        let left = coordinate(x1, width);
        let top = coordinate(y1, height);
        let right = coordinate(x2, width);
        let bottom = coordinate(y2, height);
        if left > right || top > bottom {
            continue;
        }
        draw_rectangle(frame, width, height, left, top, right, bottom);
        let label = format!(
            "{} {:.0}%",
            detection.class_name,
            detection.confidence * 100.0
        );
        draw_label(frame, width, height, left, top, &label);
    }
    Ok(())
}

fn coordinate(value: f64, extent: u32) -> u32 {
    u32::try_from(
        crate::num::sat_u64(value * f64::from(extent)).min(u64::from(extent.saturating_sub(1))),
    )
    .unwrap_or(0)
}

fn draw_rectangle(
    frame: &mut [u8],
    width: u32,
    height: u32,
    left: u32,
    top: u32,
    right: u32,
    bottom: u32,
) {
    for offset in 0..BOX_THICKNESS {
        let x1 = left.saturating_add(offset).min(right);
        let x2 = right.saturating_sub(offset).max(left);
        let y1 = top.saturating_add(offset).min(bottom);
        let y2 = bottom.saturating_sub(offset).max(top);
        for x in x1..=x2 {
            set_pixel(frame, width, height, x, y1, BOX_COLOR);
            set_pixel(frame, width, height, x, y2, BOX_COLOR);
        }
        for y in y1..=y2 {
            set_pixel(frame, width, height, x1, y, BOX_COLOR);
            set_pixel(frame, width, height, x2, y, BOX_COLOR);
        }
    }
}

/// Every narrowing here is bounded before it happens: the label width is
/// `.min()`ed against the frame width (a `u32`) before becoming one, and the
/// glyph index and row are bounded by the label's character count and the 8-row
/// font. `set_pixel` bounds-checks against `width`/`height` regardless, so an
/// out-of-frame coordinate draws nothing rather than corrupting the buffer.
#[allow(clippy::cast_possible_truncation)]
fn draw_label(frame: &mut [u8], width: u32, height: u32, left: u32, top: u32, label: &str) {
    let label_width = label
        .chars()
        .count()
        .saturating_mul(GLYPH_SIZE as usize)
        .min(width.saturating_sub(left) as usize) as u32;
    if label_width == 0 {
        return;
    }
    let label_top = top.saturating_sub(LABEL_HEIGHT);
    for y in label_top..label_top.saturating_add(LABEL_HEIGHT).min(height) {
        for x in left..left.saturating_add(label_width).min(width) {
            set_pixel(frame, width, height, x, y, BOX_COLOR);
        }
    }
    for (index, character) in label.chars().enumerate() {
        let Some(glyph) = BASIC_FONTS.get(character).or_else(|| BASIC_FONTS.get('?')) else {
            continue;
        };
        let glyph_left = left.saturating_add(index as u32 * GLYPH_SIZE);
        for (row, bits) in glyph.into_iter().enumerate() {
            for column in 0..GLYPH_SIZE {
                if bits & (1 << column) != 0 {
                    set_pixel(
                        frame,
                        width,
                        height,
                        glyph_left.saturating_add(column),
                        label_top.saturating_add(row as u32 + 1),
                        TEXT_COLOR,
                    );
                }
            }
        }
    }
}

fn set_pixel(frame: &mut [u8], width: u32, height: u32, x: u32, y: u32, color: [u8; 3]) {
    if x >= width || y >= height {
        return;
    }
    let offset = (y as usize * width as usize + x as usize) * 3;
    frame[offset..offset + 3].copy_from_slice(&color);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn draws_clamped_box_and_label_without_touching_invalid_frames() {
        let mut frame = vec![255; 20 * 20 * 3];
        draw_detections(
            &mut frame,
            20,
            20,
            &[Detection {
                class_id: 0,
                class_name: "person".to_string(),
                confidence: 0.75,
                bbox: [-0.2, 0.5, 1.2, 0.9],
            }],
        )
        .unwrap();

        assert_eq!(&frame[(10 * 20 * 3)..(10 * 20 * 3 + 3)], &BOX_COLOR);
        assert!(frame.as_chunks::<3>().0.contains(&TEXT_COLOR));
        assert!(draw_detections(&mut frame[..3], 20, 20, &[]).is_err());
    }
}
