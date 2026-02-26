"""
LINA v3 — STT Thread (Speech-to-Text)

Two operating modes:
  Mode A — Auto-record: calls record_until_silence() from vad.py internally
  Mode B — Push-to-talk: receives a pre-recorded numpy float32 array via set_audio()

Rules (Gemini.md):
  - NEVER block the main Qt thread.
  - ALWAYS create a NEW QThread instance per session. Use create_new() factory.
  - NEVER restart the same thread object.
"""

import logging
import os
from pathlib import Path
from typing import Optional

import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

from lina.config import (
    WHISPER_MODEL_SIZE,
    MAX_RECORDING_SECONDS,
    SILENCE_THRESHOLD_SECONDS,
    VAD_AGGRESSIVENESS,
)

log = logging.getLogger(__name__)

# ── Module-level Whisper model cache ─────────────────────────────────────────
# Shared across all STTThread instances to avoid reloading the ~150 MB model.
_whisper_model = None
_whisper_model_size: str = ""

_CACHE_DIR = Path.home() / ".cache" / "huggingface" / "hub"


def _model_is_cached(model_size: str) -> bool:
    """Return True if the faster-whisper model is already in the HF cache."""
    safe_name = model_size.replace(".", "-").replace("/", "--")
    for pattern in [f"*whisper*{safe_name}*", f"*{safe_name}*whisper*"]:
        import glob
        if glob.glob(str(_CACHE_DIR / pattern)):
            return True
    # broader check: any directory containing the model name
    if _CACHE_DIR.exists():
        for d in _CACHE_DIR.iterdir():
            if safe_name.lower() in d.name.lower():
                return True
    return False


def _get_whisper_model(model_size: str, status_cb=None):
    """Lazy-load and cache the WhisperModel at module level."""
    global _whisper_model, _whisper_model_size
    if _whisper_model is not None and _whisper_model_size == model_size:
        return _whisper_model

    if not _model_is_cached(model_size):
        msg = f"Downloading Whisper model '{model_size}'… (150 MB, first time only)"
        log.info(msg)
        if status_cb:
            status_cb(msg)

    log.info("Loading faster-whisper model: %s", model_size)
    if status_cb:
        status_cb(f"Loading Whisper '{model_size}'…")

    from faster_whisper import WhisperModel
    _whisper_model = WhisperModel(model_size, device="cpu", compute_type="int8")
    _whisper_model_size = model_size
    log.info("faster-whisper model ready (cached for all future calls).")
    return _whisper_model


class STTThread(QThread):
    """
    Speech-to-Text thread — faster-whisper backend.

    Modes:
      Auto-record  → set no audio; run() calls record_until_silence() itself.
      Push-to-talk → call set_audio(np_array) before start(); skips recording.

    Always create via STTThread.create_new() — never reuse an instance.
    """

    # ── Signals ───────────────────────────────────────────────────────────────
    status_update   = pyqtSignal(str)    # UI status messages
    transcript_ready = pyqtSignal(str)   # final transcribed text
    level_update    = pyqtSignal(float)  # mic RMS 0.0–1.0 for meter
    error_occurred  = pyqtSignal(str)    # error messages

    # Map VAD status keys → friendly UI strings
    _STATUS = {
        "waiting":          "Waiting for speech…",
        "speech_detected":  "Speech detected!",
        "recording":        "Recording…",
        "silence_detected": "Almost done…",
        "done":             "Transcribing…",
    }

    def __init__(
        self,
        model_size: str = WHISPER_MODEL_SIZE,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._model_size = model_size
        self._audio: Optional[np.ndarray] = None   # None → auto-record mode
        self._mode = "auto"

    # ── Factory method (required by Gemini.md — never restart same object) ───
    @staticmethod
    def create_new(model_size: str = WHISPER_MODEL_SIZE) -> "STTThread":
        """Always use this to create a fresh instance per recording session."""
        return STTThread(model_size=model_size)

    # ── Mode B: pre-recorded audio ────────────────────────────────────────────
    def set_audio(self, audio: np.ndarray) -> None:
        """Set a pre-recorded float32 audio array. Switches to push-to-talk mode."""
        if audio is None or len(audio) == 0:
            log.warning("set_audio: empty array ignored.")
            return
        self._audio = audio
        self._mode = "ptt"

    # ── QThread entry point ───────────────────────────────────────────────────
    def run(self) -> None:
        try:
            self.status_update.emit("Initialising…")
            model = _get_whisper_model(
                self._model_size,
                status_cb=lambda s: self.status_update.emit(s),
            )

            # ── Choose audio source ───────────────────────────────────────────
            if self._mode == "ptt" and self._audio is not None:
                audio = self._audio
                log.info("STT (PTT mode): %d samples received.", len(audio))
            else:
                audio = self._record()

            if audio is None or len(audio) < SAMPLE_RATE * 0.3:
                log.info("STT: audio too short or empty — skipping transcription.")
                self.status_update.emit("Idle")
                return

            # ── Transcribe ────────────────────────────────────────────────────
            self.status_update.emit("Transcribing…")
            text = _transcribe(model, audio)

            if text:
                log.info("Transcribed: %s", text)
                self.transcript_ready.emit(text)
            else:
                log.info("STT: empty transcription.")
                self.status_update.emit("Idle")

        except Exception as exc:
            log.exception("STTThread error: %s", exc)
            self.error_occurred.emit(str(exc))
            self.status_update.emit("STT error")

    # ── Auto-record helper ────────────────────────────────────────────────────
    def _record(self) -> Optional[np.ndarray]:
        from lina.voice.vad import record_until_silence

        def _on_status(s: str):
            friendly = self._STATUS.get(s, s)
            self.status_update.emit(friendly)
            # Emit a rough level pulse when recording so the UI meter moves
            if s == "recording":
                self.level_update.emit(0.6)
            elif s in ("waiting", "done", "silence_detected"):
                self.level_update.emit(0.0)

        audio = record_until_silence(
            max_seconds=MAX_RECORDING_SECONDS,
            silence_timeout=SILENCE_THRESHOLD_SECONDS,
            aggressiveness=VAD_AGGRESSIVENESS,
            on_status=_on_status,
            interrupt_check=self.isInterruptionRequested,
        )
        self.level_update.emit(0.0)
        return audio


# ── Transcription (module-level, reusable) ────────────────────────────────────
def _transcribe(model, audio: np.ndarray) -> str:
    """Run faster-whisper and return cleaned transcript string."""
    MIN_SAMPLES = SAMPLE_RATE * 0.3
    if len(audio) < MIN_SAMPLES:
        return ""
    segments, _ = model.transcribe(
        audio,
        language="en",
        beam_size=1,
        vad_filter=True,
    )
    return " ".join(seg.text for seg in segments).strip()


# Needed for the short-audio guard
try:
    from lina.config import SAMPLE_RATE
except ImportError:
    SAMPLE_RATE = 16000
