#!/usr/bin/env python3
"""Generate static JSON assets for Find Good Hikes."""

import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

import requests
from pydantic import BaseModel
from dateutil import parser as date_parser
import pytz

# Add the original project to path to reuse some modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "cluster/services/find-good-hikes/app"))

from config import *

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Walk(BaseModel):
    """Walk data model."""
    uuid: str
    name: str
    url: str
    distance_km: float
    ascent_m: int
    duration_h: float
    summary: str
    latitude: float
    longitude: float


class WeatherWindow(BaseModel):
    """Viable weather window."""
    start: str  # ISO format timestamp
    end: str    # ISO format timestamp
    weather: Dict[str, float]  # temp_c, precip_mm, wind_kmh, cloud_pct


class WalkAsset(BaseModel):
    """Individual walk asset data."""
    name: str
    url: str
    summary: str
    windows: List[WeatherWindow]


def load_walks_from_db() -> List[Walk]:
    """Load all walks from the original SQLite database."""
    walks = []
    
    try:
        with sqlite3.connect(WALKS_DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT uuid, name, url, distance_km, ascent_m, 
                       duration_h, summary, latitude, longitude 
                FROM walks
            """)
            
            for row in cursor.fetchall():
                walk = Walk(
                    uuid=row['uuid'],
                    name=row['name'],
                    url=row['url'],
                    distance_km=row['distance_km'],
                    ascent_m=row['ascent_m'],
                    duration_h=row['duration_h'],
                    summary=row['summary'],
                    latitude=row['latitude'],
                    longitude=row['longitude']
                )
                walks.append(walk)
                
        logger.info(f"Loaded {len(walks)} walks from database")
        return walks
        
    except Exception as e:
        logger.error(f"Failed to load walks from database: {e}")
        raise


def fetch_weather_forecast(lat: float, lon: float) -> Optional[Dict[str, Any]]:
    """Fetch weather forecast for a location."""
    headers = {'User-Agent': USER_AGENT}
    params = {'lat': lat, 'lon': lon}
    
    try:
        response = requests.get(
            MET_NO_API_URL,
            params=params,
            headers=headers,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch weather for ({lat}, {lon}): {e}")
        return None


def parse_weather_data(forecast_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Parse met.no forecast data into hourly windows."""
    if not forecast_data or 'properties' not in forecast_data:
        return []
        
    timeseries = forecast_data['properties']['timeseries']
    hourly_data = []
    
    for entry in timeseries:
        time_str = entry['time']
        data = entry['data']
        instant = data.get('instant', {}).get('details', {})
        next_1_hours = data.get('next_1_hours', {})
        
        # Skip if no hourly data
        if not next_1_hours:
            continue
            
        hourly_data.append({
            'time': time_str,
            'temp_c': instant.get('air_temperature'),
            'wind_speed_ms': instant.get('wind_speed'),
            'cloud_fraction': instant.get('cloud_area_fraction'),
            'precipitation_mm': next_1_hours.get('details', {}).get('precipitation_amount', 0),
        })
        
    return hourly_data


def is_weather_viable(weather: Dict[str, Any]) -> bool:
    """Check if weather conditions are viable for hiking."""
    precip = weather.get('precipitation_mm', 0)
    wind_ms = weather.get('wind_speed_ms', 0)
    
    # Convert m/s to km/h
    wind_kmh = wind_ms * 3.6 if wind_ms is not None else 0
    
    # Apply viability thresholds
    if precip > MAX_PRECIPITATION_MM:
        return False
    if wind_kmh > MAX_WIND_SPEED_KMH:
        return False
        
    return True


def is_daylight_hour(time_str: str, lat: float, lon: float) -> bool:
    """Check if the given time is during daylight hours."""
    # Simple approximation: assume daylight from 7 AM to 7 PM
    # In production, we'd use sunrise/sunset calculations
    dt = date_parser.parse(time_str)
    local_hour = dt.hour
    
    # Basic daylight check (can be improved with actual sunrise/sunset)
    return 7 <= local_hour <= 19


def generate_viable_windows(walk: Walk) -> List[WeatherWindow]:
    """Generate viable weather windows for a walk."""
    windows = []
    
    # Fetch weather forecast
    forecast_data = fetch_weather_forecast(walk.latitude, walk.longitude)
    if not forecast_data:
        return windows
        
    # Parse hourly data
    hourly_data = parse_weather_data(forecast_data)
    
    # Current time for filtering expired windows
    now = datetime.now(timezone.utc)
    
    for weather in hourly_data:
        time_str = weather['time']
        dt = date_parser.parse(time_str)
        
        # Skip past times
        if dt < now:
            continue
            
        # Skip if beyond forecast horizon
        if dt > now + timedelta(days=FORECAST_DAYS):
            continue
            
        # Skip night hours
        if not is_daylight_hour(time_str, walk.latitude, walk.longitude):
            continue
            
        # Skip non-viable weather
        if not is_weather_viable(weather):
            continue
            
        # Create weather window (1 hour duration)
        window = WeatherWindow(
            start=dt.isoformat(),
            end=(dt + timedelta(hours=1)).isoformat(),
            weather={
                'temp_c': weather.get('temp_c', 0),
                'precip_mm': weather.get('precipitation_mm', 0),
                'wind_kmh': weather.get('wind_speed_ms', 0) * 3.6 if weather.get('wind_speed_ms') else 0,
                'cloud_pct': round(weather.get('cloud_fraction', 0), 1) if weather.get('cloud_fraction') else 0
            }
        )
        windows.append(window)
        
    return windows


def generate_index_json(walks: List[Walk]) -> Dict[str, Any]:
    """Generate the index.json with filterable walk properties."""
    index_data = {
        'generated_at': datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT),
        'walks': []
    }
    
    for walk in walks:
        index_data['walks'].append({
            'id': walk.uuid,
            'lat': round(walk.latitude, 4),
            'lng': round(walk.longitude, 4),
            'duration_h': walk.duration_h,
            'distance_km': walk.distance_km,
            'ascent_m': walk.ascent_m
        })
        
    return index_data


