import React, { useMemo, useState, useEffect, useCallback } from "react";
import { Redirect } from "wouter";
import SunCalc from "suncalc";
import { useTripContext } from "../contexts/TripContext";
import { useDayData } from "../hooks/useDayData";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { useFavicon } from "../hooks/useFavicon";
import { usePageTitle } from "../hooks/usePageTitle";
import { DayNavigation } from "../components/day/DayNavigation";
import { DayMap } from "../components/map/DayMap";
import { DayStatsCard } from "../components/day/DayStatsCard";
import { PhotoViewer } from "../components/day/PhotoViewer";
import { FullscreenModal } from "../components/timeline/FullscreenModal";
import { getDisplayUrl } from "../utils/images";
import { Loader2, AlertCircle, ChevronLeft, ChevronRight } from "lucide-react";

const HIGHLIGHT_ICONS = {
  wildlife: "🦬",
  hotspring: "♨️",
  aurora: "✦",
  landscape: "◆",
  other: "●",
};

/**
 * Day Detail Page - Shows detailed view for a single day of the trip
 * Route: /:trip/day/:dayNumber
 */
export function DayDetailPage({ dayNumber }) {
  const { tripSlug, tripConfig, rawTripData, tripData, loading, error } =
    useTripContext();

  const isMobile = useMediaQuery("(max-width: 768px)");

  // Set favicon to solid dot (focus mode)
  useFavicon("detail");

  // Set page title (compact for tab display)
  const shortTitle = tripConfig?.trip?.short_title;
  usePageTitle(shortTitle ? `${shortTitle} ${dayNumber}` : null);

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
    isValidDay,
  } = useDayData(rawTripData, tripData, tripConfig, dayNumber);

  // Photo viewer state (must be before early returns)
  const [currentPhotoIndex, setCurrentPhotoIndex] = useState(0);
  const [showFullscreen, setShowFullscreen] = useState(false);
  const rawPhoto = dayPhotos?.[currentPhotoIndex] || null;

  // Interpolate GPS position from track if photo doesn't have coordinates
  const currentPhoto = useMemo(() => {
    if (!rawPhoto) return null;
    // If photo has GPS, use it directly
    if (rawPhoto.lat && rawPhoto.lng) return rawPhoto;
    // If no timestamp, can't interpolate
    if (!rawPhoto.timestamp || !dayPoints?.length) return rawPhoto;

    // Find position on track closest to photo timestamp
    const photoTime = rawPhoto.timestamp.getTime();
    let prevPoint = null;

    for (const point of dayPoints) {
      if (!point.timestamp) continue;
      const pointTime = point.timestamp.getTime();

      if (pointTime >= photoTime) {
        if (prevPoint) {
          // Interpolate between prevPoint and point
          const prevTime = prevPoint.timestamp.getTime();
          const t = (photoTime - prevTime) / (pointTime - prevTime);
          return {
            ...rawPhoto,
            lat: prevPoint.lat + (point.lat - prevPoint.lat) * t,
            lng: prevPoint.lng + (point.lng - prevPoint.lng) * t,
            elevation:
              prevPoint.elevation != null && point.elevation != null
                ? prevPoint.elevation +
                  (point.elevation - prevPoint.elevation) * t
                : rawPhoto.elevation,
          };
        }
        // Before first point, use first point's location
        return {
          ...rawPhoto,
          lat: point.lat,
          lng: point.lng,
          elevation: point.elevation,
        };
      }
      prevPoint = point;
    }

    // After last point, use last point's location
    if (prevPoint) {
      return {
        ...rawPhoto,
        lat: prevPoint.lat,
        lng: prevPoint.lng,
        elevation: prevPoint.elevation,
      };
    }

    return rawPhoto;
  }, [rawPhoto, dayPoints]);

  // Reset photo index when day changes
  useEffect(() => {
    setCurrentPhotoIndex(0);
  }, [dayNumber]);

  // Keyboard navigation for desktop
  useEffect(() => {
    if (isMobile || showFullscreen) return;
    const handleKeyDown = (e) => {
      if (e.key === "ArrowLeft") {
        setCurrentPhotoIndex((prev) => Math.max(0, prev - 1));
      } else if (e.key === "ArrowRight") {
        setCurrentPhotoIndex((prev) =>
          Math.min((dayPhotos?.length || 1) - 1, prev + 1),
        );
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isMobile, showFullscreen, dayPhotos?.length]);

  // Handle map click - find photo closest to the clicked timestamp
  const handleMapLocationClick = useCallback(
    (timestamp) => {
      if (!dayPhotos?.length || !timestamp) return;

      const clickTime = timestamp.getTime();
      let closestIndex = 0;
      let minDiff = Infinity;

      dayPhotos.forEach((photo, index) => {
        if (!photo.timestamp) return;
        const diff = Math.abs(photo.timestamp.getTime() - clickTime);
        if (diff < minDiff) {
          minDiff = diff;
          closestIndex = index;
        }
      });

      setCurrentPhotoIndex(closestIndex);
    },
    [dayPhotos],
  );

  // Loading state
  if (loading) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#fafafa",
        }}
      >
        <Loader2
          size={32}
          style={{ animation: "spin 1s linear infinite", color: "#6b7280" }}
        />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          background: "#fafafa",
          padding: "20px",
        }}
      >
        <AlertCircle
          size={48}
          style={{ color: "#ef4444", marginBottom: "16px" }}
        />
        <p style={{ color: "#ef4444", fontSize: "16px", textAlign: "center" }}>
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
    <div
      style={{
        minHeight: "100vh",
        background: "white",
        fontFamily: "system-ui, -apple-system, sans-serif",
      }}
    >
      <div
        style={{
          maxWidth: "1200px",
          margin: "0 auto",
          padding: isMobile ? "16px" : "24px 32px",
        }}
      >
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
          <div
            style={{ display: "flex", flexDirection: "column", gap: "20px" }}
          >
            {/* Map */}
            <DayMap
              points={dayPoints}
              highlights={dayHighlights}
              dayColor={dayColor}
              height="200px"
              isMobile={true}
              currentPhoto={currentPhoto}
              sunPosition={
                currentPhoto?.timestamp &&
                currentPhoto?.lat &&
                currentPhoto?.lng
                  ? SunCalc.getPosition(
                      currentPhoto.timestamp,
                      currentPhoto.lat,
                      currentPhoto.lng,
                    )
                  : null
              }
              onLocationClick={handleMapLocationClick}
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
          // Desktop: Map top, Triptych grid below (Photo | Technical Strip | Mission Log)
          <div
            style={{ display: "flex", flexDirection: "column", gap: "24px" }}
          >
            {/* Map - full width, with dynamic sun position */}
            <DayMap
              points={dayPoints}
              highlights={dayHighlights}
              dayColor={dayColor}
              height="280px"
              isMobile={false}
              currentPhoto={currentPhoto}
              sunPosition={
                currentPhoto?.timestamp &&
                currentPhoto?.lat &&
                currentPhoto?.lng
                  ? SunCalc.getPosition(
                      currentPhoto.timestamp,
                      currentPhoto.lat,
                      currentPhoto.lng,
                    )
                  : null
              }
              onLocationClick={handleMapLocationClick}
            />

            {/* Unified Triptych: Photo | Data Panel (aligned grid) */}
            <div
              style={{
                display: "flex",
                alignItems: "stretch",
                borderTop: "2px solid #1a1a1a",
              }}
            >
              {/* Column 1: The Photo - square, fixed size */}
              <img
                src={currentPhoto ? getDisplayUrl(currentPhoto.image) : ""}
                alt={`Photo ${currentPhotoIndex + 1}`}
                onClick={() => setShowFullscreen(true)}
                style={{
                  flex: "0 0 auto",
                  width: "520px",
                  height: "520px",
                  objectFit: "cover",
                  cursor: "pointer",
                  display: "block",
                }}
              />

              {/* Data Panel - unified grid with aligned rows */}
              <DataPanel
                photo={currentPhoto}
                photoIndex={currentPhotoIndex}
                totalPhotos={dayPhotos?.length || 0}
                onPrev={() =>
                  setCurrentPhotoIndex(Math.max(0, currentPhotoIndex - 1))
                }
                onNext={() =>
                  setCurrentPhotoIndex(
                    Math.min(
                      (dayPhotos?.length || 1) - 1,
                      currentPhotoIndex + 1,
                    ),
                  )
                }
                dayPoints={dayPoints}
                dayStats={dayStats}
                dayColor={dayColor}
              />
            </div>

            {/* Fullscreen modal */}
            {showFullscreen && currentPhoto && (
              <FullscreenModal
                imageUrl={getDisplayUrl(currentPhoto.image)}
                onClose={() => setShowFullscreen(false)}
                onPrev={
                  currentPhotoIndex > 0
                    ? () => setCurrentPhotoIndex(currentPhotoIndex - 1)
                    : undefined
                }
                onNext={
                  currentPhotoIndex < (dayPhotos?.length || 1) - 1
                    ? () => setCurrentPhotoIndex(currentPhotoIndex + 1)
                    : undefined
                }
              />
            )}

            {/* Highlights (if any) */}
            {dayHighlights.length > 0 && (
              <section style={{ marginTop: "8px" }}>
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
    <div
      style={{
        fontSize: isMobile ? "10px" : "11px",
        fontWeight: 700,
        fontFamily: "monospace",
        letterSpacing: "0.08em",
        color: "#1a1a1a",
        textTransform: "uppercase",
        marginBottom: isMobile ? "12px" : "16px",
        paddingBottom: "8px",
        borderBottom: "2px solid #1a1a1a",
      }}
    >
      {title}
    </div>
  );
}

// Nav Button with hover inversion
function NavButton({ onClick, disabled, children, borderRight = false }) {
  const [hovered, setHovered] = useState(false);
  const active = !disabled && hovered;

  return (
    <button
      onClick={onClick}
      disabled={disabled}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: active ? "#1a1a1a" : "white",
        border: "none",
        borderRight: borderRight ? "2px solid #1a1a1a" : "none",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.3 : 1,
        transition: "background 0.15s, color 0.15s",
      }}
    >
      {React.cloneElement(children, { color: active ? "white" : "#1a1a1a" })}
    </button>
  );
}

