"""Bluesky monitor configuration -- triage prompts + auto-response templates.

Stored in config.json under sns.bluesky_monitor.
"""

from __future__ import annotations

from typing import Any

from core.configuration.api import load_config_json, save_config_json

# -- Default triage prompts ------------------------------------------------

DEFAULT_TRIAGE_MENTION = (
    "Review this Bluesky mention and determine if it requires a response.\n\n"
    "Respond (valid):\n"
    "- A genuine question about the project or artwork\n"
    "- A bug report or technical issue\n"
    "- A collaboration request with specific details\n\n"
    "Ignore (invalid):\n"
    "- Generic praise with no question (e.g. 'nice!')\n"
    "- Spam or self-promotion\n"
    "- Hostile or abusive content\n"
    "- Bot-generated content\n\n"
    "Return: valid / invalid with reason."
)

DEFAULT_TRIAGE_REPLY = (
    "Review this reply to my Bluesky post.\n\n"
    "Respond (valid):\n"
    "- Asks a specific question\n"
    "- Reports an issue or bug\n"
    "- Provides useful feedback\n\n"
    "Ignore (invalid):\n"
    "- Simple emoji reaction\n"
    "- Generic comment with no question\n"
    "- Spam or off-topic\n\n"
    "Return: valid / invalid with reason."
)

DEFAULT_TRIAGE_QUOTE = (
    "Review this quote post of my content.\n\n"
    "Respond (valid):\n"
    "- Asks a question about the content\n"
    "- Makes a claim that needs correction\n\n"
    "Ignore (invalid):\n"
    "- Positive sharing without question\n"
    "- Unrelated commentary\n\n"
    "Return: valid / invalid with reason."
)

DEFAULT_AUTO_RESPONSE_MENTION = (
    "Thank you for reaching out! I'll take a look and get back to you."
)

DEFAULT_AUTO_RESPONSE_REPLY = (
    "Thanks for your comment! I'll review and respond shortly."
)

DEFAULT_AUTO_RESPONSE_QUOTE = ""

TRIAGE_DEFAULTS = {
    "mention": DEFAULT_TRIAGE_MENTION,
    "reply": DEFAULT_TRIAGE_REPLY,
    "quote": DEFAULT_TRIAGE_QUOTE,
}

AUTO_RESPONSE_DEFAULTS = {
    "mention": DEFAULT_AUTO_RESPONSE_MENTION,
    "reply": DEFAULT_AUTO_RESPONSE_REPLY,
    "quote": DEFAULT_AUTO_RESPONSE_QUOTE,
}


def _monitor_section() -> dict:
    """Load sns.bluesky_monitor section from config."""
    cfg = load_config_json()
    return cfg.get("sns", {}).get("bluesky_monitor", {})


def _save_monitor_section(section: dict) -> None:
    """Save sns.bluesky_monitor section to config."""
    cfg = load_config_json()
    sns = cfg.setdefault("sns", {})
    sns["bluesky_monitor"] = section
    save_config_json(cfg)


def get_monitor_config() -> dict[str, Any]:
    """Get full monitor configuration."""
    sec = _monitor_section()
    return {
        "poll_interval_minutes": sec.get("poll_interval_minutes", 30),
        "auto_dismiss_follow": sec.get("auto_dismiss_follow", True),
        "auto_dismiss_like": sec.get("auto_dismiss_like", True),
        "auto_dismiss_repost": sec.get("auto_dismiss_repost", True),
        "auto_respond_enabled": sec.get("auto_respond_enabled", False),
        "notify_on_connect": sec.get("notify_on_connect", True),
    }


def save_monitor_config(
    poll_interval_minutes: int | None = None,
    auto_dismiss_follow: bool | None = None,
    auto_dismiss_like: bool | None = None,
    auto_dismiss_repost: bool | None = None,
    auto_respond_enabled: bool | None = None,
    notify_on_connect: bool | None = None,
) -> dict[str, Any]:
    """Update monitor configuration."""
    sec = _monitor_section()
    if poll_interval_minutes is not None:
        sec["poll_interval_minutes"] = max(5, poll_interval_minutes)
    if auto_dismiss_follow is not None:
        sec["auto_dismiss_follow"] = auto_dismiss_follow
    if auto_dismiss_like is not None:
        sec["auto_dismiss_like"] = auto_dismiss_like
    if auto_dismiss_repost is not None:
        sec["auto_dismiss_repost"] = auto_dismiss_repost
    if auto_respond_enabled is not None:
        sec["auto_respond_enabled"] = auto_respond_enabled
    if notify_on_connect is not None:
        sec["notify_on_connect"] = notify_on_connect
    _save_monitor_section(sec)
    return get_monitor_config()


def get_triage_prompts() -> dict[str, str]:
    """Get triage prompts for mention/reply/quote."""
    sec = _monitor_section()
    prompts = sec.get("triage_prompts", {})
    return {
        "mention": prompts.get("mention", DEFAULT_TRIAGE_MENTION),
        "reply": prompts.get("reply", DEFAULT_TRIAGE_REPLY),
        "quote": prompts.get("quote", DEFAULT_TRIAGE_QUOTE),
    }


def save_triage_prompts(
    mention: str | None = None,
    reply: str | None = None,
    quote: str | None = None,
) -> dict[str, str]:
    """Update triage prompts."""
    sec = _monitor_section()
    prompts = sec.setdefault("triage_prompts", {})
    if mention is not None:
        prompts["mention"] = mention
    if reply is not None:
        prompts["reply"] = reply
    if quote is not None:
        prompts["quote"] = quote
    _save_monitor_section(sec)
    return get_triage_prompts()


def get_auto_response_templates() -> dict[str, str]:
    """Get auto-response templates for mention/reply/quote."""
    sec = _monitor_section()
    templates = sec.get("auto_response_templates", {})
    return {
        "mention": templates.get("mention", DEFAULT_AUTO_RESPONSE_MENTION),
        "reply": templates.get("reply", DEFAULT_AUTO_RESPONSE_REPLY),
        "quote": templates.get("quote", DEFAULT_AUTO_RESPONSE_QUOTE),
    }


def save_auto_response_templates(
    mention: str | None = None,
    reply: str | None = None,
    quote: str | None = None,
) -> dict[str, str]:
    """Update auto-response templates."""
    sec = _monitor_section()
    templates = sec.setdefault("auto_response_templates", {})
    if mention is not None:
        templates["mention"] = mention
    if reply is not None:
        templates["reply"] = reply
    if quote is not None:
        templates["quote"] = quote
    _save_monitor_section(sec)
    return get_auto_response_templates()
