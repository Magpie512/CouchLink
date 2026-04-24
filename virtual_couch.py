"""
Virtual Couch - P2P Input Sharing Application
Controller <-> Host input sharing over WebRTC DataChannels
"""

import asyncio
import json
import threading
import tkinter as tk
from tkinter import scrolledtext, messagebox
import customtkinter as ctk
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCDataChannel
from aiortc.contrib.signaling import object_from_string, object_to_string
from pynput import keyboard, mouse
from pynput.keyboard import Key, Controller as KeyboardController
from pynput.mouse import Button, Controller as MouseController
import platform
import sys
import time

# ─── Theme ────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ─── Input Simulation (Host Side) ─────────────────────────────────────────────
kb_ctrl   = KeyboardController()
ms_ctrl   = MouseController()

SPECIAL_KEY_MAP = {
    "Key.space":      Key.space,
    "Key.enter":      Key.enter,
    "Key.backspace":  Key.backspace,
    "Key.tab":        Key.tab,
    "Key.shift":      Key.shift,
    "Key.shift_r":    Key.shift_r,
    "Key.ctrl_l":     Key.ctrl_l,
    "Key.ctrl_r":     Key.ctrl_r,
    "Key.alt_l":      Key.alt_l,
    "Key.alt_r":      Key.alt_r,
    "Key.cmd":        Key.cmd,
    "Key.up":         Key.up,
    "Key.down":       Key.down,
    "Key.left":       Key.left,
    "Key.right":      Key.right,
    "Key.esc":        Key.esc,
    "Key.f1":         Key.f1,  "Key.f2":  Key.f2,  "Key.f3":  Key.f3,
    "Key.f4":         Key.f4,  "Key.f5":  Key.f5,  "Key.f6":  Key.f6,
    "Key.f7":         Key.f7,  "Key.f8":  Key.f8,  "Key.f9":  Key.f9,
    "Key.f10":        Key.f10, "Key.f11": Key.f11, "Key.f12": Key.f12,
    "Key.delete":     Key.delete, "Key.home": Key.home, "Key.end": Key.end,
    "Key.page_up":    Key.page_up, "Key.page_down": Key.page_down,
    "Key.caps_lock":  Key.caps_lock,
    "Key.print_screen": Key.print_screen,
    "Key.scroll_lock": Key.scroll_lock,
    "Key.pause":      Key.pause,
    "Key.num_lock":   Key.num_lock,
    "Key.insert":     Key.insert,
}

BUTTON_MAP = {
    "Button.left":   Button.left,
    "Button.right":  Button.right,
    "Button.middle": Button.middle,
}

def simulate_input(data: dict):
    """Parse a JSON input event and replay it on the local OS."""
    try:
        kind = data.get("kind")

        if kind == "key_press":
            k = resolve_key(data["key"])
            if k: kb_ctrl.press(k)

        elif kind == "key_release":
            k = resolve_key(data["key"])
            if k: kb_ctrl.release(k)

        elif kind == "mouse_move":
            ms_ctrl.position = (data["x"], data["y"])

        elif kind == "mouse_press":
            btn = BUTTON_MAP.get(data["button"])
            if btn: ms_ctrl.press(btn)

        elif kind == "mouse_release":
            btn = BUTTON_MAP.get(data["button"])
            if btn: ms_ctrl.release(btn)

        elif kind == "mouse_scroll":
            ms_ctrl.scroll(data["dx"], data["dy"])

    except Exception as e:
        pass  # Silently skip bad packets


def resolve_key(key_str: str):
    if key_str in SPECIAL_KEY_MAP:
        return SPECIAL_KEY_MAP[key_str]
    # Single character key
    if len(key_str) == 1:
        return key_str
    return None


# ─── WebRTC Peer ───────────────────────────────────────────────────────────────
STUN_SERVERS = [
    {"urls": "stun:stun.l.google.com:19302"},
    {"urls": "stun:stun1.l.google.com:19302"},
    {"urls": "stun:stun2.l.google.com:19302"},
    {"urls": "stun:stun.cloudflare.com:3478"},
]

