use super::*;

#[sqlx::test]
async fn write_detections_inserts_row_with_correct_source_and_key(pool: SqlitePool) {
    sqlx::query(
        "CREATE TABLE file_annotations (id INTEGER PRIMARY KEY, file_id INTEGER, source TEXT, key TEXT, value BLOB, confidence REAL, created_at INTEGER, UNIQUE(file_id, source, key))",
    )
    .execute(&pool)
    .await
    .unwrap();
    let detections = vec![Detection {
        class_id: 0,
        class_name: "person".to_owned(),
        confidence: 0.9,
        bbox: [0.1, 0.1, 0.5, 0.5],
    }];

    write_detections(&pool, 1, "hailo:yolov8n", &detections)
        .await
        .unwrap();
    let row: (String, String, f64) =
        sqlx::query_as("SELECT source, key, confidence FROM file_annotations WHERE file_id = 1")
            .fetch_one(&pool)
            .await
            .unwrap();
    assert_eq!(row.0, "hailo:yolov8n");
    assert_eq!(row.1, "detections");
    assert!((row.2 - 0.9).abs() < 1e-6);
}

#[sqlx::test]
async fn write_detections_empty_writes_empty_array_and_null_confidence(pool: SqlitePool) {
    sqlx::query(
        "CREATE TABLE file_annotations (id INTEGER PRIMARY KEY, file_id INTEGER, source TEXT, key TEXT, value BLOB, confidence REAL, created_at INTEGER, UNIQUE(file_id, source, key))",
    )
    .execute(&pool)
    .await
    .unwrap();

    write_detections(&pool, 2, "hailo:yolov8n", &[])
        .await
        .unwrap();
    let row: (String, Option<f64>) =
        sqlx::query_as("SELECT value, confidence FROM file_annotations WHERE file_id = 2")
            .fetch_one(&pool)
            .await
            .unwrap();
    assert_eq!(row.0, "[]");
    assert!(row.1.is_none());
}
