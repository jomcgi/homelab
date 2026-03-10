import { useState, useRef, useEffect, useCallback } from "react";
import { API_BASE_URL, WS_BASE_URL } from "../constants/api";

// eslint-disable-next-line no-unused-vars
export function useTripData(tripSlug = null) {
  const [points, setPoints] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [stats, setStats] = useState({ total: 0, viewers: 0 });
  const wsRef = useRef(null);
  const reconnectTimeoutRef = useRef(null);

  // Transform API response to match React component expectations
  const transformPoint = useCallback((apiPoint) => {
    const ts = apiPoint.timestamp?.replace(/Z$/, "") || "";
    return {
      id: apiPoint.id,
      lat: apiPoint.lat,
      lng: apiPoint.lng,
      image: apiPoint.image,
      source: apiPoint.source || "gopro",
      timestamp: new Date(ts),
      tags: apiPoint.tags || [],
      elevation: apiPoint.elevation,
      // OPTICS - Camera exposure data from EXIF
      lightValue: apiPoint.light_value,
      iso: apiPoint.iso,
      shutterSpeed: apiPoint.shutter_speed,
      aperture: apiPoint.aperture,
      focalLength35mm: apiPoint.focal_length_35mm,
    };
  }, []);

  // Connect to WebSocket for live updates
  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    try {
      const ws = new WebSocket(`${WS_BASE_URL}/ws/live`);

      ws.onopen = () => {
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

        // TODO: Add multi-trip support when API is ready
        // For now, use the single-trip endpoint regardless of tripSlug
        const endpoint = `${API_BASE_URL}/api/points`;

        const response = await fetch(endpoint);
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
    // TODO: Add tripSlug to dependencies when multi-trip API is ready
  }, [transformPoint, connectWebSocket]);

  return { points, loading, error, stats };
}
