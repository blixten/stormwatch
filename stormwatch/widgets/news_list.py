"""Nyhetslistepanel – vänster kolumn."""
from datetime import datetime, timezone
from typing import Optional

from textual.app import ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Label, ListItem, ListView, Static

from stormwatch.classifier import ArticleClassifier
from stormwatch.models import NewsItem
from stormwatch.widgets.activity_log import ActivityLogWidget

SOURCE_COLORS: dict[str, str] = {
    "GP":    "cyan",
    "BL":    "green",
    "ST":    "bright_green",
    "SR":    "bright_yellow",
    "P4V":   "yellow",
    "P4G":   "yellow",
    "SMHI":  "bright_red",
    "SVT":   "blue",
    "SVH":   "blue",
    "AB":    "bright_magenta",
    "EX":    "magenta",
    "KRIS":  "bright_blue",
    "VMA":   "red",
    "GOT":   "cyan",
    "SOS":   "bright_cyan",
    "POLIS": "bright_blue",
    "KBV":   "bright_cyan",
}


def _format_age(published: Optional[datetime]) -> str:
    if published is None:
        return "    "
    try:
        now = datetime.now(timezone.utc)
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        diff = now - published
        minutes = int(diff.total_seconds() / 60)
        if minutes < 60:
            return f"{minutes}m"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h"
        days = hours // 24
        return f"{days}d"
    except Exception:
        return "    "


class NewsRow(ListItem):
    """En rad i nyhetslistan."""

    DEFAULT_CSS = """
    NewsRow {
        height: 3;
        padding: 0 1;
        border-bottom: dashed $surface-lighten-2;
    }
    NewsRow > Static {
        height: 3;
    }
    """

    def __init__(self, item: NewsItem) -> None:
        super().__init__()
        self.item = item

    def compose(self) -> ComposeResult:
        yield Static(self._render_text())

    def _render_text(self) -> str:
        source_color = SOURCE_COLORS.get(self.item.source, "white")
        badge = ArticleClassifier.badge_for_score(self.item.score)
        age = _format_age(self.item.published)
        # Trunkera titel för att passa i panelen
        title = self.item.title
        if len(title) > 55:
            title = title[:54] + "…"

        updated_marker = " [bright_yellow]↑UPD[/]" if self.item.is_updated else ""
        line1 = f"[{source_color}][{self.item.source:<4}][/] {badge} {title}"
        line2 = f"[dim]      {age:>4}  score:{self.item.score}/10[/]{updated_marker}"
        return f"{line1}\n{line2}"

    def update_content(self) -> None:
        self.query_one(Static).update(self._render_text())


class NewsListWidget(Widget):
    """Vänsterpanelen med nyhetslistan."""

    class ArticleHighlighted(Message):
        """Användaren navigerade till en artikel (visa RSS-sammanfattning)."""
        def __init__(self, item: NewsItem) -> None:
            self.item = item
            super().__init__()

    class ArticleSelected(Message):
        """Användaren tryckte Enter – hämta fulltext."""
        def __init__(self, item: NewsItem) -> None:
            self.item = item
            super().__init__()

    item_count: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        yield Label(" ◈ NYHETER ", id="news-title")
        yield Label("Läser in…", id="news-status")
        yield ListView(id="news-list")
        yield ActivityLogWidget(id="activity-log")

    def on_mount(self) -> None:
        self.query_one(ListView).focus()

    def refresh_news(self, items: list[NewsItem], new_count: int = 0, updated_count: int = 0) -> None:
        """Ersätter listans innehåll med nya poster. Bevarar markering."""
        lv = self.query_one(ListView)
        old_idx = lv.index or 0

        with self.app.batch_update():
            lv.clear()
            for item in items:
                lv.append(NewsRow(item))

        self.item_count = len(items)
        self.query_one("#news-status").update(
            f"[dim]{len(items)} artiklar[/]"
        )

        if new_count > 0 and updated_count > 0:
            self.query_one("#news-title").update(
                f" ◈ NYHETER  [bright_red blink]{new_count} NYA[/] [bright_yellow]{updated_count} UPD[/] "
            )
        elif new_count > 0:
            self.query_one("#news-title").update(
                f" ◈ NYHETER  [bright_red blink]{new_count} NYA[/] "
            )
        elif updated_count > 0:
            self.query_one("#news-title").update(
                f" ◈ NYHETER  [bright_yellow]{updated_count} UPD[/] "
            )
        else:
            self.query_one("#news-title").update(" ◈ NYHETER ")

        if items:
            new_idx = min(old_idx, len(items) - 1)
            lv.index = new_idx

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item and isinstance(event.item, NewsRow):
            self.post_message(self.ArticleHighlighted(event.item.item))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item and isinstance(event.item, NewsRow):
            self.post_message(self.ArticleSelected(event.item.item))

    def move_up(self) -> None:
        lv = self.query_one(ListView)
        if lv.index is not None and lv.index > 0:
            lv.index -= 1

    def move_down(self) -> None:
        lv = self.query_one(ListView)
        if lv.index is not None:
            lv.index += 1
