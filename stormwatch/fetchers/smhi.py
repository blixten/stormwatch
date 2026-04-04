"""Hämtar SMHI-varningar med automatisk URL-sökning."""
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Testar dessa URL:er i ordning tills en fungerar
CANDIDATE_URLS = [
    "https://opendata-download-warnings.smhi.se/api/version/2/districtwarnings/county/{county}.json",
    "https://opendata-download-warnings.smhi.se/api/version/2/districtwarnings/county/{county}",
    "https://opendata-download-warnings.smhi.se/api/version/2/warnings.json",
    "https://opendata-download-warnings.smhi.se/api/version/2/warnings",
]


class SmhiFetcher:
    def __init__(self) -> None:
        self._working_url: Optional[str] = None
        self._probed: bool = False

    async def probe(self, counties: list[int], client: httpx.AsyncClient) -> Optional[str]:
        """Hitta fungerande URL vid uppstart. Returnerar URL eller None."""
        if self._probed:
            return self._working_url

        self._probed = True
        county = counties[0] if counties else 14

        for template in CANDIDATE_URLS:
            url = template.format(county=county)
            try:
                r = await client.get(url, timeout=8.0)
                if r.status_code == 200:
                    self._working_url = template
                    logger.info("SMHI API funnen: %s", template)
                    return template
            except Exception:
                pass

        logger.info("Inget SMHI-varnings-API hittades – fortsätter utan")
        return None

    async def fetch_warnings(
        self, counties: list[int], client: httpx.AsyncClient
    ) -> list[dict]:
        """Hämtar aktiva SMHI-varningar som nyhetsposter."""
        if not self._working_url:
            return []

        items = []
        for county in counties:
            url = self._working_url.format(county=county)
            try:
                r = await client.get(url, timeout=10.0)
                r.raise_for_status()
                data = r.json()
                items.extend(_parse_warnings(data, county))
            except Exception as exc:
                logger.debug("SMHI county %d: %s", county, exc)

        return items

    @property
    def is_ready(self) -> bool:
        return self._working_url is not None


def _parse_warnings(data, county: int) -> list[dict]:
    items = []
    warnings = data if isinstance(data, list) else data.get("warnings", [])
    for w in warnings:
        wtype = w.get("warningType", {})
        title = w.get("heading") or wtype.get("swedish") or "SMHI-varning"
        description = w.get("description", {}).get("swedish", "") or ""
        event_id = w.get("id") or w.get("eventId") or f"smhi-{county}-{title}"
        link = f"https://www.smhi.se/vader/varningar-och-beredskap/varningar"

        published_str = w.get("published") or w.get("validFrom") or ""
        published = None
        if published_str:
            try:
                published = datetime.fromisoformat(published_str.replace("Z", "+00:00"))
            except ValueError:
                pass

        items.append({
            "uid": f"SMHI:{event_id}",
            "source": "SMHI",
            "title": title,
            "url": link,
            "summary": description,
            "published": published,
        })
    return items
