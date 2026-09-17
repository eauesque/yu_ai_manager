#[derive(Debug, thiserror::Error)]
pub enum TagdbError {
    #[error("database error: {0}")]
    Db(#[from] sqlx::Error),
    #[error("not found: {0}")]
    NotFound(String),
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    /// Database genesis refused or failed. The message is written for a user
    /// reading a start-up failure, so it names the resolved path and what to do.
    #[error("{0}")]
    Genesis(String),
    /// The database is at a schema this build cannot use. Also written for a
    /// user reading a start-up failure.
    #[error("{0}")]
    IncompatibleSchema(String),
}
