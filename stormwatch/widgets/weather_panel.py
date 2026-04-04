"""Väderpanel – visar vindstyrka och vattennivå från VIVA-stationer."""
from datetime import datetime
from typing import Optional

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Label, Static

from stormwatch.fetchers.viva import wind_dir_arrow
from stormwatch.history import WeatherHistory
from stormwatch.models import StationReading


def _wind_color(gust: Optional[float]) -> str:
    if gust is None:
        return "dim"
    if gust >= 24.5:  # Orkan
        return "bright_red"
    if gust >= 20.8:  # Svår storm
        return "red"
    if gust >= 17.2:  # Storm
        return "bright_yellow"
    if gust >= 13.9:  # Hård kuling
        return "yellow"
    return "green"


def _format_reading(r: StationReading) -> str:
    if r.error:
        return f"[dim]  {r.name:<20} Fel: {r.error[:25]}[/dim]"

    gust_color = _wind_color(r.wind_gust or r.wind_avg)

    # Byvind med riktning
    if r.wind_gust is not None:
        gust_arrow = wind_dir_arrow(r.wind_gust_dir_str, None)
        gust_dir = r.wind_gust_dir_str or "?"
        gust_str = f"[{gust_color}]By {gust_arrow}{gust_dir} {r.wind_gust:.1f}[/]"
    else:
        gust_str = "[dim]By –[/dim]"

    # Medelvind med riktning
    if r.wind_avg is not None:
        avg_arrow = wind_dir_arrow(r.wind_dir_str, r.wind_dir_deg)
        avg_dir = r.wind_dir_str or "?"
        avg_str = f"Medel {avg_arrow}{avg_dir} {r.wind_avg:.1f}"
    else:
        avg_str = "Medel –"

    wind_str = f"{gust_str} [dim]{avg_str} m/s[/dim]"

    if r.water_level is not None:
        sign = "+" if r.water_level >= 0 else ""
        level_str = f"  [cyan]{sign}{r.water_level}cm[/cyan]"
    else:
        level_str = ""

    if r.water_temp is not None:
        level_str += f"[dim] {r.water_temp:.1f}°[/dim]"

    name_part = f"[bold]{r.name:<14}[/bold]"
    return f"  {name_part} {wind_str}{level_str}"


def _beaufort(speed: Optional[float]) -> str:
    """Returnerar Beaufort-skala som sträng."""
    if speed is None:
        return ""
    thresholds = [
        (0.3, "0 Stiltje"),
        (1.6, "1 Lätt bris"),
        (3.4, "2 Lätt bris"),
        (5.5, "3 Lätt bris"),
        (8.0, "4 God bris"),
        (10.8, "5 Frisk bris"),
        (13.9, "6 Hård bris"),
        (17.2, "7 Kuling"),
        (20.8, "8 Hård kuling"),
        (24.5, "9 Stark kuling"),
        (28.5, "10 Storm"),
        (32.7, "11 Svår storm"),
    ]
    for limit, label in thresholds:
        if speed < limit:
            return label
    return "12 Orkan"


class WeatherPanelWidget(Widget):
    """Väderpanel i övre högra hörnet."""

    DEFAULT_CSS = """
    WeatherPanelWidget {
        height: auto;
        min-height: 10;
    }
    """
    can_focus = True

    MAX_STATIONS = 8  # max antal rader

    def compose(self) -> ComposeResult:
        yield Label(" ◈ VÄDER & VATTEN ", id="weather-title")
        for i in range(self.MAX_STATIONS):
            yield Static("", id=f"station-{i}", classes="station-row")
        yield Static("", id="station-extra", classes="station-row")
        yield Label("", id="weather-updated")

    def refresh_display(
        self,
        readings: list[StationReading],
        history: WeatherHistory | None = None,
    ) -> None:
        rows = self.query(".station-row")
        row_list = list(rows)

        for i, row in enumerate(row_list):
            if i < len(readings):
                row.update(_format_reading(readings[i]))
            else:
                row.update("")

        # Sammanfattningsrad: historiskt högsta byvind och medelvind senaste 12h
        parts = []
        if history is not None:
            gust_max = history.get_recent_max("wind_gust", hours=12)
            if gust_max:
                max_gust, station_name = gust_max
                bft = _beaufort(max_gust)
                color = _wind_color(max_gust)
                parts.append(
                    f"[dim]Högsta by 12h:[/dim] [{color}]{max_gust:.1f} m/s[/] "
                    f"[dim]({station_name}, {bft})[/dim]"
                )

            avg_max = history.get_recent_max("wind_avg", hours=12)
            if avg_max:
                max_avg, station_name = avg_max
                avg_color = _wind_color(max_avg)
                parts.append(
                    f"[dim]Högsta medel 12h:[/dim] [{avg_color}]{max_avg:.1f} m/s[/] "
                    f"[dim]({station_name})[/dim]"
                )
        else:
            gust_readings = [(r.wind_gust, r) for r in readings if r.wind_gust is not None]
            avg_readings = [(r.wind_avg, r) for r in readings if r.wind_avg is not None]
            if gust_readings:
                max_gust, max_r = max(gust_readings, key=lambda x: x[0])
                bft = _beaufort(max_gust)
                color = _wind_color(max_gust)
                arr = wind_dir_arrow(max_r.wind_gust_dir_str, None)
                d = max_r.wind_gust_dir_str or "?"
                parts.append(
                    f"[dim]Max by:[/dim] [{color}]{arr}{d} {max_gust:.1f} m/s[/] "
                    f"[dim]({max_r.name}, {bft})[/dim]"
                )
            if avg_readings:
                max_avg, avg_r = max(avg_readings, key=lambda x: x[0])
                arr = wind_dir_arrow(avg_r.wind_dir_str, avg_r.wind_dir_deg)
                d = avg_r.wind_dir_str or "?"
                avg_color = _wind_color(max_avg)
                parts.append(
                    f"[dim]Max medel:[/dim] [{avg_color}]{arr}{d} {max_avg:.1f} m/s[/] "
                    f"[dim]({avg_r.name})[/dim]"
                )

        self.query_one("#station-extra").update("  " + "   ".join(parts) if parts else "")

        ts = datetime.now().strftime("%H:%M:%S")
        self.query_one("#weather-updated").update(
            f"  [dim]Uppdaterad {ts}[/dim]"
        )
