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

export default function App() {
  const mapContainer = useRef(null);
  const map = useRef(null);
  const ws = useRef(null);
  const markers = useRef({});

  const [vessels, setVessels] = useState({});
  const [selectedVessel, setSelectedVessel] = useState(null);
  const [connectionStatus, setConnectionStatus] = useState("disconnected");
  const [stats, setStats] = useState({ vessels: 0, positions: 0 });

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
          setStats((s) => ({ ...s, vessels: data.vessels.length }));
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

    map.current.addControl(new maplibregl.NavigationControl(), "top-left");

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

  // Update markers
  useEffect(() => {
    if (!map.current) return;

    Object.values(vessels).forEach((vessel) => {
      if (!vessel.lat || !vessel.lon) return;

      const mmsi = vessel.mmsi;

      if (markers.current[mmsi]) {
        markers.current[mmsi].setLngLat([vessel.lon, vessel.lat]);
        const el = markers.current[mmsi].getElement();
        if (vessel.heading !== null && vessel.heading !== undefined) {
          el.style.transform = `rotate(${vessel.heading}deg)`;
        }
      } else {
        const el = document.createElement("div");
        el.className = "vessel-marker";
        el.style.cssText = `
          width: 0;
          height: 0;
          border-left: 6px solid transparent;
          border-right: 6px solid transparent;
          border-bottom: 16px solid #0066ff;
          cursor: pointer;
          transform-origin: center bottom;
        `;
        if (vessel.heading !== null && vessel.heading !== undefined) {
          el.style.transform = `rotate(${vessel.heading}deg)`;
        }

        el.addEventListener("click", () => {
          setSelectedVessel(vessel);
        });

        const marker = new maplibregl.Marker({ element: el })
          .setLngLat([vessel.lon, vessel.lat])
          .addTo(map.current);

        markers.current[mmsi] = marker;
      }
    });

    setStats((s) => ({ ...s, vessels: Object.keys(vessels).length }));
  }, [vessels]);

  // Update selected vessel data
  useEffect(() => {
    if (selectedVessel && vessels[selectedVessel.mmsi]) {
      setSelectedVessel(vessels[selectedVessel.mmsi]);
    }
  }, [vessels, selectedVessel?.mmsi]);

  return (
    <div className="app">
      <header className="header">
        <h1 className="title">Ships</h1>
        <div className="stats">
          <div className="stat">
            <span>Vessels:</span>
            <span className="stat-value">{stats.vessels}</span>
          </div>
          <div className="connection-status">
            <span
              className={`status-dot ${connectionStatus}`}
              title={connectionStatus}
            />
            <span>{connectionStatus.toUpperCase()}</span>
          </div>
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
                onClick={() => setSelectedVessel(null)}
              >
                x
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
