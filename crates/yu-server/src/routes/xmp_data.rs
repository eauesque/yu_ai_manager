use std::collections::BTreeMap;

/// namespace prefix -> (属性名 -> 値) / (リスト要素名, 要素配列) を保持する
/// 汎用XMPデータモデル。Python `core.tools.xmp.packet.XmpData` に相当。
#[derive(Debug, Default, Clone, PartialEq)]
pub(crate) struct XmpData {
    pub(crate) namespace_uris: BTreeMap<String, String>,
    pub(crate) attrs: BTreeMap<String, BTreeMap<String, String>>,
    /// prefix -> (list wrapper element name, item values)
    pub(crate) list_items: BTreeMap<String, (String, Vec<String>)>,
}

const XPACKET_HEADER: &str = "<?xpacket begin=\"\u{FEFF}\" id=\"W5M0MpCehiHzreSzNTczkc9d\"?>\n";
const XPACKET_TRAILER: &str = "\n<?xpacket end=\"w\"?>";
const RDF_NS: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#";

fn attr_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

fn list_item_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

/// namespace URIレジストリ。Python `core/tools/xmp/registry.py` の登録値と一致させる。
pub(crate) fn uri_for(prefix: &str) -> Option<&'static str> {
    match prefix {
        "wdtag" => Some("http://ns.yu-ai-manager/wdtag/1.0/"),
        "dc" => Some("http://purl.org/dc/elements/1.1/"),
        _ => None,
    }
}

pub(crate) fn serialize_xmp(data: &XmpData) -> String {
    let mut used_prefixes: Vec<&String> = data
        .attrs
        .keys()
        .chain(data.list_items.keys())
        .collect::<std::collections::BTreeSet<_>>()
        .into_iter()
        .collect();
    used_prefixes.sort();

    let mut namespace_decls = Vec::new();
    for prefix in &used_prefixes {
        let uri = data
            .namespace_uris
            .get(*prefix)
            .cloned()
            .or_else(|| uri_for(prefix).map(str::to_string));
        if let Some(uri) = uri {
            namespace_decls.push(format!("xmlns:{prefix}=\"{}\"", attr_escape(&uri)));
        }
    }

    let mut attr_lines = Vec::new();
    for (prefix, kv) in &data.attrs {
        for (name, value) in kv {
            attr_lines.push(format!("{prefix}:{name}=\"{}\"", attr_escape(value)));
        }
    }

    let desc_inner: Vec<String> = namespace_decls.into_iter().chain(attr_lines).collect();
    let desc_open = if desc_inner.is_empty() {
        "<rdf:Description>".to_string()
    } else {
        format!("<rdf:Description\n      {}>", desc_inner.join("\n      "))
    };

    let mut list_blocks = Vec::new();
    for (prefix, (elem_name, items)) in &data.list_items {
        let bag_lines: Vec<String> = items
            .iter()
            .map(|item| format!("          <rdf:li>{}</rdf:li>", list_item_escape(item)))
            .collect();
        list_blocks.push(format!(
            "      <{prefix}:{elem_name}>\n        <rdf:Bag>\n{}\n        </rdf:Bag>\n      </{prefix}:{elem_name}>",
            bag_lines.join("\n")
        ));
    }

    let body = if list_blocks.is_empty() {
        format!("{desc_open}</rdf:Description>")
    } else {
        format!(
            "{desc_open}\n{}\n    </rdf:Description>",
            list_blocks.join("\n")
        )
    };

    format!(
        "{XPACKET_HEADER}<x:xmpmeta xmlns:x=\"adobe:ns:meta/\">\n  <rdf:RDF xmlns:rdf=\"{RDF_NS}\">\n    {body}\n  </rdf:RDF>\n</x:xmpmeta>{XPACKET_TRAILER}"
    )
}

fn strip_xpacket(input: &str) -> &str {
    let s = input.trim();
    let s = if let Some(rest) = s.strip_prefix("<?xpacket") {
        match rest.find("?>") {
            Some(end) => rest[end + 2..].trim_start(),
            None => s,
        }
    } else {
        s
    };
    match s.rfind("<?xpacket") {
        Some(idx) => s[..idx].trim_end(),
        None => s,
    }
}

/// XMPパケット文字列を`XmpData`へパースする。破損/空入力は空の`XmpData`を返す
/// (Python `parse()`の`ET.ParseError`→空、と同じ仕様)。
pub(crate) fn parse_xmp(raw: &str) -> XmpData {
    let mut data = XmpData::default();
    if raw.trim().is_empty() {
        return data;
    }
    let body = strip_xpacket(raw);
    let doc = match roxmltree::Document::parse(body) {
        Ok(doc) => doc,
        Err(_) => return data,
    };

    for desc in doc
        .descendants()
        .filter(|n| n.has_tag_name((RDF_NS, "Description")))
    {
        for attr in desc.attributes() {
            let Some(uri) = attr.namespace() else {
                continue;
            };
            if uri == RDF_NS {
                continue;
            }
            let prefix = prefix_for_uri(uri, &data);
            data.namespace_uris
                .entry(prefix.clone())
                .or_insert_with(|| uri.to_string());
            data.attrs
                .entry(prefix)
                .or_default()
                .insert(attr.name().to_string(), attr.value().to_string());
        }

        for child in desc.children().filter(|n| n.is_element()) {
            let Some(uri) = child.tag_name().namespace() else {
                continue;
            };
            if uri == RDF_NS {
                continue;
            }
            let prefix = prefix_for_uri(uri, &data);
            let container = child
                .children()
                .find(|n| n.has_tag_name((RDF_NS, "Bag")) || n.has_tag_name((RDF_NS, "Seq")));
            let Some(container) = container else { continue };
            let items: Vec<String> = container
                .children()
                .filter(|n| n.has_tag_name((RDF_NS, "li")))
                .filter_map(|n| n.text().map(str::to_string))
                .collect();
            data.list_items
                .insert(prefix.clone(), (child.tag_name().name().to_string(), items));
            data.namespace_uris
                .entry(prefix)
                .or_insert_with(|| uri.to_string());
        }
    }

    data
}

