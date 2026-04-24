# CouchLink

Share your keyboard, mouse, and gamepad over the internet (like swapping a controller on a couch.)

## How It Works

```
[Controller machine]  ──UDP─>  [Host machine]
       captures input               injects input as if it were local
```

For internet play, a lightweight relay server sits in the middle:

```
[Controller] ──UDP─> [Relay Server] ──UDP─> [Host]
```

Both peers identify each other using a shared **session ID** (a hex number you generate once and share with your friend).

## Quick Start

### 1. Build the C++ binaries

```bash
# Install prerequisites first:
#   Windows : Visual Studio + CMake
#   macOS   : Xcode CLT (xcode-select --install) + CMake
#   Linux   : build-essential + cmake  (sudo apt install build-essential cmake)

python3 couchlink.py build
```

### 2. Generate a session ID

```bash
python3 couchlink.py genid
# Session ID: a3f19c2e
```

Share this ID with whoever you're playing with.

### 3a. LAN / Direct (same network or port-forwarded)

**Host machine** (receives input):
```bash
python3 couchlink.py host --port 9000 --session a3f19c2e
```

**Controller machine** (sends input):
```bash
python3 couchlink.py controller --host 192.168.1.100 --port 9000 --session a3f19c2e
```

### 3b. Internet play (relay server)

**On your VPS / server:**
```bash
python3 relay/couchlink_relay.py --port 9000
```

**Host machine:**
```bash
python3 couchlink.py host --port 9000 --session a3f19c2e
# Connect to relay instead of direct
```

**Controller machine:**
```bash
python3 couchlink.py controller --host your.relay.server.com --port 9000 --session a3f19c2e
```

---

## Platform Notes

### Windows
- Keyboard/mouse captured via **Raw Input API** (no admin required).
- Gamepad capture via **XInput** (Xbox controllers, Steam Input, etc.).
- Gamepad *injection* requires the [ViGEm Bus Driver](https://github.com/nefarius/ViGEmBus) (free, open-source). Install it first.

### macOS
- Keyboard/mouse captured via **CGEvent tap**.
  - Go to **System Settings → Privacy & Security → Accessibility** and grant permission to the terminal / app.
- Gamepad capture via **IOHIDManager**.
- Gamepad injection requires [Karabiner-DriverKit-VirtualHIDDevice](https://github.com/pqrs-org/Karabiner-DriverKit-VirtualHIDDevice).

### Linux
- All input captured from `/dev/input/event*` via **evdev**.
  - Add your user to the `input` group: `sudo usermod -aG input $USER`
- Input injected via **uinput** (virtual device).
  - Run as root, or: `sudo setcap cap_sys_admin+eip ./build/couchlink_host`

---

## Security

The session ID acts as a simple shared secret. Every packet is tagged with it, and the host drops packets with the wrong ID.

**For stronger security**, consider:
- Running the relay behind a VPN (Tailscale, WireGuard).
- Adding HMAC packet signing (replace `session_id` field with a per-packet HMAC-SHA256 token).

---

## Project Structure

```
couchlink/
├── couchlink.py          # Python CLI launcher (friendly wrapper)
├── CMakeLists.txt        # Cross-platform C++ build
├── core/
│   ├── input_core.hpp    # InputEvent wire format + enums
│   ├── capture.hpp       # Platform input capture (Win/Mac/Linux)
│   ├── inject.hpp        # Platform input injection (Win/Mac/Linux)
│   └── net.hpp           # UDP sender + receiver
├── host/
│   └── main.cpp          # Host binary (receives + injects)
├── controller/
│   └── main.cpp          # Controller binary (captures + sends)
└── relay/
    └── couchlink_relay.py  # Python UDP relay server
```

---

## Latency Tips

- **UDP** is used throughout — no head-of-line blocking.
- On LAN, expect **<1ms** round-trip.
- Over the internet, latency depends on distance to the relay server. Pick a relay geographically close to both players.
- The gamepad poll rate is **~240Hz** on Windows (XInput) and configurable on Linux (evdev event-driven).

---

## License

MIT — do whatever you want.
