import React, { useMemo, useState } from 'react';
import { Redirect } from 'wouter';
import SunCalc from 'suncalc';
import { useTripContext } from '../contexts/TripContext';
import { useDayData } from '../hooks/useDayData';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { DayNavigation } from '../components/day/DayNavigation';
import { DayMap } from '../components/map/DayMap';
import { DayStatsCard } from '../components/day/DayStatsCard';
import { PhotoViewer } from '../components/day/PhotoViewer';
import { Loader2, AlertCircle } from 'lucide-react';
// DayPhotoGrid removed - using PhotoViewer instead

const HIGHLIGHT_ICONS = {
  wildlife: '🦬',
  hotspring: '♨️',
  aurora: '✦',
  landscape: '◆',
  other: '●'
};

/**
 * Day Detail Page - Shows detailed view for a single day of the trip
 * Route: /:trip/day/:dayNumber
 */
export function DayDetailPage({ dayNumber }) {
  const {
    tripSlug,
    tripConfig,
    rawTripData,
    tripData,
    loading,
    error
  } = useTripContext();

  const isMobile = useMediaQuery('(max-width: 768px)');

  // Get day-specific data
  const {
    dayLabel,
    dayDate,
    dayColor,
    dayPoints,
    dayPhotos,
    dayStats,
    dayHighlights,
    totalDays,
    isValidDay
  } = useDayData(rawTripData, tripData, tripConfig, dayNumber);

  // Photo viewer state (must be before early returns)
  const [currentPhotoIndex, setCurrentPhotoIndex] = useState(0);
  const currentPhoto = dayPhotos?.[currentPhotoIndex] || null;

  // Loading state
  if (loading) {
    return (
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#fafafa'
      }}>
        <Loader2
          size={32}
          style={{ animation: 'spin 1s linear infinite', color: '#6b7280' }}
        />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#fafafa',
        padding: '20px'
      }}>
        <AlertCircle size={48} style={{ color: '#ef4444', marginBottom: '16px' }} />
        <p style={{ color: '#ef4444', fontSize: '16px', textAlign: 'center' }}>
          {error}
        </p>
      </div>
    );
  }

  // Invalid day - redirect to summary
  // TRANSITION_HOOK: Page transition animation could be added here
  if (!isValidDay && totalDays > 0) {
    return <Redirect to={`/${tripSlug}`} />;
  }

  return (
    <div style={{
      minHeight: '100vh',
      background: 'white',
      fontFamily: 'system-ui, -apple-system, sans-serif'
    }}>
      <div style={{
        maxWidth: '1200px',
        margin: '0 auto',
        padding: isMobile ? '16px' : '24px 32px'
      }}>
        {/* Navigation Header */}
        <DayNavigation
          tripSlug={tripSlug}
          dayNumber={dayNumber}
          totalDays={totalDays}
          dayLabel={dayLabel}
          dayDate={dayDate}
          dayColor={dayColor}
          isMobile={isMobile}
        />

        {/* Main Content */}
        {isMobile ? (
          // Mobile: Single column stacked layout
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Map */}
            <DayMap
              points={dayPoints}
              highlights={dayHighlights}
              dayColor={dayColor}
              height="200px"
              isMobile={true}
              currentPhoto={currentPhoto}
              sunPosition={currentPhoto?.timestamp && currentPhoto?.lat && currentPhoto?.lng
                ? SunCalc.getPosition(currentPhoto.timestamp, currentPhoto.lat, currentPhoto.lng)
                : null}
            />

            {/* Photo viewer */}
            <PhotoViewer
              photos={dayPhotos}
              currentIndex={currentPhotoIndex}
              onIndexChange={setCurrentPhotoIndex}
              isMobile={true}
            />

            {/* Stats */}
            <DayStatsCard
              stats={dayStats}
              dayColor={dayColor}
              isMobile={true}
            />

            {/* Highlights */}
            {dayHighlights.length > 0 && (
              <section>
                <SectionHeader title="Highlights" isMobile={true} />
                <HighlightsGrid
                  highlights={dayHighlights}
                  dayColor={dayColor}
                  isMobile={true}
                />
              </section>
            )}
          </div>
        ) : (
          // Desktop: Map top, Photo viewer + Stats below
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
            {/* Map - full width, with dynamic sun position */}
            <DayMap
              points={dayPoints}
              highlights={dayHighlights}
              dayColor={dayColor}
              height="280px"
              isMobile={false}
              currentPhoto={currentPhoto}
              sunPosition={currentPhoto?.timestamp && currentPhoto?.lat && currentPhoto?.lng
                ? SunCalc.getPosition(currentPhoto.timestamp, currentPhoto.lat, currentPhoto.lng)
                : null}
            />

            {/* Photo viewer + Stats - strict 2-column grid */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: '1fr 280px',
              columnGap: '0',
              alignItems: 'start'
            }}>
              {/* Photo viewer - flush left, border right */}
              <div style={{
                borderRight: '2px solid #1a1a1a',
                paddingRight: '24px'
              }}>
                <PhotoViewer
                  photos={dayPhotos}
                  currentIndex={currentPhotoIndex}
                  onIndexChange={setCurrentPhotoIndex}
                  isMobile={false}
                  showTime={false}
                />
              </div>

              {/* Right panel - Telemetry */}
              <div style={{ paddingLeft: '24px' }}>
                <TelemetryPanel
                  photo={currentPhoto}
                  photoIndex={currentPhotoIndex}
                  dayPoints={dayPoints}
                  dayStats={dayStats}
                  dayColor={dayColor}
                />
              </div>
            </div>

            {/* Highlights (if any) */}
            {dayHighlights.length > 0 && (
              <section style={{ marginTop: '8px' }}>
                <SectionHeader title="Highlights" isMobile={false} />
                <HighlightsGrid
                  highlights={dayHighlights}
                  dayColor={dayColor}
                  isMobile={false}
                />
              </section>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// Section Header Component
function SectionHeader({ title, isMobile }) {
  return (
    <div style={{
      fontSize: isMobile ? '10px' : '11px',
      fontWeight: 700,
      fontFamily: 'monospace',
      letterSpacing: '0.08em',
      color: '#1a1a1a',
      textTransform: 'uppercase',
      marginBottom: isMobile ? '12px' : '16px',
      paddingBottom: '8px',
      borderBottom: '2px solid #1a1a1a'
    }}>
      {title}
    </div>
  );
}

// Telemetry Panel - industrial grade computed stats (manifest style)
function TelemetryPanel({ photo, photoIndex, dayPoints, dayStats, dayColor }) {
  // --- SOLAR CALCULATIONS ---
  const sunPosition = useMemo(() => {
    if (!photo?.timestamp || !photo?.lat || !photo?.lng) return null;
    return SunCalc.getPosition(photo.timestamp, photo.lat, photo.lng);
  }, [photo]);

  const sunTimes = useMemo(() => {
    if (!photo?.timestamp || !photo?.lat || !photo?.lng) return null;
    return SunCalc.getTimes(photo.timestamp, photo.lat, photo.lng);
  }, [photo]);

  const solarAltitude = sunPosition ? (sunPosition.altitude * 180 / Math.PI) : null;

  const getSolarLabel = (alt) => {
    if (alt == null) return 'UNKNOWN';
    if (alt < -6) return 'NIGHT';
    if (alt < 0) return 'TWILIGHT';
    if (alt < 10) return 'LOW';
    return 'DAY';
  };

  const getLightRemaining = () => {
    if (!photo?.timestamp || !sunTimes?.sunset) return null;
    const now = photo.timestamp.getTime();
    const sunset = sunTimes.sunset.getTime();
    if (now > sunset) return null;
    const diff = sunset - now;
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    return `${hours}h ${mins.toString().padStart(2, '0')}m`;
  };

  // --- PROGRESS CALCULATIONS ---
  const { progress, currentProgressIndex } = useMemo(() => {
    if (!dayPoints?.length || !photo?.timestamp) return { progress: null, currentProgressIndex: 0 };

    const photoTime = photo.timestamp.getTime();
    let distanceTraveled = 0;
    let totalDistance = 0;
    let prevPoint = null;
    let foundPhoto = false;
    let progressIdx = 0;

    for (let i = 0; i < dayPoints.length; i++) {
      const point = dayPoints[i];
      if (prevPoint) {
        const segmentDist = haversine(prevPoint, point);
        totalDistance += segmentDist;
        if (!foundPhoto && point.timestamp.getTime() >= photoTime) {
          foundPhoto = true;
          progressIdx = i;
        }
        if (!foundPhoto) {
          distanceTraveled += segmentDist;
        }
      }
      prevPoint = point;
    }

    return {
      progress: {
        km: Math.round(distanceTraveled),
        total: Math.round(totalDistance),
        percent: totalDistance > 0 ? Math.round((distanceTraveled / totalDistance) * 100) : 0
      },
      currentProgressIndex: progressIdx
    };
  }, [dayPoints, photo]);

  // --- ELEVATION PROFILE DATA ---
  const elevationProfile = useMemo(() => {
    if (!dayPoints?.length) return [];
    // Sample every Nth point to get ~50 data points
    const sampleRate = Math.max(1, Math.floor(dayPoints.length / 50));
    return dayPoints
      .filter((_, i) => i % sampleRate === 0)
      .map(p => p.elevation)
      .filter(e => e != null);
  }, [dayPoints]);

  const currentElevationIndex = useMemo(() => {
    if (!elevationProfile?.length || !progress?.percent) return 0;
    // Use progress percentage directly to position on sparkline
    return Math.round((progress.percent / 100) * (elevationProfile.length - 1));
  }, [elevationProfile, progress?.percent]);

  // --- GRADE CALCULATION ---
  const grade = useMemo(() => {
    if (!dayPoints?.length || !photo?.timestamp) return null;

    const photoTime = photo.timestamp.getTime();
    let prevPoint = null;

    for (const point of dayPoints) {
      if (point.timestamp.getTime() >= photoTime && prevPoint) {
        const dist = haversine(prevPoint, point) * 1000;
        if (dist > 10 && prevPoint.elevation != null && point.elevation != null) {
          const elevChange = point.elevation - prevPoint.elevation;
          return (elevChange / dist) * 100;
        }
      }
      prevPoint = point;
    }
    return null;
  }, [dayPoints, photo]);

  // --- FORMATTERS ---
  const formatTime = (timestamp) => {
    if (!timestamp) return '--:--';
    return timestamp.toLocaleTimeString('en-US', {
      timeZone: 'America/Vancouver',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  };

  const formatCoord = (val, isLat) => {
    if (val == null) return '--';
    const dir = isLat ? (val >= 0 ? 'N' : 'S') : (val >= 0 ? 'E' : 'W');
    return `${Math.abs(val).toFixed(2)}° ${dir}`;
  };

  // --- STYLES ---
  const labelStyle = {
    fontSize: '9px',
    fontWeight: 700,
    fontFamily: 'monospace',
    letterSpacing: '0.08em',
    color: '#6b7280',
    textTransform: 'uppercase'
  };

  const valueStyle = {
    fontSize: '13px',
    fontWeight: 700,
    fontFamily: 'monospace',
    color: '#1a1a1a'
  };

  const cellStyle = {
    padding: '8px',
    borderBottom: '2px solid #1a1a1a'
  };

  const gridCellStyle = {
    padding: '8px',
    borderBottom: '2px solid #1a1a1a',
    borderRight: '2px solid #1a1a1a'
  };

  const gridCellLastStyle = {
    padding: '8px',
    borderBottom: '2px solid #1a1a1a'
  };

  return (
    <div style={{ border: '2px solid #1a1a1a' }}>
      {/* TIME HEADER */}
      <div style={{
        padding: '12px',
        borderBottom: '2px solid #1a1a1a',
        background: '#fafafa'
      }}>
        <div style={{
          fontSize: '28px',
          fontWeight: 800,
          fontFamily: 'monospace',
          letterSpacing: '-0.02em',
          color: '#1a1a1a'
        }}>
          {formatTime(photo?.timestamp)}
        </div>
      </div>

      {/* SOLAR ROW - 2 cells */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
        <div style={gridCellStyle}>
          <div style={labelStyle}>SOLAR ALT</div>
          <div style={valueStyle}>
            {solarAltitude != null ? `${solarAltitude.toFixed(1)}°` : '--'}
            <span style={{ color: '#9ca3af', marginLeft: '4px', fontSize: '10px' }}>
              {getSolarLabel(solarAltitude)}
            </span>
          </div>
        </div>
        <div style={gridCellLastStyle}>
          <div style={labelStyle}>LIGHT LEFT</div>
          <div style={valueStyle}>{getLightRemaining() || 'DARK'}</div>
        </div>
      </div>

      {/* OPTICS ROW - Camera exposure data */}
      {(photo?.iso || photo?.aperture || photo?.shutterSpeed || photo?.focalLength35mm) && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
          <div style={gridCellStyle}>
            <div style={labelStyle}>EXPOSURE</div>
            <div style={{ ...valueStyle, fontSize: '11px', lineHeight: 1.6 }}>
              {photo.shutterSpeed && photo.aperture && (
                <div>{photo.shutterSpeed} @ ƒ/{photo.aperture}</div>
              )}
              {photo.iso && <div>ISO {photo.iso}</div>}
            </div>
          </div>
          <div style={gridCellLastStyle}>
            <div style={labelStyle}>CONDITIONS</div>
            <div style={{ ...valueStyle, fontSize: '11px', lineHeight: 1.6 }}>
              {photo.focalLength35mm && <div>{photo.focalLength35mm}mm WIDE</div>}
              {photo.lightValue != null && (
                <div>
                  EV {photo.lightValue}
                  <span style={{ color: '#9ca3af', marginLeft: '4px', fontSize: '9px' }}>
                    {photo.lightValue >= 13 ? 'BRIGHT' :
                     photo.lightValue >= 10 ? 'SUNNY' :
                     photo.lightValue >= 7 ? 'OVERCAST' :
                     photo.lightValue >= 4 ? 'DIM' : 'DARK'}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* PROGRESS ROW - 2 cells */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
        <div style={gridCellStyle}>
          <div style={labelStyle}>KM MARKER</div>
          <div style={valueStyle}>
            {progress ? `${progress.km}/${progress.total}` : '--'}
          </div>
        </div>
        <div style={gridCellLastStyle}>
          <div style={labelStyle}>PROGRESS</div>
          <div style={valueStyle}>{progress ? `${progress.percent}%` : '--%'}</div>
        </div>
      </div>

      {/* GRADE ROW */}
      <div style={cellStyle}>
        <div style={labelStyle}>GRADE</div>
        <div style={{
          ...valueStyle,
          fontSize: '16px',
          color: grade != null ? (grade > 0 ? '#059669' : grade < 0 ? '#dc2626' : '#1a1a1a') : '#1a1a1a'
        }}>
          {grade != null ? `${grade > 0 ? '+' : ''}${grade.toFixed(1)}%` : '0.0%'}
        </div>
      </div>

      {/* ELEVATION SPARKLINE */}
      <div style={cellStyle}>
        <div style={{ ...labelStyle, marginBottom: '8px' }}>ELEVATION PROFILE</div>
        <ElevationSparkline
          data={elevationProfile}
          currentIndex={currentElevationIndex}
          height={60}
        />
      </div>

      {/* ELEVATION + COORDS ROW */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr' }}>
        <div style={gridCellStyle}>
          <div style={labelStyle}>ELEVATION</div>
          <div style={{ ...valueStyle, fontSize: '16px' }}>
            {photo?.elevation != null ? `${Math.round(photo.elevation)}m` : '--'}
          </div>
        </div>
        <div style={gridCellLastStyle}>
          <div style={labelStyle}>COORDINATES</div>
          <div style={{ fontSize: '10px', fontFamily: 'monospace', color: '#1a1a1a', lineHeight: 1.4 }}>
            <div>{formatCoord(photo?.lat, true)}</div>
            <div>{formatCoord(photo?.lng, false)}</div>
          </div>
        </div>
      </div>

      {/* TOTALS FOOTER */}
      <div style={{
        background: '#1a1a1a',
        color: 'white',
        padding: '12px'
      }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '8px' }}>
          <div>
            <div style={{ ...labelStyle, color: '#9ca3af' }}>ASCENT</div>
            <div style={{ ...valueStyle, color: '#4ade80' }}>
              +{dayStats?.ascent?.toLocaleString() || 0}m
            </div>
          </div>
          <div>
            <div style={{ ...labelStyle, color: '#9ca3af' }}>DESCENT</div>
            <div style={{ ...valueStyle, color: '#f87171' }}>
              -{dayStats?.descent?.toLocaleString() || 0}m
            </div>
          </div>
          <div>
            <div style={{ ...labelStyle, color: '#9ca3af' }}>PHOTOS</div>
            <div style={{ ...valueStyle, color: 'white' }}>
              {dayStats?.photoCount || 0}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Elevation Sparkline Component
function ElevationSparkline({ data, currentIndex, height = 50 }) {
  if (!data?.length) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  // Generate SVG path
  const points = data.map((val, i) => {
    const x = (i / (data.length - 1)) * 100;
    const y = height - ((val - min) / range) * (height - 4) - 2;
    return `${x},${y}`;
  }).join(' ');

  // Current position marker
  const currentX = data.length > 1 ? (currentIndex / (data.length - 1)) * 100 : 50;
  const currentY = data[currentIndex] != null
    ? height - ((data[currentIndex] - min) / range) * (height - 4) - 2
    : height / 2;

  // Calculate pixel position for marker
  const markerLeftPercent = data.length > 1 ? (currentIndex / (data.length - 1)) * 100 : 50;
  const markerTopPercent = data[currentIndex] != null
    ? ((max - data[currentIndex]) / range) * 100
    : 50;

  return (
    <div>
      {/* Min/Max labels row */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        marginBottom: '4px',
        fontSize: '9px',
        fontFamily: 'monospace',
        color: '#9ca3af'
      }}>
        <span>↓ {Math.round(min)}m</span>
        <span>↑ {Math.round(max)}m</span>
      </div>
      <div style={{ position: 'relative', height }}>
        <svg
          width="100%"
          height={height}
          viewBox={`0 0 100 ${height}`}
          preserveAspectRatio="none"
          style={{ display: 'block' }}
        >
          {/* Profile line */}
          <polyline
            points={points}
            fill="none"
            stroke="#1a1a1a"
            strokeWidth="1.5"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
        {/* Position marker - absolute positioned div for true circle */}
        <div style={{
          position: 'absolute',
          left: `${markerLeftPercent}%`,
          top: `${markerTopPercent}%`,
          transform: 'translate(-50%, -50%)',
          width: '6px',
          height: '6px',
          borderRadius: '50%',
          background: '#dc2626'
        }} />
      </div>
    </div>
  );
}

// Haversine distance calculation (km)
function haversine(p1, p2) {
  if (!p1?.lat || !p2?.lat) return 0;
  const R = 6371;
  const dLat = ((p2.lat - p1.lat) * Math.PI) / 180;
  const dLon = ((p2.lng - p1.lng) * Math.PI) / 180;
  const a = Math.sin(dLat / 2) ** 2 +
    Math.cos((p1.lat * Math.PI) / 180) * Math.cos((p2.lat * Math.PI) / 180) *
    Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// Highlights Grid Component
function HighlightsGrid({ highlights, dayColor, isMobile }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: isMobile ? '1fr 1fr' : '1fr',
      gap: isMobile ? '8px' : '12px'
    }}>
      {highlights.map((h, idx) => (
        <div
          key={h.id || idx}
          style={{
            display: 'flex',
            flexDirection: 'column',
            padding: isMobile ? '10px' : '12px',
            background: '#fafafa',
            transition: 'background 0.15s'
          }}
        >
          {/* Icon/Image */}
          <div style={{
            width: '100%',
            aspectRatio: '1.5',
            background: h.image ? 'transparent' : `linear-gradient(135deg, ${dayColor}22, ${dayColor}44)`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: isMobile ? '28px' : '32px',
            overflow: 'hidden',
            marginBottom: isMobile ? '8px' : '10px'
          }}>
            {h.image ? (
              <img
                src={h.image.startsWith('/') ? h.image : `/${h.image}`}
                alt=""
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'cover'
                }}
              />
            ) : (
              HIGHLIGHT_ICONS[h.type] || '●'
            )}
          </div>

          {/* Title */}
          <div style={{
            fontSize: isMobile ? '13px' : '14px',
            fontWeight: 600,
            color: '#1a1a1a',
            marginBottom: '4px'
          }}>
            {h.title}
          </div>

          {/* Comment */}
          {h.comment && (
            <div style={{
              fontSize: isMobile ? '11px' : '12px',
              color: '#6b7280',
              lineHeight: 1.4
            }}>
              {h.comment}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export default DayDetailPage;
