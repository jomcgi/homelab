import React, { useState, useRef, useEffect, useCallback } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import {
  MapPin,
  Cloud,
  Thermometer,
  Wind,
  Camera,
  PawPrint,
  Play,
  Pause,
  ChevronLeft,
  ChevronRight,
  Radio,
  Eye,
  Maximize2,
  Minimize2,
  Map,
  Image,
} from "lucide-react";

// ============================================
// Route Generation - Vancouver to Dawson City
// ============================================

const routeWaypoints = [
  { lat: 49.2827, lng: -123.1207, name: "Vancouver" },
  { lat: 49.3838, lng: -123.0918, name: "North Vancouver" },
  { lat: 50.1163, lng: -122.9574, name: "Squamish" },
  { lat: 50.1171, lng: -123.0545, name: "Whistler" },
  { lat: 50.6833, lng: -122.4833, name: "Pemberton" },
  { lat: 51.253, lng: -121.953, name: "Lillooet" },
  { lat: 51.8461, lng: -121.2956, name: "Clinton" },
  { lat: 52.1417, lng: -122.1417, name: "100 Mile House" },
  { lat: 52.9784, lng: -122.493, name: "Quesnel" },
  { lat: 53.9171, lng: -122.7497, name: "Prince George" },
  { lat: 54.3833, lng: -124.25, name: "Vanderhoof" },
  { lat: 54.2305, lng: -125.761, name: "Burns Lake" },
  { lat: 54.3833, lng: -126.7, name: "Houston" },
  { lat: 54.7521, lng: -127.1681, name: "Smithers" },
  { lat: 55.25, lng: -127.6, name: "New Hazelton" },
  { lat: 55.75, lng: -128.6, name: "Kitwanga" },
  { lat: 56.25, lng: -129.6, name: "Meziadin Junction" },
  { lat: 57.0833, lng: -130.0333, name: "Bell II" },
  { lat: 57.9167, lng: -130.0333, name: "Iskut" },
  { lat: 58.4333, lng: -130.0, name: "Dease Lake" },
  { lat: 59.4167, lng: -129.1667, name: "Good Hope Lake" },
  { lat: 59.9833, lng: -128.7167, name: "Watson Lake" },
  { lat: 60.0667, lng: -128.8167, name: "Upper Liard" },
  { lat: 60.1117, lng: -128.9186, name: "Liard Hot Springs" },
  { lat: 60.85, lng: -131.4667, name: "Teslin" },
  { lat: 60.7212, lng: -135.0568, name: "Whitehorse" },
  { lat: 61.05, lng: -137.3833, name: "Haines Junction" },
  { lat: 63.4547, lng: -139.0986, name: "Dawson City" },
];

const wildlifeSpots = [
  { lat: 52.2, lng: -122.2, animal: "Black Bear" },
  { lat: 54.5, lng: -126.9, animal: "Moose" },
  { lat: 56.8, lng: -129.8, animal: "Grizzly Bear" },
  { lat: 58.1, lng: -130.0, animal: "Mountain Goat" },
  { lat: 59.6, lng: -129.0, animal: "Caribou" },
  { lat: 60.2, lng: -128.9, animal: "Bison" },
  { lat: 61.2, lng: -136.5, animal: "Fox" },
  { lat: 62.8, lng: -138.5, animal: "Moose" },
];

function generateDenseRoute(waypoints, pointsPerSegment = 50) {
  const points = [];
  const startTime = new Date("2025-06-15T06:00:00");

  for (let i = 0; i < waypoints.length - 1; i++) {
    const start = waypoints[i];
    const end = waypoints[i + 1];

    for (let j = 0; j < pointsPerSegment; j++) {
      const t = j / pointsPerSegment;
      const lat = start.lat + (end.lat - start.lat) * t;
      const lng = start.lng + (end.lng - start.lng) * t;

      const noise = () => (Math.random() - 0.5) * 0.001;

      const nearWildlife = wildlifeSpots.find(
        (w) => Math.abs(w.lat - lat) < 0.3 && Math.abs(w.lng - lng) < 0.3,
      );

      const segmentProgress =
        (i * pointsPerSegment + j) /
        ((waypoints.length - 1) * pointsPerSegment);
      const tripDurationMs = 35 * 60 * 60 * 1000;
      const timestamp = new Date(
        startTime.getTime() + segmentProgress * tripDurationMs,
      );

      points.push({
        id: points.length + 1,
        lat: lat + noise(),
        lng: lng + noise(),
        imageUrl: `/r2/trip-2025/img_${String(points.length + 1).padStart(6, "0")}.jpg`,
        timestamp,
        location:
          start.name + (j > pointsPerSegment / 2 ? ` → ${end.name}` : ""),
        animal: nearWildlife ? nearWildlife.animal : null,
      });
    }
  }

  const lastWaypoint = waypoints[waypoints.length - 1];
  points.push({
    id: points.length + 1,
    lat: lastWaypoint.lat,
    lng: lastWaypoint.lng,
    imageUrl: `/r2/trip-2025/img_${String(points.length + 1).padStart(6, "0")}.jpg`,
    timestamp: new Date(startTime.getTime() + 35 * 60 * 60 * 1000),
    location: lastWaypoint.name,
    animal: null,
  });

  return points;
}

