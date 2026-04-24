#!/usr/bin/env python3
"""
build_gui.py
────────────
Compiles couchlink_gui.py into a standalone executable using PyInstaller.
Run this once on each platform to produce:
  Windows  →  dist/CouchLink.exe
  macOS    →  dist/CouchLink.app
  Linux    →  dist/CouchLink  (single binary)

Usage:
    python3 build_gui.py
"""

import subprocess
import sys
import os
import platform

def install_pyinstaller():
    print("[build] Checking PyInstaller...")
    try:
        import PyInstaller
        print(f"[build] PyInstaller {PyInstaller.__version__} found.")
    except ImportError:
        print("[build] Installing PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"],
                       check=True)

def build():
    os_name = platform.system()
    script  = os.path.join(os.path.dirname(__file__), "couchlink_gui.py")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",           # no console window (use --console to debug)
        "--name", "CouchLink",
        "--clean",
    ]

    # Platform icon
    if os_name == "Windows":
        icon = os.path.join(os.path.dirname(__file__), "icon.ico")
        if os.path.isfile(icon):
            cmd += ["--icon", icon]
    elif os_name == "Darwin":
        icon = os.path.join(os.path.dirname(__file__), "icon.icns")
        if os.path.isfile(icon):
            cmd += ["--icon", icon]

    cmd.append(script)

    print(f"[build] Building for {os_name}...")
    print(f"[build] Command: {' '.join(cmd)}\n")
    subprocess.run(cmd, check=True)

    out = os.path.join("dist", "CouchLink")
    if os_name == "Windows":
        out += ".exe"
    elif os_name == "Darwin":
        out += ".app"

    print(f"\n[build] Done!")
    print(f"[build] Executable: {os.path.abspath(out)}")
    print()
    print("  IMPORTANT: Put the CouchLink executable in the same folder as")
    print("  your compiled C++ binaries (couchlink_host / couchlink_controller).")
    print("  The GUI will look for them in the same directory as itself.")

if __name__ == "__main__":
    install_pyinstaller()
    build()
