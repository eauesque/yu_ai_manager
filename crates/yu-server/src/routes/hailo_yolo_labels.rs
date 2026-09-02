//! App-specific YOLO label helpers.

pub(crate) use infer_core::yolo_labels::{get_label, COCO_LABELS};

pub(crate) fn annotation_source(model_name: &str) -> String {
    format!("hailo:{model_name}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn get_label_returns_person_for_class_0() {
        assert_eq!(get_label(0), "person");
    }

    #[test]
    fn get_label_returns_unknown_for_out_of_range() {
        assert_eq!(get_label(999), "unknown");
    }

    #[test]
    fn annotation_source_formats_hailo_prefix() {
        assert_eq!(annotation_source("yolov8n"), "hailo:yolov8n");
    }

    #[test]
    fn coco_labels_has_exactly_80_entries() {
        assert_eq!(COCO_LABELS.len(), 80);
    }
}
