"""Common YOLO postprocessing utilities shared by all backends.

Provides generic NMS, coordinate conversion, and detection building
that are independent of any specific inference runtime.
"""


import numpy as np

from ..yolo_labels import get_label


def sigmoid(x: np.ndarray) -> np.ndarray:
    """Numerically stable sigmoid."""
    return np.where(
        x >= 0,
        1.0 / (1.0 + np.exp(-x)),
        np.exp(x) / (1.0 + np.exp(x)),
    )


def xywh_to_xyxy(boxes: np.ndarray) -> np.ndarray:
    """Convert (cx, cy, w, h) to (x1, y1, x2, y2)."""
    out = np.empty_like(boxes)
    out[:, 0] = boxes[:, 0] - boxes[:, 2] / 2  # x1
    out[:, 1] = boxes[:, 1] - boxes[:, 3] / 2  # y1
    out[:, 2] = boxes[:, 0] + boxes[:, 2] / 2  # x2
    out[:, 3] = boxes[:, 1] + boxes[:, 3] / 2  # y2
    return out


def nms_numpy(
    boxes: np.ndarray,
    scores: np.ndarray,
    iou_threshold: float = 0.45,
) -> list[int]:
    """Pure-numpy NMS. Returns indices to keep."""
    if len(boxes) == 0:
        return []

    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)

    order = scores.argsort()[::-1]
    keep: list[int] = []

    while len(order) > 0:
        i = order[0]
        keep.append(int(i))

        if len(order) == 1:
            break

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)

        mask = iou <= iou_threshold
        order = order[1:][mask]

    return keep


def scale_boxes_to_original(
    boxes: np.ndarray,
    scale_info: dict,
) -> np.ndarray:
    """Convert pixel boxes in letterboxed image to normalised [0,1] coords.

    Args:
        boxes: (N, 4) xyxy boxes in letterboxed pixel space.
        scale_info: dict with keys orig_w, orig_h, scale, pad_x, pad_y,
                    target_size.

    Returns:
        (N, 4) xyxy boxes normalised to [0, 1] relative to original image.
    """
    if len(boxes) == 0:
        return boxes.copy()

    out = boxes.copy().astype(np.float64)
    pad_x = scale_info["pad_x"]
    pad_y = scale_info["pad_y"]
    scale = scale_info["scale"]
    orig_w = scale_info["orig_w"]
    orig_h = scale_info["orig_h"]

    out[:, 0] = (out[:, 0] - pad_x) / scale / orig_w
    out[:, 1] = (out[:, 1] - pad_y) / scale / orig_h
    out[:, 2] = (out[:, 2] - pad_x) / scale / orig_w
    out[:, 3] = (out[:, 3] - pad_y) / scale / orig_h

    return np.clip(out, 0.0, 1.0)


def build_detections(
    boxes: np.ndarray,
    scores: np.ndarray,
    conf_threshold: float,
    iou_threshold: float,
    scale_info: dict | None = None,
    num_classes: int = 80,
) -> list[dict]:
    """Standard postprocess: filter by confidence, per-class NMS, format output.

    Args:
        boxes: (N, 4) xywh boxes in pixel coords (letterboxed).
        scores: (N, num_classes) class scores after sigmoid. Only 2D supported.
        conf_threshold: Minimum confidence to keep.
        iou_threshold: IoU threshold for NMS.
        scale_info: Optional letterbox metadata for coordinate back-mapping.
        num_classes: Number of classes (default 80).

    Returns:
        List of dicts with class_id, class_name, confidence, bbox.
    """
    if scores.ndim != 2:
        return []

    if len(boxes) == 0:
        return []

    # Best class per detection
    class_ids = scores.argmax(axis=1)
    max_scores = scores[np.arange(len(class_ids)), class_ids]

    # Confidence filter
    mask = max_scores >= conf_threshold
    boxes = boxes[mask]
    max_scores = max_scores[mask]
    class_ids = class_ids[mask]

    if len(boxes) == 0:
        return []

    # Convert to xyxy
    boxes_xyxy = xywh_to_xyxy(boxes)

    # Per-class NMS
    keep_indices: list[int] = []
    for cls_id in np.unique(class_ids):
        cls_mask = class_ids == cls_id
        cls_boxes = boxes_xyxy[cls_mask]
        cls_scores = max_scores[cls_mask]
        cls_indices = np.where(cls_mask)[0]

        kept = nms_numpy(cls_boxes, cls_scores, iou_threshold)
        keep_indices.extend(cls_indices[kept].tolist())

    boxes_xyxy = boxes_xyxy[keep_indices]
    max_scores = max_scores[keep_indices]
    class_ids = class_ids[keep_indices]

    # Scale to original image coordinates
    if scale_info:
        boxes_xyxy = scale_boxes_to_original(boxes_xyxy, scale_info)
    else:
        # Normalise to [0, 1] assuming boxes are in 640x640 pixel space
        boxes_xyxy = np.clip(boxes_xyxy / 640.0, 0.0, 1.0)

    # Build result list
    detections = []
    for i in range(len(boxes_xyxy)):
        detections.append({
            "class_id": int(class_ids[i]),
            "class_name": get_label(int(class_ids[i])),
            "confidence": round(float(max_scores[i]), 4),
            "bbox": [round(float(v), 4) for v in boxes_xyxy[i]],
        })

    detections.sort(key=lambda d: d["confidence"], reverse=True)
    return detections
