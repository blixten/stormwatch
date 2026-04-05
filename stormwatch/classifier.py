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
    # Stormkonsekvenser i polisrapporter och kustbevakningsnyheter
    "träd på väg": 2,
    "nedfallet träd": 2,
    "stormskada": 3,
    "avspärrning": 1,
    "sjöräddning": 2,
    "kustbevakning": 2,
    "nödställd": 2,
    "vindskada": 3,
    "takskada": 2,
    "elavbrott": 3,
}

# Nyckelord som MÅSTE finnas (minst ett) för att en artikel ska få poäng alls.
# Dessa representerar direkta storm- eller vädervarningssignaler och förhindrar
# att enbart geografiska- eller generiska termer ger falska positiva träffar.
STORM_CORE_KEYWORDS: frozenset[str] = frozenset({
    # Storm Dave-specifika termer
    "stormen dave", "storm dave",
    "dave",          # Stormens namn; acceptabel falsk-positiv-risk i detta sammanhang
    # Meteorologiska storm-/vindtermer
    "storm", "oväder", "stormvarning", "stormbyar",
    "orkan", "orkankust",
    "klass 3", "klass 2", "klass 1",
    "röd varning", "orange varning", "gul varning",
    "stormflod", "kuling", "hård kuling",
    "vind",          # Fångar artiklar om stark vind utan att nämna "storm" explicit
    # Direkta stormkonsekvenser
    "högt vattenstånd", "översvämning",
    "evakuering", "strömavbrott", "inställda tåg",
    "stormskada", "vindskada", "elavbrott",
    "träd på väg", "nedfallet träd", "takskada",
    "sjöräddning", "nödställd",
})


class ArticleClassifier:
    def __init__(self, keywords: Optional[dict[str, int]] = None):
        kw = keywords or DEFAULT_KEYWORDS
        # Längre fraser kompileras först för greedy matchning
        sorted_kw = sorted(kw.items(), key=lambda x: len(x[0]), reverse=True)
        self._patterns: list[tuple[re.Pattern, int]] = [
            (re.compile(re.escape(word), re.IGNORECASE | re.UNICODE), weight)
            for word, weight in sorted_kw
        ]
        # Kompilerade mönster för kärnkontroll (kortslutande sökning)
        self._core_patterns: list[re.Pattern] = [
            re.compile(re.escape(word), re.IGNORECASE | re.UNICODE)
            for word in sorted(STORM_CORE_KEYWORDS, key=len, reverse=True)
        ]

    def score(self, title: str, summary: str) -> int:
        """Returnerar relevansscore 0–10. Rubrik väger dubbelt.

        Returnerar 0 direkt om varken titel eller sammanfattning innehåller
        något av kärnorden (storm/väder-specifika termer). Detta förhindrar
        att enbart geografiska träffar ger falska höga poäng.
        """
        title_lower = (title or "").lower()
        summary_lower = (summary or "").lower()
        combined = title_lower + " " + summary_lower
        # Kräv minst ett storm-/väderspecifikt kärnord – kortsluter vid första träff
        if not any(p.search(combined) for p in self._core_patterns):
            return 0
        total = 0
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
