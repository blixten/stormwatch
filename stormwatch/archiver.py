"""Sparar relevanta artiklar till disk för efteranalys."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from stormwatch.models import NewsItem

logger = logging.getLogger(__name__)

ARCHIVE_DIR = Path("data")
ARTICLES_FILE = ARCHIVE_DIR / "storm_dave_articles.jsonl"
MIN_SCORE = 4  # spara artiklar med score >= detta värde


class Archiver:
    def __init__(self) -> None:
        ARCHIVE_DIR.mkdir(exist_ok=True)
        self._saved_uids: set[str] = set()
        self._load_existing_uids()

    def _load_existing_uids(self) -> None:
        """Läs in redan sparade UIDs för att undvika dubbletter."""
        if not ARTICLES_FILE.exists():
            return
        try:
            with open(ARTICLES_FILE, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        obj = json.loads(line)
                        self._saved_uids.add(obj["uid"])
            logger.info("Arkivet innehåller %d sparade artiklar", len(self._saved_uids))
        except Exception as exc:
            logger.warning("Kunde inte läsa arkiv: %s", exc)

    def save_items(self, items: list[NewsItem]) -> int:
        """Sparar nya artiklar med score >= MIN_SCORE. Returnerar antal nyligen sparade."""
        to_save = [
            item for item in items
            if item.score >= MIN_SCORE and item.uid not in self._saved_uids
        ]
        if not to_save:
            return 0

        saved = 0
        try:
            with open(ARTICLES_FILE, "a", encoding="utf-8") as f:
                for item in to_save:
                    record = _to_record(item)
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    self._saved_uids.add(item.uid)
                    saved += 1
        except Exception as exc:
            logger.error("Arkiveringsfel: %s", exc)

        if saved:
            logger.info("Arkiverade %d nya artiklar (totalt %d)", saved, len(self._saved_uids))
        return saved

    def update_fulltext(self, item: NewsItem, text: str) -> None:
        """Skriver en uppdaterad post med fulltext om artikeln redan finns arkiverad."""
        if item.uid not in self._saved_uids or item.score < MIN_SCORE:
            return
        # Lägg till en separat fulltext-post (markerad med has_fulltext=True)
        try:
            with open(ARTICLES_FILE, "a", encoding="utf-8") as f:
                record = _to_record(item)
                record["full_text"] = text
                record["has_fulltext"] = True
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.error("Kunde inte spara fulltext: %s", exc)

    def update_ai_analysis(
        self, item: NewsItem, ai_score: int | None, ai_analysis: str | None
    ) -> None:
        """Sparar AI-relevansbedömning för en arkiverad artikel."""
        if item.uid not in self._saved_uids or item.score < MIN_SCORE:
            return
        if ai_score is None and not ai_analysis:
            return
        try:
            with open(ARTICLES_FILE, "a", encoding="utf-8") as f:
                record = _to_record(item)
                record["ai_score"] = ai_score
                record["ai_analysis"] = ai_analysis
                record["has_ai_analysis"] = True
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.error("Kunde inte spara AI-analys: %s", exc)

    @property
    def count(self) -> int:
        return len(self._saved_uids)


def _to_record(item: NewsItem) -> dict:
    return {
        "uid": item.uid,
        "source": item.source,
        "title": item.title,
        "url": item.url,
        "published": item.published.isoformat() if item.published else None,
        "score": item.score,
        "summary": item.summary,
        "full_text": item.full_text,
        "has_fulltext": item.full_text is not None,
        "archived_at": datetime.now(timezone.utc).isoformat(),
    }
