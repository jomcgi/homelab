# Static Find Good Hikes

A purely static website that helps hikers find routes with good weather conditions. This is a simplified rewrite of the original Kubernetes-based service, eliminating all server-side dependencies.

## Architecture

- **Static Site**: Pure HTML/CSS/JavaScript with client-side filtering
- **Cloudflare Pages**: Hosts the website with global CDN
- **Cloudflare R2**: Stores weather data bundles (updated as needed)
- **Two-Stage Process**: One-time scraping + periodic weather updates
- **No Server Required**: Everything served from CDN edge locations
- **Fast & Scalable**: All computation done at build time

## How It Works

1. **Initial Setup** (One-time data collection):
   - `scrape_walkhighlands/scrape.py` scrapes walk data from WalkHighlands.co.uk
   - Creates SQLite database (`walks.db`) with routes, distances, and coordinates
   - Includes robust error handling and retry logic for reliability

2. **Regular Updates** (Weather data refresh):
   - `update_forecast/generate_bundle_direct.py` runs periodically
   - Fetches 7-day weather forecasts from met.no API for each walk location
   - Filters out extreme weather (>2mm rain, >80km/h wind)
   - Creates optimized Brotli-compressed bundle and uploads to R2

3. **Client-Side Experience** (Static website):
   - Loads single bundled file with all walk + weather data
   - Calculates distances using haversine formula
   - Filters weather windows by user preferences
   - Shows results instantly (no additional requests)

## Project Structure

```
scrape_walkhighlands/           # One-time data collection for walks.db
update_forecast/                # Regular weather data updates
public/                         # Static website files
```


## Features

- **Location-based search**: Find hikes within a specified radius
- **Hike filtering**: Duration, distance, ascent preferences  
- **Weather filtering**: Temperature, rain, wind constraints
- **Date/time selection**: Choose available days and time windows

## Performance

- Bundle file: ~350KB Brotli-compressed (contains all 1,620 walks + weather)
- Uncompressed size: ~2MB
- Initial load: <0.5 seconds (single request)
- Search results: Instant (all data in memory)

## Weather Data

- **Source**: Norwegian Meteorological Institute (met.no)
- **Coverage**: 7-day forecast, hourly granularity
- **Updates**: Every 30m via GitHub Actions
- **Viability**: Excludes >2mm rain or >80km/h wind

## Future Enhancements

- Geocoding for location search
- Prefetching nearby walks
- Progressive Web App features
- Additional data sources (AllTrails, etc.)
- Weather window grouping optimizations