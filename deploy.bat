@echo off
:: ============================================================
:: Image Scraper - Windows Deploy Script
:: ============================================================
:: Usage: double-click or run in cmd: deploy.bat
:: Requirements: Python 3.10+ installed (python.org)
::   IMPORTANT: Check "Add Python to PATH" during install!
:: ============================================================

echo ========================================
echo   Image Scraper - Setup ^& Deploy
echo ========================================
echo.

cd /d "%~dp0"

:: ── Check Python ──
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo ERROR: Python not found!
    echo.
    echo Please install Python from https://python.org
    echo.
    echo IMPORTANT: During installation, check the box:
    echo   [x] Add python.exe to PATH
    echo.
    echo After installing, close this window and run deploy.bat again.
    echo.
    pause
    exit /b 1
)

echo Python found:
python --version
echo.

:: ── Create venv ──
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo Virtual environment created.
) else (
    echo Virtual environment already exists.
)

:: ── Install core dependencies ──
echo.
echo [1/4] Installing core dependencies...
venv\Scripts\python.exe -m pip install --upgrade pip --quiet
venv\Scripts\python.exe -m pip install --quiet flask requests Pillow "numpy<2" ddgs openpyxl python-docx pymupdf

if %errorlevel% neq 0 (
    echo WARNING: Some core dependencies failed to install.
    echo Trying again without --quiet flag...
    venv\Scripts\python.exe -m pip install flask requests Pillow "numpy<2" ddgs openpyxl python-docx pymupdf
)

:: ── Install AI dependencies (CLIP) ──
echo.
echo [2/4] Installing AI relevance checker (CLIP + PyTorch)...
echo   This may take a few minutes on first install (~500MB)...
venv\Scripts\python.exe -m pip install --quiet torch torchvision open-clip-torch sentence-transformers

if %errorlevel% neq 0 (
    echo.
    echo WARNING: AI dependencies failed to install.
    echo The scraper will still work but without AI relevance checking.
    echo You can install them manually later with:
    echo   venv\Scripts\python.exe -m pip install torch torchvision open-clip-torch sentence-transformers
    echo.
)

:: ── Pre-download CLIP model ──
echo.
echo [3/4] Pre-downloading CLIP model (first time only)...
venv\Scripts\python.exe -c "import open_clip; open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k'); print('CLIP model ready!')" 2>nul
if %errorlevel% neq 0 (
    echo CLIP model will download on first use.
)

:: ── Create output directory ──
echo.
echo [4/4] Creating output directory...
if not exist "output" mkdir output
if not exist "static" (
    echo WARNING: static/ folder not found. Make sure style.css and app.js are in static/
)

:: ── Verify installation ──
echo.
echo Verifying installation...
venv\Scripts\python.exe -c "from flask import Flask; from PIL import Image; print('  Flask + Pillow: OK')" 2>nul
venv\Scripts\python.exe -c "import openpyxl; print('  Excel parser: OK')" 2>nul
venv\Scripts\python.exe -c "import ddgs; print('  DuckDuckGo: OK')" 2>nul
venv\Scripts\python.exe -c "import torch; print('  PyTorch: OK')" 2>nul
venv\Scripts\python.exe -c "import open_clip; print('  CLIP: OK')" 2>nul

:: ── Summary ──
echo.
echo ========================================
echo   Setup complete!
echo ========================================
echo.
echo   Start the server:
echo     venv\Scripts\python.exe app.py --port 8080
echo.
echo   Then open in browser:
echo     http://localhost:8080
echo.
echo   For production (auto-restart, multi-thread):
echo     venv\Scripts\python.exe -m pip install waitress
echo     venv\Scripts\python.exe -m waitress --port=8080 --threads=4 app:app
echo.
echo ========================================
echo.
pause
