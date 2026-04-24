#!/usr/bin/env python3
"""
CouchLink GUI
A native desktop launcher for CouchLink.
Compiles to a standalone exe/app/binary via PyInstaller.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import subprocess
import threading
import random
import os
import sys
import platform

# ── Colors & fonts ───────────────────────────────────────────────
BG        = "#0f0f0f"
BG2       = "#1a1a1a"
BG3       = "#242424"
BORDER    = "#2e2e2e"
HOST_COL  = "#1D9E75"
CTRL_COL  = "#378ADD"
TEXT      = "#e8e8e8"
TEXT2     = "#888888"
TEXT3     = "#555555"
MONO      = ("Courier New", 11) if platform.system() == "Windows" else ("Menlo", 11) if platform.system() == "Darwin" else ("DejaVu Sans Mono", 11)
SANS      = ("Segoe UI", 10) if platform.system() == "Windows" else ("SF Pro Text", 10) if platform.system() == "Darwin" else ("Ubuntu", 10)
SANS_SM   = (SANS[0], 9)
SANS_LG   = (SANS[0], 13)
SANS_XL   = (SANS[0], 18, "bold")


def binary_dir():
    """Return the directory where C++ binaries are expected."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "build")


def binary_name(role):
    suffix = ".exe" if platform.system() == "Windows" else ""
    return os.path.join(binary_dir(), f"couchlink_{role}{suffix}")


def gen_session_id():
    return f"{random.randint(0x10000000, 0xFFFFFFFF):08x}"


def detect_os():
    s = platform.system()
    return {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(s, "unknown")


class RoundedFrame(tk.Canvas):
    """A canvas that draws a rounded rectangle as background."""
    def __init__(self, parent, bg=BG2, radius=10, border_color=BORDER,
                 accent=None, **kwargs):
        super().__init__(parent, bg=BG, highlightthickness=0, **kwargs)
        self._bg = bg
        self._radius = radius
        self._border = border_color
        self._accent = accent
        self.bind("<Configure>", self._redraw)

    def _redraw(self, event=None):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        r = self._radius
        # main rounded rect
        self.create_rounded_rect(0, 0, w, h, r, fill=self._bg, outline=self._border, width=1)
        # top accent bar
        if self._accent:
            self.create_rectangle(r, 0, w - r, 3, fill=self._accent, outline="")
            self.create_rectangle(r, 0, w - r, r, fill=self._bg, outline="")
            self.create_rounded_rect(0, 0, w, r * 2, r, fill=self._bg, outline="")
            self.create_rectangle(0, r, w, h, fill=self._bg, outline="")
            self.create_rectangle(r, 0, w - r, 3, fill=self._accent, outline="")

    def create_rounded_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1+r, y1, x2-r, y1,
            x2, y1, x2, y1+r,
            x2, y2-r, x2, y2,
            x2-r, y2, x1+r, y2,
            x1, y2, x1, y2-r,
            x1, y1+r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)


class LogPanel(tk.Frame):
    """Scrollable terminal-style log output."""
    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=BG3, **kwargs)
        self.text = tk.Text(
            self, bg=BG3, fg=TEXT2, font=MONO,
            insertbackground=TEXT, relief="flat",
            padx=8, pady=6, state="disabled",
            wrap="word", height=8,
            selectbackground="#333", selectforeground=TEXT,
        )
        scrollbar = tk.Scrollbar(self, command=self.text.yview, bg=BG3,
                                  troughcolor=BG3, activebackground=BORDER)
        self.text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)

        self.text.tag_config("host",  foreground=HOST_COL)
        self.text.tag_config("ctrl",  foreground=CTRL_COL)
        self.text.tag_config("info",  foreground=TEXT2)
        self.text.tag_config("error", foreground="#E24B4A")
        self.text.tag_config("ok",    foreground=HOST_COL)

    def log(self, msg, tag="info"):
        self.text.configure(state="normal")
        self.text.insert("end", msg + "\n", tag)
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


