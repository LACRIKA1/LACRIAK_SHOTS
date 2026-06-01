from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


APP_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
DATA_DIR = APP_ROOT / "data"
CAPTURE_DIR = APP_ROOT / "captures"
SETTINGS_FILE = DATA_DIR / "settings.json"


def default_hotkeys() -> dict[str, str]:
    return {
        "fullscreen": "print screen",
        "region": "ctrl+print screen",
        "active_window": "alt+print screen",
        "record_mp4": "shift+print screen",
        "record_gif": "ctrl+shift+print screen",
    }


@dataclass(slots=True)
class AppSettings:
    save_dir: str = str(CAPTURE_DIR)
    filename_template: str = "{type}_{date}_{time}_{window}"
    image_format: str = "png"
    copy_to_clipboard: bool = True
    open_editor_after_capture: bool = False
    hide_main_window: bool = True
    screenshot_delay_ms: int = 250
    recording_fps: int = 10
    gif_frame_ms: int = 150
    hotkeys_enabled: bool = True
    hotkeys: dict[str, str] = field(default_factory=default_hotkeys)


def ensure_directories(settings: AppSettings | None = None) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CAPTURE_DIR.mkdir(parents=True, exist_ok=True)
    if settings is not None:
        Path(settings.save_dir).expanduser().mkdir(parents=True, exist_ok=True)


def _merge_settings(raw: dict[str, Any]) -> AppSettings:
    defaults = AppSettings()
    allowed = {field.name for field in AppSettings.__dataclass_fields__.values()}
    values = {key: value for key, value in raw.items() if key in allowed}

    hotkeys = default_hotkeys()
    hotkeys.update(values.get("hotkeys") or {})
    values["hotkeys"] = hotkeys

    settings = AppSettings(**{**asdict(defaults), **values})
    if settings.image_format.lower() not in {"png", "jpg", "jpeg", "bmp"}:
        settings.image_format = "png"
    settings.recording_fps = max(1, min(int(settings.recording_fps), 60))
    settings.gif_frame_ms = max(50, min(int(settings.gif_frame_ms), 1000))
    settings.screenshot_delay_ms = max(0, min(int(settings.screenshot_delay_ms), 5000))
    return settings


def load_settings() -> AppSettings:
    ensure_directories()
    if not SETTINGS_FILE.exists():
        settings = AppSettings()
        save_settings(settings)
        return settings

    try:
        raw = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        settings = _merge_settings(raw)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        settings = AppSettings()

    ensure_directories(settings)
    return settings


def save_settings(settings: AppSettings) -> None:
    ensure_directories(settings)
    SETTINGS_FILE.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def sanitize_fragment(value: str | None, fallback: str = "screen", max_len: int = 80) -> str:
    text = (value or "").strip()
    if not text:
        text = fallback
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" ._")
    if not text:
        text = fallback
    return text[:max_len].strip(" ._") or fallback


def normalize_extension(extension: str) -> str:
    extension = extension.lower().lstrip(".")
    return "jpg" if extension == "jpeg" else extension


def build_filename(
    settings: AppSettings,
    capture_type: str,
    extension: str,
    window_title: str = "",
    moment: datetime | None = None,
) -> str:
    moment = moment or datetime.now()
    mapping = {
        "type": sanitize_fragment(capture_type, "capture", 40),
        "date": moment.strftime("%Y-%m-%d"),
        "time": moment.strftime("%H-%M-%S"),
        "datetime": moment.strftime("%Y-%m-%d_%H-%M-%S"),
        "window": sanitize_fragment(window_title, "screen"),
        "year": moment.strftime("%Y"),
        "month": moment.strftime("%m"),
        "day": moment.strftime("%d"),
        "hour": moment.strftime("%H"),
        "minute": moment.strftime("%M"),
        "second": moment.strftime("%S"),
    }

    try:
        stem = settings.filename_template.format(**mapping)
    except (KeyError, ValueError):
        stem = "{type}_{date}_{time}_{window}".format(**mapping)

    stem = sanitize_fragment(stem, "capture", 150)
    return f"{stem}.{normalize_extension(extension)}"


def unique_capture_path(
    settings: AppSettings,
    capture_type: str,
    extension: str,
    window_title: str = "",
) -> Path:
    directory = Path(settings.save_dir).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    base = directory / build_filename(settings, capture_type, extension, window_title)
    if not base.exists():
        return base

    for index in range(1, 1000):
        candidate = base.with_name(f"{base.stem}_{index:03d}{base.suffix}")
        if not candidate.exists():
            return candidate

    return base.with_name(f"{base.stem}_{datetime.now().strftime('%f')}{base.suffix}")
