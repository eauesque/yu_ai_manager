"""Decode helpers for Hailo YOLO outputs."""

import logging

import numpy as np

from .yolo_postprocess_math import (
    dequantize as _dequantize,
)
from .yolo_postprocess_math import (
    sigmoid as _sigmoid,
)
from .yolo_postprocess_math import (
    xywh_to_xyxy as _xywh_to_xyxy,
)

logger = logging.getLogger(__name__)


def decode_hailo_yolo_outputs(
    buffers: list[np.ndarray],
    quant_params: list[dict],
    num_classes: int = 80,
    input_size: int = 640,
) -> tuple:
    """Decode Hailo YOLO multi-scale outputs into boxes, scores, classes."""
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
        elif len(shape) in {1, 2}:
            logger.debug("Skipping unsupported output shape %s", shape)
            continue
        else:
            logger.debug("Skipping unexpected shape %s", shape)
            continue

        if channels < 4 + num_classes:
            logger.debug(
                "Tensor %s has %d channels (need %d+), treating as partial",
                qp.get("name", "?"),
                channels,
                4 + num_classes,
            )
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

        cls_scores = cls_scores.reshape(-1, num_classes)
        best_cls = cls_scores.argmax(axis=1)
        best_score = cls_scores[np.arange(len(best_cls)), best_cls]

        boxes = np.stack([cx.flatten(), cy.flatten(), w.flatten(), h.flatten()], axis=1)
        all_boxes.append(_xywh_to_xyxy(boxes))
        all_scores.append(best_score)
        all_class_ids.append(best_cls)

    if not all_boxes:
        return np.empty((0, 4)), np.empty(0), np.empty(0, dtype=np.int32)

    return (
        np.concatenate(all_boxes),
        np.concatenate(all_scores),
        np.concatenate(all_class_ids).astype(np.int32),
    )


def parse_nms_output(buf: np.ndarray, input_size: int = 640) -> tuple:
    """Parse HEF-embedded NMS postprocess output."""
    del input_size
    data = buf.reshape(-1, 6) if buf.ndim != 2 else buf
    data = data[data[:, 4] > 0]
    if len(data) == 0:
        return np.empty((0, 4)), np.empty(0), np.empty(0, dtype=np.int32)
    boxes = np.stack([data[:, 1], data[:, 0], data[:, 3], data[:, 2]], axis=1)
    scores = data[:, 4]
    class_ids = data[:, 5].astype(np.int32)
    return boxes, scores, class_ids


def is_nms_output(quant_params: list[dict]) -> bool:
    """Check if the model output is from HEF-embedded NMS."""
    if len(quant_params) != 1:
        return False
    qp = quant_params[0]
    return qp.get("dtype") == "float32" and "nms" in qp.get("name", "").lower()
