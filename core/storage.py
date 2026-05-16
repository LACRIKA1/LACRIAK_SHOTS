from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .config import DATA_DIR


HISTORY_FILE = DATA_DIR / "history.json"


@dataclass(slots=True)
class CaptureRecord:
    path: str
    kind: str
    created_at: str
    width: int = 0
    height: int = 0
    source_title: str = ""
    copied_to_clipboard: bool = False
    note: str = ""

    @classmethod
    def create(
        cls,
        path: Path,
        kind: str,
        width: int,
        height: int,
        source_title: str = "",
        copied_to_clipboard: bool = False,
        note: str = "",
    ) -> "CaptureRecord":
        return cls(
            path=str(path),
            kind=kind,
            created_at=datetime.now().isoformat(timespec="seconds"),
            width=width,
            height=height,
            source_title=source_title,
            copied_to_clipboard=copied_to_clipboard,
            note=note,
        )


class HistoryStore:
    def __init__(self, path: Path = HISTORY_FILE) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[CaptureRecord]:
        if not self.path.exists():
            return []
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        records: list[CaptureRecord] = []
        for row in rows:
            if isinstance(row, dict) and row.get("path") and row.get("kind"):
                try:
                    records.append(CaptureRecord(**row))
                except TypeError:
                    continue
        return records

    def save(self, records: list[CaptureRecord]) -> None:
        self.path.write_text(
            json.dumps([asdict(record) for record in records], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def add(self, record: CaptureRecord) -> list[CaptureRecord]:
        records = self.load()
        records.insert(0, record)
        records = records[:500]
        self.save(records)
        return records

