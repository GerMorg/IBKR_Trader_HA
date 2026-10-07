from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _segments_for_date(schedule: str, date_key: str) -> list[str]:
    for part in str(schedule or "").split(";"):
        if not part.startswith(f"{date_key}:"):
            continue
        value = part.split(":", 1)[1].strip()
        return [] if value.upper() == "CLOSED" else value.split(",")
    return []


def is_liquid_now(schedule: str, time_zone_id: str, now: datetime | None = None) -> bool:
    if not schedule:
        return False
    try:
        zone = ZoneInfo(time_zone_id or "UTC")
    except ZoneInfoNotFoundError:
        return False
    current = (now or datetime.now().astimezone()).astimezone(zone)
    current_minutes = current.hour * 60 + current.minute + current.second / 60

    for date in (current.date(), current.date() - timedelta(days=1)):
        key = date.strftime("%Y%m%d")
        for segment in _segments_for_date(schedule, key):
            if "-" not in segment:
                continue
            start_text, end_text = segment.split("-", 1)
            if len(start_text) < 4 or len(end_text) < 4:
                continue
            try:
                start = int(start_text[:2]) * 60 + int(start_text[2:4])
                end = int(end_text[:2]) * 60 + int(end_text[2:4])
            except ValueError:
                continue
            if start <= end:
                if date == current.date() and start <= current_minutes <= end:
                    return True
            else:
                if date == current.date() and current_minutes >= start:
                    return True
                if date == current.date() - timedelta(days=1) and current_minutes <= end:
                    return True
    return False
