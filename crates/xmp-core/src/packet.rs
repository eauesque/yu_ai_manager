//! XMP packet parse/serialize at namespace granularity, ported from
//! Python core/tools/xmp/packet.py. See spec §3.1.

use std::collections::BTreeMap;

use quick_xml::events::{BytesStart, Event};
use quick_xml::Reader;

use crate::registry::{prefix_for, RDF_NS};

const XPACKET_HEADER: &str = "<?xpacket begin=\"\u{FEFF}\" id=\"W5M0MpCehiHzreSzNTczkc9d\"?>\n";
const XPACKET_TRAILER: &str = "\n<?xpacket end=\"w\"?>";

#[derive(Debug, Default, Clone)]
pub struct XmpData {
    pub attrs: BTreeMap<String, BTreeMap<String, String>>,
    pub list_items: BTreeMap<String, Vec<String>>,
    pub list_element_name: BTreeMap<String, String>,
    pub namespace_uris: BTreeMap<String, String>,
}

impl XmpData {
    pub fn get_attrs(&self, prefix: &str) -> BTreeMap<String, String> {
        self.attrs.get(prefix).cloned().unwrap_or_default()
    }

    pub fn get_list(&self, prefix: &str) -> Vec<String> {
        self.list_items.get(prefix).cloned().unwrap_or_default()
    }

    fn resolve_prefix(&mut self, uri: &str) -> String {
        if let Some((prefix, _)) = self.namespace_uris.iter().find(|(_, u)| u.as_str() == uri) {
            return prefix.clone();
        }
        if let Some(known) = prefix_for(uri) {
            self.namespace_uris
                .insert(known.to_string(), uri.to_string());
            return known.to_string();
        }
        let mut n = 0u32;
        loop {
            let candidate = format!("ns{n}");
            if !self.namespace_uris.contains_key(&candidate)
                && candidate != "rdf"
                && candidate != "x"
            {
                self.namespace_uris
                    .insert(candidate.clone(), uri.to_string());
                return candidate;
            }
            n += 1;
        }
    }
}

fn strip_xpacket(xmp_xml: &str) -> String {
    let mut s = xmp_xml.trim();
    if s.starts_with("<?xpacket") {
        if let Some(i) = s.find("?>") {
            s = s[i + 2..].trim_start();
        }
    }
    if let Some(i) = s.rfind("<?xpacket") {
        s = &s[..i];
    }
    s.trim().to_string()
}

pub fn parse(xmp_xml: &str) -> XmpData {
    let mut data = XmpData::default();
    if xmp_xml.trim().is_empty() {
        return data;
    }

    let body = strip_xpacket(xmp_xml);
    let mut reader = Reader::from_str(&body);
    reader.config_mut().trim_text(true);

    let mut ns_stack: Vec<BTreeMap<String, String>> = vec![BTreeMap::new()];
    let mut state = ParseState::default();

    loop {
        match reader.read_event() {
            Ok(Event::Eof) => break,
            Ok(Event::Start(e)) => {
                let (name, local_ns, attr_pairs) = start_context(&e, &ns_stack);
                ns_stack.push(local_ns.clone());
                handle_start(&mut data, &name, &local_ns, &attr_pairs, &mut state);
            }
            Ok(Event::Empty(e)) => {
                let (name, local_ns, attr_pairs) = start_context(&e, &ns_stack);
                ns_stack.push(local_ns.clone());
                handle_start(&mut data, &name, &local_ns, &attr_pairs, &mut state);
                handle_end(&mut data, &name, &mut state);
                ns_stack.pop();
            }
            Ok(Event::Text(t)) => {
                if state.in_li {
                    state.li_text.push_str(&t.xml_content().unwrap_or_default());
                }
            }
            Ok(Event::End(e)) => {
                let name = String::from_utf8_lossy(e.name().as_ref()).into_owned();
                handle_end(&mut data, &name, &mut state);
                if ns_stack.len() > 1 {
                    ns_stack.pop();
                }
            }
            Ok(_) => {}
            Err(_) => return XmpData::default(),
        }
    }

    data
}

#[derive(Default)]
struct ParseState {
    in_description: bool,
    current_list_prefix: Option<String>,
    current_list_local: Option<String>,
    current_list_items: Vec<String>,
    in_li: bool,
    li_text: String,
}

