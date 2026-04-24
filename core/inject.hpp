#pragma once
#include "input_core.hpp"
#include <iostream>

// ─────────────────────────────────────────────────────────────────
//  InputInjector
//  Receives an InputEvent and replays it on the local machine
//  as a real OS-level input event.
//
//  Windows  → SendInput / XInput emulation via ViGEm (if available)
//  macOS    → CGEvent posting
//  Linux    → uinput virtual device
// ─────────────────────────────────────────────────────────────────

class InputInjector {
public:
    InputInjector()  { init(); }
    ~InputInjector() { shutdown(); }

    void inject(const InputEvent& ev) {
        switch (ev.source) {
            case SRC_KEYBOARD: inject_keyboard(ev); break;
            case SRC_MOUSE:    inject_mouse(ev);    break;
            case SRC_GAMEPAD:  inject_gamepad(ev);  break;
            default: break;
        }
    }

private:

    // ─── Windows ─────────────────────────────────────────────────
#if defined(_WIN32)
#include <windows.h>

    void init() {}
    void shutdown() {}

    void inject_keyboard(const InputEvent& ev) {
        INPUT in{};
        in.type = INPUT_KEYBOARD;
        in.ki.wVk = ev.code;
        in.ki.dwFlags = (ev.type == EV_KEY_UP) ? KEYEVENTF_KEYUP : 0;
        SendInput(1, &in, sizeof(INPUT));
    }

    void inject_mouse(const InputEvent& ev) {
        INPUT in{};
        in.type = INPUT_MOUSE;
        if (ev.type == EV_MOUSE_MOVE) {
            in.mi.dx = ev.value;
            in.mi.dy = ev.value2;
            in.mi.dwFlags = MOUSEEVENTF_MOVE;
        } else if (ev.type == EV_MOUSE_BTN) {
            // Map button flags to SendInput flags
            bool press = (ev.value == 1);
            if (ev.code & 0x0001) in.mi.dwFlags |= press ? MOUSEEVENTF_LEFTDOWN  : MOUSEEVENTF_LEFTUP;
            if (ev.code & 0x0004) in.mi.dwFlags |= press ? MOUSEEVENTF_RIGHTDOWN : MOUSEEVENTF_RIGHTUP;
            if (ev.code & 0x0010) in.mi.dwFlags |= press ? MOUSEEVENTF_MIDDLEDOWN: MOUSEEVENTF_MIDDLEUP;
        } else if (ev.type == EV_MOUSE_SCROLL) {
            in.mi.dwFlags    = MOUSEEVENTF_WHEEL;
            in.mi.mouseData  = (DWORD)ev.value;
        }
        SendInput(1, &in, sizeof(INPUT));
    }

    void inject_gamepad(const InputEvent& ev) {
        // Gamepad injection on Windows requires ViGEm Bus driver.
        // When ViGEm is present, use vigem_target_x360_update().
        // Stub prints a warning if ViGEm is not available.
        // Users can install ViGEm from https://github.com/nefarius/ViGEmBus
        std::cout << "[inject] Gamepad injection requires ViGEm Bus on Windows.\n";
    }

    // ─── macOS ───────────────────────────────────────────────────
#elif defined(__APPLE__)
#include <ApplicationServices/ApplicationServices.h>
#include <IOKit/hid/IOHIDManager.h>

    void init() {}
    void shutdown() {}

    void inject_keyboard(const InputEvent& ev) {
        CGEventRef e = CGEventCreateKeyboardEvent(
            nullptr, (CGKeyCode)ev.code, ev.type == EV_KEY_DOWN);
        CGEventPost(kCGSessionEventTap, e);
        CFRelease(e);
    }

    void inject_mouse(const InputEvent& ev) {
        if (ev.type == EV_MOUSE_MOVE) {
            CGEventRef e = CGEventCreateMouseEvent(
                nullptr, kCGEventMouseMoved, CGPointMake(0, 0), kCGMouseButtonLeft);
            CGEventSetIntegerValueField(e, kCGMouseEventDeltaX, ev.value);
            CGEventSetIntegerValueField(e, kCGMouseEventDeltaY, ev.value2);
            CGEventPost(kCGSessionEventTap, e);
            CFRelease(e);
        } else if (ev.type == EV_MOUSE_BTN) {
            CGEventType type = (ev.code == 0)
                ? (ev.value ? kCGEventLeftMouseDown  : kCGEventLeftMouseUp)
                : (ev.value ? kCGEventRightMouseDown : kCGEventRightMouseUp);
            CGMouseButton btn = (ev.code == 0) ? kCGMouseButtonLeft : kCGMouseButtonRight;
            CGPoint pos = CGEventGetLocation(CGEventCreate(nullptr));
            CGEventRef e = CGEventCreateMouseEvent(nullptr, type, pos, btn);
            CGEventPost(kCGSessionEventTap, e);
            CFRelease(e);
        } else if (ev.type == EV_MOUSE_SCROLL) {
            CGEventRef e = CGEventCreateScrollWheelEvent(
                nullptr, kCGScrollEventUnitLine, 1, ev.value);
            CGEventPost(kCGSessionEventTap, e);
            CFRelease(e);
        }
    }

