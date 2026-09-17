"""Prompt-library validators for MCP tools."""


from .validators_common import PROMPT_TITLE_MAX, VALID_PROMPT_SORTS, err


def validate_prompt_id(prompt_id: int) -> str | None:
    if prompt_id <= 0:
        return err(f"Invalid prompt_id: {prompt_id} (must be positive integer)")
    return None


def validate_prompt_sort(sort: str) -> str | None:
    if sort and sort not in VALID_PROMPT_SORTS:
        return err(f"Invalid sort value: '{sort}'. Valid options: {', '.join(sorted(VALID_PROMPT_SORTS))}")
    return None


def validate_prompt_title(title: str) -> str | None:
    if not title or not title.strip():
        return err("title is required (non-empty string)")
    if len(title) > PROMPT_TITLE_MAX:
        return err(f"title too long ({len(title)} > {PROMPT_TITLE_MAX})")
    return None
