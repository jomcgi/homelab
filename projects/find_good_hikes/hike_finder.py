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
from datetime import datetime
from zoneinfo import ZoneInfo
from hourly_forecast import HourlyForecast
from scrape import Walk, scrape_walkhighlands
from weather_scoring import rank_walks_by_weather
from hourly_forecast import fetch_forecasts
from pydantic_sqlite import DataBase
from config import get_cache_config, get_database_config, get_db_path
import requests_cache
import sqlite3

logger = logging.getLogger(__name__)


@dataclass
class Hike:
    """A hiking route with weather forecast."""
    name: str
    distance_km: float
    duration_hours: float
    url: str
    weather_score: float  # 0-100, higher is better
    weather_summary: str
    distance_from_you_km: float


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
        max_results: int = 10
    ) -> List[Hike]:
        """
        Find the best hiking routes near you.
        
        Args:
            latitude: Your latitude
            longitude: Your longitude  
            radius_km: Search radius in kilometers
            max_results: Maximum number of results
            
        Returns:
            List of Hike objects, sorted by weather score (best first)
            
        Raises:
            HikeFinderError: If something goes wrong
        """
        try:
            return self._find_hikes_implementation(
                latitude, longitude, radius_km, max_results
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
        self, lat: float, lon: float, radius: float, max_results: int
    ) -> List[Hike]:
        """Internal implementation of find_hikes."""
        
        # Check if data exists
        self._ensure_data_exists()
        
        # Get database paths
        db_config = get_database_config()
        walks_db_path = get_db_path(db_config.walks_db_path)
        forecasts_db_path = get_db_path(db_config.forecasts_db_path)
        
        # Find walks using our internal implementation
        with sqlite3.connect(walks_db_path) as walks_db, \
             sqlite3.connect(forecasts_db_path) as forecasts_db:
            
            walks = self._find_walks_with_weather(
                lat, lon, radius, walks_db, forecasts_db
            )
        
        # Convert to simple Hike objects
        hikes = []
        for walk in walks[:max_results]:
            hikes.append(Hike(
                name=walk.name,
                distance_km=walk.distance_km,
                duration_hours=walk.duration_h,
                url=walk.url,
                weather_score=walk.weather_score.score if walk.weather_score else 0,
                weather_summary=walk.weather_score.explanation if walk.weather_score else "No weather data",
                distance_from_you_km=walk.distance_from_center_km or 0
            ))
        
        return hikes
    
    def _find_walks_with_weather(self, lat, lon, radius, walks_db, forecasts_db):
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
                    forecasts.append(forecast)
            
            walk.forecast = forecasts
        
        # Rank by weather
        ranked_walks = rank_walks_by_weather(nearby_walks, hours_ahead=120)
        
        return ranked_walks
    
    def _update_data_implementation(self):
        """Internal implementation of update_data."""
        
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
        
        # Fetch weather forecasts
        logger.info("Fetching weather forecasts...")
        
        weather_session = requests_cache.CachedSession(
            cache_name=cache_config.weather_cache_name,
            backend='sqlite',
            expire_after=cache_config.weather_cache_expire_hours * 3600,
            allowable_methods=['GET'],
        )
        
        forecast_db = DataBase()
        
        with sqlite3.connect(walks_db_path) as walks_db:
            fetch_forecasts(walks_db, forecast_db, weather_session)
        
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
                "No hiking data found. Run update_data() first to download routes."
            )
        
        if not forecasts_db_path.exists():
            raise HikeFinderError(
                "No weather data found. Run update_data() first to download forecasts."
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