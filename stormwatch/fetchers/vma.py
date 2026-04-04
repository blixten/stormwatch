"""Hämtar VMA-varningar från Sveriges Radio VMA API."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

API_URL = "https://vmaapi.sr.se/api/v2/alerts/feed.json"
SOURCE = "VMA"


class VmaFetcher:
    async def fetch_alerts(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            response = await client.get(API_URL, timeout=12.0)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.warning("VMA API-fel: %s", exc)
            return []

        return _parse_alerts(data)


def _parse_alerts(data: Any) -> list[dict]:
    entries = _extract_entries(data)
    items: list[dict] = []
    for entry in entries:
        title = _first_str(entry, "title", "Title", "headline", "Headline")
        if not title:
            continue
        url = _first_str(entry, "url", "Url", "link", "Link") or "https://sverigesradio.se/vma"
        summary = _first_str(entry, "description", "Description", "summary", "Summary") or ""
        alert_id = _first_str(entry, "id", "Id", "identifier", "Identifier") or url or title
        published_raw = _first_str(entry, "published", "Published", "updated", "Updated", "created", "Created")

        items.append({
            "uid": f"{SOURCE}:{alert_id}",
            "source": SOURCE,
            "title": title.strip(),
            "url": url.strip(),
            "summary": summary.strip(),
            "published": _parse_iso_datetime(published_raw),
        })

    return items


def _extract_entries(data: Any) -> list[dict]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []

    for key in ("alerts", "Alerts", "items", "Items", "entries", "Entries"):
        val = data.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]
    return []


def _first_str(obj: dict, *keys: str) -> Optional[str]:
    for key in keys:
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val
    return None


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
