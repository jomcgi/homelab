# Static Find Good Hikes

A purely static website that helps hikers find routes with good weather conditions. This is a simplified rewrite of the original Kubernetes-based service, eliminating all server-side dependencies.

## Architecture

- **Static Site**: Pure HTML/CSS/JavaScript with client-side filtering
- **Cloudflare Pages**: Hosts the website with global CDN
- **Cloudflare R2**: Stores hourly-updated weather data
- **GitHub Actions**: Updates R2 with fresh data every hour
- **No Server Required**: Everything served from CDN edge locations
- **Fast & Scalable**: All computation done at build time

## How It Works

1. **Data Generation** (Python script runs hourly in CI):
   - Fetches walk data from SQLite database
   - Gets 7-day weather forecasts from met.no API
   - Filters out extreme weather (>2mm rain, >80km/h wind)
   - Generates static JSON assets

2. **Client-Side Filtering** (JavaScript in browser):
   - Loads index of all walks with filterable properties
   - Calculates distances using haversine formula
   - Fetches individual walk data for nearby hikes
   - Filters weather windows by user preferences

## Project Structure

```
build/                      # Python data generation pipeline
├── generate_and_upload_queue.py  # Producer-consumer pipeline
├── requirements.txt              # Python dependencies
└── config.py                    # Configuration settings

public/                    # Static website (deployed to GitHub Pages)
├── index.html            # Single page application
├── app.js               # Client-side filtering logic
├── style.css            # Minimal styling
└── data/                # Generated JSON assets (git-ignored locally)
    ├── index.json       # All walks with filterable properties
    └── walks/           # Individual walk data files
        └── [uuid].json  # Viable weather windows per walk

.github/workflows/
└── update-hike-data.yml  # Updates R2 with fresh data
```

## Local Development

### Testing with R2 Data

1. **Configure R2 URL**:
   ```bash
   # Copy the config template
   cp public/config.local.js public/config.js
   
   # Edit config.js and replace 'YOUR-R2-PUBLIC-URL-HERE' with your actual R2 public URL
   # You can find this in Cloudflare dashboard: R2 > your bucket > Settings > Public URL
   ```

2. **Run local server**:
   ```bash
   # Using the provided server script (includes CORS headers)
   python3 serve.py
   # Visit http://localhost:8000
   
   # Or using Python's built-in server
   cd public
   python3 -m http.server 8000
   ```

### Generate Test Data Locally (Optional)

If you want to test data generation:
```bash
cd build
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Set environment variables for R2
export CLOUDFLARE_S3_ACCESS_KEY_ID="your-key-id"
export CLOUDFLARE_S3_ACCESS_KEY_SECRET="your-secret"
export CLOUDFLARE_S3_ENDPOINT="your-endpoint"
export CLOUDFLARE_R2_PUBLIC_URL="your-public-url"

# Run the pipeline
python generate_and_upload_queue.py
```

## Deployment

The site uses Cloudflare's infrastructure for maximum performance:

1. **Website**: Deployed to Cloudflare Pages (auto-deploy on push)
2. **Data**: Updated hourly to Cloudflare R2 via GitHub Actions
3. **CDN**: Both website and data served through Cloudflare's global network

See [CLOUDFLARE_SETUP.md](CLOUDFLARE_SETUP.md) for detailed deployment instructions.

## Features

- **Location-based search**: Find hikes within a specified radius
- **Hike filtering**: Duration, distance, ascent preferences  
- **Weather filtering**: Temperature, rain, wind constraints
- **Date/time selection**: Choose available days and time windows
- **Preference storage**: Saves your settings in localStorage
- **Offline capable**: Once loaded, works without internet

## Performance

- Index file: ~300KB (all 1,620 Scottish walks)
- Individual walk files: <1KB each
- Total data size: ~2MB
- Initial load: <1 second
- Search results: Instant (all client-side)

## Weather Data

- **Source**: Norwegian Meteorological Institute (met.no)
- **Coverage**: 7-day forecast, hourly granularity
- **Updates**: Every hour via GitHub Actions
- **Viability**: Excludes >2mm rain or >80km/h wind

## Future Enhancements

- Geocoding for location search
- Prefetching nearby walks
- Progressive Web App features
- Additional data sources (AllTrails, etc.)
- Weather window grouping optimizations