import React, { useState, useEffect } from "react";
import { ChevronLeft, ChevronRight, Camera } from "lucide-react";
import { FullscreenModal } from "../timeline/FullscreenModal";
import { getDisplayUrl } from "../../utils/images";

/**
 * Single photo viewer with navigation - connects to map marker
 */
export function PhotoViewer({
  photos,
  currentIndex,
  onIndexChange,
  isMobile = false,
  showTime = true,
}) {
  const [showFullscreen, setShowFullscreen] = useState(false);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (showFullscreen) return; // Let modal handle its own keys
      if (e.key === "ArrowLeft") {
        onIndexChange(Math.max(0, currentIndex - 1));
      } else if (e.key === "ArrowRight") {
        onIndexChange(Math.min(photos.length - 1, currentIndex + 1));
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [currentIndex, photos.length, onIndexChange, showFullscreen]);

  if (!photos || photos.length === 0) {
    return (
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: isMobile ? "32px 16px" : "48px 24px",
          background: "#fafafa",
          border: "2px solid #e5e7eb",
          minHeight: isMobile ? "200px" : "300px",
        }}
      >
        <Camera
          size={isMobile ? 36 : 48}
          style={{ color: "#9ca3af", marginBottom: "12px" }}
        />
        <p
          style={{
            fontSize: isMobile ? "12px" : "13px",
            fontWeight: 600,
            fontFamily: "monospace",
            color: "#6b7280",
            textTransform: "uppercase",
            letterSpacing: "0.05em",
          }}
        >
          No photos
        </p>
      </div>
    );
  }

  const photo = photos[currentIndex];
  const hasPrev = currentIndex > 0;
  const hasNext = currentIndex < photos.length - 1;

  const formatTime = (timestamp) => {
    if (!timestamp) return "";
    return timestamp.toLocaleTimeString("en-US", {
      timeZone: "America/Vancouver",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  };

  const navButtonStyle = {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    width: isMobile ? "40px" : "44px",
    height: isMobile ? "40px" : "44px",
    background: "white",
    border: "2px solid #1a1a1a",
    cursor: "pointer",
    transition: "background 0.1s ease",
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: isMobile ? "8px" : "12px",
      }}
    >
      {/* Photo container - flush left */}
      <div
        style={{
          position: "relative",
          display: "flex",
          justifyContent: "flex-start",
          alignItems: "flex-start",
          minHeight: isMobile ? "250px" : "380px",
        }}
      >
        {/* Photo */}
        <img
          src={getDisplayUrl(photo.image)}
          alt={`Photo ${currentIndex + 1}`}
          onClick={() => setShowFullscreen(true)}
          style={{
            maxWidth: "100%",
            maxHeight: isMobile ? "400px" : "480px",
            objectFit: "contain",
            cursor: "pointer",
          }}
        />
      </div>

      {/* Navigation row - clustered left under photo */}
      <div
        style={{
          display: "flex",
          justifyContent: "flex-start",
          alignItems: "center",
          gap: isMobile ? "12px" : "16px",
          paddingTop: isMobile ? "12px" : "16px",
          borderTop: "2px solid #1a1a1a",
        }}
      >
        {/* Prev button */}
        <button
          onClick={() => hasPrev && onIndexChange(currentIndex - 1)}
          style={{
            ...navButtonStyle,
            opacity: hasPrev ? 1 : 0.3,
            cursor: hasPrev ? "pointer" : "not-allowed",
          }}
          disabled={!hasPrev}
        >
          <ChevronLeft size={20} color="#1a1a1a" />
        </button>

        {/* Counter + Time */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: isMobile ? "12px" : "16px",
            minWidth: isMobile ? "80px" : "100px",
            justifyContent: "center",
          }}
        >
          <span
            style={{
              fontSize: isMobile ? "11px" : "12px",
              fontFamily: "monospace",
              fontWeight: 600,
              color: "#6b7280",
              letterSpacing: "0.02em",
            }}
          >
            {currentIndex + 1} / {photos.length}
          </span>
          {showTime && photo.timestamp && (
            <span
              style={{
                fontSize: isMobile ? "11px" : "12px",
                fontFamily: "monospace",
                fontWeight: 700,
                color: "#1a1a1a",
              }}
            >
              {formatTime(photo.timestamp)}
            </span>
          )}
        </div>

        {/* Next button */}
        <button
          onClick={() => hasNext && onIndexChange(currentIndex + 1)}
          style={{
            ...navButtonStyle,
            opacity: hasNext ? 1 : 0.3,
            cursor: hasNext ? "pointer" : "not-allowed",
          }}
          disabled={!hasNext}
        >
          <ChevronRight size={20} color="#1a1a1a" />
        </button>
      </div>

      {/* Fullscreen modal */}
      {showFullscreen && (
        <FullscreenModal
          imageUrl={getDisplayUrl(photo.image)}
          onClose={() => setShowFullscreen(false)}
          onPrev={hasPrev ? () => onIndexChange(currentIndex - 1) : undefined}
          onNext={hasNext ? () => onIndexChange(currentIndex + 1) : undefined}
        />
      )}
    </div>
  );
}
