# Elevation Data API Implementation

## Data Source
**Natural Resources Canada - Canadian Digital Elevation Model (CDEM)**
- Ground-level elevation
- Covers all of Canada
- ~20m resolution

## Endpoints

### Single Point Elevation
```
GET https://geogratis.gc.ca/services/elevation/cdem/altitude?lat={lat}&lon={lng}
```

**Request:**
```
GET https://geogratis.gc.ca/services/elevation/cdem/altitude?lat=52.89&lon=-118.08
```

**Response:**
```json
{
  "altitude": 1062.0,
  "vertex": true,
  "geometry": {
    "type": "Point",
    "coordinates": [-118.08, 52.89]
  }
}
```

**Notes:**
- Returns `null` altitude if no data available
- 404 if invalid endpoint
- 400 if missing/invalid parameters

---

### Elevation Profile (Multiple Points)
```
GET https://geogratis.gc.ca/services/elevation/cdem/profile?path={WKT_LINESTRING}&steps={n}
```

**Request:**
```
GET https://geogratis.gc.ca/services/elevation/cdem/profile?path=LINESTRING(-123.12 49.28, -122.5 50.0, -118.08 52.89)&steps=10
```

**Response:**
```json
[
  {"altitude": 15.0, "vertex": true, "geometry": {"type": "Point", "coordinates": [-123.12, 49.28]}},
  {"altitude": 245.0, "vertex": false, "geometry": {"type": "Point", "coordinates": [-122.8, 49.5]}},
  ...
]
```

**Notes:**
- `path` uses WKT format: `LINESTRING(lng1 lat1, lng2 lat2, ...)`
- `steps` adds interpolated points between vertices
- `vertex: true` = original point, `vertex: false` = interpolated
- URL encode the path parameter

---

## Implementation Options

### Option 1: Enrich Points on Ingest (Recommended)
When GPS points come in, batch-enrich with elevation before storing.

```python
# Pseudocode
async def enrich_points_with_elevation(points):
    # Batch in chunks to avoid hammering API
    BATCH_SIZE = 50
    
    for chunk in chunks(points, BATCH_SIZE):
        tasks = [
            fetch(f"https://geogratis.gc.ca/services/elevation/cdem/altitude?lat={p.lat}&lon={p.lng}")
            for p in chunk
        ]
        results = await asyncio.gather(*tasks)
        
        for point, result in zip(chunk, results):
            point.elevation = result.get('altitude')
        
        # Rate limit - be nice to the API
        await sleep(0.5)
    
    return points
```

**Pros:** Elevation always available, calculated once
**Cons:** Initial backfill takes time (~5000 points = ~100 batches)

### Option 2: Profile Endpoint for Visualization
Use LINESTRING for summary charts, skip per-point accuracy.

```python
def get_day_elevation_profile(day_points, steps=100):
    # Build WKT from day's points (sample every Nth to keep URL reasonable)
    sampled = sample_points(day_points, max_points=20)
    coords = " ".join(f"{p.lng} {p.lat}" for p in sampled)
    wkt = f"LINESTRING({coords})"
    
    url = f"https://geogratis.gc.ca/services/elevation/cdem/profile?path={urlencode(wkt)}&steps={steps}"
    return fetch(url)
```

**Pros:** Fast, single request per day
**Cons:** Interpolated, not exact GPS point elevations

---

## Recommended API Response Schema

Extend your existing points response:

```json
{
  "points": [
    {
      "lat": 52.89,
      "lng": -118.08,
      "timestamp": "2025-12-27T17:21:00Z",
      "elevation": 1062,
      "image": null
    }
  ]
}
```

Add trip-level stats:

```json
{
  "stats": {
    "max_elevation": 1538,
    "min_elevation": 12,
    "total_ascent": 8420,
    "total_descent": 8380
  },
  "days": [
    {
      "date": "2025-12-26",
      "ascent": 1200,
      "descent": 450,
      "max_elevation": 1280,
      "min_elevation": 12
    }
  ]
}
```

---

## Calculating Ascent/Descent

Once you have elevation per point:

```python
def calculate_elevation_stats(points):
    ascent = 0
    descent = 0
    
    for i in range(1, len(points)):
        diff = points[i].elevation - points[i-1].elevation
        if diff > 0:
            ascent += diff
        else:
            descent += abs(diff)
    
    return {
        "ascent": round(ascent),
        "descent": round(descent),
        "max_elevation": max(p.elevation for p in points),
        "min_elevation": min(p.elevation for p in points)
    }
```

**Note:** GPS noise can inflate ascent/descent. Consider smoothing or using a threshold:

```python
# Only count changes > 5m to filter noise
THRESHOLD = 5
if abs(diff) > THRESHOLD:
    if diff > 0:
        ascent += diff
    else:
        descent += abs(diff)
```

---

## Backfill Script Outline

```python
#!/usr/bin/env python3
"""Backfill elevation data for existing GPS points."""

import asyncio
import aiohttp

API_BASE = "https://geogratis.gc.ca/services/elevation/cdem/altitude"
BATCH_SIZE = 50
DELAY = 0.5  # seconds between batches

async def fetch_elevation(session, lat, lng):
    url = f"{API_BASE}?lat={lat}&lon={lng}"
    async with session.get(url) as resp:
        if resp.status == 200:
            data = await resp.json()
            return data.get("altitude")
        return None

async def backfill():
    points = get_points_without_elevation()  # Your DB query
    
    async with aiohttp.ClientSession() as session:
        for i in range(0, len(points), BATCH_SIZE):
            batch = points[i:i + BATCH_SIZE]
            
            tasks = [fetch_elevation(session, p.lat, p.lng) for p in batch]
            elevations = await asyncio.gather(*tasks)
            
            for point, elev in zip(batch, elevations):
                update_point_elevation(point.id, elev)  # Your DB update
            
            print(f"Processed {i + len(batch)}/{len(points)}")
            await asyncio.sleep(DELAY)

if __name__ == "__main__":
    asyncio.run(backfill())
```

---

## Rate Limiting

NRCan doesn't publish rate limits, but be respectful:
- Batch requests where possible
- Add delays between batches (0.5-1s)
- Cache results - elevation doesn't change
- Consider running backfill during off-peak hours