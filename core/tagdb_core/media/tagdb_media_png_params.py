"""A1111 parameter extraction helpers for legacy PNG chunks."""



def extract_a1111_parameters(chunks: dict[str, str]) -> str | None:
    if not chunks:
        return None

    for k in ("parameters", "Parameters", "PARAMETERS"):
        v = chunks.get(k)
        if isinstance(v, str) and v.strip():
            return v

    for k, v in chunks.items():
        if isinstance(k, str) and k.strip().lower() == "parameters" and isinstance(v, str) and v.strip():
            return v
    return None
