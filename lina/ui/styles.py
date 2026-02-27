"""
LINA v3 — Qt Stylesheets
get_dark_theme() and get_light_theme() return complete QSS strings.

Dark theme: GitHub dark palette — feels like a terminal / IDE.
Light theme: GitHub light palette — clean and professional.
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# Colour tokens
# ─────────────────────────────────────────────────────────────────────────────

_DARK = {
    "bg":                "#0d1117",    # main background
    "surface":           "#161b22",    # cards, panels
    "surface2":          "#21262d",    # input backgrounds
    "surface3":          "#30363d",    # hover, pressed
    "accent":            "#238636",    # primary (GitHub green)
    "accent_hover":      "#2ea043",
    "accent_pressed":    "#1a7f37",
    "text":              "#c9d1d9",    # primary text
    "text_muted":        "#8b949e",    # secondary text
    "border":            "#30363d",
    "border_focus":      "#58a6ff",
    # Status pill states
    "idle":              "#21262d",
    "idle_text":         "#8b949e",
    "listening":         "#1f6feb",
    "listening_text":    "#cae8ff",
    "processing":        "#8b5cf6",
    "processing_text":   "#e5d3ff",
    "speaking":          "#f97316",
    "speaking_text":     "#ffe4c4",
    # Progress bar gradient
    "pb_start":          "#238636",
    "pb_end":            "#2ea043",
    # Scrollbar
    "scroll_bg":         "#161b22",
    "scroll_handle":     "#30363d",
    "scroll_hover":      "#484f58",
    # Terminal / text area
    "terminal_bg":       "#0d1117",
    "terminal_text":     "#79c0ff",    # cyan-ish like a real terminal
    "terminal_border":   "#21262d",
}

_LIGHT = {
    "bg":                "#ffffff",
    "surface":           "#f6f8fa",
    "surface2":          "#eaeef2",
    "surface3":          "#d0d7de",
    "accent":            "#2da44e",
    "accent_hover":      "#2c974b",
    "accent_pressed":    "#298e46",
    "text":              "#24292f",
    "text_muted":        "#57606a",
    "border":            "#d0d7de",
    "border_focus":      "#0969da",
    "idle":              "#eaeef2",
    "idle_text":         "#57606a",
    "listening":         "#0969da",
    "listening_text":    "#ffffff",
    "processing":        "#7c3aed",
    "processing_text":   "#ffffff",
    "speaking":          "#ea6a00",
    "speaking_text":     "#ffffff",
    "pb_start":          "#2da44e",
    "pb_end":            "#3fb950",
    "scroll_bg":         "#f6f8fa",
    "scroll_handle":     "#d0d7de",
    "scroll_hover":      "#afb8c1",
    "terminal_bg":       "#161b22",
    "terminal_text":     "#79c0ff",
    "terminal_border":   "#21262d",
}


# ─────────────────────────────────────────────────────────────────────────────
# QSS builder
# ─────────────────────────────────────────────────────────────────────────────

def _build_qss(c: dict) -> str:
    return f"""
/* ═══════════════════════════════════════════
   Base
══════════════════════════════════════════════ */
QMainWindow, QDialog {{
    background-color: {c["bg"]};
    color: {c["text"]};
}}

QWidget {{
    background-color: {c["bg"]};
    color: {c["text"]};
    font-family: "Segoe UI", "Inter", "Ubuntu", sans-serif;
    font-size: 13px;
}}

QWidget:disabled {{
    color: {c["text_muted"]};
}}

/* ═══════════════════════════════════════════
   Labels
══════════════════════════════════════════════ */
QLabel {{
    background-color: transparent;
    color: {c["text"]};
}}

QLabel[objectName="TitleLabel"] {{
    font-size: 20px;
    font-weight: 700;
    color: {c["text"]};
    letter-spacing: 0.5px;
}}

QLabel[objectName="SubtitleLabel"] {{
    font-size: 12px;
    color: {c["text_muted"]};
    letter-spacing: 0.3px;
}}

/* ═══════════════════════════════════════════
   StatusPill — colour-coded state badges
══════════════════════════════════════════════ */
QLabel[objectName="StatusPill"] {{
    padding: 4px 14px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 600;
    background-color: {c["idle"]};
    color: {c["idle_text"]};
    letter-spacing: 0.5px;
}}

