"""Historikpanel – visar sparkline-grafer för vind och vattenstånd."""
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import Label, Static

from stormwatch.history import WeatherHistory, bar_chart


class HistoryPanelWidget(Widget):
    """Overlay-panel med ASCII-grafer för de senaste 12 timmarna."""

    DEFAULT_CSS = """
    HistoryPanelWidget {
        height: 1fr;
        display: none;
    }
    HistoryPanelWidget.visible {
        display: block;
    }
    #history-scroll {
        height: 1fr;
        overflow-y: auto;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label(" ◈ HISTORIK (senaste 12h) – tryck H för att stänga ", id="history-title")
        with VerticalScroll(id="history-scroll"):
            yield Static("", id="history-body", markup=True)

    def refresh_display(self, history: WeatherHistory) -> None:
        stations = history.station_ids()
        if not stations:
            self.query_one("#history-body").update(
                "[dim]Ingen historik ännu – data sparas vid varje väderuppdatering.[/dim]"
            )
            return

        parts: list[str] = []
        for station_id, name in stations:
            parts.append(f"\n[bold underline]{name}[/bold underline]")

            gust_pts = history.get_recent(station_id, "wind_gust")
            avg_pts = history.get_recent(station_id, "wind_avg")
            level_pts = history.get_recent(station_id, "water_level")

            parts.append(bar_chart(gust_pts, "Byvind", " m/s", color="yellow"))
            parts.append(bar_chart(avg_pts, "Medelvind", " m/s", color="green"))
            if level_pts:
                parts.append(bar_chart(level_pts, "Vattenstånd", " cm", color="cyan"))

        self.query_one("#history-body").update("\n".join(parts))