def generate_walk_asset(walk: Walk, windows: List[WeatherWindow]) -> WalkAsset:
    """Generate individual walk asset data."""
    return WalkAsset(
        name=walk.name,
        url=walk.url,
        summary=walk.summary,
        windows=windows
    )


def save_json_file(path: Path, data: Any) -> None:
    """Save data as JSON file."""
    with open(path, 'w', encoding='utf-8') as f:
        if isinstance(data, BaseModel):
            json.dump(data.model_dump(), f, indent=2)
        else:
            json.dump(data, f, indent=2)
    logger.info(f"Saved {path}")


def main():
    """Main data generation process."""
    logger.info("Starting static data generation...")
    
    try:
        # Load walks from database
        walks = load_walks_from_db()
        
        # Generate index
        index_data = generate_index_json(walks)
        save_json_file(INDEX_FILE, index_data)
        
        # Process each walk
        total_windows = 0
        walks_with_windows = 0
        
        for i, walk in enumerate(walks):
            if (i + 1) % 100 == 0:
                logger.info(f"Processing walk {i + 1}/{len(walks)}...")
                
            # Generate viable windows
            windows = generate_viable_windows(walk)
            
            # Only save if there are viable windows
            if windows:
                walk_asset = generate_walk_asset(walk, windows)
                walk_file = WALKS_DIR / f"{walk.uuid}.json"
                save_json_file(walk_file, walk_asset)
                
                total_windows += len(windows)
                walks_with_windows += 1
            
        logger.info(f"Generation complete!")
        logger.info(f"- Total walks: {len(walks)}")
        logger.info(f"- Walks with viable windows: {walks_with_windows}")
        logger.info(f"- Total viable windows: {total_windows}")
        
    except Exception as e:
        logger.error(f"Data generation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()