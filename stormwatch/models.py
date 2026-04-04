"""Dataobjekt som används i hela applikationen."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class StationReading:
    station_id: int
    name: str
    wind_avg: Optional[float] = None
    wind_gust: Optional[float] = None
    wind_dir_str: Optional[str] = None   # t.ex. "SV", "V"
    wind_dir_deg: Optional[float] = None  # grader
    water_level: Optional[int] = None    # cm
    water_temp: Optional[float] = None   # °C
    air_temp: Optional[float] = None     # °C
    updated: Optional[datetime] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class NewsItem:
    uid: str
    source: str          # "GP", "BL", "SR", "SMHI"
    title: str
    url: str
    summary: str         # RSS-beskrivning, används direkt som fallback
    published: Optional[datetime]
    score: int           # 0–10 relevansscore
    full_text: Optional[str] = None  # None tills artikel skrapas


@dataclass
class AppState:
    readings: list = field(default_factory=list)       # list[StationReading]
    news: list = field(default_factory=list)           # list[NewsItem]
    displayed_news: list = field(default_factory=list) # filtrerad/sorterad vy
    selected_index: int = 0
    last_weather_refresh: Optional[datetime] = None
    last_news_refresh: Optional[datetime] = None
    filter_high_only: bool = False
    sort_by_score: bool = True
    smhi_url: Optional[str] = None  # funnet SMHI-API-URL