const tripData = generateDenseRoute(routeWaypoints, 50);

const mockWeather = {
  location: "Dawson City, YT",
  temp: 18,
  condition: "Partly Cloudy",
  wind: 12,
};

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
        <Image className="h-4 w-4" />
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

      const wildlifePoints = points.filter((p) => p.animal);
      map.current.addSource("wildlife", {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: wildlifePoints.map((p) => ({
            type: "Feature",
            properties: { id: p.id, animal: p.animal },
            geometry: { type: "Point", coordinates: [p.lng, p.lat] },
          })),
        },
      });

      map.current.addLayer({
        id: "wildlife-points",
        type: "circle",
        source: "wildlife",
        paint: {
          "circle-radius": 6,
          "circle-color": "#f59e0b",
          "circle-stroke-width": 2,
          "circle-stroke-color": "#fff",
        },
      });

      map.current.on("click", "wildlife-points", (e) => {
        onMarkerClick(e.features[0].properties.id);
      });

      map.current.on("mouseenter", "wildlife-points", () => {
        map.current.getCanvas().style.cursor = "pointer";
      });

      map.current.on("mouseleave", "wildlife-points", () => {
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

  useEffect(() => {
    if (!mapLoaded || !map.current) return;

    const point = points.find((p) => p.id === selectedId);
    if (!point) return;

    if (markerRef.current) markerRef.current.remove();

    const el = document.createElement("div");
    el.className = "current-marker";

    const baseColor = point.animal ? "#f59e0b" : isLive ? "#ef4444" : "#3b82f6";
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
  tripStart,
  totalFrames,
  currentIndex,
  isMobile = false,
}) {
  const formatTime = (date) =>
    date.toLocaleDateString("en-CA", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

  const formatDuration = (start, current) => {
    const diff = current - start;
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    return `${hours}h ${minutes}m`;
  };

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
            <h2 className="font-semibold text-lg">{point.location}</h2>
            <p className="text-sm text-zinc-500">
              {formatTime(point.timestamp)}
            </p>
          </div>
          {point.animal && (
            <span className="text-sm bg-amber-500/20 text-amber-500 px-3 py-1.5 rounded-full flex items-center gap-1.5">
              <PawPrint className="h-4 w-4" />
              {point.animal}
            </span>
          )}
        </div>
      </div>

      {/* Main Image Area */}
      <div className="flex-1 relative min-h-0 p-4">
        <div
          className={`w-full h-full rounded-lg overflow-hidden flex items-center justify-center ${
            point.animal
              ? "bg-amber-500/5 border border-amber-500/20"
              : "bg-zinc-800"
          } ${isLive ? "ring-2 ring-red-500/30" : ""}`}
        >
          {point.animal ? (
            <div className="text-center">
              <PawPrint
                className={`${iconSize} text-amber-500/30 mx-auto mb-3`}
              />
              <p className="text-amber-500/50 text-sm">
                Wildlife detected: {point.animal}
              </p>
            </div>
          ) : (
            <div className="text-center">
              <Camera
                className={`${iconSize} mx-auto mb-3 ${isLive ? "text-red-500/20" : "text-zinc-700"}`}
              />
              <p className="text-zinc-600 text-sm font-mono">
                {point.imageUrl}
              </p>
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
            <span className="text-zinc-500 block text-xs mb-0.5">
              Trip Duration
            </span>
            <span>{formatDuration(tripStart, point.timestamp)}</span>
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
  const [selectedIndex, setSelectedIndex] = useState(tripData.length - 1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(10);
  const [isLive, setIsLive] = useState(false);
  const [mapExpanded, setMapExpanded] = useState(false);
  const [mobileView, setMobileView] = useState("image"); // 'image' or 'map'
  const scrollRef = useRef(null);
  const imageRefs = useRef({});

  // Media queries for responsive design
  const isMobile = useMediaQuery("(max-width: 768px)");
  const isTablet = useMediaQuery("(max-width: 1024px)");

  const selectedPoint = tripData[selectedIndex];
  const selectedId = selectedPoint?.id;
  const animalPoints = tripData.filter((p) => p.animal);
  const latestIndex = tripData.length - 1;

  useEffect(() => {
    if (isLive) {
      setSelectedIndex(latestIndex);
      setIsPlaying(false);
    }
  }, [isLive, latestIndex]);

  useEffect(() => {
    let interval;
    if (isPlaying && !isLive) {
      interval = setInterval(() => {
        setSelectedIndex((prev) => {
          if (prev >= tripData.length - 1) {
            setIsPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, 1000 / playbackSpeed);
    }
    return () => clearInterval(interval);
  }, [isPlaying, playbackSpeed, isLive]);

  useEffect(() => {
    const el = imageRefs.current[selectedId];
    if (el)
      el.scrollIntoView({
        behavior: "smooth",
        inline: "center",
        block: "nearest",
      });
  }, [selectedId]);

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
    [latestIndex],
  );

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

  const formatTime = (date) =>
    date.toLocaleDateString("en-CA", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

  const formatTimeShort = (date) =>
    date.toLocaleTimeString("en-CA", {
      hour: "2-digit",
      minute: "2-digit",
    });

  const visibleRange = {
    start: Math.max(0, selectedIndex - 15),
    end: Math.min(tripData.length, selectedIndex + 15),
  };

  return (
    <div className="h-screen w-full bg-zinc-950 text-zinc-100 flex flex-col overflow-hidden">
      <style>{`
        @keyframes pulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.2); opacity: 0.8; }
        }
      `}</style>

      {/* Demo Data Banner */}
      <div className="absolute top-14 left-1/2 -translate-x-1/2 z-50">
        <div className="bg-amber-500/90 text-zinc-900 px-4 py-1.5 rounded-full text-sm font-medium shadow-lg flex items-center gap-2">
          <span className="w-2 h-2 bg-zinc-900 rounded-full animate-pulse" />
          Demo Data
        </div>
      </div>

      {/* Status Bar */}
      <div className="flex-none border-b border-zinc-800 bg-zinc-900/80 px-4 py-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 md:gap-4">
            <div className="flex items-center gap-2">
              <div
                className={`h-2 w-2 rounded-full ${isLive ? "bg-red-500" : "bg-emerald-500"} animate-pulse`}
              />
              {!isMobile && (
                <span className="text-sm font-medium">Joe's Location</span>
              )}
            </div>
            <div className="flex items-center gap-1.5 text-zinc-400 text-sm">
              <MapPin className="h-3.5 w-3.5" />
              <span className={isMobile ? "truncate max-w-[100px]" : ""}>
                {isMobile
                  ? selectedPoint.location.split(" → ")[0]
                  : mockWeather.location}
              </span>
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
              viewerCount={isLive ? 42 : null}
              compact={isMobile}
            />
          </div>
          {!isMobile && (
            <div className="flex items-center gap-5 text-sm text-zinc-400">
              {!isTablet && (
                <>
                  <div className="flex items-center gap-1.5">
                    <Thermometer className="h-3.5 w-3.5" />
                    <span>{mockWeather.temp}°C</span>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Cloud className="h-3.5 w-3.5" />
                    <span>{mockWeather.condition}</span>
                  </div>
                </>
              )}
              <div className="flex items-center gap-1.5">
                <Wind className="h-3.5 w-3.5" />
                <span>{mockWeather.wind} km/h</span>
              </div>
            </div>
          )}
        </div>
      </div>

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
                  <div className="mt-2 text-xs bg-amber-500/20 text-amber-500 px-2 py-1 rounded flex items-center gap-1">
                    <PawPrint className="h-3 w-3" />
                    {animalPoints.length} wildlife
                  </div>
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
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-3 rounded-full bg-amber-500 border-2 border-white" />
                    <span className="text-zinc-400">Wildlife</span>
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
                tripStart={tripData[0].timestamp}
                totalFrames={tripData.length}
                currentIndex={selectedIndex}
                isMobile={isMobile}
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
                  <div className="mt-2 text-xs bg-amber-500/20 text-amber-500 px-2 py-1 rounded flex items-center gap-1">
                    <PawPrint className="h-3 w-3" />
                    {animalPoints.length} wildlife
                  </div>
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
                  <div className="flex items-center gap-1.5">
                    <div className="w-3 h-3 rounded-full bg-amber-500 border-2 border-white" />
                    <span className="text-zinc-400">Wildlife</span>
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
                tripStart={tripData[0].timestamp}
                totalFrames={tripData.length}
                currentIndex={selectedIndex}
                isMobile={isMobile}
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
            <div
              className={`absolute ${isMobile ? "top-4" : "top-3"} left-0 right-0 h-1`}
            >
              {animalPoints.map((p) => {
                const idx = tripData.findIndex((pt) => pt.id === p.id);
                const pos = (idx / (tripData.length - 1)) * 100;
                return (
                  <button
                    key={p.id}
                    onClick={() => !isLive && handleMarkerClick(p.id)}
                    className={`absolute ${isMobile ? "w-2 h-2" : "w-1.5 h-1.5"} bg-amber-500 rounded-full -translate-x-1/2 transition-transform ${
                      isLive ? "opacity-50" : "hover:scale-150"
                    }`}
                    style={{ left: `${pos}%` }}
                    title={p.animal}
                    disabled={isLive}
                  />
                );
              })}
            </div>
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
                  className={`${isMobile ? "w-12 h-8" : "w-16 h-11"} rounded overflow-hidden flex items-center justify-center ${
                    point.animal ? "bg-amber-500/10" : "bg-zinc-800"
                  }`}
                >
                  {point.animal ? (
                    <PawPrint
                      className={`${isMobile ? "h-3 w-3" : "h-4 w-4"} text-amber-500/50`}
                    />
                  ) : (
                    <span className="text-[10px] text-zinc-600 font-mono">
                      {String(point.id).padStart(4, "0")}
                    </span>
                  )}
                </div>
                {point.animal && (
                  <div className="absolute top-0.5 right-0.5 w-1.5 h-1.5 bg-amber-500 rounded-full" />
                )}
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
