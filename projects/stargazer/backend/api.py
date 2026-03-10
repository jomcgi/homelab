"""Simple HTTP API server for Stargazer data."""

import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))


class StargazerAPIHandler(BaseHTTPRequestHandler):
    """HTTP handler for Stargazer API endpoints."""

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/health":
            self.send_health_check()
        elif self.path == "/api/locations":
            self.send_locations()
        elif self.path == "/api/best":
            self.send_best_locations()
        elif self.path == "/":
            self.send_index()
        else:
            self.send_404()

    def send_health_check(self):
        """Send health check response."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        status = {
            "status": "healthy",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.wfile.write(json.dumps(status).encode())

    def send_locations(self):
        """Send all scored locations."""
        try:
            scored_file = DATA_DIR / "output" / "forecasts_scored.json"
            if not scored_file.exists():
                logger.warning(f"Scored forecasts not found at {scored_file}")
                self.send_empty_response()
                return

            with open(scored_file) as f:
                data = json.load(f)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

        except Exception as e:
            logger.error(f"Error reading locations: {e}")
            self.send_error(500, str(e))

    def send_best_locations(self):
        """Send best locations for stargazing."""
        try:
            best_file = DATA_DIR / "output" / "best_locations.json"
            if not best_file.exists():
                logger.warning(f"Best locations not found at {best_file}")
                # Try to use scored data as fallback
                scored_file = DATA_DIR / "output" / "forecasts_scored.json"
                if scored_file.exists():
                    with open(scored_file) as f:
                        data = json.load(f)
                    # Return top 20 locations
                    if isinstance(data, list):
                        data = data[:20]
                else:
                    self.send_empty_response()
                    return
            else:
                with open(best_file) as f:
                    data = json.load(f)

            # Transform data for frontend consumption
            transformed = []
            for location in data if isinstance(data, list) else [data]:
                # Extract best hour for display
                best_hour = None
                if "best_hours" in location and location["best_hours"]:
                    best_hour = location["best_hours"][0]
                elif "hours" in location and location["hours"]:
                    # Find best scoring hour
                    best_hour = max(location["hours"], key=lambda h: h.get("score", 0))

                transformed.append(
                    {
                        "id": location.get(
                            "id",
                            f"loc_{location.get('lat', 0)}_{location.get('lon', 0)}",
                        ),
                        "name": location.get(
                            "name",
                            f"Location {location.get('lat', 0):.2f}, {location.get('lon', 0):.2f}",
                        ),
                        "lat": location.get("coordinates", {}).get("lat")
                        or location.get("lat", 0),
                        "lon": location.get("coordinates", {}).get("lon")
                        or location.get("lon", 0),
                        "altitude_m": location.get("altitude_m", 0),
                        "lp_zone": location.get("lp_zone", "unknown"),
                        "score": best_hour.get("score", 0) if best_hour else 0,
                        "cloud_cover": best_hour.get("cloud_area_fraction", 0)
                        if best_hour
                        else 100,
                        "humidity": best_hour.get("relative_humidity", 0)
                        if best_hour
                        else 100,
                        "wind_speed": best_hour.get("wind_speed", 0)
                        if best_hour
                        else 0,
                        "next_clear": best_hour.get("time", "Unknown")
                        if best_hour
                        else "Unknown",
                        "moon_phase": "New Moon",  # TODO: Calculate actual moon phase
                        "best_hours": location.get("best_hours", [])[
                            :5
                        ],  # Limit to 5 best hours
                    }
                )

            # Get file modification time for Last-Modified header
            file_mtime = datetime.fromtimestamp(
                best_file.stat().st_mtime, tz=timezone.utc
            )

            # Next update expected 30 minutes after last modification
            next_update = file_mtime.timestamp() + 1800  # 30 minutes
            now = datetime.now(timezone.utc).timestamp()
            max_age = max(60, int(next_update - now))  # At least 60 seconds

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header(
                "Access-Control-Expose-Headers", "X-Next-Update, Last-Modified"
            )
            self.send_header(
                "Last-Modified", file_mtime.strftime("%a, %d %b %Y %H:%M:%S GMT")
            )
            self.send_header(
                "X-Next-Update", str(int(next_update * 1000))
            )  # Unix ms for JS
            self.send_header("Cache-Control", f"public, max-age={max_age}")
            self.end_headers()
            self.wfile.write(json.dumps(transformed).encode())

        except Exception as e:
            logger.error(f"Error reading best locations: {e}")
            self.send_error(500, str(e))

    def send_empty_response(self):
        """Send empty but valid response when no data available."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Send sample data for demo purposes
        demo_data = [
            {
                "id": "demo-galloway",
                "name": "Galloway Forest (Demo)",
                "lat": 55.0833,
                "lon": -4.5000,
                "altitude_m": 320,
                "lp_zone": "1a",
                "score": 0,
                "cloud_cover": 100,
                "humidity": 100,
                "wind_speed": 0,
                "next_clear": "No data available - run cronjob",
                "moon_phase": "Unknown",
                "best_hours": [],
            }
        ]
        self.wfile.write(json.dumps(demo_data).encode())

    def send_index(self):
        """Send simple index page."""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()

        html = """<!DOCTYPE html>
<html>
<head>
    <title>Stargazer API</title>
    <style>
        body { font-family: monospace; background: #000; color: #0f0; padding: 20px; }
        a { color: #0ff; }
        pre { background: #111; padding: 10px; border: 1px solid #0f0; }
    </style>
</head>
<body>
    <h1>Stargazer API</h1>
    <p>Dark Sky Location Service for Scotland</p>

    <h2>Endpoints:</h2>
    <ul>
        <li><a href="/api/best">/api/best</a> - Best locations for stargazing</li>
        <li><a href="/api/locations">/api/locations</a> - All scored locations</li>
        <li><a href="/health">/health</a> - Health check</li>
    </ul>

    <h2>Status:</h2>
    <pre id="status">Loading...</pre>

    <script>
        fetch('/api/best')
            .then(r => r.json())
            .then(data => {
                document.getElementById('status').textContent =
                    data.length + ' locations available\n' +
                    'Last update: ' + new Date().toISOString();
            })
            .catch(err => {
                document.getElementById('status').textContent = 'Error: ' + err;
            });
    </script>
</body>
</html>"""
        self.wfile.write(html.encode())

    def send_404(self):
        """Send 404 response."""
        self.send_error(404, "Not Found")

    def log_message(self, format, *args):
        """Override to use logger instead of stderr."""
        logger.info("%s - %s", self.client_address[0], format % args)


def main():
    """Run the API server."""
    port = int(os.environ.get("PORT", "8080"))
    server = HTTPServer(("", port), StargazerAPIHandler)

    logger.info(f"Starting Stargazer API server on port {port}")
    logger.info(f"Data directory: {DATA_DIR}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down server")
        server.shutdown()


if __name__ == "__main__":
    main()
