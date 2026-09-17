"""SessionStart hook helper: save session_id and transcript_path from stdin JSON to /tmp."""
import json
import logging
import sys

logger = logging.getLogger(__name__)

try:
    data = json.load(sys.stdin)
    session_id = data.get("session_id", data.get("sessionId", ""))
    transcript_path = data.get("transcript_path", "")
    if session_id:
        with open("/tmp/cc-session-id", "w") as f:
            f.write(session_id)
    if transcript_path:
        with open("/tmp/cc-session-transcript", "w") as f:
            f.write(transcript_path)
except Exception:
    logger.debug("step failed", exc_info=True)
