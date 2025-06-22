#!/usr/bin/env python3
"""
Main CLI interface for the find_good_hikes project.

This provides a production-ready command-line interface for finding
hiking routes with good weather conditions.
"""

import sys
import sqlite3
from typing import Optional
import requests_cache
from pathlib import Path
import typer
from enum import Enum

from config import (
    get_database_config, get_cache_config, get_logging_config,
    get_db_path
)
from logging_config import setup_logging
from scrape import scrape_walkhighlands
from hourly_forecast import fetch_forecasts
from find_walks import find_walks
from pydantic_sqlite import DataBase

import logging

# Create the typer app
app = typer.Typer(help="Find good hiking routes with weather forecasts", rich_markup_mode="rich")

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"

def setup_logging_for_command(
    log_level: Optional[LogLevel] = None,
    log_file: Optional[Path] = None
):
    """Setup logging for CLI commands"""
    logging_config = get_logging_config()
    
    # Override logging config from command line
    level = log_level.value if log_level else logging_config.level
    file = str(log_file) if log_file else logging_config.log_file
    
    # Setup logging
    setup_logging(level=level, log_file=file)

@app.command()
def scrape(
    log_level: Optional[LogLevel] = typer.Option(None, help="Set logging level"),
    log_file: Optional[Path] = typer.Option(None, help="Log to file instead of console")
):
    """Scrape walking routes from walkhighlands.co.uk"""
    setup_logging_for_command(log_level, log_file)
    logger = logging.getLogger(__name__)
    cache_config = get_cache_config()
    
    try:
        # Create cached session for scraping with proper SQLite configuration
        session = requests_cache.CachedSession(
            cache_name=cache_config.walkhighlands_cache_name,
            backend='sqlite',
            backend_kwargs={
                'timeout': 30.0,
                'check_same_thread': False
            }
        )
        
        logger.info("Starting scrape of walkhighlands.co.uk")
        walks = scrape_walkhighlands(session)
        
        if walks:
            # Save to database
            db = DataBase()
            for walk in walks:
                db.add("walks", walk)
            
            db_path = get_db_path("walks.db")
            db.save(db_path)
            logger.info(f"Successfully scraped and saved {len(walks)} walks to {db_path}")
            raise typer.Exit(0)
        else:
            logger.error("No walks were successfully extracted")
            raise typer.Exit(1)
            
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        raise typer.Exit(1)

@app.command()
def fetch_weather(
    log_level: Optional[LogLevel] = typer.Option(None, help="Set logging level"),
    log_file: Optional[Path] = typer.Option(None, help="Log to file instead of console")
):
    """Fetch weather forecasts for all walks"""
    setup_logging_for_command(log_level, log_file)
    logger = logging.getLogger(__name__)
    db_config = get_database_config()
    cache_config = get_cache_config()
    
    try:
        # Check if walks database exists
        walks_db_path = get_db_path(db_config.walks_db_path)
        if not Path(walks_db_path).exists():
            logger.error(f"Walks database not found: {walks_db_path}")
            logger.info("Run 'python main.py scrape' first to create the walks database")
            raise typer.Exit(1)
        
        # Create cached session for weather API with proper SQLite configuration
        session = requests_cache.CachedSession(
            cache_name=cache_config.weather_cache_name,
            backend='sqlite',
            expire_after=cache_config.weather_cache_expire_hours * 3600,
            allowable_methods=['GET'],
            backend_kwargs={
                'timeout': 30.0,
                'check_same_thread': False
            }
        )
        
        # Create forecast database
        forecast_db = DataBase()
        
        logger.info("Fetching weather forecasts for all walks")
        with sqlite3.connect(walks_db_path, timeout=30.0) as walks_db:
            # Enable WAL mode for better concurrent access
            walks_db.execute("PRAGMA journal_mode=WAL")
            walks_db.execute("PRAGMA synchronous=NORMAL")
            fetch_forecasts(walks_db, forecast_db, session)
        
        # Save forecasts
        forecasts_db_path = get_db_path(db_config.forecasts_db_path)
        forecast_db.save(forecasts_db_path)
        logger.info(f"Successfully saved weather forecasts to {forecasts_db_path}")
        
    except Exception as e:
        logger.error(f"Weather fetching failed: {e}")
        raise typer.Exit(1)