fn prefix_for_uri(uri: &str, data: &XmpData) -> String {
    for (prefix, existing) in &data.namespace_uris {
        if existing == uri {
            return prefix.clone();
        }
    }
    if let Some(known) = ["wdtag", "dc"].iter().find(|p| uri_for(p) == Some(uri)) {
        return known.to_string();
    }
    let mut n = 0;
    loop {
        let candidate = format!("ns{n}");
        if !data.namespace_uris.contains_key(&candidate) && candidate != "rdf" && candidate != "x" {
            return candidate;
        }
        n += 1;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn serialize_xmp_produces_xpacket_header_and_trailer() {
        let data = XmpData::default();
        let xml = serialize_xmp(&data);
        assert!(xml.starts_with("<?xpacket begin=\"\u{FEFF}\" id=\"W5M0MpCehiHzreSzNTczkc9d\"?>\n"));
        assert!(xml.ends_with("\n<?xpacket end=\"w\"?>"));
    }

    #[test]
    fn serialize_xmp_sorts_prefixes_and_attrs() {
        let mut data = XmpData::default();
        data.attrs.insert("wdtag".to_string(), {
            let mut m = BTreeMap::new();
            m.insert("model".to_string(), "wd-swinv2".to_string());
            m.insert("tag_count".to_string(), "3".to_string());
            m
        });
        let xml = serialize_xmp(&data);
        let model_pos = xml.find("wdtag:model").unwrap();
        let tag_count_pos = xml.find("wdtag:tag_count").unwrap();
        assert!(
            model_pos < tag_count_pos,
            "attrs must be sorted alphabetically by name"
        );
    }

    #[test]
    fn serialize_xmp_writes_list_as_rdf_bag() {
        let mut data = XmpData::default();
        data.list_items.insert(
            "dc".to_string(),
            (
                "subject".to_string(),
                vec!["blue_eyes".to_string(), "smile".to_string()],
            ),
        );
        let xml = serialize_xmp(&data);
        assert!(xml.contains("<dc:subject>"));
        assert!(xml.contains("<rdf:Bag>"));
        assert!(xml.contains("<rdf:li>blue_eyes</rdf:li>"));
        assert!(xml.contains("<rdf:li>smile</rdf:li>"));
    }

    #[test]
    fn serialize_xmp_escapes_attr_values_including_quotes() {
        let mut data = XmpData::default();
        data.attrs.insert("wdtag".to_string(), {
            let mut m = BTreeMap::new();
            m.insert("model".to_string(), "a\"b".to_string());
            m
        });
        let xml = serialize_xmp(&data);
        assert!(xml.contains("a&quot;b"));
    }

    #[test]
    fn serialize_xmp_escapes_list_items_without_converting_quotes() {
        let mut data = XmpData::default();
        data.list_items.insert(
            "dc".to_string(),
            ("subject".to_string(), vec!["a\"b".to_string()]),
        );
        let xml = serialize_xmp(&data);
        // list items: only &/</> are escaped, not quotes
        assert!(xml.contains("<rdf:li>a\"b</rdf:li>"));
    }

    #[test]
    fn parse_xmp_round_trips_attrs_and_list() {
        let mut data = XmpData::default();
        data.attrs.insert("wdtag".to_string(), {
            let mut m = BTreeMap::new();
            m.insert("model".to_string(), "wd-swinv2".to_string());
            m
        });
        data.list_items.insert(
            "dc".to_string(),
            ("subject".to_string(), vec!["blue_eyes".to_string()]),
        );
        let xml = serialize_xmp(&data);
        let parsed = parse_xmp(&xml);
        assert_eq!(
            parsed.attrs.get("wdtag").unwrap().get("model").unwrap(),
            "wd-swinv2"
        );
        assert_eq!(
            parsed.list_items.get("dc").unwrap().1,
            vec!["blue_eyes".to_string()]
        );
    }

    #[test]
    fn parse_xmp_returns_empty_for_malformed_input() {
        let data = parse_xmp("not xml at all <<<");
        assert!(data.attrs.is_empty());
        assert!(data.list_items.is_empty());
    }

    #[test]
    fn parse_xmp_returns_empty_for_empty_input() {
        let data = parse_xmp("");
        assert!(data.attrs.is_empty());
    }

    #[test]
    fn parse_xmp_preserves_unknown_namespace_via_autoassigned_prefix() {
        let foreign_xml = format!(
            "{}<x:xmpmeta xmlns:x=\"adobe:ns:meta/\"><rdf:RDF xmlns:rdf=\"{}\"><rdf:Description xmlns:sweep=\"http://example.invalid/sweep/\" sweep:tag=\"v\"></rdf:Description></rdf:RDF></x:xmpmeta>{}",
            XPACKET_HEADER, RDF_NS, XPACKET_TRAILER
        );
        let data = parse_xmp(&foreign_xml);
        // 未知namespaceは既知prefixと衝突しないよう保持される(自動割当か既存宣言のいずれか)
        assert_eq!(
            data.attrs
                .values()
                .flat_map(|m| m.values())
                .next()
                .map(String::as_str),
            Some("v")
        );
    }
}
