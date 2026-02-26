"""
LINA v3 — Main Window (PyQt5 UI)
Orchestrates all threads: WakeWordThread → STTThread → CommandProcessor → TTSThread.

Threading rules (Gemini.md):
  - ALL voice ops run in QThread subclasses.
  - ALL TTS runs in a background QThread.
  - ALWAYS create new QThread instances — NEVER restart the same object.
"""

import json
import logging
import os

from PyQt5.QtCore import Qt, QSettings, QThread, QTimer, pyqtSlot
from PyQt5.QtGui import QTextCursor, QKeySequence
from PyQt5.QtWidgets import (
    QAction, QApplication, QCheckBox, QCompleter, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu,
    QPushButton, QSlider, QSplitter, QStyle, QSystemTrayIcon,
    QTextEdit, QToolButton, QVBoxLayout, QWidget, QProgressBar,
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
from lina.voice.tts_thread import TTSThread
from lina.brain.command_processor import CommandProcessor
from lina.system.history import HistoryManager

log = logging.getLogger(__name__)


class _ProcessWorker(QThread):
    """
    Runs CommandProcessor.process() off the main thread.
    Emits result_ready when done.
    """
    from PyQt5.QtCore import pyqtSignal
    result_ready = pyqtSignal(dict)

    def __init__(self, processor: CommandProcessor, command: str, parent=None):
        super().__init__(parent)
        self._processor = processor
        self._command = command

    def run(self):
        result = self._processor.process(self._command)
        self.result_ready.emit(result)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"LINA v{__version__} — AI Voice Assistant for Linux")
        self.setMinimumSize(900, 620)

        # ── Persist settings ──────────────────────────────────────────────────
        self._settings = QSettings("LINA", "VoiceAssistant")
        self.dark_theme: bool = self._settings.value("dark_theme", True, type=bool)
        self.enable_network: bool = self._settings.value("enable_network", ENABLE_NETWORK_COMMANDS, type=bool)
        self.enable_files: bool   = self._settings.value("enable_files",   ENABLE_FILE_COMMANDS,    type=bool)
        self.enable_system: bool  = self._settings.value("enable_system",  ENABLE_SYSTEM_COMMANDS,  type=bool)
        self.paranoid_mode: bool  = self._settings.value("paranoid_mode",  PARANOID_MODE,           type=bool)
        self.audit_mode: bool     = self._settings.value("audit_mode",     AUDIT_MODE,              type=bool)

        # ── Brain / history ───────────────────────────────────────────────────
        self._processor = CommandProcessor()
        self._history   = HistoryManager()
        self._active_threads: list[QThread] = []  # keep references alive

        # ── Build UI ──────────────────────────────────────────────────────────
        self._build_ui()
        self._create_toolbar()
        self._create_tray()
        self._apply_theme()
        self._setup_autocomplete()
        self._load_history()
        self._start_history_cleanup_timer()

        # ── Wake word ─────────────────────────────────────────────────────────
        self._start_wake_word()

    # ═══════════════════════════════════════════════════════════════════════════
    # UI Construction
    # ═══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(12, 8, 12, 8)

        # Command input row
        row = QHBoxLayout()
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("Type a command and press Enter, or say 'Hey LINA'…")
        self.cmd_input.returnPressed.connect(self._on_manual_command)
        row.addWidget(self.cmd_input)
        root.addLayout(row)

        # Header row: title + status pill + buttons
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        self.lbl_title    = QLabel("LINA")
        self.lbl_title.setObjectName("TitleLabel")
        self.lbl_subtitle = QLabel("AI Voice Assistant for Linux")
        self.lbl_subtitle.setObjectName("SubtitleLabel")
        title_col.addWidget(self.lbl_title)
        title_col.addWidget(self.lbl_subtitle)
        header.addLayout(title_col, stretch=4)

        self.lbl_status = QLabel("Idle", alignment=Qt.AlignCenter)
        self.lbl_status.setObjectName("StatusPill")
        self.lbl_status.setProperty("state", "idle")
        header.addWidget(self.lbl_status, stretch=0)

        self.btn_listen = QPushButton("🎙  Start Listening")
        self.btn_listen.clicked.connect(self._start_stt)
        header.addWidget(self.btn_listen, stretch=0)

        self.btn_ptt = QToolButton()
        self.btn_ptt.setText("Hold to Talk")
        self.btn_ptt.setCheckable(True)
        self.btn_ptt.pressed.connect(self._start_stt)
        self.btn_ptt.released.connect(self._stop_stt)
        header.addWidget(self.btn_ptt, stretch=0)

        root.addLayout(header)

        # Mic level / progress bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        root.addWidget(self.progress)

        # Splitter: terminal (left) + history (right)
        splitter = QSplitter(Qt.Horizontal)

        term_card = QFrame(); term_card.setObjectName("Card")
        term_layout = QVBoxLayout(term_card)
        term_layout.setContentsMargins(0, 0, 0, 0)
        self.terminal = QTextEdit(); self.terminal.setReadOnly(True)
        term_layout.addWidget(self.terminal)
        splitter.addWidget(term_card)

        hist_card = QFrame(); hist_card.setObjectName("Card")
        hist_layout = QVBoxLayout(hist_card)
        hist_layout.setContentsMargins(0, 0, 0, 0)
        self.history_view = QTextEdit()
        self.history_view.setReadOnly(True)
        self.history_view.setPlaceholderText("Command history will appear here…")
        hist_layout.addWidget(self.history_view)
        splitter.addWidget(hist_card)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, stretch=1)

        self._terminal_print("LINA v" + __version__ + " ready. Say 'Hey LINA' or type a command.")

    # ═══════════════════════════════════════════════════════════════════════════
    # Toolbar & Tray
    # ═══════════════════════════════════════════════════════════════════════════

    def _create_toolbar(self):
        tb = self.addToolBar("Main")
        tb.setMovable(False)

        def _act(icon_id, label, shortcut, slot):
            a = QAction(self.style().standardIcon(icon_id), label, self)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            tb.addAction(a)
            return a

        _act(QStyle.SP_MediaPlay,               "Start (Ctrl+L)",       "Ctrl+L",  self._start_stt)
        _act(QStyle.SP_MediaStop,               "Stop (Esc)",           "Escape",  self._stop_stt)
        _act(QStyle.SP_DialogResetButton,       "Clear (Ctrl+K)",       "Ctrl+K",  self._clear_terminal)
        _act(QStyle.SP_DialogSaveButton,        "Save Log (Ctrl+S)",    "Ctrl+S",  self._save_log)
        _act(QStyle.SP_BrowserReload,           "Toggle Theme (Ctrl+T)","Ctrl+T",  self._toggle_theme)
        _act(QStyle.SP_DialogSaveButton,        "Export Transcript",    None,      self._export_transcript)
        _act(QStyle.SP_TrashIcon,               "Clear History",        None,      self._clear_history)
        _act(QStyle.SP_FileDialogDetailedView,  "History Settings",     None,      self._open_retention_settings)
        _act(QStyle.SP_MessageBoxInformation,   "Security Settings",    None,      self._open_security_settings)

    def _create_tray(self):
        try:
            self._tray = QSystemTrayIcon(self)
            self._tray.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
            menu = QMenu()
            menu.addAction("Start Listening").triggered.connect(self._start_stt)
            menu.addAction("Stop").triggered.connect(self._stop_stt)
            menu.addAction("Toggle Theme").triggered.connect(self._toggle_theme)
            menu.addSeparator()
            menu.addAction("Quit").triggered.connect(QApplication.instance().quit)
            self._tray.setContextMenu(menu)
            self._tray.show()
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════════════════
    # Wake Word
    # ═══════════════════════════════════════════════════════════════════════════

    def _start_wake_word(self):
        self._wake_thread = WakeWordThread(self)
        self._wake_thread.wake_detected.connect(self._on_wake_detected)
        self._wake_thread.status_update.connect(self._update_status)
        self._wake_thread.start()
        self._active_threads.append(self._wake_thread)

    @pyqtSlot(str)
    def _on_wake_detected(self, phrase: str):
        self._terminal_print(f"⚡ Wake word: '{phrase}'")
        self._start_stt()

    # ═══════════════════════════════════════════════════════════════════════════
    # STT
    # ═══════════════════════════════════════════════════════════════════════════

    def _start_stt(self):
        """Create a fresh STTThread via factory method — never reuse."""
        self.btn_listen.setEnabled(False)
        self.btn_listen.setText("Listening…")
        self._update_status("Listening…")

        stt = STTThread.create_new()
        stt.transcript_ready.connect(self._on_command_received)
        stt.level_update.connect(self._on_level_update)
        stt.status_update.connect(self._update_status)
        stt.error_occurred.connect(lambda e: self._terminal_print(f"⚠ STT error: {e}"))
        stt.finished.connect(lambda: self._on_stt_finished(stt))
        stt.start()
        self._active_threads.append(stt)

    def _stop_stt(self):
        for t in list(self._active_threads):
            if isinstance(t, STTThread) and t.isRunning():
                t.requestInterruption()
        self._reset_listen_button()

    @pyqtSlot(QThread)
    def _on_stt_finished(self, thread: QThread):
        self._safe_remove_thread(thread)
        self._reset_listen_button()

    @pyqtSlot(float)
    def _on_level_update(self, level: float):
        self.progress.setValue(int(min(max(level, 0.0), 1.0) * 100))

    def _reset_listen_button(self):
        self.btn_listen.setEnabled(True)
        self.btn_listen.setText("🎙  Start Listening")
        self.progress.setValue(0)

    # ═══════════════════════════════════════════════════════════════════════════
    # Command Processing
    # ═══════════════════════════════════════════════════════════════════════════

    @pyqtSlot(str)
    def _on_command_received(self, command: str):
        self._terminal_print(f"\n▶ {command}")
        self._update_status("Processing…")

        worker = _ProcessWorker(self._processor, command, self)
        worker.result_ready.connect(self._on_result)
        worker.finished.connect(lambda: self._safe_remove_thread(worker))
        worker.start()
        self._active_threads.append(worker)

    @pyqtSlot(dict)
    def _on_result(self, result: dict):
        explanation = result.get("explanation", "")
        status      = result.get("status", "ok")

        if result.get("script"):
            self._terminal_print(f"$ {result['script']}")
        if result.get("output"):
            self._terminal_print(result["output"].strip())
        if explanation:
            self._terminal_print(f"💬 LINA: {explanation}")

        self._update_status("Idle" if status == "ok" else status.capitalize())
        self._history_print(json.dumps(result, ensure_ascii=False))

        if explanation and status == "ok":
            self._speak(explanation)

    def _on_manual_command(self):
        text = self.cmd_input.text().strip()
        if text:
            self.cmd_input.clear()
            self._on_command_received(text)

    # ═══════════════════════════════════════════════════════════════════════════
    # TTS
    # ═══════════════════════════════════════════════════════════════════════════

    def _speak(self, text: str):
        """Always creates a new TTSThread — never reuses."""
        self._update_status("Speaking…")
        tts = TTSThread(text, self)
        tts.finished_speaking.connect(lambda: self._update_status("Idle"))
        tts.finished_speaking.connect(lambda: self._safe_remove_thread(tts))
        tts.finished.connect(lambda: self._safe_remove_thread(tts))
        tts.start()
        self._active_threads.append(tts)

    # ═══════════════════════════════════════════════════════════════════════════
    # Status / Terminal helpers
    # ═══════════════════════════════════════════════════════════════════════════

    def _update_status(self, status: str):
        self.lbl_status.setText(status)
        state = "idle"
        s = status.lower()
        if "listen" in s:  state = "listening"
        elif "process" in s: state = "processing"
        elif "speak" in s:   state = "speaking"
        self.lbl_status.setProperty("state", state)
        self.lbl_status.style().unpolish(self.lbl_status)
        self.lbl_status.style().polish(self.lbl_status)

    def _terminal_print(self, text: str):
        self.terminal.moveCursor(QTextCursor.End)
        self.terminal.insertPlainText(text + "\n")
        self.terminal.moveCursor(QTextCursor.End)
        self.terminal.ensureCursorVisible()

    def _history_print(self, text: str):
        self.history_view.moveCursor(QTextCursor.End)
        self.history_view.insertPlainText(text + "\n")
        self.history_view.moveCursor(QTextCursor.End)

    def _clear_terminal(self):
        self.terminal.clear()
        self._terminal_print("$ ")

    # ═══════════════════════════════════════════════════════════════════════════
    # History helpers
    # ═══════════════════════════════════════════════════════════════════════════

    def _load_history(self):
        for line in self._history.recent(200):
            self._history_print(line)

    def _start_history_cleanup_timer(self):
        self._history.cleanup()
        t = QTimer(self)
        t.setInterval(6 * 60 * 60 * 1000)  # 6 hours
        t.timeout.connect(self._history.cleanup)
        t.start()

    def _clear_history(self):
        self._history.clear()
        self.history_view.clear()
        self._update_status("History cleared")

    # ═══════════════════════════════════════════════════════════════════════════
    # Toolbar actions
    # ═══════════════════════════════════════════════════════════════════════════

    def _save_log(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Log", "lina-output.txt", "Text (*.txt)")
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.terminal.toPlainText())
                self._update_status("Log saved")
            except Exception as exc:
                self._update_status(f"Save failed: {exc}")

    def _export_transcript(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Transcript", "lina-transcript.json", "JSON (*.json)")
        if path:
            try:
                self._history.export_json(path)
                self._update_status("Transcript exported")
            except Exception as exc:
                self._update_status(f"Export failed: {exc}")

    # ═══════════════════════════════════════════════════════════════════════════
    # Theme
    # ═══════════════════════════════════════════════════════════════════════════

    def _toggle_theme(self):
        self.dark_theme = not self.dark_theme
        self._apply_theme()
        self._settings.setValue("dark_theme", self.dark_theme)

    def _apply_theme(self):
        self.setStyleSheet(DARK_THEME if self.dark_theme else LIGHT_THEME)

    # ═══════════════════════════════════════════════════════════════════════════
    # Settings dialogs
    # ═══════════════════════════════════════════════════════════════════════════

    def _open_retention_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("History Retention")
        form = QFormLayout(dlg)
        slider = QSlider(Qt.Horizontal)
        slider.setMinimum(1); slider.setMaximum(30)
        slider.setValue(int(self._settings.value("history_days", HISTORY_RETENTION_DAYS)))
        form.addRow("Keep history (days):", slider)
        btn = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        form.addRow(btn)
        btn.accepted.connect(dlg.accept)
        btn.rejected.connect(dlg.reject)
        if dlg.exec_() == QDialog.Accepted:
            self._settings.setValue("history_days", slider.value())

    def _open_security_settings(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Security & Privacy")
        form = QFormLayout(dlg)
        cb_net     = QCheckBox("Enable network commands");    cb_net.setChecked(self.enable_network)
        cb_file    = QCheckBox("Enable file commands");       cb_file.setChecked(self.enable_files)
        cb_sys     = QCheckBox("Enable system commands");     cb_sys.setChecked(self.enable_system)
        cb_par     = QCheckBox("Paranoid mode (confirm run)");cb_par.setChecked(self.paranoid_mode)
        cb_aud     = QCheckBox("Audit mode (hash logs)");     cb_aud.setChecked(self.audit_mode)
        for cb in [cb_net, cb_file, cb_sys, cb_par, cb_aud]:
            form.addRow(cb)
        btn = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        form.addRow(btn)
        btn.accepted.connect(dlg.accept)
        btn.rejected.connect(dlg.reject)
        if dlg.exec_() == QDialog.Accepted:
            self.enable_network = cb_net.isChecked()
            self.enable_files   = cb_file.isChecked()
            self.enable_system  = cb_sys.isChecked()
            self.paranoid_mode  = cb_par.isChecked()
            self.audit_mode     = cb_aud.isChecked()
            for k, v in [
                ("enable_network", self.enable_network),
                ("enable_files",   self.enable_files),
                ("enable_system",  self.enable_system),
                ("paranoid_mode",  self.paranoid_mode),
                ("audit_mode",     self.audit_mode),
            ]:
                self._settings.setValue(k, v)

    # ═══════════════════════════════════════════════════════════════════════════
    # Autocomplete
    # ═══════════════════════════════════════════════════════════════════════════

    def _setup_autocomplete(self):
        from lina.brain.intent_router import INTENT_MAP
        phrases = list(INTENT_MAP.keys()) + [
            "hey lina", "hello lina", "help", "show history",
            "search for ", "open terminal", "current ip", "current time",
            "make directory demo", "battery status", "disk usage",
        ]
        comp = QCompleter(sorted(set(phrases)), self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        self.cmd_input.setCompleter(comp)

    # ═══════════════════════════════════════════════════════════════════════════
    # Thread lifecycle helpers
    # ═══════════════════════════════════════════════════════════════════════════

    def _safe_remove_thread(self, thread: QThread):
        try:
            self._active_threads.remove(thread)
        except ValueError:
            pass

    def closeEvent(self, event):
        """Request graceful shutdown of all running threads."""
        for t in list(self._active_threads):
            if t.isRunning():
                t.requestInterruption()
                t.wait(1500)
        event.accept()
