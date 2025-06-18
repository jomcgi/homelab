"""
FastAPI application for finding good hiking routes with weather.

Exposes the HikeFinder functionality as a REST API.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional
import logging
from hike_finder import HikeFinder, HikeFinderError, Hike

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Hike Finder API",
    description="Find good hiking routes with weather forecasts",
    version="1.0.0"
)

# Global instance
hike_finder = HikeFinder()


class HikeRequest(BaseModel):
    """Request model for finding hikes."""
    latitude: float = Field(..., description="Your latitude", ge=-90, le=90)
    longitude: float = Field(..., description="Your longitude", ge=-180, le=180)
    radius_km: float = Field(25.0, description="Search radius in kilometers", gt=0, le=100)
    max_results: int = Field(10, description="Maximum number of results", gt=0, le=50)


class HikeResponse(BaseModel):
    """Response model for a hike."""
    name: str
    distance_km: float
    duration_hours: float
    url: str
    weather_score: float
    weather_summary: str
    distance_from_you_km: float


class HikesResponse(BaseModel):
    """Response model for multiple hikes."""
    hikes: List[HikeResponse]
    total_found: int


class UpdateResponse(BaseModel):
    """Response model for data update operations."""
    message: str
    status: str


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/hikes/search", response_model=HikesResponse)
async def search_hikes(request: HikeRequest):
    """
    Find good hiking routes near your location.
    
    Returns a list of hikes sorted by weather score (best first).
    """
    try:
        hikes = hike_finder.find_hikes(
            latitude=request.latitude,
            longitude=request.longitude,
            radius_km=request.radius_km,
            max_results=request.max_results
        )
        
        hike_responses = [
            HikeResponse(
                name=hike.name,
                distance_km=hike.distance_km,
                duration_hours=hike.duration_hours,
                url=hike.url,
                weather_score=hike.weather_score,
                weather_summary=hike.weather_summary,
                distance_from_you_km=hike.distance_from_you_km
            )
            for hike in hikes
        ]
        
        return HikesResponse(
            hikes=hike_responses,
            total_found=len(hike_responses)
        )
        
    except HikeFinderError as e:
        logger.error(f"HikeFinder error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/data/update", response_model=UpdateResponse)
async def update_data(background_tasks: BackgroundTasks):
    """
    Update hiking routes and weather data.
    
    This operation runs in the background and may take several minutes.
    """
    def update_task():
        try:
            hike_finder.update_data()
            logger.info("Data update completed successfully")
        except Exception as e:
            logger.error(f"Background data update failed: {e}")
    
    background_tasks.add_task(update_task)
    
    return UpdateResponse(
        message="Data update started in background",
        status="accepted"
    )


@app.get("/data/status")
async def data_status():
    """
    Check if hiking and weather data is available.
    """
    try:
        # Try to find hikes at a test location to verify data exists
        hike_finder.find_hikes(55.9533, -3.1883, radius_km=1, max_results=1)
        return {"status": "ready", "message": "Data is available"}
    except HikeFinderError as e:
        if "No hiking data found" in str(e) or "No weather data found" in str(e):
            return {"status": "no_data", "message": str(e)}
        else:
            return {"status": "error", "message": str(e)}
    except Exception as e:
        logger.error(f"Data status check failed: {e}")
        return {"status": "error", "message": "Could not check data status"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)