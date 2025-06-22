"""
HikeFinder - A deep module for finding good hiking routes with weather.

This module hides ALL complexity behind a simple interface:
- Database management
- Web scraping
- Weather forecasting  
- Scoring algorithms
- Error handling

The user only needs to know: location → ranked hikes
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Annotated
from dataclasses import dataclass
import typer
from haversine import haversine, Unit
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from hourly_forecast import HourlyForecast
from scrape import Walk, scrape_walkhighlands
import requests_cache
from hourly_forecast import fetch_forecasts, WeatherCache
from pydantic_sqlite import DataBase
from config import get_cache_config, get_database_config, get_db_path
import requests
import sqlite3
from weather_scoring import score_forecast_period

logger = logging.getLogger(__name__)


@dataclass
class Hike:
    """A hiking route with weather forecast."""
    name: str
    distance_km: float
    duration_hours: float
    ascent_m: int
    url: str
    weather_score: float  # 0-100, higher is better
    weather_summary: str
    distance_from_you_km: float
    weather_details: dict = None  # Structured weather data for UI formatting
    weather_windows: list = None  # List of good weather windows for UI


class HikeFinder:
    """
    Find good hiking routes with weather forecasts.
    
    This is a DEEP module - simple interface hiding complex implementation.
    """
    
    def __init__(self, data_dir: Optional[Path] = None):
        """Initialize with optional data directory for testing."""
        self._data_dir = data_dir or Path.cwd()
        self._setup_logging()
        self.app = typer.Typer(help="Find good hiking routes with weather forecasts")
        self.app.command()(self.find)
        self.app.command()(self.update)
    
    def find_hikes(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 25.0,
        max_results: int = 10,
        available_dates: Optional[List[str]] = None,
        start_after: Optional[str] = None,
        finish_before: Optional[str] = None,
        max_cloud_cover_percent: Optional[float] = None,
        allow_rain: bool = True,
        max_precipitation_mm: Optional[float] = None,
        max_wind_speed_kmh: Optional[float] = None,
        min_temperature_c: Optional[float] = None,
        max_temperature_c: Optional[float] = None
    ) -> List[Hike]:
        """
        Find the best hiking routes near you.
        
        Args:
            latitude: Your latitude
            longitude: Your longitude  
            radius_km: Search radius in kilometers
            max_results: Maximum number of results
            available_dates: List of dates you're available (YYYY-MM-DD format)
            start_after: Earliest acceptable start time (HH:MM format)
            finish_before: Latest acceptable finish time (HH:MM format)
            max_cloud_cover_percent: Maximum acceptable cloud cover (0-100%)
            allow_rain: Whether to allow any rain at all
            max_precipitation_mm: Maximum acceptable precipitation per hour
            max_wind_speed_kmh: Maximum acceptable wind speed
            min_temperature_c: Minimum acceptable temperature
            max_temperature_c: Maximum acceptable temperature
            
        Returns:
            List of Hike objects, filtered by weather conditions
            
        Raises:
            HikeFinderError: If something goes wrong
        """
        try:
            return self._find_hikes_implementation(
                latitude, longitude, radius_km, max_results, available_dates, start_after, finish_before,
                max_cloud_cover_percent, allow_rain, max_precipitation_mm, max_wind_speed_kmh,
                min_temperature_c, max_temperature_c
            )
        except Exception as e:
            logger.error(f"Failed to find hikes: {e}")
            raise HikeFinderError(f"Could not find hikes: {e}") from e
    
    def update_data(self) -> None:
        """
        Update hiking routes and weather data.
        
        Call this periodically to refresh the data.
        May take several minutes on first run.
        """
        try:
            self._update_data_implementation()
        except Exception as e:
            logger.error(f"Failed to update data: {e}")
            raise HikeFinderError(f"Could not update data: {e}") from e
    
    def update_walks(self) -> None:
        """
        Update hiking routes data (one-time setup).
        
        Call this once to scrape and save hiking routes.
        Only needs to be done occasionally when new routes are added.
        """
        try:
            self._update_walks_implementation()
        except Exception as e:
            logger.error(f"Failed to update walks: {e}")
            raise HikeFinderError(f"Could not update walks: {e}") from e
    
    def update_weather(self) -> None:
        """
        Update weather forecasts only (regular updates).
        
        Call this regularly (e.g., hourly) to refresh weather data.
        Much faster than update_data() as it doesn't scrape routes.
        """
        try:
            self._update_weather_implementation()
        except Exception as e:
            logger.error(f"Failed to update weather: {e}")
            raise HikeFinderError(f"Could not update weather: {e}") from e
    
    def _setup_logging(self):
        """Configure logging for this module."""
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
    
    def _find_hikes_implementation(
        self, lat: float, lon: float, radius: float, max_results: int,
        available_dates: Optional[List[str]] = None, start_after: Optional[str] = None, finish_before: Optional[str] = None,
        max_cloud_cover_percent: Optional[float] = None, allow_rain: bool = True, max_precipitation_mm: Optional[float] = None,
        max_wind_speed_kmh: Optional[float] = None, min_temperature_c: Optional[float] = None, max_temperature_c: Optional[float] = None
    ) -> List[Hike]:
        """Internal implementation of find_hikes."""
        
        # Check if data exists
        self._ensure_data_exists()
        
        # Get database paths
        db_config = get_database_config()
        walks_db_path = get_db_path(db_config.walks_db_path)
        forecasts_db_path = get_db_path(db_config.forecasts_db_path)
        
        # Find walks using our internal implementation
        with sqlite3.connect(walks_db_path, timeout=30.0) as walks_db, \
             sqlite3.connect(forecasts_db_path, timeout=30.0) as forecasts_db:
            # Read-only mode - no WAL mode needed for web app
            
            walks = self._find_walks_with_weather(
                lat, lon, radius, walks_db, forecasts_db, available_dates, start_after, finish_before,
                max_cloud_cover_percent, allow_rain, max_precipitation_mm, max_wind_speed_kmh,
                min_temperature_c, max_temperature_c
            )
        
        # Convert to simple Hike objects
        hikes = []
        for walk in walks[:max_results]:
            weather_details = None
            weather_windows = None
            if walk.weather_score and walk.weather_score.factors.get('weather_details'):
                weather_details = walk.weather_score.factors['weather_details']
                weather_windows = walk.weather_score.factors.get('weather_windows', [])
            
            hikes.append(Hike(
                name=walk.name,
                distance_km=walk.distance_km,
                duration_hours=walk.duration_h,
                ascent_m=walk.ascent_m,
                url=walk.url,
                weather_score=walk.weather_score.score if walk.weather_score else 0,
                weather_summary=walk.weather_score.explanation if walk.weather_score else "No weather data",
                distance_from_you_km=walk.distance_from_center_km or 0,
                weather_details=weather_details,
                weather_windows=weather_windows
            ))
        
        return hikes
    
    def _find_walks_with_weather(self, lat, lon, radius, walks_db, forecasts_db, available_dates=None, start_after=None, finish_before=None,
                                max_cloud_cover_percent=None, allow_rain=True, max_precipitation_mm=None,
                                max_wind_speed_kmh=None, min_temperature_c=None, max_temperature_c=None):
        """Find walks near location with weather data and scoring."""
        
        # Create WalkSearchResult class inline to avoid dependencies
        class WalkSearchResult(Walk):
            distance_from_center_km: float | None = None
            forecast: list[HourlyForecast] | None = None
            weather_score: object = None
        
        # Find nearby walks
        import sqlite3
        walks_db.row_factory = sqlite3.Row
        cursor = walks_db.cursor()
        
        cursor.execute("""
            SELECT uuid, name, url, distance_km, ascent_m, duration_h, 
                   summary, latitude, longitude 
            FROM walks
        """)
        rows = cursor.fetchall()
        
        center_point = (lat, lon)
        nearby_walks = []
        
        for row in rows:
            walk_point = (row['latitude'], row['longitude'])
            distance = haversine(center_point, walk_point, unit=Unit.KILOMETERS)
            
            if distance <= radius:
                walk = WalkSearchResult(
                    uuid=row['uuid'],
                    name=row['name'],
                    url=row['url'],
                    distance_km=row['distance_km'],
                    ascent_m=row['ascent_m'],
                    duration_h=row['duration_h'],
                    summary=row['summary'],
                    latitude=row['latitude'],
                    longitude=row['longitude'],
                )
                walk.distance_from_center_km = round(distance, 2)
                nearby_walks.append(walk)
        
        # Fetch weather for each walk
        forecasts_db.row_factory = sqlite3.Row
        cursor = forecasts_db.cursor()
        
        for walk in nearby_walks:
            cursor.execute("""
                SELECT time, air_pressure_at_sea_level, air_temperature,
                cloud_area_fraction, relative_humidity, wind_from_direction,
                wind_speed, precipitation_amount, symbol_code, latitude,
                longitude, is_night, uuid, location_id
                FROM forecasts WHERE location_id = ?
            """, (walk.uuid,))
            
            rows = cursor.fetchall()
            forecasts = []
            
            for row in rows:
                forecast = HourlyForecast(
                    time=row['time'],
                    air_pressure_at_sea_level=row['air_pressure_at_sea_level'],
                    air_temperature=row['air_temperature'],
                    cloud_area_fraction=row['cloud_area_fraction'],
                    relative_humidity=row['relative_humidity'],
                    wind_from_direction=row['wind_from_direction'],
                    wind_speed=row['wind_speed'],
                    precipitation_amount=row['precipitation_amount'],
                    symbol_code=row['symbol_code'],
                    latitude=row['latitude'],
                    longitude=row['longitude'],
                    is_night=row['is_night'],
                    uuid=row['uuid'],
                    location_id=row['location_id']
                )
                
                # Only include daylight hours in the future
                if (forecast.time > datetime.now(tz=ZoneInfo("Europe/London")) and 
                    forecast.is_night is False):
                    
                    # Apply safety filtering first (exclude dangerous conditions)
                    if forecast.precipitation_amount and forecast.precipitation_amount > 2.0:
                        continue  # Skip heavy rain (>2mm/hour)
                    
                    if forecast.wind_speed and forecast.wind_speed * 3.6 > 50.0:
                        continue  # Skip dangerous wind (>50km/h)
                    
                    # Apply explicit weather filters
                    if not allow_rain and forecast.precipitation_amount and forecast.precipitation_amount > 0:
                        continue  # Skip any rain if not allowed
                    
                    if max_precipitation_mm and forecast.precipitation_amount and forecast.precipitation_amount > max_precipitation_mm:
                        continue  # Skip if exceeds max precipitation
                    
                    if max_wind_speed_kmh and forecast.wind_speed and forecast.wind_speed * 3.6 > max_wind_speed_kmh:
                        continue  # Skip if exceeds max wind speed
                    
                    if max_cloud_cover_percent and forecast.cloud_area_fraction:
                        cloud_percent = forecast.cloud_area_fraction * 100 if forecast.cloud_area_fraction <= 1.0 else forecast.cloud_area_fraction
                        if cloud_percent > max_cloud_cover_percent:
                            continue  # Skip if exceeds max cloud cover
                    
                    if min_temperature_c and forecast.air_temperature and forecast.air_temperature < min_temperature_c:
                        continue  # Skip if below min temperature
                    
                    if max_temperature_c and forecast.air_temperature and forecast.air_temperature > max_temperature_c:
                        continue  # Skip if above max temperature
                    
                    # If available_dates specified, only include forecasts for those dates
                    if available_dates:
                        forecast_date = forecast.time.date().strftime("%Y-%m-%d")
                        if forecast_date not in available_dates:
                            continue
                    
                    # Apply time filtering if specified
                    if start_after or finish_before:
                        forecast_hour = forecast.time.hour
                        forecast_minute = forecast.time.minute
                        forecast_time_minutes = forecast_hour * 60 + forecast_minute
                        
                        # Parse start_after time (HH:MM)
                        if start_after:
                            try:
                                start_hour, start_min = map(int, start_after.split(':'))
                                start_after_minutes = start_hour * 60 + start_min
                                if forecast_time_minutes < start_after_minutes:
                                    continue
                            except (ValueError, AttributeError):
                                logger.warning(f"Invalid start_after time format: {start_after}")
                        
                        # Parse finish_before time (HH:MM) and calculate if hike would finish in time
                        if finish_before:
                            try:
                                finish_hour, finish_min = map(int, finish_before.split(':'))
                                finish_before_minutes = finish_hour * 60 + finish_min
                                
                                # Calculate when hike would finish if started at forecast time
                                hike_duration_minutes = walk.duration_h * 60
                                expected_finish_minutes = forecast_time_minutes + hike_duration_minutes
                                
                                # Convert to same day minutes (handle day overflow)
                                expected_finish_minutes = expected_finish_minutes % (24 * 60)
                                
                                if expected_finish_minutes > finish_before_minutes:
                                    continue
                            except (ValueError, AttributeError):
                                logger.warning(f"Invalid finish_before time format: {finish_before}")
                    
                    forecasts.append(forecast)
            
            walk.forecast = forecasts
        
        # Filter out walks that don't have sufficient continuous forecast data after weather filtering
        valid_walks = []
        for walk in nearby_walks:
            if walk.forecast:
                # Check if there's a continuous window of at least the hike duration
                if self._has_continuous_window(walk.forecast, walk.duration_h):
                    # Use the proper weather scoring algorithm to find multiple windows
                    walk.weather_score = score_forecast_period(walk.forecast, hours_ahead=72, walk_duration_hours=walk.duration_h)
                    valid_walks.append(walk)
                else:
                    logger.debug(f"Excluding {walk.name} - no continuous {walk.duration_h}h window available with weather constraints")
            else:
                # No forecast at all, exclude
                logger.debug(f"Excluding {walk.name} - no forecast data")
        
        # Simple sorting by distance from user (closest first)
        valid_walks.sort(key=lambda w: w.distance_from_center_km or 0)
        
        return valid_walks
    
    def _has_continuous_window(self, forecasts: List[HourlyForecast], duration_hours: float) -> bool:
        """Check if there's a continuous window of at least the required duration."""
        if not forecasts or duration_hours <= 0:
            return False
        
        # Convert duration to number of hours (round up to ensure we have enough time)
        duration_hours_int = int(duration_hours + 0.99)
        
        if len(forecasts) < duration_hours_int:
            return False
        
        # Slide a window of the required duration across all forecasts
        for i in range(len(forecasts) - duration_hours_int + 1):
            window_forecasts = forecasts[i:i + duration_hours_int]
            
            # Check if window spans multiple days - skip if it does (for daytime hiking)
            start_date = window_forecasts[0].time.date()
            end_date = window_forecasts[-1].time.date()
            if start_date != end_date:
                continue  # Skip windows that span midnight
            
            # Check if forecasts are continuous (within 2 hours of each other)
            is_continuous = True
            for j in range(1, len(window_forecasts)):
                time_diff = (window_forecasts[j].time - window_forecasts[j-1].time).total_seconds() / 3600
                if time_diff > 2:  # More than 2 hours gap
                    is_continuous = False
                    break
            
            if is_continuous:
                return True
        
        return False
    
    
    def _update_data_implementation(self):
        """Internal implementation of update_data - updates both walks and weather."""
        self._update_walks_implementation()
        self._update_weather_implementation()
    
    def _update_walks_implementation(self):
        """Internal implementation for updating hiking routes (one-time setup)."""
        
        logger.info("Updating hiking routes...")
        
        # Set up caching
        cache_config = get_cache_config()
        
        # Scrape walks
        session = requests_cache.CachedSession(
            cache_name=cache_config.walkhighlands_cache_name,
            backend='sqlite',
        )
        
        walks = scrape_walkhighlands(session)
        if not walks:
            raise HikeFinderError("No walks could be scraped")
        
        # Save walks to database
        db = DataBase()
        for walk in walks:
            db.add("walks", walk)
        
        db_config = get_database_config()
        walks_db_path = get_db_path(db_config.walks_db_path)
        db.save(walks_db_path)
        
        logger.info(f"Saved {len(walks)} walks to database")
    
    def _is_forecast_stale(self, max_age_hours: float = 1.0) -> bool:
        """Check if forecast data is stale (older than max_age_hours)."""
        try:
            db_config = get_database_config()
            forecasts_db_path = get_db_path(db_config.forecasts_db_path)
            
            # Check if forecasts database exists
            if not Path(forecasts_db_path).exists():
                logger.info("No forecast database found - forecasts are stale")
                return True
                
            # Connect to forecasts database and check latest update time
            with sqlite3.connect(forecasts_db_path, timeout=30.0) as conn:
                cursor = conn.execute(
                    "SELECT MAX(last_updated) FROM forecasts WHERE last_updated IS NOT NULL"
                )
                result = cursor.fetchone()
                
                if not result or not result[0]:
                    logger.info("No forecast timestamps found - forecasts are stale")
                    return True
                    
                # Parse the timestamp (assuming it's stored as ISO format string)
                latest_update_str = result[0]
                try:
                    latest_update = datetime.fromisoformat(latest_update_str.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    # Handle different timestamp formats
                    try:
                        latest_update = datetime.fromisoformat(latest_update_str)
                    except (ValueError, AttributeError):
                        logger.warning(f"Could not parse forecast timestamp: {latest_update_str}")
                        return True
                
                # Check if forecast is stale
                now = datetime.now()
                if latest_update.tzinfo:
                    # Make now timezone-aware if latest_update has timezone info
                    from zoneinfo import ZoneInfo
                    now = now.replace(tzinfo=ZoneInfo("UTC"))
                    
                age_hours = (now - latest_update).total_seconds() / 3600
                is_stale = age_hours > max_age_hours
                
                logger.info(f"Latest forecast update: {latest_update} ({age_hours:.1f}h ago), stale: {is_stale}")
                return is_stale
                
        except Exception as e:
            logger.warning(f"Error checking forecast staleness: {e} - assuming stale")
            return True
    
    def _update_weather_implementation(self):
        """Internal implementation for updating weather forecasts (regular updates)."""
        
        logger.info("Fetching latest weather forecasts (using efficient caching)...")
        
        # Set up efficient caching with conditional requests
        db_config = get_database_config()
        walks_db_path = get_db_path(db_config.walks_db_path)
        
        # Check if walks database exists
        if not Path(walks_db_path).exists():
            raise HikeFinderError(
                "No hiking routes found. Run update_walks() first to download routes."
            )
        
        # Create session and cache for weather requests
        weather_session = requests.Session()
        weather_cache = WeatherCache()
        
        forecast_db = DataBase()
        
        with sqlite3.connect(walks_db_path, timeout=30.0) as walks_db:
            # Enable WAL mode for better concurrent access
            walks_db.execute("PRAGMA journal_mode=WAL")
            walks_db.execute("PRAGMA synchronous=NORMAL")
            fetch_forecasts(walks_db, forecast_db, weather_session, weather_cache)
        
        # Save forecasts
        forecasts_db_path = get_db_path(db_config.forecasts_db_path)
        forecast_db.save(forecasts_db_path)
        
        logger.info("Weather forecasts updated successfully")
    
    def _ensure_data_exists(self):
        """Check if required databases exist."""
        
        db_config = get_database_config()
        walks_db_path = Path(get_db_path(db_config.walks_db_path))
        forecasts_db_path = Path(get_db_path(db_config.forecasts_db_path))
        
        if not walks_db_path.exists():
            raise HikeFinderError(
                "No hiking data found. Run update_walks() first to download routes."
            )
        
        if not forecasts_db_path.exists():
            raise HikeFinderError(
                "No weather data found. Run update_weather() first to download forecasts."
            )


    def find(
        self,
        latitude: Annotated[float, typer.Option("--latitude", "--lat", help="Your latitude")],
        longitude: Annotated[float, typer.Option("--longitude", "--lon", help="Your longitude")],
        radius: Annotated[float, typer.Option(help="Search radius in km")] = 25.0,
        limit: Annotated[int, typer.Option(help="Maximum number of results")] = 10,
    ):
        """Find good hikes near your location."""
        try:
            hikes = self.find_hikes(latitude, longitude, radius, limit)
            
            if not hikes:
                print("No hikes found in this area.")
                return
            
            print(f"\nFound {len(hikes)} good hikes:")
            for i, hike in enumerate(hikes, 1):
                print(f"\n{i}. {hike.name}")
                print(f"   Distance: {hike.distance_km}km, Duration: {hike.duration_hours}h")
                print(f"   {hike.distance_from_you_km}km from you")
                print(f"   Weather: {hike.weather_score:.0f}/100 - {hike.weather_summary}")
                print(f"   URL: {hike.url}")
                
        except HikeFinderError as e:
            print(f"Error: {e}")
            if "No hiking data found" in str(e):
                print("Try running: python -m hike_finder update")
            raise typer.Exit(1)

    def update(self):
        """Download and update hiking routes and weather data."""
        try:
            print("Updating hiking and weather data...")
            print("This may take several minutes on first run...")
            
            self.update_data()
            
            print("✅ Data updated successfully!")
            print("You can now search for hikes.")
            
        except HikeFinderError as e:
            print(f"Error updating data: {e}")
            raise typer.Exit(1)


class HikeFinderError(Exception):
    """Error from HikeFinder operations."""
    pass


if __name__ == "__main__":
    HikeFinder().app()