"""
build.py — Virtual Couch Build Script
Run this on the target platform to produce a standalone executable.

Usage:
    python build.py

Outputs:
    dist/VirtualCouch          (macOS / Linux)
    dist/VirtualCouch.exe      (Windows)
"""

import subprocess
import sys
import platform
import os
import shutil

APP_NAME    = "VirtualCouch"
ENTRY       = "virtual_couch.py"
ICON_WIN    = "icon.ico"   # optional — place icon files next to this script
ICON_MAC    = "icon.icns"  # optional
ICON_LINUX  = "icon.png"   # optional

def run(cmd):
    print(f"\n>>> {' '.join(cmd)}\n")
    result = subprocess.run(cmd, check=True)
    return result

def ensure_pyinstaller():
    try:
        import PyInstaller
    except ImportError:
        print("PyInstaller not found — installing…")
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])

def build():
    ensure_pyinstaller()

    os_name = platform.system()
    print(f"Building for {os_name} ({platform.machine()})")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",          # no console window on Windows/macOS
        f"--name={APP_NAME}",
        "--clean",
    ]

    # Hidden imports required by aiortc / pynput
    hidden = [
        "aiortc",
        "aiortc.codecs",
        "aiortc.contrib.signaling",
        "pynput.keyboard._xorg",
        "pynput.keyboard._win32",
        "pynput.keyboard._darwin",
        "pynput.mouse._xorg",
        "pynput.mouse._win32",
        "pynput.mouse._darwin",
        "customtkinter",
        "aiohttp",
        "av",
        "google.protobuf",
    ]
    for h in hidden:
        cmd += ["--hidden-import", h]

    # Collect entire packages that use dynamic loading
    for pkg in ["aiortc", "customtkinter", "pynput"]:
        cmd += ["--collect-all", pkg]

    # Platform-specific icon
    if os_name == "Windows" and os.path.exists(ICON_WIN):
        cmd += [f"--icon={ICON_WIN}"]
    elif os_name == "Darwin" and os.path.exists(ICON_MAC):
        cmd += [f"--icon={ICON_MAC}"]
    elif os_name == "Linux" and os.path.exists(ICON_LINUX):
        cmd += [f"--icon={ICON_LINUX}"]

    # macOS: bundle as .app
    if os_name == "Darwin":
        cmd.append("--windowed")   # already set but harmless

    cmd.append(ENTRY)
    run(cmd)

    # ── Report output ──────────────────────────────────────────────────────────
    dist_dir = os.path.join("dist")
    exe = APP_NAME + (".exe" if os_name == "Windows" else "")
    out = os.path.join(dist_dir, exe)

    if os.path.exists(out):
        size_mb = os.path.getsize(out) / (1024 * 1024)
        print(f"\n✅ Build complete!")
        print(f"   Output : {os.path.abspath(out)}")
        print(f"   Size   : {size_mb:.1f} MB")
    else:
        # macOS .app bundle
        app_bundle = os.path.join(dist_dir, APP_NAME + ".app")
        if os.path.exists(app_bundle):
            print(f"\n✅ Build complete!")
            print(f"   Output : {os.path.abspath(app_bundle)}")
        else:
            print("\n⚠️  Build finished but output not found — check dist/ folder.")

    print("\nNOTES:")
    if os_name == "Darwin":
        print("  macOS: Right-click → Open the first time (Gatekeeper).")
        print("  Grant Accessibility & Input Monitoring in System Settings > Privacy.")
    elif os_name == "Windows":
        print("  Windows: Run as Administrator if input simulation doesn't work.")
        print("  Antivirus may flag the .exe — add an exclusion if needed.")
    elif os_name == "Linux":
        print("  Linux: chmod +x dist/VirtualCouch && ./dist/VirtualCouch")
        print("  If mouse fails, ensure libxtst is installed: sudo apt install libxtst6")

if __name__ == "__main__":
    build()
