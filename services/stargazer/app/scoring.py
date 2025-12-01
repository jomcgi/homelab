"""Astronomy suitability scoring for weather forecasts."""

from pydantic import BaseModel, Field


class WeatherData(BaseModel):
    """Weather data from MET Norway API."""

    cloud_area_fraction: float = Field(ge=0, le=100)
    relative_humidity: float = Field(ge=0, le=100)
    fog_area_fraction: float = Field(default=0, ge=0, le=100)
    wind_speed: float = Field(ge=0)  # m/s
    air_temperature: float  # Celsius
    dew_point_temperature: float  # Celsius
    air_pressure_at_sea_level: float = Field(default=1013.25)  # hPa


class ScoredForecast(BaseModel):
    """Forecast with astronomy suitability score."""

    time: str
    score: float = Field(ge=0, le=100)
    cloud_area_fraction: float
    relative_humidity: float
    fog_area_fraction: float
    wind_speed: float
    air_temperature: float
    dew_spread: float  # temp - dew_point
    air_pressure: float
    symbol: str = ""  # MET Norway weather symbol


def calculate_astronomy_score(weather: WeatherData) -> float:
    """
    Calculate astronomy suitability score (0-100).

    Scoring formula:
    - cloud_score: 50% weight (most important for visibility)
    - humidity_score: 15% weight (affects transparency)
    - fog_score: 10% weight (blocks visibility)
    - wind_score: 10% weight (affects seeing/stability)
    - dew_score: 15% weight (condensation risk on optics)
    - pressure_bonus: +0-10 if high pressure (stable conditions)
    """
    # Cloud score (0-100, lower cloud = higher score)
    if weather.cloud_area_fraction < 20:
        cloud_score = 100
    elif weather.cloud_area_fraction < 50:
        cloud_score = 100 - (weather.cloud_area_fraction - 20) * 1.67
    else:
        cloud_score = max(0, 50 - (weather.cloud_area_fraction - 50))

    # Humidity score (0-100, lower humidity = higher score)
    if weather.relative_humidity < 70:
        humidity_score = 100
    elif weather.relative_humidity < 85:
        humidity_score = 100 - (weather.relative_humidity - 70) * 3.33
    else:
        humidity_score = max(0, 50 - (weather.relative_humidity - 85) * 3.33)

    # Fog score (0-100, no fog = highest score)
    if weather.fog_area_fraction < 5:
        fog_score = 100
    elif weather.fog_area_fraction < 20:
        fog_score = 100 - (weather.fog_area_fraction - 5) * 3.33
    else:
        fog_score = max(0, 50 - (weather.fog_area_fraction - 20) * 1.67)

    # Wind score (0-100, calm = highest score)
    if weather.wind_speed < 5:
        wind_score = 100
    elif weather.wind_speed < 10:
        wind_score = 100 - (weather.wind_speed - 5) * 10
    else:
        wind_score = max(0, 50 - (weather.wind_speed - 10) * 5)

    # Dew spread score (temp - dew_point, higher = less condensation risk)
    dew_spread = weather.air_temperature - weather.dew_point_temperature
    if dew_spread > 5:
        dew_score = 100
    elif dew_spread > 2:
        dew_score = 100 - (5 - dew_spread) * 16.67
    else:
        dew_score = max(0, 50 - (2 - dew_spread) * 25)

    # Pressure bonus (high pressure = stable atmosphere)
    pressure_bonus = 0
    if weather.air_pressure_at_sea_level > 1015:
        pressure_bonus = min(10, (weather.air_pressure_at_sea_level - 1015) * 2)

    # Weighted average
    weighted_score = (
        cloud_score * 0.50
        + humidity_score * 0.15
        + fog_score * 0.10
        + wind_score * 0.10
        + dew_score * 0.15
        + pressure_bonus
    )

    return min(100, max(0, weighted_score))


def is_dark_enough(
    sun_altitude: float,
    astronomical_darkness_threshold: float = -18.0,
) -> bool:
    """
    Check if it's dark enough for astronomy.

    Astronomical darkness: sun > 18 degrees below horizon.
    """
    return sun_altitude <= astronomical_darkness_threshold
