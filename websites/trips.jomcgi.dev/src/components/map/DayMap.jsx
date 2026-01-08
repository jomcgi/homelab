import React, { useRef, useState, useEffect, useMemo } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

const HIGHLIGHT_ICONS = {
  wildlife: "🦬",
  hotspring: "♨️",
  aurora: "✦",
  landscape: "◆",
  other: "●",
};

/**
 * Map component for displaying a single day's route
 * Simpler than TripMap - shows one route with optional photo/highlight markers
 */
export function DayMap({
  points,
  highlights = [],
  dayColor = "#2563eb",
  height = "100%",
  isMobile = false,
  currentPhoto = null, // { lat, lng, timestamp } for current photo marker
  sunPosition = null, // { altitude, azimuth } from SunCalc - radians
  onLocationClick = null, // Callback when route is clicked: (timestamp) => void
}) {
  const mapContainer = useRef(null);
  const map = useRef(null);
  const photoMarkerRef = useRef(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const mountedRef = useRef(false);

  // Calculate bounds from points
  const bounds = useMemo(() => {
    if (!points?.length) return null;
    const lats = points.map((p) => p.lat).filter(Boolean);
    const lngs = points.map((p) => p.lng).filter(Boolean);
    if (!lats.length || !lngs.length) return null;
    return {
      minLat: Math.min(...lats),
      maxLat: Math.max(...lats),
      minLng: Math.min(...lngs),
      maxLng: Math.max(...lngs),
    };
  }, [points]);

  // Initialize map
  useEffect(() => {
    if (mountedRef.current || !mapContainer.current || !bounds) return;
    mountedRef.current = true;

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
      bounds: [
        [bounds.minLng, bounds.minLat],
        [bounds.maxLng, bounds.maxLat],
      ],
      fitBoundsOptions: { padding: isMobile ? 30 : 50 },
      interactive: true,
      scrollZoom: true,
      boxZoom: true,
      dragRotate: false,
      dragPan: true,
      keyboard: true,
      doubleClickZoom: true,
      touchZoomRotate: true,
      attributionControl: false,
    });

    map.current.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "top-right",
    );

    map.current.on("load", () => {
      // Add terrain source for hillshade
      map.current.addSource("terrain-dem", {
        type: "raster-dem",
        tiles: [
          "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
        ],
        encoding: "terrarium",
        tileSize: 256,
        maxzoom: 15,
      });

      const layers = map.current.getStyle().layers;
      const firstSymbolLayer = layers.find((layer) => layer.type === "symbol");

      // Dynamic hillshade based on sun position
      // SunCalc azimuth: radians from south, positive = west
      // MapLibre illumination-direction: degrees from north (0=N, 90=E, 180=S, 270=W)
      const getIlluminationDirection = (sunPos) => {
        if (!sunPos) return 315; // Default NW lighting
        // Convert: radians to degrees, then from-south to from-north
        const azimuthDeg = (sunPos.azimuth * 180) / Math.PI + 180;
        // Normalize to 0-360
        return ((azimuthDeg % 360) + 360) % 360;
      };

      const getSunIntensity = (sunPos) => {
        if (!sunPos)
          return {
            exaggeration: 0.8,
            shadowColor: "#cccccc",
            highlightColor: "#000000",
          };
        const altitudeDeg = (sunPos.altitude * 180) / Math.PI;

        // Smooth interpolation based on solar altitude
        const lerp = (a, b, t) => a + (b - a) * Math.max(0, Math.min(1, t));
        const lerpColor = (c1, c2, t) => {
          const r1 = parseInt(c1.slice(1, 3), 16),
            g1 = parseInt(c1.slice(3, 5), 16),
            b1 = parseInt(c1.slice(5, 7), 16);
          const r2 = parseInt(c2.slice(1, 3), 16),
            g2 = parseInt(c2.slice(3, 5), 16),
            b2 = parseInt(c2.slice(5, 7), 16);
          const r = Math.round(lerp(r1, r2, t)),
            g = Math.round(lerp(g1, g2, t)),
            b = Math.round(lerp(b1, b2, t));
          return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
        };

        // Normalize altitude to 0-1 range: -12° = 0, +15° = 1
        const t = (altitudeDeg + 12) / 27;

        // Exaggeration: peaks at low sun angles for dramatic shadows
        // Max is 1.0 in MapLibre
        let exaggeration;
        if (altitudeDeg < -6) {
          exaggeration = lerp(0.2, 0.5, (altitudeDeg + 12) / 6);
        } else if (altitudeDeg < 5) {
          exaggeration = lerp(0.5, 1.0, (altitudeDeg + 6) / 11); // peak at 1.0
        } else {
          exaggeration = 1.0; // stay at max
        }

        // Colors: smoothly transition from muted night to harsh day
        // Inverted map: shadow shows as light, highlight shows as dark
        const shadowColor = lerpColor("#222222", "#ffffff", t); // night gray -> pure white
        const highlightColor = lerpColor("#111111", "#000000", t); // night muted -> pure black

        return { exaggeration, shadowColor, highlightColor };
      };

      const intensity = getSunIntensity(sunPosition);

      // Add hillshade BEFORE the base map to blend underneath
      map.current.addLayer(
        {
          id: "hillshade",
          type: "hillshade",
          source: "terrain-dem",
          minzoom: 0,
          maxzoom: 22,
          paint: {
            "hillshade-exaggeration": intensity.exaggeration,
            "hillshade-shadow-color": intensity.shadowColor,
            "hillshade-highlight-color": intensity.highlightColor,
            "hillshade-accent-color": "#000000",
            "hillshade-illumination-direction":
              getIlluminationDirection(sunPosition),
          },
        },
        firstSymbolLayer?.id,
      );

      // Debug: log to verify hillshade is added
      console.log("Hillshade added with:", {
        exaggeration: intensity.exaggeration,
        shadow: intensity.shadowColor,
        highlight: intensity.highlightColor,
        direction: getIlluminationDirection(sunPosition),
      });

      // Add route line - clean up any existing first
      // Deduplicate points that are too close together (from multiple GPS sources)
      const dedupePoints = (pts) => {
        if (!pts.length) return [];
        const result = [pts[0]];
        for (let i = 1; i < pts.length; i++) {
          const prev = result[result.length - 1];
          const curr = pts[i];
          // Skip if within ~20 meters of previous point
          const dlat = Math.abs(curr.lat - prev.lat);
          const dlng = Math.abs(curr.lng - prev.lng);
          if (dlat > 0.0002 || dlng > 0.0002) {
            // ~20m
            result.push(curr);
          }
        }
        return result;
      };
      const routePoints = dedupePoints(points);
      const coordinates = routePoints.map((p) => [p.lng, p.lat]);

      // Remove existing route layers/source if they exist (prevents double render)
      if (map.current.getLayer("route-hit-area"))
        map.current.removeLayer("route-hit-area");
      if (map.current.getLayer("route-color-accent"))
        map.current.removeLayer("route-color-accent");
      if (map.current.getLayer("route-line"))
        map.current.removeLayer("route-line");
      if (map.current.getSource("route")) map.current.removeSource("route");

      map.current.addSource("route", {
        type: "geojson",
        data: {
          type: "Feature",
          geometry: { type: "LineString", coordinates },
        },
      });

      // Thick white line - black inverts to white
      map.current.addLayer({
        id: "route-line",
        type: "line",
        source: "route",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": "#000000",
          "line-width": 7,
          "line-opacity": 1,
        },
      });

      // Color accent line through center - inverted dayColor
      // Invert the color so it displays correctly after CSS invert
      const invertColor = (hex) => {
        const r = 255 - parseInt(hex.slice(1, 3), 16);
        const g = 255 - parseInt(hex.slice(3, 5), 16);
        const b = 255 - parseInt(hex.slice(5, 7), 16);
        return `rgb(${r}, ${g}, ${b})`;
      };

      map.current.addLayer({
        id: "route-color-accent",
        type: "line",
        source: "route",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": invertColor(dayColor),
          "line-width": 1.5,
          "line-opacity": 1,
        },
      });

      // Add invisible wider hit area for easier clicking
      map.current.addLayer({
        id: "route-hit-area",
        type: "line",
        source: "route",
        layout: { "line-join": "round", "line-cap": "round" },
        paint: {
          "line-color": "transparent",
          "line-width": 20,
          "line-opacity": 0,
        },
      });

      // Click handler for route
      if (onLocationClick && points.length > 0) {
        // Change cursor on hover
        map.current.on("mouseenter", "route-hit-area", () => {
          map.current.getCanvas().style.cursor = "pointer";
        });
        map.current.on("mouseleave", "route-hit-area", () => {
          map.current.getCanvas().style.cursor = "";
        });

        // Handle click - find nearest point
        map.current.on("click", "route-hit-area", (e) => {
          const clickLng = e.lngLat.lng;
          const clickLat = e.lngLat.lat;

          // Find the closest point on the route
          let minDist = Infinity;
          let closestPoint = null;

          for (const point of points) {
            if (!point.lat || !point.lng || !point.timestamp) continue;
            const dist =
              Math.pow(point.lng - clickLng, 2) +
              Math.pow(point.lat - clickLat, 2);
            if (dist < minDist) {
              minDist = dist;
              closestPoint = point;
            }
          }

          if (closestPoint?.timestamp) {
            onLocationClick(closestPoint.timestamp);
          }
        });
      }

      // Add start marker - black inverts to white
      if (points.length > 0) {
        const startEl = document.createElement("div");
        startEl.style.cssText = `
          width: 16px;
          height: 16px;
          background: #000000;
          border: 3px solid #ffffff;
          border-radius: 50%;
        `;
        new maplibregl.Marker({ element: startEl })
          .setLngLat([points[0].lng, points[0].lat])
          .addTo(map.current);

        // Add end marker if different from start
        const lastPoint = points[points.length - 1];
        const distance = Math.sqrt(
          Math.pow(lastPoint.lng - points[0].lng, 2) +
            Math.pow(lastPoint.lat - points[0].lat, 2),
        );

        if (distance > 0.01) {
          // Only show end if significantly different from start
          const endEl = document.createElement("div");
          endEl.style.cssText = `
            width: 14px;
            height: 14px;
            background: #ffffff;
            border: 3px solid #000000;
            border-radius: 50%;
          `;
          new maplibregl.Marker({ element: endEl })
            .setLngLat([lastPoint.lng, lastPoint.lat])
            .addTo(map.current);
        }
      }

      // Add highlight markers
      highlights.forEach((highlight) => {
        if (!highlight.location) return;

        const icon = HIGHLIGHT_ICONS[highlight.type] || HIGHLIGHT_ICONS.other;
        const el = document.createElement("div");
        el.style.cssText = `
          width: 28px;
          height: 28px;
          background: white;
          border: 2px solid #1a1a1a;
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: 14px;
          cursor: pointer;
        `;
        el.textContent = icon;
        el.title = highlight.title || "";

        new maplibregl.Marker({ element: el })
          .setLngLat([highlight.location.lng, highlight.location.lat])
          .addTo(map.current);
      });

      setMapLoaded(true);
    });

    // Handle resize
    const resizeObserver = new ResizeObserver(() => {
      if (map.current) {
        map.current.resize();
        if (bounds) {
          map.current.fitBounds(
            [
              [bounds.minLng, bounds.minLat],
              [bounds.maxLng, bounds.maxLat],
            ],
            { padding: isMobile ? 30 : 50, duration: 0 },
          );
        }
      }
    });
    resizeObserver.observe(mapContainer.current);

    return () => {
      resizeObserver.disconnect();
      if (map.current) {
        map.current.remove();
        map.current = null;
        mountedRef.current = false;
      }
      // Reset marker ref and map loaded state for clean reinit
      photoMarkerRef.current = null;
      setMapLoaded(false);
    };
  }, [bounds, points, dayColor, highlights, isMobile, onLocationClick]);

  // Update hillshade lighting when sunPosition changes
  useEffect(() => {
    if (!mapLoaded || !map.current) return;

    // Helper functions (duplicated from init for dynamic updates)
    const getIlluminationDirection = (sunPos) => {
      if (!sunPos) return 315;
      const azimuthDeg = (sunPos.azimuth * 180) / Math.PI + 180;
      return ((azimuthDeg % 360) + 360) % 360;
    };

    const getSunIntensity = (sunPos) => {
      if (!sunPos)
        return {
          exaggeration: 0.8,
          shadowColor: "#cccccc",
          highlightColor: "#000000",
        };
      const altitudeDeg = (sunPos.altitude * 180) / Math.PI;

      // Smooth interpolation based on solar altitude
      // Range: -12° (deep night) to +15° (full day)
      const lerp = (a, b, t) => a + (b - a) * Math.max(0, Math.min(1, t));
      const lerpColor = (c1, c2, t) => {
        const r1 = parseInt(c1.slice(1, 3), 16),
          g1 = parseInt(c1.slice(3, 5), 16),
          b1 = parseInt(c1.slice(5, 7), 16);
        const r2 = parseInt(c2.slice(1, 3), 16),
          g2 = parseInt(c2.slice(3, 5), 16),
          b2 = parseInt(c2.slice(5, 7), 16);
        const r = Math.round(lerp(r1, r2, t)),
          g = Math.round(lerp(g1, g2, t)),
          b = Math.round(lerp(b1, b2, t));
        return `#${r.toString(16).padStart(2, "0")}${g.toString(16).padStart(2, "0")}${b.toString(16).padStart(2, "0")}`;
      };

      // Normalize altitude to 0-1 range: -12° = 0, +15° = 1
      const t = (altitudeDeg + 12) / 27;

      // Exaggeration: peaks at low sun angles for dramatic shadows
      // Max is 1.0 in MapLibre
      let exaggeration;
      if (altitudeDeg < -6) {
        exaggeration = lerp(0.2, 0.5, (altitudeDeg + 12) / 6);
      } else if (altitudeDeg < 5) {
        exaggeration = lerp(0.5, 1.0, (altitudeDeg + 6) / 11); // peak at 1.0
      } else {
        exaggeration = 1.0; // stay at max
      }

      // Colors: smoothly transition from muted night to harsh day
      // Inverted map: shadow shows as light, highlight shows as dark
      const shadowColor = lerpColor("#222222", "#ffffff", t); // night gray -> pure white
      const highlightColor = lerpColor("#111111", "#000000", t); // night muted -> pure black

      return { exaggeration, shadowColor, highlightColor };
    };

    const intensity = getSunIntensity(sunPosition);

    // Update hillshade paint properties
    if (map.current.getLayer("hillshade")) {
      map.current.setPaintProperty(
        "hillshade",
        "hillshade-illumination-direction",
        getIlluminationDirection(sunPosition),
      );
      map.current.setPaintProperty(
        "hillshade",
        "hillshade-exaggeration",
        intensity.exaggeration,
      );
      map.current.setPaintProperty(
        "hillshade",
        "hillshade-shadow-color",
        intensity.shadowColor,
      );
      map.current.setPaintProperty(
        "hillshade",
        "hillshade-highlight-color",
        intensity.highlightColor,
      );
    }
  }, [sunPosition, mapLoaded]);

  // Update photo marker and pan/zoom to location when currentPhoto changes
  useEffect(() => {
    if (!mapLoaded || !map.current) return;

    // Debug: log currentPhoto to verify coordinates
    console.log("DayMap marker effect:", {
      hasPhoto: !!currentPhoto,
      lat: currentPhoto?.lat,
      lng: currentPhoto?.lng,
      timestamp: currentPhoto?.timestamp,
      mapLoaded,
      hasMapRef: !!map.current,
    });

    // Invert the color so it displays correctly after CSS invert
    const invertColor = (hex) => {
      const r = 255 - parseInt(hex.slice(1, 3), 16);
      const g = 255 - parseInt(hex.slice(3, 5), 16);
      const b = 255 - parseInt(hex.slice(5, 7), 16);
      return `rgb(${r}, ${g}, ${b})`;
    };

    // If we have a photo location, create or move the marker
    if (currentPhoto?.lat && currentPhoto?.lng) {
      const targetLngLat = [currentPhoto.lng, currentPhoto.lat];

      if (photoMarkerRef.current) {
        // Marker exists - animate it to new position
        const startLngLat = photoMarkerRef.current.getLngLat();
        const startTime = performance.now();
        const duration = 300; // ms

        const animate = (currentTime) => {
          const elapsed = currentTime - startTime;
          const t = Math.min(elapsed / duration, 1);
          // Ease out cubic
          const eased = 1 - Math.pow(1 - t, 3);

          const lng =
            startLngLat.lng + (targetLngLat[0] - startLngLat.lng) * eased;
          const lat =
            startLngLat.lat + (targetLngLat[1] - startLngLat.lat) * eased;

          photoMarkerRef.current.setLngLat([lng, lat]);

          if (t < 1) {
            requestAnimationFrame(animate);
          }
        };

        requestAnimationFrame(animate);
      } else {
        // Create new marker
        const el = document.createElement("div");
        el.style.cssText = `
          width: 24px;
          height: 24px;
          background: ${invertColor(dayColor)};
          border: 3px solid black;
          cursor: pointer;
        `;

        photoMarkerRef.current = new maplibregl.Marker({ element: el })
          .setLngLat(targetLngLat)
          .addTo(map.current);
      }

      // Smooth pan to photo location with zoom
      map.current.easeTo({
        center: targetLngLat,
        zoom: 10,
        duration: 300,
        easing: (t) => 1 - Math.pow(1 - t, 3), // Ease out cubic
      });
    } else if (photoMarkerRef.current) {
      // No photo location - remove marker
      photoMarkerRef.current.remove();
      photoMarkerRef.current = null;
    }
  }, [currentPhoto, mapLoaded, dayColor]);

  if (!bounds) {
    return (
      <div
        style={{
          height,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#f3f4f6",
          color: "#6b7280",
          fontSize: "14px",
        }}
      >
        No route data available
      </div>
    );
  }

  return (
    <div
      ref={mapContainer}
      style={{
        width: "100%",
        height,
        overflow: "hidden",
        filter: "invert(1)",
      }}
    />
  );
}
