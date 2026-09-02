"""pHash computation helpers."""

import math
from pathlib import Path

# ------------------------------------------------------------------
# numpy fast-path (preferred): uses scipy.fft.dctn if available,
# otherwise falls back to a numpy-only Type-II DCT via matrix multiply.
# Pure-Python fallback is kept for environments without numpy.
# ------------------------------------------------------------------
_USE_NUMPY = False
_np = None  # type: ignore[assignment]
try:
    import numpy as _np  # type: ignore[no-redef]
    _USE_NUMPY = True
except ImportError:
    pass

_USE_SCIPY_DCT = False
_scipy_dctn = None
if _USE_NUMPY:
    try:
        from scipy.fft import dctn as _scipy_dctn  # type: ignore[import-untyped]
        _USE_SCIPY_DCT = True
    except ImportError:
        pass


def _dct2d_numpy(matrix):
    """2-D Type-II DCT via scipy (fast) or numpy matrix multiply."""
    arr = _np.asarray(matrix, dtype=_np.float64)
    if _USE_SCIPY_DCT:
        return _scipy_dctn(arr, type=2, norm="ortho")
    # Fallback: manual Type-II DCT via pre-computed cosine matrix.
    n = arr.shape[0]
    idx = _np.arange(n)
    cos_mat = _np.cos(_np.pi * _np.outer(idx, 2 * idx + 1) / (2 * n))
    return cos_mat @ arr @ cos_mat.T


def _dct2d_pure(block, size=32):
    """Pure-Python 2-D DCT fallback (no numpy)."""
    temp = [[0.0] * size for _ in range(size)]
    for y in range(size):
        for u in range(size):
            s = 0.0
            for x in range(size):
                s += block[y][x] * math.cos(math.pi * u * (2 * x + 1) / (2 * size))
            temp[y][u] = s

    result = [[0.0] * size for _ in range(size)]
    for u in range(size):
        for v in range(size):
            s = 0.0
            for y in range(size):
                s += temp[y][u] * math.cos(math.pi * v * (2 * y + 1) / (2 * size))
            result[v][u] = s
    return result


def compute_phash(image_path: Path, hash_size: int = 8):
    """Compute pHash using PIL + numpy (fast) or PIL only (fallback)."""
    try:
        from PIL import Image
    except Exception:
        return None

    try:
        with Image.open(image_path) as _raw_img:
            img = _raw_img.convert("L").resize((32, 32), Image.LANCZOS)

        if _USE_NUMPY:
            arr = _np.array(img, dtype=_np.float64)
            dct = _dct2d_numpy(arr)
            low_freq = dct[:hash_size, :hash_size].flatten()
            # Exclude DC component (index 0)
            low_freq = low_freq[1:]
            median = float(_np.median(low_freq))
        else:
            pixels = list(img.getdata())
            matrix = []
            for y in range(32):
                row = [float(pixels[y * 32 + x]) for x in range(32)]
                matrix.append(row)
            dct = _dct2d_pure(matrix)
            low_freq = []
            for y in range(hash_size):
                for x in range(hash_size):
                    if y == 0 and x == 0:
                        continue
                    low_freq.append(dct[y][x])
            sorted_freq = sorted(low_freq)
            median = sorted_freq[len(sorted_freq) // 2]

        hash_bits = 0
        for val in low_freq:
            v = float(val)
            hash_bits = (hash_bits << 1) | (1 if v > median else 0)

        return format(hash_bits, "016x")
    except Exception:
        return None
