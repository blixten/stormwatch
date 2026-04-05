"""Hämtar brostatus och trafikstörningar från Trafikverkets öppna data-API."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Optional

import httpx

from stormwatch.models import BridgeStatus

logger = logging.getLogger(__name__)

API_URL = "https://api.trafikverket.se/api2/TrvInfo.ashx"

# Nyckelord (svenska) som indikerar broar i Trafikverkets textfält
_BRIDGE_KEYWORDS = (
    "bro",
    "bron",
    "bridge",
    "öppnar",
    "öppning",
    "broöppning",
    "rörlig bro",
)

# MessageCodes i Trafikverket-systemet som är relevanta för broar
_BRIDGE_MESSAGE_CODES = {
    "BridgeClosure",
    "BridgeMaintenance",
    "BridgeSwingBridgePassageRestriction",
    "MovableBridge",
    "BridgeRestrictions",
}

# MessageCodes som innebär att bron är stängd
_CLOSURE_MESSAGE_CODES = {"BridgeClosure"}

# Svårighetsgrad → läsbar text
_SEVERITY_MAP = {
    "low": "Låg",
    "medium": "Medel",
    "high": "Hög",
    "veryhigh": "Mycket hög",
}


def _build_xml_request(api_key: str, lat: float, lon: float, radius_km: int) -> str:
    return (
        f'<REQUEST>'
        f'<LOGIN authenticationkey="{api_key}" />'
        f'<QUERY objecttype="Situation" schemaversion="1.5" limit="100">'
        f'<FILTER>'
        f'<WITHIN name="Deviation.Geometry.Point.WGS84"'
        f' shape="center" value="{lat} {lon}" radius="{radius_km}km" />'
        f'</FILTER>'
        f'<INCLUDE>Deviation.Header</INCLUDE>'
        f'<INCLUDE>Deviation.MessageCode</INCLUDE>'
        f'<INCLUDE>Deviation.SeverityText</INCLUDE>'
        f'<INCLUDE>Deviation.StartTime</INCLUDE>'
        f'<INCLUDE>Deviation.EndTime</INCLUDE>'
        f'<INCLUDE>Deviation.LocationDescriptor</INCLUDE>'
        f'</QUERY>'
        f'</REQUEST>'
    )


def _is_bridge_related(header: str, message_code: str) -> bool:
    """Returnerar True om händelsen är bro-relaterad."""
    if message_code in _BRIDGE_MESSAGE_CODES:
        return True
    header_lower = header.lower()
    return any(kw in header_lower for kw in _BRIDGE_KEYWORDS)


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _extract_bridge_name(header: str) -> str:
    """Extraherar ett kortare bronamn ur rubriktexten."""
    if not header:
        return "Okänd bro"
    # Returnera de första 60 tecknen som namn
    name = header.strip()
    return name[:60] + ("…" if len(name) > 60 else "")


def _is_closed(message_code: str, header: str) -> bool:
    header_lower = header.lower()
    closed_keywords = ("stängd", "stängs", "spärrad", "avstängd", "closure", "closed")
    return message_code in _CLOSURE_MESSAGE_CODES or any(kw in header_lower for kw in closed_keywords)


def _parse_response(xml_text: str) -> list[BridgeStatus]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("Trafikverket: XML-parsningsfel: %s", exc)
        return []

    results: list[BridgeStatus] = []
    for situation in root.iter("Situation"):
        for deviation in situation.findall("Deviation"):
            header = (deviation.findtext("Header") or "").strip()
            message_code = (deviation.findtext("MessageCode") or "").strip()

            if not _is_bridge_related(header, message_code):
                continue

            severity_raw = (deviation.findtext("SeverityText") or "").lower()
            severity = _SEVERITY_MAP.get(severity_raw, "Okänd")
            start_time = _parse_datetime(deviation.findtext("StartTime"))
            end_time = _parse_datetime(deviation.findtext("EndTime"))

            results.append(BridgeStatus(
                name=_extract_bridge_name(header),
                header=header,
                severity=severity,
                message_code=message_code,
                start_time=start_time,
                end_time=end_time,
                is_closed=_is_closed(message_code, header),
            ))

    return results


class TrafikverketFetcher:
    """Hämtar brostörningar från Trafikverkets öppna data-API."""

    async def fetch_bridge_status(
        self,
        api_key: str,
        client: httpx.AsyncClient,
        lat: float = 57.70,
        lon: float = 11.97,
        radius_km: int = 200,
    ) -> list[BridgeStatus]:
        """Returnerar listan med brostörningar, tom lista vid fel eller saknad nyckel."""
        if not api_key:
            return []

        xml_body = _build_xml_request(api_key, lat, lon, radius_km)
        try:
            response = await client.post(
                API_URL,
                content=xml_body.encode("utf-8"),
                headers={"Content-Type": "text/xml; charset=utf-8"},
                timeout=15.0,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Trafikverket HTTP-fel %s: %s", exc.response.status_code, exc
            )
            return []
        except Exception as exc:
            logger.warning("Trafikverket API-fel: %s", exc)
            return []

        bridges = _parse_response(response.text)
        logger.debug("Trafikverket: %d brostörningar hittades", len(bridges))
        return bridges
