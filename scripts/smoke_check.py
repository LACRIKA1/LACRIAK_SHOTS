from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QApplication

from core.capture import CaptureService
from core.config import AppSettings, build_filename
from core.editor import EditorCanvas
from core.hotkeys import normalize_hotkey, parse_hotkey


def check_hotkeys() -> None:
    cases = {
        "print screen": "Print Screen",
        "ctrl+page up": "Ctrl+Page Up",
        "c+v": "C+V",
        "mouse 4": "Mouse 4",
        "ctrl+wheel up": "Ctrl+Wheel Up",
        "shift+f9": "Shift+F9",
    }
    for source, expected in cases.items():
        actual = normalize_hotkey(source)
        assert actual == expected, (source, actual, expected)
        assert parse_hotkey(source)
    assert normalize_hotkey("unknown-key") is None
    print(f"hotkeys: ok ({len(cases)} valid cases, 1 rejected case)")


def check_filename() -> None:
    settings = AppSettings(filename_template="{type}_{date}_{time}_{window}")
    name = build_filename(
        settings,
        "region",
        "png",
        'Отчет: этап / 1?',
        datetime(2026, 6, 1, 12, 34, 56),
    )
    assert name == "region_2026-06-01_12-34-56_Отчет_ этап _ 1.png", name
    print(f"filename: ok ({name})")


def check_monitors() -> None:
    service = CaptureService(AppSettings())
    monitors = service.available_monitors()
    assert monitors and monitors[0]["width"] > 0 and monitors[0]["height"] > 0
    print(f"monitors: ok ({len(monitors)} entries, virtual desktop {monitors[0]['width']}x{monitors[0]['height']})")


def check_editor(app: QApplication) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        image_path = Path(temporary) / "sample.png"
        Image.new("RGB", (640, 360), "#20242a").save(image_path)
        canvas = EditorCanvas(image_path)
        canvas.set_tool("rect")
        canvas.set_color(QColor("#ff4d2e"))
        painter = QPainter(canvas.pixmap)
        canvas._draw_shape(painter, QPoint(40, 40), QPoint(280, 190))
        painter.end()
        saved = canvas.save()
        canvas.copy_to_clipboard()
        assert saved.exists() and saved.stat().st_size > 0
        assert not app.clipboard().pixmap().isNull()
        print(f"editor: ok ({saved.name}, clipboard pixmap available)")


def main() -> None:
    app = QApplication.instance() or QApplication([])
    check_hotkeys()
    check_filename()
    check_monitors()
    check_editor(app)
    print("smoke: all checks passed")


if __name__ == "__main__":
    main()
