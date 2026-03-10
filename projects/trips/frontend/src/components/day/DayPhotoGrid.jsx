import React, { useState } from "react";
import { Camera } from "lucide-react";
import { FullscreenModal } from "../timeline/FullscreenModal";
import { getThumbUrl, getDisplayUrl } from "../../utils/images";

/**
 * Photo grid component for displaying day photos with fullscreen modal
 */
export function DayPhotoGrid({ photos, isMobile = false, columns }) {
  const [selectedIndex, setSelectedIndex] = useState(null);

  // Default columns: 2 on mobile, 4 on desktop (or use explicit prop)
  const gridColumns = columns || (isMobile ? 2 : 4);

  if (!photos || photos.length === 0) {
    return (
      <div
        style={{
          padding: isMobile ? "32px 16px" : "48px 24px",
          textAlign: "center",
          background: "#f9fafb",
          border: "1px dashed #e5e7eb",
        }}
      >
        <Camera
          size={isMobile ? 36 : 48}
          style={{
            color: "#d1d5db",
            margin: "0 auto 12px",
          }}
        />
        <p
          style={{
            fontSize: isMobile ? "14px" : "15px",
            fontWeight: 500,
            color: "#6b7280",
            marginBottom: "4px",
          }}
        >
          No photos captured on this day
        </p>
        <p
          style={{
            fontSize: isMobile ? "12px" : "13px",
            color: "#9ca3af",
          }}
        >
          Check the map to see the route
        </p>
      </div>
    );
  }

  const handlePhotoClick = (index) => {
    setSelectedIndex(index);
  };

  const handleClose = () => {
    setSelectedIndex(null);
  };

  const handlePrev = () => {
    setSelectedIndex((prev) => (prev > 0 ? prev - 1 : photos.length - 1));
  };

  const handleNext = () => {
    setSelectedIndex((prev) => (prev < photos.length - 1 ? prev + 1 : 0));
  };

  // Format time from timestamp
  const formatTime = (timestamp) => {
    if (!timestamp) return "";
    return timestamp.toLocaleTimeString("en-US", {
      timeZone: "America/Vancouver",
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  };

  return (
    <>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${gridColumns}, 1fr)`,
          gap: isMobile ? "8px" : "12px",
        }}
      >
        {photos.map((photo, index) => (
          <div
            key={photo.id || index}
            onClick={() => handlePhotoClick(index)}
            style={{
              position: "relative",
              aspectRatio: "1",
              overflow: "hidden",
              cursor: "pointer",
              background: "#f3f4f6",
            }}
          >
            <img
              src={getThumbUrl(photo.image)}
              alt={`Photo ${index + 1}`}
              loading="lazy"
              style={{
                width: "100%",
                height: "100%",
                objectFit: "cover",
                transition: "transform 0.2s ease",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "scale(1.05)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "scale(1)";
              }}
            />

            {/* Time overlay */}
            {photo.timestamp && (
              <div
                style={{
                  position: "absolute",
                  bottom: "0",
                  left: "0",
                  right: "0",
                  padding: isMobile ? "4px 6px" : "6px 8px",
                  background: "linear-gradient(transparent, rgba(0,0,0,0.6))",
                  color: "white",
                  fontSize: isMobile ? "10px" : "11px",
                  fontWeight: 500,
                  fontFamily: "monospace",
                }}
              >
                {formatTime(photo.timestamp)}
              </div>
            )}

            {/* Tags overlay */}
            {photo.tags &&
              photo.tags.length > 0 &&
              photo.tags.some((t) => t.toLowerCase() !== "car") && (
                <div
                  style={{
                    position: "absolute",
                    top: "6px",
                    right: "6px",
                    display: "flex",
                    gap: "4px",
                    flexWrap: "wrap",
                    justifyContent: "flex-end",
                  }}
                >
                  {photo.tags
                    .filter((t) => t.toLowerCase() !== "car")
                    .slice(0, 2)
                    .map((tag, i) => (
                      <span
                        key={i}
                        style={{
                          background: "rgba(255,255,255,0.9)",
                          color: "#1a1a1a",
                          fontSize: isMobile ? "8px" : "9px",
                          fontWeight: 600,
                          fontFamily: "monospace",
                          padding: "2px 6px",
                          textTransform: "uppercase",
                          letterSpacing: "0.02em",
                        }}
                      >
                        {tag}
                      </span>
                    ))}
                </div>
              )}
          </div>
        ))}
      </div>

      {/* Photo count */}
      <div
        style={{
          marginTop: isMobile ? "12px" : "16px",
          textAlign: "center",
          fontSize: isMobile ? "11px" : "12px",
          color: "#9ca3af",
        }}
      >
        {photos.length} photo{photos.length !== 1 ? "s" : ""}
      </div>

      {/* Fullscreen Modal */}
      {selectedIndex !== null && (
        <FullscreenModal
          imageUrl={getDisplayUrl(photos[selectedIndex].image)}
          onClose={handleClose}
          onPrev={photos.length > 1 ? handlePrev : undefined}
          onNext={photos.length > 1 ? handleNext : undefined}
        />
      )}
    </>
  );
}
