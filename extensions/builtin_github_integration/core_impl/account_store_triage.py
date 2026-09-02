"""GitHub account store — triage prompts + queue configuration."""

from __future__ import annotations

from .account_store_crud import _save_section, _section

# -- Default triage prompts for issue / PR / discussion --

DEFAULT_TRIAGE_PROMPT_ISSUE = (
    "Review the following GitHub issue and determine whether it is a "
    "technically valid bug report.\n\n"
    "Valid (valid) criteria:\n"
    "- Concrete reproduction steps are provided\n"
    "- Error log or stack trace is included\n"
    "- Environment info (OS, version, etc.) is present\n\n"
    "Invalid (invalid) criteria:\n"
    "- Emotional text only, no technical facts\n"
    "- Feature request, not a bug\n"
    "- Written in a language other than English\n"
    "- No actionable technical information\n\n"
    "Return your verdict (valid / invalid) and the reason."
)

DEFAULT_TRIAGE_PROMPT_PR = (
    "Do not accept pull requests. Close automatically."
)

DEFAULT_TRIAGE_PROMPT_DISCUSSION = (
    "Discussions are closed. No action required."
)

TRIAGE_PROMPT_DEFAULTS = {
    "issue": DEFAULT_TRIAGE_PROMPT_ISSUE,
    "pr": DEFAULT_TRIAGE_PROMPT_PR,
    "discussion": DEFAULT_TRIAGE_PROMPT_DISCUSSION,
}


def get_triage_config() -> dict:
    """Get triage configuration."""
    sec = _section()
    triage = sec.get("triage", {})
    return {
        "auto_skip_labels": triage.get("auto_skip_labels", ["question", "wontfix"]),
        "language_filter": triage.get("language_filter", "en"),
    }


def get_triage_prompts(repo: str = "") -> dict[str, str]:
    """Get triage prompts with per-repo fallback chain.

    Resolution: repo-specific -> global -> hardcoded defaults.
    """
    sec = _section()
    global_prompts = sec.get("triage_prompts", {})

    # Start with defaults
    result = {
        "issue": global_prompts.get("issue", DEFAULT_TRIAGE_PROMPT_ISSUE),
        "pr": global_prompts.get("pr", DEFAULT_TRIAGE_PROMPT_PR),
        "discussion": global_prompts.get("discussion", DEFAULT_TRIAGE_PROMPT_DISCUSSION),
    }

    # Override with repo-specific if present
    if repo:
        per_repo = sec.get("triage_prompts_per_repo", {}).get(repo, {})
        for key in ("issue", "pr", "discussion"):
            if key in per_repo and per_repo[key]:
                result[key] = per_repo[key]

    return result


def get_triage_prompts_per_repo() -> dict[str, dict[str, str]]:
    """Get all per-repo triage prompt overrides."""
    sec = _section()
    return sec.get("triage_prompts_per_repo", {})


def save_triage_prompts(
    issue: str | None = None,
    pr: str | None = None,
    discussion: str | None = None,
    repo: str = "",
) -> dict[str, str]:
    """Update triage prompts. If repo is given, saves per-repo override.

    Pass empty string for a key to clear the per-repo override (fall back to global).
    Pass None to keep existing value unchanged.
    """
    sec = _section()

    if repo:
        per_repo = sec.setdefault("triage_prompts_per_repo", {})
        repo_prompts = per_repo.setdefault(repo, {})
        for key, val in [("issue", issue), ("pr", pr), ("discussion", discussion)]:
            if val is None:
                continue
            if val == "":
                # Empty string = clear override, fall back to global
                repo_prompts.pop(key, None)
            else:
                repo_prompts[key] = val
        # Clean up empty repo entries
        if not repo_prompts:
            per_repo.pop(repo, None)
    else:
        prompts = sec.setdefault("triage_prompts", {})
        if issue is not None:
            prompts["issue"] = issue
        if pr is not None:
            prompts["pr"] = pr
        if discussion is not None:
            prompts["discussion"] = discussion

    _save_section(sec)
    return get_triage_prompts(repo)


def get_queue_config() -> dict:
    """Get issue queue configuration."""
    sec = _section()
    queue = sec.get("queue", {})
    return {
        "poll_interval_minutes": queue.get("poll_interval_minutes", 60),
        "auto_close_invalid": queue.get("auto_close_invalid", False),
        "notify_on_connect": queue.get("notify_on_connect", True),
    }


def save_queue_config(
    poll_interval_minutes: int | None = None,
    auto_close_invalid: bool | None = None,
    notify_on_connect: bool | None = None,
) -> dict:
    """Update issue queue configuration."""
    sec = _section()
    queue = sec.setdefault("queue", {})
    if poll_interval_minutes is not None:
        queue["poll_interval_minutes"] = max(5, poll_interval_minutes)
    if auto_close_invalid is not None:
        queue["auto_close_invalid"] = auto_close_invalid
    if notify_on_connect is not None:
        queue["notify_on_connect"] = notify_on_connect
    _save_section(sec)
    return get_queue_config()
