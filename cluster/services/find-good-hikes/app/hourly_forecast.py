import sqlite3
import requests
from scrape import Walk
from pydantic import ValidationError
import json
import uuid
from pydantic_sqlite import DataBase
import logging
from error_handling import (
    retry_on_failure, handle_network_errors, safe_database_operation,
    ErrorCollector, log_performance
)
from email.utils import parsedate_to_datetime, formatdate
import time
from concurrent.futures import ThreadPoolExecutor
import threading
from queue import Queue

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

class WeatherCache:
    """Custom cache for weather data with conditional HTTP requests."""
    
    def __init__(self, cache_db_path: str = "met_weather_cache.sqlite"):
        self.cache_db_path = cache_db_path
        self._lock = threading.Lock()
        self._init_cache_db()
    
    def _init_cache_db(self):
        """Initialize the cache database."""
        with self._lock:
            conn = sqlite3.connect(self.cache_db_path, timeout=30.0)
            try:
                # Enable WAL mode for better concurrency
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA cache_size=10000")
                conn.execute("PRAGMA temp_store=memory")
                
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS weather_cache (
                        url TEXT PRIMARY KEY,
                        data TEXT,
                        last_modified TEXT,
                        expires TEXT,
                        cached_at REAL
                    )
                """)
                conn.commit()
            finally:
                conn.close()
    
    def get_cached_data(self, url: str) -> tuple[Optional[dict], Optional[str], Optional[str]]:
        """Get cached data, last_modified, and expires for a URL."""
        with self._lock:
            conn = sqlite3.connect(self.cache_db_path, timeout=30.0)
            try:
                cursor = conn.execute(
                    "SELECT data, last_modified, expires FROM weather_cache WHERE url = ?",
                    (url,)
                )
                row = cursor.fetchone()
                
                if row:
                    import json
                    return json.loads(row[0]), row[1], row[2]
                return None, None, None
            finally:
                conn.close()
    
    def store_cached_data(self, url: str, data: dict, last_modified: str, expires: str):
        """Store data in cache with metadata."""
        import json
        with self._lock:
            conn = sqlite3.connect(self.cache_db_path, timeout=30.0)
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO weather_cache 
                    (url, data, last_modified, expires, cached_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (url, json.dumps(data), last_modified, expires, time.time()))
                conn.commit()
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e).lower():
                    logger.warning(f"Database locked when caching {url}, retrying...")
                    time.sleep(0.1)
                    # Retry once
                    conn.execute("""
                        INSERT OR REPLACE INTO weather_cache 
                        (url, data, last_modified, expires, cached_at)
                        VALUES (?, ?, ?, ?, ?)
                    """, (url, json.dumps(data), last_modified, expires, time.time()))
                    conn.commit()
                else:
                    raise
            finally:
                conn.close()

@retry_on_failure(max_retries=3, delay=2.0, exceptions=(requests.RequestException,))
@handle_network_errors
def get_hourly_weather_forecast(
    latitude: float,
    longitude: float,
    session: requests.Session = None,
    cache: WeatherCache = None,
) -> WeatherFeature:
    url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={round(latitude, 4)}&lon={round(longitude, 4)}"
    headers = {
        "User-Agent": "joe@jomcgi.dev",
        "Accept": "application/json",
    }
    
    if session is None:
        session = requests.Session()
    
    if cache is None:
        cache = WeatherCache()
    
    # Get cached data
    cached_data, last_modified, expires = cache.get_cached_data(url)
    
    # Check if cached data is still valid
    if cached_data and expires:
        try:
            expires_dt = parsedate_to_datetime(expires)
            if datetime.now(expires_dt.tzinfo) < expires_dt:
                logger.debug(f"Using cached data for {url} (expires: {expires})")
                return WeatherFeature(**cached_data)
        except (ValueError, TypeError) as e:
            logger.warning(f"Error parsing expires date '{expires}': {e}")
    
    # Add conditional request header if we have cached data
    if cached_data and last_modified:
        headers["If-Modified-Since"] = last_modified
        logger.debug(f"Making conditional request with If-Modified-Since: {last_modified}")
    
    try:
        response = session.get(url, headers=headers)
        
        # Handle 304 Not Modified
        if response.status_code == 304:
            if cached_data:
                logger.debug(f"304 Not Modified - using cached data for {url}")
                return WeatherFeature(**cached_data)
            else:
                logger.warning(f"Received 304 but no cached data available for {url}")
                response.raise_for_status()
        
        response.raise_for_status()
        data = response.json()
        
        # Store in cache with response headers
        response_last_modified = response.headers.get('Last-Modified')
        response_expires = response.headers.get('Expires')
        
        if response_last_modified and response_expires:
            cache.store_cached_data(url, data, response_last_modified, response_expires)
            logger.debug(f"Cached weather data for {url} (expires: {response_expires})")
        
        forecast = WeatherFeature(**data)
        return forecast
        
    except ValidationError as e:
        logger.error(f"Validation error: {e}")
        raise
    except requests.RequestException as e:
        logger.error(f"Error fetching weather data: {e}")
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
    last_updated: Optional[datetime] = None
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

class RateLimiter:
    """Token bucket rate limiter for API requests."""
    
    def __init__(self, max_requests_per_second: float = 20.0):
        self.max_requests_per_second = max_requests_per_second
        self.tokens = max_requests_per_second
        self.last_update = time.time()
        self.lock = threading.Lock()
    
    def acquire(self):
        """Wait until a token is available, respecting the rate limit."""
        with self.lock:
            now = time.time()
            # Add tokens based on elapsed time
            elapsed = now - self.last_update
            self.tokens = min(self.max_requests_per_second, 
                            self.tokens + elapsed * self.max_requests_per_second)
            self.last_update = now
            
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return  # Token acquired immediately
            
            # Need to wait for next token
            sleep_time = (1.0 - self.tokens) / self.max_requests_per_second
            
        # Sleep outside the lock to allow other threads to check
        time.sleep(sleep_time)
        
        # Try again after sleeping
        with self.lock:
            self.tokens = max(0, self.tokens - 1.0)

def fetch_single_forecast(walk: Walk, session: requests.Session, cache: WeatherCache, rate_limiter: RateLimiter) -> tuple[Walk, Optional[WeatherFeature], Optional[Exception]]:
    """Fetch forecast for a single walk with rate limiting."""
    # Acquire rate limit token before making request
    rate_limiter.acquire()
    
    try:
        logger.debug(f"Fetching forecast for: {walk.name}")
        forecast = get_hourly_weather_forecast(
            latitude=walk.latitude,
            longitude=walk.longitude,
            session=session,
            cache=cache,
        )
        return walk, forecast, None
    except Exception as e:
        logger.error(f"Failed to fetch forecast for {walk.name}: {e}")
        return walk, None, e

def process_forecast_data(walk: Walk, forecast: WeatherFeature, forecast_db: DataBase):
    """Process forecast data and add to database, filtering out non-viable forecasts at storage time."""
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
                last_updated=datetime.now(),
            )
            
            # FILTER AT STORAGE TIME - Only store viable forecasts
            # Skip if it's nighttime
            if hourly_forecast.is_night:
                continue
                
            # Skip if excessive precipitation (>2mm/hour)
            if hourly_forecast.precipitation_amount and hourly_forecast.precipitation_amount > 2.0:
                continue
                
            # Skip if excessive wind (>50km/h)
            if hourly_forecast.wind_speed and hourly_forecast.wind_speed * 3.6 > 50.0:
                continue
            
            # Only store forecasts that meet minimum viability criteria
            forecast_db.add("forecasts", hourly_forecast)
            
        except ValidationError as e:
            logger.warning(f"Validation error for {walk.name}: {e}")
            continue
        except KeyError as e:
            logger.warning(f"Key error for {walk.name}: {e}")
            continue


def fetch_forecasts(walks_db_conn: sqlite3.Connection, forecast_db: DataBase, session: requests.Session = None, cache: WeatherCache = None, max_workers: int = 5, requests_per_second: float = 10.0):
    """Fetch weather forecasts for all walks in the database using concurrent processing with rate limiting."""
    if cache is None:
        cache = WeatherCache()
    if session is None:
        session = requests.Session()
    
    try:
        walk_tuples = walks_db_conn.execute("SELECT * FROM walks").fetchall()
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e).lower():
            logger.warning("Database locked when reading walks, retrying after brief delay...")
            time.sleep(1.0)
            try:
                walk_tuples = walks_db_conn.execute("SELECT * FROM walks").fetchall()
            except sqlite3.Error as retry_e:
                logger.error(f"Database error reading walks after retry: {retry_e}")
                return
        else:
            logger.error(f"Database error reading walks: {e}")
            return
    except sqlite3.Error as e:
        logger.error(f"Database error reading walks: {e}")
        return

    walks = [
        Walk(
            uuid=row[0], name=row[1], url=row[2], distance_km=row[3],
            ascent_m=row[4], duration_h=row[5], summary=row[6],
            latitude=row[7], longitude=row[8],
        )
        for row in walk_tuples
    ]

    logger.info(f"Fetching forecasts for {len(walks)} walks with rate limit of {requests_per_second}/sec and {max_workers} concurrent workers (reduced for better database concurrency)")
    
    # Create rate limiter (slightly under 20/sec for safety margin)
    rate_limiter = RateLimiter(requests_per_second)
    
    # Process forecasts concurrently with rate limiting
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_walk = {
            executor.submit(fetch_single_forecast, walk, session, cache, rate_limiter): walk
            for walk in walks
        }
        
        # Process completed tasks
        successful_forecasts = 0
        failed_forecasts = 0
        
        for future in future_to_walk:
            walk, forecast, error = future.result()
            
            if error is None and forecast is not None:
                try:
                    process_forecast_data(walk, forecast, forecast_db)
                    successful_forecasts += 1
                except Exception as e:
                    logger.error(f"Error processing forecast data for {walk.name}: {e}")
                    failed_forecasts += 1
            else:
                failed_forecasts += 1
    
    logger.info(f"Forecast fetching completed: {successful_forecasts} successful, {failed_forecasts} failed")

if __name__ == "__main__":
    from logging_config import setup_logging
    setup_logging(level="INFO")
    
    # Create session (no longer using requests_cache as we have custom caching)
    session = requests.Session()
    
    # Create custom weather cache
    cache = WeatherCache()
    
    # Create forecast database
    forecast_db = DataBase()
    
    # Open walks database connection
    with sqlite3.connect("walks.db") as walks_db:
        fetch_forecasts(walks_db, forecast_db, session, cache)
    
    # Save forecasts
    try:
        forecast_db.save("forecasts.sqlite.db")
        logger.info("Successfully saved weather forecasts to forecasts.sqlite.db")
    except Exception as e:
        logger.error(f"Failed to save forecasts database: {e}")