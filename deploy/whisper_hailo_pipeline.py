"""Pipeline wrapper for the standalone Whisper Hailo deployment."""

from __future__ import annotations

import contextlib
import logging
from pathlib import Path

import numpy as np
from whisper_hailo_decoder import run_decoder_hailo
from whisper_hailo_support import CHUNK_SAMPLES, SAMPLE_RATE, compute_mel_spectrogram, decode_tokens

logger = logging.getLogger(__name__)


class WhisperHailoPipeline:
    """Whisper pipeline with GenAI SDK primary and ONNX/CPU fallback."""

    def __init__(self, hef_path: str, model_size: str = "base"):
        import threading

        self.model_size = model_size
        self.hef_path = hef_path
        self.encoder_session = None
        self.decoder_engine = None
        self._genai_s2t = None
        self._genai_vdevice = None
        self._mode = None
        self._lock = threading.Lock()
        self._initialized = False

    def initialize(self) -> bool:
        with self._lock:
            if self._initialized:
                return True
            if self._try_genai():
                self._mode = "genai"
                self._initialized = True
                logger.info("Whisper pipeline ready: GenAI NPU (%s)", Path(self.hef_path).stem)
                return True
            logger.warning("GenAI SDK unavailable, falling back to ONNX/CPU")
            if self._try_onnx():
                self._mode = "onnx"
                self._initialized = True
                logger.info("Whisper pipeline ready: ONNX/CPU (%s)", self.model_size)
                return True
            logger.error("Failed to initialize any Whisper backend")
            return False

    def _try_genai(self) -> bool:
        try:
            from hailo_platform import VDevice
            from hailo_platform.genai import Speech2Text

            self._genai_vdevice = VDevice()
            self._genai_s2t = Speech2Text(self._genai_vdevice, self.hef_path)
            logger.info("GenAI Speech2Text initialized: %s", self.hef_path)
            return True
        except Exception as exc:
            logger.warning("GenAI Speech2Text init failed: %s", exc)
            self._genai_s2t = None
            self._genai_vdevice = None
            return False

    def _try_onnx(self) -> bool:
        from whisper_hailo import build_onnx_decoder_engine, init_encoder_session

        self.encoder_session = init_encoder_session(self.model_size)
        if self.encoder_session is None:
            logger.error("Failed to initialize ONNX encoder")
            return False
        self.decoder_engine = build_onnx_decoder_engine(self.hef_path, self.model_size)
        return self.decoder_engine is not None

    def transcribe(self, audio_int16: np.ndarray, language: str = "ja", vdevice=None) -> list[dict]:
        if not self._initialized and not self.initialize():
            raise RuntimeError("Whisper pipeline not initialized")
        if self._mode == "genai":
            return self._transcribe_genai(audio_int16, language)
        return self._transcribe_onnx(audio_int16, language)

    def _transcribe_genai(self, audio_int16: np.ndarray, language: str) -> list[dict]:
        from hailo_platform.genai import Speech2TextTask

        audio_le = (audio_int16.astype(np.float32) / 32768.0).astype("<f4")
        try:
            segments = self._genai_s2t.generate_all_segments(
                audio_data=audio_le,
                task=Speech2TextTask.TRANSCRIBE,
                language=language,
                timeout_ms=60000,
            )
            return [
                {"text": seg.text.strip(), "start": round(seg.start_sec, 3), "end": round(seg.end_sec, 3)}
                for seg in segments
                if seg.text.strip()
            ]
        except Exception as exc:
            logger.error("GenAI transcription failed: %s", exc)
            return []

    def _transcribe_onnx(self, audio_int16: np.ndarray, language: str) -> list[dict]:
        from whisper_hailo import run_encoder_features

        audio_f32 = audio_int16.astype(np.float32) / 32768.0
        total_samples = len(audio_f32)
        segments = []
        for chunk_start in range(0, total_samples, CHUNK_SAMPLES):
            chunk = audio_f32[chunk_start:chunk_start + CHUNK_SAMPLES]
            if len(chunk) < SAMPLE_RATE:
                continue
            mel = compute_mel_spectrogram(chunk)
            features = run_encoder_features(self.encoder_session, mel)
            if features is None:
                continue
            text = decode_tokens(run_decoder_hailo(self.decoder_engine, features, language)).strip()
            if text:
                segments.append({
                    "text": text,
                    "start": round(chunk_start / SAMPLE_RATE, 3),
                    "end": round(min((chunk_start + CHUNK_SAMPLES) / SAMPLE_RATE, total_samples / SAMPLE_RATE), 3),
                })
        return segments

    def close(self) -> None:
        self._genai_s2t = None
        if self._genai_vdevice is not None:
            with contextlib.suppress(Exception):
                self._genai_vdevice.release()
            self._genai_vdevice = None
