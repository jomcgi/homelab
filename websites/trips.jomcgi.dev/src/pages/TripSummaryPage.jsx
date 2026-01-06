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
function RouteMap({ points, days, dayColors, hoveredDay, onHoverDay }) {
  const mapContainer = React.useRef(null);
  const map = React.useRef(null);
  const [mapReady, setMapReady] = React.useState(false);
  
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

  React.useEffect(() => {
    if (map.current || !bounds) return;
    
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

    return () => {
      if (map.current) {
        map.current.remove();
        map.current = null;
        setMapReady(false);
      }
    };
  }, [bounds, days, dayColors, points, furthestNorth, dayOffsets]);

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

  return (
    <div
      ref={mapContainer}
      style={{ width: '100%', height: '280px' }}
    />
  );
}

function BigNumber({ value, unit, label, color, isMobile }) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: isMobile ? '3px' : '4px' }}>
        <span style={{
          fontSize: isMobile ? '28px' : '40px',
          fontWeight: 800,
          fontFamily: 'system-ui, -apple-system, sans-serif',
          letterSpacing: '-0.03em',
          lineHeight: 1,
          color: color || '#1a1a1a'
        }}>
          {value}
        </span>
        {unit && <span style={{ fontSize: isMobile ? '13px' : '16px', fontWeight: 600, color: '#9ca3af' }}>{unit}</span>}
      </div>
      <div style={{ fontSize: isMobile ? '9px' : '10px', fontWeight: 600, fontFamily: 'monospace', letterSpacing: '0.05em', color: '#9ca3af', marginTop: '4px' }}>
        {label}
      </div>
    </div>
  );
}

function SmallStat({ value, unit, label, isMobile }) {
  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '2px' }}>
        <span style={{ fontSize: isMobile ? '16px' : '18px', fontWeight: 700, fontFamily: 'system-ui', letterSpacing: '-0.02em', color: '#1a1a1a' }}>{value}</span>
        {unit && <span style={{ fontSize: isMobile ? '10px' : '11px', fontWeight: 500, color: '#9ca3af' }}>{unit}</span>}
      </div>
      <div style={{ fontSize: isMobile ? '8px' : '9px', fontWeight: 600, fontFamily: 'monospace', letterSpacing: '0.05em', color: '#9ca3af', marginTop: '2px' }}>{label}</div>
    </div>
  );
}

