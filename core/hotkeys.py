from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QObject, Signal

from .config import AppSettings


WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A
WM_XBUTTONDOWN = 0x020B
WM_XBUTTONUP = 0x020C
HC_ACTION = 0

MOUSE_LEFT = 0x1001
MOUSE_RIGHT = 0x1002
MOUSE_MIDDLE = 0x1003
MOUSE_4 = 0x1004
MOUSE_5 = 0x1005
MOUSE_WHEEL_UP = 0x1006
MOUSE_WHEEL_DOWN = 0x1007


KEY_CODES = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "caps lock": 0x14,
    "capslock": 0x14,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "page up": 0x21,
    "pageup": 0x21,
    "pgup": 0x21,
    "пэйдж ап": 0x21,
    "пейдж ап": 0x21,
    "страница вверх": 0x21,
    "page down": 0x22,
    "pagedown": 0x22,
    "pgdn": 0x22,
    "пэйдж даун": 0x22,
    "пейдж даун": 0x22,
    "страница вниз": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "arrow left": 0x25,
    "right": 0x27,
    "arrow right": 0x27,
    "up": 0x26,
    "arrow up": 0x26,
    "down": 0x28,
    "arrow down": 0x28,
    "insert": 0x2D,
    "ins": 0x2D,
    "delete": 0x2E,
    "del": 0x2E,
    "print screen": 0x2C,
    "printscreen": 0x2C,
    "prtsc": 0x2C,
    "prt sc": 0x2C,
    "win": 0x5B,
    "windows": 0x5B,
    "cmd": 0x5B,
    "menu": 0x5D,
    "num lock": 0x90,
    "numlock": 0x90,
    "scroll lock": 0x91,
    "scrolllock": 0x91,
    "mouse left": MOUSE_LEFT,
    "left mouse": MOUSE_LEFT,
    "lmb": MOUSE_LEFT,
    "лкм": MOUSE_LEFT,
    "mouse right": MOUSE_RIGHT,
    "right mouse": MOUSE_RIGHT,
    "rmb": MOUSE_RIGHT,
    "пкм": MOUSE_RIGHT,
    "mouse middle": MOUSE_MIDDLE,
    "middle mouse": MOUSE_MIDDLE,
    "mmb": MOUSE_MIDDLE,
    "скм": MOUSE_MIDDLE,
    "mouse 4": MOUSE_4,
    "mouse4": MOUSE_4,
    "xbutton1": MOUSE_4,
    "mouse 5": MOUSE_5,
    "mouse5": MOUSE_5,
    "xbutton2": MOUSE_5,
    "wheel up": MOUSE_WHEEL_UP,
    "mouse wheel up": MOUSE_WHEEL_UP,
    "wheel down": MOUSE_WHEEL_DOWN,
    "mouse wheel down": MOUSE_WHEEL_DOWN,
}

DISPLAY_NAMES = {
    0x08: "Backspace",
    0x09: "Tab",
    0x0D: "Enter",
    0x10: "Shift",
    0x11: "Ctrl",
    0x12: "Alt",
    0x13: "Pause",
    0x14: "Caps Lock",
    0x1B: "Esc",
    0x20: "Space",
    0x21: "Page Up",
    0x22: "Page Down",
    0x23: "End",
    0x24: "Home",
    0x25: "Left",
    0x26: "Up",
    0x27: "Right",
    0x28: "Down",
    0x2C: "Print Screen",
    0x2D: "Insert",
    0x2E: "Delete",
    0x5B: "Win",
    0x5D: "Menu",
    0x90: "Num Lock",
    0x91: "Scroll Lock",
    MOUSE_LEFT: "Mouse Left",
    MOUSE_RIGHT: "Mouse Right",
    MOUSE_MIDDLE: "Mouse Middle",
    MOUSE_4: "Mouse 4",
    MOUSE_5: "Mouse 5",
    MOUSE_WHEEL_UP: "Wheel Up",
    MOUSE_WHEEL_DOWN: "Wheel Down",
}

ORDER = {
    0x11: 1,
    0x10: 2,
    0x12: 3,
    0x5B: 4,
    0x5D: 5,
    MOUSE_LEFT: 30,
    MOUSE_RIGHT: 31,
    MOUSE_MIDDLE: 32,
    MOUSE_4: 33,
    MOUSE_5: 34,
    MOUSE_WHEEL_UP: 35,
    MOUSE_WHEEL_DOWN: 36,
}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


LowLevelKeyboardProc = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", wintypes.POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


