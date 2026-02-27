"""
LINA v3 — Wake Word Thread
Always-on wake word detection using openWakeWord (offline, ONNX).

Wake word: currently uses "hey_jarvis" as a stand-in because openWakeWord
does not ship a "hey_lina" model by default.

To train a custom "Hey LINA" model:
  pip install openwakeword
  python -m openwakeword.train --positive_reference_clips /path/to/hey_lina/
  → produces hey_lina.onnx → set WAKE_WORD=/path/to/hey_lina.onnx in .env

Fallback mode (FALLBACK_WAKE_WORD=true in .env):
  No always-on mic. Instead, the STTThread's transcript is checked for
  "hey lina" / "hello lina" after every utterance. Slower, but requires
  no extra library and zero RAM overhead.

Threading rules (GEMINI.md):
  - NEVER block the main Qt thread.
  - ALWAYS create a new QThread instance — NEVER restart the same object.
"""

from __future__ import annotations

import logging
import time

import numpy as np
import sounddevice as sd
from PyQt5.QtCore import QThread, pyqtSignal

from lina.config import (
    SAMPLE_RATE, ENABLE_WAKE_WORD, WAKE_WORD,
    DISPLAY_WAKE_PHRASE, OWW_THRESHOLD, OWW_MODEL_DIR,
)

log = logging.getLogger(__name__)

# openWakeWord requires exactly 1280 samples per frame @ 16 kHz (= 80 ms)
OWW_FRAME_SIZE = 1280

# Cooldown after a detection to avoid rapid re-triggering
DETECTION_COOLDOWN_S = 2.0

# Valid built-in pretrained model names in openWakeWord
_BUILTIN_MODELS = {
    "alexa", "hey_jarvis", "hey_mycroft",
    "ok_nabu", "hey_rhasspy", "timer",
}

# Text-based fallback phrases (checked post-STT, not via mic)
_FALLBACK_PHRASES = frozenset([
    "hey lina", "hello lina", "ok lina",
    "hey liner", "hey leena",            # common Whisper mishearings
])