export function TripSummaryPage() {
  const { tripSlug, tripConfig, rawTripData, loading, error } = useTripContext();
  const [hoveredDay, setHoveredDay] = useState(null);

  const isMobile = useMediaQuery("(max-width: 768px)");
  const isTablet = useMediaQuery("(max-width: 1024px)");

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

  return (
    <div style={{
      minHeight: '100vh',
      background: '#fff',
      fontFamily: 'system-ui, -apple-system, sans-serif',
      padding: isMobile ? '16px' : isTablet ? '24px 28px' : '32px 40px',
      maxWidth: '1400px',
      margin: '0 auto'
    }}>
      {/* HEADER */}
      <header style={{ marginBottom: isMobile ? '20px' : '32px' }}>
        <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'flex-start', justifyContent: 'space-between', marginBottom: isMobile ? '12px' : '20px', gap: isMobile ? '12px' : '0' }}>
          <div>
            <div style={{ fontSize: isMobile ? '10px' : '11px', fontWeight: 600, fontFamily: 'monospace', color: '#9ca3af', letterSpacing: '0.02em', marginBottom: '4px' }}>
              {formatDate(stats.startDate)} – {formatDate(stats.endDate)}, {stats.endDate.getFullYear()}
            </div>
            <h1 style={{ fontSize: isMobile ? '22px' : isTablet ? '24px' : '28px', fontWeight: 800, letterSpacing: '-0.02em', margin: 0, color: '#1a1a1a' }}>
              {tripTitle}
            </h1>
            {tripSubtitle && <div style={{ fontSize: isMobile ? '12px' : '13px', color: '#6b7280', marginTop: '4px' }}>{tripSubtitle}</div>}
          </div>
          <Link href={`/${tripSlug}/timeline`}>
            <button style={{
              padding: isMobile ? '10px 16px' : '10px 20px',
              fontSize: isMobile ? '11px' : '12px',
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
      <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : isTablet ? '280px 1fr' : '320px 1fr', gap: isMobile ? '32px' : isTablet ? '40px' : '60px', alignItems: 'start' }}>

        {/* LEFT: Map + Highlights */}
        <div style={{ position: isMobile ? 'relative' : 'sticky', top: isMobile ? 'auto' : '32px' }}>
          <div style={{ marginBottom: isMobile ? '16px' : '20px', borderRadius: '4px', overflow: 'hidden', border: '1px solid #e5e7eb' }}>
            <RouteMap points={rawTripData} days={stats.days} dayColors={dayColors} hoveredDay={hoveredDay} onHoverDay={setHoveredDay} />
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
            <div>
              <div style={{ fontSize: '10px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '0.05em', color: '#9ca3af', marginBottom: isMobile ? '10px' : '12px' }}>
                HIGHLIGHTS
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: isMobile ? 'repeat(2, 1fr)' : isTablet ? 'repeat(2, 1fr)' : 'repeat(2, 1fr)', gap: isMobile ? '8px' : '10px' }}>
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
                        padding: isMobile ? '8px' : '10px',
                        background: hoveredDay === h.day - 1 ? '#f3f4f6' : '#fafafa',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        transition: 'background 0.1s'
                      }}
                    >
                      <div style={{
                        width: '100%',
                        aspectRatio: '1',
                        background: h.image ? 'transparent' : `linear-gradient(135deg, ${color}22, ${color}44)`,
                        borderRadius: '4px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: isMobile ? '24px' : '28px',
                        overflow: 'hidden',
                        marginBottom: isMobile ? '6px' : '8px'
                      }}>
                        {h.image ? (
                          <img src={h.image.startsWith('/') ? h.image : `/${h.image}`} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', borderRadius: '4px' }}/>
                        ) : (
                          HIGHLIGHT_ICONS[h.type] || '●'
                        )}
                      </div>
                      <div style={{ fontSize: isMobile ? '12px' : '13px', fontWeight: 600, color: '#1a1a1a', marginBottom: '3px' }}>{h.title}</div>
                      {h.comment && (
                        <div style={{ fontSize: isMobile ? '10px' : '11px', color: '#6b7280', marginBottom: isMobile ? '4px' : '6px', lineHeight: 1.4 }}>{h.comment}</div>
                      )}
                      <div style={{ fontSize: isMobile ? '9px' : '10px', color: '#9ca3af', display: 'flex', alignItems: 'center', gap: isMobile ? '4px' : '6px', marginTop: 'auto', fontFamily: 'monospace' }}>
                        <span style={{ width: isMobile ? '5px' : '6px', height: isMobile ? '5px' : '6px', borderRadius: '50%', background: color }}/>
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
        <div style={{ minWidth: 0 }}>

          {/* Hero numbers - aligned above charts */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: isMobile ? '1fr' : stats.hasElevation ? '1fr 1fr' : '1fr',
            gap: isMobile ? '20px' : '60px',
            marginBottom: isMobile ? '24px' : '32px'
          }}>
            <div style={{ display: 'flex', gap: isMobile ? '24px' : '40px', alignItems: 'flex-end', flexWrap: isMobile ? 'wrap' : 'nowrap' }}>
              <BigNumber value={stats.totalDistance.toLocaleString()} unit="km" label="Total Distance" isMobile={isMobile} />
              <BigNumber value={stats.totalDays} unit="days" label="Duration" isMobile={isMobile} />
            </div>
            {stats.hasElevation ? (
              <div style={{ display: 'flex', gap: isMobile ? '24px' : '40px', alignItems: 'flex-end', flexWrap: isMobile ? 'wrap' : 'nowrap' }}>
                <BigNumber value={stats.maxLat.toFixed(2)} unit="°N" label="Furthest North" isMobile={isMobile} />
                {stats.coldestTemp !== null && (
                  <BigNumber value={stats.coldestTemp} unit="°C" label="Coldest Temp" color="#0891b2" isMobile={isMobile} />
                )}
              </div>
            ) : (
              <>
                <BigNumber value={stats.maxLat.toFixed(2)} unit="°N" label="Furthest North" isMobile={isMobile} />
                {stats.coldestTemp !== null && (
                  <BigNumber value={stats.coldestTemp} unit="°C" label="Coldest Temp" color="#0891b2" isMobile={isMobile} />
                )}
              </>
            )}
          </div>

