import React, { useState, useMemo } from 'react';
import { Link } from 'wouter';
import { useTripContext } from '../contexts/TripContext';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { Loader2, AlertCircle } from 'lucide-react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { calculateDayOffsets, groupPointsByDayNumber } from '../components/common/RouteOffsets';

// Constants
const DEFAULT_DAY_COLORS = [
  "#2563eb", "#059669", "#d97706", "#dc2626", "#7c3aed",
  "#0891b2", "#ea580c", "#db2777", "#16a34a", "#0d9488",
  "#9333ea", "#0284c7"
];

const HIGHLIGHT_ICONS = {
  wildlife: '🦬', hotspring: '♨️', aurora: '✦', landscape: '◆', other: '●'
};

// Map style - Stadia Stamen Toner (free, no key required)
const getMapStyle = (apiKey) => {
  if (apiKey) {
    return `https://api.maptiler.com/maps/toner-v2/style.json?key=${apiKey}`;
  }
  return `https://basemaps.cartocdn.com/gl/positron-gl-style/style.json`;
};

// Download helpers
function downloadGPX(points, filename) {
  const gpxContent = `<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="trips.jomcgi.dev"
  xmlns="http://www.topografix.com/GPX/1/1"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
  <metadata>
    <name>${filename}</name>
    <time>${new Date().toISOString()}</time>
  </metadata>
  <trk>
    <name>${filename}</name>
    <trkseg>
${points.map(p => `      <trkpt lat="${p.lat}" lon="${p.lng}">
        <time>${p.timestamp instanceof Date ? p.timestamp.toISOString() : new Date(p.timestamp).toISOString()}</time>
      </trkpt>`).join('\n')}
    </trkseg>
  </trk>
</gpx>`;

  const blob = new Blob([gpxContent], { type: 'application/gpx+xml' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${filename}.gpx`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function downloadJSON(points, filename) {
  const data = {
    name: filename,
    exportedAt: new Date().toISOString(),
    totalPoints: points.length,
    points: points.map(p => ({
      lat: p.lat,
      lng: p.lng,
      timestamp: p.timestamp instanceof Date ? p.timestamp.toISOString() : new Date(p.timestamp).toISOString(),
      ...(p.image && { image: p.image }),
      ...(p.tags?.length && { tags: p.tags })
    }))
  };

  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${filename}.json`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// Data Processing
function calculateDistance(points) {
  if (!points || points.length < 2) return 0;
  const R = 6371;
  let total = 0;
  for (let i = 0; i < points.length - 1; i++) {
    const p1 = points[i], p2 = points[i + 1];
    if (!p1.lat || !p2.lat) continue;
    const dLat = ((p2.lat - p1.lat) * Math.PI) / 180;
    const dLon = ((p2.lng - p1.lng) * Math.PI) / 180;
    const a = Math.sin(dLat / 2) ** 2 + Math.cos((p1.lat * Math.PI) / 180) * Math.cos((p2.lat * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
    total += R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }
  return Math.round(total);
}

function groupPointsByDay(points) {
  const days = {};
  points.forEach(point => {
    const ts = point.timestamp;
    const y = ts.getFullYear();
    const m = String(ts.getMonth() + 1).padStart(2, '0');
    const d = String(ts.getDate()).padStart(2, '0');
    const dayKey = `${y}-${m}-${d}`;
    if (!days[dayKey]) days[dayKey] = [];
    days[dayKey].push(point);
  });
  return Object.entries(days)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, pts], index) => ({
      dayNumber: index + 1,
      date,
      points: pts,
      distance: calculateDistance(pts)
    }));
}

function deriveStats(points) {
  if (!points?.length) return null;
  const days = groupPointsByDay(points);
  const totalDistance = calculateDistance(points);
  const lats = points.map(p => p.lat);
  const lngs = points.map(p => p.lng);
  
  const rawElevations = points.map(p => p.elevation).filter(e => e != null);
  const hasElevation = rawElevations.length > 0;
  
  const NOISE_THRESHOLD = 5;
  const validElevations = rawElevations.filter(e => e > NOISE_THRESHOLD);
  const elevationFloor = validElevations.length > 0 ? Math.min(...validElevations) : 0;
  const elevations = rawElevations.map(e => e <= NOISE_THRESHOLD ? elevationFloor : e);
  
  let totalAscent = 0;
  let totalDescent = 0;
  const CHANGE_THRESHOLD = 5;
  
  if (hasElevation) {
    for (let i = 1; i < points.length; i++) {
      let prev = points[i - 1].elevation;
      let curr = points[i].elevation;
      if (prev != null && curr != null) {
        prev = prev <= NOISE_THRESHOLD ? elevationFloor : prev;
        curr = curr <= NOISE_THRESHOLD ? elevationFloor : curr;
        const diff = curr - prev;
        if (Math.abs(diff) > CHANGE_THRESHOLD) {
          if (diff > 0) totalAscent += diff;
          else totalDescent += Math.abs(diff);
        }
      }
    }
  }
  
  const daysWithElevation = days.map(day => {
    let ascent = 0;
    let descent = 0;
    const dayElevations = day.points
      .map(p => p.elevation)
      .filter(e => e != null)
      .map(e => e <= NOISE_THRESHOLD ? elevationFloor : e);
    
    for (let i = 1; i < day.points.length; i++) {
      let prev = day.points[i - 1].elevation;
      let curr = day.points[i].elevation;
      if (prev != null && curr != null) {
        prev = prev <= NOISE_THRESHOLD ? elevationFloor : prev;
        curr = curr <= NOISE_THRESHOLD ? elevationFloor : curr;
        const diff = curr - prev;
        if (Math.abs(diff) > CHANGE_THRESHOLD) {
          if (diff > 0) ascent += diff;
          else descent += Math.abs(diff);
        }
      }
    }
    
    return {
      ...day,
      ascent: Math.round(ascent),
      descent: Math.round(descent),
      maxElevation: dayElevations.length ? Math.max(...dayElevations) : null,
      minElevation: dayElevations.length ? Math.min(...dayElevations) : null,
    };
  });
  
  return {
    totalDistance,
    totalDays: days.length,
    totalPoints: points.length,
    maxLat: Math.max(...lats),
    minLat: Math.min(...lats),
    maxLng: Math.max(...lngs),
    minLng: Math.min(...lngs),
    startDate: new Date(points[0].timestamp),
    endDate: new Date(points[points.length - 1].timestamp),
    days: daysWithElevation,
    longestDay: Math.max(...days.map(d => d.distance)),
    hasElevation,
    maxElevation: hasElevation ? Math.max(...elevations) : null,
    minElevation: hasElevation ? Math.min(...elevations) : null,
    totalAscent: Math.round(totalAscent),
    totalDescent: Math.round(totalDescent),
    maxDayAscent: Math.max(...daysWithElevation.map(d => d.ascent)),
    maxDayDescent: Math.max(...daysWithElevation.map(d => d.descent)),
  };
}

// Elevation Sparkline - Filled Area (Monochrome)
function ElevationSparkline({ points, height = 28, globalMin, globalMax }) {
  const NOISE_THRESHOLD = 5;
  const rawElevations = points.map(p => p.elevation).filter(e => e != null);
  if (rawElevations.length < 2) return null;
  
  const validElevations = rawElevations.filter(e => e > NOISE_THRESHOLD);
  const elevationFloor = validElevations.length > 0 ? Math.min(...validElevations) : 0;
  const elevations = rawElevations.map(e => e <= NOISE_THRESHOLD ? elevationFloor : e);
  
  const min = globalMin ?? Math.min(...elevations);
  const max = globalMax ?? Math.max(...elevations);
  const range = max - min || 1;
  
  const maxPoints = 60;
  const step = Math.max(1, Math.floor(elevations.length / maxPoints));
  const sampled = elevations.filter((_, i) => i % step === 0);
  
  let pathD = `M 0 ${height} `;
  sampled.forEach((elev, i) => {
    const x = (i / (sampled.length - 1)) * 100;
    const y = height - ((elev - min) / range) * height;
    pathD += `L ${x} ${y} `;
  });
  pathD += `L 100 ${height} Z`;

  return (
    <svg 
      viewBox={`0 0 100 ${height}`} 
      preserveAspectRatio="none"
      style={{ width: '100%', height: `${height}px`, display: 'block' }}
    >
      <path d={pathD} fill="#1a1a1a" fillOpacity="0.85" />
    </svg>
  );
}

// MapLibre GL Map Component with offset support
function RouteMap({ points, days, dayColors, hoveredDay, onHoverDay, mapHeight = 280, isMobile = false }) {
  const wrapperRef = React.useRef(null);
  const mapContainer = React.useRef(null);
  const map = React.useRef(null);
  const [mapReady, setMapReady] = React.useState(false);
  const [containerWidth, setContainerWidth] = React.useState(0);
  const mapInitialized = React.useRef(false);

  const bounds = useMemo(() => {
    if (!points.length) return null;
    const lats = points.map(p => p.lat);
    const lngs = points.map(p => p.lng);
    return {
      minLat: Math.min(...lats),
      maxLat: Math.max(...lats),
      minLng: Math.min(...lngs),
      maxLng: Math.max(...lngs),
    };
  }, [points]);

  // Calculate if route is more east-west (horizontal) or north-south (vertical)
  const isHorizontalRoute = useMemo(() => {
    if (!bounds) return false;
    const latSpan = bounds.maxLat - bounds.minLat;
    const lngSpan = bounds.maxLng - bounds.minLng;
    // Approximate longitude to km conversion at mid-latitude
    const midLat = (bounds.maxLat + bounds.minLat) / 2;
    const lngKm = lngSpan * 111 * Math.cos(midLat * Math.PI / 180);
    const latKm = latSpan * 111;
    return lngKm > latKm * 1.2; // Route is horizontal if E-W span is 20% greater than N-S
  }, [bounds]);

  const furthestNorth = useMemo(() => {
    if (!points.length) return null;
    return points.reduce((max, p) => p.lat > max.lat ? p : max, points[0]);
  }, [points]);

  const dayOffsets = useMemo(() => {
    if (!days.length) return new Map();
    const pointsByDay = groupPointsByDayNumber(days);
    return calculateDayOffsets(pointsByDay, {
      overlapThreshold: 0.01,
      minOverlapPoints: 10,
      offsetAmount: 3,
    });
  }, [days]);

  // Measure container width and handle resize
  React.useEffect(() => {
    const updateWidth = () => {
      if (wrapperRef.current) {
        const newWidth = wrapperRef.current.offsetWidth;
        setContainerWidth(newWidth);
      }
      // Resize existing map and re-fit bounds
      if (map.current && bounds) {
        map.current.resize();
        // Small delay to let resize complete before fitting bounds
        setTimeout(() => {
          if (map.current) {
            map.current.fitBounds(
              [[bounds.minLng, bounds.minLat], [bounds.maxLng, bounds.maxLat]],
              { padding: 30, duration: 0 }
            );
          }
        }, 50);
      }
    };

    // Initial measurement
    const timer = setTimeout(updateWidth, 50);
    window.addEventListener('resize', updateWidth);
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', updateWidth);
    };
  }, [bounds]);

  // Create map only once when container is available
  React.useEffect(() => {
    // Skip if already initialized or no container
    if (mapInitialized.current || !bounds || !mapContainer.current) return;

    mapInitialized.current = true;
    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: getMapStyle(null),
      bounds: [[bounds.minLng, bounds.minLat], [bounds.maxLng, bounds.maxLat]],
      fitBoundsOptions: { padding: 40 },
      interactive: true,
      scrollZoom: false,
      boxZoom: false,
      dragRotate: false,
      dragPan: false,
      keyboard: false,
      doubleClickZoom: false,
      touchZoomRotate: false,
      attributionControl: false
    });

    map.current.on('load', () => {
      days.forEach((day, i) => {
        const color = dayColors[i] || DEFAULT_DAY_COLORS[i % DEFAULT_DAY_COLORS.length];
        const coordinates = day.points.map(p => [p.lng, p.lat]);
        const offset = dayOffsets.get(day.dayNumber) || 0;

        map.current.addSource(`route-${i}`, {
          type: 'geojson',
          data: {
            type: 'Feature',
            geometry: { type: 'LineString', coordinates }
          }
        });

        map.current.addLayer({
          id: `route-${i}-glow`,
          type: 'line',
          source: `route-${i}`,
          layout: { 'line-join': 'round', 'line-cap': 'round' },
          paint: {
            'line-color': color,
            'line-width': 8,
            'line-opacity': 0.25,
            'line-blur': 3,
            'line-offset': offset
          }
        });

        map.current.addLayer({
          id: `route-${i}`,
          type: 'line',
          source: `route-${i}`,
          layout: { 'line-join': 'round', 'line-cap': 'round' },
          paint: {
            'line-color': color,
            'line-width': 3,
            'line-opacity': 1,
            'line-offset': offset
          }
        });

        map.current.on('mouseenter', `route-${i}`, () => {
          map.current.getCanvas().style.cursor = 'pointer';
          onHoverDay?.(i);
        });
        map.current.on('mouseenter', `route-${i}-glow`, () => {
          map.current.getCanvas().style.cursor = 'pointer';
          onHoverDay?.(i);
        });
        map.current.on('mouseleave', `route-${i}`, () => {
          map.current.getCanvas().style.cursor = '';
          onHoverDay?.(null);
        });
        map.current.on('mouseleave', `route-${i}-glow`, () => {
          map.current.getCanvas().style.cursor = '';
          onHoverDay?.(null);
        });
      });

      const startEl = document.createElement('div');
      startEl.style.cssText = 'width:14px;height:14px;background:#1a1a1a;border:2px solid white;border-radius:50%;';
      new maplibregl.Marker({ element: startEl })
        .setLngLat([points[0].lng, points[0].lat])
        .addTo(map.current);

      if (furthestNorth) {
        const northEl = document.createElement('div');
        northEl.style.cssText = 'width:14px;height:14px;background:white;border:2.5px solid #1a1a1a;border-radius:50%;';
        new maplibregl.Marker({ element: northEl })
          .setLngLat([furthestNorth.lng, furthestNorth.lat])
          .addTo(map.current);
      }

      setMapReady(true);
    });
  }, [bounds, days, dayColors, points, furthestNorth, dayOffsets, containerWidth]);

  // Cleanup only on unmount
  React.useEffect(() => {
    return () => {
      if (map.current) {
        map.current.remove();
        map.current = null;
        mapInitialized.current = false;
      }
    };
  }, []);

  React.useEffect(() => {
    if (!map.current || !mapReady) return;
    
    days.forEach((_, i) => {
      const layerId = `route-${i}`;
      const glowId = `route-${i}-glow`;
      const isActive = hoveredDay === null || hoveredDay === i;
      
      if (map.current.getLayer(layerId)) {
        map.current.setPaintProperty(layerId, 'line-opacity', isActive ? 1 : 0.15);
        map.current.setPaintProperty(layerId, 'line-width', hoveredDay === i ? 4 : 3);
      }
      if (map.current.getLayer(glowId)) {
        map.current.setPaintProperty(glowId, 'line-opacity', isActive ? 0.25 : 0.05);
      }
    });
  }, [hoveredDay, days, mapReady]);

  if (!bounds) return null;

  // On mobile, rotate north-south routes 90° to fill horizontal space better
  const shouldRotate = isMobile && !isHorizontalRoute;
  const displayHeight = shouldRotate ? 200 : mapHeight;

  if (shouldRotate) {
    // For rotated maps: the map's height (after rotation) becomes the container width
    // So we render the map with width = displayHeight, height = containerWidth
    // After 90° rotation, it fills the container properly
    return (
      <div
        ref={wrapperRef}
        style={{
          position: 'relative',
          width: '100%',
          height: `${displayHeight}px`,
          overflow: 'hidden'
        }}
      >
        {containerWidth > 0 && (
          <>
            {/* Rotated map container */}
            <div style={{
              position: 'absolute',
              width: `${displayHeight}px`,
              height: `${containerWidth}px`,
              left: '50%',
              top: '50%',
              transform: 'translate(-50%, -50%) rotate(90deg)',
              transformOrigin: 'center center'
            }}>
              <div
                ref={mapContainer}
                style={{ width: '100%', height: '100%' }}
              />
            </div>
            {/* North indicator - points right since map is rotated */}
            <div style={{
              position: 'absolute',
              top: '8px',
              right: '8px',
              background: 'rgba(255,255,255,0.95)',
              borderRadius: '4px',
              padding: '4px 8px',
              fontSize: '10px',
              fontWeight: 700,
              fontFamily: 'monospace',
              color: '#1a1a1a',
              display: 'flex',
              alignItems: 'center',
              gap: '3px',
              boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
              zIndex: 10
            }}>
              <span style={{ fontSize: '12px', color: '#dc2626' }}>→</span> N
            </div>
          </>
        )}
      </div>
    );
  }

  return (
    <div ref={wrapperRef} style={{ width: '100%' }}>
      <div
        ref={mapContainer}
        style={{ width: '100%', height: `${mapHeight}px` }}
      />
    </div>
  );
}