// Unified Data Panel - aligned grid combining control strip and mission panel
function DataPanel({
  photo,
  photoIndex,
  totalPhotos,
  onPrev,
  onNext,
  dayPoints,
  dayStats,
  dayColor,
}) {
  // --- FORMATTERS ---
  const formatTime = (timestamp) => {
    if (!timestamp) return { time: "--:--", period: "" };
    const timeStr = timestamp.toLocaleTimeString("en-US", {
      timeZone: "America/Vancouver",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
    const parts = timeStr.match(/(\d+:\d+)\s*(AM|PM)/i);
    if (parts) return { time: parts[1], period: parts[2] };
    return { time: timeStr, period: "" };
  };

  const formatCoord = (val, isLat) => {
    if (val == null) return "--";
    const dir = isLat ? (val >= 0 ? "N" : "S") : val >= 0 ? "E" : "W";
    return `${Math.abs(val).toFixed(4)}° ${dir}`;
  };

  // --- SOLAR CALCULATIONS ---
  const sunPosition = useMemo(() => {
    if (!photo?.timestamp || !photo?.lat || !photo?.lng) return null;
    return SunCalc.getPosition(photo.timestamp, photo.lat, photo.lng);
  }, [photo]);

  const sunTimes = useMemo(() => {
    if (!photo?.timestamp || !photo?.lat || !photo?.lng) return null;
    return SunCalc.getTimes(photo.timestamp, photo.lat, photo.lng);
  }, [photo]);

  const solarAltitude = sunPosition
    ? (sunPosition.altitude * 180) / Math.PI
    : null;

  const getSolarLabel = (alt) => {
    if (alt == null) return "--";
    if (alt < -6) return "NIGHT";
    if (alt < 0) return "TWILIGHT";
    if (alt < 10) return "LOW";
    return "DAY";
  };

  const getLightRemaining = () => {
    if (!photo?.timestamp || !sunTimes?.sunset) return null;
    const now = photo.timestamp.getTime();
    const sunset = sunTimes.sunset.getTime();
    if (now > sunset) return null;
    const diff = sunset - now;
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    return `${hours}h ${mins.toString().padStart(2, "0")}m`;
  };

  const getEvLabel = (ev) => {
    if (ev == null) return "";
    if (ev >= 13) return "BRIGHT";
    if (ev >= 10) return "SUNNY";
    if (ev >= 7) return "OVERCAST";
    if (ev >= 4) return "DIM";
    return "DARK";
  };

  // --- BEARING CALCULATION ---
  const bearing = useMemo(() => {
    if (!dayPoints?.length || !photo?.timestamp) return null;
    const photoTime = photo.timestamp.getTime();
    let prevPoint = null;
    for (const point of dayPoints) {
      if (point.timestamp?.getTime() >= photoTime && prevPoint) {
        const lat1 = (prevPoint.lat * Math.PI) / 180;
        const lat2 = (point.lat * Math.PI) / 180;
        const dLng = ((point.lng - prevPoint.lng) * Math.PI) / 180;
        const y = Math.sin(dLng) * Math.cos(lat2);
        const x =
          Math.cos(lat1) * Math.sin(lat2) -
          Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);
        let brng = (Math.atan2(y, x) * 180) / Math.PI;
        return (brng + 360) % 360;
      }
      prevPoint = point;
    }
    return null;
  }, [dayPoints, photo]);

  const getCompassArrow = (deg) => {
    if (deg == null) return "→";
    const arrows = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"];
    const index = Math.round(deg / 45) % 8;
    return arrows[index];
  };

  // --- PROGRESS & ELEVATION ---
  const progress = useMemo(() => {
    if (!dayPoints?.length || !photo?.timestamp) return null;
    const photoTime = photo.timestamp.getTime();
    let distanceTraveled = 0;
    let totalDistance = 0;
    let prevPoint = null;
    let foundPhoto = false;

    for (const point of dayPoints) {
      if (prevPoint) {
        const segmentDist = haversine(prevPoint, point);
        totalDistance += segmentDist;
        if (!foundPhoto && point.timestamp?.getTime() >= photoTime)
          foundPhoto = true;
        if (!foundPhoto) distanceTraveled += segmentDist;
      }
      prevPoint = point;
    }

    return {
      km: Math.round(distanceTraveled),
      total: Math.round(totalDistance),
      percent:
        totalDistance > 0
          ? Math.round((distanceTraveled / totalDistance) * 100)
          : 0,
    };
  }, [dayPoints, photo]);

  const elevationProfile = useMemo(() => {
    if (!dayPoints?.length) return [];
    const sampleRate = Math.max(1, Math.floor(dayPoints.length / 60));
    return dayPoints
      .filter((_, i) => i % sampleRate === 0)
      .map((p) => p.elevation)
      .filter((e) => e != null);
  }, [dayPoints]);

  const currentElevationIndex = useMemo(() => {
    if (!elevationProfile?.length || !progress?.percent) return 0;
    return Math.round((progress.percent / 100) * (elevationProfile.length - 1));
  }, [elevationProfile, progress]);

  const timeData = formatTime(photo?.timestamp);
  const hasPrev = photoIndex > 0;
  const hasNext = photoIndex < totalPhotos - 1;

  const labelStyle = {
    fontSize: "9px",
    fontWeight: 700,
    color: "#6b7280",
    letterSpacing: "0.08em",
    marginBottom: "4px",
  };
  const valueStyle = { fontSize: "18px", fontWeight: 700, color: "#1a1a1a" };

  return (
    <div
      style={{
        flex: 1,
        display: "grid",
        gridTemplateColumns: "150px 1fr 1fr 1fr 1fr",
        gridTemplateRows: "auto 1fr auto",
        borderLeft: "2px solid #1a1a1a",
        fontFamily: "monospace",
        minWidth: 0,
      }}
    >
      {/* ROW 1: TIME | SOLAR | LIGHT | EV | ELEV */}
      <div
        style={{
          padding: "12px",
          borderBottom: "2px solid #1a1a1a",
          borderRight: "2px solid #1a1a1a",
          background: "white",
        }}
      >
        <div style={labelStyle}>TIME</div>
        <div
          style={{
            fontSize: "24px",
            fontWeight: 900,
            color: "#1a1a1a",
            lineHeight: 1,
          }}
        >
          {timeData.time}
          <span
            style={{
              fontSize: "11px",
              fontWeight: 700,
              color: "#6b7280",
              marginLeft: "4px",
            }}
          >
            {timeData.period}
          </span>
        </div>
      </div>
      <div
        style={{
          padding: "12px",
          borderBottom: "2px solid #1a1a1a",
          borderRight: "1px solid #e5e7eb",
          background: "white",
        }}
      >
        <div style={labelStyle}>SOLAR</div>
        <div style={valueStyle}>
          {solarAltitude != null ? `${solarAltitude.toFixed(0)}°` : "--"}
        </div>
        <div style={{ fontSize: "9px", color: "#9ca3af", fontWeight: 600 }}>
          {getSolarLabel(solarAltitude)}
        </div>
      </div>
      <div
        style={{
          padding: "12px",
          borderBottom: "2px solid #1a1a1a",
          borderRight: "1px solid #e5e7eb",
          background: "white",
        }}
      >
        <div style={labelStyle}>LIGHT</div>
        <div style={{ fontSize: "14px", fontWeight: 700, color: "#1a1a1a" }}>
          {getLightRemaining() || "DARK"}
        </div>
      </div>
      <div
        style={{
          padding: "12px",
          borderBottom: "2px solid #1a1a1a",
          borderRight: "1px solid #e5e7eb",
          background: "white",
        }}
      >
        <div style={labelStyle}>EV</div>
        <div style={valueStyle}>{photo?.lightValue ?? "--"}</div>
        <div style={{ fontSize: "9px", color: "#9ca3af", fontWeight: 600 }}>
          {getEvLabel(photo?.lightValue)}
        </div>
      </div>
      <div
        style={{
          padding: "12px",
          borderBottom: "2px solid #1a1a1a",
          background: "white",
        }}
      >
        <div style={labelStyle}>ELEV</div>
        <div style={valueStyle}>
          {photo?.elevation != null ? Math.round(photo.elevation) : "--"}
          <span style={{ fontSize: "10px", color: "#9ca3af" }}>m</span>
        </div>
      </div>

      {/* ROW 2: OPTICS + NAV + BEARING | ELEVATION PROFILE (spans 4 cols) */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          borderRight: "2px solid #1a1a1a",
          borderBottom: "2px solid #1a1a1a",
          background: "#fafafa",
        }}
      >
        {/* OPTICS */}
        <div
          style={{
            padding: "12px",
            borderBottom: "2px solid #1a1a1a",
            background: "#f5f5f5",
          }}
        >
          <div style={labelStyle}>OPTICS</div>
          <div style={{ fontSize: "14px", fontWeight: 700, color: "#1a1a1a" }}>
            {photo?.focalLength35mm ? `${photo.focalLength35mm}mm` : "--"} ƒ/
            {photo?.aperture || "--"}
          </div>
          <div
            style={{
              fontSize: "11px",
              fontWeight: 600,
              color: "#6b7280",
              marginTop: "2px",
            }}
          >
            ISO {photo?.iso || "--"} · {photo?.shutterSpeed || "--"}
          </div>
        </div>

        {/* NAV */}
        <div style={{ borderBottom: "2px solid #1a1a1a", background: "white" }}>
          <div style={{ display: "flex", height: "56px" }}>
            <NavButton onClick={onPrev} disabled={!hasPrev} borderRight>
              <ChevronLeft size={24} />
            </NavButton>
            <NavButton onClick={onNext} disabled={!hasNext}>
              <ChevronRight size={24} />
            </NavButton>
          </div>
          <div
            style={{
              fontSize: "11px",
              fontWeight: 700,
              color: "#1a1a1a",
              textAlign: "center",
              padding: "8px",
              borderTop: "2px solid #1a1a1a",
            }}
          >
            {photoIndex + 1} / {totalPhotos}
          </div>
        </div>

        {/* BEARING - fills remaining space */}
        <div
          style={{
            flexGrow: 1,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            alignItems: "center",
            padding: "12px",
            background: "white",
          }}
        >
          <div style={labelStyle}>BEARING</div>
          <div style={{ fontSize: "36px", lineHeight: 1, color: "#1a1a1a" }}>
            {getCompassArrow(bearing)}
          </div>
          <div
            style={{
              fontSize: "11px",
              fontWeight: 700,
              color: "#6b7280",
              marginTop: "4px",
            }}
          >
            {bearing != null ? `${Math.round(bearing)}°` : "--"}
          </div>
        </div>
      </div>

      {/* ELEVATION PROFILE - spans 4 columns */}
      <div
        style={{
          gridColumn: "span 4",
          padding: "12px 16px",
          borderBottom: "2px solid #1a1a1a",
          display: "flex",
          flexDirection: "column",
          background: "white",
        }}
      >
        <div style={{ ...labelStyle, marginBottom: "8px" }}>
          ELEVATION PROFILE
        </div>
        <div style={{ flexGrow: 1, position: "relative", minHeight: "120px" }}>
          <ElevationSparkline
            data={elevationProfile}
            currentIndex={currentElevationIndex}
            fillHeight={true}
            accentColor={dayColor}
          />
        </div>
      </div>

      {/* ROW 3: POSITION | KM | ASCENT | DESCENT | PHOTOS */}
      <div
        style={{
          padding: "10px 12px",
          borderRight: "2px solid #1a1a1a",
          background: "white",
        }}
      >
        <div style={labelStyle}>POSITION</div>
        <div
          style={{
            fontSize: "10px",
            fontWeight: 600,
            color: "#1a1a1a",
            lineHeight: 1.6,
          }}
        >
          <div>{formatCoord(photo?.lat, true)}</div>
          <div>{formatCoord(photo?.lng, false)}</div>
        </div>
      </div>
      <div
        style={{
          padding: "10px",
          borderRight: "1px solid #e5e7eb",
          background: "#fafafa",
        }}
      >
        <div style={labelStyle}>KM</div>
        <div style={{ fontSize: "16px", fontWeight: 900, color: "#1a1a1a" }}>
          {progress?.km ?? 0}
          <span style={{ fontSize: "10px", color: "#9ca3af" }}>
            /{progress?.total ?? 0}
          </span>
        </div>
      </div>
      <div
        style={{
          padding: "10px",
          borderRight: "1px solid #e5e7eb",
          background: "#fafafa",
        }}
      >
        <div style={labelStyle}>ASCENT</div>
        <div style={{ fontSize: "14px", fontWeight: 900, color: "#059669" }}>
          +{dayStats?.ascent?.toLocaleString() || 0}m
        </div>
      </div>
      <div
        style={{
          padding: "10px",
          borderRight: "1px solid #e5e7eb",
          background: "#fafafa",
        }}
      >
        <div style={labelStyle}>DESCENT</div>
        <div style={{ fontSize: "14px", fontWeight: 900, color: "#dc2626" }}>
          -{dayStats?.descent?.toLocaleString() || 0}m
        </div>
      </div>
      <div style={{ padding: "10px", background: "#fafafa" }}>
        <div style={labelStyle}>PHOTOS</div>
        <div style={{ fontSize: "14px", fontWeight: 900, color: "#1a1a1a" }}>
          {dayStats?.photoCount || 0}
        </div>
      </div>
    </div>
  );
}