fn start_context(
    e: &BytesStart<'_>,
    ns_stack: &[BTreeMap<String, String>],
) -> (String, BTreeMap<String, String>, Vec<(String, String)>) {
    let name = String::from_utf8_lossy(e.name().as_ref()).into_owned();
    let mut local_ns = ns_stack.last().cloned().unwrap_or_default();
    let mut attr_pairs = Vec::new();

    for attr in e.attributes().flatten() {
        let key = String::from_utf8_lossy(attr.key.as_ref()).into_owned();
        let value = attr.unescape_value().unwrap_or_default().into_owned();
        if let Some(prefix) = key.strip_prefix("xmlns:") {
            local_ns.insert(prefix.to_string(), value);
        } else if key == "xmlns" {
            local_ns.insert(String::new(), value);
        } else {
            attr_pairs.push((key, value));
        }
    }

    (name, local_ns, attr_pairs)
}

fn handle_start(
    data: &mut XmpData,
    name: &str,
    local_ns: &BTreeMap<String, String>,
    attr_pairs: &[(String, String)],
    state: &mut ParseState,
) {
    let (tag_prefix, tag_local) = split_qname(name);
    if tag_local == "Description" && tag_prefix == "rdf" {
        state.in_description = true;
        for (key, value) in attr_pairs {
            let (a_prefix, a_local) = split_qname(key);
            if a_prefix.is_empty() || a_prefix == "rdf" {
                continue;
            }
            let Some(uri) = local_ns.get(a_prefix) else {
                continue;
            };
            let resolved = data.resolve_prefix(uri);
            data.attrs
                .entry(resolved)
                .or_default()
                .insert(a_local.to_string(), value.clone());
        }
    } else if state.in_description && tag_prefix != "rdf" && !tag_prefix.is_empty() {
        if let Some(uri) = local_ns.get(tag_prefix) {
            let resolved = data.resolve_prefix(uri);
            state.current_list_prefix = Some(resolved);
            state.current_list_local = Some(tag_local.to_string());
            state.current_list_items.clear();
        }
    } else if tag_local == "li" {
        state.in_li = true;
        state.li_text.clear();
    }
}

fn handle_end(data: &mut XmpData, name: &str, state: &mut ParseState) {
    let (_, local) = split_qname(name);
    if local == "li" {
        state.in_li = false;
        state
            .current_list_items
            .push(std::mem::take(&mut state.li_text));
    } else if Some(local.to_string()) == state.current_list_local
        && state.current_list_prefix.is_some()
    {
        let prefix = state.current_list_prefix.take().unwrap();
        let elem_name = state.current_list_local.take().unwrap();
        data.list_items.insert(
            prefix.clone(),
            std::mem::take(&mut state.current_list_items),
        );
        data.list_element_name.insert(prefix, elem_name);
    } else if local == "Description" {
        state.in_description = false;
    }
}

fn split_qname(name: &str) -> (&str, &str) {
    match name.split_once(':') {
        Some((prefix, local)) => (prefix, local),
        None => ("", name),
    }
}

fn attr_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

fn text_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

