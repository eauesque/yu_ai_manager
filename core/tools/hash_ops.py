"""Hash compute API operations."""

from typing import Any

from core.services_core.db_api import get_db_path
from core.tools.hash_jobs import start_compute_hashes_job


def start_hash_compute(hash_type: str, limit: int) -> dict[str, Any]:
    safe_limit = min(int(limit), 50000)
    start_compute_hashes_job(get_db_path(), hash_type, safe_limit)
    return {"started": True, "type": hash_type, "limit": safe_limit}
