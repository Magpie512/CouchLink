#!/usr/bin/env python3
"""
couchlink.py
────────────
Friendly CLI launcher for CouchLink.
Wraps the compiled C++ host/controller binaries with
a guided setup wizard so you don't have to memorize arguments.

Usage:
    python3 couchlink.py host       # host mode (receives input)
    python3 couchlink.py controller # controller mode (sends input)
    python3 couchlink.py relay      # run the relay server
    python3 couchlink.py build      # compile the C++ binaries
    python3 couchlink.py genid      # generate a random session ID
"""

import argparse
import os
import platform
import random
import subprocess
import sys

BANNER = r"""
   ____                 _     _     _       _
  / ___|___  _   _  ___| |__ | |   (_)_ __ | | __
 | |   / _ \| | | |/ __| '_ \| |   | | '_ \| |/ /
 | |__| (_) | |_| | (__| | | | |___| | | | |   <
  \____\___/ \__,_|\___|_| |_|_____|_|_| |_|_|\_\

          Virtual couch · share controllers online
"""

def detect_os():
    s = platform.system()
    return {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(s, "unknown")

def binary_name(role: str) -> str:
    suffix = ".exe" if detect_os() == "windows" else ""
    return os.path.join(os.path.dirname(__file__),
                        "build", f"couchlink_{role}{suffix}")

def gen_session_id() -> str:
    return f"{random.randint(0x10000000, 0xFFFFFFFF):08x}"

def run_build():
    print("[build] Compiling CouchLink C++ binaries...\n")
    build_dir = os.path.join(os.path.dirname(__file__), "build")
    os.makedirs(build_dir, exist_ok=True)

    cmake_cmd = ["cmake", "..", "-DCMAKE_BUILD_TYPE=Release"]
    make_cmd  = ["cmake", "--build", ".", "--config", "Release"]

    try:
        subprocess.run(cmake_cmd, cwd=build_dir, check=True)
        subprocess.run(make_cmd,  cwd=build_dir, check=True)
        print("\n[build] Done! Binaries in ./build/")
    except subprocess.CalledProcessError as e:
        print(f"\n[build] Failed: {e}")
        print("Make sure cmake and a C++ compiler are installed.")
        sys.exit(1)
    except FileNotFoundError:
        print("[build] cmake not found. Install cmake (https://cmake.org) and try again.")
        sys.exit(1)

def run_host(args):
    print(BANNER)
    port       = args.port or input("Port to listen on [9000]: ").strip() or "9000"
    session_id = args.session or input(
        f"Session ID (hex) [press Enter to generate]: ").strip() or gen_session_id()

    print(f"\n[host] Your session ID: {session_id}")
    print(f"[host] Share this with your friend along with your IP address.\n")

    bin_path = binary_name("host")
    if not os.path.isfile(bin_path):
        print(f"[host] Binary not found at {bin_path}")
        print("[host] Run:  python3 couchlink.py build  first.\n")
        sys.exit(1)

    try:
        subprocess.run([bin_path, str(port), session_id])
    except KeyboardInterrupt:
        print("\n[host] Stopped.")

def run_controller(args):
    print(BANNER)
    host       = args.host or input("Host IP address (or relay IP): ").strip()
    port       = args.port or input("Port [9000]: ").strip() or "9000"
    session_id = args.session or input("Session ID (hex): ").strip()

    if not session_id:
        print("[ctrl] Session ID is required.")
        sys.exit(1)

    bin_path = binary_name("controller")
    if not os.path.isfile(bin_path):
        print(f"[ctrl] Binary not found at {bin_path}")
        print("[ctrl] Run:  python3 couchlink.py build  first.\n")
        sys.exit(1)

    print(f"\n[ctrl] Connecting to {host}:{port} with session {session_id}\n")
    try:
        subprocess.run([bin_path, host, str(port), session_id])
    except KeyboardInterrupt:
        print("\n[ctrl] Stopped.")

def run_relay(args):
    print(BANNER)
    port    = args.port or input("Relay port [9000]: ").strip() or "9000"
    timeout = args.timeout or "30"

    relay_path = os.path.join(os.path.dirname(__file__), "relay", "couchlink_relay.py")
    print(f"[relay] Starting relay on port {port}...\n")
    try:
        subprocess.run([sys.executable, relay_path,
                        "--port", str(port), "--timeout", str(timeout)])
    except KeyboardInterrupt:
        print("\n[relay] Stopped.")

def main():
    parser = argparse.ArgumentParser(
        prog="couchlink",
        description="CouchLink — virtual couch for input sharing",
    )
    sub = parser.add_subparsers(dest="mode")

    # host
    p_host = sub.add_parser("host", help="Receive input from a controller")
    p_host.add_argument("--port",    type=int, help="UDP port to listen on (default: 9000)")
    p_host.add_argument("--session", type=str, help="Session ID hex string")

    # controller
    p_ctrl = sub.add_parser("controller", help="Send your input to a host")
    p_ctrl.add_argument("--host",    type=str, help="Host IP address")
    p_ctrl.add_argument("--port",    type=int, help="UDP port (default: 9000)")
    p_ctrl.add_argument("--session", type=str, help="Session ID hex string")

    # relay
    p_relay = sub.add_parser("relay", help="Run a relay server for internet play")
    p_relay.add_argument("--port",    type=int,   help="Port (default: 9000)")
    p_relay.add_argument("--timeout", type=float, help="Session timeout in seconds (default: 30)")

    # build
    sub.add_parser("build", help="Compile the C++ host/controller binaries")

    # genid
    sub.add_parser("genid", help="Generate a random session ID")

    args = parser.parse_args()

    if args.mode == "host":
        run_host(args)
    elif args.mode == "controller":
        run_controller(args)
    elif args.mode == "relay":
        run_relay(args)
    elif args.mode == "build":
        run_build()
    elif args.mode == "genid":
        sid = gen_session_id()
        print(f"Session ID: {sid}")
        print("Share this with both players before connecting.")
    else:
        print(BANNER)
        parser.print_help()

if __name__ == "__main__":
    main()
