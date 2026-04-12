#!/usr/bin/env python3
"""
Build standalone launcher binaries for Windows, macOS, and Linux.

Prerequisites:
    pip install pyinstaller

Usage:
    python build-launcher.py          # Build for current platform
    python build-launcher.py --all    # Instructions for all platforms

Each platform must be built ON that platform (PyInstaller can't cross-compile).

Output:
    dist/ImageScraper.exe      (Windows)
    dist/ImageScraper          (macOS / Linux)
"""

import os
import sys
import subprocess
import platform
import shutil

SYSTEM = platform.system()
SCRIPT = "launcher.py"
APP_NAME = "ImageScraper"


def check_pyinstaller():
    """Ensure PyInstaller is installed."""
    try:
        import PyInstaller
        print(f"  PyInstaller {PyInstaller.__version__} found")
        return True
    except ImportError:
        print("  PyInstaller not found. Installing...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"])
        return True


def build():
    """Build the launcher binary for the current platform."""
    print(f"\n  Building {APP_NAME} for {SYSTEM}...\n")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                    # Single binary
        "--name", APP_NAME,             # Output name
        "--console",                    # Show console (needed for setup output)
        "--noconfirm",                  # Overwrite without asking
        "--clean",                      # Clean build cache
        SCRIPT,
    ]

    # Add icon if available
    if SYSTEM == "Windows" and os.path.isfile("static/icon.ico"):
        cmd.extend(["--icon", "static/icon.ico"])
    elif SYSTEM == "Darwin" and os.path.isfile("static/icon.icns"):
        cmd.extend(["--icon", "static/icon.icns"])

    result = subprocess.run(cmd)

    if result.returncode == 0:
        if SYSTEM == "Windows":
            binary = os.path.join("dist", f"{APP_NAME}.exe")
        else:
            binary = os.path.join("dist", APP_NAME)

        if os.path.isfile(binary):
            size_mb = os.path.getsize(binary) / (1024 * 1024)
            print(f"\n  Build successful!")
            print(f"  Output: {os.path.abspath(binary)}")
            print(f"  Size:   {size_mb:.1f} MB")
            print(f"\n  To distribute, copy these files to the client:")
            print(f"    {binary}")
            print(f"    app.py")
            print(f"    index.html")
            print(f"    static/          (folder)")
            print(f"    config.json")
            print(f"    requirements.txt")
        else:
            print(f"\n  ERROR: Binary not found at {binary}")
    else:
        print(f"\n  ERROR: Build failed with code {result.returncode}")


def show_all_instructions():
    """Show how to build for all platforms."""
    print("""
  ┌─────────────────────────────────────────────────────────┐
  │  PyInstaller can't cross-compile.                       │
  │  Build each binary ON the target platform.              │
  └─────────────────────────────────────────────────────────┘

  === Windows (build on Windows) ===
    pip install pyinstaller
    python build-launcher.py

  === macOS (build on macOS) ===
    pip3 install pyinstaller
    python3 build-launcher.py

  === Linux (build on Linux) ===
    pip3 install pyinstaller
    python3 build-launcher.py

  Or use GitHub Actions to build all three automatically
  (see .github/workflows/build.yml if available).

  After building on each platform, collect:
    dist/ImageScraper.exe    (from Windows build)
    dist/ImageScraper         (from macOS build)
    dist/ImageScraper         (from Linux build)
""")


def create_distribution_zip():
    """Create a distribution package with the binary + required files."""
    dist_dir = f"dist/{APP_NAME}-{SYSTEM.lower()}"
    os.makedirs(dist_dir, exist_ok=True)

    # Copy binary
    if SYSTEM == "Windows":
        src_binary = f"dist/{APP_NAME}.exe"
    else:
        src_binary = f"dist/{APP_NAME}"

    if not os.path.isfile(src_binary):
        print(f"  Binary not found. Run build first.")
        return

    shutil.copy2(src_binary, dist_dir)

    # Copy app files
    files_to_copy = ["app.py", "index.html", "config.json", "requirements.txt"]
    for f in files_to_copy:
        if os.path.isfile(f):
            shutil.copy2(f, dist_dir)

    # Copy static folder
    if os.path.isdir("static"):
        shutil.copytree("static", os.path.join(dist_dir, "static"), dirs_exist_ok=True)

    # Create the zip
    zip_name = f"dist/{APP_NAME}-{SYSTEM.lower()}"
    shutil.make_archive(zip_name, "zip", "dist", f"{APP_NAME}-{SYSTEM.lower()}")
    zip_path = f"{zip_name}.zip"
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)

    print(f"\n  Distribution package created:")
    print(f"  {os.path.abspath(zip_path)} ({size_mb:.1f} MB)")
    print(f"\n  Send this zip to the client. They extract and double-click {APP_NAME}.")


if __name__ == "__main__":
    print(f"\n  {APP_NAME} — Build Launcher Binary")
    print(f"  Platform: {SYSTEM} ({platform.machine()})\n")

    if "--all" in sys.argv:
        show_all_instructions()
        sys.exit(0)

    if not check_pyinstaller():
        sys.exit(1)

    build()

    if "--zip" in sys.argv:
        create_distribution_zip()
    else:
        print(f"\n  Tip: Run with --zip to create a ready-to-send package:")
        print(f"    python build-launcher.py --zip\n")
