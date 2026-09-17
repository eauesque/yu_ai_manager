"""Public YOLO post-processing pipeline."""


import numpy as np

from .yolo_postprocess_decode import (
    decode_hailo_yolo_outputs as _decode_hailo_yolo_outputs,
)
from .yolo_postprocess_decode import (
    is_nms_output as _is_nms_output,
)
from .yolo_postprocess_decode import (
    parse_nms_output as _parse_nms_output,
)
from .yolo_postprocess_math import nms_numpy as _nms_numpy


def postprocess_yolo_outputs(
    buffers: list[np.ndarray],
    quant_params: list[dict],
    conf_threshold: float = 0.25,
    iou_threshold: float = 0.45,
    num_classes: int = 80,
    input_size: int = 640,
    scale_info: dict | None = None,
) -> list[dict]:
    """Full YOLO post-processing pipeline."""
    from .yolo_labels import get_label

    if _is_nms_output(quant_params):
        boxes, scores, class_ids = _parse_nms_output(buffers[0], input_size)
    else:
        boxes, scores, class_ids = _decode_hailo_yolo_outputs(buffers, quant_params, num_classes, input_size)

    if len(boxes) == 0:
        return []

    mask = scores >= conf_threshold
    boxes = boxes[mask]
    scores = scores[mask]
    class_ids = class_ids[mask]

    if len(boxes) == 0:
        return []

    if not _is_nms_output(quant_params):
        keep_indices: list[int] = []
        unique_classes = np.unique(class_ids)
        for cls_id in unique_classes:
            cls_mask = class_ids == cls_id
            cls_boxes = boxes[cls_mask]
            cls_scores = scores[cls_mask]
            cls_indices = np.where(cls_mask)[0]

            kept = _nms_numpy(cls_boxes, cls_scores, iou_threshold)
            keep_indices.extend(cls_indices[kept].tolist())

        boxes = boxes[keep_indices]
        scores = scores[keep_indices]
        class_ids = class_ids[keep_indices]

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
        detections.append({
            "class_id": int(class_ids[i]),
            "class_name": get_label(int(class_ids[i])),
            "confidence": round(float(scores[i]), 4),
            "bbox": [round(float(v), 4) for v in boxes[i]],
        })

    detections.sort(key=lambda d: d["confidence"], reverse=True)
    return detections


__all__ = ["postprocess_yolo_outputs"]