    void inject_gamepad(const InputEvent& ev) {
        // macOS virtual HID requires a kernel extension or Karabiner-DriverKit.
        // Most users will rely on apps that read the network directly.
        (void)ev;
        std::cout << "[inject] Gamepad injection on macOS requires Karabiner-DriverKit.\n";
    }

    // ─── Linux ───────────────────────────────────────────────────
#else
#include <fcntl.h>
#include <unistd.h>
#include <linux/uinput.h>
#include <cstring>

    int uinput_kb_  = -1;
    int uinput_ms_  = -1;
    int uinput_gp_  = -1;

    int make_uinput(const char* name, uint32_t ev_bits,
                    uint32_t key_bits_lo, uint32_t key_bits_hi) {
        int fd = open("/dev/uinput", O_WRONLY | O_NONBLOCK);
        if (fd < 0) {
            fd = open("/dev/input/uinput", O_WRONLY | O_NONBLOCK);
        }
        if (fd < 0) {
            std::cerr << "[inject] Cannot open uinput: " << strerror(errno)
                      << " — run as root or add user to 'input' group\n";
            return -1;
        }

        ioctl(fd, UI_SET_EVBIT, EV_SYN);
        if (ev_bits & (1 << EV_KEY)) {
            ioctl(fd, UI_SET_EVBIT, EV_KEY);
            for (int i = 0; i < 256; i++) ioctl(fd, UI_SET_KEYBIT, i);
        }
        if (ev_bits & (1 << EV_REL)) {
            ioctl(fd, UI_SET_EVBIT, EV_REL);
            ioctl(fd, UI_SET_RELBIT, REL_X);
            ioctl(fd, UI_SET_RELBIT, REL_Y);
            ioctl(fd, UI_SET_RELBIT, REL_WHEEL);
        }
        if (ev_bits & (1 << EV_ABS)) {
            ioctl(fd, UI_SET_EVBIT, EV_ABS);
            struct uinput_abs_setup abs{};
            abs.code = ABS_X; abs.absinfo = {0, -32768, 32767, 16, 128, 0};
            ioctl(fd, UI_ABS_SETUP, &abs);
            abs.code = ABS_Y;  ioctl(fd, UI_ABS_SETUP, &abs);
            abs.code = ABS_RX; ioctl(fd, UI_ABS_SETUP, &abs);
            abs.code = ABS_RY; ioctl(fd, UI_ABS_SETUP, &abs);
        }

        struct uinput_setup setup{};
        strncpy(setup.name, name, UINPUT_MAX_NAME_SIZE - 1);
        setup.id.bustype = BUS_VIRTUAL;
        setup.id.vendor  = 0x1234;
        setup.id.product = 0x5678;
        ioctl(fd, UI_DEV_SETUP, &setup);
        ioctl(fd, UI_DEV_CREATE);
        return fd;
    }

    void emit(int fd, uint16_t type, uint16_t code, int32_t value) {
        if (fd < 0) return;
        struct input_event ie{};
        ie.type  = type;
        ie.code  = code;
        ie.value = value;
        write(fd, &ie, sizeof(ie));
        ie.type = EV_SYN; ie.code = SYN_REPORT; ie.value = 0;
        write(fd, &ie, sizeof(ie));
    }

    void init() {
        uinput_kb_ = make_uinput("CouchLink Keyboard",
                                  (1 << EV_KEY), 0, 0);
        uinput_ms_ = make_uinput("CouchLink Mouse",
                                  (1 << EV_KEY) | (1 << EV_REL), 0, 0);
        uinput_gp_ = make_uinput("CouchLink Gamepad",
                                  (1 << EV_KEY) | (1 << EV_ABS), 0, 0);
    }

    void shutdown() {
        for (int fd : {uinput_kb_, uinput_ms_, uinput_gp_}) {
            if (fd >= 0) { ioctl(fd, UI_DEV_DESTROY); close(fd); }
        }
    }

    void inject_keyboard(const InputEvent& ev) {
        emit(uinput_kb_, EV_KEY, ev.code, (ev.type == EV_KEY_DOWN) ? 1 : 0);
    }

    void inject_mouse(const InputEvent& ev) {
        if (ev.type == EV_MOUSE_MOVE) {
            emit(uinput_ms_, EV_REL, REL_X, ev.value);
            emit(uinput_ms_, EV_REL, REL_Y, ev.value2);
        } else if (ev.type == EV_MOUSE_BTN) {
            uint16_t btn = (ev.code == 0) ? BTN_LEFT :
                           (ev.code == 1) ? BTN_RIGHT : BTN_MIDDLE;
            emit(uinput_ms_, EV_KEY, btn, ev.value);
        } else if (ev.type == EV_MOUSE_SCROLL) {
            emit(uinput_ms_, EV_REL, REL_WHEEL, ev.value);
        }
    }

    void inject_gamepad(const InputEvent& ev) {
        if (ev.type == EV_GAMEPAD_BTN) {
            emit(uinput_gp_, EV_KEY, BTN_SOUTH + (ev.code & 0xFF), ev.value);
        } else if (ev.type == EV_GAMEPAD_AXIS) {
            uint16_t axis = (ev.code & 0x01) ? ABS_RX : ABS_X;
            emit(uinput_gp_, EV_ABS, axis,   ev.value);
            emit(uinput_gp_, EV_ABS, axis+1, ev.value2);
        }
    }
#endif
};
