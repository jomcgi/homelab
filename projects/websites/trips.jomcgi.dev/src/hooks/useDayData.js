import { useMemo } from "react";

const DEFAULT_DAY_COLORS = [
  "#2563eb",
  "#059669",
  "#d97706",
  "#dc2626",
  "#7c3aed",
  "#0891b2",
  "#ea580c",
  "#db2777",
  "#16a34a",
  "#0d9488",
  "#9333ea",
  "#0284c7",
];

// Calculate distance between points using Haversine formula
function calculateDistance(points) {
  if (!points || points.length < 2) return 0;
  const R = 6371; // Earth's radius in km
  let total = 0;
  for (let i = 0; i < points.length - 1; i++) {
    const p1 = points[i],
      p2 = points[i + 1];
    if (!p1.lat || !p2.lat) continue;
    const dLat = ((p2.lat - p1.lat) * Math.PI) / 180;
    const dLon = ((p2.lng - p1.lng) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos((p1.lat * Math.PI) / 180) *
        Math.cos((p2.lat * Math.PI) / 180) *
        Math.sin(dLon / 2) ** 2;
    total += R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }
  return Math.round(total);
}

// Group points by day and return array with day number
function groupPointsByDay(points) {
  const days = {};
  points.forEach((point) => {
    const ts = point.timestamp;
    const y = ts.getFullYear();
    const m = String(ts.getMonth() + 1).padStart(2, "0");
    const d = String(ts.getDate()).padStart(2, "0");
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
    }));
}

/**
 * Hook to extract and compute data for a specific day of a trip
 * @param {Array} rawTripData - All trip points including gaps
 * @param {Array} tripData - Deduplicated points with images
 * @param {Object} tripConfig - Trip configuration with days, highlights
 * @param {number} dayNumber - The day number to extract (1-indexed)
 * @returns {Object} Day-specific data and stats
 */
export function useDayData(rawTripData, tripData, tripConfig, dayNumber) {
  // Group all raw points by day to get route points for this day
  const allDays = useMemo(() => {
    if (!rawTripData?.length) return [];
    return groupPointsByDay(rawTripData);
  }, [rawTripData]);

  // Get total number of days
  const totalDays = allDays.length;

  // Get this day's route points (from raw data - includes all GPS points)
  const dayPoints = useMemo(() => {
    const day = allDays.find((d) => d.dayNumber === dayNumber);
    return day?.points || [];
  }, [allDays, dayNumber]);

  // Get this day's photos (from deduplicated tripData)
  const dayPhotos = useMemo(() => {
    if (!tripData?.length || !dayPoints.length) return [];

    const dayStart = dayPoints[0]?.timestamp;
    const dayEnd = dayPoints[dayPoints.length - 1]?.timestamp;
    if (!dayStart || !dayEnd) return [];

    // Get the date string for this day
    const dayDateStr = dayStart.toLocaleDateString("en-CA", {
      timeZone: "America/Vancouver",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });

    return tripData.filter((p) => {
      if (!p.image) return false;
      const pointDateStr = p.timestamp.toLocaleDateString("en-CA", {
        timeZone: "America/Vancouver",
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      });
      return pointDateStr === dayDateStr;
    });
  }, [tripData, dayPoints]);

  // Compute stats for this day
  const dayStats = useMemo(() => {
    if (!dayPoints.length) return null;

    const distance = calculateDistance(dayPoints);

    // Get elevations with noise filtering
    const NOISE_THRESHOLD = 5;
    const rawElevations = dayPoints
      .map((p) => p.elevation)
      .filter((e) => e != null);
    const hasElevation = rawElevations.length > 0;

    const validElevations = rawElevations.filter((e) => e > NOISE_THRESHOLD);
    const elevationFloor =
      validElevations.length > 0 ? Math.min(...validElevations) : 0;
    const elevations = rawElevations.map((e) =>
      e <= NOISE_THRESHOLD ? elevationFloor : e,
    );

    let ascent = 0;
    let descent = 0;
    const CHANGE_THRESHOLD = 5;

    if (hasElevation) {
      for (let i = 1; i < dayPoints.length; i++) {
        let prev = dayPoints[i - 1].elevation;
        let curr = dayPoints[i].elevation;
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
    }

    return {
      distance,
      ascent: Math.round(ascent),
      descent: Math.round(descent),
      maxElevation: elevations.length
        ? Math.round(Math.max(...elevations))
        : null,
      minElevation: elevations.length
        ? Math.round(Math.min(...elevations))
        : null,
      hasElevation,
      photoCount: dayPhotos.length,
      pointCount: dayPoints.length,
    };
  }, [dayPoints, dayPhotos]);

  // Get day config (label, notes) from tripConfig
  const dayConfig = useMemo(() => {
    return tripConfig?.days?.[dayNumber] || {};
  }, [tripConfig, dayNumber]);

  // Get day label
  const dayLabel = dayConfig.label || `Day ${dayNumber}`;

  // Get highlights for this day
  const dayHighlights = useMemo(() => {
    if (!tripConfig?.highlights) return [];
    return tripConfig.highlights.filter((h) => h.day === dayNumber);
  }, [tripConfig, dayNumber]);

  // Get the day's color
  const dayColor = useMemo(() => {
    const configColors = tripConfig?.colors;
    if (configColors && configColors[dayNumber - 1]) {
      return configColors[dayNumber - 1];
    }
    return DEFAULT_DAY_COLORS[(dayNumber - 1) % DEFAULT_DAY_COLORS.length];
  }, [tripConfig, dayNumber]);

  // Get the day's date
  const dayDate = useMemo(() => {
    if (!dayPoints.length) return null;
    return dayPoints[0].timestamp;
  }, [dayPoints]);

  // Bounds for the map
  const bounds = useMemo(() => {
    if (!dayPoints.length) return null;
    const lats = dayPoints.map((p) => p.lat).filter(Boolean);
    const lngs = dayPoints.map((p) => p.lng).filter(Boolean);
    if (!lats.length || !lngs.length) return null;
    return {
      minLat: Math.min(...lats),
      maxLat: Math.max(...lats),
      minLng: Math.min(...lngs),
      maxLng: Math.max(...lngs),
    };
  }, [dayPoints]);

  return {
    dayNumber,
    dayLabel,
    dayDate,
    dayColor,
    dayPoints,
    dayPhotos,
    dayStats,
    dayConfig,
    dayHighlights,
    bounds,
    totalDays,
    isValidDay: dayNumber >= 1 && dayNumber <= totalDays,
  };
}
