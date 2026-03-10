import { useCallback } from "react";

export function useUrlState() {
  // Parse initial frame from URL
  const getInitialFrame = useCallback(() => {
    const params = new URLSearchParams(window.location.search);
    const frame = params.get("frame");
    if (frame) {
      const parsed = parseInt(frame, 10);
      if (!isNaN(parsed) && parsed >= 0) {
        return parsed;
      }
    }
    return null; // null means "use default" (latest frame)
  }, []);

  // Parse initial tags from URL (comma-separated)
  const getInitialTags = useCallback(() => {
    const params = new URLSearchParams(window.location.search);
    const tags = params.get("tags");
    if (tags) {
      return tags
        .split(",")
        .map((t) => t.trim().toLowerCase())
        .filter(Boolean);
    }
    return [];
  }, []);

  // Update URL without adding history entry
  const updateUrl = useCallback((frame, tags = []) => {
    const url = new URL(window.location.href);
    if (frame !== null && frame !== undefined) {
      url.searchParams.set("frame", frame.toString());
    } else {
      url.searchParams.delete("frame");
    }
    if (tags && tags.length > 0) {
      url.searchParams.set("tags", tags.join(","));
    } else {
      url.searchParams.delete("tags");
    }
    window.history.replaceState({}, "", url.toString());
  }, []);

  return { getInitialFrame, getInitialTags, updateUrl };
}
