"""Bropanel – visar aktuell brostatus från Trafikverket."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, Static

from stormwatch.models import BridgeStatus


def _format_time(dt: Optional[datetime]) -> str:
    if dt is None:
        return "?"
    local = dt.astimezone()
    return local.strftime("%d/%m %H:%M")


def _format_bridge_row(b: BridgeStatus) -> str:
    if b.is_closed:
        status_str = "[bright_red]● STÄNGD[/bright_red]"
    else:
        status_str = "[yellow]◐ STÖRNING[/yellow]"

    time_part = ""
    if b.start_time or b.end_time:
        start = _format_time(b.start_time)
        end = _format_time(b.end_time)
        if b.start_time and b.end_time:
            time_part = f" [dim]{start}–{end}[/dim]"
        elif b.start_time:
            time_part = f" [dim]från {start}[/dim]"
        elif b.end_time:
            time_part = f" [dim]till {end}[/dim]"

    name = b.name[:50] + ("…" if len(b.name) > 50 else "")
    return f"  {status_str} {name}{time_part}"


class BridgePanelWidget(Widget):
    """Kompakt panel som visar aktuella brostörningar."""

    DEFAULT_CSS = """
    BridgePanelWidget {
        height: auto;
        min-height: 3;
    }
    """
    can_focus = False

    MAX_ROWS = 6

    def compose(self) -> ComposeResult:
        yield Label(" ◈ BROSTATUS ", id="bridge-title")
        for i in range(self.MAX_ROWS):
            yield Static("", id=f"bridge-row-{i}", classes="bridge-row")
        yield Static("", id="bridge-updated")

    def refresh_display(
        self,
        bridges: list[BridgeStatus],
        api_configured: bool = True,
    ) -> None:
        rows = list(self.query(".bridge-row"))

        if not api_configured:
            rows[0].update("  [dim]Trafikverket API-nyckel ej konfigurerad[/dim]")
            for row in rows[1:]:
                row.update("")
            self.query_one("#bridge-updated").update("")
            return

        if not bridges:
            rows[0].update("  [green]● Inga brostörningar rapporterade[/green]")
            for row in rows[1:]:
                row.update("")
        else:
            for i, row in enumerate(rows):
                if i < len(bridges):
                    row.update(_format_bridge_row(bridges[i]))
                else:
                    row.update("")

            if len(bridges) > self.MAX_ROWS:
                extra = len(bridges) - self.MAX_ROWS
                rows[-1].update(f"  [dim]… och {extra} till[/dim]")

        ts = datetime.now().astimezone().strftime("%H:%M:%S")
        self.query_one("#bridge-updated").update(
            f"  [dim]Uppdaterad {ts}[/dim]"
        )
