"""
LINA v3 — TTS Thread (Text-to-Speech)
Runs piper-tts (offline Python API) with edge-tts as online fallback,
fully inside a QThread. No external 'piper' binary required.

Rules (Gemini.md):
- ALL TTS must run in a background QThread.
- ALWAYS create new QThread instances — NEVER restart the same thread object.
"""

import asyncio
import logging
import os
import subprocess
import tempfile
from PyQt5.QtCore import QThread, pyqtSignal

import numpy as np
import sounddevice as sd

from lina.config import PIPER_ONNX_PATH, PIPER_JSON_PATH

log = logging.getLogger(__name__)

EDGE_VOICE = "en-US-AriaNeural"


class TTSThread(QThread):
    """
    Speaks a text string using:
      1. piper-tts Python API (offline, primary)  → plays via sounddevice
      2. edge-tts (online fallback)               → plays via ffplay/mpg123/aplay
    """

    started_speaking = pyqtSignal()
    finished_speaking = pyqtSignal()
    tts_error = pyqtSignal(str)

    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.text = text

    # ── QThread entry point ──────────────────────────────────────────────────
    def run(self):
        self.started_speaking.emit()
        try:
            if self._piper_model_available():
                self._speak_piper(self.text)
            else:
                log.warning("piper model not found at %s — falling back to edge-tts", PIPER_ONNX_PATH)
                self._speak_edge(self.text)
        except Exception as exc:
            log.exception("TTS error: %s", exc)
            self.tts_error.emit(str(exc))
            # Last-resort: try edge-tts if piper failed
            try:
                self._speak_edge(self.text)
            except Exception:
                pass
        finally:
            self.finished_speaking.emit()

    # ── piper-tts  Python API (offline primary) ───────────────────────────────
    def _piper_model_available(self) -> bool:
        return PIPER_ONNX_PATH.exists() and PIPER_JSON_PATH.exists()

    def _speak_piper(self, text: str) -> None:
        """
        Use piper-tts synthesize_wav() to write audio to an in-memory WAV buffer,
        then play via sounddevice.
        """
        import io
        import wave
        from piper.voice import PiperVoice  # lazy import — inside thread

        voice = PiperVoice.load(str(PIPER_ONNX_PATH), config_path=str(PIPER_JSON_PATH), use_cuda=False)

        # synthesize_wav writes WAV bytes into the file object and sets all params
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wav_file:
            voice.synthesize_wav(text, wav_file, set_wav_format=True)

        # Decode WAV → numpy float32 for sounddevice
        wav_buf.seek(0)
        with wave.open(wav_buf, "rb") as wf:
            sample_rate = wf.getframerate()
            n_channels  = wf.getnchannels()
            sampwidth   = wf.getsampwidth()
            raw         = wf.readframes(wf.getnframes())

        dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
        np_dtype = dtype_map.get(sampwidth, np.int16)
        audio = np.frombuffer(raw, dtype=np_dtype).astype(np.float32)
        audio /= float(np.iinfo(np_dtype).max)
        if n_channels > 1:
            audio = audio.reshape(-1, n_channels)

        log.info("piper: %d samples @ %d Hz", len(audio), sample_rate)
        sd.play(audio, samplerate=sample_rate)
        sd.wait()  # safe — we're inside a QThread

    # ── edge-tts (online fallback) ────────────────────────────────────────────
    def _speak_edge(self, text: str) -> None:
        import edge_tts

        async def _generate(path: str) -> None:
            communicate = edge_tts.Communicate(text, voice=EDGE_VOICE, rate="+10%")
            await communicate.save(path)

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            asyncio.run(_generate(tmp_path))
            played = False
            for player, args in [
                ("ffplay",  ["-nodisp", "-autoexit", tmp_path]),
                ("mpg123",  [tmp_path]),
                ("aplay",   [tmp_path]),
            ]:
                if subprocess.call(["which", player], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
                    subprocess.run([player] + args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    log.info("edge-tts played via %s", player)
                    played = True
                    break
            if not played:
                log.warning("No audio player found for edge-tts output.")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
