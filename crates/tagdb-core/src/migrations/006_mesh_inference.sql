CREATE TABLE IF NOT EXISTS peer_inference_disabled (
    peer_id        TEXT NOT NULL,
    inference_type TEXT NOT NULL,
    PRIMARY KEY (peer_id, inference_type)
);
