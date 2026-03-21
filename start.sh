#!/bin/bash
# Image Scraper UI - One-click starter
cd "$(dirname "$0")"

echo "🔧 Setting up environment..."

# Recreate venv if broken
if ! python3 -c "import flask" 2>/dev/null && [ -d "venv" ]; then
    if ! ./venv/bin/python3 -c "import flask" 2>/dev/null; then
        echo "   Recreating virtual environment..."
        rm -rf venv
        python3 -m venv venv
    fi
fi

# Create venv if missing
if [ ! -d "venv" ]; then
    echo "   Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install --quiet flask numpy Pillow requests ddgs 2>/dev/null

echo ""
echo "✅ Ready! Starting server..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Open in browser: http://localhost:5000"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

python app.py --port 5000
