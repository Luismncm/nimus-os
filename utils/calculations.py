from __future__ import annotations

from collections.abc import Iterable, Mapping


def progress(required: int, completed: int) -> float:
    """Percent of actual units, never an average of percentages."""
    return round(100 * completed / required, 1) if required else 0.0


def totals(parts: Iterable[Mapping]) -> dict:
    rows = list(parts)
    required = sum(p["quantity_required"] for p in rows)
    completed = sum(p["quantity_completed"] for p in rows)
    return {"required_total": required, "completed_total": completed,
            "remaining_total": required - completed, "progress": progress(required, completed)}
