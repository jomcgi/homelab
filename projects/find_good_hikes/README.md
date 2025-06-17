# Find Good Hikes - Production Ready

**Find hiking routes within X kilometers of your location where the weather will be good in the next 3-5 days.**

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Update all data (scrape walks + fetch weather)
python main.py update

# Find walks near Glasgow
python main.py find 55.8827 -4.2589

# Find walks with custom options
python main.py find 55.8827 -4.2589 --radius 50 --show-weather --limit 5
```

## Commands

### `update`
Updates both walk data and weather forecasts:
```bash
python main.py update
```

### `scrape`
Scrapes walking routes from walkhighlands.co.uk:
```bash
python main.py scrape
```

### `fetch-weather`
Fetches weather forecasts for all walks:
```bash
python main.py fetch-weather
```

### `find`
Finds good walks near a location with weather ranking:
```bash
# Basic usage
python main.py find <latitude> <longitude>

# With options
python main.py find 55.8827 -4.2589 \
  --radius 50 \
  --hours-ahead 72 \
  --limit 10 \
  --show-weather \
  --show-summary
```

## Configuration

Configuration is handled through environment variables:

```bash
# Database locations
export WALKS_DB_PATH="data/walks.db"
export FORECASTS_DB_PATH="data/forecasts.sqlite.db"
export DATA_DIR="./data"

# Logging
export LOG_LEVEL="DEBUG"
export LOG_FILE="hiking.log"

# Cache settings
export WEATHER_CACHE_EXPIRE_HOURS=2

# Search defaults
export DEFAULT_SEARCH_RADIUS_KM=30
export DEFAULT_HOURS_AHEAD=48
```

## Weather Scoring

Walks are automatically ranked by weather quality using a sophisticated scoring algorithm that considers:

- **Precipitation** (35% weight): Rain ruins hiking
- **Temperature** (25% weight): Optimal range 10-20°C  
- **Wind** (20% weight): Strong winds dangerous on ridges
- **Weather symbols** (15% weight): Overall conditions
- **Cloud cover** (5% weight): Affects visibility and photos

Weather scores range from 0-100, with higher scores indicating better hiking conditions.

## Production Features

✅ **Proper Logging**: INFO for operations, DEBUG for troubleshooting
✅ **Configuration Management**: Environment variable overrides
✅ **Dependency Injection**: Clean separation of concerns
✅ **Error Handling**: Graceful degradation and informative messages
✅ **Weather Scoring**: Intelligent ranking of walks by conditions
✅ **CLI Interface**: Production-ready command-line interface
✅ **Caching**: Efficient HTTP request caching
✅ **Testing**: Integration tests for core functionality

## Example Output

```
$ python main.py find 55.8827 -4.2589 --show-weather --limit 3

INFO - Searching for walks within 25.0km of (55.8827, -4.2589)
INFO - Ranked walks by weather conditions for next 48 hours
INFO - Found 12 walks:

1. Ben Lomond (22.3km away) (Weather: 87.4/100)
   Distance: 7.5km, Ascent: 974m, Duration: 4.5h
   URL: https://www.walkhighlands.co.uk/loch-lomond/ben-lomond.shtml
   Weather: Fair weather. Perfect hiking temperature (15°C). No rain. Light breeze (12.3 km/h).

2. Conic Hill (18.7km away) (Weather: 82.1/100)
   Distance: 3.2km, Ascent: 358m, Duration: 2.0h
   URL: https://www.walkhighlands.co.uk/loch-lomond/conic-hill.shtml
   Weather: Partly cloudy. Warm but manageable (22°C). Light drizzle (0.3mm). Calm (8.1 km/h).

3. Dumgoyne (15.2km away) (Weather: 76.8/100)
   Distance: 4.8km, Ascent: 427m, Duration: 2.5h
   URL: https://www.walkhighlands.co.uk/glasgow/dumgoyne.shtml
   Weather: Cloudy. Cool but comfortable (8°C). No rain. Moderate wind (28.4 km/h).
```

## Testing

Run the integration tests:
```bash
python test_integration.py
```

## Architecture

The system follows clean architecture principles:

- **config.py**: Centralized configuration management
- **logging_config.py**: Structured logging setup
- **scrape.py**: Web scraping functionality
- **hourly_forecast.py**: Weather API integration
- **weather_scoring.py**: Intelligent weather ranking
- **find_walks.py**: Core search logic
- **main.py**: CLI interface and orchestration

## Files

- `walks.db`: SQLite database of hiking routes
- `forecasts.sqlite.db`: SQLite database of weather forecasts
- `walkhighlands_cache.sqlite`: HTTP cache for scraping
- `met_weather_cache.sqlite`: HTTP cache for weather API

## Dependencies

All dependencies are listed in `requirements.txt`. The system uses:
- **requests**: HTTP client with caching
- **beautifulsoup4**: HTML parsing for scraping
- **pydantic**: Data validation and models
- **haversine**: Geographic distance calculations
- **sunrisesunset**: Day/night detection

## Environment Variables

See `config.py` for all available configuration options.