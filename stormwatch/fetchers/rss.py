"""Hämtar och parsar RSS-flöden från nyhetskällor."""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; StormWatch/1.0; +storm-monitor)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.5",
}


class RssFetcher:
    async def fetch_all(
        self, feeds: list[dict], client: httpx.AsyncClient
    ) -> list[dict]:
        tasks = [self._fetch_feed(f, client) for f in feeds]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        items: list[dict] = []
        for feed_cfg, result in zip(feeds, results):
            if isinstance(result, Exception):
                if not feed_cfg.get("optional", False):
                    logger.warning("RSS-fel %s: %s", feed_cfg["url"], result)
            else:
                items.extend(result)
        return items

    async def _fetch_feed(
        self, feed_cfg: dict, client: httpx.AsyncClient
    ) -> list[dict]:
        url = feed_cfg["url"]
        source = feed_cfg["source"]
        optional = feed_cfg.get("optional", False)

        try:
            response = await client.get(url, timeout=15.0, headers=HEADERS)
            response.raise_for_status()
            raw_content = response.content
        except Exception as exc:
            if optional:
                logger.debug("Valfritt flöde %s ej tillgängligt: %s", url, exc)
                return []
            raise

        loop = asyncio.get_event_loop()
        parsed = await loop.run_in_executor(None, feedparser.parse, raw_content)

        items = []
        for entry in parsed.entries:
            uid = entry.get("id") or entry.get("link") or entry.get("title", "")
            title = _clean_text(entry.get("title") or "")
            link = entry.get("link") or ""
            summary = _clean_html(entry.get("summary") or entry.get("description") or "")
            published = _parse_date(entry)

            if not title or not link:
                continue

            items.append({
                "uid": f"{source}:{uid}",
                "source": source,
                "title": title,
                "url": link,
                "summary": summary,
                "published": published,
            })

        logger.debug("Hämtade %d poster från %s (%s)", len(items), source, url)
        return items


def _parse_date(entry: dict) -> Optional[datetime]:
    """Konverterar feedparser-datum till datetime i UTC.
    Returnerar det senaste av published/updated/created för att fånga artikeluppdateringar.
    """
    dates: list[datetime] = []
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        val = entry.get(field)
        if val and isinstance(val, time.struct_time):
            try:
                dates.append(datetime(*val[:6], tzinfo=timezone.utc))
            except (ValueError, TypeError):
                pass
    if not dates:
        return None
    return max(dates)


def _clean_text(text: str) -> str:
    return text.strip()


def _clean_html(html: str) -> str:
    """Tar bort enkla HTML-taggar för RSS-sammanfattningar."""
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
