//! Hailo YOLO detection persistence.

use infer_core::yolo_postprocess::{round_to_four, Detection};
use sqlx::SqlitePool;

pub(crate) async fn write_detections(
    pool: &SqlitePool,
    file_id: i64,
    source: &str,
    detections: &[Detection],
) -> Result<(), sqlx::Error> {
    let value = if detections.is_empty() {
        "[]".to_owned()
    } else {
        let items: Vec<serde_json::Value> = detections
            .iter()
            .map(|detection| {
                serde_json::json!({
                    "class_id": detection.class_id,
                    "class_name": detection.class_name,
                    "confidence": detection.confidence,
                    "bbox": detection.bbox,
                })
            })
            .collect();
        serde_json::to_string(&items).unwrap_or_else(|_| "[]".to_owned())
    };
    let confidence = (!detections.is_empty()).then(|| {
        let average = detections
            .iter()
            .map(|detection| detection.confidence)
            .sum::<f64>()
            / detections.len() as f64;
        round_to_four(average)
    });

    sqlx::query(
        "INSERT INTO file_annotations (file_id, source, key, value, confidence, created_at) \
         VALUES (?1, ?2, 'detections', ?3, ?4, strftime('%s','now')) \
         ON CONFLICT(file_id, source, key) DO UPDATE SET \
         value = excluded.value, confidence = excluded.confidence, created_at = excluded.created_at",
    )
    .bind(file_id)
    .bind(source)
    .bind(value)
    .bind(confidence)
    .execute(pool)
    .await?;
    Ok(())
}

#[cfg(test)]
#[path = "hailo_yolo_postprocess/tests.rs"]
mod tests;
