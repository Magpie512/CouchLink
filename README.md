# Internet's Couch

> Swap keyboard & mouse control between two machines over the internet — like passing a controller on a couch.

---

## How It Works

```demo
[Controller Machine]                    [Host Machine]
  pynput captures                          pynput injects
  keyboard + mouse  ──── WebRTC ────?      kbm 
  events                DataChannel        into OS
```

- **No port forwarding needed** — Google & Cloudflare STUN servers handle NAT traversal.
- **Copy-paste signaling** — no server required. Exchange two text blobs (offer/answer) via Discord, chat, etc.
- **Sub-20ms latency** on good broadband (UDP-like DataChannel).

---

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the app

```bash
python virtual_couch.py
```

---

## Connection Flow

### Host (the machine that will *receive* inputs)

1. Click **Host**.
2. Click **Generate Offer** — a long code appears in the box.
3. Copy it and send to your friend (Discord, iMessage, etc.).
4. When they send back an *Answer* code, paste it in the box.
5. Click **Accept Answer** — done!

### Controller (the machine that will *send* inputs)

1. Click **Controller**.
2. Paste the Host's Offer code into the box.
3. Click **Generate Answer** — a code appears.
4. Copy it and send back to the Host.
5. Once they accept, your keyboard and mouse control their machine.

---

## Build a Standalone Executable

Run on the target platform:

```bash
pip install pyinstaller
python build.py
```

Output:

- Windows > `dist/VirtualCouch.exe`
- macOS   > `dist/VirtualCouch.app`
- Linux   > `dist/VirtualCouch`

---

## Platform Notes

| OS | Notes |
|----|-------|
| **Windows** | Run as Admin if input injection fails |
| **macOS** | Grant *Accessibility* + *Input Monitoring* in System Settings > Privacy |
| **Linux** | `sudo apt install libxtst6 python3-tk` if missing |

---

## Security

- The WebRTC connection is encrypted (DTLS).
- The app has **no built-in authentication** — only share your Offer/Answer codes with people you trust.
- Once connected, the Controller can type and move the mouse on the Host machine.

---

## Architecture

```graph
virtual_couch.py
├── VirtualCouch class      WebRTC peer + input capture/simulate
│   ├── _build_pc()         RTCPeerConnection with STUN
│   ├── host_*()            Offer generation + answer acceptance
│   ├── controller_*()      Answer generation
│   ├── start_listeners()   pynput keyboard + mouse capture
│   └── simulate_input()    pynput OS-level injection
└── App class (ctk.CTk)     CustomTkinter GUI
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `aiortc` | WebRTC DataChannels, ICE/STUN |
| `pynput` | Cross-platform input capture & simulation |
| `customtkinter` | Modern dark-theme Tkinter widgets |
| `aiohttp` | Async networking (aiortc dependency) |
