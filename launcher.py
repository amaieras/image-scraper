#!/usr/bin/env python3
"""
Image Scraper Launcher
======================
One-click launcher that:
  1. Finds or installs Python 3.10+
  2. Creates a virtual environment
  3. Installs all dependencies (including CLIP/PyTorch)
  4. Starts the Flask server
  5. Opens the browser automatically

Usage:
  - Double-click the compiled binary (or run: python launcher.py)
  - First run takes 5-10 min (downloads ~800MB of dependencies)
  - Subsequent runs start in seconds
"""

import os
import sys
import subprocess
import platform
import shutil
import time
import webbrowser
import threading
import signal
import socket

# ─── CONFIG ──────────────────────────────────────────────────────────────────

PORT = 8787
HOST = "0.0.0.0"
APP_NAME = "Image Scraper"
APP_FILE = "app.py"

# Dependencies to install in two phases:
# Phase 1: Core (fast, small)
CORE_DEPS = [
    "flask>=3.0.0",
    "requests>=2.31.0",
    "Pillow>=10.0.0",
    "numpy>=1.24.0,<2",
    "ddgs>=7.0.0",
    "rich>=13.0.0",
    "openpyxl>=3.1.0",
    "python-docx>=1.0.0",
    "pymupdf>=1.23.0",
    "beautifulsoup4>=4.12.0",
    "extruct>=0.17.0",
    "googlesearch-python>=1.2.0",
    "gunicorn>=21.2.0",
]

# Phase 2: AI / CLIP (large, takes longer)
AI_DEPS = [
    "torch",
    "torchvision",
    "open-clip-torch",
    "sentence-transformers",
    "easyocr",
]

# ─── HELPERS ─────────────────────────────────────────────────────────────────

SYSTEM = platform.system()  # "Windows", "Darwin", "Linux"
IS_WIN = SYSTEM == "Windows"
IS_MAC = SYSTEM == "Darwin"

# When running as a PyInstaller bundle, _MEIPASS is set
if getattr(sys, 'frozen', False):
    # Running from compiled binary
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # Running as script
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

VENV_DIR = os.path.join(BASE_DIR, "venv")
if IS_WIN:
    VENV_PYTHON = os.path.join(VENV_DIR, "Scripts", "python.exe")
    VENV_PIP = os.path.join(VENV_DIR, "Scripts", "pip.exe")
else:
    VENV_PYTHON = os.path.join(VENV_DIR, "bin", "python")
    VENV_PIP = os.path.join(VENV_DIR, "bin", "pip")


def print_header(text):
    width = 50
    print()
    print("=" * width)
    print(f"  {text}")
    print("=" * width)
    print()


def print_step(n, total, text):
    print(f"  [{n}/{total}] {text}")