class VirtualCouch:
    def __init__(self, log_fn, status_fn):
        self.pc            = None
        self.channel       = None
        self.log           = log_fn
        self.set_status    = status_fn
        self.is_controller = False
        self._kb_listener  = None
        self._ms_listener  = None
        self._loop         = None
        self._thread       = None

    # ── Event loop management ──────────────────────────────────────────────────
    def _start_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def ensure_loop(self):
        if self._loop is None or not self._loop.is_running():
            self._thread = threading.Thread(target=self._start_loop, daemon=True)
            self._thread.start()
            time.sleep(0.1)

    def run_coro(self, coro):
        self.ensure_loop()
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    # ── Build peer connection ──────────────────────────────────────────────────
    def _build_pc(self):
        from aiortc import RTCConfiguration, RTCIceServer
        config = RTCConfiguration(iceServers=[RTCIceServer(**s) for s in STUN_SERVERS])
        self.pc = RTCPeerConnection(configuration=config)

        @self.pc.on("connectionstatechange")
        async def on_state():
            state = self.pc.connectionState
            self.log(f"[WebRTC] Connection: {state}")
            self.set_status(state)
            if state == "connected":
                self.log("✅ Peer connected! You're on the virtual couch.")
            elif state in ("failed", "closed", "disconnected"):
                self.log("❌ Connection lost.")
                self.stop_listeners()

    # ── HOST mode ─────────────────────────────────────────────────────────────
    async def _host_create_offer(self):
        self._build_pc()

        @self.pc.on("datachannel")
        def on_datachannel(channel: RTCDataChannel):
            self.channel = channel
            self.log(f"[Host] DataChannel '{channel.label}' opened.")

            @channel.on("message")
            def on_message(msg):
                try:
                    data = json.loads(msg)
                    simulate_input(data)
                except Exception:
                    pass

        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        # Wait for ICE gathering
        await asyncio.sleep(2)
        sdp_str = object_to_string(self.pc.localDescription)
        return sdp_str

    async def _host_accept_answer(self, answer_str: str):
        answer = object_from_string(answer_str)
        await self.pc.setRemoteDescription(answer)

    # ── CONTROLLER mode ───────────────────────────────────────────────────────
    async def _controller_create_answer(self, offer_str: str):
        self._build_pc()
        offer = object_from_string(offer_str)
        await self.pc.setRemoteDescription(offer)

        self.channel = self.pc.createDataChannel("inputs")
        self.log("[Controller] DataChannel created.")

        @self.channel.on("open")
        def on_open():
            self.log("[Controller] Channel open — starting input capture.")
            self.start_listeners()

        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        await asyncio.sleep(2)
        sdp_str = object_to_string(self.pc.localDescription)
        return sdp_str

    # ── Send helper ───────────────────────────────────────────────────────────
    def send(self, payload: dict):
        if self.channel and self.channel.readyState == "open":
            try:
                self.channel.send(json.dumps(payload))
            except Exception:
                pass

    # ── Input capture (Controller) ────────────────────────────────────────────
    def start_listeners(self):
        if self._kb_listener: return

        def on_press(key):
            self.send({"kind": "key_press", "key": str(key)})

        def on_release(key):
            self.send({"kind": "key_release", "key": str(key)})

        def on_move(x, y):
            self.send({"kind": "mouse_move", "x": x, "y": y})

        def on_click(x, y, button, pressed):
            kind = "mouse_press" if pressed else "mouse_release"
            self.send({"kind": kind, "button": str(button), "x": x, "y": y})

        def on_scroll(x, y, dx, dy):
            self.send({"kind": "mouse_scroll", "x": x, "y": y, "dx": dx, "dy": dy})

        self._kb_listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self._ms_listener = mouse.Listener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
        self._kb_listener.start()
        self._ms_listener.start()
        self.log("[Controller] Input listeners active.")

    def stop_listeners(self):
        if self._kb_listener:
            self._kb_listener.stop()
            self._kb_listener = None
        if self._ms_listener:
            self._ms_listener.stop()
            self._ms_listener = None

    async def _close(self):
        if self.pc:
            await self.pc.close()

    def close(self):
        self.stop_listeners()
        if self.pc:
            self.run_coro(self._close())

    # ── Public coroutine wrappers ──────────────────────────────────────────────
    def host_create_offer(self, callback):
        def done(fut):
            try: callback(fut.result())
            except Exception as e: self.log(f"[Error] {e}")
        self.run_coro(self._host_create_offer()).add_done_callback(done)

    def host_accept_answer(self, answer_str, callback=None):
        def done(fut):
            try:
                fut.result()
                if callback: callback()
            except Exception as e: self.log(f"[Error] {e}")
        self.run_coro(self._host_accept_answer(answer_str)).add_done_callback(done)

    def controller_create_answer(self, offer_str, callback):
        def done(fut):
            try: callback(fut.result())
            except Exception as e: self.log(f"[Error] {e}")
        self.run_coro(self._controller_create_answer(offer_str)).add_done_callback(done)