// Control Strip - The narrow "Machine Interface" column (LEGACY - kept for reference)
function ControlStrip({
  photo,
  photoIndex,
  totalPhotos,
  onPrev,
  onNext,
  dayPoints,
}) {
  const formatTime = (timestamp) => {
    if (!timestamp) return { time: "--:--", period: "" };
    const timeStr = timestamp.toLocaleTimeString("en-US", {
      timeZone: "America/Vancouver",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
    const parts = timeStr.match(/(\d+:\d+)\s*(AM|PM)/i);
    if (parts) return { time: parts[1], period: parts[2] };
    return { time: timeStr, period: "" };
  };

  const formatCoord = (val, isLat) => {
    if (val == null) return "--";
    const dir = isLat ? (val >= 0 ? "N" : "S") : val >= 0 ? "E" : "W";
    return `${Math.abs(val).toFixed(4)}° ${dir}`;
  };

  // Bearing calculation
  const bearing = useMemo(() => {
    if (!dayPoints?.length || !photo?.timestamp) return null;
    const photoTime = photo.timestamp.getTime();
    let prevPoint = null;
    for (const point of dayPoints) {
      if (point.timestamp.getTime() >= photoTime && prevPoint) {
        const lat1 = (prevPoint.lat * Math.PI) / 180;
        const lat2 = (point.lat * Math.PI) / 180;
        const dLng = ((point.lng - prevPoint.lng) * Math.PI) / 180;
        const y = Math.sin(dLng) * Math.cos(lat2);
        const x =
          Math.cos(lat1) * Math.sin(lat2) -
          Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);
        let brng = (Math.atan2(y, x) * 180) / Math.PI;
        return (brng + 360) % 360;
      }
      prevPoint = point;
    }
    return null;
  }, [dayPoints, photo]);

  const getCompassArrow = (deg) => {
    if (deg == null) return "→";
    const arrows = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"];
    const index = Math.round(deg / 45) % 8;
    return arrows[index];
  };

  const timeData = formatTime(photo?.timestamp);
  const hasPrev = photoIndex > 0;
  const hasNext = photoIndex < totalPhotos - 1;

  const cellStyle = {
    padding: "12px",
    borderBottom: "2px solid #1a1a1a",
    fontFamily: "monospace",
    textAlign: "left",
  };

  const labelStyle = {
    fontSize: "9px",
    fontWeight: 700,
    color: "#6b7280",
    letterSpacing: "0.08em",
    marginBottom: "4px",
  };

  return (
    <div
      style={{
        flex: "0 0 150px",
        display: "flex",
        flexDirection: "column",
        borderLeft: "2px solid #1a1a1a",
        borderRight: "2px solid #1a1a1a",
        background: "#fafafa",
      }}
    >
      {/* TIME - left aligned */}
      <div style={{ ...cellStyle, background: "white", padding: "12px" }}>
        <div style={labelStyle}>TIME</div>
        <div
          style={{
            fontSize: "24px",
            fontWeight: 900,
            color: "#1a1a1a",
            lineHeight: 1,
          }}
        >
          {timeData.time}
          <span
            style={{
              fontSize: "11px",
              fontWeight: 700,
              color: "#6b7280",
              marginLeft: "4px",
            }}
          >
            {timeData.period}
          </span>
        </div>
      </div>

      {/* OPTICS - left aligned */}
      <div style={{ ...cellStyle, background: "#f5f5f5" }}>
        <div style={labelStyle}>OPTICS</div>
        <div style={{ fontSize: "14px", fontWeight: 700, color: "#1a1a1a" }}>
          {photo?.focalLength35mm ? `${photo.focalLength35mm}mm` : "--"} ƒ/
          {photo?.aperture || "--"}
        </div>
        <div
          style={{
            fontSize: "11px",
            fontWeight: 600,
            color: "#6b7280",
            marginTop: "2px",
          }}
        >
          ISO {photo?.iso || "--"} · {photo?.shutterSpeed || "--"}
        </div>
      </div>

      {/* NAVIGATION - full-width touch targets with hover inversion */}
      <div style={{ borderBottom: "2px solid #1a1a1a", background: "white" }}>
        <div style={{ display: "flex", height: "56px" }}>
          <NavButton onClick={onPrev} disabled={!hasPrev} borderRight>
            <ChevronLeft size={24} />
          </NavButton>
          <NavButton onClick={onNext} disabled={!hasNext}>
            <ChevronRight size={24} />
          </NavButton>
        </div>
        <div
          style={{
            fontSize: "11px",
            fontWeight: 700,
            color: "#1a1a1a",
            textAlign: "center",
            padding: "8px",
            borderTop: "2px solid #1a1a1a",
          }}
        >
          {photoIndex + 1} / {totalPhotos}
        </div>
      </div>

      {/* BEARING - fills remaining space, centered */}
      <div
        style={{
          ...cellStyle,
          flexGrow: 1,
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          textAlign: "center",
          background: "white",
        }}
      >
        <div style={labelStyle}>BEARING</div>
        <div style={{ fontSize: "36px", lineHeight: 1, color: "#1a1a1a" }}>
          {getCompassArrow(bearing)}
        </div>
        <div
          style={{
            fontSize: "11px",
            fontWeight: 700,
            color: "#6b7280",
            marginTop: "4px",
          }}
        >
          {bearing != null ? `${Math.round(bearing)}°` : "--"}
        </div>
      </div>

      {/* COORDINATES - left aligned */}
      <div style={{ ...cellStyle, borderBottom: "none", background: "white" }}>
        <div style={labelStyle}>POSITION</div>
        <div
          style={{
            fontSize: "10px",
            fontWeight: 600,
            color: "#1a1a1a",
            lineHeight: 1.6,
          }}
        >
          <div>{formatCoord(photo?.lat, true)}</div>
          <div>{formatCoord(photo?.lng, false)}</div>
        </div>
      </div>
    </div>
  );
}

// Mission Panel - The wider "Context" column
function MissionPanel({ photo, dayPoints, dayStats, dayColor }) {
  // Solar calculations
  const sunPosition = useMemo(() => {
    if (!photo?.timestamp || !photo?.lat || !photo?.lng) return null;
    return SunCalc.getPosition(photo.timestamp, photo.lat, photo.lng);
  }, [photo]);

  const sunTimes = useMemo(() => {
    if (!photo?.timestamp || !photo?.lat || !photo?.lng) return null;
    return SunCalc.getTimes(photo.timestamp, photo.lat, photo.lng);
  }, [photo]);

  const solarAltitude = sunPosition
    ? (sunPosition.altitude * 180) / Math.PI
    : null;

  const getSolarLabel = (alt) => {
    if (alt == null) return "--";
    if (alt < -6) return "NIGHT";
    if (alt < 0) return "TWILIGHT";
    if (alt < 10) return "LOW";
    return "DAY";
  };

  const getLightRemaining = () => {
    if (!photo?.timestamp || !sunTimes?.sunset) return null;
    const now = photo.timestamp.getTime();
    const sunset = sunTimes.sunset.getTime();
    if (now > sunset) return null;
    const diff = sunset - now;
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    return `${hours}h ${mins.toString().padStart(2, "0")}m`;
  };

  const getEvLabel = (ev) => {
    if (ev == null) return "";
    if (ev >= 13) return "BRIGHT";
    if (ev >= 10) return "SUNNY";
    if (ev >= 7) return "OVERCAST";
    if (ev >= 4) return "DIM";
    return "DARK";
  };

  // Progress calculation
  const progress = useMemo(() => {
    if (!dayPoints?.length || !photo?.timestamp) return null;
    const photoTime = photo.timestamp.getTime();
    let distanceTraveled = 0;
    let totalDistance = 0;
    let prevPoint = null;
    let foundPhoto = false;

    for (const point of dayPoints) {
      if (prevPoint) {
        const segmentDist = haversine(prevPoint, point);
        totalDistance += segmentDist;
        if (!foundPhoto && point.timestamp.getTime() >= photoTime)
          foundPhoto = true;
        if (!foundPhoto) distanceTraveled += segmentDist;
      }
      prevPoint = point;
    }

    return {
      km: Math.round(distanceTraveled),
      total: Math.round(totalDistance),
      percent:
        totalDistance > 0
          ? Math.round((distanceTraveled / totalDistance) * 100)
          : 0,
    };
  }, [dayPoints, photo]);

  // Elevation profile
  const elevationProfile = useMemo(() => {
    if (!dayPoints?.length) return [];
    const sampleRate = Math.max(1, Math.floor(dayPoints.length / 60));
    return dayPoints
      .filter((_, i) => i % sampleRate === 0)
      .map((p) => p.elevation)
      .filter((e) => e != null);
  }, [dayPoints]);

  const currentElevationIndex = useMemo(() => {
    if (!elevationProfile?.length || !progress?.percent) return 0;
    return Math.round((progress.percent / 100) * (elevationProfile.length - 1));
  }, [elevationProfile, progress]);

  const labelStyle = {
    fontSize: "9px",
    fontWeight: 700,
    color: "#6b7280",
    letterSpacing: "0.08em",
    marginBottom: "4px",
  };
  const valueStyle = { fontSize: "18px", fontWeight: 700, color: "#1a1a1a" };

  return (
    <div
      style={{
        flex: "1 1 320px",
        minWidth: "320px",
        display: "flex",
        flexDirection: "column",
        fontFamily: "monospace",
        background: "white",
      }}
    >
      {/* Row 1: SOLAR + LIGHT + EV + ELEV */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr 1fr",
          borderBottom: "2px solid #1a1a1a",
        }}
      >
        <div style={{ padding: "12px", borderRight: "1px solid #e5e7eb" }}>
          <div style={labelStyle}>SOLAR</div>
          <div style={valueStyle}>
            {solarAltitude != null ? `${solarAltitude.toFixed(0)}°` : "--"}
          </div>
          <div style={{ fontSize: "9px", color: "#9ca3af", fontWeight: 600 }}>
            {getSolarLabel(solarAltitude)}
          </div>
        </div>
        <div style={{ padding: "12px", borderRight: "1px solid #e5e7eb" }}>
          <div style={labelStyle}>LIGHT</div>
          <div style={{ fontSize: "14px", fontWeight: 700, color: "#1a1a1a" }}>
            {getLightRemaining() || "DARK"}
          </div>
        </div>
        <div style={{ padding: "12px", borderRight: "1px solid #e5e7eb" }}>
          <div style={labelStyle}>EV</div>
          <div style={valueStyle}>{photo?.lightValue ?? "--"}</div>
          <div style={{ fontSize: "9px", color: "#9ca3af", fontWeight: 600 }}>
            {getEvLabel(photo?.lightValue)}
          </div>
        </div>
        <div style={{ padding: "12px" }}>
          <div style={labelStyle}>ELEV</div>
          <div style={valueStyle}>
            {photo?.elevation != null ? Math.round(photo.elevation) : "--"}
            <span style={{ fontSize: "10px", color: "#9ca3af" }}>m</span>
          </div>
        </div>
      </div>

      {/* Row 2: ELEVATION PROFILE - grows to fill */}
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "2px solid #1a1a1a",
          flexGrow: 1,
          display: "flex",
          flexDirection: "column",
          minHeight: "140px",
        }}
      >
        <div style={{ ...labelStyle, marginBottom: "8px" }}>
          ELEVATION PROFILE
        </div>
        <div style={{ flexGrow: 1, position: "relative" }}>
          <ElevationSparkline
            data={elevationProfile}
            currentIndex={currentElevationIndex}
            fillHeight={true}
            accentColor={dayColor}
          />
        </div>
      </div>

      {/* Row 3: KM + TOTALS */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr 1fr",
          background: "#fafafa",
        }}
      >
        <div style={{ padding: "10px", borderRight: "1px solid #e5e7eb" }}>
          <div style={labelStyle}>KM</div>
          <div style={{ fontSize: "16px", fontWeight: 900, color: "#1a1a1a" }}>
            {progress?.km ?? 0}
            <span style={{ fontSize: "10px", color: "#9ca3af" }}>
              /{progress?.total ?? 0}
            </span>
          </div>
        </div>
        <div style={{ padding: "10px", borderRight: "1px solid #e5e7eb" }}>
          <div style={labelStyle}>ASCENT</div>
          <div style={{ fontSize: "14px", fontWeight: 900, color: "#059669" }}>
            +{dayStats?.ascent?.toLocaleString() || 0}m
          </div>
        </div>
        <div style={{ padding: "10px", borderRight: "1px solid #e5e7eb" }}>
          <div style={labelStyle}>DESCENT</div>
          <div style={{ fontSize: "14px", fontWeight: 900, color: "#dc2626" }}>
            -{dayStats?.descent?.toLocaleString() || 0}m
          </div>
        </div>
        <div style={{ padding: "10px" }}>
          <div style={labelStyle}>PHOTOS</div>
          <div style={{ fontSize: "14px", fontWeight: 900, color: "#1a1a1a" }}>
            {dayStats?.photoCount || 0}
          </div>
        </div>
      </div>
    </div>
  );
}

