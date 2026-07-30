from __future__ import annotations

from datetime import datetime, timezone


def normalize_scheduled_at(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def schedule_is_due(
    scheduled_at: str,
    *,
    now: datetime | None = None,
) -> bool:
    normalized = normalize_scheduled_at(scheduled_at)
    if not normalized:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    scheduled = datetime.fromisoformat(normalized)
    return scheduled <= current.astimezone(timezone.utc)


def format_scheduled_local(scheduled_at: str) -> str:
    normalized = normalize_scheduled_at(scheduled_at)
    if not normalized:
        return ""
    scheduled = datetime.fromisoformat(normalized).astimezone()
    return scheduled.strftime("%Y-%m-%d %H:%M")
