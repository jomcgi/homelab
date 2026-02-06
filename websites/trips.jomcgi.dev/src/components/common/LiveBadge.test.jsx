import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LiveBadge } from "./LiveBadge";

describe("LiveBadge", () => {
  describe("default mode", () => {
    it("shows 'Go Live' text when not live", () => {
      render(<LiveBadge isLive={false} onToggle={() => {}} />);

      expect(screen.getByText("Go Live")).toBeInTheDocument();
    });

    it("shows 'LIVE' text when live", () => {
      render(<LiveBadge isLive={true} onToggle={() => {}} />);

      expect(screen.getByText("LIVE")).toBeInTheDocument();
    });

    it("calls onToggle when clicked", async () => {
      const user = userEvent.setup();
      const handleToggle = vi.fn();

      render(<LiveBadge isLive={false} onToggle={handleToggle} />);

      await user.click(screen.getByRole("button"));

      expect(handleToggle).toHaveBeenCalled();
    });

    it("shows viewer count when live and viewerCount is provided", () => {
      render(<LiveBadge isLive={true} onToggle={() => {}} viewerCount={42} />);

      expect(screen.getByText("42")).toBeInTheDocument();
    });

    it("does not show viewer count when not live", () => {
      render(<LiveBadge isLive={false} onToggle={() => {}} viewerCount={42} />);

      expect(screen.queryByText("42")).not.toBeInTheDocument();
    });
  });

  describe("compact mode", () => {
    it("does not show text in compact mode when not live", () => {
      render(<LiveBadge isLive={false} onToggle={() => {}} compact={true} />);

      expect(screen.queryByText("Go Live")).not.toBeInTheDocument();
    });

    it("does not show text in compact mode when live", () => {
      render(<LiveBadge isLive={true} onToggle={() => {}} compact={true} />);

      expect(screen.queryByText("LIVE")).not.toBeInTheDocument();
    });

    it("shows correct title attribute in compact mode", () => {
      const { rerender } = render(
        <LiveBadge isLive={false} onToggle={() => {}} compact={true} />,
      );

      expect(screen.getByTitle("Go Live")).toBeInTheDocument();

      rerender(<LiveBadge isLive={true} onToggle={() => {}} compact={true} />);

      expect(screen.getByTitle("LIVE")).toBeInTheDocument();
    });

    it("calls onToggle when clicked in compact mode", async () => {
      const user = userEvent.setup();
      const handleToggle = vi.fn();

      render(
        <LiveBadge isLive={false} onToggle={handleToggle} compact={true} />,
      );

      await user.click(screen.getByRole("button"));

      expect(handleToggle).toHaveBeenCalled();
    });
  });
});
