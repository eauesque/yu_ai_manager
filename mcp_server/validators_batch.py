"""Batch and result validators for MCP tools."""


from .validators_common import BATCH_MAX, err


def validate_batch_size(items: list, expected_count: int = 0) -> str | None:
    if not isinstance(items, list) or len(items) == 0:
        return err("items array required (must be non-empty list)")
    if expected_count > 0 and expected_count != len(items):
        return err(
            f"expected_count ({expected_count}) != received items ({len(items)}): payload was likely truncated by MCP transport. "
            f"Split into batches of {BATCH_MAX} or fewer."
        )
    if len(items) > BATCH_MAX:
        return err(f"Batch size {len(items)} exceeds maximum of {BATCH_MAX}")
    return None


def check_batch_all_failed(response: dict) -> dict:
    data = response.get("data", response)
    if isinstance(data, dict):
        succeeded = data.get("succeeded", -1)
        failed = data.get("failed", 0)
        if succeeded == 0 and failed > 0:
            response["ok"] = False
    return response
