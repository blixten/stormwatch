"""Lagrar väderläsningar i SQLite för historik och grafer."""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from types import MappingProxyType

from stormwatch.models import StationReading

DB_PATH = Path("data/history.db")
ALLOWED_HISTORY_FIELDS = MappingProxyType({
    "wind_avg": (
        "SELECT timestamp, wind_avg FROM readings "
        "WHERE station_id = ? AND timestamp >= ? AND wind_avg IS NOT NULL "
        "ORDER BY timestamp ASC",
        "SELECT wind_avg, station_name FROM readings "
        "WHERE timestamp >= ? AND wind_avg IS NOT NULL "
        "ORDER BY wind_avg DESC, timestamp DESC LIMIT 1",
    ),
    "wind_gust": (
        "SELECT timestamp, wind_gust FROM readings "
        "WHERE station_id = ? AND timestamp >= ? AND wind_gust IS NOT NULL "
        "ORDER BY timestamp ASC",
        "SELECT wind_gust, station_name FROM readings "
        "WHERE timestamp >= ? AND wind_gust IS NOT NULL "
        "ORDER BY wind_gust DESC, timestamp DESC LIMIT 1",
    ),
    "water_level": (
        "SELECT timestamp, water_level FROM readings "
        "WHERE station_id = ? AND timestamp >= ? AND water_level IS NOT NULL "
        "ORDER BY timestamp ASC",
        "SELECT water_level, station_name FROM readings "
        "WHERE timestamp >= ? AND water_level IS NOT NULL "
        "ORDER BY water_level DESC, timestamp DESC LIMIT 1",
    ),
    "water_temp": (
        "SELECT timestamp, water_temp FROM readings "
        "WHERE station_id = ? AND timestamp >= ? AND water_temp IS NOT NULL "
        "ORDER BY timestamp ASC",
        "SELECT water_temp, station_name FROM readings "
        "WHERE timestamp >= ? AND water_temp IS NOT NULL "
        "ORDER BY water_temp DESC, timestamp DESC LIMIT 1",
    ),
    "air_temp": (
        "SELECT timestamp, air_temp FROM readings "
        "WHERE station_id = ? AND timestamp >= ? AND air_temp IS NOT NULL "
        "ORDER BY timestamp ASC",
        "SELECT air_temp, station_name FROM readings "
        "WHERE timestamp >= ? AND air_temp IS NOT NULL "
        "ORDER BY air_temp DESC, timestamp DESC LIMIT 1",
    ),
})


class WeatherHistory:
    def __init__(self, db_path: Path = DB_PATH) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._create_tables()

    def _create_tables(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS readings (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp    TEXT    NOT NULL,
                station_id   INTEGER NOT NULL,
                station_name TEXT    NOT NULL,
                wind_avg     REAL,
                wind_gust    REAL,
                wind_dir_str TEXT,
                water_level  INTEGER,
                water_temp   REAL,
                air_temp     REAL
            )
        """)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_station_time ON readings (station_id, timestamp)"
        )
        self._conn.commit()

    def save(self, readings: list[StationReading]) -> None:
        ts = datetime.now().isoformat(timespec="seconds")
        rows = [
            (
                ts, r.station_id, r.name,
                r.wind_avg, r.wind_gust, r.wind_dir_str,
                r.water_level, r.water_temp, r.air_temp,
            )
            for r in readings
            if not r.error
        ]
        if rows:
            self._conn.executemany("""
                INSERT INTO readings
                  (timestamp, station_id, station_name,
                   wind_avg, wind_gust, wind_dir_str,
                   water_level, water_temp, air_temp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
            self._conn.commit()

    def get_recent(
        self,
        station_id: int,
        field: str,
        hours: int = 12,
    ) -> list[tuple[datetime, float]]:
        """Returnerar (tid, värde)-par för de senaste N timmarna."""
        queries = ALLOWED_HISTORY_FIELDS.get(field)
        if queries is None:
            raise ValueError(f"Ogiltigt fält: {field}")
        recent_query, _ = queries
        since = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
        cur = self._conn.execute(recent_query, (station_id, since))
        return [(datetime.fromisoformat(row[0]), row[1]) for row in cur.fetchall()]

    def get_recent_max(
        self,
        field: str,
        hours: int = 12,
    ) -> tuple[float, str] | None:
        """Returnerar högsta värde + stationsnamn för senaste N timmarna."""
        queries = ALLOWED_HISTORY_FIELDS.get(field)
        if queries is None:
            raise ValueError(f"Ogiltigt fält: {field}")
        _, max_query = queries
        since = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
        cur = self._conn.execute(max_query, (since,))
        row = cur.fetchone()
        if row is None:
            return None
        return row[0], row[1]

    def station_ids(self) -> list[tuple[int, str]]:
        """Returnerar alla (station_id, namn) som finns i databasen."""
        cur = self._conn.execute(
            "SELECT DISTINCT station_id, station_name FROM readings ORDER BY station_name"
        )
        return cur.fetchall()

    def close(self) -> None:
        self._conn.close()


# ─── ASCII-sparkline ─────────────────────────────────────────────────────────

_BLOCKS = " ▁▂▃▄▅▆▇█"


def sparkline(values: list[float], width: int = 40) -> str:
    """Returnerar en enradig sparkline av givna värden."""
    if not values:
        return "─" * width
    # Nedsampla till width punkter
    if len(values) > width:
        step = len(values) / width
        values = [values[int(i * step)] for i in range(width)]
    lo, hi = min(values), max(values)
    span = hi - lo or 1.0
    chars = [_BLOCKS[int((v - lo) / span * (len(_BLOCKS) - 1))] for v in values]
    return "".join(chars)


def bar_chart(
    points: list[tuple[datetime, float]],
    label: str,
    unit: str,
    width: int = 44,
    color: str = "cyan",
) -> str:
    """Returnerar en Rich-markupsträng med sparkline + metadata."""
    if not points:
        return f"[dim]{label}: ingen data[/dim]"
    times, values = zip(*points)
    latest = values[-1]
    hi = max(values)
    lo = min(values)
    line = sparkline(list(values), width)
    t0 = times[0].strftime("%H:%M")
    t1 = times[-1].strftime("%H:%M")
    return (
        f"  [bold]{label}[/bold]\n"
        f"  [{color}]{line}[/{color}]\n"
        f"  [dim]{t0}→{t1}  "
        f"nu:[/dim] [{color}]{latest:.1f}{unit}[/{color}]"
        f"  [dim]↑{hi:.1f}  ↓{lo:.1f}[/dim]"
    )
