"""Skrapar fulltext från nyhetsartiklar."""
import logging
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

MAX_LENGTH = 4000

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.5",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.9",
}

# Domän → lista av CSS-selektorer att prova i ordning
DOMAIN_SELECTORS: dict[str, list[str]] = {
    "gp.se": ["article p", ".article-body p", "[class*='ArticleBody'] p"],
    "bohuslaningen.se": ["article p", ".article-body p", "[class*='article'] p"],
    "sverigesradio.se": ["article p", ".article-text p", "[class*='text'] p"],
    "trafikverket.se": [".content p", "article p", "main p"],
    "smhi.se": ["article p", ".content p", "main p"],
}

FALLBACK_SELECTORS = ["article p", "main p", ".content p"]

REMOVE_TAGS = ["script", "style", "nav", "footer", "aside", "header",
               "figure", "figcaption", "form", "button", "iframe"]


class ArticleScraper:
    async def fetch_text(self, url: str, client: httpx.AsyncClient) -> str:
        """Hämtar och extraherar artikeltext. Returnerar RSS-fallback-meddelande vid fel."""
        try:
            response = await client.get(url, timeout=12.0, headers=HEADERS)
            response.raise_for_status()
            encoding = response.encoding or "utf-8"
            html = response.content.decode(encoding, errors="replace")
        except Exception as exc:
            logger.debug("Skrapning misslyckades %s: %s", url, exc)
            return f"[Kunde inte hämta artikel: {type(exc).__name__}]"

        domain = _get_domain(url)
        selectors = DOMAIN_SELECTORS.get(domain, []) + FALLBACK_SELECTORS

        soup = BeautifulSoup(html, "lxml")
        for tag in soup(REMOVE_TAGS):
            tag.decompose()

        text = _extract_text(soup, selectors)

        if len(text) < 150:
            return "[Bakom betalvägg eller otillräcklig text]"

        if len(text) > MAX_LENGTH:
            text = text[:MAX_LENGTH] + "\n\n[… artikeln fortsätter på webben]"

        return text


def _get_domain(url: str) -> str:
    try:
        hostname = urlparse(url).hostname or ""
        parts = hostname.split(".")
        if len(parts) >= 2:
            return ".".join(parts[-2:])
        return hostname
    except Exception:
        return ""


def _extract_text(soup: BeautifulSoup, selectors: list[str]) -> str:
    for selector in selectors:
        elements = soup.select(selector)
        if not elements:
            continue
        paragraphs = []
        for el in elements:
            t = el.get_text(separator=" ", strip=True)
            t = re.sub(r"\s+", " ", t).strip()
            if t and len(t) > 20:
                paragraphs.append(t)
        if paragraphs:
            text = "\n\n".join(paragraphs)
            if len(text) > 100:
                return text
    return ""