function BigNumber({ value, unit, label, color, isMobile, scale = 1, isLargeDesktop = false, align = 'left' }) {
  return (
    <div style={{ textAlign: align }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: isMobile ? '4px' : `${4 * scale}px`, justifyContent: align === 'right' ? 'flex-end' : 'flex-start' }}>
        <span style={{
          fontSize: isMobile ? '36px' : isLargeDesktop ? `${32 * scale}px` : '40px',
          fontWeight: 800,
          fontFamily: 'system-ui, -apple-system, sans-serif',
          letterSpacing: '-0.03em',
          lineHeight: 1,
          color: color || '#1a1a1a'
        }}>
          {value}
        </span>
        {unit && <span style={{ fontSize: isMobile ? '16px' : isLargeDesktop ? `${13 * scale}px` : '16px', fontWeight: 600, color: '#9ca3af' }}>{unit}</span>}
      </div>
      <div style={{ fontSize: isMobile ? '10px' : isLargeDesktop ? `${8 * scale}px` : '10px', fontWeight: 600, fontFamily: 'monospace', letterSpacing: '0.05em', color: '#9ca3af', marginTop: `${3 * scale}px` }}>
        {label}
      </div>
    </div>
  );
}

function SmallStat({ value, unit, label, isMobile, scale = 1, isLargeDesktop = false, inline = false, labelColor = null, prefix = null, prefixColor = null, align = 'left' }) {
  if (inline) {
    return (
      <div style={{ textAlign: align }}>
        {label && <div style={{ fontSize: isMobile ? '9px' : '9px', fontWeight: 600, fontFamily: 'monospace', letterSpacing: '0.05em', color: labelColor || '#9ca3af', textTransform: 'uppercase', marginBottom: '2px' }}>{label}</div>}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: '3px', justifyContent: align === 'right' ? 'flex-end' : 'flex-start' }}>
          {prefix && <span style={{ fontSize: isMobile ? '14px' : '14px', fontWeight: 600, color: prefixColor || '#9ca3af' }}>{prefix}</span>}
          <span style={{ fontSize: isMobile ? '22px' : '22px', fontWeight: 700, fontFamily: 'system-ui', letterSpacing: '-0.02em', color: '#1a1a1a' }}>{value}</span>
          {unit && <span style={{ fontSize: isMobile ? '13px' : '13px', fontWeight: 500, color: '#9ca3af' }}>{unit}</span>}
        </div>
      </div>
    );
  }
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '2px' }}>
        <span style={{ fontSize: isMobile ? '16px' : isLargeDesktop ? `${14 * scale}px` : '18px', fontWeight: 700, fontFamily: 'system-ui', letterSpacing: '-0.02em', color: '#1a1a1a' }}>{value}</span>
        {unit && <span style={{ fontSize: isMobile ? '10px' : isLargeDesktop ? `${9 * scale}px` : '11px', fontWeight: 500, color: '#9ca3af' }}>{unit}</span>}
      </div>
      <div style={{ fontSize: isMobile ? '8px' : isLargeDesktop ? `${7 * scale}px` : '9px', fontWeight: 600, fontFamily: 'monospace', letterSpacing: '0.05em', color: '#9ca3af', marginTop: '2px' }}>{label}</div>
    </div>
  );
}

