"""Standalone YOLO postprocessing for the deploy server.

Dequantize Hailo uint8 outputs, decode multi-scale YOLO boxes,
apply per-class NMS, and return detection dicts.

No imports from the main YU AI Manager project — fully self-contained.
"""


import numpy as np

# -- COCO 80-class labels ---------------------------------------------------

COCO_LABELS = [
    "person", "bicycle", "car", "motorcycle", "airplane",
    "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird",
    "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat",
    "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
    "wine glass", "cup", "fork", "knife", "spoon",
    "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut",
    "cake", "chair", "couch", "potted plant", "bed",
    "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven",
    "toaster", "sink", "refrigerator", "book", "clock",
    "vase", "scissors", "teddy bear", "hair drier", "toothbrush",
]


def _dequantize(data: np.ndarray, scale: float, zero_point: float) -> np.ndarray:
    """uint8 -> float32 dequantization."""
    return (data.astype(np.float32) - zero_point) * scale


def _sigmoid(x: np.ndarray) -> np.ndarray:
    """Numerically stable sigmoid."""
    return np.where(
        x >= 0,
        1.0 / (1.0 + np.exp(-x)),
        np.exp(x) / (1.0 + np.exp(x)),
    )


def _xywh_to_xyxy(boxes: np.ndarray) -> np.ndarray:
    """Convert (cx, cy, w, h) to (x1, y1, x2, y2)."""
    out = np.empty_like(boxes)
    out[:, 0] = boxes[:, 0] - boxes[:, 2] / 2
    out[:, 1] = boxes[:, 1] - boxes[:, 3] / 2
    out[:, 2] = boxes[:, 0] + boxes[:, 2] / 2
    out[:, 3] = boxes[:, 1] + boxes[:, 3] / 2
    return out


def _nms_numpy(
    boxes: np.ndarray,
    scores: np.ndarray,
    iou_threshold: float,
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


def _decode_hailo_yolo_outputs(
    buffers: list[np.ndarray],
    quant_params: list[dict],
    num_classes: int = 80,
    input_size: int = 640,
) -> tuple:
    """Decode Hailo YOLO multi-scale uint8 outputs.

    Returns (boxes_xyxy, scores, class_ids) in pixel coords.
    """
    all_boxes = []
    all_scores = []
    all_class_ids = []

    for buf, qp in zip(buffers, quant_params, strict=False):
        data = _dequantize(buf.flatten(), qp["scale"], qp["zero_point"])
        shape = qp["shape"]

        if len(shape) == 4:
            _, gh, gw, channels = shape
            data = data.reshape(gh, gw, channels)
        elif len(shape) == 3:
            gh, gw, channels = shape
            data = data.reshape(gh, gw, channels)
        else:
            continue

        # Need at least 4 (box) + num_classes channels
        if channels < 4 + num_classes:
            continue

        box_data = data[:, :, :4]
        cls_data = data[:, :, 4:4 + num_classes]

        stride = input_size / gh

        grid_y, grid_x = np.meshgrid(
            np.arange(gh, dtype=np.float32),
            np.arange(gw, dtype=np.float32),
            indexing="ij",
        )

        cls_scores = _sigmoid(cls_data)

        cx = (_sigmoid(box_data[:, :, 0]) + grid_x) * stride
        cy = (_sigmoid(box_data[:, :, 1]) + grid_y) * stride
        w = np.exp(box_data[:, :, 2]) * stride
        h = np.exp(box_data[:, :, 3]) * stride

        cx = cx.flatten()
        cy = cy.flatten()
        w = w.flatten()
        h = h.flatten()
        cls_scores = cls_scores.reshape(-1, num_classes)

        best_cls = cls_scores.argmax(axis=1)
        best_score = cls_scores[np.arange(len(best_cls)), best_cls]

        boxes = np.stack([cx, cy, w, h], axis=1)
        boxes_xyxy = _xywh_to_xyxy(boxes)

        all_boxes.append(boxes_xyxy)
        all_scores.append(best_score)
        all_class_ids.append(best_cls)

    if not all_boxes:
        return np.empty((0, 4)), np.empty(0), np.empty(0, dtype=np.int32)

    return (
        np.concatenate(all_boxes),
        np.concatenate(all_scores),
        np.concatenate(all_class_ids).astype(np.int32),
    )


def postprocess_yolo_outputs(
    buffers: list[np.ndarray],
    quant_params: list[dict],
    conf_threshold: float = 0.25,
    iou_threshold: float = 0.45,
    num_classes: int = 80,
    input_size: int = 640,
    scale_info: dict | None = None,
) -> list[dict]:
    """Full YOLO post-processing: dequantize → decode → NMS → format.

    Returns list of {"class_id", "class_name", "confidence", "bbox"}.
    bbox is normalised [0,1] xyxy.
    """
    boxes, scores, class_ids = _decode_hailo_yolo_outputs(
        buffers, quant_params, num_classes, input_size,
    )

    if len(boxes) == 0:
        return []

    mask = scores >= conf_threshold
    boxes = boxes[mask]
    scores = scores[mask]
    class_ids = class_ids[mask]

    if len(boxes) == 0:
        return []

    # Per-class NMS
    keep_indices: list[int] = []
    for cls_id in np.unique(class_ids):
        cls_mask = class_ids == cls_id
        cls_boxes = boxes[cls_mask]
        cls_scores = scores[cls_mask]
        cls_indices = np.where(cls_mask)[0]
        kept = _nms_numpy(cls_boxes, cls_scores, iou_threshold)
        keep_indices.extend(cls_indices[kept].tolist())

    boxes = boxes[keep_indices]
    scores = scores[keep_indices]
    class_ids = class_ids[keep_indices]

    # Map coordinates to normalised [0,1]
    if scale_info:
        pad_x = scale_info["pad_x"]
        pad_y = scale_info["pad_y"]
        scale = scale_info["scale"]
        orig_w = scale_info["orig_w"]
        orig_h = scale_info["orig_h"]
        boxes[:, 0] = (boxes[:, 0] - pad_x) / scale / orig_w
        boxes[:, 1] = (boxes[:, 1] - pad_y) / scale / orig_h
        boxes[:, 2] = (boxes[:, 2] - pad_x) / scale / orig_w
        boxes[:, 3] = (boxes[:, 3] - pad_y) / scale / orig_h
    else:
        boxes /= input_size

    boxes = np.clip(boxes, 0.0, 1.0)

    detections = []
    for i in range(len(boxes)):
        cid = int(class_ids[i])
        label = COCO_LABELS[cid] if 0 <= cid < len(COCO_LABELS) else "unknown"
        detections.append({
            "class_id": cid,
            "class_name": label,
            "confidence": round(float(scores[i]), 4),
            "bbox": [round(float(v), 4) for v in boxes[i]],
        })

    detections.sort(key=lambda d: d["confidence"], reverse=True)
    return detections
