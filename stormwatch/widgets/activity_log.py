"""Aktivitetslogg – visar bakgrundsaktivitet i nyhetsfliken."""
from __future__ import annotations

from collections import deque
from datetime import datetime

from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Label, Static

_MAX_ENTRIES = 30


class ActivityLogWidget(Widget):
    """Kompakt rullande logg med bakgrundsaktivitet."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._entries: deque[str] = deque(maxlen=_MAX_ENTRIES)

    def compose(self) -> ComposeResult:
        yield Label(" ◈ LOGG ", id="activity-log-title")
        yield Static("", id="activity-log-content", markup=True)

    def add_entry(self, text: str) -> None:
        """Lägg till en ny loggpost och uppdatera visningen."""
        ts = datetime.now().strftime("%H:%M:%S")
        self._entries.append(f"[dim]{ts}[/] {text}")
        try:
            self.query_one("#activity-log-content", Static).update(
                "\n".join(self._entries)
            )
        except NoMatches:
            pass
