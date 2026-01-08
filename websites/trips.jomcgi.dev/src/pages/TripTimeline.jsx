import React, {
  useState,
  useRef,
  useEffect,
  useCallback,
  useMemo,
} from "react";
import { Link } from "wouter";
import {
  MapPin,
  Wind,
  Play,
  Pause,
  ChevronLeft,
  ChevronRight,
  Radio,
  Maximize2,
  Minimize2,
  Loader2,
  AlertCircle,
  Tag,
} from "lucide-react";

import { useTripContext } from "../contexts/TripContext";
import { useWeather } from "../hooks/useWeather";
import { useMediaQuery } from "../hooks/useMediaQuery";
import { useUrlState } from "../hooks/useUrlState";
import { useFavicon } from "../hooks/useFavicon";
import { usePageTitle } from "../hooks/usePageTitle";

import { TripMap } from "../components/map/TripMap";
import { ImagePanel } from "../components/image/ImagePanel";
import { FullscreenModal } from "../components/timeline/FullscreenModal";
import { ViewToggle } from "../components/common/ViewToggle";
import { LiveBadge } from "../components/common/LiveBadge";
import { TagFilter } from "../components/common/TagFilter";

import { LIVE_FEATURES_ENABLED } from "../constants/api";
import { getWeatherDescription } from "../constants/colors";
import { getThumbUrl, getDisplayUrl } from "../utils/images";

