"""Dequantize uint8 Hailo output to float32 vectors.

Hailo-10H outputs uint8 quantized values. This module converts them
to float32 using the quantization parameters from the HEF model.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)


def dequantize(
    quantized: np.ndarray,
    scale: float = 1.0,
    zero_point: float = 0.0,
) -> np.ndarray:
    """Convert uint8 quantized output to float32.

    Formula: float_val = (uint8_val - zero_point) * scale

    Args:
        quantized: uint8 array from Hailo inference
        scale: quantization scale factor
        zero_point: quantization zero point

    Returns:
        float32 array of same shape
    """
    return (quantized.astype(np.float32) - zero_point) * scale


def normalize_vector(vec: np.ndarray) -> np.ndarray:
    """L2-normalize a vector for cosine similarity."""
    norm = np.linalg.norm(vec)
    if norm < 1e-12:
        return vec
    return vec / norm


def extract_quant_params(infer_model) -> dict:
    """Extract quantization parameters from a configured InferModel.

    Attempts to read scale/zero_point from the output layer info.
    Falls back to defaults if not available.
    """
    try:
        out_info = infer_model.outputs[0]
        qp = out_info.quant_infos[0]
        return {
            "scale": float(qp.qp_scale),
            "zero_point": float(qp.qp_zp),
        }
    except (AttributeError, IndexError, TypeError) as exc:
        logger.warning("Could not extract quant params: %s. Using defaults.", exc)
        return {"scale": 1.0, "zero_point": 0.0}
