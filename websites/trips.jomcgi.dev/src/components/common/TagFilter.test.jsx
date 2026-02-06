import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TagFilter } from "./TagFilter";

describe("TagFilter", () => {
  const availableTags = ["hiking", "camping", "city"];

  it("returns null when no tags are available", () => {
    const { container } = render(
      <TagFilter
        availableTags={[]}
        selectedTags={[]}
        onTagsChange={() => {}}
      />,
    );

    expect(container.firstChild).toBeNull();
  });

  it("renders all available tags in desktop mode", () => {
    render(
      <TagFilter
        availableTags={availableTags}
        selectedTags={[]}
        onTagsChange={() => {}}
      />,
    );

    availableTags.forEach((tag) => {
      expect(screen.getByRole("button", { name: tag })).toBeInTheDocument();
    });
  });

  it("highlights selected tags", () => {
    render(
      <TagFilter
        availableTags={availableTags}
        selectedTags={["hiking"]}
        onTagsChange={() => {}}
      />,
    );

    const hikingButton = screen.getByRole("button", { name: "hiking" });
    expect(hikingButton).toHaveClass("bg-blue-500", "text-white");
  });

  it("calls onTagsChange to add a tag when clicking an unselected tag", async () => {
    const user = userEvent.setup();
    const handleTagsChange = vi.fn();

    render(
      <TagFilter
        availableTags={availableTags}
        selectedTags={[]}
        onTagsChange={handleTagsChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: "hiking" }));

    expect(handleTagsChange).toHaveBeenCalledWith(["hiking"]);
  });

  it("calls onTagsChange to remove a tag when clicking a selected tag", async () => {
    const user = userEvent.setup();
    const handleTagsChange = vi.fn();

    render(
      <TagFilter
        availableTags={availableTags}
        selectedTags={["hiking", "camping"]}
        onTagsChange={handleTagsChange}
      />,
    );

    await user.click(screen.getByRole("button", { name: "hiking" }));

    expect(handleTagsChange).toHaveBeenCalledWith(["camping"]);
  });

  it("shows clear button when tags are selected", () => {
    render(
      <TagFilter
        availableTags={availableTags}
        selectedTags={["hiking"]}
        onTagsChange={() => {}}
      />,
    );

    expect(screen.getByTitle("Clear filters")).toBeInTheDocument();
  });

  it("clears all tags when clear button is clicked", async () => {
    const user = userEvent.setup();
    const handleTagsChange = vi.fn();

    render(
      <TagFilter
        availableTags={availableTags}
        selectedTags={["hiking", "camping"]}
        onTagsChange={handleTagsChange}
      />,
    );

    await user.click(screen.getByTitle("Clear filters"));

    expect(handleTagsChange).toHaveBeenCalledWith([]);
  });

  describe("mobile mode", () => {
    it("renders a compact filter button in mobile mode", () => {
      render(
        <TagFilter
          availableTags={availableTags}
          selectedTags={[]}
          onTagsChange={() => {}}
          isMobile={true}
        />,
      );

      expect(screen.getByTitle("Filter by tags")).toBeInTheDocument();
    });

    it("shows badge count when tags are selected in mobile mode", () => {
      render(
        <TagFilter
          availableTags={availableTags}
          selectedTags={["hiking", "camping"]}
          onTagsChange={() => {}}
          isMobile={true}
        />,
      );

      expect(screen.getByText("2")).toBeInTheDocument();
    });

    it("opens dropdown when filter button is clicked in mobile mode", async () => {
      const user = userEvent.setup();

      render(
        <TagFilter
          availableTags={availableTags}
          selectedTags={[]}
          onTagsChange={() => {}}
          isMobile={true}
        />,
      );

      await user.click(screen.getByTitle("Filter by tags"));

      availableTags.forEach((tag) => {
        expect(screen.getByRole("button", { name: tag })).toBeInTheDocument();
      });
    });
  });
});
