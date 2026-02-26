"""
LINA v3 — Voice Activity Detection (VAD)

Provides:
  - VADProcessor: webrtcvad-based speech/silence classifier
  - record_until_silence(): smart recorder that waits for speech, stops on silence

Design:
  - Timer starts ONLY after speech is first detected
  - Stops automatically after SILENCE_TIMEOUT_SECONDS of continuous silence
  - Hard cap at max_seconds regardless
  - Never blocks forever
  - Status callback emits: "waiting", "speech_detected", "recording",
    "silence_detected", "done"
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Generator, Iterator
from typing import Optional

import numpy as np
import sounddevice as sd
import webrtcvad

from lina.config import SAMPLE_RATE, VAD_AGGRESSIVENESS

log = logging.getLogger(__name__)


class VADProcessor:
    """
    Wraps webrtcvad.Vad to provide is_speech() and process_stream().

    Args:
        aggressiveness: 0 (least) to 3 (most aggressive silence filter)
        sample_rate: Must be 8000, 16000, 32000, or 48000 Hz
        frame_duration_ms: Must be 10, 20, or 30 ms
    """

    VALID_RATES = {8000, 16000, 32000, 48000}
    VALID_DURATIONS = {10, 20, 30}

    def __init__(
        self,
        aggressiveness: int = VAD_AGGRESSIVENESS,
        sample_rate: int = SAMPLE_RATE,
        frame_duration_ms: int = 30,
    ) -> None:
        if sample_rate not in self.VALID_RATES:
            raise ValueError(f"sample_rate must be one of {self.VALID_RATES}, got {sample_rate}")
        if frame_duration_ms not in self.VALID_DURATIONS:
            raise ValueError(f"frame_duration_ms must be one of {self.VALID_DURATIONS}, got {frame_duration_ms}")

        self.sample_rate = sample_rate
        self.frame_duration_ms = frame_duration_ms
        self.frame_size = int(sample_rate * frame_duration_ms / 1000)  # samples per frame
        self.frame_bytes = self.frame_size * 2  # int16 = 2 bytes per sample

        self._vad = webrtcvad.Vad(aggressiveness)

    # ── Core API ──────────────────────────────────────────────────────────────

    def is_speech(self, audio_chunk_bytes: bytes) -> bool:
        """
        Returns True if the given PCM bytes contain speech.
        audio_chunk_bytes must be exactly frame_bytes in length (int16 mono).
        If it's a different length, it will be zero-padded or truncated to fit.
        """
        # Normalise length
        if len(audio_chunk_bytes) != self.frame_bytes:
            audio_chunk_bytes = (audio_chunk_bytes + b"\x00" * self.frame_bytes)[: self.frame_bytes]
        try:
            return self._vad.is_speech(audio_chunk_bytes, self.sample_rate)
        except Exception:
            return False

    def process_stream(
        self,
        audio_generator: Iterator[bytes],
    ) -> Generator[bytes, None, None]:
        """
        Filters an audio byte-stream, yielding only frames classified as speech.

        Args:
            audio_generator: Iterator that yields raw PCM bytes (any chunk size).

        Yields:
            Frames (exactly frame_bytes long) that contain speech.
        """
        buf = b""
        for chunk in audio_generator:
            buf += chunk
            while len(buf) >= self.frame_bytes:
                frame = buf[: self.frame_bytes]
                buf = buf[self.frame_bytes :]
                if self.is_speech(frame):
                    yield frame


# ── Standalone recording helper ───────────────────────────────────────────────

def record_until_silence(
    max_seconds: float = 10.0,
    silence_timeout: float = 1.5,
    aggressiveness: int = VAD_AGGRESSIVENESS,
    on_status: Optional[Callable[[str], None]] = None,
    interrupt_check: Optional[Callable[[], bool]] = None,
) -> np.ndarray:
    """
    Smart audio recorder with VAD-based start/stop.

    Behaviour:
      1. Emits "waiting" — listens for speech before starting the real timer.
      2. Once speech is detected → emits "speech_detected", starts recording.
      3. Emits "recording" on each speech frame.
      4. After SILENCE_TIMEOUT seconds of continuous post-speech silence → stops.
      5. Hard limit: max_seconds from the moment speech was first detected.
      6. Emits "done" and returns the captured numpy float32 array.

    Args:
        max_seconds:       Hard recording cap after first speech frame.
        silence_timeout:   Seconds of continuous silence that ends recording.
        aggressiveness:    webrtcvad aggressiveness (0–3).
        on_status:         Optional callback(status: str) for UI updates.
        interrupt_check:   Optional callable; if it returns True, stop early.

    Returns:
        numpy float32 array in [-1.0, 1.0], shape (N,). Empty array if no speech.
    """
    vad = VADProcessor(aggressiveness=aggressiveness)

    def _emit(status: str) -> None:
        log.debug("VAD status: %s", status)
        if on_status:
            on_status(status)

    frame_ms = vad.frame_duration_ms
    frame_size = vad.frame_size
    silence_frames_limit = int(silence_timeout * 1000 / frame_ms)
    max_speech_frames = int(max_seconds * 1000 / frame_ms)

    # Pre-speech budget: wait up to 30 seconds for speech before giving up
    pre_speech_limit = int(30 * 1000 / frame_ms)

    all_frames: list[bytes] = []
    silence_frames: int = 0
    speech_started: bool = False
    speech_frame_count: int = 0

    _emit("waiting")

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=frame_size,
    ) as stream:
        while True:
            # Check external interrupt (e.g. Qt thread interruption)
            if interrupt_check and interrupt_check():
                log.debug("VAD: interrupted by caller.")
                break

            raw, _ = stream.read(frame_size)
            pcm_bytes = raw[:, 0].tobytes()
            is_speech = vad.is_speech(pcm_bytes)

            if not speech_started:
                if is_speech:
                    speech_started = True
                    all_frames.append(pcm_bytes)
                    silence_frames = 0
                    _emit("speech_detected")
                else:
                    pre_speech_limit -= 1
                    if pre_speech_limit <= 0:
                        log.debug("VAD: no speech detected within wait window.")
                        break
            else:
                all_frames.append(pcm_bytes)

                if is_speech:
                    silence_frames = 0
                    _emit("recording")
                else:
                    silence_frames += 1
                    if silence_frames >= silence_frames_limit:
                        _emit("silence_detected")
                        break

                speech_frame_count += 1
                if speech_frame_count >= max_speech_frames:
                    log.debug("VAD: hit max_seconds limit.")
                    break

    _emit("done")

    if not all_frames:
        return np.array([], dtype=np.float32)

    pcm = np.frombuffer(b"".join(all_frames), dtype=np.int16)
    return pcm.astype(np.float32) / 32768.0
