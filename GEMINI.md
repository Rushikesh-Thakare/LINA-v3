# LINA v3 Project Context

## What this project is
LINA is an AI Voice Assistant for Linux. It listens to voice commands,
uses an LLM to understand them, generates safe bash scripts, executes them
in a sandbox, and speaks the result aloud.

## Architecture
- STT: faster-whisper (small.en model, offline)
- Wake Word: openWakeWord (offline)
- TTS: piper-tts (offline) with edge-tts fallback (online)
- AI Brain: Anthropic Claude API (Haiku) + Groq fallback
- UI: PyQt5
- Audio: sounddevice + webrtcvad

## Package structure
```
lina-v3/
├── lina/
│   ├── main.py              # entry point
│   ├── config.py            # all settings from .env
│   ├── ui/
│   │   ├── main_window.py   # PyQt5 MainWindow
│   │   └── styles.py        # dark / light themes
│   ├── voice/
│   │   ├── stt_thread.py    # faster-whisper in QThread
│   │   ├── tts_thread.py    # piper-tts / edge-tts in QThread
│   │   ├── wake_word_thread.py  # openWakeWord in QThread
│   │   └── vad.py           # webrtcvad wrapper
│   ├── brain/
│   │   ├── command_processor.py  # orchestrator
│   │   ├── intent_router.py      # fast-path intent map
│   │   ├── llm_claude.py         # Anthropic Claude client
│   │   ├── llm_groq.py           # Groq fallback client
│   │   └── validator.py          # dangerous-script regex gate
│   └── system/
│       ├── executor.py      # firejail sandbox runner
│       ├── history.py       # JSON-Lines history + cleanup
│       └── distro.py        # /etc/os-release detection
├── requirements.txt
├── setup.py
├── install_models.sh
└── .env.example
```

## Strict Rules
- NEVER use torch, transformers, faiss, langchain in requirements
- NEVER block the main Qt thread with blocking I/O
- ALL voice operations must run in QThread subclasses
- ALL TTS must run in a background QThread
- ALWAYS create new QThread instances, NEVER restart the same thread object
- Script validation must block: rm -rf /, mkfs, dd, sudo, shutdown, reboot
- Use subprocess.Popen for GUI apps, subprocess.run for shell commands
- Python package structure: all code inside lina/ directory

## Target install size
Under 500MB (not counting Whisper model download)

## Linux targets
Ubuntu 22.04+, Debian 12+, Fedora 38+, Arch Linux