pub fn serialize(data: &XmpData) -> String {
    let used_prefixes: std::collections::BTreeSet<&String> =
        data.attrs.keys().chain(data.list_items.keys()).collect();

    let mut namespace_decls = Vec::new();
    for prefix in &used_prefixes {
        let uri = data
            .namespace_uris
            .get(prefix.as_str())
            .cloned()
            .or_else(|| crate::registry::uri_for(prefix).map(str::to_string));
        if let Some(uri) = uri {
            namespace_decls.push(format!("xmlns:{prefix}=\"{}\"", attr_escape(&uri)));
        }
    }

    let mut attr_lines = Vec::new();
    for (prefix, names) in &data.attrs {
        for (name, value) in names {
            attr_lines.push(format!("{prefix}:{name}=\"{}\"", attr_escape(value)));
        }
    }

    let desc_inner = namespace_decls
        .iter()
        .chain(attr_lines.iter())
        .cloned()
        .collect::<Vec<_>>()
        .join(" ");
    let desc_open = if desc_inner.is_empty() {
        "<rdf:Description>".to_string()
    } else {
        format!("<rdf:Description\n      {desc_inner}>")
    };

    let mut list_blocks = Vec::new();
    for (prefix, items) in &data.list_items {
        let elem_name = data
            .list_element_name
            .get(prefix)
            .cloned()
            .unwrap_or_else(|| "items".to_string());
        let bag_lines = items
            .iter()
            .map(|item| format!("          <rdf:li>{}</rdf:li>", text_escape(item)))
            .collect::<Vec<_>>()
            .join("\n");
        list_blocks.push(format!(
            "      <{prefix}:{elem_name}>\n        <rdf:Bag>\n{bag_lines}\n        </rdf:Bag>\n      </{prefix}:{elem_name}>"
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    fn sample_xmp() -> &'static str {
        r#"<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/">
  <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
    <rdf:Description
      xmlns:wdtag="http://ns.yu-ai-manager/wdtag/1.0/"
      wdtag:model="wd_swinv2_v3"
      wdtag:tag_count="2">
      <dc:subject xmlns:dc="http://purl.org/dc/elements/1.1/">
        <rdf:Bag>
          <rdf:li>1girl</rdf:li>
          <rdf:li>solo</rdf:li>
        </rdf:Bag>
      </dc:subject>
    </rdf:Description>
  </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"#
    }

    #[test]
    fn parse_extracts_attrs_and_list_items() {
        let data = parse(sample_xmp());
        assert_eq!(
            data.attrs.get("wdtag").and_then(|m| m.get("model")),
            Some(&"wd_swinv2_v3".to_string())
        );
        assert_eq!(
            data.attrs.get("wdtag").and_then(|m| m.get("tag_count")),
            Some(&"2".to_string())
        );
        assert_eq!(
            data.list_items.get("dc"),
            Some(&vec!["1girl".to_string(), "solo".to_string()])
        );
        assert_eq!(
            data.list_element_name.get("dc"),
            Some(&"subject".to_string())
        );
    }

    #[test]
    fn parse_empty_string_returns_empty_data() {
        let data = parse("");
        assert!(data.attrs.is_empty());
        assert!(data.list_items.is_empty());
    }

    #[test]
    fn parse_unknown_namespace_gets_synthetic_prefix() {
        let xml = r#"<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description xmlns:foo="http://example.com/foo/" foo:bar="baz"></rdf:Description></rdf:RDF></x:xmpmeta>"#;
        let data = parse(xml);
        let (synthetic_prefix, attrs) = data
            .attrs
            .iter()
            .find(|(_, m)| m.contains_key("bar"))
            .expect("unknown namespace attrs should be preserved under a synthetic prefix");
        assert_eq!(attrs.get("bar"), Some(&"baz".to_string()));
        assert_eq!(
            data.namespace_uris.get(synthetic_prefix),
            Some(&"http://example.com/foo/".to_string())
        );
    }

    #[test]
    fn parse_self_closing_description_returns_empty_data() {
        let xml = r#"<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description xmlns:wdtag="http://ns.yu-ai-manager/wdtag/1.0/"/></rdf:RDF></x:xmpmeta>"#;
        let data = parse(xml);
        assert!(data.attrs.is_empty());
        assert!(data.list_items.is_empty());
    }

    #[test]
    fn serialize_is_deterministic_across_multiple_calls() {
        let mut data = XmpData::default();
        data.attrs.insert(
            "wdtag".to_string(),
            BTreeMap::from([
                ("model".to_string(), "m".to_string()),
                ("tag_count".to_string(), "1".to_string()),
            ]),
        );
        data.namespace_uris.insert(
            "wdtag".to_string(),
            "http://ns.yu-ai-manager/wdtag/1.0/".to_string(),
        );
        let a = serialize(&data);
        let b = serialize(&data);
        assert_eq!(a, b);
        assert!(a.contains("wdtag:model=\"m\""));
        assert!(a.contains("wdtag:tag_count=\"1\""));
    }

    #[test]
    fn serialize_round_trips_through_parse() {
        let mut data = XmpData::default();
        data.attrs.insert(
            "wdtag".to_string(),
            BTreeMap::from([("model".to_string(), "m".to_string())]),
        );
        data.namespace_uris.insert(
            "wdtag".to_string(),
            "http://ns.yu-ai-manager/wdtag/1.0/".to_string(),
        );
        data.list_items
            .insert("dc".to_string(), vec!["1girl".to_string()]);
        data.list_element_name
            .insert("dc".to_string(), "subject".to_string());
        data.namespace_uris.insert(
            "dc".to_string(),
            "http://purl.org/dc/elements/1.1/".to_string(),
        );

        let xml = serialize(&data);
        let reparsed = parse(&xml);
        assert_eq!(
            reparsed.get_attrs("wdtag").get("model"),
            Some(&"m".to_string())
        );
        assert_eq!(reparsed.get_list("dc"), vec!["1girl".to_string()]);
    }
}