class StyledEntry(tk.Entry):
    def __init__(self, parent, placeholder="", **kwargs):
        super().__init__(
            parent,
            bg=BG3, fg=TEXT, insertbackground=TEXT,
            relief="flat", font=MONO,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=CTRL_COL,
            **kwargs
        )
        self._placeholder = placeholder
        self._has_focus = False
        if placeholder:
            self.insert(0, placeholder)
            self.config(fg=TEXT3)
        self.bind("<FocusIn>",  self._on_focus_in)
        self.bind("<FocusOut>", self._on_focus_out)

    def _on_focus_in(self, _):
        if self.get() == self._placeholder:
            self.delete(0, "end")
            self.config(fg=TEXT)

    def _on_focus_out(self, _):
        if not self.get():
            self.insert(0, self._placeholder)
            self.config(fg=TEXT3)

    def real_value(self):
        v = self.get()
        return "" if v == self._placeholder else v


class CouchLinkApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CouchLink")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(760, 600)

        # Process handles
        self._host_proc = None
        self._ctrl_proc = None
        self._relay_proc = None

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._center_window(820, 680)

    def _center_window(self, w, h):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    def _build_ui(self):
        # ── Top bar ─────────────────────────────────────────────
        topbar = tk.Frame(self, bg=BG, pady=0)
        topbar.pack(fill="x", padx=20, pady=(18, 0))

        tk.Label(topbar, text="CouchLink", bg=BG, fg=TEXT,
                 font=(SANS[0], 22, "bold")).pack(side="left")
        tk.Label(topbar, text="  virtual couch · share controllers online",
                 bg=BG, fg=TEXT3, font=SANS).pack(side="left", pady=(6, 0))

        os_badge = tk.Label(topbar,
                            text=f"  {detect_os()}",
                            bg=BG3, fg=TEXT2, font=SANS_SM,
                            padx=8, pady=3)
        os_badge.pack(side="right")

        # ── Session ID row ───────────────────────────────────────
        sid_frame = tk.Frame(self, bg=BG)
        sid_frame.pack(fill="x", padx=20, pady=(14, 0))

        tk.Label(sid_frame, text="SESSION ID", bg=BG, fg=TEXT3,
                 font=(SANS[0], 9)).pack(side="left", padx=(0, 8))

        self._session_var = tk.StringVar(value=gen_session_id())
        sid_entry = tk.Entry(sid_frame, textvariable=self._session_var,
                             bg=BG3, fg=HOST_COL, insertbackground=TEXT,
                             relief="flat", font=(MONO[0], 13),
                             highlightthickness=1,
                             highlightbackground=BORDER,
                             highlightcolor=HOST_COL,
                             width=16)
        sid_entry.pack(side="left", ipady=4, padx=(0, 8))

        self._make_btn(sid_frame, "⟳  generate",
                       lambda: self._session_var.set(gen_session_id()),
                       color=HOST_COL).pack(side="left", padx=(0, 6))
        self._make_btn(sid_frame, "copy",
                       lambda: self._copy(self._session_var.get())).pack(side="left")

        tk.Label(sid_frame,
                 text="Share this with both players before connecting.",
                 bg=BG, fg=TEXT3, font=SANS_SM).pack(side="left", padx=12)

        # ── Main panels ──────────────────────────────────────────
        panels = tk.Frame(self, bg=BG)
        panels.pack(fill="both", expand=True, padx=20, pady=14)
        panels.columnconfigure(0, weight=1)
        panels.columnconfigure(1, weight=1)
        panels.rowconfigure(0, weight=1)

        self._build_host_panel(panels)
        self._build_ctrl_panel(panels)

        # ── Log ──────────────────────────────────────────────────
        log_label = tk.Label(self, text="LOG", bg=BG, fg=TEXT3, font=(SANS[0], 9),
                              anchor="w")
        log_label.pack(fill="x", padx=20)
        self._log = LogPanel(self)
        self._log.pack(fill="x", padx=20, pady=(4, 16))
        self._log.log("CouchLink GUI ready. Generate a session ID and connect.", "info")
        self._log.log(f"Binary directory: {binary_dir()}", "info")

    def _build_host_panel(self, parent):
        frame = tk.LabelFrame(parent, text="", bg=BG2,
                               relief="flat", bd=0,
                               highlightthickness=1,
                               highlightbackground=HOST_COL)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        frame.columnconfigure(0, weight=1)

        # Header
        hdr = tk.Frame(frame, bg=HOST_COL, height=3)
        hdr.pack(fill="x")

        tk.Label(frame, text="HOST", bg=BG2, fg=HOST_COL,
                 font=(SANS[0], 9)).pack(anchor="w", padx=14, pady=(10, 0))
        tk.Label(frame, text="Receive input", bg=BG2, fg=TEXT,
                 font=(SANS[0], 16, "bold")).pack(anchor="w", padx=14)
        tk.Label(frame,
                 text="Run on the PC that receives input.\nYour friend's controller will control this machine.",
                 bg=BG2, fg=TEXT2, font=SANS_SM, justify="left").pack(anchor="w", padx=14, pady=(2, 12))

        sep = tk.Frame(frame, bg=BORDER, height=1)
        sep.pack(fill="x", padx=14)

        body = tk.Frame(frame, bg=BG2)
        body.pack(fill="both", expand=True, padx=14, pady=12)

        tk.Label(body, text="PORT", bg=BG2, fg=TEXT3, font=(SANS[0], 9)).pack(anchor="w")
        self._h_port = StyledEntry(body, width=10)
        self._h_port.insert(0, "9000")
        self._h_port.pack(anchor="w", ipady=4, pady=(2, 10), fill="x")

        # Relay toggle
        self._h_relay_var = tk.BooleanVar(value=False)
        relay_chk = tk.Checkbutton(body, text="Use relay server (internet play)",
                                    variable=self._h_relay_var,
                                    bg=BG2, fg=TEXT2, selectcolor=BG3,
                                    activebackground=BG2, activeforeground=TEXT,
                                    font=SANS_SM, cursor="hand2",
                                    command=self._toggle_h_relay)
        relay_chk.pack(anchor="w")

        self._h_relay_frame = tk.Frame(body, bg=BG2)
        tk.Label(self._h_relay_frame, text="RELAY IP / HOSTNAME",
                 bg=BG2, fg=TEXT3, font=(SANS[0], 9)).pack(anchor="w")
        self._h_relay_ip = StyledEntry(self._h_relay_frame,
                                        placeholder="your.relay.server.com", width=24)
        self._h_relay_ip.pack(anchor="w", ipady=4, pady=(2, 0), fill="x")

        # Buttons
        btn_row = tk.Frame(body, bg=BG2)
        btn_row.pack(fill="x", pady=(14, 0))

        self._host_btn = self._make_btn(btn_row, "▶  Start host",
                                         self._start_host, color=HOST_COL, big=True)
        self._host_btn.pack(side="left", padx=(0, 6))

        self._stop_host_btn = self._make_btn(btn_row, "■  Stop",
                                              self._stop_host, color="#E24B4A")
        self._stop_host_btn.pack(side="left")
        self._stop_host_btn.config(state="disabled")

        self._h_status = tk.Label(body, text="● idle", bg=BG2, fg=TEXT3,
                                   font=SANS_SM)
        self._h_status.pack(anchor="w", pady=(8, 0))

    def _build_ctrl_panel(self, parent):
        frame = tk.LabelFrame(parent, text="", bg=BG2,
                               relief="flat", bd=0,
                               highlightthickness=1,
                               highlightbackground=CTRL_COL)
        frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        hdr = tk.Frame(frame, bg=CTRL_COL, height=3)
        hdr.pack(fill="x")

        tk.Label(frame, text="CONTROLLER", bg=BG2, fg=CTRL_COL,
                 font=(SANS[0], 9)).pack(anchor="w", padx=14, pady=(10, 0))
        tk.Label(frame, text="Send input", bg=BG2, fg=TEXT,
                 font=(SANS[0], 16, "bold")).pack(anchor="w", padx=14)
        tk.Label(frame,
                 text="Run on the PC you're physically using.\nYour input is forwarded to the host machine.",
                 bg=BG2, fg=TEXT2, font=SANS_SM, justify="left").pack(anchor="w", padx=14, pady=(2, 12))

        sep = tk.Frame(frame, bg=BORDER, height=1)
        sep.pack(fill="x", padx=14)

        body = tk.Frame(frame, bg=BG2)
        body.pack(fill="both", expand=True, padx=14, pady=12)

        tk.Label(body, text="HOST IP ADDRESS", bg=BG2, fg=TEXT3,
                 font=(SANS[0], 9)).pack(anchor="w")
        self._c_host_ip = StyledEntry(body, placeholder="192.168.1.100")
        self._c_host_ip.pack(anchor="w", ipady=4, pady=(2, 10), fill="x")

        tk.Label(body, text="PORT", bg=BG2, fg=TEXT3, font=(SANS[0], 9)).pack(anchor="w")
        self._c_port = StyledEntry(body, width=10)
        self._c_port.insert(0, "9000")
        self._c_port.pack(anchor="w", ipady=4, pady=(2, 10), fill="x")

        self._c_relay_var = tk.BooleanVar(value=False)
        relay_chk = tk.Checkbutton(body, text="Use relay server (internet play)",
                                    variable=self._c_relay_var,
                                    bg=BG2, fg=TEXT2, selectcolor=BG3,
                                    activebackground=BG2, activeforeground=TEXT,
                                    font=SANS_SM, cursor="hand2",
                                    command=self._toggle_c_relay)
        relay_chk.pack(anchor="w")

        self._c_relay_frame = tk.Frame(body, bg=BG2)
        tk.Label(self._c_relay_frame, text="RELAY IP / HOSTNAME",
                 bg=BG2, fg=TEXT3, font=(SANS[0], 9)).pack(anchor="w")
        self._c_relay_ip = StyledEntry(self._c_relay_frame,
                                        placeholder="your.relay.server.com")
        self._c_relay_ip.pack(anchor="w", ipady=4, pady=(2, 0), fill="x")

        btn_row = tk.Frame(body, bg=BG2)
        btn_row.pack(fill="x", pady=(14, 0))

        self._ctrl_btn = self._make_btn(btn_row, "▶  Start controller",
                                         self._start_ctrl, color=CTRL_COL, big=True)
        self._ctrl_btn.pack(side="left", padx=(0, 6))

        self._stop_ctrl_btn = self._make_btn(btn_row, "■  Stop",
                                              self._stop_ctrl, color="#E24B4A")
        self._stop_ctrl_btn.pack(side="left")
        self._stop_ctrl_btn.config(state="disabled")

        self._c_status = tk.Label(body, text="● idle", bg=BG2, fg=TEXT3,
                                   font=SANS_SM)
        self._c_status.pack(anchor="w", pady=(8, 0))

    def _make_btn(self, parent, text, cmd, color=BORDER, big=False):
        size = SANS_SM if not big else SANS
        btn = tk.Button(
            parent, text=text, command=cmd,
            bg=BG3, fg=color,
            activebackground=BORDER, activeforeground=color,
            relief="flat", font=size,
            padx=10, pady=5 if big else 4,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=color,
        )
        return btn

    def _toggle_h_relay(self):
        if self._h_relay_var.get():
            self._h_relay_frame.pack(anchor="w", fill="x", pady=(6, 0))
        else:
            self._h_relay_frame.pack_forget()

    def _toggle_c_relay(self):
        if self._c_relay_var.get():
            self._c_relay_frame.pack(anchor="w", fill="x", pady=(6, 0))
        else:
            self._c_relay_frame.pack_forget()

    def _copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self._log.log(f"Copied: {text}", "info")

    # ── Launch logic ─────────────────────────────────────────────

    def _start_host(self):
        sid  = self._session_var.get().strip()
        port = self._h_port.real_value() or "9000"
        if not sid:
            messagebox.showerror("Missing", "Generate a session ID first.")
            return

        bin_path = binary_name("host")
        if not os.path.isfile(bin_path):
            self._log.log(f"Binary not found: {bin_path}", "error")
            self._log.log("Run 'python3 couchlink.py build' first to compile the C++ binaries.", "error")
            messagebox.showerror("Binary missing",
                                  f"Host binary not found:\n{bin_path}\n\n"
                                  "Run:  python3 couchlink.py build")
            return

        cmd = [bin_path, port, sid]
        self._log.log(f"[host] Starting: {' '.join(cmd)}", "host")
        self._host_proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        self._host_btn.config(state="disabled")
        self._stop_host_btn.config(state="normal")
        self._h_status.config(text="● running", fg=HOST_COL)
        threading.Thread(target=self._stream_output,
                          args=(self._host_proc, "host"), daemon=True).start()

    def _stop_host(self):
        if self._host_proc:
            self._host_proc.terminate()
            self._host_proc = None
        self._host_btn.config(state="normal")
        self._stop_host_btn.config(state="disabled")
        self._h_status.config(text="● stopped", fg=TEXT3)
        self._log.log("[host] Stopped.", "info")

    def _start_ctrl(self):
        sid  = self._session_var.get().strip()
        port = self._c_port.real_value() or "9000"

        if self._c_relay_var.get():
            host_ip = self._c_relay_ip.real_value()
            if not host_ip:
                messagebox.showerror("Missing", "Enter the relay server IP/hostname.")
                return
        else:
            host_ip = self._c_host_ip.real_value()
            if not host_ip:
                messagebox.showerror("Missing", "Enter the host machine's IP address.")
                return

        if not sid:
            messagebox.showerror("Missing", "Generate a session ID first.")
            return

        bin_path = binary_name("controller")
        if not os.path.isfile(bin_path):
            self._log.log(f"Binary not found: {bin_path}", "error")
            self._log.log("Run 'python3 couchlink.py build' first to compile the C++ binaries.", "error")
            messagebox.showerror("Binary missing",
                                  f"Controller binary not found:\n{bin_path}\n\n"
                                  "Run:  python3 couchlink.py build")
            return

        cmd = [bin_path, host_ip, port, sid]
        self._log.log(f"[ctrl] Starting: {' '.join(cmd)}", "ctrl")
        self._ctrl_proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        self._ctrl_btn.config(state="disabled")
        self._stop_ctrl_btn.config(state="normal")
        self._c_status.config(text="● running", fg=CTRL_COL)
        threading.Thread(target=self._stream_output,
                          args=(self._ctrl_proc, "ctrl"), daemon=True).start()

    def _stop_ctrl(self):
        if self._ctrl_proc:
            self._ctrl_proc.terminate()
            self._ctrl_proc = None
        self._ctrl_btn.config(state="normal")
        self._stop_ctrl_btn.config(state="disabled")
        self._c_status.config(text="● stopped", fg=TEXT3)
        self._log.log("[ctrl] Stopped.", "info")

    def _stream_output(self, proc, tag):
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                self._log.log(line, tag)
        # Process ended
        code = proc.wait()
        self._log.log(f"[{tag}] Process exited (code {code})", "info")
        if tag == "host":
            self.after(0, self._stop_host)
        else:
            self.after(0, self._stop_ctrl)

    def _on_close(self):
        self._stop_host()
        self._stop_ctrl()
        self.destroy()


if __name__ == "__main__":
    app = CouchLinkApp()
    app.mainloop()