{/* Charts Section - Grid layout with tighter chart/stat grouping */}
<div style={{
  display: 'grid',
  gridTemplateColumns: isMobile ? '1fr' : stats.hasElevation ? '1fr 1fr' : '1fr',
  gap: isMobile ? '32px' : '60px',
  marginBottom: isMobile ? '32px' : '50px'
}}>

  {/* Distance Group */}
  <div>
    <div style={{ fontSize: isMobile ? '9px' : '10px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '0.05em', color: '#9ca3af', marginBottom: isMobile ? '12px' : '16px' }}>
      DAILY DISTANCE
    </div>

    <div style={{ display: 'flex', alignItems: 'flex-end', gap: isMobile ? '16px' : '24px' }}>
      {/* Chart grows to fill available space */}
      <div style={{ flex: 1, display: 'flex', gap: isMobile ? '2px' : '3px', height: isMobile ? '60px' : '80px', alignItems: 'flex-end' }}>
        {stats.days.map((day, i) => (
          <div
            key={i}
            onMouseEnter={() => setHoveredDay(i)}
            onMouseLeave={() => setHoveredDay(null)}
            style={{
              flex: 1,
              height: `${(day.distance / stats.longestDay) * 100}%`,
              minHeight: '4px',
              background: dayColors[i] || DEFAULT_DAY_COLORS[i % DEFAULT_DAY_COLORS.length],
              borderRadius: '2px 2px 0 0',
              opacity: hoveredDay === null ? 0.85 : (hoveredDay === i ? 1 : 0.2),
              transition: 'opacity 0.15s ease-out',
              cursor: 'pointer'
            }}
            title={`Day ${day.dayNumber}: ${day.distance} km`}
          />
        ))}
      </div>

      {/* Stats anchored right next to chart */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: isMobile ? '8px' : '12px', minWidth: isMobile ? '60px' : '80px' }}>
        <SmallStat value={stats.longestDay} unit="km" label="Longest" isMobile={isMobile} />
        <SmallStat value={Math.round(stats.totalDistance / stats.totalDays)} unit="km" label="Avg" isMobile={isMobile} />
      </div>
    </div>
  </div>

  {/* Elevation Group */}
  {stats.hasElevation && (
    <div>
      <div style={{ fontSize: isMobile ? '9px' : '10px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '0.05em', color: '#9ca3af', marginBottom: isMobile ? '12px' : '16px' }}>
        ELEVATION PROFILE
      </div>

      <div style={{ display: 'flex', alignItems: 'flex-end', gap: isMobile ? '16px' : '24px' }}>
        {/* Chart grows to fill available space */}
        <div style={{ flex: 1, display: 'flex', gap: isMobile ? '2px' : '3px', height: isMobile ? '60px' : '80px', position: 'relative' }}>
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
                style={{
                  flex: 1,
                  position: 'relative',
                  height: '100%',
                  cursor: 'pointer'
                }}
                title={`Day ${day.dayNumber}: ${day.minElevation}m – ${day.maxElevation}m`}
              >
                <div style={{
                  position: 'absolute',
                  bottom: `${bottomPct}%`,
                  height: `${Math.max(heightPct, 5)}%`,
                  width: '100%',
                  background: color,
                  borderRadius: '2px',
                  opacity: hoveredDay === null ? 0.6 : (hoveredDay === i ? 1 : 0.2),
                  transition: 'opacity 0.15s ease-out'
                }} />
              </div>
            );
          })}
        </div>

        {/* Stats anchored right next to chart - Peak is now unique to this section */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: isMobile ? '8px' : '12px', minWidth: isMobile ? '60px' : '80px' }}>
          <SmallStat value={stats.maxElevation.toLocaleString()} unit="m" label="Peak" isMobile={isMobile} />
          <SmallStat value={stats.totalAscent.toLocaleString()} unit="m" label="Ascent" isMobile={isMobile} />
          <SmallStat value={stats.totalDescent.toLocaleString()} unit="m" label="Descent" isMobile={isMobile} />
        </div>
      </div>
    </div>
  )}
