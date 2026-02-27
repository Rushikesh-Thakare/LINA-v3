"""
LINA v3 — Application Entry Point
Boots PyQt5, wires all components through LINAController, and starts the app.

Startup sequence:
  1. QApplication setup
  2. validate_config()         → friendly dialog on missing keys
  3. LINAController.__init__() → build all services + MainWindow
  4. Start wake-word thread (if ENABLE_WAKE_WORD)
  5. window.show()
  6. app.exec_()
"""

from __future__ import annotations

import logging
import sys
import os

from PyQt5.QtCore import Qt, QThread
from PyQt5.QtWidgets import QApplication, QMessageBox, QStyle

from lina import __version__

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("lina.main")


# ══════════════════════════════════════════════════════════════════════════════
# LINAController — wires all services together
# ══════════════════════════════════════════════════════════════════════════════

class LINAController:
    """
    Dependency-injection controller.
    Owns references to all services and wires them to the MainWindow signals.
    Does NOT perform any business logic — only wiring.
    """

    def __init__(self, app: QApplication):
        self._app = app

        # ── Config validation first ────────────────────────────────────────────
        self._check_config()

        # ── Import UI and services (deferred to keep startup fast) ────────────
        from lina.config import ENABLE_WAKE_WORD
        from lina.ui.main_window import MainWindow
        from lina.brain.command_processor import CommandProcessor
        from lina.voice.tts_thread import TTSManager
        from lina.system.executor import Executor
        from lina.system.history import HistoryManager
        from lina.system.distro import detect_distro

        # ── Instantiate services ───────────────────────────────────────────────
        self.history    = HistoryManager()
        self.executor   = Executor()
        self.distro     = detect_distro()

        # ── Build MainWindow first (it owns TTSManager internally) ─────────────
        self.window = MainWindow()

        # ── CommandProcessor ──────────────────────────────────────────────────
        self.processor = CommandProcessor(
            executor=self.executor,
            history=self.history,
            distro=str(self.distro),
        )
        self.processor.paranoid_mode = self.window.paranoid_mode

        # Inject the processor into the window so its _ProcessWorker uses it
        self.window._processor = self.processor

        # Wire the public signals ──────────────────────────────────────────────
        self.window.start_requested.connect(self.start_listening)
        self.window.stop_requested.connect(self.stop_listening)
        self.window.manual_command.connect(self.process_manual_command)
        self.window.theme_toggle.connect(self._on_theme_toggle)

        # ── Notify user about first-run model download ─────────────────────────
        self._check_whisper_model()

        # ── Start wake word ───────────────────────────────────────────────────
        if ENABLE_WAKE_WORD:
            self._ensure_wake_word()

        log.info("LINAController ready — distro: %s", self.distro)

    # ── Config validation ─────────────────────────────────────────────────────

    def _check_config(self):
        """Validate config and show a friendly dialog on errors."""
        try:
            from lina.config import validate_config
            errors = validate_config()
            if errors:
                _show_warning(
                    "Missing Configuration",
                    "LINA is missing required settings.\n\n"
                    + "\n".join(f"• {e}" for e in errors)
                    + "\n\nCreate a .env file from .env.example and fill in:\n"
                      "  GROQ_API_KEY=gsk_..."
                )
        except Exception as exc:
            _show_warning("Config Error", f"Failed to load configuration:\n\n{exc}")

    # ── Whisper model check ───────────────────────────────────────────────────

    def _check_whisper_model(self):
        """Inform user on first run that the Whisper model will be downloaded."""
        try:
            from lina.config import WHISPER_MODEL
            cache_dir = os.path.expanduser(
                f"~/.cache/huggingface/hub/models--Systran--faster-whisper-{WHISPER_MODEL}"
            )
            if not os.path.isdir(cache_dir):
                self.window.append_terminal(
                    f"⬇ First run: Whisper model '{WHISPER_MODEL}' (~150 MB) "
                    "will be downloaded on first voice command.",
                    prefix=""
                )
        except Exception:
            pass

    # ── Wake word ─────────────────────────────────────────────────────────────

    def _ensure_wake_word(self):
        """
        The Wake-word thread is already started inside MainWindow._start_wake_word().
        This is a hook for any additional wake-word setup needed at controller level.
        """
        log.debug("Wake-word thread handled by MainWindow.")

    # ── Public methods (connected to MainWindow signals) ──────────────────────

    def start_listening(self):
        """Start a NEW STTThread. Slot for MainWindow.start_requested signal."""
        # MainWindow._on_start_btn() already handles this internally.
        # This hook exists for external controller override / future use.
        log.debug("start_listening() called from controller.")

    def stop_listening(self):
        """Stop active STT. Slot for MainWindow.stop_requested signal."""
        log.debug("stop_listening() called from controller.")

    def process_manual_command(self, text: str):
        """
        Called when the user submits a typed command.
        MainWindow._on_command_received() already dispatches to _ProcessWorker.
        This hook allows external override / logging at controller level.
        """
        log.debug("Manual command from controller hook: %s", text)

    def _on_theme_toggle(self):
        log.debug("Theme toggled.")

    # ── Show window ───────────────────────────────────────────────────────────

    def show(self):
        self.window.show()


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _show_warning(title: str, message: str) -> None:
    """Show a non-fatal warning dialog. Safe to call before the main event loop."""
    box = QMessageBox()
    box.setWindowTitle(title)
    box.setText(message)
    box.setIcon(QMessageBox.Warning)
    box.setStandardButtons(QMessageBox.Ok)
    box.exec_()


def _show_fatal(title: str, message: str) -> None:
    """Show a fatal error dialog and exit."""
    box = QMessageBox()
    box.setWindowTitle(title)
    box.setText(message)
    box.setIcon(QMessageBox.Critical)
    box.exec_()
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    log.info("Starting LINA v%s", __version__)

    # ── QApplication ──────────────────────────────────────────────────────────
    # Set AA_ShareOpenGLContexts before creating QApplication to avoid warnings
    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    app = QApplication(sys.argv)
    app.setApplicationName("LINA")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("LINA")

    # ── Try to set app icon (optional, silently skip if missing) ──────────────
    try:
        icon_paths = [
            os.path.join(os.path.dirname(__file__), "ui", "icon.png"),
            os.path.join(os.path.dirname(__file__), "ui", "icon.ico"),
        ]
        from PyQt5.QtGui import QIcon
        for p in icon_paths:
            if os.path.exists(p):
                app.setWindowIcon(QIcon(p))
                break
    except Exception:
        pass

    # ── Controller ────────────────────────────────────────────────────────────
    try:
        controller = LINAController(app)
        controller.show()
    except Exception as exc:
        log.exception("Fatal startup error: %s", exc)
        _show_fatal(
            "LINA Failed to Start",
            f"LINA encountered an error during startup:\n\n{exc}\n\n"
            "Check the terminal for details.",
        )
        return

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
