"""
LINA v3 — Main Window (Pure PyQt5 UI)
This file contains ONLY UI logic — no business logic.

External code connects to the public signals and calls the public methods.
The controller (_ProcessWorker) is the only non-UI class kept here,
because it must live with the window to maintain thread references.

Threading rules (GEMINI.md):
  - ALL voice ops run in QThread subclasses.
  - ALL TTS runs in a background QThread.
  - ALWAYS create new QThread instances — NEVER restart the same object.
"""

from __future__ import annotations

import json
import logging
import os

from PyQt5.QtCore import (
    Qt, QSettings, QThread, QTimer,
    pyqtSignal, pyqtSlot, QSize,
)
from PyQt5.QtGui import QTextCursor, QKeySequence, QIcon, QFont
from PyQt5.QtWidgets import (
    QAction, QApplication, QCheckBox, QCompleter, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu,
    QPushButton, QSlider, QSplitter, QStyle, QSystemTrayIcon,
    QTextEdit, QToolButton, QVBoxLayout, QWidget, QProgressBar,
    QScrollArea, QSpacerItem, QSizePolicy, QMessageBox,
)

from lina import __version__
from lina.config import (
    ENABLE_FILE_COMMANDS, ENABLE_NETWORK_COMMANDS,
    ENABLE_SYSTEM_COMMANDS, PARANOID_MODE, AUDIT_MODE,
    HISTORY_RETENTION_DAYS,
)
from lina.ui.styles import DARK_THEME, LIGHT_THEME
from lina.voice.wake_word_thread import WakeWordThread
from lina.voice.stt_thread import STTThread
from lina.voice.tts_thread import TTSThread, TTSManager
from lina.brain.command_processor import CommandProcessor
from lina.system.history import HistoryManager

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# _ProcessWorker — CommandProcessor bridge (thread → Qt signals)
# ══════════════════════════════════════════════════════════════════════════════

class _ProcessWorker(QThread):
    """
    Runs CommandProcessor.process() off the main thread.
    Bridges CommandProcessor callbacks → Qt signals (QueuedConnection safe).
    """
    result_ready    = pyqtSignal(dict)
    terminal_output = pyqtSignal(str)
    speak_text      = pyqtSignal(str)
    status_update   = pyqtSignal(str)

    def __init__(self, processor: CommandProcessor, command: str, parent=None):
        super().__init__(parent)
        self._processor = processor
        self._command   = command
        self._processor.set_callbacks(
            on_output=lambda text: self.terminal_output.emit(text),
            on_speak =lambda text: self.speak_text.emit(text),
            on_status=lambda text: self.status_update.emit(text),
        )

    def run(self):
        result = self._processor.process(self._command)
        self.result_ready.emit(result)


