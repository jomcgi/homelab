import React, {
  createContext,
  useContext,
  useMemo,
  useRef,
  useEffect,
  useCallback,
} from "react";
import { useTripData } from "../hooks/useTripData";
import { useTripConfig } from "../hooks/useTripConfig";
import { getDisplayUrl } from "../utils/images";

const TripContext = createContext(null);

export function TripProvider({ tripSlug, children }) {
  // Fetch trip data and config
  const {
    points: rawTripData,
    loading: dataLoading,
    error: dataError,
    stats,
  } = useTripData(tripSlug);
  const {
    config: tripConfig,
    loading: configLoading,
    error: configError,
  } = useTripConfig(tripSlug);

  // Combined loading/error states
  const loading = dataLoading || configLoading;
  const error = dataError || configError;

  // Prefetch cache shared across all views
  const cachedImages = useRef(new Set());

  // All points including gaps - used for map route rendering
  const mapPoints = useMemo(() => {
    return [...rawTripData].sort((a, b) => a.timestamp - b.timestamp);
  }, [rawTripData]);

  // Deduplicate images for timeline/thumbnails:
  // - Gap points (no image): excluded entirely
  // - "car" tagged images: keep only 1 per minute
  // - Other tags: keep ALL images
  const tripData = useMemo(() => {
    if (rawTripData.length === 0) return [];

    const pointsWithImages = rawTripData.filter((p) => p.image !== null);
    const carOnlyImages = [];
    const specialImages = [];

    for (const point of pointsWithImages) {
      const tags = point.tags?.map((t) => t.toLowerCase()) || [];
      const hasNonCarTag = tags.some((t) => t !== "car" && t !== "gap");

      if (hasNonCarTag) {
        specialImages.push(point);
      } else {
        carOnlyImages.push(point);
      }
    }

    // Apply 1-per-minute deduplication only to car images
    const byMinute = new Map();
    for (const point of carOnlyImages) {
      const minuteKey = point.timestamp.toISOString().slice(0, 16);
      const existing = byMinute.get(minuteKey);
      if (!existing || point.timestamp < existing.timestamp) {
        byMinute.set(minuteKey, point);
      }
    }

    const combined = [...Array.from(byMinute.values()), ...specialImages];
    return combined.sort((a, b) => a.timestamp - b.timestamp);
  }, [rawTripData]);

  // Extract all unique tags (excluding internal tags)
  const availableTags = useMemo(() => {
    const tagSet = new Set();
    const hiddenTags = ["gap"];
    for (const point of rawTripData) {
      if (point.tags) {
        for (const tag of point.tags) {
          const lowered = tag.toLowerCase();
          if (!hiddenTags.includes(lowered)) {
            tagSet.add(lowered);
          }
        }
      }
    }
    return Array.from(tagSet).sort();
  }, [rawTripData]);

  // Calculate day boundaries
  const dayBoundaries = useMemo(() => {
    if (tripData.length === 0) return [];

    const boundaries = [];
    let currentDate = null;

    tripData.forEach((point, index) => {
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
  }, [tripData]);

  // Prefetch helper
  const prefetchImage = useCallback((url) => {
    if (cachedImages.current.has(url)) return Promise.resolve();

    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        cachedImages.current.add(url);
        resolve();
      };
      img.onerror = () => {
        cachedImages.current.add(url);
        resolve();
      };
      img.src = url;
    });
  }, []);

  // Prefetch timeline images in background when data loads
  useEffect(() => {
    if (!loading && tripData.length > 0) {
      // Prefetch first 20 images for timeline
      tripData.slice(0, 20).forEach((p) => {
        if (p.image) {
          prefetchImage(getDisplayUrl(p.image));
        }
      });
    }
  }, [loading, tripData, prefetchImage]);

  const value = useMemo(
    () => ({
      tripSlug,
      tripConfig,
      rawTripData,
      tripData,
      mapPoints,
      dayBoundaries,
      availableTags,
      loading,
      error,
      stats,
      cachedImages,
      prefetchImage,
    }),
    [
      tripSlug,
      tripConfig,
      rawTripData,
      tripData,
      mapPoints,
      dayBoundaries,
      availableTags,
      loading,
      error,
      stats,
      prefetchImage,
    ],
  );

  return <TripContext.Provider value={value}>{children}</TripContext.Provider>;
}

export function useTripContext() {
  const context = useContext(TripContext);
  if (!context) {
    throw new Error("useTripContext must be used within a TripProvider");
  }
  return context;
}
