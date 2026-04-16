@echo off
:: ============================================================
:: Image Scraper - Deploy Script for Windows
:: ============================================================
:: Usage: double-click or run: deploy-windows.bat
:: Installs Python automatically if not found
:: ============================================================

echo ========================================
echo   Image Scraper - Windows Deploy
echo ========================================
echo.

cd /d "%~dp0"

:: ── [1/5] Check Python ──
echo [1/5] Checking Python 3.10+...

:: Try python
where python >nul 2>nul
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set PYVER=%%v
    echo   Found python %PYVER%
    for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
        if %%a GEQ 3 if %%b GEQ 10 (
            set PYTHON=python
            goto :python_ok
        )
    )
)

:: Try py launcher
where py >nul 2>nul
if %errorlevel% equ 0 (
    for /f "tokens=*" %%v in ('py -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2^>nul') do set PYVER=%%v
    echo   Found py %PYVER%
    for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
        if %%a GEQ 3 if %%b GEQ 10 (
            set PYTHON=py
            goto :python_ok
        )
    )
)

:: Python not found - download and install
echo.
echo   Python 3.10+ not found. Downloading installer...
echo.

:: Download Python installer
powershell -Command "& {Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe' -OutFile '%TEMP%\python-installer.exe'}"

if not exist "%TEMP%\python-installer.exe" (
    echo   ERROR: Failed to download Python installer.
    echo   Please install manually from https://python.org
    echo   IMPORTANT: Check "Add python.exe to PATH" during install!
    pause
    exit /b 1
)

echo   Running Python installer...
echo   IMPORTANT: Check "Add python.exe to PATH" when prompted!
echo.
start /wait "" "%TEMP%\python-installer.exe" InstallAllUsers=0 PrependPath=1 Include_test=0

:: Refresh PATH
set "PATH=%LOCALAPPDATA%\Programs\Python\Python312\;%LOCALAPPDATA%\Programs\Python\Python312\Scripts\;%PATH%"

:: Verify
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo   ERROR: Python still not found after install.
    echo   Please close this window, reopen a new terminal, and run deploy-windows.bat again.
    echo   If it still fails, install Python manually from https://python.org
    pause
    exit /b 1
)
set PYTHON=python

:python_ok
echo   Using: %PYTHON%
%PYTHON% --version
echo.

:: ── [2/5] Create venv ──
echo [2/5] Setting up virtual environment...

if exist "venv\Scripts\python.exe" (
    :: Check if venv works
    venv\Scripts\python.exe -c "import sys" >nul 2>nul
    if %errorlevel% neq 0 (
        echo   venv broken, recreating...
        rmdir /s /q venv
    ) else (
        echo   venv already exists - OK
        goto :venv_ok
    )
)

%PYTHON% -m venv venv
if %errorlevel% neq 0 (
    echo   ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)
echo   Created venv

:venv_ok
echo.

:: ── [3/5] Install dependencies ──
echo [3/5] Installing Python dependencies...

echo   Core dependencies from requirements.txt...
venv\Scripts\python.exe -m pip install --upgrade pip --quiet 2>nul
venv\Scripts\python.exe -m pip install --quiet -r requirements.txt 2>nul

if %errorlevel% neq 0 (
    echo   Retrying without --quiet...
    venv\Scripts\python.exe -m pip install -r requirements.txt
)

echo   AI (PyTorch, CLIP) - this may take a few minutes (~500MB)...
venv\Scripts\python.exe -m pip install --quiet torch torchvision open-clip-torch sentence-transformers 2>nul

if %errorlevel% neq 0 (
    echo.
    echo   WARNING: AI dependencies failed. Scraper will work without AI relevance check.
    echo   Install manually later:
    echo     venv\Scripts\python.exe -m pip install torch torchvision open-clip-torch sentence-transformers
)

echo.

:: ── [4/5] Pre-download CLIP model ──
echo [4/5] Pre-downloading CLIP model (first time only)...
venv\Scripts\python.exe -c "import open_clip; open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k'); print('  CLIP model ready!')" 2>nul
if %errorlevel% neq 0 echo   CLIP model will download on first use.
echo.

:: ── [5/5] Verify ──
echo [5/5] Verifying installation...
if not exist "output" mkdir output
if not exist "static" echo   WARNING: static/ folder not found!

venv\Scripts\python.exe -c "from flask import Flask; from PIL import Image; print('  Flask + Pillow: OK')" 2>nul || echo   Flask + Pillow: FAILED
venv\Scripts\python.exe -c "import openpyxl; print('  Excel parser: OK')" 2>nul || echo   Excel parser: FAILED
venv\Scripts\python.exe -c "import ddgs; print('  DuckDuckGo: OK')" 2>nul || echo   DuckDuckGo: FAILED
venv\Scripts\python.exe -c "import torch; print('  PyTorch: OK')" 2>nul || echo   PyTorch: FAILED
venv\Scripts\python.exe -c "import open_clip; print('  CLIP: OK')" 2>nul || echo   CLIP: FAILED

:: ── Summary ──
echo.
echo ========================================
echo   Setup complete!
echo ========================================
echo.
echo   Start the server:
echo     venv\Scripts\python.exe app.py
echo.
echo   Then open in browser:
echo     http://localhost:8787
echo.
echo ========================================
echo.
pause
