import React, { useRef, useState, useEffect, useMemo } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { DAY_COLORS } from "../../constants/colors";
import {
  calculateDayOffsets,
  groupPointsByDayNumber,
  calculateMarkerOffset,
} from "../common/RouteOffsets";

export function TripMap({
  points,
  selectablePoints,
  selectedId,
  onMarkerClick,
  isLive,
  skipInitialZoom = false,
  initialZoom = 4,
}) {
  const mapContainer = useRef(null);
  const map = useRef(null);
  const markerRef = useRef(null);
  const [mapLoaded, setMapLoaded] = useState(false);
  const mountedRef = useRef(false);
  const dayOffsetsRef = useRef(new Map());

  // Calculate day boundaries from points
  const mapDayBoundaries = useMemo(() => {
    if (points.length === 0) return [];

    const boundaries = [];
    let currentDate = null;

    points.forEach((point, index) => {
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
  }, [points]);

  // Split points into day segments
  const { daySegments, gapSegments } = useMemo(() => {
    const splitIntoRuns = (dayPoints, dayNumber, color) => {
      const realRuns = [];
      const gapRuns = [];
      let currentRealRun = [];
      let currentGapRun = [];

      for (const p of dayPoints) {
        const isGap = p.image === null;
        if (isGap) {
          if (currentRealRun.length > 0) {
            realRuns.push({ dayNumber, points: currentRealRun, color });
            currentRealRun = [];
          }
          currentGapRun.push(p);
        } else {
          if (currentGapRun.length > 0) {
            gapRuns.push({ dayNumber, points: currentGapRun, color });
            currentGapRun = [];
          }
          currentRealRun.push(p);
        }
      }

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
        daySegments:
          realRuns.length > 0
            ? realRuns
            : [{ dayNumber: 1, points: [], color: DAY_COLORS[0] }],
        gapSegments: gapRuns,
      };
    }

    const allRealRuns = [];
    const allGapRuns = [];

    for (let i = 0; i < mapDayBoundaries.length; i++) {
      const startIdx = mapDayBoundaries[i].index;
      const endIdx =
        i < mapDayBoundaries.length - 1
          ? mapDayBoundaries[i + 1].index
          : points.length;

      const dayPoints = points.slice(startIdx, endIdx);
      const color = DAY_COLORS[i % DAY_COLORS.length];
      const { realRuns, gapRuns } = splitIntoRuns(
        dayPoints,
        mapDayBoundaries[i].dayNumber,
        color,
      );

      allRealRuns.push(...realRuns);
      allGapRuns.push(...gapRuns);
    }

    return { daySegments: allRealRuns, gapSegments: allGapRuns };
  }, [points, mapDayBoundaries]);

  // Calculate day offsets using shared utility
  const dayOffsets = useMemo(() => {
    const allSegments = [...daySegments, ...gapSegments];
    if (allSegments.length === 0) return new Map();

    const pointsByDay = groupPointsByDayNumber(allSegments);
    return calculateDayOffsets(pointsByDay, {
      overlapThreshold: 1.0541, // Original threshold for detailed view
      minOverlapPoints: 10,
      sampleRate: 5,
      offsetAmount: 4,
    });
  }, [daySegments, gapSegments]);

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

      // Create route layers for each segment
      daySegments.forEach((segment, idx) => {
        const routeCoords = segment.points.map((p) => [p.lng, p.lat]);
        const sourceId = `route-segment-${idx}`;
        const offset = dayOffsetsRef.current.get(segment.dayNumber) || 0;

        map.current.addSource(sourceId, {
          type: "geojson",
          data: {
            type: "Feature",
            properties: { day: segment.dayNumber },
            geometry: { type: "LineString", coordinates: routeCoords },
          },
        });

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

      // Add day labels
      const labeledDays = new Set();

      const addDayLabel = (segment) => {
        if (segment.points.length > 0 && !labeledDays.has(segment.dayNumber)) {
          labeledDays.add(segment.dayNumber);
          const labelIdx = Math.floor(segment.points.length * 0.15);
          const labelPoint = segment.points[Math.max(labelIdx, 0)];
          const labelSourceId = `route-day-${segment.dayNumber}-label`;

          map.current.addSource(labelSourceId, {
            type: "geojson",
            data: {
              type: "Feature",
              properties: { day: segment.dayNumber },
              geometry: {
                type: "Point",
                coordinates: [labelPoint.lng, labelPoint.lat],
              },
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
      };

      daySegments.forEach(addDayLabel);
      gapSegments.forEach(addDayLabel);

      // Click handler for route lines
      const handleRouteClick = (e) => {
        const clickedLng = e.lngLat.lng;
        const clickedLat = e.lngLat.lat;
        const clickedDayNumber = e.features?.[0]?.properties?.day;

        let clickedDateStr = null;
        if (clickedDayNumber && mapDayBoundaries.length > 0) {
          const boundary = mapDayBoundaries.find(
            (b) => b.dayNumber === clickedDayNumber,
          );
          if (boundary) {
            clickedDateStr = boundary.dateStr;
          }
        }

        const allPoints = selectablePoints || points;

        const pointsToSearch = clickedDateStr
          ? allPoints.filter((p) => {
              if (p.image === null) return false;
              const pDateStr = p.timestamp.toLocaleDateString("en-CA", {
                timeZone: "America/Vancouver",
                year: "numeric",
                month: "2-digit",
                day: "2-digit",
              });
              return pDateStr === clickedDateStr;
            })
          : allPoints;

        let closestId = null;
        let minDist = Infinity;

        pointsToSearch.forEach((p) => {
          if (p.image === null) return;

          const dist =
            Math.pow(p.lng - clickedLng, 2) + Math.pow(p.lat - clickedLat, 2);
          if (dist < minDist) {
            minDist = dist;
            closestId = p.id;
          }
        });

        if (closestId !== null) {
          onMarkerClick(closestId);
        }
      };

      // Add click and hover handlers
      daySegments.forEach((_, idx) => {
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

      gapSegments.forEach((_, idx) => {
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

  // Update route lines when points change
  useEffect(() => {
    if (!mapLoaded || !map.current) return;

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
        const offset = dayOffsets.get(segment.dayNumber) || 0;
        if (map.current.getLayer(`${sourceId}-glow`)) {
          map.current.setPaintProperty(
            `${sourceId}-glow`,
            "line-color",
            segment.color,
          );
          map.current.setPaintProperty(
            `${sourceId}-glow`,
            "line-offset",
            offset,
          );
        }
        if (map.current.getLayer(`${sourceId}-line`)) {
          map.current.setPaintProperty(
            `${sourceId}-line`,
            "line-color",
            segment.color,
          );
          map.current.setPaintProperty(
            `${sourceId}-line`,
            "line-offset",
            offset,
          );
        }
      }
    });

    gapSegments.forEach((segment, idx) => {
      const sourceId = `gap-segment-${idx}`;
      const routeCoords = segment.points.map((p) => [p.lng, p.lat]);
      const offset = dayOffsets.get(segment.dayNumber) || 0;
      const source = map.current.getSource(sourceId);

      if (source) {
        source.setData({
          type: "Feature",
          properties: { day: segment.dayNumber, isGap: true },
          geometry: { type: "LineString", coordinates: routeCoords },
        });
        if (map.current.getLayer(`${sourceId}-line`)) {
          map.current.setPaintProperty(
            `${sourceId}-line`,
            "line-color",
            segment.color,
          );
          map.current.setPaintProperty(
            `${sourceId}-line`,
            "line-offset",
            offset,
          );
        }
      } else {
        map.current.addSource(sourceId, {
          type: "geojson",
          data: {
            type: "Feature",
            properties: { day: segment.dayNumber, isGap: true },
            geometry: { type: "LineString", coordinates: routeCoords },
          },
        });

        map.current.addLayer({
          id: `${sourceId}-line`,
          type: "line",
          source: sourceId,
          paint: {
            "line-color": segment.color,
            "line-width": 2,
            "line-opacity": 0.8,
            "line-offset": offset,
          },
        });
      }
    });
  }, [mapLoaded, daySegments, gapSegments, dayOffsets]);

  // Update marker position
  useEffect(() => {
    if (!mapLoaded || !map.current) return;

    const pointIndex = points.findIndex((p) => p.id === selectedId);
    if (pointIndex === -1) return;
    const point = points[pointIndex];

    if (markerRef.current) markerRef.current.remove();

    let dayColor = DAY_COLORS[0];
    let dayNumber = 1;
    if (mapDayBoundaries.length > 0) {
      const pointDateStr = point.timestamp.toLocaleDateString("en-CA", {
        timeZone: "America/Vancouver",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      });
      const dayBoundary = mapDayBoundaries.find(
        (b) => b.dateStr === pointDateStr,
      );
      if (dayBoundary) {
        dayNumber = dayBoundary.dayNumber;
        dayColor = DAY_COLORS[(dayNumber - 1) % DAY_COLORS.length];
      }
    }

    const lineOffset = dayOffsets.get(dayNumber) || 0;
    const markerOffset = calculateMarkerOffset(
      point,
      pointIndex,
      points,
      lineOffset,
    );

    const el = document.createElement("div");
    el.className = "current-marker";

    const baseColor = isLive ? "#ef4444" : dayColor;
    el.style.cssText = `
      width: ${isLive ? "20px" : "16px"};
      height: ${isLive ? "20px" : "16px"};
      background: ${baseColor};
      border: 3px solid white;
      border-radius: 50%;
      box-shadow: 0 0 ${isLive ? "20px" : "12px"} ${baseColor};
      ${isLive ? "animation: pulse 1.5s ease-in-out infinite;" : ""}
    `;

    markerRef.current = new maplibregl.Marker({
      element: el,
      offset: markerOffset,
    })
      .setLngLat([point.lng, point.lat])
      .addTo(map.current);

    // When skipInitialZoom is true, fit to the entire route bounding box
    // Once user navigates, skipInitialZoom becomes false and we zoom in normally
    if (skipInitialZoom && points.length > 0) {
      // Calculate bounding box of all points
      let minLng = Infinity,
        maxLng = -Infinity;
      let minLat = Infinity,
        maxLat = -Infinity;
      for (const p of points) {
        if (p.lng < minLng) minLng = p.lng;
        if (p.lng > maxLng) maxLng = p.lng;
        if (p.lat < minLat) minLat = p.lat;
        if (p.lat > maxLat) maxLat = p.lat;
      }
      map.current.fitBounds(
        [
          [minLng, minLat],
          [maxLng, maxLat],
        ],
        { padding: 40, duration: 800 },
      );
    } else {
      map.current.flyTo({
        center: [point.lng, point.lat],
        zoom: Math.max(map.current.getZoom(), isLive ? 8 : 7),
        duration: 800,
      });
    }
  }, [
    selectedId,
    mapLoaded,
    points,
    isLive,
    mapDayBoundaries,
    dayOffsets,
    skipInitialZoom,
  ]);

  return (
    <div
      ref={mapContainer}
      className="absolute top-0 left-0 right-0 bottom-0 w-full h-full"
    />
  );
}
