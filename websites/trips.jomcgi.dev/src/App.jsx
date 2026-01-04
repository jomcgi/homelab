import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  useMemo,
} from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  MapPin,
  Wind,
  Camera,
  Play,
  Pause,
  ChevronLeft,
  ChevronRight,
  Radio,
  Eye,
  Maximize2,
  Minimize2,
  Map as MapIcon,
  Image as ImageIcon,
  Loader2,
  AlertCircle,
  Tag,
  X,
} from "lucide-react";

// ============================================
// API Configuration
// ============================================

// Use api-gateway for API access, not the static site
const API_BASE_URL =
  import.meta.env.VITE_API_URL || "https://api.jomcgi.dev/trips";
const WS_BASE_URL = import.meta.env.VITE_WS_URL || "wss://api.jomcgi.dev/trips";
const IMAGE_BASE_URL =
  import.meta.env.VITE_IMAGE_URL || "https://img.jomcgi.dev";

// Construct image URLs from filename
const getThumbUrl = (image) => `${IMAGE_BASE_URL}/trips/thumb/${image}`;
const getDisplayUrl = (image) => `${IMAGE_BASE_URL}/trips/display/${image}`;

// ============================================
// API Hook - Fetch real trip data
// ============================================

function useTripData() {
  const [points, setPoints] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState({ total: 0, viewers: 0 });
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  // Transform API response to match React component expectations
  const transformPoint = useCallback((apiPoint) => {
    // Strip "Z" suffix - timestamps are camera local time (Pacific), not UTC
    const ts = apiPoint.timestamp?.replace(/Z$/, "") || "";
    return {
      id: apiPoint.id,
      lat: apiPoint.lat,
      lng: apiPoint.lng,
      image: apiPoint.image,  // Just the filename
      source: apiPoint.source || "gopro",
      timestamp: new Date(ts),
      tags: apiPoint.tags || [],
    };
  }, []);

  // Connect to WebSocket for live updates
  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(`${WS_BASE_URL}/ws/live`);

      ws.onopen = () => {
        console.log("WebSocket connected");
        // Clear any pending reconnect
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = null;
        }
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "new_point") {
            const newPoint = transformPoint(data.point);
            setPoints((prev) => [...prev, newPoint]);
            setStats((prev) => ({
              ...prev,
              total: prev.total + 1,
            }));
          } else if (data.type === "connected") {
            console.log(
              `WebSocket: ${data.cached_points} points cached on server`,
            );
          } else if (data.type === "viewer_count") {
            setStats((prev) => ({
              ...prev,
              viewers: data.count,
            }));
          }
        } catch (e) {
          console.error("WebSocket message parse error:", e);
        }
      };

      ws.onclose = () => {
        console.log("WebSocket disconnected, reconnecting in 5s...");
        reconnectTimeoutRef.current = setTimeout(connectWebSocket, 5000);
      };

      ws.onerror = (err) => {
        console.error("WebSocket error:", err);
      };

      wsRef.current = ws;
    } catch (e) {
      console.error("WebSocket connection failed:", e);
    }
  }, [transformPoint]);

  // Fetch initial data
  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      try {
        setLoading(true);
        setError(null);

        const response = await fetch(`${API_BASE_URL}/api/points`);
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();

        if (cancelled) return;

        const transformedPoints = data.points?.map(transformPoint) || [];
        setPoints(transformedPoints);
        setStats({
          total: data.total || 0,
          viewers: 0,
        });

        // Connect WebSocket for live updates
        connectWebSocket();
      } catch (err) {
        console.error("Failed to fetch trip data:", err);
        if (!cancelled) {
          setError(err.message);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    fetchData();

    return () => {
      cancelled = true;
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [transformPoint, connectWebSocket]);

  return { points, loading, error, stats };
}

// ============================================
// Weather Hook - Fetch from met.no API
// ============================================

function useWeather(lat, lng) {
  const [weather, setWeather] = useState(null);
  const [loading, setLoading] = useState(false);
  const cacheRef = useRef({ key: null, data: null, timestamp: 0 });

  useEffect(() => {
    if (!lat || !lng) return;

    // Round coords to 2 decimals for caching (met.no recommends this)
    const roundedLat = Math.round(lat * 100) / 100;
    const roundedLng = Math.round(lng * 100) / 100;
    const cacheKey = `${roundedLat},${roundedLng}`;

    // Use cached data if same location and less than 10 minutes old
    const cache = cacheRef.current;
    if (cache.key === cacheKey && Date.now() - cache.timestamp < 600000) {
      setWeather(cache.data);
      return;
    }

    async function fetchWeather() {
      setLoading(true);
      try {
        const response = await fetch(
          `https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=${roundedLat}&lon=${roundedLng}`,
          {
            headers: {
              "User-Agent": "trips.jomcgi.dev/1.0 github.com/jomcgi/homelab",
            },
          },
        );

        if (!response.ok) throw new Error("Weather fetch failed");

        const data = await response.json();
        const current = data.properties.timeseries[0];
        const details = current.data.instant.details;
        const symbol =
          current.data.next_1_hours?.summary?.symbol_code ||
          current.data.next_6_hours?.summary?.symbol_code ||
          "cloudy";

        const weatherData = {
          temp: Math.round(details.air_temperature),
          windSpeed: Math.round(details.wind_speed * 3.6), // m/s to km/h
          humidity: Math.round(details.relative_humidity),
          symbol: symbol,
        };

        cacheRef.current = {
          key: cacheKey,
          data: weatherData,
          timestamp: Date.now(),
        };
        setWeather(weatherData);
      } catch (err) {
        console.error("Weather fetch error:", err);
        setWeather(null);
      } finally {
        setLoading(false);
      }
    }

    fetchWeather();
  }, [lat, lng]);

  return { weather, loading };
}

// Weather symbol to description mapping
const weatherDescriptions = {
  clearsky: "Clear",
  fair: "Fair",
  partlycloudy: "Partly Cloudy",
  cloudy: "Cloudy",
  lightrainshowers: "Light Showers",
  rainshowers: "Showers",
  heavyrainshowers: "Heavy Showers",
  lightrain: "Light Rain",
  rain: "Rain",
  heavyrain: "Heavy Rain",
  lightsnowshowers: "Light Snow",
  snowshowers: "Snow Showers",
  heavysnowshowers: "Heavy Snow",
  lightsnow: "Light Snow",
  snow: "Snow",
  heavysnow: "Heavy Snow",
  fog: "Fog",
  thunder: "Thunderstorm",
};

function getWeatherDescription(symbol) {
  // Remove _day/_night suffix
  const base = symbol?.replace(/_day|_night/g, "") || "cloudy";
  return weatherDescriptions[base] || "Cloudy";
}

// ============================================
// Media Query Hook
// ============================================

function useMediaQuery(query) {
  const [matches, setMatches] = useState(false);
  useEffect(() => {
    const media = window.matchMedia(query);
    setMatches(media.matches);
    const listener = (e) => setMatches(e.matches);
    media.addEventListener("change", listener);
    return () => media.removeEventListener("change", listener);
  }, [query]);
  return matches;
}

// ============================================
// View Toggle Component (Mobile Photo/Map Tabs)
// ============================================

function ViewToggle({ activeView, onViewChange }) {
  return (
    <div className="flex bg-gray-200 rounded-lg p-1">
      <button
        onClick={() => onViewChange("image")}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded transition-colors text-sm font-medium ${
          activeView === "image"
            ? "bg-blue-500 text-white"
            : "text-gray-600 hover:text-gray-800"
        }`}
      >
        <ImageIcon className="h-4 w-4" />
        Photo
      </button>
      <button
        onClick={() => onViewChange("map")}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded transition-colors text-sm font-medium ${
          activeView === "map"
            ? "bg-blue-500 text-white"
            : "text-gray-600 hover:text-gray-800"
        }`}
      >
        <MapIcon className="h-4 w-4" />
        Map
      </button>
    </div>
  );
}

// ============================================
// Map Component
// ============================================

// Day colors for multi-day route visualization
const DAY_COLORS = [
  "#3b82f6", // Blue - Day 1
  "#10b981", // Emerald - Day 2
  "#f59e0b", // Amber - Day 3
  "#ef4444", // Red - Day 4
  "#8b5cf6", // Violet - Day 5
  "#06b6d4", // Cyan - Day 6
  "#f97316", // Orange - Day 7
  "#ec4899", // Pink - Day 8
  "#84cc16", // Lime - Day 9
  "#14b8a6", // Teal - Day 10
  "#a855f7", // Purple - Day 11
];

