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
   - `../../services/hikes/scrape_walkhighlands/scrape.py` scrapes walk data from WalkHighlands.co.uk
   - Creates SQLite database (`walks.db`) with routes, distances, and coordinates
   - Includes robust error handling and retry logic for reliability

2. **Regular Updates** (Weather data refresh):
   - `../../services/hikes/update_forecast/generate_bundle_direct.py` runs periodically
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
../../services/hikes/
├── scrape_walkhighlands/       # One-time data collection for walks.db
└── update_forecast/            # Regular weather data updates

./
├── public/                     # Static website files
└── tests/                      # Playwright tests
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
- **Updates**: Periodic (as needed)
- **Viability**: Excludes >2mm rain or >80km/h wind

## Testing & CI/CD

A comprehensive Playwright test framework validates the static site's critical user interactions and edge cases that could break the hiking search experience. The project uses GitHub Actions for automated testing and deployment.

### Automated Testing Pipeline
- **CI Integration**: Tests run automatically on every push and pull request
- **Quality Gates**: Deployment only happens after all tests pass
- **Fast Feedback**: Developers get immediate notification if changes break functionality
- **Test Reports**: Detailed reports uploaded for debugging failed tests

### Test Coverage
- **App Functionality**: Form validation, user interactions, error handling
- **Geolocation Integration**: Browser location services, permission handling, graceful fallbacks
- **Search Logic**: Coordinate input, distance calculations, weather filtering with realistic data
- **Weather Window Logic**: Ensures consecutive weather windows match hike duration requirements
- **Deployment Health**: Critical asset loading, console error monitoring, basic functionality checks

### Running Tests Locally
```bash
npm test              # Run all tests
npm run test:headed   # Run with visible browser
npm run test:debug    # Debug mode
```

See [CI/CD Documentation](docs/ci-deployment.md) for setup details.

## Project ToDo:

- Geocoding for location search
- Additional data sources (AllTrails, etc.)
- Enhanced UX: When hikes aren't recommended due to weather, show reason ("Only 2 hours of good weather for this 4-hour hike")
- Smart suggestions: Recommend alternative time windows or shorter hikes when weather doesn't match
