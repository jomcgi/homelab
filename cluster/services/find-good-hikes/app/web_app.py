"""
Web interface for finding good hiking routes with weather forecasts.

Simple FastAPI application that provides a user-friendly interface
to the HikeFinder core functionality.
"""

import logging
from pathlib import Path
from typing import List, Optional, Annotated
from datetime import datetime, timedelta
from contextlib import asynccontextmanager
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn

from hike_finder import HikeFinder, HikeFinderError, Hike

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = AsyncIOScheduler()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    # Startup: Check and update forecasts if needed, then start scheduler
    logger.info("Starting up: Checking weather forecast freshness...")
    try:
        # Run initial forecast check/update
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, update_forecasts)
        logger.info("Initial weather forecast check completed")
        
        # Start the scheduler for hourly updates
        scheduler.add_job(
            scheduled_forecast_update,
            trigger=IntervalTrigger(hours=1),
            id="hourly_forecast_update",
            name="Update weather forecasts every hour",
            replace_existing=True
        )
        scheduler.start()
        logger.info("Scheduler started: Weather forecasts will update every hour")
        
    except Exception as e:
        logger.error(f"Failed to update forecasts on startup: {e}")
        # Don't fail startup if forecast update fails
    
    yield
    
    # Shutdown: Stop scheduler
    logger.info("Shutting down scheduler...")
    scheduler.shutdown(wait=False)

def update_forecasts():
    """Update weather forecasts synchronously, only if they're stale."""
    try:
        hike_finder = HikeFinder()
        
        # Check if forecasts are stale (older than 20 minutes)
        # This prevents unnecessary updates when container restarts shortly after CI build
        if hike_finder._is_forecast_stale(max_age_hours=20/60):  # 20 minutes in hours
            logger.info("Forecast data is stale, updating...")
            hike_finder.update_weather()
            logger.info("Forecast update completed")
        else:
            logger.info("Forecast data is recent, skipping update")
            
    except Exception as e:
        logger.error(f"Error updating forecasts: {e}")
        # Don't raise the exception - allow the app to start even if forecast update fails
        # The app can still serve requests with existing forecast data
        logger.info("Continuing startup with existing forecast data")

async def scheduled_forecast_update():
    """Async wrapper for scheduled forecast updates."""
    try:
        logger.info("Running scheduled weather forecast update...")
        loop = asyncio.get_event_loop() 
        await loop.run_in_executor(None, update_forecasts)
        logger.info("Scheduled forecast update completed successfully")
    except Exception as e:
        logger.error(f"Scheduled forecast update failed: {e}")

# Initialize FastAPI app
app = FastAPI(
    title="Good Hikes Finder",
    description="Find hiking routes with good weather conditions",
    version="1.0.0",
    lifespan=lifespan
)

# Setup templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize HikeFinder
hike_finder = HikeFinder()

# Weather score thresholds
WEATHER_THRESHOLDS = {
    'excellent': 80,
    'good': 65, 
    'ok': 50
}

def get_weather_rating(score: float) -> str:
    """Convert weather score to user-friendly rating."""
    if score >= WEATHER_THRESHOLDS['excellent']:
        return "Excellent"
    elif score >= WEATHER_THRESHOLDS['good']:
        return "Good"
    elif score >= WEATHER_THRESHOLDS['ok']:
        return "OK"
    else:
        return "Poor"

def filter_by_preferences(
    hikes: List[Hike],
    min_duration: float,
    max_duration: float,
    min_distance: float,
    max_distance: float,
    max_ascent: int,
    min_weather_score: float = 50.0
) -> List[Hike]:
    """Filter hikes by user preferences and weather quality."""
    filtered = []
    
    for hike in hikes:
        # Weather filter - only show OK or better conditions
        if hike.weather_score < min_weather_score:
            continue
            
        # Duration filter
        if not (min_duration <= hike.duration_hours <= max_duration):
            continue
            
        # Distance filter  
        if not (min_distance <= hike.distance_km <= max_distance):
            continue
            
        filtered.append(hike)
    
    return filtered