class WakeWordThread(QThread):
    """
    Runs openWakeWord in a continuous loop until interrupted.

    Signals:
        wake_detected(str)     — primary signal emitted on wake (phrase str)
        wake_word_detected()   — parameterless alias (spec compatibility)
        status_update(str)     — status text for UI
        error_occurred(str)    — non-fatal error message
    """

    # Primary signal (phrase as string, compatible with existing main_window.py)
    wake_detected       = pyqtSignal(str)

    # Parameterless alias required by spec
    wake_word_detected  = pyqtSignal()

    status_update  = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = None

    # ── Model loading ─────────────────────────────────────────────────────────

    def _load_model(self):
        if self._model is not None:
            return

        # Lazy import — only runs inside the QThread, never on the main thread
        from openwakeword.model import Model

        model_arg = self._resolve_model()
        log.info("Loading openWakeWord model: %s", model_arg)

        self._model = Model(
            wakeword_models=[model_arg],
            inference_framework="onnx",
        )
        log.info("openWakeWord model loaded (%s).", model_arg)

    def _resolve_model(self) -> str:
        """
        Returns the correct argument for openWakeWord.Model():
          • Path to existing .onnx file → use as-is (custom model)
          • Known built-in name         → use as-is
          • Anything else               → warn and fall back to 'hey_jarvis'
        """
        import os
        wake_word = WAKE_WORD.strip()

        if os.path.exists(wake_word) and wake_word.endswith(".onnx"):
            log.info("Using custom wake word model: %s", wake_word)
            return wake_word

        if wake_word.lower() in _BUILTIN_MODELS:
            return wake_word.lower()

        log.warning(
            "WAKE_WORD='%s' is not a known openWakeWord model. "
            "Valid built-ins: %s. Falling back to 'hey_jarvis'.",
            wake_word, ", ".join(sorted(_BUILTIN_MODELS)),
        )
        return "hey_jarvis"

    # ── QThread entry point ───────────────────────────────────────────────────

    def run(self):
        if not ENABLE_WAKE_WORD:
            log.info("Wake word disabled (ENABLE_WAKE_WORD=false).")
            self.status_update.emit("Wake word disabled")
            return

        try:
            self._load_model()
        except ImportError:
            msg = "openWakeWord not installed — wake word unavailable."
            log.warning(msg)
            self.error_occurred.emit(msg)
            self.status_update.emit("Wake word: unavailable")
            return
        except Exception as exc:
            log.exception("WakeWordThread error loading model: %s", exc)
            self.error_occurred.emit(str(exc))
            self.status_update.emit(f"Wake word error: {exc}")
            return

        self.status_update.emit(f"Waiting for '{DISPLAY_WAKE_PHRASE}'…")
        log.info("Listening for wake word: %s", DISPLAY_WAKE_PHRASE)

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=OWW_FRAME_SIZE,
            ) as stream:
                while not self.isInterruptionRequested():
                    self._process_frame(stream)

        except sd.PortAudioError as exc:
            msg = f"Microphone access denied or unavailable: {exc}"
            log.error(msg)
            self.error_occurred.emit(msg)
            self.status_update.emit("Wake word: mic unavailable")
        except Exception as exc:
            log.exception("WakeWordThread error: %s", exc)
            self.error_occurred.emit(str(exc))
            self.status_update.emit(f"Wake word error: {exc}")

    def _process_frame(self, stream: sd.InputStream):
        """Read one 80-ms frame and check for wake word."""
        try:
            raw, overflowed = stream.read(OWW_FRAME_SIZE)
            if overflowed:
                return

            pcm = raw[:, 0].copy()
            predictions = self._model.predict(pcm)

            for phrase, confidence in predictions.items():
                if confidence >= OWW_THRESHOLD:
                    log.info(
                        "Wake word detected: %s (confidence=%.2f)",
                        phrase, confidence,
                    )
                    # Reset model state so we don't get double-triggers
                    self._model.reset()

                    # Emit both signals (alias for spec + phrase for UI)
                    self.wake_detected.emit(DISPLAY_WAKE_PHRASE)
                    self.wake_word_detected.emit()

                    # Cooldown — drain the stream silently
                    self._cooldown(stream)
                    self.status_update.emit(f"Waiting for '{DISPLAY_WAKE_PHRASE}'…")
                    break

        except Exception as exc:
            log.warning("Frame processing error: %s", exc)

    def _cooldown(self, stream: sd.InputStream):
        """Drain the mic stream for DETECTION_COOLDOWN_S seconds."""
        deadline = time.monotonic() + DETECTION_COOLDOWN_S
        while time.monotonic() < deadline and not self.isInterruptionRequested():
            try:
                stream.read(OWW_FRAME_SIZE)
            except Exception:
                break
            time.sleep(0.01)


# ══════════════════════════════════════════════════════════════════════════════
# Fallback: text-based "wake word" check (runs after STT, not via mic)
# ══════════════════════════════════════════════════════════════════════════════

def is_wake_phrase(text: str) -> bool:
    """
    Fallback wake-word detector for when openWakeWord is unavailable.
    Called on each STT transcript — if the transcript starts with a
    recognised wake phrase, return True so the controller can strip
    the phrase and process the remainder.

    Example:
        is_wake_phrase("hey lina open terminal")  → True
        is_wake_phrase("open terminal")            → False
    """
    normalised = text.strip().lower()
    for phrase in _FALLBACK_PHRASES:
        if normalised == phrase or normalised.startswith(phrase + " "):
            return True
    return False


def strip_wake_phrase(text: str) -> str:
    """Remove the leading wake phrase from a transcript, if present."""
    normalised = text.strip()
    lower = normalised.lower()
    for phrase in _FALLBACK_PHRASES:
        if lower.startswith(phrase + " "):
            return normalised[len(phrase):].lstrip()
        if lower == phrase:
            return ""
    return normalised
