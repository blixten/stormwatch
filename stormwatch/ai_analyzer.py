"""GPT-4o-mini relevansbedömning av nyhetsartiklar (kräver OPENAI_API_KEY)."""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = (
    "Du är en redaktör som bedömer om nyhetsartiklar är relevanta för "
    "realtidsövervakning av en kraftig storm längs svenska västkusten. "
    "Svara ALLTID på svenska. "
    "Ge ett relevansscore 0–10 (10 = maximalt relevant) och en kort motivering "
    "(1–2 meningar). Svara i formatet:\n"
    "SCORE: <siffra>\nMOTIVERING: <text>"
)

_USER_TEMPLATE = (
    "Rubrik: {title}\n"
    "Sammanfattning: {summary}\n"
    "{fulltext_section}"
    "Bedöm relevansen för stormbevakning."
)


def _parse_response(text: str) -> tuple[Optional[int], str]:
    """Plockar ut score och motivering från GPT-svar."""
    score: Optional[int] = None
    motivation = ""
    for line in text.splitlines():
        line = line.strip()
        if line.upper().startswith("SCORE:"):
            try:
                score = max(0, min(10, int(line.split(":", 1)[1].strip())))
            except ValueError:
                pass
        elif line.upper().startswith("MOTIVERING:"):
            motivation = line.split(":", 1)[1].strip()
    return score, motivation


class AiAnalyzer:
    """Analyserar artikelrelevans med OpenAI GPT-4o-mini.

    Används bara om OPENAI_API_KEY är satt i miljön; annars returnerar
    ``is_available()`` False och ``analyze()`` returnerar ``None, None``.
    """

    def __init__(self) -> None:
        self._client = None
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            return
        try:
            from openai import AsyncOpenAI  # type: ignore
            self._client = AsyncOpenAI(api_key=key)
            logger.info("AiAnalyzer initierad med modell %s", _MODEL)
        except ImportError:
            logger.warning(
                "openai-paketet är inte installerat – AI-analys inaktiverad. "
                "Installera med: pip install openai"
            )

    def is_available(self) -> bool:
        return self._client is not None

    async def analyze(
        self,
        title: str,
        summary: str,
        full_text: Optional[str] = None,
    ) -> tuple[Optional[int], Optional[str]]:
        """Returnerar (score, motivering) eller (None, None) vid fel/inaktiv."""
        if not self._client:
            return None, None

        fulltext_section = ""
        if full_text:
            snippet = full_text[:600].strip()
            fulltext_section = f"Artikeltext (utdrag): {snippet}\n"

        user_msg = _USER_TEMPLATE.format(
            title=title,
            summary=(summary or "")[:300],
            fulltext_section=fulltext_section,
        )

        try:
            response = await self._client.chat.completions.create(
                model=_MODEL,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                max_tokens=120,
                temperature=0.2,
            )
            text = response.choices[0].message.content or ""
            score, motivation = _parse_response(text)
            return score, motivation
        except Exception as exc:
            logger.warning("AI-analys misslyckades: %s", exc)
            return None, None
