"""
LINA v3 — TTS Thread + Manager
Non-blocking Text-to-Speech with a 4-level priority fallback chain.

Priority chain (tried in order, first success wins):
  1. piper-tts Python API     (offline, best quality — no binary needed)
  2. piper binary             (offline, shutil.which("piper"))
  3. edge-tts                 (online,  en-IN-NeerjaNeural)
  4. pyttsx3                  (offline, robotic but always works)
  5. print to terminal        (never fail silently)

Rules (Gemini.md):
  - ALL TTS must run in a background QThread.
  - ALWAYS create new QThread instances — NEVER restart the same thread object.
  - ZERO blocking calls on the main Qt thread.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional

from PyQt5.QtCore import QMutex, QObject, QThread, pyqtSignal

import numpy as np
import sounddevice as sd

from lina.config import (
    PIPER_ONNX_PATH,
    PIPER_JSON_PATH,
    PIPER_VOICE,
)

log = logging.getLogger(__name__)

EDGE_VOICE = "en-IN-NeerjaNeural"   # online fallback voice


# ══════════════════════════════════════════════════════════════════════════════
# TTSThread
# ══════════════════════════════════════════════════════════════════════════════

class TTSThread(QThread):
    """
    Speaks a text string in a background QThread.
    Tries each TTS method in priority order and uses the first that succeeds.
    Always create a new instance — never restart the same thread object.
    """

    started_speaking  = pyqtSignal()
    finished_speaking = pyqtSignal()
    error_occurred    = pyqtSignal(str)

    def __init__(
        self,
        text: str,
        use_piper: bool = True,
        piper_model_path: Optional[str] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.text = text.strip()
        self._use_piper = use_piper
        self._piper_model_path = piper_model_path or str(PIPER_ONNX_PATH)

    # ── Entry point ───────────────────────────────────────────────────────────
    def run(self) -> None:
        if not self.text:
            return

        self.started_speaking.emit()
        success = False

        # ── Priority 1a: piper-tts Python API (offline, best) ─────────────────
        if self._use_piper and PIPER_ONNX_PATH.exists() and PIPER_JSON_PATH.exists():
            try:
                self._speak_piper_python()
                success = True
            except Exception as exc:
                log.warning("piper Python API failed: %s", exc)

        # ── Priority 1b: piper binary (offline) ───────────────────────────────
        if not success and self._use_piper:
            piper_bin = shutil.which("piper") or shutil.which("piper-tts")
            if piper_bin and os.path.exists(self._piper_model_path):
                try:
                    self._speak_piper_binary(piper_bin)
                    success = True
                except Exception as exc:
                    log.warning("piper binary failed: %s", exc)

        # ── Priority 2: edge-tts (online) ─────────────────────────────────────
        if not success:
            try:
                self._speak_edge()
                success = True
            except Exception as exc:
                log.warning("edge-tts failed: %s", exc)

        # ── Priority 3: pyttsx3 (offline, robotic) ────────────────────────────
        if not success:
            try:
                self._speak_pyttsx3()
                success = True
            except Exception as exc:
                log.warning("pyttsx3 failed: %s", exc)
                self.error_occurred.emit(str(exc))

        # ── Priority 4: print (never fail silently) ───────────────────────────
        if not success:
            print(f"[LINA says]: {self.text}")
            log.info("TTS fallback: printed to terminal.")

        self.finished_speaking.emit()

    # ── 1a: piper-tts Python API ──────────────────────────────────────────────
    def _speak_piper_python(self) -> None:
        """Use the piper-tts Python package — no external binary required."""
        import io
        import wave
        from piper.voice import PiperVoice

        voice = PiperVoice.load(
            str(PIPER_ONNX_PATH),
            config_path=str(PIPER_JSON_PATH),
            use_cuda=False,
        )

        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            voice.synthesize_wav(self.text, wf, set_wav_format=True)

        wav_buf.seek(0)
        with wave.open(wav_buf, "rb") as wf:
            rate    = wf.getframerate()
            n_ch    = wf.getnchannels()
            sw      = wf.getsampwidth()
            raw     = wf.readframes(wf.getnframes())

        dt = {1: np.int8, 2: np.int16, 4: np.int32}.get(sw, np.int16)
        audio = np.frombuffer(raw, dtype=dt).astype(np.float32) / float(np.iinfo(dt).max)
        if n_ch > 1:
            audio = audio.reshape(-1, n_ch)

        log.info("piper (Python API): %d samples @ %d Hz", len(audio), rate)
        sd.play(audio, samplerate=rate)
        sd.wait()

    # ── 1b: piper binary ─────────────────────────────────────────────────────
    def _speak_piper_binary(self, piper_bin: str) -> None:
        """Use the piper binary (Rust CLI) via subprocess."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_wav = tmp.name
        try:
            subprocess.run(
                [piper_bin, "--model", self._piper_model_path,
                 "--output_file", tmp_wav],
                input=self.text.encode(),
                check=True,
                capture_output=True,
            )
            _play_wav(tmp_wav)
            log.info("piper (binary): played %s", tmp_wav)
        finally:
            _safe_remove(tmp_wav)

    # ── 2: edge-tts ───────────────────────────────────────────────────────────
    def _speak_edge(self) -> None:
        """Use edge-tts (online) and play the resulting MP3."""
        import edge_tts

        async def _gen(path: str) -> None:
            comm = edge_tts.Communicate(self.text, voice=EDGE_VOICE, rate="+5%")
            await comm.save(path)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_mp3 = tmp.name
        try:
            asyncio.run(_gen(tmp_mp3))
            _play_audio(tmp_mp3)
            log.info("edge-tts: played via system player")
        finally:
            _safe_remove(tmp_mp3)

    # ── 3: pyttsx3 ───────────────────────────────────────────────────────────
    def _speak_pyttsx3(self) -> None:
        """Use pyttsx3 — offline, robotic, but always available."""
        import pyttsx3

        engine = pyttsx3.init()
        engine.setProperty("rate", 160)
        engine.setProperty("volume", 0.9)
        engine.say(self.text)
        engine.runAndWait()
        log.info("pyttsx3: spoke text.")