@app.get("/", response_class=HTMLResponse)
async def home(
    request: Request,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    radius: Optional[float] = None,
    min_duration: Optional[float] = None,
    max_duration: Optional[float] = None,
    min_distance: Optional[float] = None,
    max_distance: Optional[float] = None,
    max_ascent: Optional[int] = None,
    available_dates: Optional[str] = None,
    start_after: Optional[str] = None,
    finish_before: Optional[str] = None,
    max_cloud_cover_percent: Optional[float] = None,
    max_precipitation_mm: Optional[float] = None,
    max_wind_speed_kmh: Optional[float] = None,
    min_temperature_c: Optional[float] = None,
    max_temperature_c: Optional[float] = None
):
    """Display the search form with optional pre-populated values."""
    # Parse available_dates if provided
    parsed_available_dates = []
    if available_dates:
        parsed_available_dates = available_dates.split(',')
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "title": "Find Good Hikes",
        "params": {
            "latitude": latitude or 55.8827,
            "longitude": longitude or -4.2589,
            "radius": radius or 25.0,
            "min_duration": min_duration or 2.0,
            "max_duration": max_duration or 6.0,
            "min_distance": min_distance or 3.0,
            "max_distance": max_distance or 15.0,
            "max_ascent": max_ascent or 800,
            "available_dates": parsed_available_dates,
            "start_after": start_after or "08:00",
            "finish_before": finish_before or "16:00",
            "max_cloud_cover_percent": max_cloud_cover_percent,
            "max_precipitation_mm": max_precipitation_mm,
            "max_wind_speed_kmh": max_wind_speed_kmh,
            "min_temperature_c": min_temperature_c,
            "max_temperature_c": max_temperature_c
        }
    })