QLabel[objectName="StatusPill"][state="idle"] {{
    background-color: {c["idle"]};
    color: {c["idle_text"]};
}}

QLabel[objectName="StatusPill"][state="listening"] {{
    background-color: {c["listening"]};
    color: {c["listening_text"]};
}}

QLabel[objectName="StatusPill"][state="processing"] {{
    background-color: {c["processing"]};
    color: {c["processing_text"]};
}}

QLabel[objectName="StatusPill"][state="speaking"] {{
    background-color: {c["speaking"]};
    color: {c["speaking_text"]};
}}

/* ═══════════════════════════════════════════
   Cards / Frames
══════════════════════════════════════════════ */
QFrame[objectName="Card"] {{
    background-color: {c["surface"]};
    border: 1px solid {c["border"]};
    border-radius: 10px;
    padding: 8px;
}}

QFrame,
QFrame[objectName="Divider"] {{
    background-color: transparent;
    border: none;
}}

QFrame[objectName="Divider"] {{
    background-color: {c["border"]};
    max-height: 1px;
    min-height: 1px;
}}

/* ═══════════════════════════════════════════
   Buttons
══════════════════════════════════════════════ */
QPushButton {{
    background-color: {c["accent"]};
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 600;
    font-size: 13px;
}}

QPushButton:hover {{
    background-color: {c["accent_hover"]};
}}

QPushButton:pressed {{
    background-color: {c["accent_pressed"]};
}}

QPushButton:disabled {{
    background-color: {c["surface2"]};
    color: {c["text_muted"]};
}}

QPushButton[objectName="DangerButton"] {{
    background-color: #da3633;
}}

QPushButton[objectName="DangerButton"]:hover {{
    background-color: #f85149;
}}

QPushButton[objectName="SecondaryButton"] {{
    background-color: {c["surface2"]};
    color: {c["text"]};
    border: 1px solid {c["border"]};
}}

QPushButton[objectName="SecondaryButton"]:hover {{
    background-color: {c["surface3"]};
}}

QToolButton {{
    background-color: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 5px 8px;
    color: {c["text_muted"]};
    font-size: 13px;
}}

QToolButton:hover {{
    background-color: {c["surface2"]};
    border-color: {c["border"]};
    color: {c["text"]};
}}

QToolButton:pressed {{
    background-color: {c["surface3"]};
}}

QToolButton:checked {{
    background-color: {c["surface2"]};
    border-color: {c["accent"]};
    color: {c["accent"]};
}}

/* ═══════════════════════════════════════════
   Text Inputs
══════════════════════════════════════════════ */
QLineEdit {{
    background-color: {c["surface2"]};
    color: {c["text"]};
    border: 1px solid {c["border"]};
    border-radius: 6px;
    padding: 7px 10px;
    font-size: 13px;
    selection-background-color: {c["accent"]};
}}

QLineEdit:focus {{
    border: 1.5px solid {c["border_focus"]};
    background-color: {c["surface"]};
}}

QLineEdit:disabled {{
    color: {c["text_muted"]};
    background-color: {c["surface"]};
}}

/* ═══════════════════════════════════════════
   Terminal / History text areas
══════════════════════════════════════════════ */
QTextEdit {{
    background-color: {c["terminal_bg"]};
    color: {c["terminal_text"]};
    border: 1px solid {c["terminal_border"]};
    border-radius: 8px;
    padding: 10px;
    font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", "Consolas", monospace;
    font-size: 13px;
    line-height: 1.5;
    selection-background-color: {c["accent"]};
}}

/* ═══════════════════════════════════════════
   Progress Bar
══════════════════════════════════════════════ */
QProgressBar {{
    background-color: {c["surface2"]};
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    color: transparent;
}}

QProgressBar::chunk {{
    background-color: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {c["pb_start"]},
        stop:0.5 {c["pb_end"]},
        stop:1 {c["pb_start"]}
    );
    border-radius: 4px;
}}

