from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass


@dataclass(slots=True)
class WindowInfo:
    hwnd: int
    title: str
    left: int
    top: int
    width: int
    height: int

    @property
    def monitor(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


def is_windows() -> bool:
    return sys.platform.startswith("win")


def _user32():
    if not is_windows():
        return None
    return ctypes.windll.user32


def _window_title(hwnd: int) -> str:
    user32 = _user32()
    if user32 is None:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value.strip()


def _window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    user32 = _user32()
    if user32 is None:
        return None
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width <= 0 or height <= 0:
        return None
    return rect.left, rect.top, width, height


def _to_info(hwnd: int) -> WindowInfo | None:
    title = _window_title(hwnd)
    rect = _window_rect(hwnd)
    if not title or rect is None:
        return None
    left, top, width, height = rect
    return WindowInfo(int(hwnd), title, left, top, width, height)


def list_open_windows(exclude_hwnds: set[int] | None = None) -> list[WindowInfo]:
    user32 = _user32()
    if user32 is None:
        return []

    exclude_hwnds = exclude_hwnds or set()
    ignored_titles = {
        "Program Manager",
        "Settings",
        "Microsoft Text Input Application",
        "Windows Input Experience",
    }
    windows: list[WindowInfo] = []

    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def enum_proc(hwnd: int, _lparam: int) -> bool:
        if int(hwnd) in exclude_hwnds:
            return True
        if not user32.IsWindowVisible(hwnd):
            return True
        info = _to_info(int(hwnd))
        if info is None or info.title in ignored_titles:
            return True
        if info.width < 32 or info.height < 32:
            return True
        windows.append(info)
        return True

    user32.EnumWindows(callback_type(enum_proc), 0)
    return windows


def activate_window(hwnd: int) -> bool:
    user32 = _user32()
    if user32 is None:
        return False
    SW_RESTORE = 9
    user32.ShowWindow(wintypes.HWND(hwnd), SW_RESTORE)
    return bool(user32.SetForegroundWindow(wintypes.HWND(hwnd)))


def active_window() -> WindowInfo | None:
    user32 = _user32()
    if user32 is None:
        return None
    hwnd = int(user32.GetForegroundWindow())
    if hwnd == 0:
        return None
    return _to_info(hwnd)


def window_under_cursor() -> WindowInfo | None:
    user32 = _user32()
    if user32 is None:
        return None
    point = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        return None
    hwnd = int(user32.WindowFromPoint(point))
    if hwnd == 0:
        return None
    return _to_info(hwnd)

