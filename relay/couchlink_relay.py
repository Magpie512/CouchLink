#!/usr/bin/env python3
"""
couchlink_relay.py
──────────────────
A lightweight UDP relay server for CouchLink.

Both the host and controller connect to this server.
The relay simply forwards InputEvent packets between them,
identified by their shared session_id (first 4 bytes of every packet).

Deploy this on any cheap VPS (even a $4/mo Hetzner or DigitalOcean droplet).

Usage:
    python3 couchlink_relay.py [--port 9000] [--timeout 30]

The relay supports multiple sessions simultaneously.
Each session is a (controller, host) pair sharing the same session_id.
"""

import asyncio
import struct
import argparse
import time
import logging
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("relay")

# InputEvent wire layout — must match C++ struct (20 bytes)
# type(1) source(1) code(2) value(4) value2(4) timestamp_ms(4) session_id(4)
PACKET_SIZE = 20
PACKET_FMT  = "<BBHiiII"

EV_HANDSHAKE  = 0xF0
EV_HEARTBEAT  = 0xF1
EV_DISCONNECT = 0xFF


class Session:
    """Holds the two endpoints of a relay session."""
    def __init__(self, session_id: int):
        self.id         = session_id
        self.peers: list[tuple] = []   # up to 2 (addr, role)
        self.last_seen  = time.monotonic()

    def register(self, addr: tuple) -> bool:
        """Add an endpoint. Returns True if this is a new peer."""
        addrs = [p[0] for p in self.peers]
        if addr in addrs:
            self.last_seen = time.monotonic()
            return False
        if len(self.peers) >= 2:
            log.warning("Session %08x already has 2 peers — ignoring %s", self.id, addr)
            return False
        self.peers.append((addr, "host" if len(self.peers) == 1 else "ctrl"))
        self.last_seen = time.monotonic()
        log.info("Session %08x  peer joined: %s (total=%d)", self.id, addr, len(self.peers))
        return True

    def other_peer(self, sender: tuple):
        """Return the other peer's address, or None."""
        for addr, _ in self.peers:
            if addr != sender:
                return addr
        return None

    def is_expired(self, timeout: float) -> bool:
        return (time.monotonic() - self.last_seen) > timeout


class RelayProtocol(asyncio.DatagramProtocol):
    def __init__(self, timeout: float):
        self.transport:  asyncio.DatagramTransport | None = None
        self.sessions:   dict[int, Session] = {}
        self.timeout     = timeout

    def connection_made(self, transport):
        self.transport = transport
        log.info("Relay listening on %s", transport.get_extra_info("sockname"))

    def datagram_received(self, data: bytes, addr: tuple):
        if len(data) != PACKET_SIZE:
            return  # malformed — drop

        fields     = struct.unpack(PACKET_FMT, data)
        ev_type    = fields[0]
        session_id = fields[6]

        # Create session on first contact
        if session_id not in self.sessions:
            self.sessions[session_id] = Session(session_id)

        sess = self.sessions[session_id]
        sess.register(addr)
        sess.last_seen = time.monotonic()

        if ev_type == EV_HANDSHAKE:
            log.info("Handshake from %s for session %08x", addr, session_id)

        # Forward to the other peer
        target = sess.other_peer(addr)
        if target and self.transport:
            self.transport.sendto(data, target)

    def error_received(self, exc):
        log.error("Socket error: %s", exc)

    def connection_lost(self, exc):
        log.info("Relay socket closed: %s", exc)

    async def cleanup_loop(self):
        """Periodically purge expired sessions."""
        while True:
            await asyncio.sleep(10)
            expired = [sid for sid, sess in self.sessions.items()
                       if sess.is_expired(self.timeout)]
            for sid in expired:
                log.info("Session %08x expired — removing", sid)
                del self.sessions[sid]
            if self.sessions:
                log.info("Active sessions: %d", len(self.sessions))


async def main():
    parser = argparse.ArgumentParser(description="CouchLink UDP Relay Server")
    parser.add_argument("--port",    type=int, default=9000,  help="UDP port to listen on")
    parser.add_argument("--timeout", type=float, default=30.0, help="Session timeout in seconds")
    args = parser.parse_args()

    loop = asyncio.get_running_loop()
    protocol = RelayProtocol(timeout=args.timeout)

    transport, _ = await loop.create_datagram_endpoint(
        lambda: protocol,
        local_addr=("0.0.0.0", args.port),
    )

    log.info("CouchLink Relay started  port=%d  timeout=%.0fs", args.port, args.timeout)
    log.info("Share your server IP + port with both players.")
    log.info("Both players must use the SAME session_id (hex).")

    try:
        await asyncio.gather(
            asyncio.Event().wait(),   # run forever
            protocol.cleanup_loop(),
        )
    finally:
        transport.close()


if __name__ == "__main__":
    asyncio.run(main())
