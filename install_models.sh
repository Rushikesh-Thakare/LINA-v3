#!/usr/bin/env bash
# LINA v3 — Model Installer
# Downloads faster-whisper, piper-tts voice, and openWakeWord models.
# Run once before first launch: bash install_models.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODELS_DIR="$SCRIPT_DIR/models"

# ── Load .env for WHISPER_MODEL / PIPER_VOICE ─────────────────────────────────
if [ -f "$SCRIPT_DIR/.env" ]; then
    export $(grep -v '^#' "$SCRIPT_DIR/.env" | xargs)
fi

WHISPER_MODEL="${WHISPER_MODEL:-small.en}"
PIPER_VOICE="${PIPER_VOICE:-en_US-amy-medium}"

echo "======================================================"
echo "  LINA v3 — Model Installer"
echo "======================================================"
echo "  Whisper model : $WHISPER_MODEL"
echo "  Piper voice   : $PIPER_VOICE"
echo "======================================================"

# ── 1. faster-whisper (auto-downloaded by the library on first run) ───────────
echo ""
echo "[1/3] faster-whisper — model will be downloaded on first launch."
echo "      Cached at: ~/.cache/huggingface/hub/"

# ── 2. piper-tts voice model ──────────────────────────────────────────────────
echo ""
echo "[2/3] Downloading piper voice: $PIPER_VOICE ..."
PIPER_DIR="$MODELS_DIR/piper"
mkdir -p "$PIPER_DIR"

PIPER_BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"
LANG_CODE="${PIPER_VOICE%%_*}"  # e.g. "en" from "en_US-amy-medium"
LANG_REGION="${PIPER_VOICE%%"-"*}"  # e.g. "en_US" from "en_US-amy-medium"
ONNX_URL="$PIPER_BASE_URL/$LANG_CODE/$LANG_REGION/$PIPER_VOICE/$PIPER_VOICE.onnx"
JSON_URL="$PIPER_BASE_URL/$LANG_CODE/$LANG_REGION/$PIPER_VOICE/$PIPER_VOICE.onnx.json"

if [ ! -f "$PIPER_DIR/$PIPER_VOICE.onnx" ]; then
    curl -L --progress-bar -o "$PIPER_DIR/$PIPER_VOICE.onnx" "$ONNX_URL"
    curl -L --progress-bar -o "$PIPER_DIR/$PIPER_VOICE.onnx.json" "$JSON_URL"
    echo "✅ Piper voice downloaded: $PIPER_VOICE"
else
    echo "✅ Piper voice already present — skipping."
fi

# ── 3. openWakeWord model ─────────────────────────────────────────────────────
echo ""
echo "[3/3] openWakeWord — models are downloaded automatically by the library."
echo "      Run LINA once and they will be cached at: ~/.local/share/openwakeword/"

# ── piper-tts Python package check ────────────────────────────────────────────
echo ""
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [ -f "$VENV_PYTHON" ]; then
    if "$VENV_PYTHON" -c "import piper" 2>/dev/null; then
        echo "✅ piper-tts Python package found in .venv"
    else
        echo "⚠️  piper-tts not found. Run: source .venv/bin/activate && pip install piper-tts"
    fi
else
    echo "ℹ️  No .venv detected. Run setup_venv.sh first."
fi

echo ""
echo "======================================================"
echo "  Done! Run LINA with:"
echo "    cp .env.example .env   # fill in your API keys"
echo "    python -m lina.main"
echo "======================================================"
