#include "capture.hpp"
#include "net.hpp"
#include <iostream>
#include <csignal>
#include <string>
#include <thread>
#include <chrono>

// ─────────────────────────────────────────────────────────────────
//  couchlink_controller
//  Run this on the machine that SENDS input to the host.
//
//  Usage:
//    couchlink_controller <host_ip> <port> <session_id>
//    couchlink_controller 192.168.1.100 9000 deadbeef
//
//  For internet play, use the relay server IP instead.
// ─────────────────────────────────────────────────────────────────

static bool g_running = true;

void handle_signal(int) { g_running = false; }

int main(int argc, char** argv) {
    if (argc < 4) {
        std::cerr << "Usage: couchlink_controller <host_ip> <port> <session_id_hex>\n"
                  << "  LAN example   : couchlink_controller 192.168.1.100 9000 deadbeef\n"
                  << "  Relay example : couchlink_controller relay.myserver.com 9000 deadbeef\n";
        return 1;
    }

    std::string host    = argv[1];
    uint16_t    port    = (uint16_t)std::stoi(argv[2]);
    uint32_t session_id = (uint32_t)std::stoul(argv[3], nullptr, 16);

    std::cout << "=== CouchLink Controller ===\n"
              << "Platform   : " << platform_name() << "\n"
              << "Target     : " << host << ":" << port << "\n"
              << "Session ID : " << std::hex << session_id << std::dec << "\n\n";

    UDPSender sender;
    if (!sender.connect(host, port)) {
        std::cerr << "[ctrl] Failed to set up sender.\n";
        return 1;
    }

    // Send handshake
    InputEvent handshake{};
    handshake.type       = EV_HANDSHAKE;
    handshake.source     = SRC_SYSTEM;
    handshake.session_id = session_id;
    sender.send_event(handshake);
    std::cout << "[ctrl] Handshake sent.\n";

    // Capture and forward every input event
    InputCapture capture([&](const InputEvent& ev) {
        sender.send_event(ev);
    }, session_id);

    capture.start();
    std::cout << "[ctrl] Capturing input. Press Ctrl+C to quit.\n";

    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);

    // Heartbeat every 2s so the host knows we're still alive
    while (g_running) {
        std::this_thread::sleep_for(std::chrono::seconds(2));
        InputEvent hb{};
        hb.type       = EV_HEARTBEAT;
        hb.source     = SRC_SYSTEM;
        hb.session_id = session_id;
        sender.send_event(hb);
    }

    // Send disconnect notice
    InputEvent bye{};
    bye.type       = EV_DISCONNECT;
    bye.source     = SRC_SYSTEM;
    bye.session_id = session_id;
    sender.send_event(bye);

    capture.stop();
    std::cout << "\n[ctrl] Shutting down.\n";
    return 0;
}
