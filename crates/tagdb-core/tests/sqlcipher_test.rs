#[tokio::test]
async fn encrypted_connection_can_query_files_count() {
    let Some(db_path) = std::env::var_os("YU_TEST_CIPHER_DB") else {
        return;
    };
    let key = std::env::var("YU_TEST_CIPHER_KEY").expect("YU_TEST_CIPHER_KEY must be set");
    let db_path = db_path.to_string_lossy();

    let pool = tagdb_core::connect_encrypted(&db_path, &key)
        .await
        .expect("encrypted database should open");

    let count: i64 = sqlx::query_scalar("SELECT count(*) FROM files")
        .fetch_one(&pool)
        .await
        .expect("files count query should succeed");

    assert!(count >= 0);
}

#[tokio::test]
async fn encrypted_connection_rejects_wrong_key() {
    let Some(db_path) = std::env::var_os("YU_TEST_CIPHER_DB") else {
        return;
    };
    let db_path = db_path.to_string_lossy();

    let pool = tagdb_core::connect_encrypted(&db_path, "wrong-key")
        .await
        .expect("connection setup may defer key validation");

    let result = sqlx::query_scalar::<_, i64>("SELECT count(*) FROM files")
        .fetch_one(&pool)
        .await;

    assert!(result.is_err());
}