// LEGACY: Unified Data Dashboard - keeping for reference
function DataDashboard({
  photo,
  photoIndex,
  totalPhotos,
  onPrev,
  onNext,
  dayPoints,
  dayStats,
  dayColor,
}) {
  // --- FORMATTERS ---
  const formatTime = (timestamp) => {
    if (!timestamp) return { time: "--:--", period: "" };
    const timeStr = timestamp.toLocaleTimeString("en-US", {
      timeZone: "America/Vancouver",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
    const parts = timeStr.match(/(\d+:\d+)\s*(AM|PM)/i);
    if (parts) return { time: parts[1], period: parts[2] };
    return { time: timeStr, period: "" };
  };

  const formatCoord = (val, isLat) => {
    if (val == null) return "--";
    const dir = isLat ? (val >= 0 ? "N" : "S") : val >= 0 ? "E" : "W";
    return `${Math.abs(val).toFixed(4)}° ${dir}`;
  };

  // --- SOLAR CALCULATIONS ---
  const sunPosition = useMemo(() => {
    if (!photo?.timestamp || !photo?.lat || !photo?.lng) return null;
    return SunCalc.getPosition(photo.timestamp, photo.lat, photo.lng);
  }, [photo]);

  const sunTimes = useMemo(() => {
    if (!photo?.timestamp || !photo?.lat || !photo?.lng) return null;
    return SunCalc.getTimes(photo.timestamp, photo.lat, photo.lng);
  }, [photo]);

  const solarAltitude = sunPosition
    ? (sunPosition.altitude * 180) / Math.PI
    : null;

  const getSolarLabel = (alt) => {
    if (alt == null) return "--";
    if (alt < -6) return "NIGHT";
    if (alt < 0) return "TWILIGHT";
    if (alt < 10) return "LOW";
    return "DAY";
  };

  const getLightRemaining = () => {
    if (!photo?.timestamp || !sunTimes?.sunset) return null;
    const now = photo.timestamp.getTime();
    const sunset = sunTimes.sunset.getTime();
    if (now > sunset) return null;
    const diff = sunset - now;
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    return `${hours}h ${mins.toString().padStart(2, "0")}m`;
  };

  const getEvLabel = (ev) => {
    if (ev == null) return "";
    if (ev >= 13) return "BRIGHT";
    if (ev >= 10) return "SUNNY";
    if (ev >= 7) return "OVERCAST";
    if (ev >= 4) return "DIM";
    return "DARK";
  };

  // --- BEARING CALCULATION ---
  const bearing = useMemo(() => {
    if (!dayPoints?.length || !photo?.timestamp) return null;
    const photoTime = photo.timestamp.getTime();
    let prevPoint = null;
    for (const point of dayPoints) {
      if (point.timestamp.getTime() >= photoTime && prevPoint) {
        const lat1 = (prevPoint.lat * Math.PI) / 180;
        const lat2 = (point.lat * Math.PI) / 180;
        const dLng = ((point.lng - prevPoint.lng) * Math.PI) / 180;
        const y = Math.sin(dLng) * Math.cos(lat2);
        const x =
          Math.cos(lat1) * Math.sin(lat2) -
          Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);
        let brng = (Math.atan2(y, x) * 180) / Math.PI;
        return (brng + 360) % 360;
      }
      prevPoint = point;
    }
    return null;
  }, [dayPoints, photo]);

  const getCompassArrow = (deg) => {
    if (deg == null) return "→";
    // 8 directions
    const arrows = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"];
    const index = Math.round(deg / 45) % 8;
    return arrows[index];
  };

  // --- PROGRESS & ELEVATION ---
  const progress = useMemo(() => {
    if (!dayPoints?.length || !photo?.timestamp) return null;
    const photoTime = photo.timestamp.getTime();
    let distanceTraveled = 0;
    let totalDistance = 0;
    let prevPoint = null;
    let foundPhoto = false;

    for (const point of dayPoints) {
      if (prevPoint) {
        const segmentDist = haversine(prevPoint, point);
        totalDistance += segmentDist;
        if (!foundPhoto && point.timestamp.getTime() >= photoTime)
          foundPhoto = true;
        if (!foundPhoto) distanceTraveled += segmentDist;
      }
      prevPoint = point;
    }

    return {
      km: Math.round(distanceTraveled),
      total: Math.round(totalDistance),
      percent:
        totalDistance > 0
          ? Math.round((distanceTraveled / totalDistance) * 100)
          : 0,
    };
  }, [dayPoints, photo]);

  const elevationProfile = useMemo(() => {
    if (!dayPoints?.length) return [];
    const sampleRate = Math.max(1, Math.floor(dayPoints.length / 50));
    return dayPoints
      .filter((_, i) => i % sampleRate === 0)
      .map((p) => p.elevation)
      .filter((e) => e != null);
  }, [dayPoints]);

  const currentElevationIndex = useMemo(() => {
    if (!elevationProfile?.length || !progress?.percent) return 0;
    return Math.round((progress.percent / 100) * (elevationProfile.length - 1));
  }, [elevationProfile, progress]);

  const timeData = formatTime(photo?.timestamp);
  const hasPrev = photoIndex > 0;
  const hasNext = photoIndex < totalPhotos - 1;

  // Grid cell style helper
  const cellStyle = (extras = {}) => ({
    background: "white",
    padding: "12px",
    display: "flex",
    flexDirection: "column",
    justifyContent: "center",
    fontFamily: "monospace",
    ...extras,
  });

  const labelStyle = {
    fontSize: "9px",
    fontWeight: 700,
    color: "#6b7280",
    letterSpacing: "0.08em",
    marginBottom: "4px",
  };

  const valueStyle = {
    fontSize: "20px",
    fontWeight: 700,
    color: "#1a1a1a",
  };

  // Flat 3-column grid for perfect row alignment
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "160px 1fr 1fr",
        gridTemplateRows: "auto auto auto auto",
        gap: "2px",
        background: "#1a1a1a",
        borderLeft: "2px solid #1a1a1a",
        fontFamily: "monospace",
        flex: "0 0 500px",
        alignSelf: "flex-start",
      }}
    >
      {/* ROW 1: TIME | SOLAR ALT | LIGHT REM */}
      <div
        style={cellStyle({
          textAlign: "center",
          background: "#fafafa",
          padding: "16px 12px",
        })}
      >
        <div
          style={{
            fontSize: "32px",
            fontWeight: 900,
            color: "#1a1a1a",
            lineHeight: 1,
          }}
        >
          {timeData.time}
        </div>
        <div
          style={{
            fontSize: "11px",
            fontWeight: 700,
            color: "#6b7280",
            marginTop: "4px",
          }}
        >
          {timeData.period}
        </div>
      </div>
      <div style={cellStyle({ padding: "16px 12px" })}>
        <div style={labelStyle}>SOLAR ALT</div>
        <div style={valueStyle}>
          {solarAltitude != null ? `${solarAltitude.toFixed(1)}°` : "--"}
          <span
            style={{ fontSize: "10px", color: "#9ca3af", marginLeft: "6px" }}
          >
            {getSolarLabel(solarAltitude)}
          </span>
        </div>
      </div>
      <div style={cellStyle({ padding: "16px 12px" })}>
        <div style={labelStyle}>LIGHT REM</div>
        <div style={valueStyle}>{getLightRemaining() || "DARK"}</div>
      </div>

      {/* ROW 2: OPTICS | EV | ELEVATION */}
      <div
        style={cellStyle({
          background: "#f5f5f5",
          textAlign: "center",
          padding: "16px 12px",
        })}
      >
        <div style={labelStyle}>OPTICS</div>
        <div style={{ fontSize: "15px", fontWeight: 700, color: "#1a1a1a" }}>
          {photo?.focalLength35mm ? `${photo.focalLength35mm}mm` : "--"} ƒ/
          {photo?.aperture || "--"}
        </div>
        <div
          style={{
            fontSize: "12px",
            fontWeight: 600,
            color: "#6b7280",
            marginTop: "4px",
          }}
        >
          ISO {photo?.iso || "--"} · {photo?.shutterSpeed || "--"}
        </div>
      </div>
      <div style={cellStyle({ padding: "16px 12px" })}>
        <div style={labelStyle}>EV</div>
        <div style={valueStyle}>
          {photo?.lightValue ?? "--"}
          <span
            style={{ fontSize: "10px", color: "#9ca3af", marginLeft: "6px" }}
          >
            {getEvLabel(photo?.lightValue)}
          </span>
        </div>
      </div>
      <div style={cellStyle({ padding: "16px 12px" })}>
        <div style={labelStyle}>ELEVATION</div>
        <div style={valueStyle}>
          {photo?.elevation != null ? Math.round(photo.elevation) : "--"}
          <span style={{ fontSize: "11px", color: "#9ca3af" }}>m</span>
        </div>
      </div>

      {/* ROW 3: NAV + COMPASS | ELEVATION PROFILE (spans 2 cols) */}
      <div style={cellStyle({ background: "#fafafa", padding: "12px" })}>
        {/* Navigation Buttons - Chunky */}
        <div style={{ display: "flex", marginBottom: "8px" }}>
          <button
            onClick={onPrev}
            disabled={!hasPrev}
            style={{
              flex: 1,
              height: "48px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "white",
              border: "2px solid #1a1a1a",
              borderRight: "1px solid #1a1a1a",
              cursor: hasPrev ? "pointer" : "not-allowed",
              opacity: hasPrev ? 1 : 0.3,
            }}
          >
            <ChevronLeft size={24} color="#1a1a1a" />
          </button>
          <button
            onClick={onNext}
            disabled={!hasNext}
            style={{
              flex: 1,
              height: "48px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "white",
              border: "2px solid #1a1a1a",
              borderLeft: "1px solid #1a1a1a",
              cursor: hasNext ? "pointer" : "not-allowed",
              opacity: hasNext ? 1 : 0.3,
            }}
          >
            <ChevronRight size={24} color="#1a1a1a" />
          </button>
        </div>
        {/* Photo Counter */}
        <div
          style={{
            fontSize: "11px",
            fontWeight: 700,
            color: "#1a1a1a",
            textAlign: "center",
            marginBottom: "8px",
          }}
        >
          {photoIndex + 1} / {totalPhotos}
        </div>
        {/* Compass Arrow */}
        <div style={{ textAlign: "center" }}>
          <div style={{ fontSize: "32px", lineHeight: 1, color: "#1a1a1a" }}>
            {getCompassArrow(bearing)}
          </div>
          <div
            style={{
              fontSize: "10px",
              fontWeight: 700,
              color: "#6b7280",
              marginTop: "2px",
            }}
          >
            {bearing != null ? `${Math.round(bearing)}°` : "--"}
          </div>
        </div>
      </div>
      <div
        style={{ ...cellStyle({ padding: "12px 16px" }), gridColumn: "span 2" }}
      >
        <div style={{ ...labelStyle, marginBottom: "8px" }}>
          ELEVATION PROFILE
        </div>
        <div style={{ minHeight: "100px" }}>
          <ElevationSparkline
            data={elevationProfile}
            currentIndex={currentElevationIndex}
            height={100}
            accentColor={dayColor}
          />
        </div>
      </div>

      {/* ROW 4: COORDINATES | KM | ASCENT | DESCENT | PHOTOS */}
      <div style={cellStyle({ textAlign: "center", padding: "12px" })}>
        <div
          style={{
            fontSize: "10px",
            fontWeight: 600,
            color: "#1a1a1a",
            lineHeight: 1.5,
          }}
        >
          <div>{formatCoord(photo?.lat, true)}</div>
          <div>{formatCoord(photo?.lng, false)}</div>
        </div>
      </div>
      <div
        style={{
          gridColumn: "span 2",
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr 1fr",
          gap: "2px",
          background: "#1a1a1a",
        }}
      >
        <div style={cellStyle({ background: "#fafafa", padding: "10px" })}>
          <div
            style={{
              fontSize: "9px",
              fontWeight: 700,
              color: "#6b7280",
              letterSpacing: "0.08em",
            }}
          >
            KM
          </div>
          <div style={{ fontSize: "16px", fontWeight: 900, color: "#1a1a1a" }}>
            {progress?.km ?? 0}
            <span style={{ fontSize: "10px", color: "#9ca3af" }}>
              /{progress?.total ?? 0}
            </span>
          </div>
        </div>
        <div style={cellStyle({ background: "#fafafa", padding: "10px" })}>
          <div
            style={{
              fontSize: "9px",
              fontWeight: 700,
              color: "#6b7280",
              letterSpacing: "0.08em",
            }}
          >
            ASCENT
          </div>
          <div style={{ fontSize: "14px", fontWeight: 900, color: "#059669" }}>
            +{dayStats?.ascent?.toLocaleString() || 0}m
          </div>
        </div>
        <div style={cellStyle({ background: "#fafafa", padding: "10px" })}>
          <div
            style={{
              fontSize: "9px",
              fontWeight: 700,
              color: "#6b7280",
              letterSpacing: "0.08em",
            }}
          >
            DESCENT
          </div>
          <div style={{ fontSize: "14px", fontWeight: 900, color: "#dc2626" }}>
            -{dayStats?.descent?.toLocaleString() || 0}m
          </div>
        </div>
        <div style={cellStyle({ background: "#fafafa", padding: "10px" })}>
          <div
            style={{
              fontSize: "9px",
              fontWeight: 700,
              color: "#6b7280",
              letterSpacing: "0.08em",
            }}
          >
            PHOTOS
          </div>
          <div style={{ fontSize: "14px", fontWeight: 900, color: "#1a1a1a" }}>
            {dayStats?.photoCount || 0}
          </div>
        </div>
      </div>
    </div>
  );
}