LowLevelMouseProc = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_int,
    wintypes.WPARAM,
    wintypes.LPARAM,
)


class HotkeyManager(QObject):
    action_requested = Signal(str)
    status_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._keyboard_hook = None
        self._mouse_hook = None
        self._keyboard_callback = None
        self._mouse_callback = None
        self._pressed: set[int] = set()
        self._fired: set[frozenset[int]] = set()
        self._bindings: dict[frozenset[int], str] = {}
        self._keyboard = None
        self._user32 = None

    def start(self, settings: AppSettings) -> None:
        self.stop()
        if not settings.hotkeys_enabled:
            self.status_changed.emit("Глобальные горячие клавиши отключены в настройках.")
            return

        if sys.platform.startswith("win"):
            self._start_windows(settings)
        else:
            self._start_keyboard_fallback(settings)

    def stop(self) -> None:
        if sys.platform.startswith("win"):
            self._stop_windows()
        self._stop_keyboard_fallback()
        self._pressed.clear()
        self._fired.clear()

    def _start_windows(self, settings: AppSettings) -> None:
        failed: list[str] = []
        for action, sequence in settings.hotkeys.items():
            if not sequence.strip():
                continue
            parsed = parse_hotkey(sequence)
            if parsed is None:
                failed.append(sequence or action)
                continue
            self._bindings[parsed] = action

        if not self._bindings:
            self.status_changed.emit("Не удалось включить горячие клавиши: нет корректных комбинаций.")
            return

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = ctypes.c_long
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel32.GetModuleHandleW.restype = ctypes.c_void_p
        self._user32 = user32
        self._keyboard_callback = LowLevelKeyboardProc(self._keyboard_proc)
        self._mouse_callback = LowLevelMouseProc(self._mouse_proc)
        module_handle = kernel32.GetModuleHandleW(None)
        self._keyboard_hook = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            ctypes.cast(self._keyboard_callback, ctypes.c_void_p),
            module_handle,
            0,
        )
        self._mouse_hook = user32.SetWindowsHookExW(
            WH_MOUSE_LL,
            ctypes.cast(self._mouse_callback, ctypes.c_void_p),
            module_handle,
            0,
        )
        if not self._keyboard_hook or not self._mouse_hook:
            error_code = ctypes.get_last_error()
            self._stop_windows()
            self._bindings.clear()
            self.status_changed.emit(f"Не удалось включить горячие клавиши: код {error_code}.")
            return

        if failed:
            self.status_changed.emit(
                "Горячие клавиши активны. Пропущены некорректные: " + ", ".join(failed)
            )
        else:
            self.status_changed.emit("Глобальные горячие клавиши активны.")

    def _stop_windows(self) -> None:
        if self._keyboard_hook:
            user32 = self._user32 or ctypes.WinDLL("user32", use_last_error=True)
            user32.UnhookWindowsHookEx(self._keyboard_hook)
            self._keyboard_hook = None
        if self._mouse_hook:
            user32 = self._user32 or ctypes.WinDLL("user32", use_last_error=True)
            user32.UnhookWindowsHookEx(self._mouse_hook)
            self._mouse_hook = None
        self._keyboard_callback = None
        self._mouse_callback = None
        self._user32 = None
        self._bindings.clear()

    def _keyboard_proc(self, code: int, wparam: int, lparam: int) -> int:
        if code == HC_ACTION:
            data = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk = normalize_vk(int(data.vkCode))
            event = int(wparam)
            if event in {WM_KEYDOWN, WM_SYSKEYDOWN}:
                self._pressed.add(vk)
                self._check_bindings()
            elif event in {WM_KEYUP, WM_SYSKEYUP}:
                self._pressed.discard(vk)
                self._fired = {combo for combo in self._fired if combo.issubset(self._pressed)}

        user32 = self._user32 or ctypes.WinDLL("user32", use_last_error=True)
        return user32.CallNextHookEx(self._keyboard_hook, code, wparam, lparam)

    def _mouse_proc(self, code: int, wparam: int, lparam: int) -> int:
        if code == HC_ACTION:
            event = int(wparam)
            data = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            mouse_code = mouse_event_code(event, int(data.mouseData))
            if mouse_code:
                if event in {WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MBUTTONDOWN, WM_XBUTTONDOWN}:
                    self._pressed.add(mouse_code)
                    self._check_bindings()
                elif event in {WM_LBUTTONUP, WM_RBUTTONUP, WM_MBUTTONUP, WM_XBUTTONUP}:
                    self._pressed.discard(mouse_code)
                    self._fired = {combo for combo in self._fired if combo.issubset(self._pressed)}
                elif event == WM_MOUSEWHEEL:
                    self._pressed.add(mouse_code)
                    self._check_bindings()
                    self._pressed.discard(mouse_code)
                    self._fired = {combo for combo in self._fired if combo.issubset(self._pressed)}

        user32 = self._user32 or ctypes.WinDLL("user32", use_last_error=True)
        return user32.CallNextHookEx(self._mouse_hook, code, wparam, lparam)

    def _check_bindings(self) -> None:
        pressed = frozenset(self._pressed)
        for combo, action in self._bindings.items():
            if combo.issubset(pressed) and combo not in self._fired:
                self._fired.add(combo)
                self.action_requested.emit(action)

    def _start_keyboard_fallback(self, settings: AppSettings) -> None:
        try:
            import keyboard  # type: ignore

            self._keyboard = keyboard
            for action, sequence in settings.hotkeys.items():
                if not sequence.strip():
                    continue
                keyboard.add_hotkey(
                    sequence,
                    lambda action=action: self.action_requested.emit(action),
                    suppress=False,
                    trigger_on_release=True,
                )
        except Exception as exc:  # pragma: no cover - depends on OS permissions.
            self._stop_keyboard_fallback()
            self.status_changed.emit(f"Не удалось включить горячие клавиши: {exc}")
            return

        self.status_changed.emit("Глобальные горячие клавиши активны.")

    def _stop_keyboard_fallback(self) -> None:
        if self._keyboard is None:
            return
        try:
            self._keyboard.unhook_all_hotkeys()
        except Exception:
            pass
        self._keyboard = None


