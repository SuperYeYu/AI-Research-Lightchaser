from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path


class SeenStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.records: dict[str, dict[str, str]] = {}

    def _make_key(self, source: str, canonical_id: str) -> str:
        return f"{source}::{canonical_id}"

    def load(self) -> None:
        if not self.path.exists():
            self.records = {}
            return
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.records = payload if isinstance(payload, dict) else {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.records, ensure_ascii=False, indent=2), encoding="utf-8")

    def should_skip(self, source: str, canonical_id: str, now: datetime, window_hours: int) -> bool:
        record = self.records.get(self._make_key(source, canonical_id))
        if not record or not record.get("last_sent_at"):
            return False
        last_sent_at = datetime.fromisoformat(record["last_sent_at"])
        return last_sent_at >= now.astimezone(UTC) - timedelta(hours=window_hours)

    def mark_sent(self, source: str, canonical_id: str, sent_at: datetime) -> None:
        key = self._make_key(source, canonical_id)
        existing = self.records.get(key, {})
        self.records[key] = {
            "source": source,
            "canonical_id": canonical_id,
            "first_seen_at": existing.get("first_seen_at", sent_at.astimezone(UTC).isoformat()),
            "last_sent_at": sent_at.astimezone(UTC).isoformat(),
        }
