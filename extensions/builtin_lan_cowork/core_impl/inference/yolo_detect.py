"""YOLO detection paths for ONNX and Hailo."""

from __future__ import annotations

import logging

import numpy as np

from .yolo_models import COCO_NAMES

logger = logging.getLogger(__name__)


def yolo_detect_single(engine: dict, image_rgb: np.ndarray, scale_info: dict) -> list[dict]:
    """Run YOLO detection on a single preprocessed image."""
    if engine["type"] == "onnx":
        return _yolo_detect_onnx(engine, image_rgb, scale_info, conf_threshold=0.25)
    return _yolo_detect_hailo(engine, image_rgb, scale_info)


def _yolo_detect_onnx(
    engine: dict,
    image_rgb: np.ndarray,
    scale_info: dict,
    conf_threshold: float = 0.25,
) -> list[dict]:
    session = engine["session"]
    blob = image_rgb.astype(np.float32) / 255.0
    blob = blob.transpose(2, 0, 1)[np.newaxis]
    input_name = session.get_inputs()[0].name
    outputs = session.run(None, {input_name: blob})

    raw = outputs[0]
    if raw.ndim == 3:
        raw = raw[0]
    if raw.shape[0] < raw.shape[1]:
        raw = raw.T

    boxes_xywh = raw[:, :4]
    class_scores = raw[:, 4:]
    class_ids = class_scores.argmax(axis=1)
    max_scores = class_scores[np.arange(len(class_ids)), class_ids]

    mask = max_scores >= conf_threshold
    boxes_xywh = boxes_xywh[mask]
    max_scores = max_scores[mask]
    class_ids = class_ids[mask]
    if len(boxes_xywh) == 0:
        return []

    boxes_xyxy = np.empty_like(boxes_xywh)
    boxes_xyxy[:, 0] = boxes_xywh[:, 0] - boxes_xywh[:, 2] / 2
    boxes_xyxy[:, 1] = boxes_xywh[:, 1] - boxes_xywh[:, 3] / 2
    boxes_xyxy[:, 2] = boxes_xywh[:, 0] + boxes_xywh[:, 2] / 2
    boxes_xyxy[:, 3] = boxes_xywh[:, 1] + boxes_xywh[:, 3] / 2

    keep: list[int] = []
    for class_id in np.unique(class_ids):
        class_mask = class_ids == class_id
        c_boxes = boxes_xyxy[class_mask]
        c_scores = max_scores[class_mask]
        c_indices = np.where(class_mask)[0]
        order = c_scores.argsort()[::-1]
        while len(order) > 0:
            top = order[0]
            keep.append(int(c_indices[top]))
            if len(order) == 1:
                break
            xx1 = np.maximum(c_boxes[top, 0], c_boxes[order[1:], 0])
            yy1 = np.maximum(c_boxes[top, 1], c_boxes[order[1:], 1])
            xx2 = np.minimum(c_boxes[top, 2], c_boxes[order[1:], 2])
            yy2 = np.minimum(c_boxes[top, 3], c_boxes[order[1:], 3])
            inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
            area_top = (c_boxes[top, 2] - c_boxes[top, 0]) * (c_boxes[top, 3] - c_boxes[top, 1])
            area_other = (c_boxes[order[1:], 2] - c_boxes[order[1:], 0]) * (
                c_boxes[order[1:], 3] - c_boxes[order[1:], 1]
            )
            iou = inter / (area_top + area_other - inter + 1e-6)
            order = order[1:][iou <= 0.45]

    boxes_xyxy = boxes_xyxy[keep]
    max_scores = max_scores[keep]
    class_ids = class_ids[keep]

    if scale_info:
        pad_x = scale_info["pad_x"]
        pad_y = scale_info["pad_y"]
        sc = scale_info["scale"]
        orig_w = scale_info["orig_w"]
        orig_h = scale_info["orig_h"]
        boxes_xyxy[:, 0] = (boxes_xyxy[:, 0] - pad_x) / sc / orig_w
        boxes_xyxy[:, 1] = (boxes_xyxy[:, 1] - pad_y) / sc / orig_h
        boxes_xyxy[:, 2] = (boxes_xyxy[:, 2] - pad_x) / sc / orig_w
        boxes_xyxy[:, 3] = (boxes_xyxy[:, 3] - pad_y) / sc / orig_h
        boxes_xyxy = np.clip(boxes_xyxy, 0.0, 1.0)
    else:
        boxes_xyxy = np.clip(boxes_xyxy / 640.0, 0.0, 1.0)

    detections: list[dict] = []
    for idx, bbox in enumerate(boxes_xyxy):
        cid = int(class_ids[idx])
        detections.append(
            {
                "class_id": cid,
                "class_name": COCO_NAMES[cid] if cid < len(COCO_NAMES) else f"class_{cid}",
                "confidence": round(float(max_scores[idx]), 4),
                "bbox": [round(float(v), 4) for v in bbox],
            }
        )
    detections.sort(key=lambda d: d["confidence"], reverse=True)
    return detections


def _yolo_detect_hailo(engine: dict, image_rgb: np.ndarray, scale_info: dict) -> list[dict]:
    from core.hailo_device_core.device_manager import acquire_device

    infer_model, configured, _ = acquire_device("lan-yolo", engine["hef_path"])
    bindings = configured.create_bindings()
    bindings.input().set_buffer(image_rgb)

    output_buffers: list[np.ndarray] = []
    for out in infer_model.outputs:
        dtype = np.float32 if engine["has_nms"] else np.uint8
        buf = np.empty(tuple(out.shape), dtype=dtype)
        bindings.output(out.name).set_buffer(buf)
        output_buffers.append(buf)

    configured.run([bindings], timeout=10000)

    if engine["has_nms"]:
        return _parse_nms_output(output_buffers, scale_info, engine["input_size"])

    logger.warning("Hailo YOLO without NMS is not fully supported in this port")
    return []


def _parse_nms_output(output_buffers: list[np.ndarray], scale_info: dict, input_size: int) -> list[dict]:
    detections: list[dict] = []

    for buf in output_buffers:
        if buf.size % 6 == 0:
            data = buf.flatten().reshape(-1, 6)
        elif buf.ndim >= 2 and buf.shape[-1] >= 5:
            data = buf.reshape(-1, buf.shape[-1])
        else:
            continue

        for row in data:
            if len(row) < 6:
                continue
            score = float(row[4])
            if score < 0.25:
                continue
            class_id = int(row[5])
            y1, x1, y2, x2 = float(row[0]), float(row[1]), float(row[2]), float(row[3])

            if scale_info:
                pad_x = scale_info["pad_x"]
                pad_y = scale_info["pad_y"]
                sc = scale_info["scale"]
                orig_w = scale_info["orig_w"]
                orig_h = scale_info["orig_h"]
                x1 = max(0.0, min(1.0, (x1 - pad_x) / sc / orig_w))
                y1 = max(0.0, min(1.0, (y1 - pad_y) / sc / orig_h))
                x2 = max(0.0, min(1.0, (x2 - pad_x) / sc / orig_w))
                y2 = max(0.0, min(1.0, (y2 - pad_y) / sc / orig_h))
            else:
                x1 = x1 / input_size
                y1 = y1 / input_size
                x2 = x2 / input_size
                y2 = y2 / input_size

            label = COCO_NAMES[class_id] if 0 <= class_id < len(COCO_NAMES) else "unknown"
            detections.append(
                {
                    "class_id": class_id,
                    "class_name": label,
                    "confidence": round(score, 4),
                    "bbox": [round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4)],
                }
            )

    detections.sort(key=lambda d: d["confidence"], reverse=True)
    return detections