// Technical Strip - LEGACY (keeping for reference)
function TechnicalStrip({ photo, photoIndex, totalPhotos, onPrev, onNext }) {
  const formatTime = (timestamp) => {
    if (!timestamp) return { time: "--:--", period: "" };
    const timeStr = timestamp.toLocaleTimeString("en-US", {
      timeZone: "America/Vancouver",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
    const parts = timeStr.match(/(\d+:\d+)\s*(AM|PM)/i);
    if (parts) return { time: parts[1], period: parts[2] };
    return { time: timeStr, period: "" };
  };

  const formatCoord = (val, isLat) => {
    if (val == null) return "--";
    const dir = isLat ? (val >= 0 ? "N" : "S") : val >= 0 ? "E" : "W";
    return `${Math.abs(val).toFixed(4)}° ${dir}`;
  };

  const timeData = formatTime(photo?.timestamp);
  const hasPrev = photoIndex > 0;
  const hasNext = photoIndex < totalPhotos - 1;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        borderLeft: "2px solid #1a1a1a",
        borderRight: "2px solid #1a1a1a",
        fontFamily: "monospace",
        background: "#fafafa",
      }}
    >
      {/* TIME - Top Block */}
      <div
        style={{
          padding: "16px 12px",
          borderBottom: "2px solid #1a1a1a",
          textAlign: "center",
          background: "white",
        }}
      >
        <div
          style={{
            fontSize: "36px",
            fontWeight: 900,
            letterSpacing: "-0.02em",
            color: "#1a1a1a",
            lineHeight: 1,
          }}
        >
          {timeData.time}
        </div>
        <div
          style={{
            fontSize: "12px",
            fontWeight: 700,
            color: "#6b7280",
            marginTop: "4px",
          }}
        >
          {timeData.period}
        </div>
      </div>

      {/* OPTICS - Camera Data */}
      <div
        style={{
          padding: "12px",
          borderBottom: "2px solid #1a1a1a",
          background: "#f5f5f5",
        }}
      >
        <div
          style={{
            fontSize: "9px",
            fontWeight: 700,
            color: "#6b7280",
            letterSpacing: "0.08em",
            marginBottom: "8px",
            textAlign: "center",
          }}
        >
          OPTICS
        </div>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "6px",
            alignItems: "center",
          }}
        >
          <div style={{ fontSize: "16px", fontWeight: 700, color: "#1a1a1a" }}>
            {photo?.focalLength35mm ? `${photo.focalLength35mm}mm` : "--"}
          </div>
          <div style={{ fontSize: "13px", fontWeight: 600, color: "#1a1a1a" }}>
            ISO {photo?.iso || "--"}
          </div>
          <div style={{ fontSize: "13px", fontWeight: 600, color: "#1a1a1a" }}>
            ƒ/{photo?.aperture || "--"}
          </div>
          <div style={{ fontSize: "13px", fontWeight: 600, color: "#1a1a1a" }}>
            {photo?.shutterSpeed || "--"}
          </div>
        </div>
      </div>

      {/* NAVIGATION - The Fix */}
      <div
        style={{
          padding: "16px 12px",
          borderBottom: "2px solid #1a1a1a",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "12px",
          background: "white",
        }}
      >
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            onClick={onPrev}
            disabled={!hasPrev}
            style={{
              width: "44px",
              height: "44px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "white",
              border: "2px solid #1a1a1a",
              cursor: hasPrev ? "pointer" : "not-allowed",
              opacity: hasPrev ? 1 : 0.3,
            }}
          >
            <ChevronLeft size={20} color="#1a1a1a" />
          </button>
          <button
            onClick={onNext}
            disabled={!hasNext}
            style={{
              width: "44px",
              height: "44px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              background: "white",
              border: "2px solid #1a1a1a",
              cursor: hasNext ? "pointer" : "not-allowed",
              opacity: hasNext ? 1 : 0.3,
            }}
          >
            <ChevronRight size={20} color="#1a1a1a" />
          </button>
        </div>
        <div
          style={{
            fontSize: "12px",
            fontWeight: 700,
            color: "#1a1a1a",
            letterSpacing: "0.02em",
          }}
        >
          {photoIndex + 1} / {totalPhotos}
        </div>
      </div>

      {/* COORDINATES - Bottom Block */}
      <div
        style={{
          padding: "12px",
          textAlign: "center",
          marginTop: "auto",
          background: "white",
        }}
      >
        <div
          style={{
            fontSize: "9px",
            fontWeight: 700,
            color: "#6b7280",
            letterSpacing: "0.08em",
            marginBottom: "6px",
          }}
        >
          COORDINATES
        </div>
        <div
          style={{
            fontSize: "11px",
            fontWeight: 600,
            color: "#1a1a1a",
            lineHeight: 1.6,
          }}
        >
          <div>{formatCoord(photo?.lat, true)}</div>
          <div>{formatCoord(photo?.lng, false)}</div>
        </div>
      </div>
    </div>
  );
}

