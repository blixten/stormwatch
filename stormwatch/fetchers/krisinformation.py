"""Hämtar nyheter från Krisinformation.se API."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

API_URL = "https://api.krisinformation.se/v3/news"
SOURCE = "KRIS"


class KrisinformationFetcher:
    async def fetch_news(self, counties: list[int], client: httpx.AsyncClient) -> list[dict]:
        params = {}
        if counties:
            params["counties"] = ",".join(str(c) for c in counties)

        try:
            response = await client.get(API_URL, params=params, timeout=12.0)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.warning("Krisinformation API-fel: %s", exc)
            return []

        return _parse_items(data)


def _parse_items(data: Any) -> list[dict]:
    entries = _extract_entries(data)
    items: list[dict] = []
    for entry in entries:
        title = _first_str(entry, "Title", "title", "Headline", "headline")
        url = _first_str(entry, "Link", "link", "Url", "url")
        summary = _first_str(entry, "BodyText", "bodyText", "Summary", "summary", "Description", "description")
        uid_raw = _first_str(entry, "Identifier", "identifier", "Id", "id", "NewsId", "newsId")
        published_raw = _first_str(entry, "Published", "published", "PublishedDate", "publishedDate", "Date", "date")

        if not title:
            continue
        if not url:
            url = "https://www.krisinformation.se/"
        uid = uid_raw or url or title

        items.append({
            "uid": f"{SOURCE}:{uid}",
            "source": SOURCE,
            "title": title.strip(),
            "url": url.strip(),
            "summary": (summary or "").strip(),
            "published": _parse_iso_datetime(published_raw),
        })
    return items


def _extract_entries(data: Any) -> list[dict]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []

    for key in ("news", "News", "items", "Items", "results", "Results"):
        val = data.get(key)
        if isinstance(val, list):
            return [x for x in val if isinstance(x, dict)]

    return [data]


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
