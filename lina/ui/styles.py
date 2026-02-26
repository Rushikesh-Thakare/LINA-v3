"""
LINA v3 — UI Styles
Central stylesheet definitions for dark and light themes.
Import DARK_THEME and LIGHT_THEME into main_window.py.
"""

DARK_THEME = """
/* ── Base ─────────────────────────────────────────────────────────── */
QMainWindow, QWidget {
    background-color: #0D1117;
    color: #E6EDF3;
    font-family: 'Inter', 'Segoe UI', 'DejaVu Sans', sans-serif;
    font-size: 13px;
}

/* ── Title / Subtitle ─────────────────────────────────────────────── */
#TitleLabel {
    font-size: 20px;
    font-weight: 700;
    color: #58A6FF;
    letter-spacing: 0.5px;
}
#SubtitleLabel {
    font-size: 12px;
    color: #8B949E;
}

/* ── Status Pill ──────────────────────────────────────────────────── */
#StatusPill {
    padding: 5px 14px;
    border-radius: 14px;
    font-size: 12px;
    font-weight: 600;
    background-color: #21262D;
    color: #8B949E;
}
#StatusPill[state="listening"]  { background-color: #1F6FEB; color: #FFFFFF; }
#StatusPill[state="processing"] { background-color: #8957E5; color: #FFFFFF; }
#StatusPill[state="speaking"]   { background-color: #F78166; color: #FFFFFF; }
#StatusPill[state="idle"]       { background-color: #21262D; color: #8B949E; }

/* ── Buttons ──────────────────────────────────────────────────────── */
QPushButton {
    background-color: #238636;
    color: #FFFFFF;
    border: none;
    padding: 8px 18px;
    border-radius: 6px;
    font-weight: 600;
}
QPushButton:hover   { background-color: #2EA043; }
QPushButton:pressed { background-color: #196C2E; }
QPushButton:disabled { background-color: #21262D; color: #484F58; }

/* ── ToolButton ───────────────────────────────────────────────────── */
QToolButton {
    background-color: #21262D;
    color: #C9D1D9;
    border: 1px solid #30363D;
    padding: 5px 10px;
    border-radius: 6px;
}
QToolButton:hover   { background-color: #30363D; color: #FFFFFF; }
QToolButton:checked { background-color: #1F6FEB; color: #FFFFFF; border-color: #1F6FEB; }

/* ── Terminal / TextEdit ──────────────────────────────────────────── */
QTextEdit {
    background-color: #010409;
    color: #39D353;
    border: 1px solid #21262D;
    border-radius: 8px;
    font-family: 'JetBrains Mono', 'Fira Code', 'DejaVu Sans Mono', monospace;
    font-size: 13px;
    padding: 10px;
}

/* ── Line Input ───────────────────────────────────────────────────── */
QLineEdit {
    background-color: #161B22;
    color: #E6EDF3;
    border: 1px solid #30363D;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
}
QLineEdit:focus { border-color: #58A6FF; }

/* ── Progress Bar ─────────────────────────────────────────────────── */
QProgressBar {
    background-color: #21262D;
    border: none;
    border-radius: 4px;
    height: 6px;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #1F6FEB, stop:1 #58A6FF);
    border-radius: 4px;
}

/* ── Toolbar ──────────────────────────────────────────────────────── */
QToolBar {
    background-color: #161B22;
    border-bottom: 1px solid #21262D;
    padding: 2px 4px;
    spacing: 4px;
}

/* ── Cards (panels) ───────────────────────────────────────────────── */
#Card {
    background-color: #0D1117;
    border: 1px solid #21262D;
    border-radius: 10px;
}

/* ── Splitter ─────────────────────────────────────────────────────── */
QSplitter::handle { background-color: #21262D; width: 2px; }

/* ── Scrollbar ────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background: #0D1117;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #30363D;
    border-radius: 4px;
    min-height: 20px;
}

/* ── Dialog ───────────────────────────────────────────────────────── */
QDialog { background-color: #161B22; }
QDialogButtonBox QPushButton { min-width: 72px; }

/* ── Checkbox ─────────────────────────────────────────────────────── */
QCheckBox { color: #C9D1D9; }
QCheckBox::indicator:checked { background-color: #1F6FEB; border-radius: 3px; }
"""

LIGHT_THEME = """
QMainWindow, QWidget {
    background-color: #F6F8FA;
    color: #1F2328;
    font-family: 'Inter', 'Segoe UI', 'DejaVu Sans', sans-serif;
    font-size: 13px;
}
#TitleLabel { font-size: 20px; font-weight: 700; color: #0969DA; }
#SubtitleLabel { font-size: 12px; color: #656D76; }

#StatusPill {
    padding: 5px 14px; border-radius: 14px;
    font-size: 12px; font-weight: 600;
    background-color: #EAEEF2; color: #57606A;
}
#StatusPill[state="listening"]  { background-color: #0969DA; color: #FFFFFF; }
#StatusPill[state="processing"] { background-color: #8250DF; color: #FFFFFF; }
#StatusPill[state="speaking"]   { background-color: #CF222E; color: #FFFFFF; }
#StatusPill[state="idle"]       { background-color: #EAEEF2; color: #57606A; }

QPushButton {
    background-color: #1A7F37; color: #FFFFFF;
    border: none; padding: 8px 18px;
    border-radius: 6px; font-weight: 600;
}
QPushButton:hover { background-color: #116329; }
QPushButton:disabled { background-color: #EAEEF2; color: #8C959F; }

QToolButton {
    background-color: #EAEEF2; color: #1F2328;
    border: 1px solid #D0D7DE; padding: 5px 10px; border-radius: 6px;
}
QToolButton:hover { background-color: #D0D7DE; }
QToolButton:checked { background-color: #0969DA; color: #FFFFFF; }

QTextEdit {
    background-color: #FFFFFF; color: #1F2328;
    border: 1px solid #D0D7DE; border-radius: 8px;
    font-family: 'JetBrains Mono', 'Fira Code', 'DejaVu Sans Mono', monospace;
    font-size: 13px; padding: 10px;
}
QLineEdit {
    background-color: #FFFFFF; color: #1F2328;
    border: 1px solid #D0D7DE; border-radius: 6px; padding: 8px 12px;
}
QLineEdit:focus { border-color: #0969DA; }

QProgressBar {
    background-color: #EAEEF2; border: none; border-radius: 4px; height: 6px;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #0969DA, stop:1 #218BFF);
    border-radius: 4px;
}

QToolBar { background-color: #FFFFFF; border-bottom: 1px solid #D0D7DE; padding: 2px 4px; }
#Card { background-color: #FFFFFF; border: 1px solid #D0D7DE; border-radius: 10px; }
QSplitter::handle { background-color: #D0D7DE; width: 2px; }
"""
