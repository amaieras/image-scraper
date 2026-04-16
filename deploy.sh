#!/bin/bash
# ============================================================
# Image Scraper - Deploy Script
# ============================================================
# Usage:
#   chmod +x deploy.sh
#   ./deploy.sh
#
# Requirements: Python 3.10+ installed on the server
# ============================================================

set -e

echo "========================================"
echo "  Image Scraper - Setup & Deploy"
echo "========================================"
echo ""

cd "$(dirname "$0")"

# ── Check Python ──
if command -v python3 &>/dev/null; then
    PYTHON=python3
elif command -v python &>/dev/null; then
    PYTHON=python
else
    echo "ERROR: Python 3.10+ is required but not found."
    echo "Install it with:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "  macOS:         brew install python@3.12"
    exit 1
fi

PY_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python found: $PYTHON ($PY_VERSION)"

# ── Create venv ──
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    $PYTHON -m venv venv
else
    echo "Virtual environment exists."
fi

source venv/bin/activate

# ── Install core dependencies ──
echo ""
echo "Installing core dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# ── Install AI dependencies (CLIP) ──
echo ""
echo "Installing AI relevance checker (CLIP + PyTorch)..."
echo "  This may take a few minutes on first install (~500MB)..."
pip install --quiet \
    torch \
    torchvision \
    open-clip-torch \
    sentence-transformers

# ── Install optional: background removal ──
read -p "Install AI background removal (rembg)? ~300MB extra [y/N]: " install_rembg
if [[ "$install_rembg" =~ ^[Yy]$ ]]; then
    echo "Installing rembg + onnxruntime..."
    pip install --quiet rembg onnxruntime
fi

# ── Pre-download CLIP model ──
echo ""
echo "Pre-downloading CLIP model (first time only)..."
$PYTHON -c "
import open_clip
model, _, preprocess = open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k')
print('CLIP model ready!')
" 2>/dev/null || echo "CLIP model will download on first use."

# ── Create output directory ──
mkdir -p output

# ── Summary ──
echo ""
echo "========================================"
echo "  Setup complete!"
echo "========================================"
echo ""
echo "  Start the server:"
echo "    source venv/bin/activate"
echo "    python app.py --port 8080"
echo ""
echo "  Then open: http://localhost:8080"
echo ""
echo "  For production (with gunicorn):"
echo "    pip install gunicorn"
echo "    gunicorn -w 2 --threads 4 -b 0.0.0.0:8080 app:app"
echo ""
echo "========================================"
