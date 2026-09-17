"""Issue triage — classify and summarize fetched issues.

Uses LLM (if available) for intelligent triage, falls back to rule-based.
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Triage categories
VALID_BUG = "valid_bug"
FEATURE_REQUEST = "feature_request"
SKIP_EMOTIONAL = "skip_emotional"
SKIP_DUPLICATE = "skip_duplicate"
SKIP_LANGUAGE = "skip_language"
SKIP_LABEL = "skip_label"
NEEDS_INFO = "needs_info"


def _detect_language(text: str) -> str:
    """Simple language detection based on character ranges."""
    if not text:
        return "unknown"
    # Count CJK characters
    cjk = sum(1 for c in text if '\u3000' <= c <= '\u9fff' or '\uac00' <= c <= '\ud7af')
    latin = sum(1 for c in text if 'a' <= c.lower() <= 'z')
    total = cjk + latin
    if total == 0:
        return "unknown"
    if cjk / total > 0.3:
        # Further distinguish
        jp = sum(1 for c in text if '\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff')
        ko = sum(1 for c in text if '\uac00' <= c <= '\ud7af')
        if ko > jp:
            return "ko"
        if jp > 0:
            return "ja"
        return "zh"
    return "en"


def _has_technical_content(body: str) -> bool:
    """Check if issue body contains technical indicators."""
    patterns = [
        r"```",                    # Code blocks
        r"traceback|error|exception",  # Error keywords
        r"step[s]?\s*(to\s*)?reproduce",  # Reproduction steps
        r"expected|actual",        # Expected/actual behavior
        r"version|v\d+\.\d+",     # Version info
        r"log|output|console",     # Log references
        r"HTTP\s*\d{3}",          # HTTP status codes
        r"File\s+\"",             # Python traceback
        r"TypeError|ValueError|KeyError|AttributeError",
    ]
    text = body.lower()
    matches = sum(1 for p in patterns if re.search(p, text, re.IGNORECASE))
    return matches >= 2


def _is_emotional(body: str) -> bool:
    """Check if issue is primarily emotional/non-technical."""
    emotional_patterns = [
        r"please\s+(help|fix|do)",
        r"this\s+is\s+(terrible|awful|bad|broken|unacceptable)",
        r"you\s+(should|must|need\s+to)",
        r"i\s+(demand|insist|require)",
        r"!!!+",
        r"worst|hate|angry|frustrated",
    ]
    text = body.lower()
    matches = sum(1 for p in emotional_patterns if re.search(p, text))
    return matches >= 2 and not _has_technical_content(body)


def triage_issue(
    issue: dict,
    skip_labels: list[str] | None = None,
    language_filter: str = "en",
) -> dict[str, Any]:
    """Triage a single issue using rule-based classification.

    Returns:
        {
            "number": int,
            "title": str,
            "category": str,  # VALID_BUG, SKIP_*, etc.
            "reason": str,
            "summary": str,   # One-line summary
            "priority": str,  # "high" | "medium" | "low"
            "actionable": bool,
        }
    """
    skip_labels = skip_labels or []
    body = issue.get("body", "")
    title = issue.get("title", "")
    labels = issue.get("labels", [])
    number = issue.get("number", 0)

    # Skip pull requests
    if issue.get("is_pull_request"):
        return _result(number, title, "skip_pr", "Pull request, not an issue", False)

    # Skip by label
    for label in labels:
        if label.lower() in [s.lower() for s in skip_labels]:
            return _result(number, title, SKIP_LABEL,
                          f"Skipped: label '{label}'", False)

    # Language filter
    if language_filter:
        lang = _detect_language(title + " " + body)
        if lang != language_filter and lang != "unknown":
            return _result(number, title, SKIP_LANGUAGE,
                          f"Skipped: language '{lang}' (filter: {language_filter})", False)

    # Emotional check
    if _is_emotional(body):
        return _result(number, title, SKIP_EMOTIONAL,
                      "Skipped: emotional/non-technical content", False)

    # Technical content check
    has_tech = _has_technical_content(body)

    if has_tech:
        # Determine priority
        priority = "medium"
        lower_body = body.lower()
        if any(kw in lower_body for kw in ["crash", "data loss", "security", "critical"]):
            priority = "high"
        elif any(kw in lower_body for kw in ["minor", "cosmetic", "typo", "docs"]):
            priority = "low"

        summary = _extract_summary(title, body)
        return _result(number, title, VALID_BUG, summary, True, priority)

    # Feature request detection
    if any(kw in title.lower() for kw in ["feature", "request", "enhancement", "add", "support"]):
        return _result(number, title, FEATURE_REQUEST,
                      "Feature request", False)

    # Needs more info
    if len(body) < 50:
        return _result(number, title, NEEDS_INFO,
                      "Insufficient information", False)

    # Default: treat as potential bug
    return _result(number, title, VALID_BUG,
                  _extract_summary(title, body), True, "low")


def _result(
    number: int, title: str, category: str, reason: str,
    actionable: bool, priority: str = "low"
) -> dict:
    return {
        "number": number,
        "title": title,
        "category": category,
        "reason": reason,
        "priority": priority,
        "actionable": actionable,
    }


def _extract_summary(title: str, body: str) -> str:
    """Extract a one-line summary from issue body."""
    # Try to find error message
    for line in body.split("\n"):
        stripped = line.strip()
        if any(kw in stripped.lower() for kw in ["error:", "exception:", "traceback"]):
            return stripped[:200]
    # Fall back to first non-empty line
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("```"):
            return stripped[:200]
    return title


def triage_batch(
    issues: list[dict],
    skip_labels: list[str] | None = None,
    language_filter: str = "en",
) -> dict[str, Any]:
    """Triage a batch of issues and produce a summary report."""
    results = []
    for issue in issues:
        result = triage_issue(issue, skip_labels, language_filter)
        results.append(result)

    valid = [r for r in results if r["actionable"]]
    skipped = [r for r in results if not r["actionable"]]
    high = [r for r in valid if r["priority"] == "high"]
    medium = [r for r in valid if r["priority"] == "medium"]

    return {
        "total": len(results),
        "actionable": len(valid),
        "skipped": len(skipped),
        "high_priority": len(high),
        "medium_priority": len(medium),
        "results": results,
    }


def format_for_claude_code(issue: dict, comments: list[dict] | None = None) -> str:
    """Format an issue for Claude Code consumption.

    Structured text output with repo, issue number, error logs, and reproduction steps.
    """
    lines = [
        f"## GitHub Issue #{issue.get('number')} — {issue.get('title', '')}",
        f"**Repository:** {issue.get('html_url', '').rsplit('/issues/', 1)[0]}",
        f"**URL:** {issue.get('html_url', '')}",
        f"**Reporter:** {issue.get('user', '')}",
        f"**Labels:** {', '.join(issue.get('labels', [])) or 'none'}",
        f"**Created:** {issue.get('created_at', '')}",
        "",
        "### Description",
        issue.get("body", "(empty)"),
    ]

    if comments:
        lines.append("")
        lines.append("### Comments")
        for c in comments[:5]:
            lines.append(f"**{c.get('user', {}).get('login', 'unknown')}** ({c.get('created_at', '')}):")
            lines.append(c.get("body", "")[:1000])
            lines.append("")

    return "\n".join(lines)
