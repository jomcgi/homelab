import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SexyBackDemo from "./SexyBackDemo";

describe("SexyBackDemo", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("entry screen", () => {
    it("shows Enter button on initial render", () => {
      render(<SexyBackDemo />);

      expect(screen.getByText("Enter")).toBeInTheDocument();
    });

    it("entry screen has dark background initially", () => {
      render(<SexyBackDemo />);

      const container = screen.getByText("Enter").closest("div");
      expect(container).toHaveStyle({ background: "#000" });
    });

    it("changes background on hover over Enter", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<SexyBackDemo />);

      const enterText = screen.getByText("Enter");

      await user.hover(enterText);

      // The hover state should invert colors
      expect(enterText).toHaveStyle({ color: "#000" });
    });
  });

  describe("after entering", () => {
    it("shows main content after clicking Enter and waiting", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<SexyBackDemo />);

      await user.click(screen.getByText("Enter"));

      // Advance past the 5 second delay
      vi.advanceTimersByTime(6000);

      await waitFor(() => {
        expect(screen.getByText("The JT Archives")).toBeInTheDocument();
      });
    });

    it("shows Invert button after entering", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<SexyBackDemo />);

      await user.click(screen.getByText("Enter"));
      vi.advanceTimersByTime(6000);

      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /invert/i }),
        ).toBeInTheDocument();
      });
    });

    it("shows section headers", async () => {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      render(<SexyBackDemo />);

      await user.click(screen.getByText("Enter"));
      vi.advanceTimersByTime(6000);

      await waitFor(() => {
        expect(screen.getByText(/SexyBack/)).toBeInTheDocument();
        expect(screen.getByText(/NSYNC Era/)).toBeInTheDocument();
      });
    });
  });
});
