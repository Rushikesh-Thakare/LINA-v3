#!/usr/bin/env bash
# LINA v3 — Virtual Environment Setup
# Creates .venv, installs all dependencies correctly (Python 3.12 compatible).
#
# Run once from the lina-v3/ directory:
#   bash setup_venv.sh
#
# Then activate with:
#   source .venv/bin/activate

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "======================================================"
echo "  LINA v3 — Virtual Environment Setup"
echo "======================================================"

# ── 1. Create venv ─────────────────────────────────────────────────────────────
echo ""
echo "[1/4] Creating virtual environment at .venv/ ..."
python3 -m venv "$VENV_DIR"
echo "✅ venv created."

PIP="$VENV_DIR/bin/pip"
PYTHON="$VENV_DIR/bin/python"

# ── 2. Upgrade pip silently ────────────────────────────────────────────────────
echo ""
echo "[2/4] Upgrading pip ..."
"$PIP" install --quiet --upgrade pip setuptools wheel
echo "✅ pip upgraded."

# ── 3. Install main requirements ───────────────────────────────────────────────
echo ""
echo "[3/4] Installing requirements.txt ..."
"$PIP" install -r "$SCRIPT_DIR/requirements.txt"
echo "✅ requirements.txt installed."

# ── 4. Install openwakeword without its tflite-runtime dep ────────────────────
# tflite-runtime has no Python 3.12 wheel on PyPI.
# We already installed onnxruntime above; openwakeword's ONNX path works fine.
echo ""
echo "[4/4] Installing openwakeword (onnx-only, --no-deps) ..."
"$PIP" install --no-deps openwakeword>=0.6.0
echo "✅ openwakeword installed (onnx backend)."

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo "  All dependencies installed!"
echo ""
echo "  ➜ Activate the environment:"
echo "      source .venv/bin/activate"
echo ""
echo "  ➜ Download models (piper voice):"
echo "      bash install_models.sh"
echo ""
echo "  ➜ Launch LINA:"
echo "      python -m lina.main"
echo "======================================================"