@app.command()
def find(
    latitude: str = typer.Argument(help="Latitude of search center"),
    longitude: str = typer.Argument(help="Longitude of search center"),
    radius: float = typer.Option(25.0, help="Search radius in km"),
    hours_ahead: int = typer.Option(120, help="Hours ahead to consider for weather (default: 120 - 5 days)"),
    limit: int = typer.Option(10, help="Maximum number of results"),
    no_weather_ranking: bool = typer.Option(False, "--no-weather-ranking", help="Disable weather-based ranking"),
    show_weather: bool = typer.Option(False, "--show-weather", help="Show detailed weather information"),
    show_summary: bool = typer.Option(False, "--show-summary", help="Show walk summaries"),
    log_level: Optional[LogLevel] = typer.Option(None, help="Set logging level"),
    log_file: Optional[Path] = typer.Option(None, help="Log to file instead of console")
):
    """Find good walks near a location with weather forecasts
    
    Examples:
    
    • Find walks near Glasgow:
      python main.py find 55.8827 -4.2589
    
    • Find walks with custom radius and show weather details:
      python main.py find 55.8827 -4.2589 --radius 50 --show-weather
    """
    setup_logging_for_command(log_level, log_file)
    logger = logging.getLogger(__name__)
    db_config = get_database_config()
    
    try:
        # Convert string arguments to float
        lat = float(latitude)
        lon = float(longitude)
    except ValueError as e:
        logger.error(f"Invalid coordinates: {e}")
        raise typer.Exit(1)
    
    try:
        # Check if databases exist
        walks_db_path = get_db_path(db_config.walks_db_path)
        forecasts_db_path = get_db_path(db_config.forecasts_db_path)
        
        if not Path(walks_db_path).exists():
            logger.error(f"Walks database not found: {walks_db_path}")
            logger.info("Run 'python main.py scrape' first")
            raise typer.Exit(1)
            
        if not Path(forecasts_db_path).exists():
            logger.error(f"Forecasts database not found: {forecasts_db_path}")
            logger.info("Run 'python main.py fetch-weather' first")
            raise typer.Exit(1)
        
        # Find walks
        logger.info(f"Searching for walks within {radius}km of ({lat}, {lon})")
        
        with sqlite3.connect(walks_db_path, timeout=30.0) as walks_db, \
             sqlite3.connect(forecasts_db_path, timeout=30.0) as forecasts_db:
            # Enable WAL mode for better concurrent access
            walks_db.execute("PRAGMA journal_mode=WAL")
            walks_db.execute("PRAGMA synchronous=NORMAL")
            forecasts_db.execute("PRAGMA journal_mode=WAL") 
            forecasts_db.execute("PRAGMA synchronous=NORMAL")
            
            walks = find_walks(
                latitude=lat,
                longitude=lon,
                max_distance_km=radius,
                walks_db_conn=walks_db,
                forecasts_db_conn=forecasts_db,
                rank_by_weather=not no_weather_ranking,
                hours_ahead=hours_ahead,
            )
        
        if walks:
            logger.info(f"Found {len(walks)} walks:")
            for i, walk in enumerate(walks[:limit], 1):
                weather_info = ""
                if walk.weather_score:
                    weather_info = f" (Weather: {walk.weather_score.score:.1f}/100)"
                
                print(f"\n{i}. {walk.name} ({walk.distance_from_center_km}km away){weather_info}")
                print(f"   Distance: {walk.distance_km}km, Ascent: {walk.ascent_m}m, Duration: {walk.duration_h}h")
                print(f"   URL: {walk.url}")
                
                if walk.weather_score and show_weather:
                    print(f"   Weather: {walk.weather_score.explanation}")
                
                if show_summary:
                    print(f"   Summary: {walk.summary}")
            
            raise typer.Exit(0)
        else:
            logger.warning("No walks found within the specified distance")
            raise typer.Exit(1)
            
    except typer.Exit:
        # Re-raise typer exits without logging
        raise
    except Exception as e:
        logger.error(f"Search failed: {e}")
        raise typer.Exit(1)

@app.command()
def update(
    log_level: Optional[LogLevel] = typer.Option(None, help="Set logging level"),
    log_file: Optional[Path] = typer.Option(None, help="Log to file instead of console")
):
    """Update both walks and weather data"""
    setup_logging_for_command(log_level, log_file)
    logger = logging.getLogger(__name__)
    
    logger.info("Updating walks and weather data...")
    
    # First scrape walks
    try:
        scrape()
    except typer.Exit as e:
        if e.exit_code != 0:
            raise e
    
    # Then fetch weather
    try:
        fetch_weather()
    except typer.Exit as e:
        raise e

def main():
    """Main entry point"""
    app()

if __name__ == "__main__":
    main()