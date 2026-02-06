import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { DayNavigation } from "./DayNavigation";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";

// Wrapper to provide router context
function renderWithRouter(ui, { route = "/" } = {}) {
  const { hook } = memoryLocation({ path: route, static: true });
  return render(<Router hook={hook}>{ui}</Router>);
}

describe("DayNavigation", () => {
  const defaultProps = {
    tripSlug: "japan-2024",
    dayNumber: 3,
    totalDays: 7,
    dayLabel: "Tokyo Adventures",
    dayDate: new Date("2024-03-15"),
    dayColor: "#4f46e5",
  };

  it("renders Summary link pointing to trip page", () => {
    renderWithRouter(<DayNavigation {...defaultProps} />);

    const summaryLink = screen.getByRole("link", { name: /summary/i });
    expect(summaryLink).toHaveAttribute("href", "/japan-2024");
  });

  it("shows day number and total days", () => {
    renderWithRouter(<DayNavigation {...defaultProps} />);

    expect(screen.getByText(/day 3 of 7/i)).toBeInTheDocument();
  });

  it("displays the day label", () => {
    renderWithRouter(<DayNavigation {...defaultProps} />);

    expect(screen.getByText("Tokyo Adventures")).toBeInTheDocument();
  });

  it("formats and displays the date", () => {
    renderWithRouter(<DayNavigation {...defaultProps} />);

    // The date format is "Mar 14, 2024" (because of America/Vancouver timezone)
    expect(screen.getByText(/Mar \d+, 2024/)).toBeInTheDocument();
  });

  describe("navigation buttons", () => {
    it("enables Prev button when not on first day", () => {
      renderWithRouter(<DayNavigation {...defaultProps} dayNumber={3} />);

      const prevLink = screen.getByRole("link", { name: /prev/i });
      expect(prevLink).toHaveAttribute("href", "/japan-2024/day/2");
    });

    it("disables Prev button on first day", () => {
      renderWithRouter(<DayNavigation {...defaultProps} dayNumber={1} />);

      // When disabled, it's a span not a link
      const prevButton = screen.getByText(/prev/i);
      expect(prevButton.closest("a")).toBeNull();
    });

    it("enables Next button when not on last day", () => {
      renderWithRouter(<DayNavigation {...defaultProps} dayNumber={3} />);

      const nextLink = screen.getByRole("link", { name: /next/i });
      expect(nextLink).toHaveAttribute("href", "/japan-2024/day/4");
    });

    it("disables Next button on last day", () => {
      renderWithRouter(
        <DayNavigation {...defaultProps} dayNumber={7} totalDays={7} />,
      );

      // When disabled, it's a span not a link
      const nextButton = screen.getByText(/next/i);
      expect(nextButton.closest("a")).toBeNull();
    });
  });

  describe("mobile mode", () => {
    it("renders in mobile layout when isMobile is true", () => {
      renderWithRouter(<DayNavigation {...defaultProps} isMobile={true} />);

      // Component still renders all elements
      expect(screen.getByText("Tokyo Adventures")).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: /summary/i }),
      ).toBeInTheDocument();
    });
  });
});