// Mission Log - The "Context Layer" (Column 3 of Triptych)
function MissionLog({ photo, dayPoints, dayStats }) {
  // --- SOLAR CALCULATIONS ---
  const sunPosition = useMemo(() => {
    if (!photo?.timestamp || !photo?.lat || !photo?.lng) return null;
    return SunCalc.getPosition(photo.timestamp, photo.lat, photo.lng);
  }, [photo]);

  const sunTimes = useMemo(() => {
    if (!photo?.timestamp || !photo?.lat || !photo?.lng) return null;
    return SunCalc.getTimes(photo.timestamp, photo.lat, photo.lng);
  }, [photo]);

  const solarAltitude = sunPosition
    ? (sunPosition.altitude * 180) / Math.PI
    : null;

  const getSolarLabel = (alt) => {
    if (alt == null) return "UNKNOWN";
    if (alt < -6) return "NIGHT";
    if (alt < 0) return "TWILIGHT";
    if (alt < 10) return "LOW";
    return "DAY";
  };

  const getLightRemaining = () => {
    if (!photo?.timestamp || !sunTimes?.sunset) return null;
    const now = photo.timestamp.getTime();
    const sunset = sunTimes.sunset.getTime();
    if (now > sunset) return null;
    const diff = sunset - now;
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    return `${hours}h ${mins.toString().padStart(2, "0")}m`;
  };

  const getEvLabel = (ev) => {
    if (ev == null) return "";
    if (ev >= 13) return "BRIGHT";
    if (ev >= 10) return "SUNNY";
    if (ev >= 7) return "OVERCAST";
    if (ev >= 4) return "DIM";
    return "DARK";
  };

  // --- PROGRESS CALCULATIONS ---
  const progress = useMemo(() => {
    if (!dayPoints?.length || !photo?.timestamp) return null;
    const photoTime = photo.timestamp.getTime();
    let distanceTraveled = 0;
    let totalDistance = 0;
    let prevPoint = null;
    let foundPhoto = false;

    for (const point of dayPoints) {
      if (prevPoint) {
        const segmentDist = haversine(prevPoint, point);
        totalDistance += segmentDist;
        if (!foundPhoto && point.timestamp.getTime() >= photoTime) {
          foundPhoto = true;
        }
        if (!foundPhoto) {
          distanceTraveled += segmentDist;
        }
      }
      prevPoint = point;
    }

    return {
      km: Math.round(distanceTraveled),
      total: Math.round(totalDistance),
      percent:
        totalDistance > 0
          ? Math.round((distanceTraveled / totalDistance) * 100)
          : 0,
    };
  }, [dayPoints, photo]);

  // --- ELEVATION PROFILE ---
  const elevationProfile = useMemo(() => {
    if (!dayPoints?.length) return [];
    const sampleRate = Math.max(1, Math.floor(dayPoints.length / 50));
    return dayPoints
      .filter((_, i) => i % sampleRate === 0)
      .map((p) => p.elevation)
      .filter((e) => e != null);
  }, [dayPoints]);

  const currentElevationIndex = useMemo(() => {
    if (!elevationProfile?.length || !progress?.percent) return 0;
    return Math.round((progress.percent / 100) * (elevationProfile.length - 1));
  }, [elevationProfile, progress?.percent]);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        fontFamily: "monospace",
        background: "white",
      }}
    >
      {/* SOLAR / ATMOSPHERE */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "2px",
          background: "#1a1a1a",
          borderBottom: "2px solid #1a1a1a",
        }}
      >
        <div style={{ background: "white", padding: "12px" }}>
          <div
            style={{
              fontSize: "9px",
              fontWeight: 700,
              color: "#6b7280",
              letterSpacing: "0.08em",
              marginBottom: "4px",
            }}
          >
            SOLAR ALT
          </div>
          <div style={{ fontSize: "20px", fontWeight: 700, color: "#1a1a1a" }}>
            {solarAltitude != null ? `${solarAltitude.toFixed(1)}°` : "--"}
            <span
              style={{
                fontSize: "10px",
                color: "#9ca3af",
                marginLeft: "6px",
                fontWeight: 600,
              }}
            >
              {getSolarLabel(solarAltitude)}
            </span>
          </div>
        </div>
        <div style={{ background: "white", padding: "12px" }}>
          <div
            style={{
              fontSize: "9px",
              fontWeight: 700,
              color: "#6b7280",
              letterSpacing: "0.08em",
              marginBottom: "4px",
            }}
          >
            LIGHT REM
          </div>
          <div style={{ fontSize: "20px", fontWeight: 700, color: "#1a1a1a" }}>
            {getLightRemaining() || "DARK"}
          </div>
        </div>
        <div style={{ background: "white", padding: "12px" }}>
          <div
            style={{
              fontSize: "9px",
              fontWeight: 700,
              color: "#6b7280",
              letterSpacing: "0.08em",
              marginBottom: "4px",
            }}
          >
            EV
          </div>
          <div style={{ fontSize: "20px", fontWeight: 700, color: "#1a1a1a" }}>
            {photo?.lightValue ?? "--"}
            <span
              style={{
                fontSize: "10px",
                color: "#9ca3af",
                marginLeft: "6px",
                fontWeight: 600,
              }}
            >
              {getEvLabel(photo?.lightValue)}
            </span>
          </div>
        </div>
        <div style={{ background: "white", padding: "12px" }}>
          <div
            style={{
              fontSize: "9px",
              fontWeight: 700,
              color: "#6b7280",
              letterSpacing: "0.08em",
              marginBottom: "4px",
            }}
          >
            ELEVATION
          </div>
          <div style={{ fontSize: "20px", fontWeight: 700, color: "#1a1a1a" }}>
            {photo?.elevation != null ? Math.round(photo.elevation) : "--"}
            <span
              style={{ fontSize: "11px", fontWeight: 600, color: "#9ca3af" }}
            >
              m
            </span>
          </div>
        </div>
      </div>

      {/* ELEVATION PROFILE */}
      <div
        style={{
          padding: "16px",
          borderBottom: "2px solid #1a1a1a",
          flexGrow: 1,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            fontSize: "9px",
            fontWeight: 700,
            color: "#6b7280",
            letterSpacing: "0.08em",
            marginBottom: "12px",
          }}
        >
          ELEVATION PROFILE
        </div>
        <div style={{ flexGrow: 1, minHeight: "100px" }}>
          <ElevationSparkline
            data={elevationProfile}
            currentIndex={currentElevationIndex}
            height={120}
          />
        </div>
      </div>

      {/* KM MARKER / PROGRESS */}
      <div
        style={{
          padding: "12px 16px",
          borderBottom: "2px solid #1a1a1a",
          display: "flex",
          alignItems: "baseline",
          gap: "8px",
        }}
      >
        <div
          style={{
            fontSize: "9px",
            fontWeight: 700,
            color: "#6b7280",
            letterSpacing: "0.08em",
          }}
        >
          KM
        </div>
        <div style={{ fontSize: "28px", fontWeight: 900, color: "#1a1a1a" }}>
          {progress?.km ?? 0}
        </div>
        <div style={{ fontSize: "14px", fontWeight: 600, color: "#9ca3af" }}>
          / {progress?.total ?? 0}
        </div>
      </div>

      {/* TOTALS FOOTER */}
      <div
        style={{
          padding: "12px 16px",
          marginTop: "auto",
          background: "#fafafa",
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr 1fr",
            gap: "8px",
          }}
        >
          <div>
            <div
              style={{
                fontSize: "9px",
                fontWeight: 700,
                color: "#6b7280",
                letterSpacing: "0.08em",
              }}
            >
              ASCENT
            </div>
            <div
              style={{ fontSize: "16px", fontWeight: 900, color: "#059669" }}
            >
              +{dayStats?.ascent?.toLocaleString() || 0}m
            </div>
          </div>
          <div>
            <div
              style={{
                fontSize: "9px",
                fontWeight: 700,
                color: "#6b7280",
                letterSpacing: "0.08em",
              }}
            >
              DESCENT
            </div>
            <div
              style={{ fontSize: "16px", fontWeight: 900, color: "#dc2626" }}
            >
              -{dayStats?.descent?.toLocaleString() || 0}m
            </div>
          </div>
          <div>
            <div
              style={{
                fontSize: "9px",
                fontWeight: 700,
                color: "#6b7280",
                letterSpacing: "0.08em",
              }}
            >
              PHOTOS
            </div>
            <div
              style={{ fontSize: "16px", fontWeight: 900, color: "#1a1a1a" }}
            >
              {dayStats?.photoCount || 0}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Telemetry Panel - Flight Recorder style industrial dashboard (LEGACY - keeping for mobile)
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

  const solarAltitude = sunPosition
    ? (sunPosition.altitude * 180) / Math.PI
    : null;

  const getSolarLabel = (alt) => {
    if (alt == null) return "UNKNOWN";
    if (alt < -6) return "NIGHT";
    if (alt < 0) return "TWILIGHT";
    if (alt < 10) return "LOW";
    return "DAY";
  };

  const getLightRemaining = () => {
    if (!photo?.timestamp || !sunTimes?.sunset) return null;
    const now = photo.timestamp.getTime();
    const sunset = sunTimes.sunset.getTime();
    if (now > sunset) return null;
    const diff = sunset - now;
    const hours = Math.floor(diff / (1000 * 60 * 60));
    const mins = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
    return `${hours}h ${mins.toString().padStart(2, "0")}m`;
  };

  // --- PROGRESS CALCULATIONS ---
  const { progress } = useMemo(() => {
    if (!dayPoints?.length || !photo?.timestamp) return { progress: null };

    const photoTime = photo.timestamp.getTime();
    let distanceTraveled = 0;
    let totalDistance = 0;
    let prevPoint = null;
    let foundPhoto = false;

    for (let i = 0; i < dayPoints.length; i++) {
      const point = dayPoints[i];
      if (prevPoint) {
        const segmentDist = haversine(prevPoint, point);
        totalDistance += segmentDist;
        if (!foundPhoto && point.timestamp.getTime() >= photoTime) {
          foundPhoto = true;
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
        percent:
          totalDistance > 0
            ? Math.round((distanceTraveled / totalDistance) * 100)
            : 0,
      },
    };
  }, [dayPoints, photo]);

  // --- ELEVATION PROFILE DATA ---
  const elevationProfile = useMemo(() => {
    if (!dayPoints?.length) return [];
    const sampleRate = Math.max(1, Math.floor(dayPoints.length / 50));
    return dayPoints
      .filter((_, i) => i % sampleRate === 0)
      .map((p) => p.elevation)
      .filter((e) => e != null);
  }, [dayPoints]);

  const currentElevationIndex = useMemo(() => {
    if (!elevationProfile?.length || !progress?.percent) return 0;
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
        if (
          dist > 10 &&
          prevPoint.elevation != null &&
          point.elevation != null
        ) {
          const elevChange = point.elevation - prevPoint.elevation;
          return (elevChange / dist) * 100;
        }
      }
      prevPoint = point;
    }
    return null;
  }, [dayPoints, photo]);

  // --- BEARING CALCULATION ---
  const bearing = useMemo(() => {
    if (!dayPoints?.length || !photo?.timestamp) return null;
    const photoTime = photo.timestamp.getTime();
    let prevPoint = null;
    for (const point of dayPoints) {
      if (point.timestamp.getTime() >= photoTime && prevPoint) {
        // Calculate bearing from prevPoint to point
        const lat1 = (prevPoint.lat * Math.PI) / 180;
        const lat2 = (point.lat * Math.PI) / 180;
        const dLng = ((point.lng - prevPoint.lng) * Math.PI) / 180;
        const y = Math.sin(dLng) * Math.cos(lat2);
        const x =
          Math.cos(lat1) * Math.sin(lat2) -
          Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLng);
        let brng = (Math.atan2(y, x) * 180) / Math.PI;
        brng = (brng + 360) % 360; // Normalize to 0-360
        return Math.round(brng);
      }
      prevPoint = point;
    }
    return null;
  }, [dayPoints, photo]);

  const getBearingArrow = (deg) => {
    if (deg == null) return { arrow: "→", label: "--" };
    // 8 cardinal/intercardinal directions
    const arrows = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"];
    const labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
    const index = Math.round(deg / 45) % 8;
    return { arrow: arrows[index], label: labels[index] };
  };

  // --- FORMATTERS ---
  const formatTime = (timestamp) => {
    if (!timestamp) return "--:--";
    const timeStr = timestamp.toLocaleTimeString("en-US", {
      timeZone: "America/Vancouver",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
    // Split into time and period
    const parts = timeStr.match(/(\d+:\d+)\s*(AM|PM)/i);
    if (parts) return { time: parts[1], period: parts[2] };
    return { time: timeStr, period: "" };
  };

  const formatCoord = (val, isLat) => {
    if (val == null) return "--";
    const dir = isLat ? (val >= 0 ? "N" : "S") : val >= 0 ? "E" : "W";
    return `${Math.abs(val).toFixed(4)}° ${dir}`;
  };

  const getEvLabel = (ev) => {
    if (ev == null) return "";
    if (ev >= 13) return "BRIGHT";
    if (ev >= 10) return "SUNNY";
    if (ev >= 7) return "OVERCAST";
    if (ev >= 4) return "DIM";
    return "DARK";
  };

  const getLensLabel = (mm) => {
    if (mm == null) return "";
    if (mm <= 24) return "WIDE";
    if (mm <= 50) return "NORMAL";
    return "TELE";
  };

  const timeData = formatTime(photo?.timestamp);
  const hasOptics =
    photo?.iso ||
    photo?.lightValue ||
    photo?.shutterSpeed ||
    photo?.focalLength35mm;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        border: "2px solid #1a1a1a",
        fontFamily: "monospace",
      }}
    >
      {/* ZONE A: TIME HEADER */}
      <div
        style={{
          padding: "16px 12px",
          borderBottom: "2px solid #1a1a1a",
          background: "#fafafa",
        }}
      >
        <div
          style={{
            fontSize: "48px",
            fontWeight: 900,
            letterSpacing: "-0.03em",
            color: "#1a1a1a",
            lineHeight: 1,
          }}
        >
          {timeData.time}
          <span
            style={{
              fontSize: "14px",
              fontWeight: 700,
              verticalAlign: "super",
              marginLeft: "4px",
              letterSpacing: "0",
            }}
          >
            {timeData.period}
          </span>
        </div>
      </div>

      {/* ZONE A: SOLAR - Gap Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "2px",
          background: "#1a1a1a",
        }}
      >
        <div style={{ background: "white", padding: "10px" }}>
          <div
            style={{
              fontSize: "9px",
              fontWeight: 700,
              color: "#6b7280",
              letterSpacing: "0.08em",
              marginBottom: "4px",
            }}
          >
            SOLAR ALT
          </div>
          <div style={{ fontSize: "18px", fontWeight: 700, color: "#1a1a1a" }}>
            {solarAltitude != null ? `${solarAltitude.toFixed(1)}°` : "--"}
            <span
              style={{
                fontSize: "10px",
                color: "#9ca3af",
                marginLeft: "6px",
                fontWeight: 600,
              }}
            >
              {getSolarLabel(solarAltitude)}
            </span>
          </div>
        </div>
        <div style={{ background: "white", padding: "10px" }}>
          <div
            style={{
              fontSize: "9px",
              fontWeight: 700,
              color: "#6b7280",
              letterSpacing: "0.08em",
              marginBottom: "4px",
            }}
          >
            LIGHT REM
          </div>
          <div style={{ fontSize: "18px", fontWeight: 700, color: "#1a1a1a" }}>
            {getLightRemaining() || "DARK"}
          </div>
        </div>
      </div>

      {/* ZONE B: OPTICS - 2x2 Gap Grid */}
      {hasOptics && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: "2px",
            background: "#1a1a1a",
          }}
        >
          <div style={{ background: "#f5f5f5", padding: "10px" }}>
            <div
              style={{
                fontSize: "9px",
                fontWeight: 700,
                color: "#6b7280",
                letterSpacing: "0.08em",
              }}
            >
              ISO
            </div>
            <div
              style={{ fontSize: "18px", fontWeight: 700, color: "#1a1a1a" }}
            >
              {photo.iso || "--"}
            </div>
          </div>
          <div style={{ background: "#f5f5f5", padding: "10px" }}>
            <div
              style={{
                fontSize: "9px",
                fontWeight: 700,
                color: "#6b7280",
                letterSpacing: "0.08em",
              }}
            >
              EV
            </div>
            <div
              style={{ fontSize: "18px", fontWeight: 700, color: "#1a1a1a" }}
            >
              {photo.lightValue ?? "--"}
              <span
                style={{
                  fontSize: "10px",
                  color: "#9ca3af",
                  marginLeft: "6px",
                  fontWeight: 600,
                }}
              >
                {getEvLabel(photo.lightValue)}
              </span>
            </div>
          </div>
          <div style={{ background: "#f5f5f5", padding: "10px" }}>
            <div
              style={{
                fontSize: "9px",
                fontWeight: 700,
                color: "#6b7280",
                letterSpacing: "0.08em",
              }}
            >
              LENS
            </div>
            <div
              style={{ fontSize: "18px", fontWeight: 700, color: "#1a1a1a" }}
            >
              {photo.focalLength35mm ? `${photo.focalLength35mm}mm` : "--"}
              <span
                style={{
                  fontSize: "10px",
                  color: "#9ca3af",
                  marginLeft: "6px",
                  fontWeight: 600,
                }}
              >
                {getLensLabel(photo.focalLength35mm)}
              </span>
            </div>
          </div>
          <div style={{ background: "#f5f5f5", padding: "10px" }}>
            <div
              style={{
                fontSize: "9px",
                fontWeight: 700,
                color: "#6b7280",
                letterSpacing: "0.08em",
              }}
            >
              EXP
            </div>
            <div
              style={{ fontSize: "18px", fontWeight: 700, color: "#1a1a1a" }}
            >
              {photo.shutterSpeed || "--"}
              {photo.aperture && (
                <span
                  style={{
                    fontSize: "12px",
                    color: "#6b7280",
                    marginLeft: "4px",
                  }}
                >
                  ƒ/{photo.aperture}
                </span>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ZONE C: SPATIAL - Gap Grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: "2px",
          background: "#1a1a1a",
        }}
      >
        <div style={{ background: "white", padding: "10px" }}>
          <div
            style={{
              fontSize: "9px",
              fontWeight: 700,
              color: "#6b7280",
              letterSpacing: "0.08em",
              marginBottom: "4px",
            }}
          >
            KM MARKER
          </div>
          <div style={{ fontSize: "20px", fontWeight: 900, color: "#1a1a1a" }}>
            {progress?.km ?? "--"}
            <span
              style={{ fontSize: "11px", fontWeight: 600, color: "#9ca3af" }}
            >
              /{progress?.total ?? "--"}
            </span>
          </div>
        </div>
        <div style={{ background: "white", padding: "10px" }}>
          <div
            style={{
              fontSize: "9px",
              fontWeight: 700,
              color: "#6b7280",
              letterSpacing: "0.08em",
              marginBottom: "4px",
            }}
          >
            GRADE
          </div>
          <div
            style={{
              fontSize: "20px",
              fontWeight: 900,
              color:
                grade != null
                  ? grade > 0
                    ? "#059669"
                    : grade < 0
                      ? "#dc2626"
                      : "#1a1a1a"
                  : "#1a1a1a",
            }}
          >
            {grade != null
              ? `${grade > 0 ? "+" : ""}${grade.toFixed(1)}%`
              : "0.0%"}
          </div>
        </div>
        <div
          style={{ background: "white", padding: "10px", textAlign: "center" }}
        >
          <div
            style={{
              fontSize: "9px",
              fontWeight: 700,
              color: "#6b7280",
              letterSpacing: "0.08em",
              marginBottom: "2px",
            }}
          >
            BEARING
          </div>
          <div style={{ fontSize: "28px", lineHeight: 1, color: "#1a1a1a" }}>
            {getBearingArrow(bearing).arrow}
          </div>
          <div
            style={{
              fontSize: "10px",
              fontWeight: 700,
              color: "#6b7280",
              marginTop: "2px",
            }}
          >
            {bearing != null
              ? `${bearing}° ${getBearingArrow(bearing).label}`
              : "--"}
          </div>
        </div>
      </div>

      {/* ZONE D: ELEVATION PROFILE */}
      <div
        style={{
          padding: "12px",
          borderTop: "2px solid #1a1a1a",
          borderBottom: "2px solid #1a1a1a",
        }}
      >
        <div
          style={{
            fontSize: "9px",
            fontWeight: 700,
            color: "#6b7280",
            letterSpacing: "0.08em",
            marginBottom: "8px",
          }}
        >
          ELEVATION PROFILE
        </div>
        <ElevationSparkline
          data={elevationProfile}
          currentIndex={currentElevationIndex}
          height={80}
        />
      </div>

      {/* ZONE C2: LOCATION */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "2px",
          background: "#1a1a1a",
        }}
      >
        <div style={{ background: "white", padding: "10px" }}>
          <div
            style={{
              fontSize: "9px",
              fontWeight: 700,
              color: "#6b7280",
              letterSpacing: "0.08em",
              marginBottom: "4px",
            }}
          >
            ELEVATION
          </div>
          <div style={{ fontSize: "24px", fontWeight: 900, color: "#1a1a1a" }}>
            {photo?.elevation != null ? Math.round(photo.elevation) : "--"}
            <span
              style={{ fontSize: "12px", fontWeight: 600, color: "#9ca3af" }}
            >
              m
            </span>
          </div>
        </div>
        <div style={{ background: "white", padding: "10px" }}>
          <div
            style={{
              fontSize: "9px",
              fontWeight: 700,
              color: "#6b7280",
              letterSpacing: "0.08em",
              marginBottom: "4px",
            }}
          >
            COORDINATES
          </div>
          <div
            style={{
              fontSize: "11px",
              fontWeight: 600,
              color: "#1a1a1a",
              lineHeight: 1.5,
            }}
          >
            <div>{formatCoord(photo?.lat, true)}</div>
            <div>{formatCoord(photo?.lng, false)}</div>
          </div>
        </div>
      </div>

      {/* ZONE E: TOTALS FOOTER - White with heavy separator */}
      <div
        style={{
          borderTop: "4px solid #1a1a1a",
          padding: "12px",
          background: "white",
        }}
      >
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr 1fr",
            gap: "8px",
          }}
        >
          <div>
            <div
              style={{
                fontSize: "9px",
                fontWeight: 700,
                color: "#6b7280",
                letterSpacing: "0.08em",
              }}
            >
              ASCENT
            </div>
            <div
              style={{ fontSize: "16px", fontWeight: 900, color: "#059669" }}
            >
              +{dayStats?.ascent?.toLocaleString() || 0}m
            </div>
          </div>
          <div>
            <div
              style={{
                fontSize: "9px",
                fontWeight: 700,
                color: "#6b7280",
                letterSpacing: "0.08em",
              }}
            >
              DESCENT
            </div>
            <div
              style={{ fontSize: "16px", fontWeight: 900, color: "#dc2626" }}
            >
              -{dayStats?.descent?.toLocaleString() || 0}m
            </div>
          </div>
          <div>
            <div
              style={{
                fontSize: "9px",
                fontWeight: 700,
                color: "#6b7280",
                letterSpacing: "0.08em",
              }}
            >
              PHOTOS
            </div>
            <div
              style={{ fontSize: "16px", fontWeight: 900, color: "#1a1a1a" }}
            >
              {dayStats?.photoCount || 0}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Elevation Sparkline Component