def find_system_python():
    """Find a suitable Python 3.10+ on the system."""
    candidates = ["python3", "python", "py"]
    if IS_WIN:
        candidates = ["python", "py", "python3"]

    for cmd in candidates:
        path = shutil.which(cmd)
        if not path:
            continue
        try:
            result = subprocess.run(
                [path, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                major, minor = map(int, version.split("."))
                if major >= 3 and minor >= 10:
                    return path, version
        except Exception:
            continue

    return None, None


def is_port_in_use(port):
    """Check if a port is already in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def wait_for_server(port, timeout=30):
    """Wait until the server is responding."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use(port):
            return True
        time.sleep(0.5)
    return False


def run_pip_install(packages, label="dependencies"):
    """Install packages using pip in the venv."""
    print(f"\n  Installing {label}...")
    cmd = [VENV_PIP, "install", "--upgrade"] + packages
    result = subprocess.run(cmd, capture_output=False)
    if result.returncode != 0:
        print(f"  WARNING: Some {label} may have failed to install.")
        print(f"  The app may still work without them.")
        return False
    return True


def auto_install_python_windows():
    """Download and install Python automatically on Windows."""
    import tempfile
    installer_url = "https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe"
    installer_path = os.path.join(tempfile.gettempdir(), "python-installer.exe")

    print("  Python 3.10+ not found. Downloading installer...")
    print(f"  URL: {installer_url}")
    print()

    # Download using PowerShell
    ps_cmd = f"Invoke-WebRequest -Uri '{installer_url}' -OutFile '{installer_path}'"
    result = subprocess.run(["powershell", "-Command", ps_cmd])
    if result.returncode != 0 or not os.path.isfile(installer_path):
        print("  ERROR: Failed to download Python installer.")
        return None, None

    print("  Running Python installer...")
    print('  IMPORTANT: Check "Add python.exe to PATH" when prompted!')
    print()

    # Run installer — InstallAllUsers=0 (user only), PrependPath=1 (add to PATH)
    subprocess.run([
        installer_path,
        "InstallAllUsers=0", "PrependPath=1", "Include_test=0"
    ])

    # Refresh PATH to pick up new Python
    local_app = os.environ.get("LOCALAPPDATA", "")
    for ver in ["Python312", "Python313", "Python311"]:
        py_dir = os.path.join(local_app, "Programs", "Python", ver)
        if os.path.isdir(py_dir):
            os.environ["PATH"] = py_dir + ";" + os.path.join(py_dir, "Scripts") + ";" + os.environ["PATH"]

    # Try finding Python again
    return find_system_python()


def auto_install_python_mac():
    """Install Python via Homebrew on macOS."""
    # Check if Homebrew is installed
    brew_path = shutil.which("brew")
    if not brew_path:
        print("  Homebrew not found. Installing Homebrew first...")
        result = subprocess.run(
            ["/bin/bash", "-c",
             'NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'],
        )
        # Add brew to PATH for Apple Silicon
        brew_paths = ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]
        for bp in brew_paths:
            if os.path.isfile(bp):
                brew_path = bp
                os.environ["PATH"] = os.path.dirname(bp) + ":" + os.environ["PATH"]
                break

    if not brew_path:
        print("  ERROR: Could not install Homebrew.")
        return None, None

    print("  Installing Python 3.12 via Homebrew...")
    subprocess.run([brew_path, "install", "python@3.12"])

    return find_system_python()


def auto_install_python_linux():
    """Install Python on Linux (Debian/Ubuntu/Fedora)."""
    # Try apt (Debian/Ubuntu)
    if shutil.which("apt-get"):
        print("  Installing Python via apt...")
        subprocess.run(["sudo", "apt-get", "update", "-y"])
        subprocess.run(["sudo", "apt-get", "install", "-y", "python3", "python3-venv", "python3-pip"])
        return find_system_python()

    # Try dnf (Fedora)
    if shutil.which("dnf"):
        print("  Installing Python via dnf...")
        subprocess.run(["sudo", "dnf", "install", "-y", "python3", "python3-pip"])
        return find_system_python()

    return None, None


# ─── SETUP ───────────────────────────────────────────────────────────────────

def setup():
    """Full setup: check Python, create venv, install deps."""
    total_steps = 4

    # Step 1: Find Python
    print_step(1, total_steps, "Checking Python...")

    # If venv already exists and works, skip Python check
    if os.path.isfile(VENV_PYTHON):
        try:
            result = subprocess.run(
                [VENV_PYTHON, "-c", "import flask; print('ok')"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and "ok" in result.stdout:
                print(f"  Virtual environment OK ({VENV_DIR})")
                print_step(2, total_steps, "Skipping (venv exists)")
                print_step(3, total_steps, "Skipping (deps installed)")

                # Still check if AI deps are installed
                print_step(4, total_steps, "Checking AI dependencies...")
                check_ai = subprocess.run(
                    [VENV_PYTHON, "-c", "import open_clip; print('ok')"],
                    capture_output=True, text=True, timeout=10
                )
                if check_ai.returncode != 0 or "ok" not in check_ai.stdout:
                    print("  CLIP not found — installing AI dependencies...")
                    print("  This may take a few minutes (~500MB download)")
                    run_pip_install(AI_DEPS, "AI/CLIP dependencies")
                else:
                    print("  AI dependencies OK")
                return True
        except Exception:
            pass  # venv broken, recreate

    # Need system Python to create venv
    python_path, python_ver = find_system_python()
    if not python_path:
        print()
        print("  Python 3.10+ not found. Attempting automatic install...")
        print()

        if IS_WIN:
            python_path, python_ver = auto_install_python_windows()
        elif IS_MAC:
            python_path, python_ver = auto_install_python_mac()
        else:
            python_path, python_ver = auto_install_python_linux()

        if not python_path:
            print()
            print("  ERROR: Automatic Python install failed.")
            print()
            if IS_WIN:
                print("  Please install manually from: https://www.python.org/downloads/")
                print('  IMPORTANT: Check "Add python.exe to PATH" during installation!')
            elif IS_MAC:
                print("  Please install manually:")
                print("    brew install python@3.12")
            else:
                print("  Please install manually:")
                print("    sudo apt install python3 python3-venv  (Ubuntu/Debian)")
                print("    sudo dnf install python3  (Fedora)")
            print()
            print("  After installing Python, run this launcher again.")
            input("\n  Press Enter to exit...")
            return False

    print(f"  Found Python {python_ver} at {python_path}")

    # Step 2: Create venv
    print_step(2, total_steps, "Creating virtual environment...")
    if os.path.isdir(VENV_DIR):
        print(f"  Removing broken venv...")
        shutil.rmtree(VENV_DIR, ignore_errors=True)

    result = subprocess.run([python_path, "-m", "venv", VENV_DIR])
    if result.returncode != 0:
        print("  ERROR: Failed to create virtual environment.")
        print("  Try installing python3-venv:")
        print("    sudo apt install python3-venv  (Ubuntu/Debian)")
        input("\n  Press Enter to exit...")
        return False
    print(f"  Created at {VENV_DIR}")

    # Step 3: Install core dependencies
    print_step(3, total_steps, "Installing core dependencies...")
    subprocess.run([VENV_PIP, "install", "--upgrade", "pip"], capture_output=True)
    if not run_pip_install(CORE_DEPS, "core dependencies"):
        print("  ERROR: Core dependencies failed. Cannot continue.")
        input("\n  Press Enter to exit...")
        return False

    # Step 4: Install AI dependencies
    print_step(4, total_steps, "Installing AI dependencies (PyTorch + CLIP)...")
    print("  This may take 5-10 minutes on first install (~800MB)")
    run_pip_install(AI_DEPS, "AI/CLIP dependencies")

    # Pre-download CLIP model
    print("\n  Pre-downloading CLIP model (~350MB, one time only)...")
    subprocess.run(
        [VENV_PYTHON, "-c",
         "import open_clip; open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k'); print('  CLIP model ready!')"],
        timeout=300
    )

    return True


# ─── LAUNCH ──────────────────────────────────────────────────────────────────

def launch():
    """Start the Flask server and open the browser."""
    app_path = os.path.join(BASE_DIR, APP_FILE)

    if not os.path.isfile(app_path):
        print(f"  ERROR: {APP_FILE} not found at {BASE_DIR}")
        print(f"  Make sure the launcher is in the same folder as {APP_FILE}")
        input("\n  Press Enter to exit...")
        return

    # Check if already running
    if is_port_in_use(PORT):
        print(f"\n  {APP_NAME} is already running on port {PORT}")
        url = f"http://localhost:{PORT}"
        print(f"  Opening {url}...")
        webbrowser.open(url)
        return

    print_header(f"Starting {APP_NAME}")
    print(f"  Server: http://localhost:{PORT}")
    print(f"  Press Ctrl+C to stop\n")

    # Start server in subprocess
    env = os.environ.copy()
    env["PORT"] = str(PORT)

    # Fix SSL certificates on Windows — ensure requests finds the cert bundle
    if IS_WIN:
        try:
            result = subprocess.run(
                [VENV_PYTHON, "-c", "import certifi; print(certifi.where())"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0 and result.stdout.strip():
                cert_path = result.stdout.strip()
                env.setdefault("SSL_CERT_FILE", cert_path)
                env.setdefault("REQUESTS_CA_BUNDLE", cert_path)
        except Exception:
            pass
    server_process = subprocess.Popen(
        [VENV_PYTHON, app_path, "--port", str(PORT)],
        cwd=BASE_DIR,
        env=env,
    )

    # Open browser after server is ready
    def open_browser():
        if wait_for_server(PORT, timeout=30):
            url = f"http://localhost:{PORT}"
            print(f"\n  Opening browser at {url}\n")
            webbrowser.open(url)
        else:
            print(f"\n  Server didn't start in time. Open http://localhost:{PORT} manually.\n")

    browser_thread = threading.Thread(target=open_browser, daemon=True)
    browser_thread.start()

    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print(f"\n\n  Stopping {APP_NAME}...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()
        print("  Stopped. Goodbye!")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, signal_handler)

    # Wait for server process — restart automatically if it exits cleanly
    try:
        while True:
            exit_code = server_process.wait()
            if exit_code != 0:
                print(f"\n  Server exited with code {exit_code}.")
                break
            # Exit code 0 = normal restart (e.g. after auto-update)
            print(f"\n  Restarting {APP_NAME}...")
            server_process = subprocess.Popen(
                [VENV_PYTHON, app_path, "--port", str(PORT)],
                cwd=BASE_DIR,
                env=env,
            )
    except KeyboardInterrupt:
        signal_handler(None, None)


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    os.chdir(BASE_DIR)

    print_header(f"{APP_NAME} Launcher")
    print(f"  Platform: {SYSTEM} ({platform.machine()})")
    print(f"  Location: {BASE_DIR}")

    if not setup():
        sys.exit(1)

    print("\n  Setup complete!")
    launch()


if __name__ == "__main__":
    main()