</div>

          {/* Daily Breakdown Table */}
          <div style={{ overflowX: isMobile ? 'auto' : 'visible' }}>
            <div style={{
              display: 'grid',
              gridTemplateColumns: isMobile
                ? (stats.hasElevation ? '1fr 1.5fr 60px 80px' : '1fr 70px')
                : (stats.hasElevation ? '1.5fr 2fr 70px 90px' : '1fr 80px'),
              padding: isMobile ? '0 0 10px' : '0 0 12px',
              borderBottom: '2px solid #1a1a1a',
              fontSize: isMobile ? '9px' : '10px',
              fontWeight: 700,
              fontFamily: 'monospace',
              letterSpacing: '0.05em',
              color: '#9ca3af',
              gap: isMobile ? '12px' : '20px',
              minWidth: isMobile ? '480px' : 'auto'
            }}>
              <div>ROUTE</div>
              {stats.hasElevation && isMobile && <div>RANGE</div>}
              {stats.hasElevation && !isMobile && <div>PROFILE</div>}
              <div style={{ textAlign: 'right' }}>KM</div>
              {stats.hasElevation && isMobile && <div style={{ textAlign: 'right' }}>UP</div>}
              {stats.hasElevation && !isMobile && <div style={{ textAlign: 'right' }}>ELEV</div>}
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', minWidth: isMobile ? '480px' : 'auto' }}>
              {stats.days.map((day, i) => {
                const color = dayColors[i] || DEFAULT_DAY_COLORS[i % DEFAULT_DAY_COLORS.length];
                return (
                  <div
                    key={i}
                    onMouseEnter={() => setHoveredDay(i)}
                    onMouseLeave={() => setHoveredDay(null)}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: isMobile
                        ? (stats.hasElevation ? '1fr 1.5fr 60px 80px' : '1fr 70px')
                        : (stats.hasElevation ? '1.5fr 2fr 70px 90px' : '1fr 80px'),
                      padding: isMobile ? '10px 0' : '14px 0',
                      borderBottom: '1px solid #f3f4f6',
                      background: hoveredDay === i ? '#fafafa' : 'transparent',
                      transition: 'background 0.1s',
                      alignItems: 'center',
                      gap: isMobile ? '12px' : '20px',
                      cursor: 'pointer'
                    }}
                  >
                    <div>
                      <span style={{
                        fontWeight: 600,
                        color: '#1a1a1a',
                        fontSize: isMobile ? '11px' : '13px',
                        paddingBottom: isMobile ? '3px' : '4px',
                        borderBottom: `${isMobile ? '1.5px' : '1.5px'} solid ${color}`
                      }}>
                        {getDayLabel(day.dayNumber)}
                      </span>
                    </div>

                    {stats.hasElevation && (
                      <div style={{ height: isMobile ? '20px' : '24px' }}>
                        <ElevationSparkline
                          points={day.points}
                          height={isMobile ? 20 : 24}
                          globalMin={stats.minElevation}
                          globalMax={stats.maxElevation}
                        />
                      </div>
                    )}

                    <div style={{ textAlign: 'right', fontWeight: 600, color: '#1a1a1a', fontSize: isMobile ? '11px' : '13px', fontFamily: 'monospace' }}>
                      {day.distance}
                    </div>

                    {stats.hasElevation && (
                      <div style={{ textAlign: 'right', fontSize: isMobile ? '10px' : '11px', fontFamily: 'monospace', color: '#6b7280' }}>
                        +{day.ascent}/-{day.descent}
                      </div>
                    )}

                    {stats.hasElevation && isMobile && (
                      <div style={{ textAlign: 'right', fontSize: '10px', fontFamily: 'monospace', color: '#6b7280' }}>
                        +{day.ascent}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* FOOTER */}
      <footer style={{
        marginTop: isMobile ? '32px' : '48px',
        paddingTop: isMobile ? '16px' : '20px',
        borderTop: '1px solid #e5e7eb',
        display: 'flex',
        justifyContent: isMobile ? 'center' : 'flex-end',
        alignItems: 'center',
        gap: isMobile ? '12px' : '8px',
        flexWrap: 'wrap'
      }}>
        <button
          onClick={() => downloadGPX(points, tripSlug.replace(/\//g, '-'))}
          style={{
            padding: isMobile ? '10px 16px' : '8px 14px',
            fontSize: isMobile ? '10px' : '11px',
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
            padding: isMobile ? '10px 16px' : '8px 14px',
            fontSize: isMobile ? '10px' : '11px',
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