@app.post("/search", response_class=HTMLResponse) 
async def search_hikes(
    request: Request,
    latitude: Annotated[float, Form()],
    longitude: Annotated[float, Form()],
    radius: Annotated[float, Form()] = 25.0,
    min_duration: Annotated[float, Form()] = 2.0,
    max_duration: Annotated[float, Form()] = 6.0,
    min_distance: Annotated[float, Form()] = 3.0,
    max_distance: Annotated[float, Form()] = 15.0,
    max_ascent: Annotated[int, Form()] = 800,
    available_dates: Annotated[List[str], Form()] = [],
    start_after: Annotated[str, Form()] = "08:00",
    finish_before: Annotated[str, Form()] = "16:00",
    max_cloud_cover_percent: Annotated[Optional[str], Form()] = None,
    max_precipitation_mm: Annotated[Optional[str], Form()] = None,
    max_wind_speed_kmh: Annotated[Optional[str], Form()] = None,
    min_temperature_c: Annotated[Optional[str], Form()] = None,
    max_temperature_c: Annotated[Optional[str], Form()] = None
):
    """Search for hikes and display results."""
    try:
        # Convert empty string inputs to None and parse numbers
        def parse_optional_float(value: Optional[str]) -> Optional[float]:
            if value is None or value.strip() == "":
                return None
            try:
                return float(value)
            except ValueError:
                return None
        
        # Parse weather filter parameters
        parsed_max_cloud_cover = parse_optional_float(max_cloud_cover_percent)
        parsed_max_precipitation = parse_optional_float(max_precipitation_mm)
        parsed_max_wind_speed = parse_optional_float(max_wind_speed_kmh)
        parsed_min_temperature = parse_optional_float(min_temperature_c)
        parsed_max_temperature = parse_optional_float(max_temperature_c)
        
        # Validate coordinates
        if not (-90 <= latitude <= 90):
            raise HTTPException(status_code=400, detail="Latitude must be between -90 and 90")
        if not (-180 <= longitude <= 180):
            raise HTTPException(status_code=400, detail="Longitude must be between -180 and 180")
        
        # Validate available dates
        if not available_dates:
            raise HTTPException(status_code=400, detail="Please select at least one available date")
        
        # Validate date format and range
        today = datetime.now().date()
        max_date = today + timedelta(days=7)
        
        for date_str in available_dates:
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid date format: {date_str}")
            
            if date_obj < today:
                raise HTTPException(status_code=400, detail=f"Date cannot be in the past: {date_str}")
            
            if date_obj > max_date:
                raise HTTPException(status_code=400, detail=f"Date too far in future (max 7 days): {date_str}")
        
        # Find hikes using HikeFinder with weather filters
        all_hikes = hike_finder.find_hikes(
            latitude=latitude,
            longitude=longitude, 
            radius_km=radius,
            max_results=50,  # Get more results for filtering
            available_dates=available_dates,
            start_after=start_after,
            finish_before=finish_before,
            max_cloud_cover_percent=parsed_max_cloud_cover,
            allow_rain=True,  # Remove boolean rain control, use max_precipitation_mm instead
            max_precipitation_mm=parsed_max_precipitation,
            max_wind_speed_kmh=parsed_max_wind_speed,
            min_temperature_c=parsed_min_temperature,
            max_temperature_c=parsed_max_temperature
        )
        
        # Filter by preferences (weather filtering already done in find_hikes)
        good_hikes = filter_by_preferences(
            all_hikes,
            min_duration=min_duration,
            max_duration=max_duration,
            min_distance=min_distance,
            max_distance=max_distance,
            max_ascent=max_ascent,
            min_weather_score=0.0  # No weather score filtering needed anymore
        )
        
        # Limit final results
        good_hikes = good_hikes[:20]
        
        # Add weather ratings for display
        for hike in good_hikes:
            hike.weather_rating = get_weather_rating(hike.weather_score)
        
        return templates.TemplateResponse("results.html", {
            "request": request,
            "title": "Hiking Results",
            "hikes": good_hikes,
            "search_params": {
                "latitude": latitude,
                "longitude": longitude,
                "radius": radius,
                "min_duration": min_duration,
                "max_duration": max_duration,
                "min_distance": min_distance,
                "max_distance": max_distance,
                "max_ascent": max_ascent,
                "available_dates": available_dates,
                "start_after": start_after,
                "finish_before": finish_before,
                "max_cloud_cover_percent": parsed_max_cloud_cover,
                "max_precipitation_mm": parsed_max_precipitation,
                "max_wind_speed_kmh": parsed_max_wind_speed,
                "min_temperature_c": parsed_min_temperature,
                "max_temperature_c": parsed_max_temperature
            },
            "total_found": len(all_hikes),
            "filtered_count": len(good_hikes)
        })
        
    except HikeFinderError as e:
        logger.error(f"HikeFinder error: {e}")
        error_message = str(e)
        if "No hiking data found" in error_message:
            error_message += " Please update the data first by running: python -m hike_finder update"
        
        return templates.TemplateResponse("error.html", {
            "request": request,
            "title": "Error",
            "error": error_message
        })
    
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return templates.TemplateResponse("error.html", {
            "request": request,
            "title": "Error", 
            "error": "An unexpected error occurred. Please try again."
        })

@app.get("/viable-dates")
async def get_viable_dates(
    latitude: float,
    longitude: float,
    radius: float = 25.0
):
    """Get all dates that have viable hiking conditions."""
    try:
        viable_dates = hike_finder.get_viable_dates(latitude, longitude, radius)
        return {"viable_dates": viable_dates}
    except Exception as e:
        logger.error(f"Error getting viable dates: {e}")
        return {"error": str(e), "viable_dates": []}

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

def create_directories():
    """Create required directories for templates and static files."""
    Path("templates").mkdir(exist_ok=True)
    Path("static").mkdir(exist_ok=True)

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    # Configure uvicorn logging to reduce noise
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    
    # Create directories
    create_directories()
    
    # Run the application
    uvicorn.run(
        "web_app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        access_log=False
    )