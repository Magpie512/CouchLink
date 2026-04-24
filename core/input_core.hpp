#pragma once
#include <cstdint>
#include <string>
#include <functional>
#include <vector>

// ─────────────────────────────────────────────
//  InputEvent – wire format (packed, 20 bytes)
// ─────────────────────────────────────────────
#pragma pack(push, 1)
struct InputEvent {
    uint8_t  type;        // EventType enum
    uint8_t  source;      // InputSource enum
    uint16_t code;        // key/button/axis code
    int32_t  value;       // axis value or 1/0 for press/release
    int32_t  value2;      // secondary axis (mouse Y, stick Y)
    uint32_t timestamp_ms;
    uint32_t session_id;  // simple auth token
};
#pragma pack(pop)

static_assert(sizeof(InputEvent) == 20, "InputEvent must be 20 bytes");

enum EventType : uint8_t {
    EV_KEY_DOWN   = 0x01,
    EV_KEY_UP     = 0x02,
    EV_MOUSE_MOVE = 0x10,
    EV_MOUSE_BTN  = 0x11,
    EV_MOUSE_SCROLL = 0x12,
    EV_GAMEPAD_BTN  = 0x20,
    EV_GAMEPAD_AXIS = 0x21,
    EV_HANDSHAKE    = 0xF0,
    EV_HEARTBEAT    = 0xF1,
    EV_DISCONNECT   = 0xFF,
};

enum InputSource : uint8_t {
    SRC_KEYBOARD = 0,
    SRC_MOUSE    = 1,
    SRC_GAMEPAD  = 2,
    SRC_SYSTEM   = 3,
};

// Callback signature for received events
using EventCallback = std::function<void(const InputEvent&)>;

// Platform string helper
inline std::string platform_name() {
#if defined(_WIN32)
    return "windows";
#elif defined(__APPLE__)
    return "macos";
#else
    return "linux";
#endif
}
