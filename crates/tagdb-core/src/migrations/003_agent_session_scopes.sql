CREATE TABLE IF NOT EXISTS agent_session_scopes (
    session_id  TEXT PRIMARY KEY,
    preset      TEXT NOT NULL DEFAULT 'organizer',
    name        TEXT NOT NULL DEFAULT '',
    denied_json TEXT NOT NULL DEFAULT '[]',
    created_at  TEXT NOT NULL,
    expires_at  TEXT
);