function TripMap({ points, selectablePoints, selectedId, onMarkerClick, isLive }) {
  const mapContainer = useRef(null);
  const map = useRef(null);
  const markerRef = useRef(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const mountedRef = useRef(false);
  const dayOffsetsRef = useRef(new Map()); // Ref to access current offsets in callbacks

  // Calculate day boundaries from the actual points we're rendering (not from timeline data)
  // This ensures gap points get the correct day color
  const mapDayBoundaries = useMemo(() => {
    if (points.length === 0) return [];

    const boundaries = [];
    let currentDate = null;

    points.forEach((point, index) => {
      // Get date string in Pacific Time (for BC/Yukon trip)
      const dateStr = point.timestamp.toLocaleDateString("en-CA", {
        timeZone: "America/Vancouver",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      });

      if (dateStr !== currentDate) {
        boundaries.push({
          index,
          date: point.timestamp,
          dateStr,
          dayNumber: boundaries.length + 1,
        });
        currentDate = dateStr;
      }
    });

    console.log("Map day boundaries:", JSON.stringify(boundaries.map(b => ({ dayNumber: b.dayNumber, dateStr: b.dateStr, index: b.index }))));
    return boundaries;
  }, [points]);

  // Split points into day segments, separating gap points from real points
  // Real points are further split into contiguous runs (broken by gaps)
  const { daySegments, gapSegments } = useMemo(() => {
    // Helper to split points into contiguous runs of real vs gap points
    const splitIntoRuns = (dayPoints, dayNumber, color) => {
      const realRuns = [];
      const gapRuns = [];
      let currentRealRun = [];
      let currentGapRun = [];

      for (const p of dayPoints) {
        const isGap = p.image === null;
        if (isGap) {
          // End current real run if any
          if (currentRealRun.length > 0) {
            realRuns.push({ dayNumber, points: currentRealRun, color });
            currentRealRun = [];
          }
          currentGapRun.push(p);
        } else {
          // End current gap run if any
          if (currentGapRun.length > 0) {
            gapRuns.push({ dayNumber, points: currentGapRun, color });
            currentGapRun = [];
          }
          currentRealRun.push(p);
        }
      }

      // Flush remaining runs
      if (currentRealRun.length > 0) {
        realRuns.push({ dayNumber, points: currentRealRun, color });
      }
      if (currentGapRun.length > 0) {
        gapRuns.push({ dayNumber, points: currentGapRun, color });
      }

      return { realRuns, gapRuns };
    };

    if (mapDayBoundaries.length === 0 || points.length === 0) {
      const { realRuns, gapRuns } = splitIntoRuns(points, 1, DAY_COLORS[0]);
      return {
        daySegments: realRuns.length > 0 ? realRuns : [{ dayNumber: 1, points: [], color: DAY_COLORS[0] }],
        gapSegments: gapRuns,
      };
    }

    const allRealRuns = [];
    const allGapRuns = [];

    for (let i = 0; i < mapDayBoundaries.length; i++) {
      const startIdx = mapDayBoundaries[i].index;
      const endIdx = i < mapDayBoundaries.length - 1
        ? mapDayBoundaries[i + 1].index
        : points.length;

      const dayPoints = points.slice(startIdx, endIdx);
      const color = DAY_COLORS[(i) % DAY_COLORS.length];
      const { realRuns, gapRuns } = splitIntoRuns(dayPoints, mapDayBoundaries[i].dayNumber, color);

      allRealRuns.push(...realRuns);
      allGapRuns.push(...gapRuns);
    }

    console.log("Gap segments:", JSON.stringify(allGapRuns.map(g => ({ dayNumber: g.dayNumber, color: g.color, pointCount: g.points.length, firstTimestamp: g.points[0]?.timestamp?.toISOString() }))));
    return { daySegments: allRealRuns, gapSegments: allGapRuns };
  }, [points, mapDayBoundaries]);

  // Detect which days have overlapping routes and assign offsets
  const dayOffsets = useMemo(() => {
    const offsets = new Map(); // dayNumber -> offset
    const OVERLAP_THRESHOLD = 1.0541;
    const MIN_OVERLAP_POINTS = 10;

    // Aggregate all points by day number (regardless of gaps/runs)
    // This ensures we compare whole days, not individual runs
    const pointsByDay = new Map();
    for (const segment of daySegments) {
      const existing = pointsByDay.get(segment.dayNumber) || [];
      pointsByDay.set(segment.dayNumber, [...existing, ...segment.points]);
    }

    const dayNumbers = Array.from(pointsByDay.keys()).sort((a, b) => a - b);
    console.log("Day offset detection - days:", dayNumbers, "points per day:", Array.from(pointsByDay.entries()).map(([d, p]) => ({ day: d, count: p.length })));

    // First pass: detect all overlaps and their counts
    const overlaps = [];
    for (let i = 0; i < dayNumbers.length; i++) {
      for (let j = i + 1; j < dayNumbers.length; j++) {
        const day1 = dayNumbers[i];
        const day2 = dayNumbers[j];
        const points1 = pointsByDay.get(day1);
        const points2 = pointsByDay.get(day2);

        let overlapCount = 0;
        const sampleRate = 5;

        for (let pi = 0; pi < points2.length; pi += sampleRate) {
          const p2 = points2[pi];
          for (let pj = 0; pj < points1.length; pj += sampleRate) {
            const p1 = points1[pj];
            const dist = Math.abs(p1.lat - p2.lat) + Math.abs(p1.lng - p2.lng);
            if (dist < OVERLAP_THRESHOLD) {
              overlapCount++;
              break;
            }
          }
        }

        if (overlapCount >= MIN_OVERLAP_POINTS) {
          overlaps.push({ day1, day2, points1, points2, overlapCount });
        }
      }
    }

    // Sort by overlap count descending - process most significant overlaps first
    overlaps.sort((a, b) => b.overlapCount - a.overlapCount);
    console.log("Overlaps sorted by count:", overlaps.map(o => `D${o.day1}-D${o.day2}:${o.overlapCount}`).join(", "));

    // Second pass: assign offsets, prioritizing high-overlap pairs
    for (const { day1, day2, points1, points2, overlapCount } of overlaps) {
      // Skip if both days already have offsets
      if (offsets.has(day1) && offsets.has(day2)) {
        console.log(`Overlap: Day ${day1} vs Day ${day2}, count=${overlapCount}, both already set`);
        continue;
      }

      // Detect travel direction by comparing start/end of each day's points
      // If both going same direction: use opposite offsets (-4, +4)
      // If going opposite directions: use same offsets (-4, -4) since
      // line-offset is relative to travel direction
      const dir1 = points1.length > 1
        ? Math.sign(points1[points1.length - 1].lat - points1[0].lat)
        : 0;
      const dir2 = points2.length > 1
        ? Math.sign(points2[points2.length - 1].lat - points2[0].lat)
        : 0;
      const sameDirection = dir1 === dir2 || dir1 === 0 || dir2 === 0;

      let assignedOffset1, assignedOffset2;
      if (sameDirection) {
        // Same direction: opposite offsets work correctly
        assignedOffset1 = -4;
        assignedOffset2 = 4;
      } else {
        // Opposite directions: same offsets put them on opposite sides
        assignedOffset1 = -4;
        assignedOffset2 = -4;
      }

      const offset1 = offsets.has(day1) ? "(already set)" : assignedOffset1;
      const offset2 = offsets.has(day2) ? "(already set)" : assignedOffset2;
      console.log(`Overlap: Day ${day1} vs Day ${day2}, count=${overlapCount}, dirs=${dir1}/${dir2} (${sameDirection ? "same" : "opposite"}), assigning: D${day1}=${offset1}, D${day2}=${offset2}`);

      if (!offsets.has(day1)) {
        offsets.set(day1, assignedOffset1);
      }
      if (!offsets.has(day2)) {
        offsets.set(day2, assignedOffset2);
      }
    }

    console.log("Final day offsets:", Object.fromEntries(offsets));
    return offsets;
  }, [daySegments]);

  // Keep ref in sync with dayOffsets for use in callbacks
  useEffect(() => {
    dayOffsetsRef.current = dayOffsets;
  }, [dayOffsets]);

  useEffect(() => {
    if (mountedRef.current) return;
    mountedRef.current = true;

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
      center: [-128, 56],
      zoom: 4,
    });

    map.current.addControl(new maplibregl.NavigationControl(), "top-right");

    map.current.on("load", () => {
      map.current.resize();

      // Add terrain DEM source for hillshading (free AWS Mapzen tiles)
      map.current.addSource("terrain-dem", {
        type: "raster-dem",
        tiles: [
          "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
        ],
        encoding: "terrarium",
        tileSize: 256,
        maxzoom: 15,
      });

      // Find the first symbol layer to insert hillshade below labels
      const layers = map.current.getStyle().layers;
      const firstSymbolLayer = layers.find((layer) => layer.type === "symbol");

      // Add hillshade layer - insert below labels for terrain visibility
      map.current.addLayer(
        {
          id: "hillshade",
          type: "hillshade",
          source: "terrain-dem",
          paint: {
            "hillshade-exaggeration": 0.5,
            "hillshade-shadow-color": "#473B24",
            "hillshade-highlight-color": "#ffffff",
            "hillshade-illumination-direction": 315,
          },
        },
        firstSymbolLayer?.id,
      );

      // Create route layers for each segment (multiple per day if gaps exist)
      daySegments.forEach((segment, idx) => {
        const routeCoords = segment.points.map((p) => [p.lng, p.lat]);
        const sourceId = `route-segment-${idx}`;

        // Only offset days that overlap with other days (detected above)
        // Non-overlapping days stay on the road (offset 0)
        // Use ref to get current offsets (closure would have stale value)
        const offset = dayOffsetsRef.current.get(segment.dayNumber) || 0;
        console.log(`Initial layer creation: segment ${idx} (day ${segment.dayNumber}) offset=${offset}`);

        map.current.addSource(sourceId, {
          type: "geojson",
          data: {
            type: "Feature",
            properties: { day: segment.dayNumber },
            geometry: { type: "LineString", coordinates: routeCoords },
          },
        });

        // Glow layer
        map.current.addLayer({
          id: `${sourceId}-glow`,
          type: "line",
          source: sourceId,
          paint: {
            "line-color": segment.color,
            "line-width": 10,
            "line-opacity": 0.3,
            "line-blur": 4,
            "line-offset": offset,
          },
        });

        // Main line layer
        map.current.addLayer({
          id: `${sourceId}-line`,
          type: "line",
          source: sourceId,
          paint: {
            "line-color": segment.color,
            "line-width": 4,
            "line-opacity": 0.9,
            "line-offset": offset,
          },
        });
      });

      // Gap route layers are created dynamically in the update effect
      // to ensure they use current (not stale) segment data with correct colors

      // Add day labels (only one per day, on the first segment of each day)
      const labeledDays = new Set();
      daySegments.forEach((segment) => {
        if (segment.points.length > 0 && !labeledDays.has(segment.dayNumber)) {
          labeledDays.add(segment.dayNumber);
          // Place label ~15% into the route - near the start where each day diverges
          const labelIdx = Math.floor(segment.points.length * 0.15);
          const labelPoint = segment.points[Math.max(labelIdx, 0)];
          const labelSourceId = `route-day-${segment.dayNumber}-label`;

          map.current.addSource(labelSourceId, {
            type: "geojson",
            data: {
              type: "Feature",
              properties: { day: segment.dayNumber },
              geometry: { type: "Point", coordinates: [labelPoint.lng, labelPoint.lat] },
            },
          });

          map.current.addLayer({
            id: `${labelSourceId}-text`,
            type: "symbol",
            source: labelSourceId,
            layout: {
              "text-field": `Day ${segment.dayNumber}`,
              "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
              "text-size": 12,
              "text-offset": [0, -1],
              "text-anchor": "bottom",
              "text-allow-overlap": true,
            },
            paint: {
              "text-color": segment.color,
              "text-halo-color": "#ffffff",
              "text-halo-width": 2,
            },
          });
        }
      });

      // Click handler for route lines - navigate to closest selectable point (with image)
      const handleRouteClick = (e) => {
        const clickedLng = e.lngLat.lng;
        const clickedLat = e.lngLat.lat;

        // Find the closest selectable point (one with an image)
        // Gap points are not selectable - they're just for route visualization
        const pointsToSearch = selectablePoints || points;
        let closestId = null;
        let minDist = Infinity;

        pointsToSearch.forEach((p) => {
          // Skip gap points (no image)
          if (p.image === null) return;

          const dist = Math.pow(p.lng - clickedLng, 2) + Math.pow(p.lat - clickedLat, 2);
          if (dist < minDist) {
            minDist = dist;
            closestId = p.id;
          }
        });

        if (closestId !== null) {
          onMarkerClick(closestId);
        }
      };

      // Add click and hover handlers for each route segment
      daySegments.forEach((segment, idx) => {
        const lineId = `route-segment-${idx}-line`;
        const glowId = `route-segment-${idx}-glow`;

        map.current.on("click", lineId, handleRouteClick);
        map.current.on("click", glowId, handleRouteClick);

        map.current.on("mouseenter", lineId, () => {
          map.current.getCanvas().style.cursor = "pointer";
        });
        map.current.on("mouseleave", lineId, () => {
          map.current.getCanvas().style.cursor = "";
        });
        map.current.on("mouseenter", glowId, () => {
          map.current.getCanvas().style.cursor = "pointer";
        });
        map.current.on("mouseleave", glowId, () => {
          map.current.getCanvas().style.cursor = "";
        });
      });

      // Add click handlers for gap route lines (navigates to nearest real point)
      gapSegments.forEach((segment, idx) => {
        const lineId = `gap-segment-${idx}-line`;

        map.current.on("click", lineId, handleRouteClick);

        map.current.on("mouseenter", lineId, () => {
          map.current.getCanvas().style.cursor = "pointer";
        });
        map.current.on("mouseleave", lineId, () => {
          map.current.getCanvas().style.cursor = "";
        });
      });

      setMapLoaded(true);
      setTimeout(() => map.current?.resize(), 100);
    });

    const resizeObserver = new ResizeObserver(() => {
      if (map.current) map.current.resize();
    });
    resizeObserver.observe(mapContainer.current);

    return () => resizeObserver.disconnect();
  }, []);

  // Update route lines when points change (e.g., from WebSocket)
  useEffect(() => {
    if (!mapLoaded || !map.current) return;

    // Update each route segment source and colors
    daySegments.forEach((segment, idx) => {
      const sourceId = `route-segment-${idx}`;
      const source = map.current.getSource(sourceId);
      if (source) {
        const routeCoords = segment.points.map((p) => [p.lng, p.lat]);
        source.setData({
          type: "Feature",
          properties: { day: segment.dayNumber },
          geometry: { type: "LineString", coordinates: routeCoords },
        });
        // Update layer colors (in case day assignment changed)
        const offset = dayOffsets.get(segment.dayNumber) || 0;
        console.log(`Applying offset to segment ${idx} (day ${segment.dayNumber}): offset=${offset}, color=${segment.color}`);
        if (map.current.getLayer(`${sourceId}-glow`)) {
          map.current.setPaintProperty(`${sourceId}-glow`, "line-color", segment.color);
          map.current.setPaintProperty(`${sourceId}-glow`, "line-offset", offset);
        }
        if (map.current.getLayer(`${sourceId}-line`)) {
          map.current.setPaintProperty(`${sourceId}-line`, "line-color", segment.color);
          map.current.setPaintProperty(`${sourceId}-line`, "line-offset", offset);
        }
      } else {
        console.log(`WARNING: Source ${sourceId} for day ${segment.dayNumber} does not exist!`);
      }
    });

    // Update or create gap route sources and colors
    gapSegments.forEach((segment, idx) => {
      const sourceId = `gap-segment-${idx}`;
      const routeCoords = segment.points.map((p) => [p.lng, p.lat]);
      const offset = dayOffsets.get(segment.dayNumber) || 0;
      const source = map.current.getSource(sourceId);

      if (source) {
        // Update existing source
        source.setData({
          type: "Feature",
          properties: { day: segment.dayNumber, isGap: true },
          geometry: { type: "LineString", coordinates: routeCoords },
        });
        // Update layer color (in case day assignment changed)
        if (map.current.getLayer(`${sourceId}-line`)) {
          map.current.setPaintProperty(`${sourceId}-line`, "line-color", segment.color);
          map.current.setPaintProperty(`${sourceId}-line`, "line-offset", offset);
        }
      } else {
        // Create new source and layer for gap segments that didn't exist on initial load
        console.log(`CREATING gap layer ${sourceId} with color ${segment.color} for day ${segment.dayNumber}`);
        map.current.addSource(sourceId, {
          type: "geojson",
          data: {
            type: "Feature",
            properties: { day: segment.dayNumber, isGap: true },
            geometry: { type: "LineString", coordinates: routeCoords },
          },
        });

        // Gap line layer - same color/opacity as real routes, just dashed
        map.current.addLayer({
          id: `${sourceId}-line`,
          type: "line",
          source: sourceId,
          paint: {
            "line-color": segment.color,
            "line-width": 4,
            "line-opacity": 0.9,
            "line-offset": offset,
            "line-dasharray": [2, 2],
          },
        });
      }
    });
  }, [mapLoaded, daySegments, gapSegments, dayOffsets]);

  useEffect(() => {
    if (!mapLoaded || !map.current) return;

    const point = points.find((p) => p.id === selectedId);
    if (!point) return;

    if (markerRef.current) markerRef.current.remove();

    const el = document.createElement("div");
    el.className = "current-marker";

    const baseColor = isLive ? "#ef4444" : "#3b82f6";
    el.style.cssText = `
      width: ${isLive ? "20px" : "16px"};
      height: ${isLive ? "20px" : "16px"};
      background: ${baseColor};
      border: 3px solid white;
      border-radius: 50%;
      box-shadow: 0 0 ${isLive ? "20px" : "12px"} ${baseColor};
      ${isLive ? "animation: pulse 1.5s ease-in-out infinite;" : ""}
    `;

    markerRef.current = new maplibregl.Marker({ element: el })
      .setLngLat([point.lng, point.lat])
      .addTo(map.current);

    map.current.flyTo({
      center: [point.lng, point.lat],
      zoom: Math.max(map.current.getZoom(), isLive ? 8 : 7),
      duration: 800,
    });
  }, [selectedId, mapLoaded, points, isLive]);

  return (
    <div
      ref={mapContainer}
      className="absolute top-0 left-0 right-0 bottom-0 w-full h-full"
    />
  );
}