function ElevationSparkline({
  data,
  currentIndex,
  height = 50,
  fillHeight = false,
  accentColor = "#dc2626",
}) {
  if (!data?.length) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;

  // For fillHeight mode, use percentage-based viewBox
  const viewBoxHeight = fillHeight ? 100 : height;

  // Generate SVG path (normalized to 0-100 for both axes)
  const points = data
    .map((val, i) => {
      const x = (i / (data.length - 1)) * 100;
      const y = viewBoxHeight - ((val - min) / range) * (viewBoxHeight - 4) - 2;
      return `${x},${y}`;
    })
    .join(" ");

  // Calculate position for marker - must match the line's y formula exactly
  const markerLeftPercent =
    data.length > 1 ? (currentIndex / (data.length - 1)) * 100 : 50;
  // Line y formula: viewBoxHeight - ((val - min) / range) * (viewBoxHeight - 4) - 2
  // Convert to percentage of viewBoxHeight for CSS positioning
  const markerTopPercent =
    data[currentIndex] != null
      ? ((viewBoxHeight -
          ((data[currentIndex] - min) / range) * (viewBoxHeight - 4) -
          2) /
          viewBoxHeight) *
        100
      : 50;

  const containerStyle = fillHeight
    ? {
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
      }
    : {};

  const svgContainerStyle = fillHeight
    ? { flexGrow: 1, position: "relative", minHeight: 0 }
    : { position: "relative", height };

  return (
    <div style={containerStyle}>
      {/* Min/Max labels row */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: "4px",
          fontSize: "9px",
          fontFamily: "monospace",
          fontWeight: 600,
          color: "#9ca3af",
        }}
      >
        <span>↓ {Math.round(min)}m</span>
        <span>↑ {Math.round(max)}m</span>
      </div>
      <div style={svgContainerStyle}>
        <svg
          width="100%"
          height="100%"
          viewBox={`0 0 100 ${viewBoxHeight}`}
          preserveAspectRatio={fillHeight ? "none" : "xMidYMid meet"}
          style={{
            display: "block",
            position: fillHeight ? "absolute" : "relative",
            inset: fillHeight ? 0 : "auto",
          }}
        >
          {/* Baseline */}
          <line
            x1="0"
            y1={viewBoxHeight - 1}
            x2="100"
            y2={viewBoxHeight - 1}
            stroke="#e5e7eb"
            strokeWidth="1"
            vectorEffect="non-scaling-stroke"
          />
          {/* Profile line - heavy stroke to match grid borders */}
          <polyline
            points={points}
            fill="none"
            stroke="#1a1a1a"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
        {/* Position marker - absolute positioned div for true circle */}
        <div
          style={{
            position: "absolute",
            left: `${markerLeftPercent}%`,
            top: `${markerTopPercent}%`,
            transform: "translate(-50%, -50%)",
            width: "10px",
            height: "10px",
            borderRadius: "50%",
            background: accentColor,
            border: "2px solid white",
            boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
          }}
        />
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
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((p1.lat * Math.PI) / 180) *
      Math.cos((p2.lat * Math.PI) / 180) *
      Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// Highlights Grid Component
function HighlightsGrid({ highlights, dayColor, isMobile }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: isMobile ? "1fr 1fr" : "1fr",
        gap: isMobile ? "8px" : "12px",
      }}
    >
      {highlights.map((h, idx) => (
        <div
          key={h.id || idx}
          style={{
            display: "flex",
            flexDirection: "column",
            padding: isMobile ? "10px" : "12px",
            background: "#fafafa",
            transition: "background 0.15s",
          }}
        >
          {/* Icon/Image */}
          <div
            style={{
              width: "100%",
              aspectRatio: "1.5",
              background: h.image
                ? "transparent"
                : `linear-gradient(135deg, ${dayColor}22, ${dayColor}44)`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: isMobile ? "28px" : "32px",
              overflow: "hidden",
              marginBottom: isMobile ? "8px" : "10px",
            }}
          >
            {h.image ? (
              <img
                src={h.image.startsWith("/") ? h.image : `/${h.image}`}
                alt=""
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                }}
              />
            ) : (
              HIGHLIGHT_ICONS[h.type] || "●"
            )}
          </div>

          {/* Title */}
          <div
            style={{
              fontSize: isMobile ? "13px" : "14px",
              fontWeight: 600,
              color: "#1a1a1a",
              marginBottom: "4px",
            }}
          >
            {h.title}
          </div>

          {/* Comment */}
          {h.comment && (
            <div
              style={{
                fontSize: isMobile ? "11px" : "12px",
                color: "#6b7280",
                lineHeight: 1.4,
              }}
            >
              {h.comment}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export default DayDetailPage;