# ─── GUI ──────────────────────────────────────────────────────────────────────
class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Virtual Couch 🛋️")
        self.geometry("780x640")
        self.resizable(False, False)
        self.configure(fg_color="#0d0d0f")

        self.vc = VirtualCouch(log_fn=self._log, status_fn=self._set_status)
        self._build_ui()

    # ── UI Construction ────────────────────────────────────────────────────────
    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="#111115", corner_radius=0, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header, text="🛋️  Virtual Couch",
            font=ctk.CTkFont(family="Georgia", size=22, weight="bold"),
            text_color="#e8e0d0"
        ).pack(side="left", padx=20, pady=14)

        self.status_dot = ctk.CTkLabel(
            header, text="● disconnected",
            font=ctk.CTkFont(size=12), text_color="#555"
        )
        self.status_dot.pack(side="right", padx=20)

        # Mode selector
        mode_frame = ctk.CTkFrame(self, fg_color="#16161a", corner_radius=12)
        mode_frame.pack(padx=20, pady=(16, 0), fill="x")

        ctk.CTkLabel(
            mode_frame, text="Select Your Role",
            font=ctk.CTkFont(size=13, weight="bold"), text_color="#888"
        ).pack(pady=(12, 6))

        btn_row = ctk.CTkFrame(mode_frame, fg_color="transparent")
        btn_row.pack(pady=(0, 12))

        self.mode_var = tk.StringVar(value="")
        self.host_btn = ctk.CTkButton(
            btn_row, text="🖥️  Host  (receives inputs)",
            width=280, height=44, corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1a3a5c", hover_color="#1f4d7a",
            command=lambda: self._select_mode("host")
        )
        self.host_btn.pack(side="left", padx=(0, 12))

        self.ctrl_btn = ctk.CTkButton(
            btn_row, text="🎮  Controller  (sends inputs)",
            width=280, height=44, corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#3a1a5c", hover_color="#4d1f7a",
            command=lambda: self._select_mode("controller")
        )
        self.ctrl_btn.pack(side="left")

        # Steps panel
        self.steps_frame = ctk.CTkFrame(self, fg_color="#16161a", corner_radius=12)
        self.steps_frame.pack(padx=20, pady=12, fill="x")

        self.steps_label = ctk.CTkLabel(
            self.steps_frame,
            text="← Choose a role above to begin",
            font=ctk.CTkFont(size=13), text_color="#666"
        )
        self.steps_label.pack(pady=16)

        # Offer / Answer text area
        code_label_row = ctk.CTkFrame(self, fg_color="transparent")
        code_label_row.pack(padx=20, fill="x")
        ctk.CTkLabel(
            code_label_row, text="Connection Code",
            font=ctk.CTkFont(size=12, weight="bold"), text_color="#666"
        ).pack(side="left")

        self.code_box = ctk.CTkTextbox(
            self, height=90, corner_radius=8,
            font=ctk.CTkFont(family="Courier New", size=11),
            fg_color="#0a0a0d", text_color="#a0e8a0",
            border_color="#2a2a35", border_width=1
        )
        self.code_box.pack(padx=20, pady=(4, 8), fill="x")

        self.action_btn = ctk.CTkButton(
            self, text="—", state="disabled",
            height=40, corner_radius=8,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#222", hover_color="#2a2a2a",
            command=self._action
        )
        self.action_btn.pack(padx=20, fill="x")

        # Log
        ctk.CTkLabel(
            self, text="Log",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="#444"
        ).pack(padx=20, pady=(12, 2), anchor="w")

        self.log_box = ctk.CTkTextbox(
            self, corner_radius=8,
            font=ctk.CTkFont(family="Courier New", size=11),
            fg_color="#0a0a0d", text_color="#888",
            border_color="#1a1a25", border_width=1
        )
        self.log_box.pack(padx=20, pady=(0, 20), fill="both", expand=True)
        self.log_box.configure(state="disabled")

        self._log(f"Virtual Couch started. OS: {platform.system()} {platform.machine()}")

    # ── Mode Selection ─────────────────────────────────────────────────────────
    def _select_mode(self, mode: str):
        self.mode = mode
        self.vc.is_controller = (mode == "controller")
        self._step = "idle"

        if mode == "host":
            self.host_btn.configure(fg_color="#1f4d7a")
            self.ctrl_btn.configure(fg_color="#3a1a5c")
            self._show_steps(
                "HOST STEPS:\n"
                "1. Click 'Generate Offer' — copy the code that appears.\n"
                "2. Send the code to your friend (Discord, chat, etc.).\n"
                "3. Paste their Answer code here and click 'Accept Answer'."
            )
            self.action_btn.configure(
                text="1️⃣  Generate Offer", state="normal",
                fg_color="#1a3a5c", hover_color="#1f4d7a"
            )
            self._step = "host_offer"

        else:
            self.ctrl_btn.configure(fg_color="#4d1f7a")
            self.host_btn.configure(fg_color="#1a3a5c")
            self._show_steps(
                "CONTROLLER STEPS:\n"
                "1. Paste the Host's Offer code into the box above.\n"
                "2. Click 'Generate Answer' — copy the code that appears.\n"
                "3. Send the Answer code back to your Host friend.\n"
                "4. Once they accept, your inputs go straight to their machine!"
            )
            self.action_btn.configure(
                text="2️⃣  Generate Answer from Offer", state="normal",
                fg_color="#3a1a5c", hover_color="#4d1f7a"
            )
            self._step = "ctrl_answer"

    def _show_steps(self, text: str):
        for w in self.steps_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(
            self.steps_frame, text=text,
            font=ctk.CTkFont(family="Courier New", size=11),
            text_color="#aaa", justify="left"
        ).pack(padx=16, pady=12, anchor="w")

    # ── Button Action dispatcher ───────────────────────────────────────────────
    def _action(self):
        step = getattr(self, "_step", "")

        if step == "host_offer":
            self._log("Generating WebRTC offer (gathering ICE candidates)…")
            self.action_btn.configure(state="disabled", text="Generating…")
            self.vc.host_create_offer(self._on_offer_ready)

        elif step == "host_answer":
            answer = self._get_code()
            if not answer:
                messagebox.showwarning("Empty", "Paste the Controller's answer code first.")
                return
            self._log("Accepting answer…")
            self.vc.host_accept_answer(answer, lambda: self._log("Answer accepted — waiting for connection."))

        elif step == "ctrl_answer":
            offer = self._get_code()
            if not offer:
                messagebox.showwarning("Empty", "Paste the Host's offer code first.")
                return
            self._log("Generating answer…")
            self.action_btn.configure(state="disabled", text="Generating…")
            self.vc.controller_create_answer(offer, self._on_answer_ready)

    def _on_offer_ready(self, sdp: str):
        self._set_code(sdp)
        self._log("✅ Offer ready — copy the code above and send to your friend.")
        self._step = "host_answer"
        self.after(0, lambda: self.action_btn.configure(
            state="normal", text="3️⃣  Accept Answer (paste theirs above)"
        ))

    def _on_answer_ready(self, sdp: str):
        self._set_code(sdp)
        self._log("✅ Answer ready — copy the code above and send back to Host.")
        self.after(0, lambda: self.action_btn.configure(
            state="disabled", text="Waiting for Host to accept…"
        ))

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _get_code(self) -> str:
        return self.code_box.get("1.0", "end").strip()

    def _set_code(self, text: str):
        self.after(0, lambda: [
            self.code_box.delete("1.0", "end"),
            self.code_box.insert("1.0", text)
        ])

    def _log(self, msg: str):
        def _do():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.after(0, _do)

    def _set_status(self, state: str):
        colors = {
            "connected":    "#4caf50",
            "connecting":   "#ff9800",
            "checking":     "#ff9800",
            "disconnected": "#f44336",
            "failed":       "#f44336",
            "closed":       "#555",
            "new":          "#555",
        }
        color = colors.get(state, "#888")
        self.after(0, lambda: self.status_dot.configure(
            text=f"● {state}", text_color=color
        ))

    def on_close(self):
        self.vc.close()
        self.destroy()


# ─── Entry point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()
