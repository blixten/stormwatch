"""Hämtar data från Sjöfartsverkets VIVA-API."""
import asyncio
import logging
from datetime import datetime
from typing import Optional

import httpx

from stormwatch.models import StationReading

logger = logging.getLogger(__name__)

BASE_URL = (
    "https://services.viva.sjofartsverket.se/output/vivaoutputservice.svc"
    "/ViVaStationWithDirection/{station_id}?isMVY=false"
)

# Svenska kompassriktningar → grader
DIR_MAP = {
    "N": 0.0, "NO": 45.0, "O": 90.0, "SO": 135.0,
    "S": 180.0, "SV": 225.0, "V": 270.0, "NV": 315.0,
}


class VivaFetcher:
    async def fetch_all(
        self, stations: list[dict], client: httpx.AsyncClient
    ) -> list[StationReading]:
        tasks = [
            self.fetch_one(s["id"], s["label"], client)
            for s in stations
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        readings = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                s = stations[i]
                readings.append(StationReading(
                    station_id=s["id"],
                    name=s["label"],
                    error=str(r),
                ))
            else:
                readings.append(r)
        return readings

    async def fetch_one(
        self, station_id: int, label: str, client: httpx.AsyncClient
    ) -> StationReading:
        url = BASE_URL.format(station_id=station_id)
        try:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            return self._parse(data, station_id, label)
        except Exception as exc:
            logger.warning("VIVA station %d (%s): %s", station_id, label, exc)
            return StationReading(
                station_id=station_id,
                name=label,
                error=type(exc).__name__,
            )

    def _parse(self, data: dict, station_id: int, label: str) -> StationReading:
        result = data.get("GetSingleStationWithDirectionsAsParametersResult", data)
        name = label or result.get("Name", f"Station {station_id}")
        samples = result.get("Samples") or []

        wind_avg: Optional[float] = None
        wind_gust: Optional[float] = None
        wind_dir_str: Optional[str] = None
        wind_dir_deg: Optional[float] = None
        wind_gust_dir_str: Optional[str] = None
        water_level: Optional[int] = None
        water_temp: Optional[float] = None
        air_temp: Optional[float] = None
        updated: Optional[datetime] = None

        for sample in samples:
            sname = (sample.get("Name") or "").lower()
            stype = (sample.get("Type") or "").lower()
            raw = str(sample.get("Value") or "").strip()
            ts = sample.get("Updated") or ""

            if ts and updated is None:
                try:
                    updated = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass

            if stype == "wind":
                dir_s, speed = _parse_wind_value(raw)
                if "medelvind" in sname:
                    wind_avg = speed
                    if dir_s and wind_dir_str is None:
                        wind_dir_str = dir_s
                elif "byvind" in sname:
                    wind_gust = speed
                    if dir_s and wind_gust_dir_str is None:
                        wind_gust_dir_str = dir_s

            elif stype == "heading" and "vindriktning" in sname:
                try:
                    wind_dir_deg = float(raw.replace(",", "."))
                except ValueError:
                    pass

            elif stype == "level" and "vattenstånd" in sname:
                try:
                    water_level = int(round(float(raw.replace(",", "."))))
                except ValueError:
                    pass

            elif "vattentemp" in sname:
                try:
                    water_temp = float(raw.replace(",", "."))
                except ValueError:
                    pass

            elif "lufttemp" in sname:
                try:
                    air_temp = float(raw.replace(",", "."))
                except ValueError:
                    pass

        return StationReading(
            station_id=station_id,
            name=name,
            wind_avg=wind_avg,
            wind_gust=wind_gust,
            wind_dir_str=wind_dir_str,
            wind_dir_deg=wind_dir_deg,
            wind_gust_dir_str=wind_gust_dir_str,
            water_level=water_level,
            water_temp=water_temp,
            air_temp=air_temp,
            updated=updated,
        )


def _parse_wind_value(raw: str) -> tuple[Optional[str], Optional[float]]:
    """Parsar vindvärde som 'SV 17.4' eller 'V 14.1' → (riktning, hastighet)."""
    parts = raw.split(" ", 1)
    if len(parts) == 2:
        dir_candidate = parts[0].upper()
        try:
            speed = float(parts[1].replace(",", "."))
            return dir_candidate, speed
        except ValueError:
            pass
    try:
        return None, float(raw.replace(",", "."))
    except ValueError:
        return None, None


def wind_dir_arrow(dir_str: Optional[str], dir_deg: Optional[float]) -> str:
    """Returnerar pil/kompassriktning för visning."""
    arrows = {
        "N": "↓", "NO": "↙", "O": "←", "SO": "↖",
        "S": "↑", "SV": "↗", "V": "→", "NV": "↘",
    }
    if dir_str and dir_str.upper() in arrows:
        return arrows[dir_str.upper()]
    if dir_deg is not None:
        idx = int((dir_deg + 22.5) / 45) % 8
        dirs = ["N", "NO", "O", "SO", "S", "SV", "V", "NV"]
        return arrows.get(dirs[idx], "?")
    return "?"
