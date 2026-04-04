"""Gemensamma hjälpfunktioner för fetchers."""
from __future__ import annotations

from datetime import datetime
from typing import Optional


def first_str(obj: dict, *keys: str) -> Optional[str]:
    for key in keys:
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return None


def parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
