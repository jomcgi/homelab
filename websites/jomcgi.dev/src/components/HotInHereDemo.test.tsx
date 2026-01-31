import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import HotInHereDemo from "./HotInHereDemo";

describe("HotInHereDemo", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("entry screen", () => {
    it("shows Enter button on initial render", () => {
      render(<HotInHereDemo />);

      expect(screen.getByText("Enter")).toBeInTheDocument();
    });

    it("entry screen has dark background initially", () => {
      render(<HotInHereDemo />);

      const container = screen.getByText("Enter").closest("div");
      expect(container).toHaveStyle({ background: "#000" });
    });

    it("changes background color on hover over Enter", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<HotInHereDemo />);

      const enterText = screen.getByText("Enter");

      await user.hover(enterText);

      // The hover state should change to orange/red
      const container = enterText.closest("div");
      expect(container).toHaveStyle({ background: "#ff4400" });
    });
  });

  describe("after entering", () => {
    it("shows main title after clicking Enter and waiting", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<HotInHereDemo />);

      await user.click(screen.getByText("Enter"));

      // Advance past the 2 second delay
      vi.advanceTimersByTime(3000);

      await waitFor(() => {
        expect(screen.getByText(/Hot In Here/i)).toBeInTheDocument();
      });
    });

    it("shows initial temperature of 0%", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<HotInHereDemo />);

      await user.click(screen.getByText("Enter"));
      vi.advanceTimersByTime(3000);

      await waitFor(() => {
        expect(screen.getByText("0%")).toBeInTheDocument();
      });
    });

    it("shows initial subtitle about heat", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<HotInHereDemo />);

      await user.click(screen.getByText("Enter"));
      vi.advanceTimersByTime(3000);

      await waitFor(() => {
        expect(screen.getByText("So hot.")).toBeInTheDocument();
      });
    });

    it("shows Status Report section", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<HotInHereDemo />);

      await user.click(screen.getByText("Enter"));
      vi.advanceTimersByTime(3000);

      await waitFor(() => {
        expect(screen.getByText("Status Report")).toBeInTheDocument();
      });
    });

    it("shows Heat Index section", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<HotInHereDemo />);

      await user.click(screen.getByText("Enter"));
      vi.advanceTimersByTime(3000);

      await waitFor(() => {
        expect(screen.getByText("Heat Index")).toBeInTheDocument();
      });
    });

    it("temperature increases over time", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<HotInHereDemo />);

      await user.click(screen.getByText("Enter"));
      vi.advanceTimersByTime(3000);

      // Wait for initial render
      await waitFor(() => {
        expect(screen.getByText("0%")).toBeInTheDocument();
      });

      // Advance time to let temperature rise (temp rises 0.5 every 200ms)
      vi.advanceTimersByTime(2000);

      await waitFor(() => {
        expect(screen.queryByText("0%")).not.toBeInTheDocument();
      });
    });
  });
});