// ============================================
// Live Badge Component
// ============================================

function LiveBadge({ isLive, onToggle, viewerCount = null, compact = false }) {
  if (compact) {
    // Mobile: circular 40x40px button with just the dot
    return (
      <button
        onClick={onToggle}
        className={`
          flex items-center justify-center w-10 h-10 rounded-full
          transition-all duration-200
          ${
            isLive
              ? "bg-red-500/20 border border-red-500/30 hover:bg-red-500/30"
              : "bg-gray-200 border border-gray-300 hover:bg-gray-300"
          }
        `}
        title={isLive ? "LIVE" : "Go Live"}
      >
        <span
          className={`
          w-3 h-3 rounded-full
          ${isLive ? "bg-red-500 animate-pulse" : "bg-gray-400"}
        `}
        />
      </button>
    );
  }

  // Desktop: full badge with text
  return (
    <button
      onClick={onToggle}
      className={`
        flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium
        transition-all duration-200
        ${
          isLive
            ? "bg-red-500/20 text-red-600 border border-red-500/30 hover:bg-red-500/30"
            : "bg-gray-200 text-gray-600 border border-gray-300 hover:bg-gray-300 hover:text-gray-800"
        }
      `}
    >
      <span
        className={`
        w-2 h-2 rounded-full
        ${isLive ? "bg-red-500 animate-pulse" : "bg-gray-400"}
      `}
      />
      <span>{isLive ? "LIVE" : "Go Live"}</span>
      {isLive && viewerCount !== null && (
        <span className="flex items-center gap-1 text-xs text-red-500/70 border-l border-red-500/30 pl-2 ml-1">
          <Eye className="w-3 h-3" />
          {viewerCount}
        </span>
      )}
    </button>
  );
}

