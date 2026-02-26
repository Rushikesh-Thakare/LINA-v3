"""
LINA v3 — Wake Word Thread
Listens continuously for the wake phrase using openWakeWord (offline, ONNX).
Emits wake_detected signal → MainWindow starts a fresh STTThread.

Rules (Gemini.md):
- NEVER block the main Qt thread.
- ALWAYS create a new QThread instance — NEVER restart the same object.
"""

import logging
import numpy as np
import sounddevice as sd
from PyQt5.QtCore import QThread, pyqtSignal

from lina.config import (
    SAMPLE_RATE, ENABLE_WAKE_WORD, WAKE_WORD,
    DISPLAY_WAKE_PHRASE, OWW_THRESHOLD, OWW_MODEL_DIR,
)

log = logging.getLogger(__name__)

# openWakeWord requires exactly 1280 samples per frame @ 16 kHz (80 ms)
OWW_FRAME_SIZE = 1280

# Valid built-in pretrained model names in openWakeWord
# Use one of: "alexa", "hey_jarvis", "hey_mycroft", "ok_nabu", "hey_rhasspy"
# Set WAKE_WORD in .env to match. Custom .onnx paths are also accepted.
_BUILTIN_MODELS = {
    "alexa", "hey_jarvis", "hey_mycroft",
    "ok_nabu", "hey_rhasspy", "timer",
}


class WakeWordThread(QThread):
    """
    Runs openWakeWord in a continuous loop until interrupted.
    Emits wake_detected(phrase) when the configured wake word is detected.
    Falls back gracefully if openWakeWord is unavailable or misconfigured.
    """

    wake_detected = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._model = None

    # ── Lazy model loader ────────────────────────────────────────────────────
    def _load_model(self):
        if self._model is not None:
            return

        from openwakeword.model import Model  # lazy — only imported in this thread

        model_arg = self._resolve_model()
        log.info("Loading openWakeWord model: %s", model_arg)

        self._model = Model(
            wakeword_models=[model_arg],
            inference_framework="onnx",
        )
        log.info("openWakeWord model loaded (%s).", model_arg)

    def _resolve_model(self) -> str:
        """
        Returns the correct argument for openWakeWord:
          - If WAKE_WORD is a path to an existing .onnx file → use as-is
          - If WAKE_WORD is a known built-in name (e.g. 'hey_jarvis') → use as-is
          - Otherwise → fall back to 'hey_jarvis' and log a warning
        """
        import os
        wake_word = WAKE_WORD.strip()

        # Absolute/relative path to a custom model
        if os.path.exists(wake_word) and wake_word.endswith(".onnx"):
            log.info("Using custom wake word model: %s", wake_word)
            return wake_word

        # Valid built-in name
        if wake_word.lower() in _BUILTIN_MODELS:
            return wake_word.lower()

        # Unknown name — warn and fall back
        log.warning(
            "WAKE_WORD='%s' is not a valid openWakeWord model name. "
            "Valid options: %s. Falling back to 'hey_jarvis'.",
            wake_word, ", ".join(sorted(_BUILTIN_MODELS)),
        )
        return "hey_jarvis"

    # ── QThread entry point ──────────────────────────────────────────────────
    def run(self):
        if not ENABLE_WAKE_WORD:
            log.info("Wake word disabled (ENABLE_WAKE_WORD=false).")
            self.status_update.emit("Wake word disabled")
            return

        try:
            self._load_model()
            self.status_update.emit(f"Waiting for '{DISPLAY_WAKE_PHRASE}'…")

            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=OWW_FRAME_SIZE,
            ) as stream:
                while not self.isInterruptionRequested():
                    raw, _ = stream.read(OWW_FRAME_SIZE)
                    pcm = raw[:, 0].copy()

                    predictions = self._model.predict(pcm)
                    for phrase, confidence in predictions.items():
                        if confidence >= OWW_THRESHOLD:
                            log.info(
                                "Wake word detected: %s (confidence=%.2f)",
                                phrase, confidence,
                            )
                            self.wake_detected.emit(DISPLAY_WAKE_PHRASE)
                            self._model.reset()
                            break

        except Exception as exc:
            log.exception("WakeWordThread error: %s", exc)
            self.status_update.emit(f"Wake word error: {exc}")
