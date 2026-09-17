"""Schema SQL for integrations, chat logs, and audit tables."""

BASE_SCHEMA_SQL_INTEGRATIONS = """
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    webhook_id   TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status_code  INTEGER,
    response_body TEXT,
    attempt      INTEGER NOT NULL DEFAULT 1,
    success      INTEGER NOT NULL DEFAULT 0,
    error        TEXT,
    created_at   INTEGER NOT NULL,
    delivered_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_webhook_id ON webhook_deliveries(webhook_id);
CREATE INDEX IF NOT EXISTS idx_webhook_deliveries_created_at ON webhook_deliveries(created_at);

CREATE TABLE IF NOT EXISTS tag_dictionary (
    id         INTEGER PRIMARY KEY,
    tag_name   TEXT NOT NULL UNIQUE COLLATE NOCASE,
    category   INTEGER NOT NULL DEFAULT 0,
    post_count INTEGER NOT NULL DEFAULT 0,
    aliases    TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_tag_dict_name ON tag_dictionary(tag_name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_tag_dict_post_count ON tag_dictionary(post_count DESC);

CREATE TABLE IF NOT EXISTS trophies (
    id             INTEGER PRIMARY KEY,
    trophy_type    TEXT NOT NULL UNIQUE,
    title          TEXT NOT NULL,
    tier           TEXT NOT NULL DEFAULT 'gold',
    category       TEXT NOT NULL DEFAULT 'milestone',
    achieved_month TEXT,
    achieved_at    INTEGER NOT NULL,
    metadata       TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_trophies_category ON trophies(category);

CREATE TABLE IF NOT EXISTS monthly_stats_cache (
    month      TEXT NOT NULL,
    stat_key   TEXT NOT NULL,
    stat_value TEXT NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (month, stat_key)
);

CREATE TABLE IF NOT EXISTS md_files (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    path       TEXT    NOT NULL UNIQUE,
    mtime      REAL    NOT NULL DEFAULT 0,
    size       INTEGER NOT NULL DEFAULT 0,
    title      TEXT    NOT NULL DEFAULT '',
    content    TEXT    NOT NULL DEFAULT '',
    is_deleted INTEGER NOT NULL DEFAULT 0,
    indexed_at INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_md_files_path ON md_files(path);
CREATE INDEX IF NOT EXISTS idx_md_files_is_deleted ON md_files(is_deleted);

CREATE TABLE IF NOT EXISTS chat_conversations (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source              TEXT    NOT NULL,
    external_id         TEXT,
    title               TEXT    NOT NULL DEFAULT '',
    model               TEXT    NOT NULL DEFAULT '',
    created_at          INTEGER NOT NULL DEFAULT 0,
    updated_at          INTEGER NOT NULL DEFAULT 0,
    message_count       INTEGER NOT NULL DEFAULT 0,
    imported_at         INTEGER NOT NULL DEFAULT 0,
    summary             TEXT,
    ai_processed_at     INTEGER,
    ai_model            TEXT,
    language            TEXT DEFAULT '',
    language_confidence REAL DEFAULT 0.0
);
CREATE INDEX IF NOT EXISTS idx_chat_conv_source ON chat_conversations(source);
CREATE INDEX IF NOT EXISTS idx_chat_conv_external_id ON chat_conversations(external_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_conv_source_extid ON chat_conversations(source, external_id);

CREATE TABLE IF NOT EXISTS chat_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    role            TEXT    NOT NULL,
    content         TEXT    NOT NULL DEFAULT '',
    created_at      INTEGER NOT NULL DEFAULT 0,
    seq             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_chat_msg_conv_id ON chat_messages(conversation_id);

CREATE TABLE IF NOT EXISTS chat_decisions (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    message_id      INTEGER,
    decision_text   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_decisions_conv ON chat_decisions(conversation_id);

CREATE TABLE IF NOT EXISTS chat_entities (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    message_id      INTEGER,
    entity_type     TEXT NOT NULL,
    entity_value    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_entities_type_value ON chat_entities(entity_type, entity_value);
CREATE INDEX IF NOT EXISTS idx_chat_entities_conv ON chat_entities(conversation_id);

CREATE TABLE IF NOT EXISTS chat_topics (
    id              INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
    topic           TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chat_topics_topic ON chat_topics(topic);

CREATE TABLE IF NOT EXISTS agent_action_journal (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id       TEXT NOT NULL,
    timestamp        TEXT NOT NULL,
    tool_name        TEXT NOT NULL,
    params_json      TEXT NOT NULL DEFAULT '{}',
    result_summary   TEXT,
    status           TEXT NOT NULL DEFAULT 'success',
    duration_ms      INTEGER DEFAULT 0,
    caller_info      TEXT DEFAULT '',
    affected_count   INTEGER DEFAULT 0,
    reversible       INTEGER DEFAULT 0,
    undo_params_json TEXT,
    undone           INTEGER DEFAULT 0,
    undone_at        TEXT
);
CREATE INDEX IF NOT EXISTS idx_agent_journal_session ON agent_action_journal(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_journal_time ON agent_action_journal(timestamp);
CREATE INDEX IF NOT EXISTS idx_agent_journal_tool ON agent_action_journal(tool_name);

CREATE TABLE IF NOT EXISTS audit_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT NOT NULL,
    event_type        TEXT NOT NULL,
    source            TEXT NOT NULL,
    target            TEXT,
    severity          TEXT NOT NULL,
    reported_to       TEXT NOT NULL,
    detail_json       TEXT,
    user_acknowledged INTEGER DEFAULT 0,
    acknowledged_at   TEXT,
    prev_hash         TEXT DEFAULT '',
    entry_hash        TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_log_event_type ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_log_severity ON audit_log(severity);
CREATE INDEX IF NOT EXISTS idx_audit_log_timestamp ON audit_log(timestamp);

CREATE TABLE IF NOT EXISTS agent_session_scopes (
    session_id  TEXT PRIMARY KEY,
    preset      TEXT NOT NULL DEFAULT 'organizer',
    name        TEXT NOT NULL DEFAULT '',
    denied_json TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    expires_at  TEXT
);

CREATE TABLE IF NOT EXISTS agent_auto_approve_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tool            TEXT NOT NULL,
    conditions_json TEXT NOT NULL DEFAULT '{}',
    approved_at     TEXT NOT NULL,
    approved_by     TEXT NOT NULL DEFAULT 'user'
);

CREATE TABLE IF NOT EXISTS gateway_status_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backend_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    from_state TEXT NOT NULL
        CHECK (from_state IN ('running','stopped','unknown')),
    to_state TEXT NOT NULL
        CHECK (to_state IN ('running','stopped')),
    last_request_id TEXT,
    metadata TEXT
);
CREATE INDEX IF NOT EXISTS idx_status_backend_time
    ON gateway_status_transitions(backend_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS bluesky_notification_queue (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    notification_type    TEXT NOT NULL,
    author_handle        TEXT NOT NULL,
    author_display_name  TEXT,
    uri                  TEXT NOT NULL,
    cid                  TEXT,
    subject_uri          TEXT,
    text                 TEXT,
    indexed_at           TEXT,
    fetched_at           TEXT,
    status               TEXT DEFAULT 'pending',
    triage_result        TEXT DEFAULT 'pending',
    auto_response_sent   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_bsky_queue_status ON bluesky_notification_queue(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_bsky_queue_uri ON bluesky_notification_queue(uri);
CREATE INDEX IF NOT EXISTS idx_bsky_queue_type ON bluesky_notification_queue(notification_type);

CREATE TABLE IF NOT EXISTS github_issue_queue (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    repo          TEXT NOT NULL,
    issue_number  INTEGER NOT NULL,
    title         TEXT,
    body          TEXT,
    created_at    TEXT,
    fetched_at    TEXT,
    status        TEXT DEFAULT 'pending',
    triage_result TEXT DEFAULT 'pending'
);
CREATE INDEX IF NOT EXISTS idx_github_queue_status ON github_issue_queue(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_github_queue_repo_issue ON github_issue_queue(repo, issue_number);

CREATE TABLE IF NOT EXISTS import_session (
    id                 TEXT PRIMARY KEY,
    peer_id            TEXT NOT NULL,
    peer_name          TEXT NOT NULL,
    mode               TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'pending',
    last_seen_rowid    INTEGER,
    snapshot_max_rowid INTEGER,
    total_files        INTEGER,
    done_files         INTEGER NOT NULL DEFAULT 0,
    import_folder      TEXT NOT NULL,
    options            TEXT NOT NULL DEFAULT '{"include_favorites":false,"merge_metadata":false}',
    created_at         INTEGER NOT NULL,
    updated_at         INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS import_file_id_map (
    session_id     TEXT NOT NULL REFERENCES import_session(id) ON DELETE CASCADE,
    remote_peer_id TEXT NOT NULL,
    remote_file_id INTEGER NOT NULL,
    local_file_id  INTEGER NOT NULL,
    status         TEXT NOT NULL DEFAULT 'done',
    PRIMARY KEY (session_id, remote_peer_id, remote_file_id)
);

CREATE TABLE IF NOT EXISTS import_collection_id_map (
    session_id           TEXT NOT NULL REFERENCES import_session(id) ON DELETE CASCADE,
    remote_peer_id       TEXT NOT NULL,
    remote_collection_id INTEGER NOT NULL,
    local_collection_id  INTEGER NOT NULL,
    PRIMARY KEY (session_id, remote_peer_id, remote_collection_id)
);

CREATE TABLE IF NOT EXISTS peer_pairing_requests (
    request_id      TEXT PRIMARY KEY,
    peer_id         TEXT NOT NULL,
    host            TEXT NOT NULL,
    port            INTEGER NOT NULL,
    pin_hash        TEXT,
    pin_expires_at  INTEGER,
    verify_attempts INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL,
    created_at      INTEGER NOT NULL,
    updated_at      INTEGER NOT NULL,
    pubkey          BLOB,
    x25519_pk       BLOB,
    commit_hash     BLOB,
    sas             TEXT,
    source_ip       TEXT
);
CREATE INDEX IF NOT EXISTS idx_pairing_status ON peer_pairing_requests(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_pairing_peer_id ON peer_pairing_requests(peer_id, status);

CREATE TABLE IF NOT EXISTS peer_tokens (
    peer_id    TEXT PRIMARY KEY,
    token_hash TEXT NOT NULL,
    issued_at  INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    revoked_at INTEGER,
    source     TEXT NOT NULL DEFAULT 'pairing',
    note       TEXT
);
CREATE INDEX IF NOT EXISTS idx_peer_tokens_expires ON peer_tokens(expires_at) WHERE revoked_at IS NULL;

CREATE TABLE IF NOT EXISTS peers (
    peer_id           TEXT PRIMARY KEY,
    name              TEXT,
    api_host          TEXT,
    api_port          INTEGER,
    token             TEXT,
    token_expires_at  INTEGER,
    token_issued_at   INTEGER,
    pubkey            BLOB,
    x25519_pk         BLOB,
    created_at        INTEGER NOT NULL,
    updated_at        INTEGER NOT NULL,
    last_reached_at   INTEGER,
    last_attempted_at INTEGER,
    -- Added by migration 86. Kept last so that a table created here and a table
    -- created by migration 86's ALTER end up with the same column order.
    inference_types   TEXT NOT NULL DEFAULT '[]'
);

-- Added by migration 86 alongside peers.inference_types. Disabled types live in
-- their own table because mDNS re-discovery may replace a peer row without
-- re-enabling a type the user turned off.
CREATE TABLE IF NOT EXISTS peer_inference_disabled (
    peer_id        TEXT NOT NULL,
    inference_type TEXT NOT NULL,
    PRIMARY KEY (peer_id, inference_type)
);

CREATE TABLE IF NOT EXISTS lan_cowork_identity (
    key   TEXT PRIMARY KEY,
    value BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_circuit_breaker_state (
    process_id    TEXT PRIMARY KEY,
    state         TEXT NOT NULL DEFAULT 'CLOSED',
    open_reason   TEXT NOT NULL DEFAULT '',
    failure_count INTEGER NOT NULL DEFAULT 0,
    last_updated  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_budget_usage (
    session_id       TEXT NOT NULL,
    process_id       TEXT NOT NULL,
    used_total       INTEGER NOT NULL DEFAULT 0,
    used_write       INTEGER NOT NULL DEFAULT 0,
    used_destructive INTEGER NOT NULL DEFAULT 0,
    last_updated     TEXT NOT NULL,
    PRIMARY KEY (session_id, process_id)
);

CREATE TABLE IF NOT EXISTS wd_tag_stats_cache (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    stats_json  TEXT    NOT NULL DEFAULT '{}',
    computed_at INTEGER NOT NULL DEFAULT 0
);
"""
