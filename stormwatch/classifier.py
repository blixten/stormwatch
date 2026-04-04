"""Klassificerar nyhetsartiklar efter relevans för stormen Dave."""
import re
from typing import Optional

DEFAULT_KEYWORDS: dict[str, int] = {
    "stormen dave": 5,
    "storm dave": 5,
    "dave": 4,
    "storm": 3,
    "oväder": 3,
    "stormvarning": 4,
    "stormbyar": 3,
    "orkan": 4,
    "orkankust": 4,
    "klass 3": 4,
    "klass 2": 3,
    "klass 1": 2,
    "röd varning": 4,
    "orange varning": 3,
    "gul varning": 2,
    "varning": 1,
    "översvämning": 3,
    "vind": 1,
    "kuling": 2,
    "hård kuling": 3,
    "västsverige": 2,
    "göteborg": 2,
    "bohuslän": 2,
    "halland": 1,
    "lysekil": 1,
    "strömstad": 1,
    "kungsbacka": 1,
    "marstrand": 2,
    "vinga": 2,
    "smhi": 1,
    "trafikverket": 1,
    # Konsekvenser av stormen
    "stormflod": 4,
    "evakuering": 3,
    "strömavbrott": 3,
    "högt vattenstånd": 3,
    "räddningstjänst": 2,
    "inställda tåg": 2,
    "orust": 2,
    "tjörn": 2,
    "stenungsund": 1,
    "västtrafik": 1,
    "hamn": 1,
    "liverapport": 1,
    "liveblogg": 1,
    "skadad": 1,
    "olycka": 1,
    "sj": 1,
}


class ArticleClassifier:
    def __init__(self, keywords: Optional[dict[str, int]] = None):
        kw = keywords or DEFAULT_KEYWORDS
        # Längre fraser kompileras först för greedy matchning
        sorted_kw = sorted(kw.items(), key=lambda x: len(x[0]), reverse=True)
        self._patterns: list[tuple[re.Pattern, int]] = [
            (re.compile(re.escape(word), re.IGNORECASE | re.UNICODE), weight)
            for word, weight in sorted_kw
        ]

    def score(self, title: str, summary: str) -> int:
        """Returnerar relevansscore 0–10. Rubrik väger dubbelt."""
        total = 0
        title_lower = (title or "").lower()
        summary_lower = (summary or "").lower()
        for pattern, weight in self._patterns:
            title_hits = len(pattern.findall(title_lower))
            summary_hits = len(pattern.findall(summary_lower))
            total += title_hits * weight * 2 + summary_hits * weight
        return min(10, total)

    @staticmethod
    def color_for_score(score: int) -> str:
        if score >= 7:
            return "bright_red"
        elif score >= 4:
            return "yellow"
        return "white"

    @staticmethod
    def badge_for_score(score: int) -> str:
        if score >= 7:
            return "[bright_red]▲[/]"
        elif score >= 4:
            return "[yellow]◆[/]"
        return "[dim]·[/]"
