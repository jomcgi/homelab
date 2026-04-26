"""Stars refresh service: fetch MET Norway forecasts, score them, write a row."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx
from astral import LocationInfo
from astral.sun import elevation
from sqlmodel import Session, desc, select

from stars.models import RefreshRun
from stars.scoring import WeatherData, calculate_astronomy_score
from stars.seed import SCOTLAND_DARK_SKY_LOCATIONS, SeedLocation

logger = logging.getLogger("monolith.stars")

MET_NORWAY_URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
USER_AGENT = os.environ.get(
    "STARS_USER_AGENT", "monolith-stars/1.0 github.com/jomcgi/homelab"
)
RATE_LIMIT_PER_SEC = int(os.environ.get("STARS_RATE_LIMIT", "15"))
MIN_DISPLAY_SCORE = int(os.environ.get("STARS_MIN_DISPLAY_SCORE", "60"))
TOP_HOURS_PER_LOCATION = 5
HTTP_TIMEOUT = 30.0


async def _fetch_one(
    client: httpx.AsyncClient, loc: SeedLocation
) -> tuple[str, dict | None]:
    """Fetch a single forecast; None on transport failure (don't fail the whole refresh)."""
    try:
        resp = await client.get(
            MET_NORWAY_URL,
            params={
                "lat": loc["lat"],
                "lon": loc["lon"],
                "altitude": loc["altitude_m"],
            },
            headers={"User-Agent": USER_AGENT},
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        return loc["id"], resp.json()
    except httpx.HTTPError as exc:
        logger.warning("Forecast fetch failed for %s: %s", loc["id"], exc)
        return loc["id"], None


async def _fetch_all(locations: list[SeedLocation]) -> dict[str, dict]:
    """Fetch forecasts for every seed location with bounded concurrency."""
    semaphore = asyncio.Semaphore(RATE_LIMIT_PER_SEC)

    async with httpx.AsyncClient(timeout=httpx.Timeout(HTTP_TIMEOUT)) as client:

        async def _bounded(loc: SeedLocation) -> tuple[str, dict | None]:
            async with semaphore:
                result = await _fetch_one(client, loc)
                # Spread requests over time so we don't burst above MET's 20/s limit.
                await asyncio.sleep(1.0 / RATE_LIMIT_PER_SEC)
                return result

        results = await asyncio.gather(*(_bounded(loc) for loc in locations))

    return {loc_id: forecast for loc_id, forecast in results if forecast is not None}


def _score_location(loc: SeedLocation, forecast: dict) -> dict | None:
    """Score every dark hour in a forecast; return the location's ranked summary or None."""
    observer = LocationInfo(latitude=loc["lat"], longitude=loc["lon"]).observer
    timeseries = forecast.get("properties", {}).get("timeseries", [])
    scored_hours: list[dict] = []

    for entry in timeseries:
        time_str = entry["time"]
        try:
            t = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        except ValueError as exc:
            logger.debug("skip unparseable timeseries time %r: %s", time_str, exc)
            continue

        try:
            sun_alt = elevation(observer, t)
        except Exception as exc:  # pragma: no cover — defensive vs astral edge cases
            logger.debug("astral elevation failed at %s: %s", t, exc)
            continue
        if sun_alt > -12:  # nautical twilight or brighter — skip
            continue

        instant = entry.get("data", {}).get("instant", {}).get("details", {})
        next_1h = entry.get("data", {}).get("next_1_hours", {})
        try:
            weather = WeatherData(
                cloud_area_fraction=instant.get("cloud_area_fraction", 100),
                relative_humidity=instant.get("relative_humidity", 100),
                fog_area_fraction=instant.get("fog_area_fraction", 0),
                wind_speed=instant.get("wind_speed", 0),
                air_temperature=instant.get("air_temperature", 10),
                dew_point_temperature=instant.get("dew_point_temperature", 5),
                air_pressure_at_sea_level=instant.get(
                    "air_pressure_at_sea_level", 1013.25
                ),
            )
        except Exception as exc:
            logger.debug("skip malformed weather entry at %s: %s", time_str, exc)
            continue

        score = calculate_astronomy_score(weather)
        if score < MIN_DISPLAY_SCORE:
            continue

        scored_hours.append(
            {
                "time": time_str,
                "score": round(score, 1),
                "cloud_area_fraction": weather.cloud_area_fraction,
                "relative_humidity": weather.relative_humidity,
                "wind_speed": weather.wind_speed,
                "air_temperature": weather.air_temperature,
                "dew_spread": round(
                    weather.air_temperature - weather.dew_point_temperature, 1
                ),
                "symbol": next_1h.get("summary", {}).get("symbol_code", ""),
            }
        )

    if not scored_hours:
        return None

    scored_hours.sort(key=lambda h: h["score"], reverse=True)
    return {
        "id": loc["id"],
        "name": loc["name"],
        "lat": loc["lat"],
        "lon": loc["lon"],
        "altitude_m": loc["altitude_m"],
        "lp_zone": loc["lp_zone"],
        "best_score": scored_hours[0]["score"],
        "best_hours": scored_hours[:TOP_HOURS_PER_LOCATION],
    }


def build_payload(forecasts: dict[str, dict]) -> dict:
    """Score each forecast and assemble the final ranked payload."""
    by_id = {loc["id"]: loc for loc in SCOTLAND_DARK_SKY_LOCATIONS}
    ranked: list[dict] = []
    for loc_id, forecast in forecasts.items():
        loc = by_id.get(loc_id)
        if loc is None:
            continue
        scored = _score_location(loc, forecast)
        if scored is not None:
            ranked.append(scored)

    ranked.sort(key=lambda r: r["best_score"], reverse=True)
    return {
        "locations": ranked,
        "total_locations": len(SCOTLAND_DARK_SKY_LOCATIONS),
        "ranked_count": len(ranked),
        "min_display_score": MIN_DISPLAY_SCORE,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }


async def refresh_handler(session: Session) -> None:
    """Scheduled job: fetch + score + write one row.

    Records every run (success or failure) so the read endpoint can surface
    "last good payload" and the operator can see refresh history. A failed
    refresh never overwrites the last good payload — it just adds an
    ``error`` row.
    """
    started = datetime.now(timezone.utc)
    run = RefreshRun(started_at=started, status="running")
    session.add(run)
    session.commit()
    session.refresh(run)

    try:
        forecasts = await _fetch_all(SCOTLAND_DARK_SKY_LOCATIONS)
        payload = build_payload(forecasts)
        run.completed_at = datetime.now(timezone.utc)
        run.status = "ok"
        run.payload = payload
        run.locations_count = payload["ranked_count"]
        session.add(run)
        session.commit()
        logger.info(
            "stars.refresh ok: %d/%d locations ranked",
            payload["ranked_count"],
            payload["total_locations"],
        )
    except Exception as exc:
        run.completed_at = datetime.now(timezone.utc)
        run.status = "error"
        run.error = str(exc)[:1000]
        session.add(run)
        session.commit()
        logger.exception("stars.refresh failed")
        raise


def get_latest_payload(session: Session) -> dict | None:
    """Return the most recent successful refresh payload, or None if there isn't one yet."""
    stmt = (
        select(RefreshRun)
        .where(RefreshRun.status == "ok")
        .order_by(desc(RefreshRun.completed_at))
        .limit(1)
    )
    row = session.exec(stmt).first()
    return row.payload if row else None
