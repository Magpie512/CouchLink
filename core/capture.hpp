#pragma once
#include "input_core.hpp"
#include <thread>
#include <atomic>
#include <chrono>
#include <iostream>

// ─────────────────────────────────────────────────────────────────
//  InputCapture
//  Captures keyboard, mouse, and gamepad events on the local machine
//  and fires the callback for each one.
//
//  Platform-specific backend is selected at compile time.
//  Windows  → Raw Input API + XInput
//  macOS    → CGEvent tap
//  Linux    → /dev/input + uinput (evdev)
// ─────────────────────────────────────────────────────────────────

class InputCapture {
public:
    explicit InputCapture(EventCallback cb, uint32_t session_id)
        : callback_(std::move(cb)), session_id_(session_id), running_(false) {}

    ~InputCapture() { stop(); }

    void start() {
        running_ = true;
#if defined(_WIN32)
        capture_thread_ = std::thread(&InputCapture::windows_loop, this);
#elif defined(__APPLE__)
        capture_thread_ = std::thread(&InputCapture::macos_loop, this);
#else
        capture_thread_ = std::thread(&InputCapture::linux_loop, this);
#endif
        gamepad_thread_ = std::thread(&InputCapture::gamepad_loop, this);
    }

    void stop() {
        running_ = false;
        if (capture_thread_.joinable()) capture_thread_.join();
        if (gamepad_thread_.joinable()) gamepad_thread_.join();
    }

private:
    EventCallback callback_;
    uint32_t session_id_;
    std::atomic<bool> running_;
    std::thread capture_thread_;
    std::thread gamepad_thread_;

    uint32_t now_ms() {
        using namespace std::chrono;
        return (uint32_t)duration_cast<milliseconds>(
            steady_clock::now().time_since_epoch()).count();
    }

    void fire(InputEvent ev) {
        ev.timestamp_ms = now_ms();
        ev.session_id   = session_id_;
        callback_(ev);
    }

    // ─── Windows ─────────────────────────────────────────────────
#if defined(_WIN32)
    // Raw Input is registered on a message-only window so we don't
    // need to hook into a real GUI window. This works system-wide.
#include <windows.h>
#include <xinput.h>

    static InputCapture* g_instance;

    static LRESULT CALLBACK raw_wnd_proc(HWND hwnd, UINT msg,
                                          WPARAM wp, LPARAM lp) {
        if (msg == WM_INPUT && g_instance) {
            UINT size = 0;
            GetRawInputData((HRAWINPUT)lp, RID_INPUT,
                            nullptr, &size, sizeof(RAWINPUTHEADER));
            std::vector<BYTE> buf(size);
            GetRawInputData((HRAWINPUT)lp, RID_INPUT,
                            buf.data(), &size, sizeof(RAWINPUTHEADER));
            RAWINPUT* raw = (RAWINPUT*)buf.data();

            if (raw->header.dwType == RIM_TYPEKEYBOARD) {
                auto& kb = raw->data.keyboard;
                InputEvent ev{};
                ev.type   = (kb.Flags & RI_KEY_BREAK) ? EV_KEY_UP : EV_KEY_DOWN;
                ev.source = SRC_KEYBOARD;
                ev.code   = kb.VKey;
                ev.value  = 1;
                g_instance->fire(ev);
            } else if (raw->header.dwType == RIM_TYPEMOUSE) {
                auto& m = raw->data.mouse;
                if (m.usFlags & MOUSE_MOVE_RELATIVE) {
                    InputEvent ev{};
                    ev.type   = EV_MOUSE_MOVE;
                    ev.source = SRC_MOUSE;
                    ev.value  = m.lLastX;
                    ev.value2 = m.lLastY;
                    g_instance->fire(ev);
                }
                // Buttons
                if (m.usButtonFlags) {
                    InputEvent ev{};
                    ev.type   = EV_MOUSE_BTN;
                    ev.source = SRC_MOUSE;
                    ev.code   = m.usButtonFlags;
                    ev.value  = (m.usButtonFlags & 0x5555) ? 1 : 0;
                    g_instance->fire(ev);
                }
                if (m.usButtonFlags & RI_MOUSE_WHEEL) {
                    InputEvent ev{};
                    ev.type   = EV_MOUSE_SCROLL;
                    ev.source = SRC_MOUSE;
                    ev.value  = (SHORT)m.usButtonData;
                    g_instance->fire(ev);
                }
            }
        }
        return DefWindowProc(hwnd, msg, wp, lp);
    }

