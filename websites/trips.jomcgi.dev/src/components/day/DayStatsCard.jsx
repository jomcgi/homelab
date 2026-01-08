import React from "react";
import {
  Camera,
  Mountain,
  TrendingUp,
  TrendingDown,
  MapPin,
} from "lucide-react";

/**
 * Display day-specific statistics in a card layout
 */
export function DayStatsCard({ stats, dayColor, isMobile = false }) {
  if (!stats) return null;

  const {
    distance,
    ascent,
    descent,
    maxElevation,
    minElevation,
    hasElevation,
    photoCount,
    pointCount,
  } = stats;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: isMobile ? "20px" : "24px",
      }}
    >
      {/* Hero stat - Distance */}
      <div>
        <div
          style={{
            fontSize: isMobile ? "10px" : "11px",
            fontWeight: 600,
            fontFamily: "monospace",
            letterSpacing: "0.05em",
            color: "#9ca3af",
            textTransform: "uppercase",
            marginBottom: "4px",
          }}
        >
          Distance
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: "6px" }}>
          <span
            style={{
              fontSize: isMobile ? "42px" : "48px",
              fontWeight: 800,
              fontFamily: "system-ui, -apple-system, sans-serif",
              letterSpacing: "-0.03em",
              lineHeight: 1,
              color: "#1a1a1a",
            }}
          >
            {distance.toLocaleString()}
          </span>
          <span
            style={{
              fontSize: isMobile ? "18px" : "20px",
              fontWeight: 600,
              color: "#9ca3af",
            }}
          >
            km
          </span>
        </div>
      </div>

      {/* Secondary stats grid */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: isMobile ? "1fr 1fr" : "1fr 1fr",
          gap: isMobile ? "16px" : "20px",
        }}
      >
        {/* Elevation gain */}
        {hasElevation && (
          <StatItem
            icon={<TrendingUp size={16} />}
            label="Ascent"
            value={`+${ascent.toLocaleString()}`}
            unit="m"
            color="#059669"
            isMobile={isMobile}
          />
        )}

        {/* Elevation loss */}
        {hasElevation && (
          <StatItem
            icon={<TrendingDown size={16} />}
            label="Descent"
            value={`-${descent.toLocaleString()}`}
            unit="m"
            color="#dc2626"
            isMobile={isMobile}
          />
        )}

        {/* High point */}
        {hasElevation && maxElevation != null && (
          <StatItem
            icon={<Mountain size={16} />}
            label="High Point"
            value={maxElevation.toLocaleString()}
            unit="m"
            isMobile={isMobile}
          />
        )}

        {/* Low point */}
        {hasElevation && minElevation != null && (
          <StatItem
            icon={<MapPin size={16} />}
            label="Low Point"
            value={minElevation.toLocaleString()}
            unit="m"
            isMobile={isMobile}
          />
        )}

        {/* Photo count */}
        <StatItem
          icon={<Camera size={16} />}
          label="Photos"
          value={photoCount.toString()}
          isMobile={isMobile}
        />
      </div>
    </div>
  );
}

function StatItem({ icon, label, value, unit, color, isMobile }) {
  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "6px",
          marginBottom: "4px",
        }}
      >
        <span style={{ color: color || "#9ca3af" }}>{icon}</span>
        <span
          style={{
            fontSize: isMobile ? "9px" : "10px",
            fontWeight: 600,
            fontFamily: "monospace",
            letterSpacing: "0.05em",
            color: "#9ca3af",
            textTransform: "uppercase",
          }}
        >
          {label}
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: "3px" }}>
        <span
          style={{
            fontSize: isMobile ? "22px" : "24px",
            fontWeight: 700,
            fontFamily: "system-ui",
            letterSpacing: "-0.02em",
            color: color || "#1a1a1a",
          }}
        >
          {value}
        </span>
        {unit && (
          <span
            style={{
              fontSize: isMobile ? "13px" : "14px",
              fontWeight: 500,
              color: "#9ca3af",
            }}
          >
            {unit}
          </span>
        )}
      </div>
    </div>
  );
}
