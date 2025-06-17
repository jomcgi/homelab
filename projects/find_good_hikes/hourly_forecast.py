import sqlite3
import requests_cache
import requests
from scrape import Walk
from pydantic import ValidationError
import uuid
from pydantic_sqlite import DataBase
import logging
from error_handling import (
    retry_on_failure, handle_network_errors, safe_database_operation,
    ErrorCollector, log_performance
)

# Configure logging
logger = logging.getLogger(__name__)

from typing import List, Tuple, Optional
from datetime import datetime
from pydantic import BaseModel

# Inner Models (Details, Summaries)

class InstantDetails(BaseModel):
    air_pressure_at_sea_level: Optional[float] = None
    air_temperature: Optional[float] = None
    cloud_area_fraction: Optional[float] = None
    relative_humidity: Optional[float] = None
    wind_from_direction: Optional[float] = None
    wind_speed: Optional[float] = None

class NextXHoursDetails(BaseModel):
    # Using Field alias because 'precipitation_amount' might not always be present
    # Making it optional covers cases where the details dict is empty {}
    precipitation_amount: Optional[float] = None

class Summary(BaseModel):
    symbol_code: str

# Intermediate Models (Forecast Intervals)

class InstantData(BaseModel):
    details: InstantDetails

class NextXHoursData(BaseModel):
    summary: Summary
    details: NextXHoursDetails

# Data Model (within Timeseries)

class Data(BaseModel):
    instant: InstantData
    next_1_hours: Optional[NextXHoursData] = None
    next_6_hours: Optional[NextXHoursData] = None
    next_12_hours: Optional[NextXHoursData] = None

# Timeseries List Item Model

class TimeseriesData(BaseModel):
    time: datetime
    data: Data

# Meta and Properties Models

class MetaUnits(BaseModel):
    air_pressure_at_sea_level: Optional[str] = None
    air_temperature: Optional[str] = None
    cloud_area_fraction: Optional[str] = None
    precipitation_amount: Optional[str] = None
    relative_humidity: Optional[str] = None
    wind_from_direction: Optional[str] = None
    wind_speed: Optional[str] = None
    # Allow for other potential future units
    # class Config:
    #     extra = 'allow'
    # Or define explicitly if known, or make the whole dict Optional[str]

class Meta(BaseModel):
    updated_at: datetime
    units: MetaUnits # Or Dict[str, str] if units can vary widely

class Properties(BaseModel):
    meta: Meta
    timeseries: List[TimeseriesData]

# Geometry Model

class Geometry(BaseModel):
    type: str # Could use Literal['Point'] for stricter validation
    coordinates: Tuple[float, float, int] # Longitude, Latitude, Altitude

# Top-Level Feature Model (Root)

class WeatherFeature(BaseModel):
    type: str # Could use Literal['Feature']
    geometry: Geometry
    properties: Properties

@retry_on_failure(max_retries=3, delay=2.0, exceptions=(requests.RequestException,))
@handle_network_errors
def get_hourly_weather_forecast(
    latitude: float,
    longitude: float,
    session: requests.Session = None,
) -> WeatherFeature:
  url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={round(latitude, 4)}&lon={round(longitude, 4)}"
  headers = {
    "User-Agent": "joe@jomcgi.dev",
    "Accept": "application/json",
  }
  if session is None:
    session = requests.Session()
  
  try:
    response = session.get(url, headers=headers)
    response.raise_for_status()  # Raise an error for bad responses
    data = response.json()
    forecast = WeatherFeature(**data)
    return forecast
  except ValidationError as e:
    print(f"Validation error: {e}")
    raise
  except requests.RequestException as e:
    print(f"Error fetching weather data: {e}")
    raise

from sunrisesunset import SunriseSunset

def is_night(
        latitude: float,
        longitude: float,
        time: datetime,
):
    sun_info = SunriseSunset(
        lat=latitude,
        lon=longitude,
        date=time,
    )
    return sun_info.is_night()

