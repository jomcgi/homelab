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

function trackToGeoJSON(track) {
  if (!track || track.length < 2) {
    return { type: "FeatureCollection", features: [] };
  }
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: track.map((p) => [p.lon, p.lat]),
        },
        properties: {},
      },
    ],
  };
}

function selectedVesselToGeoJSON(vessel) {
  if (!vessel || !vessel.lat || !vessel.lon) {
    return { type: "FeatureCollection", features: [] };
  }
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        geometry: {
          type: "Point",
          coordinates: [vessel.lon, vessel.lat],
        },
        properties: {},
      },
    ],
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
  const [selectedTrack, setSelectedTrack] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState("disconnected");
  const [stats, setStats] = useState({ vessels: 0 });

  // Derive selected vessel from MMSI - always up to date
  const selectedVessel = selectedMmsi ? vessels[selectedMmsi] : null;

  // Ref for websocket handler to access current selected MMSI
  const selectedMmsiRef = useRef(selectedMmsi);
  selectedMmsiRef.current = selectedMmsi;

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
        } else if (data.type === "positions") {
          // Batch all position updates into a single state update
          const positions = data.positions;

          setVessels((prev) => {
            const next = { ...prev };
            for (const pos of positions) {
              next[pos.mmsi] = { ...prev[pos.mmsi], ...pos };
            }
            return next;
          });

          // Batch track updates for selected vessel
          const selectedMmsi = selectedMmsiRef.current;
          if (selectedMmsi) {
            const trackPoints = positions
              .filter(
                (pos) =>
                  pos.mmsi === selectedMmsi &&
                  pos.lat != null &&
                  pos.lon != null,
              )
              .map((pos) => ({
                lat: pos.lat,
                lon: pos.lon,
                timestamp: pos.timestamp,
              }));

            if (trackPoints.length > 0) {
              setSelectedTrack((prevTrack) => {
                if (!prevTrack) return prevTrack;
                const newPoints = trackPoints.filter((pt) => {
                  const last = prevTrack[prevTrack.length - 1];
                  return !last || last.lat !== pt.lat || last.lon !== pt.lon;
                });
                return newPoints.length > 0
                  ? [...prevTrack, ...newPoints]
                  : prevTrack;
              });
            }
          }
        } else if (data.mmsi) {
          // Legacy: single position update
          setVessels((prev) => ({
            ...prev,
            [data.mmsi]: { ...prev[data.mmsi], ...data },
          }));

          if (
            data.mmsi === selectedMmsiRef.current &&
            data.lat != null &&
            data.lon != null
          ) {
            setSelectedTrack((prevTrack) => {
              if (!prevTrack) return prevTrack;
              const lastPoint = prevTrack[prevTrack.length - 1];
              if (
                lastPoint &&
                lastPoint.lat === data.lat &&
                lastPoint.lon === data.lon
              ) {
                return prevTrack;
              }
              return [
                ...prevTrack,
                { lat: data.lat, lon: data.lon, timestamp: data.timestamp },
              ];
            });
          }
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
  }, []);

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
      "top-left",
    );

    map.current.on("load", async () => {
      // Add arrow image for moving vessels (scaled for device pixel ratio)
      const { img: arrowImg, pixelRatio } = await createArrowImage();
      map.current.addImage("arrow", arrowImg, { sdf: false, pixelRatio });

      map.current.addSource("vessels", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      // Anchored vessels - black dots with zoom-responsive sizing
      map.current.addLayer({
        id: "vessels-anchored",
        type: "circle",
        source: "vessels",
        filter: ["==", ["get", "moving"], false],
        paint: {
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            5,
            3,
            8,
            5,
            12,
            8,
            16,
            12,
          ],
          "circle-color": "#000",
          "circle-stroke-width": [
            "interpolate",
            ["linear"],
            ["zoom"],
            5,
            1,
            12,
            1.5,
            16,
            2,
          ],
          "circle-stroke-color": "#fff",
        },
      });

      // Moving vessels - orange arrows, size scales with zoom
      map.current.addLayer({
        id: "vessels-moving",
        type: "symbol",
        source: "vessels",
        filter: ["==", ["get", "moving"], true],
        layout: {
          "icon-image": "arrow",
          "icon-size": [
            "interpolate",
            ["linear"],
            ["zoom"],
            5,
            0.4,
            8,
            0.6,
            12,
            0.9,
            16,
            1.2,
          ],
          "icon-rotate": ["get", "rotation"],
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
      });

      // Vessel track line source and layer
      map.current.addSource("vessel-track", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.current.addLayer(
        {
          id: "vessel-track-line",
          type: "line",
          source: "vessel-track",
          paint: {
            "line-color": "#22c55e",
            "line-width": 3,
            "line-opacity": 0.8,
          },
        },
        "vessels-anchored",
      );

      // Selection indicator source and layer
      map.current.addSource("selected-vessel", {
        type: "geojson",
        data: { type: "FeatureCollection", features: [] },
      });

      map.current.addLayer(
        {
          id: "selected-vessel-ring",
          type: "circle",
          source: "selected-vessel",
          paint: {
            "circle-radius": [
              "interpolate",
              ["linear"],
              ["zoom"],
              5,
              8,
              8,
              12,
              12,
              18,
              16,
              24,
            ],
            "circle-color": "transparent",
            "circle-stroke-width": 3,
            "circle-stroke-color": "#3b82f6",
            "circle-stroke-opacity": 0.9,
          },
        },
        "vessels-anchored",
      );

      // Click handler for individual vessels
      const handleVesselClick = (e) => {
        if (e.features && e.features.length > 0) {
          const mmsi = e.features[0].properties.mmsi;
          setSelectedMmsi(mmsi);
        }
      };

      map.current.on("click", "vessels-anchored", handleVesselClick);
      map.current.on("click", "vessels-moving", handleVesselClick);

      const setCursor = () => {
        map.current.getCanvas().style.cursor = "pointer";
      };
      const resetCursor = () => {
        map.current.getCanvas().style.cursor = "";
      };

      map.current.on("mouseenter", "vessels-anchored", setCursor);
      map.current.on("mouseenter", "vessels-moving", setCursor);
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

  // Fetch track when vessel is selected
  useEffect(() => {
    if (!selectedMmsi) {
      setSelectedTrack(null);
      return;
    }

    const fetchTrack = async () => {
      try {
        const response = await fetch(
          `/api/vessels/${selectedMmsi}/track?since=24h&limit=1000`,
        );
        if (response.ok) {
          const data = await response.json();
          setSelectedTrack(data.track || []);
        } else {
          setSelectedTrack(null);
        }
      } catch (e) {
        console.error("Failed to fetch track:", e);
        setSelectedTrack(null);
      }
    };

    fetchTrack();
  }, [selectedMmsi]);

  // Update track source when track data changes
  useEffect(() => {
    if (!map.current) return;

    const source = map.current.getSource("vessel-track");
    if (source) {
      source.setData(trackToGeoJSON(selectedTrack));
    }
  }, [selectedTrack]);

  // Update selection indicator when selected vessel changes
  useEffect(() => {
    if (!map.current) return;

    const source = map.current.getSource("selected-vessel");
    if (source) {
      source.setData(selectedVesselToGeoJSON(selectedVessel));
    }
  }, [selectedVessel]);

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
                  <a
                    href={`https://maps.google.com/maps?q=${selectedVessel.lat},${selectedVessel.lon}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="position-link"
                  >
                    {selectedVessel.lat?.toFixed(4)},{" "}
                    {selectedVessel.lon?.toFixed(4)}
                  </a>
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