export function TripSummaryPage() {
  const { tripSlug, tripConfig, rawTripData, loading, error } = useTripContext();
  const [hoveredDay, setHoveredDay] = useState(null);

  const isMobile = useMediaQuery("(max-width: 768px)");
  const isTablet = useMediaQuery("(max-width: 1024px)");
  // Very large displays (4K+): fit everything on one screen
  const isLargeDesktop = useMediaQuery("(min-width: 2560px) and (min-height: 1400px)");
  // 5K or ultrawide: even more compact
  const is5K = useMediaQuery("(min-width: 3840px) and (min-height: 2000px)");

  const points = useMemo(() => {
    return rawTripData.filter(p => p.image !== null);
  }, [rawTripData]);

  const stats = useMemo(() => {
    if (!rawTripData?.length) return null;
    const baseStats = deriveStats(rawTripData);
    baseStats.coldestTemp = tripConfig?.stats?.coldest_temp ?? null;
    return baseStats;
  }, [rawTripData, tripConfig]);

  const dayColors = DEFAULT_DAY_COLORS;
  const highlights = tripConfig?.highlights || [];
  const tripTitle = tripConfig?.trip?.title || "ROAD TRIP";
  const tripSubtitle = tripConfig?.trip?.subtitle || "";

  const getDayLabel = (dayNumber) => {
    return tripConfig?.days?.[dayNumber]?.label || `Day ${dayNumber}`;
  };

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'system-ui' }}>
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-12 w-12 animate-spin text-blue-500" />
          <p className="text-gray-500">Loading trip data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: 'system-ui' }}>
        <div className="flex flex-col items-center gap-4">
          <AlertCircle className="h-12 w-12 text-amber-500" />
          <p className="text-gray-600">Error: {error}</p>
        </div>
      </div>
    );
  }

  if (!stats) return null;

  const formatDate = (d) => d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

  // Scaling factor for very large desktops to fit everything on one screen
  const scale = is5K ? 0.85 : isLargeDesktop ? 0.9 : 1;

  return (
    <div style={{
      height: isLargeDesktop ? '100vh' : 'auto',
      minHeight: isLargeDesktop ? 'auto' : '100vh',
      background: '#fff',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      padding: isMobile ? '16px' : isTablet ? '24px 28px' : isLargeDesktop ? `${24 * scale}px ${32 * scale}px` : '32px 40px',
      maxWidth: isLargeDesktop ? 'none' : '1400px',
      margin: '0 auto',
      overflowY: isLargeDesktop ? 'hidden' : 'auto',
      overflowX: 'hidden',
      WebkitOverflowScrolling: 'touch',
      display: isLargeDesktop ? 'flex' : 'block',
      flexDirection: 'column'
    }}>
      {/* HEADER */}
      <header style={{ marginBottom: isMobile ? '20px' : isLargeDesktop ? `${20 * scale}px` : '32px', flexShrink: 0 }}>
        <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'flex-start', justifyContent: 'space-between', marginBottom: isMobile ? '12px' : isLargeDesktop ? `${12 * scale}px` : '20px', gap: isMobile ? '12px' : '0' }}>
          <div>
            <div style={{ fontSize: isMobile ? '10px' : isLargeDesktop ? `${10 * scale}px` : '11px', fontWeight: 600, fontFamily: 'monospace', color: '#9ca3af', letterSpacing: '0.02em', marginBottom: `${4 * scale}px` }}>
              {formatDate(stats.startDate)} – {formatDate(stats.endDate)}, {stats.endDate.getFullYear()}
            </div>
            <h1 style={{ fontSize: isMobile ? '22px' : isTablet ? '24px' : isLargeDesktop ? `${24 * scale}px` : '28px', fontWeight: 800, letterSpacing: '-0.02em', margin: 0, color: '#1a1a1a' }}>
              {tripTitle}
            </h1>
            {tripSubtitle && <div style={{ fontSize: isMobile ? '12px' : isLargeDesktop ? `${12 * scale}px` : '13px', color: '#6b7280', marginTop: `${4 * scale}px` }}>{tripSubtitle}</div>}
          </div>
          <Link href={`/${tripSlug}/timeline`}>
            <button style={{
              padding: isMobile ? '10px 16px' : isLargeDesktop ? `${8 * scale}px ${16 * scale}px` : '10px 20px',
              fontSize: isMobile ? '11px' : isLargeDesktop ? `${10 * scale}px` : '12px',
              fontWeight: 700,
              fontFamily: 'monospace',
              background: '#1a1a1a',
              color: '#fff',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '8px',
              width: isMobile ? '100%' : 'auto'
            }}>
              TIMELINE →
            </button>
          </Link>
        </div>
      </header>

      {/* MAIN GRID */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: isMobile ? '1fr' : isTablet ? '280px 1fr' : isLargeDesktop ? `${280 * scale}px 1fr` : '320px 1fr',
        gap: isMobile ? '32px' : isTablet ? '40px' : isLargeDesktop ? `${40 * scale}px` : '60px',
        alignItems: 'start',
        flex: isLargeDesktop ? 1 : 'none',
        minHeight: 0
      }}>

        {/* LEFT: Map + Highlights */}
        <div style={{ position: isMobile ? 'relative' : isLargeDesktop ? 'relative' : 'sticky', top: isMobile ? 'auto' : isLargeDesktop ? 'auto' : '32px', display: 'flex', flexDirection: 'column', height: isLargeDesktop ? '100%' : 'auto' }}>
          <div style={{ marginBottom: isMobile ? '16px' : isLargeDesktop ? `${12 * scale}px` : '20px', borderRadius: '4px', overflow: 'hidden', border: '1px solid #e5e7eb', flexShrink: 0 }}>
            <RouteMap points={rawTripData} days={stats.days} dayColors={dayColors} hoveredDay={hoveredDay} onHoverDay={setHoveredDay} mapHeight={isLargeDesktop ? Math.round(220 * scale) : isMobile ? 240 : 280} isMobile={isMobile} />
            {/* Day color bar */}
            <div style={{ display: 'flex', background: '#fafafa', padding: '6px' }}>
              {stats.days.map((_, i) => (
                <div
                  key={i}
                  onMouseEnter={() => setHoveredDay(i)}
                  onMouseLeave={() => setHoveredDay(null)}
                  style={{
                    flex: 1,
                    height: '4px',
                    background: dayColors[i] || DEFAULT_DAY_COLORS[i % DEFAULT_DAY_COLORS.length],
                    opacity: hoveredDay === null ? 0.85 : (hoveredDay === i ? 1 : 0.2),
                    cursor: 'pointer',
                    transition: 'opacity 0.12s'
                  }}
                />
              ))}
            </div>
          </div>

          {/* Highlights */}
          {highlights.length > 0 && (
            <div style={{ flex: isLargeDesktop ? 1 : 'none', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <div style={{ fontSize: isLargeDesktop ? `${9 * scale}px` : '10px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '0.05em', color: '#9ca3af', marginBottom: isMobile ? '10px' : isLargeDesktop ? `${8 * scale}px` : '12px', flexShrink: 0 }}>
                HIGHLIGHTS
              </div>
              <div style={{
                display: 'grid',
                gridTemplateColumns: isMobile ? 'repeat(2, 1fr)' : isLargeDesktop ? 'repeat(3, 1fr)' : 'repeat(2, 1fr)',
                gap: isMobile ? '8px' : isLargeDesktop ? `${6 * scale}px` : '10px',
                flex: isLargeDesktop ? 1 : 'none',
                alignContent: 'start',
                overflow: isLargeDesktop ? 'hidden' : 'visible'
              }}>
                {highlights.map(h => {
                  const color = dayColors[h.day - 1] || DEFAULT_DAY_COLORS[(h.day - 1) % DEFAULT_DAY_COLORS.length];
                  return (
                    <div
                      key={h.id}
                      onMouseEnter={() => setHoveredDay(h.day - 1)}
                      onMouseLeave={() => setHoveredDay(null)}
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        padding: isMobile ? '8px' : isLargeDesktop ? `${6 * scale}px` : '10px',
                        background: hoveredDay === h.day - 1 ? '#f3f4f6' : '#fafafa',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        transition: 'background 0.1s'
                      }}
                    >
                      <div style={{
                        width: '100%',
                        aspectRatio: isLargeDesktop ? '1.2' : '1',
                        background: h.image ? 'transparent' : `linear-gradient(135deg, ${color}22, ${color}44)`,
                        borderRadius: '4px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: isMobile ? '24px' : isLargeDesktop ? `${20 * scale}px` : '28px',
                        overflow: 'hidden',
                        marginBottom: isMobile ? '6px' : isLargeDesktop ? `${4 * scale}px` : '8px'
                      }}>
                        {h.image ? (
                          <img src={h.image.startsWith('/') ? h.image : `/${h.image}`} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '4px' }}/>
                        ) : (
                          HIGHLIGHT_ICONS[h.type] || '●'
                        )}
                      </div>
                      <div style={{ fontSize: isMobile ? '12px' : isLargeDesktop ? `${10 * scale}px` : '13px', fontWeight: 600, color: '#1a1a1a', marginBottom: `${2 * scale}px` }}>{h.title}</div>
                      {h.comment && !isLargeDesktop && (
                        <div style={{ fontSize: isMobile ? '10px' : '11px', color: '#6b7280', marginBottom: isMobile ? '4px' : '6px', lineHeight: 1.4 }}>{h.comment}</div>
                      )}
                      <div style={{ fontSize: isMobile ? '9px' : isLargeDesktop ? `${8 * scale}px` : '10px', color: '#9ca3af', display: 'flex', alignItems: 'center', gap: isMobile ? '4px' : `${4 * scale}px`, marginTop: 'auto', fontFamily: 'monospace' }}>
                        <span style={{ width: isMobile ? '5px' : `${5 * scale}px`, height: isMobile ? '5px' : `${5 * scale}px`, borderRadius: '50%', background: color }}/>
                        Day {h.day}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* RIGHT: Charts & Data */}
        <div style={{ minWidth: 0, display: 'flex', flexDirection: 'column', height: isLargeDesktop ? '100%' : 'auto' }}>

          {/* Hero numbers - aligned above charts */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: isMobile ? '1fr' : stats.hasElevation ? '1fr 1fr' : '1fr',
            gap: isMobile ? '20px' : isLargeDesktop ? `${40 * scale}px` : '60px',
            marginBottom: isMobile ? '24px' : isLargeDesktop ? `${20 * scale}px` : '32px',
            flexShrink: 0
          }}>
            <div style={{ display: 'flex', gap: isMobile ? '24px' : isLargeDesktop ? `${28 * scale}px` : '40px', alignItems: 'flex-end', flexWrap: 'nowrap', justifyContent: isMobile ? 'space-between' : 'flex-start' }}>
              <BigNumber value={stats.totalDistance.toLocaleString()} unit="km" label="Total Distance" isMobile={isMobile} scale={scale} isLargeDesktop={isLargeDesktop} />
              <BigNumber value={stats.totalDays} unit="days" label="Duration" isMobile={isMobile} scale={scale} isLargeDesktop={isLargeDesktop} align={isMobile ? 'right' : 'left'} />
            </div>
            {stats.hasElevation ? (
              <div style={{ display: 'flex', gap: isMobile ? '24px' : isLargeDesktop ? `${28 * scale}px` : '40px', alignItems: 'flex-end', flexWrap: 'nowrap', justifyContent: isMobile ? 'space-between' : 'flex-start' }}>
                <BigNumber value={stats.maxLat.toFixed(2)} unit="°N" label="Furthest North" isMobile={isMobile} scale={scale} isLargeDesktop={isLargeDesktop} />
                {stats.coldestTemp !== null && (
                  <BigNumber value={stats.coldestTemp} unit="°C" label="Coldest Temp" color="#0891b2" isMobile={isMobile} scale={scale} isLargeDesktop={isLargeDesktop} align={isMobile ? 'right' : 'left'} />
                )}
              </div>
            ) : (
              <>
                <BigNumber value={stats.maxLat.toFixed(2)} unit="°N" label="Furthest North" isMobile={isMobile} scale={scale} isLargeDesktop={isLargeDesktop} />
                {stats.coldestTemp !== null && (
                  <BigNumber value={stats.coldestTemp} unit="°C" label="Coldest Temp" color="#0891b2" isMobile={isMobile} scale={scale} isLargeDesktop={isLargeDesktop} align={isMobile ? 'right' : 'left'} />
                )}
              </>
            )}
          </div>

{/* Charts Section - Grid layout with tighter chart/stat grouping */}
<div style={{
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : stats.hasElevation ? '1fr 1fr' : '1fr',
  gap: isMobile ? '32px' : isLargeDesktop ? `${40 * scale}px` : '60px',
  marginBottom: isMobile ? '32px' : isLargeDesktop ? `${30 * scale}px` : '50px',
  flexShrink: 0
}}>

  {/* Distance Group */}
  <div>
    <div style={{ fontSize: isMobile ? '9px' : isLargeDesktop ? `${9 * scale}px` : '10px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '0.05em', color: '#9ca3af', marginBottom: isMobile ? '12px' : isLargeDesktop ? `${10 * scale}px` : '16px' }}>
      DISTANCE
    </div>

    {isMobile ? (
      /* Mobile: full-width chart with stats row below */
      <div>
        <div style={{ display: 'flex', gap: '4px', height: '60px', alignItems: 'flex-end', marginBottom: '12px' }}>
          {stats.days.map((day, i) => (
            <div
              key={i}
              onClick={() => setHoveredDay(hoveredDay === i ? null : i)}
              style={{
                flex: 1,
                height: `${(day.distance / stats.longestDay) * 100}%`,
                minHeight: '8px',
                background: dayColors[i] || DEFAULT_DAY_COLORS[i % DEFAULT_DAY_COLORS.length],
                borderRadius: '4px 4px 0 0',
                opacity: hoveredDay === null ? 0.8 : (hoveredDay === i ? 1 : 0.3),
                transition: 'opacity 0.15s ease-out',
                cursor: 'pointer'
              }}
            />
          ))}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <SmallStat value={stats.longestDay} unit="km" label="Longest" isMobile={isMobile} scale={scale} isLargeDesktop={isLargeDesktop} inline />
          <SmallStat value={Math.round(stats.totalDistance / stats.totalDays)} unit="km" label="Avg" isMobile={isMobile} scale={scale} isLargeDesktop={isLargeDesktop} inline align="right" />
        </div>
      </div>
    ) : (
      /* Desktop: thin lines with stats beside */
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: '24px' }}>
        <div style={{ display: 'flex', gap: '3px', height: '50px', alignItems: 'flex-end' }}>
          {stats.days.map((day, i) => (
            <div
              key={i}
              onMouseEnter={() => setHoveredDay(i)}
              onMouseLeave={() => setHoveredDay(null)}
              style={{
                width: '4px',
                height: `${(day.distance / stats.longestDay) * 100}%`,
                minHeight: '8px',
                background: dayColors[i] || DEFAULT_DAY_COLORS[i % DEFAULT_DAY_COLORS.length],
                borderRadius: '100px',
                opacity: hoveredDay === null ? 0.7 : (hoveredDay === i ? 1 : 0.25),
                transition: 'opacity 0.15s ease-out',
                cursor: 'pointer'
              }}
              title={`Day ${day.dayNumber}: ${day.distance} km`}
            />
          ))}
        </div>
        <div style={{ display: 'flex', flexDirection: 'row', gap: '24px', alignItems: 'baseline', flexShrink: 0 }}>
          <SmallStat value={stats.longestDay} unit="km" label="Longest" isMobile={isMobile} scale={scale} isLargeDesktop={isLargeDesktop} inline />
          <SmallStat value={Math.round(stats.totalDistance / stats.totalDays)} unit="km" label="Avg" isMobile={isMobile} scale={scale} isLargeDesktop={isLargeDesktop} inline />
        </div>
      </div>
    )}
  </div>

  {/* Elevation Group */}
  {stats.hasElevation && (
    <div>
      <div style={{ fontSize: isMobile ? '9px' : isLargeDesktop ? `${9 * scale}px` : '10px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '0.05em', color: '#9ca3af', marginBottom: isMobile ? '12px' : isLargeDesktop ? `${10 * scale}px` : '16px' }}>
        ELEVATION
      </div>

      {isMobile ? (
        /* Mobile: full-width chart with stats row below */
        <div>
          <div style={{ display: 'flex', gap: '4px', height: '60px', position: 'relative', marginBottom: '12px' }}>
            {stats.days.map((day, i) => {
              const range = stats.maxElevation - stats.minElevation;
              const topPct = range > 0 ? ((day.maxElevation - stats.minElevation) / range) * 100 : 50;
              const bottomPct = range > 0 ? ((day.minElevation - stats.minElevation) / range) * 100 : 50;
              const heightPct = topPct - bottomPct;
              const color = dayColors[i] || DEFAULT_DAY_COLORS[i % DEFAULT_DAY_COLORS.length];
              return (
                <div
                  key={i}
                  onClick={() => setHoveredDay(hoveredDay === i ? null : i)}
                  style={{ flex: 1, position: 'relative', height: '100%', cursor: 'pointer' }}
                >
                  <div style={{
                    position: 'absolute',
                    bottom: `${bottomPct}%`,
                    height: `${Math.max(heightPct, 8)}%`,
                    width: '100%',
                    background: color,
                    borderRadius: '4px',
                    opacity: hoveredDay === null ? 0.8 : (hoveredDay === i ? 1 : 0.3),
                    transition: 'opacity 0.15s ease-out'
                  }} />
                </div>
              );
            })}
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
            <SmallStat value={stats.maxElevation.toLocaleString()} unit="m" label="Peak" isMobile={isMobile} scale={scale} isLargeDesktop={isLargeDesktop} inline />
            <SmallStat value={stats.totalAscent.toLocaleString()} unit="m" prefix="↑" prefixColor="#22c55e" isMobile={isMobile} scale={scale} isLargeDesktop={isLargeDesktop} inline />
            <SmallStat value={stats.totalDescent.toLocaleString()} unit="m" prefix="↓" prefixColor="#ef4444" isMobile={isMobile} scale={scale} isLargeDesktop={isLargeDesktop} inline align="right" />
          </div>
        </div>
      ) : (
        /* Desktop: thin lines with stats beside */
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: '24px' }}>
          <div style={{ display: 'flex', gap: '3px', height: '50px', position: 'relative' }}>
            {stats.days.map((day, i) => {
              const range = stats.maxElevation - stats.minElevation;
              const topPct = range > 0 ? ((day.maxElevation - stats.minElevation) / range) * 100 : 50;
              const bottomPct = range > 0 ? ((day.minElevation - stats.minElevation) / range) * 100 : 50;
              const heightPct = topPct - bottomPct;
              const color = dayColors[i] || DEFAULT_DAY_COLORS[i % DEFAULT_DAY_COLORS.length];
              return (
                <div
                  key={i}
                  onMouseEnter={() => setHoveredDay(i)}
                  onMouseLeave={() => setHoveredDay(null)}
                  style={{ width: '4px', position: 'relative', height: '100%', cursor: 'pointer' }}
                  title={`Day ${day.dayNumber}: ${day.minElevation}m – ${day.maxElevation}m`}
                >
                  <div style={{
                    position: 'absolute',
                    bottom: `${bottomPct}%`,
                    height: `${Math.max(heightPct, 8)}%`,
                    width: '100%',
                    background: color,
                    borderRadius: '100px',
                    opacity: hoveredDay === null ? 0.7 : (hoveredDay === i ? 1 : 0.25),
                    transition: 'opacity 0.15s ease-out'
                  }} />
                </div>
              );
            })}
          </div>
          <div style={{ display: 'flex', flexDirection: 'row', gap: '20px', alignItems: 'flex-end', flexShrink: 0 }}>
            <SmallStat value={stats.maxElevation.toLocaleString()} unit="m" label="Peak" isMobile={isMobile} scale={scale} isLargeDesktop={isLargeDesktop} inline />
            <SmallStat value={stats.totalAscent.toLocaleString()} unit="m" prefix="↑" prefixColor="#22c55e" isMobile={isMobile} scale={scale} isLargeDesktop={isLargeDesktop} inline />
            <SmallStat value={stats.totalDescent.toLocaleString()} unit="m" prefix="↓" prefixColor="#ef4444" isMobile={isMobile} scale={scale} isLargeDesktop={isLargeDesktop} inline />
          </div>
        </div>
      )}
    </div>
  )}
</div>

          {/* Daily Breakdown - Card layout for mobile, table for desktop */}
          {isMobile ? (
            /* Mobile: Stacked card layout - no horizontal scroll */
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ fontSize: '9px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '0.05em', color: '#9ca3af' }}>
                DAILY ROUTES
              </div>
              {stats.days.map((day, i) => {
                const color = dayColors[i] || DEFAULT_DAY_COLORS[i % DEFAULT_DAY_COLORS.length];
                return (
                  <div
                    key={i}
                    style={{
                      background: '#fafafa',
                      borderRadius: '6px',
                      padding: '12px'
                    }}
                  >
                    {/* Route title with colored underline */}
                    <div style={{ marginBottom: stats.hasElevation ? '8px' : '6px' }}>
                      {(() => {
                        const label = getDayLabel(day.dayNumber);
                        const arrowMatch = label.match(/^(.+?)\s*(→)\s*(.+)$/);
                        if (arrowMatch) {
                          const [, from, arrow, to] = arrowMatch;
                          return (
                            <span style={{
                              fontSize: '12px',
                              fontWeight: 600,
                              color: '#1a1a1a',
                              paddingBottom: '3px',
                              borderBottom: `1.5px solid ${color}`,
                              display: 'inline-flex',
                              flexWrap: 'wrap',
                              gap: '0 4px'
                            }}>
                              <span style={{ whiteSpace: 'nowrap' }}>{from} {arrow}</span>
                              <span style={{ whiteSpace: 'nowrap' }}>{to}</span>
                            </span>
                          );
                        }
                        return (
                          <span style={{
                            fontSize: '12px',
                            fontWeight: 600,
                            color: '#1a1a1a',
                            paddingBottom: '3px',
                            borderBottom: `1.5px solid ${color}`
                          }}>
                            {label}
                          </span>
                        );
                      })()}
                    </div>

                    {/* Elevation sparkline - full width */}
                    {stats.hasElevation && (
                      <div style={{ height: '32px', marginBottom: '10px' }}>
                        <ElevationSparkline
                          points={day.points}
                          height={32}
                          globalMin={stats.minElevation}
                          globalMax={stats.maxElevation}
                        />
                      </div>
                    )}

                    {/* Stats row */}
                    <div style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      fontSize: '11px',
                      fontFamily: 'monospace'
                    }}>
                      <span style={{ fontWeight: 600, color: '#1a1a1a' }}>
                        {day.distance} km
                      </span>
                      {stats.hasElevation && (
                        <span style={{ color: '#6b7280' }}>
                          ↑{day.ascent}m ↓{day.descent}m
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            /* Desktop: Table layout */
            <div style={{ flex: isLargeDesktop ? 1 : 'none', minHeight: 0, display: 'flex', flexDirection: 'column' }}>
              <div style={{
                display: 'grid',
                gridTemplateColumns: stats.hasElevation ? '1.5fr 2fr 70px 90px' : '1fr 80px',
                padding: isLargeDesktop ? `0 0 ${8 * scale}px` : '0 0 12px',
                borderBottom: '2px solid #1a1a1a',
                fontSize: isLargeDesktop ? `${8 * scale}px` : '10px',
                fontWeight: 700,
                fontFamily: 'monospace',
                letterSpacing: '0.05em',
                color: '#9ca3af',
                gap: isLargeDesktop ? `${14 * scale}px` : '20px',
                flexShrink: 0
              }}>
                <div>ROUTE</div>
                {stats.hasElevation && <div>PROFILE</div>}
                <div style={{ textAlign: 'right' }}>KM</div>
                {stats.hasElevation && <div style={{ textAlign: 'right' }}>ELEV</div>}
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', flex: isLargeDesktop ? 1 : 'none', overflow: isLargeDesktop ? 'hidden' : 'visible' }}>
                {stats.days.map((day, i) => {
                  const color = dayColors[i] || DEFAULT_DAY_COLORS[i % DEFAULT_DAY_COLORS.length];
                  return (
                    <div
                      key={i}
                      onMouseEnter={() => setHoveredDay(i)}
                      onMouseLeave={() => setHoveredDay(null)}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: stats.hasElevation ? '1.5fr 2fr 70px 90px' : '1fr 80px',
                        padding: isLargeDesktop ? `${8 * scale}px 0` : '14px 0',
                        borderBottom: '1px solid #f3f4f6',
                        background: hoveredDay === i ? '#fafafa' : 'transparent',
                        transition: 'background 0.1s',
                        alignItems: 'center',
                        gap: isLargeDesktop ? `${14 * scale}px` : '20px',
                        cursor: 'pointer',
                        flex: isLargeDesktop ? 1 : 'none',
                        minHeight: 0
                      }}
                    >
                      <div style={{ minWidth: 0 }}>
                        {(() => {
                          const label = getDayLabel(day.dayNumber);
                          const arrowMatch = label.match(/^(.+?)\s*(→)\s*(.+)$/);
                          if (arrowMatch) {
                            const [, from, arrow, to] = arrowMatch;
                            return (
                              <span style={{
                                fontWeight: 600,
                                color: '#1a1a1a',
                                fontSize: isLargeDesktop ? `${10 * scale}px` : '13px',
                                paddingBottom: `${3 * scale}px`,
                                borderBottom: `1.5px solid ${color}`,
                                display: 'inline-flex',
                                flexWrap: 'wrap',
                                gap: '0 4px'
                              }}>
                                <span style={{ whiteSpace: 'nowrap' }}>{from} {arrow}</span>
                                <span style={{ whiteSpace: 'nowrap' }}>{to}</span>
                              </span>
                            );
                          }
                          return (
                            <span style={{
                              fontWeight: 600,
                              color: '#1a1a1a',
                              fontSize: isLargeDesktop ? `${10 * scale}px` : '13px',
                              paddingBottom: `${3 * scale}px`,
                              borderBottom: `1.5px solid ${color}`
                            }}>
                              {label}
                            </span>
                          );
                        })()}
                      </div>

                      {stats.hasElevation && (
                        <div style={{ height: isLargeDesktop ? `${18 * scale}px` : '24px' }}>
                          <ElevationSparkline
                            points={day.points}
                            height={isLargeDesktop ? Math.round(18 * scale) : 24}
                            globalMin={stats.minElevation}
                            globalMax={stats.maxElevation}
                          />
                        </div>
                      )}

                      <div style={{ textAlign: 'right', fontWeight: 600, color: '#1a1a1a', fontSize: isLargeDesktop ? `${10 * scale}px` : '13px', fontFamily: 'monospace' }}>
                        {day.distance}
                      </div>

                      {stats.hasElevation && (
                        <div style={{ textAlign: 'right', fontSize: isLargeDesktop ? `${9 * scale}px` : '11px', fontFamily: 'monospace', color: '#6b7280' }}>
                          +{day.ascent}/-{day.descent}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* FOOTER */}
      <footer style={{
        marginTop: isMobile ? '32px' : isLargeDesktop ? `${16 * scale}px` : '48px',
        paddingTop: isMobile ? '16px' : isLargeDesktop ? `${12 * scale}px` : '20px',
        borderTop: '1px solid #e5e7eb',
        display: 'flex',
        justifyContent: isMobile ? 'center' : 'flex-end',
        alignItems: 'center',
        gap: isMobile ? '12px' : `${8 * scale}px`,
        flexWrap: 'wrap',
        flexShrink: 0
      }}>
        <button
          onClick={() => downloadGPX(points, tripSlug.replace(/\//g, '-'))}
          style={{
            padding: isMobile ? '10px 16px' : isLargeDesktop ? `${6 * scale}px ${12 * scale}px` : '8px 14px',
            fontSize: isMobile ? '10px' : isLargeDesktop ? `${9 * scale}px` : '11px',
            fontWeight: 600,
            fontFamily: 'monospace',
            background: 'transparent',
            border: '1px solid #e5e7eb',
            borderRadius: '4px',
            color: '#6b7280',
            cursor: 'pointer',
            minWidth: isMobile ? '100px' : 'auto'
          }}
        >
          ↓ GPX
        </button>
        <button
          onClick={() => downloadJSON(points, tripSlug.replace(/\//g, '-'))}
          style={{
            padding: isMobile ? '10px 16px' : isLargeDesktop ? `${6 * scale}px ${12 * scale}px` : '8px 14px',
            fontSize: isMobile ? '10px' : isLargeDesktop ? `${9 * scale}px` : '11px',
            fontWeight: 600,
            fontFamily: 'monospace',
            background: 'transparent',
            border: '1px solid #e5e7eb',
            borderRadius: '4px',
            color: '#6b7280',
            cursor: 'pointer',
            minWidth: isMobile ? '100px' : 'auto'
          }}
        >
          ↓ JSON
        </button>
      </footer>
    </div>
  );
}

export default TripSummaryPage;