# ══════════════════════════════════════════════════════════════════════════════
# MainWindow
# ══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """
    Pure UI layer. Emits signals — does not contain business logic.

    ── Signals (connect in controller / main.py) ─────────────────────────────
    start_requested()      — user wants to start listening
    stop_requested()       — user wants to stop
    manual_command(str)    — user typed and submitted a command
    theme_toggle()         — user toggled dark/light theme

    ── Public methods (call from controller) ─────────────────────────────────
    append_terminal(text, prefix)
    append_history(text)
    set_status(status)
    set_mic_level(level)        0..1
    set_listening_mode(bool)
    clear_terminal()
    setup_autocomplete(phrases)
    show_security_dialog() -> dict
    show_confirm_dialog(script) -> bool
    save_log_dialog()
    export_transcript_dialog()
    """

    # ── Outbound signals ───────────────────────────────────────────────────────
    start_requested = pyqtSignal()
    stop_requested  = pyqtSignal()
    manual_command  = pyqtSignal(str)
    theme_toggle    = pyqtSignal()

    # ── Internal signals (private use) ─────────────────────────────────────────
    _terminal_sig   = pyqtSignal(str)     # thread-safe terminal append
    _speak_sig      = pyqtSignal(str)     # thread-safe TTS

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"LINA v{__version__} — AI Voice Assistant for Linux")
        self.setMinimumSize(960, 640)

        # ── Persistent settings ────────────────────────────────────────────────
        self._settings      = QSettings("LINA", "VoiceAssistant")
        self.dark_theme     = self._settings.value("dark_theme",   True,                    type=bool)
        self.enable_network = self._settings.value("enable_network", ENABLE_NETWORK_COMMANDS, type=bool)
        self.enable_files   = self._settings.value("enable_files",   ENABLE_FILE_COMMANDS,    type=bool)
        self.enable_system  = self._settings.value("enable_system",  ENABLE_SYSTEM_COMMANDS,  type=bool)
        self.paranoid_mode  = self._settings.value("paranoid_mode",  PARANOID_MODE,           type=bool)
        self.audit_mode     = self._settings.value("audit_mode",     AUDIT_MODE,              type=bool)

        # ── Brain / TTS / history ──────────────────────────────────────────────
        self._processor = CommandProcessor()
        self._processor.paranoid_mode = self.paranoid_mode
        self._history   = HistoryManager()
        self._tts       = TTSManager(self)
        self._active_threads: list[QThread] = []

        # ── Wire internal signals (thread-safe) ────────────────────────────────
        self._terminal_sig.connect(self._do_terminal_append, Qt.QueuedConnection)
        self._speak_sig.connect(self._speak, Qt.QueuedConnection)

        # ── Build UI ───────────────────────────────────────────────────────────
        self._build_ui()
        self._create_toolbar()
        self._create_tray()
        self._setup_autocomplete()
        self._apply_theme()
        self._load_history()
        self._start_history_cleanup_timer()
        self._start_wake_word()

    # ══════════════════════════════════════════════════════════════════════════
    # ── UI Construction ────────────────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(6)
        root.setContentsMargins(12, 6, 12, 8)

        # ── Header: Logo | Status | Buttons ──────────────────────────────────
        header = QHBoxLayout()
        header.setSpacing(10)

        # Title block
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        self.lbl_title = QLabel("LINA")
        self.lbl_title.setObjectName("TitleLabel")
        self.lbl_subtitle = QLabel("Say  Hey LINA  to start")
        self.lbl_subtitle.setObjectName("SubtitleLabel")
        title_col.addWidget(self.lbl_title)
        title_col.addWidget(self.lbl_subtitle)
        header.addLayout(title_col, stretch=4)

        header.addStretch(1)

        # StatusPill
        self.lbl_status = QLabel("Idle")
        self.lbl_status.setObjectName("StatusPill")
        self.lbl_status.setProperty("state", "idle")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setMinimumWidth(120)
        header.addWidget(self.lbl_status, stretch=0)

        # Start button
        self.btn_listen = QPushButton("🎙  Start Listening")
        self.btn_listen.setFixedHeight(36)
        self.btn_listen.clicked.connect(self._on_start_btn)
        header.addWidget(self.btn_listen, stretch=0)

        # Hold-to-talk
        self.btn_ptt = QToolButton()
        self.btn_ptt.setText("Hold to Talk")
        self.btn_ptt.setCheckable(True)
        self.btn_ptt.setFixedHeight(36)
        self.btn_ptt.pressed.connect(self._on_start_btn)
        self.btn_ptt.released.connect(self._on_stop_btn)
        header.addWidget(self.btn_ptt, stretch=0)

        root.addLayout(header)

        # ── Command input ─────────────────────────────────────────────────────
        cmd_row = QHBoxLayout()
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText(
            "Type a command and press Enter…  (or say 'Hey LINA')"
        )
        self.cmd_input.returnPressed.connect(self._on_manual_cmd)
        self.cmd_input.setFixedHeight(36)
        cmd_row.addWidget(self.cmd_input)

        self.btn_send = QPushButton("Send")
        self.btn_send.setObjectName("SecondaryButton")
        self.btn_send.setFixedHeight(36)
        self.btn_send.clicked.connect(self._on_manual_cmd)
        cmd_row.addWidget(self.btn_send)
        root.addLayout(cmd_row)

        # ── Mic level / progress bar ─────────────────────────────────────────
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(5)
        root.addWidget(self.progress)

        # ── Splitter: Terminal | History ─────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Left: Terminal
        term_card = QFrame()
        term_card.setObjectName("Card")
        term_layout = QVBoxLayout(term_card)
        term_layout.setContentsMargins(6, 6, 6, 6)
        term_layout.setSpacing(4)

        term_header = QHBoxLayout()
        term_label = QLabel("Terminal Output")
        term_label.setObjectName("SubtitleLabel")
        term_header.addWidget(term_label)
        term_header.addStretch()
        btn_clear = QToolButton()
        btn_clear.setText("Clear")
        btn_clear.clicked.connect(self.clear_terminal)
        term_header.addWidget(btn_clear)
        term_layout.addLayout(term_header)

        self.terminal = QTextEdit()
        self.terminal.setReadOnly(True)
        self.terminal.setPlaceholderText("LINA output will appear here…")
        term_layout.addWidget(self.terminal)
        splitter.addWidget(term_card)

        # Right: History
        hist_card = QFrame()
        hist_card.setObjectName("Card")
        hist_layout = QVBoxLayout(hist_card)
        hist_layout.setContentsMargins(6, 6, 6, 6)
        hist_layout.setSpacing(4)

        hist_header = QHBoxLayout()
        hist_label = QLabel("Command History")
        hist_label.setObjectName("SubtitleLabel")
        hist_header.addWidget(hist_label)
        hist_header.addStretch()
        btn_clrhist = QToolButton()
        btn_clrhist.setText("Clear")
        btn_clrhist.clicked.connect(self._clear_history)
        hist_header.addWidget(btn_clrhist)
        hist_layout.addLayout(hist_header)

        self.history_view = QTextEdit()
        self.history_view.setReadOnly(True)
        self.history_view.setPlaceholderText("Command history will appear here…")
        hist_layout.addWidget(self.history_view)
        splitter.addWidget(hist_card)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, stretch=1)

        # ── Status bar ────────────────────────────────────────────────────────
        self.statusBar().showMessage("Ready")

        # Welcome message
        self._do_terminal_append(
            f"LINA v{__version__} ready.  "
            "Wake word: Hey LINA  |  Shortcut: Ctrl+L"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Toolbar
    # ─────────────────────────────────────────────────────────────────────────

    def _create_toolbar(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))

        def _act(icon_id, label, shortcut, slot):
            a = QAction(self.style().standardIcon(icon_id), label, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            tb.addAction(a)
            return a

        _act(QStyle.SP_MediaPlay,              "Start Listening (Ctrl+L)", "Ctrl+L",  self._on_start_btn)
        _act(QStyle.SP_MediaStop,              "Stop (Esc)",                "Escape",  self._on_stop_btn)
        tb.addSeparator()
        _act(QStyle.SP_DialogResetButton,      "Clear Terminal (Ctrl+K)",  "Ctrl+K",  self.clear_terminal)
        _act(QStyle.SP_DialogSaveButton,       "Save Log (Ctrl+S)",        "Ctrl+S",  self.save_log_dialog)
        _act(QStyle.SP_ArrowForward,           "Export Transcript",         None,      self.export_transcript_dialog)
        tb.addSeparator()
        _act(QStyle.SP_BrowserReload,          "Toggle Theme (Ctrl+T)",    "Ctrl+T",  self._do_toggle_theme)
        _act(QStyle.SP_MessageBoxInformation,  "Security Settings",         None,      self._open_security_settings)
        _act(QStyle.SP_FileDialogDetailedView, "History Retention",         None,      self._open_retention_settings)
        tb.addSeparator()
        _act(QStyle.SP_TrashIcon,              "Clear History",             None,      self._clear_history)

    # ─────────────────────────────────────────────────────────────────────────
    # System tray
    # ─────────────────────────────────────────────────────────────────────────

    def _create_tray(self):
        try:
            self._tray = QSystemTrayIcon(self)
            self._tray.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
            self._tray.setToolTip(f"LINA v{__version__}")

            menu = QMenu()
            menu.addAction("▶  Start Listening").triggered.connect(self._on_start_btn)
            menu.addAction("⏹  Stop").triggered.connect(self._on_stop_btn)
            menu.addSeparator()
            menu.addAction("🎨  Toggle Theme").triggered.connect(self._do_toggle_theme)
            menu.addSeparator()
            menu.addAction("✕  Quit").triggered.connect(QApplication.instance().quit)

            self._tray.setContextMenu(menu)
            self._tray.activated.connect(self._on_tray_activated)
            self._tray.show()
        except Exception as exc:
            log.warning("System tray unavailable: %s", exc)

    @pyqtSlot(QSystemTrayIcon.ActivationReason)
    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show()
            self.raise_()

    # ══════════════════════════════════════════════════════════════════════════
    # ── Public API (called by controller / main.py) ────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    def append_terminal(self, text: str, prefix: str = "") -> None:
        """Thread-safe append to the terminal pane."""
        self._terminal_sig.emit(f"{prefix}{text}")

    def append_history(self, text: str) -> None:
        """Append a line to the history pane."""
        cursor = self.history_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text + "\n")
        self.history_view.setTextCursor(cursor)
        self.history_view.ensureCursorVisible()

    def set_status(self, status: str) -> None:
        """Update StatusPill colour and text + status bar."""
        self.lbl_status.setText(status)
        s = status.lower()
        if "listen" in s:
            state = "listening"
        elif "process" in s or "think" in s or "running" in s or "interpret" in s:
            state = "processing"
        elif "speak" in s:
            state = "speaking"
        else:
            state = "idle"
        self.lbl_status.setProperty("state", state)
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)
        self.statusBar().showMessage(status)

    def set_mic_level(self, level: float) -> None:
        """Update the progress bar mic level (0.0–1.0)."""
        self.progress.setValue(int(min(max(level, 0.0), 1.0) * 100))

    def set_listening_mode(self, is_listening: bool) -> None:
        """Toggle the Start/Stop button visual state."""
        if is_listening:
            self.btn_listen.setEnabled(False)
            self.btn_listen.setText("Listening…")
        else:
            self.btn_listen.setEnabled(True)
            self.btn_listen.setText("🎙  Start Listening")
            self.progress.setValue(0)

    def clear_terminal(self) -> None:
        """Clear the terminal output pane."""
        self.terminal.clear()
        self._do_terminal_append("Terminal cleared.")

    def setup_autocomplete(self, phrases: list[str]) -> None:
        """Install or update QCompleter on the command input."""
        comp = QCompleter(sorted(set(phrases)), self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        self.cmd_input.setCompleter(comp)

    def show_security_dialog(self) -> dict:
        """
        Opens the Security & Privacy settings dialog modal.
        Returns a dict of updated settings.
        """
        self._open_security_settings()
        return {
            "enable_network": self.enable_network,
            "enable_files":   self.enable_files,
            "enable_system":  self.enable_system,
            "paranoid_mode":  self.paranoid_mode,
            "audit_mode":     self.audit_mode,
        }

    def show_confirm_dialog(self, script: str) -> bool:
        """
        Paranoid mode: ask user to confirm running a HIGH_RISK script.
        Returns True if confirmed.
        """
        box = QMessageBox(self)
        box.setWindowTitle("Confirm High-Risk Command")
        box.setText("LINA generated a command that is flagged as HIGH RISK.\n\nScript:\n")
        box.setDetailedText(script)
        box.setIcon(QMessageBox.Warning)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setDefaultButton(QMessageBox.No)
        return box.exec_() == QMessageBox.Yes

    def save_log_dialog(self) -> None:
        """Open file dialog and save terminal content to .txt."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Terminal Log", "lina-output.txt", "Text (*.txt)"
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.terminal.toPlainText())
                self.set_status("Log saved")
            except Exception as exc:
                self.set_status(f"Save failed: {exc}")

    def export_transcript_dialog(self) -> None:
        """Export full history as JSON via file dialog."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Transcript", "lina-transcript.json", "JSON (*.json)"
        )
        if path:
            try:
                self._history.export_json(path)
                self.set_status("Transcript exported")
            except Exception as exc:
                self.set_status(f"Export failed: {exc}")

    # ══════════════════════════════════════════════════════════════════════════
    # ── Wake word thread ────────────────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    def _start_wake_word(self):
        self._wake_thread = WakeWordThread(self)
        self._wake_thread.wake_detected.connect(self._on_wake_detected)
        self._wake_thread.status_update.connect(self.set_status)
        self._wake_thread.start()
        self._active_threads.append(self._wake_thread)

    @pyqtSlot(str)
    def _on_wake_detected(self, phrase: str):
        self._do_terminal_append(f"⚡ Wake word: '{phrase}'")
        self._on_start_btn()

    # ══════════════════════════════════════════════════════════════════════════
    # ── STT ─────────────────────────────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    def _on_start_btn(self):
        self.set_listening_mode(True)
        self.set_status("Listening…")
        self.start_requested.emit()

        stt = STTThread.create_new()
        stt.transcript_ready.connect(self._on_command_received)
        stt.level_update.connect(lambda lvl: self.set_mic_level(lvl))
        stt.status_update.connect(self.set_status)
        stt.error_occurred.connect(
            lambda e: self._do_terminal_append(f"⚠ STT error: {e}")
        )
        stt.finished.connect(lambda: self._on_stt_finished(stt))
        stt.start()
        self._active_threads.append(stt)

    def _on_stop_btn(self):
        for t in list(self._active_threads):
            if isinstance(t, STTThread) and t.isRunning():
                t.requestInterruption()
        self.set_listening_mode(False)
        self.set_status("Idle")
        self.stop_requested.emit()

    def _on_stt_finished(self, thread: QThread):
        self._safe_remove_thread(thread)
        self.set_listening_mode(False)
        self.set_status("Idle")

    # ══════════════════════════════════════════════════════════════════════════
    # ── Command dispatch ────────────────────────────════════════════════════════
    # ══════════════════════════════════════════════════════════════════════════

    def _on_manual_cmd(self):
        text = self.cmd_input.text().strip()
        if text:
            self.cmd_input.clear()
            self._on_command_received(text)

    @pyqtSlot(str)
    def _on_command_received(self, command: str):
        self._do_terminal_append(f"\n▶ {command}")
        self.set_status("Processing…")
        self.manual_command.emit(command)

        worker = _ProcessWorker(self._processor, command, self)
        worker.terminal_output.connect(self._do_terminal_append, Qt.QueuedConnection)
        worker.speak_text.connect(self._speak,                   Qt.QueuedConnection)
        worker.status_update.connect(self.set_status,            Qt.QueuedConnection)
        worker.result_ready.connect(self._on_result)
        worker.finished.connect(lambda: self._safe_remove_thread(worker))
        worker.start()
        self._active_threads.append(worker)

    @pyqtSlot(dict)
    def _on_result(self, result: dict):
        status = result.get("status", "ok")
        self.append_history(json.dumps(result, ensure_ascii=False))
        if result.get("type") == "clear_terminal":
            self.clear_terminal()
        self.set_status("Idle" if status == "ok" else status.capitalize())

    # ══════════════════════════════════════════════════════════════════════════
    # ── TTS ─────────────────────────────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    @pyqtSlot(str)
    def _speak(self, text: str):
        self.set_status("Speaking…")
        self._tts.speaking_finished.connect(lambda: self.set_status("Idle"))
        self._tts.speak(text)

    # ══════════════════════════════════════════════════════════════════════════
    # ── Theme ────────────────────────────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    def _do_toggle_theme(self):
        self.dark_theme = not self.dark_theme
        self._apply_theme()
        self._settings.setValue("dark_theme", self.dark_theme)
        self.theme_toggle.emit()

    def _apply_theme(self):
        self.setStyleSheet(DARK_THEME if self.dark_theme else LIGHT_THEME)

    # ══════════════════════════════════════════════════════════════════════════
    # ── History helpers ──────────────────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    def _load_history(self):
        for line in self._history.recent(200):
            self.append_history(line)

    def _start_history_cleanup_timer(self):
        self._history.cleanup()
        t = QTimer(self)
        t.setInterval(6 * 60 * 60 * 1000)  # every 6 hours
        t.timeout.connect(self._history.cleanup)
        t.start()

    def _clear_history(self):
        self._history.clear()
        self.history_view.clear()
        self.set_status("History cleared")

    # ══════════════════════════════════════════════════════════════════════════
    # ── Autocomplete ─────────────────────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    def _setup_autocomplete(self):
        try:
            from lina.brain.intent_router import INTENT_MAP
            phrases = list(INTENT_MAP.keys())
        except Exception:
            phrases = []
        phrases += [
            "hey lina", "hello lina", "help", "show history",
            "search for ", "current time", "disk usage", "battery status",
            "open terminal", "list files", "network status",
        ]
        self.setup_autocomplete(phrases)

    # ══════════════════════════════════════════════════════════════════════════
    # ── Settings dialogs ─────────────────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    def _open_security_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Security & Privacy Settings")
        dlg.setMinimumWidth(340)
        form = QFormLayout(dlg)
        form.setSpacing(12)

        cb_net = QCheckBox("Enable network commands"); cb_net.setChecked(self.enable_network)
        cb_fil = QCheckBox("Enable file commands");    cb_fil.setChecked(self.enable_files)
        cb_sys = QCheckBox("Enable system commands");  cb_sys.setChecked(self.enable_system)
        cb_par = QCheckBox("Paranoid mode (confirm high-risk scripts before running)"); cb_par.setChecked(self.paranoid_mode)
        cb_aud = QCheckBox("Audit mode (hash-log scripts)"); cb_aud.setChecked(self.audit_mode)

        for cb in (cb_net, cb_fil, cb_sys, cb_par, cb_aud):
            form.addRow(cb)

        btn = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn.accepted.connect(dlg.accept)
        btn.rejected.connect(dlg.reject)
        form.addRow(btn)

        if dlg.exec_() == QDialog.Accepted:
            self.enable_network = cb_net.isChecked()
            self.enable_files   = cb_fil.isChecked()
            self.enable_system  = cb_sys.isChecked()
            self.paranoid_mode  = cb_par.isChecked()
            self.audit_mode     = cb_aud.isChecked()
            self._processor.paranoid_mode = self.paranoid_mode
            for k, v in [
                ("enable_network", self.enable_network),
                ("enable_files",   self.enable_files),
                ("enable_system",  self.enable_system),
                ("paranoid_mode",  self.paranoid_mode),
                ("audit_mode",     self.audit_mode),
            ]:
                self._settings.setValue(k, v)

    def _open_retention_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("History Retention Settings")
        dlg.setMinimumWidth(320)
        form = QFormLayout(dlg)
        form.setSpacing(12)

        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(1)
        slider.setMaximum(30)
        slider.setValue(int(self._settings.value("history_days", HISTORY_RETENTION_DAYS)))
        slider.setTickInterval(5)
        slider.setTickPosition(QSlider.TicksBelow)
        lbl_val = QLabel(f"{slider.value()} days")
        slider.valueChanged.connect(lambda v: lbl_val.setText(f"{v} days"))

        form.addRow("Keep history:", slider)
        form.addRow("", lbl_val)

        btn = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn.accepted.connect(dlg.accept)
        btn.rejected.connect(dlg.reject)
        form.addRow(btn)

        if dlg.exec_() == QDialog.Accepted:
            self._settings.setValue("history_days", slider.value())

    # ══════════════════════════════════════════════════════════════════════════
    # ── Private terminal helpers ─────────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    @pyqtSlot(str)
    def _do_terminal_append(self, text: str):
        """Always runs on the main thread via QueuedConnection."""
        cursor = self.terminal.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text + "\n")
        self.terminal.setTextCursor(cursor)
        self.terminal.ensureCursorVisible()

    # ── Private back-compat alias used in older internal code paths ────────────
    def _terminal_print(self, text: str):
        self._do_terminal_append(text)

    def _history_print(self, text: str):
        self.append_history(text)

    def _update_status(self, status: str):
        self.set_status(status)

    def _clear_terminal(self):
        self.clear_terminal()

    # ══════════════════════════════════════════════════════════════════════════
    # ── Thread lifecycle ─────────────────────────────────────────────────────────
    # ══════════════════════════════════════════════════════════════════════════

    def _safe_remove_thread(self, thread: QThread):
        try:
            self._active_threads.remove(thread)
        except ValueError:
            pass

    def closeEvent(self, event):
        """Graceful shutdown — ask all threads to stop."""
        try:
            self._tts.stop()
        except Exception:
            pass
        for t in list(self._active_threads):
            if t.isRunning():
                t.requestInterruption()
                t.wait(1500)
        event.accept()
