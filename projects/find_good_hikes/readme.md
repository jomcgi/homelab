# Find Good Hikes

**Find hiking routes within X kilometers of your location where the weather will be good in the next 3-5 days.**

## Problem Statement

Planning a good hike requires answering several questions:
1. **What walks are near me?** (within reasonable driving distance)
2. **What will the weather be like?** (no one wants to hike in rain)
3. **When should I go?** (finding the best weather window)

This project solves all three by combining Scottish walking route data with accurate weather forecasts to suggest the best hikes near you.

## How It Works

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│ Scrape Walk     │    │ Fetch Weather    │    │ Find Good       │
│ Data            │───▶│ Forecasts        │───▶│ Hikes           │
│ (walkhighlands) │    │ (met.no API)     │    │ (location +     │
└─────────────────┘    └──────────────────┘    │ weather filter) │
                                               └─────────────────┘
```

### Data Pipeline

1. **Walk Data Collection** (`scrape.py`)
   - Scrapes comprehensive walk information from walkhighlands.co.uk
   - Extracts: name, distance, ascent, duration, coordinates, summary
   - Stores in SQLite database (`walks.db`)

2. **Weather Forecasting** (`hourly_forecast.py`)
   - Fetches detailed weather forecasts for each walk location
   - Uses Norwegian Meteorological Institute API (met.no)
   - Includes: temperature, precipitation, wind, cloud cover, day/night
   - Stores hourly forecasts in SQLite database (`forecasts.sqlite.db`)

3. **Smart Search** (`find_walks.py`)
   - Finds walks within specified radius using haversine distance calculation
   - Filters weather forecasts for next 3-5 days, daylight hours only
   - Returns ranked results with weather outlook

## Usage

```python
from find_walks import find_walks

# Find walks within 25km of Glasgow with weather forecasts
glasgow_lat = 55.8827
glasgow_lon = -4.2589
radius_km = 25

good_hikes = find_walks(
    latitude=glasgow_lat,
    longitude=glasgow_lon, 
    max_distance_km=radius_km
)

for hike in good_hikes:
    print(f"{hike.name} - {hike.distance_from_center_km}km away")
    print(f"Distance: {hike.distance_km}km, Ascent: {hike.ascent_m}m")
    
    # Check weather for next few days
    for forecast in hike.forecast[:24]:  # Next 24 hours
        temp = forecast.air_temperature
        rain = forecast.precipitation_amount or 0
        conditions = forecast.symbol_code
        print(f"  {forecast.time}: {temp}°C, {rain}mm rain, {conditions}")
```

## Architecture

### Data Storage
- **`walks.db`** - SQLite database containing walk information
- **`forecasts.sqlite.db`** - SQLite database containing weather forecasts

### Core Modules

#### `scrape.py` - Walk Data Collection
- **Purpose**: Scrape comprehensive walk data from walkhighlands.co.uk
- **Key Function**: `scrape_walkhighlands()` → `List[Walk]`
- **Data Model**:
  ```python
  class Walk(BaseModel):
      uuid: str
      name: str
      url: str
      distance_km: float
      ascent_m: int
      duration_h: float
      summary: str
      latitude: float
      longitude: float
  ```

#### `hourly_forecast.py` - Weather Intelligence
- **Purpose**: Fetch and store detailed weather forecasts
- **Key Function**: `fetch_forecasts()` - gets weather for all walk locations
- **API**: Norwegian Meteorological Institute (met.no)
- **Features**: 
  - Day/night detection using sunrise/sunset calculations
  - Comprehensive weather metrics (temp, precipitation, wind, clouds)
  - Hourly granularity for precise planning

#### `find_walks.py` - Smart Search Engine
- **Purpose**: Find optimal hikes based on location and weather
- **Key Function**: `find_walks(lat, lon, radius)` → `List[WalkSearchResult]`
- **Intelligence**:
  - Haversine distance calculation for accurate geographic search
  - Weather filtering (daylight hours only, next 3-5 days)
  - Combined location + weather ranking

### Data Flow

```
1. scrape.py          → walks.db
2. hourly_forecast.py → forecasts.sqlite.db  
3. find_walks.py      → reads both DBs → smart recommendations
```

## Design Principles

### Simplicity First
- **Single responsibility** per module
- **Clear data models** using Pydantic
- **SQLite storage** - no complex database setup required
- **Minimal dependencies** - requests, BeautifulSoup, basic geo libraries

### Reliable Data Sources
- **walkhighlands.co.uk** - Comprehensive Scottish walking routes
- **met.no API** - Norwegian Meteorological Institute (highly accurate)
- **Request caching** - Reduces API calls during development

### Practical Features
- **Daylight filtering** - No one wants night hiking recommendations
- **Distance-based search** - Find walks within driving distance
- **Weather-aware** - Only suggest hikes when conditions are good
- **Future-focused** - Plan for next 3-5 days, not just today

## Current State

✅ **Working:**
- Complete walk data scraping from walkhighlands.co.uk
- Weather forecast fetching and storage
- Location-based walk search with weather integration
- Basic filtering for daylight hours

🚧 **Next Steps:**
- **Weather scoring algorithm** - Rank walks by weather quality
- **Web interface** - Simple UI for non-technical users  
- **Smart notifications** - "Great weather for hiking tomorrow!"
- **Route optimization** - Suggest multiple walks for a hiking trip
- **Caching improvements** - Better forecast update scheduling

## Example Output

```
Searching for walks within 25km of (55.8827, -4.2589)

Found 12 walks:
-----------------------
Ben Lomond (22.3 km away)
URL: https://www.walkhighlands.co.uk/loch-lomond/ben-lomond.shtml
Summary: Scotland's most southerly Munro, with excellent views...
Distance: 7.5 km, Ascent: 974 m, Duration: 4.5 hours
Coordinates: (56.1897, -4.6337)
Forecasts:
  2025-06-17 09:00: 12°C, 0mm rain, partlycloudy_day
  2025-06-17 12:00: 15°C, 0mm rain, fair_day  
  2025-06-17 15:00: 16°C, 0.1mm rain, partlycloudy_day
```

## Dependencies

```
requests>=2.31.0
requests-cache>=1.1.0
beautifulsoup4>=4.12.0
pydantic>=2.0.0
haversine>=2.8.0
sunrisesunset>=0.0.1
timelength>=1.0.0
pydantic-sqlite>=0.1.0
bng-latlon>=1.0.0
```

## Goals

The end goal is a **simple, reliable tool** that answers: 

> **"What's a good hike I can do this weekend?"**

By combining accurate location search with reliable weather forecasting, this project helps outdoor enthusiasts make better decisions about when and where to hike.

No complex interfaces, no over-engineering - just practical intelligence for better hiking decisions.