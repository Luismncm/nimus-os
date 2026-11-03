from __future__ import annotations

import os
from datetime import date, datetime
from zoneinfo import ZoneInfo


def now() -> datetime:
    return datetime.now(ZoneInfo(os.environ.get("NIMUS_TIMEZONE", "America/Mexico_City"))).replace(tzinfo=None)


def timestamp() -> str:
    return now().isoformat(timespec="microseconds")


def parse_deadline(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def parse_end(value: str | None) -> datetime | None:
    if not value:
        return None
    result = datetime.fromisoformat(value)
    if result.tzinfo is not None:
        raise ValueError("Usa la hora local del taller, sin zona horaria en el campo.")
    return result


def fmt(value: str | None, *, time: bool = False) -> str:
    if not value:
        return "Sin fecha"
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M" if time else "%d/%m/%Y")
    except ValueError:
        return value