    void windows_loop() {
        g_instance = this;
        WNDCLASS wc{};
        wc.lpfnWndProc   = raw_wnd_proc;
        wc.hInstance     = GetModuleHandle(nullptr);
        wc.lpszClassName = L"CouchLinkRaw";
        RegisterClass(&wc);

        HWND hwnd = CreateWindowEx(0, L"CouchLinkRaw", nullptr, 0,
                                   0, 0, 0, 0, HWND_MESSAGE,
                                   nullptr, wc.hInstance, nullptr);

        RAWINPUTDEVICE rid[2];
        // Keyboard
        rid[0].usUsagePage = 0x01; rid[0].usUsage = 0x06;
        rid[0].dwFlags = RIDEV_INPUTSINK; rid[0].hwndTarget = hwnd;
        // Mouse
        rid[1].usUsagePage = 0x01; rid[1].usUsage = 0x02;
        rid[1].dwFlags = RIDEV_INPUTSINK; rid[1].hwndTarget = hwnd;
        RegisterRawInputDevices(rid, 2, sizeof(RAWINPUTDEVICE));

        MSG msg;
        while (running_ && GetMessage(&msg, nullptr, 0, 0)) {
            TranslateMessage(&msg);
            DispatchMessage(&msg);
        }
        DestroyWindow(hwnd);
    }

    void gamepad_loop() {
        XINPUT_STATE prev[XUSER_MAX_COUNT]{};
        while (running_) {
            for (DWORD i = 0; i < XUSER_MAX_COUNT; i++) {
                XINPUT_STATE state{};
                if (XInputGetState(i, &state) != ERROR_SUCCESS) continue;
                if (state.dwPacketNumber == prev[i].dwPacketNumber) continue;

                auto& gp = state.Gamepad;
                auto& pg = prev[i].Gamepad;

                // Buttons bitmask diff
                WORD changed = gp.wButtons ^ pg.wButtons;
                for (int b = 0; b < 16; b++) {
                    if (changed & (1 << b)) {
                        InputEvent ev{};
                        ev.type   = (gp.wButtons & (1 << b)) ? EV_GAMEPAD_BTN : EV_GAMEPAD_BTN;
                        ev.source = SRC_GAMEPAD;
                        ev.code   = (i << 8) | b;
                        ev.value  = (gp.wButtons & (1 << b)) ? 1 : 0;
                        fire(ev);
                    }
                }
                // Left stick
                if (gp.sThumbLX != pg.sThumbLX || gp.sThumbLY != pg.sThumbLY) {
                    InputEvent ev{};
                    ev.type   = EV_GAMEPAD_AXIS;
                    ev.source = SRC_GAMEPAD;
                    ev.code   = (i << 8) | 0x00; // left stick
                    ev.value  = gp.sThumbLX;
                    ev.value2 = gp.sThumbLY;
                    fire(ev);
                }
                // Right stick
                if (gp.sThumbRX != pg.sThumbRX || gp.sThumbRY != pg.sThumbRY) {
                    InputEvent ev{};
                    ev.type   = EV_GAMEPAD_AXIS;
                    ev.source = SRC_GAMEPAD;
                    ev.code   = (i << 8) | 0x01; // right stick
                    ev.value  = gp.sThumbRX;
                    ev.value2 = gp.sThumbRY;
                    fire(ev);
                }
                prev[i] = state;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(4)); // ~240Hz poll
        }
    }

    // ─── macOS ───────────────────────────────────────────────────
#elif defined(__APPLE__)
#include <ApplicationServices/ApplicationServices.h>
#include <IOKit/hid/IOHIDManager.h>

    static CGEventRef event_tap_cb(CGEventTapProxy, CGEventType type,
                                   CGEventRef event, void* ctx) {
        auto* self = static_cast<InputCapture*>(ctx);
        InputEvent ev{};

        if (type == kCGEventKeyDown || type == kCGEventKeyUp) {
            ev.type   = (type == kCGEventKeyDown) ? EV_KEY_DOWN : EV_KEY_UP;
            ev.source = SRC_KEYBOARD;
            ev.code   = (uint16_t)CGEventGetIntegerValueField(
                event, kCGKeyboardEventKeycode);
            ev.value  = 1;
            self->fire(ev);
        } else if (type == kCGEventMouseMoved) {
            ev.type   = EV_MOUSE_MOVE;
            ev.source = SRC_MOUSE;
            ev.value  = (int32_t)CGEventGetIntegerValueField(
                event, kCGMouseEventDeltaX);
            ev.value2 = (int32_t)CGEventGetIntegerValueField(
                event, kCGMouseEventDeltaY);
            self->fire(ev);
        } else if (type == kCGEventLeftMouseDown || type == kCGEventRightMouseDown ||
                   type == kCGEventLeftMouseUp   || type == kCGEventRightMouseUp) {
            ev.type   = EV_MOUSE_BTN;
            ev.source = SRC_MOUSE;
            ev.code   = (type == kCGEventLeftMouseDown || type == kCGEventLeftMouseUp) ? 0 : 1;
            ev.value  = (type == kCGEventLeftMouseDown || type == kCGEventRightMouseDown) ? 1 : 0;
            self->fire(ev);
        } else if (type == kCGEventScrollWheel) {
            ev.type   = EV_MOUSE_SCROLL;
            ev.source = SRC_MOUSE;
            ev.value  = (int32_t)CGEventGetIntegerValueField(
                event, kCGScrollWheelEventDeltaAxis1);
            self->fire(ev);
        }
        return event;
    }

