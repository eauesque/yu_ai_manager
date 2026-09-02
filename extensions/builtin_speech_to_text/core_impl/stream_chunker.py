"""Split a continuous audio stream into transcription-ready chunks at silence boundaries."""

import logging

import numpy as np

logger = logging.getLogger(__name__)


class StreamChunker:
    """Buffer incoming PCM int16 audio and emit chunks split at silence gaps.

    Silence is detected by scanning 30 ms windows and checking if the RMS
    energy stays below *silence_threshold* for at least *min_silence_ms*.
    A small overlap is kept between consecutive chunks so the transcriber
    does not lose words at boundaries.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        max_chunk_sec: float = 30.0,
        min_chunk_sec: float = 1.0,
        silence_threshold: float = 500,
        min_silence_ms: int = 500,
        overlap_ms: int = 200,
    ) -> None:
        self.sample_rate = sample_rate
        self.max_chunk_sec = max_chunk_sec
        self.min_chunk_sec = min_chunk_sec
        self.silence_threshold = silence_threshold
        self.min_silence_ms = min_silence_ms
        self.overlap_ms = overlap_ms

        # Derived sizes in samples
        self._window_samples = int(sample_rate * 0.030)  # 30 ms window
        self._min_silence_samples = int(sample_rate * min_silence_ms / 1000)
        self._overlap_samples = int(sample_rate * overlap_ms / 1000)
        self._max_chunk_samples = int(sample_rate * max_chunk_sec)
        self._min_chunk_samples = int(sample_rate * min_chunk_sec)

        self._chunks: list[np.ndarray] = []
        self._sample_count = 0
        self._buffer_cache: np.ndarray | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def feed(self, audio: np.ndarray) -> None:
        """Append int16 PCM samples to the internal buffer."""
        if len(audio) == 0:
            return
        chunk = audio.astype(np.int16, copy=False)
        self._chunks.append(chunk)
        self._sample_count += len(chunk)
        self._buffer_cache = None

    def pending_duration(self) -> float:
        """Return duration of buffered audio in seconds."""
        return self._sample_count / self.sample_rate

    def try_extract(self) -> np.ndarray | None:
        """Try to extract a chunk delimited by a silence boundary.

        Returns *None* when no suitable split point is found yet.
        """
        buf_len = self._sample_count

        # Force-split if we exceed max duration
        if buf_len >= self._max_chunk_samples:
            return self._split_at(self._max_chunk_samples)

        # Need at least min_chunk_sec of audio before we look for silence
        if buf_len < self._min_chunk_samples:
            return None

        split = self._find_silence_boundary()
        if split is not None:
            return self._split_at(split)

        return None

    def flush(self) -> np.ndarray | None:
        """Return all remaining buffered audio (end-of-stream)."""
        if self._sample_count == 0:
            return None
        chunk = self._materialize().copy()
        self.clear()
        return chunk

    def clear(self) -> None:
        """Discard the entire buffer."""
        self._chunks = []
        self._sample_count = 0
        self._buffer_cache = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rms(self, segment: np.ndarray) -> float:
        """Compute RMS energy of a segment."""
        return float(np.sqrt(np.mean(segment.astype(np.float64) ** 2)))

    def _find_silence_boundary(self) -> int | None:
        """Scan the buffer for a silence region of sufficient length.

        Returns the sample index at the *start* of the silence region
        (i.e. the split point) or None.
        """
        win = self._window_samples
        step = win // 2  # half-window hop for finer boundary detection
        buf = self._materialize()
        buf_len = len(buf)

        # Start scanning from min_chunk_samples onward
        start = max(self._min_chunk_samples - self._min_silence_samples, 0)
        silence_start: int | None = None

        pos = start
        while pos + win <= buf_len:
            rms = self._rms(buf[pos : pos + win])
            if rms < self.silence_threshold:
                if silence_start is None:
                    silence_start = pos
                # Check if we accumulated enough silence
                silence_len = pos + win - silence_start
                if silence_len >= self._min_silence_samples:  # noqa: SIM102
                    if silence_start >= self._min_chunk_samples:
                        return silence_start
            else:
                # Silence region just ended — the actual silence extends
                # from silence_start to approximately pos (where the loud
                # window begins).  Accept it if the gap is close enough
                # (within one analysis window of the threshold).
                if silence_start is not None:
                    silence_len = pos - silence_start
                    if silence_len >= self._min_silence_samples - win:  # noqa: SIM102
                        if silence_start >= self._min_chunk_samples:
                            return silence_start
                silence_start = None
            pos += step

        return None

    def _split_at(self, index: int) -> np.ndarray:
        """Extract buffer[:index] as a chunk and keep overlap."""
        buf = self._materialize()
        chunk = buf[:index].copy()
        # Keep overlap so the next chunk shares a small tail
        keep_from = max(0, index - self._overlap_samples)
        tail = buf[keep_from:].copy()
        self._chunks = [tail] if len(tail) else []
        self._sample_count = len(tail)
        self._buffer_cache = tail if len(tail) else None
        return chunk

    def _materialize(self) -> np.ndarray:
        """Return a contiguous view of buffered chunks, concatenating lazily."""
        if self._buffer_cache is not None:
            return self._buffer_cache
        if not self._chunks:
            self._buffer_cache = np.empty(0, dtype=np.int16)
        elif len(self._chunks) == 1:
            self._buffer_cache = self._chunks[0]
        else:
            self._buffer_cache = np.concatenate(self._chunks)
            self._chunks = [self._buffer_cache]
        return self._buffer_cache
