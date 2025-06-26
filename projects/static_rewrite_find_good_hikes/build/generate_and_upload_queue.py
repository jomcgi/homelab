#!/usr/bin/env python3
"""Generate and upload static JSON assets using a producer-consumer queue pattern."""

import json
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import os
from queue import Queue
import threading

import requests
from pydantic import BaseModel
from dateutil import parser as date_parser
import pytz
import boto3
from botocore.config import Config

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


class CompactWalkAsset(BaseModel):
    """Compact walk asset for smaller file size."""
    n: str  # name
    u: str  # url
    s: str  # summary
    w: List[List[Any]]  # windows as arrays [timestamp, temp, precip, wind, cloud]


def create_compact_windows(windows: List[WeatherWindow]) -> List[List[Any]]:
    """Convert weather windows to compact array format."""
    compact_windows = []
    
    for window in windows:
        # Parse start time
        start_dt = date_parser.parse(window.start)
        
        # Convert to Unix timestamp (seconds since epoch)
        timestamp = int(start_dt.timestamp())
        
        # Format: [timestamp, temp, precip, wind, cloud]
        compact_window = [
            timestamp,
            round(window.weather['temp_c'], 1),
            round(window.weather['precip_mm'], 1) if window.weather['precip_mm'] > 0 else 0,
            round(window.weather['wind_kmh']),  # Round to nearest km/h
            int(window.weather['cloud_pct'])
        ]
        compact_windows.append(compact_window)
    
    return compact_windows


class ProcessedWalk:
    """Container for processed walk data ready for upload."""
    def __init__(self, walk: Walk, windows: List[WeatherWindow]):
        self.walk = walk
        self.windows = windows
        # Use compact format for smaller file size
        self.walk_asset = CompactWalkAsset(
            n=walk.name,
            u=walk.url,
            s=walk.summary,
            w=create_compact_windows(windows)
        )


class S3Uploader:
    """Handles S3/R2 uploads with connection pooling."""
    
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            endpoint_url=R2_ENDPOINT,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            config=Config(
                signature_version='s3v4',
                max_pool_connections=100,  # High connection pool for uploaders
                retries={'max_attempts': 2},
                read_timeout=10,
                connect_timeout=10
            )
        )
        self.bucket_name = R2_BUCKET_NAME
        
    def upload_json(self, key: str, data: Any) -> bool:
        """Upload JSON data to S3/R2."""
        try:
            json_content = json.dumps(
                data.model_dump() if isinstance(data, BaseModel) else data,
                separators=(',', ':')  # No spaces for compact JSON
            )
            
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=json_content,
                ContentType='application/json',
                CacheControl='public, max-age=1800'  # 30 minute cache
            )
            return True
        except Exception as e:
            logger.error(f"Failed to upload {key}: {e}")
            return False


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


def weather_producer(walks: List[Walk], result_queue: Queue, stats: Dict):
    """Producer: Fetch weather data at controlled rate."""
    logger.info(f"Weather producer starting for {len(walks)} walks")
    
    # Use ThreadPoolExecutor for parallel weather fetching
    # Limit to 20 requests/second as per Met.no guidelines
    max_workers = 20
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit walks in batches to control rate
        future_to_walk = {}
        
        for i, walk in enumerate(walks):
            # Submit walk for processing
            future = executor.submit(generate_viable_windows, walk)
            future_to_walk[future] = walk
            
            # Log progress
            if (i + 1) % 100 == 0:
                logger.info(f"Submitted {i + 1}/{len(walks)} walks for weather fetching")
        
        # Process completed weather fetches
        for future in as_completed(future_to_walk):
            walk = future_to_walk[future]
            
            try:
                windows = future.result()
                stats['weather_fetched'] += 1
                
                # Only queue walks with viable windows
                if windows:
                    processed_walk = ProcessedWalk(walk, windows)
                    result_queue.put(processed_walk)
                    stats['walks_with_windows'] += 1
                    stats['total_windows'] += len(windows)
                    
            except Exception as e:
                logger.error(f"Failed to process walk {walk.name}: {e}")
                stats['weather_failed'] += 1
    
    # Signal completion
    result_queue.put(None)
    logger.info("Weather producer completed")


def upload_consumer(result_queue: Queue, uploader: S3Uploader, stats: Dict, num_consumers: int = 1):
    """Consumer: Upload processed walks to R2."""
    consumer_id = threading.current_thread().name
    logger.info(f"Upload consumer {consumer_id} starting")
    
    none_count = 0
    
    while True:
        try:
            # Get processed walk from queue
            processed_walk = result_queue.get(timeout=30)
            
            if processed_walk is None:
                none_count += 1
                if none_count >= num_consumers:
                    # All producers done, put None back for other consumers
                    result_queue.put(None)
                    break
                continue
                
            # Upload to R2
            key = f"walks/{processed_walk.walk.uuid}.json"
            if uploader.upload_json(key, processed_walk.walk_asset):
                stats['successful_uploads'] += 1
            else:
                stats['failed_uploads'] += 1
                
            # Mark task as done
            result_queue.task_done()
            
        except Queue.Empty:
            logger.warning(f"Consumer {consumer_id} timed out waiting for work")
            break
        except Exception as e:
            logger.error(f"Consumer {consumer_id} error: {e}")
            stats['failed_uploads'] += 1
    
    logger.info(f"Upload consumer {consumer_id} completed")


