"""ComfyUI CLIP prompt text extraction."""

from typing import Any


def find_clip_texts(obj: Any) -> tuple[list[str], list[str]]:
    pos: list[str] = []
    neg: list[str] = []

    if not isinstance(obj, dict):
        return pos, neg

    if isinstance(obj.get("nodes"), list):
        nodes_by_id = {}
        for n in obj["nodes"]:
            if isinstance(n, dict) and "id" in n:
                nodes_by_id[str(n["id"])] = n
    else:
        nodes_by_id = {k: v for k, v in obj.items() if isinstance(v, dict)}

    pos_node_ids = set()
    neg_node_ids = set()

    for node in nodes_by_id.values():
        ct = (node.get("class_type") or node.get("type") or "").lower()
        if "ksampler" not in ct:
            continue
        inputs = node.get("inputs", {})

        pos_link = inputs.get("positive")
        neg_link = inputs.get("negative")
        if isinstance(pos_link, list) and len(pos_link) >= 1:
            pos_node_ids.add(str(pos_link[0]))
        if isinstance(neg_link, list) and len(neg_link) >= 1:
            neg_node_ids.add(str(neg_link[0]))

    clip_nodes: list[tuple] = []
    for nid, node in nodes_by_id.items():
        ct = node.get("class_type") or node.get("type") or ""
        if not isinstance(ct, str) or "cliptextencode" not in ct.lower():
            continue

        inputs = node.get("inputs", {})
        if "flux" in ct.lower():
            clip_l = inputs.get("clip_l", "")
            t5xxl = inputs.get("t5xxl", "")
            parts = []
            if isinstance(clip_l, str) and clip_l.strip():
                parts.append(clip_l.strip())
            if isinstance(t5xxl, str) and t5xxl.strip():
                parts.append(t5xxl.strip())
            text = ", ".join(parts) if parts else ""
            if not text:
                continue
        else:
            text = inputs.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            text = text.strip()

        meta = node.get("_meta")
        title = meta.get("title") if isinstance(meta, dict) else None
        is_neg_title = isinstance(title, str) and "negative" in title.lower()
        clip_nodes.append((nid, text, is_neg_title))

    if pos_node_ids or neg_node_ids:
        used_ids = set()
        for nid, text, _ in clip_nodes:
            if nid in pos_node_ids:
                pos.append(text)
                used_ids.add(nid)
            elif nid in neg_node_ids:
                neg.append(text)
                used_ids.add(nid)

        for nid, text, is_neg_title in clip_nodes:
            if nid in used_ids:
                continue
            if is_neg_title:
                neg.append(text)
            else:
                pos.append(text)
    else:
        title_classified = False
        for _, text, is_neg_title in clip_nodes:
            if is_neg_title:
                neg.append(text)
                title_classified = True
            else:
                pos.append(text)

        if not title_classified and len(pos) >= 2 and not neg:
            neg.append(pos.pop(1))

    # Fallback for non-CLIP samplers (MMAudioSampler, AudioLDMSampler, etc.):
    # these expose prompt / negative_prompt directly on the sampler's inputs.
    if not pos and not neg:
        for node in nodes_by_id.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs")
            if not isinstance(inputs, dict):
                continue
            for k in ("prompt", "positive_prompt"):
                v = inputs.get(k)
                if isinstance(v, str) and v.strip():
                    pos.append(v.strip())
                    break
            v = inputs.get("negative_prompt")
            if isinstance(v, str) and v.strip():
                neg.append(v.strip())

    return pos, neg
