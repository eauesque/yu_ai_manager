"""Parse and serialize XMP packets at namespace granularity.

Data model — each XMP packet is reduced to one :class:`XmpData` containing,
per namespace prefix:

* ``attrs`` — flat ``name -> value`` strings, written as
  ``prefix:name="value"`` attributes on the single ``rdf:Description``.
* ``list_items`` — at most one child element per namespace whose body is an
  ``rdf:Bag`` of ``rdf:li`` strings (the convention Dublin Core uses for
  ``dc:subject`` tag lists). The wrapper element name is remembered in
  ``list_element_name`` so it round-trips.

Multiple ``rdf:Description`` blocks in the input are merged. Namespaces not
in the registry are preserved by remembering their URIs in
``namespace_uris`` so the serializer can re-emit ``xmlns:`` declarations and
unknown attrs survive the round-trip.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

from core.tools.xmp.registry import RDF_NS, all_namespaces, prefix_for, uri_for

_XPACKET_HEADER = '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
_XPACKET_TRAILER = '\n<?xpacket end="w"?>'


@dataclass
class XmpData:
    """Decomposed XMP packet keyed by namespace prefix."""

    # prefix -> {attr name: value} for rdf:Description attrs.
    attrs: dict[str, dict[str, str]] = field(default_factory=dict)
    # prefix -> [list items] (the rdf:Bag/rdf:li strings).
    list_items: dict[str, list[str]] = field(default_factory=dict)
    # prefix -> wrapper local element name (e.g. "subject" for dc:subject).
    list_element_name: dict[str, str] = field(default_factory=dict)
    # prefix -> URI for any namespace (registered or unknown) seen here.
    namespace_uris: dict[str, str] = field(default_factory=dict)

    def get_attrs(self, prefix: str) -> dict[str, str]:
        return dict(self.attrs.get(prefix, {}))

    def get_list(self, prefix: str) -> list[str]:
        return list(self.list_items.get(prefix, []))


def parse(xmp_xml: str | None) -> XmpData:
    """Parse an XMP packet string into :class:`XmpData`. Empty input → empty data."""
    data = XmpData()
    if not xmp_xml or not xmp_xml.strip():
        return data

    body = _strip_xpacket(xmp_xml)
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return data

    uri_to_prefix = {uri: prefix for prefix, uri in all_namespaces().items()}

    rdf_desc_tag = f"{{{RDF_NS}}}Description"
    rdf_bag_tag = f"{{{RDF_NS}}}Bag"
    rdf_seq_tag = f"{{{RDF_NS}}}Seq"
    rdf_li_tag = f"{{{RDF_NS}}}li"

    for desc in root.iter(rdf_desc_tag):
        for qname, value in desc.attrib.items():
            if not qname.startswith("{"):
                continue
            uri, local = qname[1:].split("}", 1)
            prefix = uri_to_prefix.get(uri) or prefix_for(uri) or _autoassign_prefix(uri, data)
            if prefix == "rdf":
                continue
            data.namespace_uris.setdefault(prefix, uri)
            data.attrs.setdefault(prefix, {})[local] = value

        for child in desc:
            if not child.tag.startswith("{"):
                continue
            uri, local = child.tag[1:].split("}", 1)
            prefix = uri_to_prefix.get(uri) or prefix_for(uri) or _autoassign_prefix(uri, data)
            if prefix == "rdf":
                continue
            container = child.find(rdf_bag_tag)
            if container is None:
                container = child.find(rdf_seq_tag)
            if container is None:
                continue
            items = [li.text for li in container.findall(rdf_li_tag) if li.text is not None]
            data.list_items[prefix] = items
            data.list_element_name[prefix] = local
            data.namespace_uris.setdefault(prefix, uri)

    return data


def serialize(data: XmpData) -> str:
    """Serialize :class:`XmpData` to a complete XMP packet string."""
    used_prefixes = set(data.attrs.keys()) | set(data.list_items.keys())

    namespace_decls: list[str] = []
    for prefix in sorted(used_prefixes):
        uri = data.namespace_uris.get(prefix) or uri_for(prefix)
        if not uri:
            continue
        namespace_decls.append(f'xmlns:{prefix}="{_attr_escape(uri)}"')

    attr_lines: list[str] = []
    for prefix in sorted(data.attrs.keys()):
        for name in sorted(data.attrs[prefix].keys()):
            value = data.attrs[prefix][name]
            attr_lines.append(f'{prefix}:{name}="{_attr_escape(str(value))}"')

    desc_inner = "\n      ".join(namespace_decls + attr_lines)
    desc_open = f"<rdf:Description\n      {desc_inner}>" if desc_inner else "<rdf:Description>"

    list_blocks: list[str] = []
    for prefix in sorted(data.list_items.keys()):
        elem_name = data.list_element_name.get(prefix, "items")
        items = data.list_items[prefix]
        bag_lines = "\n".join(f"          <rdf:li>{escape(item)}</rdf:li>" for item in items)
        list_blocks.append(
            f"      <{prefix}:{elem_name}>\n"
            f"        <rdf:Bag>\n{bag_lines}\n        </rdf:Bag>\n"
            f"      </{prefix}:{elem_name}>"
        )

    if list_blocks:
        body = desc_open + "\n" + "\n".join(list_blocks) + "\n    </rdf:Description>"
    else:
        body = desc_open + "</rdf:Description>"

    return (
        _XPACKET_HEADER
        + '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
        + '  <rdf:RDF xmlns:rdf="' + RDF_NS + '">\n'
        + '    ' + body + '\n'
        + '  </rdf:RDF>\n'
        + '</x:xmpmeta>'
        + _XPACKET_TRAILER
    )


def _strip_xpacket(xmp_xml: str) -> str:
    s = xmp_xml.strip()
    if s.startswith("<?xpacket"):
        end = s.find("?>")
        if end != -1:
            s = s[end + 2 :].lstrip()
    # The trailer xpacket is also a PI; ET cannot parse trailing PIs at the
    # document root, so strip it if present.
    tail_idx = s.rfind("<?xpacket")
    if tail_idx != -1:
        s = s[:tail_idx].rstrip()
    return s


def _attr_escape(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def _autoassign_prefix(uri: str, data: XmpData) -> str:
    """Assign a synthetic prefix for an unknown URI seen in an existing file.

    We keep the data round-trip-safe even though the caller may not have
    registered this namespace ahead of time.
    """
    for prefix, existing in data.namespace_uris.items():
        if existing == uri:
            return prefix
    n = 0
    while True:
        candidate = f"ns{n}"
        if candidate not in data.namespace_uris and candidate not in {"rdf", "x"}:
            data.namespace_uris[candidate] = uri
            return candidate
        n += 1
