from __future__ import annotations

from pathlib import Path

import cv2
import mss
import numpy as np
from PIL import Image
from PySide6.QtCore import QThread, Signal

from .config import AppSettings, unique_capture_path


class RecorderThread(QThread):
    finished_recording = Signal(object)
    failed = Signal(str)
    status = Signal(str)

    def __init__(
        self,
        settings: AppSettings,
        mode: str = "mp4",
        monitor: dict[str, int] | None = None,
        source_title: str = "screen",
    ) -> None:
        super().__init__()
        self.settings = settings
        self.mode = mode
        self.monitor = monitor
        self.source_title = source_title
        self._recording = True

    def stop(self) -> None:
        self._recording = False

    def run(self) -> None:
        try:
            with mss.MSS() as sct:
                monitor = self.monitor or sct.monitors[1 if len(sct.monitors) > 1 else 0]
                if self.mode == "gif":
                    result = self._record_gif(sct, monitor)
                else:
                    result = self._record_mp4(sct, monitor)
            self.finished_recording.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))

    def _record_mp4(self, sct: mss.MSS, monitor: dict[str, int]) -> dict[str, object]:
        fps = max(1, min(int(self.settings.recording_fps), 60))
        output = unique_capture_path(self.settings, "video", "mp4", self.source_title)
        width = int(monitor["width"])
        height = int(monitor["height"])

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(output), fourcc, float(fps), (width, height))
        if not writer.isOpened():
            raise RuntimeError("Не удалось открыть кодек MP4 для записи.")

        delay_ms = int(1000 / fps)
        frames = 0
        self.status.emit("Запись MP4 запущена.")
        try:
            while self._recording:
                raw = sct.grab(monitor)
                frame = np.array(raw)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                writer.write(frame)
                frames += 1
                QThread.msleep(delay_ms)
        finally:
            writer.release()

        return {
            "path": Path(output),
            "kind": "video",
            "width": width,
            "height": height,
            "frames": frames,
            "source_title": self.source_title,
        }

    def _record_gif(self, sct: mss.MSS, monitor: dict[str, int]) -> dict[str, object]:
        frame_ms = max(50, min(int(self.settings.gif_frame_ms), 1000))
        output = unique_capture_path(self.settings, "gif", "gif", self.source_title)
        frames: list[Image.Image] = []
        width = int(monitor["width"])
        height = int(monitor["height"])

        self.status.emit("Запись GIF запущена.")
        while self._recording:
            raw = sct.grab(monitor)
            frames.append(Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX"))
            QThread.msleep(frame_ms)

        if not frames:
            raise RuntimeError("GIF не создан: нет записанных кадров.")

        self.status.emit("Сохранение GIF...")
        first, rest = frames[0], frames[1:]
        first.save(
            output,
            save_all=True,
            append_images=rest,
            duration=frame_ms,
            loop=0,
            optimize=True,
        )
        return {
            "path": Path(output),
            "kind": "gif",
            "width": width,
            "height": height,
            "frames": len(frames),
            "source_title": self.source_title,
        }