    void macos_loop() {
        CGEventMask mask = CGEventMaskBit(kCGEventKeyDown)        |
                           CGEventMaskBit(kCGEventKeyUp)          |
                           CGEventMaskBit(kCGEventMouseMoved)     |
                           CGEventMaskBit(kCGEventLeftMouseDown)  |
                           CGEventMaskBit(kCGEventLeftMouseUp)    |
                           CGEventMaskBit(kCGEventRightMouseDown) |
                           CGEventMaskBit(kCGEventRightMouseUp)   |
                           CGEventMaskBit(kCGEventScrollWheel);

        CFMachPortRef tap = CGEventTapCreate(
            kCGSessionEventTap, kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly, mask, event_tap_cb, this);

        if (!tap) {
            std::cerr << "[capture] CGEventTap failed — check Accessibility permissions\n";
            return;
        }
        CFRunLoopSourceRef src = CFMachPortCreateRunLoopSource(
            kCFAllocatorDefault, tap, 0);
        CFRunLoopAddSource(CFRunLoopGetCurrent(), src, kCFRunLoopCommonModes);
        CGEventTapEnable(tap, true);
        while (running_) CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.1, false);
        CFRelease(src); CFRelease(tap);
    }

    void gamepad_loop() {
        // IOHIDManager-based gamepad polling for macOS
        // Full implementation uses IOHIDManagerCreate + value callbacks.
        // Simplified polling stub — expand per-device as needed.
        IOHIDManagerRef mgr = IOHIDManagerCreate(kCFAllocatorDefault, kIOHIDOptionsTypeNone);
        if (!mgr) return;

        CFDictionaryRef gamepad_match = nullptr; // match all gamepads
        IOHIDManagerSetDeviceMatching(mgr, gamepad_match);
        IOHIDManagerOpen(mgr, kIOHIDOptionsTypeNone);
        IOHIDManagerScheduleWithRunLoop(mgr, CFRunLoopGetCurrent(), kCFRunLoopDefaultMode);

        while (running_) {
            CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.004, false); // ~240Hz
        }
        IOHIDManagerClose(mgr, kIOHIDOptionsTypeNone);
        CFRelease(mgr);
    }

    // ─── Linux ───────────────────────────────────────────────────
#else
#include <fcntl.h>
#include <unistd.h>
#include <dirent.h>
#include <linux/input.h>
#include <glob.h>

    void linux_loop() {
        // Open all /dev/input/event* devices concurrently
        glob_t g;
        glob("/dev/input/event*", 0, nullptr, &g);

        std::vector<std::thread> workers;
        for (size_t i = 0; i < g.gl_pathc; i++) {
            std::string path = g.gl_pathv[i];
            workers.emplace_back([this, path]() {
                int fd = open(path.c_str(), O_RDONLY | O_NONBLOCK);
                if (fd < 0) return;
                struct input_event ie;
                while (running_) {
                    ssize_t n = read(fd, &ie, sizeof(ie));
                    if (n < (ssize_t)sizeof(ie)) {
                        std::this_thread::sleep_for(std::chrono::milliseconds(1));
                        continue;
                    }
                    InputEvent ev{};
                    if (ie.type == EV_KEY) {
                        ev.type   = (ie.value == 1) ? EV_KEY_DOWN :
                                    (ie.value == 0) ? EV_KEY_UP : EV_KEY_DOWN;
                        ev.source = (ie.code < 256) ? SRC_KEYBOARD : SRC_GAMEPAD;
                        ev.code   = ie.code;
                        ev.value  = ie.value;
                        fire(ev);
                    } else if (ie.type == EV_REL) {
                        ev.source = SRC_MOUSE;
                        if (ie.code == REL_WHEEL) {
                            ev.type  = EV_MOUSE_SCROLL;
                            ev.value = ie.value;
                        } else {
                            ev.type  = EV_MOUSE_MOVE;
                            ev.value  = (ie.code == REL_X) ? ie.value : 0;
                            ev.value2 = (ie.code == REL_Y) ? ie.value : 0;
                        }
                        fire(ev);
                    } else if (ie.type == EV_ABS) {
                        ev.type   = EV_GAMEPAD_AXIS;
                        ev.source = SRC_GAMEPAD;
                        ev.code   = ie.code;
                        ev.value  = ie.value;
                        fire(ev);
                    }
                }
                close(fd);
            });
        }
        globfree(&g);
        for (auto& t : workers) t.join();
    }

    void gamepad_loop() {
        // On Linux, gamepad events come through /dev/input/event* (evdev),
        // which is already handled by linux_loop(). No separate thread needed.
        // This thread just waits until stopped.
        while (running_) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }
#endif
};

#if defined(_WIN32)
InputCapture* InputCapture::g_instance = nullptr;
#endif
