import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ViewToggle } from "./ViewToggle";

describe("ViewToggle", () => {
  it("renders both Photo and Map buttons", () => {
    render(<ViewToggle activeView="image" onViewChange={() => {}} />);

    expect(screen.getByRole("button", { name: /photo/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /map/i })).toBeInTheDocument();
  });

  it("highlights the active Photo view", () => {
    render(<ViewToggle activeView="image" onViewChange={() => {}} />);

    const photoButton = screen.getByRole("button", { name: /photo/i });
    expect(photoButton).toHaveClass("bg-blue-500", "text-white");
  });

  it("highlights the active Map view", () => {
    render(<ViewToggle activeView="map" onViewChange={() => {}} />);

    const mapButton = screen.getByRole("button", { name: /map/i });
    expect(mapButton).toHaveClass("bg-blue-500", "text-white");
  });

  it("calls onViewChange with 'image' when Photo button is clicked", async () => {
    const user = userEvent.setup();
    const handleViewChange = vi.fn();

    render(<ViewToggle activeView="map" onViewChange={handleViewChange} />);

    await user.click(screen.getByRole("button", { name: /photo/i }));

    expect(handleViewChange).toHaveBeenCalledWith("image");
  });

  it("calls onViewChange with 'map' when Map button is clicked", async () => {
    const user = userEvent.setup();
    const handleViewChange = vi.fn();

    render(<ViewToggle activeView="image" onViewChange={handleViewChange} />);

    await user.click(screen.getByRole("button", { name: /map/i }));

    expect(handleViewChange).toHaveBeenCalledWith("map");
  });
});
