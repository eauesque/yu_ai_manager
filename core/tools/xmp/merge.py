"""High-level: read existing XMP, merge one namespace, write back.

This is the entry point most callers want. ``merge_into_file`` only touches
the named namespace; every other namespace's attrs and list items are
preserved verbatim across the round-trip — so two subsystems writing
different namespaces to the same image cannot clobber each other.
"""

from __future__ import annotations

from pathlib import Path

from core.tools.xmp.io import read_xmp_packet, write_xmp_packet
from core.tools.xmp.packet import XmpData, parse, serialize
from core.tools.xmp.registry import uri_for


def read_namespaces(image_path: str | Path) -> XmpData:
    """Read the image's XMP packet and return parsed :class:`XmpData`."""
    raw = read_xmp_packet(image_path)
    return parse(raw)


def merge_into_file(
    image_path: str | Path,
    *,
    prefix: str,
    attrs: dict[str, str] | None = None,
    list_items: list[str] | None = None,
    list_element_name: str | None = None,
    replace_attrs: bool = False,
) -> bool:
    """Merge one namespace's contribution into the image's XMP packet.

    Args:
        image_path: target file (PNG / JPEG / WebP).
        prefix: namespace prefix to update; must be registered or already
            present in the file. Other namespaces are left untouched.
        attrs: ``name -> value`` attributes to set under ``prefix:``. Merged
            into existing attrs by default; pass ``replace_attrs=True`` to
            drop any prior attrs for this prefix first.
        list_items: full replacement for the namespace's rdf:Bag list.
            Lists do not merge naturally so this is always replace-style.
        list_element_name: required when *list_items* is given (e.g.
            ``"subject"`` for ``dc:subject``).
        replace_attrs: when True, prior attrs for *prefix* are dropped
            before applying *attrs*.

    Returns ``True`` on successful write, ``False`` otherwise.
    """
    if not prefix:
        raise ValueError("prefix is required")
    if list_items is not None and not list_element_name:
        raise ValueError("list_element_name is required when list_items is given")

    data = read_namespaces(image_path)

    # Make sure the prefix has a URI in the data so the serializer emits
    # xmlns:<prefix>=... — fall back to the registry if this is the first
    # time we see it on this file.
    if prefix not in data.namespace_uris:
        uri = uri_for(prefix)
        if uri:
            data.namespace_uris[prefix] = uri

    if attrs is not None:
        if replace_attrs or prefix not in data.attrs:
            data.attrs[prefix] = {k: str(v) for k, v in attrs.items()}
        else:
            data.attrs[prefix].update({k: str(v) for k, v in attrs.items()})

    if list_items is not None:
        data.list_items[prefix] = list(list_items)
        data.list_element_name[prefix] = list_element_name  # type: ignore[assignment]

    new_xml = serialize(data)
    return write_xmp_packet(image_path, new_xml)
