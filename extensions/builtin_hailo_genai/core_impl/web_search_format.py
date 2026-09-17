def format_search_context(results: list[dict], query: str) -> str:
    if not results:
        return ""
    lines = [
        "IMPORTANT: The following are LIVE web search results retrieved just now.",
        "You MUST use these results to answer. Do NOT use your training data.",
        f'Search query: "{query}"',
        "",
    ]
    for i, result in enumerate(results, 1):
        lines.append(f"[{i}] {result['title']}")
        if result["snippet"]:
            lines.append(f"    {result['snippet']}")
    lines.append("")
    lines.append("Answer based ONLY on the search results above. Cite sources by number [1], [2], etc.")
    return "\n".join(lines)
