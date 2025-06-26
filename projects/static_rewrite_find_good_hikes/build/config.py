"""Configuration for static data generation."""

import os
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
BUILD_DIR = PROJECT_ROOT / "build"
PUBLIC_DIR = PROJECT_ROOT / "public"
DATA_DIR = BUILD_DIR / "dist"  # Local output directory for R2 upload

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)

# R2 Configuration (from environment variables)
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "jomcgi-hikes")
R2_ACCESS_KEY_ID = os.getenv("CLOUDFLARE_S3_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("CLOUDFLARE_S3_ACCESS_KEY_SECRET")
R2_ENDPOINT = os.getenv("CLOUDFLARE_S3_ENDPOINT")
R2_PUBLIC_URL = os.getenv("CLOUDFLARE_R2_PUBLIC_URL", "https://hike-assets.jomcgi.dev")

# Weather API
MET_NO_API_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
USER_AGENT = "find-good-hikes-static/1.0 (https://github.com/yourusername/homelab)"

# Weather viability thresholds
MAX_PRECIPITATION_MM = 2.0  # Exclude if more than 2mm rain
MAX_WIND_SPEED_KMH = 80.0   # Exclude if wind > 80 km/h

# Forecast settings
FORECAST_DAYS = 7
HOURS_PER_DAY = 24

# Data source paths (reuse from original project)
# Try to find the walks.db relative to the repo root
REPO_ROOT = Path(__file__).parent.parent.parent.parent  # Navigate up to homelab root
ORIGINAL_PROJECT = REPO_ROOT / "cluster/services/find-good-hikes/app"
WALKS_DB_PATH = ORIGINAL_PROJECT / "walks.db"

# Fallback to absolute path if relative path doesn't work
if not WALKS_DB_PATH.exists():
    WALKS_DB_PATH = Path("/workspaces/homelab/cluster/services/find-good-hikes/app/walks.db")

# Output settings
INDEX_FILE = DATA_DIR / "index.json"
WALKS_DIR = DATA_DIR / "walks"
WALKS_DIR.mkdir(parents=True, exist_ok=True)
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"