def parse_hotkey(sequence: str) -> frozenset[int] | None:
    tokens = [part.strip().lower() for part in sequence.replace("＋", "+").split("+") if part.strip()]
    if not tokens:
        return None

    keys: set[int] = set()
    for token in tokens:
        code = key_code(token)
        if code is None:
            return None
        keys.add(code)
    return frozenset(keys) if keys else None


def normalize_hotkey(sequence: str) -> str | None:
    parsed = parse_hotkey(sequence)
    if parsed is None:
        return None
    return "+".join(key_name(code) for code in sorted(parsed, key=lambda item: (ORDER.get(item, 20), item)))


def key_code(token: str) -> int | None:
    normalized = " ".join(token.lower().split())
    compact = normalized.replace(" ", "")
    if normalized in KEY_CODES:
        return KEY_CODES[normalized]
    if compact in KEY_CODES:
        return KEY_CODES[compact]
    if len(compact) == 1 and "a" <= compact <= "z":
        return ord(compact.upper())
    if len(compact) == 1 and "0" <= compact <= "9":
        return ord(compact)
    if compact.startswith("f") and compact[1:].isdigit():
        number = int(compact[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    return None


def key_name(code: int) -> str:
    if code in DISPLAY_NAMES:
        return DISPLAY_NAMES[code]
    if 0x30 <= code <= 0x39 or 0x41 <= code <= 0x5A:
        return chr(code)
    if 0x70 <= code <= 0x87:
        return f"F{code - 0x70 + 1}"
    return f"VK{code}"


def normalize_vk(vk: int) -> int:
    if vk in {0xA0, 0xA1}:
        return 0x10
    if vk in {0xA2, 0xA3}:
        return 0x11
    if vk in {0xA4, 0xA5}:
        return 0x12
    if vk in {0x5B, 0x5C}:
        return 0x5B
    return vk


def hotkey_from_codes(codes: set[int]) -> str | None:
    if not codes:
        return None
    return "+".join(key_name(code) for code in sorted(codes, key=lambda item: (ORDER.get(item, 20), item)))


def mouse_event_code(event: int, mouse_data: int) -> int | None:
    if event in {WM_LBUTTONDOWN, WM_LBUTTONUP}:
        return MOUSE_LEFT
    if event in {WM_RBUTTONDOWN, WM_RBUTTONUP}:
        return MOUSE_RIGHT
    if event in {WM_MBUTTONDOWN, WM_MBUTTONUP}:
        return MOUSE_MIDDLE
    if event in {WM_XBUTTONDOWN, WM_XBUTTONUP}:
        button = (mouse_data >> 16) & 0xFFFF
        return MOUSE_4 if button == 1 else MOUSE_5 if button == 2 else None
    if event == WM_MOUSEWHEEL:
        delta = ctypes.c_short((mouse_data >> 16) & 0xFFFF).value
        return MOUSE_WHEEL_UP if delta > 0 else MOUSE_WHEEL_DOWN
    return None
