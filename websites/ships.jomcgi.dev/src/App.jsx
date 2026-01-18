import { useEffect, useRef, useState, useCallback } from "react";
import maplibregl from "maplibre-gl";

const SHIP_TYPES = {
  0: "Unknown",
  20: "Wing in ground",
  30: "Fishing",
  31: "Towing",
  32: "Towing (large)",
  33: "Dredging",
  34: "Diving ops",
  35: "Military ops",
  36: "Sailing",
  37: "Pleasure craft",
  40: "High-speed craft",
  50: "Pilot vessel",
  51: "Search & rescue",
  52: "Tug",
  53: "Port tender",
  54: "Anti-pollution",
  55: "Law enforcement",
  60: "Passenger",
  70: "Cargo",
  80: "Tanker",
  90: "Other",
};

const NAV_STATUS = {
  0: "Under way using engine",
  1: "At anchor",
  2: "Not under command",
  3: "Restricted manoeuvrability",
  4: "Constrained by draught",
  5: "Moored",
  6: "Aground",
  7: "Engaged in fishing",
  8: "Under way sailing",
  15: "Not defined",
};

function getShipType(code) {
  if (!code) return "Unknown";
  const baseCode = Math.floor(code / 10) * 10;
  return SHIP_TYPES[baseCode] || SHIP_TYPES[code] || `Type ${code}`;
}

function formatSpeed(speed) {
  if (speed === null || speed === undefined) return "-";
  return `${speed.toFixed(1)} kn`;
}

function formatCourse(course) {
  if (course === null || course === undefined) return "-";
  return `${Math.round(course)}°`;
}

function formatTimestamp(ts) {
  if (!ts) return "-";
  const date = new Date(ts);
  return date.toLocaleTimeString();
}

// Ship is considered moving if speed > 0.5 knots
function isMoving(vessel) {
  const speed = vessel.speed ?? 0;
  return speed > 0.5;
}

// Get rotation angle - prefer heading, fall back to course
function getRotation(vessel) {
  if (vessel.heading != null && vessel.heading !== 511) return vessel.heading;
  if (vessel.course != null && vessel.course !== 360) return vessel.course;
  return 0;
}

function vesselsToGeoJSON(vessels) {
  return {
    type: "FeatureCollection",
    features: Object.values(vessels)
      .filter((v) => v.lat && v.lon)
      .map((v) => ({
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [v.lon, v.lat],
        },
        properties: {
          mmsi: v.mmsi,
          moving: isMoving(v),
          rotation: getRotation(v),
          speed: v.speed ?? 0,
        },
      })),
  };
}

// Arrow SVG generator - scales with device pixel ratio for sharp rendering on high-DPI displays
function createArrowSvg(size) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 32 32">
  <path d="M16 2 L26 22 L16 15 L6 22 Z" fill="#ff4400" stroke="#fff" stroke-width="2.5"/>