# ══════════════════════════════════════════════════════════════════════════════
# TTSManager
# ══════════════════════════════════════════════════════════════════════════════

class TTSManager(QObject):
    """
    Manages speech so that only ONE TTSThread runs at a time.
    - speak(text): cancels any current speech, starts a new TTSThread immediately.
    - stop(): cancels current speech.
    Thread-safe: uses QMutex internally.
    """

    speaking_started  = pyqtSignal()
    speaking_finished = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current: Optional[TTSThread] = None
        self._mutex = QMutex()

    def speak(self, text: str) -> None:
        """Stop any current speech and begin speaking the new text immediately."""
        if not text or not text.strip():
            return
        self.stop()                      # cancel current thread if active

        tts = TTSThread(text)
        tts.started_speaking.connect(self.speaking_started)
        tts.finished_speaking.connect(self.speaking_finished)
        tts.finished_speaking.connect(lambda: self._clear(tts))

        self._mutex.lock()
        self._current = tts
        self._mutex.unlock()

        tts.start()

    def stop(self) -> None:
        """Immediately interrupt current speech if any."""
        self._mutex.lock()
        tts = self._current
        self._mutex.unlock()

        if tts and tts.isRunning():
            log.debug("TTSManager: interrupting current speech.")
            tts.requestInterruption()
            sd.stop()                    # cut playback immediately
            tts.wait(500)               # max 500 ms grace period

    def _clear(self, tts: TTSThread) -> None:
        self._mutex.lock()
        if self._current is tts:
            self._current = None
        self._mutex.unlock()

    @property
    def is_speaking(self) -> bool:
        self._mutex.lock()
        running = self._current is not None and self._current.isRunning()
        self._mutex.unlock()
        return running


# ══════════════════════════════════════════════════════════════════════════════
# Audio playback helpers (module-level utilities)
# ══════════════════════════════════════════════════════════════════════════════

def _play_wav(path: str) -> None:
    """Play a WAV file using the best available system player."""
    for player, args in [
        ("aplay",  [path]),
        ("paplay", [path]),
        ("ffplay", ["-nodisp", "-autoexit", path]),
    ]:
        if shutil.which(player):
            subprocess.run(
                [player] + args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return
    log.warning("No WAV player found (tried aplay, paplay, ffplay).")


def _play_audio(path: str) -> None:
    """Play an audio file (any format) using the best available player."""
    for player, args in [
        ("ffplay",  ["-nodisp", "-autoexit", path]),
        ("mpg123",  [path]),
        ("aplay",   [path]),
    ]:
        if shutil.which(player):
            subprocess.run(
                [player] + args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return
    log.warning("No audio player found (tried ffplay, mpg123, aplay).")


def _safe_remove(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
