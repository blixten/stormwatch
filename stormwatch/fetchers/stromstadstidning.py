"""Hämtar nyheter från Strömstads Tidnings webbplats via HTML-skrapning."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://www.stromstadstidning.se"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.5",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
}

# CSS-selektorer att prova i ordning för att hitta artikellänkar
ARTICLE_LINK_SELECTORS = [
    "article a[href]",
    ".article-teaser a[href]",
    ".news-item a[href]",
    ".teaser a[href]",
    ".teaserItem a[href]",
    ".entry-title a[href]",
    ".post-title a[href]",
    "h2 a[href]",
    "h3 a[href]",
]

MAX_ARTICLES = 25
MIN_TITLE_LENGTH = 10


class StromstadsTidningFetcher:
    """Hämtar nyhetsartiklar från Strömstads Tidning via HTML-skrapning."""

    async def fetch_news(self, client: httpx.AsyncClient) -> list[dict]:
        """Hämtar och returnerar nyhetsartiklar i standardformat. Returnerar [] vid fel."""
        try:
            response = await client.get(BASE_URL, timeout=15.0, headers=HEADERS)
            response.raise_for_status()
        except Exception as exc:
            logger.debug("Strömstads Tidning ej tillgänglig: %s", exc)
            return []

        encoding = response.encoding or "utf-8"
        html = response.content.decode(encoding, errors="replace")
        items = _parse_articles(html, BASE_URL)
        logger.debug("Strömstads Tidning: %d artiklar hittade", len(items))
        return items


def _parse_articles(html: str, base_url: str) -> list[dict]:
    """Extraherar artiklar ur HTML-sida. Returnerar lista med standardformat-dicts."""
    soup = BeautifulSoup(html, "lxml")
    seen_urls: set[str] = set()
    items: list[dict] = []

    for selector in ARTICLE_LINK_SELECTORS:
        for link in soup.select(selector):
            href = link.get("href", "")
            if not href:
                continue
            url = urljoin(base_url, str(href))
            if not _is_same_domain(url, base_url):
                continue
            if url in seen_urls:
                continue

            title = link.get_text(strip=True)
            if not title or len(title) < MIN_TITLE_LENGTH:
                parent = link.find_parent(["h1", "h2", "h3", "h4"])
                if parent:
                    title = parent.get_text(strip=True)

            if not title or len(title) < MIN_TITLE_LENGTH:
                continue

            published = _extract_published(link, soup)
            seen_urls.add(url)
            items.append({
                "uid": f"ST:{url}",
                "source": "ST",
                "title": title,
                "url": url,
                "summary": "",
                "published": published,
            })

            if len(items) >= MAX_ARTICLES:
                return items

    return items


def _is_same_domain(url: str, base_url: str) -> bool:
    """Kontrollerar om url tillhör samma domän som base_url."""
    try:
        base_host = (urlparse(base_url).hostname or "").removeprefix("www.")
        url_host = (urlparse(url).hostname or "").removeprefix("www.")
        return url_host == base_host or url_host.endswith("." + base_host)
    except Exception:
        return False


def _extract_published(link, soup: BeautifulSoup) -> Optional[datetime]:
    article = link.find_parent("article")
    candidates = []
    if article:
        candidates.append(article)
    candidates.append(link)
    candidates.extend(link.parents)

    for node in candidates:
        if not hasattr(node, "select_one"):
            continue
        time_tag = node.select_one("time[datetime]")
        if time_tag:
            dt = _parse_datetime(time_tag.get("datetime"))
            if dt is not None:
                return dt

    meta_time = soup.select_one('meta[property="article:published_time"]')
    if meta_time:
        return _parse_datetime(meta_time.get("content"))
    return None


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