class HourlyForecast(BaseModel):
    time: datetime
    air_pressure_at_sea_level: Optional[float] = None
    air_temperature: Optional[float] = None
    cloud_area_fraction: Optional[float] = None
    relative_humidity: Optional[float] = None
    wind_from_direction: Optional[float] = None
    wind_speed: Optional[float] = None
    precipitation_amount: Optional[float] = None
    symbol_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_night: Optional[bool] = None
    uuid: Optional[str] = None
    location_id: Optional[str] = None
    def __init__(self, **data):
        super().__init__(**data)
        self.is_night = is_night(
            latitude=self.latitude,
            longitude=self.longitude,
            time=self.time,
        )
        self.location_id = str(uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"{self.latitude},{self.longitude}",))
        self.uuid = str(uuid.uuid4())

def fetch_forecasts(walks_db_conn: sqlite3.Connection, forecast_db: DataBase, session: requests.Session = None):
  """Fetch weather forecasts for all walks in the database."""
  try:
    walk_tuples = walks_db_conn.execute(
        "SELECT * FROM walks"
    ).fetchall()
  except sqlite3.Error as e:
    logger.error(f"Database error reading walks: {e}")
    return

  walks = [
      Walk(
          uuid=row[0],
          name=row[1],
          url=row[2],
          distance_km=row[3],
          ascent_m=row[4],
          duration_h=row[5],
          summary=row[6],
          latitude=row[7],
          longitude=row[8],
      )
      for row in walk_tuples
  ]

  for walk in walks:
      logger.debug(f"Fetching forecast for: {walk.name}")
      try:
        forecast = get_hourly_weather_forecast(
            latitude=walk.latitude,
            longitude=walk.longitude,
            session=session,
        )
      except Exception as e:
        logger.error(f"Failed to fetch forecast for {walk.name}: {e}")
        continue

      for timeseries in forecast.properties.timeseries:
          try:
              next_1_hours = timeseries.data.next_1_hours
              if next_1_hours is None:
                  precipitation_amount = None
                  symbol_code = None
              else:
                  precipitation_amount = next_1_hours.details.precipitation_amount
                  symbol_code = next_1_hours.summary.symbol_code
              hourly_forecast = HourlyForecast(
                  time=timeseries.time,
                  air_pressure_at_sea_level=timeseries.data.instant.details.air_pressure_at_sea_level,
                  air_temperature=timeseries.data.instant.details.air_temperature,
                  cloud_area_fraction=timeseries.data.instant.details.cloud_area_fraction,
                  relative_humidity=timeseries.data.instant.details.relative_humidity,
                  wind_from_direction=timeseries.data.instant.details.wind_from_direction,
                  wind_speed=timeseries.data.instant.details.wind_speed,
                  precipitation_amount=precipitation_amount,
                  symbol_code=symbol_code,
                  latitude=forecast.geometry.coordinates[1],
                  longitude=forecast.geometry.coordinates[0],
              )
              forecast_db.add(
                "forecasts",
                hourly_forecast
              )
          except ValidationError as e:
              logger.warning(f"Validation error for {walk.name}: {e}")
              continue
          except KeyError as e:
              logger.warning(f"Key error for {walk.name}: {e}")
              continue

if __name__ == "__main__":
    from logging_config import setup_logging
    setup_logging(level="INFO")
    
    import requests_cache
    
    # Create cached session
    session = requests_cache.CachedSession(
        cache_name='met_weather_cache',
        backend='sqlite',
        expire_after=3600,  # Cache for 1 hour
        allowable_methods=['GET'],
    )
    
    # Create forecast database
    forecast_db = DataBase()
    
    # Open walks database connection
    with sqlite3.connect("walks.db") as walks_db:
        fetch_forecasts(walks_db, forecast_db, session)
    
    # Save forecasts
    try:
        forecast_db.save("forecasts.sqlite.db")
        logger.info("Successfully saved weather forecasts to forecasts.sqlite.db")
    except Exception as e:
        logger.error(f"Failed to save forecasts database: {e}")