</svg>`;
}

function createArrowImage() {
  const pixelRatio = window.devicePixelRatio || 1;
  const size = Math.round(32 * pixelRatio);
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve({ img, pixelRatio });
    img.src = "data:image/svg+xml," + encodeURIComponent(createArrowSvg(size));
  });
}

export default function App() {
  const mapContainer = useRef(null);
  const map = useRef(null);
  const ws = useRef(null);

  const [vessels, setVessels] = useState({});
  const [selectedMmsi, setSelectedMmsi] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState("disconnected");
  const [stats, setStats] = useState({ vessels: 0 });

  // Derive selected vessel from MMSI - always up to date
  const selectedVessel = selectedMmsi ? vessels[selectedMmsi] : null;

  // Ref for click handler to access setter (defined once in map.on('load'))
  const setSelectedMmsiRef = useRef(setSelectedMmsi);
  setSelectedMmsiRef.current = setSelectedMmsi;

  const updateVessel = useCallback((data) => {
    setVessels((prev) => ({
      ...prev,
      [data.mmsi]: { ...prev[data.mmsi], ...data },
    }));
  }, []);

  const connectWebSocket = useCallback(() => {
    setConnectionStatus("connecting");

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/live`;

    ws.current = new WebSocket(wsUrl);

    ws.current.onopen = () => {
      setConnectionStatus("connected");
    };

    ws.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === "snapshot") {
          const vesselMap = {};
          data.vessels.forEach((v) => {
            vesselMap[v.mmsi] = v;
          });
          setVessels(vesselMap);
          setStats({ vessels: data.vessels.length });
        } else if (data.mmsi) {
          updateVessel(data);
        }
      } catch (e) {
        console.error("Failed to parse message:", e);
      }
    };

    ws.current.onclose = () => {
      setConnectionStatus("disconnected");
      setTimeout(connectWebSocket, 3000);
    };

    ws.current.onerror = () => {
      setConnectionStatus("disconnected");
    };
  }, [updateVessel]);

  // Initialize map
  useEffect(() => {
    if (map.current) return;

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "&copy; OpenStreetMap contributors",
          },
        },
        layers: [
          {
            id: "osm",
            type: "raster",
            source: "osm",
          },
        ],
      },
      center: [-125, 49],
      zoom: 7,
    });

    map.current.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "top-left"
    );

    map.current.on("load", async () => {
      // Add arrow image for moving vessels (scaled for device pixel ratio)
      const { img: arrowImg, pixelRatio } = await createArrowImage();
      map.current.addImage("arrow", arrowImg, { sdf: false, pixelRatio });

      map.current.addSource("vessels", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
        cluster: true,
        clusterMaxZoom: 8,
        clusterRadius: 30,
      });

      // Cluster circles - sized by point count
      map.current.addLayer({
        id: "vessel-clusters",
        type: "circle",
        source: "vessels",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#ff4400",
          "circle-radius": [
            "step",
            ["get", "point_count"],
            15,
            10, 20,
            50, 25,
            100, 30,
          ],
          "circle-stroke-width": 2,
          "circle-stroke-color": "#fff",
        },
      });

      // Cluster count labels
      map.current.addLayer({
        id: "vessel-cluster-count",
        type: "symbol",
        source: "vessels",
        filter: ["has", "point_count"],
        layout: {
          "text-field": "{point_count_abbreviated}",
          "text-size": 12,
        },
        paint: {
          "text-color": "#fff",
        },
      });

      // Anchored vessels - black dots with zoom-responsive sizing
      map.current.addLayer({
        id: "vessels-anchored",
        type: "circle",
        source: "vessels",
        filter: [
          "all",
          ["==", ["get", "moving"], false],
          ["!", ["has", "point_count"]],
        ],
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            6, 6,
            10, 10,
            14, 16,
            18, 24,
          ],
          "circle-color": "#000",
          "circle-stroke-width": [
            "interpolate",
            ["linear"],
            ["zoom"],
            6, 1.5,
            14, 2.5,
            18, 3.5,
          ],
          "circle-stroke-color": "#fff",
        },
      });

      // Moving vessels - orange arrows, size scales with zoom and speed
      map.current.addLayer({
        id: "vessels-moving",
        type: "symbol",
        source: "vessels",
        filter: [
          "all",
          ["==", ["get", "moving"], true],
          ["!", ["has", "point_count"]],
        ],
        layout: {
          "icon-image": "arrow",
          "icon-size": [
            "interpolate",
            ["linear"],
            ["zoom"],
            6,
            ["interpolate", ["linear"], ["get", "speed"], 0, 0.7, 30, 1.2],
            10,
            ["interpolate", ["linear"], ["get", "speed"], 0, 1.0, 30, 1.4],
            14,
            ["interpolate", ["linear"], ["get", "speed"], 0, 1.3, 30, 1.8],
            18,
            ["interpolate", ["linear"], ["get", "speed"], 0, 1.8, 30, 2.5],
          ],
          "icon-rotate": ["get", "rotation"],
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
      });

      // Click handler for individual vessels
      const handleVesselClick = (e) => {
        if (e.features && e.features.length > 0) {
          const mmsi = e.features[0].properties.mmsi;
          setSelectedMmsiRef.current(mmsi);
        }
      };

      map.current.on("click", "vessels-anchored", handleVesselClick);
      map.current.on("click", "vessels-moving", handleVesselClick);

      // Click handler for clusters - zoom to bounding box of all points
      map.current.on("click", "vessel-clusters", (e) => {
        const features = map.current.queryRenderedFeatures(e.point, {
          layers: ["vessel-clusters"],
        });
        const clusterId = features[0].properties.cluster_id;
        const pointCount = features[0].properties.point_count;
        map.current
          .getSource("vessels")
          .getClusterLeaves(clusterId, pointCount, 0, (err, leaves) => {
            if (err || !leaves.length) return;
            const bounds = new maplibregl.LngLatBounds();
            leaves.forEach((leaf) => {
              bounds.extend(leaf.geometry.coordinates);
            });
            map.current.fitBounds(bounds, { padding: 50 });
          });
      });

      const setCursor = () => {
        map.current.getCanvas().style.cursor = "pointer";
      };
      const resetCursor = () => {
        map.current.getCanvas().style.cursor = "";
      };

      map.current.on("mouseenter", "vessel-clusters", setCursor);
      map.current.on("mouseenter", "vessels-anchored", setCursor);
      map.current.on("mouseenter", "vessels-moving", setCursor);
      map.current.on("mouseleave", "vessel-clusters", resetCursor);
      map.current.on("mouseleave", "vessels-anchored", resetCursor);
      map.current.on("mouseleave", "vessels-moving", resetCursor);
    });

    return () => {
      if (map.current) {
        map.current.remove();
        map.current = null;
      }
    };
  }, []);

  // Connect WebSocket
  useEffect(() => {
    connectWebSocket();

    return () => {
      if (ws.current) {
        ws.current.close();
      }
    };
  }, [connectWebSocket]);

  // Update GeoJSON source when vessels change
  useEffect(() => {
    if (!map.current) return;

    const source = map.current.getSource("vessels");
    if (source) {
      source.setData(vesselsToGeoJSON(vessels));
    }

    setStats({ vessels: Object.keys(vessels).length });
  }, [vessels]);

  return (
    <div className="app">
      <header className="header">
        <h1 className="title">Ships</h1>
        <div className="stats">
          <span className="stat">{stats.vessels}</span>
          <span
            className={`status-dot ${connectionStatus}`}
            title={connectionStatus}
          />
        </div>
      </header>

      <div className="map-container">
        <div id="map" ref={mapContainer} />

        {selectedVessel && (
          <div className="vessel-panel">
            <div className="vessel-panel-header">
              <span>{selectedVessel.ship_name || selectedVessel.mmsi}</span>
              <button
                className="vessel-panel-close"
                onClick={() => setSelectedMmsi(null)}
              >
                ×
              </button>
            </div>
            <div className="vessel-panel-content">
              <div className="vessel-row">
                <span className="vessel-label">MMSI</span>
                <span className="vessel-value">{selectedVessel.mmsi}</span>
              </div>
              {selectedVessel.call_sign && (
                <div className="vessel-row">
                  <span className="vessel-label">Call Sign</span>
                  <span className="vessel-value">
                    {selectedVessel.call_sign}
                  </span>
                </div>
              )}
              <div className="vessel-row">
                <span className="vessel-label">Type</span>
                <span className="vessel-value">
                  {getShipType(selectedVessel.ship_type)}
                </span>
              </div>
              <div className="vessel-row">
                <span className="vessel-label">Status</span>
                <span className="vessel-value">
                  {NAV_STATUS[selectedVessel.nav_status] || "Unknown"}
                </span>
              </div>
              <div className="vessel-row">
                <span className="vessel-label">Position</span>
                <span className="vessel-value">
                  {selectedVessel.lat?.toFixed(4)},{" "}
                  {selectedVessel.lon?.toFixed(4)}
                </span>
              </div>
              <div className="vessel-row">
                <span className="vessel-label">Speed</span>
                <span className="vessel-value">
                  {formatSpeed(selectedVessel.speed)}
                </span>
              </div>
              <div className="vessel-row">
                <span className="vessel-label">Course</span>
                <span className="vessel-value">
                  {formatCourse(selectedVessel.course)}
                </span>
              </div>
              <div className="vessel-row">
                <span className="vessel-label">Heading</span>
                <span className="vessel-value">
                  {formatCourse(selectedVessel.heading)}
                </span>
              </div>
              {selectedVessel.destination && (
                <div className="vessel-row">
                  <span className="vessel-label">Destination</span>
                  <span className="vessel-value">
                    {selectedVessel.destination}
                  </span>
                </div>
              )}
              <div className="vessel-row">
                <span className="vessel-label">Updated</span>
                <span className="vessel-value">
                  {formatTimestamp(selectedVessel.timestamp)}
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
