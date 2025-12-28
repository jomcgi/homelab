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
  Map,
  Image as ImageIcon,
  Loader2,
  AlertCircle,
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
    <div className="flex bg-zinc-800 rounded-lg p-1">
      <button
        onClick={() => onViewChange("image")}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded transition-colors text-sm font-medium ${
          activeView === "image"
            ? "bg-blue-500 text-white"
            : "text-zinc-400 hover:text-zinc-300"
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
            : "text-zinc-400 hover:text-zinc-300"
        }`}
      >
        <Map className="h-4 w-4" />
        Map
      </button>
    </div>
  );
}

// ============================================
// Map Component
// ============================================

function TripMap({ points, selectedId, onMarkerClick, isLive }) {
  const mapContainer = useRef(null);
  const map = useRef(null);
  const markerRef = useRef(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const mountedRef = useRef(false);

  useEffect(() => {
    if (mountedRef.current) return;
    mountedRef.current = true;

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
      center: [-128, 56],
      zoom: 4,
    });

    map.current.addControl(new maplibregl.NavigationControl(), "top-right");

    map.current.on("load", () => {
      map.current.resize();
      const routeCoords = points.map((p) => [p.lng, p.lat]);

      map.current.addSource("route", {
        type: "geojson",
        data: {
          type: "Feature",
          properties: {},
          geometry: { type: "LineString", coordinates: routeCoords },
        },
      });

      map.current.addLayer({
        id: "route-glow",
        type: "line",
        source: "route",
        paint: {
          "line-color": "#3b82f6",
          "line-width": 6,
          "line-opacity": 0.4,
          "line-blur": 3,
        },
      });

      map.current.addLayer({
        id: "route-line",
        type: "line",
        source: "route",
        paint: {
          "line-color": "#3b82f6",
          "line-width": 2,
          "line-opacity": 0.9,
        },
      });

      // Click handler for route line - navigate to closest point
      map.current.on("click", "route-line", (e) => {
        const clickedLng = e.lngLat.lng;
        const clickedLat = e.lngLat.lat;

        // Find the closest point in tripData
        let closestId = null;
        let minDist = Infinity;

        points.forEach((p) => {
          // Simple Euclidean distance (sufficient for finding closest)
          const dist = Math.pow(p.lng - clickedLng, 2) + Math.pow(p.lat - clickedLat, 2);
          if (dist < minDist) {
            minDist = dist;
            closestId = p.id;
          }
        });

        if (closestId !== null) {
          onMarkerClick(closestId);
        }
      });

      // Also handle clicks on the glow layer for better hit area
      map.current.on("click", "route-glow", (e) => {
        const clickedLng = e.lngLat.lng;
        const clickedLat = e.lngLat.lat;

        let closestId = null;
        let minDist = Infinity;

        points.forEach((p) => {
          const dist = Math.pow(p.lng - clickedLng, 2) + Math.pow(p.lat - clickedLat, 2);
          if (dist < minDist) {
            minDist = dist;
            closestId = p.id;
          }
        });

        if (closestId !== null) {
          onMarkerClick(closestId);
        }
      });

      map.current.on("mouseenter", "route-line", () => {
        map.current.getCanvas().style.cursor = "pointer";
      });

      map.current.on("mouseleave", "route-line", () => {
        map.current.getCanvas().style.cursor = "";
      });

      map.current.on("mouseenter", "route-glow", () => {
        map.current.getCanvas().style.cursor = "pointer";
      });

      map.current.on("mouseleave", "route-glow", () => {
        map.current.getCanvas().style.cursor = "";
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

  // Update route line when points change (e.g., from WebSocket)
  useEffect(() => {
    if (!mapLoaded || !map.current) return;

    const source = map.current.getSource("route");
    if (source) {
      const routeCoords = points.map((p) => [p.lng, p.lat]);
      source.setData({
        type: "Feature",
        properties: {},
        geometry: { type: "LineString", coordinates: routeCoords },
      });
    }
  }, [mapLoaded, points]);

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
              : "bg-zinc-800 border border-zinc-700 hover:bg-zinc-700"
          }
        `}
        title={isLive ? "LIVE" : "Go Live"}
      >
        <span
          className={`
          w-3 h-3 rounded-full
          ${isLive ? "bg-red-500 animate-pulse" : "bg-zinc-500"}
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
            ? "bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30"
            : "bg-zinc-800 text-zinc-400 border border-zinc-700 hover:bg-zinc-700 hover:text-zinc-300"
        }
      `}
    >
      <span
        className={`
        w-2 h-2 rounded-full
        ${isLive ? "bg-red-500 animate-pulse" : "bg-zinc-500"}
      `}
      />
      <span>{isLive ? "LIVE" : "Go Live"}</span>
      {isLive && viewerCount !== null && (
        <span className="flex items-center gap-1 text-xs text-red-400/70 border-l border-red-500/30 pl-2 ml-1">
          <Eye className="w-3 h-3" />
          {viewerCount}
        </span>
      )}
    </button>
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
}) {
  // Track the currently displayed image (stays until new image is loaded)
  const [displayedImageUrl, setDisplayedImageUrl] = useState(null);
  const [isImageLoading, setIsImageLoading] = useState(false);

  // Preload new images before displaying them
  useEffect(() => {
    if (!point?.image) {
      setDisplayedImageUrl(null);
      return;
    }

    const displayUrl = getDisplayUrl(point.image);

    // If it's the same image, no need to reload
    if (displayUrl === displayedImageUrl) {
      return;
    }

    // If already in our prefetch cache, show immediately
    if (cachedImages?.current?.has(displayUrl)) {
      setDisplayedImageUrl(displayUrl);
      setIsImageLoading(false);
      return;
    }

    // Preload the new image
    setIsImageLoading(true);
    const img = new Image();
    img.onload = () => {
      setDisplayedImageUrl(displayUrl);
      setIsImageLoading(false);
      // Also add to cache for future reference
      cachedImages?.current?.add(displayUrl);
    };
    img.onerror = () => {
      // Still show the image even if preload fails
      setDisplayedImageUrl(displayUrl);
      setIsImageLoading(false);
    };
    img.src = displayUrl;
  }, [point?.image, displayedImageUrl, cachedImages]);

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
    <div className="h-full flex flex-col bg-zinc-900">
      {/* Header */}
      <div
        className={`flex-none px-4 py-3 border-b ${isLive ? "border-red-500/30 bg-red-500/5" : "border-zinc-800"}`}
      >
        <div className="flex items-center justify-between">
          <div>
            {isLive && (
              <div className="flex items-center gap-2 mb-1">
                <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                <span className="text-xs font-medium text-red-400">
                  LIVE VIEW
                </span>
              </div>
            )}
            <a
              href={`https://www.google.com/maps?q=${point.lat},${point.lng}`}
              target="_blank"
              rel="noopener noreferrer"
              className="font-semibold text-lg hover:text-blue-400 transition-colors"
            >
              Point #{point.id} ↗
            </a>
            <p className="text-sm text-zinc-500">
              {formatTime(point.timestamp)}
            </p>
          </div>
          <span className="text-xs text-zinc-600 bg-zinc-800 px-2 py-1 rounded">
            {point.source}
          </span>
        </div>
      </div>

      {/* Main Image Area */}
      <div className="flex-1 relative min-h-0 p-4">
        <div
          className={`w-full h-full rounded-lg overflow-hidden flex items-center justify-center bg-zinc-800 ${isLive ? "ring-2 ring-red-500/30" : ""}`}
        >
          {displayedImageUrl ? (
            <img
              key={displayedImageUrl}
              src={displayedImageUrl}
              alt="Trip photo"
              className={`w-full h-full object-contain transition-opacity duration-200 ${
                isImageLoading ? "opacity-80" : "opacity-100"
              }`}
            />
          ) : point.image ? (
            // Show loading state while first image loads
            <div className="text-center">
              <Camera
                className={`${iconSize} mx-auto mb-3 animate-pulse ${isLive ? "text-red-500/20" : "text-zinc-700"}`}
              />
              <p className="text-zinc-600 text-sm font-mono">Loading...</p>
            </div>
          ) : (
            <div className="text-center">
              <Camera
                className={`${iconSize} mx-auto mb-3 ${isLive ? "text-red-500/20" : "text-zinc-700"}`}
              />
              <p className="text-zinc-600 text-sm font-mono">No image</p>
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
      <div className="flex-none px-4 py-3 border-t border-zinc-800 bg-zinc-900/50">
        <div
          className={`grid ${isMobile ? "grid-cols-2" : "grid-cols-3"} gap-4 text-sm`}
        >
          <div>
            <span className="text-zinc-500 block text-xs mb-0.5">
              Coordinates
            </span>
            <span className="font-mono">
              {point.lat.toFixed(4)}, {point.lng.toFixed(4)}
            </span>
          </div>
          <div>
            <span className="text-zinc-500 block text-xs mb-0.5">Day</span>
            <span>
              {currentDay} of {totalDays}
            </span>
          </div>
          {!isMobile && (
            <div>
              <span className="text-zinc-500 block text-xs mb-0.5">Frame</span>
              <span className="font-mono">
                {currentIndex + 1} / {totalFrames}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================
// Main App Component
// ============================================

export default function App() {
  // Fetch trip data from API
  const { points: tripData, loading, error, stats } = useTripData();

  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(10);
  const [isLive, setIsLive] = useState(false);
  const [mapExpanded, setMapExpanded] = useState(false);
  const [mobileView, setMobileView] = useState("image"); // 'image' or 'map'
  const scrollRef = useRef(null);
  const imageRefs = useRef({});
  const cachedImages = useRef(new Set());

  // Media queries for responsive design
  const isMobile = useMediaQuery("(max-width: 768px)");
  const isTablet = useMediaQuery("(max-width: 1024px)");

  // Reset selected index when data loads
  useEffect(() => {
    if (tripData.length > 0) {
      setSelectedIndex(tripData.length - 1);
    }
  }, [tripData.length]);

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

  // Playback: only advance when next image is cached
  useEffect(() => {
    let interval;
    if (isPlaying && !isLive && tripData.length > 0) {
      interval = setInterval(() => {
        setSelectedIndex((prev) => {
          if (prev >= tripData.length - 1) {
            setIsPlaying(false);
            return prev;
          }

          // Check if next image is cached
          const nextPoint = tripData[prev + 1];
          if (nextPoint?.image) {
            const nextUrl = getDisplayUrl(nextPoint.image);
            if (!cachedImages.current.has(nextUrl)) {
              // Not cached yet, wait for it
              return prev;
            }
          }

          return prev + 1;
        });
      }, 1000 / playbackSpeed);
    }
    return () => clearInterval(interval);
  }, [isPlaying, playbackSpeed, isLive, tripData.length, tripData]);

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
      // Don't navigate when in live mode
      if (isLive) return;

      if (e.key === "ArrowLeft") {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(0, prev - 1));
        setIsPlaying(false);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        setSelectedIndex((prev) => Math.min(tripData.length - 1, prev + 1));
        setIsPlaying(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isLive, tripData.length]);

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

  // Show loading screen
  if (loading) {
    return (
      <div className="h-screen w-full bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center gap-4">
        <Loader2 className="h-12 w-12 animate-spin text-blue-500" />
        <p className="text-zinc-400">Loading trip data...</p>
      </div>
    );
  }

  // Handle empty data state
  if (tripData.length === 0) {
    return (
      <div className="h-screen w-full bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center gap-4">
        <AlertCircle className="h-12 w-12 text-amber-500" />
        <p className="text-zinc-400">No trip data available</p>
        <p className="text-zinc-500 text-sm">
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

  // Buffer enough thumbnails to cover wide screens (68px per thumbnail on desktop)
  // 50 thumbnails on each side covers ~3400px of screen width plus buffer
  const visibleRange = {
    start: Math.max(0, selectedIndex - 50),
    end: Math.min(tripData.length, selectedIndex + 50),
  };

  return (
    <div className="h-screen w-full bg-zinc-950 text-zinc-100 flex flex-col overflow-hidden">
      <style>{`
        @keyframes pulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.2); opacity: 0.8; }
        }
      `}</style>

      {/* Status Bar */}
      <div className="flex-none border-b border-zinc-800 bg-zinc-900/80 px-4 py-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 md:gap-4">
            <div className="flex items-center gap-2">
              <div
                className={`h-2 w-2 rounded-full ${isLive ? "bg-red-500" : "bg-emerald-500"} animate-pulse`}
              />
              {!isMobile && (
                <span className="text-sm font-medium">Winter Road Trip to Liard Hot Springs</span>
              )}
            </div>
            <div className="bg-emerald-500/20 text-emerald-500 px-2 py-0.5 rounded text-xs font-medium flex items-center gap-1.5">
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
          </div>
          {!isMobile && weather && (
            <div className="flex items-center gap-3 text-sm text-zinc-400">
              <MapPin className="h-3 w-3 text-zinc-500" />
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
          <div className="flex items-center gap-2 text-sm text-amber-400">
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
                points={tripData}
                selectedId={selectedId}
                onMarkerClick={handleMarkerClick}
                isLive={isLive}
              />

              {/* Stats Overlay */}
              <div className="absolute top-3 left-3 z-10">
                <div className="bg-zinc-900/90 border border-zinc-800 rounded-lg p-3 backdrop-blur-sm">
                  <div className="text-xl font-bold">
                    {tripData.length.toLocaleString()}
                  </div>
                  <div className="text-xs text-zinc-500">Photos</div>
                </div>
              </div>

              {/* Legend */}
              <div className="absolute bottom-3 left-3 z-10">
                <div className="bg-zinc-900/90 border border-zinc-800 rounded-lg p-2 backdrop-blur-sm flex gap-3 text-xs">
                  <div className="flex items-center gap-1.5">
                    <div
                      className={`w-3 h-3 rounded-full border-2 border-white ${isLive ? "bg-red-500" : "bg-blue-500"}`}
                    />
                    <span className="text-zinc-400">
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
                points={tripData}
                selectedId={selectedId}
                onMarkerClick={handleMarkerClick}
                isLive={isLive}
              />

              {/* Stats Overlay */}
              <div className="absolute top-3 left-3 z-10">
                <div className="bg-zinc-900/90 border border-zinc-800 rounded-lg p-3 backdrop-blur-sm">
                  <div className="text-xl font-bold">
                    {tripData.length.toLocaleString()}
                  </div>
                  <div className="text-xs text-zinc-500">Photos</div>
                </div>
              </div>

              {/* Legend */}
              <div className="absolute bottom-3 left-3 z-10">
                <div className="bg-zinc-900/90 border border-zinc-800 rounded-lg p-2 backdrop-blur-sm flex gap-3 text-xs">
                  <div className="flex items-center gap-1.5">
                    <div
                      className={`w-3 h-3 rounded-full border-2 border-white ${isLive ? "bg-red-500" : "bg-blue-500"}`}
                    />
                    <span className="text-zinc-400">
                      {isLive ? "Live" : "Position"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Expand/Collapse Toggle */}
              <button
                onClick={() => setMapExpanded(!mapExpanded)}
                className="absolute top-3 right-14 z-10 p-2 bg-zinc-900/90 border border-zinc-800 rounded-lg backdrop-blur-sm hover:bg-zinc-800 transition-colors"
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
              className={`w-px ${isLive ? "bg-red-500/30" : "bg-zinc-800"}`}
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
              />
            </div>
          </>
        )}
      </div>

      {/* Timeline Controls */}
      <div
        className={`flex-none border-t bg-zinc-900/90 px-4 py-2 transition-colors ${
          isLive ? "border-red-500/30" : "border-zinc-800"
        }`}
      >
        <div className="flex items-center gap-3">
          <div
            className={`flex items-center gap-1 ${isLive ? "opacity-50" : ""}`}
          >
            <button
              onClick={() =>
                handleTimelineChange(Math.max(0, selectedIndex - 1))
              }
              className={`${isMobile ? "p-2" : "p-1.5"} rounded hover:bg-zinc-800 transition-colors disabled:opacity-30`}
              disabled={selectedIndex === 0 || isLive}
            >
              <ChevronLeft className={isMobile ? "h-5 w-5" : "h-4 w-4"} />
            </button>
            <button
              onClick={() => setIsPlaying(!isPlaying)}
              className={`${isMobile ? "p-2" : "p-1.5"} rounded transition-colors ${isPlaying ? "bg-blue-500" : "hover:bg-zinc-800"}`}
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
                handleTimelineChange(
                  Math.min(tripData.length - 1, selectedIndex + 1),
                )
              }
              className={`${isMobile ? "p-2" : "p-1.5"} rounded hover:bg-zinc-800 transition-colors disabled:opacity-30`}
              disabled={selectedIndex === tripData.length - 1 || isLive}
            >
              <ChevronRight className={isMobile ? "h-5 w-5" : "h-4 w-4"} />
            </button>
          </div>

          {!isMobile && (
            <select
              value={playbackSpeed}
              onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
              className="bg-zinc-800 border border-zinc-700 rounded px-2 py-1 text-xs text-zinc-300 disabled:opacity-50"
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
                className="p-1 rounded hover:bg-zinc-800 transition-colors disabled:opacity-30"
                disabled={currentDay === 1 || isLive}
                title="Previous day"
              >
                <ChevronLeft className="h-3 w-3" />
              </button>
              <span className="text-xs text-zinc-400 min-w-[45px] text-center font-medium">
                Day {currentDay}
              </span>
              <button
                onClick={() => {
                  const nextDay = dayBoundaries.find((d) => d.dayNumber === currentDay + 1);
                  if (nextDay) handleTimelineChange(nextDay.index);
                }}
                className="p-1 rounded hover:bg-zinc-800 transition-colors disabled:opacity-30"
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
              className={`w-full ${isMobile ? "h-2" : "h-1.5"} bg-zinc-800 rounded-lg appearance-none cursor-pointer ${
                isLive ? "accent-red-500 opacity-50" : "accent-blue-500"
              }`}
              disabled={isLive}
            />
          </div>

          <div
            className={`text-xs ${isMobile ? "min-w-[60px]" : "min-w-[100px]"} text-right`}
          >
            {isLive ? (
              <span className="text-red-400 flex items-center gap-1 justify-end">
                <Radio className="w-3 h-3 animate-pulse" />
                {!isMobile && "Live"}
              </span>
            ) : (
              <span className="text-zinc-500">
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
        className={`flex-none border-t bg-zinc-950 overflow-x-auto transition-colors ${
          isLive ? "border-red-500/30" : "border-zinc-800"
        }`}
        ref={scrollRef}
      >
        <div
          className={`flex ${isMobile ? "gap-1 p-1.5" : "gap-1.5 p-2"}`}
          style={{ width: "max-content" }}
        >
          <div style={{ width: visibleRange.start * (isMobile ? 52 : 68) }} />
          {tripData.slice(visibleRange.start, visibleRange.end).map((point) => {
            const isSelected = point.id === selectedId;
            const isLatest = point.id === tripData[latestIndex].id;
            return (
              <button
                key={point.id}
                ref={(el) => (imageRefs.current[point.id] = el)}
                onClick={() => handleMarkerClick(point.id)}
                className={`flex-none relative transition-all ${
                  isSelected
                    ? isLive
                      ? "ring-2 ring-red-500 ring-offset-1 ring-offset-zinc-950 scale-105"
                      : "ring-2 ring-blue-500 ring-offset-1 ring-offset-zinc-950 scale-105"
                    : "hover:ring-1 hover:ring-zinc-600"
                }`}
              >
                <div
                  className={`${isMobile ? "w-12 h-8" : "w-16 h-11"} rounded overflow-hidden flex items-center justify-center bg-zinc-800`}
                >
                  <img
                    src={getThumbUrl(point.image)}
                    alt=""
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                </div>
                {isLive && isLatest && (
                  <div className="absolute -top-1 -right-1 w-3 h-3 bg-red-500 rounded-full animate-pulse border border-zinc-950" />
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
        </div>
      </div>
    </div>
  );
}