/* ═══════════════════════════════════════════
   Toolbar
══════════════════════════════════════════════ */
QToolBar {{
    background-color: {c["surface"]};
    border-bottom: 1px solid {c["border"]};
    padding: 4px 8px;
    spacing: 4px;
}}

QToolBar::separator {{
    background-color: {c["border"]};
    width: 1px;
    margin: 4px 6px;
}}

/* ═══════════════════════════════════════════
   Scrollbars
══════════════════════════════════════════════ */
QScrollBar:vertical {{
    background-color: {c["scroll_bg"]};
    width: 8px;
    border-radius: 4px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background-color: {c["scroll_handle"]};
    border-radius: 4px;
    min-height: 40px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {c["scroll_hover"]};
}}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
    width: 0;
}}

QScrollBar:horizontal {{
    background-color: {c["scroll_bg"]};
    height: 8px;
    border-radius: 4px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background-color: {c["scroll_handle"]};
    border-radius: 4px;
    min-width: 40px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {c["scroll_hover"]};
}}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    height: 0;
    width: 0;
}}

/* ═══════════════════════════════════════════
   Menus
══════════════════════════════════════════════ */
QMenu {{
    background-color: {c["surface"]};
    border: 1px solid {c["border"]};
    border-radius: 8px;
    padding: 4px;
    color: {c["text"]};
}}

QMenu::item {{
    padding: 7px 24px 7px 12px;
    border-radius: 4px;
    font-size: 13px;
}}

QMenu::item:selected {{
    background-color: {c["surface3"]};
    color: {c["text"]};
}}

QMenu::separator {{
    height: 1px;
    background-color: {c["border"]};
    margin: 4px 8px;
}}

/* ═══════════════════════════════════════════
   Sliders
══════════════════════════════════════════════ */
QSlider::groove:horizontal {{
    background-color: {c["surface2"]};
    height: 4px;
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background-color: {c["accent"]};
    width: 14px;
    height: 14px;
    border-radius: 7px;
    margin: -5px 0;
}}

QSlider::handle:horizontal:hover {{
    background-color: {c["accent_hover"]};
}}

QSlider::sub-page:horizontal {{
    background-color: {c["accent"]};
    border-radius: 2px;
}}

/* ═══════════════════════════════════════════
   Checkboxes
══════════════════════════════════════════════ */
QCheckBox {{
    color: {c["text"]};
    spacing: 8px;
    font-size: 13px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1.5px solid {c["border"]};
    border-radius: 4px;
    background-color: {c["surface2"]};
}}

QCheckBox::indicator:hover {{
    border-color: {c["accent"]};
}}

QCheckBox::indicator:checked {{
    background-color: {c["accent"]};
    border-color: {c["accent"]};
    /* Checkmark via Unicode char via image — falls back to colour only */
    image: url(:/icons/check.svg);
}}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_dark_theme() -> str:
    """Return the complete dark-mode QSS string."""
    return _build_qss(_DARK)


def get_light_theme() -> str:
    """Return the complete light-mode QSS string."""
    return _build_qss(_LIGHT)


def get_theme(dark: bool = True) -> str:
    """Convenience wrapper — returns dark or light theme based on flag."""
    return get_dark_theme() if dark else get_light_theme()


# Status pill state colours for use outside QSS (e.g. palette calculations)
STATUS_COLORS_DARK = {
    "idle":       (_DARK["idle"],       _DARK["idle_text"]),
    "listening":  (_DARK["listening"],  _DARK["listening_text"]),
    "processing": (_DARK["processing"], _DARK["processing_text"]),
    "speaking":   (_DARK["speaking"],   _DARK["speaking_text"]),
}

STATUS_COLORS_LIGHT = {
    "idle":       (_LIGHT["idle"],       _LIGHT["idle_text"]),
    "listening":  (_LIGHT["listening"],  _LIGHT["listening_text"]),
    "processing": (_LIGHT["processing"], _LIGHT["processing_text"]),
    "speaking":   (_LIGHT["speaking"],   _LIGHT["speaking_text"]),
}

# ── Backward-compatible constants (main_window.py imports these) ──────────────
# Built once at module load to avoid re-generating on every import.
DARK_THEME  = get_dark_theme()
LIGHT_THEME = get_light_theme()
