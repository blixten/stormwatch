"""Artikelpanel – visar fulltext för markerad nyhet."""
import re
from typing import Optional

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, Static
from textual.containers import VerticalScroll

from stormwatch.classifier import ArticleClassifier
from stormwatch.models import NewsItem


class ArticlePanelWidget(Widget):
    """Nedre högra panelen – artikeltext."""

    DEFAULT_CSS = """
    ArticlePanelWidget {
        height: 1fr;
    }
    #article-scroll {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
    }
    #article-url {
        height: 1;
        overflow: hidden;
    }
    """
    can_focus = True

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_text: str = ""

    def compose(self) -> ComposeResult:
        yield Label(" ◈ ARTIKEL ", id="article-title")
        yield Label("", id="article-url")
        with VerticalScroll(id="article-scroll"):
            yield Static(
                "[dim]Välj en artikel från listan med ↑↓, Enter för att hämta fulltext.[/dim]",
                id="article-body",
                markup=True,
            )

    def show_summary(self, item: NewsItem) -> None:
        """Visas direkt vid navigation (↑↓) – RSS-sammanfattning."""
        self._current_text = ""
        self._set_url(item.url)
        score_badge = ArticleClassifier.badge_for_score(item.score)
        color = ArticleClassifier.color_for_score(item.score)
        from stormwatch.widgets.news_list import SOURCE_COLORS
        src_color = SOURCE_COLORS.get(item.source, "white")

        header = (
            f"[bold]{item.title}[/bold]\n\n"
            f"[{src_color}]{item.source}[/]  "
            f"{score_badge} [{color}]Relevans {item.score}/10[/{color}]\n\n"
            f"[dim]Tryck Enter för att hämta fulltext[/dim]\n\n"
            f"[italic]{_sanitize(item.summary)}[/italic]"
        )
        self._set_body(header)

    def show_loading(self, item: NewsItem) -> None:
        """Visas medan artikeln skrapas."""
        self._current_text = ""
        self._set_url(item.url)
        score_badge = ArticleClassifier.badge_for_score(item.score)
        self._set_body(
            f"[bold]{item.title}[/bold]\n\n"
            f"{score_badge} Relevans {item.score}/10\n\n"
            f"[dim blink]Hämtar artikel…[/dim blink]\n\n"
            f"[italic]{_sanitize(item.summary)}[/italic]"
        )

    def show_article(self, item: NewsItem, text: str) -> None:
        """Visas när fulltext är hämtad."""
        self._current_text = text
        self._set_url(item.url)
        self._set_body(_build_article_body(item, text))

    def show_ai_analysis(
        self,
        item: NewsItem,
        ai_score: Optional[int],
        ai_analysis: Optional[str],
    ) -> None:
        """Uppdaterar artikelpanelen med AI-relevansbedömning."""
        self._set_url(item.url)
        self._set_body(_build_article_body(item, self._current_text, ai_score, ai_analysis))

    def _set_url(self, url: str) -> None:
        short = url[:80] + "…" if len(url) > 80 else url
        # Undvik Rich link-markup (kraschar på specialtecken i URL:er)
        self.query_one("#article-url").update(f"[dim]{short}[/dim]")

    def _set_body(self, markup: str) -> None:
        self.query_one("#article-body").update(markup)
        # Scrolla till toppen
        try:
            self.query_one("#article-scroll").scroll_home(animate=False)
        except Exception:
            pass


def _build_article_body(
    item: NewsItem,
    text: str,
    ai_score: Optional[int] = None,
    ai_analysis: Optional[str] = None,
) -> str:
    """Bygger den fullständiga artikelkroppen, med valfri AI-sektion."""
    from stormwatch.widgets.news_list import SOURCE_COLORS
    score_badge = ArticleClassifier.badge_for_score(item.score)
    color = ArticleClassifier.color_for_score(item.score)
    src_color = SOURCE_COLORS.get(item.source, "white")

    # Kombinera AI-data från argumenten och från item (om det finns)
    effective_ai_score = ai_score if ai_score is not None else item.ai_score
    effective_ai_analysis = ai_analysis or item.ai_analysis
    ai_section = _format_ai_block(effective_ai_score, effective_ai_analysis)

    return (
        f"[bold]{item.title}[/bold]\n\n"
        f"[{src_color}]{item.source}[/]  "
        f"{score_badge} [{color}]Relevans {item.score}/10[/{color}]\n"
        f"{ai_section}"
        f"{'─' * 40}\n\n"
        f"{_sanitize(text)}"
    )


def _sanitize(text: str) -> str:
    """Tar bort Rich-markup-tecken som kan krascha renderingen."""
    if not text:
        return ""
    # Escapa hakparenteser som inte är Rich-markup
    text = re.sub(r"\[(?![a-zA-Z/\#!])", r"\\[", text)
    return text


def _format_ai_block(ai_score: Optional[int], ai_analysis: Optional[str]) -> str:
    """Formaterar AI-relevansbedömning för visning i artikelpanelen."""
    parts = []
    if ai_score is not None:
        if ai_score >= 7:
            color = "bright_red"
        elif ai_score >= 4:
            color = "yellow"
        else:
            color = "dim"
        parts.append(f"[{color}]🤖 GPT-relevans {ai_score}/10[/{color}]")
    if ai_analysis:
        parts.append(f"[dim italic]{_sanitize(ai_analysis)}[/dim italic]")
    if parts:
        return "  ".join(parts) + "\n\n"
    return "\n"
