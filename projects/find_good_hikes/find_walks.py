from datetime import datetime
import sqlite3
from haversine import haversine, Unit # Import the haversine function and Unit enum
from typing import List, Dict, Any, Tuple
from hourly_forecast import HourlyForecast
from scrape import Walk
from zoneinfo import ZoneInfo

# Define the Walk structure (optional, but good for clarity if you use it later)
# from pydantic import BaseModel
# class Walk(BaseModel):
#     uuid: str
#     name: str
#     url: str
#     distance_km: float
#     ascent_m: int
#     duration_h: float
#     summary: str
#     latitude: float
#     longitude: float

class WalkSearchResult(Walk):
    """
    A subclass of Walk that includes the distance from a center point.
    """
    distance_from_center_km: float | None = None
    forecast: list[HourlyForecast] | None = None


def find_nearby_walks(
    center_lat: float,
    center_lon: float,
    max_distance_km: float,
    table_name: str = "walks" # Assuming your table name is 'walks'
) -> List[WalkSearchResult]:
    """
    Finds walks within a specified distance from a central point in an SQLite database.

    Args:
        center_lat: Latitude of the center point.
        center_lon: Longitude of the center point.
        max_distance_km: Maximum distance in kilometers.
        table_name: Name of the table containing walk data.

    Returns:
        A list of dictionaries, where each dictionary represents a walk
        within the specified distance. Includes an added 'distance_from_center_km' key.
    """
    nearby_walks = []
    center_point: Tuple[float, float] = (center_lat, center_lon)
    conn = None # Initialize conn to None

    try:
        conn = sqlite3.connect("walks.db") # Connect to your SQLite database
        # Use row_factory for easy dictionary access
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # --- Optimization Note ---
        # For very large databases, selecting ALL rows can be slow.
        # A common optimization is to first select rows within a bounding box
        # using SQL's BETWEEN operator, and *then* apply the precise haversine
        # check in Python. See the "Optimization: Bounding Box" section below.
        # For simplicity, this example fetches all rows first.

        query = f"SELECT uuid, name, url, distance_km, ascent_m, duration_h, summary, latitude, longitude FROM {table_name}"
        cursor.execute(query)

        rows = cursor.fetchall()

        walks = [WalkSearchResult(
            uuid=row[0],
            name=row[1],
            url=row[2],
            distance_km=row[3],
            ascent_m=row[4],
            duration_h=row[5],
            summary=row[6],
            latitude=row[7],
            longitude=row[8],
        ) for row in rows]
        for walk in walks:
            walk_point: Tuple[float, float] = (walk.latitude, walk.longitude)

            # Calculate distance using haversine
            distance = haversine(center_point, walk_point, unit=Unit.KILOMETERS)
            print(distance)
            if distance <= max_distance_km:
                # Add the calculated distance to the result
                walk.distance_from_center_km = round(distance, 2)
                nearby_walks.append(walk)

        # Optional: Sort results by distance
        # walks.sort(key=lambda w: w['distance_from_center_km'])

        return nearby_walks

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return [] # Return empty list on error
    except Exception as e:
        print(f"An error occurred: {e}")
        return [] # Return empty list on error
    finally:
        if conn:
            conn.close()
    

def fetch_weather(
    nearby_walks: list[WalkSearchResult],
) -> list[WalkSearchResult]:
    try:
        db = sqlite3.connect("forecasts.sqlite.db")
        db.row_factory = sqlite3.Row
        cursor = db.cursor()
        for walk in nearby_walks:
    # time: datetime
    # air_pressure_at_sea_level: Optional[float] = None
    # air_temperature: Optional[float] = None
    # cloud_area_fraction: Optional[float] = None
    # relative_humidity: Optional[float] = None
    # wind_from_direction: Optional[float] = None
    # wind_speed: Optional[float] = None
    # precipitation_amount: Optional[float] = None
    # symbol_code: Optional[str] = None
    # latitude: Optional[float] = None
    # longitude: Optional[float] = None
    # is_night: Optional[bool] = None
    # uuid: Optional[str] = None
    # location_id: Optional[str] = None
            cursor.execute("""
                SELECT time, air_pressure_at_sea_level, air_temperature,
                cloud_area_fraction, relative_humidity, wind_from_direction,
                wind_speed, precipitation_amount, symbol_code, latitude,
                longitude, is_night, uuid, location_id
                FROM forecasts WHERE location_id = ?
                """,
                (walk.uuid,)
            )
            rows = cursor.fetchall()
            forecasts = [
                HourlyForecast(
                    time=row[0],
                    air_pressure_at_sea_level=row[1],
                    air_temperature=row[2],
                    cloud_area_fraction=row[3],
                    relative_humidity=row[4],
                    wind_from_direction=row[5],
                    wind_speed=row[6],
                    precipitation_amount=row[7],
                    symbol_code=row[8],
                    latitude=row[9],
                    longitude=row[10],
                    is_night=row[11],
                    uuid=row[12],
                    location_id=row[13]
                )
                for row in rows
            ]
            forecasts = [
                forecast for forecast in forecasts
                if forecast.time > datetime.now(tz=ZoneInfo("Europe/London"))
                and forecast.is_night is False
            ]
            walk.forecast = forecasts
        return nearby_walks
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []
    except Exception as e:
        print(f"An error occurred: {e}")
        return []






def find_walks(
    latitude: float,
    longitude: float,
    max_distance_km: float,
) -> List[WalkSearchResult]:
    """
    Finds walks within a specified distance from a central point in an SQLite database.

    Args:
        latitude: Latitude of the center point.
        longitude: Longitude of the center point.
        max_distance_km: Maximum distance in kilometers.
        table_name: Name of the table containing walk data.

    Returns:
        A list of WalkSearchResult objects representing walks within the specified distance.
    """
    walks = find_nearby_walks(
        center_lat=latitude,
        center_lon=longitude,
        max_distance_km=max_distance_km,
    )
    walks = fetch_weather(walks)

    return walks

# --- Example Usage ---
if __name__ == "__main__":
    search_lat = 55.88272269960411 # Latitude of Glasgow
    search_lon = -4.2589411313548515 # Longitude of Glasgow
    search_radius_km = 25 # Find walks within 15km

    print(f"Searching for walks within {search_radius_km}km of ({search_lat}, {search_lon})")
    nearby_walks = find_walks(search_lat, search_lon, search_radius_km)

    if nearby_walks:
        print(f"\nFound {len(nearby_walks)} walks:")
        for walk in nearby_walks:
            print("-----------------------")
            print(f" - {walk.name} ({walk.distance_from_center_km} km away)")
            print(f"   URL: {walk.url}")
            print(f"   Summary: {walk.summary}")
            print(f"   Distance: {walk.distance_km} km")
            print(f"   Ascent: {walk.ascent_m} m")
            print(f"   Duration: {walk.duration_h} hours")
            print(f"   Coordinates: ({walk.latitude}, {walk.longitude})")
            print(f"   Forecasts:")
            if walk.forecast:
                for forecast in walk.forecast:
                    print(f"     - {forecast.time}: {forecast.air_temperature}°C, {forecast.symbol_code}")
            else:
                print("     No forecasts available.")
    else:
        print("No walks found within the specified distance.")