export function TripTimeline() {
  const {
    tripSlug,
    tripConfig,
    tripData,
    mapPoints,
    dayBoundaries,
    availableTags,
    loading,
    error,
    stats,
    cachedImages,
    prefetchImage,
  } = useTripContext();

  // Set favicon to hollow ring (overview mode)
  useFavicon("summary");

  // Set page title
  const shortTitle = tripConfig?.trip?.short_title;
  usePageTitle(shortTitle, "Timeline");

  const { getInitialFrame, getInitialTags, updateUrl } = useUrlState();

  // Tag filter state
  const [selectedTags, setSelectedTags] = useState(() => getInitialTags());

  // Filter trip data by selected tags
  const filteredTripData = useMemo(() => {
    if (selectedTags.length === 0) return tripData;
    return tripData.filter((point) =>
      point.tags?.some((t) => selectedTags.includes(t.toLowerCase())),
    );
  }, [tripData, selectedTags]);

  // Get indices in tripData for filtered points
  const filteredIndices = useMemo(() => {
    if (selectedTags.length === 0) return null;
    const indices = [];
    tripData.forEach((point, idx) => {
      if (point.tags?.some((t) => selectedTags.includes(t.toLowerCase()))) {
        indices.push(idx);
      }
    });
    return indices;
  }, [tripData, selectedTags]);

  // Navigation helpers for tag-constrained movement
  const getNextFilteredIndex = useCallback(
    (currentIdx) => {
      if (!filteredIndices)
        return Math.min(tripData.length - 1, currentIdx + 1);
      const nextIdx = filteredIndices.find((i) => i > currentIdx);
      return nextIdx !== undefined ? nextIdx : currentIdx;
    },
    [filteredIndices, tripData.length],
  );

  const getPrevFilteredIndex = useCallback(
    (currentIdx) => {
      if (!filteredIndices) return Math.max(0, currentIdx - 1);
      for (let i = filteredIndices.length - 1; i >= 0; i--) {
        if (filteredIndices[i] < currentIdx) return filteredIndices[i];
      }
      return currentIdx;
    },
    [filteredIndices],
  );

  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  // Track if we're at the initial default view (zoomed out map)
  const [isInitialDefaultView, setIsInitialDefaultView] = useState(false);

  const canGoPrev = useMemo(() => {
    if (!filteredIndices) return selectedIndex > 0;
    return filteredIndices.some((i) => i < selectedIndex);
  }, [filteredIndices, selectedIndex]);

  const canGoNext = useMemo(() => {
    if (!filteredIndices) return selectedIndex < tripData.length - 1;
    return filteredIndices.some((i) => i > selectedIndex);
  }, [filteredIndices, selectedIndex, tripData.length]);

  const [playbackSpeed, setPlaybackSpeed] = useState(10);
  const [isLive, setIsLive] = useState(false);
  const [mapExpanded, setMapExpanded] = useState(false);
  const [mobileView, setMobileView] = useState("image");
  const [scrollVisibleCenter, setScrollVisibleCenter] = useState(0);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const scrollRef = useRef(null);
  const imageRefs = useRef({});

  const isMobile = useMediaQuery("(max-width: 768px)");
  const isTablet = useMediaQuery("(max-width: 1024px)");

  const initializedRef = useRef(false);

  // Initialize selected index from URL, config default_image, or latest
  useEffect(() => {
    if (tripData.length > 0 && !initializedRef.current) {
      initializedRef.current = true;
      const urlFrame = getInitialFrame();

      if (urlFrame !== null && urlFrame < tripData.length) {
        // URL frame takes priority
        setSelectedIndex(urlFrame);
      } else if (tripConfig?.timeline?.default_image) {
        // Look for default_image from config
        const defaultImageId = tripConfig.timeline.default_image;
        const defaultIndex = tripData.findIndex(
          (p) => p.id === defaultImageId || p.image?.includes(defaultImageId),
        );
        if (defaultIndex !== -1) {
          setSelectedIndex(defaultIndex);
          setIsInitialDefaultView(true); // Enable zoomed-out map view
        } else {
          setSelectedIndex(tripData.length - 1);
        }
      } else {
        setSelectedIndex(tripData.length - 1);
      }
    }
  }, [tripData.length, tripConfig, getInitialFrame]);

  // Sync URL with current frame and tags
  useEffect(() => {
    if (tripData.length === 0) return;
    updateUrl(selectedIndex, selectedTags);
  }, [selectedIndex, selectedTags, tripData.length, updateUrl]);

  // Jump to first filtered image when tags are applied
  useEffect(() => {
    if (filteredIndices && filteredIndices.length > 0) {
      if (!filteredIndices.includes(selectedIndex)) {
        setSelectedIndex(filteredIndices[0]);
        setIsLive(false);
        setIsPlaying(false);
      }
    }
  }, [filteredIndices]);

  const selectedPoint = tripData[selectedIndex];
  const selectedId = selectedPoint?.id;

  const currentDay = useMemo(() => {
    if (dayBoundaries.length === 0) return 1;
    for (let i = dayBoundaries.length - 1; i >= 0; i--) {
      if (dayBoundaries[i].index <= selectedIndex) {
        return dayBoundaries[i].dayNumber;
      }
    }
    return 1;
  }, [dayBoundaries, selectedIndex]);

  const latestIndex = tripData.length - 1;
  const latestPoint = tripData[latestIndex];

  const { weather } = useWeather(latestPoint?.lat, latestPoint?.lng);

  useEffect(() => {
    if (isLive && tripData.length > 0) {
      setSelectedIndex(latestIndex);
      setIsPlaying(false);
    }
  }, [isLive, latestIndex, tripData.length]);

  // Prefetch images ahead during playback
  useEffect(() => {
    if (!isPlaying || isLive || tripData.length === 0) return;

    const prefetchCount = Math.min(Math.ceil(playbackSpeed / 2) + 3, 20);

    for (let i = 1; i <= prefetchCount; i++) {
      const idx = selectedIndex + i;
      if (idx < tripData.length && tripData[idx]?.image) {
        prefetchImage(getDisplayUrl(tripData[idx].image));
      }
    }
  }, [
    isPlaying,
    selectedIndex,
    playbackSpeed,
    isLive,
    tripData,
    prefetchImage,
  ]);

  // Playback timer
  useEffect(() => {
    let interval;
    if (isPlaying && !isLive && tripData.length > 0) {
      interval = setInterval(() => {
        setSelectedIndex((prev) => {
          const nextIdx = getNextFilteredIndex(prev);

          if (nextIdx === prev) {
            setIsPlaying(false);
            return prev;
          }

          const nextPoint = tripData[nextIdx];
          if (nextPoint?.image) {
            const nextUrl = getDisplayUrl(nextPoint.image);
            if (!cachedImages.current.has(nextUrl)) {
              return prev;
            }
          }

          return nextIdx;
        });
      }, 1000 / playbackSpeed);
    }
    return () => clearInterval(interval);
  }, [
    isPlaying,
    playbackSpeed,
    isLive,
    tripData,
    getNextFilteredIndex,
    cachedImages,
  ]);

  // Continuous priority-based prefetching
  useEffect(() => {
    if (tripData.length === 0) return;

    const prefetchRadius = 10;

    for (let distance = 1; distance <= prefetchRadius; distance++) {
      const prevIdx = selectedIndex - distance;
      const nextIdx = selectedIndex + distance;

      if (prevIdx >= 0 && tripData[prevIdx]?.image) {
        prefetchImage(getDisplayUrl(tripData[prevIdx].image));
      }
      if (nextIdx < tripData.length && tripData[nextIdx]?.image) {
        prefetchImage(getDisplayUrl(tripData[nextIdx].image));
      }
    }
  }, [selectedIndex, tripData, prefetchImage]);

  // Scroll to selected thumbnail
  useEffect(() => {
    const el = imageRefs.current[selectedId];
    if (el)
      el.scrollIntoView({
        behavior: "smooth",
        inline: "center",
        block: "nearest",
      });
  }, [selectedId]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
      if (isLive || isFullscreen) return;

      if (e.key === "ArrowLeft") {
        e.preventDefault();
        setSelectedIndex((prev) => getPrevFilteredIndex(prev));
        setIsPlaying(false);
        setIsInitialDefaultView(false); // Clear zoomed-out state on navigation
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        setSelectedIndex((prev) => getNextFilteredIndex(prev));
        setIsPlaying(false);
        setIsInitialDefaultView(false); // Clear zoomed-out state on navigation
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isLive, isFullscreen, getPrevFilteredIndex, getNextFilteredIndex]);

  // Track scroll position for virtualization
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;

    const thumbWidth = isMobile ? 52 : 68;

    const handleScroll = () => {
      const scrollLeft = container.scrollLeft;
      const containerWidth = container.clientWidth;
      const centerScroll = scrollLeft + containerWidth / 2;
      const centerIndex = Math.floor(centerScroll / thumbWidth);
      setScrollVisibleCenter(centerIndex);
    };

    handleScroll();

    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => container.removeEventListener("scroll", handleScroll);
  }, [isMobile, tripData.length]);

  const handleMarkerClick = useCallback(
    (id) => {
      const idx = tripData.findIndex((p) => p.id === id);
      if (idx !== -1) {
        setSelectedIndex(idx);
        setIsPlaying(false);
        setIsInitialDefaultView(false); // Clear zoomed-out state on navigation
        if (idx !== latestIndex) {
          setIsLive(false);
        }
      }
    },
    [tripData, latestIndex],
  );

  const visibleRange = useMemo(() => {
    const buffer = 50;
    const preloadPadding = 30;

    const selectedStart = selectedIndex - buffer;
    const selectedEnd = selectedIndex + buffer;

    const scrollStart = scrollVisibleCenter - buffer;
    const scrollEnd = scrollVisibleCenter + buffer;

    const start = Math.max(
      0,
      Math.min(selectedStart, scrollStart) - preloadPadding,
    );
    const end = Math.min(
      tripData.length,
      Math.max(selectedEnd, scrollEnd) + preloadPadding,
    );

    return { start, end };
  }, [selectedIndex, scrollVisibleCenter, tripData.length]);

  if (loading) {
    return (
      <div className="h-dvh w-full bg-gray-50 text-gray-900 flex flex-col items-center justify-center gap-4">
        <Loader2 className="h-12 w-12 animate-spin text-blue-500" />
        <p className="text-gray-500">Loading trip data...</p>
      </div>
    );
  }

  if (tripData.length === 0) {
    return (
      <div className="h-dvh w-full bg-gray-50 text-gray-900 flex flex-col items-center justify-center gap-4">
        <AlertCircle className="h-12 w-12 text-amber-500" />
        <p className="text-gray-600">No trip data available</p>
        <p className="text-gray-500 text-sm">
          The trip hasn't started yet or data is unavailable.
        </p>
      </div>
    );
  }

  const showErrorBanner = !!error;

  const handleTimelineChange = (newIndex) => {
    setSelectedIndex(newIndex);
    setIsPlaying(false);
    setIsInitialDefaultView(false); // Clear zoomed-out state on navigation
    if (newIndex !== latestIndex) {
      setIsLive(false);
    }
  };

  const toggleLive = () => {
    setIsLive(!isLive);
  };

  const formatTime = (date) =>
    date.toLocaleDateString("en-CA", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "America/Vancouver",
    });

  const formatTimeShort = (date) =>
    date.toLocaleTimeString("en-CA", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "America/Vancouver",
    });

  return (
    <div className="h-dvh w-full bg-gray-50 text-gray-900 flex flex-col overflow-hidden">
      <style>{`
        @keyframes pulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.2); opacity: 0.8; }
        }
      `}</style>

      {/* Status Bar */}
      <div className="flex-none border-b border-gray-200 bg-white/80 backdrop-blur-sm px-4 py-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 md:gap-4">
            {/* Back button */}
            <Link
              href={`/${tripSlug}`}
              className="p-1.5 rounded hover:bg-gray-100 transition-colors text-gray-600 hover:text-gray-900"
              title="Back to summary"
            >
              <ChevronLeft className="h-5 w-5" />
            </Link>
            <div className="flex items-center gap-2">
              {LIVE_FEATURES_ENABLED && (
                <div
                  className={`h-2 w-2 rounded-full ${isLive ? "bg-red-500" : "bg-emerald-500"} animate-pulse`}
                />
              )}
              {!isMobile && (
                <span className="text-sm font-medium text-gray-900">
                  Winter Road Trip to Liard Hot Springs
                </span>
              )}
            </div>
            {LIVE_FEATURES_ENABLED && (
              <div className="bg-emerald-500/20 text-emerald-600 px-2 py-0.5 rounded text-xs font-medium flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
                Live Trip
              </div>
            )}
            {isMobile && (
              <ViewToggle
                activeView={mobileView}
                onViewChange={setMobileView}
              />
            )}
            {LIVE_FEATURES_ENABLED && (
              <LiveBadge
                isLive={isLive}
                onToggle={toggleLive}
                viewerCount={stats.viewers > 0 ? stats.viewers : null}
                compact={isMobile}
              />
            )}
            {isMobile && availableTags.length > 0 && (
              <TagFilter
                availableTags={availableTags}
                selectedTags={selectedTags}
                onTagsChange={setSelectedTags}
                isMobile={true}
              />
            )}
          </div>
          {!isMobile && availableTags.length > 0 && (
            <TagFilter
              availableTags={availableTags}
              selectedTags={selectedTags}
              onTagsChange={setSelectedTags}
              isMobile={false}
            />
          )}
          {LIVE_FEATURES_ENABLED && !isMobile && weather && (
            <div className="flex items-center gap-3 text-sm text-gray-600">
              <MapPin className="h-3 w-3 text-gray-400" />
              <span>{weather.temp}°C</span>
              {!isTablet && (
                <span>{getWeatherDescription(weather.symbol)}</span>
              )}
              <span className="flex items-center gap-1">
                <Wind className="h-3 w-3" />
                {weather.windSpeed} km/h
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Error Banner */}
      {showErrorBanner && (
        <div className="flex-none bg-amber-500/10 border-b border-amber-500/20 px-4 py-2">
          <div className="flex items-center gap-2 text-sm text-amber-600">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span>Unable to connect to API: {error}</span>
          </div>
        </div>
      )}

      {/* Main Content */}
      <div className="flex-1 flex min-h-0">
        {isMobile ? (
          <>
            <div
              className={`relative w-full ${mobileView === "map" ? "block" : "hidden"}`}
            >
              <TripMap
                points={mapPoints}
                selectablePoints={tripData}
                selectedId={selectedId}
                onMarkerClick={handleMarkerClick}
                isLive={isLive}
                skipInitialZoom={isInitialDefaultView}
                initialZoom={tripConfig?.timeline?.default_zoom}
              />

              <div className="absolute top-3 left-3 z-10">
                <div className="bg-white/90 border border-gray-200 rounded-lg p-3 backdrop-blur-sm shadow-sm">
                  <div className="text-xl font-bold text-gray-900">
                    {tripData.length.toLocaleString()}
                  </div>
                  <div className="text-xs text-gray-500">Photos</div>
                </div>
              </div>

              <div className="absolute bottom-3 left-3 z-10">
                <div className="bg-white/90 border border-gray-200 rounded-lg p-2 backdrop-blur-sm shadow-sm">
                  <div className="flex items-center gap-1.5 text-xs">
                    <div
                      className={`w-3 h-3 rounded-full border-2 border-white ${isLive ? "bg-red-500" : "bg-blue-500"}`}
                    />
                    <span className="text-gray-600">
                      {isLive ? "Live" : "Position"}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div
              className={`w-full ${mobileView === "image" ? "block" : "hidden"}`}
            >
              <ImagePanel
                point={selectedPoint}
                isLive={isLive}
                totalFrames={tripData.length}
                currentIndex={selectedIndex}
                currentDay={currentDay}
                totalDays={dayBoundaries.length}
                isMobile={isMobile}
                cachedImages={cachedImages}
                onImageClick={() => setIsFullscreen(true)}
                onPrev={
                  canGoPrev
                    ? () => {
                        setSelectedIndex(getPrevFilteredIndex(selectedIndex));
                        setIsPlaying(false);
                        setIsLive(false);
                        setIsInitialDefaultView(false);
                      }
                    : null
                }
                onNext={
                  canGoNext
                    ? () => {
                        const nextIdx = getNextFilteredIndex(selectedIndex);
                        setSelectedIndex(nextIdx);
                        setIsPlaying(false);
                        setIsInitialDefaultView(false);
                        if (nextIdx !== tripData.length - 1) setIsLive(false);
                      }
                    : null
                }
              />
            </div>
          </>
        ) : (
          <>
            <div
              className={`relative transition-all duration-300 ${mapExpanded ? "w-2/3" : "w-1/2"}`}
            >
              <TripMap
                points={mapPoints}
                selectablePoints={tripData}
                selectedId={selectedId}
                onMarkerClick={handleMarkerClick}
                isLive={isLive}
                skipInitialZoom={isInitialDefaultView}
                initialZoom={tripConfig?.timeline?.default_zoom}
              />

              <div className="absolute top-3 left-3 z-10">
                <div className="bg-white/90 border border-gray-200 rounded-lg p-3 backdrop-blur-sm shadow-sm">
                  <div className="text-xl font-bold text-gray-900">
                    {tripData.length.toLocaleString()}
                  </div>
                  <div className="text-xs text-gray-500">Photos</div>
                </div>
              </div>

              <div className="absolute bottom-3 left-3 z-10">
                <div className="bg-white/90 border border-gray-200 rounded-lg p-2 backdrop-blur-sm shadow-sm">
                  <div className="flex items-center gap-1.5 text-xs">
                    <div
                      className={`w-3 h-3 rounded-full border-2 border-white ${isLive ? "bg-red-500" : "bg-blue-500"}`}
                    />
                    <span className="text-gray-600">
                      {isLive ? "Live" : "Position"}
                    </span>
                  </div>
                </div>
              </div>

              <button
                onClick={() => setMapExpanded(!mapExpanded)}
                className="absolute top-3 right-14 z-10 p-2 bg-white/90 border border-gray-200 rounded-lg backdrop-blur-sm shadow-sm hover:bg-gray-100 transition-colors text-gray-700"
              >
                {mapExpanded ? (
                  <Minimize2 className="h-4 w-4" />
                ) : (
                  <Maximize2 className="h-4 w-4" />
                )}
              </button>
            </div>

            <div
              className={`w-px ${isLive ? "bg-red-500/30" : "bg-gray-200"}`}
            />

            <div
              className={`transition-all duration-300 ${mapExpanded ? "w-1/3" : "w-1/2"}`}
            >
              <ImagePanel
                point={selectedPoint}
                isLive={isLive}
                totalFrames={tripData.length}
                currentIndex={selectedIndex}
                currentDay={currentDay}
                totalDays={dayBoundaries.length}
                isMobile={isMobile}
                cachedImages={cachedImages}
                onImageClick={() => setIsFullscreen(true)}
              />
            </div>
          </>
        )}
      </div>

      {/* Fullscreen Image Modal */}
      {isFullscreen && selectedPoint?.image && (
        <FullscreenModal
          imageUrl={getDisplayUrl(selectedPoint.image)}
          onClose={() => setIsFullscreen(false)}
          onPrev={
            canGoPrev
              ? () => {
                  setSelectedIndex(getPrevFilteredIndex(selectedIndex));
                  setIsPlaying(false);
                  setIsLive(false);
                  setIsInitialDefaultView(false);
                }
              : null
          }
          onNext={
            canGoNext
              ? () => {
                  const nextIdx = getNextFilteredIndex(selectedIndex);
                  setSelectedIndex(nextIdx);
                  setIsPlaying(false);
                  setIsInitialDefaultView(false);
                  if (nextIdx !== tripData.length - 1) {
                    setIsLive(false);
                  }
                }
              : null
          }
        />
      )}

      {/* Timeline Controls */}
      <div
        className={`flex-none border-t bg-white/90 backdrop-blur-sm px-4 py-2 transition-colors ${
          isLive ? "border-red-500/30" : "border-gray-200"
        }`}
      >
        <div className="flex items-center gap-3">
          <div
            className={`flex items-center gap-1 ${isLive ? "opacity-50" : ""}`}
          >
            <button
              onClick={() =>
                handleTimelineChange(getPrevFilteredIndex(selectedIndex))
              }
              className={`${isMobile ? "p-2" : "p-1.5"} rounded hover:bg-gray-200 transition-colors disabled:opacity-30 text-gray-700`}
              disabled={!canGoPrev || isLive}
            >
              <ChevronLeft className={isMobile ? "h-5 w-5" : "h-4 w-4"} />
            </button>
            <button
              onClick={() => {
                setIsPlaying(!isPlaying);
                if (!isPlaying) setIsInitialDefaultView(false); // Clear zoomed-out state when starting playback
              }}
              className={`${isMobile ? "p-2" : "p-1.5"} rounded transition-colors ${isPlaying ? "bg-blue-500 text-white" : "hover:bg-gray-200 text-gray-700"}`}
              disabled={isLive}
            >
              {isPlaying ? (
                <Pause className={isMobile ? "h-5 w-5" : "h-4 w-4"} />
              ) : (
                <Play className={isMobile ? "h-5 w-5" : "h-4 w-4"} />
              )}
            </button>
            <button
              onClick={() =>
                handleTimelineChange(getNextFilteredIndex(selectedIndex))
              }
              className={`${isMobile ? "p-2" : "p-1.5"} rounded hover:bg-gray-200 transition-colors disabled:opacity-30 text-gray-700`}
              disabled={!canGoNext || isLive}
            >
              <ChevronRight className={isMobile ? "h-5 w-5" : "h-4 w-4"} />
            </button>
          </div>

          {!isMobile && (
            <select
              value={playbackSpeed}
              onChange={(e) => setPlaybackSpeed(Number(e.target.value))}
              className="bg-gray-100 border border-gray-300 rounded px-2 py-1 text-xs text-gray-700 disabled:opacity-50"
              disabled={isLive}
            >
              <option value={1}>1x</option>
              <option value={5}>5x</option>
              <option value={10}>10x</option>
              <option value={30}>30x</option>
            </select>
          )}

          {!isMobile && dayBoundaries.length > 1 && (
            <div
              className={`flex items-center gap-1 ${isLive ? "opacity-50" : ""}`}
            >
              <button
                onClick={() => {
                  const prevDay = dayBoundaries.find(
                    (d) => d.dayNumber === currentDay - 1,
                  );
                  if (prevDay) handleTimelineChange(prevDay.index);
                }}
                className="p-1 rounded hover:bg-gray-200 transition-colors disabled:opacity-30 text-gray-700"
                disabled={currentDay === 1 || isLive}
                title="Previous day"
              >
                <ChevronLeft className="h-3 w-3" />
              </button>
              <span className="text-xs text-gray-500 min-w-[45px] text-center font-medium">
                Day {currentDay}
              </span>
              <button
                onClick={() => {
                  const nextDay = dayBoundaries.find(
                    (d) => d.dayNumber === currentDay + 1,
                  );
                  if (nextDay) handleTimelineChange(nextDay.index);
                }}
                className="p-1 rounded hover:bg-gray-200 transition-colors disabled:opacity-30 text-gray-700"
                disabled={currentDay === dayBoundaries.length || isLive}
                title="Next day"
              >
                <ChevronRight className="h-3 w-3" />
              </button>
            </div>
          )}

          <div className="flex-1 relative">
            <input
              type="range"
              min={0}
              max={tripData.length - 1}
              value={selectedIndex}
              onChange={(e) => handleTimelineChange(Number(e.target.value))}
              className={`w-full ${isMobile ? "h-2" : "h-1.5"} bg-gray-200 rounded-lg appearance-none cursor-pointer ${
                isLive ? "accent-red-500 opacity-50" : "accent-blue-500"
              }`}
              disabled={isLive}
            />
          </div>

          <div
            className={`text-xs ${isMobile ? "min-w-[60px]" : "min-w-[100px]"} text-right`}
          >
            {isLive ? (
              <span className="text-red-500 flex items-center gap-1 justify-end">
                <Radio className="w-3 h-3 animate-pulse" />
                {!isMobile && "Live"}
              </span>
            ) : (
              <span className="text-gray-500">
                {selectedPoint &&
                  (isMobile
                    ? formatTimeShort(selectedPoint.timestamp)
                    : formatTime(selectedPoint.timestamp))}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Image Reel */}
      <div
        className={`flex-none border-t bg-gray-100 overflow-x-auto transition-colors ${
          isLive
            ? "border-red-500/30"
            : selectedTags.length > 0
              ? "border-blue-500/30"
              : "border-gray-200"
        }`}
        ref={scrollRef}
      >
        {selectedTags.length > 0 && (
          <div className="flex items-center gap-2 px-3 py-1 bg-blue-50 border-b border-blue-100 text-xs text-blue-600">
            <Tag className="w-3 h-3" />
            <span>
              Showing {filteredTripData.length} of {tripData.length} photos with
              tags: {selectedTags.join(", ")}
            </span>
          </div>
        )}
        <div
          className={`flex ${isMobile ? "gap-1 p-1.5" : "gap-1.5 p-2"}`}
          style={{ width: "max-content" }}
        >
          {selectedTags.length > 0 ? (
            filteredTripData.map((point) => {
              const isSelected = point.id === selectedId;
              const isLatest = point.id === tripData[latestIndex].id;
              return (
                <button
                  key={point.id}
                  ref={(el) => (imageRefs.current[point.id] = el)}
                  onClick={() => handleMarkerClick(point.id)}
                  className={`flex-none relative transition-all duration-150 origin-bottom ${
                    isSelected
                      ? "ring-2 ring-blue-500 ring-offset-1 ring-offset-zinc-950 scale-105 z-10"
                      : "hover:scale-150 hover:z-20 hover:ring-1 hover:ring-zinc-500"
                  }`}
                >
                  <div
                    className={`${isMobile ? "w-12 h-8" : "w-16 h-11"} rounded overflow-hidden flex items-center justify-center bg-gray-200`}
                  >
                    <img
                      src={getThumbUrl(point.image)}
                      alt=""
                      className="w-full h-full object-cover"
                      loading="lazy"
                      decoding="async"
                    />
                  </div>
                  {isLive && isLatest && (
                    <div className="absolute -top-1 -right-1 w-3 h-3 bg-red-500 rounded-full animate-pulse border border-gray-100" />
                  )}
                </button>
              );
            })
          ) : (
            <>
              <div
                style={{ width: visibleRange.start * (isMobile ? 52 : 68) }}
              />
              {tripData
                .slice(visibleRange.start, visibleRange.end)
                .map((point) => {
                  const isSelected = point.id === selectedId;
                  const isLatest = point.id === tripData[latestIndex].id;
                  const hasSelectedTag = point.tags?.some((t) =>
                    selectedTags.includes(t.toLowerCase()),
                  );
                  return (
                    <button
                      key={point.id}
                      ref={(el) => (imageRefs.current[point.id] = el)}
                      onClick={() => handleMarkerClick(point.id)}
                      className={`flex-none relative transition-all duration-150 origin-bottom ${
                        isSelected
                          ? isLive
                            ? "ring-2 ring-red-500 ring-offset-1 ring-offset-zinc-950 scale-105 z-10"
                            : "ring-2 ring-blue-500 ring-offset-1 ring-offset-zinc-950 scale-105 z-10"
                          : hasSelectedTag
                            ? "ring-1 ring-blue-400 hover:scale-150 hover:z-20"
                            : "hover:scale-150 hover:z-20 hover:ring-1 hover:ring-zinc-500"
                      }`}
                    >
                      <div
                        className={`${isMobile ? "w-12 h-8" : "w-16 h-11"} rounded overflow-hidden flex items-center justify-center bg-gray-200`}
                      >
                        <img
                          src={getThumbUrl(point.image)}
                          alt=""
                          className="w-full h-full object-cover"
                          loading="lazy"
                          decoding="async"
                        />
                      </div>
                      {isLive && isLatest && (
                        <div className="absolute -top-1 -right-1 w-3 h-3 bg-red-500 rounded-full animate-pulse border border-gray-100" />
                      )}
                    </button>
                  );
                })}
              <div
                style={{
                  width:
                    (tripData.length - visibleRange.end) * (isMobile ? 52 : 68),
                }}
              />
            </>
          )}
        </div>
      </div>
    </div>
  );
}