def delete_orphaned_files(uploader: S3Uploader, valid_uuids: set):
    """Delete files in R2 that are no longer in the database."""
    try:
        # List all objects in the walks/ prefix
        paginator = uploader.s3_client.get_paginator('list_objects_v2')
        pages = paginator.paginate(Bucket=uploader.bucket_name, Prefix='walks/')
        
        files_to_delete = []
        
        for page in pages:
            if 'Contents' not in page:
                continue
                
            for obj in page['Contents']:
                key = obj['Key']
                # Extract UUID from filename (walks/uuid.json)
                if key.startswith('walks/') and key.endswith('.json'):
                    uuid = key[6:-5]  # Remove 'walks/' and '.json'
                    if uuid not in valid_uuids:
                        files_to_delete.append({'Key': key})
        
        # Delete orphaned files in batches
        if files_to_delete:
            logger.info(f"Deleting {len(files_to_delete)} orphaned files from R2")
            
            # S3 delete_objects has a limit of 1000 keys per request
            for i in range(0, len(files_to_delete), 1000):
                batch = files_to_delete[i:i+1000]
                uploader.s3_client.delete_objects(
                    Bucket=uploader.bucket_name,
                    Delete={'Objects': batch}
                )
                
            logger.info(f"Deleted {len(files_to_delete)} orphaned files")
            
    except Exception as e:
        logger.error(f"Failed to delete orphaned files: {e}")


def main():
    """Main producer-consumer pipeline process."""
    logger.info("Starting producer-consumer pipeline for data generation and upload...")
    
    try:
        # Initialize uploader
        uploader = S3Uploader()
        
        # Load walks from database
        walks = load_walks_from_db()
        valid_uuids = {walk.uuid for walk in walks}
        
        # Generate and upload index
        logger.info("Generating and uploading index.json...")
        index_data = generate_index_json(walks)
        if not uploader.upload_json("index.json", index_data):
            logger.error("Failed to upload index.json")
            sys.exit(1)
        
        # Initialize statistics
        stats = {
            'weather_fetched': 0,
            'weather_failed': 0,
            'walks_with_windows': 0,
            'total_windows': 0,
            'successful_uploads': 0,
            'failed_uploads': 0
        }
        
        # Create queue for processed walks
        result_queue = Queue(maxsize=200)  # Buffer size
        
        # Start timer
        start_time = time.time()
        
        # Start upload consumers (many consumers for fast uploads)
        num_consumers = 50  # High parallelism for R2 uploads
        consumers = []
        
        logger.info(f"Starting {num_consumers} upload consumers...")
        for i in range(num_consumers):
            consumer = threading.Thread(
                target=upload_consumer,
                args=(result_queue, uploader, stats, num_consumers),
                name=f"Consumer-{i+1}"
            )
            consumer.start()
            consumers.append(consumer)
        
        # Start weather producer (rate-limited to 20/sec)
        logger.info("Starting weather producer...")
        producer = threading.Thread(
            target=weather_producer,
            args=(walks, result_queue, stats),
            name="Producer"
        )
        producer.start()
        
        # Monitor progress
        last_log_time = time.time()
        while producer.is_alive() or not result_queue.empty():
            current_time = time.time()
            if current_time - last_log_time >= 5:  # Log every 5 seconds
                elapsed = current_time - start_time
                rate = stats['weather_fetched'] / elapsed if elapsed > 0 else 0
                logger.info(
                    f"Progress: {stats['weather_fetched']}/{len(walks)} weather fetched "
                    f"({rate:.1f}/sec), {stats['successful_uploads']} uploaded, "
                    f"queue size: {result_queue.qsize()}"
                )
                last_log_time = current_time
            time.sleep(0.5)
        
        # Wait for all threads to complete
        producer.join()
        for consumer in consumers:
            consumer.join()
        
        # Clean up orphaned files
        logger.info("Cleaning up orphaned files in R2...")
        delete_orphaned_files(uploader, valid_uuids)
        
        # Final statistics
        elapsed_total = time.time() - start_time
        logger.info(f"Pipeline complete in {elapsed_total:.1f} seconds!")
        logger.info(f"- Total walks: {len(walks)}")
        logger.info(f"- Weather fetched: {stats['weather_fetched']}")
        logger.info(f"- Weather failed: {stats['weather_failed']}")
        logger.info(f"- Walks with viable windows: {stats['walks_with_windows']}")
        logger.info(f"- Total viable windows: {stats['total_windows']}")
        logger.info(f"- Successful uploads: {stats['successful_uploads']}")
        logger.info(f"- Failed uploads: {stats['failed_uploads']}")
        logger.info(f"- Average processing rate: {len(walks)/elapsed_total:.1f} walks/sec")
        
        if stats['failed_uploads'] > 0 or stats['weather_failed'] > 0:
            logger.warning(f"Some operations failed - check logs for details")
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()