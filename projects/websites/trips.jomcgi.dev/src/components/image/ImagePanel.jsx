import React, { useState, useRef, useEffect } from "react";
import { Camera, Tag } from "lucide-react";
import { getDisplayUrl } from "../../utils/images";

export function ImagePanel({
  point,
  isLive,
  totalFrames,
  currentIndex,
  currentDay = 1,
  totalDays = 1,
  isMobile = false,
  cachedImages = null,
  onImageClick = null,
  onPrev = null,
  onNext = null,
}) {
  const [currentImageUrl, setCurrentImageUrl] = useState(null);
  const [previousImageUrl, setPreviousImageUrl] = useState(null);
  const touchStartX = useRef(null);
  const touchStartY = useRef(null);

  const handleTouchStart = (e) => {
    touchStartX.current = e.touches[0].clientX;
    touchStartY.current = e.touches[0].clientY;
  };

  const handleTouchEnd = (e) => {
    if (touchStartX.current === null || isLive) return;

    const touchEndX = e.changedTouches[0].clientX;
    const touchEndY = e.changedTouches[0].clientY;
    const deltaX = touchEndX - touchStartX.current;
    const deltaY = touchEndY - touchStartY.current;

    const minSwipeDistance = 50;
    if (
      Math.abs(deltaX) > Math.abs(deltaY) &&
      Math.abs(deltaX) > minSwipeDistance
    ) {
      if (deltaX > 0 && onPrev) {
        onPrev();
      } else if (deltaX < 0 && onNext) {
        onNext();
      }
    }

    touchStartX.current = null;
    touchStartY.current = null;
  };

  useEffect(() => {
    if (!point?.image) {
      setCurrentImageUrl(null);
      setPreviousImageUrl(null);
      return;
    }

    const displayUrl = getDisplayUrl(point.image);

    if (displayUrl === currentImageUrl) {
      return;
    }

    const swapImages = (newUrl) => {
      setPreviousImageUrl(currentImageUrl);
      setCurrentImageUrl(newUrl);
    };

    if (cachedImages?.current?.has(displayUrl)) {
      swapImages(displayUrl);
      return;
    }

    const img = new Image();
    img.onload = () => {
      cachedImages?.current?.add(displayUrl);
      swapImages(displayUrl);
    };
    img.onerror = () => {
      swapImages(displayUrl);
    };
    img.src = displayUrl;
  }, [point?.image, currentImageUrl, cachedImages]);

  const formatTime = (date) =>
    date.toLocaleDateString("en-CA", {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "America/Vancouver",
    });

  if (!point) return null;

  const iconSize = isMobile ? "h-12 w-12" : "h-16 w-16";

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Header */}
      <div
        className={`flex-none px-4 py-3 border-b ${isLive ? "border-red-500/30 bg-red-500/5" : "border-gray-200"}`}
      >
        <div className="flex items-center justify-between">
          <div>
            {isLive && (
              <div className="flex items-center gap-2 mb-1">
                <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
                <span className="text-xs font-medium text-red-600">
                  LIVE VIEW
                </span>
              </div>
            )}
            <a
              href={`https://www.google.com/maps?q=${point.lat},${point.lng}`}
              target="_blank"
              rel="noopener noreferrer"
              className="font-semibold text-lg text-gray-900 hover:text-blue-600 transition-colors"
            >
              {Math.abs(point.lat).toFixed(2)}°{point.lat >= 0 ? "N" : "S"},{" "}
              {Math.abs(point.lng).toFixed(2)}°{point.lng >= 0 ? "E" : "W"} ↗
            </a>
            <p className="text-sm text-gray-500">
              {formatTime(point.timestamp)}
            </p>
          </div>
          <span className="text-xs text-gray-500 bg-gray-100 px-2 py-1 rounded">
            {point.source}
          </span>
        </div>
      </div>

      {/* Main Image Area */}
      <div
        className="flex-1 relative min-h-0 p-4"
        onTouchStart={isMobile ? handleTouchStart : undefined}
        onTouchEnd={isMobile ? handleTouchEnd : undefined}
      >
        <div
          className={`w-full h-full rounded-lg overflow-hidden flex items-center justify-center bg-gray-900 ${isLive ? "ring-2 ring-red-500/30" : ""}`}
        >
          {currentImageUrl ? (
            <div className="relative w-full h-full flex items-center justify-center">
              {previousImageUrl && (
                <img
                  src={previousImageUrl}
                  alt=""
                  className="absolute inset-0 w-full h-full object-contain"
                  decoding="async"
                />
              )}
              <img
                src={currentImageUrl}
                alt="Trip photo"
                className="absolute inset-0 w-full h-full object-contain cursor-pointer hover:opacity-90"
                onClick={() => onImageClick?.(currentImageUrl)}
                title="Click to view fullscreen"
                fetchPriority="high"
                decoding="async"
              />
            </div>
          ) : point.image ? (
            <div className="text-center">
              <Camera
                className={`${iconSize} mx-auto mb-3 animate-pulse ${isLive ? "text-red-500/40" : "text-gray-600"}`}
              />
              <p className="text-gray-500 text-sm font-mono">Loading...</p>
            </div>
          ) : (
            <div className="text-center">
              <Camera
                className={`${iconSize} mx-auto mb-3 ${isLive ? "text-red-500/40" : "text-gray-600"}`}
              />
              <p className="text-gray-500 text-sm font-mono">No image</p>
            </div>
          )}
        </div>

        {isLive && (
          <div className="absolute top-6 left-6 flex items-center gap-2 bg-red-500/90 text-white px-3 py-1.5 rounded-full text-sm font-medium">
            <span className="w-2 h-2 rounded-full bg-white animate-pulse" />
            LIVE
          </div>
        )}
      </div>

      {/* Metadata Footer */}
      <div className="flex-none px-4 py-3 border-t border-gray-200 bg-gray-50">
        <div
          className={`grid ${isMobile ? "grid-cols-2" : "grid-cols-3"} gap-4 text-sm text-gray-900`}
        >
          <div>
            <span className="text-gray-500 block text-xs mb-0.5">
              Coordinates
            </span>
            <span className="font-mono">
              {point.lat.toFixed(4)}, {point.lng.toFixed(4)}
            </span>
          </div>
          <div>
            <span className="text-gray-500 block text-xs mb-0.5">Day</span>
            <span>
              {currentDay} of {totalDays}
            </span>
          </div>
          {!isMobile && (
            <div>
              <span className="text-gray-500 block text-xs mb-0.5">Frame</span>
              <span className="font-mono">
                {currentIndex + 1} / {totalFrames}
              </span>
            </div>
          )}
        </div>
        {point.tags &&
          point.tags.filter((t) => t.toLowerCase() !== "gap").length > 0 && (
            <div className="mt-2 pt-2 border-t border-gray-200">
              <div className="flex items-center gap-2 flex-wrap">
                <Tag className="w-3 h-3 text-gray-400" />
                {point.tags
                  .filter((t) => t.toLowerCase() !== "gap")
                  .map((tag) => (
                    <span
                      key={tag}
                      className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full text-xs font-medium"
                    >
                      {tag}
                    </span>
                  ))}
              </div>
            </div>
          )}
      </div>
    </div>
  );
}