// ============================================
// Tag Filter Component
// ============================================

function TagFilter({ availableTags, selectedTags, onTagsChange, isMobile = false }) {
  const [isOpen, setIsOpen] = useState(false);

  if (availableTags.length === 0) return null;

  const toggleTag = (tag) => {
    if (selectedTags.includes(tag)) {
      onTagsChange(selectedTags.filter((t) => t !== tag));
    } else {
      onTagsChange([...selectedTags, tag]);
    }
  };

  const clearTags = () => {
    onTagsChange([]);
    setIsOpen(false);
  };

  if (isMobile) {
    // Mobile: compact button with count badge
    return (
      <div className="relative">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className={`
            flex items-center justify-center w-10 h-10 rounded-full
            transition-all duration-200
            ${
              selectedTags.length > 0
                ? "bg-blue-500/20 border border-blue-500/30 hover:bg-blue-500/30"
                : "bg-gray-200 border border-gray-300 hover:bg-gray-300"
            }
          `}
          title="Filter by tags"
        >
          <Tag className={`w-4 h-4 ${selectedTags.length > 0 ? "text-blue-600" : "text-gray-500"}`} />
          {selectedTags.length > 0 && (
            <span className="absolute -top-1 -right-1 w-4 h-4 bg-blue-500 text-white text-[10px] rounded-full flex items-center justify-center">
              {selectedTags.length}
            </span>
          )}
        </button>

        {/* Dropdown */}
        {isOpen && (
          <>
            <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
            <div className="absolute right-0 top-12 z-50 bg-white border border-gray-200 rounded-lg shadow-lg p-2 min-w-[150px]">
              {selectedTags.length > 0 && (
                <button
                  onClick={clearTags}
                  className="w-full text-left px-3 py-1.5 text-xs text-red-600 hover:bg-red-50 rounded mb-1"
                >
                  Clear all
                </button>
              )}
              {availableTags.map((tag) => (
                <button
                  key={tag}
                  onClick={() => toggleTag(tag)}
                  className={`
                    w-full text-left px-3 py-1.5 text-sm rounded transition-colors
                    ${selectedTags.includes(tag) ? "bg-blue-100 text-blue-700" : "hover:bg-gray-100 text-gray-700"}
                  `}
                >
                  {tag}
                </button>
              ))}
            </div>
          </>
        )}
      </div>
    );
  }

  // Desktop: inline chips
  return (
    <div className="flex items-center gap-2">
      <Tag className="w-3.5 h-3.5 text-gray-400" />
      <div className="flex items-center gap-1.5 flex-wrap">
        {availableTags.map((tag) => (
          <button
            key={tag}
            onClick={() => toggleTag(tag)}
            className={`
              px-2 py-0.5 rounded-full text-xs font-medium transition-colors
              ${
                selectedTags.includes(tag)
                  ? "bg-blue-500 text-white"
                  : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }
            `}
          >
            {tag}
          </button>
        ))}
        {selectedTags.length > 0 && (
          <button
            onClick={clearTags}
            className="p-0.5 rounded-full text-gray-400 hover:text-gray-600 hover:bg-gray-200 transition-colors"
            title="Clear filters"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

// ============================================
// Image Panel Component
// ============================================

// ============================================
// Fullscreen Image Modal
// ============================================

function FullscreenModal({ imageUrl, onClose, onPrev, onNext }) {
  const touchStartX = useRef(null);
  const touchStartY = useRef(null);

  // Handle keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowLeft" && onPrev) {
        e.preventDefault();
        onPrev();
      } else if (e.key === "ArrowRight" && onNext) {
        e.preventDefault();
        onNext();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, onPrev, onNext]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, []);

  // Handle touch swipe gestures
  const handleTouchStart = (e) => {
    touchStartX.current = e.touches[0].clientX;
    touchStartY.current = e.touches[0].clientY;
  };

  const handleTouchEnd = (e) => {
    if (touchStartX.current === null) return;

    const touchEndX = e.changedTouches[0].clientX;
    const touchEndY = e.changedTouches[0].clientY;
    const deltaX = touchEndX - touchStartX.current;
    const deltaY = touchEndY - touchStartY.current;

    // Only trigger if horizontal swipe is dominant and significant
    const minSwipeDistance = 50;
    if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > minSwipeDistance) {
      if (deltaX > 0 && onPrev) {
        // Swipe right -> previous
        onPrev();
      } else if (deltaX < 0 && onNext) {
        // Swipe left -> next
        onNext();
      }
    }

    touchStartX.current = null;
    touchStartY.current = null;
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-black/95 flex items-center justify-center cursor-pointer"
      onClick={onClose}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
    >
      <img
        src={imageUrl}
        alt="Trip photo fullscreen"
        className="max-w-full max-h-full object-contain select-none"
        onClick={(e) => e.stopPropagation()}
        draggable={false}
        decoding="async"
      />

      {/* Close button */}
      <button
        onClick={onClose}
        className="absolute top-4 right-4 text-white/70 hover:text-white p-2 rounded-full hover:bg-white/10 transition-colors"
        aria-label="Close fullscreen"
      >
        <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>

      {/* Previous button */}
      {onPrev && (
        <button
          onClick={(e) => { e.stopPropagation(); onPrev(); }}
          className="absolute left-4 top-1/2 -translate-y-1/2 text-white/70 hover:text-white p-3 rounded-full hover:bg-white/10 transition-colors"
          aria-label="Previous photo"
        >
          <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
        </button>
      )}

      {/* Next button */}
      {onNext && (
        <button
          onClick={(e) => { e.stopPropagation(); onNext(); }}
          className="absolute right-4 top-1/2 -translate-y-1/2 text-white/70 hover:text-white p-3 rounded-full hover:bg-white/10 transition-colors"
          aria-label="Next photo"
        >
          <svg className="w-10 h-10" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      )}

      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 text-white/50 text-sm text-center">
        <span className="hidden md:inline">Press ESC to close · Arrow keys to navigate</span>
        <span className="md:hidden">Tap to close · Swipe to navigate</span>
      </div>
    </div>
  );
}

// ============================================
// Image Panel Component
// ============================================

function ImagePanel({
  point,
  isLive,
  totalFrames,
  currentIndex,
  currentDay = 1,
  totalDays = 1,
  isMobile = false,
  cachedImages = null,
  onImageClick = null,
  onPrev = null,
  onNext = null,
}) {
  // Double-buffer for smooth transitions (previous image stays visible as backdrop)
  const [currentImageUrl, setCurrentImageUrl] = useState(null);
  const [previousImageUrl, setPreviousImageUrl] = useState(null);
  const touchStartX = useRef(null);
  const touchStartY = useRef(null);

  // Handle touch swipe gestures for mobile navigation
  const handleTouchStart = (e) => {
    touchStartX.current = e.touches[0].clientX;
    touchStartY.current = e.touches[0].clientY;
  };

  const handleTouchEnd = (e) => {
    if (touchStartX.current === null || isLive) return;

    const touchEndX = e.changedTouches[0].clientX;
    const touchEndY = e.changedTouches[0].clientY;
    const deltaX = touchEndX - touchStartX.current;
    const deltaY = touchEndY - touchStartY.current;

    // Only trigger if horizontal swipe is dominant and significant
    const minSwipeDistance = 50;
    if (Math.abs(deltaX) > Math.abs(deltaY) && Math.abs(deltaX) > minSwipeDistance) {
      if (deltaX > 0 && onPrev) {
        // Swipe right -> previous
        onPrev();
      } else if (deltaX < 0 && onNext) {
        // Swipe left -> next
        onNext();
      }
    }

    touchStartX.current = null;
    touchStartY.current = null;
  };

  // Preload new images and crossfade when ready
  useEffect(() => {
    if (!point?.image) {
      setCurrentImageUrl(null);
      setPreviousImageUrl(null);
      return;
    }

    const displayUrl = getDisplayUrl(point.image);

    // If it's the same image, no need to reload
    if (displayUrl === currentImageUrl) {
      return;
    }

    // Swap images: current becomes previous (backdrop), new becomes current
    const swapImages = (newUrl) => {
      setPreviousImageUrl(currentImageUrl);
      setCurrentImageUrl(newUrl);
    };

    // If already in our prefetch cache, swap immediately
    if (cachedImages?.current?.has(displayUrl)) {
      swapImages(displayUrl);
      return;
    }

    // Preload the new image, then swap
    const img = new Image();
    img.onload = () => {
      cachedImages?.current?.add(displayUrl);
      swapImages(displayUrl);
    };
    img.onerror = () => {
      // Still show the image even if preload fails
      swapImages(displayUrl);
    };
    img.src = displayUrl;
  }, [point?.image, currentImageUrl, cachedImages]);

  // Use Pacific Time for BC/Yukon trip
  const formatTime = (date) =>
    date.toLocaleDateString("en-CA", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "America/Vancouver",
    });

  if (!point) return null;

  const iconSize = isMobile ? "h-12 w-12" : "h-16 w-16";

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Header */}
      <div
        className={`flex-none px-4 py-3 border-b ${isLive ? "border-red-500/30 bg-red-500/5" : "border-gray-200"}`}
      >
        <div className="flex items-center justify-between">
          <div>
            {isLive && (
              <div className="flex items-center gap-2 mb-1">
                <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                <span className="text-xs font-medium text-red-600">
                  LIVE VIEW
                </span>
              </div>
            )}
            <a
              href={`https://www.google.com/maps?q=${point.lat},${point.lng}`}
              target="_blank"
              rel="noopener noreferrer"
              className="font-semibold text-lg text-gray-900 hover:text-blue-600 transition-colors"
            >
              {Math.abs(point.lat).toFixed(2)}°{point.lat >= 0 ? "N" : "S"},{" "}
              {Math.abs(point.lng).toFixed(2)}°{point.lng >= 0 ? "E" : "W"} ↗
            </a>
            <p className="text-sm text-gray-500">
              {formatTime(point.timestamp)}
            </p>
          </div>
          <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
            {point.source}
          </span>
        </div>
      </div>

      {/* Main Image Area */}
      <div
        className="flex-1 relative min-h-0 p-4"
        onTouchStart={isMobile ? handleTouchStart : undefined}
        onTouchEnd={isMobile ? handleTouchEnd : undefined}
      >
        <div
          className={`w-full h-full rounded-lg overflow-hidden flex items-center justify-center bg-gray-900 ${isLive ? "ring-2 ring-red-500/30" : ""}`}
        >
          {currentImageUrl ? (
            <div className="relative w-full h-full flex items-center justify-center">
              {/* Previous image (stays visible as backdrop during transition) */}
              {previousImageUrl && (
                <img
                  src={previousImageUrl}
                  alt=""
                  className="absolute inset-0 w-full h-full object-contain"
                  decoding="async"
                />
              )}
              {/* Current image (always on top, visible immediately since it's preloaded) */}
              <img
                src={currentImageUrl}
                alt="Trip photo"
                className="absolute inset-0 w-full h-full object-contain cursor-pointer hover:opacity-90"
                onClick={() => onImageClick?.(currentImageUrl)}
                title="Click to view fullscreen"
                fetchPriority="high"
                decoding="async"
              />
            </div>
          ) : point.image ? (
            // Show loading state while first image loads
            <div className="text-center">
              <Camera
                className={`${iconSize} mx-auto mb-3 animate-pulse ${isLive ? "text-red-500/40" : "text-gray-600"}`}
              />
              <p className="text-gray-500 text-sm font-mono">Loading...</p>
            </div>
          ) : (
            <div className="text-center">
              <Camera
                className={`${iconSize} mx-auto mb-3 ${isLive ? "text-red-500/40" : "text-gray-600"}`}
              />
              <p className="text-gray-500 text-sm font-mono">No image</p>
            </div>
          )}
        </div>

        {/* Live indicator overlay */}
        {isLive && (
          <div className="absolute top-6 left-6 flex items-center gap-2 bg-red-500/90 text-white px-3 py-1.5 rounded-full text-sm font-medium">
            <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
            LIVE
          </div>
        )}
      </div>

      {/* Metadata Footer */}
      <div className="flex-none px-4 py-3 border-t border-gray-200 bg-gray-50">
        <div
          className={`grid ${isMobile ? "grid-cols-2" : "grid-cols-3"} gap-4 text-sm text-gray-900`}
        >
          <div>
            <span className="text-gray-500 block text-xs mb-0.5">
              Coordinates
            </span>
            <span className="font-mono">
              {point.lat.toFixed(4)}, {point.lng.toFixed(4)}
            </span>
          </div>
          <div>
            <span className="text-gray-500 block text-xs mb-0.5">Day</span>
            <span>
              {currentDay} of {totalDays}
            </span>
          </div>
          {!isMobile && (
            <div>
              <span className="text-gray-500 block text-xs mb-0.5">Frame</span>
              <span className="font-mono">
                {currentIndex + 1} / {totalFrames}
              </span>
            </div>
          )}
        </div>
        {/* Tags display (filter out internal tags like "gap") */}
        {point.tags && point.tags.filter((t) => t.toLowerCase() !== "gap").length > 0 && (
          <div className="mt-2 pt-2 border-t border-gray-200">
            <div className="flex items-center gap-2 flex-wrap">
              <Tag className="w-3 h-3 text-gray-400" />
              {point.tags.filter((t) => t.toLowerCase() !== "gap").map((tag) => (
                <span
                  key={tag}
                  className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full text-xs font-medium"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================
// Main App Component
// ============================================

// ============================================
// URL State Hook - Deep linking support
// ============================================

function useUrlState() {
  // Parse initial frame from URL
  const getInitialFrame = useCallback(() => {
    const params = new URLSearchParams(window.location.search);
    const frame = params.get("frame");
    if (frame) {
      const parsed = parseInt(frame, 10);
      if (!isNaN(parsed) && parsed >= 0) {
        return parsed;
      }
    }
    return null; // null means "use default" (latest frame)
  }, []);

  // Parse initial tags from URL (comma-separated)
  const getInitialTags = useCallback(() => {
    const params = new URLSearchParams(window.location.search);
    const tags = params.get("tags");
    if (tags) {
      return tags.split(",").map((t) => t.trim().toLowerCase()).filter(Boolean);
    }
    return [];
  }, []);

  // Update URL without adding history entry
  const updateUrl = useCallback((frame, tags = []) => {
    const url = new URL(window.location.href);
    if (frame !== null && frame !== undefined) {
      url.searchParams.set("frame", frame.toString());
    } else {
      url.searchParams.delete("frame");
    }
    if (tags && tags.length > 0) {
      url.searchParams.set("tags", tags.join(","));
    } else {
      url.searchParams.delete("tags");
    }
    window.history.replaceState({}, "", url.toString());
  }, []);

  return { getInitialFrame, getInitialTags, updateUrl };
}

export default function App() {
  // Fetch trip data from API
  const { points: rawTripData, loading, error, stats } = useTripData();
  const { getInitialFrame, getInitialTags, updateUrl } = useUrlState();

  // All points including gaps - used for map route rendering
  // Gap points (image: null) are included to draw continuous route lines
  const mapPoints = useMemo(() => {
    return [...rawTripData].sort((a, b) => a.timestamp - b.timestamp);
  }, [rawTripData]);

  // Deduplicate images for timeline/thumbnails:
  // - Gap points (no image): excluded entirely - only for map rendering
  // - "car" tagged images: keep only 1 per minute (continuous driving footage)
  // - Other tags (hotspring, etc): keep ALL images (intentional moments)
  const tripData = useMemo(() => {
    if (rawTripData.length === 0) return [];

    // Filter out gap points (no image) - they're only for map route rendering
    const pointsWithImages = rawTripData.filter((p) => p.image !== null);

    // Separate car-only images from images with other tags
    const carOnlyImages = [];
    const specialImages = []; // Images with tags other than "car"

    for (const point of pointsWithImages) {
      const tags = point.tags?.map((t) => t.toLowerCase()) || [];
      const hasNonCarTag = tags.some((t) => t !== "car" && t !== "gap");

      if (hasNonCarTag) {
        // Has a special tag (hotspring, etc) - keep all of these
        specialImages.push(point);
      } else {
        // Only has "car" tag or no tags - apply sampling
        carOnlyImages.push(point);
      }
    }

    // Apply 1-per-minute deduplication only to car images
    const byMinute = new Map();
    for (const point of carOnlyImages) {
      const minuteKey = point.timestamp.toISOString().slice(0, 16);
      const existing = byMinute.get(minuteKey);
      if (!existing || point.timestamp < existing.timestamp) {
        byMinute.set(minuteKey, point);
      }
    }

    // Combine sampled car images with all special images
    const combined = [...Array.from(byMinute.values()), ...specialImages];

    // Return sorted by timestamp
    return combined.sort((a, b) => a.timestamp - b.timestamp);
  }, [rawTripData]);

  // Extract all unique tags from trip data (excluding internal tags like "gap")
  const availableTags = useMemo(() => {
    const tagSet = new Set();
    const hiddenTags = ["gap"]; // Internal tags not shown in UI
    for (const point of rawTripData) {
      if (point.tags) {
        for (const tag of point.tags) {
          const lowered = tag.toLowerCase();
          if (!hiddenTags.includes(lowered)) {
            tagSet.add(lowered);
          }
        }
      }
    }
    return Array.from(tagSet).sort();
  }, [rawTripData]);

  // Tag filter state (must be defined before filteredTripData)
  const [selectedTags, setSelectedTags] = useState(() => getInitialTags());

  // Filter trip data by selected tags (if any tags selected)
  const filteredTripData = useMemo(() => {
    if (selectedTags.length === 0) return tripData;
    return tripData.filter((point) =>
      point.tags?.some((t) => selectedTags.includes(t.toLowerCase()))
    );
  }, [tripData, selectedTags]);

  // Get indices in tripData for filtered points (for constrained navigation)
  const filteredIndices = useMemo(() => {
    if (selectedTags.length === 0) return null; // No constraint
    const indices = [];
    tripData.forEach((point, idx) => {
      if (point.tags?.some((t) => selectedTags.includes(t.toLowerCase()))) {
        indices.push(idx);
      }
    });
    return indices;
  }, [tripData, selectedTags]);

  // Navigation helpers for tag-constrained movement
  const getNextFilteredIndex = useCallback((currentIdx) => {
    if (!filteredIndices) return Math.min(tripData.length - 1, currentIdx + 1);
    const nextIdx = filteredIndices.find((i) => i > currentIdx);
    return nextIdx !== undefined ? nextIdx : currentIdx; // Stay at current if at end
  }, [filteredIndices, tripData.length]);

  const getPrevFilteredIndex = useCallback((currentIdx) => {
    if (!filteredIndices) return Math.max(0, currentIdx - 1);
    // Find the last index that's less than currentIdx
    for (let i = filteredIndices.length - 1; i >= 0; i--) {
      if (filteredIndices[i] < currentIdx) return filteredIndices[i];
    }
    return currentIdx; // Stay at current if at beginning
  }, [filteredIndices]);

  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  // Check if we can navigate in a direction (for disabling buttons)
  // Must be after selectedIndex is declared
  const canGoPrev = useMemo(() => {
    if (!filteredIndices) return selectedIndex > 0;
    return filteredIndices.some((i) => i < selectedIndex);
  }, [filteredIndices, selectedIndex]);

  const canGoNext = useMemo(() => {
    if (!filteredIndices) return selectedIndex < tripData.length - 1;
    return filteredIndices.some((i) => i > selectedIndex);
  }, [filteredIndices, selectedIndex, tripData.length]);
  const [playbackSpeed, setPlaybackSpeed] = useState(10);
  const [isLive, setIsLive] = useState(false);
  const [mapExpanded, setMapExpanded] = useState(false);
  const [mobileView, setMobileView] = useState("image"); // 'image' or 'map'
  const [scrollVisibleCenter, setScrollVisibleCenter] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const scrollRef = useRef(null);
  const imageRefs = useRef({});
  const cachedImages = useRef(new Set());

  // Media queries for responsive design
  const isMobile = useMediaQuery("(max-width: 768px)");
  const isTablet = useMediaQuery("(max-width: 1024px)");

  // Track if we've done the initial position setup
  const initializedRef = useRef(false);

  // Initialize selected index from URL or default to latest (only on first load)
  useEffect(() => {
    if (tripData.length > 0 && !initializedRef.current) {
      initializedRef.current = true;
      const urlFrame = getInitialFrame();
      if (urlFrame !== null && urlFrame < tripData.length) {
        setSelectedIndex(urlFrame);
      } else {
        setSelectedIndex(tripData.length - 1);
      }
    }
  }, [tripData.length, getInitialFrame]);

  // Sync URL with current frame and tags (debounced to avoid excessive updates)
  useEffect(() => {
    if (tripData.length === 0) return;
    updateUrl(selectedIndex, selectedTags);
  }, [selectedIndex, selectedTags, tripData.length, updateUrl]);

  // Jump to first filtered image when tags are applied
  useEffect(() => {
    if (filteredIndices && filteredIndices.length > 0) {
      // Check if current selection is not in the filtered set
      if (!filteredIndices.includes(selectedIndex)) {
        setSelectedIndex(filteredIndices[0]);
        setIsLive(false);
        setIsPlaying(false);
      }
    }
  }, [filteredIndices]); // Only trigger when filter changes, not when selectedIndex changes

  const selectedPoint = tripData[selectedIndex];
  const selectedId = selectedPoint?.id;

  // Calculate day boundaries for timeline markers
  const dayBoundaries = useMemo(() => {
    if (tripData.length === 0) return [];

    const boundaries = [];
    let currentDate = null;

    tripData.forEach((point, index) => {
      // Get date string in Pacific Time (for BC/Yukon trip)
      const dateStr = point.timestamp.toLocaleDateString("en-CA", {
        timeZone: "America/Vancouver",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      });

      if (dateStr !== currentDate) {
        boundaries.push({
          index,
          date: point.timestamp,
          dateStr,
          dayNumber: boundaries.length + 1,
        });
        currentDate = dateStr;
      }
    });

    return boundaries;
  }, [tripData]);

  // Calculate which day the current selection is on
  const currentDay = useMemo(() => {
    if (dayBoundaries.length === 0) return 1;
    // Find the last day boundary that's <= selectedIndex
    for (let i = dayBoundaries.length - 1; i >= 0; i--) {
      if (dayBoundaries[i].index <= selectedIndex) {
        return dayBoundaries[i].dayNumber;
      }
    }
    return 1;
  }, [dayBoundaries, selectedIndex]);

  const latestIndex = tripData.length - 1;
  const latestPoint = tripData[latestIndex];

  // Fetch weather for the latest point's location
  const { weather } = useWeather(latestPoint?.lat, latestPoint?.lng);

  // All hooks must be called before any early returns
  useEffect(() => {
    if (isLive && tripData.length > 0) {
      setSelectedIndex(latestIndex);
      setIsPlaying(false);
    }
  }, [isLive, latestIndex, tripData.length]);

  // Prefetch images ahead during playback
  const prefetchImage = useCallback(
    (index) => {
      if (index < 0 || index >= tripData.length) return Promise.resolve();
      const point = tripData[index];
      if (!point?.image) return Promise.resolve();

      const displayUrl = getDisplayUrl(point.image);
      if (cachedImages.current.has(displayUrl)) return Promise.resolve();

      return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => {
          cachedImages.current.add(displayUrl);
          resolve();
        };
        img.onerror = () => {
          cachedImages.current.add(displayUrl); // Mark as "attempted" even on error
          resolve();
        };
        img.src = displayUrl;
      });
    },
    [tripData],
  );

  // Prefetch ahead when playback starts or index changes during playback
  useEffect(() => {
    if (!isPlaying || isLive || tripData.length === 0) return;

    // Prefetch the next several images based on speed
    // Higher speed = more prefetch needed
    const prefetchCount = Math.min(Math.ceil(playbackSpeed / 2) + 3, 20);

    for (let i = 1; i <= prefetchCount; i++) {
      prefetchImage(selectedIndex + i);
    }
  }, [
    isPlaying,
    selectedIndex,
    playbackSpeed,
    isLive,
    tripData.length,
    prefetchImage,
  ]);

  // Playback: only advance when next image is cached (respects tag filter)
  useEffect(() => {
    let interval;
    if (isPlaying && !isLive && tripData.length > 0) {
      interval = setInterval(() => {
        setSelectedIndex((prev) => {
          const nextIdx = getNextFilteredIndex(prev);

          // If we can't advance, stop playing
          if (nextIdx === prev) {
            setIsPlaying(false);
            return prev;
          }

          // Check if next image is cached
          const nextPoint = tripData[nextIdx];
          if (nextPoint?.image) {
            const nextUrl = getDisplayUrl(nextPoint.image);
            if (!cachedImages.current.has(nextUrl)) {
              // Not cached yet, wait for it
              return prev;
            }
          }

          return nextIdx;
        });
      }, 1000 / playbackSpeed);
    }
    return () => clearInterval(interval);
  }, [isPlaying, playbackSpeed, isLive, tripData.length, tripData, getNextFilteredIndex]);

  // Continuous priority-based prefetching: prefetch images around current selection
  // Priority order: closest to selected index first (N±1, then N±2, etc.)
  useEffect(() => {
    if (tripData.length === 0) return;

    const prefetchRadius = 10; // 10 images on each side = 20 total buffer

    // Prefetch in priority order: closest to selected first
    for (let distance = 1; distance <= prefetchRadius; distance++) {
      const prevIdx = selectedIndex - distance;
      const nextIdx = selectedIndex + distance;

      if (prevIdx >= 0) {
        prefetchImage(prevIdx);
      }
      if (nextIdx < tripData.length) {
        prefetchImage(nextIdx);
      }
    }
  }, [selectedIndex, tripData.length, prefetchImage]);

  useEffect(() => {
    const el = imageRefs.current[selectedId];
    if (el)
      el.scrollIntoView({
        behavior: "smooth",
        inline: "center",
        block: "nearest",
      });
  }, [selectedId]);

  // Keyboard navigation: Left/Right arrows to scrub through photos
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Don't interfere if user is typing in an input or select
      if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
      // Don't navigate when in live mode or fullscreen (fullscreen has its own handler)
      if (isLive || isFullscreen) return;

      if (e.key === "ArrowLeft") {
        e.preventDefault();
        setSelectedIndex((prev) => getPrevFilteredIndex(prev));
        setIsPlaying(false);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        setSelectedIndex((prev) => getNextFilteredIndex(prev));
        setIsPlaying(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isLive, isFullscreen, tripData.length, getPrevFilteredIndex, getNextFilteredIndex]);

  // Track scroll position to load thumbnails in visible area
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;

    const thumbWidth = isMobile ? 52 : 68; // thumbnail width + gap

    const handleScroll = () => {
      const scrollLeft = container.scrollLeft;
      const containerWidth = container.clientWidth;
      const centerScroll = scrollLeft + containerWidth / 2;
      const centerIndex = Math.floor(centerScroll / thumbWidth);
      setScrollVisibleCenter(centerIndex);
    };

    // Initial calculation
    handleScroll();

    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => container.removeEventListener("scroll", handleScroll);
  }, [isMobile, tripData.length]);

  const handleMarkerClick = useCallback(
    (id) => {
      const idx = tripData.findIndex((p) => p.id === id);
      if (idx !== -1) {
        setSelectedIndex(idx);
        setIsPlaying(false);
        if (idx !== latestIndex) {
          setIsLive(false);
        }
      }
    },
    [tripData, latestIndex],
  );

  // Calculate visible range based on both selected index and scroll position
  // This ensures thumbnails load when scrolling, not just when selecting
  const visibleRange = useMemo(() => {
    const buffer = 50; // thumbnails on each side of center
    const preloadPadding = 30; // extra thumbnails to preload at edges

    // Range around selected index (for when selection changes)
    const selectedStart = selectedIndex - buffer;
    const selectedEnd = selectedIndex + buffer;

    // Range around scroll center (for when user scrolls manually)
    const scrollStart = scrollVisibleCenter - buffer;
    const scrollEnd = scrollVisibleCenter + buffer;

    // Combine both ranges and add preload padding
    const start = Math.max(0, Math.min(selectedStart, scrollStart) - preloadPadding);
    const end = Math.min(tripData.length, Math.max(selectedEnd, scrollEnd) + preloadPadding);

    return { start, end };
  }, [selectedIndex, scrollVisibleCenter, tripData.length]);

  // Show loading screen
  if (loading) {
    return (
      <div className="h-dvh w-full bg-gray-50 text-gray-900 flex flex-col items-center justify-center gap-4">
        <Loader2 className="h-12 w-12 animate-spin text-blue-500" />
        <p className="text-gray-500">Loading trip data...</p>
      </div>
    );
  }

  // Handle empty data state
  if (tripData.length === 0) {
    return (
      <div className="h-dvh w-full bg-gray-50 text-gray-900 flex flex-col items-center justify-center gap-4">
        <AlertCircle className="h-12 w-12 text-amber-500" />
        <p className="text-gray-600">No trip data available</p>
        <p className="text-gray-500 text-sm">
          The trip hasn't started yet or data is unavailable.
        </p>
      </div>
    );
  }

  // Show error banner if API failed
  const showErrorBanner = !!error;

  const handleTimelineChange = (newIndex) => {
    setSelectedIndex(newIndex);
    setIsPlaying(false);
    if (newIndex !== latestIndex) {
      setIsLive(false);
    }
  };

  const toggleLive = () => {
    setIsLive(!isLive);
  };

  // Use Pacific Time for BC/Yukon trip
  const formatTime = (date) =>
    date.toLocaleDateString("en-CA", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "America/Vancouver",
    });

  const formatTimeShort = (date) =>
    date.toLocaleTimeString("en-CA", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "America/Vancouver",
    });

  return (
    <div className="h-dvh w-full bg-gray-50 text-gray-900 flex flex-col overflow-hidden">
      <style>{`
        @keyframes pulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.2); opacity: 0.8; }
        }
      `}</style>

      {/* Status Bar */}
      <div className="flex-none border-b border-gray-200 bg-white/80 backdrop-blur-sm px-4 py-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 md:gap-4">
            <div className="flex items-center gap-2">
              <div
                className={`h-2 w-2 rounded-full ${isLive ? "bg-red-500" : "bg-emerald-500"} animate-pulse`}
              />
              {!isMobile && (
                <span className="text-sm font-medium text-gray-900">Winter Road Trip to Liard Hot Springs</span>
              )}
            </div>
            <div className="bg-emerald-500/20 text-emerald-600 px-2 py-0.5 rounded text-xs font-medium flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
              Live Trip
            </div>
            {isMobile && (
              <ViewToggle
                activeView={mobileView}
                onViewChange={setMobileView}
              />
            )}
            <LiveBadge
              isLive={isLive}
              onToggle={toggleLive}
              viewerCount={stats.viewers > 0 ? stats.viewers : null}
              compact={isMobile}
            />
            {isMobile && availableTags.length > 0 && (
              <TagFilter
                availableTags={availableTags}
                selectedTags={selectedTags}
                onTagsChange={setSelectedTags}
                isMobile={true}
              />
            )}
          </div>
          {!isMobile && availableTags.length > 0 && (
            <TagFilter
              availableTags={availableTags}
              selectedTags={selectedTags}
              onTagsChange={setSelectedTags}
              isMobile={false}
            />
          )}
          {!isMobile && weather && (
            <div className="flex items-center gap-3 text-sm text-gray-600">
              <MapPin className="h-3 w-3 text-gray-400" />
              <span>{weather.temp}°C</span>
              {!isTablet && <span>{getWeatherDescription(weather.symbol)}</span>}
              <span className="flex items-center gap-1">
                <Wind className="h-3 w-3" />
                {weather.windSpeed} km/h
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Error Banner */}
      {showErrorBanner && (
        <div className="flex-none bg-amber-500/10 border-b border-amber-500/20 px-4 py-2">
          <div className="flex items-center gap-2 text-sm text-amber-600">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span>Unable to connect to API: {error}</span>
          </div>
        </div>
      )}

      {/* Main Content - Split View / Tabbed View */}
      <div className="flex-1 flex min-h-0">
        {isMobile ? (
          // Mobile: Tabbed view
          <>
            {/* Map Panel - shown when mobileView === 'map' */}
            <div
              className={`relative w-full ${mobileView === "map" ? "block" : "hidden"}`}
            >
              <TripMap
                points={mapPoints}
                selectablePoints={tripData}
                selectedId={selectedId}
                onMarkerClick={handleMarkerClick}
                isLive={isLive}
              />

              {/* Stats Overlay */}
              <div className="absolute top-3 left-3 z-10">
                <div className="bg-white/90 border border-gray-200 rounded-lg p-3 backdrop-blur-sm shadow-sm">
                  <div className="text-xl font-bold text-gray-900">
                    {tripData.length.toLocaleString()}
                  </div>
                  <div className="text-xs text-gray-500">Photos</div>
                </div>
              </div>

              {/* Position indicator */}
              <div className="absolute bottom-3 left-3 z-10">
                <div className="bg-white/90 border border-gray-200 rounded-lg p-2 backdrop-blur-sm shadow-sm">
                  <div className="flex items-center gap-1.5 text-xs">
                    <div
                      className={`w-3 h-3 rounded-full border-2 border-white ${isLive ? "bg-red-500" : "bg-blue-500"}`}
                    />
                    <span className="text-gray-600">
                      {isLive ? "Live" : "Position"}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Image Panel - shown when mobileView === 'image' */}
            <div
              className={`w-full ${mobileView === "image" ? "block" : "hidden"}`}
            >
              <ImagePanel
                point={selectedPoint}
                isLive={isLive}
                totalFrames={tripData.length}
                currentIndex={selectedIndex}
                currentDay={currentDay}
                totalDays={dayBoundaries.length}
                isMobile={isMobile}
                cachedImages={cachedImages}
                onImageClick={() => setIsFullscreen(true)}
                onPrev={canGoPrev ? () => {
                  setSelectedIndex(getPrevFilteredIndex(selectedIndex));
                  setIsPlaying(false);
                  setIsLive(false);
                } : null}
                onNext={canGoNext ? () => {
                  const nextIdx = getNextFilteredIndex(selectedIndex);
                  setSelectedIndex(nextIdx);
                  setIsPlaying(false);
                  if (nextIdx !== tripData.length - 1) setIsLive(false);
                } : null}
              />
            </div>
          </>
        ) : (
          // Desktop: Side-by-side split view
          <>
            {/* Map Panel */}
            <div
              className={`relative transition-all duration-300 ${mapExpanded ? "w-2/3" : "w-1/2"}`}
            >
              <TripMap
                points={mapPoints}
                selectablePoints={tripData}
                selectedId={selectedId}
                onMarkerClick={handleMarkerClick}
                isLive={isLive}
              />

              {/* Stats Overlay */}
              <div className="absolute top-3 left-3 z-10">
                <div className="bg-white/90 border border-gray-200 rounded-lg p-3 backdrop-blur-sm shadow-sm">
                  <div className="text-xl font-bold text-gray-900">
                    {tripData.length.toLocaleString()}
                  </div>
                  <div className="text-xs text-gray-500">Photos</div>
                </div>
              </div>

              {/* Position indicator */}
              <div className="absolute bottom-3 left-3 z-10">
                <div className="bg-white/90 border border-gray-200 rounded-lg p-2 backdrop-blur-sm shadow-sm">
                  <div className="flex items-center gap-1.5 text-xs">
                    <div
                      className={`w-3 h-3 rounded-full border-2 border-white ${isLive ? "bg-red-500" : "bg-blue-500"}`}
                    />
                    <span className="text-gray-600">
                      {isLive ? "Live" : "Position"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Expand/Collapse Toggle */}
              <button
                onClick={() => setMapExpanded(!mapExpanded)}
                className="absolute top-3 right-14 z-10 p-2 bg-white/90 border border-gray-200 rounded-lg backdrop-blur-sm shadow-sm hover:bg-gray-100 transition-colors text-gray-700"
              >
                {mapExpanded ? (
                  <Minimize2 className="h-4 w-4" />
                ) : (
                  <Maximize2 className="h-4 w-4" />
                )}
              </button>
            </div>

            {/* Divider */}
            <div
              className={`w-px ${isLive ? "bg-red-500/30" : "bg-gray-200"}`}
            />

            {/* Image Panel */}
            <div
              className={`transition-all duration-300 ${mapExpanded ? "w-1/3" : "w-1/2"}`}
            >
              <ImagePanel
                point={selectedPoint}
                isLive={isLive}
                totalFrames={tripData.length}
                currentIndex={selectedIndex}
                currentDay={currentDay}
                totalDays={dayBoundaries.length}
                isMobile={isMobile}
                cachedImages={cachedImages}
                onImageClick={() => setIsFullscreen(true)}
              />
            </div>
          </>
        )}
      </div>

      {/* Fullscreen Image Modal */}
      {isFullscreen && selectedPoint?.image && (
        <FullscreenModal
          imageUrl={getDisplayUrl(selectedPoint.image)}
          onClose={() => setIsFullscreen(false)}
          onPrev={canGoPrev ? () => {
            setSelectedIndex(getPrevFilteredIndex(selectedIndex));
            setIsPlaying(false);
            setIsLive(false);
          } : null}
          onNext={canGoNext ? () => {
            const nextIdx = getNextFilteredIndex(selectedIndex);
            setSelectedIndex(nextIdx);
            setIsPlaying(false);
            if (nextIdx !== tripData.length - 1) {
              setIsLive(false);
            }
          } : null}
        />
      )}

      {/* Timeline Controls */}
      <div
        className={`flex-none border-t bg-white/90 backdrop-blur-sm px-4 py-2 transition-colors ${
          isLive ? "border-red-500/30" : "border-gray-200"
        }`}
      >
        <div className="flex items-center gap-3">
          <div
            className={`flex items-center gap-1 ${isLive ? "opacity-50" : ""}`}
          >
            <button
              onClick={() =>
                handleTimelineChange(getPrevFilteredIndex(selectedIndex))
              }
              className={`${isMobile ? "p-2" : "p-1.5"} rounded hover:bg-gray-200 transition-colors disabled:opacity-30 text-gray-700`}
              disabled={!canGoPrev || isLive}
            >
              <ChevronLeft className={isMobile ? "h-5 w-5" : "h-4 w-4"} />
            </button>
            <button
              onClick={() => setIsPlaying(!isPlaying)}
              className={`${isMobile ? "p-2" : "p-1.5"} rounded transition-colors ${isPlaying ? "bg-blue-500 text-white" : "hover:bg-gray-200 text-gray-700"}`}
              disabled={isLive}
            >
              {isPlaying ? (
                <Pause className={isMobile ? "h-5 w-5" : "h-4 w-4"} />
              ) : (
                <Play className={isMobile ? "h-5 w-5" : "h-4 w-4"} />
              )}
            </button>
            <button
              onClick={() =>
                handleTimelineChange(getNextFilteredIndex(selectedIndex))
              }
              className={`${isMobile ? "p-2" : "p-1.5"} rounded hover:bg-gray-200 transition-colors disabled:opacity-30 text-gray-700`}
              disabled={!canGoNext || isLive}
            >
              <ChevronRight className={isMobile ? "h-5 w-5" : "h-4 w-4"} />
            </button>
          </div>

          {!isMobile && (
            <select
              value={playbackSpeed}
              onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
              className="bg-gray-100 border border-gray-300 rounded px-2 py-1 text-xs text-gray-700 disabled:opacity-50"
              disabled={isLive}
            >
              <option value={1}>1x</option>
              <option value={5}>5x</option>
              <option value={10}>10x</option>
              <option value={30}>30x</option>
            </select>
          )}

          {/* Day Navigator */}
          {!isMobile && dayBoundaries.length > 1 && (
            <div className={`flex items-center gap-1 ${isLive ? "opacity-50" : ""}`}>
              <button
                onClick={() => {
                  const prevDay = dayBoundaries.find((d) => d.dayNumber === currentDay - 1);
                  if (prevDay) handleTimelineChange(prevDay.index);
                }}
                className="p-1 rounded hover:bg-gray-200 transition-colors disabled:opacity-30 text-gray-700"
                disabled={currentDay === 1 || isLive}
                title="Previous day"
              >
                <ChevronLeft className="h-3 w-3" />
              </button>
              <span className="text-xs text-gray-500 min-w-[45px] text-center font-medium">
                Day {currentDay}
              </span>
              <button
                onClick={() => {
                  const nextDay = dayBoundaries.find((d) => d.dayNumber === currentDay + 1);
                  if (nextDay) handleTimelineChange(nextDay.index);
                }}
                className="p-1 rounded hover:bg-gray-200 transition-colors disabled:opacity-30 text-gray-700"
                disabled={currentDay === dayBoundaries.length || isLive}
                title="Next day"
              >
                <ChevronRight className="h-3 w-3" />
              </button>
            </div>
          )}

          <div className="flex-1 relative">
            <input
              type="range"
              min={0}
              max={tripData.length - 1}
              value={selectedIndex}
              onChange={(e) => handleTimelineChange(Number(e.target.value))}
              className={`w-full ${isMobile ? "h-2" : "h-1.5"} bg-gray-200 rounded-lg appearance-none cursor-pointer ${
                isLive ? "accent-red-500 opacity-50" : "accent-blue-500"
              }`}
              disabled={isLive}
            />
          </div>

          <div
            className={`text-xs ${isMobile ? "min-w-[60px]" : "min-w-[100px]"} text-right`}
          >
            {isLive ? (
              <span className="text-red-500 flex items-center gap-1 justify-end">
                <Radio className="w-3 h-3 animate-pulse" />
                {!isMobile && "Live"}
              </span>
            ) : (
              <span className="text-gray-500">
                {selectedPoint &&
                  (isMobile
                    ? formatTimeShort(selectedPoint.timestamp)
                    : formatTime(selectedPoint.timestamp))}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Image Reel */}
      <div
        className={`flex-none border-t bg-gray-100 overflow-x-auto transition-colors ${
          isLive ? "border-red-500/30" : selectedTags.length > 0 ? "border-blue-500/30" : "border-gray-200"
        }`}
        ref={scrollRef}
      >
        {/* Filter indicator */}
        {selectedTags.length > 0 && (
          <div className="flex items-center gap-2 px-3 py-1 bg-blue-50 border-b border-blue-100 text-xs text-blue-600">
            <Tag className="w-3 h-3" />
            <span>
              Showing {filteredTripData.length} of {tripData.length} photos with tags: {selectedTags.join(", ")}
            </span>
          </div>
        )}
        <div
          className={`flex ${isMobile ? "gap-1 p-1.5" : "gap-1.5 p-2"}`}
          style={{ width: "max-content" }}
        >
          {selectedTags.length > 0 ? (
            // When filtering, show only filtered images (no virtualization for now)
            filteredTripData.map((point) => {
              const isSelected = point.id === selectedId;
              const isLatest = point.id === tripData[latestIndex].id;
              return (
                <button
                  key={point.id}
                  ref={(el) => (imageRefs.current[point.id] = el)}
                  onClick={() => handleMarkerClick(point.id)}
                  className={`flex-none relative transition-all duration-150 origin-bottom ${
                    isSelected
                      ? "ring-2 ring-blue-500 ring-offset-1 ring-offset-zinc-950 scale-105 z-10"
                      : "hover:scale-150 hover:z-20 hover:ring-1 hover:ring-zinc-500"
                  }`}
                >
                  <div
                    className={`${isMobile ? "w-12 h-8" : "w-16 h-11"} rounded overflow-hidden flex items-center justify-center bg-gray-200`}
                  >
                    <img
                      src={getThumbUrl(point.image)}
                      alt=""
                      className="w-full h-full object-cover"
                      loading="lazy"
                      decoding="async"
                    />
                  </div>
                  {isLive && isLatest && (
                    <div className="absolute -top-1 -right-1 w-3 h-3 bg-red-500 rounded-full animate-pulse border border-gray-100" />
                  )}
                </button>
              );
            })
          ) : (
            // No filter: virtualized full list
            <>
              <div style={{ width: visibleRange.start * (isMobile ? 52 : 68) }} />
              {tripData.slice(visibleRange.start, visibleRange.end).map((point) => {
                const isSelected = point.id === selectedId;
                const isLatest = point.id === tripData[latestIndex].id;
                const hasSelectedTag = point.tags?.some((t) => selectedTags.includes(t.toLowerCase()));
                return (
                  <button
                    key={point.id}
                    ref={(el) => (imageRefs.current[point.id] = el)}
                    onClick={() => handleMarkerClick(point.id)}
                    className={`flex-none relative transition-all duration-150 origin-bottom ${
                      isSelected
                        ? isLive
                          ? "ring-2 ring-red-500 ring-offset-1 ring-offset-zinc-950 scale-105 z-10"
                          : "ring-2 ring-blue-500 ring-offset-1 ring-offset-zinc-950 scale-105 z-10"
                        : hasSelectedTag
                          ? "ring-1 ring-blue-400 hover:scale-150 hover:z-20"
                          : "hover:scale-150 hover:z-20 hover:ring-1 hover:ring-zinc-500"
                    }`}
                  >
                    <div
                      className={`${isMobile ? "w-12 h-8" : "w-16 h-11"} rounded overflow-hidden flex items-center justify-center bg-gray-200`}
                    >
                      <img
                        src={getThumbUrl(point.image)}
                        alt=""
                        className="w-full h-full object-cover"
                        loading="lazy"
                        decoding="async"
                      />
                    </div>
                    {isLive && isLatest && (
                      <div className="absolute -top-1 -right-1 w-3 h-3 bg-red-500 rounded-full animate-pulse border border-gray-100" />
                    )}
                  </button>
                );
              })}
              <div
                style={{
                  width:
                    (tripData.length - visibleRange.end) * (isMobile ? 52 : 68),
                }}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
