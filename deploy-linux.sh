#!/bin/bash
# ============================================================
# Image Scraper - Deploy Script for Linux
# ============================================================
# Usage:
#   chmod +x deploy-linux.sh
#   sudo ./deploy-linux.sh
#
# Supports: Ubuntu/Debian, CentOS/RHEL/Fedora, Arch
# Installs everything from scratch if needed
# ============================================================

set -e

MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=10

echo "========================================"
echo "  Image Scraper - Linux Deploy"
echo "========================================"
echo ""

cd "$(dirname "$0")"

# ── Detect distro ──
detect_distro() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        echo "$ID"
    elif [ -f /etc/redhat-release ]; then
        echo "rhel"
    else
        echo "unknown"
    fi
}

DISTRO=$(detect_distro)
echo "Detected distro: $DISTRO"

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

# ── Install Python if needed ──
install_python() {
    echo ""
    echo "[1/5] Checking Python $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR+..."

    # Try python3 first, then python
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
        echo "  Python $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR+ not found. Installing..."

        case "$DISTRO" in
            ubuntu|debian|linuxmint|pop)
                sudo apt-get update -qq
                sudo apt-get install -y -qq python3 python3-pip python3-venv python3-dev
                ;;
            centos|rhel|rocky|alma)
                sudo yum install -y python3 python3-pip python3-devel
                ;;
            fedora)
                sudo dnf install -y python3 python3-pip python3-devel
                ;;
            arch|manjaro)
                sudo pacman -Sy --noconfirm python python-pip
                ;;
            *)
                echo "  ERROR: Unknown distro '$DISTRO'. Please install Python $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR+ manually."
                exit 1
                ;;
        esac

        # Verify installation
        for cmd in python3 python; do
            ver=$(check_python_version "$cmd" 2>/dev/null)
            if [ $? -eq 0 ]; then
                PYTHON="$cmd"
                echo "  Installed $cmd ($ver) - OK"
                break
            fi
        done

        if [ -z "$PYTHON" ]; then
            echo "  ERROR: Python installation failed."
            echo "  Please install Python $MIN_PYTHON_MAJOR.$MIN_PYTHON_MINOR+ manually and re-run this script."
            exit 1
        fi
    fi
}

# ── Install system dependencies ──
install_system_deps() {
    echo ""
    echo "[2/5] Checking system dependencies..."

    # Check for pip/venv support
    if ! $PYTHON -m venv --help &>/dev/null; then
        echo "  Installing python3-venv..."
        case "$DISTRO" in
            ubuntu|debian|linuxmint|pop)
                sudo apt-get install -y -qq python3-venv
                ;;
            centos|rhel|rocky|alma)
                sudo yum install -y python3-libs
                ;;
            fedora)
                sudo dnf install -y python3-libs
                ;;
        esac
    else
        echo "  python3-venv: OK"
    fi

    # Check for pip
    if ! $PYTHON -m pip --version &>/dev/null; then
        echo "  Installing pip..."
        case "$DISTRO" in
            ubuntu|debian|linuxmint|pop)
                sudo apt-get install -y -qq python3-pip
                ;;
            centos|rhel|rocky|alma)
                sudo yum install -y python3-pip
                ;;
            fedora)
                sudo dnf install -y python3-pip
                ;;
            arch|manjaro)
                sudo pacman -Sy --noconfirm python-pip
                ;;
        esac
    else
        echo "  pip: OK"
    fi
}

# ── Create venv ──
setup_venv() {
    echo ""
    echo "[3/5] Setting up virtual environment..."

    if [ ! -d "venv" ]; then
        $PYTHON -m venv venv
        echo "  Created venv"
    else
        echo "  venv already exists"
    fi

    # Use venv python for everything from here
    PIP="venv/bin/python -m pip"
}

# ── Install Python dependencies ──
install_deps() {
    echo ""
    echo "[4/5] Installing Python dependencies..."

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
    echo "[5/5] Pre-downloading CLIP model..."

    venv/bin/python -c "
import open_clip
open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k')
print('  CLIP model ready!')
" 2>/dev/null || echo "  CLIP model will download on first use."
}

# ── Verify ──
verify() {
    echo ""
    echo "Verifying installation..."
    venv/bin/python -c "from flask import Flask; from PIL import Image; print('  Flask + Pillow: OK')" 2>/dev/null || echo "  Flask + Pillow: FAILED"
    venv/bin/python -c "import openpyxl; print('  Excel parser: OK')" 2>/dev/null || echo "  Excel parser: FAILED"
    venv/bin/python -c "import ddgs; print('  DuckDuckGo: OK')" 2>/dev/null || echo "  DuckDuckGo: FAILED"
    venv/bin/python -c "import torch; print('  PyTorch: OK')" 2>/dev/null || echo "  PyTorch: FAILED"
    venv/bin/python -c "import open_clip; print('  CLIP: OK')" 2>/dev/null || echo "  CLIP: FAILED"
}

# ── Run ──
install_python
install_system_deps
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
