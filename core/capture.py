from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import mss
from PIL import Image
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from .config import AppSettings, normalize_extension, unique_capture_path


@dataclass(slots=True)
class CaptureResult:
    path: Path
    kind: str
    width: int
    height: int
    source_title: str = ""
    copied_to_clipboard: bool = False


class CaptureError(RuntimeError):
    pass


class CaptureService:
    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings

    def update_settings(self, settings: AppSettings) -> None:
        self.settings = settings

    def available_monitors(self) -> list[dict[str, int]]:
        with mss.MSS() as sct:
            return [dict(monitor) for monitor in sct.monitors]

    def capture_all(self) -> CaptureResult:
        with mss.MSS() as sct:
            return self._grab(sct.monitors[0], "full", "all-screens")

    def capture_monitor(self, monitor: dict[str, int], index: int) -> CaptureResult:
        return self.capture_rect(monitor, f"monitor-{index}", f"monitor-{index}")

    def capture_rect(
        self,
        monitor: dict[str, int],
        kind: str = "region",
        source_title: str = "",
    ) -> CaptureResult:
        width = int(monitor.get("width", 0))
        height = int(monitor.get("height", 0))
        if width < 2 or height < 2:
            raise CaptureError("Область захвата слишком мала.")
        with mss.MSS() as sct:
            return self._grab(monitor, kind, source_title)

    def capture_window(self, monitor: dict[str, int], title: str = "window") -> CaptureResult:
        return self.capture_rect(monitor, "window", title)

    def _grab(
        self,
        monitor: dict[str, int],
        kind: str,
        source_title: str,
    ) -> CaptureResult:
        extension = normalize_extension(self.settings.image_format)
        output_path = unique_capture_path(self.settings, kind, extension, source_title)

        with mss.MSS() as sct:
            raw = sct.grab(monitor)
            image = Image.frombytes("RGB", raw.size, raw.rgb)
            save_format = "JPEG" if extension == "jpg" else extension.upper()
            if extension == "jpg":
                image.save(output_path, save_format, quality=92, optimize=True)
            else:
                image.save(output_path, save_format)

        copied = False
        if self.settings.copy_to_clipboard:
            copied = self.copy_image_to_clipboard(output_path)

        return CaptureResult(
            path=output_path,
            kind=kind,
            width=raw.width,
            height=raw.height,
            source_title=source_title,
            copied_to_clipboard=copied,
        )

    @staticmethod
    def copy_image_to_clipboard(path: Path) -> bool:
        image = QImage(str(path))
        if image.isNull():
            return False
        QApplication.clipboard().setImage(image)
        return True


def wait_for_ui_to_hide(delay_ms: int) -> None:
    QApplication.processEvents()
    time.sleep(max(0, delay_ms) / 1000)

