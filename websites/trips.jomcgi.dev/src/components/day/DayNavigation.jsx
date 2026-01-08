import React, { useState } from "react";
import { Link } from "wouter";
import { ChevronLeft, ChevronRight } from "lucide-react";

// Nav link with hover inversion
function NavLink({ href, disabled, children, style }) {
  const [hovered, setHovered] = useState(false);

  if (disabled) {
    return (
      <span
        style={{
          ...style,
          opacity: 0.4,
          cursor: "not-allowed",
          pointerEvents: "none",
        }}
      >
        {children}
      </span>
    );
  }

  return (
    <Link
      href={href}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        ...style,
        background: hovered ? "#1a1a1a" : "white",
        color: hovered ? "white" : "#1a1a1a",
        transition: "background 0.15s, color 0.15s",
      }}
    >
      {React.Children.map(children, (child) => {
        if (
          React.isValidElement(child) &&
          (child.type === ChevronLeft || child.type === ChevronRight)
        ) {
          return React.cloneElement(child, {
            color: hovered ? "white" : "#1a1a1a",
          });
        }
        return child;
      })}
    </Link>
  );
}

/**
 * Navigation component for the day detail page
 * Shows back to summary, day title, and prev/next day buttons
 */
export function DayNavigation({
  tripSlug,
  dayNumber,
  totalDays,
  dayLabel,
  dayDate,
  dayColor,
  isMobile = false,
}) {
  const hasPrev = dayNumber > 1;
  const hasNext = dayNumber < totalDays;

  const formattedDate = dayDate
    ? dayDate.toLocaleDateString("en-US", {
        timeZone: "America/Vancouver",
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    : "";

  const navButtonStyle = {
    display: "flex",
    alignItems: "center",
    gap: "4px",
    padding: isMobile ? "8px 12px" : "8px 14px",
    fontSize: isMobile ? "12px" : "13px",
    fontWeight: 600,
    color: "#1a1a1a",
    background: "white",
    border: "2px solid #1a1a1a",
    cursor: "pointer",
    textDecoration: "none",
    transition: "background 0.1s ease",
  };

  return (
    <nav
      style={{
        display: "flex",
        flexDirection: isMobile ? "column" : "row",
        justifyContent: "space-between",
        alignItems: isMobile ? "stretch" : "center",
        gap: isMobile ? "16px" : "20px",
        padding: isMobile ? "16px 0" : "20px 0",
        borderBottom: "2px solid #1a1a1a",
        marginBottom: isMobile ? "16px" : "24px",
      }}
    >
      {/* Back to Summary */}
      <NavLink href={`/${tripSlug}`} style={navButtonStyle}>
        <ChevronLeft size={16} />
        <span>Summary</span>
      </NavLink>

      {/* Day Title - Center */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "4px",
          flex: 1,
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontSize: isMobile ? "10px" : "11px",
            fontWeight: 500,
            fontFamily: "monospace",
            letterSpacing: "0.05em",
            color: "#9ca3af",
            textTransform: "uppercase",
          }}
        >
          Day {dayNumber} of {totalDays}
          {formattedDate && (
            <span style={{ marginLeft: "8px" }}>{formattedDate}</span>
          )}
        </div>
        <div
          style={{
            fontSize: isMobile ? "16px" : "18px",
            fontWeight: 700,
            color: "#1a1a1a",
            borderBottom: `3px solid ${dayColor}`,
            paddingBottom: "4px",
            letterSpacing: "0.02em",
          }}
        >
          {dayLabel}
        </div>
      </div>

      {/* Prev/Next Buttons */}
      <div
        style={{
          display: "flex",
          gap: "8px",
          justifyContent: isMobile ? "center" : "flex-end",
        }}
      >
        <NavLink
          href={`/${tripSlug}/day/${dayNumber - 1}`}
          disabled={!hasPrev}
          style={navButtonStyle}
        >
          <ChevronLeft size={16} />
          <span>Prev</span>
        </NavLink>

        <NavLink
          href={`/${tripSlug}/day/${dayNumber + 1}`}
          disabled={!hasNext}
          style={navButtonStyle}
        >
          <span>Next</span>
          <ChevronRight size={16} />
        </NavLink>
      </div>
    </nav>
  );
}
