"""Support utilities for the standalone Whisper Hailo pipeline."""

from __future__ import annotations

import contextlib
import json
import logging
import urllib.request
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
N_FFT = 400
HOP_LENGTH = 160
N_MELS = 80
CHUNK_SAMPLES = SAMPLE_RATE * 10
MEL_FRAMES = CHUNK_SAMPLES // HOP_LENGTH

SOT = 50258
EOT = 50257
TRANSCRIBE = 50359
NO_TIMESTAMPS = 50363

LANG_TOKENS = {
    "en": 50259, "zh": 50260, "de": 50261, "es": 50262,
    "ru": 50263, "ko": 50264, "fr": 50265, "ja": 50266,
    "pt": 50267, "tr": 50268, "pl": 50269, "ca": 50270,
    "nl": 50271, "ar": 50272, "sv": 50273, "it": 50274,
    "id": 50275, "hi": 50276, "fi": 50277, "vi": 50278,
}

_CACHE_DIR = Path.home() / ".cache" / "yu_ai_manager" / "whisper_onnx"
_HF_BASE = "https://huggingface.co/onnx-community/whisper-base/resolve/main/onnx"
_ENCODER_URL = f"{_HF_BASE}/encoder_model.onnx"
_DECODER_URL = f"{_HF_BASE}/decoder_model.onnx"
_VOCAB_URL = "https://huggingface.co/openai/whisper-base/resolve/main/vocab.json"
_USER_AGENT = "YuAiManager/1.0"

_mel_filters: np.ndarray | None = None
_vocab: dict[int, str] | None = None


def _mel_frequencies(n_mels: int, fmin: float, fmax: float) -> np.ndarray:
    def _hz_to_mel(freq):
        return 2595.0 * np.log10(1.0 + freq / 700.0)

    def _mel_to_hz(mel):
        return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

    mel_min = _hz_to_mel(fmin)
    mel_max = _hz_to_mel(fmax)
    return _mel_to_hz(np.linspace(mel_min, mel_max, n_mels + 2))


def _mel_filter_bank(sr: int, n_fft: int, n_mels: int) -> np.ndarray:
    fmax = sr / 2.0
    freqs = _mel_frequencies(n_mels, 0.0, fmax)
    fft_freqs = np.linspace(0, fmax, n_fft // 2 + 1)
    weights = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for i in range(n_mels):
        lo, mid, hi = freqs[i], freqs[i + 1], freqs[i + 2]
        for j, freq in enumerate(fft_freqs):
            if lo <= freq <= mid and mid > lo:
                weights[i, j] = (freq - lo) / (mid - lo)
            elif mid < freq <= hi and hi > mid:
                weights[i, j] = (hi - freq) / (hi - mid)
    weights *= (2.0 / (freqs[2:n_mels + 2] - freqs[:n_mels]))[:, np.newaxis]
    return weights


def compute_mel_spectrogram(audio: np.ndarray) -> np.ndarray:
    """Compute a fixed-size Whisper log-mel spectrogram."""
    global _mel_filters
    if _mel_filters is None:
        _mel_filters = _mel_filter_bank(SAMPLE_RATE, N_FFT, N_MELS)

    audio = np.pad(audio, (0, CHUNK_SAMPLES - len(audio))) if len(audio) < CHUNK_SAMPLES else audio[:CHUNK_SAMPLES]

    window = np.hanning(N_FFT + 1)[:-1].astype(np.float32)
    if len(audio) < N_FFT + (MEL_FRAMES - 1) * HOP_LENGTH:
        pad = N_FFT + (MEL_FRAMES - 1) * HOP_LENGTH - len(audio)
        audio = np.pad(audio, (0, pad))

    stft = np.zeros((N_FFT // 2 + 1, MEL_FRAMES), dtype=np.float32)
    for i in range(MEL_FRAMES):
        start = i * HOP_LENGTH
        frame = audio[start:start + N_FFT] * window
        stft[:, i] = np.abs(np.fft.rfft(frame)) ** 2

    mel = _mel_filters @ stft
    mel = np.log10(np.maximum(mel, 1e-10))
    mel = np.maximum(mel, mel.max() - 8.0)
    return (mel + 4.0) / 4.0


def download_file(url: str, dest: Path, desc: str = "") -> bool:
    """Download a file with a fixed User-Agent header."""
    if dest.exists():
        return True
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading %s (%s)...", desc or dest.name, url[:80])
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=300) as response:
            dest.write_bytes(response.read())
        logger.info("Downloaded %s (%d bytes)", dest.name, dest.stat().st_size)
        return True
    except Exception as exc:
        logger.error("Download failed %s: %s", desc, exc)
        return False


def _load_vocab() -> dict[int, str]:
    global _vocab
    if _vocab is not None:
        return _vocab

    vocab_path = _CACHE_DIR / "vocab.json"
    if not vocab_path.exists():
        download_file(_VOCAB_URL, vocab_path, "vocab.json")
    if not vocab_path.exists():
        logger.error("vocab.json not available")
        return {}

    raw = json.loads(vocab_path.read_text(encoding="utf-8"))
    _vocab = {int(value): key for key, value in raw.items()}
    return _vocab


def _build_byte_decoder():
    bs = (
        list(range(ord("!"), ord("~") + 1))
        + list(range(ord("\xa1"), ord("\xac") + 1))
        + list(range(ord("\xae"), ord("\xff") + 1))
    )
    cs = list(bs)
    n = 0
    for b in range(2**8):
        if b not in bs:
            bs.append(b)
            cs.append(2**8 + n)
            n += 1
    return {chr(c): b for b, c in zip(bs, cs, strict=False)}


_BYTE_DECODER = _build_byte_decoder()


def decode_tokens(token_ids: list[int]) -> str:
    """Decode Whisper token IDs into text."""
    vocab = _load_vocab()
    if not vocab:
        return ""

    parts = []
    for token_id in token_ids:
        if token_id >= 50257:
            continue
        text = vocab.get(token_id, "")
        if text:
            text = text.replace("\u0120", " ")
            with contextlib.suppress(Exception):
                text = bytearray(
                    [_BYTE_DECODER.get(char, ord(char)) for char in text]
                ).decode("utf-8", errors="replace")
            parts.append(text)
    return "".join(parts).strip()
