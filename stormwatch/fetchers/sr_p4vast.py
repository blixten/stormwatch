"""Hämtar nyheter från Sveriges Radio P4 Väst via HTML-skrapning."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

NEWS_URL = "https://www.sverigesradio.se/nyheter/p4-vast"
BASE_URL = "https://www.sverigesradio.se"
SOURCE = "P4V"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.5",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
}

# SR:s webbplats är en React-app; klassnamn kan variera – testar i ordning
ARTICLE_LINK_SELECTORS = [
    "[class*='article-teaser'] a[href]",
    "[class*='nyhetslista'] a[href]",
    "[class*='news-list'] a[href]",
    "[class*='hydra-'] a[href]",
    "article a[href]",
    "h2 a[href]",
    "h3 a[href]",
]

# SR-artiklar ska ligga under /artikel/ eller /nyheter/
VALID_PATH_PREFIXES = ("/artikel/", "/nyheter/")

MAX_ARTICLES = 30
MIN_TITLE_LENGTH = 10


class SrP4VastFetcher:
    """Hämtar nyhetsartiklar från SR P4 Väst via HTML-skrapning."""

    async def fetch_news(self, client: httpx.AsyncClient) -> list[dict]:
        try:
            response = await client.get(NEWS_URL, timeout=15.0, headers=HEADERS)
            response.raise_for_status()
        except Exception as exc:
            logger.debug("SR P4 Väst ej tillgänglig: %s", exc)
            return []

        encoding = response.encoding or "utf-8"
        html = response.content.decode(encoding, errors="replace")
        items = _parse_articles(html)
        logger.debug("SR P4 Väst: %d artiklar hittade", len(items))
        return items


def _parse_articles(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    seen_urls: set[str] = set()
    items: list[dict] = []

    for selector in ARTICLE_LINK_SELECTORS:
        for link in soup.select(selector):
            href = str(link.get("href") or "")
            if not href:
                continue

            url = urljoin(BASE_URL, href)
            if not _is_sr_article(url):
                continue
            if url in seen_urls:
                continue

            title = _extract_title(link)
            if not title or len(title) < MIN_TITLE_LENGTH:
                continue

            seen_urls.add(url)
            items.append({
                "uid": f"{SOURCE}:{url}",
                "source": SOURCE,
                "title": title,
                "url": url,
                "summary": _extract_summary(link),
                "published": _extract_published(link, soup),
            })

            if len(items) >= MAX_ARTICLES:
                return items

    return items


def _is_sr_article(url: str) -> bool:
    """Accepterar bara SR-interna artikellänkar."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").removeprefix("www.")
        if host != "sverigesradio.se":
            return False
        return any(parsed.path.startswith(p) for p in VALID_PATH_PREFIXES)
    except Exception:
        return False


def _extract_title(link) -> str:
    """Hämtar länktext eller närmaste rubrikelement."""
    title = link.get_text(strip=True)
    if title and len(title) >= MIN_TITLE_LENGTH:
        return title
    parent = link.find_parent(["h1", "h2", "h3", "h4"])
    if parent:
        return parent.get_text(strip=True)
    return title


def _extract_summary(link) -> str:
    """Försöker hitta ingress/sammanfattning i samma artikel-container."""
    container = link.find_parent("article") or link.find_parent(
        lambda t: t.name in ("li", "div") and t.get("class")
    )
    if not container:
        return ""
    # Letar efter stycke- eller ingress-element i samma container
    for tag in container.select("p, [class*='preamble'], [class*='ingress'], [class*='description']"):
        text = tag.get_text(strip=True)
        if len(text) > 20:
            return text
    return ""


def _extract_published(link, soup: BeautifulSoup) -> Optional[datetime]:
    """Extraherar publiceringsdatum från time[datetime] eller meta-taggar."""
    # Sök uppåt från länken
    candidates = [link.find_parent("article")] + list(link.parents)
    for node in candidates:
        if node is None or not hasattr(node, "select_one"):
            continue
        time_tag = node.select_one("time[datetime]")
        if time_tag:
            dt = _parse_datetime(str(time_tag.get("datetime") or ""))
            if dt is not None:
                return dt

    # Fallback: meta-taggar på sidan (finns om det bara är en artikel)
    for prop in ("article:published_time", "article:modified_time"):
        meta = soup.select_one(f'meta[property="{prop}"]')
        if meta:
            dt = _parse_datetime(str(meta.get("content") or ""))
            if dt is not None:
                return dt
    return None


def _parse_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        # Normalisera till UTC-medveten datetime
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None
