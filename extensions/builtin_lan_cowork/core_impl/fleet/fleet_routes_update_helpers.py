"""Helpers shared by fleet update/restart route modules."""
from __future__ import annotations


def gc_dispatches(dispatches: dict, update_status) -> None:
    terminal_states = (update_status.SUCCESS, update_status.FAILED)
    terminal_ids = [
        dispatch_id
        for dispatch_id, runner in dispatches.items()
        if getattr(runner, "_status", None) in terminal_states
    ]
    for old_id in terminal_ids[:-5]:
        dispatches.pop(old_id, None)


def validate_peer_ids(value):
    if not isinstance(value, list):
        return None, (
            {
                "error": "invalid_peer_ids",
                "message": "peer_ids must be a list",
            },
            400,
        )
    peer_ids: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            return None, (
                {
                    "error": "invalid_peer_ids",
                    "message": "peer_ids must be a list of non-empty strings",
                },
                400,
            )
        peer_ids.append(item.strip())
    return peer_ids, None


def validate_consent_tokens(value):
    if value is None:
        return {}, None
    if not isinstance(value, dict):
        return None, (
            {
                "error": "invalid_consent_tokens",
                "message": "consent_tokens must be an object",
            },
            400,
        )
    tokens: dict[str, str] = {}
    for peer_id, token in value.items():
        if not isinstance(peer_id, str) or not peer_id.strip():
            return None, (
                {
                    "error": "invalid_consent_tokens",
                    "message": "consent_tokens keys must be non-empty strings",
                },
                400,
            )
        if not isinstance(token, str):
            return None, (
                {
                    "error": "invalid_consent_tokens",
                    "message": "consent_tokens values must be strings",
                },
                400,
            )
        tokens[peer_id.strip()] = token
    return tokens, None
