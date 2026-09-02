

def normalize_for_search(text: str, is_regex: bool = False) -> str:
    """Normalize escaped bracket literals for non-regex search."""
    if is_regex:
        return text
    normalized = text.replace('\\(', '(').replace('\\)', ')')
    normalized = normalized.replace('\\[', '[').replace('\\]', ']')
    normalized = normalized.replace('\\{', '{').replace('\\}', '}')
    return normalized


def parse_tag_query(query: str) -> list[str]:
    """Parse comma-separated tags and preserve `-tag` exclusions."""
    tags = []
    parts = [p.strip() for p in query.split(',') if p.strip()]
    for part in parts:
        if part.startswith('-'):
            tag = part[1:].strip().lower()
            if tag:
                tags.append('-' + tag)
        else:
            tag = part.strip().lower()
            if tag:
                tags.append(tag)
    return tags


def normalize_tag_for_search(tag: str) -> list[str]:
    """Return searchable tag variants (escaped/plain, underscore/space).

    Returns query-side search variants. The comparison target is
    `wd_tag_dict.tag_name_normalized` (= `normalize_tag()` output). Do not add
    query-side casefold/NFKC here; this preserves current recall semantics
    (spec 2026-06-02 §4.7).
    """
    normalized = tag.replace('\\(', '(').replace('\\)', ')')
    normalized = normalized.replace('\\[', '[').replace('\\]', ']')
    normalized = normalized.replace('\\{', '{').replace('\\}', '}')
    variants = [normalized]
    if normalized != tag:
        variants.append(tag)
    if '_' in normalized:
        variants.append(normalized.replace('_', ' '))
    elif ' ' in normalized:
        variants.append(normalized.replace(' ', '_'))
    return list(set(variants))
