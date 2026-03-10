"""Phase 4: Weather Integration - fetch forecasts and score locations."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import httpx
from astral import LocationInfo
from astral.sun import elevation

from projects.stargazer.backend.config import Settings
from projects.stargazer.backend.scoring import (
    WeatherData,
    calculate_astronomy_score,
)

logger = logging.getLogger(__name__)


async def fetch_forecast(
    lat: float,
    lon: float,
    altitude: int,
    client: httpx.AsyncClient,
    settings: Settings,
) -> dict | None:
    """Fetch weather forecast from MET Norway API for a single location."""
    url = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
    params = {"lat": lat, "lon": lon, "altitude": altitude}
    headers = {"User-Agent": settings.met_norway_user_agent}

    try:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        logger.warning(f"Failed to fetch forecast for ({lat}, {lon}): {e}")
        return None


async def fetch_all_forecasts(settings: Settings) -> Path:
    """
    Fetch forecasts for all sample points with rate limiting.

    Always fetches fresh data - cron schedule controls refresh frequency.
    """
    points_path = settings.processed_dir / "sample_points_enriched.geojson"
    output_path = settings.output_dir / "forecasts_raw.json"

    settings.output_dir.mkdir(parents=True, exist_ok=True)

    points = gpd.read_file(points_path)
    logger.info(f"Fetching forecasts for {len(points)} locations...")

    semaphore = asyncio.Semaphore(settings.met_norway_rate_limit)
    forecasts = {}

    async def fetch_with_limit(row):
        async with semaphore:
            point_id = row["id"]

            async with httpx.AsyncClient(timeout=30) as client:
                forecast = await fetch_forecast(
                    lat=row["lat"],
                    lon=row["lon"],
                    altitude=int(row.get("altitude_m", 0)),
                    client=client,
                    settings=settings,
                )

            # Rate limiting delay
            await asyncio.sleep(1.0 / settings.met_norway_rate_limit)
            return point_id, forecast

    tasks = [fetch_with_limit(row) for _, row in points.iterrows()]
    results = await asyncio.gather(*tasks)

    for point_id, forecast in results:
        if forecast:
            forecasts[point_id] = forecast

    with open(output_path, "w") as f:
        json.dump(forecasts, f)

    logger.info(f"Fetched {len(forecasts)} forecasts: {output_path}")
    return output_path


def score_locations(settings: Settings) -> Path:
    """
    Calculate astronomy suitability score for each forecast hour.

    Filters to:
    - Only hours during nautical darkness (sun below -12°)
    - Only hours with score >= min_astronomy_score
    """
    forecasts_path = settings.output_dir / "forecasts_raw.json"
    points_path = settings.processed_dir / "sample_points_enriched.geojson"
    output_path = settings.output_dir / "forecasts_scored.json"

    with open(forecasts_path) as f:
        forecasts = json.load(f)

    points = gpd.read_file(points_path)
    points_dict = {row["id"]: row for _, row in points.iterrows()}

    scored_data = {}

    for point_id, forecast in forecasts.items():
        point = points_dict.get(point_id)
        if point is None:
            continue

        lat, lon = point["lat"], point["lon"]
        location = LocationInfo(latitude=lat, longitude=lon)

        timeseries = forecast.get("properties", {}).get("timeseries", [])
        scored_hours = []

        for entry in timeseries:
            time_str = entry["time"]
            time = datetime.fromisoformat(time_str.replace("Z", "+00:00"))

            # Check if it's dark enough (nautical twilight: sun below -12°)
            try:
                sun_alt = elevation(location.observer, time)
                if sun_alt > -12:
                    continue
            except Exception:
                # If sun calculation fails, skip
                continue

            # Extract weather data
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
            except Exception as e:
                logger.debug(f"Failed to parse weather data: {e}")
                continue

            score = calculate_astronomy_score(weather)

            if score >= settings.min_astronomy_score:
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
                        "air_pressure": weather.air_pressure_at_sea_level,
                        "symbol": next_1h.get("summary", {}).get("symbol_code", ""),
                    }
                )

        if scored_hours:
            scored_data[point_id] = {
                "coordinates": {"lat": lat, "lon": lon},
                "altitude_m": point.get("altitude_m", 0),
                "lp_zone": point.get("lp_zone", "unknown"),
                "scored_hours": sorted(
                    scored_hours, key=lambda x: x["score"], reverse=True
                ),
            }

    with open(output_path, "w") as f:
        json.dump(scored_data, f, indent=2)

    logger.info(f"Scored {len(scored_data)} locations: {output_path}")
    return output_path


def output_best_locations(settings: Settings) -> Path:
    """
    Produce final ranked list of best viewing opportunities.

    Returns all locations with score >= 80, sorted by best score.
    """
    scored_path = settings.output_dir / "forecasts_scored.json"
    output_path = settings.output_dir / "best_locations.json"

    with open(scored_path) as f:
        scored_data = json.load(f)

    # Filter to locations with best_score >= 80 (matches frontend MIN_SCORE)
    min_display_score = 80
    ranked = []
    for point_id, data in scored_data.items():
        best_hours = [
            h for h in data["scored_hours"] if h["score"] >= min_display_score
        ]
        if best_hours:
            ranked.append(
                {
                    "id": point_id,
                    "coordinates": data["coordinates"],
                    "altitude_m": data["altitude_m"],
                    "lp_zone": data["lp_zone"],
                    "best_hours": best_hours[:5],  # Top 5 hours per location
                    "best_score": best_hours[0]["score"],
                }
            )

    # Sort by best score
    ranked.sort(key=lambda x: x["best_score"], reverse=True)

    with open(output_path, "w") as f:
        json.dump(ranked, f, indent=2)

    logger.info(f"Output {len(ranked)} best locations: {output_path}")
    return output_path
