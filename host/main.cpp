#include "inject.hpp"
#include "net.hpp"
#include <iostream>
#include <csignal>
#include <cstdlib>
#include <string>

// ─────────────────────────────────────────────────────────────────
//  couchlink_host
//  Run this on the machine that RECEIVES input from the controller.
//
//  Usage:
//    couchlink_host <port> <session_id>
//    couchlink_host 9000 deadbeef
//
//  session_id is a hex string that both sides must share (simple auth).
// ─────────────────────────────────────────────────────────────────

static bool g_running = true;

void handle_signal(int) { g_running = false; }

int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "Usage: couchlink_host <port> <session_id_hex>\n"
                  << "  Example: couchlink_host 9000 deadbeef\n";
        return 1;
    }

    uint16_t port       = (uint16_t)std::stoi(argv[1]);
    uint32_t session_id = (uint32_t)std::stoul(argv[2], nullptr, 16);

    std::cout << "=== CouchLink Host ===\n"
              << "Platform   : " << platform_name() << "\n"
              << "Port       : " << port << "\n"
              << "Session ID : " << std::hex << session_id << std::dec << "\n"
              << "Waiting for controller...\n\n";

    InputInjector injector;
    UDPReceiver   receiver(session_id);

    auto on_event = [&](const InputEvent& ev) {
        if (ev.type == EV_HANDSHAKE) {
            std::cout << "[host] Controller connected! (session="
                      << std::hex << ev.session_id << std::dec << ")\n";
            return;
        }
        if (ev.type == EV_HEARTBEAT) return;
        if (ev.type == EV_DISCONNECT) {
            std::cout << "[host] Controller disconnected.\n";
            return;
        }
        injector.inject(ev);
    };

    if (!receiver.listen(port, on_event)) {
        std::cerr << "[host] Failed to start listener.\n";
        return 1;
    }

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    std::cout << "[host] Running. Press Ctrl+C to quit.\n";
    while (g_running) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }

    std::cout << "\n[host] Shutting down.\n";
    return 0;
}
