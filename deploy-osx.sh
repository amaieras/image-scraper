#!/bin/bash
# ============================================================
# Image Scraper - Deploy Script for macOS
# ============================================================
# Usage:
#   chmod +x deploy-osx.sh
#   ./deploy-osx.sh
#
# Installs Homebrew + Python if needed
# ============================================================

set -e

MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10

echo "========================================"
echo "  Image Scraper - macOS Deploy"
echo "========================================"
echo ""

cd "$(dirname "$0")"

# ── Check if command exists ──
has_cmd() { command -v "$1" &>/dev/null; }

# ── Check Python version ──
check_python_version() {
    local py="$1"
    if ! has_cmd "$py"; then return 1; fi
    local version=$($py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    local major=$(echo "$version" | cut -d. -f1)
    local minor=$(echo "$version" | cut -d. -f2)
    if [ "$major" -ge "$MIN_PYTHON_MAJOR" ] && [ "$minor" -ge "$MIN_PYTHON_MINOR" ]; then
        echo "$version"
        return 0
    fi
    return 1
}

# ── Install Homebrew if needed ──
install_homebrew() {
    if has_cmd brew; then
        echo "  Homebrew: OK"
        return
    fi
    echo "  Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

    # Add to PATH for Apple Silicon
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
}

# ── Install Python ──
install_python() {
    echo ""
    echo "[1/5] Checking Python $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR+..."

    PYTHON=""
    for cmd in python3 python python3.12 python3.11 python3.10; do
        ver=$(check_python_version "$cmd" 2>/dev/null)
        if [ $? -eq 0 ]; then
            PYTHON="$cmd"
            echo "  Found $cmd ($ver) - OK"
            break
        fi
    done

    if [ -z "$PYTHON" ]; then
        echo "  Python $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR+ not found. Installing via Homebrew..."
        install_homebrew
        brew install python@3.12

        for cmd in python3 python3.12; do
            ver=$(check_python_version "$cmd" 2>/dev/null)
            if [ $? -eq 0 ]; then
                PYTHON="$cmd"
                echo "  Installed $cmd ($ver) - OK"
                break
            fi
        done

        if [ -z "$PYTHON" ]; then
            echo "  ERROR: Python installation failed."
            echo "  Try: brew install python@3.12"
            exit 1
        fi
    fi
}

# ── Create venv ──
setup_venv() {
    echo ""
    echo "[2/5] Setting up virtual environment..."

    if [ -d "venv" ]; then
        # Check if venv Python still works (architecture match)
        if ! venv/bin/python -c "import sys" 2>/dev/null; then
            echo "  venv broken (architecture mismatch?), recreating..."
            rm -rf venv
        else
            echo "  venv already exists - OK"
        fi
    fi

    if [ ! -d "venv" ]; then
        $PYTHON -m venv venv
        echo "  Created venv"
    fi

    PIP="venv/bin/python -m pip"
}

# ── Install Python dependencies ──
install_deps() {
    echo ""
    echo "[3/5] Installing Python dependencies..."

    $PIP install --upgrade pip --quiet 2>/dev/null

    echo "  Core dependencies from requirements.txt..."
    $PIP install --quiet -r requirements.txt 2>/dev/null

    if [ $? -ne 0 ]; then
        echo "  Retrying without --quiet..."
        $PIP install -r requirements.txt
    fi

    echo "  AI (PyTorch, CLIP)..."
    echo "  This may take a few minutes on first install (~500MB)..."
    $PIP install --quiet torch torchvision open-clip-torch sentence-transformers 2>/dev/null

    if [ $? -ne 0 ]; then
        echo ""
        echo "  WARNING: AI dependencies failed. Scraper will work without AI relevance check."
        echo "  Install manually later: venv/bin/python -m pip install torch torchvision open-clip-torch sentence-transformers"
    fi
}

# ── Pre-download CLIP model ──
preload_clip() {
    echo ""
    echo "[4/5] Pre-downloading CLIP model..."

    venv/bin/python -c "
import open_clip
open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k')
print('  CLIP model ready!')
" 2>/dev/null || echo "  CLIP model will download on first use."
}

# ── Verify ──
verify() {
    echo ""
    echo "[5/5] Verifying installation..."
    venv/bin/python -c "from flask import Flask; from PIL import Image; print('  Flask + Pillow: OK')" 2>/dev/null || echo "  Flask + Pillow: FAILED"
    venv/bin/python -c "import openpyxl; print('  Excel parser: OK')" 2>/dev/null || echo "  Excel parser: FAILED"
    venv/bin/python -c "import ddgs; print('  DuckDuckGo: OK')" 2>/dev/null || echo "  DuckDuckGo: FAILED"
    venv/bin/python -c "import torch; print('  PyTorch: OK')" 2>/dev/null || echo "  PyTorch: FAILED"
    venv/bin/python -c "import open_clip; print('  CLIP: OK')" 2>/dev/null || echo "  CLIP: FAILED"
}

# ── Run ──
install_python
setup_venv
install_deps
preload_clip
mkdir -p output
verify

echo ""
echo "========================================"
echo "  Setup complete!"
echo "========================================"
echo ""
echo "  Start the server:"
echo "    venv/bin/python app.py"
echo ""
echo "  Then open: http://localhost:8787"
echo ""
echo "========================================"
