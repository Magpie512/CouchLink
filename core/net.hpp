#pragma once
#include "input_core.hpp"
#include <thread>
#include <atomic>
#include <functional>
#include <iostream>
#include <cstring>

// ─────────────────────────────────────────────────────────────────
//  Platform socket includes
// ─────────────────────────────────────────────────────────────────
#if defined(_WIN32)
#  include <winsock2.h>
#  include <ws2tcpip.h>
#  pragma comment(lib, "ws2_32.lib")
   using socklen_t = int;
#  define SOCK_CLOSE closesocket
#  define SOCK_INVALID INVALID_SOCKET
   using sock_t = SOCKET;
#else
#  include <sys/socket.h>
#  include <netinet/in.h>
#  include <arpa/inet.h>
#  include <unistd.h>
#  define SOCK_CLOSE close
#  define SOCK_INVALID (-1)
   using sock_t = int;
#endif

// ─────────────────────────────────────────────────────────────────
//  UDPSender  — controller side
//  Serializes InputEvents and blasts them over UDP.
// ─────────────────────────────────────────────────────────────────
class UDPSender {
public:
    UDPSender() : sock_(SOCK_INVALID) { platform_init(); }
    ~UDPSender() { if (sock_ != SOCK_INVALID) SOCK_CLOSE(sock_); platform_shutdown(); }

    bool connect(const std::string& host, uint16_t port) {
        sock_ = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        if (sock_ == SOCK_INVALID) return false;

        memset(&remote_, 0, sizeof(remote_));
        remote_.sin_family = AF_INET;
        remote_.sin_port   = htons(port);
        if (inet_pton(AF_INET, host.c_str(), &remote_.sin_addr) != 1) {
            std::cerr << "[net] Invalid address: " << host << "\n";
            return false;
        }
        std::cout << "[net] Sender ready → " << host << ":" << port << "\n";
        return true;
    }

    void send_event(const InputEvent& ev) {
        sendto(sock_, (const char*)&ev, sizeof(ev), 0,
               (sockaddr*)&remote_, sizeof(remote_));
    }

private:
    sock_t sock_;
    sockaddr_in remote_{};

    void platform_init() {
#if defined(_WIN32)
        WSADATA wsa; WSAStartup(MAKEWORD(2,2), &wsa);
#endif
    }
    void platform_shutdown() {
#if defined(_WIN32)
        WSACleanup();
#endif
    }
};

// ─────────────────────────────────────────────────────────────────
//  UDPReceiver  — host side
//  Listens for incoming InputEvents, verifies session_id,
//  and fires the callback for each valid event.
// ─────────────────────────────────────────────────────────────────
class UDPReceiver {
public:
    explicit UDPReceiver(uint32_t session_id)
        : sock_(SOCK_INVALID), session_id_(session_id), running_(false) {
        platform_init();
    }
    ~UDPReceiver() {
        stop();
        if (sock_ != SOCK_INVALID) SOCK_CLOSE(sock_);
        platform_shutdown();
    }

    bool listen(uint16_t port, EventCallback cb) {
        sock_ = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
        if (sock_ == SOCK_INVALID) return false;

        // Allow address reuse
        int opt = 1;
        setsockopt(sock_, SOL_SOCKET, SO_REUSEADDR, (char*)&opt, sizeof(opt));

        sockaddr_in local{};
        local.sin_family      = AF_INET;
        local.sin_addr.s_addr = INADDR_ANY;
        local.sin_port        = htons(port);

        if (bind(sock_, (sockaddr*)&local, sizeof(local)) < 0) {
            std::cerr << "[net] Bind failed on port " << port << "\n";
            return false;
        }

        running_ = true;
        recv_thread_ = std::thread([this, cb]() {
            InputEvent ev;
            sockaddr_in sender;
            socklen_t slen = sizeof(sender);

            std::cout << "[net] Listening on UDP port "
                      << ntohs(((sockaddr_in*)&sender)->sin_port) << "\n";

            while (running_) {
                int n = recvfrom(sock_, (char*)&ev, sizeof(ev), 0,
                                 (sockaddr*)&sender, &slen);
                if (n != sizeof(InputEvent)) continue;

                // Simple auth: drop events with wrong session token
                if (ev.session_id != session_id_ && ev.type != EV_HANDSHAKE) {
                    std::cerr << "[net] Dropped packet — wrong session ID\n";
                    continue;
                }
                cb(ev);
            }
        });
        return true;
    }

    void stop() {
        running_ = false;
        if (recv_thread_.joinable()) recv_thread_.join();
    }

private:
    sock_t sock_;
    uint32_t session_id_;
    std::atomic<bool> running_;
    std::thread recv_thread_;

    void platform_init() {
#if defined(_WIN32)
        WSADATA wsa; WSAStartup(MAKEWORD(2,2), &wsa);
#endif
    }
    void platform_shutdown() {
#if defined(_WIN32)
        WSACleanup();
#endif
    }
};
